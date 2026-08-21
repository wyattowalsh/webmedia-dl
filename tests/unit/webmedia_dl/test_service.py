from pathlib import Path

from fastapi.testclient import TestClient

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
