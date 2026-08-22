"""Persisted pairing sessions. Transport does not decide capability policy."""

from __future__ import annotations

import hmac
import json
from pathlib import Path
from uuid import UUID

from webmedia_dl.errors import DelegationDenied
from webmedia_dl.ledger import NonceLedger
from webmedia_dl.transport import (
    PairingChallenge,
    PairingRecord,
    create_challenge,
    derive_session_key,
    expired,
)


class PairingStore:
    PAIRABLE_CLIENT_PROFILES = frozenset(
        {
            "personal-restricted",
            "browser-capture",
            "watch-capture",
            "tv-control",
        }
    )

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.root.chmod(0o700)
        self._path = self.root / "pairing.json"
        self.ledger = NonceLedger(self.root / "nonces.sqlite")
        self._records: dict[str, PairingRecord] = {}
        self._load()
        if self._path.is_file():
            self._path.chmod(0o600)

    def _load(self) -> None:
        if not self._path.is_file():
            return
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        for item in payload:
            record = PairingRecord.model_validate(item)
            self._records[str(record.pairing_id)] = record
        if self._prune_expired():
            self._save()

    def _prune_expired(self) -> bool:
        changed = False
        for key, record in list(self._records.items()):
            if expired(record.to_challenge()):
                del self._records[key]
                changed = True
        return changed

    def _save(self) -> None:
        data = [item.model_dump(mode="json") for item in self._records.values()]
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.chmod(0o600)
        tmp.replace(self._path)
        self._path.chmod(0o600)

    def create(self, client_profile_id: str, worker_id: str) -> PairingChallenge:
        from webmedia_dl.policy.profiles import builtin_profiles

        if client_profile_id not in builtin_profiles():
            msg = f"Unknown client profile {client_profile_id!r}."
            raise DelegationDenied(msg)
        if client_profile_id not in self.PAIRABLE_CLIENT_PROFILES:
            msg = "Pairing cannot grant the host full profile to a client."
            raise DelegationDenied(msg)
        challenge = create_challenge(client_profile_id, worker_id)
        record = PairingRecord(
            pairing_id=challenge.pairing_id,
            nonce=challenge.nonce,
            expires_at=challenge.expires_at,
            client_profile_id=challenge.client_profile_id,
            worker_id=challenge.worker_id,
        )
        self._prune_expired()
        self._records[str(record.pairing_id)] = record
        self._save()
        return challenge

    def confirm(self, pairing_id: UUID) -> PairingRecord:
        record = self._records.get(str(pairing_id))
        if record is None:
            msg = "Unknown pairing challenge."
            raise DelegationDenied(msg)
        challenge = record.to_challenge()
        if expired(challenge):
            msg = "Pairing challenge expired."
            raise DelegationDenied(msg)
        session_key = derive_session_key(record.nonce, "mac-confirm")
        updated = record.model_copy(update={"confirmed": True, "session_key": session_key})
        self._records[str(pairing_id)] = updated
        self._save()
        return updated

    def get(self, pairing_id: UUID) -> PairingRecord | None:
        return self._records.get(str(pairing_id))

    def require_confirmed(self, pairing_id: UUID, session_key: str | None = None) -> PairingRecord:
        record = self.get(pairing_id)
        if record is None:
            msg = "Unknown pairing challenge."
            raise DelegationDenied(msg)
        if expired(record.to_challenge()):
            msg = "Pairing challenge expired."
            raise DelegationDenied(msg)
        if not record.confirmed:
            msg = "The Mac user has not confirmed this pairing."
            raise DelegationDenied(msg)
        if not session_key:
            msg = "Pairing session key is required."
            raise DelegationDenied(msg)
        left = hmac.new(
            b"webmedia-dl-pairing", (record.session_key or "").encode(), "sha256"
        ).digest()
        right = hmac.new(b"webmedia-dl-pairing", session_key.encode(), "sha256").digest()
        if not hmac.compare_digest(left, right):
            msg = "Pairing session key does not match."
            raise DelegationDenied(msg)
        return record
