"""Durable job lifecycle and events. Not a raw provider console API."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from sqlalchemy.pool import NullPool
from sqlmodel import Field, Session, SQLModel, create_engine, select

from webmedia_dl.domain.enums import EventType, JobState
from webmedia_dl.domain.models import BrowserEvidence, EventRecord, Job

QUEUE_EVENT_JOB_ID = UUID(int=0)
_QUEUE_TABLES = frozenset({"jobs", "events", "queue_control", "job_context"})


@dataclass(frozen=True)
class JobContext:
    html: str | None = None
    cookies: str | None = None
    evidence: tuple[BrowserEvidence, ...] = ()


class JobRow(SQLModel, table=True):
    __tablename__ = "jobs"

    job_id: str = Field(primary_key=True)
    state: str
    payload: str
    created_at: str


class EventRow(SQLModel, table=True):
    __tablename__ = "events"

    event_id: str = Field(primary_key=True)
    job_id: str = Field(index=True)
    sequence: int
    payload: str


class QueueControlRow(SQLModel, table=True):
    __tablename__ = "queue_control"

    id: int = Field(default=1, primary_key=True)
    paused: bool = False
    seq: int = 0


class JobContextRow(SQLModel, table=True):
    __tablename__ = "job_context"

    job_id: str = Field(primary_key=True)
    html: str | None = None
    cookies: str | None = None
    evidence_json: str = "[]"


class QueueStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.root / 'queue.sqlite'}",
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
        tables = [table for table in SQLModel.metadata.sorted_tables if table.name in _QUEUE_TABLES]
        SQLModel.metadata.create_all(self.engine, tables=tables)
        self._ensure_control()

    def _ensure_control(self) -> None:
        with Session(self.engine) as session:
            row = session.get(QueueControlRow, 1)
            if row is None:
                session.add(QueueControlRow(id=1, paused=False, seq=0))
                session.commit()

    def put_job(self, job: Job) -> Job:
        payload = job.model_dump_json()
        with Session(self.engine) as session:
            row = session.get(JobRow, str(job.job_id))
            if row is None:
                session.add(
                    JobRow(
                        job_id=str(job.job_id),
                        state=job.state.value,
                        payload=payload,
                        created_at=job.created_at.isoformat(),
                    )
                )
            else:
                row.state = job.state.value
                row.payload = payload
                row.created_at = job.created_at.isoformat()
            session.commit()
        return job

    def get_job(self, job_id: UUID) -> Job:
        with Session(self.engine) as session:
            row = session.get(JobRow, str(job_id))
            if row is None:
                raise KeyError(job_id)
            return Job.model_validate_json(row.payload)

    def list_jobs(self) -> list[Job]:
        with Session(self.engine) as session:
            rows = session.exec(select(JobRow)).all()
        jobs = [Job.model_validate_json(row.payload) for row in rows]
        return sorted(jobs, key=lambda job: job.created_at, reverse=True)

    def next_runnable(self) -> Job | None:
        if self.is_paused():
            return None
        for job in reversed(self.list_jobs()):
            if job.state is JobState.ACCEPTED:
                return job
        return None

    def set_state(self, job_id: UUID, state: JobState, error: str | None = None) -> Job:
        job = self.get_job(job_id)
        updated = job.model_copy(update={"state": state, "error": error})
        return self.put_job(updated)

    def emit(self, job_id: UUID, event_type: EventType, payload: dict | None = None) -> EventRecord:
        with Session(self.engine) as session:
            control = session.get(QueueControlRow, 1)
            if control is None:
                control = QueueControlRow(id=1, paused=False, seq=0)
                session.add(control)
            control.seq += 1
            sequence = control.seq
            event = EventRecord(
                job_id=job_id,
                type=event_type,
                sequence=sequence,
                payload=payload or {},
            )
            session.add(
                EventRow(
                    event_id=str(event.event_id),
                    job_id=str(job_id),
                    sequence=sequence,
                    payload=event.model_dump_json(),
                )
            )
            session.commit()
        return event

    def events_for(self, job_id: UUID) -> list[EventRecord]:
        with Session(self.engine) as session:
            rows = session.exec(select(EventRow).where(EventRow.job_id == str(job_id))).all()
        records = [EventRecord.model_validate_json(row.payload) for row in rows]
        return sorted(records, key=lambda event: event.sequence)

    def is_paused(self) -> bool:
        with Session(self.engine) as session:
            row = session.get(QueueControlRow, 1)
            return bool(row and row.paused)

    def set_paused(self, paused: bool) -> bool:
        with Session(self.engine) as session:
            row = session.get(QueueControlRow, 1)
            if row is None:
                row = QueueControlRow(id=1, paused=paused, seq=0)
                session.add(row)
            else:
                row.paused = paused
            session.commit()
        return paused

    def put_context(
        self,
        job_id: UUID,
        *,
        html: str | None,
        cookies: str | None,
        evidence: list[BrowserEvidence] | None,
    ) -> None:
        payload = json.dumps(
            [item.model_dump(mode="json") for item in evidence or []],
            default=str,
        )
        with Session(self.engine) as session:
            row = session.get(JobContextRow, str(job_id))
            if row is None:
                session.add(
                    JobContextRow(
                        job_id=str(job_id),
                        html=html,
                        cookies=cookies,
                        evidence_json=payload,
                    )
                )
            else:
                row.html = html
                row.cookies = cookies
                row.evidence_json = payload
            session.commit()

    def get_context(self, job_id: UUID) -> JobContext:
        with Session(self.engine) as session:
            row = session.get(JobContextRow, str(job_id))
        if row is None:
            return JobContext()
        raw = json.loads(row.evidence_json or "[]")
        evidence = tuple(BrowserEvidence.model_validate(item) for item in raw)
        return JobContext(html=row.html, cookies=row.cookies, evidence=evidence)
