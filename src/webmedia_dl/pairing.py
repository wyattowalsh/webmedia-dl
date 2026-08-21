"""Persisted pairing sessions. Transport does not decide capability policy."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from webmedia_dl.errors import DelegationDenied
from webmedia_dl.transport import (
    PairingChallenge,
    PairingRecord,
    create_challenge,
    derive_session_key,
    expired,
)


class PairingStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._path = self.root / "pairing.json"
        self._records: dict[str, PairingRecord] = {}
        self._load()

    def _load(self) -> None:
        if not self._path.is_file():
            return
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        for item in payload:
            record = PairingRecord.model_validate(item)
            self._records[str(record.pairing_id)] = record

    def _save(self) -> None:
        data = [item.model_dump(mode="json") for item in self._records.values()]
        tmp = self._path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
        tmp.replace(self._path)

    def create(self, client_profile_id: str, worker_id: str) -> PairingChallenge:
        challenge = create_challenge(client_profile_id, worker_id)
        record = PairingRecord(
            pairing_id=challenge.pairing_id,
            nonce=challenge.nonce,
            expires_at=challenge.expires_at,
            client_profile_id=challenge.client_profile_id,
            worker_id=challenge.worker_id,
        )
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
        if session_key is not None and record.session_key != session_key:
            msg = "Pairing session key does not match."
            raise DelegationDenied(msg)
        return record
