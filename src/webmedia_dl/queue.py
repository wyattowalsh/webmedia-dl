"""Durable job lifecycle and events. Not a raw provider console API."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import event, text
from sqlalchemy.pool import NullPool
from sqlmodel import Field, Session, SQLModel, create_engine, select

from webmedia_dl.domain.enums import EventType, JobState
from webmedia_dl.domain.models import BrowserEvidence, EventRecord, Job, sanitize_event_payload
from webmedia_dl.errors import CancelledError, PauseRequested, QueueIntegrityError

QUEUE_EVENT_JOB_ID = UUID(int=0)
_QUEUE_TABLES = frozenset({"jobs", "events", "queue_control", "job_context"})
TRANSITION_ATTEMPTS = 8


@dataclass(frozen=True)
class JobContext:
    html: str | None = None
    cookies: str | None = None
    evidence: tuple[BrowserEvidence, ...] = ()
    checkpoint: dict[str, Any] = field(default_factory=dict)
    pause_requested: bool = False
    cancel_requested: bool = False


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
    checkpoint_json: str = "{}"
    pause_requested: bool = False
    cancel_requested: bool = False


class QueueStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.root / 'queue.sqlite'}",
            connect_args={"check_same_thread": False, "timeout": 30.0},
            poolclass=NullPool,
        )

        @event.listens_for(self.engine, "connect")
        def _disable_sqlite_autobegin(dbapi_connection, _connection_record) -> None:
            dbapi_connection.isolation_level = None

        @event.listens_for(self.engine, "begin")
        def _begin_immediate(conn) -> None:
            conn.exec_driver_sql("BEGIN IMMEDIATE")

        tables = [table for table in SQLModel.metadata.sorted_tables if table.name in _QUEUE_TABLES]
        SQLModel.metadata.create_all(self.engine, tables=tables)
        self._ensure_control()
        self._migrate_context()

    def _ensure_control(self) -> None:
        with Session(self.engine) as session:
            row = session.get(QueueControlRow, 1)
            if row is None:
                session.add(QueueControlRow(id=1, paused=False, seq=0))
                session.commit()

    def _migrate_context(self) -> None:
        statements = {
            "checkpoint_json": "ALTER TABLE job_context ADD COLUMN checkpoint_json TEXT DEFAULT '{}'",
            "pause_requested": (
                "ALTER TABLE job_context ADD COLUMN pause_requested INTEGER DEFAULT 0"
            ),
            "cancel_requested": (
                "ALTER TABLE job_context ADD COLUMN cancel_requested INTEGER DEFAULT 0"
            ),
        }
        with self.engine.connect() as conn:
            info = conn.exec_driver_sql("PRAGMA table_info(job_context)").fetchall()
            names = {row[1] for row in info}
            for column, sql in statements.items():
                if column not in names:
                    conn.exec_driver_sql(sql)
            conn.commit()

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

    def claim_next(self) -> Job | None:
        """Atomically claim the oldest accepted job by moving it to discovering."""
        for _ in range(TRANSITION_ATTEMPTS):
            with self.engine.begin() as conn:
                paused = conn.execute(
                    text("SELECT paused FROM queue_control WHERE id = 1")
                ).scalar()
                if paused:
                    return None
                row = conn.execute(
                    text(
                        "SELECT job_id, payload FROM jobs "
                        "WHERE state = :state "
                        "ORDER BY created_at ASC, job_id ASC LIMIT 1"
                    ),
                    {"state": JobState.ACCEPTED.value},
                ).fetchone()
                if row is None:
                    return None
                job = Job.model_validate_json(row[1])
                claimed = job.model_copy(update={"state": JobState.DISCOVERING})
                returned = conn.execute(
                    text(
                        "UPDATE jobs SET state = :new_state, payload = :payload "
                        "WHERE job_id = :job_id AND state = :old_state "
                        "RETURNING job_id"
                    ),
                    {
                        "new_state": JobState.DISCOVERING.value,
                        "payload": claimed.model_dump_json(),
                        "job_id": row[0],
                        "old_state": JobState.ACCEPTED.value,
                    },
                ).fetchone()
                if returned is not None:
                    return claimed
        return None

    def claim(self, job_id: UUID) -> Job | None:
        """Atomically claim one accepted job unless the queue is paused."""
        for _ in range(TRANSITION_ATTEMPTS):
            with self.engine.begin() as conn:
                paused = conn.execute(
                    text("SELECT paused FROM queue_control WHERE id = 1")
                ).scalar()
                if paused:
                    return None
                row = conn.execute(
                    text(
                        "SELECT job_id, payload FROM jobs WHERE job_id = :job_id AND state = :state"
                    ),
                    {"job_id": str(job_id), "state": JobState.ACCEPTED.value},
                ).fetchone()
                if row is None:
                    return None
                job = Job.model_validate_json(row[1])
                claimed = job.model_copy(update={"state": JobState.DISCOVERING})
                returned = conn.execute(
                    text(
                        "UPDATE jobs SET state = :new_state, payload = :payload "
                        "WHERE job_id = :job_id AND state = :old_state "
                        "RETURNING job_id"
                    ),
                    {
                        "new_state": JobState.DISCOVERING.value,
                        "payload": claimed.model_dump_json(),
                        "job_id": row[0],
                        "old_state": JobState.ACCEPTED.value,
                    },
                ).fetchone()
                if returned is not None:
                    return claimed
        return None

    def pause_unless_committed(self, job_id: UUID) -> Job | None:
        """Pause a job unless publication has already committed."""
        return self._transition_unless_committed(job_id, JobState.PAUSED)

    def cancel_unless_committed(self, job_id: UUID) -> Job | None:
        """Cancel a job unless publication has already committed."""
        return self._transition_unless_committed(
            job_id, JobState.CANCELLED, error="cancelled by user"
        )

    def _transition_unless_committed(
        self,
        job_id: UUID,
        state: JobState,
        error: str | None = None,
    ) -> Job | None:
        blocked = (
            JobState.COMPLETED.value,
            JobState.FAILED.value,
            JobState.CANCELLED.value,
            JobState.PUBLISHING.value,
        )
        for _ in range(TRANSITION_ATTEMPTS):
            with self.engine.begin() as conn:
                row = conn.execute(
                    text("SELECT job_id, payload, state FROM jobs WHERE job_id = :job_id"),
                    {"job_id": str(job_id)},
                ).fetchone()
                if row is None or row[2] in blocked:
                    return None
                job = Job.model_validate_json(row[1])
                updated = job.model_copy(update={"state": state, "error": error})
                returned = conn.execute(
                    text(
                        "UPDATE jobs SET state = :new_state, payload = :payload "
                        "WHERE job_id = :job_id AND state NOT IN "
                        "(:completed, :failed, :cancelled, :publishing) "
                        "RETURNING job_id"
                    ),
                    {
                        "new_state": state.value,
                        "payload": updated.model_dump_json(),
                        "job_id": row[0],
                        "completed": JobState.COMPLETED.value,
                        "failed": JobState.FAILED.value,
                        "cancelled": JobState.CANCELLED.value,
                        "publishing": JobState.PUBLISHING.value,
                    },
                ).fetchone()
                if returned is not None:
                    return updated
        return None

    def set_state(self, job_id: UUID, state: JobState, error: str | None = None) -> Job:
        pause_requested, cancel_requested = self._control_flags(job_id)
        job = self.get_job(job_id)
        if job.state is JobState.PUBLISHING and state is JobState.COMPLETED:
            updated = job.model_copy(update={"state": state, "error": error})
            self.put_job(updated)
            self.set_job_flags(job_id, pause_requested=False, cancel_requested=False)
            return updated
        if cancel_requested and state is not JobState.CANCELLED:
            cancelled = job.model_copy(
                update={"state": JobState.CANCELLED, "error": error or "cancelled by user"}
            )
            self.put_job(cancelled)
            raise CancelledError(f"Job {job_id} was cancelled.")
        if pause_requested and state not in {
            JobState.PAUSED,
            JobState.CANCELLED,
            JobState.COMPLETED,
            JobState.FAILED,
        }:
            paused = job.model_copy(update={"state": JobState.PAUSED, "error": error})
            self.put_job(paused)
            raise PauseRequested(f"Job {job_id} is paused.")
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
                payload=sanitize_event_payload(payload),
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

    def put_checkpoint(self, job_id: UUID, checkpoint: dict) -> None:
        encoded = json.dumps(checkpoint, default=str)
        with Session(self.engine) as session:
            row = session.get(JobContextRow, str(job_id))
            if row is None:
                session.add(JobContextRow(job_id=str(job_id), checkpoint_json=encoded))
            else:
                row.checkpoint_json = encoded
            session.commit()

    def set_job_flags(
        self,
        job_id: UUID,
        *,
        pause_requested: bool | None = None,
        cancel_requested: bool | None = None,
    ) -> None:
        with Session(self.engine) as session:
            row = session.get(JobContextRow, str(job_id))
            if row is None:
                row = JobContextRow(job_id=str(job_id))
                session.add(row)
            if pause_requested is not None:
                row.pause_requested = pause_requested
            if cancel_requested is not None:
                row.cancel_requested = cancel_requested
            session.commit()

    def _control_flags(self, job_id: UUID) -> tuple[bool, bool]:
        with Session(self.engine) as session:
            row = session.get(JobContextRow, str(job_id))
        if row is None:
            return False, False
        return bool(row.pause_requested), bool(row.cancel_requested)

    def get_context(self, job_id: UUID) -> JobContext:
        with Session(self.engine) as session:
            row = session.get(JobContextRow, str(job_id))
        if row is None:
            return JobContext()
        try:
            raw = json.loads(row.evidence_json or "[]")
        except (TypeError, json.JSONDecodeError) as exc:
            msg = "Job browser evidence is not valid JSON."
            raise QueueIntegrityError(msg) from exc
        if not isinstance(raw, list):
            msg = "Job browser evidence must be a JSON array."
            raise QueueIntegrityError(msg)
        try:
            evidence = tuple(BrowserEvidence.model_validate(item) for item in raw)
        except ValidationError as exc:
            msg = "Job browser evidence failed validation."
            raise QueueIntegrityError(msg) from exc
        try:
            checkpoint = json.loads(row.checkpoint_json or "{}")
        except (TypeError, json.JSONDecodeError):
            checkpoint = {}
        if not isinstance(checkpoint, dict):
            checkpoint = {}
        return JobContext(
            html=row.html,
            cookies=row.cookies,
            evidence=evidence,
            checkpoint=checkpoint,
            pause_requested=bool(row.pause_requested),
            cancel_requested=bool(row.cancel_requested),
        )
