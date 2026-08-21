"""Legacy command-layout migration. Never overwrites user archives silently."""

from __future__ import annotations

from pathlib import Path
from typing import Any

LEGACY_MARKERS = ("yt-dlp-archive.txt", "archive.txt", ".ytdlp-history.json")


def scan_legacy(root: Path) -> dict[str, Any]:
    found = [name for name in LEGACY_MARKERS if (root / name).exists()]
    extra = list(root.glob("**/yt-dlp-archive.txt"))
    return {
        "root": str(root),
        "markers": found,
        "extra_archives": [str(path) for path in extra],
        "migrated": False,
        "destructive": False,
    }


def migrate_legacy(root: Path, *, apply: bool = False) -> dict[str, Any]:
    report = scan_legacy(root)
    if not apply:
        report["status"] = "dry-run"
        return report
    dest = root / "webmedia-dl-migrated"
    dest.mkdir(parents=True, exist_ok=True)
    report["status"] = "copied-sidecar"
    report["migrated"] = True
    (dest / "migration.json").write_text(
        '{"note":"Legacy files were indexed, not rewritten."}\n',
        encoding="utf-8",
    )
    return report
