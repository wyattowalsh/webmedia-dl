from datetime import UTC, datetime, timedelta
from pathlib import Path

from webmedia_dl.compat import migrate_legacy, scan_legacy
from webmedia_dl.transport import create_challenge, expired


def test_legacy_scan_is_non_destructive(tmp_path: Path) -> None:
    marker = tmp_path / "yt-dlp-archive.txt"
    marker.write_text("id\n", encoding="utf-8")
    report = scan_legacy(tmp_path)
    assert "yt-dlp-archive.txt" in report["markers"]
    assert report["destructive"] is False
    applied = migrate_legacy(tmp_path, apply=True)
    assert applied["migrated"] is True
    assert marker.read_text(encoding="utf-8") == "id\n"
    assert (tmp_path / "webmedia-dl-migrated" / "migration.json").is_file()


def test_pairing_expiry() -> None:
    challenge = create_challenge("personal-restricted", "local-macos", ttl_seconds=1)
    assert expired(challenge, now=challenge.expires_at + timedelta(seconds=1)) is True
    assert expired(challenge, now=datetime.now(UTC) - timedelta(seconds=5)) is False
