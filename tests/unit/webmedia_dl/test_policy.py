import pytest

from webmedia_dl.domain.enums import Surface
from webmedia_dl.errors import CapabilityDenied, DelegationDenied
from webmedia_dl.policy.profiles import (
    assert_no_privilege_escalation,
    assert_worker_capability,
    default_worker_for_surface,
    get_profile,
)


def test_restricted_cannot_delegate_ytdlp() -> None:
    client = get_profile("personal-restricted")
    worker = get_profile("personal-full")
    with pytest.raises(DelegationDenied):
        assert_no_privilege_escalation(client, worker, "acquire.ytdlp")


def test_watch_is_not_a_subprocess_worker() -> None:
    worker = default_worker_for_surface(Surface.WATCHOS)
    assert worker.subprocess_capable is False
    profile = get_profile(worker.profile_id)
    with pytest.raises(CapabilityDenied):
        assert_worker_capability(worker, profile, "acquire.ytdlp")


def test_tv_is_not_a_subprocess_worker() -> None:
    worker = default_worker_for_surface(Surface.TVOS)
    assert worker.subprocess_capable is False


def test_browser_profile_cannot_run_native_commands() -> None:
    worker = default_worker_for_surface(Surface.CHROMIUM)
    profile = get_profile(worker.profile_id)
    assert "acquire.ytdlp" not in profile.allowed_capabilities
    with pytest.raises(CapabilityDenied):
        assert_worker_capability(worker, profile, "process.ffmpeg.remux")


def test_full_worker_allows_http() -> None:
    worker = default_worker_for_surface(Surface.MACOS)
    profile = get_profile(worker.profile_id)
    assert_worker_capability(worker, profile, "acquire.http")


def test_unknown_profile_and_worker_cannot_accept() -> None:
    with pytest.raises(CapabilityDenied, match="Unknown policy profile"):
        get_profile("not-a-profile")
    with pytest.raises(DelegationDenied, match="cannot accept"):
        assert_no_privilege_escalation(
            get_profile("personal-full"),
            get_profile("personal-restricted"),
            "acquire.ytdlp",
        )


def test_resource_overlay_cannot_enable_non_goals(monkeypatch) -> None:
    from webmedia_dl.policy import profiles as profiles_mod

    restricted = get_profile("personal-restricted")

    def overlay(extra: dict) -> None:
        monkeypatch.setattr(
            profiles_mod,
            "_resource_profiles",
            lambda: {restricted.profile_id: extra},
        )

    overlay({"drm_circumvention": True})
    with pytest.raises(CapabilityDenied, match="DRM circumvention"):
        profiles_mod._apply_resource_overlay(restricted)
    overlay({"telemetry_default": True})
    with pytest.raises(CapabilityDenied, match="default telemetry"):
        profiles_mod._apply_resource_overlay(restricted)
    overlay({"cookie_access": "explicit_path"})
    with pytest.raises(CapabilityDenied, match="widen cookie"):
        profiles_mod._apply_resource_overlay(restricted)
    overlay({"subprocess_worker": True})
    with pytest.raises(CapabilityDenied, match="subprocess"):
        profiles_mod._apply_resource_overlay(restricted)
    overlay({"can_delegate": True})
    with pytest.raises(CapabilityDenied, match="delegation"):
        profiles_mod._apply_resource_overlay(restricted)


def test_builtin_profile_ids_must_match_resource_file(monkeypatch) -> None:
    from webmedia_dl.policy import profiles as profiles_mod

    monkeypatch.setattr(profiles_mod, "_resource_profiles", lambda: {"only-one": {}})
    profiles_mod.builtin_profiles.cache_clear()
    try:
        with pytest.raises(CapabilityDenied, match="must match"):
            profiles_mod.builtin_profiles()
    finally:
        profiles_mod.builtin_profiles.cache_clear()


def test_subprocess_flag_and_worker_capability_list() -> None:
    from webmedia_dl.domain.models import Worker

    profile = get_profile("personal-full")
    watch = Worker(
        worker_id="watch-misconfigured",
        platform=Surface.WATCHOS,
        profile_id=profile.profile_id,
        capabilities=list(profile.allowed_capabilities),
        subprocess_capable=False,
    )
    with pytest.raises(CapabilityDenied, match="not a subprocess worker"):
        assert_worker_capability(watch, profile, "acquire.ytdlp")
    thin = Worker(
        worker_id="thin",
        platform=Surface.MACOS,
        profile_id=profile.profile_id,
        capabilities=["intake.normalize"],
        subprocess_capable=True,
    )
    with pytest.raises(CapabilityDenied, match="cannot execute capability"):
        assert_worker_capability(thin, profile, "acquire.http")
