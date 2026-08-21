import shutil
import subprocess
from pathlib import Path

import pytest

from webmedia_dl.domain.enums import JobState
from webmedia_dl.domain.models import ExportIntent
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.providers import ProviderRequest, ProviderRuntime, default_subprocess_run


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
