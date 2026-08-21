"""Policy package."""

from webmedia_dl.policy.profiles import (
    assert_capability,
    assert_no_privilege_escalation,
    assert_worker_capability,
    builtin_profiles,
    default_worker_for_surface,
    get_profile,
)

__all__ = [
    "assert_capability",
    "assert_no_privilege_escalation",
    "assert_worker_capability",
    "builtin_profiles",
    "default_worker_for_surface",
    "get_profile",
]
