import json
from pathlib import Path

import pytest

from webmedia_dl.discovery import candidates_from_manifest_json, discover
from webmedia_dl.domain.enums import IntakeKind, JobState, Surface
from webmedia_dl.domain.models import MediaSource
from webmedia_dl.errors import CookiePolicyError
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import get_profile
from webmedia_dl.providers import ProviderRequest, ProviderRuntime
from webmedia_dl.security import resolve_cookie_path


def test_nested_jsonld_video_object() -> None:
    html = """
    <script type="application/ld+json">
      {"@graph": [{"@type": "VideoObject", "contentUrl": "https://cdn.example.com/nested.mp4"}]}
    </script>
    """
    source = MediaSource(
        kind=IntakeKind.URL,
        locator="https://example.com/page",
        normalized_url="https://example.com/page",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )
    candidates = discover(source, get_profile("personal-full"), html=html)
    urls = [item.retrieval_urls[0] for item in candidates if item.retrieval_urls]
    assert "https://cdn.example.com/nested.mp4" in urls


def test_manifest_json_builds_alternatives() -> None:
    source = MediaSource(
        kind=IntakeKind.URL,
        locator="https://example.com/watch",
        normalized_url="https://example.com/watch",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )
    raw = b"""{"id":"abc","title":"Clip","webpage_url":"https://example.com/watch",
        "formats":[{"format_id":"137","ext":"mp4","height":1080,"tbr":2500}]}"""
    found = candidates_from_manifest_json(source, raw)
    assert found
    assert found[0].alternatives
    assert found[0].alternatives[0].format_id == "137"
    assert found[0].title_display == "Clip"
    assert found[0].identity_key != "Clip"


def test_dump_json_argv(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        captured.append(argv)
        return 0, b'{"id":"1","webpage_url":"https://example.com/v","formats":[]}', b""

    runtime = ProviderRuntime(which=lambda name: "/usr/bin/yt-dlp", run=run)
    result = runtime.execute(
        ProviderRequest(
            provider_id="ytdlp",
            capability_id="discover.manifest",
            typed_inputs={"url": "https://example.com/v"},
        ),
        tmp_path,
    )
    assert result.exit_code == 0
    assert "--dump-json" in captured[0]
    assert "--output" not in captured[0]
    assert "--exec" not in captured[0]


def test_queue_pause_leaves_job_accepted(tmp_data: Path, png_bytes: bytes) -> None:
    pipeline = Pipeline(data_dir=tmp_data)
    pipeline.pause_queue()
    media = tmp_data / "held.png"
    media.write_bytes(png_bytes)
    job = pipeline.submit(str(media))
    assert job.state is JobState.ACCEPTED
    pipeline.resume_queue()
    ran = pipeline.run_next()
    assert ran is not None
    assert ran.state is JobState.COMPLETED


def test_html_cookie_file_rejected(tmp_path: Path) -> None:
    cookies = tmp_path / "cookies.html"
    cookies.write_text("<html>not cookies</html>", encoding="utf-8")
    profile = get_profile("personal-full")
    with pytest.raises(CookiePolicyError):
        resolve_cookie_path(profile, str(cookies), repo_root=tmp_path / "repo")


def test_paused_job_is_not_auto_started(tmp_data: Path, png_bytes: bytes) -> None:
    pipeline = Pipeline(data_dir=tmp_data)
    media = tmp_data / "held.png"
    media.write_bytes(png_bytes)
    job = pipeline.submit(str(media), wait=False)
    paused = pipeline.pause_job(job.job_id)
    assert paused.state is JobState.PAUSED
    assert pipeline.run_next() is None
    resumed = pipeline.resume_job(job.job_id)
    assert resumed.state is JobState.COMPLETED


def test_wait_false_preserves_html_for_run_next(tmp_data: Path, ytdlp_run_ok) -> None:
    runtime = ProviderRuntime(
        which=lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None,
        run=ytdlp_run_ok,
        http_get=lambda url: (404, {}, b""),
    )
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit(
        "https://example.com/watch",
        html="<html><title>Video</title></html>",
        wait=False,
    )
    assert job.state is JobState.ACCEPTED
    ran = pipeline.run_next()
    assert ran is not None
    assert ran.state is JobState.COMPLETED


def test_cli_run_next_empty(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from webmedia_dl.cli import app

    result = CliRunner().invoke(app, ["run-next", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["job"] is None


def test_cli_submit_no_wait(tmp_path: Path, png_bytes: bytes) -> None:
    from typer.testing import CliRunner

    from webmedia_dl.cli import app

    media = tmp_path / "held.png"
    media.write_bytes(png_bytes)
    result = CliRunner().invoke(
        app,
        ["submit", str(media), "--no-wait", "--data-dir", str(tmp_path / "data")],
    )
    assert result.exit_code == 0
    assert json.loads(result.stdout)["job"]["state"] == "accepted"
    ran = CliRunner().invoke(app, ["run-next", "--data-dir", str(tmp_path / "data")])
    assert ran.exit_code == 0
    assert json.loads(ran.stdout)["job"]["state"] == "completed"


def test_cli_pause_queue(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from webmedia_dl.cli import app

    result = CliRunner().invoke(app, ["pause", "--queue", "--data-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "true" in result.stdout
