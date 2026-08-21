from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from urllib.error import URLError
from uuid import uuid4

import pytest

from webmedia_dl.acquisition import plan_acquisition, preferred_format_id
from webmedia_dl.compat import migrate_legacy, scan_legacy
from webmedia_dl.discovery import candidates_from_manifest_json, discover
from webmedia_dl.domain.enums import ArtifactRole, IntakeKind, JobState, MediaKind, Surface
from webmedia_dl.domain.models import (
    Artifact,
    ExportIntent,
    FormatAlternative,
    MediaCandidate,
    MediaSource,
)
from webmedia_dl.errors import CookiePolicyError, DelegationDenied, NetworkPolicyError
from webmedia_dl.live import record_clear_stream, record_kind_streams, recordable_parts
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import get_profile
from webmedia_dl.processing import execute_export_plan
from webmedia_dl.providers import ProviderRuntime
from webmedia_dl.security import CookieGrantLedger
from webmedia_dl.support import _sanitize
from webmedia_dl.updates import check_updates
from webmedia_dl.validation import validate_artifact


def test_pairing_rejects_full_client_profile(tmp_data: Path) -> None:
    pipeline = Pipeline(data_dir=tmp_data)
    with pytest.raises(DelegationDenied, match="full profile"):
        pipeline.pairing.create("personal-full", pipeline.host_worker.worker_id)


def test_cookie_grants_are_job_and_profile_bound(tmp_path: Path) -> None:
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    ledger = CookieGrantLedger()
    job_a = uuid4()
    job_b = uuid4()
    grant = ledger.issue(job_a, cookies, "personal-full")
    assert (
        ledger.resolve(grant.grant_id, job_id=job_a, profile_id="personal-full")
        == cookies.resolve()
    )
    with pytest.raises(CookiePolicyError, match="single job"):
        ledger.resolve(grant.grant_id, job_id=job_b, profile_id="personal-full")
    with pytest.raises(CookiePolicyError, match="policy profile"):
        ledger.resolve(grant.grant_id, job_id=job_a, profile_id="personal-restricted")
    with pytest.raises(CookiePolicyError, match="forbids cookie"):
        ledger.issue(job_a, cookies, "personal-restricted")


def test_probe_encrypted_stream_refuses_closed(tmp_data: Path, tmp_path: Path, monkeypatch) -> None:
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"not-a-real-mp4")

    class Result:
        returncode = 0
        stdout = json.dumps(
            {
                "streams": [
                    {
                        "index": 0,
                        "codec_type": "video",
                        "codec_name": "h264",
                        "tags": {"ENCRYPTED": "1"},
                    }
                ],
                "format": {"format_name": "mp4"},
            }
        )

    monkeypatch.setattr(
        "webmedia_dl.probe.shutil.which",
        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None,
    )
    monkeypatch.setattr(
        "webmedia_dl.probe.subprocess.run",
        lambda *_args, **_kwargs: Result(),
    )
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media))
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "encrypted" in job.error.lower() or "drm" in job.error.lower()
    assert not any(
        event.type.value == "publication.committed"
        for event in pipeline.queue.events_for(job.job_id)
    )


def test_resume_job_does_not_run_while_queue_paused(tmp_data: Path, png_bytes: bytes) -> None:
    pipeline = Pipeline(data_dir=tmp_data)
    media = tmp_data.parent / "held.png"
    media.write_bytes(png_bytes)
    job = pipeline.submit(str(media), wait=False)
    paused = pipeline.pause_job(job.job_id)
    assert paused.state is JobState.PAUSED
    pipeline.pause_queue()
    resumed = pipeline.resume_job(job.job_id)
    assert resumed.state is JobState.ACCEPTED
    assert not pipeline.store._records


def test_live_byte_bound_is_aggregate(tmp_path: Path) -> None:
    playlist = "#EXTM3U\n#EXTINF:1,\na.ts\n#EXTINF:1,\nb.ts\n"

    def fetch(url: str) -> tuple[int, str, bytes]:
        return 200, "video/MP2T", b"123456"

    output = tmp_path / "live.ts"
    with pytest.raises(NetworkPolicyError):
        record_clear_stream(
            playlist,
            "https://cdn.example.com/live.m3u8",
            output,
            fetch,
            max_bytes=10,
        )
    if output.exists():
        assert output.stat().st_size < 12


def test_hls_and_dash_keep_alternate_audio(tmp_path: Path) -> None:
    master = (
        "#EXTM3U\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",NAME="eng",DEFAULT=YES,URI="audio.m3u8"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=800000,AUDIO="aac"\n'
        "video.m3u8\n"
    )
    video = "#EXTM3U\n#EXTINF:1,\nv.ts\n"
    audio = "#EXTM3U\n#EXTINF:1,\na.ts\n"
    bodies = {
        "https://cdn.example.com/master.m3u8": master.encode(),
        "https://cdn.example.com/video.m3u8": video.encode(),
        "https://cdn.example.com/audio.m3u8": audio.encode(),
        "https://cdn.example.com/v.ts": b"VIDEO",
        "https://cdn.example.com/a.ts": b"AUDIO",
    }

    def fetch(url: str) -> tuple[int, str, bytes]:
        return 200, "application/vnd.apple.mpegurl", bodies[url]

    recorded = record_kind_streams(
        master,
        "https://cdn.example.com/master.m3u8",
        tmp_path / "live.bin",
        fetch,
    )
    kinds = {kind for kind, _path in recorded}
    assert MediaKind.VIDEO in kinds
    assert MediaKind.AUDIO in kinds
    payloads = {kind: path.read_bytes() for kind, path in recorded}
    assert payloads[MediaKind.VIDEO] == b"VIDEO"
    assert payloads[MediaKind.AUDIO] == b"AUDIO"
    assert b"VIDEOAUDIO" not in payloads[MediaKind.VIDEO]
    dash = """
    <MPD><Period>
      <AdaptationSet contentType="audio">
        <SegmentTemplate media="audio/$RepresentationID$.m4s" startNumber="1"/>
        <Representation id="a1" bandwidth="128000" mimeType="audio/mp4"/>
      </AdaptationSet>
      <AdaptationSet contentType="video">
        <SegmentTemplate media="video/$RepresentationID$.m4s" startNumber="1"/>
        <Representation id="v1" bandwidth="800000" mimeType="video/mp4"/>
      </AdaptationSet>
    </Period></MPD>
    """
    dash_bodies = {
        "https://cdn.example.com/video/v1.m4s": b"V",
        "https://cdn.example.com/audio/a1.m4s": b"A",
    }

    def dash_fetch(url: str) -> tuple[int, str, bytes]:
        return 200, "video/mp4", dash_bodies[url]

    dash_recorded = record_kind_streams(
        dash,
        "https://cdn.example.com/manifest.mpd",
        tmp_path / "dash.bin",
        dash_fetch,
    )
    dash_kinds = {kind for kind, _path in dash_recorded}
    assert MediaKind.VIDEO in dash_kinds
    assert MediaKind.AUDIO in dash_kinds


def test_live_watch_page_plans_ytdlp_not_clear_recorder() -> None:
    source = MediaSource(
        kind=IntakeKind.URL,
        locator="https://www.youtube.com/watch?v=abc",
        normalized_url="https://www.youtube.com/watch?v=abc",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )
    live_watch = candidates_from_manifest_json(
        source,
        b'{"id":"abc","webpage_url":"https://www.youtube.com/watch?v=abc","is_live":true}',
    )
    assert live_watch[0].media_kind is MediaKind.VIDEO
    plan = plan_acquisition(uuid4(), live_watch[0], get_profile("personal-full"))
    assert all(item.capability_id != "live.record_clear_manifest" for item in plan.strategies)
    assert any(item.capability_id == "acquire.ytdlp" for item in plan.strategies)
    direct = MediaCandidate(
        source_id=uuid4(),
        media_kind=MediaKind.LIVE_STREAM,
        identity_key="host:cdn.example.com:path:/live.m3u8",
        retrieval_urls=["https://cdn.example.com/live.m3u8"],
    )
    live_plan = plan_acquisition(uuid4(), direct, get_profile("personal-full"))
    assert any(item.capability_id == "live.record_clear_manifest" for item in live_plan.strategies)


def test_multi_period_same_uri_is_appended_twice() -> None:
    text = """
    <MPD>
      <Period>
        <AdaptationSet contentType="video">
          <SegmentTemplate media="clip.m4s" startNumber="1"/>
          <Representation id="v1" bandwidth="800000" mimeType="video/mp4"/>
        </AdaptationSet>
      </Period>
      <Period>
        <AdaptationSet contentType="video">
          <SegmentTemplate media="clip.m4s" startNumber="1"/>
          <Representation id="v1" bandwidth="800000" mimeType="video/mp4"/>
        </AdaptationSet>
      </Period>
    </MPD>
    """
    parts = recordable_parts(text, "https://cdn.example.com/")
    urls = [part.url for part in parts]
    assert urls == [
        "https://cdn.example.com/clip.m4s",
        "https://cdn.example.com/clip.m4s",
    ]
    assert parts[0].occurrence != parts[1].occurrence


def test_preferred_format_pairs_video_and_audio() -> None:
    candidate = MediaCandidate(
        source_id=uuid4(),
        media_kind=MediaKind.VIDEO,
        identity_key="host:example.com:path:/watch",
        retrieval_urls=["https://example.com/watch"],
        alternatives=[
            FormatAlternative(format_id="137", container="mp4", vcodec="avc1", height=1080),
            FormatAlternative(format_id="140", container="m4a", acodec="mp4a", bitrate=128000),
        ],
    )
    assert preferred_format_id(candidate) == "137+140"


def test_remux_success_skips_transcode(tmp_path: Path) -> None:
    from webmedia_dl.artifacts import ArtifactStore
    from webmedia_dl.domain.models import Job
    from webmedia_dl.export import plan_export
    from webmedia_dl.queue import QueueStore

    src = tmp_path / "source.mp4"
    src.write_bytes(b"src")
    store = ArtifactStore(tmp_path / "data")
    source = store.register(
        src, role=ArtifactRole.SOURCE, media_kind=MediaKind.VIDEO, container="mp4"
    )
    queue = QueueStore(tmp_path / "data" / "queue")
    job_id = uuid4()
    queue.put_job(
        Job(
            job_id=job_id,
            source=MediaSource(
                kind=IntakeKind.FILE,
                locator=str(src),
                local_path=str(src),
                surface=Surface.CLI,
                policy_profile_id="personal-full",
            ),
            policy_profile_id="personal-full",
            worker_id="local-macos",
        )
    )
    captured: list[str] = []

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        captured.append(Path(argv[-1]).name)
        Path(argv[-1]).write_bytes(b"ok")
        return 0, b"", b""

    plan = plan_export(
        job_id,
        source,
        ExportIntent(allow_lossy=True, container_preference="mkv"),
    )
    execute_export_plan(
        plan,
        job_id=job_id,
        source=source,
        source_path=src,
        store=store,
        runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
        staging=tmp_path / "staging",
        queue=queue,
        authorize=lambda _cap: None,
    )
    assert any(name.startswith("remux.") for name in captured)
    assert not any(name.startswith("transcode.") for name in captured)


def test_filename_suffix_cannot_pass_container_gate(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "clip.mkv"
    path.write_bytes(b"bytes")
    artifact = Artifact(
        artifact_id="sha256:ab",
        role=ArtifactRole.DERIVATIVE,
        sha256="ab",
        byte_size=5,
        media_kind=MediaKind.VIDEO,
        storage_relpath="clip.mkv",
        container="mkv",
    )

    class Result:
        returncode = 0
        stdout = json.dumps(
            {
                "streams": [{"index": 0, "codec_type": "video"}],
                "format": {"format_name": "mov,mp4,m4a"},
            }
        )

    monkeypatch.setattr(
        "webmedia_dl.probe.shutil.which",
        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None,
    )
    monkeypatch.setattr(
        "webmedia_dl.probe.subprocess.run",
        lambda *_args, **_kwargs: Result(),
    )
    from webmedia_dl.identity import sha256_file

    artifact = artifact.model_copy(update={"sha256": sha256_file(str(path)), "byte_size": 5})
    results = validate_artifact(uuid4(), artifact, path, expected_container="mkv")
    container = next(item for item in results if item.gate_id == "container-match")
    assert container.status.value == "FAIL"


def test_discovery_picture_amp_jsonld_list_and_html_cap() -> None:
    html = """
    <html>
      <body>
        <picture>
          <source type="image/webp" srcset="https://cdn.example.com/hero.webp">
        </picture>
        <amp-video src="https://cdn.example.com/amp.mp4"></amp-video>
        <amp-audio src="https://cdn.example.com/amp.m4a"></amp-audio>
        <script type="application/ld+json">
          {"@type": "VideoObject", "contentUrl": ["https://cdn.example.com/one.mp4", "https://cdn.example.com/two.mp4"]}
        </script>
      </body>
    </html>
    """
    source = MediaSource(
        kind=IntakeKind.URL,
        locator="https://example.com/page",
        normalized_url="https://example.com/page",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )
    profile = get_profile("personal-full")
    candidates = discover(source, profile, html=html)
    urls = [item.retrieval_urls[0] for item in candidates if item.retrieval_urls]
    kinds = {item.retrieval_urls[0]: item.media_kind for item in candidates if item.retrieval_urls}
    assert "https://cdn.example.com/hero.webp" in urls
    assert kinds["https://cdn.example.com/hero.webp"] is MediaKind.IMAGE
    assert kinds["https://cdn.example.com/amp.mp4"] is MediaKind.VIDEO
    assert kinds["https://cdn.example.com/amp.m4a"] is MediaKind.AUDIO
    assert "https://cdn.example.com/one.mp4" in urls
    assert "https://cdn.example.com/two.mp4" in urls
    tiny = profile.model_copy(update={"max_html_bytes": 40})
    capped = discover(
        source,
        tiny,
        html=("x" * 80) + "<img src='https://cdn.example.com/too-late.png'>",
    )
    capped_urls = [item.retrieval_urls[0] for item in capped if item.retrieval_urls]
    assert not any("too-late.png" in item for item in capped_urls)


def test_support_sanitizes_nested_console_and_cookie_paths() -> None:
    cleaned = _sanitize({"debug": {"stdout": "secret", "note": "ok"}, "cookies_file": "/tmp/c.txt"})
    assert "stdout" not in cleaned["debug"]
    assert cleaned["debug"]["note"] == "ok"
    assert "cookies_file" not in cleaned


def test_updates_reports_newer_equal_malformed_and_offline(monkeypatch) -> None:
    class _Resp(BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def newer(_url, timeout=2.5):
        return _Resp(json.dumps({"info": {"version": "9.9.9"}}).encode())

    payload = check_updates(current="0.1.0", opener=newer)
    assert payload["latest"] == "9.9.9"
    assert payload["update_available"] is True
    assert payload["auto_install"] is False

    def same(_url, timeout=2.5):
        return _Resp(json.dumps({"info": {"version": "0.1.0"}}).encode())

    equal = check_updates(current="0.1.0", opener=same)
    assert equal["update_available"] is False
    assert equal["status"] == "PASS"

    def bad(_url, timeout=2.5):
        return _Resp(json.dumps({"info": {"version": "not-a-version"}}).encode())

    malformed = check_updates(current="0.1.0", opener=bad)
    assert malformed["status"] == "WARN"

    def offline(_url, timeout=2.5):
        raise URLError("offline")

    blocked = check_updates(current="0.1.0", opener=offline)
    assert blocked["status"] == "BLOCKED"
    assert blocked["auto_install"] is False


def test_nested_archive_txt_is_indexed(tmp_path: Path) -> None:
    nested = tmp_path / "legacy" / "archive.txt"
    nested.parent.mkdir()
    nested.write_text("id-nested\n", encoding="utf-8")
    report = scan_legacy(tmp_path)
    assert any(
        str(nested) == item or item.endswith("archive.txt") for item in report["extra_archives"]
    )
    applied = migrate_legacy(tmp_path, apply=True)
    assert nested.read_text(encoding="utf-8") == "id-nested\n"
    assert applied["index_entries"] >= 1
