"""Acquire, validation, processing, and worker-API fail-closed gates."""

from __future__ import annotations

import signal
import subprocess
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from webmedia_dl.artifacts import ArtifactStore
from webmedia_dl.discovery import discover
from webmedia_dl.domain.enums import ArtifactRole, IntakeKind, JobState, MediaKind, Surface
from webmedia_dl.domain.models import (
    ExportIntent,
    ExportPlan,
    Job,
    MediaProbe,
    MediaSource,
    Operation,
    StreamInfo,
)
from webmedia_dl.errors import (
    DrmRefused,
    RequiredOperationFailed,
    ValidationFailed,
)
from webmedia_dl.intake import normalize_source
from webmedia_dl.live import _expand_dash_template
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import get_profile
from webmedia_dl.processing import execute_export_plan
from webmedia_dl.providers import ProviderRuntime, _http_suffix, _terminate_process
from webmedia_dl.queue import QueueStore
from webmedia_dl.service import create_app, load_or_create_token


def test_cancel_during_acquire_raises_closed(tmp_data: Path, png_bytes: bytes) -> None:
    html = """
    <html><body>
      <video src="https://cdn.example.com/clip.mp4"></video>
      <img src="https://cdn.example.com/hero.png">
    </body></html>
    """
    holders: dict[str, object] = {}

    def http_get(url: str) -> tuple[int, dict[str, str], bytes]:
        pipeline = cast(Pipeline, holders["pipeline"])
        job_id = cast(UUID, holders["job_id"])
        if url.endswith(".mp4"):
            pipeline.cancel(job_id)
        return 200, {"content-type": "image/png"}, png_bytes

    pipeline = Pipeline(data_dir=tmp_data, runtime=ProviderRuntime(http_get=http_get))
    holders["pipeline"] = pipeline
    job = pipeline.submit("https://example.com/mixed", html=html, wait=False)
    holders["job_id"] = job.job_id
    cancelled = pipeline.run_next()
    assert cancelled is not None
    assert cancelled.state is JobState.CANCELLED


def test_all_kinds_fail_reraises_last_error(tmp_data: Path) -> None:
    html = """
    <html><body>
      <video src="https://cdn.example.com/clip.mp4"></video>
      <img src="https://cdn.example.com/hero.png">
    </body></html>
    """

    def boom(_url: str) -> tuple[int, dict[str, str], bytes]:
        raise DrmRefused("cenc")

    def boom_run(_argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        raise DrmRefused("widevine")

    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(
            which=lambda name: f"/usr/bin/{name}" if name == "yt-dlp" else None,
            run=boom_run,
            http_get=boom,
        ),
    )
    job = pipeline.submit("https://example.com/mixed", html=html)
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "produced no source artifact" not in job.error.lower()
    assert "cenc" in job.error or "widevine" in job.error or "drm" in job.error.lower()


def test_source_validation_failure_still_publishes_derivative(
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
        if artifact.role is ArtifactRole.SOURCE:
            raise ValidationFailed("source rejected")
        return validate_artifact(job_id, artifact, path)

    monkeypatch.setattr("webmedia_dl.pipeline.validate_artifact", fake_validate)
    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
    )
    job = pipeline.submit(str(media), intent=ExportIntent(container_preference="mkv"))
    assert job.state is JobState.COMPLETED
    roles = {item.role for item in pipeline.store.list_artifacts()}
    assert ArtifactRole.DERIVATIVE in roles


def test_processing_rewrites_source_output_role_and_missing_inputs(
    tmp_path: Path, png_bytes: bytes, pass_container_probe
) -> None:
    src = tmp_path / "source.mp4"
    src.write_bytes(png_bytes)
    store = ArtifactStore(tmp_path / "data")
    source = store.register(
        src, role=ArtifactRole.SOURCE, media_kind=MediaKind.VIDEO, container="mp4"
    )
    queue = QueueStore(tmp_path / "data" / "queue")
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

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        Path(argv[-1]).write_bytes(b"mkv")
        return 0, b"", b""

    remux_as_source = Operation(
        operation_id="remux",
        op_type="ffmpeg.remux",
        capability_id="process.ffmpeg.remux",
        input_artifact_ids=[],
        output_role=ArtifactRole.SOURCE,
        loss_class="container_only",
        validator_ids=[],
        typed_inputs={"container": "mkv"},
    )
    produced = execute_export_plan(
        ExportPlan(job_id=job.job_id, operations=[remux_as_source]),
        job_id=job.job_id,
        source=source,
        source_path=store.resolve(source),
        store=store,
        runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
        staging=tmp_path / "stage",
        queue=queue,
        authorize=lambda _cap: None,
    )
    roles = {item.role for item, _path in produced}
    assert ArtifactRole.DERIVATIVE in roles

    ghost = Operation(
        operation_id="ghost",
        op_type="ffmpeg.remux",
        capability_id="process.ffmpeg.remux",
        input_artifact_ids=["missing-op"],
        output_role=ArtifactRole.DERIVATIVE,
        loss_class="container_only",
        validator_ids=[],
        typed_inputs={"container": "mkv"},
    )
    with pytest.raises(RequiredOperationFailed, match="missing inputs"):
        execute_export_plan(
            ExportPlan(job_id=job.job_id, operations=[ghost]),
            job_id=job.job_id,
            source=source,
            source_path=store.resolve(source),
            store=store,
            runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
            staging=tmp_path / "stage-ghost",
            queue=queue,
            authorize=lambda _cap: None,
        )


def test_processing_skips_compound_and_successful_remux_transcode(
    tmp_path: Path, png_bytes: bytes, pass_container_probe
) -> None:
    src = tmp_path / "source.mp4"
    src.write_bytes(png_bytes)
    store = ArtifactStore(tmp_path / "data")
    source = store.register(
        src, role=ArtifactRole.SOURCE, media_kind=MediaKind.VIDEO, container="mp4"
    )
    queue = QueueStore(tmp_path / "data" / "queue")
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
    transcode = Operation(
        operation_id="transcode",
        op_type="ffmpeg.transcode",
        capability_id="process.ffmpeg.transcode",
        input_artifact_ids=[source.artifact_id],
        output_role=ArtifactRole.DERIVATIVE,
        loss_class="lossy_transcode",
        validator_ids=[],
        typed_inputs={"container": "mp4"},
    )
    calls: list[str] = []

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        calls.append(Path(argv[-1]).name)
        Path(argv[-1]).write_bytes(b"out")
        return 0, b"", b""

    execute_export_plan(
        ExportPlan(job_id=job.job_id, operations=[remux]),
        job_id=job.job_id,
        source=source,
        source_path=store.resolve(source),
        store=store,
        runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
        staging=tmp_path / "stage-skip",
        queue=queue,
        authorize=lambda _cap: None,
        skip_operation_ids={f"{source.artifact_id}:remux"},
    )
    assert calls == []

    calls.clear()
    execute_export_plan(
        ExportPlan(job_id=job.job_id, operations=[remux, transcode]),
        job_id=job.job_id,
        source=source,
        source_path=store.resolve(source),
        store=store,
        runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
        staging=tmp_path / "stage-both",
        queue=queue,
        authorize=lambda _cap: None,
    )
    assert calls == ["remux.mkv"]


def test_ffmpeg_probe_drm_fails_closed(
    tmp_path: Path, png_bytes: bytes, pass_container_probe, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "source.mp4"
    src.write_bytes(png_bytes)
    store = ArtifactStore(tmp_path / "data")
    source = store.register(
        src, role=ArtifactRole.SOURCE, media_kind=MediaKind.VIDEO, container="mp4"
    )
    queue = QueueStore(tmp_path / "data" / "queue")
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

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        Path(argv[-1]).write_bytes(b"mkv")
        return 0, b"", b""

    def encrypted_probe(_path: Path, **_kwargs: object) -> MediaProbe:
        return MediaProbe(
            candidate_id=uuid4(),
            container="mkv",
            format_names="matroska,webm",
            streams=[StreamInfo(index=0, codec="h264", media_kind=MediaKind.VIDEO, encrypted=True)],
            drm_signals=["probe:encrypted-stream"],
        )

    monkeypatch.setattr("webmedia_dl.processing.probe_media", encrypted_probe)
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
    with pytest.raises(RequiredOperationFailed, match="drm-clear"):
        execute_export_plan(
            ExportPlan(job_id=job.job_id, operations=[remux]),
            job_id=job.job_id,
            source=source,
            source_path=store.resolve(source),
            store=store,
            runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
            staging=tmp_path / "stage-drm",
            queue=queue,
            authorize=lambda _cap: None,
        )


def test_lineage_skips_dangling_parent_and_derivative_can_mutate(
    tmp_path: Path, png_bytes: bytes
) -> None:
    store = ArtifactStore(tmp_path / "store")
    src = tmp_path / "a.png"
    src.write_bytes(png_bytes)
    child = store.register(
        src,
        role=ArtifactRole.DERIVATIVE,
        media_kind=MediaKind.IMAGE,
        parent_ids=["sha256:does-not-exist"],
    )
    lineage = store.lineage(child.artifact_id)
    assert [item.artifact_id for item in lineage] == [child.artifact_id]
    store.mutate_source(child.artifact_id, png_bytes + b"x")
    assert store.resolve(child).read_bytes() == png_bytes + b"x"


def test_http_suffix_png_magic_and_unexpanded_number_token() -> None:
    assert _http_suffix("https://cdn.example.com/x", {}, b"\x89PNG\r\n\x1a\nxxxx") == ".png"
    assert "$Number$" in _expand_dash_template("seg$Number$.m4s", number=None)


def test_discovery_source_mime_video() -> None:
    html = (
        '<video><source type="video/mp4" src="https://cdn.example.com/plain"></video>'
        '<video><source src="https://cdn.example.com/untyped"></video>'
        '<audio><source src="https://cdn.example.com/untyped-audio"></audio>'
    )
    source = normalize_source(
        "https://example.com/page",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )
    found = discover(source, get_profile("personal-full"), html=html)
    kinds = {item.retrieval_urls[0]: item.media_kind for item in found if item.retrieval_urls}
    assert kinds["https://cdn.example.com/plain"] is MediaKind.VIDEO
    assert kinds["https://cdn.example.com/untyped"] is MediaKind.VIDEO
    assert kinds["https://cdn.example.com/untyped-audio"] is MediaKind.AUDIO


def test_tracked_run_deadline_returns_124(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    proc = MagicMock()
    proc.pid = 9
    proc.returncode = 124

    def communicate(timeout: float | None = None) -> tuple[bytes, bytes]:
        if timeout is not None:
            raise subprocess.TimeoutExpired(cmd="sleep", timeout=timeout)
        return b"", b""

    proc.communicate.side_effect = communicate
    monkeypatch.setattr("webmedia_dl.providers.subprocess.Popen", lambda *_a, **_k: proc)
    monkeypatch.setattr("webmedia_dl.providers._terminate_process", lambda _proc: None)
    runtime = ProviderRuntime()
    code, _out, _err = runtime._tracked_run(["sleep", "1"], tmp_path)
    assert code == 124


def test_terminate_process_sigkill_lookup_error(monkeypatch: pytest.MonkeyPatch) -> None:
    live = MagicMock()
    live.poll.return_value = None
    live.pid = 11
    live.wait.side_effect = subprocess.TimeoutExpired(cmd="sleep", timeout=2)

    def killpg(_pid: int, sig: int) -> None:
        if sig == signal.SIGKILL:
            raise ProcessLookupError

    monkeypatch.setattr("webmedia_dl.providers.os.killpg", killpg)
    _terminate_process(cast(subprocess.Popen[bytes], live))
    live.kill.assert_called()


def test_service_lists_jobs_plan_pairing_and_empty_run_next(
    tmp_path: Path, png_bytes: bytes
) -> None:
    app_api = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app_api)
    mac = {"Authorization": f"Bearer {token}"}
    empty = client.post("/v1/queue/run-next", headers=mac)
    assert empty.status_code == 200
    assert empty.json()["job"] is None
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    created = client.post("/v1/jobs", headers=mac, json={"locator": str(media)})
    assert created.status_code == 200
    listed = client.get("/v1/jobs", headers=mac)
    assert listed.status_code == 200
    assert any(item["job_id"] == created.json()["job"]["job_id"] for item in listed.json())
    pair = client.post("/v1/pair", headers=mac)
    pairing_id = pair.json()["pairing_id"]
    confirmed = client.post("/v1/pair/confirm", headers=mac, json={"pairing_id": pairing_id})
    session_key = confirmed.json()["session_key"]
    planned = client.post(
        "/v1/plan",
        json={"locator": str(media)},
        headers={
            "X-WebMedia-Pairing": pairing_id,
            "X-WebMedia-Session": session_key,
        },
    )
    assert planned.status_code == 200
    assert planned.json()["acquired"] is False
    assert planned.json()["client_profile"] == "personal-restricted"
