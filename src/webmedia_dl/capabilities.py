"""Typed capability registry. Health is executed evidence, not a planned PASS."""

from __future__ import annotations

import json
from functools import lru_cache

from webmedia_dl.domain.enums import Surface
from webmedia_dl.domain.models import Capability
from webmedia_dl.paths import repo_root
from webmedia_dl.providers import ProviderRuntime, builtin_manifests

CAPABILITY_PLATFORMS: dict[str, list[Surface]] = {
    "intake.normalize": list(Surface),
    "network.fetch": [
        Surface.MACOS,
        Surface.IOS,
        Surface.IPADOS,
        Surface.VISIONOS,
        Surface.CLI,
    ],
    "discover.html": [Surface.MACOS, Surface.CLI],
    "discover.direct": [
        Surface.MACOS,
        Surface.IOS,
        Surface.IPADOS,
        Surface.VISIONOS,
        Surface.CLI,
        Surface.SAFARI,
        Surface.CHROME,
        Surface.BRAVE,
        Surface.EDGE,
        Surface.CHROMIUM,
        Surface.FIREFOX,
    ],
    "discover.manifest": [Surface.MACOS, Surface.CLI],
    "acquire.http": [
        Surface.MACOS,
        Surface.IOS,
        Surface.IPADOS,
        Surface.VISIONOS,
        Surface.CLI,
    ],
    "acquire.ytdlp": [Surface.MACOS, Surface.CLI],
    "acquire.gallery_dl": [Surface.MACOS, Surface.CLI],
    "process.ffmpeg.remux": [Surface.MACOS, Surface.CLI],
    "process.ffmpeg.transcode": [Surface.MACOS, Surface.CLI],
    "process.imagemagick.convert": [Surface.MACOS, Surface.CLI],
    "live.record_clear_manifest": [Surface.MACOS, Surface.CLI],
    "export.plan": [
        Surface.MACOS,
        Surface.IOS,
        Surface.IPADOS,
        Surface.VISIONOS,
        Surface.CLI,
    ],
    "validate.hash": [
        Surface.MACOS,
        Surface.IOS,
        Surface.IPADOS,
        Surface.VISIONOS,
        Surface.CLI,
    ],
    "validate.container": [Surface.MACOS, Surface.CLI],
    "publish.atomic": [
        Surface.MACOS,
        Surface.IOS,
        Surface.IPADOS,
        Surface.VISIONOS,
        Surface.CLI,
    ],
    "queue.events": list(Surface),
}


@lru_cache(maxsize=1)
def load_platform_matrix() -> dict[str, list[str]]:
    path = repo_root() / "resources" / "platform-capability-matrix.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _provider_for(capability_id: str) -> str:
    for manifest in builtin_manifests().values():
        if capability_id in manifest.capabilities:
            return manifest.provider_id
    if capability_id.startswith("live."):
        return "http-direct"
    return "webmedia-dl"


def registry(*, runtime: ProviderRuntime | None = None) -> list[Capability]:
    runtime = runtime or ProviderRuntime()
    matrix = load_platform_matrix()
    items: list[Capability] = []
    for capability_id, platforms in CAPABILITY_PLATFORMS.items():
        provider_id = _provider_for(capability_id)
        health: str = "healthy"
        if provider_id in builtin_manifests():
            health = runtime.health(provider_id)
        bound = []
        for platform in platforms:
            features = matrix.get(platform.value)
            if features is None and platform is not Surface.CLI:
                continue
            bound.append(platform)
        items.append(
            Capability(
                capability_id=capability_id,
                provider_id=provider_id,
                platforms=bound or platforms,
                description=capability_id.replace(".", " "),
                health=health
                if health in {"healthy", "missing", "unhealthy", "disabled"}
                else "missing",
            )
        )
    return items
