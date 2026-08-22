import shutil
import subprocess
from pathlib import Path

import pytest

from webmedia_dl.artifacts import ArtifactStore
from webmedia_dl.domain.enums import ArtifactRole, IntakeKind, JobState, MediaKind
from webmedia_dl.domain.models import ExportIntent, ExportPlan, Job, MediaSource, Operation
from webmedia_dl.errors import ProviderPolicyError, RequiredOperationFailed
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.processing import bounded_staging_output, execute_export_plan
from webmedia_dl.providers import ProviderRequest, ProviderRuntime, default_subprocess_run
from webmedia_dl.queue import QueueStore


def test_magick_configure_path_is_set(tmp_path: Path) -> None:
    code, stdout, _stderr = default_subprocess_run(
        [
            "python3",
            "-c",
            "import os; print(os.environ.get('MAGICK_CONFIGURE_PATH', ''))",
        ],
        tmp_path,
    )
    assert code == 0
    assert "imagemagick-runtime" in stdout.decode()
    policy = Path(stdout.decode().strip()) / "policy.xml"
    assert policy.is_file()


def test_remux_argv_uses_stream_copy(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        captured.append(argv)
        Path(argv[-1]).write_bytes(b"mkv")
        return 0, b"", b""

    runtime = ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run)
    runtime.execute(
        ProviderRequest(
            provider_id="ffmpeg",
            capability_id="process.ffmpeg.remux",
            typed_inputs={"input": "/tmp/a.mp4", "output": str(tmp_path / "a.mkv")},
        ),
        tmp_path,
    )
    argv = captured[0]
    assert "-c" in argv
    assert "copy" in argv
    assert "--enable-file-urls" not in argv


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_pipeline_executes_ffmpeg_remux(tmp_path: Path) -> None:
    src = tmp_path / "clip.mp4"
    completed = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=16x16:d=0.2",
            "-c:v",
            "mpeg4",
            str(src),
        ],
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        pytest.skip(completed.stderr.decode()[:200])
    pipeline = Pipeline(data_dir=tmp_path / "data")
    job = pipeline.submit(str(src), intent=ExportIntent(container_preference="mkv"))
    assert job.state is JobState.COMPLETED
    types = [event.type.value for event in pipeline.queue.events_for(job.job_id)]
    assert "operation.completed" in types
    assert any(
        event.payload.get("operation_id") == "remux"
        for event in pipeline.queue.events_for(job.job_id)
    )


def test_bounded_staging_output_stays_under_staging(tmp_path: Path) -> None:
    staging = tmp_path / "stage"
    staging.mkdir()
    output = bounded_staging_output(staging, "remux", "mkv")
    assert output == (staging / "remux.mkv").resolve()
    assert output.is_relative_to(staging.resolve())


@pytest.mark.parametrize(
    "container",
    [
        "../../../../tmp/wmprobe3/ESC.mkv",
        "/tmp/escape",
        "mkv; rm -rf /",
        "mkv\nbad",
        "",
        "verylongcontainer",
    ],
)
def test_bounded_staging_output_refuses_hostile_container(tmp_path: Path, container: str) -> None:
    staging = tmp_path / "stage"
    staging.mkdir()
    with pytest.raises(ProviderPolicyError, match="allowed extension"):
        bounded_staging_output(staging, "remux", container)


def test_bounded_staging_output_refuses_operation_id_escape(tmp_path: Path) -> None:
    staging = tmp_path / "stage"
    staging.mkdir()
    with pytest.raises(ProviderPolicyError, match="escaped staging"):
        bounded_staging_output(staging, "../escape", "mkv")


def test_execute_export_plan_refuses_hostile_container_before_provider(tmp_path: Path) -> None:
    src = tmp_path / "clip.bin"
    src.write_bytes(b"bytes")
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
    calls: list[list[str]] = []

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        calls.append(argv)
        return 0, b"", b""

    remux = Operation(
        operation_id="remux",
        op_type="ffmpeg.remux",
        capability_id="process.ffmpeg.remux",
        input_artifact_ids=[source.artifact_id],
        output_role=ArtifactRole.DERIVATIVE,
        loss_class="container_only",
        validator_ids=[],
        typed_inputs={"container": "../../../../tmp/escape"},
    )
    with pytest.raises(RequiredOperationFailed, match="allowed extension"):
        execute_export_plan(
            ExportPlan(job_id=job.job_id, operations=[remux]),
            job_id=job.job_id,
            source=source,
            source_path=store.resolve(source),
            store=store,
            runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
            staging=tmp_path / "stage",
            queue=queue,
            authorize=lambda _cap: None,
        )
    assert calls == []
