import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

from webmedia_dl.compat import migrate_legacy, scan_legacy
from webmedia_dl.transport import create_challenge, derive_session_key, expired


def test_legacy_scan_is_non_destructive(tmp_path: Path) -> None:
    marker = tmp_path / "yt-dlp-archive.txt"
    marker.write_text("# comment\nid-one\nid-two\n", encoding="utf-8")
    extra = tmp_path / "nested" / "yt-dlp-archive.txt"
    extra.parent.mkdir()
    extra.write_text('["json-one", "json-two"]\n', encoding="utf-8")
    report = scan_legacy(tmp_path)
    assert "yt-dlp-archive.txt" in report["markers"]
    assert report["destructive"] is False
    applied = migrate_legacy(tmp_path, apply=True)
    assert applied["migrated"] is True
    assert marker.read_text(encoding="utf-8") == "# comment\nid-one\nid-two\n"
    sidecar = json.loads((tmp_path / "webmedia-dl-migrated" / "migration.json").read_text())
    assert sidecar["version"] == 1
    ids = [tuple(item["ids"]) for item in sidecar["archives"]]
    assert ("id-one", "id-two") in ids
    assert ("json-one", "json-two") in ids
    assert applied["index_entries"] == 4


def test_pairing_expiry() -> None:
    challenge = create_challenge("personal-restricted", "local-macos", ttl_seconds=1)
    assert expired(challenge, now=challenge.expires_at + timedelta(seconds=1)) is True
    assert expired(challenge, now=datetime.now(UTC) - timedelta(seconds=5)) is False


def test_derive_session_key_is_sha256_nonce_mac_confirm() -> None:
    assert (
        derive_session_key("pairing-nonce", "mac-confirm")
        == sha256(b"pairing-nonce:mac-confirm").hexdigest()
    )
    assert (
        derive_session_key("pairing-nonce", "mac-confirm")
        == "bc863f6d9e1fc62a49c474506a660ac0a6f44a19d97e41348d3a2e682c1cdf63"
    )
