"""Typed source validation and normalization. Does not retrieve bytes."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from webmedia_dl.domain.enums import IntakeKind, Surface
from webmedia_dl.domain.models import MediaSource
from webmedia_dl.errors import IntakeError
from webmedia_dl.network_policy import assert_not_url_as_path, authorize_url
from webmedia_dl.policy.profiles import get_profile


def classify_locator(raw: str) -> IntakeKind:
    text = raw.strip()
    parsed = urlparse(text)
    if parsed.scheme in {"http", "https"}:
        return IntakeKind.URL
    if parsed.scheme in {"file"}:
        msg = "file: locators are not accepted as URLs; use explicit file intake."
        raise IntakeError(msg)
    path = Path(text).expanduser()
    if path.exists():
        return IntakeKind.FILE
    if text.startswith("{") or "browser_evidence" in text:
        return IntakeKind.BROWSER_EVIDENCE
    msg = "Unable to classify intake locator; expected an https URL or existing file."
    raise IntakeError(msg)


def normalize_source(
    raw: str,
    *,
    surface: Surface,
    policy_profile_id: str,
    kind: IntakeKind | None = None,
) -> MediaSource:
    locator = raw.strip()
    if not locator:
        msg = "Intake locator is empty."
        raise IntakeError(msg)
    profile = get_profile(policy_profile_id)
    resolved_kind = kind or classify_locator(locator)
    if resolved_kind in {IntakeKind.FILE, IntakeKind.DROP}:
        assert_not_url_as_path(locator)
        path = Path(locator).expanduser().resolve()
        if not path.is_file():
            msg = f"File intake requires an existing file: {path}"
            raise IntakeError(msg)
        return MediaSource(
            kind=resolved_kind,
            locator=str(path),
            local_path=str(path),
            surface=surface,
            policy_profile_id=profile.profile_id,
        )
    url = authorize_url(locator, profile)
    return MediaSource(
        kind=resolved_kind,
        locator=locator,
        normalized_url=url,
        surface=surface,
        policy_profile_id=profile.profile_id,
    )
