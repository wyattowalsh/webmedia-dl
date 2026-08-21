"""DRM refusal and explicit-path cookie policy. No circumvention, no silent cookies."""

from __future__ import annotations

import re
from pathlib import Path

from webmedia_dl.domain.enums import CookieAccess
from webmedia_dl.domain.models import PolicyProfile
from webmedia_dl.errors import CookiePolicyError, DrmRefused

DRM_PATTERNS = (
    re.compile(r"widevine", re.I),
    re.compile(r"fairplay", re.I),
    re.compile(r"playready", re.I),
    re.compile(r"com\.widevine\.alpha", re.I),
    re.compile(r"EXT-X-KEY:.*METHOD=(?!NONE)", re.I),
    re.compile(r"pssh", re.I),
    re.compile(r"encrypted-media", re.I),
    re.compile(r"clearkey", re.I),
)

REPO_COOKIE_DENY = ("cookies.txt", "www.youtube.com_cookies.txt")


def detect_drm_signals(*texts: str) -> list[str]:
    hits: list[str] = []
    for text in texts:
        for pattern in DRM_PATTERNS:
            if pattern.search(text):
                hits.append(pattern.pattern)
    return sorted(set(hits))


def refuse_drm(signals: list[str]) -> None:
    if signals:
        joined = ", ".join(signals)
        msg = (
            "This source appears to use encrypted or DRM-protected media "
            f"({joined}). WebMedia DL refuses DRM circumvention."
        )
        raise DrmRefused(msg)


def resolve_cookie_path(
    profile: PolicyProfile,
    requested: str | None,
    *,
    repo_root: Path | None = None,
) -> Path | None:
    if requested is None:
        return None
    if profile.cookie_access == CookieAccess.NEVER:
        msg = "This profile forbids cookie access."
        raise CookiePolicyError(msg)
    path = Path(requested).expanduser()
    if not path.is_absolute():
        msg = "Cookie files must be user-owned absolute paths."
        raise CookiePolicyError(msg)
    resolved = path.resolve()
    if not resolved.is_file():
        msg = f"Cookie file does not exist: {resolved}"
        raise CookiePolicyError(msg)
    if repo_root is not None:
        try:
            resolved.relative_to(repo_root.resolve())
        except ValueError:
            pass
        else:
            msg = "Cookie files inside the repository are forbidden."
            raise CookiePolicyError(msg)
    if resolved.name in REPO_COOKIE_DENY and "test" not in resolved.parts:
        # still allowed outside repo; name check is advisory for common mistakes
        pass
    return resolved
