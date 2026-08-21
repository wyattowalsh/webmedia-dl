#!/usr/bin/env python3
"""Validate the planning overlay, schemas, invariants, and archive safety."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = [
    "START_HERE.md",
    "README.md",
    "AGENTS.md",
    "AUDIT_REPORT.md",
    "CHANGELOG.md",
    "CONTINUATION_PROMPT.md",
    "LICENSE",
    "openspec/config.yaml",
    "openspec/changes/build-webmedia-dl-v1/proposal.md",
    "openspec/changes/build-webmedia-dl-v1/design.md",
    "openspec/changes/build-webmedia-dl-v1/tasks.md",
    "docs/planning/build-webmedia-dl-v1/product-brief.md",
    "docs/planning/build-webmedia-dl-v1/system-architecture.md",
    "docs/planning/build-webmedia-dl-v1/traceability-matrix.md",
    "scripts/package_bundle.py",
    "scripts/validate_bundle.py",
    "guide/index.html",
    "schemas/index.json",
    "resources/policy-profiles.json",
    "resources/export-presets.json",
    "src/webmedia_dl/pipeline.py",
    "src/webmedia_dl/cli.py",
    "scripts/pack_inventory.json",
]

CAPABILITIES = [
    "accessibility-ux",
    "acquisition-adapters",
    "apple-platform-clients",
    "apple-system-integrations",
    "asset-store-provenance",
    "browser-extensions",
    "cross-device-workers",
    "diagnostics-support",
    "discovery-candidates",
    "export-planning",
    "export-validation-publication",
    "intake-routing",
    "live-manifest-recording",
    "media-processing",
    "migration-compatibility",
    "packaging-distribution-updates",
    "queue-events-observability",
    "security-privacy-policy",
]

FORBIDDEN = [
    r"widevine.?decrypt",
    r"cdm.?host",
    r"--enable-file-urls",
    r"accepts_user_argv\s*=\s*True",
]


def fail(errors: list[str]) -> int:
    for item in errors:
        print(f"FAIL: {item}", file=sys.stderr)
    print(f"{len(errors)} error(s)", file=sys.stderr)
    return 1


def main() -> int:
    errors: list[str] = []
    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            errors.append(f"missing {rel}")
    for cap in CAPABILITIES:
        spec = ROOT / "openspec/changes/build-webmedia-dl-v1/specs" / cap / "spec.md"
        if not spec.is_file():
            errors.append(f"missing spec {cap}")
        else:
            text = spec.read_text(encoding="utf-8")
            if "SHALL" not in text and "SHALL NOT" not in text:
                errors.append(f"{cap} spec has no SHALL")
            if "#### Scenario:" not in text:
                errors.append(f"{cap} spec has no Scenario")
    start = (ROOT / "START_HERE.md").read_text(encoding="utf-8")
    for token in ("WebMedia DL", "webmedia-dl", "PASS", "BLOCKED"):
        if token not in start:
            errors.append(f"START_HERE.md missing {token}")
    if (
        "wmdl" in start
        and "personal alias" not in start.lower()
        and "optional personal alias" not in start
    ):
        errors.append("START_HERE.md must qualify wmdl as a personal alias")
    schemas = ROOT / "schemas"
    if schemas.is_dir():
        for path in schemas.glob("*.schema.json"):
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"invalid JSON schema {path.name}: {exc}")
        index = schemas / "index.json"
        if index.is_file():
            json.loads(index.read_text(encoding="utf-8"))
    for path in ROOT.rglob("*"):
        if path.suffix not in {".md", ".py", ".json", ".js", ".swift", ".html", ".yml"}:
            continue
        if (
            ".venv" in path.parts
            or "node_modules" in path.parts
            or path.name == "validate_bundle.py"
            or "tests" in path.parts
        ):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for pattern in FORBIDDEN:
            if re.search(pattern, text, re.I):
                errors.append(f"forbidden pattern {pattern} in {path.relative_to(ROOT)}")
    html = (ROOT / "guide/index.html").read_text(encoding="utf-8")
    if 'lang="en"' not in html or "<h1>" not in html:
        errors.append("guide/index.html missing basic accessibility markup")
    inventory_path = ROOT / "scripts/pack_inventory.json"
    if inventory_path.is_file():
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        paths = inventory.get("paths_relative", inventory if isinstance(inventory, list) else [])
        if len(paths) != 159:
            errors.append(f"pack inventory count is {len(paths)}, expected 159")
        for rel in paths:
            if not (ROOT / rel).exists():
                errors.append(f"pack inventory missing {rel}")
    for browser in ("chromium", "chrome", "brave", "edge", "firefox", "safari"):
        popup = ROOT / "extensions" / browser / "popup.html"
        if not popup.is_file():
            errors.append(f"missing extension popup {browser}")
        else:
            text = popup.read_text(encoding="utf-8")
            if 'lang="en"' not in text or 'for="token"' not in text or "aria-live" not in text:
                errors.append(f"{browser} popup missing accessibility markup")
        manifest = ROOT / "extensions" / browser / "manifest.json"
        if manifest.is_file():
            data = json.loads(manifest.read_text(encoding="utf-8"))
            hosts = data.get("host_permissions", [])
            if hosts != ["http://127.0.0.1:8765/*"]:
                errors.append(f"{browser} host_permissions are not loopback-only")
    for app in (
        "WebMediaDLMac",
        "WebMediaDLiOS",
        "WebMediaDLiPadOS",
        "WebMediaDLVision",
        "WebMediaDLWatch",
        "WebMediaDLTV",
        "WebMediaDLCore",
    ):
        if not (ROOT / "apps" / app).is_dir():
            errors.append(f"missing Apple surface {app}")
    manifest = {
        "files": sorted(
            str(path.relative_to(ROOT))
            for path in ROOT.rglob("*")
            if path.is_file()
            and ".git" not in path.parts
            and ".venv" not in path.parts
            and "__pycache__" not in path.parts
            and "node_modules" not in path.parts
        )
    }
    (ROOT / "manifest.generated.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    if errors:
        return fail(errors)
    print("PASS: bundle validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
