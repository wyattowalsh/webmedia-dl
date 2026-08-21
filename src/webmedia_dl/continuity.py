"""Companion/Continuity control messages.

watchOS and tvOS send capture, status, history, and controls to the Mac. The Mac
forwards them to the loopback worker. Messages never carry provider argv or a
native command runner.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from webmedia_dl.domain.enums import Surface
from webmedia_dl.errors import ProviderPolicyError

ALLOWED_KINDS = frozenset(
    {"capture", "pause", "resume", "history", "status", "cancel", "pause_job", "resume_job"}
)
FORBIDDEN_KEYS = frozenset({"providerArgv", "extra_args", "argv", "yt-dlp", "ffmpeg", "gallery-dl"})


class CompanionRelay:
    """watchOS/tvOS queue until the Mac forwards messages to loopback."""

    def __init__(self) -> None:
        self._pending: list[dict[str, Any]] = []

    def enqueue(self, payload: dict[str, Any]) -> dict[str, Any]:
        message = validate_companion_message(payload)
        self._pending.append(message)
        return {
            "queued": True,
            "count": len(self._pending),
            "kind": message["kind"],
            "nativeCommand": None,
            "subprocessWorker": False,
        }

    def drain(self) -> list[dict[str, Any]]:
        items = list(self._pending)
        self._pending.clear()
        return items


def companion_message(
    kind: str,
    *,
    locator: str | None = None,
    job_id: UUID | str | None = None,
    surface: str | Surface | None = None,
) -> dict[str, Any]:
    if kind not in ALLOWED_KINDS:
        msg = f"Companion kind {kind!r} is not allowlisted."
        raise ProviderPolicyError(msg)
    resolved = Surface.WATCHOS
    if isinstance(surface, Surface):
        resolved = surface
    elif isinstance(surface, str):
        try:
            resolved = Surface(surface)
        except ValueError:
            resolved = Surface.WATCHOS
    payload: dict[str, Any] = {
        "kind": kind,
        "nativeCommand": None,
        "subprocessWorker": False,
        "surface": resolved.value,
    }
    if locator:
        payload["locator"] = locator
    if job_id is not None:
        payload["job_id"] = str(job_id)
    return payload


def validate_companion_message(payload: dict[str, Any]) -> dict[str, Any]:
    native = payload.get("nativeCommand")
    if native not in (None, ""):
        msg = "Companion messages cannot carry a native command."
        raise ProviderPolicyError(msg)
    if payload.get("subprocessWorker") is True:
        msg = "watchOS and tvOS are not subprocess workers."
        raise ProviderPolicyError(msg)
    for key in FORBIDDEN_KEYS:
        if payload.get(key):
            msg = "Companion messages cannot carry provider argv."
            raise ProviderPolicyError(msg)
    kind = payload.get("kind")
    if not isinstance(kind, str) or kind not in ALLOWED_KINDS:
        msg = "Companion kind is missing or not allowlisted."
        raise ProviderPolicyError(msg)
    locator = payload.get("locator")
    if locator is not None and not isinstance(locator, str):
        msg = "Companion locator must be a string."
        raise ProviderPolicyError(msg)
    job_id = payload.get("job_id") or payload.get("jobId")
    if kind == "capture" and not locator:
        msg = "Companion capture requires a locator."
        raise ProviderPolicyError(msg)
    if kind in {"cancel", "pause_job", "resume_job"} and not job_id:
        msg = f"Companion {kind} requires a job_id."
        raise ProviderPolicyError(msg)
    return companion_message(
        kind,
        locator=locator,
        job_id=job_id,
        surface=payload.get("surface"),
    ) | {
        "job_id": str(job_id) if job_id else None,
        "locator": locator,
    }
