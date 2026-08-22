"""Typed shared job, event, capability, policy, artifact, and export model.

Invariant notes (enforced in validators and runtime, not just comments):
- A source URL never becomes a filesystem path.
- A display title never becomes artifact identity.
- A provider never receives arbitrary user arguments.
- A source artifact is never mutated after registration.
- A derivative never publishes before its mandatory validation passes.
- A planned or simulated check never becomes runtime PASS.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from webmedia_dl.domain.enums import (
    ArtifactRole,
    CookieAccess,
    DestinationKind,
    EventType,
    EvidenceStatus,
    IntakeKind,
    JobState,
    LossClass,
    MediaKind,
    Surface,
)
from webmedia_dl.errors import SimulatedPassError
from webmedia_dl.identity import is_safe_container


def utcnow() -> datetime:
    return datetime.now(UTC)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class MediaSource(StrictModel):
    source_id: UUID = Field(default_factory=uuid4)
    kind: IntakeKind
    locator: str
    normalized_url: str | None = None
    local_path: str | None = None
    submitted_at: datetime = Field(default_factory=utcnow)
    surface: Surface
    policy_profile_id: str
    content_type_hint: str | None = None

    @model_validator(mode="after")
    def url_never_becomes_path(self) -> Self:
        url_kinds = {
            IntakeKind.URL,
            IntakeKind.PASTE,
            IntakeKind.SHARE_SHEET,
            IntakeKind.INTENT,
            IntakeKind.CLI,
            IntakeKind.BROWSER_EVIDENCE,
            IntakeKind.LIVE_MANIFEST,
            IntakeKind.SPEAK,
        }
        if self.kind in url_kinds and self.local_path is not None:
            msg = "A source URL never becomes a filesystem path."
            raise ValueError(msg)
        if self.normalized_url is not None and self.normalized_url.startswith("file:"):
            msg = "A source URL never becomes a filesystem path."
            raise ValueError(msg)
        return self


class FormatAlternative(StrictModel):
    format_id: str
    container: str | None = None
    codec: str | None = None
    vcodec: str | None = None
    acodec: str | None = None
    width: int | None = None
    height: int | None = None
    bitrate: int | None = None
    note: str | None = None
    drm: bool = False


class MediaCandidate(StrictModel):
    candidate_id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    media_kind: MediaKind
    identity_key: str
    title_display: str | None = None
    grouping_key: str | None = None
    retrieval_urls: list[str] = Field(default_factory=list)
    alternatives: list[FormatAlternative] = Field(default_factory=list)
    drm_signals: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    host: str | None = None

    @field_validator("identity_key")
    @classmethod
    def identity_is_not_title(cls, value: str) -> str:
        if value.lower().startswith("title:"):
            msg = "A display title never becomes artifact identity."
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def title_not_used_as_identity(self) -> Self:
        if self.title_display and self.identity_key == self.title_display:
            msg = "A display title never becomes artifact identity."
            raise ValueError(msg)
        return self


class GraphEdge(StrictModel):
    from_id: UUID
    to_id: UUID
    relation: Literal[
        "alternative_of",
        "grouped_with",
        "derived_from",
        "conflicts_with",
    ]


class CandidateGraph(StrictModel):
    graph_id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    nodes: list[MediaCandidate] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)


class StreamInfo(StrictModel):
    index: int
    codec: str | None = None
    media_kind: MediaKind = MediaKind.UNKNOWN
    width: int | None = None
    height: int | None = None
    sample_rate: int | None = None
    channels: int | None = None
    encrypted: bool = False


class MediaProbe(StrictModel):
    probe_id: UUID = Field(default_factory=uuid4)
    candidate_id: UUID
    duration_ms: int | None = None
    streams: list[StreamInfo] = Field(default_factory=list)
    container: str | None = None
    format_names: str | None = None
    drm_signals: list[str] = Field(default_factory=list)


class ExportIntent(StrictModel):
    preset_id: str = "original-sacred"
    destination_kind: DestinationKind = DestinationKind.STAGING_ONLY
    destination_path: str | None = None
    include_original: bool = True
    allow_lossy: bool = False
    container_preference: str | None = None
    approved_roots: list[str] = Field(default_factory=list)
    security_scoped_path: str | None = None
    security_scoped_bookmark: str | None = None

    @model_validator(mode="after")
    def destination_requires_approval(self) -> Self:
        path_kinds = {
            DestinationKind.USER_APPROVED_PATH,
            DestinationKind.FILES_APP,
            DestinationKind.SHARE,
        }
        cleaned = [item.strip() for item in self.approved_roots if str(item).strip()]
        if cleaned != list(self.approved_roots):
            object.__setattr__(self, "approved_roots", cleaned)
        if self.destination_kind in path_kinds and (not self.destination_path or not cleaned):
            msg = "Publication destinations require an approved path and root."
            raise ValueError(msg)
        if self.destination_kind == DestinationKind.PHOTOS and not cleaned:
            msg = "Photos publication requires a user-approved root."
            raise ValueError(msg)
        if self.destination_kind is DestinationKind.FILES_APP:
            if not self.security_scoped_path:
                object.__setattr__(self, "security_scoped_path", self.destination_path)
            bookmark = (self.security_scoped_bookmark or "").strip()
            if not bookmark:
                msg = "Files destinations require a security-scoped bookmark."
                raise ValueError(msg)
            scoped = (self.security_scoped_path or self.destination_path or "").strip()
            allowed = False
            for root in cleaned:
                if (
                    path_is_under(Path(scoped), Path(root))
                    or Path(scoped).resolve() == Path(root).resolve()
                ):
                    allowed = True
                    break
            if not allowed:
                msg = "Files security-scoped path must stay inside approved roots."
                raise ValueError(msg)
        if self.container_preference is not None and not is_safe_container(
            self.container_preference
        ):
            msg = "container preference is not an allowed extension"
            raise ValueError(msg)
        return self


class Job(StrictModel):
    job_id: UUID = Field(default_factory=uuid4)
    source: MediaSource
    state: JobState = JobState.ACCEPTED
    policy_profile_id: str
    worker_id: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    intent: ExportIntent = Field(default_factory=ExportIntent)
    error: str | None = None


class Capability(StrictModel):
    capability_id: str
    provider_id: str
    platforms: list[Surface]
    description: str
    health: Literal["healthy", "missing", "unhealthy", "disabled"] = "healthy"
    required_entitlements: list[str] = Field(default_factory=list)


class ProviderManifest(StrictModel):
    provider_id: str
    display_name: str
    binary_name: str | None = None
    capabilities: list[str]
    allowed_flags: list[str] = Field(default_factory=list)
    install_automatic: bool = False
    license: str
    source_url: str
    accepts_user_argv: bool = False
    notes: str | None = None

    @model_validator(mode="after")
    def no_arbitrary_argv_and_no_auto_install(self) -> Self:
        if self.accepts_user_argv:
            msg = "A provider never receives arbitrary user arguments."
            raise ValueError(msg)
        if self.install_automatic:
            msg = "Providers are never installed automatically."
            raise ValueError(msg)
        return self


class PolicyProfile(StrictModel):
    profile_id: str
    display_name: str
    allowed_capabilities: list[str]
    cookie_access: CookieAccess = CookieAccess.NEVER
    drm_circumvention: bool = False
    can_delegate: bool = False
    subprocess_worker: bool = True
    network_schemes: list[str] = Field(default_factory=lambda: ["https"])
    max_html_bytes: int = 2_000_000
    max_download_bytes: int = 512 * 1024 * 1024
    max_redirects: int = 5
    telemetry_default: bool = False

    @model_validator(mode="after")
    def hard_non_goals(self) -> Self:
        if self.drm_circumvention:
            msg = "DRM circumvention is forbidden."
            raise ValueError(msg)
        if self.telemetry_default:
            msg = "Default telemetry is forbidden."
            raise ValueError(msg)
        return self


class Worker(StrictModel):
    worker_id: str
    platform: Surface
    profile_id: str
    capabilities: list[str]
    paired: bool = False
    subprocess_capable: bool = True


class AcquisitionStrategy(StrictModel):
    strategy_id: str
    provider_id: str
    capability_id: str
    typed_inputs: dict[str, Any] = Field(default_factory=dict)
    estimated_loss: LossClass = LossClass.NONE
    rank: int = 0
    extra_args: list[str] = Field(default_factory=list)

    @field_validator("extra_args")
    @classmethod
    def forbid_user_argv(cls, value: list[str]) -> list[str]:
        if value:
            msg = "A provider never receives arbitrary user arguments."
            raise ValueError(msg)
        return value


class AcquisitionPlan(StrictModel):
    plan_id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    candidate_id: UUID
    strategies: list[AcquisitionStrategy] = Field(default_factory=list)


class Artifact(StrictModel):
    artifact_id: str
    role: ArtifactRole
    sha256: str
    byte_size: int
    media_kind: MediaKind
    container: str | None = None
    storage_relpath: str
    parent_ids: list[str] = Field(default_factory=list)
    registered_at: datetime = Field(default_factory=utcnow)
    immutable: bool = False
    provenance: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def source_is_immutable(self) -> Self:
        if self.role == ArtifactRole.SOURCE:
            object.__setattr__(self, "immutable", True)
        if self.artifact_id == self.provenance.get("title"):
            msg = "A display title never becomes artifact identity."
            raise ValueError(msg)
        if self.role == ArtifactRole.SOURCE and self.artifact_id != f"sha256:{self.sha256}":
            msg = "Source artifacts SHALL be identified as sha256:<digest>."
            raise ValueError(msg)
        return self


class BrowserEvidence(StrictModel):
    url: str
    kind: MediaKind = MediaKind.UNKNOWN


class Operation(StrictModel):
    operation_id: str
    op_type: str
    capability_id: str
    input_artifact_ids: list[str]
    output_role: ArtifactRole
    loss_class: LossClass
    validator_ids: list[str]
    typed_inputs: dict[str, Any] = Field(default_factory=dict)
    optional: bool = False


class ExportPlan(StrictModel):
    plan_id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    operations: list[Operation] = Field(default_factory=list)
    publish_source: bool = True


class ValidationResult(StrictModel):
    result_id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    target_artifact_id: str
    gate_id: str
    status: EvidenceStatus
    message: str
    simulated: bool = False
    planned: bool = False
    executed: bool = True
    details: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def planned_never_pass(self) -> Self:
        if self.status == EvidenceStatus.PASS and (
            self.simulated or self.planned or not self.executed
        ):
            raise SimulatedPassError(
                "A planned or simulated check never becomes runtime PASS.",
            )
        return self


FORBIDDEN_EVENT_PAYLOAD_KEYS = frozenset(
    {"stdout", "stderr", "argv", "nativeCommand", "providerArgv", "cookies_path"}
)


def _forbidden_event_keys(value: object) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FORBIDDEN_EVENT_PAYLOAD_KEYS:
                found.add(key)
            elif "cookie" in str(key).lower() and _looks_like_path(item):
                found.add(str(key))
            found |= _forbidden_event_keys(item)
    elif isinstance(value, list):
        for item in value:
            found |= _forbidden_event_keys(item)
    return found


def _looks_like_path(value: object) -> bool:
    if not isinstance(value, str):
        return False
    return "/" in value or "\\" in value or value.startswith("~")


def sanitize_event_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Public events are typed lifecycle records, never provider consoles."""
    if not payload:
        return {}
    forbidden = _forbidden_event_keys(payload)
    if forbidden:
        msg = f"Event payloads must not include {sorted(forbidden)}."
        raise ValueError(msg)
    return dict(payload)


class EventRecord(StrictModel):
    event_id: UUID = Field(default_factory=uuid4)
    job_id: UUID
    type: EventType
    sequence: int
    ts: datetime = Field(default_factory=utcnow)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def payload_is_not_provider_console(cls, value: dict[str, Any]) -> dict[str, Any]:
        return sanitize_event_payload(value)


class HistoryEntry(StrictModel):
    job_id: UUID
    state: JobState
    policy_profile_id: str
    worker_id: str
    created_at: datetime
    updated_at: datetime
    source: MediaSource
    intent: ExportIntent = Field(default_factory=ExportIntent)
    error: str | None = None
    artifact_ids: list[str] = Field(default_factory=list)
    last_events: list[str] = Field(default_factory=list)
    partial: bool = False
    failed_kinds: list[str] = Field(default_factory=list)

    @classmethod
    def from_job(cls, job: Job, events: list[EventRecord]) -> HistoryEntry:
        artifact_ids: list[str] = []
        partial = False
        failed_kinds: list[str] = []
        for event in events:
            if event.type is not EventType.JOB_COMPLETED:
                continue
            partial = bool(event.payload.get("partial"))
            failed_kinds = [str(item) for item in event.payload.get("failed_kinds") or []]
            artifact_ids = [str(item) for item in event.payload.get("artifact_ids") or []]
        return cls(
            job_id=job.job_id,
            state=job.state,
            policy_profile_id=job.policy_profile_id,
            worker_id=job.worker_id,
            created_at=job.created_at,
            updated_at=job.updated_at,
            source=job.source,
            intent=job.intent,
            error=job.error,
            artifact_ids=artifact_ids,
            last_events=[event.type.value for event in events[-8:]],
            partial=partial,
            failed_kinds=failed_kinds,
        )


def path_is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True
