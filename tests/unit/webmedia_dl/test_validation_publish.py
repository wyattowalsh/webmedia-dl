from pathlib import Path
from uuid import uuid4

import pytest

from webmedia_dl.domain.enums import ArtifactRole, EvidenceStatus, MediaKind
from webmedia_dl.domain.models import Artifact, ExportIntent
from webmedia_dl.errors import SimulatedPassError, ValidationFailed
from webmedia_dl.network_policy import authorize_destination
from webmedia_dl.publish import publish_artifacts
from webmedia_dl.validation import record_result, require_pass, validate_artifact


def test_validate_hash_and_size(tmp_path: Path) -> None:
    path = tmp_path / "a.bin"
    path.write_bytes(b"abc")
    from webmedia_dl.identity import sha256_file

    digest = sha256_file(str(path))
    artifact = Artifact(
        artifact_id=f"sha256:{digest}",
        role=ArtifactRole.SOURCE,
        sha256=digest,
        byte_size=3,
        media_kind=MediaKind.UNKNOWN,
        storage_relpath="a.bin",
    )
    results = validate_artifact(uuid4(), artifact, path)
    require_pass(results)


def test_require_pass_raises() -> None:
    result = record_result(
        job_id=uuid4(),
        artifact_id="sha256:x",
        gate_id="hash-match",
        status=EvidenceStatus.FAIL,
        message="nope",
    )
    with pytest.raises(ValidationFailed):
        require_pass([result])


def test_require_pass_rejects_blocked_and_empty() -> None:
    blocked = record_result(
        job_id=uuid4(),
        artifact_id="sha256:x",
        gate_id="container-match",
        status=EvidenceStatus.BLOCKED,
        message="probe missing",
    )
    with pytest.raises(ValidationFailed, match="BLOCKED"):
        require_pass([blocked])
    with pytest.raises(ValidationFailed, match="no executed evidence"):
        require_pass([])
    probe_only = record_result(
        job_id=uuid4(),
        artifact_id="sha256:x",
        gate_id="probe-streams",
        status=EvidenceStatus.PASS,
        message="streams",
    )
    require_pass([probe_only], identity_gates=False)
    with pytest.raises(ValidationFailed, match="hash-match"):
        require_pass([probe_only])
    hash_only = record_result(
        job_id=uuid4(),
        artifact_id="sha256:x",
        gate_id="hash-match",
        status=EvidenceStatus.PASS,
        message="hash",
    )
    with pytest.raises(ValidationFailed, match="size-match"):
        require_pass([hash_only])
    both = [
        record_result(
            job_id=uuid4(),
            artifact_id="sha256:x",
            gate_id="hash-match",
            status=EvidenceStatus.PASS,
            message="hash",
        ),
        record_result(
            job_id=uuid4(),
            artifact_id="sha256:x",
            gate_id="size-match",
            status=EvidenceStatus.PASS,
            message="size",
        ),
    ]
    require_pass(both)
    with pytest.raises(ValidationFailed, match="does not match the artifact"):
        require_pass(both, artifact_id="sha256:other")


def test_blank_approved_roots_are_denied(tmp_path: Path) -> None:
    from webmedia_dl.errors import NetworkPolicyError

    target = tmp_path / "out"
    target.mkdir()
    with pytest.raises(NetworkPolicyError, match="non-blank absolute"):
        authorize_destination(target, [""])
    with pytest.raises(NetworkPolicyError, match="non-blank absolute"):
        authorize_destination(target, ["  "])
    with pytest.raises(NetworkPolicyError, match="non-blank absolute"):
        authorize_destination(target, ["."])
    with pytest.raises(NetworkPolicyError, match="non-blank absolute"):
        authorize_destination(target, [])
    assert authorize_destination(target, [str(tmp_path)]) == target.resolve()


def test_record_result_blocks_simulated_pass() -> None:
    with pytest.raises(SimulatedPassError):
        record_result(
            job_id=uuid4(),
            artifact_id="sha256:x",
            gate_id="demo",
            status=EvidenceStatus.PASS,
            message="no",
            simulated=True,
            executed=False,
        )


def test_publish_stays_inside_approved_root(tmp_path: Path) -> None:
    src = tmp_path / "src.bin"
    src.write_bytes(b"data")
    from webmedia_dl.identity import sha256_file

    digest = sha256_file(str(src))
    artifact = Artifact(
        artifact_id=f"sha256:{digest}",
        role=ArtifactRole.SOURCE,
        sha256=digest,
        byte_size=4,
        media_kind=MediaKind.UNKNOWN,
        storage_relpath="src.bin",
    )
    dest = tmp_path / "out"
    dest.mkdir()
    intent = ExportIntent(
        destination_kind="user_approved_path",
        destination_path=str(dest),
        approved_roots=[str(dest)],
    )
    results = validate_artifact(uuid4(), artifact, src)
    published = publish_artifacts([(artifact, src, results)], intent)
    assert published
    assert published[0].is_file()
    assert published[0].is_relative_to(dest)


def test_destination_outside_roots_denied(tmp_path: Path) -> None:
    from webmedia_dl.errors import NetworkPolicyError

    with pytest.raises(NetworkPolicyError):
        authorize_destination(tmp_path / "other", [str(tmp_path / "allowed")])
