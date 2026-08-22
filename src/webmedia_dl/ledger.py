"""Durable nonce ledger for pairing envelopes. Transport still does not set policy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy.pool import NullPool
from sqlmodel import Field, Session, SQLModel, create_engine, select

from webmedia_dl.errors import DelegationDenied

NONCE_RETENTION = timedelta(hours=24)


def _utc_naive(value: datetime | None = None) -> datetime:
    stamp = value or datetime.now(UTC)
    if stamp.tzinfo is None:
        return stamp
    return stamp.astimezone(UTC).replace(tzinfo=None)


class UsedNonce(SQLModel, table=True):
    __tablename__ = "used_nonces"

    nonce: str = Field(primary_key=True)
    used_at: datetime = Field(default_factory=_utc_naive)


class NonceLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.path}",
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
        tables = [table for table in SQLModel.metadata.sorted_tables if table.name == "used_nonces"]
        SQLModel.metadata.create_all(self.engine, tables=tables)
        with Session(self.engine) as session:
            self._prune_expired(session)
            session.commit()

    def _prune_expired(self, session: Session, *, now: datetime | None = None) -> None:
        cutoff = _utc_naive(now) - NONCE_RETENTION
        rows = session.exec(select(UsedNonce)).all()
        for row in rows:
            if _utc_naive(row.used_at) < cutoff:
                session.delete(row)

    def consume(self, nonce: str) -> None:
        with Session(self.engine) as session:
            self._prune_expired(session)
            existing = session.exec(select(UsedNonce).where(UsedNonce.nonce == nonce)).first()
            if existing is not None:
                msg = "Pairing envelope nonce was already consumed."
                raise DelegationDenied(msg)
            session.add(UsedNonce(nonce=nonce, used_at=_utc_naive()))
            session.commit()
