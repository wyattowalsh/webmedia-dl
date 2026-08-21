"""Least-destructive export planner. Does not own provider-specific flags."""

from __future__ import annotations

from uuid import UUID

from webmedia_dl.domain.enums import ArtifactRole, LossClass
from webmedia_dl.domain.models import Artifact, ExportIntent, ExportPlan, Operation
from webmedia_dl.errors import ProviderPolicyError


def plan_export(job_id: UUID, source: Artifact, intent: ExportIntent) -> ExportPlan:
    operations = [
        Operation(
            operation_id="keep-original",
            op_type="identity.copy",
            capability_id="export.plan",
            input_artifact_ids=[source.artifact_id],
            output_role=ArtifactRole.SOURCE,
            loss_class=LossClass.NONE,
            validator_ids=["hash-match", "size-match"],
            typed_inputs={},
        )
    ]
    if intent.container_preference and intent.container_preference != source.container:
        if not intent.allow_lossy:
            operations.append(
                Operation(
                    operation_id="remux",
                    op_type="ffmpeg.remux",
                    capability_id="process.ffmpeg.remux",
                    input_artifact_ids=[source.artifact_id],
                    output_role=ArtifactRole.DERIVATIVE,
                    loss_class=LossClass.CONTAINER_ONLY,
                    validator_ids=["hash-changed", "container-match"],
                    typed_inputs={"container": intent.container_preference},
                )
            )
        else:
            operations.append(
                Operation(
                    operation_id="transcode",
                    op_type="ffmpeg.transcode",
                    capability_id="process.ffmpeg.transcode",
                    input_artifact_ids=[source.artifact_id],
                    output_role=ArtifactRole.DERIVATIVE,
                    loss_class=LossClass.LOSSY_TRANSCODE,
                    validator_ids=["container-match"],
                    typed_inputs={"container": intent.container_preference},
                )
            )
    if any(op.loss_class == LossClass.FORBIDDEN for op in operations):
        msg = "Forbidden loss class cannot be planned."
        raise ProviderPolicyError(msg)
    return ExportPlan(
        job_id=job_id,
        operations=operations,
        publish_source=intent.include_original,
    )
