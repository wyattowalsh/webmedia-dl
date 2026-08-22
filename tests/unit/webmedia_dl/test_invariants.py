"""Architectural invariants from system-architecture.md."""

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from webmedia_dl.artifacts import ArtifactStore
from webmedia_dl.domain.enums import (
    ArtifactRole,
    CookieAccess,
    EvidenceStatus,
    IntakeKind,
    MediaKind,
    Surface,
)
from webmedia_dl.domain.models import (
    AcquisitionStrategy,
    Artifact,
    MediaCandidate,
    MediaSource,
    PolicyProfile,
    ProviderManifest,
    ValidationResult,
)
from webmedia_dl.errors import ArtifactImmutabilityError, SimulatedPassError


def test_source_url_cannot_become_path() -> None:
    with pytest.raises(ValidationError):
        MediaSource(
            kind=IntakeKind.URL,
            locator="https://example.com/a.mp4",
            normalized_url="https://example.com/a.mp4",
            local_path="/tmp/a.mp4",
            surface=Surface.CLI,
            policy_profile_id="personal-full",
        )


def test_title_cannot_be_identity() -> None:
    with pytest.raises(ValidationError):
        MediaCandidate(
            source_id=uuid4(),
            media_kind=MediaKind.VIDEO,
            identity_key="Cool Video Title",
            title_display="Cool Video Title",
            retrieval_urls=["https://example.com/v"],
        )


def test_title_prefix_rejected_as_identity() -> None:
    with pytest.raises(ValidationError):
        MediaCandidate(
            source_id=uuid4(),
            media_kind=MediaKind.VIDEO,
            identity_key="title:Cool Video Title",
            retrieval_urls=["https://example.com/v"],
        )


def test_provider_rejects_user_argv() -> None:
    with pytest.raises(ValidationError):
        AcquisitionStrategy(
            strategy_id="x",
            provider_id="ytdlp",
            capability_id="acquire.ytdlp",
            extra_args=["--postprocessor-args", "malicious"],
        )


def test_provider_manifest_rejects_auto_install_and_argv() -> None:
    with pytest.raises(ValidationError):
        ProviderManifest(
            provider_id="x",
            display_name="x",
            capabilities=["acquire.http"],
            license="MIT",
            source_url="https://example.com",
            accepts_user_argv=True,
        )
    with pytest.raises(ValidationError):
        ProviderManifest(
            provider_id="x",
            display_name="x",
            capabilities=["acquire.http"],
            license="MIT",
            source_url="https://example.com",
            install_automatic=True,
        )


def test_source_artifact_cannot_be_mutated(tmp_path: Path) -> None:
    src = tmp_path / "a.bin"
    src.write_bytes(b"hello")
    store = ArtifactStore(tmp_path)
    artifact = store.register(src, role=ArtifactRole.SOURCE, media_kind=MediaKind.UNKNOWN)
    with pytest.raises(ArtifactImmutabilityError):
        store.mutate_source(artifact.artifact_id, b"mutated")
    assert artifact.artifact_id == f"sha256:{artifact.sha256}"
    with pytest.raises(ValidationError, match="sha256:<digest>"):
        Artifact(
            artifact_id="plan:source",
            role=ArtifactRole.SOURCE,
            sha256="0" * 64,
            byte_size=0,
            media_kind=MediaKind.VIDEO,
            storage_relpath="plan-source.bin",
        )
    with pytest.raises(ValidationError, match="sha256:<digest>"):
        Artifact(
            artifact_id="Cool Video Title",
            role=ArtifactRole.SOURCE,
            sha256="ab",
            byte_size=1,
            media_kind=MediaKind.VIDEO,
            storage_relpath="a.bin",
        )


def test_simulated_check_cannot_pass() -> None:
    with pytest.raises(SimulatedPassError):
        ValidationResult(
            job_id=uuid4(),
            target_artifact_id="sha256:abc",
            gate_id="demo",
            status=EvidenceStatus.PASS,
            message="planned",
            simulated=True,
            executed=False,
        )
    with pytest.raises(SimulatedPassError):
        ValidationResult(
            job_id=uuid4(),
            target_artifact_id="sha256:abc",
            gate_id="demo",
            status=EvidenceStatus.PASS,
            message="planned",
            planned=True,
            executed=False,
        )


def test_policy_profile_forbids_drm_and_default_telemetry() -> None:
    with pytest.raises(ValidationError, match="DRM circumvention"):
        PolicyProfile(
            profile_id="bad",
            display_name="bad",
            allowed_capabilities=["intake.normalize"],
            cookie_access=CookieAccess.NEVER,
            drm_circumvention=True,
        )
    with pytest.raises(ValidationError, match="Default telemetry"):
        PolicyProfile(
            profile_id="bad",
            display_name="bad",
            allowed_capabilities=["intake.normalize"],
            cookie_access=CookieAccess.NEVER,
            telemetry_default=True,
        )
