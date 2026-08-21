from pathlib import Path

import pytest

from webmedia_dl.domain.enums import ArtifactRole, JobState, Surface
from webmedia_dl.domain.models import Job
from webmedia_dl.envelope import open_payload, seal_payload
from webmedia_dl.errors import CancelledError, DelegationDenied
from webmedia_dl.intake import normalize_source
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.providers import ProviderRuntime


def test_envelope_roundtrip_and_tamper() -> None:
    key = "ab" * 32
    sealed = seal_payload(key, {"locator": "https://example.com/a.png"})
    opened = open_payload(key, sealed)
    assert opened["locator"] == "https://example.com/a.png"
    assert bytes.fromhex(sealed["ciphertext"]) != b'{"locator":"https://example.com/a.png"}'
    sealed["mac"] = "00" * 32
    with pytest.raises(DelegationDenied):
        open_payload(key, sealed)


def test_cancel_queued_job(tmp_data: Path, png_bytes: bytes) -> None:
    pipeline = Pipeline(data_dir=tmp_data)
    media = tmp_data / "queued.png"
    media.write_bytes(png_bytes)
    source = normalize_source(str(media), surface=Surface.CLI, policy_profile_id="personal-full")
    job = Job(source=source, policy_profile_id="personal-full", worker_id="local-macos")
    pipeline.queue.put_job(job)
    cancelled = pipeline.cancel(job.job_id)
    assert cancelled.state is JobState.CANCELLED
    with pytest.raises(CancelledError):
        pipeline.cancel(job.job_id)


def test_quarantine_on_failed_provider(tmp_data: Path, ytdlp_run_fail) -> None:
    runtime = ProviderRuntime(
        which=lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None,
        run=ytdlp_run_fail,
        http_get=lambda url: (404, {}, b""),
    )
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit("https://example.com/watch", html="<html><title>x</title></html>")
    assert job.state is JobState.FAILED
    quarantined = [
        item for item in pipeline.store._records.values() if item.role is ArtifactRole.QUARANTINE
    ]
    assert quarantined
    types = [event.type.value for event in pipeline.queue.events_for(job.job_id)]
    assert "acquisition.quarantine" in types
