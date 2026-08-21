"""Authenticated pairing envelope. Transport does not decide capability policy."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from typing import Any

from webmedia_dl.errors import DelegationDenied


def _key_bytes(session_key: str) -> bytes:
    try:
        raw = bytes.fromhex(session_key)
    except ValueError:
        raw = session_key.encode()
    if len(raw) != 32:
        return hashlib.sha256(raw).digest()
    return raw


def _keystream(key: bytes, nonce: bytes, length: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < length:
        out.extend(hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest())
        counter += 1
    return bytes(out[:length])


def seal_payload(session_key: str, payload: dict[str, Any]) -> dict[str, str]:
    key = _key_bytes(session_key)
    nonce = secrets.token_bytes(16)
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ciphertext = bytes(a ^ b for a, b in zip(raw, _keystream(key, nonce, len(raw)), strict=True))
    mac = hmac.new(key, nonce + ciphertext, hashlib.sha256).hexdigest()
    return {"nonce": nonce.hex(), "ciphertext": ciphertext.hex(), "mac": mac}


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
        mac = envelope["mac"]
    except (KeyError, ValueError) as exc:
        msg = "Pairing envelope is malformed."
        raise DelegationDenied(msg) from exc
    expected = hmac.new(key, nonce + ciphertext, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, mac):
        msg = "Pairing envelope authentication failed."
        raise DelegationDenied(msg)
    if ledger is not None:
        ledger.consume(envelope["nonce"])
    raw = bytes(
        a ^ b for a, b in zip(ciphertext, _keystream(key, nonce, len(ciphertext)), strict=True)
    )
    return json.loads(raw.decode())
