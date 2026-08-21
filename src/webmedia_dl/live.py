"""Clear-stream live manifest recording. Encrypted playlists are refused, not decrypted."""

from __future__ import annotations

import re

from webmedia_dl.errors import DrmRefused

_ENCRYPTED_HLS = re.compile(r"#EXT-X-KEY:.*METHOD=(?!NONE)([A-Z0-9-]+)", re.I)
_DASH_CONTENT_PROTECTION = re.compile(r"ContentProtection", re.I)


def inspect_manifest(text: str) -> None:
    match = _ENCRYPTED_HLS.search(text)
    if match:
        method = match.group(1)
        msg = (
            f"Live manifest uses encryption method {method}. "
            "WebMedia DL records clear manifests only and does not circumvent DRM."
        )
        raise DrmRefused(msg)
    if _DASH_CONTENT_PROTECTION.search(text) and "cenc" in text.lower():
        msg = "DASH ContentProtection/cenc is refused."
        raise DrmRefused(msg)


def recordable_segment_urls(text: str, base: str) -> list[str]:
    inspect_manifest(text)
    urls: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            if stripped.startswith("http"):
                urls.append(stripped)
            else:
                urls.append(base.rsplit("/", 1)[0] + "/" + stripped)
    return urls
