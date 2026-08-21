from pathlib import Path
from time import sleep

import pytest

from webmedia_dl.dispatcher import QueueDispatcher
from webmedia_dl.domain.enums import JobState
from webmedia_dl.pipeline import Pipeline


def test_dispatcher_runs_accepted_job(tmp_data: Path, png_bytes: bytes) -> None:
    pipeline = Pipeline(data_dir=tmp_data)
    media = tmp_data / "held.png"
    media.write_bytes(png_bytes)
    job = pipeline.submit(str(media), wait=False)
    assert job.state is JobState.ACCEPTED
    dispatcher = QueueDispatcher(pipeline, interval=0.05)
    dispatcher.start()
    dispatcher.start()
    try:
        current = pipeline.job(job.job_id)
        for _ in range(40):
            if current.state is JobState.COMPLETED:
                break
            sleep(0.05)
            current = pipeline.job(job.job_id)
        assert current.state is JobState.COMPLETED
    finally:
        dispatcher.stop()


def test_dispatcher_keeps_running_after_run_next_error(
    tmp_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipeline = Pipeline(data_dir=tmp_data)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("dispatcher")

    monkeypatch.setattr(pipeline, "run_next", boom)
    dispatcher = QueueDispatcher(pipeline, interval=0.01)
    dispatcher.start()
    sleep(0.04)
    dispatcher.stop()
    assert dispatcher._thread is None
