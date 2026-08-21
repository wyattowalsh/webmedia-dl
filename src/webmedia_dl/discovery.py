"""Bounded discovery. Produces candidates and evidence, not acquisition decisions."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

from webmedia_dl.domain.enums import MediaKind
from webmedia_dl.domain.models import MediaCandidate, MediaSource, PolicyProfile
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
        if tag in {"video", "audio", "source", "img"}:
            src = mapping.get("src") or mapping.get("data-src")
            if src:
                kind = (
                    MediaKind.VIDEO
                    if tag == "video"
                    else (
                        MediaKind.AUDIO
                        if tag == "audio"
                        else (MediaKind.IMAGE if tag == "img" else MediaKind.UNKNOWN)
                    )
                )
                self.urls.append((src, kind))
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


def discover(
    source: MediaSource,
    profile: PolicyProfile,
    *,
    fetch: FetchFn | None = None,
    html: str | None = None,
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
    kind = _kind_from_url(url)
    if kind != MediaKind.PAGE:
        drm = detect_drm_signals(url)
        return [_candidate(source, url, kind, evidence=["intake:direct"], drm=drm)]

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
    found: list[MediaCandidate] = []
    seen: set[str] = set()
    meta_image = parser.meta.get("og:image")
    if meta_image:
        parser.urls.append((meta_image, MediaKind.IMAGE))
    og_video = parser.meta.get("og:video") or parser.meta.get("og:video:url")
    if og_video:
        parser.urls.append((og_video, MediaKind.VIDEO))
    for raw, guessed in parser.urls:
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
        for item in items:
            if not isinstance(item, dict):
                continue
            content_url = item.get("contentUrl") or item.get("url")
            if isinstance(content_url, str) and content_url.startswith("http"):
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
    return found
