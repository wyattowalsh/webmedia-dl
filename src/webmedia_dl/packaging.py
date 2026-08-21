"""Reproducible local packaging. Never uploads stores or auto-installs providers."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path
from typing import Any

from webmedia_dl.paths import repo_root

BROWSERS = ("chromium", "chrome", "brave", "edge", "firefox", "safari")
FIXED_ZIP_TIME = (2026, 8, 18, 0, 0, 0)


def write_extension_zips(*, dest_root: Path | None = None) -> list[dict[str, Any]]:
    root = repo_root()
    dest = dest_root or (root / "dist-bundle" / "extensions")
    dest.mkdir(parents=True, exist_ok=True)
    written: list[dict[str, Any]] = []
    for browser in BROWSERS:
        folder = root / "extensions" / browser
        archive_path = dest / f"webmedia-dl-{browser}.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.rglob("*")):
                if not path.is_file():
                    continue
                info = zipfile.ZipInfo(str(path.relative_to(folder)).replace("\\", "/"))
                info.date_time = FIXED_ZIP_TIME
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
        written.append(
            {
                "browser": browser,
                "path": str(archive_path),
                "sha256": hashlib.sha256(archive_path.read_bytes()).hexdigest(),
            }
        )
    return written
