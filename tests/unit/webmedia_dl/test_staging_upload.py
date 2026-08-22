"""Complete-client drop staging on the Mac worker."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from webmedia_dl.domain.models import PolicyProfile
from webmedia_dl.errors import IntakeError
from webmedia_dl.identity import sha256_bytes
from webmedia_dl.policy.profiles import get_profile
from webmedia_dl.service import create_app, load_or_create_token
from webmedia_dl.staging import (
    assert_staging_size,
    declared_content_length,
    ingest_staged_upload,
    normalize_digest,
    safe_filename,
    staging_owner,
)


def test_staging_helpers_fail_closed() -> None:
    assert normalize_digest("sha256:" + "ab" * 32) == "ab" * 32
    with pytest.raises(IntakeError, match="64-character"):
        normalize_digest("not-a-digest")
    assert safe_filename("../secret.mp4") == "upload.bin"
    assert safe_filename("clip.mp4") == "clip.mp4"
    assert safe_filename("") == "upload.bin"
    assert safe_filename(".") == "upload.bin"
    assert safe_filename("..") == "upload.bin"
    assert safe_filename("dir\\clip.mp4") == "upload.bin"
    assert staging_owner("..") == "mac"
    assert staging_owner("  pairing-id  ") == "pairing-id"
    assert declared_content_length(None) is None
    assert declared_content_length("") is None
    assert declared_content_length("12") == 12
    with pytest.raises(IntakeError, match="Content-Length"):
        declared_content_length("nope")
    with pytest.raises(IntakeError, match="Content-Length"):
        declared_content_length("-1")
    with pytest.raises(IntakeError, match="byte bound"):
        assert_staging_size(declared=9, actual=1, max_bytes=8)
    with pytest.raises(IntakeError, match="byte bound"):
        assert_staging_size(declared=None, actual=9, max_bytes=8)
    assert_staging_size(declared=4, actual=4, max_bytes=8)


def test_ingest_staged_upload_verifies_digest_and_bounds(tmp_path: Path) -> None:
    payload = b"webmedia-dl-drop"
    digest = sha256_bytes(payload)
    first = ingest_staged_upload(
        data_dir=tmp_path,
        owner="11111111-1111-1111-1111-111111111111",
        expected_digest=digest,
        filename="clip.mp4",
        chunks=[payload],
        max_bytes=64,
    )
    path = Path(str(first["path"]))
    assert path.is_file()
    assert path.read_bytes() == payload
    assert first["sha256"] == digest
    assert first["bytes"] == len(payload)
    again = ingest_staged_upload(
        data_dir=tmp_path,
        owner="11111111-1111-1111-1111-111111111111",
        expected_digest=digest,
        filename="clip.mp4",
        chunks=[payload],
        max_bytes=64,
    )
    assert again["path"] == first["path"]
    with pytest.raises(IntakeError, match="empty"):
        ingest_staged_upload(
            data_dir=tmp_path,
            owner="mac",
            expected_digest=digest,
            filename="empty.bin",
            chunks=[b""],
            max_bytes=64,
        )
    with pytest.raises(IntakeError, match="byte bound"):
        ingest_staged_upload(
            data_dir=tmp_path,
            owner="mac",
            expected_digest=sha256_bytes(b"abcdef"),
            filename="big.bin",
            chunks=[b"abcdef"],
            max_bytes=4,
        )
    with pytest.raises(IntakeError, match="does not match"):
        ingest_staged_upload(
            data_dir=tmp_path,
            owner="mac",
            expected_digest=digest,
            filename="mismatch.bin",
            chunks=[b"other-bytes-here"],
            max_bytes=64,
        )
    with pytest.raises(IntakeError, match="positive byte bound"):
        ingest_staged_upload(
            data_dir=tmp_path,
            owner="mac",
            expected_digest=digest,
            filename="clip.mp4",
            chunks=[payload],
            max_bytes=0,
        )


def test_staging_upload_then_drop_job(
    tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = get_profile

    def tiny(profile_id: str) -> PolicyProfile:
        return original(profile_id).model_copy(update={"max_download_bytes": 8})

    monkeypatch.setattr("webmedia_dl.pipeline.get_profile", tiny)
    bounded = create_app(tmp_path / "bounded")
    bounded_client = TestClient(bounded)
    bounded_token = load_or_create_token(tmp_path / "bounded")
    overflow = bounded_client.post(
        "/v1/staging",
        headers={
            "Authorization": f"Bearer {bounded_token}",
            "X-WebMedia-Digest": sha256(png_bytes).hexdigest(),
            "X-WebMedia-Filename": "hero.png",
        },
        content=png_bytes,
    )
    assert overflow.status_code == 413
    monkeypatch.setattr("webmedia_dl.pipeline.get_profile", original)

    app = create_app(tmp_path)
    client = TestClient(app)
    token = load_or_create_token(tmp_path)
    mac = {"Authorization": f"Bearer {token}"}
    started = client.post("/v1/pair").json()
    confirmed = client.post(
        "/v1/pair/confirm",
        headers=mac,
        json={"pairing_id": started["pairing_id"]},
    )
    session = confirmed.json()["session_key"]
    paired = {
        "X-WebMedia-Pairing": started["pairing_id"],
        "X-WebMedia-Session": session,
    }
    digest = sha256(png_bytes).hexdigest()
    denied = client.post("/v1/staging", content=png_bytes)
    assert denied.status_code == 401
    missing = client.post("/v1/staging", headers=paired, content=png_bytes)
    assert missing.status_code == 400
    mismatch = client.post(
        "/v1/staging",
        headers={
            **paired,
            "X-WebMedia-Digest": "ab" * 32,
            "X-WebMedia-Filename": "../secret.mp4",
        },
        content=png_bytes,
    )
    assert mismatch.status_code == 400
    staged = client.post(
        "/v1/staging",
        headers={
            **paired,
            "X-WebMedia-Digest": digest,
            "X-WebMedia-Filename": "hero.png",
        },
        content=png_bytes,
    )
    assert staged.status_code == 200
    body = staged.json()
    staged_path = Path(body["path"])
    assert staged_path.is_file()
    assert tmp_path.resolve() in staged_path.resolve().parents
    assert "uploads" in staged_path.parts
    phone_path = "/private/var/mobile/Containers/Data/Application/dead/tmp/hero.png"
    doomed = client.post(
        "/v1/jobs",
        headers=paired,
        json={
            "locator": phone_path,
            "surface": "ios",
            "intake_kind": "drop",
            "wait": False,
            "local_user_confirmed": True,
            "pairing_id": started["pairing_id"],
            "session_key": session,
        },
    )
    assert doomed.status_code == 400
    created = client.post(
        "/v1/jobs",
        headers=paired,
        json={
            "locator": body["path"],
            "surface": "ios",
            "intake_kind": "drop",
            "wait": True,
            "local_user_confirmed": True,
            "pairing_id": started["pairing_id"],
            "session_key": session,
            "intent": {"destination_kind": "staging_only"},
        },
    )
    assert created.status_code == 200
    job = created.json()["job"]
    assert job["source"]["kind"] == "drop"
    assert job["source"]["local_path"] == body["path"]
    assert phone_path not in job["source"]["locator"]
    assert job["state"] in {"completed", "failed"}
    assert job["intent"]["destination_kind"] == "staging_only"
