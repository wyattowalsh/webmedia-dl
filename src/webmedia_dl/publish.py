"""Contained atomic destination commit. Never bypasses validation."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from webmedia_dl.domain.enums import ArtifactRole, DestinationKind
from webmedia_dl.domain.models import Artifact, ExportIntent, ValidationResult
from webmedia_dl.errors import PublicationError, ValidationFailed
from webmedia_dl.network_policy import authorize_destination
from webmedia_dl.validation import require_pass


def publish_artifacts(
    artifacts: list[tuple[Artifact, Path, list[ValidationResult]]],
    intent: ExportIntent,
) -> list[Path]:
    if intent.destination_kind in {
        DestinationKind.PHOTOS,
        DestinationKind.FILES_APP,
        DestinationKind.SHARE,
    }:
        msg = (
            "Photos, Files, and Share destinations require an Apple device and a "
            "user-approved root. This environment cannot execute that gate."
        )
        raise PublicationError(msg)
    if intent.destination_kind.value == "staging_only":
        return [path for _, path, _ in artifacts]
    if not intent.destination_path:
        msg = "Publication requires a destination path."
        raise PublicationError(msg)
    dest_root = authorize_destination(Path(intent.destination_path), intent.approved_roots)
    dest_root.mkdir(parents=True, exist_ok=True)
    published: list[Path] = []
    tmp_dir = Path(tempfile.mkdtemp(prefix="webmedia-dl-pub-", dir=dest_root))
    try:
        for artifact, src, results in artifacts:
            if artifact.role == ArtifactRole.DERIVATIVE or artifact.role == ArtifactRole.SOURCE:
                require_pass(results)
            else:
                continue
            name = artifact.sha256[:16] + (Path(src).suffix or "")
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
