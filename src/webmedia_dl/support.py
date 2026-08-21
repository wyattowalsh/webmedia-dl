"""User-exportable diagnostics. No telemetry upload and no raw provider console."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

from webmedia_dl.diagnostics import doctor
from webmedia_dl.pipeline import Pipeline

FIXED_ZIP_TIME = (2026, 8, 18, 0, 0, 0)
STRIP_KEYS = frozenset({"stdout", "stderr", "argv", "nativeCommand", "providerArgv"})


def _sanitize(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key not in STRIP_KEYS}


def write_support_bundle(*, data_dir: Path, dest: Path) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    pipeline = Pipeline(data_dir=data_dir)
    jobs = pipeline.history_entries()
    events: dict[str, list[dict[str, Any]]] = {}
    for job in pipeline.history():
        records = []
        for event in pipeline.queue.events_for(job.job_id):
            dumped = event.model_dump(mode="json")
            dumped["payload"] = _sanitize(dict(dumped.get("payload") or {}))
            records.append(dumped)
        events[str(job.job_id)] = records
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
