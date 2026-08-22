"""Clear-stream live manifest recording. Encrypted playlists are refused, not decrypted."""

from __future__ import annotations

import html
import math
import re
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple
from urllib.parse import urljoin, urlparse

from tqdm import tqdm

from webmedia_dl.domain.enums import MediaKind
from webmedia_dl.errors import DiscoveryError, DrmRefused, NetworkPolicyError
from webmedia_dl.security import DRM_PATTERNS, detect_drm_signals, refuse_drm

_XML_NS = r"(?:[A-Za-z_][\w.-]*:)?"
_HLS_BYTERANGE = re.compile(r"#EXT-X-BYTERANGE:\s*(\d+)\s*(?:@\s*(\d+))?", re.I)
_DASH_CONTENT_PROTECTION = re.compile(r"ContentProtection", re.I)
_DASH_BASE_URL = re.compile(
    rf"<{_XML_NS}BaseURL>\s*(?:<!\[CDATA\[(.*?)\]\]>|(.*?))\s*</{_XML_NS}BaseURL>",
    re.I | re.S,
)
_DASH_MEDIA = re.compile(
    r"""\b(?:media|initialization|sourceURL)=(?:"([^"]+)"|'([^']+)')""",
    re.I,
)
_DASH_TEMPLATE = re.compile(
    rf"<{_XML_NS}SegmentTemplate\b([^>]*)(?:/>|>(.*?)</{_XML_NS}SegmentTemplate>)",
    re.I | re.S,
)
_DASH_S = re.compile(rf"<{_XML_NS}S\b([^>]*)/?>", re.I)
_DASH_SEGMENT_BASE = re.compile(
    rf"<{_XML_NS}SegmentBase\b([^>]*)(?:/>|>(.*?)</{_XML_NS}SegmentBase>)",
    re.I | re.S,
)
_DASH_SEGMENT_LIST = re.compile(
    rf"<{_XML_NS}SegmentList\b([^>]*)(?:/>|>(.*?)</{_XML_NS}SegmentList>)",
    re.I | re.S,
)
_DASH_ATTR = re.compile(r"([A-Za-z_:][\w:.-]*)=(?:\"([^\"]*)\"|'([^']*)')")
_NUMBER_TOKEN = re.compile(r"\$Number(%[^$]+)?\$")
_TIME_TOKEN = re.compile(r"\$Time(%[^$]+)?\$")
_BANDWIDTH_TOKEN = re.compile(r"\$Bandwidth(%[^$]+)?\$")
_UNEXPANDED_DASH = re.compile(r"\$(?:Number|Time|RepresentationID|Bandwidth)(?:%[^$]+)?\$")
_REPRESENTATION = re.compile(
    rf"<{_XML_NS}Representation\b([^>]*)(?:/>|>(.*?)</{_XML_NS}Representation>)",
    re.I | re.S,
)
_ADAPTATION_SET = re.compile(
    rf"<{_XML_NS}AdaptationSet\b([^>]*)(?:/>|>(.*?)</{_XML_NS}AdaptationSet>)",
    re.I | re.S,
)
_PERIOD = re.compile(
    rf"<{_XML_NS}Period\b([^>]*)(?:/>|>(.*?)</{_XML_NS}Period>)",
    re.I | re.S,
)
_MPD_ROOT = re.compile(rf"<{_XML_NS}MPD\b", re.I)
_MPD_OPEN = re.compile(rf"<{_XML_NS}MPD\b([^>]*)>", re.I)
_INIT_TAG = re.compile(rf"<{_XML_NS}Initialization\b([^>]*)/?>", re.I)
_SEGMENT_URL_TAG = re.compile(rf"<{_XML_NS}SegmentURL\b([^>]*)/?>", re.I)
_ISO_DURATION = re.compile(
    r"^P(?:(\d+)Y)?(?:(\d+)M)?(?:(\d+)D)?"
    r"(?:T(?:(\d+(?:\.\d+)?)H)?(?:(\d+(?:\.\d+)?)M)?(?:(\d+(?:\.\d+)?)S)?)?$",
    re.I,
)
MAX_TIMELINE_SEGMENTS = 64
MAX_LIVE_POLLS = 8
MAX_PLAYLIST_NESTING = 8

FetchFn = Callable[[str], tuple[int, str, bytes]]
StopFn = Callable[[], None]


def _is_dash_manifest(text: str) -> bool:
    return _MPD_ROOT.search(text) is not None


class ManifestPart(NamedTuple):
    url: str
    start: int | None = None
    length: int | None = None
    occurrence: int = 0


class ByteBudget:
    def __init__(self, max_bytes: int | None = None) -> None:
        self.max_bytes = max_bytes
        self.written = 0

    def consume(self, size: int) -> None:
        if self.max_bytes is not None and self.written + size > self.max_bytes:
            msg = (
                f"Live recording would exceed the {self.max_bytes} byte bound "
                f"({self.written} + {size})."
            )
            raise NetworkPolicyError(msg)
        self.written += size


AddPart = Callable[[ManifestPart], None]


def _hls_attr_map(blob: str) -> tuple[dict[str, str], set[str]]:
    parsed: dict[str, str] = {}
    duplicates: set[str] = set()
    for match in re.finditer(r"([A-Z0-9-]+)=(\"[^\"]*\"|'[^']*'|[^\",]+)", blob, flags=re.I):
        key = match.group(1).upper()
        value = match.group(2).strip().strip("\"'")
        if key in parsed:
            duplicates.add(key)
            continue
        parsed[key] = value
    return parsed, duplicates


def _hls_line(text: str) -> str:
    return text.strip().lstrip("\ufeff")


def _without_bom(text: str) -> str:
    return text.lstrip("\ufeff")


def _hls_tag_method(stripped: str, tag: str) -> str | None:
    if not stripped.upper().startswith(tag):
        return None
    attrs, duplicates = _hls_attr_map(stripped.split(":", 1)[-1])
    if "METHOD" in duplicates:
        return "UNKNOWN"
    method = attrs.get("METHOD", "").upper() or "UNKNOWN"
    if method == "NONE" and set(attrs) - {"METHOD"}:
        return "UNKNOWN"
    return method


def _first_encrypted_method(text: str, tag: str) -> str | None:
    for line in text.splitlines():
        method = _hls_tag_method(_hls_line(line), tag)
        if method is not None and method != "NONE":
            return method
    return None


def _drm_refused_encryption(method: str, *, session: bool = False) -> DrmRefused:
    kind = "session encryption method" if session else "encryption method"
    msg = (
        f"Live manifest uses {kind} {method}. "
        "WebMedia DL records clear manifests only and does not circumvent DRM."
    )
    return DrmRefused(msg)


def _refuse_encrypted_session_key(text: str) -> None:
    method = _first_encrypted_method(text, "#EXT-X-SESSION-KEY:")
    if method is None:
        return
    raise _drm_refused_encryption(method, session=True)


def _refuse_encrypted_media_key(text: str) -> None:
    method = _first_encrypted_method(text, "#EXT-X-KEY:")
    if method is None:
        return
    raise _drm_refused_encryption(method)


def _refuse_hls_playlist_drm(text: str) -> None:
    """Refuse Widevine/FairPlay/cenc/skd signals. Per-line EXT-X-KEY stays mixed-prefix."""
    _refuse_encrypted_session_key(text)
    skip = {
        pattern.pattern
        for pattern in DRM_PATTERNS
        if "EXT-X-KEY" in pattern.pattern or "EXT-X-SESSION-KEY" in pattern.pattern
    }
    refuse_drm([item for item in detect_drm_signals(text) if item not in skip])


def inspect_manifest(text: str) -> None:
    text = _without_bom(text)
    dash = _is_dash_manifest(text)
    if dash:
        refuse_drm(detect_drm_signals(text))
        if _DASH_CONTENT_PROTECTION.search(text):
            msg = "DASH ContentProtection is refused."
            raise DrmRefused(msg)
        return
    _refuse_hls_playlist_drm(text)
    if _clear_hls_parts(text, "https://live.invalid/"):
        return
    _refuse_encrypted_media_key(text)


def recordable_segment_urls(text: str, base: str) -> list[str]:
    return [part.url for part in recordable_parts(text, base)]


def recordable_parts(text: str, base: str) -> list[ManifestPart]:
    text = _without_bom(text)
    dash = _is_dash_manifest(text)
    if dash:
        refuse_drm(detect_drm_signals(text))
        if _DASH_CONTENT_PROTECTION.search(text):
            msg = "DASH ContentProtection is refused."
            raise DrmRefused(msg)
        return _dash_parts(text, base)
    _refuse_hls_playlist_drm(text)
    parts = _clear_hls_parts(text, base)
    if not parts:
        _refuse_encrypted_media_key(text)
    return parts


def _join(base: str, href: str) -> str:
    if _live_playlist_locator(base):
        parsed = urlparse(base)
        stripped = parsed.path.rstrip("/")
        if parsed.path != stripped:
            base = parsed._replace(path=stripped).geturl()
    return urljoin(base, href)


def _parse_dash_range(text: str | None) -> tuple[int | None, int | None]:
    """Parse DASH `range` / `mediaRange` into offset+length.

    Closed `start-end` is inclusive. Open `start-` (RFC 2616 byte-range-spec)
    means from that offset through the end of the fetched object. Suffix
    `-N` means the last N bytes (`start=-N`).
    """
    if not text:
        return None, None
    stripped = text.strip()
    suffix = re.fullmatch(r"-\s*(\d+)", stripped)
    if suffix:
        count = int(suffix.group(1))
        if count <= 0:
            return None, None
        return -count, None
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)?", stripped)
    if match is None:
        return None, None
    start = int(match.group(1))
    end_raw = match.group(2)
    if end_raw is None:
        return start, None
    end = int(end_raw)
    if end < start:
        return None, None
    return start, end - start + 1


def _parse_byterange(
    text: str | None, *, default_offset: int | None
) -> tuple[int | None, int | None]:
    if not text:
        return default_offset, None
    match = re.fullmatch(r"(\d+)\s*(?:@\s*(\d+))?", text.strip())
    if match is None:
        return default_offset, None
    length = int(match.group(1))
    offset = int(match.group(2)) if match.group(2) is not None else default_offset
    return offset, length


def _clear_hls_parts(text: str, base: str) -> list[ManifestPart]:
    """Collect MAP + URI parts until the first non-NONE EXT-X-KEY."""
    parts: list[ManifestPart] = []
    pending: tuple[int | None, int] | None = None
    next_offset: dict[str, int] = {}
    media_sequence = 0
    index = 0
    for line in text.splitlines():
        stripped = _hls_line(line)
        if not stripped:
            continue
        if stripped.upper().startswith("#EXT-X-MEDIA-SEQUENCE:"):
            raw = stripped.split(":", 1)[1].strip()
            try:
                media_sequence = int(raw)
            except ValueError:
                media_sequence = 0
            continue
        method = _hls_tag_method(stripped, "#EXT-X-KEY:")
        if method is not None:
            if method != "NONE":
                break
            continue
        if stripped.upper().startswith("#EXT-X-MAP:"):
            attrs, _duplicates = _hls_attr_map(stripped.split(":", 1)[-1])
            href = attrs.get("URI")
            if not href:
                continue
            uri = _join(base, href)
            offset, length = _parse_byterange(attrs.get("BYTERANGE"), default_offset=0)
            parts.append(ManifestPart(uri, offset, length, media_sequence + index))
            index += 1
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
        occurrence = media_sequence + index
        index += 1
        if pending is not None:
            offset, length = pending
            pending = None
            if offset is None:
                offset = next_offset.get(url, 0)
            parts.append(ManifestPart(url, offset, length, occurrence))
            next_offset[url] = offset + length
            continue
        parts.append(ManifestPart(url, occurrence=occurrence))
    return parts


def _attrs(blob: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for key, double, single in _DASH_ATTR.findall(blob):
        parsed[key.lower()] = html.unescape(double or single)
    return parsed


def _dash_href(value: str | None) -> str:
    return html.unescape((value or "").strip())


def _dash_baseurls(text: str) -> list[str]:
    found: list[str] = []
    for cdata, plain in _DASH_BASE_URL.findall(text):
        href = re.sub(r"\s+", "", _dash_href(cdata or plain))
        if href:
            found.append(href)
    return found


def _int_attr(attrs: dict[str, str], name: str, default: int) -> int:
    try:
        return int(attrs.get(name) or default)
    except ValueError:
        return default


def _iso8601_duration_seconds(value: str | None) -> float | None:
    """Parse a DASH ISO 8601 duration (`PT…` / `PnDTnHnMnS`). Calendar Y/M units are refused."""
    if not value:
        return None
    match = _ISO_DURATION.fullmatch(value.strip())
    if match is None:
        return None
    years, months, days, hours, minutes, seconds = match.groups()
    if years and float(years) != 0:
        return None
    if months and float(months) != 0:
        return None
    total = 0.0
    if days:
        total += float(days) * 86400
    if hours:
        total += float(hours) * 3600
    if minutes:
        total += float(minutes) * 60
    if seconds:
        total += float(seconds)
    if not (days or hours or minutes or seconds):
        return None
    return total


def _template_last_number(
    attrs: dict[str, str],
    start: int,
    *,
    period_seconds: float | None,
) -> int | None:
    end_raw = attrs.get("endnumber")
    if end_raw:
        try:
            last = int(end_raw)
        except ValueError:
            last = start
        return min(max(last, start), start + MAX_TIMELINE_SEGMENTS - 1)
    duration_ticks = _int_attr(attrs, "duration", 0)
    timescale = _int_attr(attrs, "timescale", 1)
    if duration_ticks <= 0 or timescale <= 0 or not period_seconds or period_seconds <= 0:
        return None
    segment_seconds = duration_ticks / timescale
    count = math.ceil(period_seconds / segment_seconds - 1e-9)
    count = min(max(int(count), 1), MAX_TIMELINE_SEGMENTS)
    return start + count - 1


def _format_token(value: int, spec: str | None) -> str:
    if not spec:
        return str(value)
    token = spec[1:] if spec.startswith("%") else spec
    try:
        return format(value, token)
    except ValueError:
        return str(value)


def _expand_bandwidth(text: str, bandwidth: str) -> str:
    """Bind `$Bandwidth$` / `$Bandwidth%0Nd$` once the Representation bandwidth is known."""

    def replace(match: re.Match[str]) -> str:
        try:
            value = int(bandwidth)
        except ValueError:
            return bandwidth
        return _format_token(value, match.group(1))

    return _BANDWIDTH_TOKEN.sub(replace, text)


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
    text = text.replace("$RepresentationID$", representation)
    text = _expand_bandwidth(text, bandwidth)
    return text.replace("\x00", "$")


def _resolved_dash_href(
    href: str,
    *,
    representation: str | None = None,
    bandwidth: str | None = None,
    number: int | None = None,
    time_value: int | None = None,
) -> str | None:
    """Expand DASH identifier tokens; return None when `$Number$` / `$Time$` remain."""
    resolved = _expand_dash_template(
        href.strip(),
        number=number,
        time_value=time_value,
        representation=representation or "1",
        bandwidth=bandwidth or "1",
    )
    if _UNEXPANDED_DASH.search(resolved):
        return None
    return resolved


def _expand_locator_tokens(
    value: str,
    *,
    representation: str | None = None,
    bandwidth: str | None = None,
) -> str:
    """Bind DASH BaseURL `$RepresentationID$` / `$Bandwidth$` once the Representation is known."""
    if "$" not in value:
        return value
    text = value
    if representation is not None:
        text = text.replace("$RepresentationID$", representation)
    if bandwidth is not None:
        text = _expand_bandwidth(text, bandwidth)
    return text


def _template_urls(
    attr_blob: str,
    body: str,
    base: str,
    *,
    representation: str | None = None,
    bandwidth: str | None = None,
    period_seconds: float | None = None,
    inherited_timescale: str | None = None,
    include_initialization: bool = True,
    include_media: bool = True,
) -> list[str]:
    attrs = _attrs(attr_blob)
    if inherited_timescale and not attrs.get("timescale"):
        attrs["timescale"] = inherited_timescale
    representation = representation or attrs.get("id") or attrs.get("representationid") or "1"
    bandwidth = bandwidth or attrs.get("bandwidth") or "1"
    base = _expand_locator_tokens(base, representation=representation, bandwidth=bandwidth)
    start = _int_attr(attrs, "startnumber", 1)
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
        if _UNEXPANDED_DASH.search(resolved):
            return
        urls.append(_join(base, resolved))

    if include_initialization:
        add(attrs.get("initialization"), number=start)
    if not include_media:
        return urls
    media = attrs.get("media")
    samples = list(_DASH_S.finditer(body or ""))
    if samples and media:
        clock = 0
        number = start
        for item in samples:
            sattrs = _attrs(item.group(1))
            if "t" in sattrs:
                clock = int(sattrs["t"])
            if "n" in sattrs:
                number = _int_attr(sattrs, "n", number)
            duration = int(sattrs.get("d") or 0)
            repeats = int(sattrs.get("r") or 0)
            count = (
                max(MAX_TIMELINE_SEGMENTS - len(urls), 1) if repeats < 0 else max(repeats + 1, 1)
            )
            count = min(count, MAX_TIMELINE_SEGMENTS)
            if repeats < 0 and duration > 0 and period_seconds is not None:
                timescale = _int_attr(attrs, "timescale", 1)
                if timescale > 0:
                    remaining = period_seconds * timescale - clock
                    fitted = math.ceil(remaining / duration - 1e-9)
                    if fitted <= 0:
                        continue
                    count = min(count, fitted)
            for _ in range(count):
                add(media, number=number, time_value=clock)
                number += 1
                clock += duration
        return urls
    last = _template_last_number(attrs, start, period_seconds=period_seconds)
    if media and last is not None:
        duration = _int_attr(attrs, "duration", 0)
        clock = 0
        for number in range(start, last + 1):
            add(media, number=number, time_value=clock)
            clock += duration
        return urls
    add(media, number=start)
    return urls


def _is_directory_base(resolved: str) -> bool:
    suffix = Path(urlparse(resolved).path).suffix.lower()
    return resolved.endswith("/") or not suffix


def _has_indexed_segments(text: str) -> bool:
    return bool(_DASH_SEGMENT_BASE.search(text) or _DASH_SEGMENT_LIST.search(text))


def _has_segment_addressing(text: str) -> bool:
    return bool(_DASH_TEMPLATE.search(text) or _has_indexed_segments(text))


def _strip_segment_addressing(text: str) -> str:
    return _strip_blocks(
        _strip_blocks(_strip_blocks(text, _DASH_TEMPLATE), _DASH_SEGMENT_LIST),
        _DASH_SEGMENT_BASE,
    )


def _advance_base(current: str, href: str) -> tuple[str, str | None]:
    """Step one BaseURL. Directories (including unexpanded tokens) update the prefix."""
    resolved = _join(current, href)
    if _is_directory_base(resolved):
        next_base = resolved if resolved.endswith("/") else f"{resolved}/"
        return next_base, None
    if _UNEXPANDED_DASH.search(resolved):
        return current, None
    return current, resolved


def _collect_baseurls(
    text: str,
    current: str,
    add: AddPart,
    *,
    emit_files: bool = True,
    representation: str | None = None,
    bandwidth: str | None = None,
) -> str:
    current = _expand_locator_tokens(current, representation=representation, bandwidth=bandwidth)
    for href in _dash_baseurls(text):
        href = _expand_locator_tokens(href, representation=representation, bandwidth=bandwidth)
        current, file_url = _advance_base(current, href)
        if file_url is not None and emit_files:
            add(ManifestPart(file_url))
    return current


def _file_baseurl(
    text: str,
    current: str,
    *,
    representation: str | None = None,
    bandwidth: str | None = None,
) -> str | None:
    """Resolve SegmentBase/SegmentList media objects.

    Earlier extensionless BaseURLs stay directory prefixes. The last BaseURL
    without a trailing slash is the ranged object even when it has no suffix.
    """
    current = _expand_locator_tokens(current, representation=representation, bandwidth=bandwidth)
    hrefs = [
        _expand_locator_tokens(href, representation=representation, bandwidth=bandwidth)
        for href in _dash_baseurls(text)
    ]
    file_url = None
    last_index = len(hrefs) - 1
    for index, href in enumerate(hrefs):
        resolved = _join(current, href)
        last_object = (
            index == last_index
            and not resolved.endswith("/")
            and _UNEXPANDED_DASH.search(resolved) is None
        )
        if last_object:
            file_url = resolved
            current = resolved
            continue
        current = _advance_base(current, href)[0]
    return file_url


def _collect_segment_base(
    text: str,
    file_url: str,
    add: AddPart,
    *,
    representation: str | None = None,
    bandwidth: str | None = None,
) -> None:
    for match in _DASH_SEGMENT_BASE.finditer(text):
        attrs = _attrs(match.group(1))
        body = match.group(2) or ""
        for init in _INIT_TAG.finditer(body):
            iattrs = _attrs(init.group(1))
            href = iattrs.get("sourceurl")
            start, length = _parse_dash_range(iattrs.get("range"))
            if href:
                resolved = _resolved_dash_href(
                    href, representation=representation, bandwidth=bandwidth
                )
                if resolved is None:
                    continue
                url = _join(file_url, resolved)
            else:
                url = file_url
            add(ManifestPart(url, start, length))
        index_start, index_length = _parse_dash_range(attrs.get("indexrange"))
        if index_start is not None:
            add(ManifestPart(file_url, index_start, index_length))
        media_start, media_length = _parse_dash_range(attrs.get("mediarange"))
        if media_start is not None:
            add(ManifestPart(file_url, media_start, media_length))


def _collect_segments(
    text: str,
    current: str,
    add: AddPart,
    seen_urls: set[str],
    *,
    representation: str | None = None,
    bandwidth: str | None = None,
    include_templates: bool = True,
    period_seconds: float | None = None,
    inherited_timescale: str | None = None,
) -> None:
    current = _expand_locator_tokens(current, representation=representation, bandwidth=bandwidth)
    if include_templates:
        for match in _DASH_TEMPLATE.finditer(text):
            attr_blob = match.group(1)
            body = match.group(2) or ""
            for url in _template_urls(
                attr_blob,
                body,
                current,
                representation=representation,
                bandwidth=bandwidth,
                period_seconds=period_seconds,
                inherited_timescale=inherited_timescale,
                include_media=False,
            ):
                add(ManifestPart(url))
            start_number = _int_attr(_attrs(attr_blob), "startnumber", 1)
            for init in _INIT_TAG.finditer(body):
                iattrs = _attrs(init.group(1))
                href = iattrs.get("sourceurl")
                start, length = _parse_dash_range(iattrs.get("range"))
                if not href:
                    continue
                resolved = _resolved_dash_href(
                    href,
                    number=start_number,
                    representation=representation,
                    bandwidth=bandwidth,
                )
                if resolved is None:
                    continue
                add(ManifestPart(_join(current, resolved), start, length))
            for url in _template_urls(
                attr_blob,
                body,
                current,
                representation=representation,
                bandwidth=bandwidth,
                period_seconds=period_seconds,
                inherited_timescale=inherited_timescale,
                include_initialization=False,
            ):
                add(ManifestPart(url))
    file_url = _file_baseurl(text, current, representation=representation, bandwidth=bandwidth)
    outside_templates = _strip_blocks(text, _DASH_TEMPLATE)
    for match in _INIT_TAG.finditer(outside_templates):
        attrs = _attrs(match.group(1))
        href = attrs.get("sourceurl")
        start, length = _parse_dash_range(attrs.get("range"))
        if href:
            resolved = _resolved_dash_href(href, representation=representation, bandwidth=bandwidth)
            if resolved is None:
                continue
            add(ManifestPart(_join(current, resolved), start, length))
        elif file_url is not None and (start is not None or length is not None):
            add(ManifestPart(file_url, start, length))
    for match in _SEGMENT_URL_TAG.finditer(text):
        attrs = _attrs(match.group(1))
        href = attrs.get("media")
        start, length = _parse_dash_range(attrs.get("mediarange") or attrs.get("range"))
        if href:
            resolved = _resolved_dash_href(href, representation=representation, bandwidth=bandwidth)
            if resolved is None:
                continue
            add(ManifestPart(_join(current, resolved), start, length))
        elif file_url is not None and (start is not None or length is not None):
            add(ManifestPart(file_url, start, length))
    if not include_templates or _DASH_TEMPLATE.search(text) or _has_indexed_segments(text):
        return
    for double, single in _DASH_MEDIA.findall(text):
        media = _dash_href(double or single)
        resolved = _resolved_dash_href(
            media,
            number=1,
            time_value=0,
            representation=representation,
            bandwidth=bandwidth,
        )
        if resolved is None:
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


_LIVE_PLAYLIST_SUFFIXES = (".m3u8", ".m3u", ".mpd")


def _live_playlist_locator(url: str) -> bool:
    """True when the path names an HLS/DASH playlist, ignoring query, fragment, and case."""
    path = urlparse(url).path.lower().rstrip("/")
    return path.endswith(_LIVE_PLAYLIST_SUFFIXES)


def _preferred_hls_variant(text: str, base: str) -> str | None:
    variants: list[tuple[int, str]] = []
    pending: int | None = None
    for line in text.splitlines():
        stripped = _hls_line(line)
        if stripped.startswith("#EXT-X-STREAM-INF:"):
            attrs, duplicates = _hls_attr_map(stripped.split(":", 1)[1])
            raw = attrs.get("BANDWIDTH")
            pending = (
                int(raw)
                if raw is not None and raw.isdigit() and "BANDWIDTH" not in duplicates
                else None
            )
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
    seen: set[tuple[str, int | None, int | None, int]] = set()
    seen_urls: set[str] = set()

    def add(part: ManifestPart) -> None:
        key = (part.url, part.start, part.length, part.occurrence)
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
    period_seconds: float | None = None,
    inherited_timescale: str | None = None,
) -> tuple[int, str]:
    rattrs = _attrs(match.group(1))
    body = match.group(2) or ""
    representation = rattrs.get("id")
    bandwidth_token = rattrs.get("bandwidth")
    working = body if _has_segment_addressing(body) else f"{inherited_templates}{body}"
    has_segment_base = bool(_DASH_SEGMENT_BASE.search(working))
    has_indexed = has_segment_base or bool(_DASH_SEGMENT_LIST.search(working))
    local_base = _collect_baseurls(
        body,
        current,
        add,
        emit_files=not has_indexed,
        representation=representation,
        bandwidth=bandwidth_token,
    )
    if has_segment_base:
        file_url = (
            _file_baseurl(
                working,
                current,
                representation=representation,
                bandwidth=bandwidth_token,
            )
            or local_base
        )
        _collect_segment_base(
            working,
            file_url,
            add,
            representation=representation,
            bandwidth=bandwidth_token,
        )
        try:
            bandwidth = int(rattrs.get("bandwidth") or 0)
        except ValueError:
            bandwidth = 0
        return bandwidth, _dash_kind(rattrs)
    _collect_segments(
        working,
        local_base,
        add,
        seen_urls,
        representation=rattrs.get("id"),
        bandwidth=rattrs.get("bandwidth"),
        period_seconds=period_seconds,
        inherited_timescale=rattrs.get("timescale") or inherited_timescale,
    )
    try:
        bandwidth = int(rattrs.get("bandwidth") or 0)
    except ValueError:
        bandwidth = 0
    return bandwidth, _dash_kind(rattrs)


def _dash_scope_groups(
    text: str,
    base: str,
    *,
    period_seconds: float | None = None,
    inherited_timescale: str | None = None,
    inherited_templates: str = "",
) -> list[tuple[int, str, list[ManifestPart]]]:
    parts, seen_urls, add = _new_part_bucket()
    representations = list(_REPRESENTATION.finditer(text))
    prefix = text[: representations[0].start()] if representations else text
    resolve_base = _collect_baseurls(
        prefix, base, add, emit_files=not _has_indexed_segments(prefix)
    )
    inherited = (
        prefix if representations and _has_segment_addressing(prefix) else ""
    ) or inherited_templates
    groups: list[tuple[int, str, list[ManifestPart]]] = []
    for rep in representations:
        bucket, bucket_urls, bucket_add = _new_part_bucket()
        bandwidth, kind = _collect_representation(
            rep,
            resolve_base,
            bucket_add,
            bucket_urls,
            inherited_templates=inherited,
            period_seconds=period_seconds,
            inherited_timescale=inherited_timescale,
        )
        groups.append((bandwidth, kind, [*parts, *bucket] if parts else bucket))
    remainder = _strip_blocks(text, _REPRESENTATION) if representations else text
    if representations:
        suffix = text[representations[-1].end() :]
        resolve_base = _collect_baseurls(
            suffix, resolve_base, add, emit_files=not _has_indexed_segments(suffix)
        )
        if inherited:
            remainder = _strip_segment_addressing(remainder)
    elif not _has_segment_addressing(remainder):
        remainder = f"{inherited_templates}{remainder}"
    _collect_segments(
        remainder,
        resolve_base,
        add,
        seen_urls,
        include_templates=not representations,
        period_seconds=period_seconds,
        inherited_timescale=inherited_timescale,
    )
    if groups:
        return groups
    return [(0, "unknown", parts)] if parts else []


def _dash_adaptation_groups(
    text: str,
    base: str,
    as_attrs: dict[str, str],
    *,
    period_seconds: float | None = None,
    inherited_timescale: str | None = None,
    inherited_templates: str = "",
) -> list[tuple[int, str, list[ManifestPart]]]:
    without_rep = _strip_blocks(text, _REPRESENTATION)
    parts, seen_urls, add = _new_part_bucket()
    as_base = _collect_baseurls(
        without_rep, base, add, emit_files=not _has_indexed_segments(without_rep)
    )
    as_inherited = without_rep if _has_segment_addressing(without_rep) else ""
    inherited = as_inherited or inherited_templates
    as_kind = _dash_kind(as_attrs)
    timescale = as_attrs.get("timescale") or inherited_timescale
    representations = list(_REPRESENTATION.finditer(text))
    if not representations:
        _collect_segments(
            text,
            as_base,
            add,
            seen_urls,
            period_seconds=period_seconds,
            inherited_timescale=timescale,
        )
        return [(0, as_kind, parts)] if parts else []
    groups: list[tuple[int, str, list[ManifestPart]]] = []
    for rep in representations:
        bucket, bucket_urls, bucket_add = _new_part_bucket()
        bandwidth, kind = _collect_representation(
            rep,
            as_base,
            bucket_add,
            bucket_urls,
            inherited_templates=inherited,
            period_seconds=period_seconds,
            inherited_timescale=timescale,
        )
        groups.append(
            (
                bandwidth,
                kind if kind != "unknown" else as_kind,
                [*parts, *bucket] if parts else bucket,
            )
        )
    return groups


def _select_dash_kinds(
    groups: list[tuple[int, str, list[ManifestPart]]],
) -> dict[str, list[ManifestPart]]:
    populated = [(bandwidth, kind, parts) for bandwidth, kind, parts in groups if parts]
    selected: dict[str, list[ManifestPart]] = {}
    if not populated:
        return selected
    videos = [item for item in populated if item[1] == "video"]
    audios = [item for item in populated if item[1] == "audio"]
    if videos:
        selected["video"] = max(videos, key=lambda item: item[0])[2]
    if audios:
        selected["audio"] = max(audios, key=lambda item: item[0])[2]
    if not selected:
        best = max(populated, key=lambda item: item[0])
        selected[best[1] if best[1] != "unknown" else "video"] = best[2]
    return selected


def _select_dash_group(
    groups: list[tuple[int, str, list[ManifestPart]]],
) -> list[ManifestPart]:
    kinds = _select_dash_kinds(groups)
    if "video" in kinds:
        return kinds["video"]
    if "audio" in kinds:
        return kinds["audio"]
    return next(iter(kinds.values()), [])


def _period_kind_parts(
    body: str,
    base: str,
    *,
    period_seconds: float | None = None,
    inherited_timescale: str | None = None,
    inherited_templates: str = "",
) -> dict[str, list[ManifestPart]]:
    shared, shared_urls, shared_add = _new_part_bucket()
    period_without_as = _strip_blocks(body, _ADAPTATION_SET)
    representations_present = bool(_REPRESENTATION.search(body))
    period_base = _collect_baseurls(
        period_without_as,
        base,
        shared_add,
        emit_files=not representations_present and not _has_indexed_segments(period_without_as),
    )
    groups: list[tuple[int, str, list[ManifestPart]]] = []
    adaptations = list(_ADAPTATION_SET.finditer(body))
    period_inherited = (
        period_without_as if _has_segment_addressing(period_without_as) else ""
    ) or inherited_templates
    if not adaptations:
        groups.extend(
            _dash_scope_groups(
                body,
                period_base,
                period_seconds=period_seconds,
                inherited_timescale=inherited_timescale,
                inherited_templates=inherited_templates,
            )
        )
    else:
        leftover = (
            _strip_segment_addressing(period_without_as)
            if _has_segment_addressing(period_without_as)
            else period_without_as
        )
        _collect_segments(
            leftover,
            period_base,
            shared_add,
            shared_urls,
            period_seconds=period_seconds,
            inherited_timescale=inherited_timescale,
        )
        for adaptation in adaptations:
            groups.extend(
                _dash_adaptation_groups(
                    adaptation.group(2) or "",
                    period_base,
                    _attrs(adaptation.group(1)),
                    period_seconds=period_seconds,
                    inherited_timescale=inherited_timescale,
                    inherited_templates=period_inherited,
                )
            )
    selected = _select_dash_kinds(groups) if groups else {"video": list(shared)}
    result: dict[str, list[ManifestPart]] = {}
    for kind, parts in selected.items():
        if not parts:
            continue
        result[kind] = [*shared, *parts] if groups else list(parts)
    return result


def _period_parts(body: str, base: str) -> list[ManifestPart]:
    kinds = _period_kind_parts(body, base)
    if "video" in kinds:
        return kinds["video"]
    if "audio" in kinds:
        return kinds["audio"]
    return next(iter(kinds.values()), [])


def _dash_parts(text: str, base: str) -> list[ManifestPart]:
    kinds = _dash_kind_parts(text, base)
    if "video" in kinds:
        return kinds["video"]
    if "audio" in kinds:
        return kinds["audio"]
    return next(iter(kinds.values()), [])


def _period_window_seconds(
    period_attrs_list: list[dict[str, str]],
    mpd_seconds: float | None,
) -> list[float | None]:
    """Resolve each Period's presentation window.

    DASH Period `@duration` is explicit when present. Otherwise the window is
    the difference between adjacent `@start` values, and the last Period runs
    through MPD `mediaPresentationDuration`. A first Period without `@start`
    begins at 0. Periods that still have no timing stay unbounded so `$Number$`
    does not inherit the full MPD duration on every Period.
    """
    count = len(period_attrs_list)
    if count == 0:
        return []
    starts: list[float | None] = [
        _iso8601_duration_seconds(attrs.get("start")) for attrs in period_attrs_list
    ]
    durations: list[float | None] = [
        _iso8601_duration_seconds(attrs.get("duration")) for attrs in period_attrs_list
    ]
    if starts[0] is None:
        starts[0] = 0.0
    changed = True
    while changed:
        changed = False
        for index in range(count - 1):
            start_here = starts[index]
            start_next = starts[index + 1]
            if durations[index] is None and start_here is not None and start_next is not None:
                delta = start_next - start_here
                if delta > 0:
                    durations[index] = delta
                    changed = True
        for index in range(1, count):
            start_prev = starts[index - 1]
            duration_prev = durations[index - 1]
            if starts[index] is None and start_prev is not None and duration_prev is not None:
                starts[index] = start_prev + duration_prev
                changed = True
        last_start = starts[-1]
        if durations[-1] is None and mpd_seconds is not None and last_start is not None:
            delta = mpd_seconds - last_start
            if delta > 0:
                durations[-1] = delta
                changed = True
    return durations


def _dash_kind_parts(text: str, base: str) -> dict[str, list[ManifestPart]]:
    buckets: dict[str, list[ManifestPart]] = {}
    seen: dict[str, set[tuple[str, int | None, int | None, int]]] = {}

    periods = list(_PERIOD.finditer(text))
    mpd_match = _MPD_OPEN.search(text)
    mpd_attrs = _attrs(mpd_match.group(1)) if mpd_match else {}
    mpd_seconds = _iso8601_duration_seconds(mpd_attrs.get("mediapresentationduration"))
    mpd_prefix = text[: periods[0].start()] if periods else ""
    mpd_shared, _mpd_urls, mpd_add = _new_part_bucket()
    mpd_base = _collect_baseurls(
        mpd_prefix, base, mpd_add, emit_files=not _has_indexed_segments(mpd_prefix)
    )
    mpd_inherited = mpd_prefix if _has_segment_addressing(mpd_prefix) else ""
    scopes = (
        [(match.group(2) or "", _attrs(match.group(1))) for match in periods]
        if periods
        else [(text, {})]
    )
    windows = _period_window_seconds([attrs for _body, attrs in scopes], mpd_seconds)
    for index, ((body, period_attrs), period_seconds) in enumerate(
        zip(scopes, windows, strict=True)
    ):
        kind_parts = _period_kind_parts(
            body,
            mpd_base,
            period_seconds=period_seconds,
            inherited_timescale=period_attrs.get("timescale"),
            inherited_templates=mpd_inherited,
        )
        for kind, parts in kind_parts.items():
            bucket = buckets.setdefault(kind, list(mpd_shared) if mpd_shared else [])
            kind_seen = seen.setdefault(kind, set())
            for part in parts:
                tagged = part._replace(occurrence=index)
                key = (tagged.url, tagged.start, tagged.length, tagged.occurrence)
                if key in kind_seen:
                    continue
                kind_seen.add(key)
                bucket.append(tagged)
    return {kind: parts for kind, parts in buckets.items() if parts}


def manifest_is_live(text: str) -> bool:
    if _is_dash_manifest(text):
        match = _MPD_OPEN.search(text)
        if match is None:
            return False
        return _attrs(match.group(1)).get("type", "").lower() == "dynamic"
    if "#EXTM3U" in text:
        return "#EXT-X-ENDLIST" not in text
    return False


def hls_audio_playlist_urls(text: str, base: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        stripped = _hls_line(line)
        if not stripped.startswith("#EXT-X-MEDIA:"):
            continue
        attrs, _duplicates = _hls_attr_map(stripped.split(":", 1)[1])
        if attrs.get("TYPE", "").upper() != "AUDIO":
            continue
        uri = attrs.get("URI")
        if not uri:
            continue
        resolved = _join(base, uri)
        if resolved in seen:
            continue
        seen.add(resolved)
        urls.append(resolved)
    return urls


def _part_record_key(part: ManifestPart) -> tuple[str, int | None, int | None, int]:
    return (part.url, part.start, part.length, part.occurrence)


def _write_recorded_parts(
    parts: list[ManifestPart],
    dest: Path,
    fetch: FetchFn,
    *,
    budget: ByteBudget,
    should_stop: StopFn | None,
    live: bool,
    max_segments: int,
    cache: dict[tuple[str, int], bytes],
    recorded: set[tuple],
    written_through: dict[tuple[str, int], int] | None = None,
) -> int:
    written = 0
    through = written_through if written_through is not None else {}
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("ab" if dest.exists() else "wb") as handle:
        for part in tqdm(parts[:max_segments], desc="live-record", disable=True, unit="seg"):
            key = _part_record_key(part)
            if key in recorded:
                continue
            if should_stop is not None:
                should_stop()
            cache_key = (part.url, part.occurrence)
            if cache_key not in cache:
                status, _, data = fetch(part.url)
                if status >= 400:
                    msg = f"Live segment fetch failed with HTTP {status}."
                    raise DiscoveryError(msg)
                cache[cache_key] = data
            elif live and part.start is not None:
                needed = part.start + (part.length if part.length is not None else 0)
                if part.length is None or needed > len(cache[cache_key]):
                    status, _, data = fetch(part.url)
                    if status >= 400:
                        msg = f"Live segment fetch failed with HTTP {status}."
                        raise DiscoveryError(msg)
                    cache[cache_key] = data
            chunk = cache[cache_key]
            if part.start is not None:
                origin = part.start
                if origin < 0:
                    origin = max(0, len(chunk) + origin)
                end = origin + (part.length if part.length is not None else len(chunk) - origin)
                if live:
                    origin = max(origin, through.get(cache_key, 0))
                if origin >= end or origin >= len(chunk):
                    recorded.add(key)
                    continue
                chunk = chunk[origin:end]
                through[cache_key] = max(through.get(cache_key, 0), min(end, len(cache[cache_key])))
            budget.consume(len(chunk))
            handle.write(chunk)
            written += len(chunk)
            recorded.add(key)
    return written


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
    max_bytes: int | None = None,
    budget: ByteBudget | None = None,
    parts: list[ManifestPart] | None = None,
    rendition_kind: str | None = None,
    drm_flag: list[bool] | None = None,
) -> Path:
    dest = output
    playlist = _without_bom(playlist_text)
    bound = budget or ByteBudget(max_bytes)
    if _DASH_CONTENT_PROTECTION.search(playlist):
        msg = "DASH ContentProtection is refused."
        raise DrmRefused(msg)
    _refuse_hls_playlist_drm(playlist)
    round_parts = parts if parts is not None else recordable_parts(playlist, playlist_url)
    if not round_parts:
        _refuse_encrypted_media_key(playlist)
        msg = "Clear live playlist contained no recordable segments."
        raise DiscoveryError(msg)
    first = round_parts[0].url
    preferred = _preferred_hls_variant(playlist, playlist_url)
    if (
        parts is None
        and depth < MAX_PLAYLIST_NESTING
        and (preferred or _live_playlist_locator(first) or "#EXT-X-STREAM-INF" in playlist)
    ):
        nested = [item.url for item in round_parts if _live_playlist_locator(item.url)]
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
            budget=bound,
            rendition_kind=rendition_kind,
            drm_flag=drm_flag,
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    cache: dict[tuple[str, int], bytes] = {}
    recorded: set[tuple] = set()
    through: dict[tuple[str, int], int] = {}
    polls = max(1, min(live_polls, MAX_LIVE_POLLS))
    written = 0
    live_mode = polls > 1 or manifest_is_live(playlist)
    round_index = 0
    while True:
        try:
            inspect_manifest(playlist)
            if rendition_kind and _is_dash_manifest(playlist):
                current_parts = _dash_kind_parts(playlist, playlist_url).get(rendition_kind, [])
            elif parts is not None and round_index == 0:
                current_parts = parts
            else:
                current_parts = recordable_parts(playlist, playlist_url)
        except DrmRefused:
            if drm_flag is not None:
                drm_flag.append(True)
            if written > 0:
                break
            raise
        written += _write_recorded_parts(
            current_parts,
            dest,
            fetch,
            budget=bound,
            should_stop=should_stop,
            live=live_mode,
            max_segments=max_segments,
            cache=cache,
            recorded=recorded,
            written_through=through,
        )
        more = round_index + 1 < polls and manifest_is_live(playlist)
        if not more:
            break
        if should_stop is not None:
            should_stop()
        status, _, data = fetch(playlist_url)
        if status >= 400:
            break
        playlist = _without_bom(data.decode("utf-8", errors="replace"))
        round_index += 1
    if not dest.exists() or dest.stat().st_size == 0 or written == 0:
        msg = "Live recording produced an empty artifact."
        raise DiscoveryError(msg)
    return dest


def record_kind_streams(
    playlist_text: str,
    playlist_url: str,
    output: Path,
    fetch: FetchFn,
    *,
    max_bytes: int | None = None,
    should_stop: StopFn | None = None,
    live_polls: int = 1,
) -> list[tuple[MediaKind, Path]]:
    """Record the primary stream plus a separate audio rendition when present."""
    inspect_manifest(playlist_text)
    playlist_text = _without_bom(playlist_text)
    bound = ByteBudget(max_bytes)
    dash = _is_dash_manifest(playlist_text)
    if dash:
        kinds = _dash_kind_parts(playlist_text, playlist_url)
        mapping: list[tuple[MediaKind, str]] = []
        if "video" in kinds:
            mapping.append((MediaKind.VIDEO, "video"))
        if "audio" in kinds:
            mapping.append((MediaKind.AUDIO, "audio"))
        if mapping:
            recorded: list[tuple[MediaKind, Path]] = []
            drm_flag: list[bool] = []
            for media_kind, name in mapping:
                if drm_flag:
                    break
                dest = (
                    output
                    if len(mapping) == 1
                    else output.parent / f"{output.stem}-{name}{output.suffix or '.bin'}"
                )
                record_clear_stream(
                    playlist_text,
                    playlist_url,
                    dest,
                    fetch,
                    should_stop=should_stop,
                    live_polls=live_polls,
                    budget=bound,
                    parts=kinds[name],
                    rendition_kind=name,
                    drm_flag=drm_flag,
                )
                recorded.append((media_kind, dest))
            return recorded
        record_clear_stream(
            playlist_text,
            playlist_url,
            output,
            fetch,
            should_stop=should_stop,
            live_polls=live_polls,
            budget=bound,
        )
        return [(MediaKind.LIVE_STREAM, output)]
    audio_uris = hls_audio_playlist_urls(playlist_text, playlist_url)
    drm_flag: list[bool] = []
    record_clear_stream(
        playlist_text,
        playlist_url,
        output,
        fetch,
        should_stop=should_stop,
        live_polls=live_polls,
        budget=bound,
        drm_flag=drm_flag,
    )
    if not audio_uris or drm_flag:
        return [(MediaKind.LIVE_STREAM, output)] if not audio_uris else [(MediaKind.VIDEO, output)]
    video_dest = output
    results: list[tuple[MediaKind, Path]] = [(MediaKind.VIDEO, video_dest)]
    audio_url = audio_uris[0]
    if should_stop is not None:
        should_stop()
    status, _, data = fetch(audio_url)
    if status >= 400:
        msg = f"Live audio playlist fetch failed with HTTP {status}."
        raise DiscoveryError(msg)
    audio_dest = output.parent / f"{output.stem}-audio{output.suffix or '.bin'}"
    record_clear_stream(
        data.decode("utf-8", errors="replace"),
        audio_url,
        audio_dest,
        fetch,
        should_stop=should_stop,
        live_polls=live_polls,
        budget=bound,
        drm_flag=drm_flag,
    )
    results.append((MediaKind.AUDIO, audio_dest))
    return results
