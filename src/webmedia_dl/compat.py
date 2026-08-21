"""Legacy command-layout migration. Never overwrites user archives silently."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from webmedia_dl.identity import sha256_file

LEGACY_MARKERS = ("yt-dlp-archive.txt", "archive.txt", ".ytdlp-history.json")
SIDECAR_VERSION = 1


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
    archives = [_index_archive(path) for path in _archive_paths(report, root)]
    sidecar = {
        "version": SIDECAR_VERSION,
        "note": "Legacy files were indexed, not rewritten.",
        "archives": archives,
    }
    (dest / "migration.json").write_text(
        json.dumps(sidecar, indent=2) + "\n",
        encoding="utf-8",
    )
    report["status"] = "copied-sidecar"
    report["migrated"] = True
    report["index_entries"] = sum(len(item["ids"]) for item in archives)
    return report


def _archive_paths(report: dict[str, Any], root: Path) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for name in report["markers"]:
        path = (root / name).resolve()
        if path.is_file() and path not in seen:
            seen.add(path)
            paths.append(path)
    for extra in report["extra_archives"]:
        path = Path(str(extra)).resolve()
        if path.is_file() and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def _index_archive(path: Path) -> dict[str, Any]:
    digest = sha256_file(str(path))
    return {
        "source_path": str(path),
        "sha256": digest,
        "ids": _legacy_ids(path),
    }


def _legacy_ids(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8", errors="replace")
    stripped = text.strip()
    if stripped.startswith(("[", "{")):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, list):
            return [str(item) for item in payload if str(item).strip()]
        if isinstance(payload, dict):
            raw = payload.get("ids") or payload.get("download_archive") or []
            if isinstance(raw, list):
                return [str(item) for item in raw if str(item).strip()]
    ids: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        item = line.strip()
        if not item or item.startswith("#"):
            continue
        if item in seen:
            continue
        seen.add(item)
        ids.append(item)
    return ids
