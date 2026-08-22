"""Content-addressed identity. Titles and URLs never become ids."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

SAFE_CONTAINER_PATTERN = r"^[A-Za-z0-9]{1,12}$"
_SAFE_FORMAT_ID = re.compile(r"^[A-Za-z0-9+._][A-Za-z0-9+._-]*$")
_SAFE_CONTAINER = re.compile(SAFE_CONTAINER_PATTERN)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def artifact_id_for_digest(digest: str) -> str:
    return f"sha256:{digest}"


def identity_key_for_url(url: str, resource_id: str | None = None) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "unknown").lower()
    if resource_id:
        return f"host:{host}:id:{resource_id}"
    path = parsed.path.rstrip("/") or "/"
    return f"host:{host}:path:{path}"


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "unknown").lower()


def is_safe_format_id(format_id: str) -> bool:
    return bool(_SAFE_FORMAT_ID.fullmatch(format_id))


def is_safe_container(container: str) -> bool:
    return bool(_SAFE_CONTAINER.fullmatch(container))
