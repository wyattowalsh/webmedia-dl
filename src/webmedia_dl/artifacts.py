"""Immutable artifact store. Bytes are content-addressed; filenames are not identity."""

from __future__ import annotations

import fcntl
import json
import shutil
from pathlib import Path

from webmedia_dl.domain.enums import ArtifactRole, MediaKind
from webmedia_dl.domain.models import Artifact
from webmedia_dl.errors import ArtifactImmutabilityError
from webmedia_dl.identity import artifact_id_for_digest, sha256_file
from webmedia_dl.paths import artifact_dir, quarantine_dir


class ArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.artifacts = artifact_dir(root)
        self.quarantine = quarantine_dir(root)
        self._index_path = self.artifacts / "index.json"
        self._records: dict[str, Artifact] = {}
        self._load()

    def _load(self) -> None:
        if not self._index_path.is_file():
            return
        payload = json.loads(self._index_path.read_text(encoding="utf-8"))
        for item in payload:
            artifact = Artifact.model_validate(item)
            self._records[artifact.artifact_id] = artifact
        self._index_path.chmod(0o600)

    def _lock(self):
        lock_path = self._index_path.with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        handle = lock_path.open("a+")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        return handle

    def _save(self) -> None:
        handle = self._lock()
        try:
            data = [item.model_dump(mode="json") for item in self._records.values()]
            tmp = self._index_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
            tmp.chmod(0o600)
            tmp.replace(self._index_path)
            self._index_path.chmod(0o600)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def register(
        self,
        src: Path,
        *,
        role: ArtifactRole,
        media_kind: MediaKind,
        container: str | None = None,
        parent_ids: list[str] | None = None,
        provenance: dict | None = None,
    ) -> Artifact:
        digest = sha256_file(str(src))
        artifact_id = artifact_id_for_digest(digest)
        dest_dir = self.quarantine if role == ArtifactRole.QUARANTINE else self.artifacts
        relpath = f"{digest[:2]}/{digest}{src.suffix}"
        dest = dest_dir / relpath
        dest.parent.mkdir(parents=True, exist_ok=True)
        existing = self._records.get(artifact_id)
        if existing and existing.immutable:
            if existing.sha256 != digest:
                msg = "A source artifact is never mutated after registration."
                raise ArtifactImmutabilityError(msg)
            occurrences = list(existing.provenance.get("occurrences") or [])
            if not occurrences and existing.provenance:
                seed = {
                    key: value for key, value in existing.provenance.items() if key != "occurrences"
                }
                if seed:
                    occurrences.append(seed)
            if provenance:
                occurrences.append(
                    {
                        **provenance,
                        "role": role.value,
                        "parent_ids": list(parent_ids or []),
                    }
                )
            merged_parents = list(dict.fromkeys([*existing.parent_ids, *(parent_ids or [])]))
            updated = existing.model_copy(
                update={
                    "parent_ids": merged_parents,
                    "provenance": {**existing.provenance, "occurrences": occurrences},
                }
            )
            self._records[artifact_id] = updated
            self._save()
            return updated
        if not dest.exists():
            shutil.copy2(src, dest)
        if role == ArtifactRole.SOURCE:
            dest.chmod(0o444)
        artifact = Artifact(
            artifact_id=artifact_id,
            role=role,
            sha256=digest,
            byte_size=dest.stat().st_size,
            media_kind=media_kind,
            container=container or src.suffix.lstrip(".") or None,
            storage_relpath=str(dest.relative_to(self.root)),
            parent_ids=parent_ids or [],
            immutable=role == ArtifactRole.SOURCE,
            provenance=provenance or {},
        )
        self._records[artifact_id] = artifact
        self._save()
        return artifact

    def get(self, artifact_id: str) -> Artifact:
        return self._records[artifact_id]

    def list_artifacts(self) -> list[Artifact]:
        return list(self._records.values())

    def lineage(self, artifact_id: str) -> list[Artifact]:
        if artifact_id not in self._records:
            raise KeyError(artifact_id)
        ordered: list[Artifact] = []
        seen: set[str] = set()
        stack = [artifact_id]
        while stack:
            current_id = stack.pop()
            if current_id in seen:
                continue
            seen.add(current_id)
            artifact = self._records.get(current_id)
            if artifact is None:
                continue
            ordered.append(artifact)
            stack.extend(reversed(artifact.parent_ids))
        return ordered

    def resolve(self, artifact: Artifact) -> Path:
        return self.root / artifact.storage_relpath

    def mutate_source(self, artifact_id: str, data: bytes) -> None:
        artifact = self._records[artifact_id]
        if artifact.immutable or artifact.role == ArtifactRole.SOURCE:
            msg = "A source artifact is never mutated after registration."
            raise ArtifactImmutabilityError(msg)
        path = self.resolve(artifact)
        path.write_bytes(data)
