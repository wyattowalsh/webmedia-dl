"""Remaining Linux-provable fail-closed gates for fetch, providers, queue, and CLI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from typer.testing import CliRunner

from webmedia_dl.acquisition import preferred_format_id
from webmedia_dl.artifacts import ArtifactStore
from webmedia_dl.cli import app, main
from webmedia_dl.discovery import discover
from webmedia_dl.domain.enums import ArtifactRole, EventType, JobState, MediaKind, Surface
from webmedia_dl.domain.models import FormatAlternative, MediaCandidate, ProviderManifest
from webmedia_dl.errors import (
    ArtifactImmutabilityError,
    CancelledError,
    CookiePolicyError,
    DiscoveryError,
    DrmRefused,
    NetworkPolicyError,
    PauseRequested,
    ProviderPolicyError,
    PublicationError,
)
from webmedia_dl.fetch import bound_fetch
from webmedia_dl.intake import normalize_source
from webmedia_dl.live import _period_parts, record_clear_stream
from webmedia_dl.packaging import extension_root, write_extension_zips
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import get_profile
from webmedia_dl.providers import (
    ProviderRequest,
    ProviderRuntime,
    _cookie_argv_flags,
    _ffmpeg_argv,
    _http_suffix,
)
from webmedia_dl.security import resolve_cookie_path
from webmedia_dl.service import create_app, load_or_create_token

runner = CliRunner()


def test_bound_fetch_stream_completes_within_limit() -> None:
    profile = get_profile("personal-full")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"abcd", headers={"content-type": "video/mp4"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    status, _content_type, body = bound_fetch(
        "https://cdn.example.com/a.mp4",
        profile=profile,
        max_bytes=8,
        client=client,
        should_stop=lambda: None,
    )
    assert status == 200
    assert body == b"abcd"


def test_bound_fetch_redirect_bound_fails_closed() -> None:
    profile = get_profile("personal-full").model_copy(update={"max_redirects": 1})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": str(request.url)})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    with pytest.raises(NetworkPolicyError, match="Redirect bound"):
        bound_fetch(
            "https://example.com/loop",
            profile=profile,
            max_bytes=32,
            client=client,
        )


def test_bound_fetch_closes_owned_client(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = get_profile("personal-full")
    created: list[httpx.Client] = []
    real_client = httpx.Client

    def factory(**kwargs: Any) -> httpx.Client:
        kwargs["transport"] = httpx.MockTransport(
            lambda request: httpx.Response(200, content=b"ok")
        )
        client = real_client(**kwargs)
        created.append(client)
        return client

    monkeypatch.setattr("webmedia_dl.fetch.httpx.Client", factory)
    status, _content_type, body = bound_fetch(
        "https://example.com/x",
        profile=profile,
        max_bytes=16,
    )
    assert status == 200
    assert body == b"ok"
    assert created
    assert created[0].is_closed


def test_drop_publish_error_exits_with_job_error(
    tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise PublicationError("destination refused")

    monkeypatch.setattr("webmedia_dl.pipeline.publish_artifacts", boom)
    result = runner.invoke(app, ["drop", str(media), "--data-dir", str(tmp_path / "data")])
    assert result.exit_code == 1
    body = json.loads(result.stdout)
    assert "refused" in body["job"]["error"]


def test_cli_main_invokes_app(monkeypatch: pytest.MonkeyPatch) -> None:
    from webmedia_dl import cli as cli_mod

    called = {"n": 0}

    def fake() -> None:
        called["n"] += 1

    monkeypatch.setattr(cli_mod, "app", fake)
    main()
    assert called["n"] == 1


def test_provider_builders_fail_closed(tmp_path: Path) -> None:
    runtime = ProviderRuntime(which=lambda _name: None)
    with pytest.raises(ProviderPolicyError, match="not installed"):
        runtime.execute(
            ProviderRequest(
                provider_id="ytdlp",
                capability_id="acquire.ytdlp",
                typed_inputs={"url": "https://example.com/v", "output": str(tmp_path / "o")},
            ),
            tmp_path,
        )
    present = ProviderRuntime(which=lambda name: f"/usr/bin/{name}")
    with pytest.raises(ProviderPolicyError, match="url"):
        present.execute(
            ProviderRequest(
                provider_id="http-direct",
                capability_id="acquire.http",
                typed_inputs={},
            ),
            tmp_path,
        )
    with pytest.raises(ProviderPolicyError, match="url"):
        present.execute(
            ProviderRequest(
                provider_id="ytdlp",
                capability_id="discover.manifest",
                typed_inputs={},
            ),
            tmp_path,
        )
    with pytest.raises(ProviderPolicyError, match="output"):
        present.execute(
            ProviderRequest(
                provider_id="ytdlp",
                capability_id="acquire.ytdlp",
                typed_inputs={"url": "https://example.com/v"},
            ),
            tmp_path,
        )
    with pytest.raises(ProviderPolicyError, match="url"):
        present.execute(
            ProviderRequest(
                provider_id="gallery-dl",
                capability_id="acquire.gallery_dl",
                typed_inputs={},
            ),
            tmp_path,
        )
    with pytest.raises(ProviderPolicyError, match="input"):
        present.execute(
            ProviderRequest(
                provider_id="ffmpeg",
                capability_id="process.ffmpeg.remux",
                typed_inputs={"output": str(tmp_path / "a.mkv")},
            ),
            tmp_path,
        )
    with pytest.raises(ProviderPolicyError, match="input"):
        present.execute(
            ProviderRequest(
                provider_id="imagemagick",
                capability_id="process.imagemagick.convert",
                typed_inputs={"output": str(tmp_path / "b.png")},
            ),
            tmp_path,
        )
    with pytest.raises(ProviderPolicyError, match="Unsupported"):
        _ffmpeg_argv("/usr/bin/ffmpeg", {"input": "a", "output": "b"}, "process.ffmpeg.loop")
    with pytest.raises(CookiePolicyError, match="unavailable"):
        _cookie_argv_flags({"cookie_grant_id": "g1"}, job_id=None, ledger=None, profile_id=None)
    manifest = present._manifests["http-direct"]
    with pytest.raises(ProviderPolicyError, match="no binary"):
        present._build_argv(
            manifest,
            ProviderRequest(
                provider_id="http-direct",
                capability_id="acquire.http",
                typed_inputs={"url": "https://cdn.example.com/a.mp4"},
            ),
            tmp_path,
        )
    fake = ProviderManifest(
        provider_id="curl",
        display_name="curl",
        binary_name="curl",
        capabilities=["acquire.http"],
        license="MIT",
        source_url="https://example.com",
    )
    with pytest.raises(ProviderPolicyError, match="No argv builder"):
        present._build_argv(
            fake,
            ProviderRequest(
                provider_id="curl",
                capability_id="acquire.http",
                typed_inputs={"url": "https://cdn.example.com/a.mp4"},
            ),
            tmp_path,
        )


def test_http_suffix_jpeg_magic_and_fallback() -> None:
    assert _http_suffix("https://cdn.example.com/a.jpeg", {}, b"") == ".jpg"
    assert _http_suffix("https://cdn.example.com/a", {}, b"\xff\xd8xxxx") == ".jpg"
    assert _http_suffix("https://cdn.example.com/a", {}, b"nope") == ".bin"
    assert _http_suffix("https://cdn.example.com/icon.svg", {}, b"") == ".svg"


def test_ytdlp_ext_template_without_created_files(tmp_path: Path) -> None:
    runtime = ProviderRuntime(
        which=lambda name: "/usr/bin/yt-dlp",
        run=lambda _argv, _cwd: (0, b"", b""),
    )
    result = runtime.execute(
        ProviderRequest(
            provider_id="ytdlp",
            capability_id="acquire.ytdlp",
            typed_inputs={
                "url": "https://example.com/v",
                "output": str(tmp_path / "clip.%(ext)s"),
            },
        ),
        tmp_path,
    )
    assert result.exit_code == 0
    assert result.output_paths == ()


def test_ffmpeg_ext_template_falls_back_to_created(tmp_path: Path) -> None:
    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        dest = tmp_path / "other.mkv"
        dest.write_bytes(b"x")
        return 0, b"", b""

    runtime = ProviderRuntime(which=lambda name: "/usr/bin/ffmpeg", run=run)
    result = runtime.execute(
        ProviderRequest(
            provider_id="ffmpeg",
            capability_id="process.ffmpeg.remux",
            typed_inputs={
                "input": str(tmp_path / "a.mp4"),
                "output": str(tmp_path / "clip.%(ext)s"),
            },
        ),
        tmp_path,
    )
    assert result.output_path is not None
    assert result.output_path.name == "other.mkv"


def test_pipeline_cookie_unresolved_and_control_states(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    monkeypatch.setattr("webmedia_dl.pipeline.resolve_cookie_path", lambda *_a, **_k: None)
    pipeline = Pipeline(data_dir=tmp_data)
    failed = pipeline.submit(str(media), cookies=str(cookies))
    assert failed.state is JobState.FAILED
    assert failed.error is not None
    assert "could not be resolved" in failed.error

    other = Pipeline(data_dir=tmp_data / "ok")
    completed = other.submit(str(media))
    assert completed.state is JobState.COMPLETED
    with pytest.raises(PauseRequested, match="cannot be paused"):
        other.pause_job(completed.job_id)
    with pytest.raises(PauseRequested, match="cannot be resumed"):
        other.resume_job(completed.job_id)

    empty = Pipeline(data_dir=tmp_data / "empty")
    none = empty.submit("https://example.com/none", html="<html><body>no media</body></html>")
    assert none.state is JobState.FAILED
    assert none.error is not None


def test_pipeline_ytdlp_produces_no_source_files(tmp_data: Path) -> None:
    html = '<html><body><video src="https://example.com/watch?v=1"></video></body></html>'
    runtime = ProviderRuntime(
        which=lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None,
        run=lambda _argv, _cwd: (0, b"", b""),
    )
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit("https://example.com/watch", html=html)
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "produced no source files" in job.error


def test_pipeline_ytdlp_nonzero_exit_quarantines_partial_output(tmp_data: Path) -> None:
    html = '<html><body><video src="https://example.com/watch?v=1"></video></body></html>'

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        for index, token in enumerate(argv):
            if token == "--output" and index + 1 < len(argv):
                target = Path(argv[index + 1])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"partial-ytdlp")
                return 1, b"", b"unavailable"
        return 1, b"", b"unavailable"

    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(
            which=lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None,
            run=run,
        ),
    )
    job = pipeline.submit("https://example.com/watch", html=html)
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "exited 1" in job.error
    roles = {item.role for item in pipeline.store.list_artifacts()}
    assert ArtifactRole.QUARANTINE in roles
    assert ArtifactRole.SOURCE not in roles
    types = [event.type for event in pipeline.queue.events_for(job.job_id)]
    assert EventType.ACQUISITION_QUARANTINE in types
    assert EventType.JOB_FAILED in types


def test_pipeline_ytdlp_nonzero_exit_without_partial_output(tmp_data: Path) -> None:
    html = '<html><body><video src="https://example.com/watch?v=1"></video></body></html>'
    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(
            which=lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None,
            run=lambda _argv, _cwd: (1, b"", b"unavailable"),
        ),
    )
    job = pipeline.submit("https://example.com/watch", html=html)
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "exited 1" in job.error
    roles = {item.role for item in pipeline.store.list_artifacts()}
    assert ArtifactRole.QUARANTINE not in roles
    assert ArtifactRole.SOURCE not in roles
    types = [event.type for event in pipeline.queue.events_for(job.job_id)]
    assert EventType.ACQUISITION_QUARANTINE not in types
    assert EventType.JOB_FAILED in types


def test_queue_pause_claim_and_cancel_intercept(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = tmp_path / "held.png"
    media.write_bytes(png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    pipeline.pause_queue()
    assert pipeline.queue.next_runnable() is None
    assert pipeline.queue.claim_next() is None
    pipeline.resume_queue()
    pipeline.queue.set_job_flags(job.job_id, cancel_requested=True)
    with pytest.raises(CancelledError, match="cancelled"):
        pipeline.queue.set_state(job.job_id, JobState.DISCOVERING)

    with pipeline.queue.engine.begin() as conn:
        conn.execute(
            text("UPDATE job_context SET checkpoint_json = :payload WHERE job_id = :job_id"),
            {"payload": '["not-a-dict"]', "job_id": str(job.job_id)},
        )
    assert pipeline.queue.get_context(job.job_id).checkpoint == {}


def test_service_pairing_and_companion_fail_closed(tmp_path: Path) -> None:
    app_api = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app_api)
    denied = client.get(
        "/v1/jobs",
        headers={"X-WebMedia-Pairing": "not-a-uuid", "X-WebMedia-Session": "x"},
    )
    assert denied.status_code == 401
    mac = {"Authorization": f"Bearer {token}"}
    missing_kind = client.post(
        "/v1/companion",
        json={"nativeCommand": None, "subprocessWorker": False},
        headers=mac,
    )
    assert missing_kind.status_code == 400
    created = client.post("/v1/pair", headers=mac)
    pairing_id = created.json()["pairing_id"]
    confirmed = client.post("/v1/pair/confirm", headers=mac, json={"pairing_id": pairing_id})
    session_key = confirmed.json()["session_key"]
    paired = client.post(
        "/v1/companion",
        json={"kind": "status", "nativeCommand": None, "subprocessWorker": False},
        headers={
            "X-WebMedia-Pairing": pairing_id,
            "X-WebMedia-Session": session_key,
        },
    )
    assert paired.status_code == 403


def test_local_unknown_kind_and_fetched_html_cap(tmp_path: Path) -> None:
    notes = tmp_path / "notes.txt"
    notes.write_text("hello", encoding="utf-8")
    source = normalize_source(
        str(notes),
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )
    found = discover(source, get_profile("personal-full"))
    assert found[0].media_kind is MediaKind.UNKNOWN
    profile = get_profile("personal-full").model_copy(update={"max_html_bytes": 40})
    page = normalize_source(
        "https://example.com/page",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )

    def fetch(_url: str) -> tuple[int, str, bytes]:
        blob = ("x" * 80) + "<img src='https://cdn.example.com/too-late.png'>"
        return 200, "text/html", blob.encode()

    capped = discover(page, profile, fetch=fetch)
    urls = [item.retrieval_urls[0] for item in capped if item.retrieval_urls]
    assert not any("too-late.png" in item for item in urls)


def test_record_clear_stream_encrypted_empty_parts(tmp_path: Path) -> None:
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        raise AssertionError(url)

    with pytest.raises(DrmRefused, match="AES-128"):
        record_clear_stream(
            '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key"\nseg.ts\n',
            "https://cdn.example.com/live.m3u8",
            tmp_path / "x.ts",
            fetch,
            parts=[],
        )
    assert fetched == []


def test_period_parts_audio_only() -> None:
    body = """
    <AdaptationSet contentType="audio">
      <SegmentTemplate media="a.m4s" startNumber="1"/>
      <Representation id="a1" bandwidth="128000" mimeType="audio/mp4"/>
    </AdaptationSet>
    """
    parts = _period_parts(body, "https://cdn.example.com/")
    assert [part.url for part in parts] == ["https://cdn.example.com/a.m4s"]


def test_audio_only_codec_format_id() -> None:
    candidate = MediaCandidate(
        source_id=uuid4(),
        media_kind=MediaKind.AUDIO,
        identity_key="host:example.com:path:/a",
        retrieval_urls=["https://example.com/a"],
        alternatives=[FormatAlternative(format_id="140", codec="aac")],
    )
    assert preferred_format_id(candidate) == "140"


def test_cookie_html_missing_and_none(tmp_path: Path) -> None:
    profile = get_profile("personal-full")
    assert resolve_cookie_path(profile, None) is None
    missing = tmp_path / "nope.txt"
    with pytest.raises(CookiePolicyError, match="does not exist"):
        resolve_cookie_path(profile, str(missing))
    html = tmp_path / "cookies.txt"
    html.write_text("<!doctype html>", encoding="utf-8")
    with pytest.raises(CookiePolicyError, match="Netscape"):
        resolve_cookie_path(profile, str(html))


def test_artifact_reregister_and_immutable_mutate(tmp_path: Path, png_bytes: bytes) -> None:
    store = ArtifactStore(tmp_path / "store")
    path = tmp_path / "a.png"
    path.write_bytes(png_bytes)
    first = store.register(
        path,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.IMAGE,
        provenance={"job": "1"},
    )
    second = store.register(
        path,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.IMAGE,
        provenance={"job": "2"},
    )
    assert first.artifact_id == second.artifact_id
    assert second.provenance.get("occurrences")
    with pytest.raises(ArtifactImmutabilityError):
        store.mutate_source(first.artifact_id, b"nope")
    with pytest.raises(KeyError):
        store.lineage("sha256:missing")


def test_extension_root_falls_back_and_missing_browser(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    empty = tmp_path / "runtime"
    (empty / "extensions").mkdir(parents=True)
    monkeypatch.setattr("webmedia_dl.packaging.runtime_root", lambda: empty)
    from webmedia_dl.paths import repo_root

    assert extension_root() == repo_root() / "extensions"
    monkeypatch.setattr("webmedia_dl.packaging.runtime_root", lambda: tmp_path / "missing")
    monkeypatch.setattr("webmedia_dl.packaging.repo_root", lambda: tmp_path / "repo")
    (tmp_path / "repo" / "extensions" / "chrome").mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="missing"):
        write_extension_zips(dest_root=tmp_path / "zips")


def test_discovery_fetch_http_error_raises() -> None:
    source = normalize_source(
        "https://example.com/page",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )
    with pytest.raises(DiscoveryError, match="HTTP 503"):
        discover(
            source,
            get_profile("personal-full"),
            fetch=lambda _url: (503, "text/html", b"no"),
        )
