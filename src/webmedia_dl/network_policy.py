"""URL and destination authorization. Does not own media semantics."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from webmedia_dl.domain.models import PolicyProfile, path_is_under
from webmedia_dl.errors import NetworkPolicyError

BLOCKED_SCHEMES = frozenset(
    {"file", "javascript", "data", "blob", "about", "chrome", "chrome-extension"},
)


def authorize_url(url: str, profile: PolicyProfile) -> str:
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme in BLOCKED_SCHEMES:
        msg = f"Scheme {scheme!r} is not allowed for network intake."
        raise NetworkPolicyError(msg)
    if scheme not in profile.network_schemes:
        msg = f"Scheme {scheme!r} is not allowed by profile {profile.profile_id!r}."
        raise NetworkPolicyError(msg)
    if not parsed.netloc:
        msg = "Network locators require a host."
        raise NetworkPolicyError(msg)
    return url


def authorize_destination(destination: Path, approved_roots: list[str]) -> Path:
    roots: list[Path] = []
    for raw in approved_roots:
        text = str(raw).strip()
        if not text:
            continue
        root = Path(text).expanduser()
        if not root.is_absolute():
            continue
        roots.append(root)
    if not roots:
        msg = "Publication destinations require a non-blank absolute approved root."
        raise NetworkPolicyError(msg)
    resolved = destination.expanduser().resolve()
    for root in roots:
        if path_is_under(resolved, root):
            return resolved
    msg = "Destination is outside user-approved roots."
    raise NetworkPolicyError(msg)


def assert_not_url_as_path(locator: str) -> None:
    parsed = urlparse(locator)
    if parsed.scheme in {"http", "https"} and (
        locator.startswith("/") or locator.startswith("file:")
    ):
        msg = "A source URL never becomes a filesystem path."
        raise NetworkPolicyError(msg)
