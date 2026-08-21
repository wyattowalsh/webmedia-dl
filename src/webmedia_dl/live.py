"""Clear-stream live manifest recording. Encrypted playlists are refused, not decrypted."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin

from webmedia_dl.errors import DiscoveryError, DrmRefused

_ENCRYPTED_HLS = re.compile(r"#EXT-X-KEY:.*METHOD=(?!NONE)([A-Z0-9-]+)", re.I)
_DASH_CONTENT_PROTECTION = re.compile(r"ContentProtection", re.I)

FetchFn = Callable[[str], tuple[int, str, bytes]]


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
    if "<MPD" in text or "<mpd" in text:
        for href in re.findall(r'(?:<BaseURL>|media=")([^"<\s]+)', text):
            urls.append(href if href.startswith("http") else urljoin(base, href))
        return urls
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            if stripped.startswith("http"):
                urls.append(stripped)
            else:
                urls.append(urljoin(base, stripped))
    return urls


def record_clear_stream(
    playlist_text: str,
    playlist_url: str,
    output: Path,
    fetch: FetchFn,
    *,
    max_segments: int = 128,
    depth: int = 0,
) -> Path:
    inspect_manifest(playlist_text)
    urls = recordable_segment_urls(playlist_text, playlist_url)
    if not urls:
        msg = "Clear live playlist contained no recordable segments."
        raise DiscoveryError(msg)
    first = urls[0]
    if depth < 2 and (
        first.endswith(".m3u8") or first.endswith(".mpd") or "#EXT-X-STREAM-INF" in playlist_text
    ):
        nested = [item for item in urls if item.endswith(".m3u8") or item.endswith(".mpd")]
        target = nested[0] if nested else first
        status, _, data = fetch(target)
        if status >= 400:
            msg = f"Nested live playlist fetch failed with HTTP {status}."
            raise DiscoveryError(msg)
        return record_clear_stream(
            data.decode("utf-8", errors="replace"),
            target,
            output,
            fetch,
            max_segments=max_segments,
            depth=depth + 1,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        for url in urls[:max_segments]:
            status, _, data = fetch(url)
            if status >= 400:
                msg = f"Live segment fetch failed with HTTP {status}."
                raise DiscoveryError(msg)
            handle.write(data)
    if output.stat().st_size == 0:
        msg = "Live recording produced an empty artifact."
        raise DiscoveryError(msg)
    return output
