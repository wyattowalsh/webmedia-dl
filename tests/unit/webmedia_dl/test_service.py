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
    assert body["state"] in {"completed", "failed"}


def test_pair_loopback(tmp_path: Path) -> None:
    app = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app)
    response = client.post(
        "/v1/pair",
        headers={"Authorization": f"Bearer {token}"},
        params={"client_profile_id": "personal-restricted"},
    )
    assert response.status_code == 200
    assert "nonce" in response.json()
