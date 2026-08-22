"""Authenticated worker staging for complete-client file drops."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path

from webmedia_dl.errors import IntakeError
from webmedia_dl.identity import sha256_file
from webmedia_dl.paths import staging_dir

_DIGEST = re.compile(r"^(?:sha256:)?([0-9a-fA-F]{64})$")
_SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_OWNER = re.compile(r"[^A-Za-z0-9._-]+")


def normalize_digest(raw: str) -> str:
    match = _DIGEST.fullmatch((raw or "").strip())
    if match is None:
        msg = "Staging upload requires a 64-character sha256 digest."
        raise IntakeError(msg)
    return match.group(1).lower()


def safe_filename(raw: str | None) -> str:
    text = (raw or "").strip()
    if "/" in text or "\\" in text:
        return "upload.bin"
    name = Path(text or "upload.bin").name
    if not _SAFE_NAME.fullmatch(name) or name in {".", ".."}:
        return "upload.bin"
    return name


def declared_content_length(header: str | None) -> int | None:
    if header is None or header == "":
        return None
    try:
        value = int(header)
    except ValueError as exc:
        msg = "Invalid Content-Length."
        raise IntakeError(msg) from exc
    if value < 0:
        msg = "Invalid Content-Length."
        raise IntakeError(msg)
    return value


def assert_staging_size(*, declared: int | None, actual: int, max_bytes: int) -> None:
    if declared is not None and declared > max_bytes:
        msg = "Staging upload exceeds the byte bound."
        raise IntakeError(msg)
    if actual > max_bytes:
        msg = "Staging upload exceeds the byte bound."
        raise IntakeError(msg)


def staging_owner(raw: str | None) -> str:
    cleaned = _OWNER.sub("_", (raw or "").strip()).strip("._-")
    return cleaned or "mac"


def ingest_staged_upload(
    *,
    data_dir: Path,
    owner: str,
    expected_digest: str,
    filename: str | None,
    chunks: Iterable[bytes],
    max_bytes: int,
) -> dict[str, str | int]:
    if max_bytes <= 0:
        msg = "Staging upload requires a positive byte bound."
        raise IntakeError(msg)
    digest = normalize_digest(expected_digest)
    name = safe_filename(filename)
    dest_dir = staging_dir(data_dir) / "uploads" / staging_owner(owner) / digest[:2] / digest
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_dir.chmod(0o700)
    dest = dest_dir / name
    if dest.is_file() and sha256_file(str(dest)) == digest:
        return {"path": str(dest.resolve()), "sha256": digest, "bytes": dest.stat().st_size}
    hasher = hashlib.sha256()
    written = 0
    tmp = dest.with_name(f"{dest.name}.part")
    try:
        with tmp.open("wb") as handle:
            for chunk in chunks:
                if not chunk:
                    continue
                written += len(chunk)
                if written > max_bytes:
                    msg = f"Staging upload would exceed the {max_bytes} byte bound."
                    raise IntakeError(msg)
                hasher.update(chunk)
                handle.write(chunk)
        if written == 0:
            msg = "Staging upload is empty."
            raise IntakeError(msg)
        actual = hasher.hexdigest()
        if actual != digest:
            msg = "Staging upload digest does not match the declared sha256."
            raise IntakeError(msg)
        tmp.replace(dest)
        dest.chmod(0o600)
        return {"path": str(dest.resolve()), "sha256": actual, "bytes": written}
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
