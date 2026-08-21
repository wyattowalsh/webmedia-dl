from uuid import uuid4

import pytest

from webmedia_dl.candidates import preferred_candidates
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
