#!/usr/bin/env python3
"""Create a reproducible zip of the planning-and-source tree."""

from __future__ import annotations

import argparse
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    ".ruff_cache",
    ".pytest_cache",
    "htmlcov",
}
SKIP_SUFFIX = {".pyc", ".zip"}


def iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_PARTS for part in path.parts):
            continue
        if path.suffix in SKIP_SUFFIX:
            continue
        files.append(path)
    return files


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "dist-bundle" / "webmedia-dl-final-planning-pack-2026-08-18.zip",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    files = iter_files(ROOT)
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            info = zipfile.ZipInfo(str(path.relative_to(ROOT)).replace("\\", "/"))
            info.date_time = (2026, 8, 18, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    print(f"wrote {args.output} sha256:{digest} files:{len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
