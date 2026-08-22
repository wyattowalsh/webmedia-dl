from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from types import TracebackType
from urllib.error import URLError
from uuid import uuid4

import pytest

from webmedia_dl.acquisition import plan_acquisition, preferred_format_id
from webmedia_dl.compat import migrate_legacy, scan_legacy
from webmedia_dl.discovery import candidates_from_manifest_json, discover
from webmedia_dl.domain.enums import (
    ArtifactRole,
    DestinationKind,
    EvidenceStatus,
    IntakeKind,
    JobState,
    MediaKind,
    Surface,
)
from webmedia_dl.domain.models import (
    Artifact,
    ExportIntent,
    FormatAlternative,
    MediaCandidate,
    MediaSource,
    path_is_under,
)
from webmedia_dl.errors import (
    CookiePolicyError,
    DelegationDenied,
    NetworkPolicyError,
    ValidationFailed,
)
from webmedia_dl.identity import sha256_file
from webmedia_dl.live import record_clear_stream, record_kind_streams, recordable_parts
from webmedia_dl.paths import repo_root
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import get_profile
from webmedia_dl.processing import execute_export_plan
from webmedia_dl.providers import ProviderRuntime
from webmedia_dl.publish import publish_artifacts
from webmedia_dl.security import CookieGrantLedger
from webmedia_dl.support import _sanitize
from webmedia_dl.updates import check_updates
from webmedia_dl.validation import record_result, validate_artifact


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
    with pytest.raises(CookiePolicyError, match="single job"):
        ledger.resolve(grant.grant_id, job_id="not-a-uuid", profile_id="personal-full")
    with pytest.raises(CookiePolicyError, match="policy profile"):
        ledger.resolve(grant.grant_id, job_id=job_a, profile_id="personal-restricted")
    with pytest.raises(CookiePolicyError, match="forbids cookie"):
        ledger.issue(job_a, cookies, "personal-restricted")


def test_cookie_grant_rejects_html_replacement(tmp_path: Path) -> None:
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    ledger = CookieGrantLedger()
    job_id = uuid4()
    grant = ledger.issue(job_id, cookies, "personal-full")
    cookies.write_text("<html>not cookies</html>", encoding="utf-8")
    with pytest.raises(CookiePolicyError, match="HTML"):
        ledger.resolve(grant.grant_id, job_id=job_id, profile_id="personal-full")


def test_cookie_grant_rejects_missing_file(tmp_path: Path) -> None:
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    ledger = CookieGrantLedger()
    job_id = uuid4()
    grant = ledger.issue(job_id, cookies, "personal-full")
    cookies.unlink()
    with pytest.raises(CookiePolicyError, match="does not exist"):
        ledger.resolve(grant.grant_id, job_id=job_id, profile_id="personal-full")


def test_cookie_grant_resolve_when_repo_root_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    ledger = CookieGrantLedger()
    job_id = uuid4()
    grant = ledger.issue(job_id, cookies, "personal-full")

    def missing() -> Path:
        raise FileNotFoundError("no checkout")

    monkeypatch.setattr("webmedia_dl.paths.repo_root", missing)
    assert (
        ledger.resolve(grant.grant_id, job_id=job_id, profile_id="personal-full")
        == cookies.resolve()
    )


def test_cookie_grant_rejects_unresolved_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    ledger = CookieGrantLedger()
    job_id = uuid4()
    grant = ledger.issue(job_id, cookies, "personal-full")
    monkeypatch.setattr("webmedia_dl.security.resolve_cookie_path", lambda *_a, **_k: None)
    with pytest.raises(CookiePolicyError, match="absolute"):
        ledger.resolve(grant.grant_id, job_id=job_id, profile_id="personal-full")


def test_cookie_grant_rejects_path_change(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    other = tmp_path / "elsewhere.txt"
    other.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    ledger = CookieGrantLedger()
    job_id = uuid4()
    grant = ledger.issue(job_id, cookies, "personal-full")
    monkeypatch.setattr(
        "webmedia_dl.security.resolve_cookie_path",
        lambda *_a, **_k: other.resolve(),
    )
    with pytest.raises(CookiePolicyError, match="path changed"):
        ledger.resolve(grant.grant_id, job_id=job_id, profile_id="personal-full")


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
    comment_first = (
        "#EXTM3U\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",NAME="commentary",URI="comment.m3u8"\n'
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",NAME="eng",DEFAULT=YES,URI="audio.m3u8"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=800000,AUDIO="aac"\n'
        "video.m3u8\n"
    )

    def fetch_default(url: str) -> tuple[int, str, bytes]:
        if url.endswith("comment.m3u8"):
            raise AssertionError(url)
        return 200, "application/vnd.apple.mpegurl", bodies[url]

    defaulted = record_kind_streams(
        comment_first,
        "https://cdn.example.com/master.m3u8",
        tmp_path / "default.bin",
        fetch_default,
    )
    default_payloads = {kind: path.read_bytes() for kind, path in defaulted}
    assert default_payloads[MediaKind.AUDIO] == b"AUDIO"
    autoselect_first = (
        "#EXTM3U\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",NAME="commentary",URI="comment.m3u8"\n'
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",NAME="eng",AUTOSELECT=YES,URI="audio.m3u8"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=800000,AUDIO="aac"\n'
        "video.m3u8\n"
    )
    autoselected = record_kind_streams(
        autoselect_first,
        "https://cdn.example.com/master.m3u8",
        tmp_path / "autoselect.bin",
        fetch_default,
    )
    autoselect_payloads = {kind: path.read_bytes() for kind, path in autoselected}
    assert autoselect_payloads[MediaKind.AUDIO] == b"AUDIO"
    sub_master = (
        "#EXTM3U\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",NAME="eng",DEFAULT=YES,URI="audio.m3u8"\n'
        '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="commentary",URI="comment.vtt"\n'
        '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="eng",DEFAULT=YES,URI="eng.vtt"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=800000,AUDIO="aac",SUBTITLES="subs"\n'
        "video.m3u8\n"
    )
    captions = b"WEBVTT\n\nHi\n"
    sub_bodies = {
        **bodies,
        "https://cdn.example.com/eng.vtt": b"#EXTM3U\n#EXTINF:1,\neng1.vtt\n",
        "https://cdn.example.com/eng1.vtt": captions,
    }

    def fetch_subs(url: str) -> tuple[int, str, bytes]:
        if url.endswith("comment.vtt"):
            raise AssertionError(url)
        return 200, "application/vnd.apple.mpegurl", sub_bodies[url]

    subtitled = record_kind_streams(
        sub_master,
        "https://cdn.example.com/master.m3u8",
        tmp_path / "subs.bin",
        fetch_subs,
    )
    sub_payloads = {kind: path.read_bytes() for kind, path in subtitled}
    assert sub_payloads[MediaKind.VIDEO] == b"VIDEO"
    assert sub_payloads[MediaKind.AUDIO] == b"AUDIO"
    assert sub_payloads[MediaKind.SUBTITLE] == captions
    only_subs = (
        "#EXTM3U\n"
        '#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",URI="eng.vtt"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=800000,SUBTITLES="subs"\n'
        "video.m3u8\n"
    )
    only = record_kind_streams(
        only_subs,
        "https://cdn.example.com/master.m3u8",
        tmp_path / "only-subs.bin",
        fetch_subs,
    )
    only_kinds = {kind for kind, _path in only}
    assert MediaKind.LIVE_STREAM in only_kinds
    assert MediaKind.SUBTITLE in only_kinds
    assert MediaKind.VIDEO not in only_kinds
    assert MediaKind.AUDIO not in only_kinds
    muxed_audio = (
        "#EXTM3U\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",NAME="eng",DEFAULT=YES,AUTOSELECT=YES\n'
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",NAME="commentary",URI="comment.m3u8"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=800000,AUDIO="aac"\n'
        "video.m3u8\n"
    )

    def fetch_muxed(url: str) -> tuple[int, str, bytes]:
        if url.endswith("comment.m3u8"):
            raise AssertionError(url)
        return 200, "application/vnd.apple.mpegurl", bodies[url]

    muxed = record_kind_streams(
        muxed_audio,
        "https://cdn.example.com/master.m3u8",
        tmp_path / "muxed.bin",
        fetch_muxed,
    )
    assert muxed == [(MediaKind.LIVE_STREAM, tmp_path / "muxed.bin")]
    assert (tmp_path / "muxed.bin").read_bytes() == b"VIDEO"
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
    for token in ("m3u8", "m3u", "mpd"):
        listed = candidates_from_manifest_json(
            source,
            json.dumps({"url": "https://cdn.example.com/plain-live", "ext": token}).encode(),
        )
        assert listed[0].media_kind is MediaKind.LIVE_STREAM
        listed_plan = plan_acquisition(uuid4(), listed[0], get_profile("personal-full"))
        assert any(
            item.capability_id == "live.record_clear_manifest" for item in listed_plan.strategies
        )
        assert all(item.capability_id != "acquire.ytdlp" for item in listed_plan.strategies)
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
    extensionless = MediaCandidate(
        source_id=uuid4(),
        media_kind=MediaKind.LIVE_STREAM,
        identity_key="host:cdn.example.com:path:/plain-live",
        retrieval_urls=["https://cdn.example.com/plain-live"],
    )
    extensionless_plan = plan_acquisition(uuid4(), extensionless, get_profile("personal-full"))
    assert any(
        item.capability_id == "live.record_clear_manifest" for item in extensionless_plan.strategies
    )
    assert all(item.strategy_id != "http-direct" for item in extensionless_plan.strategies)
    assert all(item.capability_id != "acquire.http" for item in extensionless_plan.strategies)
    assert all(item.capability_id != "acquire.ytdlp" for item in extensionless_plan.strategies)
    restricted = get_profile("personal-restricted")
    assert plan_acquisition(uuid4(), direct, restricted).strategies == []
    assert plan_acquisition(uuid4(), extensionless, restricted).strategies == []
    gallery = MediaCandidate(
        source_id=uuid4(),
        media_kind=MediaKind.GALLERY,
        identity_key="host:example.com:path:/album",
        retrieval_urls=["https://example.com/album"],
    )
    assert plan_acquisition(uuid4(), gallery, restricted).strategies == []
    browser = get_profile("browser-capture")
    http = MediaCandidate(
        source_id=uuid4(),
        media_kind=MediaKind.VIDEO,
        identity_key="host:cdn.example.com:path:/a.mp4",
        retrieval_urls=["https://cdn.example.com/a.mp4"],
    )
    assert all(
        item.strategy_id != "http-direct"
        for item in plan_acquisition(uuid4(), http, browser).strategies
    )


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
    muxed = MediaCandidate(
        source_id=uuid4(),
        media_kind=MediaKind.VIDEO,
        identity_key="host:example.com:path:/watch",
        retrieval_urls=["https://example.com/watch"],
        alternatives=[
            FormatAlternative(
                format_id="18",
                container="mp4",
                vcodec="avc1",
                acodec="mp4a",
                height=360,
                bitrate=500_000,
            ),
            FormatAlternative(
                format_id="22",
                container="mp4",
                vcodec="avc1",
                acodec="mp4a",
                height=720,
                bitrate=2_000_000,
            ),
        ],
    )
    assert preferred_format_id(muxed) == "22"
    same = MediaCandidate(
        source_id=uuid4(),
        media_kind=MediaKind.VIDEO,
        identity_key="host:example.com:path:/watch",
        retrieval_urls=["https://example.com/watch"],
        alternatives=[
            FormatAlternative(format_id="best", container="mp4", vcodec="avc1", height=720),
            FormatAlternative(format_id="best", container="m4a", acodec="mp4a", bitrate=128000),
        ],
    )
    assert preferred_format_id(same) == "best"
    gallery = MediaCandidate(
        source_id=uuid4(),
        media_kind=MediaKind.GALLERY,
        identity_key="host:example.com:path:/album",
        retrieval_urls=["https://example.com/album"],
        alternatives=[FormatAlternative(format_id="1", container="jpg", height=1200)],
    )
    planned = plan_acquisition(uuid4(), gallery, get_profile("personal-full"), cookies="grant-1")
    ytdlp = next(item for item in planned.strategies if item.strategy_id == "ytdlp")
    assert ytdlp.typed_inputs["format_id"] == "1"
    assert ytdlp.typed_inputs["cookie_grant_id"] == "grant-1"


def test_remux_success_skips_transcode(tmp_path: Path, pass_container_probe) -> None:
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
    class _Resp:
        def __init__(self, payload: bytes) -> None:
            self._buf = BytesIO(payload)

        def read(self) -> bytes:
            return self._buf.read()

        def __enter__(self) -> _Resp:
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc_val: BaseException | None,
            exc_tb: TracebackType | None,
        ) -> bool:
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


def test_cookie_grants_persist_across_pipeline_instances(
    tmp_data: Path, tmp_path: Path, ytdlp_run_ok
) -> None:
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    captured: list[list[str]] = []

    def run(argv: list[str], cwd: Path) -> tuple[int, bytes, bytes]:
        captured.append(list(argv))
        return ytdlp_run_ok(argv, cwd)

    def runtime() -> ProviderRuntime:
        return ProviderRuntime(
            which=lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None,
            run=run,
            http_get=lambda _url: (404, {}, b""),
        )

    first = Pipeline(data_dir=tmp_data, runtime=runtime())
    job = first.submit(
        "https://example.com/watch",
        html="<html><title>Video</title></html>",
        cookies=str(cookies),
        wait=False,
    )
    assert job.state is JobState.ACCEPTED
    assert (tmp_data / "cookie-grants.json").is_file()
    attached = next(
        event
        for event in first.queue.events_for(job.job_id)
        if event.type.value == "cookie.attached"
    )
    assert attached.payload["cookies_path_basename"] == cookies.name
    assert "cookies_path" not in attached.payload
    for event in first.queue.events_for(job.job_id):
        dumped = json.dumps(event.model_dump(mode="json"))
        assert str(cookies.resolve()) not in dumped

    second = Pipeline(data_dir=tmp_data, runtime=runtime())
    ran = second.run_next()
    assert ran is not None
    assert ran.state is JobState.COMPLETED
    cookie_argv = [argv for argv in captured if "--cookies" in argv]
    assert cookie_argv
    resolved = str(cookies.resolve())
    assert any(resolved in argv for argv in cookie_argv)
    dump_json = [argv for argv in captured if "--dump-json" in argv]
    assert dump_json
    assert "--cookies" in dump_json[0]


def test_cookie_grant_ledger_reloads_and_rechecks_file(tmp_path: Path) -> None:
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    store = tmp_path / "data" / "cookie-grants.json"
    job_id = uuid4()
    first = CookieGrantLedger(store)
    grant = first.issue(job_id, cookies, "personal-full")
    second = CookieGrantLedger(store)
    assert (
        second.resolve(grant.grant_id, job_id=job_id, profile_id="personal-full")
        == cookies.resolve()
    )
    cookies.unlink()
    with pytest.raises(CookiePolicyError, match="does not exist"):
        second.resolve(grant.grant_id, job_id=job_id, profile_id="personal-full")
    store.write_text("{not-json", encoding="utf-8")
    recovered = CookieGrantLedger(store)
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    later = recovered.issue(uuid4(), cookies, "personal-full")
    assert (
        CookieGrantLedger(store).resolve(
            later.grant_id, job_id=later.job_id, profile_id="personal-full"
        )
        == cookies.resolve()
    )


def test_publish_skips_failed_sibling(tmp_path: Path) -> None:
    good = tmp_path / "good.bin"
    bad = tmp_path / "bad.bin"
    good.write_bytes(b"good-bytes")
    bad.write_bytes(b"bad-bytes")
    good_digest = sha256_file(str(good))
    bad_digest = sha256_file(str(bad))
    good_artifact = Artifact(
        artifact_id=f"sha256:{good_digest}",
        role=ArtifactRole.SOURCE,
        sha256=good_digest,
        byte_size=good.stat().st_size,
        media_kind=MediaKind.IMAGE,
        storage_relpath="good.bin",
    )
    bad_artifact = Artifact(
        artifact_id=f"sha256:{bad_digest}",
        role=ArtifactRole.SOURCE,
        sha256=bad_digest,
        byte_size=bad.stat().st_size,
        media_kind=MediaKind.IMAGE,
        storage_relpath="bad.bin",
    )
    dest = tmp_path / "out"
    dest.mkdir()
    intent = ExportIntent(
        destination_kind=DestinationKind.USER_APPROVED_PATH,
        destination_path=str(dest),
        approved_roots=[str(dest)],
    )
    failed = record_result(
        job_id=uuid4(),
        artifact_id=bad_artifact.artifact_id,
        gate_id="hash-match",
        status=EvidenceStatus.FAIL,
        message="hash mismatch",
    )
    published = publish_artifacts(
        [
            (good_artifact, good, validate_artifact(uuid4(), good_artifact, good)),
            (bad_artifact, bad, [failed]),
        ],
        intent,
    )
    assert len(published) == 1
    assert published[0].is_file()
    assert published[0].read_bytes() == b"good-bytes"
    with pytest.raises(ValidationFailed):
        publish_artifacts([(bad_artifact, bad, [failed])], intent)


def test_path_is_under_rejects_dotdot_sibling(tmp_path: Path) -> None:
    movies = tmp_path / "Movies"
    movies.mkdir()
    backup = tmp_path / "Movies-backup"
    backup.mkdir()
    (backup / "clip.mp4").write_bytes(b"x")
    sneaky = movies / ".." / "Movies-backup" / "clip.mp4"
    assert not path_is_under(sneaky, movies)
    assert path_is_under(movies / "inside" / "clip.mp4", movies)


def test_readme_lists_every_cli_command() -> None:
    from typer.testing import CliRunner

    from webmedia_dl.cli import app, pair_app

    def command_names(typer_app) -> list[str]:
        names: list[str] = []
        for command in typer_app.registered_commands:
            raw = command.name
            if not raw and command.callback is not None:
                raw = command.callback.__name__.removesuffix("_cmd").replace("_", "-")
            if raw:
                names.append(raw)
        for group in typer_app.registered_groups:
            if group.name:
                names.append(group.name)
        return names

    runner = CliRunner()
    readme = (repo_root() / "README.md").read_text(encoding="utf-8")
    root_help = runner.invoke(app, ["--help"])
    assert root_help.exit_code == 0
    names = command_names(app)
    assert "submit" in names
    assert "pair" in names
    for name in names:
        assert name in readme, name
        assert name in root_help.stdout, name
    pair_help = runner.invoke(app, ["pair", "--help"])
    assert pair_help.exit_code == 0
    for name in command_names(pair_app):
        assert name in readme, f"pair {name}"
        assert name in pair_help.stdout, f"pair {name}"


def test_cookie_ledger_merges_and_rejects_relative(tmp_path: Path) -> None:
    cookies_a = tmp_path / "cookies-a.txt"
    cookies_b = tmp_path / "cookies-b.txt"
    cookies_a.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    cookies_b.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    store = tmp_path / "data" / "cookie-grants.json"
    first = CookieGrantLedger(store)
    grant_a = first.issue(uuid4(), cookies_a, "personal-full")
    stale = CookieGrantLedger(store)
    stale._grants = {}
    grant_b = stale.issue(uuid4(), cookies_b, "personal-full")
    recovered = CookieGrantLedger(store)
    assert (
        recovered.resolve(grant_a.grant_id, job_id=grant_a.job_id, profile_id="personal-full")
        == cookies_a.resolve()
    )
    assert (
        recovered.resolve(grant_b.grant_id, job_id=grant_b.job_id, profile_id="personal-full")
        == cookies_b.resolve()
    )
    assert store.stat().st_mode & 0o777 == 0o600
    relative = CookieGrantLedger(store)
    with pytest.raises(CookiePolicyError, match="absolute"):
        relative.issue(uuid4(), Path("relative.txt"), "personal-full")
    with pytest.raises(CookiePolicyError, match="repository"):
        relative.issue(uuid4(), repo_root() / "README.md", "personal-full")
    lock = store.with_suffix(".lock")
    assert lock.is_file()


def test_standalone_cenc_pssh_is_refused() -> None:
    from webmedia_dl.errors import DrmRefused
    from webmedia_dl.live import inspect_manifest

    text = "<MPD><Period><cenc:pssh>AAAA</cenc:pssh></Period></MPD>"
    with pytest.raises(DrmRefused):
        inspect_manifest(text)
    with pytest.raises(DrmRefused):
        recordable_parts(text, "https://cdn.example.com/manifest.mpd")


def test_source_artifact_file_is_not_writable(tmp_path: Path) -> None:
    import os

    from webmedia_dl.artifacts import ArtifactStore

    src = tmp_path / "a.bin"
    src.write_bytes(b"hello")
    store = ArtifactStore(tmp_path / "data")
    artifact = store.register(src, role=ArtifactRole.SOURCE, media_kind=MediaKind.UNKNOWN)
    path = store.resolve(artifact)
    assert path.stat().st_mode & 0o222 == 0
    if os.geteuid() != 0:
        with pytest.raises(PermissionError):
            path.write_bytes(b"mutated")


def test_publish_isolates_unreadable_sibling(tmp_path: Path) -> None:
    good = tmp_path / "good.bin"
    ghost = tmp_path / "ghost.bin"
    good.write_bytes(b"good-bytes")
    ghost.write_bytes(b"ghost-bytes")
    good_digest = sha256_file(str(good))
    ghost_digest = sha256_file(str(ghost))
    good_artifact = Artifact(
        artifact_id=f"sha256:{good_digest}",
        role=ArtifactRole.SOURCE,
        sha256=good_digest,
        byte_size=good.stat().st_size,
        media_kind=MediaKind.IMAGE,
        storage_relpath="good.bin",
    )
    ghost_artifact = Artifact(
        artifact_id=f"sha256:{ghost_digest}",
        role=ArtifactRole.SOURCE,
        sha256=ghost_digest,
        byte_size=ghost.stat().st_size,
        media_kind=MediaKind.IMAGE,
        storage_relpath="ghost.bin",
    )
    dest = tmp_path / "out"
    dest.mkdir()
    intent = ExportIntent(
        destination_kind=DestinationKind.USER_APPROVED_PATH,
        destination_path=str(dest),
        approved_roots=[str(dest)],
    )
    ghost_results = validate_artifact(uuid4(), ghost_artifact, ghost)
    ghost.unlink()
    published = publish_artifacts(
        [
            (good_artifact, good, validate_artifact(uuid4(), good_artifact, good)),
            (ghost_artifact, ghost, ghost_results),
        ],
        intent,
    )
    assert len(published) == 1
    assert published[0].read_bytes() == b"good-bytes"
    reversed_published = publish_artifacts(
        [
            (ghost_artifact, ghost, ghost_results),
            (good_artifact, good, validate_artifact(uuid4(), good_artifact, good)),
        ],
        intent,
    )
    assert len(reversed_published) == 1
    with pytest.raises(OSError):
        publish_artifacts([(ghost_artifact, ghost, ghost_results)], intent)


def test_blank_export_roots_are_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="approved"):
        ExportIntent(
            destination_kind=DestinationKind.USER_APPROVED_PATH,
            destination_path="/tmp/webmedia-dl-out",
            approved_roots=["", " "],
        )


def test_package_bundle_skips_coverage_and_caches(tmp_path: Path) -> None:
    import importlib.util

    path = repo_root() / "scripts" / "package_bundle.py"
    spec = importlib.util.spec_from_file_location("package_bundle", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "keep.txt").write_text("ok", encoding="utf-8")
    (tree / ".coverage").write_text("cov", encoding="utf-8")
    (tree / "CACHEDIR.TAG").write_text("tag", encoding="utf-8")
    cache = tree / ".ruff_cache"
    cache.mkdir()
    (cache / "x").write_text("x", encoding="utf-8")
    names = {path.name for path in mod.iter_files(tree)}
    assert "keep.txt" in names
    assert ".coverage" not in names
    assert "CACHEDIR.TAG" not in names
    assert "x" not in names
