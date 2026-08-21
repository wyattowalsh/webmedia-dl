from pathlib import Path
from time import sleep

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
