"""Durable job lifecycle and events. Not a raw provider console API."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from webmedia_dl.domain.enums import EventType, JobState
from webmedia_dl.domain.models import EventRecord, Job


class QueueStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._jobs_path = self.root / "jobs.json"
        self._events_path = self.root / "events.json"
        self._jobs: dict[str, Job] = {}
        self._events: list[EventRecord] = []
        self._seq = 0
        self._load()

    def _load(self) -> None:
        if self._jobs_path.is_file():
            for item in json.loads(self._jobs_path.read_text(encoding="utf-8")):
                job = Job.model_validate(item)
                self._jobs[str(job.job_id)] = job
        if self._events_path.is_file():
            for item in json.loads(self._events_path.read_text(encoding="utf-8")):
                event = EventRecord.model_validate(item)
                self._events.append(event)
                self._seq = max(self._seq, event.sequence)

    def _save(self) -> None:
        jobs = [job.model_dump(mode="json") for job in self._jobs.values()]
        events = [event.model_dump(mode="json") for event in self._events]
        self._jobs_path.write_text(json.dumps(jobs, indent=2, default=str), encoding="utf-8")
        self._events_path.write_text(json.dumps(events, indent=2, default=str), encoding="utf-8")

    def put_job(self, job: Job) -> Job:
        self._jobs[str(job.job_id)] = job
        self._save()
        return job

    def get_job(self, job_id: UUID) -> Job:
        return self._jobs[str(job_id)]

    def list_jobs(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def set_state(self, job_id: UUID, state: JobState, error: str | None = None) -> Job:
        job = self.get_job(job_id)
        updated = job.model_copy(update={"state": state, "error": error})
        return self.put_job(updated)

    def emit(self, job_id: UUID, event_type: EventType, payload: dict | None = None) -> EventRecord:
        self._seq += 1
        event = EventRecord(
            job_id=job_id,
            type=event_type,
            sequence=self._seq,
            payload=payload or {},
        )
        self._events.append(event)
        self._save()
        return event

    def events_for(self, job_id: UUID) -> list[EventRecord]:
        return [event for event in self._events if event.job_id == job_id]
