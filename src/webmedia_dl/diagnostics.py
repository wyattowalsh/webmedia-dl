"""Support diagnostics. Claims follow executed evidence only."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

from webmedia_dl import __version__
from webmedia_dl.domain.enums import EvidenceStatus
from webmedia_dl.names import CLI_NAME, DISPLAY_NAME
from webmedia_dl.policy.profiles import builtin_profiles
from webmedia_dl.providers import builtin_manifests

APPLE_SURFACES = ("macos", "ios", "ipados", "visionos", "watchos", "tvos")


def _status(executed: bool, ok: bool, *, blocked_reason: str | None = None) -> dict[str, Any]:
    if not executed and blocked_reason:
        return {"status": EvidenceStatus.BLOCKED.value, "reason": blocked_reason, "executed": False}
    if not executed:
        return {"status": EvidenceStatus.BLOCKED.value, "reason": "not executed", "executed": False}
    return {
        "status": EvidenceStatus.PASS.value if ok else EvidenceStatus.FAIL.value,
        "executed": True,
    }


def doctor(*, data_dir: Path | None = None) -> dict[str, Any]:
    manifests = builtin_manifests()
    providers = {}
    for provider_id, manifest in manifests.items():
        if manifest.binary_name is None:
            providers[provider_id] = _status(True, True)
            continue
        path = shutil.which(manifest.binary_name)
        if path is None:
            providers[provider_id] = _status(
                False,
                False,
                blocked_reason=f"{manifest.binary_name} is not installed",
            ) | {"binary": None}
        else:
            providers[provider_id] = _status(True, True) | {"binary": path}
    apple = {
        surface: _status(
            False, False, blocked_reason="Apple device and Xcode not available in this environment"
        )
        for surface in APPLE_SURFACES
    }
    return {
        "product": DISPLAY_NAME,
        "cli": CLI_NAME,
        "version": __version__,
        "python": sys.version.split()[0],
        "profiles": sorted(builtin_profiles()),
        "providers": providers,
        "apple_devices": apple,
        "browser_stores": _status(
            False, False, blocked_reason="Browser store submission not executed"
        ),
        "signing_notarization": _status(
            False, False, blocked_reason="Signing and notarization require Apple hardware"
        ),
        "app_review": _status(False, False, blocked_reason="Human App Review is not automated"),
        "legal_review": _status(False, False, blocked_reason="Human legal review is not automated"),
        "telemetry_default": False,
        "drm_circumvention": False,
        "data_dir": str(data_dir) if data_dir else None,
    }
