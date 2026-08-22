from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from webmedia_dl.errors import WebMediaError
from webmedia_dl.service import create_app, load_or_create_token


def test_health_is_public(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_pair_start_is_public_confirm_is_mac_owned(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    created = client.post("/v1/pair")
    assert created.status_code == 200
    body = created.json()
    assert body["confirmed"] is False
    assert body["pairing_id"]
    denied = client.post("/v1/pair/confirm", json={"pairing_id": body["pairing_id"]})
    assert denied.status_code == 401
    token = load_or_create_token(tmp_path)
    confirmed = client.post(
        "/v1/pair/confirm",
        headers={"Authorization": f"Bearer {token}"},
        json={"pairing_id": body["pairing_id"]},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["confirmed"] is True
    assert confirmed.json()["session_key"]
    later = client.post("/v1/pair").json()
    paired_confirm = client.post(
        "/v1/pair/confirm",
        headers={
            "X-WebMedia-Pairing": body["pairing_id"],
            "X-WebMedia-Session": confirmed.json()["session_key"],
        },
        json={"pairing_id": later["pairing_id"]},
    )
    assert paired_confirm.status_code == 403


def test_jobs_require_auth(tmp_path: Path, png_bytes: bytes) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    denied = client.post("/v1/jobs", json={"locator": "https://cdn.example.com/a.png"})
    assert denied.status_code == 401
    token = load_or_create_token(tmp_path)
    media = tmp_path / "a.png"
    media.write_bytes(png_bytes)
    ok = client.post(
        "/v1/jobs",
        json={"locator": str(media)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["job"]["state"] in {"completed", "failed"}
    assert body["events"]


def test_pair_and_envelope_and_plan(tmp_path: Path, png_bytes: bytes) -> None:
    app = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    created = client.post("/v1/pair", headers=headers)
    assert created.status_code == 200
    typed = client.post(
        "/v1/pair",
        headers=headers,
        json={"client_profile_id": "personal-restricted"},
    )
    assert typed.status_code == 200
    pairing_id = created.json()["pairing_id"]
    confirmed = client.post("/v1/pair/confirm", headers=headers, json={"pairing_id": pairing_id})
    session_key = confirmed.json()["session_key"]
    sealed = client.post(
        "/v1/pair/envelope",
        headers=headers,
        json={"pairing_id": pairing_id, "session_key": session_key, "payload": {"ok": True}},
    )
    assert sealed.status_code == 200
    opened = client.post(
        "/v1/pair/envelope/open",
        headers=headers,
        json={"pairing_id": pairing_id, "session_key": session_key, **sealed.json()},
    )
    assert opened.json() == {"ok": True}
    replay = client.post(
        "/v1/pair/envelope/open",
        headers=headers,
        json={"pairing_id": pairing_id, "session_key": session_key, **sealed.json()},
    )
    assert replay.status_code == 401
    media = tmp_path / "a.png"
    media.write_bytes(png_bytes)
    planned = client.post(
        "/v1/plan",
        headers=headers,
        json={"locator": str(media)},
    )
    assert planned.status_code == 200
    assert planned.json()["acquired"] is False
    artifacts = client.get("/v1/artifacts", headers=headers)
    assert artifacts.status_code == 200
    doctor = client.get("/v1/doctor", headers=headers)
    assert doctor.status_code == 200
    assert doctor.json()["telemetry_default"] is False
    support = client.get("/v1/support-bundle", headers=headers)
    assert support.status_code == 200
    assert support.json()["telemetry"] is False
    queue = client.get("/v1/queue", headers=headers)
    assert queue.status_code == 200
    assert queue.json()["paused"] is False
    paused = client.post("/v1/queue/pause", headers=headers)
    assert paused.json()["paused"] is True
    client.post("/v1/queue/resume", headers=headers)


def test_job_detail_companion_and_provenance(tmp_path: Path, png_bytes: bytes) -> None:
    app = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    media = tmp_path / "a.png"
    media.write_bytes(png_bytes)
    created = client.post("/v1/jobs", json={"locator": str(media)}, headers=headers)
    job_id = created.json()["job"]["job_id"]
    detail = client.get(f"/v1/jobs/{job_id}", headers=headers)
    assert detail.status_code == 200
    assert "artifact_ids" in detail.json()
    missing = client.get("/v1/jobs/00000000-0000-0000-0000-000000000000", headers=headers)
    assert missing.status_code == 404
    artifacts = client.get("/v1/artifacts", headers=headers).json()
    proven = client.get(
        f"/v1/artifacts/{artifacts[0]['artifact_id']}/provenance",
        headers=headers,
    )
    assert proven.status_code == 200
    unknown = client.get("/v1/artifacts/sha256:nope/provenance", headers=headers)
    assert unknown.status_code == 404
    companion = client.post(
        "/v1/companion",
        headers=headers,
        json={"kind": "status", "nativeCommand": None, "subprocessWorker": False},
    )
    assert companion.status_code == 200
    assert companion.json()["paused"] is False
    cancelled = client.post(f"/v1/jobs/{job_id}/cancel", headers=headers)
    assert cancelled.status_code == 400
    nxt = client.post("/v1/queue/run-next", headers=headers)
    assert nxt.status_code == 200


def test_pause_and_resume_job_endpoints(tmp_path: Path, png_bytes: bytes) -> None:
    app = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    media = tmp_path / "held.png"
    media.write_bytes(png_bytes)
    created = client.post(
        "/v1/jobs",
        json={"locator": str(media), "wait": False},
        headers=headers,
    )
    job_id = created.json()["job"]["job_id"]
    paused = client.post(f"/v1/jobs/{job_id}/pause", headers=headers)
    assert paused.status_code == 200
    assert paused.json()["state"] == "paused"
    resumed = client.post(f"/v1/jobs/{job_id}/resume", headers=headers)
    assert resumed.status_code == 200
    assert resumed.json()["state"] in {"completed", "failed", "accepted"}


def test_lifespan_starts_dispatcher(tmp_path: Path) -> None:
    app = create_app(tmp_path, enable_dispatcher=True)
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_sealed_companion_requires_pairing(tmp_path: Path) -> None:
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
    missing_key = client.post(
        "/v1/companion",
        json={"pairing_id": pairing_id, **sealed},
        headers=headers,
    )
    assert missing_key.status_code == 400
    assert "confirmed pairing" in missing_key.json()["detail"]


def test_share_and_intent_loopback_payloads_reject_native_command(
    tmp_path: Path, png_bytes: bytes
) -> None:
    app = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    media = tmp_path / "shared.png"
    media.write_bytes(png_bytes)
    share = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "locator": "https://cdn.example.com/a.mp4",
            "surface": "ios",
            "local_user_confirmed": True,
            "evidence": [],
            "wait": False,
            "intake_kind": "share_sheet",
        },
    )
    assert share.status_code == 200, share.text
    assert share.json()["job"]["source"]["kind"] == "share_sheet"
    assert share.json()["job"]["source"]["local_path"] is None
    intent = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "locator": "https://cdn.example.com/b.mp4",
            "surface": "ios",
            "local_user_confirmed": True,
            "wait": False,
            "intake_kind": "intent",
        },
    )
    assert intent.status_code == 200, intent.text
    assert intent.json()["job"]["source"]["kind"] == "intent"
    dropped = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "locator": str(media),
            "surface": "ios",
            "local_user_confirmed": True,
            "wait": True,
            "intake_kind": "drop",
        },
    )
    assert dropped.status_code == 200, dropped.text
    assert dropped.json()["job"]["source"]["kind"] == "drop"
    argv = client.post(
        "/v1/jobs",
        headers=headers,
        json={"locator": str(media), "surface": "ios", "nativeCommand": "yt-dlp"},
    )
    assert argv.status_code == 422
    extra = client.post(
        "/v1/jobs",
        headers=headers,
        json={"locator": str(media), "providerArgv": ["--format"]},
    )
    assert extra.status_code == 422
    hostile = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "locator": str(media),
            "intent": {"container_preference": "../../../../tmp/escape"},
        },
    )
    assert hostile.status_code == 422
    hostile_plan = client.post(
        "/v1/plan",
        headers=headers,
        json={
            "locator": str(media),
            "intent": {"container_preference": "mkv; rm -rf /"},
        },
    )
    assert hostile_plan.status_code == 422
    companion = client.post(
        "/v1/companion",
        headers=headers,
        json={
            "kind": "capture",
            "locator": "https://example.com/a.mp4",
            "nativeCommand": "yt-dlp",
            "subprocessWorker": False,
        },
    )
    assert companion.status_code == 400


def test_control_and_pair_bodies_forbid_native_runner(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    extra_pair = client.post(
        "/v1/pair",
        headers=headers,
        json={"client_profile_id": "personal-restricted", "nativeCommand": "yt-dlp"},
    )
    assert extra_pair.status_code == 422
    native_pause = client.post(
        "/v1/queue/pause",
        headers=headers,
        json={"nativeCommand": "yt-dlp"},
    )
    assert native_pause.status_code == 422
    empty_native = client.post(
        "/v1/queue/pause",
        headers=headers,
        json={"nativeCommand": ""},
    )
    assert empty_native.status_code == 200
    assert empty_native.json()["paused"] is True
    client.post("/v1/queue/resume", headers=headers)
    subprocess_resume = client.post(
        "/v1/queue/resume",
        headers=headers,
        json={"subprocessWorker": True},
    )
    assert subprocess_resume.status_code == 422


def test_empty_worker_token_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "worker.token"
    path.write_text(" \n", encoding="utf-8")
    with pytest.raises(WebMediaError, match="empty"):
        load_or_create_token(tmp_path)


def test_existing_worker_token_is_mode_600(tmp_path: Path) -> None:
    path = tmp_path / "worker.token"
    path.write_text("token-value", encoding="utf-8")
    path.chmod(0o644)
    assert load_or_create_token(tmp_path) == "token-value"
    assert path.stat().st_mode & 0o777 == 0o600
