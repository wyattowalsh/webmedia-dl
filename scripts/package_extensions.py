#!/usr/bin/env python3
"""Zip each browser capture tree with a fixed timestamp."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BROWSERS = ("chromium", "chrome", "brave", "edge", "firefox", "safari")


def main() -> int:
    dest_root = ROOT / "dist-bundle" / "extensions"
    dest_root.mkdir(parents=True, exist_ok=True)
    for browser in BROWSERS:
        folder = ROOT / "extensions" / browser
        archive_path = dest_root / f"webmedia-dl-{browser}.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(folder.rglob("*")):
                if not path.is_file():
                    continue
                info = zipfile.ZipInfo(str(path.relative_to(folder)).replace("\\", "/"))
                info.date_time = (2026, 8, 18, 0, 0, 0)
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
        digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        print(f"{archive_path} sha256:{digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
