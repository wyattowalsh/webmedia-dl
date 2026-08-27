"""Bounded discovery. Produces candidates and evidence, not acquisition decisions."""

from __future__ import annotations

import html
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
from webmedia_dl.errors import DiscoveryError, NetworkPolicyError
from webmedia_dl.identity import host_of, identity_key_for_url
from webmedia_dl.network_policy import BLOCKED_SCHEMES, authorize_url
from webmedia_dl.security import detect_drm_signals

DIRECT_EXTENSIONS = {
    ".mp4": MediaKind.VIDEO,
    ".webm": MediaKind.VIDEO,
    ".mkv": MediaKind.VIDEO,
    ".mov": MediaKind.VIDEO,
    ".m4v": MediaKind.VIDEO,
    ".m2ts": MediaKind.VIDEO,
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
    ".m3u": MediaKind.LIVE_STREAM,
    ".mpd": MediaKind.LIVE_STREAM,
}

_SCRIPT_ASSET_PATH_SUFFIXES = (
    ".js",
    ".mjs",
    ".cjs",
    ".css",
    ".wasm",
    ".map",
)
_DOCUMENT_ASSET_PATH_SUFFIXES = (
    ".html",
    ".htm",
    ".json",
)
_NON_MEDIA_PATH_SUFFIXES = (
    *_SCRIPT_ASSET_PATH_SUFFIXES,
    *_DOCUMENT_ASSET_PATH_SUFFIXES,
)


def _locator_path(url: str) -> str:
    return urlparse(url).path.lower().rstrip("/")


def _locator_has_script_asset_suffix(url: str) -> bool:
    path = _locator_path(url)
    return any(path.endswith(ext) for ext in _SCRIPT_ASSET_PATH_SUFFIXES)


def _locator_has_non_media_suffix(url: str) -> bool:
    path = _locator_path(url)
    return any(path.endswith(ext) for ext in _NON_MEDIA_PATH_SUFFIXES)


def _srcset_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    for part in value.split(","):
        pieces = part.strip().split()
        token = pieces[0] if pieces else ""
        if token:
            tokens.append(token)
    return tokens


FetchFn = Callable[[str], tuple[int, str, bytes]]


def _is_jsonld_script_type(value: str | None) -> bool:
    if not value:
        return False
    return value.split(";", 1)[0].strip().lower() == "application/ld+json"


class _MediaHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[tuple[str, MediaKind]] = []
        self.meta: dict[str, str] = {}
        self.title: str | None = None
        self._in_title = False
        self.json_ld: list[str] = []
        self.base_href: str | None = None
        self._in_picture = False
        self._in_video = False
        self._in_audio = False
        self._in_object = 0
        self._in_json_ld = False
        self._json_ld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        mapping = dict(attrs)
        if tag == "base" and self.base_href is None:
            href = mapping.get("href")
            if href and href.strip():
                self.base_href = href.strip()
        if tag == "title":
            self._in_title = True
        if tag == "picture":
            self._in_picture = True
        if tag in {"video", "amp-video"}:
            self._in_video = True
        if tag in {"audio", "amp-audio"}:
            self._in_audio = True
        if tag in {
            "video",
            "audio",
            "source",
            "img",
            "picture",
            "amp-img",
            "amp-video",
            "amp-audio",
        }:
            kind = (
                MediaKind.VIDEO
                if tag in {"video", "amp-video"}
                else (
                    MediaKind.AUDIO
                    if tag in {"audio", "amp-audio"}
                    else (
                        MediaKind.IMAGE
                        if tag in {"img", "picture", "amp-img"}
                        else MediaKind.UNKNOWN
                    )
                )
            )
            mime_kind = _kind_from_mime(mapping.get("type"))
            if mime_kind is not None:
                kind = mime_kind
            elif tag == "source" and self._in_picture:
                kind = MediaKind.IMAGE
            elif tag == "source" and self._in_audio:
                kind = MediaKind.AUDIO
            elif tag == "source" and self._in_video:
                kind = MediaKind.VIDEO
            for attr in ("src", "data-src", "poster"):
                value = mapping.get(attr)
                if value:
                    item_kind = MediaKind.IMAGE if attr == "poster" else kind
                    self.urls.append((value, item_kind))
            for attr in ("srcset", "data-srcset"):
                srcset = mapping.get(attr)
                if srcset:
                    for token in _srcset_tokens(srcset):
                        self.urls.append((token, kind))
        if tag == "track":
            for attr in ("src", "data-src"):
                value = mapping.get(attr)
                if value:
                    self.urls.append((value, MediaKind.SUBTITLE))
        if tag == "a":
            href = mapping.get("href")
            if href:
                self.urls.append((href, MediaKind.UNKNOWN))
        if tag == "object":
            self._in_object += 1
        if tag == "param" and self._in_object:
            name = (mapping.get("name") or "").strip().lower()
            value = mapping.get("value")
            if value and name in {"movie", "src", "url"}:
                self.urls.append((value, MediaKind.VIDEO))
        if tag in {"iframe", "embed", "object", "amp-iframe"}:
            src = mapping.get("src") or mapping.get("data") or mapping.get("data-src")
            if src:
                self.urls.append((src, MediaKind.VIDEO))
        if tag == "link":
            href = mapping.get("href")
            rel = (mapping.get("rel") or "").lower()
            as_attr = (mapping.get("as") or "").lower()
            mime = (mapping.get("type") or "").lower()
            mime_kind = _kind_from_mime(mapping.get("type"))
            media_as = as_attr in {"video", "audio", "image", "track"}
            typed_media = mime_kind not in {None, MediaKind.LIVE_STREAM}
            if href and (
                mime_kind is MediaKind.LIVE_STREAM
                or ((media_as or typed_media) and not _locator_has_non_media_suffix(href))
                or ("preload" in rel.split() and is_direct_media_url(href))
            ):
                kind = mime_kind or MediaKind.VIDEO
                if as_attr == "audio" or mime.startswith("audio/"):
                    kind = MediaKind.AUDIO
                elif as_attr == "image" or mime.startswith("image/"):
                    kind = MediaKind.IMAGE
                elif as_attr == "track":
                    kind = MediaKind.SUBTITLE
                self.urls.append((href, kind))
            if as_attr == "image":
                for token in _srcset_tokens(mapping.get("imagesrcset") or ""):
                    self.urls.append((token, MediaKind.IMAGE))
        if tag == "meta":
            key = mapping.get("property") or mapping.get("name")
            content = mapping.get("content")
            if key and content:
                self.meta[key] = content
        if tag == "script" and _is_jsonld_script_type(mapping.get("type")):
            self._in_json_ld = True
            self._json_ld_parts = []
            return

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_json_ld:
            self.json_ld.append("".join(self._json_ld_parts))
            self._in_json_ld = False
            self._json_ld_parts = []
        if tag == "title":
            self._in_title = False
        if tag == "picture":
            self._in_picture = False
        if tag in {"video", "amp-video"}:
            self._in_video = False
        if tag in {"audio", "amp-audio"}:
            self._in_audio = False
        if tag == "object" and self._in_object:
            self._in_object -= 1

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._json_ld_parts.append(data)
        if self._in_title:
            text = data.strip()
            if text:
                self.title = text


def _parse_jsonld_block(block: str) -> object | None:
    text = block.strip()
    if text.startswith("<!--"):
        text = text.removeprefix("<!--")
        if text.endswith("-->"):
            text = text[:-3]
        text = text.strip()
    if text.startswith("<![CDATA["):
        text = text.removeprefix("<![CDATA[")
        if text.endswith("]]>"):
            text = text[:-3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        decoded = html.unescape(text)
        if decoded == text:
            return None
        try:
            return json.loads(decoded)
        except json.JSONDecodeError:
            return None


def _kind_from_mime(mime: str | None) -> MediaKind | None:
    if not mime:
        return None
    text = mime.lower()
    if "mpegurl" in text or "dash+xml" in text:
        return MediaKind.LIVE_STREAM
    if text.startswith("video/"):
        return MediaKind.VIDEO
    if text.startswith("audio/"):
        return MediaKind.AUDIO
    if text.startswith("image/"):
        return MediaKind.IMAGE
    return None


_MPD_HINT = re.compile(r"<(?:[A-Za-z_][\w.-]*:)?MPD\b", re.I)


def _sniff_live_manifest(content_type: str, body: str) -> bool:
    """True when a non-HTML fetch is itself an HLS/DASH playlist."""
    if _kind_from_mime(content_type) is MediaKind.LIVE_STREAM:
        return True
    stripped = body
    while True:
        trimmed = stripped.lstrip("\ufeff").lstrip()
        if trimmed == stripped:
            break
        stripped = trimmed
    if stripped.startswith("#EXTM3U"):
        return True
    if "html" in content_type.lower():
        return False
    return _MPD_HINT.search(stripped[:8192]) is not None


def is_direct_media_url(url: str) -> bool:
    """True when the locator itself names a media object, not a watch page."""
    return _kind_from_url(url) not in {MediaKind.PAGE, MediaKind.UNKNOWN}


def _kind_from_url(url: str) -> MediaKind:
    path = _locator_path(url)
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


def _usable_url(value: str, profile: PolicyProfile | None = None) -> bool:
    text = value.strip()
    if not text:
        return False
    scheme = (urlparse(text).scheme or "").lower()
    if scheme in BLOCKED_SCHEMES:
        return False
    if not scheme:
        return True
    if profile is None:
        return True
    try:
        authorize_url(text, profile)
    except NetworkPolicyError:
        return False
    return True


def _document_base(page_url: str, base_href: str | None) -> str:
    """Resolve relative locators against the first HTML ``<base href>``."""
    href = (base_href or "").strip()
    if not href:
        return page_url
    resolved = urljoin(page_url, href)
    parsed = urlparse(resolved)
    scheme = (parsed.scheme or "").lower()
    if scheme in BLOCKED_SCHEMES or scheme not in {"http", "https"} or not parsed.netloc:
        return page_url
    return resolved


def _candidates_from_evidence(
    source: MediaSource,
    evidence: list[BrowserEvidence] | None,
    base: str,
    profile: PolicyProfile,
) -> list[MediaCandidate]:
    seeded: list[MediaCandidate] = []
    for item in evidence or []:
        absolute = urljoin(base, item.url)
        if not _usable_url(absolute, profile):
            continue
        if _locator_has_script_asset_suffix(absolute):
            continue
        item_kind = _kind_from_evidence(absolute, item.kind)
        seeded.append(
            _candidate(
                source,
                absolute,
                item_kind,
                evidence=["discover:browser-evidence"],
                drm=detect_drm_signals(absolute),
            )
        )
    return seeded


def _kind_from_url_or_guess(url: str, guessed: MediaKind) -> MediaKind | None:
    """Resolve kind from the locator, keeping subtitle hints on HLS WebVTT playlists.

    `track[src]` and `as=track` are subtitles even when the locator is `.m3u8`
    / `.m3u` / `.mpd`. A suffix-based live kind would steal `live_stream` from
    the actual media playlist on mixed pages.
    """
    if guessed is MediaKind.SUBTITLE:
        return MediaKind.SUBTITLE
    item_kind = _kind_from_url(url)
    if item_kind == MediaKind.PAGE:
        if guessed in {MediaKind.UNKNOWN, MediaKind.PAGE}:
            return None
        return guessed
    return item_kind


def _kind_from_evidence(url: str, hinted: MediaKind) -> MediaKind:
    resolved = _kind_from_url_or_guess(url, hinted)
    if resolved is not None:
        return resolved
    return _kind_from_url(url)


def _kind_from_jsonld(item: dict, url: str) -> MediaKind:
    kind = _kind_from_url(url)
    if kind not in {MediaKind.PAGE, MediaKind.UNKNOWN}:
        return kind
    raw = item.get("@type") or item.get("type")
    types = raw if isinstance(raw, list) else [raw]
    joined = " ".join(str(token) for token in types if token).lower()
    if any(token in joined for token in ("video", "movie", "clip", "broadcast")):
        return MediaKind.VIDEO
    if any(token in joined for token in ("audio", "music", "podcast", "song")):
        return MediaKind.AUDIO
    if any(token in joined for token in ("image", "photograph", "photo")):
        return MediaKind.IMAGE
    return kind


def _jsonld_locator_urls(raw: object) -> list[str]:
    items = raw if isinstance(raw, list) else [raw]
    found: list[str] = []
    for item in items:
        if isinstance(item, str):
            found.append(item)
        elif isinstance(item, dict):
            token = item.get("@id") or item.get("url")
            if isinstance(token, str):
                found.append(token)
    return found


def _walk_jsonld(node: object):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _walk_jsonld(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_jsonld(item)


def candidates_from_manifest_json(
    source: MediaSource, raw: bytes, profile: PolicyProfile | None = None
) -> list[MediaCandidate]:
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
        if not isinstance(url, str) or not _usable_url(url, profile):
            continue
        kind = _kind_from_url(url)
        ext = str(item.get("ext") or "").lower().lstrip(".")
        if kind is MediaKind.LIVE_STREAM or ext in {"m3u8", "m3u", "mpd"}:
            kind = MediaKind.LIVE_STREAM
        elif kind is MediaKind.PAGE:
            kind = MediaKind.VIDEO
        alternatives: list[FormatAlternative] = []
        drm: list[str] = detect_drm_signals(json.dumps(item, default=str))
        for fmt in item.get("formats") or []:
            if not isinstance(fmt, dict):
                continue
            format_id = str(fmt.get("format_id") or "")
            if not format_id:
                continue
            if fmt.get("has_drm") or fmt.get("__has_drm"):
                drm.append(f"format-drm:{format_id}")
            vcodec = fmt.get("vcodec")
            acodec = fmt.get("acodec")
            if isinstance(vcodec, str) and vcodec.lower() in {"none", "null"}:
                vcodec = None
            if isinstance(acodec, str) and acodec.lower() in {"none", "null"}:
                acodec = None
            alternatives.append(
                FormatAlternative(
                    format_id=format_id,
                    container=fmt.get("ext"),
                    codec=vcodec or acodec,
                    vcodec=vcodec if isinstance(vcodec, str) else None,
                    acodec=acodec if isinstance(acodec, str) else None,
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
    kind = _kind_from_url(url)
    if kind != MediaKind.PAGE:
        drm = detect_drm_signals(url)
        return [
            _candidate(source, url, kind, evidence=["intake:direct"], drm=drm),
            *_candidates_from_evidence(source, evidence, url, profile),
        ]

    body = html
    if body is not None:
        encoded = body.encode("utf-8")
        if len(encoded) > profile.max_html_bytes:
            body = encoded[: profile.max_html_bytes].decode("utf-8", errors="replace")
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
        if _sniff_live_manifest(content_type, body):
            drm = detect_drm_signals(body[:2048])
            return [
                _candidate(
                    source,
                    url,
                    MediaKind.LIVE_STREAM,
                    evidence=["intake:manifest"],
                    drm=drm,
                ),
                *_candidates_from_evidence(source, evidence, url, profile),
            ]
        if "html" not in content_type and not body.lstrip().lower().startswith("<"):
            drm = detect_drm_signals(body[:2048])
            sniff = MediaKind.UNKNOWN
            return [_candidate(source, url, sniff, evidence=["intake:bytes"], drm=drm)]

    parser = _MediaHTMLParser()
    parser.feed(body)
    document_base = _document_base(url, parser.base_href)
    drm = detect_drm_signals(body)
    title = parser.title or parser.meta.get("og:title")
    seen: set[str] = set()
    found: list[MediaCandidate] = []
    seeded = _candidates_from_evidence(source, evidence, document_base, profile)
    for key, kind_hint in (
        ("og:image", MediaKind.IMAGE),
        ("og:image:url", MediaKind.IMAGE),
        ("og:image:secure_url", MediaKind.IMAGE),
        ("twitter:image", MediaKind.IMAGE),
        ("twitter:image:src", MediaKind.IMAGE),
        ("og:video", MediaKind.VIDEO),
        ("og:video:url", MediaKind.VIDEO),
        ("og:video:secure_url", MediaKind.VIDEO),
        ("og:audio", MediaKind.AUDIO),
        ("og:audio:url", MediaKind.AUDIO),
        ("og:audio:secure_url", MediaKind.AUDIO),
        ("twitter:player:stream", MediaKind.VIDEO),
        ("twitter:player", MediaKind.VIDEO),
    ):
        meta_url = parser.meta.get(key)
        if meta_url:
            parser.urls.append((meta_url, kind_hint))
    for item in seeded:
        seen.update(item.retrieval_urls)
        found.append(
            item.model_copy(update={"drm_signals": sorted(set(item.drm_signals) | set(drm))})
        )
    for raw, guessed in parser.urls:
        absolute = urljoin(document_base, raw)
        if not _usable_url(absolute, profile):
            continue
        if absolute in seen:
            continue
        if _locator_has_script_asset_suffix(absolute):
            continue
        item_kind = _kind_from_url_or_guess(absolute, guessed)
        if item_kind is None:
            continue
        seen.add(absolute)
        found.append(
            _candidate(
                source,
                absolute,
                item_kind,
                title=title,
                evidence=["discover:html"],
                drm=sorted(set(detect_drm_signals(absolute)) | set(drm)),
            )
        )
    ld_hits = list(
        dict.fromkeys(
            [
                *parser.json_ld,
                *re.findall(
                    r'<script[^>]+type=["\']application/ld\+json[^"\']*["\'][^>]*>(.*?)</script>',
                    body,
                    flags=re.I | re.S,
                ),
            ]
        )
    )
    for block in ld_hits:
        payload = _parse_jsonld_block(block)
        if not isinstance(payload, (dict, list)):
            continue
        items = payload if isinstance(payload, list) else [payload]
        for item in _walk_jsonld(items):
            for key in ("contentUrl", "embedUrl", "url"):
                for content_url in _jsonld_locator_urls(item.get(key)):
                    absolute = urljoin(document_base, content_url)
                    if not _usable_url(absolute, profile):
                        continue
                    if absolute in seen:
                        continue
                    if _locator_has_script_asset_suffix(absolute):
                        continue
                    kind = _kind_from_jsonld(item, absolute)
                    if key == "url" and kind in {MediaKind.PAGE, MediaKind.UNKNOWN}:
                        continue
                    seen.add(absolute)
                    found.append(
                        _candidate(
                            source,
                            absolute,
                            kind,
                            title=title,
                            evidence=["discover:jsonld"],
                            drm=sorted(set(detect_drm_signals(absolute)) | set(drm)),
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
