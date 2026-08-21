"""Clear-stream live manifest recording. Encrypted playlists are refused, not decrypted."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urljoin

from tqdm import tqdm

from webmedia_dl.errors import DiscoveryError, DrmRefused

_ENCRYPTED_HLS = re.compile(r"#EXT-X-KEY:.*METHOD=(?!NONE)([A-Z0-9-]+)", re.I)
_HLS_KEY_METHOD = re.compile(r"#EXT-X-KEY:.*METHOD=([A-Z0-9-]+)", re.I)
_DASH_CONTENT_PROTECTION = re.compile(r"ContentProtection", re.I)
_DASH_BASE_URL = re.compile(r"<BaseURL>\s*([^<\s]+)\s*</BaseURL>", re.I)
_DASH_MEDIA = re.compile(r'\b(?:media|initialization)="([^"]+)"', re.I)

FetchFn = Callable[[str], tuple[int, str, bytes]]
StopFn = Callable[[], None]


def inspect_manifest(text: str) -> None:
    if _DASH_CONTENT_PROTECTION.search(text) and "cenc" in text.lower():
        msg = "DASH ContentProtection/cenc is refused."
        raise DrmRefused(msg)
    if _clear_hls_segment_urls(text, "https://live.invalid/") or "<MPD" in text or "<mpd" in text:
        return
    match = _ENCRYPTED_HLS.search(text)
    if match:
        method = match.group(1)
        msg = (
            f"Live manifest uses encryption method {method}. "
            "WebMedia DL records clear manifests only and does not circumvent DRM."
        )
        raise DrmRefused(msg)


def recordable_segment_urls(text: str, base: str) -> list[str]:
    if "<MPD" in text or "<mpd" in text:
        if _DASH_CONTENT_PROTECTION.search(text) and "cenc" in text.lower():
            msg = "DASH ContentProtection/cenc is refused."
            raise DrmRefused(msg)
        return _dash_segment_urls(text, base)
    urls = _clear_hls_segment_urls(text, base)
    if not urls:
        match = _ENCRYPTED_HLS.search(text)
        if match:
            method = match.group(1)
            msg = (
                f"Live manifest uses encryption method {method}. "
                "WebMedia DL records clear manifests only and does not circumvent DRM."
            )
            raise DrmRefused(msg)
    return urls


def _join(base: str, href: str) -> str:
    return href if href.startswith("http") else urljoin(base, href)


def _clear_hls_segment_urls(text: str, base: str) -> list[str]:
    """Collect URI lines until the first non-NONE EXT-X-KEY. Prior clear bytes are kept."""
    urls: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        key = _HLS_KEY_METHOD.search(stripped)
        if key:
            method = key.group(1).upper()
            if method != "NONE":
                break
            continue
        if stripped.startswith("#"):
            continue
        urls.append(_join(base, stripped))
    return urls


def _dash_segment_urls(text: str, base: str) -> list[str]:
    urls: list[str] = []
    for href in _DASH_BASE_URL.findall(text):
        urls.append(_join(base, href.strip()))
    for media in _DASH_MEDIA.findall(text):
        resolved = (
            media.replace("$Number$", "1")
            .replace("$Number%05d$", "00001")
            .replace("$RepresentationID$", "1")
            .replace("$Bandwidth$", "1")
            .replace("$$", "$")
        )
        if "$" in resolved:
            continue
        urls.append(_join(base, resolved))
    seen: list[str] = []
    for item in urls:
        if item not in seen:
            seen.append(item)
    return seen


def record_clear_stream(
    playlist_text: str,
    playlist_url: str,
    output: Path,
    fetch: FetchFn,
    *,
    max_segments: int = 128,
    depth: int = 0,
    should_stop: StopFn | None = None,
) -> Path:
    if _DASH_CONTENT_PROTECTION.search(playlist_text) and "cenc" in playlist_text.lower():
        msg = "DASH ContentProtection/cenc is refused."
        raise DrmRefused(msg)
    urls = recordable_segment_urls(playlist_text, playlist_url)
    if not urls:
        match = _ENCRYPTED_HLS.search(playlist_text)
        if match:
            method = match.group(1)
            msg = (
                f"Live manifest uses encryption method {method}. "
                "WebMedia DL records clear manifests only and does not circumvent DRM."
            )
            raise DrmRefused(msg)
        msg = "Clear live playlist contained no recordable segments."
        raise DiscoveryError(msg)
    first = urls[0]
    if depth < 2 and (
        first.endswith(".m3u8") or first.endswith(".mpd") or "#EXT-X-STREAM-INF" in playlist_text
    ):
        nested = [item for item in urls if item.endswith(".m3u8") or item.endswith(".mpd")]
        target = nested[0] if nested else first
        if should_stop is not None:
            should_stop()
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
            should_stop=should_stop,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("wb") as handle:
        for url in tqdm(
            urls[:max_segments],
            desc="live-record",
            disable=True,
            unit="seg",
        ):
            if should_stop is not None:
                should_stop()
            status, _, data = fetch(url)
            if status >= 400:
                msg = f"Live segment fetch failed with HTTP {status}."
                raise DiscoveryError(msg)
            handle.write(data)
    if output.stat().st_size == 0:
        msg = "Live recording produced an empty artifact."
        raise DiscoveryError(msg)
    return output
