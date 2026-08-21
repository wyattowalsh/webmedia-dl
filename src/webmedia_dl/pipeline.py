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
from webmedia_dl.domain.enums import ArtifactRole, EventType, JobState, MediaKind, Surface
from webmedia_dl.domain.models import ExportIntent, Job, MediaCandidate, PolicyProfile, Worker
from webmedia_dl.errors import (
    DrmRefused,
    ProviderPolicyError,
    WebMediaError,
)
from webmedia_dl.export import plan_export
from webmedia_dl.fetch import bound_fetch
from webmedia_dl.intake import normalize_source
from webmedia_dl.live import record_clear_stream
from webmedia_dl.pairing import PairingStore
from webmedia_dl.paths import repo_root, staging_dir, worker_data_dir
from webmedia_dl.policy.profiles import (
    SAME_MACHINE_SURFACES,
    assert_no_privilege_escalation,
    assert_worker_capability,
    default_worker_for_surface,
    get_profile,
)
from webmedia_dl.processing import execute_export_plan
from webmedia_dl.providers import ProviderRequest, ProviderRuntime
from webmedia_dl.publish import publish_artifacts
from webmedia_dl.queue import QueueStore
from webmedia_dl.security import refuse_drm, resolve_cookie_path
from webmedia_dl.validation import require_pass, validate_artifact

FetchFn = Callable[[str], tuple[int, str, bytes]]


class Pipeline:
    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        runtime: ProviderRuntime | None = None,
        fetch: FetchFn | None = None,
        client_profile_id: str = "personal-full",
        worker: Worker | None = None,
    ) -> None:
        self.data_dir = worker_data_dir(data_dir)
        self.queue = QueueStore(self.data_dir / "queue")
        self.store = ArtifactStore(self.data_dir)
        self.pairing = PairingStore(self.data_dir / "pairing")
        self.runtime = runtime or ProviderRuntime()
        self.fetch = fetch
        self.host_profile = get_profile(client_profile_id)
        self.host_worker = worker or default_worker_for_surface(Surface.MACOS)
        self.client_profile = self.host_profile
        self.worker = self.host_worker
        self.worker_profile = get_profile(self.host_worker.profile_id)

    def _fetch_bytes(
        self, url: str, profile: PolicyProfile, *, html: bool
    ) -> tuple[int, str, bytes]:
        if self.fetch is not None:
            return self.fetch(url)
        return bound_fetch(
            url,
            profile=profile,
            max_bytes=profile.max_html_bytes if html else profile.max_download_bytes,
            on_overflow="truncate" if html else "error",
        )

    def _mac_owned(
        self,
        surface: Surface,
        *,
        local_user_confirmed: bool,
        pairing_id: UUID | None,
        session_key: str | None,
    ) -> bool:
        if pairing_id is not None:
            self.pairing.require_confirmed(pairing_id, session_key)
            return True
        return local_user_confirmed and surface in SAME_MACHINE_SURFACES

    def submit(
        self,
        locator: str,
        *,
        surface: Surface = Surface.CLI,
        intent: ExportIntent | None = None,
        html: str | None = None,
        cookies: str | None = None,
        local_user_confirmed: bool = False,
        pairing_id: UUID | None = None,
        session_key: str | None = None,
    ) -> Job:
        mac_owned = self._mac_owned(
            surface,
            local_user_confirmed=local_user_confirmed,
            pairing_id=pairing_id,
            session_key=session_key,
        )
        if mac_owned:
            job_worker = self.host_worker
            client_profile = get_profile(self.host_worker.profile_id)
        else:
            job_worker = default_worker_for_surface(surface)
            client_profile = get_profile(job_worker.profile_id)
        self.worker = job_worker
        self.client_profile = client_profile
        self.worker_profile = get_profile(job_worker.profile_id)
        source = normalize_source(
            locator,
            surface=surface,
            policy_profile_id=client_profile.profile_id,
        )
        job = Job(
            source=source,
            policy_profile_id=client_profile.profile_id,
            worker_id=job_worker.worker_id,
            intent=intent or ExportIntent(),
        )
        self.queue.put_job(job)
        self.queue.emit(
            job.job_id, EventType.JOB_ACCEPTED, {"locator": locator, "surface": surface.value}
        )
        try:
            cookie_value = None
            if cookies:
                cookie_value = str(
                    resolve_cookie_path(client_profile, cookies, repo_root=repo_root())
                )
            return self._run(job, html=html, cookies=cookie_value)
        except WebMediaError as exc:
            logger.warning("job {} failed: {}", job.job_id, exc)
            failed = self.queue.set_state(job.job_id, JobState.FAILED, error=str(exc))
            self.queue.emit(
                job.job_id, EventType.JOB_FAILED, {"code": exc.code, "message": str(exc)}
            )
            return failed

    def _run(self, job: Job, *, html: str | None, cookies: str | None) -> Job:
        self.queue.set_state(job.job_id, JobState.DISCOVERING)

        def page_fetch(url: str) -> tuple[int, str, bytes]:
            return self._fetch_bytes(url, self.client_profile, html=True)

        candidates = discover(
            job.source,
            self.client_profile,
            fetch=page_fetch if html is None else None,
            html=html,
        )
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
            artifact = self._acquire_remote(job, candidate, staging, cookies=cookies)

        export_plan = plan_export(job.job_id, artifact, job.intent)
        self.queue.emit(
            job.job_id,
            EventType.EXPORT_PLANNED,
            {"operations": [item.operation_id for item in export_plan.operations]},
        )
        produced = execute_export_plan(
            export_plan,
            job_id=job.job_id,
            source=artifact,
            source_path=self.store.resolve(artifact),
            store=self.store,
            runtime=self.runtime,
            staging=staging,
            queue=self.queue,
            authorize=self._authorize,
        )

        self.queue.set_state(job.job_id, JobState.VALIDATING)
        publishable: list[tuple[Any, Path, list]] = []
        for item, path in produced:
            if (
                item.role.value == "derivative"
                and not job.intent.include_original
                and item is artifact
            ):
                continue
            results = validate_artifact(job.job_id, item, path)
            for result in results:
                self.queue.emit(
                    job.job_id,
                    EventType.VALIDATION_RECORDED,
                    {"gate": result.gate_id, "status": result.status.value},
                )
            require_pass(results)
            if item.role.value == "source" and not job.intent.include_original:
                continue
            publishable.append((item, path, results))

        self.queue.set_state(job.job_id, JobState.PUBLISHING)
        published = publish_artifacts(publishable, job.intent)
        self.queue.emit(
            job.job_id,
            EventType.PUBLISHED,
            {"paths": [str(item) for item in published]},
        )
        completed = self.queue.set_state(job.job_id, JobState.COMPLETED)
        self.queue.emit(job.job_id, EventType.JOB_COMPLETED, {"artifact_id": artifact.artifact_id})
        return completed

    def _acquire_remote(
        self,
        job: Job,
        candidate: MediaCandidate,
        staging: Path,
        *,
        cookies: str | None,
    ):
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
                if strategy.capability_id == "live.record_clear_manifest":
                    artifact = self._record_live(job, candidate, staging)
                else:
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
                    {
                        "artifact_id": artifact.artifact_id,
                        "provider": strategy.provider_id,
                    },
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
        return artifact

    def _record_live(self, job: Job, candidate: MediaCandidate, staging: Path):
        url = candidate.retrieval_urls[0]
        status, _, data = self._fetch_bytes(url, self.client_profile, html=True)
        if status >= 400:
            msg = f"Live playlist fetch failed with HTTP {status}."
            raise ProviderPolicyError(msg)
        output = staging / "live.bin"
        record_clear_stream(
            data.decode("utf-8", errors="replace"),
            url,
            output,
            lambda item: self._fetch_bytes(item, self.client_profile, html=False),
        )
        return self.store.register(
            output,
            role=ArtifactRole.SOURCE,
            media_kind=MediaKind.LIVE_STREAM,
            provenance={"provider": "live-clear-record", "job_id": str(job.job_id)},
        )

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
