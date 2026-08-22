from pathlib import Path

from webmedia_dl.domain.enums import EventType, JobState, MediaKind
from webmedia_dl.pipeline import Pipeline
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
