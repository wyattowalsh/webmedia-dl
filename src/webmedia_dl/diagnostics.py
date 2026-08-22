"""Support diagnostics. Claims follow executed evidence only."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from webmedia_dl import __version__
from webmedia_dl.capabilities import registry
from webmedia_dl.domain.enums import EvidenceStatus
from webmedia_dl.names import CLI_NAME, DISPLAY_NAME
from webmedia_dl.policy.profiles import builtin_profiles
from webmedia_dl.providers import builtin_manifests, provider_version_ok, resolve_provider_binary

APPLE_SURFACES = ("macos", "ios", "ipados", "visionos", "watchos", "tvos")


def _status(
    executed: bool,
    ok: bool,
    *,
    blocked_reason: str | None = None,
    warn: bool = False,
) -> dict[str, Any]:
    if not executed and blocked_reason:
        return {"status": EvidenceStatus.BLOCKED.value, "reason": blocked_reason, "executed": False}
    if not executed:
        return {"status": EvidenceStatus.BLOCKED.value, "reason": "not executed", "executed": False}
    if warn and ok:
        return {"status": EvidenceStatus.WARN.value, "executed": True}
    return {
        "status": EvidenceStatus.PASS.value if ok else EvidenceStatus.FAIL.value,
        "executed": True,
    }


def _provider_version_ok(path: str, binary_name: str) -> bool:
    return provider_version_ok(path, binary_name)


def doctor(*, data_dir: Path | None = None) -> dict[str, Any]:
    manifests = builtin_manifests()
    providers = {}
    for provider_id, manifest in manifests.items():
        if manifest.binary_name is None:
            providers[provider_id] = _status(True, True)
            continue
        path = resolve_provider_binary(manifest.binary_name)
        if path is None:
            providers[provider_id] = _status(
                False,
                False,
                blocked_reason=f"{manifest.binary_name} is not installed",
            ) | {"binary": None}
            continue
        probed = _provider_version_ok(path, manifest.binary_name)
        convert_alias = Path(path).name == "convert" and manifest.binary_name == "magick"
        providers[provider_id] = _status(
            True,
            probed,
            warn=probed and convert_alias,
        ) | {"binary": path}
        if not probed:
            providers[provider_id]["reason"] = f"{path} did not report a version"
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
        "original_planning_pack": _status(
            False,
            False,
            blocked_reason="webmedia-dl-final-planning-pack-2026-08-18 zip is not attached",
        ),
        "capabilities": [
            {
                "capability_id": item.capability_id,
                "provider_id": item.provider_id,
                "health": item.health,
                "platforms": [surface.value for surface in item.platforms],
            }
            for item in registry()
        ],
        "telemetry_default": False,
        "drm_circumvention": False,
        "data_dir": str(data_dir) if data_dir else None,
    }
