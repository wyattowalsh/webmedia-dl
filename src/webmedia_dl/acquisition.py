"""Acquisition planner: ranked retrieval strategies. Does not convert media."""

from __future__ import annotations

from uuid import UUID

from webmedia_dl.domain.enums import LossClass, MediaKind
from webmedia_dl.domain.models import (
    AcquisitionPlan,
    AcquisitionStrategy,
    MediaCandidate,
    PolicyProfile,
)
from webmedia_dl.errors import CapabilityDenied
from webmedia_dl.policy.profiles import assert_capability
from webmedia_dl.security import refuse_drm


def plan_acquisition(
    job_id: UUID,
    candidate: MediaCandidate,
    profile: PolicyProfile,
    *,
    cookies: str | None = None,
) -> AcquisitionPlan:
    refuse_drm(candidate.drm_signals)
    strategies: list[AcquisitionStrategy] = []
    rank = 0
    if not candidate.retrieval_urls:
        return AcquisitionPlan(
            job_id=job_id, candidate_id=candidate.candidate_id, strategies=strategies
        )
    url = candidate.retrieval_urls[0]
    if candidate.media_kind == MediaKind.LIVE_STREAM:
        try:
            assert_capability(profile, "live.record_clear_manifest")
            strategies.append(
                AcquisitionStrategy(
                    strategy_id="live-clear-record",
                    provider_id="http-direct",
                    capability_id="live.record_clear_manifest",
                    typed_inputs={"url": url},
                    estimated_loss=LossClass.NONE,
                    rank=rank,
                )
            )
        except CapabilityDenied:
            pass
        return AcquisitionPlan(
            job_id=job_id, candidate_id=candidate.candidate_id, strategies=strategies
        )
    if candidate.media_kind == MediaKind.GALLERY:
        try:
            assert_capability(profile, "acquire.gallery_dl")
            strategies.append(
                AcquisitionStrategy(
                    strategy_id="gallery-dl",
                    provider_id="gallery-dl",
                    capability_id="acquire.gallery_dl",
                    typed_inputs={"url": url},
                    estimated_loss=LossClass.NONE,
                    rank=rank,
                )
            )
            rank += 1
        except CapabilityDenied:
            pass
        try:
            assert_capability(profile, "acquire.ytdlp")
            typed = {"url": url}
            if cookies:
                typed["cookies"] = cookies
            strategies.append(
                AcquisitionStrategy(
                    strategy_id="ytdlp",
                    provider_id="ytdlp",
                    capability_id="acquire.ytdlp",
                    typed_inputs=typed,
                    estimated_loss=LossClass.NONE,
                    rank=rank,
                )
            )
        except CapabilityDenied:
            pass
        return AcquisitionPlan(
            job_id=job_id, candidate_id=candidate.candidate_id, strategies=strategies
        )
    if candidate.media_kind != MediaKind.PAGE:
        try:
            assert_capability(profile, "acquire.http")
            strategies.append(
                AcquisitionStrategy(
                    strategy_id="http-direct",
                    provider_id="http-direct",
                    capability_id="acquire.http",
                    typed_inputs={"url": url},
                    estimated_loss=LossClass.NONE,
                    rank=rank,
                )
            )
            rank += 1
        except CapabilityDenied:
            pass
    try:
        assert_capability(profile, "acquire.ytdlp")
        typed = {"url": url}
        if cookies:
            typed["cookies"] = cookies
        strategies.append(
            AcquisitionStrategy(
                strategy_id="ytdlp",
                provider_id="ytdlp",
                capability_id="acquire.ytdlp",
                typed_inputs=typed,
                estimated_loss=LossClass.NONE,
                rank=rank,
            )
        )
        rank += 1
    except CapabilityDenied:
        pass
    return AcquisitionPlan(
        job_id=job_id, candidate_id=candidate.candidate_id, strategies=strategies
    )
