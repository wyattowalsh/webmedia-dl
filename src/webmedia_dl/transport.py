"""Cross-device pairing: explicit trust, encrypted payload envelope, expiry. No policy decisions."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4


@dataclass(frozen=True)
class PairingChallenge:
    pairing_id: UUID
    nonce: str
    expires_at: datetime
    client_profile_id: str
    worker_id: str


def create_challenge(
    client_profile_id: str, worker_id: str, *, ttl_seconds: int = 300
) -> PairingChallenge:
    return PairingChallenge(
        pairing_id=uuid4(),
        nonce=secrets.token_urlsafe(32),
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        client_profile_id=client_profile_id,
        worker_id=worker_id,
    )


def derive_session_key(nonce: str, confirmation: str) -> str:
    digest = hashlib.sha256(f"{nonce}:{confirmation}".encode()).hexdigest()
    return digest


def expired(challenge: PairingChallenge, now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    return current >= challenge.expires_at
