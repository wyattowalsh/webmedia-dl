"""Typed capability registry. Health is executed evidence, not a planned PASS."""

from __future__ import annotations

from webmedia_dl.domain.enums import Surface
from webmedia_dl.domain.models import Capability
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


def _provider_for(capability_id: str) -> str:
    for manifest in builtin_manifests().values():
        if capability_id in manifest.capabilities:
            return manifest.provider_id
    if capability_id.startswith("live."):
        return "http-direct"
    return "webmedia-dl"


def registry(*, runtime: ProviderRuntime | None = None) -> list[Capability]:
    runtime = runtime or ProviderRuntime()
    items: list[Capability] = []
    for capability_id, platforms in CAPABILITY_PLATFORMS.items():
        provider_id = _provider_for(capability_id)
        health: str = "healthy"
        if provider_id in builtin_manifests():
            health = runtime.health(provider_id)
        items.append(
            Capability(
                capability_id=capability_id,
                provider_id=provider_id,
                platforms=platforms,
                description=capability_id.replace(".", " "),
                health=health
                if health in {"healthy", "missing", "unhealthy", "disabled"}
                else "missing",
            )
        )
    return items
