from pathlib import Path
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from webmedia_dl.continuity import companion_message, validate_companion_message
from webmedia_dl.domain.enums import IntakeKind, JobState, Surface
from webmedia_dl.errors import ProviderPolicyError
from webmedia_dl.intake import normalize_source
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.providers import ProviderRuntime
from webmedia_dl.service import create_app, load_or_create_token


def test_companion_message_rejects_native_command_and_argv() -> None:
    payload = companion_message("capture", locator="https://cdn.example.com/a.mp4")
    assert payload["nativeCommand"] is None
    assert payload["subprocessWorker"] is False
    with pytest.raises(ProviderPolicyError):
        validate_companion_message(
            {"kind": "capture", "locator": "https://x", "nativeCommand": "yt-dlp"}
        )
    with pytest.raises(ProviderPolicyError):
        validate_companion_message(
            {"kind": "capture", "locator": "https://x", "providerArgv": ["-f"]}
        )
    with pytest.raises(ProviderPolicyError):
        validate_companion_message(
            {"kind": "capture", "subprocessWorker": True, "locator": "https://x"}
        )
    with pytest.raises(ProviderPolicyError):
        companion_message("explode")
    with pytest.raises(ProviderPolicyError):
        validate_companion_message({"kind": "status", "ffmpeg": "-i"})
    with pytest.raises(ProviderPolicyError):
        validate_companion_message({"kind": "capture"})
    with pytest.raises(ProviderPolicyError):
        validate_companion_message({"kind": "cancel"})
    with pytest.raises(ProviderPolicyError, match="job UUID"):
        validate_companion_message({"kind": "cancel", "job_id": "not-a-uuid"})
    with pytest.raises(ProviderPolicyError, match="job UUID"):
        validate_companion_message({"kind": "pause_job", "jobId": "also-not"})
    with pytest.raises(ProviderPolicyError):
        validate_companion_message({"kind": "status", "locator": 1})
    fallback = validate_companion_message({"kind": "status", "surface": "not-a-surface"})
    assert fallback["surface"] == "watchos"
    cancel = companion_message("cancel", job_id="11111111-1111-1111-1111-111111111111")
    assert cancel["job_id"]


def test_mac_companion_capture_is_host_owned(tmp_data: Path, png_bytes: bytes) -> None:
    runtime = ProviderRuntime(http_get=lambda url: (200, {}, png_bytes))
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    result = pipeline.handle_companion(
        {"kind": "capture", "locator": "https://cdn.example.com/hero.png", "surface": "watchos"}
    )
    job = pipeline.job(UUID(result["job"]["job_id"]))
    assert job.source.surface is Surface.WATCHOS
    assert job.policy_profile_id == "personal-full"
    assert job.state is JobState.ACCEPTED
    ran = pipeline.run_next()
    assert ran is not None
    assert ran.state is JobState.COMPLETED


def test_mixed_media_one_kind_failure_still_publishes_other(
    tmp_data: Path, png_bytes: bytes
) -> None:
    html = """
    <html><body>
      <video src="https://cdn.example.com/clip.mp4"></video>
      <img src="https://cdn.example.com/hero.png">
    </body></html>
    """

    def http_get(url: str) -> tuple[int, dict[str, str], bytes]:
        if url.endswith(".mp4"):
            return 500, {}, b"no"
        return 200, {}, png_bytes

    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(which=lambda _name: None, http_get=http_get),
    )
    job = pipeline.submit("https://example.com/mixed", html=html)
    assert job.state is JobState.COMPLETED
    kinds = {
        item.media_kind.value
        for item in pipeline.store.list_artifacts()
        if item.role.value == "source"
    }
    assert "image" in kinds
    completed = next(
        item for item in pipeline.queue.events_for(job.job_id) if item.type.value == "job.completed"
    )
    assert completed.payload["partial"] is True
    assert "video" in completed.payload["failed_kinds"]


def test_pause_during_acquire_checkpoints_and_resume_skips_done_kind(
    tmp_data: Path, png_bytes: bytes
) -> None:
    html = """
    <html><body>
      <video src="https://cdn.example.com/clip.mp4"></video>
      <img src="https://cdn.example.com/hero.png">
    </body></html>
    """
    pipeline_holder: dict[str, Pipeline] = {}
    job_holder: dict[str, UUID] = {}

    def http_get(url: str) -> tuple[int, dict[str, str], bytes]:
        pipeline = pipeline_holder["p"]
        job_id = job_holder["id"]
        if url.endswith(".mp4"):
            pipeline.pause_job(job_id)
            return 200, {}, b"fake-mp4-bytes"
        return 200, {}, png_bytes

    pipeline = Pipeline(data_dir=tmp_data, runtime=ProviderRuntime(http_get=http_get))
    pipeline_holder["p"] = pipeline
    job = pipeline.submit("https://example.com/mixed", html=html, wait=False)
    job_holder["id"] = job.job_id
    paused = pipeline.run_next()
    assert paused is not None
    assert paused.state is JobState.PAUSED
    checkpoint = pipeline.queue.get_context(job.job_id).checkpoint
    assert checkpoint.get("source_ids")
    resumed = pipeline.resume_job(job.job_id)
    assert resumed.state is JobState.COMPLETED
    sources = [item for item in pipeline.store.list_artifacts() if item.role.value == "source"]
    assert len(sources) >= 2


def test_drop_intake_kind(tmp_path: Path, png_bytes: bytes) -> None:
    media = tmp_path / "dropped.png"
    media.write_bytes(png_bytes)
    source = normalize_source(
        str(media),
        surface=Surface.CLI,
        policy_profile_id="personal-full",
        kind=IntakeKind.DROP,
    )
    assert source.kind is IntakeKind.DROP
    assert source.local_path == str(media.resolve())


def test_companion_endpoint_requires_mac_actor(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app)
    denied = client.post("/v1/companion", json={"kind": "status"})
    assert denied.status_code == 401
    ok = client.post(
        "/v1/companion",
        json={"kind": "status"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok.status_code == 200
    assert ok.json()["paused"] is False
    argv = client.post(
        "/v1/companion",
        json={"kind": "capture", "locator": "https://x", "nativeCommand": "/bin/sh"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert argv.status_code == 400
    history = client.post(
        "/v1/companion",
        json={"kind": "history"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert history.status_code == 200
    assert history.json()["kind"] == "history"
    pause = client.post(
        "/v1/companion",
        json={"kind": "pause"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert pause.json()["paused"] is True
    client.post(
        "/v1/companion",
        json={"kind": "resume"},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_companion_pause_and_resume_job(tmp_path: Path, png_bytes: bytes) -> None:
    pipeline = Pipeline(data_dir=tmp_path / "worker-data")
    media = tmp_path / "held.png"
    media.write_bytes(png_bytes)
    job = pipeline.submit(str(media), wait=False)
    paused = pipeline.handle_companion(
        {
            "kind": "pause_job",
            "job_id": str(job.job_id),
            "nativeCommand": None,
            "subprocessWorker": False,
        }
    )
    assert paused["kind"] == "pause_job"
    assert paused["job"]["state"] == "paused"
    resumed = pipeline.handle_companion(
        {
            "kind": "resume_job",
            "job_id": str(job.job_id),
            "nativeCommand": None,
            "subprocessWorker": False,
        }
    )
    assert resumed["kind"] == "resume_job"
    assert resumed["job"]["state"] in {"accepted", "completed", "failed"}


def test_companion_accepts_sealed_pairing_envelope(tmp_path: Path) -> None:
    from webmedia_dl.envelope import seal_payload

    app = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post("/v1/pair", headers=headers)
    pairing_id = created.json()["pairing_id"]
    confirmed = client.post("/v1/pair/confirm", headers=headers, json={"pairing_id": pairing_id})
    session_key = confirmed.json()["session_key"]
    sealed = seal_payload(
        session_key,
        {"kind": "status", "nativeCommand": None, "subprocessWorker": False},
    )
    ok = client.post(
        "/v1/companion",
        json={"pairing_id": pairing_id, "session_key": session_key, **sealed},
        headers=headers,
    )
    assert ok.status_code == 200
    replay = client.post(
        "/v1/companion",
        json={"pairing_id": pairing_id, "session_key": session_key, **sealed},
        headers=headers,
    )
    assert replay.status_code == 401
    missing = client.post(
        "/v1/companion",
        json={"nonce": sealed["nonce"], "ciphertext": sealed["ciphertext"], "mac": sealed["mac"]},
        headers=headers,
    )
    assert missing.status_code == 400


def test_sealed_companion_cancel_requires_job_uuid(tmp_path: Path) -> None:
    from webmedia_dl.envelope import seal_payload

    app = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post("/v1/pair", headers=headers)
    pairing_id = created.json()["pairing_id"]
    confirmed = client.post("/v1/pair/confirm", headers=headers, json={"pairing_id": pairing_id})
    session_key = confirmed.json()["session_key"]
    sealed = seal_payload(
        session_key,
        {
            "kind": "cancel",
            "job_id": "not-a-uuid",
            "nativeCommand": None,
            "subprocessWorker": False,
        },
    )
    refused = client.post(
        "/v1/companion",
        json={"pairing_id": pairing_id, "session_key": session_key, **sealed},
        headers=headers,
    )
    assert refused.status_code == 400
    assert "uuid" in refused.json()["detail"].lower()


def test_companion_body_forbids_provider_argv(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    argv = client.post(
        "/v1/companion",
        headers=headers,
        json={"kind": "status", "providerArgv": ["yt-dlp", "--exec"]},
    )
    assert argv.status_code == 422
    cookies = client.post(
        "/v1/companion",
        headers=headers,
        json={"kind": "status", "cookies": "/tmp/cookies.txt"},
    )
    assert cookies.status_code == 422
