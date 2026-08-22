"""OpenSpec SHALL proofs that were previously unasserted or fail-open."""

from __future__ import annotations

import ast
import importlib.util
import re
import zipfile
from collections import Counter
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from webmedia_dl.candidates import build_graph
from webmedia_dl.diagnostics import doctor
from webmedia_dl.domain.enums import DestinationKind, EventType, MediaKind, Surface
from webmedia_dl.domain.models import ExportIntent, MediaCandidate
from webmedia_dl.errors import CapabilityDenied, DrmRefused, ProviderPolicyError
from webmedia_dl.identity import is_safe_format_id
from webmedia_dl.live import inspect_manifest, record_clear_stream, recordable_parts
from webmedia_dl.paths import repo_root
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import assert_worker_capability, get_profile
from webmedia_dl.providers import (
    ProviderRequest,
    ProviderRuntime,
    _assert_allowed_flags,
    builtin_manifests,
)
from webmedia_dl.queue import QUEUE_EVENT_JOB_ID
from webmedia_dl.security import detect_drm_signals, refuse_drm


def test_session_key_fairplay_is_refused_before_fetch(tmp_path: Path) -> None:
    playlist = (
        "#EXTM3U\n"
        '#EXT-X-SESSION-KEY:METHOD=SAMPLE-AES,URI="skd://key",'
        'KEYFORMAT="com.apple.streamingkeydelivery"\n'
        "#EXTINF:4,\n"
        "seg1.ts\n"
        "#EXTINF:4,\n"
        "seg2.ts\n"
    )
    with pytest.raises(DrmRefused, match="session encryption"):
        inspect_manifest(playlist)
    with pytest.raises(DrmRefused, match="session encryption"):
        recordable_parts(playlist, "https://cdn.example.com/index.m3u8")

    def fetch(_url: str) -> tuple[int, str, bytes]:
        raise AssertionError("encrypted session playlists must not fetch segments")

    with pytest.raises(DrmRefused, match="session encryption"):
        record_clear_stream(
            playlist,
            "https://cdn.example.com/index.m3u8",
            tmp_path / "out.ts",
            fetch,
        )


def test_detect_drm_signals_covers_cenc_and_system_uuids() -> None:
    assert detect_drm_signals('schemeIdUri="urn:mpeg:cenc:2013" cenc:default_KID="aa"')
    assert detect_drm_signals("urn:uuid:EDEF8BA9-79D6-4ACE-A3C8-27DCD51D21ED")
    assert detect_drm_signals("urn:uuid:9A04F079-9840-4286-AB92-E65BE0885F95")
    assert detect_drm_signals('KEYFORMAT="com.apple.streamingkeydelivery" skd://clip')
    assert detect_drm_signals('value="cbcs"')
    with pytest.raises(DrmRefused):
        refuse_drm(detect_drm_signals("urn:mpeg:dash:mp4protection:2011"))


def test_candidate_graph_records_duplicates_drm_and_grouping() -> None:
    source_id = uuid4()
    shared = "host:cdn.example.com"
    first = MediaCandidate(
        source_id=source_id,
        media_kind=MediaKind.VIDEO,
        identity_key="host:cdn.example.com:path:/a.mp4",
        grouping_key=shared,
        host="cdn.example.com",
        retrieval_urls=["https://cdn.example.com/a.mp4"],
    )
    duplicate = MediaCandidate(
        source_id=source_id,
        media_kind=MediaKind.VIDEO,
        identity_key="host:cdn.example.com:path:/a.mp4",
        grouping_key=shared,
        host="cdn.example.com",
        retrieval_urls=["https://cdn.example.com/a.mp4?alt=1"],
        drm_signals=["widevine"],
    )
    graph = build_graph(uuid4(), [first, duplicate])
    relations = {edge.relation for edge in graph.edges}
    assert "grouped_with" in relations
    assert "alternative_of" in relations
    assert any(item.startswith("duplicate-identity:") for item in graph.conflicts)
    assert f"drm:{duplicate.identity_key}" in graph.conflicts


def test_queue_events_use_zero_uuid(tmp_data: Path) -> None:
    assert UUID(int=0) == QUEUE_EVENT_JOB_ID
    pipeline = Pipeline(data_dir=tmp_data)
    pipeline.pause_queue()
    pipeline.resume_queue()
    events = pipeline.queue.events_for(QUEUE_EVENT_JOB_ID)
    types = {event.type for event in events}
    assert EventType.QUEUE_PAUSED in types
    assert EventType.QUEUE_RESUMED in types
    assert all(event.job_id == QUEUE_EVENT_JOB_ID for event in events)


def test_format_id_cannot_be_a_leading_dash_flag(tmp_path: Path) -> None:
    assert is_safe_format_id("137+140")
    assert not is_safe_format_id("--cookies")
    assert not is_safe_format_id("-best")
    runtime = ProviderRuntime(which=lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None)
    with pytest.raises(ProviderPolicyError):
        runtime.execute(
            ProviderRequest(
                provider_id="ytdlp",
                capability_id="acquire.ytdlp",
                typed_inputs={
                    "url": "https://example.com/v",
                    "output": str(tmp_path / "out.bin"),
                    "format_id": "--cookies",
                },
            ),
            tmp_path,
        )


def test_every_provider_argv_is_allowlisted() -> None:
    manifests = builtin_manifests()
    _assert_allowed_flags(
        ["ffmpeg", "-y", "-i", "in.mp4", "-c", "copy", "out.mkv"],
        manifests["ffmpeg"],
    )
    _assert_allowed_flags(
        ["gallery-dl", "--no-mtime", "--destination", "/tmp", "https://e/a"],
        manifests["gallery-dl"],
    )
    _assert_allowed_flags(["magick", "in.png", "-auto-orient", "out.jpg"], manifests["imagemagick"])
    with pytest.raises(ProviderPolicyError, match="not allowlisted"):
        _assert_allowed_flags(["ffmpeg", "-y", "--enable-file-urls", "in"], manifests["ffmpeg"])


def test_transport_modules_do_not_import_policy() -> None:
    root = repo_root() / "src" / "webmedia_dl"
    for name in ("transport.py", "continuity.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
        assert not any("policy" in item or "capabilities" in item for item in imported), name


def test_package_bundle_uses_fixed_timestamp(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "package_bundle",
        repo_root() / "scripts" / "package_bundle.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "keep.txt").write_text("ok", encoding="utf-8")
    first = tmp_path / "one.zip"
    second = tmp_path / "two.zip"
    digest_one = mod.write_bundle(tree, first)
    digest_two = mod.write_bundle(tree, second)
    assert digest_one == digest_two
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        info = archive.getinfo("keep.txt")
        assert info.date_time == (2026, 8, 18, 0, 0, 0)


def test_validate_bundle_fails_when_overlay_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = importlib.util.spec_from_file_location(
        "validate_bundle",
        repo_root() / "scripts" / "validate_bundle.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    assert mod.main() != 0


def test_doctor_fail_and_warn_and_missing_skip_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "webmedia_dl.diagnostics.resolve_provider_binary",
        lambda name: "/bin/false" if name else None,
    )
    monkeypatch.setattr("webmedia_dl.diagnostics._provider_version_ok", lambda *_a, **_k: False)
    failed = doctor()
    assert failed["providers"]["ffmpeg"]["status"] == "FAIL"
    assert failed["providers"]["ffmpeg"]["executed"] is True
    assert failed["providers"]["http-direct"]["status"] == "PASS"

    monkeypatch.setattr(
        "webmedia_dl.diagnostics.resolve_provider_binary",
        lambda name: "/usr/bin/convert" if name == "magick" else None,
    )
    monkeypatch.setattr("webmedia_dl.diagnostics._provider_version_ok", lambda *_a, **_k: True)
    warned = doctor()
    assert warned["providers"]["imagemagick"]["status"] == "WARN"
    assert warned["providers"]["ytdlp"]["status"] == "BLOCKED"

    calls: list[object] = []

    def boom(*_args: object, **_kwargs: object) -> None:
        calls.append(1)
        raise AssertionError("doctor must not download providers")

    monkeypatch.setattr("webmedia_dl.diagnostics.resolve_provider_binary", lambda _name: None)
    monkeypatch.setattr("webmedia_dl.diagnostics.subprocess.run", boom)
    blocked = doctor()
    assert blocked["providers"]["ytdlp"]["status"] == "BLOCKED"
    assert calls == []


def test_watch_worker_cannot_run_gallery_dl() -> None:
    from webmedia_dl.domain.models import Worker

    profile = get_profile("personal-full")
    watch = Worker(
        worker_id="watch-misconfigured",
        platform=Surface.WATCHOS,
        profile_id=profile.profile_id,
        capabilities=list(profile.allowed_capabilities),
        subprocess_capable=False,
    )
    with pytest.raises(CapabilityDenied, match="not a subprocess worker"):
        assert_worker_capability(watch, profile, "acquire.gallery_dl")


def test_files_app_intent_requires_bookmark(tmp_path: Path) -> None:
    dest = tmp_path / "Movies"
    dest.mkdir()
    with pytest.raises(ValueError, match="security-scoped bookmark"):
        ExportIntent(
            destination_kind=DestinationKind.FILES_APP,
            destination_path=str(dest),
            approved_roots=[str(dest)],
        )
    with pytest.raises(ValueError, match="security-scoped bookmark"):
        ExportIntent(
            destination_kind=DestinationKind.FILES_APP,
            destination_path=str(dest),
            approved_roots=[str(dest)],
            security_scoped_bookmark="   ",
        )
    filled = ExportIntent(
        destination_kind=DestinationKind.FILES_APP,
        destination_path=str(dest),
        approved_roots=[str(dest)],
        security_scoped_path="   ",
        security_scoped_bookmark="ZmFrZQ==",
    )
    assert filled.security_scoped_path == str(dest)
    assert filled.security_scoped_bookmark == "ZmFrZQ=="


def test_inspect_dash_content_protection_without_named_drm_still_refuses() -> None:
    with pytest.raises(DrmRefused, match="ContentProtection"):
        inspect_manifest("<MPD><ContentProtection /></MPD>")


def test_doctor_version_probe_oserror_is_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    from webmedia_dl import diagnostics as diagnostics_mod

    monkeypatch.setattr(
        diagnostics_mod,
        "resolve_provider_binary",
        lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None,
    )

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("exec format error")

    monkeypatch.setattr(diagnostics_mod.subprocess, "run", _boom)
    rows = doctor()
    ffmpeg = rows["providers"]["ffmpeg"]
    assert ffmpeg["status"] == "FAIL"
    assert ffmpeg["executed"] is True
    assert "did not report a version" in ffmpeg["reason"]


def test_every_openspec_scenario_has_when_then() -> None:
    root = repo_root() / "openspec/changes/build-webmedia-dl-v1/specs"
    titles: list[str] = []
    for spec in sorted(root.glob("*/spec.md")):
        text = spec.read_text(encoding="utf-8")
        chunks = re.split(r"(?m)^#### Scenario:", text)
        assert "SHALL" in text, spec.parent.name
        for chunk in chunks[1:]:
            title = chunk.splitlines()[0].strip()
            assert "**WHEN**" in chunk, f"{spec.parent.name}: {title}"
            assert "**THEN**" in chunk, f"{spec.parent.name}: {title}"
            titles.append(title)
    assert len(titles) >= 40
    dupes = [name for name, count in Counter(titles).items() if count > 1]
    assert dupes == [], dupes
