"""Clear-stream live manifest recording. Encrypted playlists are refused, not decrypted."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urljoin

from tqdm import tqdm

from webmedia_dl.errors import DiscoveryError, DrmRefused

_ENCRYPTED_HLS = re.compile(r"#EXT-X-KEY:.*METHOD=(?!NONE)([A-Z0-9-]+)", re.I)
_HLS_KEY_METHOD = re.compile(r"#EXT-X-KEY:.*METHOD=([A-Z0-9-]+)", re.I)
_HLS_MAP = re.compile(
    r"#EXT-X-MAP:.*URI=(?P<q>['\"])(?P<uri>.*?)(?P=q)"
    r"(?:.*BYTERANGE=(?P<bq>['\"])(?P<byterange>.*?)(?P=bq))?",
    re.I,
)
_HLS_BYTERANGE = re.compile(r"#EXT-X-BYTERANGE:(\d+)(?:@(\d+))?", re.I)
_DASH_CONTENT_PROTECTION = re.compile(r"ContentProtection", re.I)
_DASH_BASE_URL = re.compile(r"<BaseURL>\s*([^<\s]+)\s*</BaseURL>", re.I)
_DASH_MEDIA = re.compile(r'\b(?:media|initialization|sourceURL)="([^"]+)"', re.I)
_DASH_TEMPLATE = re.compile(
    r"<SegmentTemplate\b([^>]*)(?:/>|>(.*?)</SegmentTemplate>)",
    re.I | re.S,
)
_DASH_S = re.compile(r"<S\b([^>]*)/?>", re.I)
_DASH_ATTR = re.compile(r'([A-Za-z_:][\w:.-]*)="([^"]*)"')
_NUMBER_TOKEN = re.compile(r"\$Number(%[^$]+)?\$")
_TIME_TOKEN = re.compile(r"\$Time(%[^$]+)?\$")

FetchFn = Callable[[str], tuple[int, str, bytes]]
StopFn = Callable[[], None]


class ManifestPart(NamedTuple):
    url: str
    start: int | None = None
    length: int | None = None


def inspect_manifest(text: str) -> None:
    if _DASH_CONTENT_PROTECTION.search(text) and "cenc" in text.lower():
        msg = "DASH ContentProtection/cenc is refused."
        raise DrmRefused(msg)
    if recordable_parts(text, "https://live.invalid/") or "<MPD" in text or "<mpd" in text:
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
    return [part.url for part in recordable_parts(text, base)]


def recordable_parts(text: str, base: str) -> list[ManifestPart]:
    if "<MPD" in text or "<mpd" in text:
        if _DASH_CONTENT_PROTECTION.search(text) and "cenc" in text.lower():
            msg = "DASH ContentProtection/cenc is refused."
            raise DrmRefused(msg)
        return [ManifestPart(url) for url in _dash_segment_urls(text, base)]
    parts = _clear_hls_parts(text, base)
    if not parts:
        match = _ENCRYPTED_HLS.search(text)
        if match:
            method = match.group(1)
            msg = (
                f"Live manifest uses encryption method {method}. "
                "WebMedia DL records clear manifests only and does not circumvent DRM."
            )
            raise DrmRefused(msg)
    return parts


def _join(base: str, href: str) -> str:
    return href if href.startswith("http") else urljoin(base, href)


def _parse_byterange(
    text: str | None, *, default_offset: int | None
) -> tuple[int | None, int | None]:
    if not text:
        return default_offset, None
    match = re.fullmatch(r"(\d+)(?:@(\d+))?", text.strip())
    if match is None:
        return default_offset, None
    length = int(match.group(1))
    offset = int(match.group(2)) if match.group(2) is not None else default_offset
    return offset, length


def _clear_hls_parts(text: str, base: str) -> list[ManifestPart]:
    """Collect MAP + URI parts until the first non-NONE EXT-X-KEY."""
    parts: list[ManifestPart] = []
    pending: tuple[int | None, int | None] | None = None
    next_offset: dict[str, int] = {}
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
        mapped = _HLS_MAP.search(stripped)
        if mapped:
            uri = _join(base, mapped.group("uri"))
            offset, length = _parse_byterange(mapped.group("byterange"), default_offset=0)
            parts.append(ManifestPart(uri, offset, length))
            if offset is not None and length is not None:
                next_offset[uri] = offset + length
            continue
        ranged = _HLS_BYTERANGE.match(stripped)
        if ranged:
            length = int(ranged.group(1))
            offset = int(ranged.group(2)) if ranged.group(2) is not None else None
            pending = (offset, length)
            continue
        if stripped.startswith("#"):
            continue
        url = _join(base, stripped)
        if pending is not None:
            offset, length = pending
            pending = None
            if offset is None:
                offset = next_offset.get(url, 0)
            parts.append(ManifestPart(url, offset, length))
            if offset is not None and length is not None:
                next_offset[url] = offset + length
            continue
        parts.append(ManifestPart(url))
    return parts


def _attrs(blob: str) -> dict[str, str]:
    return {key.lower(): value for key, value in _DASH_ATTR.findall(blob)}


def _format_token(value: int, spec: str | None) -> str:
    if not spec:
        return str(value)
    token = spec[1:] if spec.startswith("%") else spec
    try:
        return format(value, token)
    except ValueError:
        return str(value)


def _expand_dash_template(
    template: str,
    *,
    number: int | None = None,
    time_value: int | None = None,
    representation: str = "1",
    bandwidth: str = "1",
) -> str:
    text = template.replace("$$", "\x00")
    if number is not None:
        text = _NUMBER_TOKEN.sub(lambda match: _format_token(number, match.group(1)), text)
    if time_value is not None:
        text = _TIME_TOKEN.sub(lambda match: _format_token(time_value, match.group(1)), text)
    text = text.replace("$RepresentationID$", representation).replace("$Bandwidth$", bandwidth)
    return text.replace("\x00", "$")


def _template_urls(attr_blob: str, body: str, base: str) -> list[str]:
    attrs = _attrs(attr_blob)
    representation = attrs.get("id") or attrs.get("representationid") or "1"
    bandwidth = attrs.get("bandwidth") or "1"
    start = int(attrs.get("startnumber") or 1)
    urls: list[str] = []

    def add(
        template: str | None, *, number: int | None = None, time_value: int | None = None
    ) -> None:
        if not template:
            return
        resolved = _expand_dash_template(
            template,
            number=number,
            time_value=time_value,
            representation=representation,
            bandwidth=bandwidth,
        )
        if "$" in resolved:
            return
        urls.append(_join(base, resolved))

    add(attrs.get("initialization"), number=start)
    media = attrs.get("media")
    samples = list(_DASH_S.finditer(body or ""))
    if samples and media:
        clock = 0
        number = start
        for item in samples:
            sattrs = _attrs(item.group(1))
            if "t" in sattrs:
                clock = int(sattrs["t"])
            duration = int(sattrs.get("d") or 0)
            repeats = int(sattrs.get("r") or 0)
            count = repeats + 1
            if count < 1:
                count = 1
            for _ in range(count):
                add(media, number=number, time_value=clock)
                number += 1
                clock += duration
        return urls
    add(media, number=start)
    return urls


def _dash_segment_urls(text: str, base: str) -> list[str]:
    urls: list[str] = []
    for href in _DASH_BASE_URL.findall(text):
        urls.append(_join(base, href.strip()))
    for match in _DASH_TEMPLATE.finditer(text):
        urls.extend(_template_urls(match.group(1), match.group(2) or "", base))
    for media in _DASH_MEDIA.findall(text):
        resolved = _expand_dash_template(
            media,
            number=1,
            time_value=0,
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
    dest = output
    if _DASH_CONTENT_PROTECTION.search(playlist_text) and "cenc" in playlist_text.lower():
        msg = "DASH ContentProtection/cenc is refused."
        raise DrmRefused(msg)
    parts = recordable_parts(playlist_text, playlist_url)
    if not parts:
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
    first = parts[0].url
    if depth < 2 and (
        first.endswith(".m3u8") or first.endswith(".mpd") or "#EXT-X-STREAM-INF" in playlist_text
    ):
        nested = [
            item.url for item in parts if item.url.endswith(".m3u8") or item.url.endswith(".mpd")
        ]
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
            dest,
            fetch,
            max_segments=max_segments,
            depth=depth + 1,
            should_stop=should_stop,
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    cache: dict[str, bytes] = {}
    with dest.open("wb") as handle:
        for part in tqdm(
            parts[:max_segments],
            desc="live-record",
            disable=True,
            unit="seg",
        ):
            if should_stop is not None:
                should_stop()
            if part.url not in cache:
                status, _, data = fetch(part.url)
                if status >= 400:
                    msg = f"Live segment fetch failed with HTTP {status}."
                    raise DiscoveryError(msg)
                cache[part.url] = data
            chunk = cache[part.url]
            if part.start is not None:
                end = part.start + (part.length if part.length is not None else len(chunk))
                chunk = chunk[part.start : end]
            handle.write(chunk)
    if dest.stat().st_size == 0:
        msg = "Live recording produced an empty artifact."
        raise DiscoveryError(msg)
    return dest
