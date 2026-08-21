"""Clear-stream live manifest recording. Encrypted playlists are refused, not decrypted."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urljoin, urlparse

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
_DASH_MEDIA = re.compile(
    r"""\b(?:media|initialization|sourceURL)=(?:"([^"]+)"|'([^']+)')""",
    re.I,
)
_DASH_TEMPLATE = re.compile(
    r"<SegmentTemplate\b([^>]*)(?:/>|>(.*?)</SegmentTemplate>)",
    re.I | re.S,
)
_DASH_S = re.compile(r"<S\b([^>]*)/?>", re.I)
_DASH_ATTR = re.compile(r"([A-Za-z_:][\w:.-]*)=(?:\"([^\"]*)\"|'([^']*)')")
_NUMBER_TOKEN = re.compile(r"\$Number(%[^$]+)?\$")
_TIME_TOKEN = re.compile(r"\$Time(%[^$]+)?\$")
_REPRESENTATION = re.compile(
    r"<Representation\b([^>]*)(?:/>|>(.*?)</Representation>)",
    re.I | re.S,
)
_ADAPTATION_SET = re.compile(
    r"<AdaptationSet\b([^>]*)(?:/>|>(.*?)</AdaptationSet>)",
    re.I | re.S,
)
_PERIOD = re.compile(
    r"<Period\b([^>]*)(?:/>|>(.*?)</Period>)",
    re.I | re.S,
)
_MPD_OPEN = re.compile(r"<MPD\b([^>]*)>", re.I)
MAX_TIMELINE_SEGMENTS = 64
MAX_LIVE_POLLS = 8

FetchFn = Callable[[str], tuple[int, str, bytes]]
StopFn = Callable[[], None]


class ManifestPart(NamedTuple):
    url: str
    start: int | None = None
    length: int | None = None


AddPart = Callable[[ManifestPart], None]


def inspect_manifest(text: str) -> None:
    if _DASH_CONTENT_PROTECTION.search(text):
        msg = "DASH ContentProtection is refused."
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
        if _DASH_CONTENT_PROTECTION.search(text):
            msg = "DASH ContentProtection is refused."
            raise DrmRefused(msg)
        return _dash_parts(text, base)
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


def _parse_dash_range(text: str | None) -> tuple[int | None, int | None]:
    """Parse inclusive DASH `range` / `mediaRange` (`start-end`) into offset+length."""
    if not text:
        return None, None
    match = re.fullmatch(r"(\d+)-(\d+)", text.strip())
    if match is None:
        return None, None
    start = int(match.group(1))
    end = int(match.group(2))
    if end < start:
        return None, None
    return start, end - start + 1


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
    parsed: dict[str, str] = {}
    for key, double, single in _DASH_ATTR.findall(blob):
        parsed[key.lower()] = double or single
    return parsed


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


def _template_urls(
    attr_blob: str,
    body: str,
    base: str,
    *,
    representation: str | None = None,
    bandwidth: str | None = None,
) -> list[str]:
    attrs = _attrs(attr_blob)
    representation = representation or attrs.get("id") or attrs.get("representationid") or "1"
    bandwidth = bandwidth or attrs.get("bandwidth") or "1"
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
            count = max(MAX_TIMELINE_SEGMENTS - len(urls), 1) if repeats < 0 else repeats + 1
            if count < 1:
                count = 1
            count = min(count, MAX_TIMELINE_SEGMENTS)
            for _ in range(count):
                add(media, number=number, time_value=clock)
                number += 1
                clock += duration
        return urls
    add(media, number=start)
    return urls


def _is_directory_base(resolved: str) -> bool:
    suffix = Path(urlparse(resolved).path).suffix.lower()
    return resolved.endswith("/") or not suffix


def _collect_baseurls(text: str, current: str, add: AddPart) -> str:
    for href in _DASH_BASE_URL.findall(text):
        resolved = _join(current, href.strip())
        if _is_directory_base(resolved):
            current = resolved if resolved.endswith("/") else f"{resolved}/"
            continue
        add(ManifestPart(resolved))
    return current


def _collect_segments(
    text: str,
    current: str,
    add: AddPart,
    seen_urls: set[str],
    *,
    representation: str | None = None,
    bandwidth: str | None = None,
    include_templates: bool = True,
) -> None:
    if include_templates:
        for match in _DASH_TEMPLATE.finditer(text):
            for url in _template_urls(
                match.group(1),
                match.group(2) or "",
                current,
                representation=representation,
                bandwidth=bandwidth,
            ):
                add(ManifestPart(url))
    for match in re.finditer(r"<Initialization\b([^>]*)/?>", text, flags=re.I):
        attrs = _attrs(match.group(1))
        href = attrs.get("sourceurl")
        if href:
            start, length = _parse_dash_range(attrs.get("range"))
            add(ManifestPart(_join(current, href.strip()), start, length))
    for match in re.finditer(r"<SegmentURL\b([^>]*)/?>", text, flags=re.I):
        attrs = _attrs(match.group(1))
        href = attrs.get("media")
        if href:
            start, length = _parse_dash_range(attrs.get("mediarange"))
            add(ManifestPart(_join(current, href.strip()), start, length))
    if not include_templates:
        return
    for double, single in _DASH_MEDIA.findall(text):
        media = double or single
        resolved = _expand_dash_template(
            media,
            number=1,
            time_value=0,
            representation=representation or "1",
            bandwidth=bandwidth or "1",
        )
        if "$" in resolved:
            continue
        url = _join(current, resolved)
        if url in seen_urls:
            continue
        add(ManifestPart(url))


def _strip_blocks(text: str, pattern: re.Pattern[str]) -> str:
    chunks: list[str] = []
    cursor = 0
    for match in pattern.finditer(text):
        chunks.append(text[cursor : match.start()])
        cursor = match.end()
    chunks.append(text[cursor:])
    return "".join(chunks)


def _preferred_hls_variant(text: str, base: str) -> str | None:
    variants: list[tuple[int, str]] = []
    pending: int | None = None
    for line in text.splitlines():
        stripped = line.strip()
        match = re.search(r"#EXT-X-STREAM-INF:.*\bBANDWIDTH=(\d+)", stripped, flags=re.I)
        if match:
            pending = int(match.group(1))
            continue
        if pending is not None and stripped and not stripped.startswith("#"):
            variants.append((pending, _join(base, stripped)))
            pending = None
    if not variants:
        return None
    return max(variants, key=lambda item: item[0])[1]


def _dash_kind(attrs: dict[str, str]) -> str:
    blob = " ".join(
        [
            attrs.get("mimetype") or "",
            attrs.get("contenttype") or "",
            attrs.get("codecs") or "",
        ]
    ).lower()
    video_tokens = ("video", "avc", "hev1", "hvc1", "vp9", "av01")
    audio_tokens = ("audio", "mp4a", "opus", "ec-3", "ac-3")
    if any(token in blob for token in video_tokens):
        return "video"
    if any(token in blob for token in audio_tokens):
        return "audio"
    return "unknown"


def _new_part_bucket() -> tuple[list[ManifestPart], set[str], AddPart]:
    parts: list[ManifestPart] = []
    seen: set[tuple[str, int | None, int | None]] = set()
    seen_urls: set[str] = set()

    def add(part: ManifestPart) -> None:
        key = (part.url, part.start, part.length)
        if key in seen:
            return
        seen.add(key)
        seen_urls.add(part.url)
        parts.append(part)

    return parts, seen_urls, add


def _collect_representation(
    match: re.Match[str],
    current: str,
    add: AddPart,
    seen_urls: set[str],
    *,
    inherited_templates: str = "",
) -> tuple[int, str]:
    rattrs = _attrs(match.group(1))
    body = match.group(2) or ""
    local_base = _collect_baseurls(body, current, add)
    combined = body if _DASH_TEMPLATE.search(body) else f"{inherited_templates}{body}"
    _collect_segments(
        combined,
        local_base,
        add,
        seen_urls,
        representation=rattrs.get("id"),
        bandwidth=rattrs.get("bandwidth"),
    )
    try:
        bandwidth = int(rattrs.get("bandwidth") or 0)
    except ValueError:
        bandwidth = 0
    return bandwidth, _dash_kind(rattrs)


def _dash_scope_groups(text: str, base: str) -> list[tuple[int, str, list[ManifestPart]]]:
    parts, seen_urls, add = _new_part_bucket()
    representations = list(_REPRESENTATION.finditer(text))
    prefix = text[: representations[0].start()] if representations else text
    resolve_base = _collect_baseurls(prefix, base, add)
    inherited = prefix if representations and _DASH_TEMPLATE.search(prefix) else ""
    groups: list[tuple[int, str, list[ManifestPart]]] = []
    for rep in representations:
        bucket, bucket_urls, bucket_add = _new_part_bucket()
        bandwidth, kind = _collect_representation(
            rep, resolve_base, bucket_add, bucket_urls, inherited_templates=inherited
        )
        groups.append((bandwidth, kind, [*parts, *bucket] if parts else bucket))
    remainder = _strip_blocks(text, _REPRESENTATION) if representations else text
    if representations:
        resolve_base = _collect_baseurls(text[representations[-1].end() :], resolve_base, add)
    _collect_segments(
        remainder,
        resolve_base,
        add,
        seen_urls,
        include_templates=not representations,
    )
    if groups:
        return groups
    return [(0, "unknown", parts)] if parts else []


def _dash_adaptation_groups(
    text: str, base: str, as_attrs: dict[str, str]
) -> list[tuple[int, str, list[ManifestPart]]]:
    without_rep = _strip_blocks(text, _REPRESENTATION)
    parts, seen_urls, add = _new_part_bucket()
    as_base = _collect_baseurls(without_rep, base, add)
    inherited = without_rep if _DASH_TEMPLATE.search(without_rep) else ""
    as_kind = _dash_kind(as_attrs)
    representations = list(_REPRESENTATION.finditer(text))
    if not representations:
        _collect_segments(text, as_base, add, seen_urls)
        return [(0, as_kind, parts)] if parts else []
    groups: list[tuple[int, str, list[ManifestPart]]] = []
    for rep in representations:
        bucket, bucket_urls, bucket_add = _new_part_bucket()
        bandwidth, kind = _collect_representation(
            rep, as_base, bucket_add, bucket_urls, inherited_templates=inherited
        )
        groups.append(
            (
                bandwidth,
                kind if kind != "unknown" else as_kind,
                [*parts, *bucket] if parts else bucket,
            )
        )
    return groups


def _select_dash_group(
    groups: list[tuple[int, str, list[ManifestPart]]],
) -> list[ManifestPart]:
    populated = [(bandwidth, kind, parts) for bandwidth, kind, parts in groups if parts]
    if not populated:
        return []
    videos = [item for item in populated if item[1] == "video"]
    pool = videos or [item for item in populated if item[1] == "audio"] or populated
    return max(pool, key=lambda item: item[0])[2]


def _period_parts(body: str, base: str) -> list[ManifestPart]:
    shared, shared_urls, shared_add = _new_part_bucket()
    period_without_as = _strip_blocks(body, _ADAPTATION_SET)
    period_base = _collect_baseurls(period_without_as, base, shared_add)
    groups: list[tuple[int, str, list[ManifestPart]]] = []
    adaptations = list(_ADAPTATION_SET.finditer(body))
    if not adaptations:
        groups.extend(_dash_scope_groups(body, period_base))
    else:
        _collect_segments(period_without_as, period_base, shared_add, shared_urls)
        for adaptation in adaptations:
            groups.extend(
                _dash_adaptation_groups(
                    adaptation.group(2) or "",
                    period_base,
                    _attrs(adaptation.group(1)),
                )
            )
    selected = _select_dash_group(groups) if groups else list(shared)
    if not selected:
        return list(shared)
    if groups:
        return [*shared, *selected]
    return selected


def _dash_parts(text: str, base: str) -> list[ManifestPart]:
    parts: list[ManifestPart] = []
    seen: set[tuple[str, int | None, int | None]] = set()

    def add(part: ManifestPart) -> None:
        key = (part.url, part.start, part.length)
        if key in seen:
            return
        seen.add(key)
        parts.append(part)

    periods = list(_PERIOD.finditer(text))
    mpd_prefix = text[: periods[0].start()] if periods else ""
    mpd_shared, _mpd_urls, mpd_add = _new_part_bucket()
    mpd_base = _collect_baseurls(mpd_prefix, base, mpd_add)
    scopes = [(match.group(2) or "") for match in periods] or [text]
    ordered: list[ManifestPart] = list(mpd_shared)
    for body in scopes:
        ordered.extend(_period_parts(body, mpd_base))
    for part in ordered:
        add(part)
    return parts


def manifest_is_live(text: str) -> bool:
    if "<MPD" in text or "<mpd" in text:
        match = _MPD_OPEN.search(text)
        if match is None:
            return False
        return _attrs(match.group(1)).get("type", "").lower() == "dynamic"
    if "#EXTM3U" in text:
        return "#EXT-X-ENDLIST" not in text
    return False


def record_clear_stream(
    playlist_text: str,
    playlist_url: str,
    output: Path,
    fetch: FetchFn,
    *,
    max_segments: int = 128,
    depth: int = 0,
    should_stop: StopFn | None = None,
    live_polls: int = 1,
) -> Path:
    dest = output
    playlist = playlist_text
    if _DASH_CONTENT_PROTECTION.search(playlist):
        msg = "DASH ContentProtection is refused."
        raise DrmRefused(msg)
    parts = recordable_parts(playlist, playlist_url)
    if not parts:
        match = _ENCRYPTED_HLS.search(playlist)
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
    preferred = _preferred_hls_variant(playlist, playlist_url)
    if depth < 2 and (
        preferred
        or first.endswith(".m3u8")
        or first.endswith(".mpd")
        or "#EXT-X-STREAM-INF" in playlist
    ):
        nested = [
            item.url for item in parts if item.url.endswith(".m3u8") or item.url.endswith(".mpd")
        ]
        target = preferred or (nested[0] if nested else first)
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
            live_polls=live_polls,
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    cache: dict[str, bytes] = {}
    recorded: set[tuple[str, int | None, int | None]] = set()
    polls = max(1, min(live_polls, MAX_LIVE_POLLS))
    written = 0
    with dest.open("wb") as handle:
        for round_index in range(polls):
            inspect_manifest(playlist)
            round_parts = recordable_parts(playlist, playlist_url)
            for part in tqdm(
                round_parts[:max_segments],
                desc="live-record",
                disable=True,
                unit="seg",
            ):
                key = (part.url, part.start, part.length)
                if key in recorded:
                    continue
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
                written += len(chunk)
                recorded.add(key)
            more = round_index + 1 < polls and manifest_is_live(playlist)
            if not more:
                break
            if should_stop is not None:
                should_stop()
            status, _, data = fetch(playlist_url)
            if status >= 400:
                break
            playlist = data.decode("utf-8", errors="replace")
    if dest.stat().st_size == 0 or written == 0:
        msg = "Live recording produced an empty artifact."
        raise DiscoveryError(msg)
    return dest
