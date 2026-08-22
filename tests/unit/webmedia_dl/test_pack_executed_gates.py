"""Linux-executed pack gates named in START_HERE.md plus catalog parity."""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
from pathlib import Path
from uuid import uuid4

import pytest

from webmedia_dl.domain.enums import ArtifactRole, EvidenceStatus, MediaKind
from webmedia_dl.domain.models import Artifact, MediaProbe, StreamInfo
from webmedia_dl.paths import repo_root
from webmedia_dl.providers import builtin_manifests
from webmedia_dl.validation import validate_semantic_parity


def _load(name: str, relative: str):
    path = repo_root() / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_validate_bundle_executes_start_here_gates() -> None:
    mod = _load("validate_bundle", "scripts/validate_bundle.py")
    assert mod.main() == 0
    listed = json.loads((repo_root() / "manifest.generated.json").read_text(encoding="utf-8"))[
        "files"
    ]
    assert all("dist-bundle" not in path for path in listed)
    assert all(not path.endswith(".zip") for path in listed)


def test_validate_bundle_pins_inventory_path_set() -> None:
    root = repo_root()
    mod = _load("validate_bundle_inventory_pin", "scripts/validate_bundle.py")
    payload = json.loads((root / "scripts/pack_inventory.json").read_text(encoding="utf-8"))
    assert mod.inventory_errors(payload, root) == []
    mismatched = dict(payload)
    mismatched["count"] = 158
    assert any("count field" in item for item in mod.inventory_errors(mismatched, root))
    swapped = dict(payload)
    swapped["paths_relative"] = [*payload["paths_relative"][:-1], "src/webmedia_dl/pipeline.py"]
    assert any("digest mismatch" in item for item in mod.inventory_errors(swapped, root))
    directory = dict(payload)
    directory["paths_relative"] = [*payload["paths_relative"][:-1], "apps"]
    directory_errors = mod.inventory_errors(directory, root)
    assert any("digest mismatch" in item for item in directory_errors)
    assert any("directory" in item for item in directory_errors)


def test_planning_note_writes_column_zero_yaml_front_matter(tmp_path: Path) -> None:
    mod = _load("generate_planning_overlay", "scripts/generate_planning_overlay.py")
    mod.ROOT = tmp_path
    dest = tmp_path / "docs" / "planning" / "build-webmedia-dl-v1"
    dest.mkdir(parents=True)
    mod.planning_note("sample", "Sample", "first line\nsecond line")
    text = (dest / "sample.md").read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert not text.startswith(" ")
    assert 'title: "Sample"' in text.split("---", 2)[1]
    assert text.split("---", 2)[2].lstrip().startswith("# Sample")


def test_package_bundle_skips_symlinks(tmp_path: Path) -> None:
    mod = _load("package_bundle", "scripts/package_bundle.py")
    tree = tmp_path / "tree"
    tree.mkdir()
    keep = tree / "keep.txt"
    keep.write_text("ok", encoding="utf-8")
    (tree / ".env").write_text("SECRET=1", encoding="utf-8")
    (tree / "id_rsa.pem").write_text("key", encoding="utf-8")
    outside = tmp_path / "secret.txt"
    outside.write_text("nope", encoding="utf-8")
    (tree / "escape").symlink_to(outside)
    names = {path.name for path in mod.iter_files(tree)}
    assert "keep.txt" in names
    assert "escape" not in names
    assert "secret.txt" not in names
    assert ".env" not in names
    assert "id_rsa.pem" not in names
    (tree / "queue.sqlite").write_bytes(b"sqlite")
    (tree / "nonces.sqlite-wal").write_bytes(b"wal")
    names = {path.name for path in mod.iter_files(tree)}
    assert "queue.sqlite" not in names
    assert "nonces.sqlite-wal" not in names
    assert "keep.txt" in names
    assert mod.archive_member_is_unsafe("../etc/passwd")
    assert mod.archive_member_is_unsafe("/tmp/x")
    assert not mod.archive_member_is_unsafe("docs/planning/note.md")


def test_semantic_parity_refuses_dropped_audio_stream() -> None:
    job_id = uuid4()
    artifact = Artifact(
        artifact_id="sha256:ab",
        role=ArtifactRole.DERIVATIVE,
        sha256="ab",
        byte_size=1,
        media_kind=MediaKind.VIDEO,
        storage_relpath="a.mkv",
    )
    source = MediaProbe(
        candidate_id=uuid4(),
        duration_ms=1000,
        streams=[
            StreamInfo(index=0, codec="h264", media_kind=MediaKind.VIDEO),
            StreamInfo(index=1, codec="aac", media_kind=MediaKind.AUDIO),
        ],
    )
    dropped = MediaProbe(
        candidate_id=uuid4(),
        duration_ms=1000,
        streams=[StreamInfo(index=0, codec="h264", media_kind=MediaKind.VIDEO)],
    )
    failed = validate_semantic_parity(job_id, artifact, source, dropped)
    assert failed[0].gate_id == "semantic-parity"
    assert failed[0].status is EvidenceStatus.FAIL
    drifted = MediaProbe(
        candidate_id=uuid4(),
        duration_ms=10_000,
        streams=list(source.streams),
    )
    duration = validate_semantic_parity(job_id, artifact, source, drifted)
    assert duration[0].status is EvidenceStatus.FAIL
    assert "duration" in duration[0].message.lower()
    kept = validate_semantic_parity(job_id, artifact, source, source)
    assert kept[0].status is EvidenceStatus.PASS
    blocked = validate_semantic_parity(job_id, artifact, source, None)
    assert blocked[0].status is EvidenceStatus.BLOCKED
    assert blocked[0].executed is False


def test_tool_catalog_matches_builtin_manifests() -> None:
    catalog = json.loads(
        (repo_root() / "resources" / "tool-catalog.json").read_text(encoding="utf-8")
    )
    manifests = builtin_manifests()
    assert set(catalog) == set(manifests)
    for provider_id, row in catalog.items():
        assert row["auto_install"] is False
        assert manifests[provider_id].install_automatic is False
        assert row["binary"] == manifests[provider_id].binary_name


def test_source_registry_kinds_are_media_kinds() -> None:
    registry = json.loads(
        (repo_root() / "resources" / "source-registry.json").read_text(encoding="utf-8")
    )
    allowed = {item.value for item in MediaKind}
    listed: set[str] = set()
    for group in registry.values():
        listed.update(group["kinds"])
    assert listed <= allowed
    assert {"image", "audio", "video", "live_stream", "page", "gallery"} <= listed


def test_imagemagick_inventory_policy_is_subset_of_runtime() -> None:
    root = repo_root()
    inventory = (root / "resources" / "imagemagick-policy.xml").read_text(encoding="utf-8")
    runtime = (root / "resources" / "imagemagick-runtime" / "policy.xml").read_text(
        encoding="utf-8"
    )
    patterns = set(re.findall(r'pattern="([^"]+)"', inventory))
    runtime_patterns = set(re.findall(r'pattern="([^"]+)"', runtime))
    assert patterns
    assert patterns <= runtime_patterns


def test_sync_browser_extensions_matches_checked_in_trees() -> None:
    mod = _load("sync_browser_extensions", "scripts/sync_browser_extensions.py")
    root = repo_root()
    for folder, (name, surface, gecko) in mod.BROWSERS.items():
        dest = root / "extensions" / folder
        packaged = root / "src" / "webmedia_dl" / "runtime" / "extensions" / folder
        assert (dest / "capture.js").read_text(encoding="utf-8") == mod.SHARED
        assert (dest / "popup.html").read_text(encoding="utf-8") == mod.POPUP_HTML
        assert (dest / "popup.js").read_text(encoding="utf-8") == mod.POPUP_JS.format(
            surface=surface
        )
        manifest = json.loads((dest / "manifest.json").read_text(encoding="utf-8"))
        assert manifest == mod.manifest(name, gecko)
        for filename in ("capture.js", "popup.html", "popup.js", "manifest.json"):
            assert (dest / filename).read_bytes() == (packaged / filename).read_bytes()


@pytest.mark.skipif(
    shutil.which("magick") is None and shutil.which("convert") is None,
    reason="ImageMagick is not installed",
)
def test_pipeline_executes_imagemagick_convert(tmp_path: Path, png_bytes: bytes) -> None:
    from webmedia_dl.domain.enums import JobState
    from webmedia_dl.domain.models import ExportIntent
    from webmedia_dl.pipeline import Pipeline

    src = tmp_path / "photo.png"
    src.write_bytes(png_bytes)
    pipeline = Pipeline(data_dir=tmp_path / "data")
    job = pipeline.submit(
        str(src), intent=ExportIntent(container_preference="jpg", allow_lossy=True)
    )
    assert job.state is JobState.COMPLETED
    assert any(
        event.payload.get("operation_id") == "image-convert"
        for event in pipeline.queue.events_for(job.job_id)
    )


def test_week_evidence_files_declare_scope() -> None:
    files = sorted((repo_root() / "docs/build").glob("w*-evidence.md"))
    assert len(files) >= 13
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert re.search(r"(?m)^- status: ", text), path.name
        assert re.search(r"(?m)^- scope: ", text), path.name
        assert re.search(r"(?m)^- reason: ", text), path.name


def test_openspec_capabilities_match_bundle_inventory() -> None:
    root = repo_root()
    specs = sorted(
        path.name
        for path in (root / "openspec/changes/build-webmedia-dl-v1/specs").iterdir()
        if path.is_dir()
    )
    yaml_text = (root / "openspec/changes/build-webmedia-dl-v1/.openspec.yaml").read_text(
        encoding="utf-8"
    )
    declared: list[str] = []
    collecting = False
    for line in yaml_text.splitlines():
        if line.startswith("capabilities:"):
            collecting = True
            continue
        if collecting:
            if line.startswith("  - "):
                declared.append(line[4:].strip())
            elif line.strip() and not line.startswith(" "):
                break
    mod = _load("validate_bundle", "scripts/validate_bundle.py")
    expected = sorted(mod.CAPABILITIES)
    assert specs == expected
    assert sorted(declared) == expected


def test_runtime_dependencies_do_not_bundle_provider_clis() -> None:
    import tomllib

    data = tomllib.loads((repo_root() / "pyproject.toml").read_text(encoding="utf-8"))
    runtime = "\n".join(data["project"]["dependencies"])
    dev = "\n".join(data["dependency-groups"]["dev"])
    assert "yt-dlp" not in runtime
    assert "gallery-dl" not in runtime
    assert "yt-dlp" in dev
    assert "gallery-dl" in dev
    workflow = (repo_root() / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "webmedia-dl doctor" in workflow


def test_validate_bundle_refuses_to_extract_unsafe_members(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import zipfile
    from types import SimpleNamespace

    mod = _load("validate_bundle_unsafe", "scripts/validate_bundle.py")
    pkg = _load("package_bundle_unsafe", "scripts/package_bundle.py")
    extracted: list[bool] = []

    def write_bundle(_root: Path, output: Path) -> str:
        with zipfile.ZipFile(output, "w") as archive:
            archive.writestr("../etc/passwd", "x")
        return "deadbeef"

    def extractall(self: zipfile.ZipFile, path: str | Path | None = None) -> None:
        extracted.append(True)
        raise AssertionError("unsafe archives must not extract")

    monkeypatch.setattr(
        mod,
        "_load_package_bundle",
        lambda: SimpleNamespace(
            write_bundle=write_bundle,
            archive_member_is_unsafe=pkg.archive_member_is_unsafe,
        ),
    )
    monkeypatch.setattr(zipfile.ZipFile, "extractall", extractall)
    errors: list[str] = []
    mod.check_archive_safety_and_extract(errors, ["keep.txt"])
    assert any("unsafe zip member" in item for item in errors)
    assert any("refusing to extract" in item for item in errors)
    assert extracted == []
