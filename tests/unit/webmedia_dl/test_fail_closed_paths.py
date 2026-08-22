"""Linux-provable fail-closed paths for queue, pipeline, live, processing, and the worker API."""

from __future__ import annotations

import signal
import sqlite3
import subprocess
from pathlib import Path
from typing import Any, cast
from unittest.mock import MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from typer.testing import CliRunner

from webmedia_dl.artifacts import ArtifactStore
from webmedia_dl.cli import app
from webmedia_dl.discovery import discover
from webmedia_dl.domain.enums import (
    ArtifactRole,
    EventType,
    IntakeKind,
    JobState,
    MediaKind,
    Surface,
)
from webmedia_dl.domain.models import (
    Artifact,
    ExportIntent,
    ExportPlan,
    Job,
    MediaProbe,
    MediaSource,
    Operation,
    StreamInfo,
)
from webmedia_dl.errors import (
    ArtifactImmutabilityError,
    CancelledError,
    PauseRequested,
    ProviderPolicyError,
    RequiredOperationFailed,
    ValidationFailed,
)
from webmedia_dl.identity import artifact_id_for_digest, sha256_file
from webmedia_dl.intake import normalize_source
from webmedia_dl.live import (
    ManifestPart,
    _expand_dash_template,
    _format_token,
    _iso8601_duration_seconds,
    _period_parts,
    record_clear_stream,
    record_kind_streams,
    recordable_segment_urls,
)
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import get_profile
from webmedia_dl.processing import execute_export_plan
from webmedia_dl.providers import (
    ProviderRequest,
    ProviderRuntime,
    _http_suffix,
    _terminate_process,
)
from webmedia_dl.queue import QueueStore
from webmedia_dl.service import create_app, load_or_create_token, serve_worker

runner = CliRunner()


def _png(tmp_path: Path, png_bytes: bytes, name: str = "hero.png") -> Path:
    media = tmp_path / name
    media.write_bytes(png_bytes)
    return media


def test_queue_migrates_legacy_context_columns(tmp_path: Path) -> None:
    root = tmp_path / "legacy-queue"
    root.mkdir()
    db = root / "queue.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE jobs (
            job_id TEXT PRIMARY KEY,
            state TEXT,
            payload TEXT,
            created_at TEXT
        );
        CREATE TABLE events (
            event_id TEXT PRIMARY KEY,
            job_id TEXT,
            sequence INTEGER,
            payload TEXT
        );
        CREATE TABLE queue_control (
            id INTEGER PRIMARY KEY,
            paused INTEGER,
            seq INTEGER
        );
        CREATE TABLE job_context (
            job_id TEXT PRIMARY KEY,
            html TEXT,
            cookies TEXT,
            evidence_json TEXT DEFAULT '[]'
        );
        """
    )
    conn.commit()
    conn.close()
    store = QueueStore(root)
    with store.engine.connect() as engine_conn:
        names = {row[1] for row in engine_conn.exec_driver_sql("PRAGMA table_info(job_context)")}
    assert "checkpoint_json" in names
    assert "pause_requested" in names
    assert "cancel_requested" in names


def test_queue_control_emit_pause_checkpoint_and_invalid_json(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = _png(tmp_path, png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    store = pipeline.queue
    with store.engine.begin() as conn:
        conn.execute(text("DELETE FROM queue_control"))
    event = store.emit(job.job_id, store.events_for(job.job_id)[0].type, {"ok": True})
    assert event.sequence >= 1
    with store.engine.begin() as conn:
        conn.execute(text("DELETE FROM queue_control"))
    assert store.set_paused(True) is True
    assert store.is_paused() is True
    store.set_paused(False)
    orphan = uuid4()
    store.put_checkpoint(orphan, {"stage": "acquired"})
    assert store.get_context(orphan).checkpoint == {"stage": "acquired"}
    store.put_context(job.job_id, html="<html/>", cookies=None, evidence=None)
    store.put_context(job.job_id, html="<p>updated</p>", cookies="grant", evidence=None)
    assert store.get_context(job.job_id).html == "<p>updated</p>"
    with store.engine.begin() as conn:
        conn.execute(
            text("UPDATE job_context SET checkpoint_json = :payload WHERE job_id = :job_id"),
            {"payload": "not-json", "job_id": str(job.job_id)},
        )
    assert store.get_context(job.job_id).checkpoint == {}


def test_next_runnable_skips_non_accepted_jobs(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = _png(tmp_path, png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    failed = pipeline.submit(
        "https://example.com/none",
        html="<html><body>no media</body></html>",
        wait=True,
    )
    assert failed.state is JobState.FAILED
    held = pipeline.submit(str(media), wait=False)
    nxt = pipeline.queue.next_runnable()
    assert nxt is not None
    assert nxt.job_id == held.job_id
    empty = Pipeline(data_dir=tmp_data / "empty")
    only_failed = empty.submit(
        "https://example.com/none",
        html="<html><body>no media</body></html>",
    )
    assert only_failed.state is JobState.FAILED
    assert empty.queue.next_runnable() is None


def test_discovery_without_candidates_fails_job(
    tmp_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("webmedia_dl.pipeline.discover", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        "webmedia_dl.pipeline.Pipeline._manifest_candidates",
        lambda *_args, **_kwargs: [],
    )
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit("https://example.com/page", html="<html></html>")
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "no candidates" in job.error.lower()


def test_claim_next_returns_none_after_cas_misses(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = _png(tmp_path, png_bytes, "held.png")
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    store = pipeline.queue
    with store.engine.begin() as conn:
        conn.exec_driver_sql(
            """
            CREATE TRIGGER jobs_cas_miss BEFORE UPDATE ON jobs
            BEGIN
              SELECT RAISE(IGNORE);
            END
            """
        )
    assert store.claim_next() is None
    assert store.get_job(job.job_id).state is JobState.ACCEPTED


def test_pipeline_skips_missing_checkpoint_artifacts_and_preview(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = _png(tmp_path, png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    source = pipeline.store.register(
        media,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.IMAGE,
        provenance={"job_id": str(job.job_id)},
    )
    preview_path = tmp_path / "preview.jpg"
    preview_path.write_bytes(png_bytes + b"preview")
    preview = pipeline.store.register(
        preview_path,
        role=ArtifactRole.PREVIEW,
        media_kind=MediaKind.IMAGE,
        provenance={"job_id": str(job.job_id)},
    )
    pipeline.queue.put_checkpoint(
        job.job_id,
        {
            "stage": "exported",
            "source_ids": ["sha256:missing", source.artifact_id],
            "produced_ids": ["sha256:missing", preview.artifact_id],
            "operation_artifacts": {"keep-original": "sha256:missing"},
            "acquired_kinds": ["image"],
        },
    )
    result = pipeline.run_next()
    assert result is not None
    assert result.state is JobState.FAILED
    assert result.error is not None
    assert "missing source artifact" in result.error.lower()


def test_pipeline_restores_local_source_from_checkpoint(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = _png(tmp_path, png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    source = pipeline.store.register(
        media,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.IMAGE,
        provenance={"provider": "local-file", "job_id": str(job.job_id)},
    )
    pipeline.queue.put_checkpoint(
        job.job_id,
        {
            "stage": "acquired",
            "source_ids": [source.artifact_id],
            "acquired_kinds": ["image"],
        },
    )
    result = pipeline.run_next()
    assert result is not None
    assert result.state is JobState.COMPLETED


def test_include_original_false_leaves_no_publishable_source(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = _png(tmp_path, png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), intent=ExportIntent(include_original=False))
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "publishable" in job.error.lower()


def test_pipeline_skips_preview_produced_ids_and_publishes_source(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = _png(tmp_path, png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    source = pipeline.store.register(
        media,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.IMAGE,
        provenance={"job_id": str(job.job_id)},
    )
    preview_path = tmp_path / "preview.jpg"
    preview_path.write_bytes(png_bytes + b"preview")
    preview = pipeline.store.register(
        preview_path,
        role=ArtifactRole.PREVIEW,
        media_kind=MediaKind.IMAGE,
        provenance={"job_id": str(job.job_id)},
    )
    pipeline.queue.put_checkpoint(
        job.job_id,
        {
            "stage": "exported",
            "source_ids": [source.artifact_id],
            "produced_ids": [preview.artifact_id, source.artifact_id],
            "acquired_kinds": ["image"],
            "completed_operations": [f"{source.artifact_id}:keep-original"],
            "operation_artifacts": {f"{source.artifact_id}:keep-original": source.artifact_id},
        },
    )
    result = pipeline.run_next()
    assert result is not None
    assert result.state is JobState.COMPLETED


def test_pipeline_skips_missing_produced_and_operation_artifact_ids(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = _png(tmp_path, png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    source = pipeline.store.register(
        media,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.IMAGE,
        provenance={"job_id": str(job.job_id)},
    )
    pipeline.queue.put_checkpoint(
        job.job_id,
        {
            "stage": "exported",
            "source_ids": [source.artifact_id],
            "produced_ids": ["sha256:missing", source.artifact_id],
            "acquired_kinds": ["image"],
            "completed_operations": [f"{source.artifact_id}:keep-original"],
            "operation_artifacts": {
                "keep-original": "sha256:missing",
                f"{source.artifact_id}:keep-original": source.artifact_id,
            },
        },
    )
    result = pipeline.run_next()
    assert result is not None
    assert result.state is JobState.COMPLETED


def test_pipeline_preview_only_produced_set_is_not_publishable(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = _png(tmp_path, png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    source = pipeline.store.register(
        media,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.IMAGE,
        provenance={"job_id": str(job.job_id)},
    )
    preview_path = tmp_path / "preview.jpg"
    preview_path.write_bytes(png_bytes + b"preview")
    preview = pipeline.store.register(
        preview_path,
        role=ArtifactRole.PREVIEW,
        media_kind=MediaKind.IMAGE,
        provenance={"job_id": str(job.job_id)},
    )
    pipeline.queue.put_checkpoint(
        job.job_id,
        {
            "stage": "exported",
            "source_ids": [source.artifact_id],
            "produced_ids": [preview.artifact_id],
            "acquired_kinds": ["image"],
        },
    )
    result = pipeline.run_next()
    assert result is not None
    assert result.state is JobState.FAILED
    assert result.error is not None
    assert "publishable" in result.error.lower()


def test_acquired_kinds_without_restored_sources_fail_closed(
    tmp_data: Path, png_bytes: bytes
) -> None:
    runtime = ProviderRuntime(
        which=lambda _name: None,
        http_get=lambda _url: (200, {"content-type": "image/png"}, png_bytes),
    )
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit("https://cdn.example.com/hero.png", wait=False)
    pipeline.queue.put_checkpoint(
        job.job_id,
        {
            "stage": "acquiring",
            "source_ids": [],
            "acquired_kinds": ["image"],
        },
    )
    result = pipeline.run_next()
    assert result is not None
    assert result.state is JobState.FAILED
    assert result.error is not None
    assert "no source artifact" in result.error.lower()


def test_record_probe_refuses_drm_after_clear_acquire(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = {"n": 0}

    def two_phase(_path: Path, **kwargs: object) -> MediaProbe:
        calls["n"] += 1
        candidate = kwargs.get("candidate_id")
        probe_id = candidate if isinstance(candidate, UUID) else uuid4()
        if calls["n"] == 1:
            return MediaProbe(
                candidate_id=probe_id,
                container="png",
                streams=[StreamInfo(index=0, codec="png", media_kind=MediaKind.IMAGE)],
            )
        return MediaProbe(
            candidate_id=probe_id,
            container="png",
            streams=[
                StreamInfo(
                    index=0,
                    codec="png",
                    media_kind=MediaKind.IMAGE,
                    encrypted=True,
                )
            ],
            drm_signals=["probe:encrypted-stream"],
        )

    monkeypatch.setattr("webmedia_dl.pipeline.probe_media", two_phase)
    media = _png(tmp_path, png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media))
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "drm" in job.error.lower()
    assert calls["n"] >= 2
    types = [event.type for event in pipeline.queue.events_for(job.job_id)]
    assert EventType.SOURCE_REGISTERED in types
    assert EventType.ACQUISITION_QUARANTINE not in types


def test_validation_failure_fails_closed(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = _png(tmp_path, png_bytes)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise ValidationFailed("container evidence missing")

    monkeypatch.setattr("webmedia_dl.pipeline.require_pass", boom)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media))
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "container evidence" in job.error


def test_submit_pause_and_cancel_return_current_job(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = _png(tmp_path, png_bytes)

    def paused(self: Pipeline, *_args: object, **_kwargs: object) -> Job:
        raise PauseRequested("paused during run")

    monkeypatch.setattr(Pipeline, "_run", paused)
    pipeline = Pipeline(data_dir=tmp_data)
    paused_job = pipeline.submit(str(media))
    assert paused_job.state is JobState.ACCEPTED

    def cancelled(self: Pipeline, *_args: object, **_kwargs: object) -> Job:
        raise CancelledError("cancelled during run")

    monkeypatch.setattr(Pipeline, "_run", cancelled)
    other = Pipeline(data_dir=tmp_data / "cancel")
    cancelled_job = other.submit(str(media))
    assert cancelled_job.state is JobState.ACCEPTED


def test_fail_and_check_control_honor_terminal_states(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = _png(tmp_path, png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    pipeline.queue.set_job_flags(job.job_id, cancel_requested=True)
    failed = pipeline._fail(job.job_id, ProviderPolicyError("late failure"))
    assert failed.state is JobState.CANCELLED
    with pytest.raises(CancelledError, match="cancelled"):
        pipeline._check_control(job.job_id)

    held = pipeline.submit(str(_png(tmp_path, png_bytes, "held.png")), wait=False)
    pipeline.queue.set_state(held.job_id, JobState.CANCELLED, error="cancelled by user")
    with pytest.raises(CancelledError, match="cancelled"):
        pipeline._check_control(held.job_id)


def test_companion_cancel_and_explain_fetch(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = _png(tmp_path, png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    cancelled = pipeline.handle_companion(
        {
            "kind": "cancel",
            "job_id": str(job.job_id),
            "nativeCommand": None,
            "subprocessWorker": False,
        }
    )
    assert cancelled["job"]["state"] == "cancelled"

    def fake_fetch(url: str, **_kwargs: object) -> tuple[int, str, bytes]:
        html = "<html><body><img src='https://cdn.example.com/a.png'></body></html>"
        return 200, "text/html", html.encode()

    monkeypatch.setattr("webmedia_dl.pipeline.bound_fetch", fake_fetch)
    explained = pipeline.explain("https://example.com/page")
    assert explained["acquired"] is False
    assert explained["candidates"]
    assert any("a.png" in item["identity_key"] for item in explained["candidates"])


def test_pause_requested_set_state_intercept(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = _png(tmp_path, png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    pipeline.queue.set_job_flags(job.job_id, pause_requested=True)
    with pytest.raises(PauseRequested, match="paused"):
        pipeline.queue.set_state(job.job_id, JobState.DISCOVERING)
    assert pipeline.queue.get_job(job.job_id).state is JobState.PAUSED


def test_hls_byterange_without_offset_follows_previous(tmp_path: Path) -> None:
    playlist = "#EXTM3U\n#EXT-X-BYTERANGE:4@0\nseg.bin\n#EXT-X-BYTERANGE:4\nseg.bin\n"
    bodies = {"https://cdn.example.com/seg.bin": b"ABCDEFGH"}

    def fetch(url: str) -> tuple[int, str, bytes]:
        return 200, "video/MP2T", bodies[url]

    dest = tmp_path / "live.bin"
    record_clear_stream(playlist, "https://cdn.example.com/index.m3u8", dest, fetch)
    assert dest.read_bytes() == b"ABCDEFGH"


def test_live_poll_stops_on_later_drm_and_http_error(tmp_path: Path) -> None:
    playlists = [
        "#EXTM3U\n#EXTINF:1,\na.ts\n",
        '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key"\n#EXTINF:1,\nb.ts\n',
    ]
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        if url.endswith("a.ts"):
            return 200, "video/MP2T", b"AAAA"
        if url.endswith("live.m3u8"):
            return 200, "application/vnd.apple.mpegurl", playlists.pop(0).encode()
        raise AssertionError(url)

    dest = tmp_path / "live.ts"
    record_clear_stream(
        playlists.pop(0),
        "https://cdn.example.com/live.m3u8",
        dest,
        fetch,
        live_polls=3,
    )
    assert dest.read_bytes() == b"AAAA"
    assert "https://cdn.example.com/b.ts" not in fetched

    second = tmp_path / "poll.ts"
    rounds = ["#EXTM3U\n#EXTINF:1,\nc.ts\n"]

    def poll_fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("c.ts"):
            return 200, "video/MP2T", b"CCCC"
        if url.endswith("poll.m3u8"):
            return 400, "text/plain", b"nope"
        raise AssertionError(url)

    record_clear_stream(
        rounds[0],
        "https://cdn.example.com/poll.m3u8",
        second,
        poll_fetch,
        live_polls=3,
    )
    assert second.read_bytes() == b"CCCC"


def test_dash_unknown_kinds_record_as_live_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "live.bin"

    def fake_record(*_args: object, **_kwargs: object) -> Path:
        dest.write_bytes(b"dash")
        return dest

    monkeypatch.setattr("webmedia_dl.live.inspect_manifest", lambda *_a, **_k: None)
    monkeypatch.setattr("webmedia_dl.live._dash_kind_parts", lambda *_a, **_k: {})
    monkeypatch.setattr("webmedia_dl.live.record_clear_stream", fake_record)
    recorded = record_kind_streams(
        "<MPD></MPD>",
        "https://cdn.example.com/manifest.mpd",
        dest,
        lambda _url: (200, "application/dash+xml", b"<MPD></MPD>"),
    )
    assert recorded == [(MediaKind.LIVE_STREAM, dest)]


def test_dash_template_tokens_and_period_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _format_token(3, None) == "3"
    assert _format_token(3, "%z") == "3"
    assert _expand_dash_template("seg$$_$Number$.m4s", number=1) == "seg$_1.m4s"
    text = """
    <MPD><Period>
      <SegmentTemplate media="s$Number$.m4s" startNumber="1">
        <SegmentTimeline><S t="0" d="1000" r="-1"/></SegmentTimeline>
      </SegmentTemplate>
    </Period></MPD>
    """
    urls = recordable_segment_urls(text, "https://cdn.example.com/")
    assert len(urls) == 64
    assert urls[0] == "https://cdn.example.com/s1.m4s"
    leftover = """
    <MPD><Period>
      <SegmentTemplate media="t_$Time$.m4s"/>
    </Period></MPD>
    """
    assert recordable_segment_urls(leftover, "https://cdn.example.com/") == []
    numbered = """
    <MPD><Period>
      <SegmentTemplate media="s$Number$.m4s" startNumber="2" endNumber="4" duration="1000"/>
    </Period></MPD>
    """
    assert recordable_segment_urls(numbered, "https://cdn.example.com/") == [
        "https://cdn.example.com/s2.m4s",
        "https://cdn.example.com/s3.m4s",
        "https://cdn.example.com/s4.m4s",
    ]
    bounded = """
    <MPD><Period>
      <SegmentTemplate media="n$Number$.m4s" startNumber="1" endNumber="9999"/>
    </Period></MPD>
    """
    assert len(recordable_segment_urls(bounded, "https://cdn.example.com/")) == 64
    assert _iso8601_duration_seconds("PT6S") == 6
    assert _iso8601_duration_seconds("PT1M30S") == 90
    assert _iso8601_duration_seconds("P0Y0M0DT0H0M4.5S") == 4.5
    assert _iso8601_duration_seconds("P1Y") is None
    assert _iso8601_duration_seconds("P1M") is None
    assert _iso8601_duration_seconds("PT1H") == 3600
    assert _iso8601_duration_seconds("not-a-duration") is None
    timed_duration = """
    <MPD mediaPresentationDuration="PT6S"><Period>
      <SegmentTemplate media="s$Number$.m4s" startNumber="1" duration="2000" timescale="1000"/>
    </Period></MPD>
    """
    assert recordable_segment_urls(timed_duration, "https://cdn.example.com/") == [
        "https://cdn.example.com/s1.m4s",
        "https://cdn.example.com/s2.m4s",
        "https://cdn.example.com/s3.m4s",
    ]
    period_wins = """
    <MPD mediaPresentationDuration="PT99S">
      <Period duration="PT4S">
        <SegmentTemplate media="p$Number$.m4s" startNumber="1" duration="2" timescale="1"/>
      </Period>
    </MPD>
    """
    assert recordable_segment_urls(period_wins, "https://cdn.example.com/") == [
        "https://cdn.example.com/p1.m4s",
        "https://cdn.example.com/p2.m4s",
    ]
    duration_cap = """
    <MPD mediaPresentationDuration="PT10000S"><Period>
      <SegmentTemplate media="n$Number$.m4s" startNumber="1" duration="1" timescale="1"/>
    </Period></MPD>
    """
    assert len(recordable_segment_urls(duration_cap, "https://cdn.example.com/")) == 64
    unknown_duration = """
    <MPD mediaPresentationDuration="not-a-duration"><Period>
      <SegmentTemplate media="s$Number$.m4s" startNumber="5" duration="1000"/>
    </Period></MPD>
    """
    assert recordable_segment_urls(unknown_duration, "https://cdn.example.com/") == [
        "https://cdn.example.com/s5.m4s",
    ]
    bad_end = """
    <MPD><Period>
      <SegmentTemplate media="s$Number$.m4s" startNumber="2" endNumber="nope"/>
    </Period></MPD>
    """
    assert recordable_segment_urls(bad_end, "https://cdn.example.com/") == [
        "https://cdn.example.com/s2.m4s",
    ]
    bad_ticks = """
    <MPD mediaPresentationDuration="PT6S"><Period>
      <SegmentTemplate media="s$Number$.m4s" startNumber="1" duration="nope" timescale="1000"/>
    </Period></MPD>
    """
    assert recordable_segment_urls(bad_ticks, "https://cdn.example.com/") == [
        "https://cdn.example.com/s1.m4s",
    ]
    two_periods_mpd_duration = """
    <MPD mediaPresentationDuration="PT6S">
      <Period>
        <SegmentTemplate media="a$Number$.m4s" startNumber="1" duration="2000" timescale="1000"/>
      </Period>
      <Period>
        <SegmentTemplate media="b$Number$.m4s" startNumber="1" duration="2000" timescale="1000"/>
      </Period>
    </MPD>
    """
    assert recordable_segment_urls(two_periods_mpd_duration, "https://cdn.example.com/") == [
        "https://cdn.example.com/a1.m4s",
        "https://cdn.example.com/b1.m4s",
    ]
    two_periods_own_duration = """
    <MPD>
      <Period duration="PT2S">
        <SegmentTemplate media="a$Number$.m4s" startNumber="1" duration="1" timescale="1"/>
      </Period>
      <Period duration="PT2S">
        <SegmentTemplate media="b$Number$.m4s" startNumber="1" duration="1" timescale="1"/>
      </Period>
    </MPD>
    """
    assert recordable_segment_urls(two_periods_own_duration, "https://cdn.example.com/") == [
        "https://cdn.example.com/a1.m4s",
        "https://cdn.example.com/a2.m4s",
        "https://cdn.example.com/b1.m4s",
        "https://cdn.example.com/b2.m4s",
    ]
    video = [ManifestPart("https://cdn.example.com/v.m4s")]
    monkeypatch.setattr(
        "webmedia_dl.live._period_kind_parts",
        lambda _body, _base: {"other": video},
    )
    assert _period_parts("<Period/>", "https://cdn.example.com/") == video


def test_http_direct_uses_default_get_and_jpeg_content_type(
    tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_fetch(url: str, **_kwargs: object) -> tuple[int, str, bytes]:
        return 200, "image/jpeg", png_bytes

    monkeypatch.setattr("webmedia_dl.providers.bound_fetch", fake_fetch)
    runtime = ProviderRuntime(which=lambda name: f"/usr/bin/{name}")
    result = runtime.execute(
        ProviderRequest(
            provider_id="http-direct",
            capability_id="acquire.http",
            typed_inputs={
                "url": "https://cdn.example.com/photo",
                "output": str(tmp_path / "out.bin"),
            },
        ),
        tmp_path,
    )
    assert result.exit_code == 0
    assert result.output_path is not None
    assert result.output_path.suffix == ".jpg"
    assert _http_suffix("https://cdn.example.com/x", {"Content-Type": "image/jpeg"}, b"") == ".jpg"


def test_ytdlp_dump_json_flag_must_be_allowlisted(tmp_path: Path) -> None:
    runtime = ProviderRuntime(which=lambda name: "/usr/bin/yt-dlp")
    manifest = runtime._manifests["ytdlp"]
    runtime._manifests["ytdlp"] = manifest.model_copy(update={"allowed_flags": ["--no-playlist"]})
    with pytest.raises(ProviderPolicyError, match="not allowlisted"):
        runtime.execute(
            ProviderRequest(
                provider_id="ytdlp",
                capability_id="discover.manifest",
                typed_inputs={"url": "https://example.com/watch"},
            ),
            tmp_path,
        )


def test_ytdlp_acquire_flag_must_be_allowlisted(tmp_path: Path) -> None:
    runtime = ProviderRuntime(which=lambda name: "/usr/bin/yt-dlp")
    manifest = runtime._manifests["ytdlp"]
    runtime._manifests["ytdlp"] = manifest.model_copy(
        update={"allowed_flags": ["--output", "--no-playlist"]}
    )
    with pytest.raises(ProviderPolicyError, match="not allowlisted"):
        runtime.execute(
            ProviderRequest(
                provider_id="ytdlp",
                capability_id="acquire.ytdlp",
                typed_inputs={
                    "url": "https://example.com/watch",
                    "output": str(tmp_path / "clip.bin"),
                },
            ),
            tmp_path,
        )


def test_ffmpeg_ext_template_matches_stem(tmp_path: Path) -> None:
    def run(_argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        dest = tmp_path / "clip.mkv"
        dest.write_bytes(b"mkv")
        return 0, b"", b""

    runtime = ProviderRuntime(which=lambda name: "/usr/bin/ffmpeg", run=run)
    result = runtime.execute(
        ProviderRequest(
            provider_id="ffmpeg",
            capability_id="process.ffmpeg.remux",
            typed_inputs={
                "input": str(tmp_path / "a.mp4"),
                "output": str(tmp_path / "clip.%(ext)s"),
            },
        ),
        tmp_path,
    )
    assert result.output_path is not None
    assert result.output_path.name == "clip.mkv"


def test_ffmpeg_transcode_rejects_unknown_codec(tmp_path: Path) -> None:
    runtime = ProviderRuntime(which=lambda name: "/usr/bin/ffmpeg")
    with pytest.raises(ProviderPolicyError, match="allowlisted"):
        runtime.execute(
            ProviderRequest(
                provider_id="ffmpeg",
                capability_id="process.ffmpeg.transcode",
                typed_inputs={
                    "input": str(tmp_path / "a.mp4"),
                    "output": str(tmp_path / "b.mp4"),
                    "video_codec": "libx999",
                    "audio_codec": "aac",
                },
            ),
            tmp_path,
        )


def test_terminate_process_already_dead_and_kill_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    dead = MagicMock()
    dead.poll.return_value = 0
    _terminate_process(cast(subprocess.Popen[bytes], dead))
    dead.kill.assert_not_called()

    live = MagicMock()
    live.poll.return_value = None
    live.pid = 4242
    live.wait.side_effect = subprocess.TimeoutExpired(cmd="sleep", timeout=2)
    signals: list[int] = []

    def killpg(_pid: int, sig: int) -> None:
        signals.append(sig)

    monkeypatch.setattr("webmedia_dl.providers.os.killpg", killpg)
    _terminate_process(cast(subprocess.Popen[bytes], live))
    assert signal.SIGTERM in signals
    assert signal.SIGKILL in signals

    missing = MagicMock()
    missing.poll.return_value = None
    missing.pid = 7
    missing.wait.side_effect = subprocess.TimeoutExpired(cmd="sleep", timeout=2)

    def missing_group(_pid: int, _sig: int) -> None:
        raise ProcessLookupError

    monkeypatch.setattr("webmedia_dl.providers.os.killpg", missing_group)
    _terminate_process(cast(subprocess.Popen[bytes], missing))
    missing.kill.assert_called()


def test_processing_skips_existing_compound_and_failed_inputs(
    tmp_path: Path, png_bytes: bytes
) -> None:
    src = tmp_path / "source.jpg"
    src.write_bytes(png_bytes)
    store = ArtifactStore(tmp_path / "data")
    source = store.register(
        src, role=ArtifactRole.SOURCE, media_kind=MediaKind.IMAGE, container="jpg"
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
        input_artifact_ids=["remux"],
        output_role=ArtifactRole.DERIVATIVE,
        loss_class="lossy_transcode",
        validator_ids=[],
        typed_inputs={"container": "mp4"},
    )
    calls: list[str] = []

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        calls.append(Path(argv[-1]).name)
        return 1, b"", b"fail"

    plan = ExportPlan(job_id=job.job_id, operations=[remux, transcode])
    with pytest.raises(RequiredOperationFailed, match="exited 1"):
        execute_export_plan(
            plan,
            job_id=job.job_id,
            source=source,
            source_path=store.resolve(source),
            store=store,
            runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
            staging=tmp_path / "stage",
            queue=queue,
            authorize=lambda _cap: None,
        )
    assert calls == ["remux.mkv"]

    derived = tmp_path / "already.mkv"
    derived.write_bytes(b"mkv")
    recorded = store.register(
        derived,
        role=ArtifactRole.DERIVATIVE,
        media_kind=MediaKind.IMAGE,
        container="mkv",
    )
    skipped: list[str] = []

    def record_run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        skipped.append(Path(argv[-1]).name)
        Path(argv[-1]).write_bytes(b"x")
        return 0, b"", b""

    execute_export_plan(
        ExportPlan(job_id=job.job_id, operations=[remux]),
        job_id=job.job_id,
        source=source,
        source_path=store.resolve(source),
        store=store,
        runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=record_run),
        staging=tmp_path / "stage2",
        queue=queue,
        authorize=lambda _cap: None,
        existing={f"{source.artifact_id}:remux": (recorded, derived)},
    )
    assert skipped == []


def test_lossy_transcode_skips_semantic_parity(
    tmp_path: Path, png_bytes: bytes, pass_container_probe: object
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
    transcode = Operation(
        operation_id="transcode",
        op_type="ffmpeg.transcode",
        capability_id="process.ffmpeg.transcode",
        input_artifact_ids=[source.artifact_id],
        output_role=ArtifactRole.DERIVATIVE,
        loss_class="lossy_transcode",
        validator_ids=[],
        typed_inputs={"container": "mp4", "video_codec": "libx264", "audio_codec": "aac"},
    )

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        Path(argv[-1]).write_bytes(b"lossy")
        return 0, b"", b""

    produced = execute_export_plan(
        ExportPlan(job_id=job.job_id, operations=[transcode]),
        job_id=job.job_id,
        source=source,
        source_path=store.resolve(source),
        store=store,
        runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
        staging=tmp_path / "stage-lossy",
        queue=queue,
        authorize=lambda _cap: None,
    )
    assert produced
    assert any(artifact.role is ArtifactRole.DERIVATIVE for artifact, _path in produced)
    assert not any(
        event.type is EventType.VALIDATION_RECORDED
        and event.payload.get("gate") == "semantic-parity"
        for event in queue.events_for(job.job_id)
    )


def test_artifact_sha_mismatch_and_existing_dest(tmp_path: Path, png_bytes: bytes) -> None:
    store = ArtifactStore(tmp_path / "store")
    path = tmp_path / "a.png"
    path.write_bytes(png_bytes)
    first = store.register(path, role=ArtifactRole.SOURCE, media_kind=MediaKind.IMAGE)
    dest = store.resolve(first)
    assert dest.is_file()
    store._records.clear()
    second = store.register(path, role=ArtifactRole.DERIVATIVE, media_kind=MediaKind.IMAGE)
    assert second.artifact_id == first.artifact_id
    digest = sha256_file(str(path))
    artifact_id = artifact_id_for_digest(digest)
    store._records[artifact_id] = Artifact.model_construct(
        artifact_id=artifact_id,
        role=ArtifactRole.SOURCE,
        sha256="0" * 64,
        byte_size=1,
        media_kind=MediaKind.IMAGE,
        storage_relpath=first.storage_relpath,
        immutable=True,
        parent_ids=[],
        provenance={},
    )
    with pytest.raises(ArtifactImmutabilityError, match="never mutated"):
        store.register(path, role=ArtifactRole.SOURCE, media_kind=MediaKind.IMAGE)


def test_discovery_link_iframe_jsonld_and_duplicates() -> None:
    html = """
    <html>
      <link rel="preload" as="track" href="https://cdn.example.com/subs.vtt">
      <iframe src="https://cdn.example.com/player.mp4"></iframe>
      <a href="javascript:alert(1)">skip</a>
      <a href="file:///tmp/secret.mp4">skip file</a>
      <a href="http://cdn.example.com/insecure.mp4">skip http</a>
      <video src="https://cdn.example.com/clip.mp4"></video>
      <video src="https://cdn.example.com/clip.mp4"></video>
      <script type="application/ld+json">
        {"@type": "Photograph", "contentUrl": "https://cdn.example.com/photo.jpg"}
      </script>
    </html>
    """
    source = normalize_source(
        "https://example.com/page",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )
    found = discover(source, get_profile("personal-full"), html=html)
    urls = [item.retrieval_urls[0] for item in found if item.retrieval_urls]
    assert urls.count("https://cdn.example.com/clip.mp4") == 1
    assert "https://cdn.example.com/subs.vtt" in urls
    assert "https://cdn.example.com/player.mp4" in urls
    assert "https://cdn.example.com/photo.jpg" in urls
    assert not any(item.startswith("javascript:") for item in urls)
    assert not any(item.startswith("file:") for item in urls)
    assert not any(item.startswith("http:") for item in urls)
    photo = next(item for item in found if item.retrieval_urls[0].endswith("photo.jpg"))
    assert photo.media_kind is MediaKind.IMAGE


def test_service_error_paths_and_companion_surface(
    tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_api = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app_api)
    mac = {"Authorization": f"Bearer {token}"}
    unknown = "00000000-0000-0000-0000-000000000000"
    confirm = client.post("/v1/pair/confirm", headers=mac, json={"pairing_id": unknown})
    assert confirm.status_code == 400
    denied = client.post(
        "/v1/jobs",
        headers=mac,
        json={
            "locator": "https://cdn.example.com/a.png",
            "pairing_id": unknown,
            "session_key": "x",
        },
    )
    assert denied.status_code == 400
    planned = client.post(
        "/v1/plan",
        headers=mac,
        json={
            "locator": "https://cdn.example.com/a.png",
            "pairing_id": unknown,
            "session_key": "x",
        },
    )
    assert planned.status_code == 400
    envelope = client.post(
        "/v1/pair/envelope",
        headers=mac,
        json={"pairing_id": unknown, "session_key": "x", "payload": {"ok": True}},
    )
    assert envelope.status_code == 401
    missing = client.post(f"/v1/jobs/{unknown}/cancel", headers=mac)
    assert missing.status_code == 400
    media = _png(tmp_path, png_bytes)
    created = client.post("/v1/jobs", headers=mac, json={"locator": str(media)})
    job_id = created.json()["job"]["job_id"]
    paused = client.post(f"/v1/jobs/{job_id}/pause", headers=mac)
    assert paused.status_code == 400
    resumed = client.post(f"/v1/jobs/{job_id}/resume", headers=mac)
    assert resumed.status_code == 400
    capture = client.post(
        "/v1/companion",
        headers=mac,
        json={
            "kind": "capture",
            "locator": str(media),
            "surface": "watchos",
            "nativeCommand": None,
            "subprocessWorker": False,
        },
    )
    assert capture.status_code == 200
    assert capture.json()["job"]["source"]["surface"] == "watchos"

    created_pair = client.post("/v1/pair", headers=mac)
    pairing_id = created_pair.json()["pairing_id"]
    confirmed = client.post("/v1/pair/confirm", headers=mac, json={"pairing_id": pairing_id})
    session_key = confirmed.json()["session_key"]
    monkeypatch.setattr("webmedia_dl.service.open_payload", lambda *_a, **_k: ["not-a-dict"])
    sealed = client.post(
        "/v1/companion",
        headers=mac,
        json={
            "pairing_id": pairing_id,
            "session_key": session_key,
            "nonce": "aa",
            "ciphertext": "bb",
            "mac": "cc",
        },
    )
    assert sealed.status_code == 400
    assert "invalid" in sealed.json()["detail"].lower()


def test_serve_worker_and_cli_loopback_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    def fake_run(app_obj: object, host: str, port: int, log_level: str = "info") -> None:
        seen["host"] = host
        seen["port"] = port
        seen["log_level"] = log_level
        seen["app"] = app_obj

    monkeypatch.setattr("uvicorn.run", fake_run)
    serve_worker(data_dir=tmp_path, host="127.0.0.1", port=8765)
    assert seen["host"] == "127.0.0.1"
    assert seen["port"] == 8765

    called: dict[str, object] = {}

    def fake_serve(*, data_dir: Path | None, host: str, port: int) -> None:
        called["host"] = host
        called["port"] = port
        called["data_dir"] = data_dir

    monkeypatch.setattr("webmedia_dl.service.serve_worker", fake_serve)
    result = runner.invoke(
        app,
        ["serve", "--host", "127.0.0.1", "--port", "8765", "--data-dir", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert called["host"] == "127.0.0.1"


def test_lifespan_without_dispatcher(tmp_path: Path) -> None:
    with TestClient(create_app(tmp_path)) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_queue_claim_is_atomic_with_pause(tmp_data: Path, tmp_path: Path, png_bytes: bytes) -> None:
    media = _png(tmp_path, png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    pipeline.pause_queue()
    assert pipeline.queue.claim(job.job_id) is None
    assert pipeline.queue.get_job(job.job_id).state is JobState.ACCEPTED
    pipeline.resume_queue()
    claimed = pipeline.queue.claim(job.job_id)
    assert claimed is not None
    assert claimed.state is JobState.DISCOVERING
    assert pipeline.queue.claim(job.job_id) is None


def test_malformed_browser_evidence_fails_closed(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = _png(tmp_path, png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    with pipeline.queue.engine.begin() as conn:
        conn.execute(
            text("UPDATE job_context SET evidence_json = :payload WHERE job_id = :job_id"),
            {"payload": "not-json", "job_id": str(job.job_id)},
        )
    result = pipeline.run_next()
    assert result is not None
    assert result.state is JobState.FAILED
    assert result.error is not None
    assert "evidence" in result.error.lower()


def test_checkpoint_kinds_must_match_restored_sources(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(which=lambda _name: None),
        fetch=lambda url: (_ for _ in ()).throw(AssertionError(url)),
    )
    job = pipeline.submit(
        "https://cdn.example.com/hero.png",
        wait=False,
        html='<html><img src="https://cdn.example.com/hero.png"></html>',
    )
    source = pipeline.store.register(
        media,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.IMAGE,
        provenance={"job_id": str(job.job_id)},
    )
    pipeline.queue.put_checkpoint(
        job.job_id,
        {
            "stage": "acquired",
            "source_ids": [source.artifact_id],
            "acquired_kinds": ["video"],
        },
    )
    result = pipeline.run_next()
    assert result is not None
    assert result.state is JobState.FAILED
    assert result.error is not None
    assert "acquired_kinds" in result.error
