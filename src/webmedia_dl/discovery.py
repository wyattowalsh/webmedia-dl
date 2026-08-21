"""Bounded discovery. Produces candidates and evidence, not acquisition decisions."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from webmedia_dl.domain.enums import MediaKind
from webmedia_dl.domain.models import (
    BrowserEvidence,
    FormatAlternative,
    MediaCandidate,
    MediaSource,
    PolicyProfile,
)
from webmedia_dl.errors import DiscoveryError
from webmedia_dl.identity import host_of, identity_key_for_url
from webmedia_dl.network_policy import authorize_url
from webmedia_dl.security import detect_drm_signals

DIRECT_EXTENSIONS = {
    ".mp4": MediaKind.VIDEO,
    ".webm": MediaKind.VIDEO,
    ".mkv": MediaKind.VIDEO,
    ".mov": MediaKind.VIDEO,
    ".m4v": MediaKind.VIDEO,
    ".mp3": MediaKind.AUDIO,
    ".m4a": MediaKind.AUDIO,
    ".aac": MediaKind.AUDIO,
    ".flac": MediaKind.AUDIO,
    ".wav": MediaKind.AUDIO,
    ".ogg": MediaKind.AUDIO,
    ".opus": MediaKind.AUDIO,
    ".jpg": MediaKind.IMAGE,
    ".jpeg": MediaKind.IMAGE,
    ".png": MediaKind.IMAGE,
    ".gif": MediaKind.IMAGE,
    ".webp": MediaKind.IMAGE,
    ".avif": MediaKind.IMAGE,
    ".svg": MediaKind.IMAGE,
    ".pdf": MediaKind.DOCUMENT,
    ".vtt": MediaKind.SUBTITLE,
    ".srt": MediaKind.SUBTITLE,
    ".m3u8": MediaKind.LIVE_STREAM,
    ".mpd": MediaKind.LIVE_STREAM,
}

FetchFn = Callable[[str], tuple[int, str, bytes]]


class _MediaHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[tuple[str, MediaKind]] = []
        self.meta: dict[str, str] = {}
        self.title: str | None = None
        self._in_title = False
        self.json_ld: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        mapping = dict(attrs)
        if tag == "title":
            self._in_title = True
        if tag in {"video", "audio", "source", "img", "picture"}:
            kind = (
                MediaKind.VIDEO
                if tag == "video"
                else (
                    MediaKind.AUDIO
                    if tag == "audio"
                    else (MediaKind.IMAGE if tag in {"img", "picture"} else MediaKind.UNKNOWN)
                )
            )
            for attr in ("src", "data-src", "poster"):
                value = mapping.get(attr)
                if value:
                    item_kind = MediaKind.IMAGE if attr == "poster" else kind
                    self.urls.append((value, item_kind))
            srcset = mapping.get("srcset")
            if srcset:
                for part in srcset.split(","):
                    token = part.strip().split()[0]
                    if token:
                        self.urls.append((token, kind))
        if tag == "meta":
            key = mapping.get("property") or mapping.get("name")
            content = mapping.get("content")
            if key and content:
                self.meta[key] = content
        if tag == "script" and mapping.get("type") == "application/ld+json":
            return

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            text = data.strip()
            if text:
                self.title = text


def is_direct_media_url(url: str) -> bool:
    """True when the locator itself names a media object, not a watch page."""
    return _kind_from_url(url) not in {MediaKind.PAGE, MediaKind.UNKNOWN}


def _kind_from_url(url: str) -> MediaKind:
    path = urlparse(url).path.lower()
    for ext, kind in DIRECT_EXTENSIONS.items():
        if path.endswith(ext):
            return kind
    return MediaKind.PAGE


def _candidate(
    source: MediaSource,
    url: str,
    kind: MediaKind,
    *,
    title: str | None = None,
    evidence: list[str],
    drm: list[str],
) -> MediaCandidate:
    return MediaCandidate(
        source_id=source.source_id,
        media_kind=kind,
        identity_key=identity_key_for_url(url),
        title_display=title,
        retrieval_urls=[url],
        alternatives=[],
        drm_signals=drm,
        evidence_refs=evidence,
        host=host_of(url),
        grouping_key=host_of(url),
    )


def _usable_url(value: str) -> bool:
    return bool(value) and not value.lower().startswith("javascript:")


def _walk_jsonld(node: object):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_jsonld(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_jsonld(item)


def candidates_from_manifest_json(source: MediaSource, raw: bytes) -> list[MediaCandidate]:
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return []
    payloads: list[dict] = []
    try:
        parsed = json.loads(text)
        payloads = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                payloads.append(item)
    found: list[MediaCandidate] = []
    for item in payloads:
        if not isinstance(item, dict):
            continue
        url = item.get("url") or item.get("webpage_url") or source.normalized_url
        if not isinstance(url, str) or not _usable_url(url):
            continue
        kind = MediaKind.LIVE_STREAM if item.get("is_live") else _kind_from_url(url)
        if kind is MediaKind.PAGE:
            kind = MediaKind.VIDEO
        alternatives: list[FormatAlternative] = []
        drm: list[str] = detect_drm_signals(json.dumps(item)[:4000])
        for fmt in item.get("formats") or []:
            if not isinstance(fmt, dict):
                continue
            format_id = str(fmt.get("format_id") or "")
            if not format_id:
                continue
            if fmt.get("has_drm") or fmt.get("__has_drm"):
                drm.append(f"format-drm:{format_id}")
            alternatives.append(
                FormatAlternative(
                    format_id=format_id,
                    container=fmt.get("ext"),
                    codec=fmt.get("vcodec") or fmt.get("acodec"),
                    width=fmt.get("width"),
                    height=fmt.get("height"),
                    bitrate=int(fmt["tbr"] * 1000)
                    if isinstance(fmt.get("tbr"), int | float)
                    else None,
                    drm=bool(fmt.get("has_drm") or fmt.get("__has_drm")),
                )
            )
        found.append(
            MediaCandidate(
                source_id=source.source_id,
                media_kind=kind,
                identity_key=identity_key_for_url(url, str(item["id"]) if item.get("id") else None),
                title_display=item.get("title") if item.get("title") != url else None,
                retrieval_urls=[url],
                alternatives=alternatives,
                drm_signals=sorted(set(drm)),
                evidence_refs=["discover:manifest"],
                host=host_of(url),
                grouping_key=host_of(url),
            )
        )
    return found


def discover(
    source: MediaSource,
    profile: PolicyProfile,
    *,
    fetch: FetchFn | None = None,
    html: str | None = None,
    evidence: list[BrowserEvidence] | None = None,
) -> list[MediaCandidate]:
    if source.local_path:
        path = source.local_path
        kind = _kind_from_url(path)
        if kind == MediaKind.PAGE:
            kind = MediaKind.UNKNOWN
        return [
            MediaCandidate(
                source_id=source.source_id,
                media_kind=kind,
                identity_key=f"file:{Path(path).resolve()}",
                title_display=None,
                retrieval_urls=[],
                evidence_refs=["intake:file"],
                host="local",
            )
        ]
    url = source.normalized_url or source.locator
    authorize_url(url, profile)
    seeded: list[MediaCandidate] = []
    for item in evidence or []:
        if not _usable_url(item.url):
            continue
        absolute = urljoin(url, item.url)
        item_kind = item.kind if item.kind is not MediaKind.UNKNOWN else _kind_from_url(absolute)
        seeded.append(
            _candidate(
                source,
                absolute,
                item_kind,
                evidence=["discover:browser-evidence"],
                drm=detect_drm_signals(absolute),
            )
        )
    kind = _kind_from_url(url)
    if kind != MediaKind.PAGE:
        drm = detect_drm_signals(url)
        return [
            _candidate(source, url, kind, evidence=["intake:direct"], drm=drm),
            *seeded,
        ]

    body = html
    if body is None:
        if fetch is None:
            msg = "Page discovery requires a fetch function or provided HTML."
            raise DiscoveryError(msg)
        status, content_type, data = fetch(url)
        if status >= 400:
            msg = f"Discovery fetch failed with HTTP {status}."
            raise DiscoveryError(msg)
        if len(data) > profile.max_html_bytes:
            data = data[: profile.max_html_bytes]
        body = data.decode("utf-8", errors="replace")
        if "html" not in content_type and not body.lstrip().lower().startswith("<"):
            drm = detect_drm_signals(body[:2048])
            sniff = MediaKind.UNKNOWN
            return [_candidate(source, url, sniff, evidence=["intake:bytes"], drm=drm)]

    parser = _MediaHTMLParser()
    parser.feed(body)
    drm = detect_drm_signals(body)
    title = parser.title or parser.meta.get("og:title")
    seen: set[str] = set()
    for key, kind_hint in (
        ("og:image", MediaKind.IMAGE),
        ("og:image:url", MediaKind.IMAGE),
        ("twitter:image", MediaKind.IMAGE),
        ("og:video", MediaKind.VIDEO),
        ("og:video:url", MediaKind.VIDEO),
        ("og:audio", MediaKind.AUDIO),
        ("og:audio:url", MediaKind.AUDIO),
        ("twitter:player:stream", MediaKind.VIDEO),
    ):
        meta_url = parser.meta.get(key)
        if meta_url:
            parser.urls.append((meta_url, kind_hint))
    for item in seeded:
        seen.update(item.retrieval_urls)
    found: list[MediaCandidate] = list(seeded)
    for raw, guessed in parser.urls:
        if not _usable_url(raw):
            continue
        absolute = urljoin(url, raw)
        if absolute in seen:
            continue
        seen.add(absolute)
        item_kind = _kind_from_url(absolute)
        if item_kind == MediaKind.PAGE:
            item_kind = guessed
        found.append(
            _candidate(
                source,
                absolute,
                item_kind,
                title=title,
                evidence=["discover:html"],
                drm=detect_drm_signals(absolute, *drm),
            )
        )
    ld_hits = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        body,
        flags=re.I | re.S,
    )
    for block in ld_hits:
        try:
            payload = json.loads(block)
        except json.JSONDecodeError:
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in _walk_jsonld(items):
            content_url = item.get("contentUrl") or item.get("embedUrl")
            if isinstance(content_url, str) and _usable_url(content_url):
                absolute = urljoin(url, content_url)
                if absolute in seen:
                    continue
                seen.add(absolute)
                found.append(
                    _candidate(
                        source,
                        absolute,
                        _kind_from_url(absolute),
                        title=title,
                        evidence=["discover:jsonld"],
                        drm=detect_drm_signals(absolute),
                    )
                )
    if not found:
        found.append(
            _candidate(
                source,
                url,
                MediaKind.PAGE,
                title=title,
                evidence=["discover:page-without-direct-media"],
                drm=drm,
            )
        )
    images = [item for item in found if item.media_kind is MediaKind.IMAGE]
    has_av = any(item.media_kind in {MediaKind.VIDEO, MediaKind.AUDIO} for item in found)
    if len(images) >= 3 and not has_av:
        found.append(
            _candidate(
                source,
                url,
                MediaKind.GALLERY,
                title=title,
                evidence=["discover:gallery"],
                drm=drm,
            )
        )
    return found
