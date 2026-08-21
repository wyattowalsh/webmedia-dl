"""Execute a planned export DAG. Never mutates the registered source."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from webmedia_dl.artifacts import ArtifactStore
from webmedia_dl.domain.enums import ArtifactRole, EventType, JobState
from webmedia_dl.domain.models import Artifact, ExportPlan, Operation
from webmedia_dl.errors import ProviderPolicyError, WebMediaError
from webmedia_dl.providers import ProviderRequest, ProviderRuntime
from webmedia_dl.queue import QueueStore
from webmedia_dl.validation import require_pass, validate_artifact


def provider_for_operation(operation: Operation) -> str:
    if operation.op_type.startswith("ffmpeg."):
        return "ffmpeg"
    if operation.op_type.startswith("imagemagick.") or operation.capability_id.startswith(
        "process.imagemagick"
    ):
        return "imagemagick"
    msg = f"No provider is mapped for operation {operation.op_type!r}."
    raise ProviderPolicyError(msg)


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
) -> list[tuple[Artifact, Path]]:
    """Run non-identity operations. The source bytes are never overwritten."""
    produced: list[tuple[Artifact, Path]] = [(source, source_path)]
    current = source
    current_path = source_path
    queue.set_state(job_id, JobState.EXPORTING)
    for operation in plan.operations:
        if operation.op_type == "identity.copy":
            queue.emit(
                job_id,
                EventType.OPERATION_COMPLETED,
                {"operation_id": operation.operation_id, "op_type": operation.op_type},
            )
            continue
        try:
            authorize(operation.capability_id)
            container = str(operation.typed_inputs.get("container") or "bin")
            output = staging / f"{operation.operation_id}.{container}"
            request = ProviderRequest(
                provider_id=provider_for_operation(operation),
                capability_id=operation.capability_id,
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
            derivative = store.register(
                result.output_path,
                role=ArtifactRole.DERIVATIVE,
                media_kind=current.media_kind,
                container=container,
                parent_ids=[current.artifact_id],
                provenance={
                    "operation_id": operation.operation_id,
                    "op_type": operation.op_type,
                    "parent": current.artifact_id,
                },
            )
            results = validate_artifact(
                job_id,
                derivative,
                result.output_path,
                expected_container=container,
            )
            require_pass(results)
            for item in results:
                queue.emit(
                    job_id,
                    EventType.VALIDATION_RECORDED,
                    {"gate": item.gate_id, "status": item.status.value},
                )
            produced.append((derivative, result.output_path))
            current = derivative
            current_path = result.output_path
            queue.emit(
                job_id,
                EventType.OPERATION_COMPLETED,
                {
                    "operation_id": operation.operation_id,
                    "artifact_id": derivative.artifact_id,
                },
            )
        except WebMediaError as exc:
            queue.emit(
                job_id,
                EventType.OPERATION_FAILED,
                {"operation_id": operation.operation_id, "message": str(exc)},
            )
            if operation.optional:
                continue
            raise
    return produced
