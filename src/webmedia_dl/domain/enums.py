"""Enumerations for the shared job, event, capability, policy, and artifact model."""

from __future__ import annotations

from enum import StrEnum


class EvidenceStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    BLOCKED = "BLOCKED"
    FAIL = "FAIL"


class JobState(StrEnum):
    ACCEPTED = "accepted"
    DISCOVERING = "discovering"
    PLANNING = "planning"
    ACQUIRING = "acquiring"
    EXPORTING = "exporting"
    VALIDATING = "validating"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"
    QUARANTINED = "quarantined"


class MediaKind(StrEnum):
    VIDEO = "video"
    AUDIO = "audio"
    IMAGE = "image"
    GALLERY = "gallery"
    DOCUMENT = "document"
    SUBTITLE = "subtitle"
    LIVE_STREAM = "live_stream"
    PAGE = "page"
    UNKNOWN = "unknown"


class IntakeKind(StrEnum):
    URL = "url"
    FILE = "file"
    SHARE_SHEET = "share_sheet"
    PASTE = "paste"
    DROP = "drop"
    INTENT = "intent"
    CLI = "cli"
    BROWSER_EVIDENCE = "browser_evidence"
    LIVE_MANIFEST = "live_manifest"


class Surface(StrEnum):
    MACOS = "macos"
    IOS = "ios"
    IPADOS = "ipados"
    VISIONOS = "visionos"
    WATCHOS = "watchos"
    TVOS = "tvos"
    SAFARI = "safari"
    CHROME = "chrome"
    BRAVE = "brave"
    EDGE = "edge"
    CHROMIUM = "chromium"
    FIREFOX = "firefox"
    CLI = "cli"


class ArtifactRole(StrEnum):
    SOURCE = "source"
    DERIVATIVE = "derivative"
    PREVIEW = "preview"
    EVIDENCE = "evidence"
    QUARANTINE = "quarantine"


class LossClass(StrEnum):
    NONE = "none"
    CONTAINER_ONLY = "container_only"
    REVERSIBLE_METADATA = "reversible_metadata"
    LOSSY_TRANSCODE = "lossy_transcode"
    SEMANTIC_RISK = "semantic_risk"
    FORBIDDEN = "forbidden"


class EventType(StrEnum):
    JOB_ACCEPTED = "job.accepted"
    INTAKE_NORMALIZED = "intake.normalized"
    DISCOVERY_PARTIAL = "discovery.partial"
    DISCOVERY_COMPLETED = "discovery.completed"
    GRAPH_BUILT = "graph.built"
    PLAN_RANKED = "plan.ranked"
    ACQUISITION_STARTED = "acquisition.started"
    ACQUISITION_QUARANTINE = "acquisition.quarantine"
    SOURCE_REGISTERED = "artifact.source_registered"
    EVIDENCE_REGISTERED = "artifact.evidence_registered"
    COOKIE_ATTACHED = "cookie.attached"
    COMPANION_RECEIVED = "companion.received"
    EXPORT_PLANNED = "export.planned"
    OPERATION_COMPLETED = "operation.completed"
    OPERATION_FAILED = "operation.failed"
    VALIDATION_RECORDED = "validation.recorded"
    PUBLISHED = "publication.committed"
    JOB_FAILED = "job.failed"
    JOB_COMPLETED = "job.completed"
    JOB_CANCELLED = "job.cancelled"
    JOB_PAUSED = "job.paused"
    JOB_RESUMED = "job.resumed"
    QUEUE_PAUSED = "queue.paused"
    QUEUE_RESUMED = "queue.resumed"
    PROBE_RECORDED = "media.probed"


class CookieAccess(StrEnum):
    NEVER = "never"
    EXPLICIT_PATH = "explicit_path"


class DestinationKind(StrEnum):
    USER_APPROVED_PATH = "user_approved_path"
    PHOTOS = "photos"
    FILES_APP = "files_app"
    SHARE = "share"
    STAGING_ONLY = "staging_only"
