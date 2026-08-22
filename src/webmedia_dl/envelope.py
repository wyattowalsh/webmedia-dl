"""Authenticated pairing envelope. Transport does not decide capability policy."""

from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from webmedia_dl.errors import DelegationDenied

_NONCE_SIZE = 12
_TAG_SIZE = 16


def _key_bytes(session_key: str) -> bytes:
    try:
        raw = bytes.fromhex(session_key)
    except ValueError:
        raw = session_key.encode()
    if len(raw) != 32:
        return hashlib.sha256(raw).digest()
    return raw


def seal_payload(session_key: str, payload: dict[str, Any]) -> dict[str, str]:
    key = _key_bytes(session_key)
    nonce = secrets.token_bytes(_NONCE_SIZE)
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    packed = AESGCM(key).encrypt(nonce, raw, None)
    ciphertext = packed[:-_TAG_SIZE]
    tag = packed[-_TAG_SIZE:]
    return {"nonce": nonce.hex(), "ciphertext": ciphertext.hex(), "mac": tag.hex()}


def open_payload(
    session_key: str,
    envelope: dict[str, str],
    *,
    ledger: Any | None = None,
) -> dict[str, Any]:
    key = _key_bytes(session_key)
    try:
        nonce = bytes.fromhex(envelope["nonce"])
        ciphertext = bytes.fromhex(envelope["ciphertext"])
        tag = bytes.fromhex(envelope["mac"])
    except (KeyError, ValueError) as exc:
        msg = "Pairing envelope is malformed."
        raise DelegationDenied(msg) from exc
    try:
        raw = AESGCM(key).decrypt(nonce, ciphertext + tag, None)
    except (InvalidTag, ValueError) as exc:
        msg = "Pairing envelope authentication failed."
        raise DelegationDenied(msg) from exc
    if ledger is not None:
        ledger.consume(envelope["nonce"])
    try:
        payload = json.loads(raw.decode())
    except json.JSONDecodeError as exc:
        msg = "Pairing envelope payload is not JSON."
        raise DelegationDenied(msg) from exc
    if not isinstance(payload, dict):
        msg = "Pairing envelope payload must be an object."
        raise DelegationDenied(msg)
    return payload
