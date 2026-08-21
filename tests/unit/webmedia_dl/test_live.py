from pathlib import Path

import pytest

from webmedia_dl.domain.enums import MediaKind
from webmedia_dl.errors import DiscoveryError, DrmRefused, PauseRequested
from webmedia_dl.live import (
    _select_dash_group,
    ManifestPart,
    inspect_manifest,
    manifest_is_live,
    record_clear_stream,
    record_kind_streams,
    recordable_parts,
    recordable_segment_urls,
)


def test_record_clear_stream_concatenates_segments(tmp_path: Path) -> None:
    playlist = "#EXTM3U\n#EXTINF:1,\nseg1.ts\n#EXTINF:1,\nseg2.ts\n"
    inspect_manifest(playlist)
    bodies = {
        "https://cdn.example.com/live/seg1.ts": b"AAA",
        "https://cdn.example.com/live/seg2.ts": b"BBB",
    }

    def fetch(url: str) -> tuple[int, str, bytes]:
        return 200, "video/MP2T", bodies[url]

    output = tmp_path / "live.ts"
    record_clear_stream(playlist, "https://cdn.example.com/live/index.m3u8", output, fetch)
    assert output.read_bytes() == b"AAABBB"


def test_record_follows_master_playlist(tmp_path: Path) -> None:
    master = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\nlow.m3u8\n"
    media = "#EXTM3U\n#EXTINF:1,\nseg.ts\n"

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("low.m3u8"):
            return 200, "application/vnd.apple.mpegurl", media.encode()
        return 200, "video/MP2T", b"SEG"

    output = tmp_path / "live.ts"
    record_clear_stream(master, "https://cdn.example.com/master.m3u8", output, fetch)
    assert output.read_bytes() == b"SEG"


def test_relative_segment_urls_join_base() -> None:
    text = "#EXTM3U\n#EXT-X-KEY:METHOD=NONE\nseg.ts\n"
    urls = recordable_segment_urls(text, "https://cdn.example.com/live/index.m3u8")
    assert urls == ["https://cdn.example.com/live/seg.ts"]


def test_encrypted_master_refused_before_fetch(tmp_path: Path) -> None:
    text = '#EXTM3U\n#EXT-X-KEY:METHOD=SAMPLE-AES,URI="https://example.com/key"\nseg.ts\n'
    with pytest.raises(DrmRefused):
        inspect_manifest(text)
    with pytest.raises(DrmRefused):
        record_clear_stream(
            text,
            "https://cdn.example.com/live.m3u8",
            tmp_path / "x.ts",
            lambda url: (200, "", b""),
        )


def test_aes128_playlist_refused_before_any_segment_fetch(tmp_path: Path) -> None:
    text = '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key"\nseg.ts\n'
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        raise AssertionError(url)

    with pytest.raises(DrmRefused, match="AES-128"):
        inspect_manifest(text)
    with pytest.raises(DrmRefused, match="AES-128"):
        record_clear_stream(text, "https://cdn.example.com/live.m3u8", tmp_path / "x.ts", fetch)
    assert fetched == []


def test_live_segment_http_error_fails_closed(tmp_path: Path) -> None:
    from webmedia_dl.errors import DiscoveryError

    playlist = "#EXTM3U\n#EXTINF:1,\nseg.ts\n"

    def fetch(url: str) -> tuple[int, str, bytes]:
        return 404, "", b""

    with pytest.raises(DiscoveryError, match="HTTP 404"):
        record_clear_stream(playlist, "https://cdn.example.com/live.m3u8", tmp_path / "x.ts", fetch)


def test_inspect_manifest_aes128_without_clear_prefix() -> None:
    with pytest.raises(DrmRefused, match="AES-128"):
        inspect_manifest('#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key"\n')


def test_hls_map_invalid_byterange_and_blank_lines(tmp_path: Path) -> None:
    playlist = '#EXTM3U\n\n#EXT-X-MAP:URI="init.mp4",BYTERANGE="nope"\nseg.ts\n'
    bodies = {
        "https://cdn.example.com/live/init.mp4": b"INIT",
        "https://cdn.example.com/live/seg.ts": b"SEG",
    }

    def fetch(url: str) -> tuple[int, str, bytes]:
        return 200, "video/mp4", bodies[url]

    output = tmp_path / "live.bin"
    record_clear_stream(playlist, "https://cdn.example.com/live/index.m3u8", output, fetch)
    assert output.read_bytes() == b"INITSEG"


def test_dash_directory_baseurl_without_slash() -> None:
    from webmedia_dl.live import recordable_segment_urls

    text = """
    <MPD><Period>
      <BaseURL>https://cdn.example.com/dash</BaseURL>
      <SegmentTemplate media="seg$Number$.m4s" startNumber="1"/>
    </Period></MPD>
    """
    urls = recordable_segment_urls(text, "https://cdn.example.com/manifest.mpd")
    assert urls == ["https://cdn.example.com/dash/seg1.m4s"]


def test_time_token_without_timeline_is_skipped() -> None:
    from webmedia_dl.live import recordable_segment_urls

    text = """
    <MPD><Period>
      <SegmentTemplate media="t_$Time$.m4s" startNumber="1"/>
    </Period></MPD>
    """
    assert recordable_segment_urls(text, "https://cdn.example.com/") == []


def test_dash_segmentbase_media_range() -> None:
    text = """
    <MPD><Period>
      <Representation id="v1" bandwidth="800000" mimeType="video/mp4">
        <BaseURL>video.mp4</BaseURL>
        <SegmentBase indexRange="10-15" mediaRange="16-20">
          <Initialization range="0-9"/>
        </SegmentBase>
      </Representation>
    </Period></MPD>
    """
    parts = recordable_parts(text, "https://cdn.example.com/")
    assert [(part.url, part.start, part.length) for part in parts] == [
        ("https://cdn.example.com/video.mp4", 0, 10),
        ("https://cdn.example.com/video.mp4", 10, 6),
        ("https://cdn.example.com/video.mp4", 16, 5),
    ]


def test_select_dash_group_prefers_video_then_audio() -> None:
    video = [ManifestPart("https://cdn.example.com/v.m4s")]
    audio = [ManifestPart("https://cdn.example.com/a.m4a")]
    assert _select_dash_group([(1, "video", video), (9, "audio", audio)]) == video
    assert _select_dash_group([(9, "audio", audio)]) == audio
    assert _select_dash_group([]) == []


def test_manifest_is_live_requires_mpd_open_or_hls_without_endlist() -> None:
    assert manifest_is_live("see <MPD without a closing bracket") is False
    assert manifest_is_live('<MPD type="dynamic">') is True
    assert manifest_is_live('<MPD type="static">') is False
    assert manifest_is_live("#EXTM3U\n#EXTINF:1,\nseg.ts\n") is True
    assert manifest_is_live("#EXTM3U\n#EXT-X-ENDLIST\n") is False
    assert manifest_is_live("not a playlist") is False


def test_record_refuses_dash_content_protection_before_fetch(tmp_path: Path) -> None:
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        raise AssertionError(url)

    with pytest.raises(DrmRefused, match="ContentProtection"):
        record_clear_stream(
            "<MPD><ContentProtection schemeIdUri='urn:mpeg:cenc'/></MPD>",
            "https://cdn.example.com/manifest.mpd",
            tmp_path / "x.bin",
            fetch,
        )
    assert fetched == []


def test_empty_live_segments_fail_closed(tmp_path: Path) -> None:
    playlist = "#EXTM3U\n#EXTINF:1,\nseg.ts\n"
    with pytest.raises(DiscoveryError, match="empty artifact"):
        record_clear_stream(
            playlist,
            "https://cdn.example.com/live.m3u8",
            tmp_path / "x.ts",
            lambda url: (200, "", b""),
        )


def test_record_kind_streams_hls_without_audio_stays_live(tmp_path: Path) -> None:
    playlist = "#EXTM3U\n#EXTINF:1,\nseg.ts\n"
    dest = tmp_path / "live.ts"
    recorded = record_kind_streams(
        playlist,
        "https://cdn.example.com/live.m3u8",
        dest,
        lambda url: (200, "", b"SEG"),
    )
    assert recorded == [(MediaKind.LIVE_STREAM, dest)]
    assert dest.read_bytes() == b"SEG"


def test_nested_playlist_respects_should_stop(tmp_path: Path) -> None:
    master = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\nlow.m3u8\n"
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        return 200, "", b"#EXTM3U\n#EXTINF:1,\nseg.ts\n"

    def should_stop() -> None:
        raise PauseRequested("nested")

    with pytest.raises(PauseRequested, match="nested"):
        record_clear_stream(
            master,
            "https://cdn.example.com/master.m3u8",
            tmp_path / "x.ts",
            fetch,
            should_stop=should_stop,
        )
    assert fetched == []


def test_record_kind_streams_stops_before_audio_fetch(tmp_path: Path) -> None:
    master = (
        "#EXTM3U\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",URI="audio.m3u8"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=1,AUDIO="aac"\n'
        "video.m3u8\n"
    )
    dest = tmp_path / "live.bin"
    fetched: list[str] = []

    def should_stop() -> None:
        if dest.exists() and dest.stat().st_size > 0:
            raise PauseRequested("stop before audio")

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        if url.endswith("video.m3u8"):
            return 200, "application/vnd.apple.mpegurl", b"#EXTM3U\n#EXTINF:1,\nv.ts\n"
        if url.endswith("v.ts"):
            return 200, "video/MP2T", b"V"
        if url.endswith("audio.m3u8"):
            return 200, "application/vnd.apple.mpegurl", b"#EXTM3U\n#EXTINF:1,\na.ts\n"
        if url.endswith("a.ts"):
            return 200, "audio/aac", b"A"
        return 200, "application/vnd.apple.mpegurl", master.encode()

    with pytest.raises(PauseRequested, match="before audio"):
        record_kind_streams(
            master,
            "https://cdn.example.com/master.m3u8",
            dest,
            fetch,
            should_stop=should_stop,
        )
    assert not any(item.endswith("audio.m3u8") for item in fetched)
