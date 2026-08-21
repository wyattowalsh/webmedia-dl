"""Validation proves output contracts. It does not make subjective quality claims."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from webmedia_dl.domain.enums import EvidenceStatus
from webmedia_dl.domain.models import Artifact, MediaProbe, ValidationResult
from webmedia_dl.errors import SimulatedPassError, ValidationFailed
from webmedia_dl.identity import sha256_file
from webmedia_dl.probe import probe_media

CONTAINER_ALIASES = {
    "matroska": "mkv",
    "quicktime": "mov",
    "mpegts": "ts",
    "jpeg": "jpg",
    "jpeg_pipe": "jpg",
    "mjpeg": "jpg",
    "png_pipe": "png",
    "webp_pipe": "webp",
    "gif_pipe": "gif",
    "tiff": "tif",
}

STILL_IMAGE_CONTAINERS = {"jpg", "jpeg", "png", "webp", "gif", "tif", "tiff", "avif", "bmp"}
GENERIC_IMAGE_PROBE = {"image2"}


def normalize_container(name: str | None) -> str | None:
    if not name:
        return None
    token = name.strip().lower()
    return CONTAINER_ALIASES.get(token, token)


def container_matches(probe_name: str | None, expected: str) -> bool:
    expected_n = normalize_container(expected)
    if not expected_n or not probe_name:
        return False
    tokens = {
        token
        for part in probe_name.split(",")
        if part.strip()
        for token in [normalize_container(part)]
        if token
    }
    if expected_n in tokens:
        return True
    return expected_n in STILL_IMAGE_CONTAINERS and bool(tokens & GENERIC_IMAGE_PROBE)


def record_result(
    *,
    job_id: UUID,
    artifact_id: str,
    gate_id: str,
    status: EvidenceStatus,
    message: str,
    simulated: bool = False,
    planned: bool = False,
    executed: bool = True,
    details: dict | None = None,
) -> ValidationResult:
    if status == EvidenceStatus.PASS and (simulated or planned or not executed):
        raise SimulatedPassError("A planned or simulated check never becomes runtime PASS.")
    return ValidationResult(
        job_id=job_id,
        target_artifact_id=artifact_id,
        gate_id=gate_id,
        status=status,
        message=message,
        simulated=simulated,
        planned=planned,
        executed=executed,
        details=details or {},
    )


def validate_artifact(
    job_id: UUID,
    artifact: Artifact,
    path: Path,
    *,
    expected_container: str | None = None,
) -> list[ValidationResult]:
    results: list[ValidationResult] = []
    if not path.is_file():
        results.append(
            record_result(
                job_id=job_id,
                artifact_id=artifact.artifact_id,
                gate_id="exists",
                status=EvidenceStatus.FAIL,
                message="Artifact path is missing.",
            )
        )
        return results
    digest = sha256_file(str(path))
    size = path.stat().st_size
    hash_status = EvidenceStatus.PASS if digest == artifact.sha256 else EvidenceStatus.FAIL
    results.append(
        record_result(
            job_id=job_id,
            artifact_id=artifact.artifact_id,
            gate_id="hash-match",
            status=hash_status,
            message="Content digest matches the registered artifact."
            if hash_status is EvidenceStatus.PASS
            else "Digest mismatch.",
            details={"expected": artifact.sha256, "actual": digest},
        )
    )
    size_status = EvidenceStatus.PASS if size == artifact.byte_size else EvidenceStatus.FAIL
    results.append(
        record_result(
            job_id=job_id,
            artifact_id=artifact.artifact_id,
            gate_id="size-match",
            status=size_status,
            message="Byte size matches."
            if size_status is EvidenceStatus.PASS
            else "Byte size mismatch.",
            details={"expected": artifact.byte_size, "actual": size},
        )
    )
    if expected_container:
        probe = probe_media(path)
        if probe is None or not (probe.format_names or probe.container):
            results.append(
                record_result(
                    job_id=job_id,
                    artifact_id=artifact.artifact_id,
                    gate_id="container-match",
                    status=EvidenceStatus.BLOCKED,
                    message="Container gate requires ffprobe evidence.",
                    executed=probe is not None,
                    details={"expected": expected_container, "suffix": path.suffix},
                )
            )
        else:
            actual_blob = probe.format_names or probe.container or ""
            container_status = (
                EvidenceStatus.PASS
                if container_matches(actual_blob, expected_container)
                else EvidenceStatus.FAIL
            )
            results.append(
                record_result(
                    job_id=job_id,
                    artifact_id=artifact.artifact_id,
                    gate_id="container-match",
                    status=container_status,
                    message="Container matches the export plan."
                    if container_status is EvidenceStatus.PASS
                    else f"Expected container {expected_container}, found {actual_blob}.",
                    details={"expected": expected_container, "actual": actual_blob},
                )
            )
    return results


def validate_probe(
    job_id: UUID,
    artifact: Artifact,
    probe: MediaProbe | None,
) -> list[ValidationResult]:
    if probe is None:
        return [
            record_result(
                job_id=job_id,
                artifact_id=artifact.artifact_id,
                gate_id="probe-available",
                status=EvidenceStatus.BLOCKED,
                message="ffprobe was not available; probe gate was not executed.",
                executed=False,
            )
        ]
    if not probe.streams:
        return [
            record_result(
                job_id=job_id,
                artifact_id=artifact.artifact_id,
                gate_id="probe-streams",
                status=EvidenceStatus.WARN,
                message="Probe recorded no streams.",
            )
        ]
    if any(stream.encrypted for stream in probe.streams) or probe.drm_signals:
        return [
            record_result(
                job_id=job_id,
                artifact_id=artifact.artifact_id,
                gate_id="drm-clear",
                status=EvidenceStatus.FAIL,
                message="Probe recorded encrypted streams; DRM circumvention is refused.",
                details={"drm_signals": probe.drm_signals},
            )
        ]
    return [
        record_result(
            job_id=job_id,
            artifact_id=artifact.artifact_id,
            gate_id="probe-streams",
            status=EvidenceStatus.PASS,
            message="Probe recorded stream facts.",
            details={"streams": len(probe.streams), "container": probe.container},
        )
    ]


IDENTITY_GATES = ("hash-match", "size-match")


def require_pass(
    results: list[ValidationResult],
    *,
    identity_gates: bool = True,
) -> None:
    if not results:
        msg = "Mandatory validation produced no executed evidence."
        raise ValidationFailed(msg)
    closed = [
        item for item in results if item.status in {EvidenceStatus.FAIL, EvidenceStatus.BLOCKED}
    ]
    if closed:
        names = ", ".join(f"{item.gate_id}:{item.status.value}" for item in closed)
        msg = f"Mandatory validation failed: {names}."
        raise ValidationFailed(msg)
    if not identity_gates:
        return
    by_gate = {item.gate_id: item for item in results}
    if not any(gate in by_gate for gate in IDENTITY_GATES):
        return
    for gate in IDENTITY_GATES:
        item = by_gate.get(gate)
        if item is None or item.status is not EvidenceStatus.PASS or not item.executed:
            msg = f"Mandatory validation missing executed PASS for {gate}."
            raise ValidationFailed(msg)
