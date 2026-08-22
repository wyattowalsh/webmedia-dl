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
    job = pipeline.submit(str(src), intent=ExportIntent(container_preference="jpg"))
    assert job.state is JobState.COMPLETED
    assert any(
        event.payload.get("operation_id") == "image-convert"
        for event in pipeline.queue.events_for(job.job_id)
    )
