"""Report whether a newer package version exists. Never installs anything."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import URLError
from urllib.request import urlopen

from webmedia_dl import __version__
from webmedia_dl.names import DISPLAY_NAME

PYPI_JSON = "https://pypi.org/pypi/webmedia-dl/json"
_VERSION_PARTS = re.compile(r"\d+")


def _version_tuple(text: str) -> tuple[int, ...]:
    parts = [int(item) for item in _VERSION_PARTS.findall(text)]
    return tuple(parts) if parts else ()


def check_updates(
    *,
    current: str | None = None,
    opener=urlopen,
    timeout: float = 2.5,
) -> dict[str, Any]:
    installed = current or __version__
    payload: dict[str, Any] = {
        "product": DISPLAY_NAME,
        "current": installed,
        "latest": None,
        "update_available": False,
        "auto_install": False,
        "providers_auto_install": False,
        "telemetry_default": False,
        "app_store": "BLOCKED",
        "browser_stores": "BLOCKED",
        "signing_notarization": "BLOCKED",
        "status": "BLOCKED",
    }
    try:
        with opener(PYPI_JSON, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
        payload["message"] = f"Update check could not reach a release feed ({exc})."
        return payload
    latest = None
    if isinstance(body, dict):
        info = body.get("info") or {}
        if isinstance(info, dict):
            latest = info.get("version")
    if not isinstance(latest, str) or not _version_tuple(latest):
        payload["status"] = "WARN"
        payload["message"] = "Release feed version was missing or malformed."
        return payload
    payload["latest"] = latest
    current_tuple = _version_tuple(installed)
    latest_tuple = _version_tuple(latest)
    payload["update_available"] = latest_tuple > current_tuple
    payload["status"] = "PASS"
    payload["message"] = "Update check does not install packages."
    return payload
