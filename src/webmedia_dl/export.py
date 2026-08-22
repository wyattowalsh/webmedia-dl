"""Least-destructive export planner. Does not own provider-specific flags."""

from __future__ import annotations

import json
from functools import lru_cache
from uuid import UUID

from webmedia_dl.domain.enums import ArtifactRole, LossClass, MediaKind
from webmedia_dl.domain.models import Artifact, ExportIntent, ExportPlan, Operation
from webmedia_dl.errors import ProviderPolicyError
from webmedia_dl.paths import runtime_file

IMAGE_CONTAINERS = {"jpg", "jpeg", "png", "webp", "avif", "gif", "tif", "tiff"}
LOSSY_IMAGE_CONTAINERS = {"jpg", "jpeg", "webp", "avif", "gif"}
PASSTHROUGH_KINDS = {MediaKind.DOCUMENT, MediaKind.SUBTITLE}


@lru_cache(maxsize=1)
def load_presets() -> dict[str, dict[str, object]]:
    path = runtime_file("export-presets.json")
    return json.loads(path.read_text(encoding="utf-8"))


def _resolved_intent(intent: ExportIntent) -> ExportIntent:
    presets = load_presets()
    if intent.preset_id not in presets:
        msg = f"Unknown export preset {intent.preset_id!r}."
        raise ProviderPolicyError(msg)
    preset = presets[intent.preset_id]
    allow_lossy = intent.allow_lossy or bool(preset.get("allow_lossy"))
    container = intent.container_preference or preset.get("container_preference")
    include_original = (
        intent.include_original
        if "include_original" not in preset
        else bool(preset.get("include_original", True))
    )
    if container == intent.container_preference and allow_lossy == intent.allow_lossy:
        return intent.model_copy(update={"include_original": include_original})
    return intent.model_copy(
        update={
            "allow_lossy": allow_lossy,
            "container_preference": str(container) if container else intent.container_preference,
            "include_original": include_original,
        }
    )


def plan_export(job_id: UUID, source: Artifact, intent: ExportIntent) -> ExportPlan:
    resolved = _resolved_intent(intent)
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
    preference = resolved.container_preference
    image_like = source.media_kind in {MediaKind.IMAGE, MediaKind.GALLERY} or (
        (source.container or "").lower() in IMAGE_CONTAINERS
        and source.media_kind not in PASSTHROUGH_KINDS
    )
    if source.media_kind in PASSTHROUGH_KINDS:
        return ExportPlan(
            job_id=job_id,
            operations=operations,
            publish_source=resolved.include_original,
        )
    if preference and preference != source.container:
        wanted = preference.lower()
        if image_like and wanted in IMAGE_CONTAINERS:
            lossy_target = wanted in LOSSY_IMAGE_CONTAINERS
            if not lossy_target or resolved.allow_lossy:
                operations.append(
                    Operation(
                        operation_id="image-convert",
                        op_type="imagemagick.convert",
                        capability_id="process.imagemagick.convert",
                        input_artifact_ids=[source.artifact_id],
                        output_role=ArtifactRole.DERIVATIVE,
                        loss_class=LossClass.LOSSY_TRANSCODE if lossy_target else LossClass.NONE,
                        validator_ids=["hash-changed", "container-match"],
                        typed_inputs={"container": preference},
                    )
                )
        elif not resolved.allow_lossy:
            operations.append(
                Operation(
                    operation_id="remux",
                    op_type="ffmpeg.remux",
                    capability_id="process.ffmpeg.remux",
                    input_artifact_ids=[source.artifact_id],
                    output_role=ArtifactRole.DERIVATIVE,
                    loss_class=LossClass.CONTAINER_ONLY,
                    validator_ids=["hash-changed", "container-match"],
                    typed_inputs={"container": preference},
                )
            )
        else:
            operations.append(
                Operation(
                    operation_id="remux",
                    op_type="ffmpeg.remux",
                    capability_id="process.ffmpeg.remux",
                    input_artifact_ids=[source.artifact_id],
                    output_role=ArtifactRole.DERIVATIVE,
                    loss_class=LossClass.CONTAINER_ONLY,
                    validator_ids=["hash-changed", "container-match"],
                    typed_inputs={"container": preference},
                )
            )
            operations.append(
                Operation(
                    operation_id="transcode",
                    op_type="ffmpeg.transcode",
                    capability_id="process.ffmpeg.transcode",
                    input_artifact_ids=[source.artifact_id],
                    output_role=ArtifactRole.DERIVATIVE,
                    loss_class=LossClass.LOSSY_TRANSCODE,
                    validator_ids=["container-match"],
                    typed_inputs={"container": preference},
                )
            )
    elif resolved.allow_lossy and not image_like:
        operations.append(
            Operation(
                operation_id="transcode",
                op_type="ffmpeg.transcode",
                capability_id="process.ffmpeg.transcode",
                input_artifact_ids=[source.artifact_id],
                output_role=ArtifactRole.DERIVATIVE,
                loss_class=LossClass.LOSSY_TRANSCODE,
                validator_ids=["container-match"],
                typed_inputs={"container": source.container or "mp4"},
            )
        )
    if image_like and preference is None:
        operations.append(
            Operation(
                operation_id="image-orient",
                op_type="imagemagick.convert",
                capability_id="process.imagemagick.convert",
                input_artifact_ids=[source.artifact_id],
                output_role=ArtifactRole.PREVIEW,
                loss_class=LossClass.REVERSIBLE_METADATA,
                validator_ids=["hash-match", "size-match"],
                typed_inputs={"container": source.container or "png"},
                optional=True,
            )
        )
    if any(op.loss_class == LossClass.FORBIDDEN for op in operations):
        msg = "Forbidden loss class cannot be planned."
        raise ProviderPolicyError(msg)
    return ExportPlan(
        job_id=job_id,
        operations=operations,
        publish_source=resolved.include_original,
    )
