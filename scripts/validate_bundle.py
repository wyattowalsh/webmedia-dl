#!/usr/bin/env python3
"""Validate the planning overlay, schemas, invariants, and archive safety."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import zipfile
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
    "src/webmedia_dl/envelope.py",
    "src/webmedia_dl/probe.py",
    "scripts/pack_inventory.json",
    "apps/WebMediaDLCore/Sources/WebMediaDLCore/ShareIntake.swift",
    "apps/WebMediaDLCore/Sources/WebMediaDLCore/ContinuityBridge.swift",
    "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacShareView.swift",
    "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLSubmitURLIntent.swift",
    "extensions/safari/SafariWebExtensionHandler.swift",
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

RECOVERED_SHA256 = {
    "START_HERE.md": "e6b77fb739d11f7665f547c34e0067a4d341e016f20a25710cd6444ac1e50742",
    "docs/planning/build-webmedia-dl-v1/product-brief.md": (
        "06352bc4e84d0a70e0d2c9acb1d6191f69a558b7c9c445e52008745f816a82b4"
    ),
    "docs/planning/build-webmedia-dl-v1/system-architecture.md": (
        "5d56c524ee4f2457f8d52560c1944bba68df11ddf5b98102f924511926abdffb"
    ),
}


INVENTORY_COUNT = 159
INVENTORY_PATHS_SHA256 = "58210026695534887595087274e420b97fa14451713411bcbc4852c989cc888d"


def inventory_errors(payload: object, root: Path) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["pack inventory is not an object"]
    paths = payload.get("paths_relative")
    if not isinstance(paths, list) or not all(isinstance(item, str) for item in paths):
        return ["pack inventory paths_relative is not a string list"]
    declared = payload.get("count")
    if declared != INVENTORY_COUNT:
        errors.append(f"pack inventory count field is {declared}, expected {INVENTORY_COUNT}")
    if len(paths) != INVENTORY_COUNT:
        errors.append(f"pack inventory path list is {len(paths)}, expected {INVENTORY_COUNT}")
    if declared != len(paths):
        errors.append("pack inventory count field does not match path list")
    if len(paths) != len(set(paths)):
        errors.append("pack inventory has duplicate paths")
    digest = hashlib.sha256("\n".join(paths).encode()).hexdigest()
    if digest != INVENTORY_PATHS_SHA256:
        errors.append("pack inventory path set digest mismatch")
    for rel in paths:
        overlay = Path(rel.replace("\\", "/"))
        if overlay.is_absolute() or ".." in overlay.parts:
            errors.append(f"pack inventory path is not a relative overlay {rel}")
            continue
        path = root / rel
        if path.is_dir():
            errors.append(f"pack inventory path is a directory {rel}")
        elif not path.is_file():
            errors.append(f"pack inventory missing {rel}")
    return errors


def fail(errors: list[str]) -> int:
    for item in errors:
        print(f"FAIL: {item}", file=sys.stderr)
    print(f"{len(errors)} error(s)", file=sys.stderr)
    return 1


LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HREF = re.compile(r"""(?:href|src)=["']([^"']+)["']""", re.I)
TASK = re.compile(r"TASK-\d+")
TICK = re.compile(r"`([^`]+)`")
SKIP_LINK_SCHEMES = ("http:", "https:", "mailto:", "data:")


def _load_package_bundle():
    import importlib.util

    path = Path(__file__).resolve().parent / "package_bundle.py"
    spec = importlib.util.spec_from_file_location("package_bundle", path)
    if spec is None or spec.loader is None:
        msg = "Unable to load scripts/package_bundle.py"
        raise RuntimeError(msg)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_markdown_links(errors: list[str], inventory: list[str]) -> None:
    for rel in inventory:
        if not rel.endswith(".md") and not rel.endswith(".html"):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        targets = [match.group(1) for match in LINK.finditer(text)]
        if path.suffix == ".html":
            targets.extend(match.group(1) for match in HREF.finditer(text))
        for raw in targets:
            target = raw.strip()
            if not target or target.startswith("#") or target.startswith(SKIP_LINK_SCHEMES):
                continue
            target = target.split("#", 1)[0]
            if not target:
                continue
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"link escapes repo {rel} -> {raw}")
                continue
            if not resolved.exists():
                errors.append(f"broken link {rel} -> {raw}")


def check_task_dag(errors: list[str]) -> None:
    graph_path = ROOT / "docs/build/task-graph.json"
    tasks_path = ROOT / "openspec/changes/build-webmedia-dl-v1/tasks.md"
    if not graph_path.is_file() or not tasks_path.is_file():
        return
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    listed = graph.get("tasks", [])
    found = TASK.findall(tasks_path.read_text(encoding="utf-8"))
    if sorted(listed) != sorted(set(found)):
        errors.append(
            f"task DAG mismatch: task-graph.json={sorted(listed)!r} tasks.md={sorted(set(found))!r}"
        )


def check_traceability(errors: list[str]) -> None:
    matrix = ROOT / "docs/planning/build-webmedia-dl-v1/traceability-matrix.md"
    if not matrix.is_file():
        return
    tests_root = ROOT / "tests"
    apps_root = ROOT / "apps"
    for token in TICK.findall(matrix.read_text(encoding="utf-8")):
        if " " in token or token.startswith("http"):
            continue
        expanded = token.replace("openspec/.../", "openspec/changes/build-webmedia-dl-v1/")
        specs = token.replace("openspec/.../", "openspec/changes/build-webmedia-dl-v1/specs/")
        if "*" in expanded or "*" in specs:
            if not list(ROOT.glob(expanded)) and not list(ROOT.glob(specs)):
                errors.append(f"traceability glob matched nothing: {token}")
            continue
        if (ROOT / expanded).exists() or (ROOT / specs).exists():
            continue
        name = Path(expanded).name
        hits = list(tests_root.rglob(name)) + list(apps_root.rglob(name))
        script = ROOT / "scripts" / name
        if script.is_file():
            hits.append(script)
        if not hits:
            errors.append(f"traceability missing {token}")


def check_overlay_front_matter(errors: list[str], inventory: list[str]) -> None:
    for rel in inventory:
        if not rel.endswith(".md"):
            continue
        path = ROOT / rel
        if not path.is_file():
            continue
        first = path.read_text(encoding="utf-8").splitlines()[:1]
        if first and first[0].startswith(" ") and first[0].lstrip().startswith("---"):
            errors.append(f"indented YAML front matter {rel}")


def check_archive_safety_and_extract(errors: list[str], inventory: list[str]) -> None:
    bundle = _load_package_bundle()
    with tempfile.TemporaryDirectory(prefix="webmedia-dl-bundle-") as raw:
        tmp = Path(raw)
        archive_path = tmp / "bundle.zip"
        try:
            bundle.write_bundle(ROOT, archive_path)
        except ValueError as exc:
            errors.append(str(exc))
            return
        with zipfile.ZipFile(archive_path) as archive:
            for info in archive.infolist():
                if bundle.archive_member_is_unsafe(info.filename):
                    errors.append(f"unsafe zip member {info.filename}")
                if info.is_dir():
                    continue
            extract_root = tmp / "extracted"
            unsafe = any(
                bundle.archive_member_is_unsafe(info.filename) for info in archive.infolist()
            )
            if unsafe:
                errors.append("refusing to extract archive with unsafe members")
                return
            archive.extractall(extract_root)
        for rel in inventory:
            if not (extract_root / rel).exists():
                errors.append(f"clean extraction missing {rel}")


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
    start_path = ROOT / "START_HERE.md"
    start = start_path.read_text(encoding="utf-8") if start_path.is_file() else ""
    if start:
        for token in ("WebMedia DL", "webmedia-dl", "PASS", "BLOCKED"):
            if token not in start:
                errors.append(f"START_HERE.md missing {token}")
        if (
            "wmdl" in start
            and "personal alias" not in start.lower()
            and "optional personal alias" not in start
        ):
            errors.append("START_HERE.md must qualify wmdl as a personal alias")
    for rel, expected in RECOVERED_SHA256.items():
        path = ROOT / rel
        if not path.is_file():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected:
            errors.append(f"recovered file hash mismatch {rel}")
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
    html_path = ROOT / "guide/index.html"
    if html_path.is_file():
        html = html_path.read_text(encoding="utf-8")
        if 'lang="en"' not in html or "<h1>" not in html:
            errors.append("guide/index.html missing basic accessibility markup")
    inventory_path = ROOT / "scripts/pack_inventory.json"
    inventory_paths: list[str] = []
    inventory_complete = False
    if inventory_path.is_file():
        inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        inv_errs = inventory_errors(inventory, ROOT)
        errors.extend(inv_errs)
        raw_paths = inventory.get("paths_relative") if isinstance(inventory, dict) else inventory
        inventory_paths = [str(rel) for rel in raw_paths] if isinstance(raw_paths, list) else []
        inventory_complete = not inv_errs
        if inventory_paths:
            check_markdown_links(errors, inventory_paths)
            check_overlay_front_matter(errors, inventory_paths)
        check_task_dag(errors)
        check_traceability(errors)
        if inventory_complete:
            check_archive_safety_and_extract(errors, inventory_paths)
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
    skip_parts = {
        ".git",
        ".venv",
        "__pycache__",
        "node_modules",
        ".ruff_cache",
        ".pytest_cache",
        ".ty",
        "htmlcov",
        "dist-bundle",
        ".build",
        ".ci-derived",
        ".ci-derived-appex",
        ".ci-derived-appex-xcode",
    }
    skip_names = {".coverage", "CACHEDIR.TAG"}
    skip_suffix = {".pyc", ".pyo", ".whl", ".so", ".zip"}
    manifest = {
        "files": sorted(
            str(path.relative_to(ROOT))
            for path in ROOT.rglob("*")
            if path.is_file()
            and not any(part in skip_parts for part in path.parts)
            and path.name not in skip_names
            and path.suffix not in skip_suffix
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
