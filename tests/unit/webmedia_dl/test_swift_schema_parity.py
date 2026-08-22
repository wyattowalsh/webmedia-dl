"""Swift Core types expose the same JSON keys as exported Pydantic schemas."""

from __future__ import annotations

import json
import re
from typing import Any, cast

from webmedia_dl.paths import repo_root

SCHEMA_TYPES: dict[str, str] = {
    "media-source": "WebMediaDLMediaSource",
    "media-candidate": "WebMediaDLMediaCandidate",
    "candidate-graph": "WebMediaDLCandidateGraph",
    "media-probe": "WebMediaDLMediaProbe",
    "job": "WebMediaDLPipelineJob",
    "export-intent": "WebMediaDLExportIntent",
    "capability": "WebMediaDLCapability",
    "provider-manifest": "WebMediaDLProviderManifest",
    "policy-profile": "WebMediaDLPolicyProfile",
    "worker": "WebMediaDLWorker",
    "acquisition-plan": "WebMediaDLAcquisitionPlan",
    "artifact": "WebMediaDLArtifact",
    "operation": "WebMediaDLOperation",
    "export-plan": "WebMediaDLExportPlan",
    "validation-result": "WebMediaDLValidationResult",
    "event": "WebMediaDLEvent",
    "history-entry": "WebMediaDLHistoryEntry",
    "security-scoped-bookmark": "WebMediaDLSecurityScopedBookmark",
    "clipboard-locator": "WebMediaDLClipboardIntake",
}

NESTED_TYPES: dict[tuple[str, str], str] = {
    ("media-candidate", "FormatAlternative"): "WebMediaDLFormatAlternative",
    ("candidate-graph", "GraphEdge"): "WebMediaDLGraphEdge",
    ("candidate-graph", "MediaCandidate"): "WebMediaDLMediaCandidate",
    ("media-probe", "StreamInfo"): "WebMediaDLStreamInfo",
    ("export-plan", "Operation"): "WebMediaDLOperation",
    ("acquisition-plan", "AcquisitionStrategy"): "WebMediaDLAcquisitionStrategy",
    ("history-entry", "ExportIntent"): "WebMediaDLExportIntent",
    ("history-entry", "MediaSource"): "WebMediaDLMediaSource",
    ("job", "ExportIntent"): "WebMediaDLExportIntent",
    ("job", "MediaSource"): "WebMediaDLMediaSource",
}

ENUM_TYPES: dict[str, str] = {
    "ArtifactRole": "WebMediaDLArtifactRole",
    "LossClass": "WebMediaDLLossClass",
    "MediaKind": "WebMediaDLMediaKind",
    "IntakeKind": "WebMediaDLIntakeKind",
    "Surface": "WebMediaDLSurface",
    "DestinationKind": "WebMediaDLDestinationKind",
    "CookieAccess": "WebMediaDLCookieAccess",
    "EvidenceStatus": "WebMediaDLEvidenceStatus",
    "JobState": "WebMediaDLJobState",
    "EventType": "WebMediaDLEventType",
}


def _swift_sources() -> str:
    root = repo_root() / "apps/WebMediaDLCore/Sources/WebMediaDLCore"
    return "\n".join(path.read_text(encoding="utf-8") for path in sorted(root.glob("*.swift")))


def _type_body(text: str, name: str) -> str:
    match = re.search(
        rf"(?:public\s+)?(?:struct|enum)\s+{re.escape(name)}\b",
        text,
    )
    assert match is not None, f"missing Swift type {name}"
    brace = text.find("{", match.start())
    assert brace >= 0, name
    depth = 0
    for index, char in enumerate(text[brace:], brace):
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[brace : index + 1]
    raise AssertionError(f"unclosed Swift type {name}")


def _coding_keys(body: str) -> set[str]:
    match = re.search(r"enum CodingKeys[^\{]*\{(.+?)\}", body, flags=re.S)
    if match is None:
        return set()
    keys: set[str] = set()
    for line in match.group(1).splitlines():
        stripped = line.strip().rstrip(",")
        if not stripped.startswith("case "):
            continue
        rest = stripped[len("case ") :]
        for part in rest.split(","):
            token = part.strip()
            if not token:
                continue
            if "=" in token:
                _name, raw = token.split("=", 1)
                keys.add(raw.strip().strip('"'))
            else:
                keys.add(token)
    return keys


def _enum_values(body: str) -> set[str]:
    values: set[str] = set()
    for line in body.splitlines():
        stripped = line.strip().rstrip(",")
        if not stripped.startswith("case "):
            continue
        if stripped.startswith("case ") and "(" in stripped and "=" not in stripped:
            continue
        rest = stripped[len("case ") :]
        for part in rest.split(","):
            token = part.strip()
            if not token or token.startswith("CodingKeys"):
                continue
            if "=" in token:
                _name, raw = token.split("=", 1)
                values.add(raw.strip().strip('"'))
            else:
                values.add(token)
    return values


def _schema(name: str) -> dict[str, Any]:
    path = repo_root() / "schemas" / f"{name}.schema.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return cast(dict[str, Any], payload)


def _object_keys(payload: dict[str, Any], field: str, default: Any) -> set[str]:
    value = payload.get(field, default)
    if isinstance(value, dict):
        return set(value)
    if isinstance(value, list):
        return {str(item) for item in value}
    return set()


def test_index_maps_every_exported_schema() -> None:
    index = json.loads((repo_root() / "schemas" / "index.json").read_text(encoding="utf-8"))
    listed = set(index["schemas"])
    assert listed == set(SCHEMA_TYPES)


def test_swift_coding_keys_cover_schema_properties() -> None:
    text = _swift_sources()
    for schema_name, type_name in SCHEMA_TYPES.items():
        schema = _schema(schema_name)
        properties = _object_keys(schema, "properties", {})
        required = _object_keys(schema, "required", [])
        keys = _coding_keys(_type_body(text, type_name))
        missing_required = required - keys
        extra = keys - properties
        assert not missing_required, f"{type_name} missing required {sorted(missing_required)}"
        assert not extra, f"{type_name} extra keys {sorted(extra)}"
        assert properties <= keys, f"{type_name} missing properties {sorted(properties - keys)}"


def test_nested_schema_defs_match_swift_coding_keys() -> None:
    text = _swift_sources()
    for (schema_name, def_name), type_name in NESTED_TYPES.items():
        schema = _schema(schema_name)
        defs = schema.get("$defs", {})
        assert isinstance(defs, dict)
        nested = defs.get(def_name)
        assert isinstance(nested, dict), def_name
        properties = _object_keys(nested, "properties", {})
        required = _object_keys(nested, "required", [])
        if "properties" not in nested:
            continue
        keys = _coding_keys(_type_body(text, type_name))
        assert required <= keys, f"{type_name} missing required {sorted(required - keys)}"
        assert keys <= properties, f"{type_name} extra keys {sorted(keys - properties)}"
        assert properties <= keys, f"{type_name} missing {sorted(properties - keys)}"


def test_swift_graph_relation_matches_schema() -> None:
    schema = _schema("candidate-graph")
    edge = schema["$defs"]["GraphEdge"]
    assert isinstance(edge, dict)
    relation = edge["properties"]["relation"]
    assert isinstance(relation, dict)
    expected = {str(item) for item in relation["enum"]}
    actual = _enum_values(_type_body(_swift_sources(), "WebMediaDLGraphRelation"))
    assert (
        actual
        == expected
        == {
            "alternative_of",
            "grouped_with",
            "derived_from",
            "conflicts_with",
        }
    )


def test_swift_enum_raw_values_match_schema() -> None:
    text = _swift_sources()
    seen: set[str] = set()
    for schema_path in sorted((repo_root() / "schemas").glob("*.schema.json")):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        assert isinstance(schema, dict)
        defs = schema.get("$defs", {})
        if not isinstance(defs, dict):
            continue
        for def_name, payload in defs.items():
            swift_name = ENUM_TYPES.get(str(def_name))
            if swift_name is None or not isinstance(payload, dict) or "enum" not in payload:
                continue
            if str(def_name) in seen:
                continue
            seen.add(str(def_name))
            enum_values = payload["enum"]
            assert isinstance(enum_values, list)
            expected = {str(item) for item in enum_values}
            actual = _enum_values(_type_body(text, swift_name))
            assert actual == expected, f"{swift_name}: {sorted(actual ^ expected)}"
    assert seen == set(ENUM_TYPES)


def test_domain_invariants_remain_in_swift_source() -> None:
    domain = (repo_root() / "apps/WebMediaDLCore/Sources/WebMediaDLCore/Domain.swift").read_text(
        encoding="utf-8"
    )
    for phrase in (
        "A source URL never becomes a filesystem path.",
        "A display title never becomes artifact identity.",
        "A provider never receives arbitrary user arguments.",
        "A planned or simulated check never becomes runtime PASS.",
        "DRM circumvention is forbidden.",
        "Providers are never installed automatically.",
        'capabilityId: "acquire.http"',
        "required_entitlements",
        "network_schemes",
        "include_original",
        "parent_ids",
        "operation_id",
        "security_scoped_path",
    ):
        assert phrase in domain, phrase


def test_bookmark_and_event_coding_keys_live_in_destinations() -> None:
    destinations = (
        repo_root() / "apps/WebMediaDLCore/Sources/WebMediaDLCore/Destinations.swift"
    ).read_text(encoding="utf-8")
    assert (
        'case path       = "resolved_path"' in destinations
        or 'case path = "resolved_path"' in destinations
    )
    assert 'case bookmarkId = "bookmark_id"' in destinations
    assert 'case id = "event_id"' in destinations
    assert "case ts" in destinations
    history = (repo_root() / "apps/WebMediaDLCore/Sources/WebMediaDLCore/Models.swift").read_text(
        encoding="utf-8"
    )
    assert 'case createdAt = "created_at"' in history
    assert 'case updatedAt = "updated_at"' in history
    assert "case source" in history
    assert "case intent" in history
