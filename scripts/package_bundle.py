#!/usr/bin/env python3
"""Create a reproducible zip of the planning-and-source tree."""

from __future__ import annotations

import argparse
import hashlib
import os
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
    ".ty",
    "htmlcov",
    "dist-bundle",
}
SKIP_NAMES = {
    ".coverage",
    "CACHEDIR.TAG",
    ".env",
    ".env.mcphub",
    "worker.token",
    "cookie-grants.json",
    "pairing.json",
}
SKIP_SUFFIX = {".pyc", ".pyo", ".zip", ".whl", ".so", ".pem", ".key", ".p12"}


def archive_member_is_unsafe(name: str) -> bool:
    member = name.replace("\\", "/")
    if member.startswith("/") or member.startswith("../") or member == "..":
        return True
    return any(part in {"", ".."} for part in member.split("/"))


def iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    root = root.resolve()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        rel = current.relative_to(root)
        if any(part in SKIP_PARTS for part in rel.parts):
            dirnames[:] = []
            continue
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_PARTS)
        for name in sorted(filenames):
            path = current / name
            if name in SKIP_NAMES or path.suffix in SKIP_SUFFIX or name.startswith(".env."):
                continue
            if path.is_symlink() or not path.is_file():
                continue
            files.append(path)
    return files


def write_bundle(root: Path, output: Path) -> str:
    output.parent.mkdir(parents=True, exist_ok=True)
    files = iter_files(root)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            member = str(path.relative_to(root)).replace("\\", "/")
            if archive_member_is_unsafe(member):
                msg = f"Refusing zip member {member!r}."
                raise ValueError(msg)
            info = zipfile.ZipInfo(member)
            info.date_time = (2026, 8, 18, 0, 0, 0)
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=ROOT / "dist-bundle" / "webmedia-dl-final-planning-pack-2026-08-18.zip",
    )
    args = parser.parse_args()
    digest = write_bundle(ROOT, args.output)
    files = iter_files(ROOT)
    print(f"wrote {args.output} sha256:{digest} files:{len(files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
