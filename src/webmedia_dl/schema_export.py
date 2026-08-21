"""Export JSON Schema documents from the Pydantic domain model."""

from __future__ import annotations

import json
from pathlib import Path

from webmedia_dl.destinations import ClipboardLocator, SecurityScopedBookmark
from webmedia_dl.domain.models import (
    AcquisitionPlan,
    Artifact,
    CandidateGraph,
    Capability,
    EventRecord,
    ExportIntent,
    ExportPlan,
    HistoryEntry,
    Job,
    MediaCandidate,
    MediaProbe,
    MediaSource,
    Operation,
    PolicyProfile,
    ProviderManifest,
    ValidationResult,
    Worker,
)
from webmedia_dl.paths import repo_root

MODELS = {
    "media-source": MediaSource,
    "media-candidate": MediaCandidate,
    "candidate-graph": CandidateGraph,
    "media-probe": MediaProbe,
    "job": Job,
    "export-intent": ExportIntent,
    "capability": Capability,
    "provider-manifest": ProviderManifest,
    "policy-profile": PolicyProfile,
    "worker": Worker,
    "acquisition-plan": AcquisitionPlan,
    "artifact": Artifact,
    "operation": Operation,
    "export-plan": ExportPlan,
    "validation-result": ValidationResult,
    "event": EventRecord,
    "history-entry": HistoryEntry,
    "security-scoped-bookmark": SecurityScopedBookmark,
    "clipboard-locator": ClipboardLocator,
}


def export_schemas(dest: Path | None = None) -> list[Path]:
    root = dest or (repo_root() / "schemas")
    root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    index: dict[str, str] = {}
    for name, model in MODELS.items():
        schema = model.model_json_schema()
        schema["$id"] = f"https://webmedia-dl.local/schemas/{name}.schema.json"
        path = root / f"{name}.schema.json"
        path.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
        written.append(path)
        index[name] = path.name
    (root / "index.json").write_text(
        json.dumps({"schemas": index}, indent=2) + "\n", encoding="utf-8"
    )
    written.append(root / "index.json")
    return written


if __name__ == "__main__":
    for path in export_schemas():
        print(path)
