from pathlib import Path
from uuid import uuid4

import pytest

from webmedia_dl.artifacts import ArtifactStore
from webmedia_dl.capabilities import load_platform_matrix, registry
from webmedia_dl.domain.enums import ArtifactRole, DestinationKind, IntakeKind, JobState, MediaKind
from webmedia_dl.domain.models import (
    Artifact,
    ExportIntent,
    ExportPlan,
    Job,
    MediaSource,
    Operation,
)
from webmedia_dl.errors import CancelledError, DrmRefused, ProviderPolicyError, PublicationError
from webmedia_dl.export import plan_export
from webmedia_dl.identity import sha256_file
from webmedia_dl.live import record_clear_stream, recordable_segment_urls
from webmedia_dl.paths import repo_root
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import builtin_profiles
from webmedia_dl.processing import execute_export_plan
from webmedia_dl.providers import ProviderRequest, ProviderRuntime
from webmedia_dl.publish import publish_artifacts
from webmedia_dl.queue import QueueStore
from webmedia_dl.validation import validate_artifact


def test_document_and_subtitle_are_passthrough() -> None:
    doc = Artifact(
        artifact_id="sha256:aa",
        role=ArtifactRole.SOURCE,
        sha256="aa",
        byte_size=1,
        media_kind=MediaKind.DOCUMENT,
        storage_relpath="a.pdf",
        container="pdf",
    )
    plan = plan_export(uuid4(), doc, ExportIntent(container_preference="mkv"))
    assert [item.operation_id for item in plan.operations] == ["keep-original"]
    sub = doc.model_copy(update={"media_kind": MediaKind.SUBTITLE, "container": "vtt"})
    sub_plan = plan_export(uuid4(), sub, ExportIntent(allow_lossy=True, container_preference="mp4"))
    assert [item.operation_id for item in sub_plan.operations] == ["keep-original"]


def test_unknown_preset_is_rejected() -> None:
    artifact = Artifact(
        artifact_id="sha256:ab",
        role=ArtifactRole.SOURCE,
        sha256="ab",
        byte_size=1,
        media_kind=MediaKind.VIDEO,
        storage_relpath="a.mp4",
        container="mp4",
    )
    with pytest.raises(ProviderPolicyError, match="Unknown export preset"):
        plan_export(uuid4(), artifact, ExportIntent(preset_id="not-a-preset"))


def test_preview_role_and_sibling_isolation(tmp_path: Path) -> None:
    src = tmp_path / "source.jpg"
    src.write_bytes(b"jpeg-bytes")
    store = ArtifactStore(tmp_path / "data")
    source = store.register(
        src, role=ArtifactRole.SOURCE, media_kind=MediaKind.IMAGE, container="jpg"
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
                surface="cli",
                policy_profile_id="personal-full",
            ),
            policy_profile_id="personal-full",
            worker_id="local-macos",
        )
    )

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        raw = argv[-1]
        output = raw.split(":", 1)[1] if raw.startswith(("png:", "jpeg:")) else raw
        path = Path(output)
        if path.name.startswith("bad."):
            return 1, b"", b"fail"
        path.write_bytes(b"derived")
        return 0, b"", b""

    plan = ExportPlan(
        job_id=job_id,
        operations=[
            Operation(
                operation_id="keep-original",
                op_type="identity.copy",
                capability_id="export.plan",
                input_artifact_ids=[source.artifact_id],
                output_role=ArtifactRole.SOURCE,
                loss_class="none",
                validator_ids=[],
            ),
            Operation(
                operation_id="bad",
                op_type="imagemagick.convert",
                capability_id="process.imagemagick.convert",
                input_artifact_ids=[source.artifact_id],
                output_role=ArtifactRole.DERIVATIVE,
                loss_class="none",
                validator_ids=[],
                typed_inputs={"container": "png"},
            ),
            Operation(
                operation_id="preview",
                op_type="imagemagick.convert",
                capability_id="process.imagemagick.convert",
                input_artifact_ids=[source.artifact_id],
                output_role=ArtifactRole.PREVIEW,
                loss_class="reversible_metadata",
                validator_ids=[],
                typed_inputs={"container": "jpg"},
                optional=True,
            ),
        ],
    )
    produced = execute_export_plan(
        plan,
        job_id=job_id,
        source=source,
        source_path=store.resolve(source),
        store=store,
        runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
        staging=tmp_path / "stage",
        queue=queue,
        authorize=lambda _cap: None,
    )
    roles = {item.role for item, _path in produced}
    assert ArtifactRole.SOURCE in roles
    assert ArtifactRole.PREVIEW in roles
    assert ArtifactRole.DERIVATIVE not in roles
    types = [event.type.value for event in queue.events_for(job_id)]
    assert "operation.failed" in types
    assert "operation.completed" in types


def test_gallery_registers_every_created_file(tmp_path: Path, png_bytes: bytes) -> None:
    def run(argv: list[str], cwd: Path) -> tuple[int, bytes, bytes]:
        (cwd / "a.jpg").write_bytes(png_bytes)
        (cwd / "b.jpg").write_bytes(png_bytes + b"2")
        return 0, b"", b""

    runtime = ProviderRuntime(
        which=lambda name: "/usr/bin/gallery-dl" if name == "gallery-dl" else None,
        run=run,
        http_get=lambda url: (200, {}, png_bytes),
    )
    result = runtime.execute(
        ProviderRequest(
            provider_id="gallery-dl",
            capability_id="acquire.gallery_dl",
            typed_inputs={"url": "https://example.com/album"},
        ),
        tmp_path,
    )
    assert result.output_path is not None
    assert {path.name for path in result.output_paths} == {"a.jpg", "b.jpg"}

    html = """
    <html><body>
      <img src="https://cdn.example.com/a.jpg">
      <img src="https://cdn.example.com/b.jpg">
      <img src="https://cdn.example.com/c.jpg">
    </body></html>
    """
    pipeline = Pipeline(data_dir=tmp_path / "data", runtime=runtime)
    job = pipeline.submit("https://example.com/album", html=html)
    assert job.state is JobState.COMPLETED
    sources = [item for item in pipeline.store.list_artifacts() if item.role is ArtifactRole.SOURCE]
    assert len(sources) >= 2


def test_hls_keeps_clear_segments_then_stops(tmp_path: Path) -> None:
    playlist = (
        "#EXTM3U\n#EXTINF:1,\nseg1.ts\n"
        '#EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key"\n'
        "#EXTINF:1,\nseg2.ts\n"
    )
    urls = recordable_segment_urls(playlist, "https://cdn.example.com/live/index.m3u8")
    assert urls == ["https://cdn.example.com/live/seg1.ts"]
    bodies = {"https://cdn.example.com/live/seg1.ts": b"CLEAR"}

    def fetch(url: str) -> tuple[int, str, bytes]:
        if "key" in url or url.endswith("seg2.ts"):
            raise AssertionError(f"must not fetch encrypted material: {url}")
        return 200, "video/MP2T", bodies[url]

    output = tmp_path / "live.ts"
    record_clear_stream(playlist, "https://cdn.example.com/live/index.m3u8", output, fetch)
    assert output.read_bytes() == b"CLEAR"


def test_hls_cancel_between_segments(tmp_path: Path) -> None:
    playlist = "#EXTM3U\n#EXTINF:1,\nseg1.ts\n#EXTINF:1,\nseg2.ts\n"
    seen: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        seen.append(url)
        return 200, "video/MP2T", b"X"

    def should_stop() -> None:
        if seen:
            raise CancelledError("cancelled between segments")

    with pytest.raises(CancelledError):
        record_clear_stream(
            playlist,
            "https://cdn.example.com/live/index.m3u8",
            tmp_path / "live.ts",
            fetch,
            should_stop=should_stop,
        )
    assert len(seen) == 1


def test_files_app_publishes_under_approved_root(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"data")
    digest = sha256_file(str(src))
    artifact = Artifact(
        artifact_id=f"sha256:{digest}",
        role=ArtifactRole.SOURCE,
        sha256=digest,
        byte_size=4,
        media_kind=MediaKind.UNKNOWN,
        storage_relpath="src.bin",
    )
    dest = tmp_path / "files"
    dest.mkdir()
    intent = ExportIntent(
        destination_kind=DestinationKind.FILES_APP,
        destination_path=str(dest),
        approved_roots=[str(dest)],
    )
    published = publish_artifacts(
        [(artifact, src, validate_artifact(uuid4(), artifact, src))],
        intent,
    )
    assert published
    assert published[0].is_relative_to(dest)


def test_photos_library_stays_blocked(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"data")
    digest = sha256_file(str(src))
    artifact = Artifact(
        artifact_id=f"sha256:{digest}",
        role=ArtifactRole.SOURCE,
        sha256=digest,
        byte_size=4,
        media_kind=MediaKind.UNKNOWN,
        storage_relpath="src.bin",
    )
    intent = ExportIntent(destination_kind=DestinationKind.PHOTOS, approved_roots=[str(tmp_path)])
    with pytest.raises(PublicationError, match="Photos library"):
        publish_artifacts(
            [(artifact, src, validate_artifact(uuid4(), artifact, src))],
            intent,
        )


def test_subtitle_sidecar_uses_primary_stem(tmp_path: Path) -> None:
    video = tmp_path / "clip.bin"
    video.write_bytes(b"videobytes")
    caption = tmp_path / "clip.vtt"
    caption.write_text("WEBVTT\n", encoding="utf-8")
    video_digest = sha256_file(str(video))
    caption_digest = sha256_file(str(caption))
    video_artifact = Artifact(
        artifact_id=f"sha256:{video_digest}",
        role=ArtifactRole.SOURCE,
        sha256=video_digest,
        byte_size=video.stat().st_size,
        media_kind=MediaKind.VIDEO,
        storage_relpath="clip.bin",
    )
    caption_artifact = Artifact(
        artifact_id=f"sha256:{caption_digest}",
        role=ArtifactRole.SOURCE,
        sha256=caption_digest,
        byte_size=caption.stat().st_size,
        media_kind=MediaKind.SUBTITLE,
        storage_relpath="clip.vtt",
    )
    dest = tmp_path / "out"
    dest.mkdir()
    published = publish_artifacts(
        [
            (video_artifact, video, validate_artifact(uuid4(), video_artifact, video)),
            (caption_artifact, caption, validate_artifact(uuid4(), caption_artifact, caption)),
        ],
        ExportIntent(
            destination_kind=DestinationKind.USER_APPROVED_PATH,
            destination_path=str(dest),
            approved_roots=[str(dest)],
        ),
    )
    names = {path.name for path in published}
    assert f"{video_digest[:16]}.vtt" in names


def test_preview_is_not_published(tmp_path: Path) -> None:
    src = tmp_path / "a.bin"
    src.write_bytes(b"data")
    digest = sha256_file(str(src))
    preview = Artifact(
        artifact_id=f"sha256:{digest}",
        role=ArtifactRole.PREVIEW,
        sha256=digest,
        byte_size=4,
        media_kind=MediaKind.IMAGE,
        storage_relpath="a.bin",
    )
    dest = tmp_path / "out"
    dest.mkdir()
    published = publish_artifacts(
        [(preview, src, validate_artifact(uuid4(), preview, src))],
        ExportIntent(
            destination_kind=DestinationKind.USER_APPROVED_PATH,
            destination_path=str(dest),
            approved_roots=[str(dest)],
        ),
    )
    assert published == []


def test_cookie_event_has_basename_only(tmp_data: Path, tmp_path: Path, png_bytes: bytes) -> None:
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), cookies=str(cookies))
    event = next(
        item
        for item in pipeline.queue.events_for(job.job_id)
        if item.type.value == "cookie.attached"
    )
    assert event.payload["cookies_path_basename"] == "user-cookies.txt"
    assert event.payload["profile_id"] == "personal-full"
    assert "path" not in event.payload


def test_history_includes_artifact_ids(tmp_path: Path, png_bytes: bytes) -> None:
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    pipeline = Pipeline(data_dir=tmp_path / "data")
    job = pipeline.submit(str(media))
    entries = pipeline.history_entries()
    match = next(item for item in entries if item["job_id"] == str(job.job_id))
    assert match["artifact_ids"]
    assert match["last_events"]


def test_policy_resources_match_runtime() -> None:
    import json

    raw = json.loads(
        (repo_root() / "resources" / "policy-profiles.json").read_text(encoding="utf-8")
    )
    profiles = builtin_profiles()
    assert set(profiles) == set(raw)
    assert profiles["personal-full"].cookie_access.value == raw["personal-full"]["cookie_access"]
    matrix = load_platform_matrix()
    assert "macos" in matrix
    assert "watchos" in matrix
    ids = {item.capability_id for item in registry()}
    assert "acquire.gallery_dl" in ids


def test_magick_convert_uses_format_prefix(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        captured.append(argv)
        Path(str(argv[-1]).split(":", 1)[-1]).write_bytes(b"ok")
        return 0, b"", b""

    runtime = ProviderRuntime(which=lambda name: "/usr/bin/magick", run=run)
    runtime.execute(
        ProviderRequest(
            provider_id="imagemagick",
            capability_id="process.imagemagick.convert",
            typed_inputs={
                "input": str(tmp_path / "a.jpg"),
                "output": str(tmp_path / "b.png"),
                "container": "png",
            },
        ),
        tmp_path,
    )
    assert captured[0][-1].startswith("png:")
    assert captured[0][-2] == "-auto-orient"


def test_dash_baseurl_and_encrypted_master() -> None:
    text = "<MPD><Period><BaseURL>seg.m4s</BaseURL></Period></MPD>"
    urls = recordable_segment_urls(text, "https://cdn.example.com/dash/")
    assert urls == ["https://cdn.example.com/dash/seg.m4s"]
    with pytest.raises(DrmRefused):
        recordable_segment_urls(
            '#EXTM3U\n#EXT-X-KEY:METHOD=SAMPLE-AES,URI="k"\nseg.ts\n',
            "https://cdn.example.com/live.m3u8",
        )
