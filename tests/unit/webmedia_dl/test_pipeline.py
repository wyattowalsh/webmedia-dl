from pathlib import Path

import pytest

from webmedia_dl.domain.enums import JobState, Surface
from webmedia_dl.errors import CapabilityDenied, ProviderPolicyError
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import get_profile
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


def test_pipeline_emits_cookie_attached(tmp_data: Path, tmp_path: Path, png_bytes: bytes) -> None:
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), cookies=str(cookies))
    assert job.state is JobState.COMPLETED
    types = [event.type.value for event in pipeline.queue.events_for(job.job_id)]
    assert "cookie.attached" in types
    event = next(
        item
        for item in pipeline.queue.events_for(job.job_id)
        if item.type.value == "cookie.attached"
    )
    assert event.payload["cookies_path_basename"] == "user-cookies.txt"


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
    types = [event.type.value for event in pipeline.queue.events_for(job.job_id)]
    assert "artifact.evidence_registered" in types


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


def test_pipeline_acquires_mixed_image_and_video(tmp_data: Path, png_bytes: bytes) -> None:
    html = """
    <html><body>
      <video src="https://cdn.example.com/clip.mp4"></video>
      <img src="https://cdn.example.com/hero.png">
    </body></html>
    """

    def http_get(url: str) -> tuple[int, dict[str, str], bytes]:
        if url.endswith(".png"):
            return 200, {}, png_bytes
        return 200, {}, b"fake-mp4-bytes"

    pipeline = Pipeline(data_dir=tmp_data, runtime=ProviderRuntime(http_get=http_get))
    job = pipeline.submit("https://example.com/mixed", html=html)
    assert job.state is JobState.COMPLETED
    sources = [item for item in pipeline.store.list_artifacts() if item.role.value == "source"]
    assert len(sources) >= 2
    line = pipeline.store.lineage(sources[0].artifact_id)
    assert line[0].artifact_id == sources[0].artifact_id


def test_failed_remux_still_publishes_original(
    tmp_path: Path, pass_container_probe: object
) -> None:
    from webmedia_dl.domain.enums import DestinationKind
    from webmedia_dl.domain.models import ExportIntent

    dest = tmp_path / "out"
    dest.mkdir()
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"fake-mp4-bytes")

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        return 1, b"", b"ffmpeg failed"

    pipeline = Pipeline(
        data_dir=tmp_path / "data",
        runtime=ProviderRuntime(
            which=lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None,
            run=run,
        ),
    )
    job = pipeline.submit(
        str(media),
        intent=ExportIntent(
            destination_kind=DestinationKind.USER_APPROVED_PATH,
            destination_path=str(dest),
            approved_roots=[str(dest)],
            container_preference="mkv",
        ),
    )
    assert job.state is JobState.COMPLETED
    published = [path for path in dest.rglob("*") if path.is_file()]
    assert published
    assert any(path.read_bytes() == b"fake-mp4-bytes" for path in published)


def test_export_policy_error_still_publishes_original(
    tmp_path: Path, pass_container_probe: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    from webmedia_dl.domain.enums import DestinationKind
    from webmedia_dl.domain.models import ExportIntent

    dest = tmp_path / "out"
    dest.mkdir()
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"fake-mp4-bytes")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise ProviderPolicyError("export exploded")

    monkeypatch.setattr("webmedia_dl.pipeline.execute_export_plan", boom)
    pipeline = Pipeline(data_dir=tmp_path / "data")
    job = pipeline.submit(
        str(media),
        intent=ExportIntent(
            destination_kind=DestinationKind.USER_APPROVED_PATH,
            destination_path=str(dest),
            approved_roots=[str(dest)],
            container_preference="mkv",
        ),
    )
    assert job.state is JobState.COMPLETED
    published = [path for path in dest.rglob("*") if path.is_file()]
    assert any(path.read_bytes() == b"fake-mp4-bytes" for path in published)


def test_cookie_grant_when_repo_root_missing(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    def missing() -> Path:
        raise FileNotFoundError("no checkout")

    monkeypatch.setattr("webmedia_dl.pipeline.repo_root", missing)
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), cookies=str(cookies))
    assert job.state is JobState.COMPLETED
    types = [event.type.value for event in pipeline.queue.events_for(job.job_id)]
    assert "cookie.attached" in types


def test_live_playlist_http_error_fails_job(tmp_data: Path) -> None:
    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(http_get=lambda url: (400, {}, b"")),
        fetch=lambda url: (400, "", b"nope"),
    )
    job = pipeline.submit("https://cdn.example.com/live.m3u8")
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "HTTP 400" in job.error


def test_pause_and_cancel_during_discovery_fetch(tmp_data: Path, png_bytes: bytes) -> None:
    html = b'<html><body><img src="https://cdn.example.com/hero.png"></body></html>'

    def page(url: str) -> tuple[int, str, bytes]:
        if url.endswith(".png"):
            return 200, "image/png", png_bytes
        return 200, "text/html", html

    paused = Pipeline(
        data_dir=tmp_data / "pause",
        runtime=ProviderRuntime(http_get=lambda url: (200, {}, png_bytes)),
    )
    pause_job = paused.submit("https://example.com/gallery", wait=False)

    def pause_fetch(url: str) -> tuple[int, str, bytes]:
        paused.queue.set_job_flags(pause_job.job_id, pause_requested=True)
        return page(url)

    paused.fetch = pause_fetch
    paused_result = paused.run_next()
    assert paused_result is not None
    assert paused_result.state is JobState.PAUSED

    cancelled = Pipeline(
        data_dir=tmp_data / "cancel",
        runtime=ProviderRuntime(http_get=lambda url: (200, {}, png_bytes)),
    )
    cancel_job = cancelled.submit("https://example.com/gallery", wait=False)

    def cancel_fetch(url: str) -> tuple[int, str, bytes]:
        cancelled.queue.set_job_flags(cancel_job.job_id, cancel_requested=True)
        return page(url)

    cancelled.fetch = cancel_fetch
    cancelled_result = cancelled.run_next()
    assert cancelled_result is not None
    assert cancelled_result.state is JobState.CANCELLED


def test_manifest_candidates_skip_when_denied(
    tmp_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit("https://example.com/watch", wait=False, html="<html></html>")
    pipeline.client_profile = get_profile("personal-restricted")
    assert pipeline._manifest_candidates(job, staging=None) == []

    pipeline.client_profile = get_profile("personal-full")

    def deny(_capability_id: str) -> None:
        raise CapabilityDenied("discover.manifest denied")

    monkeypatch.setattr(pipeline, "_authorize", deny)
    assert pipeline._manifest_candidates(job, staging=None) == []
