"""Enforced distribution profiles. Restricted workers never inherit extra power."""

from __future__ import annotations

import json
from functools import lru_cache

from webmedia_dl.domain.enums import CookieAccess, Surface
from webmedia_dl.domain.models import PolicyProfile, Worker
from webmedia_dl.errors import CapabilityDenied, DelegationDenied
from webmedia_dl.paths import runtime_file

FULL_CAPABILITIES = (
    "intake.normalize",
    "network.fetch",
    "discover.html",
    "discover.direct",
    "discover.manifest",
    "acquire.http",
    "acquire.ytdlp",
    "acquire.gallery_dl",
    "process.ffmpeg.remux",
    "process.ffmpeg.transcode",
    "process.imagemagick.convert",
    "export.plan",
    "validate.hash",
    "validate.container",
    "publish.atomic",
    "queue.events",
    "live.record_clear_manifest",
)

RESTRICTED_CAPABILITIES = (
    "intake.normalize",
    "network.fetch",
    "discover.direct",
    "acquire.http",
    "export.plan",
    "validate.hash",
    "publish.atomic",
    "queue.events",
)

CAPTURE_CAPABILITIES = (
    "intake.normalize",
    "discover.direct",
    "queue.events",
)

WATCH_TV_CAPABILITIES = (
    "intake.normalize",
    "queue.events",
)


@lru_cache(maxsize=1)
def _resource_profiles() -> dict[str, dict]:
    path = runtime_file("policy-profiles.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _apply_resource_overlay(profile: PolicyProfile) -> PolicyProfile:
    extra = _resource_profiles().get(profile.profile_id, {})
    if extra.get("drm_circumvention"):
        msg = "policy-profiles.json cannot enable DRM circumvention."
        raise CapabilityDenied(msg)
    if extra.get("telemetry_default"):
        msg = "policy-profiles.json cannot enable default telemetry."
        raise CapabilityDenied(msg)
    updates: dict = {}
    if "cookie_access" in extra:
        requested = CookieAccess(str(extra["cookie_access"]))
        if profile.cookie_access == CookieAccess.NEVER and requested != CookieAccess.NEVER:
            msg = "policy-profiles.json cannot widen cookie access."
            raise CapabilityDenied(msg)
        updates["cookie_access"] = requested
    if "subprocess_worker" in extra:
        requested_sub = bool(extra["subprocess_worker"])
        if requested_sub and not profile.subprocess_worker:
            msg = "policy-profiles.json cannot enable subprocess execution."
            raise CapabilityDenied(msg)
        updates["subprocess_worker"] = requested_sub and profile.subprocess_worker
    if "can_delegate" in extra:
        requested_delegate = bool(extra["can_delegate"])
        if requested_delegate and not profile.can_delegate:
            msg = "policy-profiles.json cannot enable delegation."
            raise CapabilityDenied(msg)
        updates["can_delegate"] = requested_delegate and profile.can_delegate
    return profile.model_copy(update=updates) if updates else profile


@lru_cache(maxsize=1)
def builtin_profiles() -> dict[str, PolicyProfile]:
    built = {
        "personal-full": PolicyProfile(
            profile_id="personal-full",
            display_name="Personal full macOS worker",
            allowed_capabilities=list(FULL_CAPABILITIES),
            cookie_access=CookieAccess.EXPLICIT_PATH,
            can_delegate=False,
            subprocess_worker=True,
        ),
        "personal-restricted": PolicyProfile(
            profile_id="personal-restricted",
            display_name="Restricted client worker",
            allowed_capabilities=list(RESTRICTED_CAPABILITIES),
            cookie_access=CookieAccess.NEVER,
            can_delegate=False,
            subprocess_worker=False,
        ),
        "browser-capture": PolicyProfile(
            profile_id="browser-capture",
            display_name="Browser capture extension",
            allowed_capabilities=list(CAPTURE_CAPABILITIES),
            cookie_access=CookieAccess.NEVER,
            can_delegate=False,
            subprocess_worker=False,
        ),
        "watch-capture": PolicyProfile(
            profile_id="watch-capture",
            display_name="watchOS capture and status",
            allowed_capabilities=list(WATCH_TV_CAPABILITIES),
            cookie_access=CookieAccess.NEVER,
            can_delegate=False,
            subprocess_worker=False,
        ),
        "tv-control": PolicyProfile(
            profile_id="tv-control",
            display_name="tvOS status and controls",
            allowed_capabilities=list(WATCH_TV_CAPABILITIES),
            cookie_access=CookieAccess.NEVER,
            can_delegate=False,
            subprocess_worker=False,
        ),
    }
    resource_ids = set(_resource_profiles())
    if resource_ids != set(built):
        msg = "policy-profiles.json ids must match builtin profile ids."
        raise CapabilityDenied(msg)
    return {key: _apply_resource_overlay(value) for key, value in built.items()}


def get_profile(profile_id: str) -> PolicyProfile:
    profiles = builtin_profiles()
    try:
        return profiles[profile_id]
    except KeyError as exc:
        msg = f"Unknown policy profile {profile_id!r}."
        raise CapabilityDenied(msg) from exc


def assert_capability(profile: PolicyProfile, capability_id: str) -> None:
    if capability_id not in profile.allowed_capabilities:
        msg = f"Profile {profile.profile_id!r} cannot execute capability {capability_id!r}."
        raise CapabilityDenied(msg)


def assert_worker_capability(worker: Worker, profile: PolicyProfile, capability_id: str) -> None:
    assert_capability(profile, capability_id)
    if capability_id not in worker.capabilities:
        msg = f"Worker {worker.worker_id!r} cannot execute capability {capability_id!r}."
        raise CapabilityDenied(msg)
    if (
        capability_id.startswith("process.")
        or capability_id.startswith("acquire.ytdlp")
        or capability_id.startswith("acquire.gallery")
    ) and not worker.subprocess_capable:
        msg = (
            f"Worker {worker.worker_id!r} is not a subprocess worker and cannot "
            f"run {capability_id!r}."
        )
        raise CapabilityDenied(msg)


def assert_no_privilege_escalation(
    client: PolicyProfile, worker: PolicyProfile, capability_id: str
) -> None:
    """A restricted profile never delegates disallowed work to a more capable worker."""
    if capability_id not in client.allowed_capabilities:
        msg = (
            f"Client profile {client.profile_id!r} cannot delegate "
            f"{capability_id!r} to worker {worker.profile_id!r}."
        )
        raise DelegationDenied(msg)
    if capability_id not in worker.allowed_capabilities:
        msg = (
            f"Worker profile {worker.profile_id!r} cannot accept "
            f"{capability_id!r} from {client.profile_id!r}."
        )
        raise DelegationDenied(msg)


SAME_MACHINE_SURFACES = frozenset(
    {
        Surface.CLI,
        Surface.MACOS,
        Surface.SAFARI,
        Surface.CHROME,
        Surface.BRAVE,
        Surface.EDGE,
        Surface.CHROMIUM,
        Surface.FIREFOX,
    }
)

REMOTE_CLIENT_SURFACES = frozenset(
    {
        Surface.IOS,
        Surface.IPADOS,
        Surface.VISIONOS,
        Surface.WATCHOS,
        Surface.TVOS,
    }
)


def default_worker_for_surface(surface: Surface, worker_id: str = "local-macos") -> Worker:
    if surface in {Surface.WATCHOS}:
        profile = get_profile("watch-capture")
        return Worker(
            worker_id=f"{worker_id}-watch",
            platform=surface,
            profile_id=profile.profile_id,
            capabilities=list(profile.allowed_capabilities),
            subprocess_capable=False,
        )
    if surface in {Surface.TVOS}:
        profile = get_profile("tv-control")
        return Worker(
            worker_id=f"{worker_id}-tv",
            platform=surface,
            profile_id=profile.profile_id,
            capabilities=list(profile.allowed_capabilities),
            subprocess_capable=False,
        )
    if surface in {
        Surface.SAFARI,
        Surface.CHROME,
        Surface.BRAVE,
        Surface.EDGE,
        Surface.CHROMIUM,
        Surface.FIREFOX,
    }:
        profile = get_profile("browser-capture")
        return Worker(
            worker_id=f"{worker_id}-browser",
            platform=surface,
            profile_id=profile.profile_id,
            capabilities=list(profile.allowed_capabilities),
            subprocess_capable=False,
        )
    if surface in {Surface.IOS, Surface.IPADOS, Surface.VISIONOS}:
        profile = get_profile("personal-restricted")
        return Worker(
            worker_id=f"{worker_id}-mobile",
            platform=surface,
            profile_id=profile.profile_id,
            capabilities=list(profile.allowed_capabilities),
            subprocess_capable=False,
        )
    profile = get_profile("personal-full")
    return Worker(
        worker_id=worker_id,
        platform=surface,
        profile_id=profile.profile_id,
        capabilities=list(profile.allowed_capabilities),
        subprocess_capable=True,
    )
