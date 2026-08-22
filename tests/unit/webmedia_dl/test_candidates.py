from uuid import uuid4

import pytest

from webmedia_dl.candidates import preferred_by_kind, preferred_candidates
from webmedia_dl.discovery import discover
from webmedia_dl.domain.enums import IntakeKind, MediaKind, Surface
from webmedia_dl.domain.models import CandidateGraph, MediaCandidate, MediaSource
from webmedia_dl.errors import DiscoveryError
from webmedia_dl.policy.profiles import get_profile


def test_preferred_candidates_rank_video_over_page() -> None:
    source_id = uuid4()
    graph = CandidateGraph(
        job_id=uuid4(),
        nodes=[
            MediaCandidate(
                source_id=source_id,
                media_kind=MediaKind.PAGE,
                identity_key="host:example.com:path:/page",
                retrieval_urls=["https://example.com/page"],
            ),
            MediaCandidate(
                source_id=source_id,
                media_kind=MediaKind.VIDEO,
                identity_key="host:cdn.example.com:path:/a.mp4",
                retrieval_urls=["https://cdn.example.com/a.mp4"],
            ),
            MediaCandidate(
                source_id=source_id,
                media_kind=MediaKind.IMAGE,
                identity_key="host:cdn.example.com:path:/a.png",
                retrieval_urls=["https://cdn.example.com/a.png"],
            ),
        ],
    )
    ranked = preferred_candidates(graph)
    assert ranked[0].media_kind is MediaKind.VIDEO
    assert MediaKind.PAGE in {item.media_kind for item in ranked}
    mixed = preferred_by_kind(graph)
    assert [item.media_kind for item in mixed] == [MediaKind.VIDEO, MediaKind.IMAGE]
    protected = CandidateGraph(
        job_id=uuid4(),
        nodes=[
            MediaCandidate(
                source_id=source_id,
                media_kind=MediaKind.VIDEO,
                identity_key="host:cdn.example.com:path:/protected.mpd",
                retrieval_urls=["https://cdn.example.com/protected.mpd"],
                drm_signals=["widevine"],
            ),
            MediaCandidate(
                source_id=source_id,
                media_kind=MediaKind.IMAGE,
                identity_key="host:cdn.example.com:path:/a.png",
                retrieval_urls=["https://cdn.example.com/a.png"],
            ),
        ],
    )
    mixed_drm = preferred_by_kind(protected)
    assert {item.media_kind for item in mixed_drm} == {MediaKind.VIDEO, MediaKind.IMAGE}
    live_graph = CandidateGraph(
        job_id=uuid4(),
        nodes=[
            MediaCandidate(
                source_id=source_id,
                media_kind=MediaKind.LIVE_STREAM,
                identity_key="host:example.com:path:/watch",
                retrieval_urls=["https://example.com/watch"],
            ),
            MediaCandidate(
                source_id=source_id,
                media_kind=MediaKind.LIVE_STREAM,
                identity_key="host:cdn.example.com:path:/live.m3u8",
                retrieval_urls=["https://cdn.example.com/live.m3u8"],
            ),
        ],
    )
    live_pref = [
        item for item in preferred_by_kind(live_graph) if item.media_kind is MediaKind.LIVE_STREAM
    ]
    assert live_pref
    assert live_pref[0].retrieval_urls[0] == "https://cdn.example.com/live.m3u8"


def test_discovery_page_without_fetch_still_requires_html_or_fetch() -> None:
    source = MediaSource(
        kind=IntakeKind.URL,
        locator="https://example.com/page",
        normalized_url="https://example.com/page",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )
    with pytest.raises(DiscoveryError):
        discover(source, get_profile("personal-full"))
