"""Durable nonce ledger for pairing envelopes. Transport still does not set policy."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.pool import NullPool
from sqlmodel import Field, Session, SQLModel, create_engine, select

from webmedia_dl.errors import DelegationDenied


class UsedNonce(SQLModel, table=True):
    nonce: str = Field(primary_key=True)
    used_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NonceLedger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.path}",
            connect_args={"check_same_thread": False},
            poolclass=NullPool,
        )
        SQLModel.metadata.create_all(self.engine)

    def consume(self, nonce: str) -> None:
        with Session(self.engine) as session:
            existing = session.exec(select(UsedNonce).where(UsedNonce.nonce == nonce)).first()
            if existing is not None:
                msg = "Pairing envelope nonce was already consumed."
                raise DelegationDenied(msg)
            session.add(UsedNonce(nonce=nonce))
            session.commit()
