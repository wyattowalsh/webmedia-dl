"""Validation proves output contracts. It does not make subjective quality claims."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from webmedia_dl.domain.enums import EvidenceStatus
from webmedia_dl.domain.models import Artifact, ValidationResult
from webmedia_dl.errors import SimulatedPassError, ValidationFailed
from webmedia_dl.identity import sha256_file


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


def validate_artifact(job_id: UUID, artifact: Artifact, path: Path) -> list[ValidationResult]:
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
    return results


def require_pass(results: list[ValidationResult]) -> None:
    failures = [item for item in results if item.status == EvidenceStatus.FAIL]
    if failures:
        names = ", ".join(item.gate_id for item in failures)
        msg = f"Mandatory validation failed: {names}."
        raise ValidationFailed(msg)
