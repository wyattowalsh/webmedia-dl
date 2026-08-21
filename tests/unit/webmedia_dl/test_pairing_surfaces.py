from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from webmedia_dl.domain.enums import JobState, Surface
from webmedia_dl.errors import DelegationDenied
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.providers import ProviderRuntime
from webmedia_dl.service import create_app, load_or_create_token


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


def test_pairing_confirmation_lets_mac_own_ytdlp(tmp_data: Path) -> None:
    captured: list[list[str]] = []

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        captured.append(argv)
        Path(argv[argv.index("--output") + 1]).write_bytes(b"video-bytes")
        return 0, b"", b""

    runtime = ProviderRuntime(
        which=lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None,
        run=run,
        http_get=lambda url: (200, {}, b"nope"),
    )
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    challenge = pipeline.pairing.create("personal-restricted", pipeline.host_worker.worker_id)
    record = pipeline.pairing.confirm(challenge.pairing_id)
    job = pipeline.submit(
        "https://example.com/watch",
        html="<html><title>Video</title></html>",
        surface=Surface.IOS,
        pairing_id=challenge.pairing_id,
        session_key=record.session_key,
    )
    assert job.state is JobState.COMPLETED
    assert captured
    assert job.policy_profile_id == "personal-full"


def test_unconfirmed_pairing_does_not_escalate(tmp_data: Path) -> None:
    pipeline = Pipeline(data_dir=tmp_data)
    challenge = pipeline.pairing.create("personal-restricted", pipeline.host_worker.worker_id)
    with pytest.raises(DelegationDenied):
        pipeline.submit(
            "https://example.com/watch",
            html="<html><title>Video</title></html>",
            surface=Surface.IOS,
            pairing_id=UUID(str(challenge.pairing_id)),
        )


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
