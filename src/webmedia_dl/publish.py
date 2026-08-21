"""Contained atomic destination commit. Never bypasses validation."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from webmedia_dl.domain.enums import ArtifactRole, DestinationKind, MediaKind
from webmedia_dl.domain.models import Artifact, ExportIntent, ValidationResult
from webmedia_dl.errors import PublicationError, ValidationFailed
from webmedia_dl.network_policy import authorize_destination
from webmedia_dl.validation import require_pass

PATH_DESTINATIONS = {
    DestinationKind.USER_APPROVED_PATH,
    DestinationKind.FILES_APP,
    DestinationKind.SHARE,
}
PUBLISHABLE_ROLES = {ArtifactRole.SOURCE, ArtifactRole.DERIVATIVE}


def publish_artifacts(
    artifacts: list[tuple[Artifact, Path, list[ValidationResult]]],
    intent: ExportIntent,
) -> list[Path]:
    if intent.destination_kind is DestinationKind.PHOTOS:
        msg = (
            "Photos library publication requires an Apple Photos API on a real device. "
            "Approved-root file copies use files_app or user_approved_path."
        )
        raise PublicationError(msg)
    if intent.destination_kind is DestinationKind.STAGING_ONLY:
        return [path for artifact, path, _ in artifacts if artifact.role in PUBLISHABLE_ROLES]
    if intent.destination_kind not in PATH_DESTINATIONS:
        msg = f"Unsupported destination {intent.destination_kind.value}."
        raise PublicationError(msg)
    if not intent.destination_path:
        msg = "Publication requires a destination path."
        raise PublicationError(msg)
    dest_root = authorize_destination(Path(intent.destination_path), intent.approved_roots)
    dest_root.mkdir(parents=True, exist_ok=True)
    published: list[Path] = []
    tmp_dir = Path(tempfile.mkdtemp(prefix="webmedia-dl-pub-", dir=dest_root))
    primary_stem = _primary_stem(artifacts)
    try:
        for artifact, src, results in artifacts:
            if artifact.role not in PUBLISHABLE_ROLES:
                continue
            require_pass(results)
            name = _publish_name(artifact, src, primary_stem)
            staged = tmp_dir / name
            staged.write_bytes(src.read_bytes())
            final = dest_root / name
            os.replace(staged, final)
            published.append(final)
    except ValidationFailed:
        raise
    except Exception as exc:
        raise PublicationError(str(exc)) from exc
    finally:
        for leftover in tmp_dir.glob("*"):
            leftover.unlink(missing_ok=True)
        tmp_dir.rmdir()
    return published


def _primary_stem(artifacts: list[tuple[Artifact, Path, list[ValidationResult]]]) -> str | None:
    for artifact, _src, _results in artifacts:
        if artifact.role not in PUBLISHABLE_ROLES:
            continue
        if artifact.media_kind in {MediaKind.VIDEO, MediaKind.AUDIO, MediaKind.LIVE_STREAM}:
            return artifact.sha256[:16]
    for artifact, _src, _results in artifacts:
        if artifact.role in PUBLISHABLE_ROLES:
            return artifact.sha256[:16]
    return None


def _publish_name(artifact: Artifact, src: Path, primary_stem: str | None) -> str:
    suffix = Path(src).suffix or ""
    if artifact.media_kind is MediaKind.SUBTITLE and primary_stem:
        return f"{primary_stem}{suffix or '.vtt'}"
    return artifact.sha256[:16] + suffix
