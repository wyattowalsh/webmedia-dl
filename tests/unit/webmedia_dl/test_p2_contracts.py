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
from webmedia_dl.domain.enums import DestinationKind, EventType, IntakeKind, MediaKind, Surface
from webmedia_dl.domain.models import EventRecord, ExportIntent
from webmedia_dl.errors import (
    CancelledError,
    DiscoveryError,
    IntakeError,
    PauseRequested,
    ProviderPolicyError,
    PublicationError,
)
from webmedia_dl.live import (
    MAX_TIMELINE_SEGMENTS,
    hls_audio_playlist_urls,
    manifest_is_live,
    record_clear_stream,
    record_kind_streams,
    recordable_segment_urls,
)
from webmedia_dl.providers import ProviderRequest, ProviderRuntime
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


def test_dynamic_mpd_poll_stops_on_contentprotection(tmp_path: Path) -> None:
    first = (
        '<MPD type="dynamic"><Period>'
        '<SegmentTemplate media="seg$Number$.m4s" startNumber="1"/>'
        "</Period></MPD>"
    )
    protected = (
        '<MPD type="dynamic"><ContentProtection schemeIdUri="urn:mpeg:cenc"/>'
        "<Period>"
        '<SegmentTemplate media="secret$Number$.m4s" startNumber="2"/>'
        "</Period></MPD>"
    )
    playlists = [protected]
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        if url.endswith("live.mpd"):
            payload = playlists.pop(0) if playlists else protected
            return 200, "application/dash+xml", payload.encode()
        if "secret" in url:
            raise AssertionError(url)
        return 200, "video/mp4", b"CLEAR"

    output = tmp_path / "live.bin"
    record_clear_stream(
        first,
        "https://cdn.example.com/live.mpd",
        output,
        fetch,
        live_polls=2,
    )
    assert output.read_bytes() == b"CLEAR"
    assert any(item.endswith("seg1.m4s") for item in fetched)
    assert all("secret" not in item for item in fetched)


def test_hls_live_poll_stops_on_later_aes128(tmp_path: Path) -> None:
    first = "#EXTM3U\n#EXTINF:1,\nseg1.ts\n"
    second = (
        '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key"\n#EXTINF:1,\nsecret.ts\n'
    )
    playlists = [second]
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        if url.endswith("index.m3u8"):
            payload = playlists.pop(0) if playlists else second
            return 200, "application/vnd.apple.mpegurl", payload.encode()
        if url.endswith("secret.ts") or "key" in url:
            raise AssertionError(url)
        return 200, "video/MP2T", b"A"

    output = tmp_path / "live.ts"
    record_clear_stream(
        first,
        "https://cdn.example.com/live/index.m3u8",
        output,
        fetch,
        live_polls=2,
    )
    assert output.read_bytes() == b"A"
    assert all("secret" not in item for item in fetched)


def test_hls_live_poll_keeps_prefix_when_playlist_fetch_fails(tmp_path: Path) -> None:
    first = "#EXTM3U\n#EXTINF:1,\nseg1.ts\n"

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("index.m3u8"):
            return 404, "", b""
        return 200, "video/MP2T", b"A"

    output = tmp_path / "live.ts"
    record_clear_stream(
        first,
        "https://cdn.example.com/live/index.m3u8",
        output,
        fetch,
        live_polls=2,
    )
    assert output.read_bytes() == b"A"


def test_audio_only_dash_uses_highest_bandwidth(tmp_path: Path) -> None:
    from webmedia_dl.domain.enums import MediaKind
    from webmedia_dl.live import record_kind_streams

    text = """
    <MPD><Period>
      <AdaptationSet contentType="audio">
        <SegmentTemplate media="$RepresentationID$.m4s" startNumber="1"/>
        <Representation id="low" bandwidth="64000" mimeType="audio/mp4"/>
        <Representation id="high" bandwidth="256000" mimeType="audio/mp4"/>
      </AdaptationSet>
    </Period></MPD>
    """
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        if url.endswith("low.m4s"):
            raise AssertionError(url)
        return 200, "audio/mp4", b"HI"

    recorded = record_kind_streams(
        text,
        "https://cdn.example.com/manifest.mpd",
        tmp_path / "dash.bin",
        fetch,
    )
    assert recorded == [(MediaKind.AUDIO, tmp_path / "dash.bin")]
    assert (tmp_path / "dash.bin").read_bytes() == b"HI"
    assert any(item.endswith("high.m4s") for item in fetched)
    assert all("low.m4s" not in item for item in fetched)


def test_hls_map_without_byterange_and_implicit_offset(tmp_path: Path) -> None:
    playlist = (
        "#EXTM3U\n"
        '#EXT-X-MAP:URI="init.mp4"\n'
        "#EXT-X-BYTERANGE:3\n"
        "seg.ts\n"
        "#EXT-X-BYTERANGE:3\n"
        "seg.ts\n"
    )
    bodies = {
        "https://cdn.example.com/live/init.mp4": b"INITXXXX",
        "https://cdn.example.com/live/seg.ts": b"ABCDEF",
    }

    def fetch(url: str) -> tuple[int, str, bytes]:
        return 200, "video/mp4", bodies[url]

    output = tmp_path / "live.bin"
    record_clear_stream(playlist, "https://cdn.example.com/live/index.m3u8", output, fetch)
    assert output.read_bytes() == b"INITXXXXABCDEF"


def test_dash_number_width_and_dollar_escape() -> None:
    padded = """
    <MPD><Period>
      <SegmentTemplate media="seg$Number%05d$.m4s" startNumber="7"/>
    </Period></MPD>
    """
    urls = recordable_segment_urls(padded, "https://cdn.example.com/")
    assert urls == ["https://cdn.example.com/seg00007.m4s"]
    escaped = """
    <MPD><Period>
      <SegmentTemplate media="a$$b/$Number$.m4s" startNumber="1"/>
    </Period></MPD>
    """
    dollars = recordable_segment_urls(escaped, "https://cdn.example.com/")
    assert dollars == ["https://cdn.example.com/a$b/1.m4s"]
    invalid_range = """
    <MPD><Period><SegmentList>
      <Initialization sourceURL="bundle.mp4" range="9-1"/>
      <SegmentURL media="ok.m4s" mediaRange="nope"/>
    </SegmentList></Period></MPD>
    """
    parts = recordable_segment_urls(invalid_range, "https://cdn.example.com/")
    assert parts == [
        "https://cdn.example.com/bundle.mp4",
        "https://cdn.example.com/ok.m4s",
    ]


def test_adaptationset_without_representation_keeps_segment_list() -> None:
    text = """
    <MPD><Period>
      <AdaptationSet mimeType="audio/mp4">
        <SegmentList>
          <SegmentURL media="only-audio.m4s"/>
        </SegmentList>
      </AdaptationSet>
    </Period></MPD>
    """
    urls = recordable_segment_urls(text, "https://cdn.example.com/")
    assert urls == ["https://cdn.example.com/only-audio.m4s"]


def test_video_only_dash_is_video_kind(tmp_path: Path) -> None:
    text = """
    <MPD><Period>
      <AdaptationSet contentType="video">
        <SegmentTemplate media="$RepresentationID$.m4s" startNumber="1"/>
        <Representation id="v1" bandwidth="800000" mimeType="video/mp4"/>
        <Representation id="bad" bandwidth="nope" mimeType="video/mp4"/>
      </AdaptationSet>
    </Period></MPD>
    """
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        if url.endswith("bad.m4s"):
            raise AssertionError(url)
        return 200, "video/mp4", b"VID"

    recorded = record_kind_streams(
        text,
        "https://cdn.example.com/manifest.mpd",
        tmp_path / "dash.bin",
        fetch,
    )
    assert recorded == [(MediaKind.VIDEO, tmp_path / "dash.bin")]
    assert (tmp_path / "dash.bin").read_bytes() == b"VID"
    assert any(item.endswith("v1.m4s") for item in fetched)


def test_dash_open_ended_timeline_is_capped() -> None:
    text = """
    <MPD><Period>
      <SegmentTemplate media="chunk_$Number$.m4s" startNumber="1">
        <SegmentTimeline>
          <S t="0" d="90000" r="-1"/>
        </SegmentTimeline>
      </SegmentTemplate>
    </Period></MPD>
    """
    urls = recordable_segment_urls(text, "https://cdn.example.com/")
    assert urls == [
        f"https://cdn.example.com/chunk_{index}.m4s"
        for index in range(1, MAX_TIMELINE_SEGMENTS + 1)
    ]


def test_dash_invalid_number_format_falls_back_to_decimal() -> None:
    text = """
    <MPD><Period>
      <SegmentTemplate media="seg$Number%zz$.m4s" startNumber="3"/>
    </Period></MPD>
    """
    urls = recordable_segment_urls(text, "https://cdn.example.com/")
    assert urls == ["https://cdn.example.com/seg3.m4s"]


def test_record_clear_stream_replaces_existing_dest(tmp_path: Path) -> None:
    playlist = "#EXTM3U\n#EXTINF:1,\nseg.ts\n"
    output = tmp_path / "live.ts"
    output.write_bytes(b"OLD")

    def fetch(url: str) -> tuple[int, str, bytes]:
        return 200, "video/MP2T", b"NEW"

    record_clear_stream(playlist, "https://cdn.example.com/live.m3u8", output, fetch)
    assert output.read_bytes() == b"NEW"


def test_hls_audio_media_skips_non_audio_and_duplicates() -> None:
    text = (
        "#EXTM3U\n"
        '#EXT-X-MEDIA:TYPE=VIDEO,URI="v.m3u8"\n'
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac"\n'
        '#EXT-X-MEDIA:TYPE=AUDIO,URI="a.m3u8"\n'
        '#EXT-X-MEDIA:TYPE=AUDIO,URI="a.m3u8"\n'
    )
    assert hls_audio_playlist_urls(text, "https://cdn.example.com/") == [
        "https://cdn.example.com/a.m3u8"
    ]


def test_hls_audio_playlist_fetch_failure(tmp_path: Path) -> None:
    master = (
        "#EXTM3U\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",URI="audio.m3u8"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=1,AUDIO="aac"\n'
        "video.m3u8\n"
    )

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("video.m3u8"):
            return 200, "application/vnd.apple.mpegurl", b"#EXTM3U\n#EXTINF:1,\nv.ts\n"
        if url.endswith("v.ts"):
            return 200, "video/MP2T", b"V"
        if url.endswith("audio.m3u8"):
            return 404, "", b""
        return 200, "application/vnd.apple.mpegurl", master.encode()

    with pytest.raises(DiscoveryError, match="audio playlist"):
        record_kind_streams(
            master,
            "https://cdn.example.com/master.m3u8",
            tmp_path / "live.bin",
            fetch,
        )


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


@pytest.mark.parametrize(
    "payload",
    [
        {"stdout": "ffmpeg"},
        {"stderr": "ffmpeg"},
        {"nativeCommand": "yt-dlp"},
        {"providerArgv": ["--format"]},
        {"cookies_path": "/tmp/cookies.txt"},
        {"nested": {"stdout": "secret"}},
        {"nested": ({"stdout": "secret"},)},
    ],
)
def test_event_payload_rejects_every_forbidden_key(payload: dict) -> None:
    with pytest.raises(ValidationError):
        EventRecord(
            job_id=uuid4(),
            type=EventType.OPERATION_COMPLETED,
            sequence=1,
            payload=payload,
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
    assert not SecurityScopedBookmark(resolved_path="").allows(str(dest / "clip.mp4"))
    assert not SecurityScopedBookmark(resolved_path="   ").allows(str(dest / "clip.mp4"))
    intent = FilesAppDestination(bookmark=bookmark).as_intent()
    assert intent.destination_kind is DestinationKind.FILES_APP
    assert intent.security_scoped_path == str(dest.resolve())
    assert intent.security_scoped_bookmark
    photos = PhotoKitDestination(approved_root=str(dest))
    assert photos.can_publish is False
    with pytest.raises(PublicationError, match="Photos"):
        photos.assert_publishable()
    outside = tmp_path / "escape"
    outside.mkdir()
    with pytest.raises(ValueError, match="inside approved roots"):
        ExportIntent(
            destination_kind=DestinationKind.FILES_APP,
            destination_path=str(outside),
            approved_roots=[str(outside)],
            security_scoped_path=str(dest),
            security_scoped_bookmark="ZmFrZQ==",
        )
    with pytest.raises(ValueError, match="security-scoped bookmark"):
        ExportIntent(
            destination_kind=DestinationKind.FILES_APP,
            destination_path=str(dest),
            approved_roots=[str(dest)],
        )
    sneaky = dest / ".." / "escape"
    with pytest.raises(ValueError, match="inside approved roots"):
        ExportIntent(
            destination_kind=DestinationKind.FILES_APP,
            destination_path=str(sneaky),
            approved_roots=[str(dest)],
            security_scoped_bookmark="ZmFrZQ==",
        )
    nested = ExportIntent(
        destination_kind=DestinationKind.FILES_APP,
        destination_path=str(dest / "inside"),
        approved_roots=[str(dest)],
        security_scoped_bookmark="ZmFrZQ==",
    )
    assert nested.security_scoped_path == str(dest / "inside")


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
        "#EXT-X-STREAM-INF:AVERAGE-BANDWIDTH=9999999\nskip-no-bw.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=not-a-number\nskip-bad.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=1,BANDWIDTH=9999999\nskip-dup.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=800000,AVERAGE-BANDWIDTH=2000000\nlow.m3u8\n"
        "#EXT-X-STREAM-INF:AVERAGE-BANDWIDTH=400000,BANDWIDTH=1600000\nhigh.m3u8\n"
    )
    high = "#EXTM3U\n#EXTINF:1,\nhi.ts\n"

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("high.m3u8"):
            return 200, "application/vnd.apple.mpegurl", high.encode()
        if url.endswith(("low.m3u8", "skip-no-bw.m3u8", "skip-bad.m3u8", "skip-dup.m3u8")):
            raise AssertionError("must not fetch lower-bandwidth or malformed variants")
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
