"""Correctness gates for job isolation, packaging, provenance, and export failures."""

from __future__ import annotations

import json
import sys
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from webmedia_dl.artifacts import ArtifactStore
from webmedia_dl.domain.enums import ArtifactRole, IntakeKind, JobState, MediaKind, Surface
from webmedia_dl.domain.models import ExportPlan, Job, MediaSource, Operation
from webmedia_dl.errors import (
    CancelledError,
    CapabilityDenied,
    DrmRefused,
    RequiredOperationFailed,
)
from webmedia_dl.export import load_presets
from webmedia_dl.live import recordable_segment_urls
from webmedia_dl.paths import repo_root, runtime_file
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy import profiles as profiles_mod
from webmedia_dl.probe import probe_media
from webmedia_dl.processing import execute_export_plan
from webmedia_dl.providers import ProviderRequest, ProviderRuntime
from webmedia_dl.queue import QueueStore


def test_cancel_is_scoped_to_one_job(tmp_path: Path, png_bytes: bytes) -> None:
    class SleepingRuntime(ProviderRuntime):
        def _build_argv(self, manifest, request, staging):
            return [sys.executable, "-c", "import time; time.sleep(30)"]

    runtime = SleepingRuntime(http_get=lambda _url: (200, {"content-type": "image/png"}, png_bytes))
    job_a = uuid4()
    started = threading.Event()
    finished: dict[str, str] = {}

    def sleeper() -> None:
        started.set()
        try:
            runtime.execute(
                ProviderRequest(
                    provider_id="ytdlp",
                    capability_id="acquire.ytdlp",
                    job_id=job_a,
                    typed_inputs={
                        "url": "https://example.com/a",
                        "output": str(tmp_path / "a.bin"),
                    },
                ),
                tmp_path,
            )
        except CancelledError:
            finished["state"] = "cancelled"
        else:
            finished["state"] = "ok"

    thread = threading.Thread(target=sleeper)
    thread.start()
    assert started.wait(2)
    time.sleep(0.2)
    runtime.cancel_running(job_a)
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert finished["state"] == "cancelled"
    other = runtime.execute(
        ProviderRequest(
            provider_id="http-direct",
            capability_id="acquire.http",
            job_id=uuid4(),
            typed_inputs={"url": "https://cdn.example.com/hero.png"},
        ),
        tmp_path,
    )
    assert other.exit_code == 0
    assert other.output_path is not None
    assert other.output_path.suffix == ".png"


def test_claim_next_runs_each_accepted_job_once(tmp_path: Path, png_bytes: bytes) -> None:
    pipeline = Pipeline(data_dir=tmp_path / "data")
    first = tmp_path / "a.png"
    second = tmp_path / "b.png"
    first.write_bytes(png_bytes)
    second.write_bytes(png_bytes + b"x")
    pipeline.submit(str(first), wait=False)
    pipeline.submit(str(second), wait=False)
    seen: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(2)

    def worker() -> None:
        barrier.wait()
        job = pipeline.run_next()
        with lock:
            seen.append(str(job.job_id) if job is not None else "")

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert all(not thread.is_alive() for thread in threads)
    assert "" not in seen
    assert len(set(seen)) == 2
    assert pipeline.run_next() is None


def test_claim_next_is_exclusive_across_threads(tmp_path: Path) -> None:
    store = QueueStore(tmp_path / "queue")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    expected: set[str] = set()
    workers = 8
    queued = 24
    for index in range(queued):
        src = tmp_path / f"file-{index}.bin"
        src.write_bytes(b"x")
        job = Job(
            source=MediaSource(
                kind=IntakeKind.FILE,
                locator=str(src),
                local_path=str(src),
                surface=Surface.CLI,
                policy_profile_id="personal-full",
            ),
            policy_profile_id="personal-full",
            worker_id="local-macos",
            created_at=base + timedelta(milliseconds=index),
        )
        store.put_job(job)
        expected.add(str(job.job_id))
        assert job.state is JobState.ACCEPTED

    claimed: list[str] = []
    lock = threading.Lock()
    barrier = threading.Barrier(workers)

    def worker() -> None:
        barrier.wait()
        while True:
            job = store.claim_next()
            if job is None:
                return
            assert job.state is JobState.DISCOVERING
            with lock:
                claimed.append(str(job.job_id))

    threads = [threading.Thread(target=worker) for _ in range(workers)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    assert all(not thread.is_alive() for thread in threads)
    assert len(claimed) == queued
    assert set(claimed) == expected
    assert store.claim_next() is None


def test_http_direct_uses_content_type_suffix(tmp_path: Path, png_bytes: bytes) -> None:
    runtime = ProviderRuntime(http_get=lambda _url: (200, {"Content-Type": "image/png"}, png_bytes))
    result = runtime.execute(
        ProviderRequest(
            provider_id="http-direct",
            capability_id="acquire.http",
            typed_inputs={
                "url": "https://cdn.example.com/hero",
                "output": str(tmp_path / "source.bin"),
            },
        ),
        tmp_path,
    )
    assert result.output_path is not None
    assert result.output_path.name == "source.png"


def test_identical_bytes_keep_later_job_occurrence(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "data")
    path = tmp_path / "same.bin"
    path.write_bytes(b"same-bytes")
    first = store.register(
        path,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.VIDEO,
        provenance={"job_id": "one", "provider": "http-direct"},
    )
    second = store.register(
        path,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.VIDEO,
        parent_ids=["parent-two"],
        provenance={"job_id": "two", "provider": "ytdlp"},
    )
    assert first.artifact_id == second.artifact_id
    jobs = [item.get("job_id") for item in second.provenance["occurrences"]]
    assert "one" in jobs
    assert "two" in jobs
    assert "parent-two" in second.parent_ids


def test_dash_content_protection_without_cenc_is_refused() -> None:
    with pytest.raises(DrmRefused, match="ContentProtection"):
        recordable_segment_urls(
            "<MPD><ContentProtection schemeIdUri='urn:uuid:edef8ba9'></ContentProtection></MPD>",
            "https://cdn.example.com/manifest.mpd",
        )


def test_dash_representation_binds_id_and_baseurl() -> None:
    text = (
        "<MPD><Period><BaseURL>https://cdn.example.com/dash/</BaseURL>"
        '<Representation id="v1" bandwidth="800000">'
        "<BaseURL>video/</BaseURL>"
        '<SegmentTemplate media="$RepresentationID$/seg$Number$.m4s" startNumber="1"/>'
        "</Representation></Period></MPD>"
    )
    urls = recordable_segment_urls(text, "https://cdn.example.com/manifest.mpd")
    assert urls == ["https://cdn.example.com/dash/video/v1/seg1.m4s"]


def test_dash_negative_repeat_is_bounded() -> None:
    text = (
        "<MPD><Period><SegmentTemplate media='seg$Number$.m4s' startNumber='1'>"
        "<SegmentTimeline><S t='0' d='1' r='-1'/></SegmentTimeline>"
        "</SegmentTemplate></Period></MPD>"
    )
    urls = recordable_segment_urls(text, "https://cdn.example.com/")
    assert 1 <= len(urls) <= 64
    assert urls[0].endswith("seg1.m4s")


def test_policy_overlay_cannot_widen_cookie_access(monkeypatch: pytest.MonkeyPatch) -> None:
    data = json.loads(runtime_file("policy-profiles.json").read_text(encoding="utf-8"))
    data["personal-restricted"]["cookie_access"] = "explicit_path"
    monkeypatch.setattr(profiles_mod, "_resource_profiles", lambda: data)
    profiles_mod.builtin_profiles.cache_clear()
    try:
        with pytest.raises(CapabilityDenied, match="widen cookie access"):
            profiles_mod.builtin_profiles()
    finally:
        profiles_mod.builtin_profiles.cache_clear()


def test_packaged_runtime_files_are_loadable() -> None:
    assert runtime_file("export-presets.json").is_file()
    assert runtime_file("policy-profiles.json").is_file()
    assert runtime_file("platform-capability-matrix.json").is_file()
    assert (runtime_file("imagemagick-runtime") / "policy.xml").is_file()
    load_presets.cache_clear()
    assert "original-sacred" in load_presets()
    packaged = runtime_file("export-presets.json").read_text(encoding="utf-8")
    assert packaged == (repo_root() / "resources" / "export-presets.json").read_text(
        encoding="utf-8"
    )


def test_probe_tolerates_malformed_numeric_fields(tmp_path: Path) -> None:
    media = tmp_path / "clip.bin"
    media.write_bytes(b"bytes")
    payload = {
        "streams": [
            {
                "index": "0",
                "codec_type": "video",
                "width": "wide",
                "height": "9.5",
                "sample_rate": "nope",
                "channels": "stereo",
            }
        ],
        "format": {"duration": "not-a-number", "format_name": "mov,mp4,m4a"},
    }

    class Result:
        returncode = 0
        stdout = json.dumps(payload)

    probe = probe_media(
        media,
        which=lambda _name: "/usr/bin/ffprobe",
        runner=lambda *_args, **_kwargs: Result(),
    )
    assert probe is not None
    assert probe.duration_ms is None
    assert probe.streams[0].width is None
    assert probe.streams[0].height == 9
    assert probe.container == "mov"


def test_required_export_failure_skips_dependents(tmp_path: Path) -> None:
    src = tmp_path / "source.bin"
    src.write_bytes(b"src")
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
        output = Path(argv[-1])
        if output.name.startswith("bad."):
            return 1, b"", b"fail"
        output.write_bytes(b"ok")
        return 0, b"", b""

    plan = ExportPlan(
        job_id=job.job_id,
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
                op_type="ffmpeg.remux",
                capability_id="process.ffmpeg.remux",
                input_artifact_ids=[source.artifact_id],
                output_role=ArtifactRole.DERIVATIVE,
                loss_class="container_only",
                validator_ids=[],
                typed_inputs={"container": "mkv"},
            ),
            Operation(
                operation_id="dependent",
                op_type="ffmpeg.remux",
                capability_id="process.ffmpeg.remux",
                input_artifact_ids=["bad"],
                output_role=ArtifactRole.DERIVATIVE,
                loss_class="container_only",
                validator_ids=[],
                typed_inputs={"container": "mp4"},
            ),
        ],
    )
    with pytest.raises(RequiredOperationFailed):
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
    types = [event.type.value for event in queue.events_for(job.job_id)]
    failed = [
        event.payload.get("operation_id")
        for event in queue.events_for(job.job_id)
        if event.type.value == "operation.failed"
    ]
    assert "operation.failed" in types
    assert "bad" in failed
    assert "dependent" not in [
        event.payload.get("operation_id")
        for event in queue.events_for(job.job_id)
        if event.type.value == "operation.completed"
    ]


def test_repo_root_missing_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    from webmedia_dl import paths as paths_mod

    original = paths_mod.Path.is_file

    def hide_pyproject(self: Path) -> bool:
        if self.name == "pyproject.toml":
            return False
        return original(self)

    monkeypatch.setattr(paths_mod.Path, "is_file", hide_pyproject)
    with pytest.raises(FileNotFoundError, match="repository root"):
        paths_mod.repo_root()


def test_runtime_root_falls_back_without_packaged_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    from webmedia_dl import paths as paths_mod

    original = paths_mod.Path.is_dir

    def hide_runtime(self: Path) -> bool:
        if self.name == "runtime" and self.parent.name == "webmedia_dl":
            return False
        return original(self)

    monkeypatch.setattr(paths_mod.Path, "is_dir", hide_runtime)
    assert paths_mod.runtime_root() == paths_mod.repo_root() / "resources"


def test_runtime_file_falls_back_to_checkout_resources(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from webmedia_dl import paths as paths_mod

    monkeypatch.setattr(paths_mod, "runtime_root", lambda: tmp_path / "absent")
    found = paths_mod.runtime_file("export-presets.json")
    assert found == paths_mod.repo_root() / "resources" / "export-presets.json"
    missing = paths_mod.runtime_file("does-not-exist.json")
    assert missing == tmp_path / "absent" / "does-not-exist.json"


def test_worker_data_dir_uses_platformdirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from webmedia_dl import paths as paths_mod

    monkeypatch.setattr(paths_mod, "user_data_dir", lambda *_args, **_kwargs: str(tmp_path / "xdg"))
    path = paths_mod.worker_data_dir()
    assert path == tmp_path / "xdg"
    assert path.is_dir()
    assert path.stat().st_mode & 0o777 == 0o700
