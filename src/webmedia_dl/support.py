"""User-exportable diagnostics. No telemetry upload and no raw provider console."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any
from uuid import UUID

from webmedia_dl.diagnostics import doctor
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.queue import QUEUE_EVENT_JOB_ID

FIXED_ZIP_TIME = (2026, 8, 18, 0, 0, 0)
STRIP_KEYS = frozenset(
    {"stdout", "stderr", "argv", "nativeCommand", "providerArgv", "cookies_path"}
)
COOKIE_KEY = re.compile(r"cookie", re.I)


def _event_records(pipeline: Pipeline, job_id: UUID) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for event in pipeline.queue.events_for(job_id):
        dumped = event.model_dump(mode="json")
        dumped["payload"] = _sanitize(dict(dumped.get("payload") or {}))
        records.append(dumped)
    return records


def _looks_like_path(value: object) -> bool:
    return isinstance(value, str) and ("/" in value or "\\" in value or value.startswith("~"))


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            if key in STRIP_KEYS:
                continue
            if COOKIE_KEY.search(str(key)) and _looks_like_path(item):
                continue
            cleaned[key] = _sanitize(item)
        return cleaned
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value]
    return value


def write_support_bundle(*, data_dir: Path, dest: Path) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    pipeline = Pipeline(data_dir=data_dir)
    jobs = _sanitize(pipeline.history_entries())
    events: dict[str, list[dict[str, Any]]] = {}
    for job in pipeline.history():
        events[str(job.job_id)] = _event_records(pipeline, job.job_id)
    queue_events = _event_records(pipeline, QUEUE_EVENT_JOB_ID)
    if queue_events:
        events[str(QUEUE_EVENT_JOB_ID)] = queue_events
    files = {
        "doctor.json": doctor(data_dir=data_dir),
        "jobs.json": jobs,
        "events.json": events,
        "readme.txt": (
            "WebMedia DL support bundle. Local-only. Default telemetry is false. "
            "Provider console output is not included."
        ),
    }
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, body in files.items():
            info = zipfile.ZipInfo(name)
            info.date_time = FIXED_ZIP_TIME
            info.compress_type = zipfile.ZIP_DEFLATED
            if isinstance(body, str):
                archive.writestr(info, body)
            else:
                archive.writestr(info, json.dumps(body, indent=2, default=str))
    return {
        "path": str(dest.resolve()),
        "files": sorted(files),
        "telemetry": False,
        "job_count": len(jobs),
    }
