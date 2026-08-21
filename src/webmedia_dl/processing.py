"""Execute a planned export DAG. Never mutates the registered source."""

from __future__ import annotations

from collections.abc import Callable
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
from uuid import UUID

from webmedia_dl.artifacts import ArtifactStore
from webmedia_dl.domain.enums import ArtifactRole, EventType, JobState
from webmedia_dl.domain.models import Artifact, ExportPlan, Operation
from webmedia_dl.errors import (
    CancelledError,
    PauseRequested,
    ProviderPolicyError,
    RequiredOperationFailed,
    WebMediaError,
)
from webmedia_dl.probe import probe_media
from webmedia_dl.providers import ProviderRequest, ProviderRuntime
from webmedia_dl.queue import QueueStore
from webmedia_dl.validation import require_pass, validate_artifact, validate_probe


def provider_for_operation(operation: Operation) -> str:
    if operation.op_type.startswith("ffmpeg."):
        return "ffmpeg"
    if operation.op_type.startswith("imagemagick.") or operation.capability_id.startswith(
        "process.imagemagick"
    ):
        return "imagemagick"
    msg = f"No provider is mapped for operation {operation.op_type!r}."
    raise ProviderPolicyError(msg)


def ordered_operations(plan: ExportPlan) -> list[Operation]:
    """Topological order. Edges are operation_id references in input_artifact_ids."""
    ops = {item.operation_id: item for item in plan.operations}
    sorter: TopologicalSorter[str] = TopologicalSorter()
    for operation in plan.operations:
        deps = [item for item in operation.input_artifact_ids if item in ops]
        if operation.operation_id == "transcode" and "remux" in ops:
            deps.append("remux")
        sorter.add(operation.operation_id, *deps)
    try:
        order = list(sorter.static_order())
    except CycleError as exc:
        msg = "Export plan is not a DAG."
        raise ProviderPolicyError(msg) from exc
    return [ops[item] for item in order]


def execute_export_plan(
    plan: ExportPlan,
    *,
    job_id: UUID,
    source: Artifact,
    source_path: Path,
    store: ArtifactStore,
    runtime: ProviderRuntime,
    staging: Path,
    queue: QueueStore,
    authorize,
    check_control: Callable[[], None] | None = None,
    existing: dict[str, tuple[Artifact, Path]] | None = None,
    skip_operation_ids: set[str] | None = None,
    on_progress: Callable[[Operation, Artifact | None], None] | None = None,
) -> list[tuple[Artifact, Path]]:
    """Run non-identity operations. Independent ops fail without invalidating siblings."""
    produced: list[tuple[Artifact, Path]] = [(source, source_path)]
    artifacts: dict[str, tuple[Artifact, Path]] = {source.artifact_id: (source, source_path)}
    seen = {source.artifact_id}
    if existing:
        for key, pair in existing.items():
            artifacts[key] = pair
            artifact, _path = pair
            if artifact.artifact_id not in seen:
                produced.append(pair)
                seen.add(artifact.artifact_id)
    skip = skip_operation_ids or set()
    staging.mkdir(parents=True, exist_ok=True)
    queue.set_state(job_id, JobState.EXPORTING)
    op_ids = {item.operation_id for item in plan.operations}
    failed_ops: set[str] = set()
    required_failures: list[WebMediaError] = []
    for operation in ordered_operations(plan):
        if check_control is not None:
            check_control()
        compound = f"{source.artifact_id}:{operation.operation_id}"
        if existing and compound in existing:
            artifacts[operation.operation_id] = existing[compound]
            artifacts[compound] = existing[compound]
            continue
        if operation.operation_id in skip and operation.operation_id in artifacts:
            continue
        if compound in skip:
            continue
        if (
            operation.operation_id == "transcode"
            and "remux" in op_ids
            and "remux" in artifacts
            and "remux" not in failed_ops
        ):
            continue
        if any(dep in failed_ops for dep in operation.input_artifact_ids if dep in op_ids):
            failed_ops.add(operation.operation_id)
            if not operation.optional:
                required_failures.append(
                    ProviderPolicyError(f"{operation.operation_id} skipped; required input failed.")
                )
            continue
        if operation.op_type == "identity.copy":
            artifacts[operation.operation_id] = (source, source_path)
            queue.emit(
                job_id,
                EventType.OPERATION_COMPLETED,
                {"operation_id": operation.operation_id, "op_type": operation.op_type},
            )
            if on_progress is not None:
                on_progress(operation, source)
            continue
        try:
            current, current_path = _resolve_input(operation, artifacts, source, source_path)
            authorize(operation.capability_id)
            container = str(operation.typed_inputs.get("container") or "bin")
            output = staging / f"{operation.operation_id}.{container}"
            provider = provider_for_operation(operation)
            request = ProviderRequest(
                provider_id=provider,
                capability_id=operation.capability_id,
                job_id=job_id,
                typed_inputs={
                    "input": str(current_path),
                    "output": str(output),
                    **operation.typed_inputs,
                },
            )
            result = runtime.execute(request, staging)
            if (
                result.exit_code != 0
                or result.output_path is None
                or not result.output_path.exists()
            ):
                msg = f"{operation.operation_id} exited {result.exit_code}"
                raise ProviderPolicyError(msg)
            role = operation.output_role
            if role is ArtifactRole.SOURCE:
                role = ArtifactRole.DERIVATIVE
            derivative = store.register(
                result.output_path,
                role=role,
                media_kind=current.media_kind,
                container=container,
                parent_ids=[current.artifact_id],
                provenance={
                    "operation_id": operation.operation_id,
                    "op_type": operation.op_type,
                    "parent": current.artifact_id,
                },
            )
            # ImageMagick writes the requested still-image format; ffprobe often
            # reports the generic `image2` demuxer instead of jpeg/png/webp.
            expected_container = None if provider == "imagemagick" else container
            results = validate_artifact(
                job_id,
                derivative,
                result.output_path,
                expected_container=expected_container,
            )
            require_pass(results)
            for item in results:
                queue.emit(
                    job_id,
                    EventType.VALIDATION_RECORDED,
                    {"gate": item.gate_id, "status": item.status.value},
                )
            if operation.op_type.startswith("ffmpeg."):
                probe = probe_media(result.output_path)
                probe_results = validate_probe(job_id, derivative, probe)
                for item in probe_results:
                    queue.emit(
                        job_id,
                        EventType.VALIDATION_RECORDED,
                        {"gate": item.gate_id, "status": item.status.value},
                    )
                if probe is not None:
                    require_pass(probe_results, identity_gates=False)
            produced.append((derivative, result.output_path))
            artifacts[derivative.artifact_id] = (derivative, result.output_path)
            artifacts[operation.operation_id] = (derivative, result.output_path)
            queue.emit(
                job_id,
                EventType.OPERATION_COMPLETED,
                {
                    "operation_id": operation.operation_id,
                    "artifact_id": derivative.artifact_id,
                    "role": role.value,
                },
            )
            if on_progress is not None:
                on_progress(operation, derivative)
        except (PauseRequested, CancelledError):
            raise
        except WebMediaError as exc:
            failed_ops.add(operation.operation_id)
            queue.emit(
                job_id,
                EventType.OPERATION_FAILED,
                {"operation_id": operation.operation_id, "message": str(exc)},
            )
            if operation.optional:
                continue
            required_failures.append(exc)
            continue
    if required_failures:
        raise RequiredOperationFailed(str(required_failures[0]), produced=produced)
    return produced


def _resolve_input(
    operation: Operation,
    artifacts: dict[str, tuple[Artifact, Path]],
    source: Artifact,
    source_path: Path,
) -> tuple[Artifact, Path]:
    if not operation.input_artifact_ids:
        return source, source_path
    for item in operation.input_artifact_ids:
        if item in artifacts:
            return artifacts[item]
    msg = f"{operation.operation_id} is missing inputs {operation.input_artifact_ids}."
    raise ProviderPolicyError(msg)
