"""Remaining Linux-provable pipeline, live, discovery, processing, and API gates."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from webmedia_dl import cli as cli_mod
from webmedia_dl.artifacts import ArtifactStore
from webmedia_dl.discovery import candidates_from_manifest_json, discover
from webmedia_dl.domain.enums import (
    ArtifactRole,
    EventType,
    IntakeKind,
    JobState,
    MediaKind,
    Surface,
)
from webmedia_dl.domain.models import (
    ExportIntent,
    ExportPlan,
    Job,
    MediaSource,
    Operation,
)
from webmedia_dl.errors import (
    ArtifactImmutabilityError,
    DiscoveryError,
    PauseRequested,
    ValidationFailed,
)
from webmedia_dl.live import (
    _file_baseurl,
    _parse_byterange,
    _parse_dash_range,
    _period_parts,
    hls_audio_playlist_urls,
    hls_subtitle_playlist_urls,
    record_clear_stream,
    record_kind_streams,
    recordable_parts,
    recordable_segment_urls,
)
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import get_profile
from webmedia_dl.processing import execute_export_plan
from webmedia_dl.providers import ProviderRuntime, _http_suffix
from webmedia_dl.queue import QueueStore
from webmedia_dl.service import create_app, load_or_create_token


def _page_source() -> MediaSource:
    return MediaSource(
        kind=IntakeKind.URL,
        locator="https://example.com/page",
        normalized_url="https://example.com/page",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )


def _queue_job(queue: QueueStore, src: Path) -> Job:
    job = Job(
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
    queue.put_job(job)
    return job


def test_pause_during_export_keeps_exporting_checkpoint(
    tmp_data: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"fake-mp4")
    original = Pipeline._save_acquire_checkpoint

    def save(
        self: Pipeline,
        job: Job,
        sources: list[Any],
        acquired_kinds: set[str],
        **kwargs: Any,
    ) -> None:
        original(self, job, sources, acquired_kinds, **kwargs)
        if kwargs.get("stage") == "exporting":
            self.queue.set_job_flags(job.job_id, pause_requested=True)

    monkeypatch.setattr(Pipeline, "_save_acquire_checkpoint", save)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(
        str(media),
        intent=ExportIntent(container_preference="mkv"),
        wait=False,
    )
    paused = pipeline.run_next()
    assert paused is not None
    assert paused.state is JobState.PAUSED
    checkpoint = pipeline.queue.get_context(job.job_id).checkpoint
    assert checkpoint.get("stage") == "exporting"
    assert checkpoint.get("completed_operations")


def test_resume_skips_already_acquired_kind(tmp_data: Path, png_bytes: bytes) -> None:
    html = """
    <html><body>
      <video src="https://cdn.example.com/clip.mp4"></video>
      <img src="https://cdn.example.com/hero.png">
    </body></html>
    """
    fetched: list[str] = []

    def http_get(url: str) -> tuple[int, dict[str, str], bytes]:
        fetched.append(url)
        if url.endswith(".mp4"):
            return 200, {"content-type": "video/mp4"}, b"fake-mp4"
        return 200, {"content-type": "image/png"}, png_bytes

    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(which=lambda _name: None, http_get=http_get),
    )
    job = pipeline.submit("https://example.com/mixed", html=html, wait=False)
    image = tmp_data.parent / "hero.png"
    image.write_bytes(png_bytes)
    source = pipeline.store.register(
        image,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.IMAGE,
        provenance={"job_id": str(job.job_id)},
    )
    pipeline.queue.put_checkpoint(
        job.job_id,
        {
            "stage": "acquiring",
            "source_ids": [source.artifact_id],
            "acquired_kinds": ["image"],
        },
    )
    completed = pipeline.run_next()
    assert completed is not None
    assert completed.state is JobState.COMPLETED
    assert any(item.endswith("clip.mp4") for item in fetched)
    assert not any(item.endswith("hero.png") for item in fetched)


def test_failed_kind_is_not_appended_twice(tmp_data: Path, png_bytes: bytes) -> None:
    html = """
    <html><body>
      <video src="https://cdn.example.com/clip.mp4"></video>
      <img src="https://cdn.example.com/hero.png">
    </body></html>
    """

    def http_get(url: str) -> tuple[int, dict[str, str], bytes]:
        if url.endswith(".mp4"):
            return 500, {}, b"no"
        return 200, {"content-type": "image/png"}, png_bytes

    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(which=lambda _name: None, http_get=http_get),
    )
    job = pipeline.submit("https://example.com/mixed", html=html, wait=False)
    pipeline.queue.put_checkpoint(job.job_id, {"failed_kinds": ["video"], "stage": "acquiring"})
    completed = pipeline.run_next()
    assert completed is not None
    assert completed.state is JobState.COMPLETED
    events = pipeline.queue.events_for(job.job_id)
    completed_event = [item for item in events if item.type is EventType.JOB_COMPLETED][-1]
    assert completed_event.payload["failed_kinds"] == ["video"]


def test_derivative_validation_failure_still_publishes_source(
    tmp_data: Path,
    tmp_path: Path,
    pass_container_probe,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"fake-mp4")

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        Path(argv[-1]).write_bytes(b"mkv-bytes")
        return 0, b"", b""

    def fake_validate(job_id: UUID, item: object, path: Path, **_kwargs: object) -> list:
        from webmedia_dl.domain.models import Artifact
        from webmedia_dl.validation import validate_artifact

        artifact = cast(Artifact, item)
        if artifact.role is ArtifactRole.DERIVATIVE:
            raise ValidationFailed("derivative rejected")
        return validate_artifact(job_id, artifact, path)

    monkeypatch.setattr("webmedia_dl.pipeline.validate_artifact", fake_validate)
    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
    )
    job = pipeline.submit(str(media), intent=ExportIntent(container_preference="mkv"))
    assert job.state is JobState.COMPLETED
    roles = {item.role for item in pipeline.store.list_artifacts()}
    assert ArtifactRole.SOURCE in roles


def test_optional_dependent_skips_when_required_input_failed(
    tmp_path: Path, png_bytes: bytes
) -> None:
    src = tmp_path / "source.mp4"
    src.write_bytes(png_bytes)
    store = ArtifactStore(tmp_path / "data")
    source = store.register(
        src, role=ArtifactRole.SOURCE, media_kind=MediaKind.VIDEO, container="mp4"
    )
    queue = QueueStore(tmp_path / "data" / "queue")
    job = _queue_job(queue, src)

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        return 1, b"", b"fail"

    remux = Operation(
        operation_id="remux",
        op_type="ffmpeg.remux",
        capability_id="process.ffmpeg.remux",
        input_artifact_ids=[source.artifact_id],
        output_role=ArtifactRole.DERIVATIVE,
        loss_class="container_only",
        validator_ids=[],
        typed_inputs={"container": "mkv"},
        optional=True,
    )
    preview = Operation(
        operation_id="preview",
        op_type="ffmpeg.remux",
        capability_id="process.ffmpeg.remux",
        input_artifact_ids=["remux"],
        output_role=ArtifactRole.PREVIEW,
        loss_class="reversible_metadata",
        validator_ids=[],
        typed_inputs={"container": "jpg"},
        optional=True,
    )
    produced = execute_export_plan(
        ExportPlan(job_id=job.job_id, operations=[remux, preview]),
        job_id=job.job_id,
        source=source,
        source_path=store.resolve(source),
        store=store,
        runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
        staging=tmp_path / "stage-optional",
        queue=queue,
        authorize=lambda _cap: None,
    )
    assert produced
    assert all(item.role is ArtifactRole.SOURCE for item, _path in produced)


def test_processing_skips_probe_require_pass_when_probe_missing(
    tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "source.mp4"
    src.write_bytes(png_bytes)
    store = ArtifactStore(tmp_path / "data")
    source = store.register(
        src, role=ArtifactRole.SOURCE, media_kind=MediaKind.VIDEO, container="mp4"
    )
    queue = QueueStore(tmp_path / "data" / "queue")
    job = _queue_job(queue, src)

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        Path(argv[-1]).write_bytes(b"mkv")
        return 0, b"", b""

    monkeypatch.setattr("webmedia_dl.processing.validate_artifact", lambda *_a, **_k: [])
    monkeypatch.setattr("webmedia_dl.processing.require_pass", lambda *_a, **_k: None)
    monkeypatch.setattr("webmedia_dl.processing.probe_media", lambda *_a, **_k: None)
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
    produced = execute_export_plan(
        ExportPlan(job_id=job.job_id, operations=[remux]),
        job_id=job.job_id,
        source=source,
        source_path=store.resolve(source),
        store=store,
        runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
        staging=tmp_path / "stage-probe",
        queue=queue,
        authorize=lambda _cap: None,
    )
    assert any(item.role is ArtifactRole.DERIVATIVE for item, _path in produced)


def test_artifact_dest_exists_skip_and_sha_mismatch(tmp_path: Path, png_bytes: bytes) -> None:
    store = ArtifactStore(tmp_path / "store")
    path = tmp_path / "a.png"
    path.write_bytes(png_bytes)
    first = store.register(
        path,
        role=ArtifactRole.DERIVATIVE,
        media_kind=MediaKind.IMAGE,
        parent_ids=["op-remux"],
        provenance={"job_id": "derived", "operation": "remux"},
    )
    second = store.register(path, role=ArtifactRole.SOURCE, media_kind=MediaKind.IMAGE)
    assert first.artifact_id == second.artifact_id
    assert second.immutable is True
    assert second.role is ArtifactRole.SOURCE
    assert "op-remux" in second.parent_ids
    jobs = [item.get("job_id") for item in second.provenance["occurrences"]]
    assert "derived" in jobs
    corrupted = second.model_copy()
    object.__setattr__(corrupted, "sha256", "00" * 32)
    store._records[second.artifact_id] = corrupted
    with pytest.raises(ArtifactImmutabilityError, match="never mutated"):
        store.register(path, role=ArtifactRole.SOURCE, media_kind=MediaKind.IMAGE)


def test_artifact_reregister_empty_provenance(tmp_path: Path, png_bytes: bytes) -> None:
    store = ArtifactStore(tmp_path / "store")
    path = tmp_path / "a.png"
    path.write_bytes(png_bytes)
    store.register(path, role=ArtifactRole.SOURCE, media_kind=MediaKind.IMAGE, provenance={})
    again = store.register(
        path,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.IMAGE,
        provenance={"job": "2"},
    )
    assert again.provenance.get("occurrences")


def test_artifact_reregister_occurrences_only_and_lineage_cycle(
    tmp_path: Path, png_bytes: bytes
) -> None:
    store = ArtifactStore(tmp_path / "occ")
    path = tmp_path / "a.png"
    path.write_bytes(png_bytes)
    store.register(
        path,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.IMAGE,
        provenance={"occurrences": []},
    )
    store.register(path, role=ArtifactRole.SOURCE, media_kind=MediaKind.IMAGE, provenance=None)
    parent_path = tmp_path / "b.png"
    parent_path.write_bytes(png_bytes + b"b")
    child_path = tmp_path / "c.png"
    child_path.write_bytes(png_bytes + b"c")
    parent = store.register(parent_path, role=ArtifactRole.DERIVATIVE, media_kind=MediaKind.IMAGE)
    child = store.register(
        child_path,
        role=ArtifactRole.DERIVATIVE,
        media_kind=MediaKind.IMAGE,
        parent_ids=[parent.artifact_id],
    )
    store._records[parent.artifact_id] = parent.model_copy(
        update={"parent_ids": [child.artifact_id]}
    )
    ids = [item.artifact_id for item in store.lineage(child.artifact_id)]
    assert child.artifact_id in ids
    assert parent.artifact_id in ids


def test_http_suffix_content_type_is_case_insensitive() -> None:
    assert (
        _http_suffix(
            "https://cdn.example.com/x",
            {"Content-Type": "Video/MP4; charset=binary"},
            b"",
        )
        == ".mp4"
    )
    assert _http_suffix("https://cdn.example.com/clip.mp4/", {}, b"") == ".mp4"
    assert (
        _http_suffix(
            "https://cdn.example.com/x",
            {"Content-Type": "Image/SVG+XML; charset=utf-8"},
            b"",
        )
        == ".svg"
    )
    assert _http_suffix("https://cdn.example.com/icon.svg/", {}, b"") == ".svg"
    assert _http_suffix("https://cdn.example.com/clip.m2ts/", {}, b"") == ".m2ts"
    assert (
        _http_suffix(
            "https://cdn.example.com/x",
            {"Content-Type": "Video/MP2T; charset=binary"},
            b"",
        )
        == ".m2ts"
    )


def test_hls_map_then_follow_on_byterange(tmp_path: Path) -> None:
    playlist = (
        "#EXTM3U\n"
        '#EXT-X-MAP:URI="seg.bin",BYTERANGE="4@0"\n'
        "#EXT-X-BYTERANGE:4\n"
        "seg.bin\n"
        "#EXT-X-BYTERANGE:4\n"
        "seg.bin\n"
    )
    body = {"https://cdn.example.com/live/seg.bin": b"ABCDEFGHIJKL"}

    def fetch(url: str) -> tuple[int, str, bytes]:
        return 200, "video/MP2T", body[url]

    dest = tmp_path / "live.bin"
    record_clear_stream(playlist, "https://cdn.example.com/live/index.m3u8", dest, fetch)
    assert dest.read_bytes() == b"ABCDEFGHIJKL"


def test_dash_segmentbase_sourceurl_and_directory_file_baseurl() -> None:
    text = """
    <MPD><Period>
      <Representation id="v1" bandwidth="800000" mimeType="video/mp4">
        <BaseURL>https://cdn.example.com/dash</BaseURL>
        <BaseURL>video.mp4</BaseURL>
        <SegmentBase indexRange="10-15" mediaRange="16-20">
          <Initialization sourceURL="init.mp4" range="0-9"/>
        </SegmentBase>
      </Representation>
    </Period></MPD>
    """
    parts = recordable_parts(text, "https://cdn.example.com/")
    urls = [part.url for part in parts]
    assert "https://cdn.example.com/dash/init.mp4" in urls
    assert "https://cdn.example.com/dash/video.mp4" in urls
    current = "https://cdn.example.com/"
    body = "<BaseURL>https://cdn.example.com/dash</BaseURL><BaseURL>video.mp4</BaseURL>"
    assert _file_baseurl(body, current) == "https://cdn.example.com/dash/video.mp4"
    cdata_body = (
        "<BaseURL><![CDATA[https://cdn.example.com/dash]]></BaseURL>"
        "<BaseURL><![CDATA[video.mp4]]></BaseURL>"
    )
    assert _file_baseurl(cdata_body, current) == "https://cdn.example.com/dash/video.mp4"
    assert (
        _file_baseurl("<BaseURL>https://cdn.example.com/video123</BaseURL>", current)
        == "https://cdn.example.com/video123"
    )
    assert (
        _file_baseurl(
            "<BaseURL>https://cdn.example.com/dash</BaseURL><BaseURL>video123</BaseURL>",
            current,
        )
        == "https://cdn.example.com/dash/video123"
    )
    assert _file_baseurl("<BaseURL>https://cdn.example.com/dash/</BaseURL>", current) is None
    assert _file_baseurl("<BaseURL>$RepresentationID$</BaseURL>", current) is None


def test_unexpanded_escaped_number_token_is_skipped() -> None:
    text = """
    <MPD><Period>
      <Foo media="$$Number$$.m4s"/>
    </Period></MPD>
    """
    assert recordable_segment_urls(text, "https://cdn.example.com/") == []


def test_segment_timeline_t_override_and_inverted_range() -> None:
    text = """
    <MPD><Period>
      <SegmentTemplate media="s$Number$-t$Time$.m4s" startNumber="3">
        <SegmentTimeline>
          <S t="5000" d="1000" r="1"/>
        </SegmentTimeline>
      </SegmentTemplate>
    </Period></MPD>
    """
    urls = recordable_segment_urls(text, "https://cdn.example.com/")
    assert urls == [
        "https://cdn.example.com/s3-t5000.m4s",
        "https://cdn.example.com/s4-t6000.m4s",
    ]
    numbered = """
    <MPD><Period>
      <SegmentTemplate media="s$Number$-t$Time$.m4s" startNumber="1">
        <SegmentTimeline>
          <S t="5000" d="1000" r="1" n="10"/>
          <S t="7000" d="1000" r="0" n="50"/>
        </SegmentTimeline>
      </SegmentTemplate>
    </Period></MPD>
    """
    assert recordable_segment_urls(numbered, "https://cdn.example.com/") == [
        "https://cdn.example.com/s10-t5000.m4s",
        "https://cdn.example.com/s11-t6000.m4s",
        "https://cdn.example.com/s50-t7000.m4s",
    ]
    invalid_n = """
    <MPD><Period>
      <SegmentTemplate media="s$Number$.m4s" startNumber="3">
        <SegmentTimeline>
          <S t="0" d="1" r="0" n="nope"/>
        </SegmentTimeline>
      </SegmentTemplate>
    </Period></MPD>
    """
    assert recordable_segment_urls(invalid_n, "https://cdn.example.com/") == [
        "https://cdn.example.com/s3.m4s",
    ]
    zero_n = """
    <MPD><Period>
      <SegmentTemplate media="s$Number$.m4s" startNumber="3">
        <SegmentTimeline>
          <S t="0" d="1" r="0" n="0"/>
        </SegmentTimeline>
      </SegmentTemplate>
    </Period></MPD>
    """
    assert recordable_segment_urls(zero_n, "https://cdn.example.com/") == [
        "https://cdn.example.com/s0.m4s",
    ]
    inverted = """
    <MPD><Period>
      <Representation id="v" bandwidth="1" mimeType="video/mp4">
        <BaseURL>clip.mp4</BaseURL>
        <SegmentBase mediaRange="20-10" indexRange="9-3"/>
      </Representation>
    </Period></MPD>
    """
    assert recordable_parts(inverted, "https://cdn.example.com/") == []
    assert _parse_dash_range("0 - 9") == (0, 10)
    assert _parse_dash_range("4 - 7") == (4, 4)
    assert _parse_dash_range("4-") == (4, None)
    assert _parse_dash_range("4 - ") == (4, None)
    assert _parse_dash_range("-4") == (-4, None)
    assert _parse_dash_range("- 4") == (-4, None)
    assert _parse_dash_range("-0") == (None, None)
    assert _parse_dash_range(None) == (None, None)
    assert _parse_dash_range("nope") == (None, None)
    assert _parse_dash_range("9-3") == (None, None)
    assert _parse_byterange(None, default_offset=4) == (4, None)
    assert _parse_byterange("abc", default_offset=4) == (4, None)
    assert _parse_byterange("4@0", default_offset=0) == (0, 4)
    assert _parse_byterange("4 @ 0", default_offset=0) == (0, 4)


def test_period_parts_prefers_video_then_audio() -> None:
    body = """
      <AdaptationSet mimeType="audio/mp4">
        <Representation id="a" bandwidth="128000">
          <BaseURL>audio.m4s</BaseURL>
        </Representation>
      </AdaptationSet>
      <AdaptationSet mimeType="video/mp4">
        <Representation id="v" bandwidth="800000">
          <BaseURL>video.m4s</BaseURL>
        </Representation>
      </AdaptationSet>
    """
    parts = _period_parts(body, "https://cdn.example.com/")
    assert [part.url for part in parts] == ["https://cdn.example.com/video.m4s"]
    audio_only = """
      <AdaptationSet mimeType="audio/mp4">
        <Representation id="a" bandwidth="128000">
          <BaseURL>audio.m4s</BaseURL>
        </Representation>
      </AdaptationSet>
    """
    audio = _period_parts(audio_only, "https://cdn.example.com/")
    assert [part.url for part in audio] == ["https://cdn.example.com/audio.m4s"]


def test_record_kind_streams_writes_separate_dash_kinds(tmp_path: Path) -> None:
    text = """
    <MPD>
      <Period>
        <AdaptationSet mimeType="video/mp4">
          <Representation id="v" bandwidth="800000">
            <BaseURL>video.m4s</BaseURL>
          </Representation>
        </AdaptationSet>
        <AdaptationSet mimeType="audio/mp4">
          <Representation id="a" bandwidth="128000">
            <BaseURL>audio.m4s</BaseURL>
          </Representation>
        </AdaptationSet>
        <AdaptationSet contentType="text" mimeType="text/vtt">
          <Representation id="t1" bandwidth="1000">
            <BaseURL>subs-lo.vtt</BaseURL>
          </Representation>
          <Representation id="t2" bandwidth="2000" codecs="wvtt">
            <BaseURL>subs.vtt</BaseURL>
          </Representation>
        </AdaptationSet>
      </Period>
    </MPD>
    """
    captions = b"WEBVTT\n"
    bodies = {
        "https://cdn.example.com/video.m4s": b"VID",
        "https://cdn.example.com/audio.m4s": b"AUD",
        "https://cdn.example.com/subs.vtt": captions,
    }

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("subs-lo.vtt"):
            raise AssertionError(url)
        return 200, "video/mp4", bodies[url]

    dest = tmp_path / "live.bin"
    recorded = record_kind_streams(text, "https://cdn.example.com/manifest.mpd", dest, fetch)
    kinds = {kind for kind, _path in recorded}
    assert MediaKind.VIDEO in kinds
    assert MediaKind.AUDIO in kinds
    assert MediaKind.SUBTITLE in kinds
    by_kind = {kind: path.read_bytes() for kind, path in recorded}
    assert by_kind[MediaKind.VIDEO] == b"VID"
    assert by_kind[MediaKind.AUDIO] == b"AUD"
    assert by_kind[MediaKind.SUBTITLE] == captions
    sub_path = next(path for kind, path in recorded if kind is MediaKind.SUBTITLE)
    assert sub_path.name == "live-subtitles.bin"
    role = """
    <MPD>
      <Period>
        <AdaptationSet mimeType="video/mp4">
          <Representation id="v" bandwidth="800000">
            <BaseURL>video.m4s</BaseURL>
          </Representation>
        </AdaptationSet>
        <AdaptationSet mimeType="application/mp4">
          <Role schemeIdUri="urn:mpeg:dash:role:2011" value="main"/>
          <Representation id="m" bandwidth="900000">
            <BaseURL>main.m4s</BaseURL>
          </Representation>
        </AdaptationSet>
        <AdaptationSet mimeType="application/mp4">
          <Role schemeIdUri="urn:mpeg:dash:role:2011" value="main"/>
          <Role schemeIdUri="urn:mpeg:dash:role:2011" value="subtitle"/>
          <Representation id="r1" bandwidth="1000">
            <BaseURL>role.vtt</BaseURL>
          </Representation>
        </AdaptationSet>
      </Period>
    </MPD>
    """
    role_captions = b"ROLE\n"
    role_bodies = {
        "https://cdn.example.com/video.m4s": b"VID",
        "https://cdn.example.com/role.vtt": role_captions,
    }

    def role_fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("main.m4s"):
            raise AssertionError(url)
        return 200, "video/mp4", role_bodies[url]

    role_recorded = record_kind_streams(
        role, "https://cdn.example.com/manifest.mpd", tmp_path / "role.bin", role_fetch
    )
    role_by_kind = {kind: path.read_bytes() for kind, path in role_recorded}
    assert MediaKind.VIDEO in role_by_kind
    assert MediaKind.SUBTITLE in role_by_kind
    assert role_by_kind[MediaKind.SUBTITLE] == role_captions
    component = """
    <MPD>
      <Period>
        <AdaptationSet mimeType="video/mp4">
          <Representation id="v" bandwidth="800000">
            <BaseURL>video.m4s</BaseURL>
          </Representation>
        </AdaptationSet>
        <AdaptationSet mimeType="application/mp4">
          <ContentComponent contentType="video" id="vcc"/>
          <ContentComponent contentType="text" id="cc1"/>
          <Representation id="c1" bandwidth="500">
            <BaseURL>cc.vtt</BaseURL>
          </Representation>
        </AdaptationSet>
      </Period>
    </MPD>
    """
    cc_captions = b"CC\n"
    cc_bodies = {
        "https://cdn.example.com/video.m4s": b"VID",
        "https://cdn.example.com/cc.vtt": cc_captions,
    }

    def cc_fetch(url: str) -> tuple[int, str, bytes]:
        return 200, "video/mp4", cc_bodies[url]

    cc_recorded = record_kind_streams(
        component, "https://cdn.example.com/manifest.mpd", tmp_path / "cc.bin", cc_fetch
    )
    cc_by_kind = {kind: path.read_bytes() for kind, path in cc_recorded}
    assert cc_by_kind[MediaKind.SUBTITLE] == cc_captions


def test_live_poll_should_stop_and_hls_audio_http_error(tmp_path: Path) -> None:
    playlist = "#EXTM3U\n#EXTINF:1,\na.ts\n"
    dest = tmp_path / "live.ts"

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("a.ts"):
            return 200, "video/MP2T", b"AAAA"
        raise AssertionError(url)

    def should_stop() -> None:
        if dest.exists() and dest.stat().st_size > 0:
            raise PauseRequested("poll stop")

    with pytest.raises(PauseRequested, match="poll stop"):
        record_clear_stream(
            playlist,
            "https://cdn.example.com/live.m3u8",
            dest,
            fetch,
            live_polls=3,
            should_stop=should_stop,
        )
    assert dest.read_bytes() == b"AAAA"

    master = (
        "#EXTM3U\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",URI="audio.m3u8"\n'
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",URI="audio.m3u8"\n'
        '#EXT-X-MEDIA:TYPE=SUBTITLES,URI="subs.vtt"\n'
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=1,AUDIO="aac"\n'
        "video.m3u8\n"
    )
    assert hls_audio_playlist_urls(master, "https://cdn.example.com/") == [
        "https://cdn.example.com/audio.m3u8"
    ]
    assert hls_subtitle_playlist_urls(master, "https://cdn.example.com/") == [
        "https://cdn.example.com/subs.vtt"
    ]

    def audio_fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("video.m3u8"):
            return 200, "application/vnd.apple.mpegurl", b"#EXTM3U\n#EXTINF:1,\nv.ts\n"
        if url.endswith("v.ts"):
            return 200, "video/MP2T", b"V"
        if url.endswith("audio.m3u8"):
            return 400, "text/plain", b"nope"
        return 200, "application/vnd.apple.mpegurl", master.encode()

    with pytest.raises(DiscoveryError, match="audio playlist"):
        record_kind_streams(
            master,
            "https://cdn.example.com/master.m3u8",
            tmp_path / "mux.bin",
            audio_fetch,
        )
    captions = b"WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHi\n"

    def sidecar_fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("video.m3u8"):
            return 200, "application/vnd.apple.mpegurl", b"#EXTM3U\n#EXTINF:1,\nv.ts\n"
        if url.endswith("v.ts"):
            return 200, "video/MP2T", b"V"
        if url.endswith("audio.m3u8"):
            return 200, "application/vnd.apple.mpegurl", b"#EXTM3U\n#EXTINF:1,\na.ts\n"
        if url.endswith("a.ts"):
            return 200, "audio/MP2T", b"A"
        if url.endswith("subs.vtt"):
            return 200, "text/vtt", captions
        return 200, "application/vnd.apple.mpegurl", master.encode()

    muxed = record_kind_streams(
        master,
        "https://cdn.example.com/master.m3u8",
        tmp_path / "mux-ok.bin",
        sidecar_fetch,
    )
    mux_payloads = {kind: path.read_bytes() for kind, path in muxed}
    assert mux_payloads[MediaKind.VIDEO] == b"V"
    assert mux_payloads[MediaKind.AUDIO] == b"A"
    assert mux_payloads[MediaKind.SUBTITLE] == captions


def test_discovery_picture_embed_gallery_and_jsonld_list() -> None:
    html = """
    <html>
      <head>
        <title>Album</title>
        <meta property="og:image:url" content="https://cdn.example.com/og.png">
        <meta property="og:image:secure_url" content="https://cdn.example.com/og-secure.png">
        <meta name="twitter:image" content="https://cdn.example.com/tw.png">
        <link rel="preload" type="audio/mpeg" href="https://cdn.example.com/x.mp3">
        <script type="application/ld+json">
          {"@type": ["Movie", "Broadcast"], "contentUrl": [
            "https://cdn.example.com/a.mp4",
            "javascript:alert(1)"
          ]}
        </script>
      </head>
      <body>
        <picture>
          <source type="image/webp" srcset="https://cdn.example.com/hero.webp 1x">
          <img data-src="https://cdn.example.com/hero.png">
        </picture>
        <img src="https://cdn.example.com/one.jpg">
        <img src="https://cdn.example.com/two.jpg">
        <img src="https://cdn.example.com/three.jpg">
        <embed src="https://cdn.example.com/player.mp4">
        <object data="https://cdn.example.com/other.mp4"></object>
        <amp-video src="https://cdn.example.com/amp.mp4"></amp-video>
        <amp-audio src="https://cdn.example.com/amp.m4a"></amp-audio>
        <a href="javascript:void(0)">skip</a>
      </body>
    </html>
    """
    profile = get_profile("personal-full")
    found = discover(_page_source(), profile, html=html)
    urls = [item.retrieval_urls[0] for item in found if item.retrieval_urls]
    kinds = {item.retrieval_urls[0]: item.media_kind for item in found if item.retrieval_urls}
    assert "https://cdn.example.com/hero.webp" in urls
    assert "https://cdn.example.com/hero.png" in urls
    assert "https://cdn.example.com/og-secure.png" in urls
    assert kinds["https://cdn.example.com/og-secure.png"] is MediaKind.IMAGE
    assert "https://cdn.example.com/player.mp4" in urls
    assert "https://cdn.example.com/other.mp4" in urls
    assert "https://cdn.example.com/amp.mp4" in urls
    assert "https://cdn.example.com/amp.m4a" in urls
    assert "https://cdn.example.com/x.mp3" in urls
    assert "https://cdn.example.com/a.mp4" in urls
    assert kinds["https://cdn.example.com/a.mp4"] is MediaKind.VIDEO
    assert kinds["https://cdn.example.com/amp.m4a"] is MediaKind.AUDIO
    assert not any(item.startswith("javascript:") for item in urls)
    gallery_html = """
    <html><body>
      <img src="https://cdn.example.com/one.jpg">
      <img src="https://cdn.example.com/two.jpg">
      <img src="https://cdn.example.com/three.jpg">
    </body></html>
    """
    gallery = discover(_page_source(), profile, html=gallery_html)
    assert any(item.media_kind is MediaKind.GALLERY for item in gallery)


def test_manifest_json_live_drm_and_empty() -> None:
    source = _page_source()
    assert candidates_from_manifest_json(source, b"") == []
    assert candidates_from_manifest_json(source, b"[]") == []
    live = candidates_from_manifest_json(
        source,
        json.dumps(
            {
                "url": "https://cdn.example.com/live.m3u8",
                "is_live": True,
                "title": "https://cdn.example.com/live.m3u8",
                "formats": [
                    {"format_id": ""},
                    "skip",
                    {
                        "format_id": "91",
                        "vcodec": "none",
                        "acodec": "mp4a",
                        "has_drm": True,
                        "tbr": 128,
                    },
                ],
            }
        ).encode(),
    )
    assert live[0].media_kind is MediaKind.LIVE_STREAM
    assert live[0].title_display is None
    assert any(item.drm for item in live[0].alternatives)
    assert any(signal.startswith("format-drm:") for signal in live[0].drm_signals)


def test_job_detail_artifact_ids_from_history(tmp_path: Path, png_bytes: bytes) -> None:
    app_api = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app_api)
    headers = {"Authorization": f"Bearer {token}"}
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    queued = client.post(
        "/v1/jobs",
        headers=headers,
        json={"locator": str(media), "wait": False},
    )
    queued_id = queued.json()["job"]["job_id"]
    empty = client.get(f"/v1/jobs/{queued_id}", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["artifact_ids"] == []
    created = client.post("/v1/jobs", headers=headers, json={"locator": str(media)})
    job_id = created.json()["job"]["job_id"]
    detail = client.get(f"/v1/jobs/{job_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["artifact_ids"]


def test_cli_and_schema_export_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["webmedia-dl", "alias-note"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_path(cli_mod.__file__, run_name="__main__")
    assert exc.value.code in {0, None}

    monkeypatch.setattr("webmedia_dl.paths.repo_root", lambda: tmp_path)
    runpy.run_module("webmedia_dl.schema_export", run_name="__main__")
    captured = capsys.readouterr()
    assert "index.json" in captured.out
    assert (tmp_path / "schemas" / "index.json").is_file()
