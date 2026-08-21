"""DRM refusal and explicit-path cookie policy. No circumvention, no silent cookies."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID, uuid4

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
    header = resolved.read_bytes()[:200]
    if b"<html" in header.lower() or b"<!doctype" in header.lower():
        msg = "Cookie file must be a Netscape cookie file, not HTML."
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


@dataclass(frozen=True)
class CookieGrant:
    grant_id: str
    job_id: UUID
    path: Path
    profile_id: str


class CookieGrantLedger:
    """Job-bound cookie grants. Providers never receive a raw filesystem path."""

    def __init__(self, store: Path | None = None) -> None:
        self._store = store
        self._grants: dict[str, CookieGrant] = {}
        self._load()

    def _load(self) -> None:
        if self._store is None or not self._store.is_file():
            return
        try:
            payload = json.loads(self._store.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return
        if not isinstance(payload, list):
            return
        for item in payload:
            if not isinstance(item, dict):
                continue
            try:
                grant = CookieGrant(
                    grant_id=str(item["grant_id"]),
                    job_id=UUID(str(item["job_id"])),
                    path=Path(str(item["path"])),
                    profile_id=str(item["profile_id"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
            self._grants[grant.grant_id] = grant

    def _save(self) -> None:
        if self._store is None:
            return
        self._store.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "grant_id": grant.grant_id,
                "job_id": str(grant.job_id),
                "path": str(grant.path),
                "profile_id": grant.profile_id,
            }
            for grant in self._grants.values()
        ]
        tmp = self._store.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._store)

    def issue(self, job_id: UUID, path: Path, profile_id: str) -> CookieGrant:
        from webmedia_dl.policy.profiles import get_profile

        if get_profile(profile_id).cookie_access == CookieAccess.NEVER:
            msg = "This profile forbids cookie access."
            raise CookiePolicyError(msg)
        grant = CookieGrant(
            grant_id=str(uuid4()),
            job_id=job_id,
            path=path,
            profile_id=profile_id,
        )
        self._grants[grant.grant_id] = grant
        self._save()
        return grant

    def resolve(
        self,
        grant_id: str,
        *,
        job_id: UUID | str | None,
        profile_id: str | None,
    ) -> Path:
        grant = self._grants.get(str(grant_id))
        if grant is None:
            msg = "Cookie grant is unknown or expired."
            raise CookiePolicyError(msg)
        if job_id is None or UUID(str(job_id)) != grant.job_id:
            msg = "Cookie grants are bound to a single job."
            raise CookiePolicyError(msg)
        if profile_id is None or profile_id != grant.profile_id:
            msg = "Cookie grants are bound to the issuing policy profile."
            raise CookiePolicyError(msg)
        if not grant.path.is_file():
            msg = f"Cookie file does not exist: {grant.path}"
            raise CookiePolicyError(msg)
        return grant.path
