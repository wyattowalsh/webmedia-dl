from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from webmedia_dl.domain.enums import JobState, Surface
from webmedia_dl.errors import DelegationDenied
from webmedia_dl.pairing import PairingStore
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.providers import ProviderRuntime
from webmedia_dl.service import create_app, load_or_create_token
from webmedia_dl.transport import derive_session_key


def test_watch_surface_cannot_acquire_http(tmp_data: Path, png_bytes: bytes) -> None:
    runtime = ProviderRuntime(http_get=lambda url: (200, {}, png_bytes))
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit("https://cdn.example.com/hero.png", surface=Surface.WATCHOS)
    assert job.state is JobState.FAILED
    assert job.error is not None


def test_ios_can_http_but_not_ytdlp_page(tmp_data: Path) -> None:
    runtime = ProviderRuntime(http_get=lambda url: (200, {}, b"<html></html>"))
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit(
        "https://example.com/watch", html="<html><title>x</title></html>", surface=Surface.IOS
    )
    assert job.state is JobState.FAILED
    assert job.error is not None


def test_ios_http_direct_image(tmp_data: Path, png_bytes: bytes) -> None:
    runtime = ProviderRuntime(http_get=lambda url: (200, {}, png_bytes))
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit("https://cdn.example.com/hero.png", surface=Surface.IOS)
    assert job.state is JobState.COMPLETED


@pytest.mark.parametrize("surface", [Surface.IPADOS, Surface.VISIONOS])
def test_complete_mobile_clients_http_direct_image(
    tmp_data: Path, png_bytes: bytes, surface: Surface
) -> None:
    runtime = ProviderRuntime(http_get=lambda url: (200, {}, png_bytes))
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit("https://cdn.example.com/hero.png", surface=surface)
    assert job.state is JobState.COMPLETED


def test_pairing_confirmation_lets_mac_own_without_widening(tmp_data: Path, ytdlp_run_ok) -> None:
    captured: list[list[str]] = []

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        captured.append(argv)
        return ytdlp_run_ok(argv, _cwd)

    runtime = ProviderRuntime(
        which=lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None,
        run=run,
        http_get=lambda url: (200, {}, b"nope"),
    )
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    challenge = pipeline.pairing.create("personal-restricted", pipeline.host_worker.worker_id)
    record = pipeline.pairing.confirm(challenge.pairing_id)
    assert record.session_key == derive_session_key(challenge.nonce, "mac-confirm")
    job = pipeline.submit(
        "https://example.com/watch",
        html="<html><title>Video</title></html>",
        surface=Surface.IOS,
        pairing_id=challenge.pairing_id,
        session_key=record.session_key,
    )
    assert job.worker_id == pipeline.host_worker.worker_id
    assert job.policy_profile_id == "personal-restricted"
    assert job.state is JobState.COMPLETED
    assert any("--output" in argv for argv in captured)


def test_unconfirmed_pairing_does_not_escalate(tmp_data: Path) -> None:
    captured: list[list[str]] = []

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        captured.append(argv)
        raise AssertionError("unconfirmed pairing must not execute yt-dlp")

    runtime = ProviderRuntime(
        which=lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None,
        run=run,
        http_get=lambda url: (200, {}, b"nope"),
    )
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    challenge = pipeline.pairing.create("personal-restricted", pipeline.host_worker.worker_id)
    with pytest.raises(DelegationDenied):
        pipeline.submit(
            "https://example.com/watch",
            html="<html><title>Video</title></html>",
            surface=Surface.IOS,
            pairing_id=UUID(str(challenge.pairing_id)),
        )
    assert captured == []
    assert pipeline.history() == []


def test_service_confirm_and_paired_job(tmp_path: Path, png_bytes: bytes) -> None:
    app = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    challenge = client.post("/v1/pair", headers=headers).json()
    confirmed = client.post(
        "/v1/pair/confirm",
        headers=headers,
        json={"pairing_id": challenge["pairing_id"]},
    )
    assert confirmed.status_code == 200
    session = confirmed.json()["session_key"]
    media = tmp_path / "a.png"
    media.write_bytes(png_bytes)
    paired = client.post(
        "/v1/jobs",
        headers={
            "X-WebMedia-Pairing": challenge["pairing_id"],
            "X-WebMedia-Session": session,
        },
        json={"locator": str(media), "surface": "ios"},
    )
    assert paired.status_code == 200
    body = paired.json()
    assert body["job"]["state"] in {"completed", "failed"}
    assert body["events"]


def test_pairing_unknown_profile_and_expired_and_session_key(tmp_data: Path) -> None:
    pipeline = Pipeline(data_dir=tmp_data)
    with pytest.raises(DelegationDenied, match="Unknown client profile"):
        pipeline.pairing.create("not-a-profile", pipeline.host_worker.worker_id)
    challenge = pipeline.pairing.create("personal-restricted", pipeline.host_worker.worker_id)
    with pytest.raises(DelegationDenied, match="has not confirmed"):
        pipeline.pairing.require_confirmed(challenge.pairing_id, "preview")
    record = pipeline.pairing.confirm(challenge.pairing_id)
    with pytest.raises(DelegationDenied, match="session key is required"):
        pipeline.pairing.require_confirmed(challenge.pairing_id, session_key=None)
    with pytest.raises(DelegationDenied, match="does not match"):
        pipeline.pairing.require_confirmed(challenge.pairing_id, "wrong-key")
    pipeline.pairing.require_confirmed(challenge.pairing_id, record.session_key)
    expired = pipeline.pairing.get(challenge.pairing_id)
    assert expired is not None
    pipeline.pairing._records[str(challenge.pairing_id)] = expired.model_copy(
        update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
    )
    with pytest.raises(DelegationDenied, match="expired"):
        pipeline.pairing.require_confirmed(challenge.pairing_id, record.session_key)
    with pytest.raises(DelegationDenied, match="Unknown pairing"):
        pipeline.pairing.confirm(UUID("11111111-1111-1111-1111-111111111111"))
    stale = pipeline.pairing.create("browser-capture", pipeline.host_worker.worker_id)
    stale_record = pipeline.pairing.get(stale.pairing_id)
    assert stale_record is not None
    pipeline.pairing._records[str(stale.pairing_id)] = stale_record.model_copy(
        update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
    )
    with pytest.raises(DelegationDenied, match="expired"):
        pipeline.pairing.confirm(stale.pairing_id)


def test_pairing_store_prunes_expired_records(tmp_data: Path) -> None:
    pipeline = Pipeline(data_dir=tmp_data)
    challenge = pipeline.pairing.create("personal-restricted", pipeline.host_worker.worker_id)
    record = pipeline.pairing.get(challenge.pairing_id)
    assert record is not None
    pipeline.pairing._records[str(challenge.pairing_id)] = record.model_copy(
        update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
    )
    pipeline.pairing._save()
    reloaded = PairingStore(tmp_data / "pairing")
    assert reloaded.get(challenge.pairing_id) is None


def test_pairing_store_modes_are_owner_only(tmp_data: Path) -> None:
    pipeline = Pipeline(data_dir=tmp_data)
    challenge = pipeline.pairing.create("personal-restricted", pipeline.host_worker.worker_id)
    pipeline.pairing.confirm(challenge.pairing_id)
    pairing_dir = tmp_data / "pairing"
    assert pairing_dir.is_dir()
    assert pairing_dir.stat().st_mode & 0o777 == 0o700
    assert (pairing_dir / "pairing.json").stat().st_mode & 0o777 == 0o600
