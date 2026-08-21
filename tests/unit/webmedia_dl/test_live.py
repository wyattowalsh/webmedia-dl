from pathlib import Path

import pytest

from webmedia_dl.errors import DrmRefused
from webmedia_dl.live import inspect_manifest, record_clear_stream, recordable_segment_urls


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
