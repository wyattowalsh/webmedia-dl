"""User-approved Files, Photos, clipboard, and security-scoped destination contracts."""

from __future__ import annotations

import re
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import Field

from webmedia_dl.domain.enums import DestinationKind, IntakeKind, Surface
from webmedia_dl.domain.models import ExportIntent, MediaSource, StrictModel, path_is_under
from webmedia_dl.errors import IntakeError, PublicationError
from webmedia_dl.intake import normalize_source

_CLIPBOARD_URL = re.compile(r"https?://[^\s<>\"']+", re.I)


class SecurityScopedBookmark(StrictModel):
    """Bookmark for a user-granted Files/Share root. Never a silent home-path write."""

    bookmark_id: UUID = Field(default_factory=uuid4)
    resolved_path: str
    stale: bool = False

    def allows(self, path: str) -> bool:
        if self.stale:
            return False
        if not str(self.resolved_path).strip():
            return False
        candidate = Path(path).expanduser()
        root = Path(self.resolved_path).expanduser()
        if not root.is_absolute():
            return False
        return path_is_under(candidate, root) or candidate.resolve() == root.resolve()


class FilesAppDestination(StrictModel):
    bookmark: SecurityScopedBookmark

    def as_intent(self, *, preset_id: str = "original-sacred") -> ExportIntent:
        root = str(Path(self.bookmark.resolved_path).expanduser().resolve())
        return ExportIntent(
            preset_id=preset_id,
            destination_kind=DestinationKind.FILES_APP,
            destination_path=root,
            approved_roots=[root],
            security_scoped_path=root,
        )


class PhotoKitDestination(StrictModel):
    """Photos library writes require PhotoKit on a signed Apple device."""

    approved_root: str | None = None
    library_write_available: bool = False

    @property
    def can_publish(self) -> bool:
        return bool(self.approved_root) and self.library_write_available

    def assert_publishable(self) -> None:
        if not self.approved_root:
            msg = "Photos destination requires a user-approved root."
            raise PublicationError(msg)
        msg = (
            "Photos library publication requires an Apple Photos API on a real device. "
            "Approved-root file copies use files_app or user_approved_path."
        )
        raise PublicationError(msg)


class ClipboardLocator(StrictModel):
    """Clipboard/paste text becomes a URL locator, never a filesystem path."""

    text: str

    def locator(self) -> str:
        return extract_clipboard_locator(self.text)

    def as_source(self, *, surface: Surface, policy_profile_id: str) -> MediaSource:
        return normalize_source(
            self.locator(),
            surface=surface,
            policy_profile_id=policy_profile_id,
            kind=IntakeKind.PASTE,
        )


def extract_clipboard_locator(text: str) -> str:
    blob = text.strip()
    if not blob:
        msg = "Clipboard did not contain an http(s) URL."
        raise IntakeError(msg)
    first = blob.split()[0]
    if first.lower().startswith(("http://", "https://")):
        return first
    match = _CLIPBOARD_URL.search(blob)
    if match is None:
        msg = "Clipboard did not contain an http(s) URL."
        raise IntakeError(msg)
    return match.group(0)
