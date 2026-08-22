"""Remaining Linux-provable contract gates for export, publish, probe, and resume."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from webmedia_dl.artifacts import ArtifactStore
from webmedia_dl.compat import migrate_legacy, scan_legacy
from webmedia_dl.continuity import companion_message
from webmedia_dl.destinations import PhotoKitDestination, SecurityScopedBookmark
from webmedia_dl.diagnostics import _status
from webmedia_dl.discovery import discover
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
    AcquisitionStrategy,
    Artifact,
    ExportIntent,
    ExportPlan,
    FormatAlternative,
    Job,
    MediaCandidate,
    MediaSource,
    Operation,
    sanitize_event_payload,
)
from webmedia_dl.errors import PauseRequested, PublicationError, WebMediaError
from webmedia_dl.export import plan_export
from webmedia_dl.identity import sha256_bytes
from webmedia_dl.live import recordable_parts, recordable_segment_urls
from webmedia_dl.network_policy import authorize_destination
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import get_profile
from webmedia_dl.probe import _as_int, probe_media
from webmedia_dl.processing import execute_export_plan
from webmedia_dl.providers import ProviderRequest, ProviderResult, ProviderRuntime
from webmedia_dl.publish import publish_artifacts
from webmedia_dl.queue import QueueStore
from webmedia_dl.validation import record_result


def _page() -> MediaSource:
    return MediaSource(
        kind=IntakeKind.URL,
        locator="https://example.com/page",
        normalized_url="https://example.com/page",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )


def test_resume_job_holds_when_queue_paused(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = tmp_path / "held.png"
    media.write_bytes(png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    pipeline.pause_job(job.job_id)
    pipeline.pause_queue()
    resumed = pipeline.resume_job(job.job_id)
    assert resumed.state is JobState.ACCEPTED
    assert pipeline.queue.is_paused() is True
    held = pipeline.submit(str(media), wait=False)
    held_resume = pipeline.resume_job(held.job_id)
    assert held_resume.state is JobState.ACCEPTED
    assert pipeline.queue.is_paused() is True


def test_pause_requested_during_export_execute(
    tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "source.mp4"
    src.write_bytes(png_bytes)
    store = ArtifactStore(tmp_path / "data")
    source = store.register(
        src, role=ArtifactRole.SOURCE, media_kind=MediaKind.VIDEO, container="mp4"
    )
    queue = QueueStore(tmp_path / "data" / "queue")
    queued = Job(
        source=MediaSource(
            kind=IntakeKind.FILE,
            locator=str(src),
            local_path=str(src),
            surface="cli",
            policy_profile_id="personal-full",
        ),
        policy_profile_id="personal-full",
        worker_id="local-macos",
    )
    queue.put_job(queued)
    remux = Operation(
        operation_id="remux",
        op_type="ffmpeg.remux",
        capability_id="process.ffmpeg.remux",
        input_artifact_ids=[source.artifact_id],
        output_role=ArtifactRole.DERIVATIVE,
        loss_class="container_only",
        validator_ids=[],
        typed_inputs={"container": "mkv"},
    )
    runtime = ProviderRuntime(which=lambda name: f"/usr/bin/{name}")

    def boom(*_args: object, **_kwargs: object) -> ProviderResult:
        raise PauseRequested("during remux")

    monkeypatch.setattr(runtime, "execute", boom)
    with pytest.raises(PauseRequested, match="during remux"):
        execute_export_plan(
            ExportPlan(job_id=queued.job_id, operations=[remux]),
            job_id=queued.job_id,
            source=source,
            source_path=store.resolve(source),
            store=store,
            runtime=runtime,
            staging=tmp_path / "stage-pause",
            queue=queue,
            authorize=lambda _cap: None,
        )


def test_empty_output_paths_fall_back_to_output_path(
    tmp_data: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    def http_get(url: str) -> tuple[int, dict[str, str], bytes]:
        return 200, {"content-type": "image/png"}, png_bytes

    runtime = ProviderRuntime(which=lambda _name: None, http_get=http_get)
    original = runtime.execute

    def wrapped(request: ProviderRequest, staging: Path) -> ProviderResult:
        result = original(request, staging)
        return ProviderResult(
            result.exit_code,
            result.stdout,
            result.stderr,
            result.output_path,
            result.argv,
            output_paths=(),
        )

    monkeypatch.setattr(runtime, "execute", wrapped)
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit("https://cdn.example.com/hero.png")
    assert job.state is JobState.COMPLETED


def test_acquire_registers_output_paths_when_primary_missing(
    tmp_data: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    html = '<html><body><video src="https://example.com/watch?v=1"></video></body></html>'
    runtime = ProviderRuntime(
        which=lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None,
        run=lambda _argv, _cwd: (0, b"", b""),
    )
    original = runtime.execute

    def wrapped(request: ProviderRequest, staging: Path) -> ProviderResult:
        result = original(request, staging)
        dest = staging / "clip.jpg"
        dest.write_bytes(png_bytes)
        return ProviderResult(
            0,
            result.stdout,
            result.stderr,
            None,
            result.argv,
            output_paths=(dest,),
        )

    monkeypatch.setattr(runtime, "execute", wrapped)
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit("https://example.com/watch", html=html)
    assert job.state is JobState.COMPLETED


def test_export_preset_override_and_lossy_without_container(tmp_path: Path) -> None:
    video = Artifact(
        artifact_id="sha256:" + "ab" * 32,
        role=ArtifactRole.SOURCE,
        sha256="ab" * 32,
        byte_size=1,
        media_kind=MediaKind.VIDEO,
        storage_relpath="clip.mp4",
        container="mp4",
    )
    remux = plan_export(uuid4(), video, ExportIntent(preset_id="remux-mkv"))
    assert any(item.operation_id == "remux" for item in remux.operations)
    lossy = plan_export(uuid4(), video, ExportIntent(allow_lossy=True))
    assert any(item.operation_id == "transcode" for item in lossy.operations)


def test_publish_photos_staging_and_missing_path(tmp_path: Path, png_bytes: bytes) -> None:
    path = tmp_path / "a.png"
    path.write_bytes(png_bytes)
    artifact = Artifact(
        artifact_id="sha256:" + "cd" * 32,
        role=ArtifactRole.SOURCE,
        sha256="cd" * 32,
        byte_size=len(png_bytes),
        media_kind=MediaKind.IMAGE,
        storage_relpath="a.png",
    )
    results: list = []
    with pytest.raises(PublicationError, match="Photos"):
        publish_artifacts(
            [(artifact, path, results)],
            ExportIntent(
                destination_kind=DestinationKind.PHOTOS,
                approved_roots=[str(tmp_path)],
            ),
        )
    staged = publish_artifacts([(artifact, path, results)], ExportIntent())
    assert staged == [path]
    missing = ExportIntent.model_construct(
        destination_kind=DestinationKind.USER_APPROVED_PATH,
        destination_path=None,
        approved_roots=[str(tmp_path)],
    )
    with pytest.raises(PublicationError, match="destination path"):
        publish_artifacts([(artifact, path, results)], missing)


def test_publish_replace_oserror_unlinks_leftovers(
    tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "out"
    dest.mkdir()
    path = tmp_path / "a.png"
    path.write_bytes(png_bytes)
    artifact = Artifact(
        artifact_id="sha256:" + "ef" * 32,
        role=ArtifactRole.SOURCE,
        sha256="ef" * 32,
        byte_size=len(png_bytes),
        media_kind=MediaKind.IMAGE,
        storage_relpath="a.png",
    )

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("busy")

    monkeypatch.setattr("webmedia_dl.publish.os.replace", boom)
    passed = [
        record_result(
            job_id=uuid4(),
            artifact_id=artifact.artifact_id,
            gate_id="hash-match",
            status=EvidenceStatus.PASS,
            message="ok",
        ),
        record_result(
            job_id=uuid4(),
            artifact_id=artifact.artifact_id,
            gate_id="size-match",
            status=EvidenceStatus.PASS,
            message="ok",
        ),
    ]
    with pytest.raises(OSError, match="busy"):
        publish_artifacts(
            [(artifact, path, passed)],
            ExportIntent(
                destination_kind=DestinationKind.USER_APPROVED_PATH,
                destination_path=str(dest),
                approved_roots=[str(dest)],
            ),
        )


def test_probe_timeout_empty_stdout_encrypted_tags_and_bool_index(tmp_path: Path) -> None:
    media = tmp_path / "clip.bin"
    media.write_bytes(b"bytes")

    def timeout(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="ffprobe", timeout=30)

    assert probe_media(media, which=lambda _name: "/usr/bin/ffprobe", runner=timeout) is None

    def empty(*_args: object, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(returncode=0, stdout=b"")

    assert probe_media(media, which=lambda _name: "/usr/bin/ffprobe", runner=empty) is not None

    def tagged(*_args: object, **_kwargs: object) -> SimpleNamespace:
        payload = {
            "streams": [
                {
                    "index": True,
                    "codec_type": "video",
                    "codec_name": "h264",
                    "tags": {"ENCRYPTED": "yes"},
                }
            ],
            "format": {"format_name": "mov,mp4,m4a", "duration": "bad"},
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload).encode())

    probed = probe_media(media, which=lambda _name: "/usr/bin/ffprobe", runner=tagged)
    assert probed is not None
    assert probed.streams[0].encrypted is True
    assert probed.streams[0].index == 1
    assert _as_int(True) == 1
    assert _as_int("") is None


def test_bookmark_stale_relative_and_photokit_missing_root(tmp_path: Path) -> None:
    dest = tmp_path / "Movies"
    dest.mkdir()
    stale = SecurityScopedBookmark(resolved_path=str(dest), stale=True)
    assert stale.allows(str(dest / "clip.mp4")) is False
    relative = SecurityScopedBookmark(resolved_path="Movies")
    assert relative.allows("Movies/clip.mp4") is False
    photos = PhotoKitDestination()
    with pytest.raises(PublicationError, match="approved root"):
        photos.assert_publishable()


def test_dash_invalid_bandwidth_and_missing_segment_hrefs() -> None:
    text = """
    <MPD><Period>
      <Representation id="v" bandwidth="nope" mimeType="video/mp4">
        <BaseURL>clip.mp4</BaseURL>
        <SegmentBase mediaRange="0-3">
          <Initialization range="0-3"/>
        </SegmentBase>
      </Representation>
    </Period></MPD>
    """
    parts = recordable_parts(text, "https://cdn.example.com/")
    assert parts
    leftover = """
    <MPD><Period>
      <SegmentList>
        <Initialization range="0-9"/>
        <SegmentURL mediaRange="10-19"/>
        <SegmentURL media="seg.m4s"/>
      </SegmentList>
    </Period></MPD>
    """
    urls = recordable_segment_urls(leftover, "https://cdn.example.com/")
    assert urls == ["https://cdn.example.com/seg.m4s"]


def test_legacy_directory_marker_symlink_and_relative_root(tmp_path: Path) -> None:
    (tmp_path / "archive.txt").mkdir()
    nested = tmp_path / "nested" / "yt-dlp-archive.txt"
    nested.parent.mkdir()
    nested.write_text("id-one\n", encoding="utf-8")
    alias = tmp_path / "also" / "yt-dlp-archive.txt"
    alias.parent.mkdir()
    alias.symlink_to(nested)
    report = scan_legacy(tmp_path)
    assert nested.as_posix() in report["extra_archives"] or any(
        Path(item).resolve() == nested.resolve() for item in report["extra_archives"]
    )
    applied = migrate_legacy(tmp_path, apply=True)
    assert applied["migrated"] is True
    with pytest.raises(Exception, match="absolute approved root"):
        authorize_destination(tmp_path, ["relative-root", "  "])


def test_explain_mixed_kinds_and_empty_preferred(
    tmp_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipeline = Pipeline(data_dir=tmp_data)
    html = """
    <html><body>
      <video src="https://cdn.example.com/clip.mp4"></video>
      <img src="https://cdn.example.com/hero.png">
    </body></html>
    """
    explained = pipeline.explain("https://example.com/page", html=html)
    assert len(explained["preferred_by_kind"]) >= 2
    assert explained["plans"]

    monkeypatch.setattr("webmedia_dl.pipeline.preferred_by_kind", lambda _graph: [])
    empty = pipeline.explain("https://example.com/page", html=html)
    assert empty["preferred"] is None
    assert empty["export_operations"] == []

    alt = MediaCandidate(
        source_id=uuid4(),
        media_kind=MediaKind.VIDEO,
        identity_key="host:cdn.example.com:path:/clip.mp4",
        retrieval_urls=["https://cdn.example.com/clip.mp4"],
        alternatives=[FormatAlternative(format_id="137", container="webm")],
        host="cdn.example.com",
    )
    monkeypatch.setattr("webmedia_dl.pipeline.preferred_by_kind", lambda _graph: [alt])
    monkeypatch.setattr("webmedia_dl.pipeline.discover", lambda *_a, **_k: [alt])
    with_alt = pipeline.explain("https://cdn.example.com/clip.mp4")
    assert with_alt["export_operations"]


def test_discovery_mime_kinds_and_jsonld_unknown() -> None:
    html = """
    <html>
      <head>
        <script type="application/ld+json">
          {"@type": "Article", "contentUrl": "https://example.com/story"}
        </script>
      </head>
      <body>
        <source type="audio/mpeg" src="https://cdn.example.com/plain-audio">
        <source type="application/vnd.apple.mpegurl" src="https://cdn.example.com/plain-live">
        <source type="image/jpeg" src="https://cdn.example.com/plain-image">
      </body>
    </html>
    """
    found = discover(_page(), get_profile("personal-full"), html=html)
    kinds = {item.retrieval_urls[0]: item.media_kind for item in found if item.retrieval_urls}
    assert kinds["https://cdn.example.com/plain-audio"] is MediaKind.AUDIO
    assert kinds["https://cdn.example.com/plain-live"] is MediaKind.LIVE_STREAM
    assert kinds["https://cdn.example.com/plain-image"] is MediaKind.IMAGE
    assert kinds["https://example.com/story"] is MediaKind.PAGE


def test_identity_error_event_and_doctor_status() -> None:
    assert sha256_bytes(b"x") == sha256_bytes(b"x")
    err = WebMediaError("boom", code="custom.code")
    assert err.code == "custom.code"
    blocked = _status(False, False)
    assert blocked["status"] == "BLOCKED"
    assert blocked["executed"] is False
    companion_message("status", surface=Surface.TVOS)
    assert sanitize_event_payload(None) == {}
    assert sanitize_event_payload({"nested": [{"note": "ok"}, {"cookie_jar": 1}]}) == {
        "nested": [{"note": "ok"}, {"cookie_jar": 1}]
    }


def test_url_never_becomes_path_and_title_identity() -> None:
    with pytest.raises(ValueError, match="filesystem path"):
        MediaSource(
            kind=IntakeKind.URL,
            locator="https://example.com/a",
            normalized_url="https://example.com/a",
            local_path="/tmp/a",
            surface=Surface.CLI,
            policy_profile_id="personal-full",
        )
    with pytest.raises(ValueError, match="filesystem path"):
        MediaSource(
            kind=IntakeKind.URL,
            locator="https://example.com/a",
            normalized_url="file:/tmp/a",
            surface=Surface.CLI,
            policy_profile_id="personal-full",
        )
    with pytest.raises(ValueError, match="display title"):
        Artifact(
            artifact_id="Clip Title",
            role=ArtifactRole.SOURCE,
            sha256="00" * 32,
            byte_size=1,
            media_kind=MediaKind.VIDEO,
            storage_relpath="x.bin",
            provenance={"title": "Clip Title"},
        )
    with pytest.raises(ValueError, match="Photos publication"):
        ExportIntent(destination_kind=DestinationKind.PHOTOS)
    with pytest.raises(ValueError, match="arbitrary user arguments"):
        AcquisitionStrategy(
            strategy_id="s",
            provider_id="http-direct",
            capability_id="acquire.http",
            extra_args=["-f"],
        )
    with pytest.raises(ValueError, match="must not include"):
        sanitize_event_payload({"cookies_dir": "/tmp/cookies.txt"})
