"""End-to-end local pipeline: intake → discovery → plan → acquire → validate → publish."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from loguru import logger

from webmedia_dl.acquisition import plan_acquisition
from webmedia_dl.artifacts import ArtifactStore
from webmedia_dl.candidates import build_graph, preferred_candidates
from webmedia_dl.discovery import discover
from webmedia_dl.domain.enums import ArtifactRole, EventType, JobState, Surface
from webmedia_dl.domain.models import ExportIntent, Job, MediaCandidate, Worker
from webmedia_dl.errors import (
    DrmRefused,
    ProviderPolicyError,
    WebMediaError,
)
from webmedia_dl.export import plan_export
from webmedia_dl.intake import normalize_source
from webmedia_dl.live import inspect_manifest
from webmedia_dl.paths import staging_dir, worker_data_dir
from webmedia_dl.policy.profiles import (
    assert_no_privilege_escalation,
    assert_worker_capability,
    get_profile,
)
from webmedia_dl.providers import ProviderRequest, ProviderRuntime
from webmedia_dl.publish import publish_artifacts
from webmedia_dl.queue import QueueStore
from webmedia_dl.security import refuse_drm
from webmedia_dl.validation import require_pass, validate_artifact


class Pipeline:
    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        runtime: ProviderRuntime | None = None,
        fetch: Callable[[str], tuple[int, str, bytes]] | None = None,
        client_profile_id: str = "personal-full",
        worker: Worker | None = None,
    ) -> None:
        self.data_dir = worker_data_dir(data_dir)
        self.queue = QueueStore(self.data_dir / "queue")
        self.store = ArtifactStore(self.data_dir)
        self.runtime = runtime or ProviderRuntime()
        self.fetch = fetch
        self.client_profile = get_profile(client_profile_id)
        self.worker = worker or Worker(
            worker_id="local-macos",
            platform=Surface.MACOS,
            profile_id="personal-full",
            capabilities=list(get_profile("personal-full").allowed_capabilities),
            subprocess_capable=True,
        )
        self.worker_profile = get_profile(self.worker.profile_id)

    def submit(
        self,
        locator: str,
        *,
        surface: Surface = Surface.CLI,
        intent: ExportIntent | None = None,
        html: str | None = None,
        cookies: str | None = None,
    ) -> Job:
        source = normalize_source(
            locator,
            surface=surface,
            policy_profile_id=self.client_profile.profile_id,
        )
        job = Job(
            source=source,
            policy_profile_id=self.client_profile.profile_id,
            worker_id=self.worker.worker_id,
            intent=intent or ExportIntent(),
        )
        self.queue.put_job(job)
        self.queue.emit(job.job_id, EventType.JOB_ACCEPTED, {"locator": locator})
        try:
            return self._run(job, html=html, cookies=cookies)
        except WebMediaError as exc:
            logger.warning("job {} failed: {}", job.job_id, exc)
            failed = self.queue.set_state(job.job_id, JobState.FAILED, error=str(exc))
            self.queue.emit(
                job.job_id, EventType.JOB_FAILED, {"code": exc.code, "message": str(exc)}
            )
            return failed

    def _run(self, job: Job, *, html: str | None, cookies: str | None) -> Job:
        self.queue.set_state(job.job_id, JobState.DISCOVERING)
        candidates = discover(job.source, self.client_profile, fetch=self.fetch, html=html)
        graph = build_graph(job.job_id, candidates)
        self.queue.emit(
            job.job_id,
            EventType.GRAPH_BUILT,
            {"nodes": len(graph.nodes), "conflicts": graph.conflicts},
        )
        chosen = preferred_candidates(graph)
        if not chosen:
            msg = "Discovery produced no candidates."
            raise ProviderPolicyError(msg)
        candidate = chosen[0]
        refuse_drm(candidate.drm_signals)
        if candidate.media_kind.value == "live_stream" and html:
            inspect_manifest(html)

        staging = staging_dir(self.data_dir) / str(job.job_id)
        staging.mkdir(parents=True, exist_ok=True)

        if job.source.local_path:
            self.queue.set_state(job.job_id, JobState.ACQUIRING)
            artifact = self.store.register(
                Path(job.source.local_path),
                role=ArtifactRole.SOURCE,
                media_kind=candidate.media_kind,
                provenance={"provider": "local-file", "job_id": str(job.job_id)},
            )
            self.queue.emit(
                job.job_id,
                EventType.SOURCE_REGISTERED,
                {"artifact_id": artifact.artifact_id, "provider": "local-file"},
            )
        else:
            self.queue.set_state(job.job_id, JobState.PLANNING)
            plan = plan_acquisition(
                job.job_id,
                candidate,
                self.worker_profile,
                cookies=cookies,
            )
            if not plan.strategies:
                msg = "No acquisition strategy is allowed for this profile and candidate."
                raise ProviderPolicyError(msg)
            self.queue.emit(
                job.job_id,
                EventType.PLAN_RANKED,
                {"strategies": [item.strategy_id for item in plan.strategies]},
            )

            artifact = None
            last_error: Exception | None = None
            self.queue.set_state(job.job_id, JobState.ACQUIRING)
            for strategy in sorted(plan.strategies, key=lambda item: item.rank):
                try:
                    self._authorize(strategy.capability_id)
                    request = ProviderRequest(
                        provider_id=strategy.provider_id,
                        capability_id=strategy.capability_id,
                        typed_inputs={
                            **strategy.typed_inputs,
                            "output": str(staging / "source.bin"),
                        },
                        extra_args=tuple(strategy.extra_args),
                    )
                    result = self.runtime.execute(request, staging)
                    if (
                        result.exit_code != 0
                        or result.output_path is None
                        or not result.output_path.exists()
                    ):
                        last_error = ProviderPolicyError(
                            f"{strategy.provider_id} exited {result.exit_code}",
                        )
                        continue
                    artifact = self.store.register(
                        result.output_path,
                        role=ArtifactRole.SOURCE,
                        media_kind=candidate.media_kind,
                        provenance={"provider": strategy.provider_id, "job_id": str(job.job_id)},
                    )
                    self.queue.emit(
                        job.job_id,
                        EventType.SOURCE_REGISTERED,
                        {"artifact_id": artifact.artifact_id, "provider": strategy.provider_id},
                    )
                    break
                except (DrmRefused, WebMediaError) as exc:
                    last_error = exc
                    continue
            if artifact is None:
                if last_error:
                    raise last_error
                msg = "Acquisition produced no source artifact."
                raise ProviderPolicyError(msg)

        export_plan = plan_export(job.job_id, artifact, job.intent)
        self.queue.emit(
            job.job_id,
            EventType.EXPORT_PLANNED,
            {"operations": [item.operation_id for item in export_plan.operations]},
        )
        self.queue.set_state(job.job_id, JobState.VALIDATING)
        path = self.store.resolve(artifact)
        results = validate_artifact(job.job_id, artifact, path)
        for item in results:
            self.queue.emit(
                job.job_id,
                EventType.VALIDATION_RECORDED,
                {"gate": item.gate_id, "status": item.status.value},
            )
        require_pass(results)

        self.queue.set_state(job.job_id, JobState.PUBLISHING)
        published = publish_artifacts([(artifact, path, results)], job.intent)
        self.queue.emit(
            job.job_id,
            EventType.PUBLISHED,
            {"paths": [str(item) for item in published]},
        )
        completed = self.queue.set_state(job.job_id, JobState.COMPLETED)
        self.queue.emit(job.job_id, EventType.JOB_COMPLETED, {"artifact_id": artifact.artifact_id})
        return completed

    def _authorize(self, capability_id: str) -> None:
        assert_no_privilege_escalation(self.client_profile, self.worker_profile, capability_id)
        assert_worker_capability(self.worker, self.worker_profile, capability_id)

    def job(self, job_id: UUID) -> Job:
        return self.queue.get_job(job_id)

    def history(self) -> list[Job]:
        return self.queue.list_jobs()


def describe_candidate(candidate: MediaCandidate) -> dict[str, Any]:
    return {
        "identity_key": candidate.identity_key,
        "kind": candidate.media_kind.value,
        "title_display": candidate.title_display,
        "drm": candidate.drm_signals,
    }
