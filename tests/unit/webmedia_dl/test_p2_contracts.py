"""Contracts for AdaptationSet/live polling, typed events, and destination adapters."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from webmedia_dl.continuity import CompanionRelay
from webmedia_dl.destinations import (
    ClipboardLocator,
    FilesAppDestination,
    PhotoKitDestination,
    SecurityScopedBookmark,
    extract_clipboard_locator,
)
from webmedia_dl.domain.enums import DestinationKind, EventType, IntakeKind, Surface
from webmedia_dl.domain.models import EventRecord, ExportIntent
from webmedia_dl.errors import (
    CancelledError,
    IntakeError,
    PauseRequested,
    ProviderPolicyError,
    PublicationError,
)
from webmedia_dl.live import manifest_is_live, record_clear_stream, recordable_segment_urls
from webmedia_dl.providers import ProviderRequest, ProviderRuntime
from webmedia_dl.publish import publish_artifacts
from webmedia_dl.queue import QueueStore


def test_dash_adaptationset_binds_self_closing_representation() -> None:
    text = """
    <MPD>
      <Period>
        <AdaptationSet>
          <BaseURL>https://cdn.example.com/as/</BaseURL>
          <SegmentTemplate media="$RepresentationID$/seg$Number$.m4s" startNumber="1"/>
          <Representation id="v1" bandwidth="800000"/>
        </AdaptationSet>
      </Period>
    </MPD>
    """
    urls = recordable_segment_urls(text, "https://cdn.example.com/manifest.mpd")
    assert urls == ["https://cdn.example.com/as/v1/seg1.m4s"]


def test_dynamic_mpd_polls_new_segments(tmp_path: Path) -> None:
    first = (
        '<MPD type="dynamic"><Period>'
        '<SegmentTemplate media="seg$Number$.m4s" startNumber="1"/>'
        "</Period></MPD>"
    )
    second = (
        '<MPD type="dynamic"><Period>'
        '<SegmentTemplate media="seg$Number$.m4s" startNumber="2"/>'
        "</Period></MPD>"
    )
    playlists = [second]
    bodies = {
        "https://cdn.example.com/seg1.m4s": b"ONE",
        "https://cdn.example.com/seg2.m4s": b"TWO",
    }

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("live.mpd"):
            payload = playlists.pop(0) if playlists else second
            return 200, "application/dash+xml", payload.encode()
        return 200, "video/mp4", bodies[url]

    assert manifest_is_live(first) is True
    output = tmp_path / "live.bin"
    record_clear_stream(
        first,
        "https://cdn.example.com/live.mpd",
        output,
        fetch,
        live_polls=2,
    )
    assert output.read_bytes() == b"ONETWO"


def test_hls_live_poll_appends_new_segments(tmp_path: Path) -> None:
    first = "#EXTM3U\n#EXTINF:1,\nseg1.ts\n"
    second = "#EXTM3U\n#EXTINF:1,\nseg1.ts\n#EXTINF:1,\nseg2.ts\n"
    state = {"playlist": first}

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("index.m3u8"):
            return 200, "application/vnd.apple.mpegurl", state["playlist"].encode()
        if url.endswith("seg1.ts"):
            state["playlist"] = second
            return 200, "video/MP2T", b"A"
        return 200, "video/MP2T", b"B"

    output = tmp_path / "live.ts"
    record_clear_stream(
        first,
        "https://cdn.example.com/live/index.m3u8",
        output,
        fetch,
        live_polls=2,
    )
    assert output.read_bytes() == b"AB"


def test_event_payload_rejects_provider_console() -> None:
    with pytest.raises(ValidationError, match="stdout"):
        EventRecord(
            job_id=uuid4(),
            type=EventType.OPERATION_COMPLETED,
            sequence=1,
            payload={"stdout": "ffmpeg"},
        )


def test_queue_emit_rejects_argv(tmp_path: Path) -> None:
    queue = QueueStore(tmp_path / "queue")
    with pytest.raises(ValueError, match="argv"):
        queue.emit(uuid4(), EventType.JOB_COMPLETED, {"argv": ["yt-dlp"]})


def test_clipboard_locator_extracts_url() -> None:
    clip = ClipboardLocator(text="watch https://cdn.example.com/a.mp4 thanks")
    assert clip.locator() == "https://cdn.example.com/a.mp4"
    source = clip.as_source(surface=Surface.MACOS, policy_profile_id="personal-full")
    assert source.kind is IntakeKind.PASTE
    assert source.local_path is None
    assert source.normalized_url == "https://cdn.example.com/a.mp4"
    with pytest.raises(IntakeError):
        extract_clipboard_locator("no url here")


def test_files_bookmark_and_photokit(tmp_path: Path) -> None:
    dest = tmp_path / "Movies"
    dest.mkdir()
    bookmark = SecurityScopedBookmark(resolved_path=str(dest))
    assert bookmark.allows(str(dest / "clip.mp4"))
    assert not bookmark.allows(str(tmp_path / "Movies-backup" / "clip.mp4"))
    intent = FilesAppDestination(bookmark=bookmark).as_intent()
    assert intent.destination_kind is DestinationKind.FILES_APP
    assert intent.security_scoped_path == str(dest.resolve())
    photos = PhotoKitDestination(approved_root=str(dest))
    assert photos.can_publish is False
    with pytest.raises(PublicationError, match="Photos"):
        photos.assert_publishable()
    outside = tmp_path / "escape"
    outside.mkdir()
    with pytest.raises(Exception, match="outside user-approved"):
        publish_artifacts(
            [],
            ExportIntent(
                destination_kind=DestinationKind.FILES_APP,
                destination_path=str(outside),
                approved_roots=[str(outside)],
                security_scoped_path=str(dest),
            ),
        )


def test_dash_prefers_highest_video_representation() -> None:
    text = """
    <MPD><Period>
      <AdaptationSet contentType="audio">
        <SegmentTemplate media="audio/$RepresentationID$.m4s" startNumber="1"/>
        <Representation id="a1" bandwidth="128000" mimeType="audio/mp4"/>
      </AdaptationSet>
      <AdaptationSet contentType="video">
        <SegmentTemplate media="video/$RepresentationID$.m4s" startNumber="1"/>
        <Representation id="v1" bandwidth="800000" mimeType="video/mp4"/>
        <Representation id="v2" bandwidth="1600000" mimeType="video/mp4"/>
      </AdaptationSet>
    </Period></MPD>
    """
    urls = recordable_segment_urls(text, "https://cdn.example.com/manifest.mpd")
    assert urls == ["https://cdn.example.com/video/v2.m4s"]
    assert not any("audio" in url or "v1.m4s" in url for url in urls)


def test_hls_master_prefers_highest_bandwidth(tmp_path: Path) -> None:
    master = (
        "#EXTM3U\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=800000\nlow.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=1600000\nhigh.m3u8\n"
    )
    high = "#EXTM3U\n#EXTINF:1,\nhi.ts\n"

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("high.m3u8"):
            return 200, "application/vnd.apple.mpegurl", high.encode()
        if url.endswith("low.m3u8"):
            raise AssertionError("must not fetch lower-bandwidth variant")
        if url.endswith("hi.ts"):
            return 200, "video/MP2T", b"HI"
        raise AssertionError(url)

    output = tmp_path / "live.ts"
    record_clear_stream(master, "https://cdn.example.com/master.m3u8", output, fetch)
    assert output.read_bytes() == b"HI"


def test_dash_audio_only_picks_highest_audio() -> None:
    text = """
    <MPD><Period>
      <AdaptationSet contentType="audio">
        <SegmentTemplate media="audio/$RepresentationID$.m4s" startNumber="1"/>
        <Representation id="a1" bandwidth="64000" mimeType="audio/mp4"/>
        <Representation id="a2" bandwidth="128000" mimeType="audio/mp4"/>
      </AdaptationSet>
    </Period></MPD>
    """
    urls = recordable_segment_urls(text, "https://cdn.example.com/manifest.mpd")
    assert urls == ["https://cdn.example.com/audio/a2.m4s"]


def test_dash_period_representations_pick_highest_video() -> None:
    text = """
    <MPD><Period>
      <Representation id="v1" bandwidth="800000" mimeType="video/mp4">
        <SegmentTemplate media="$RepresentationID$.m4s" startNumber="1"/>
      </Representation>
      <Representation id="v2" bandwidth="1600000" mimeType="video/mp4">
        <SegmentTemplate media="$RepresentationID$.m4s" startNumber="1"/>
      </Representation>
    </Period></MPD>
    """
    urls = recordable_segment_urls(text, "https://cdn.example.com/manifest.mpd")
    assert urls == ["https://cdn.example.com/v2.m4s"]


def test_dash_multiperiod_concatenates_selected_video() -> None:
    text = """
    <MPD>
      <Period>
        <AdaptationSet contentType="video">
          <SegmentTemplate media="p1/$RepresentationID$.m4s" startNumber="1"/>
          <Representation id="v1" bandwidth="800000" mimeType="video/mp4"/>
          <Representation id="v2" bandwidth="1600000" mimeType="video/mp4"/>
        </AdaptationSet>
      </Period>
      <Period>
        <AdaptationSet contentType="video">
          <SegmentTemplate media="p2/$RepresentationID$.m4s" startNumber="1"/>
          <Representation id="v1" bandwidth="800000" mimeType="video/mp4"/>
          <Representation id="v2" bandwidth="1600000" mimeType="video/mp4"/>
        </AdaptationSet>
      </Period>
    </MPD>
    """
    urls = recordable_segment_urls(text, "https://cdn.example.com/manifest.mpd")
    assert urls == [
        "https://cdn.example.com/p1/v2.m4s",
        "https://cdn.example.com/p2/v2.m4s",
    ]


def test_dash_segmentbase_keeps_representation_file() -> None:
    text = """
    <MPD><Period>
      <Representation id="v1" bandwidth="800000" mimeType="video/mp4">
        <BaseURL>video.mp4</BaseURL>
        <SegmentBase indexRange="10-15">
          <Initialization range="0-9"/>
        </SegmentBase>
      </Representation>
    </Period></MPD>
    """
    from webmedia_dl.live import recordable_parts

    parts = recordable_parts(text, "https://cdn.example.com/")
    assert [(part.url, part.start, part.length) for part in parts] == [
        ("https://cdn.example.com/video.mp4", 0, 10),
        ("https://cdn.example.com/video.mp4", 10, 6),
    ]


def test_companion_relay_queues_until_mac_forwards() -> None:
    relay = CompanionRelay()
    queued = relay.enqueue({"kind": "capture", "locator": "https://example.com/a.mp4"})
    assert queued["queued"] is True
    assert queued["nativeCommand"] is None
    assert queued["subprocessWorker"] is False
    drained = relay.drain()
    assert len(drained) == 1
    assert drained[0]["kind"] == "capture"
    assert relay.drain() == []
    with pytest.raises(ProviderPolicyError, match="native command"):
        relay.enqueue(
            {
                "kind": "capture",
                "locator": "https://example.com/a.mp4",
                "nativeCommand": "yt-dlp",
            }
        )
    with pytest.raises(ProviderPolicyError, match="subprocess"):
        relay.enqueue(
            {
                "kind": "status",
                "subprocessWorker": True,
            }
        )


def test_http_direct_cancel_discards_completed_fetch(tmp_path: Path, png_bytes: bytes) -> None:
    runtime = ProviderRuntime()

    def getter(_url: str) -> tuple[int, dict[str, str], bytes]:
        runtime.cancel_running()
        return 200, {"content-type": "image/png"}, png_bytes

    runtime._http_get = getter
    with pytest.raises(CancelledError):
        runtime.execute(
            ProviderRequest(
                provider_id="http-direct",
                capability_id="acquire.http",
                typed_inputs={"url": "https://cdn.example.com/hero.png"},
            ),
            tmp_path,
        )
    assert list(tmp_path.glob("*.png")) == []


def test_http_direct_pause_keeps_completed_fetch(tmp_path: Path, png_bytes: bytes) -> None:
    runtime = ProviderRuntime()

    def getter(_url: str) -> tuple[int, dict[str, str], bytes]:
        runtime.pause_running()
        return 200, {"content-type": "image/png"}, png_bytes

    runtime._http_get = getter
    result = runtime.execute(
        ProviderRequest(
            provider_id="http-direct",
            capability_id="acquire.http",
            typed_inputs={"url": "https://cdn.example.com/hero.png"},
        ),
        tmp_path,
    )
    assert result.output_path is not None
    assert result.output_path.exists()
    with pytest.raises(PauseRequested):
        runtime.execute(
            ProviderRequest(
                provider_id="http-direct",
                capability_id="acquire.http",
                typed_inputs={"url": "https://cdn.example.com/hero2.png"},
            ),
            tmp_path,
        )
