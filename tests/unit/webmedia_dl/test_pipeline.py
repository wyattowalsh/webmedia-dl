from pathlib import Path

from webmedia_dl.domain.enums import JobState, Surface
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.providers import ProviderRuntime


def test_pipeline_downloads_direct_png(tmp_data: Path, png_bytes: bytes) -> None:
    runtime = ProviderRuntime(http_get=lambda url: (200, {"content-type": "image/png"}, png_bytes))
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit("https://cdn.example.com/hero.png")
    assert job.state is JobState.COMPLETED
    events = pipeline.queue.events_for(job.job_id)
    types = [event.type.value for event in events]
    assert "artifact.source_registered" in types
    assert "publication.committed" in types
    assert job.error is None


def test_pipeline_html_fixture_without_network(tmp_data: Path, png_bytes: bytes) -> None:
    html = """
    <html><body>
      <img src="https://cdn.example.com/hero.png">
    </body></html>
    """
    runtime = ProviderRuntime(http_get=lambda url: (200, {}, png_bytes))
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit(
        "https://example.com/gallery",
        html=html,
        surface=Surface.CLI,
    )
    assert job.state is JobState.COMPLETED


def test_pipeline_records_drm_failure(tmp_data: Path) -> None:
    html = """
    <html><body>
      <video src="https://cdn.example.com/widevine-stream.mpd"></video>
      <p>com.widevine.alpha</p>
    </body></html>
    """
    pipeline = Pipeline(
        data_dir=tmp_data, runtime=ProviderRuntime(http_get=lambda url: (200, {}, b"x"))
    )
    job = pipeline.submit("https://example.com/drm", html=html)
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "DRM" in job.error or "drm" in job.error.lower() or "widevine" in job.error.lower()
