from pathlib import Path

import pytest

from webmedia_dl.domain.enums import EventType, JobState, MediaKind
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import get_profile
from webmedia_dl.providers import ProviderRuntime


def test_pipeline_records_clear_hls(tmp_data: Path) -> None:
    playlist = "#EXTM3U\n#EXTINF:1,\nseg.ts\n"
    bodies = {
        "https://cdn.example.com/live.m3u8": playlist.encode(),
        "https://cdn.example.com/seg.ts": b"SEGMENT",
    }

    def fetch(url: str) -> tuple[int, str, bytes]:
        return 200, "application/vnd.apple.mpegurl", bodies[url]

    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(http_get=lambda url: (200, {}, bodies.get(url, b""))),
        fetch=fetch,
    )
    job = pipeline.submit("https://cdn.example.com/live.m3u8")
    assert job.state is JobState.COMPLETED
    artifacts = list(pipeline.store._records.values())
    assert artifacts
    assert artifacts[0].media_kind is MediaKind.LIVE_STREAM
    path = pipeline.store.resolve(artifacts[0])
    assert path.read_bytes() == b"SEGMENT"

    html = (
        "<html><body>"
        '<source type="application/vnd.apple.mpegurl" '
        'src="https://cdn.example.com/plain-live">'
        "</body></html>"
    )
    bodies["https://cdn.example.com/plain-live"] = b"#EXTM3U\n#EXTINF:1,\nplain.ts\n"
    bodies["https://cdn.example.com/plain.ts"] = b"PLAINLIVE"
    job = pipeline.submit("https://example.com/watch", html=html)
    assert job.state is JobState.COMPLETED
    ranked = [
        event.payload["strategies"]
        for event in pipeline.queue.events_for(job.job_id)
        if event.type is EventType.PLAN_RANKED
    ]
    assert ranked == [["live-clear-record"]]
    live_bytes = {
        pipeline.store.resolve(item).read_bytes()
        for item in pipeline.store._records.values()
        if item.media_kind is MediaKind.LIVE_STREAM
    }
    assert live_bytes == {b"SEGMENT", b"PLAINLIVE"}
    bodies["https://cdn.example.com/live.m3u"] = b"#EXTM3U\n#EXTINF:1,\nm3u.ts\n"
    bodies["https://cdn.example.com/m3u.ts"] = b"M3ULIVE"
    job = pipeline.submit("https://cdn.example.com/live.m3u")
    assert job.state is JobState.COMPLETED
    ranked = [
        event.payload["strategies"]
        for event in pipeline.queue.events_for(job.job_id)
        if event.type is EventType.PLAN_RANKED
    ]
    assert ranked == [["live-clear-record"]]
    live_bytes = {
        pipeline.store.resolve(item).read_bytes()
        for item in pipeline.store._records.values()
        if item.media_kind is MediaKind.LIVE_STREAM
    }
    assert live_bytes == {b"SEGMENT", b"PLAINLIVE", b"M3ULIVE"}
    steal = (
        "<html><head>"
        '<link type="application/vnd.apple.mpegurl" href="https://example.com/watch">'
        "</head><body>"
        '<video src="https://cdn.example.com/steal.m3u8"></video>'
        "</body></html>"
    )
    bodies["https://example.com/watch"] = b"<html>not a playlist</html>"
    bodies["https://cdn.example.com/steal.m3u8"] = b"#EXTM3U\n#EXTINF:1,\nsteal.ts\n"
    bodies["https://cdn.example.com/steal.ts"] = b"STEALLIVE"
    job = pipeline.submit("https://example.com/watch-page", html=steal)
    assert job.state is JobState.COMPLETED
    ranked = [
        event.payload["strategies"]
        for event in pipeline.queue.events_for(job.job_id)
        if event.type is EventType.PLAN_RANKED
    ]
    assert ranked == [["live-clear-record"]]
    live_bytes = {
        pipeline.store.resolve(item).read_bytes()
        for item in pipeline.store._records.values()
        if item.media_kind is MediaKind.LIVE_STREAM
    }
    assert b"STEALLIVE" in live_bytes
    mixed = (
        "<html><body>"
        '<video src="https://cdn.example.com/clip.mp4"></video>'
        '<video src="https://cdn.example.com/mixed.m3u8"></video>'
        "</body></html>"
    )
    bodies["https://cdn.example.com/clip.mp4"] = b"MP4BYTES"
    bodies["https://cdn.example.com/mixed.m3u8"] = b"#EXTM3U\n#EXTINF:1,\nmixed.ts\n"
    bodies["https://cdn.example.com/mixed.ts"] = b"MIXEDLIVE"
    job = pipeline.submit("https://example.com/clip-and-live", html=mixed)
    assert job.state is JobState.COMPLETED
    ranked = [
        event.payload["strategies"]
        for event in pipeline.queue.events_for(job.job_id)
        if event.type is EventType.PLAN_RANKED
    ]
    assert ranked == [["http-direct", "ytdlp"], ["live-clear-record"]]
    source_bytes = {
        pipeline.store.resolve(item).read_bytes()
        for item in pipeline.store._records.values()
        if item.role.value == "source"
    }
    assert b"MP4BYTES" in source_bytes
    assert b"MIXEDLIVE" in source_bytes
    slash = (
        "<html><head>"
        '<link type="application/vnd.apple.mpegurl" href="https://example.com/watch">'
        "</head><body>"
        '<video src="https://cdn.example.com/slash.m3u8/"></video>'
        "</body></html>"
    )
    bodies["https://cdn.example.com/slash.m3u8/"] = b"#EXTM3U\n#EXTINF:1,\nslash.ts\n"
    bodies["https://cdn.example.com/slash.ts"] = b"SLASHLIVE"
    job = pipeline.submit("https://example.com/slash-live", html=slash)
    assert job.state is JobState.COMPLETED
    ranked = [
        event.payload["strategies"]
        for event in pipeline.queue.events_for(job.job_id)
        if event.type is EventType.PLAN_RANKED
    ]
    assert ranked == [["live-clear-record"]]
    live_bytes = {
        pipeline.store.resolve(item).read_bytes()
        for item in pipeline.store._records.values()
        if item.media_kind is MediaKind.LIVE_STREAM
    }
    assert b"SLASHLIVE" in live_bytes


def test_live_playlist_fetch_uses_download_bound(
    tmp_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    playlist = b"#EXTM3U\n#EXTINF:1,\nseg.ts\n"
    bodies = {
        "https://cdn.example.com/live.m3u8": (200, "application/vnd.apple.mpegurl", playlist),
        "https://cdn.example.com/seg.ts": (200, "video/mp2t", b"SEGMENT"),
    }
    calls: list[tuple[str, int | None, object]] = []

    def fake_fetch(
        url: str,
        *,
        profile: object,
        max_bytes: int | None = None,
        on_overflow: str = "error",
        **_kwargs: object,
    ) -> tuple[int, str, bytes]:
        calls.append((url, max_bytes, on_overflow))
        return bodies[url]

    monkeypatch.setattr("webmedia_dl.pipeline.bound_fetch", fake_fetch)
    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(run=lambda _argv, _staging: (1, b"", b"")),
    )
    job = pipeline.submit("https://cdn.example.com/live.m3u8")
    assert job.state is JobState.COMPLETED
    bound = get_profile("personal-full").max_download_bytes
    playlist_calls = [item for item in calls if item[0].endswith("/live.m3u8")]
    segment_calls = [item for item in calls if item[0].endswith("/seg.ts")]
    assert playlist_calls
    assert segment_calls
    assert all(item[1] == bound and item[2] == "error" for item in playlist_calls)
    assert all(item[1] == bound and item[2] == "error" for item in segment_calls)


def test_pipeline_fetches_html_when_no_fixture(tmp_data: Path, png_bytes: bytes) -> None:
    html = b'<html><body><img src="https://cdn.example.com/hero.png"></body></html>'

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith(".png"):
            return 200, "image/png", png_bytes
        return 200, "text/html", html

    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(http_get=lambda url: (200, {}, png_bytes)),
        fetch=fetch,
    )
    job = pipeline.submit("https://example.com/gallery")
    assert job.state is JobState.COMPLETED
