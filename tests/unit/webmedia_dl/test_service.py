from pathlib import Path

from fastapi.testclient import TestClient

from webmedia_dl.service import create_app, load_or_create_token


def test_health_is_public(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


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
    doctor = client.get("/v1/doctor", headers=headers)
    assert doctor.status_code == 200
    assert doctor.json()["telemetry_default"] is False
