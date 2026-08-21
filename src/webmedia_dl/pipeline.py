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
from webmedia_dl.discovery import candidates_from_manifest_json, discover
from webmedia_dl.domain.enums import ArtifactRole, EventType, JobState, MediaKind, Surface
from webmedia_dl.domain.models import (
    BrowserEvidence,
    ExportIntent,
    Job,
    MediaCandidate,
    PolicyProfile,
    Worker,
)
from webmedia_dl.errors import (
    CancelledError,
    DrmRefused,
    PauseRequested,
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
from webmedia_dl.probe import probe_media
from webmedia_dl.processing import execute_export_plan
from webmedia_dl.providers import ProviderRequest, ProviderRuntime
from webmedia_dl.publish import publish_artifacts
from webmedia_dl.queue import QUEUE_EVENT_JOB_ID, QueueStore
from webmedia_dl.security import refuse_drm, resolve_cookie_path
from webmedia_dl.validation import require_pass, validate_artifact, validate_probe

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
        evidence: list[BrowserEvidence] | None = None,
        wait: bool = True,
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
        self.queue.emit(
            job.job_id,
            EventType.INTAKE_NORMALIZED,
            {
                "kind": source.kind.value,
                "normalized_url": source.normalized_url,
                "local_path": source.local_path,
            },
        )
        try:
            cookie_value = None
            if cookies:
                cookie_value = str(
                    resolve_cookie_path(client_profile, cookies, repo_root=repo_root())
                )
            self.queue.put_context(job.job_id, html=html, cookies=cookie_value, evidence=evidence)
            if self.queue.is_paused() or not wait:
                return job
            return self._run(job, html=html, cookies=cookie_value, evidence=evidence)
        except PauseRequested:
            return self.queue.get_job(job.job_id)
        except WebMediaError as exc:
            return self._fail(job.job_id, exc)

    def _run(
        self,
        job: Job,
        *,
        html: str | None,
        cookies: str | None,
        evidence: list[BrowserEvidence] | None = None,
    ) -> Job:
        self.queue.set_state(job.job_id, JobState.DISCOVERING)

        def page_fetch(url: str) -> tuple[int, str, bytes]:
            return self._fetch_bytes(url, self.client_profile, html=True)

        candidates = discover(
            job.source,
            self.client_profile,
            fetch=page_fetch if html is None else None,
            html=html,
            evidence=evidence,
        )
        candidates.extend(self._manifest_candidates(job, staging=None))
        graph = build_graph(job.job_id, candidates)
        if any(item.media_kind is MediaKind.PAGE for item in candidates):
            self.queue.emit(
                job.job_id,
                EventType.DISCOVERY_PARTIAL,
                {"reason": "page-without-direct-media", "nodes": len(graph.nodes)},
            )
        self.queue.emit(
            job.job_id,
            EventType.DISCOVERY_COMPLETED,
            {"nodes": len(graph.nodes)},
        )
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
            self._record_probe(job, artifact, Path(job.source.local_path), candidate.candidate_id)
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
        self.queue.emit(
            job.job_id,
            EventType.ACQUISITION_STARTED,
            {"candidate_id": str(candidate.candidate_id)},
        )
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
                        if result.output_path is not None and result.output_path.exists():
                            quarantined = self.store.register(
                                result.output_path,
                                role=ArtifactRole.QUARANTINE,
                                media_kind=candidate.media_kind,
                                provenance={
                                    "provider": strategy.provider_id,
                                    "job_id": str(job.job_id),
                                },
                            )
                            self.queue.emit(
                                job.job_id,
                                EventType.ACQUISITION_QUARANTINE,
                                {"artifact_id": quarantined.artifact_id},
                            )
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
                self._record_probe(
                    job, artifact, self.store.resolve(artifact), candidate.candidate_id
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

    def _manifest_candidates(self, job: Job, *, staging: Path | None) -> list[MediaCandidate]:
        url = job.source.normalized_url
        if not url:
            return []
        if "discover.manifest" not in self.client_profile.allowed_capabilities:
            return []
        try:
            self._authorize("discover.manifest")
        except WebMediaError:
            return []
        dest = staging or (staging_dir(self.data_dir) / str(job.job_id))
        dest.mkdir(parents=True, exist_ok=True)
        try:
            result = self.runtime.execute(
                ProviderRequest(
                    provider_id="ytdlp",
                    capability_id="discover.manifest",
                    typed_inputs={"url": url},
                ),
                dest,
            )
        except WebMediaError as exc:
            logger.info("manifest discovery skipped: {}", exc)
            return []
        if result.exit_code != 0:
            return []
        return candidates_from_manifest_json(job.source, result.stdout)

    def _record_probe(self, job: Job, artifact, path: Path, candidate_id) -> None:
        probe = probe_media(path, candidate_id=candidate_id)
        if probe is not None:
            self.queue.emit(
                job.job_id,
                EventType.PROBE_RECORDED,
                {
                    "artifact_id": artifact.artifact_id,
                    "container": probe.container,
                    "streams": len(probe.streams),
                    "duration_ms": probe.duration_ms,
                },
            )
        for result in validate_probe(job.job_id, artifact, probe):
            self.queue.emit(
                job.job_id,
                EventType.VALIDATION_RECORDED,
                {"gate": result.gate_id, "status": result.status.value},
            )

    def cancel(self, job_id: UUID) -> Job:
        job = self.queue.get_job(job_id)
        if job.state in {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}:
            msg = f"Job {job_id} cannot be cancelled from state {job.state.value}."
            raise CancelledError(msg)
        cancelled = self.queue.set_state(job_id, JobState.CANCELLED, error="cancelled by user")
        self.queue.emit(job_id, EventType.JOB_CANCELLED, {"state": "cancelled"})
        return cancelled

    def pause_queue(self) -> dict[str, bool]:
        self.queue.set_paused(True)
        self.queue.emit(QUEUE_EVENT_JOB_ID, EventType.QUEUE_PAUSED, {"paused": True})
        return {"paused": True}

    def resume_queue(self) -> dict[str, bool]:
        self.queue.set_paused(False)
        self.queue.emit(QUEUE_EVENT_JOB_ID, EventType.QUEUE_RESUMED, {"paused": False})
        return {"paused": False}

    def pause_job(self, job_id: UUID) -> Job:
        job = self.queue.get_job(job_id)
        if job.state in {JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED}:
            msg = f"Job {job_id} cannot be paused from state {job.state.value}."
            raise PauseRequested(msg)
        paused = self.queue.set_state(job_id, JobState.PAUSED)
        self.queue.emit(job_id, EventType.JOB_PAUSED, {"state": "paused"})
        return paused

    def resume_job(self, job_id: UUID) -> Job:
        job = self.queue.get_job(job_id)
        if job.state not in {JobState.PAUSED, JobState.ACCEPTED}:
            msg = f"Job {job_id} cannot be resumed from state {job.state.value}."
            raise PauseRequested(msg)
        self.queue.emit(job_id, EventType.JOB_RESUMED, {"state": "resumed"})
        return self._execute_stored(job)

    def run_next(self) -> Job | None:
        job = self.queue.next_runnable()
        if job is None:
            return None
        return self._execute_stored(job)

    def _execute_stored(self, job: Job) -> Job:
        ctx = self.queue.get_context(job.job_id)
        try:
            return self._run(
                job,
                html=ctx.html,
                cookies=ctx.cookies,
                evidence=list(ctx.evidence) or None,
            )
        except PauseRequested:
            return self.queue.get_job(job.job_id)
        except WebMediaError as exc:
            return self._fail(job.job_id, exc)

    def _fail(self, job_id: UUID, exc: WebMediaError) -> Job:
        logger.warning("job {} failed: {}", job_id, exc)
        failed = self.queue.set_state(job_id, JobState.FAILED, error=str(exc))
        self.queue.emit(job_id, EventType.JOB_FAILED, {"code": exc.code, "message": str(exc)})
        return failed

    def _authorize(self, capability_id: str) -> None:
        assert_no_privilege_escalation(self.client_profile, self.worker_profile, capability_id)
        assert_worker_capability(self.worker, self.worker_profile, capability_id)

    def explain(
        self,
        locator: str,
        *,
        surface: Surface = Surface.CLI,
        html: str | None = None,
        intent: ExportIntent | None = None,
        evidence: list[BrowserEvidence] | None = None,
        local_user_confirmed: bool = False,
        pairing_id: UUID | None = None,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        """Ranked acquisition/export plan. Does not retrieve media bytes."""
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
        source = normalize_source(
            locator,
            surface=surface,
            policy_profile_id=client_profile.profile_id,
        )

        def page_fetch(url: str) -> tuple[int, str, bytes]:
            return self._fetch_bytes(url, client_profile, html=True)

        candidates = discover(
            source,
            client_profile,
            fetch=page_fetch if html is None and source.local_path is None else None,
            html=html,
            evidence=evidence,
        )
        graph = build_graph(source.source_id, candidates)
        chosen = preferred_candidates(graph)
        strategies: list[dict[str, Any]] = []
        if chosen:
            plan = plan_acquisition(source.source_id, chosen[0], get_profile(job_worker.profile_id))
            strategies = [
                {
                    "strategy_id": item.strategy_id,
                    "provider_id": item.provider_id,
                    "capability_id": item.capability_id,
                    "rank": item.rank,
                    "estimated_loss": item.estimated_loss.value,
                }
                for item in plan.strategies
            ]
        export_intent = intent or ExportIntent()
        return {
            "source": source.model_dump(mode="json"),
            "surface": surface.value,
            "client_profile": client_profile.profile_id,
            "worker_id": job_worker.worker_id,
            "candidates": [describe_candidate(item) for item in candidates],
            "conflicts": graph.conflicts,
            "preferred": describe_candidate(chosen[0]) if chosen else None,
            "strategies": strategies,
            "export_intent": export_intent.model_dump(mode="json"),
            "acquired": False,
        }

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
