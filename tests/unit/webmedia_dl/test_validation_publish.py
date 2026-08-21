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
