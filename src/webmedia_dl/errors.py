"""Typed error hierarchy. Failures are truthful; nothing is silent."""

from __future__ import annotations


class WebMediaError(Exception):
    """Base error with a stable machine code."""

    code = "webmedia.error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class IntakeError(WebMediaError):
    code = "intake.invalid"


class NetworkPolicyError(WebMediaError):
    code = "network.denied"


class DiscoveryError(WebMediaError):
    code = "discovery.failed"


class CapabilityDenied(WebMediaError):
    code = "capability.denied"


class ProviderPolicyError(WebMediaError):
    code = "provider.policy"


class DrmRefused(WebMediaError):
    code = "drm.refused"


class ArtifactImmutabilityError(WebMediaError):
    code = "artifact.immutable"


class ValidationFailed(WebMediaError):
    code = "validation.failed"


class PublicationError(WebMediaError):
    code = "publication.failed"


class SimulatedPassError(WebMediaError):
    code = "evidence.simulated_pass_forbidden"


class DelegationDenied(WebMediaError):
    code = "worker.delegation_denied"


class CookiePolicyError(WebMediaError):
    code = "cookie.policy"


class CancelledError(WebMediaError):
    code = "job.cancelled"


class PauseRequested(WebMediaError):
    code = "job.paused"
