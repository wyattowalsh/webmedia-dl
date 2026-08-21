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
