"""End-to-end local pipeline: intake → discovery → plan → acquire → validate → publish."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import local
from typing import Any
from uuid import UUID

from loguru import logger

from webmedia_dl.acquisition import plan_acquisition
from webmedia_dl.artifacts import ArtifactStore
from webmedia_dl.candidates import build_graph, preferred_by_kind
from webmedia_dl.discovery import DIRECT_EXTENSIONS, candidates_from_manifest_json, discover
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
    BrowserEvidence,
    ExportIntent,
    HistoryEntry,
    Job,
    MediaCandidate,
    PolicyProfile,
    Worker,
)
from webmedia_dl.errors import (
    CancelledError,
    CookiePolicyError,
    DrmRefused,
    PauseRequested,
    ProviderPolicyError,
    RequiredOperationFailed,
    WebMediaError,
)
from webmedia_dl.export import plan_export
from webmedia_dl.fetch import bound_fetch
from webmedia_dl.intake import normalize_source
from webmedia_dl.live import manifest_is_live, record_kind_streams
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
from webmedia_dl.security import CookieGrantLedger, refuse_drm, resolve_cookie_path
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
        self.cookie_ledger = CookieGrantLedger(self.data_dir / "cookie-grants.json")
        self.runtime = runtime or ProviderRuntime()
        self.runtime.cookie_ledger = self.cookie_ledger
        self.fetch = fetch
        self.host_profile = get_profile(client_profile_id)
        self.host_worker = worker or default_worker_for_surface(Surface.MACOS)
        self._tls = local()

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

    @property
    def client_profile(self) -> PolicyProfile:
        return getattr(self._tls, "client_profile", self.host_profile)

    @client_profile.setter
    def client_profile(self, value: PolicyProfile) -> None:
        self._tls.client_profile = value

    @property
    def worker(self) -> Worker:
        return getattr(self._tls, "worker", self.host_worker)

    @worker.setter
    def worker(self, value: Worker) -> None:
        self._tls.worker = value

    @property
    def worker_profile(self) -> PolicyProfile:
        return getattr(self._tls, "worker_profile", get_profile(self.host_worker.profile_id))

    @worker_profile.setter
    def worker_profile(self, value: PolicyProfile) -> None:
        self._tls.worker_profile = value

    def _activate_job(self, job: Job) -> None:
        self.client_profile = get_profile(job.policy_profile_id)
        if job.worker_id == self.host_worker.worker_id:
            self.worker = self.host_worker
        else:
            self.worker = default_worker_for_surface(job.source.surface)
        self.worker_profile = get_profile(self.worker.profile_id)
        self.runtime._tls.profile_id = job.policy_profile_id

    def _job_owner(
        self,
        surface: Surface,
        *,
        local_user_confirmed: bool,
        pairing_id: UUID | None,
        session_key: str | None,
        host_owned: bool = False,
    ) -> tuple[Worker, PolicyProfile]:
        if pairing_id is not None:
            record = self.pairing.require_confirmed(pairing_id, session_key)
            return self.host_worker, get_profile(record.client_profile_id)
        if host_owned or (local_user_confirmed and surface in SAME_MACHINE_SURFACES):
            return self.host_worker, get_profile(self.host_worker.profile_id)
        job_worker = default_worker_for_surface(surface)
        return job_worker, get_profile(job_worker.profile_id)

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
        intake_kind: IntakeKind | None = None,
        host_owned: bool = False,
    ) -> Job:
        job_worker, client_profile = self._job_owner(
            surface,
            local_user_confirmed=local_user_confirmed,
            pairing_id=pairing_id,
            session_key=session_key,
            host_owned=host_owned,
        )
        self.worker = job_worker
        self.client_profile = client_profile
        self.worker_profile = get_profile(job_worker.profile_id)
        source = normalize_source(
            locator,
            surface=surface,
            policy_profile_id=client_profile.profile_id,
            kind=intake_kind,
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
                try:
                    cookie_root = repo_root()
                except FileNotFoundError:
                    cookie_root = None
                cookie_path = resolve_cookie_path(client_profile, cookies, repo_root=cookie_root)
                if cookie_path is None:
                    msg = "Cookie file path could not be resolved."
                    raise CookiePolicyError(msg)
                grant = self.cookie_ledger.issue(job.job_id, cookie_path, client_profile.profile_id)
                cookie_value = grant.grant_id
                self.queue.emit(
                    job.job_id,
                    EventType.COOKIE_ATTACHED,
                    {
                        "cookies_path_basename": cookie_path.name,
                        "profile_id": client_profile.profile_id,
                    },
                )
            self.queue.put_context(job.job_id, html=html, cookies=cookie_value, evidence=evidence)
            if self.queue.is_paused() or not wait:
                return job
            return self._run(job, html=html, cookies=cookie_value, evidence=evidence)
        except PauseRequested:
            return self.queue.get_job(job.job_id)
        except CancelledError:
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
        self._activate_job(job)
        self._check_control(job.job_id)
        stored = self.queue.get_context(job.job_id)
        checkpoint = dict(stored.checkpoint)
        acquired_kinds = {str(item) for item in checkpoint.get("acquired_kinds") or []}
        failed_kinds: list[str] = list(checkpoint.get("failed_kinds") or [])
        sources: list[Any] = []
        for artifact_id in checkpoint.get("source_ids") or []:
            try:
                sources.append(self.store.get(str(artifact_id)))
            except KeyError:
                continue

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
        chosen = preferred_by_kind(graph)
        if not chosen:
            msg = "Discovery produced no candidates."
            raise ProviderPolicyError(msg)
        for candidate in chosen:
            refuse_drm(candidate.drm_signals)

        staging = staging_dir(self.data_dir) / str(job.job_id)
        staging.mkdir(parents=True, exist_ok=True)
        if html and not checkpoint.get("evidence_id"):
            evidence_path = staging / "page.html"
            evidence_path.write_text(html, encoding="utf-8")
            recorded = self.store.register(
                evidence_path,
                role=ArtifactRole.EVIDENCE,
                media_kind=MediaKind.PAGE,
                provenance={"job_id": str(job.job_id), "kind": "html"},
            )
            self.queue.emit(
                job.job_id,
                EventType.EVIDENCE_REGISTERED,
                {"artifact_id": recorded.artifact_id, "kind": "html"},
            )
            checkpoint["evidence_id"] = recorded.artifact_id
            self.queue.put_checkpoint(job.job_id, checkpoint)

        stage = checkpoint.get("stage")
        if job.source.local_path:
            if not sources:
                self._check_control(job.job_id)
                self.queue.set_state(job.job_id, JobState.ACQUIRING)
                artifact = self.store.register(
                    Path(job.source.local_path),
                    role=ArtifactRole.SOURCE,
                    media_kind=chosen[0].media_kind,
                    provenance={"provider": "local-file", "job_id": str(job.job_id)},
                )
                self.queue.emit(
                    job.job_id,
                    EventType.SOURCE_REGISTERED,
                    {"artifact_id": artifact.artifact_id, "provider": "local-file"},
                )
                self._record_probe(
                    job, artifact, Path(job.source.local_path), chosen[0].candidate_id
                )
                sources.append(artifact)
                acquired_kinds.add(chosen[0].media_kind.value)
                self._save_acquire_checkpoint(job, sources, acquired_kinds, stage="acquired")
            self._check_control(job.job_id)
        elif stage not in {"acquired", "exporting", "exported", "validating", "publishing"}:
            last_error: Exception | None = None
            for index, candidate in enumerate(chosen):
                self._check_control(job.job_id)
                if candidate.media_kind.value in acquired_kinds:
                    continue
                try:
                    kind_dir = staging / f"{index}-{candidate.media_kind.value}"
                    kind_dir.mkdir(parents=True, exist_ok=True)
                    artifact_list = self._acquire_remote(
                        job,
                        candidate,
                        kind_dir,
                        cookies=cookies,
                    )
                    sources.extend(artifact_list)
                    acquired_kinds.add(candidate.media_kind.value)
                    self._save_acquire_checkpoint(
                        job, sources, acquired_kinds, stage="acquiring", failed_kinds=failed_kinds
                    )
                except (PauseRequested, CancelledError):
                    raise
                except (DrmRefused, WebMediaError) as exc:
                    last_error = exc
                    kind = candidate.media_kind.value
                    if kind not in failed_kinds:
                        failed_kinds.append(kind)
                    self.queue.emit(
                        job.job_id,
                        EventType.DISCOVERY_PARTIAL,
                        {"kind": kind, "message": str(exc)},
                    )
                    continue
            if not sources:
                if last_error:
                    raise last_error
                msg = "Acquisition produced no source artifact."
                raise ProviderPolicyError(msg)
            self._save_acquire_checkpoint(
                job, sources, acquired_kinds, stage="acquired", failed_kinds=failed_kinds
            )

        produced: list[tuple[Any, Path]] = []
        export_errors: list[WebMediaError] = []
        stored_stage = checkpoint.get("stage")
        existing_ops: dict[str, tuple[Any, Path]] = {}
        skip_ops: set[str] = set()
        for op_id, art_id in (checkpoint.get("operation_artifacts") or {}).items():
            try:
                recorded = self.store.get(str(art_id))
                existing_ops[str(op_id)] = (recorded, self.store.resolve(recorded))
                skip_ops.add(str(op_id))
            except KeyError:
                continue
        skip_ops.update(str(item) for item in checkpoint.get("completed_operations") or [])
        if stored_stage in {"exporting", "exported", "validating", "publishing"}:
            for artifact_id in checkpoint.get("produced_ids") or []:
                try:
                    recorded = self.store.get(str(artifact_id))
                    produced.append((recorded, self.store.resolve(recorded)))
                except KeyError:
                    continue
        if stored_stage not in {"exported", "validating", "publishing"} or not produced:
            completed_ops = list(checkpoint.get("completed_operations") or [])
            op_arts = {
                str(key): str(value)
                for key, value in (checkpoint.get("operation_artifacts") or {}).items()
            }
            produced_ids = [item.artifact_id for item, _path in produced]
            if not produced_ids:
                produced_ids = [item.artifact_id for item in sources]

            current_source = {"id": ""}

            def on_progress(operation, artifact) -> None:
                key = f"{current_source['id']}:{operation.operation_id}"
                if key not in completed_ops:
                    completed_ops.append(key)
                if artifact is not None:
                    op_arts[key] = artifact.artifact_id
                    if artifact.artifact_id not in produced_ids:
                        produced_ids.append(artifact.artifact_id)
                self._save_acquire_checkpoint(
                    job,
                    sources,
                    acquired_kinds,
                    stage="exporting",
                    produced_ids=list(produced_ids),
                    completed_operations=list(completed_ops),
                    operation_artifacts=dict(op_arts),
                    failed_kinds=failed_kinds,
                )

            for artifact in sources:
                self._check_control(job.job_id)
                current_source["id"] = artifact.artifact_id
                try:
                    export_plan = plan_export(job.job_id, artifact, job.intent)
                    self.queue.emit(
                        job.job_id,
                        EventType.EXPORT_PLANNED,
                        {"operations": [item.operation_id for item in export_plan.operations]},
                    )
                    export_dir = staging / artifact.artifact_id.replace(":", "_")[:40]
                    export_dir.mkdir(parents=True, exist_ok=True)
                    produced.extend(
                        execute_export_plan(
                            export_plan,
                            job_id=job.job_id,
                            source=artifact,
                            source_path=self.store.resolve(artifact),
                            store=self.store,
                            runtime=self.runtime,
                            staging=export_dir,
                            queue=self.queue,
                            authorize=self._authorize,
                            check_control=lambda: self._check_control(job.job_id),
                            existing=existing_ops,
                            skip_operation_ids=skip_ops,
                            on_progress=on_progress,
                        )
                    )
                except (PauseRequested, CancelledError):
                    raise
                except RequiredOperationFailed as exc:
                    export_errors.append(exc)
                    produced.extend(exc.produced)
                    self.queue.emit(
                        job.job_id,
                        EventType.OPERATION_FAILED,
                        {"artifact_id": artifact.artifact_id, "message": str(exc)},
                    )
                    produced.append((artifact, self.store.resolve(artifact)))
                except WebMediaError as exc:
                    export_errors.append(exc)
                    self.queue.emit(
                        job.job_id,
                        EventType.OPERATION_FAILED,
                        {"artifact_id": artifact.artifact_id, "message": str(exc)},
                    )
                    produced.append((artifact, self.store.resolve(artifact)))
            unique: list[tuple[Any, Path]] = []
            seen_ids: set[str] = set()
            for item, path in produced:
                if item.artifact_id in seen_ids:
                    continue
                seen_ids.add(item.artifact_id)
                unique.append((item, path))
            produced = unique
            self._save_acquire_checkpoint(
                job,
                sources,
                acquired_kinds,
                stage="exported",
                produced_ids=[item.artifact_id for item, _path in produced],
                completed_operations=list(completed_ops),
                operation_artifacts=dict(op_arts),
                failed_kinds=failed_kinds,
            )

        self._check_control(job.job_id)
        self.queue.set_state(job.job_id, JobState.VALIDATING)
        publishable: list[tuple[Any, Path, list]] = []
        for item, path in produced:
            self._check_control(job.job_id)
            if item.role is ArtifactRole.PREVIEW:
                continue
            if item.role is ArtifactRole.SOURCE and not job.intent.include_original:
                continue
            try:
                results = validate_artifact(job.job_id, item, path)
                for result in results:
                    self.queue.emit(
                        job.job_id,
                        EventType.VALIDATION_RECORDED,
                        {"gate": result.gate_id, "status": result.status.value},
                    )
                require_pass(results)
                publishable.append((item, path, results))
            except WebMediaError as exc:
                export_errors.append(exc)
                if item.role is ArtifactRole.SOURCE:
                    continue
                continue

        if not publishable:
            if export_errors:
                raise export_errors[0]
            msg = "No publishable artifacts remained after validation."
            raise ProviderPolicyError(msg)

        self.queue.set_state(job.job_id, JobState.PUBLISHING)
        published = publish_artifacts(publishable, job.intent)
        self.queue.emit(
            job.job_id,
            EventType.PUBLISHED,
            {"paths": [str(item) for item in published]},
        )
        completed = self.queue.set_state(job.job_id, JobState.COMPLETED)
        artifact_ids = []
        for item, _path, _results in publishable:
            if item.artifact_id not in artifact_ids:
                artifact_ids.append(item.artifact_id)
        for item in sources:
            if item.artifact_id not in artifact_ids:
                artifact_ids.append(item.artifact_id)
        self.queue.emit(
            job.job_id,
            EventType.JOB_COMPLETED,
            {
                "artifact_ids": artifact_ids,
                "partial": bool(failed_kinds or export_errors),
                "failed_kinds": failed_kinds,
            },
        )
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
            self.client_profile,
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
                    live_artifacts = self._record_live(job, candidate, staging)
                    for live_artifact in live_artifacts:
                        self.queue.emit(
                            job.job_id,
                            EventType.SOURCE_REGISTERED,
                            {
                                "artifact_id": live_artifact.artifact_id,
                                "provider": strategy.provider_id,
                            },
                        )
                        self._record_probe(
                            job,
                            live_artifact,
                            self.store.resolve(live_artifact),
                            candidate.candidate_id,
                        )
                    artifact = live_artifacts
                    break
                request = ProviderRequest(
                    provider_id=strategy.provider_id,
                    capability_id=strategy.capability_id,
                    job_id=job.job_id,
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
                registered: list = []
                paths = [path for path in result.output_paths if path.exists()]
                if not paths and result.output_path is not None:
                    paths = [result.output_path]
                for path in paths:
                    suffix = path.suffix.lower()
                    kind = DIRECT_EXTENSIONS.get(suffix, candidate.media_kind)
                    item = self.store.register(
                        path,
                        role=ArtifactRole.SOURCE,
                        media_kind=kind,
                        provenance={
                            "provider": strategy.provider_id,
                            "job_id": str(job.job_id),
                            "member_of": candidate.media_kind.value,
                        },
                    )
                    self.queue.emit(
                        job.job_id,
                        EventType.SOURCE_REGISTERED,
                        {
                            "artifact_id": item.artifact_id,
                            "provider": strategy.provider_id,
                        },
                    )
                    self._record_probe(job, item, self.store.resolve(item), candidate.candidate_id)
                    registered.append(item)
                if registered:
                    artifact = registered
                    break
                last_error = ProviderPolicyError(
                    f"{strategy.provider_id} produced no source files",
                )
                continue
            except (PauseRequested, CancelledError):
                raise
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
        text = data.decode("utf-8", errors="replace")
        output = staging / "live.bin"
        recorded = record_kind_streams(
            text,
            url,
            output,
            lambda item: self._fetch_bytes(item, self.client_profile, html=False),
            max_bytes=self.client_profile.max_download_bytes,
            should_stop=lambda: self._check_control(job.job_id),
            live_polls=8 if manifest_is_live(text) else 1,
        )
        artifacts = []
        for kind, path in recorded:
            artifacts.append(
                self.store.register(
                    path,
                    role=ArtifactRole.SOURCE,
                    media_kind=kind,
                    provenance={"provider": "live-clear-record", "job_id": str(job.job_id)},
                )
            )
        return artifacts

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
        typed_inputs: dict[str, str] = {"url": url}
        grant_id = self.queue.get_context(job.job_id).cookies
        if grant_id:
            typed_inputs["cookie_grant_id"] = grant_id
        try:
            result = self.runtime.execute(
                ProviderRequest(
                    provider_id="ytdlp",
                    capability_id="discover.manifest",
                    job_id=job.job_id,
                    typed_inputs=typed_inputs,
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
            if any(stream.encrypted for stream in probe.streams) or probe.drm_signals:
                refuse_drm(probe.drm_signals or ["probe:encrypted-stream"])
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
        self.queue.set_job_flags(job_id, cancel_requested=True)
        self.runtime.cancel_running(job_id)
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
        self.queue.set_job_flags(job_id, pause_requested=True)
        self.runtime.pause_running(job_id)
        paused = self.queue.set_state(job_id, JobState.PAUSED)
        self.queue.emit(job_id, EventType.JOB_PAUSED, {"state": "paused"})
        return paused

    def resume_job(self, job_id: UUID) -> Job:
        job = self.queue.get_job(job_id)
        if job.state not in {JobState.PAUSED, JobState.ACCEPTED}:
            msg = f"Job {job_id} cannot be resumed from state {job.state.value}."
            raise PauseRequested(msg)
        self.queue.set_job_flags(job_id, pause_requested=False)
        self.runtime.clear_stop_flags(job_id)
        if job.state is JobState.PAUSED:
            self.queue.set_state(job_id, JobState.ACCEPTED)
        self.queue.emit(job_id, EventType.JOB_RESUMED, {"state": "resumed"})
        if self.queue.is_paused():
            return self.queue.get_job(job_id)
        return self._execute_stored(self.queue.get_job(job_id))

    def run_next(self) -> Job | None:
        job = self.queue.claim_next()
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
        except CancelledError:
            return self.queue.get_job(job.job_id)
        except WebMediaError as exc:
            return self._fail(job.job_id, exc)

    def _fail(self, job_id: UUID, exc: WebMediaError) -> Job:
        logger.warning("job {} failed: {}", job_id, exc)
        try:
            failed = self.queue.set_state(job_id, JobState.FAILED, error=str(exc))
        except (CancelledError, PauseRequested):
            return self.queue.get_job(job_id)
        self.queue.emit(job_id, EventType.JOB_FAILED, {"code": exc.code, "message": str(exc)})
        return failed

    def _check_control(self, job_id: UUID) -> None:
        ctx = self.queue.get_context(job_id)
        job = self.queue.get_job(job_id)
        if ctx.cancel_requested or job.state is JobState.CANCELLED:
            if job.state is not JobState.CANCELLED:
                self.queue.set_state(job_id, JobState.CANCELLED, error="cancelled by user")
            msg = f"Job {job_id} was cancelled."
            raise CancelledError(msg)
        if ctx.pause_requested or job.state is JobState.PAUSED:
            if job.state is not JobState.PAUSED:
                self.queue.set_state(job_id, JobState.PAUSED)
            msg = f"Job {job_id} is paused."
            raise PauseRequested(msg)

    def _save_acquire_checkpoint(
        self,
        job: Job,
        sources: list[Any],
        acquired_kinds: set[str],
        *,
        stage: str,
        produced_ids: list[str] | None = None,
        completed_operations: list[str] | None = None,
        operation_artifacts: dict[str, str] | None = None,
        failed_kinds: list[str] | None = None,
    ) -> None:
        payload = dict(self.queue.get_context(job.job_id).checkpoint)
        payload.update(
            {
                "stage": stage,
                "source_ids": [item.artifact_id for item in sources],
                "acquired_kinds": sorted(acquired_kinds),
            }
        )
        if produced_ids is not None:
            payload["produced_ids"] = produced_ids
        if completed_operations is not None:
            payload["completed_operations"] = completed_operations
        if operation_artifacts is not None:
            payload["operation_artifacts"] = operation_artifacts
        if failed_kinds is not None:
            payload["failed_kinds"] = failed_kinds
        self.queue.put_checkpoint(job.job_id, payload)

    def handle_companion(self, payload: dict[str, Any]) -> dict[str, Any]:
        from webmedia_dl.continuity import validate_companion_message

        message = validate_companion_message(payload)
        self.queue.emit(
            QUEUE_EVENT_JOB_ID,
            EventType.COMPANION_RECEIVED,
            {"kind": message["kind"]},
        )
        kind = message["kind"]
        if kind == "capture":
            surface = Surface(message.get("surface") or Surface.WATCHOS.value)
            job = self.submit(
                str(message["locator"]),
                surface=surface,
                wait=False,
                host_owned=True,
                local_user_confirmed=True,
            )
            return {"kind": kind, "job": job.model_dump(mode="json")}
        if kind == "pause":
            return {**self.pause_queue(), "kind": kind}
        if kind == "resume":
            return {**self.resume_queue(), "kind": kind}
        if kind == "history":
            return {
                "kind": kind,
                "jobs": self.history_entries(),
            }
        if kind == "status":
            return {"kind": kind, "paused": self.queue.is_paused()}
        job_id = UUID(str(message["job_id"]))
        if kind == "cancel":
            return {"kind": kind, "job": self.cancel(job_id).model_dump(mode="json")}
        if kind == "pause_job":
            return {"kind": kind, "job": self.pause_job(job_id).model_dump(mode="json")}
        return {"kind": kind, "job": self.resume_job(job_id).model_dump(mode="json")}

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
        host_owned: bool = False,
    ) -> dict[str, Any]:
        """Ranked acquisition/export plan. Does not retrieve media bytes."""
        job_worker, client_profile = self._job_owner(
            surface,
            local_user_confirmed=local_user_confirmed,
            pairing_id=pairing_id,
            session_key=session_key,
            host_owned=host_owned,
        )
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
        chosen = preferred_by_kind(graph)
        strategies: list[dict[str, Any]] = []
        mixed: list[dict[str, Any]] = []
        for candidate in chosen:
            plan = plan_acquisition(source.source_id, candidate, client_profile)
            item_strategies = [
                {
                    "strategy_id": item.strategy_id,
                    "provider_id": item.provider_id,
                    "capability_id": item.capability_id,
                    "rank": item.rank,
                    "estimated_loss": item.estimated_loss.value,
                }
                for item in plan.strategies
            ]
            mixed.append(
                {
                    "kind": candidate.media_kind.value,
                    "identity_key": candidate.identity_key,
                    "strategies": item_strategies,
                }
            )
            if not strategies:
                strategies = item_strategies
        export_intent = intent or ExportIntent()
        export_operations: list[dict[str, Any]] = []
        if chosen:
            preferred = chosen[0]
            container = None
            if preferred.alternatives:
                container = preferred.alternatives[0].container
            if container is None and source.local_path:
                container = Path(source.local_path).suffix.lstrip(".") or None
            if container is None and preferred.retrieval_urls:
                container = Path(preferred.retrieval_urls[0]).suffix.lstrip(".") or None
            standin = Artifact(
                artifact_id="plan:source",
                role=ArtifactRole.SOURCE,
                sha256="0" * 64,
                byte_size=0,
                media_kind=preferred.media_kind,
                storage_relpath="plan-source.bin",
                container=container or "mp4",
            )
            export_plan = plan_export(source.source_id, standin, export_intent)
            export_operations = [
                {
                    "operation_id": operation.operation_id,
                    "op_type": operation.op_type,
                    "loss_class": operation.loss_class.value,
                }
                for operation in export_plan.operations
            ]
        return {
            "source": source.model_dump(mode="json"),
            "surface": surface.value,
            "client_profile": client_profile.profile_id,
            "worker_id": job_worker.worker_id,
            "candidates": [describe_candidate(item) for item in candidates],
            "conflicts": graph.conflicts,
            "preferred": describe_candidate(chosen[0]) if chosen else None,
            "preferred_by_kind": [describe_candidate(item) for item in chosen],
            "plans": mixed,
            "strategies": strategies,
            "export_intent": export_intent.model_dump(mode="json"),
            "export_operations": export_operations,
            "acquired": False,
        }

    def job(self, job_id: UUID) -> Job:
        return self.queue.get_job(job_id)

    def history(self) -> list[Job]:
        return self.queue.list_jobs()

    def history_entries(self) -> list[dict[str, Any]]:
        return [
            HistoryEntry.from_job(job, self.queue.events_for(job.job_id)).model_dump(mode="json")
            for job in self.history()
        ]


def describe_candidate(candidate: MediaCandidate) -> dict[str, Any]:
    return {
        "identity_key": candidate.identity_key,
        "kind": candidate.media_kind.value,
        "title_display": candidate.title_display,
        "drm": candidate.drm_signals,
    }
