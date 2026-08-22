"""OpenSpec SHALL proofs that were previously unasserted or fail-open."""

from __future__ import annotations

import ast
import importlib.util
import re
import shutil
import subprocess
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


def _imported_modules(relative: str) -> list[str]:
    tree = ast.parse((repo_root() / "src" / "webmedia_dl" / relative).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    return imported


def test_intake_does_not_perform_network_retrieval() -> None:
    imported = _imported_modules("intake.py")
    banned = ("httpx", "urllib.request", "requests", "aiohttp", "http.client")
    assert not any(
        item == name or item.startswith(f"{name}.") for item in imported for name in banned
    )


def test_discovery_does_not_import_acquisition() -> None:
    imported = _imported_modules("discovery.py")
    assert not any("acquisition" in item for item in imported)


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


def test_validate_bundle_fails_when_one_spec_is_missing() -> None:
    spec = importlib.util.spec_from_file_location(
        "validate_bundle_missing_spec",
        repo_root() / "scripts" / "validate_bundle.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    current = list(vars(mod)["CAPABILITIES"])
    vars(mod)["CAPABILITIES"] = [*current, "missing-capability"]
    assert mod.main() != 0


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
    assert failed["providers"]["http-direct"]["executed"] is True
    assert "httpx" in failed["providers"]["http-direct"]["probe"]

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
    monkeypatch.setattr("webmedia_dl.capabilities.resolve_provider_binary", lambda _name: None)
    monkeypatch.setattr("webmedia_dl.providers.resolve_provider_binary", lambda *_a, **_k: None)
    monkeypatch.setattr("webmedia_dl.providers.subprocess.run", boom)
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


def test_recordable_parts_refuses_dash_system_uuid_without_protection_tag() -> None:
    text = (
        "<MPD><Period><AdaptationSet>"
        "<Representation id='v1'>urn:uuid:EDEF8BA9-79D6-4ACE-A3C8-27DCD51D21ED</Representation>"
        "</AdaptationSet></Period></MPD>"
    )
    with pytest.raises(DrmRefused):
        recordable_parts(text, "https://cdn.example.com/manifest.mpd")


def test_doctor_version_probe_oserror_is_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    from webmedia_dl import diagnostics as diagnostics_mod
    from webmedia_dl import providers as providers_mod

    monkeypatch.setattr(
        diagnostics_mod,
        "resolve_provider_binary",
        lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None,
    )

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("exec format error")

    monkeypatch.setattr(providers_mod.subprocess, "run", _boom)
    rows = doctor()
    ffmpeg = rows["providers"]["ffmpeg"]
    assert ffmpeg["status"] == "FAIL"
    assert ffmpeg["executed"] is True
    assert "did not report a version" in ffmpeg["reason"]


SCENARIO_EVIDENCE: dict[str, tuple[str, str]] = {
    "publication requires approved roots": (
        "tests/unit/webmedia_dl/test_fail_closed_followups.py",
        "test_user_approved_path_omits_approved_roots",
    ),
    "files bookmark path boundary": (
        "tests/unit/webmedia_dl/test_p2_contracts.py",
        "test_files_bookmark_and_photokit",
    ),
    "clipboard url is not a path": (
        "tests/unit/webmedia_dl/test_p2_contracts.py",
        "test_clipboard_locator_extracts_url",
    ),
    "photos without approval": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/IdentityTests.swift",
        "testPhotosDestinationRequiresApprovedRoot",
    ),
    "share sheet url versus file": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/IdentityTests.swift",
        "testContinuityIsNotASubprocessWorker",
    ),
    "complete clients carry files destinations": (
        "tests/unit/webmedia_dl/test_surfaces_inventory.py",
        "test_complete_clients_http_direct_and_shared_domain",
    ),
    "share destination publishes under approved root": (
        "tests/unit/webmedia_dl/test_pack_gaps.py",
        "test_share_destination_publishes_under_approved_root",
    ),
    "AES-128 playlist": (
        "tests/unit/webmedia_dl/test_live.py",
        "test_aes128_playlist_refused_before_any_segment_fetch",
    ),
    "two clear transport segments": (
        "tests/unit/webmedia_dl/test_live.py",
        "test_record_clear_stream_concatenates_segments",
    ),
    "DASH SegmentList byte ranges": (
        "tests/unit/webmedia_dl/test_runtime_gaps.py",
        "test_dash_segment_timeline",
    ),
    "AdaptationSet binds Representation identifiers": (
        "tests/unit/webmedia_dl/test_p2_contracts.py",
        "test_dash_adaptationset_binds_self_closing_representation",
    ),
    "highest-bandwidth video representation": (
        "tests/unit/webmedia_dl/test_p2_contracts.py",
        "test_dash_prefers_highest_video_representation",
    ),
    "HLS master highest bandwidth": (
        "tests/unit/webmedia_dl/test_p2_contracts.py",
        "test_hls_master_prefers_highest_bandwidth",
    ),
    "multi-period DASH concatenates each period": (
        "tests/unit/webmedia_dl/test_pack_gap_fixes.py",
        "test_multi_period_same_uri_is_appended_twice",
    ),
    "dynamic MPD polls new segments": (
        "tests/unit/webmedia_dl/test_p2_contracts.py",
        "test_dynamic_mpd_polls_new_segments",
    ),
    "DASH SegmentTemplate endNumber": (
        "tests/unit/webmedia_dl/test_fail_closed_paths.py",
        "test_dash_template_tokens_and_period_fallback",
    ),
    "DASH SegmentTemplate presentation duration": (
        "tests/unit/webmedia_dl/test_fail_closed_paths.py",
        "test_dash_template_tokens_and_period_fallback",
    ),
    "companion capture has no native command": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/IdentityTests.swift",
        "testContinuityIsNotASubprocessWorker",
    ),
    "watch worker cannot run yt-dlp": (
        "tests/unit/webmedia_dl/test_policy.py",
        "test_watch_is_not_a_subprocess_worker",
    ),
    "watch queues for Mac relay": (
        "tests/unit/webmedia_dl/test_fail_closed_followups.py",
        "test_watch_tv_capture_queues_without_ytdlp",
    ),
    "watch control intents queue companion kinds": (
        "tests/unit/webmedia_dl/test_companion_checkpoint.py",
        "test_sealed_companion_cancel_requires_job_uuid",
    ),
    "sealed companion envelope": (
        "tests/unit/webmedia_dl/test_companion_checkpoint.py",
        "test_companion_accepts_sealed_pairing_envelope",
    ),
    "unconfirmed pairing": (
        "tests/unit/webmedia_dl/test_pairing_surfaces.py",
        "test_unconfirmed_pairing_does_not_escalate",
    ),
    "confirmed pairing lets mac execute without widening": (
        "tests/unit/webmedia_dl/test_pairing_surfaces.py",
        "test_pairing_confirmation_lets_mac_own_without_widening",
    ),
    "mac lan relay rewrites to loopback": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/ContractTests.swift",
        "testLoopbackRequestBuildersStayOnLoopback",
    ),
    "complete-client history uses mac relay": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/ContractTests.swift",
        "testLoopbackRequestBuildersStayOnLoopback",
    ),
    "complete-client control intents use mac relay": (
        "tests/unit/webmedia_dl/test_surfaces_inventory.py",
        "test_complete_clients_http_direct_and_shared_domain",
    ),
    "HTML extracts media without using the title as identity": (
        "tests/unit/webmedia_dl/test_discovery.py",
        "test_html_discovery_extracts_media_without_using_title_as_id",
    ),
    "track and media anchors": (
        "tests/unit/webmedia_dl/test_discovery.py",
        "test_html_discovery_extracts_track_and_media_anchors",
    ),
    "iframe, preload link, and JSON-LD type": (
        "tests/unit/webmedia_dl/test_discovery.py",
        "test_html_discovery_extracts_iframe_link_and_jsonld_type",
    ),
    "amp-img and twitter player": (
        "tests/unit/webmedia_dl/test_discovery.py",
        "test_html_discovery_amp_img_and_twitter_player",
    ),
    "Graph records DRM conflicts": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_candidate_graph_records_duplicates_drm_and_grouping",
    ),
    "completed job has events": ("tests/e2e/test_cli_e2e.py", "test_submit_history_job_roundtrip"),
    "event payload is not a provider console": (
        "tests/unit/webmedia_dl/test_p2_contracts.py",
        "test_event_payload_rejects_every_forbidden_key",
    ),
    "Queue is paused": (
        "tests/unit/webmedia_dl/test_queue_manifest.py",
        "test_queue_pause_leaves_job_accepted",
    ),
    "Per-job pause is distinct from queue pause": (
        "tests/unit/webmedia_dl/test_queue_manifest.py",
        "test_paused_job_is_not_auto_started",
    ),
    "Pause mid-acquire keeps registered sources": (
        "tests/unit/webmedia_dl/test_companion_checkpoint.py",
        "test_pause_during_acquire_checkpoints_and_resume_skips_done_kind",
    ),
    "doctor JSON": ("tests/unit/webmedia_dl/test_cli.py", "test_doctor_json"),
    "support bundle is local-only": (
        "tests/unit/webmedia_dl/test_cli.py",
        "test_support_bundle_is_local_and_strips_console",
    ),
    "HTTPS paste": ("tests/unit/webmedia_dl/test_intake.py", "test_paste_kind_stays_a_url"),
    "file scheme rejected": ("tests/unit/webmedia_dl/test_intake.py", "test_file_scheme_rejected"),
    "URL plus path is invalid": (
        "tests/unit/webmedia_dl/test_invariants.py",
        "test_source_url_cannot_become_path",
    ),
    "drop of an existing file": ("tests/unit/webmedia_dl/test_cli.py", "test_drop_command"),
    "restricted cannot delegate yt-dlp": (
        "tests/unit/webmedia_dl/test_policy.py",
        "test_restricted_cannot_delegate_ytdlp",
    ),
    "consumed envelope nonces expire from the ledger": (
        "tests/unit/webmedia_dl/test_plan_evidence_replay.py",
        "test_nonce_ledger_prunes_expired_rows",
    ),
    "simulated PASS forbidden": (
        "tests/unit/webmedia_dl/test_invariants.py",
        "test_simulated_check_cannot_pass",
    ),
    "outside approved root": (
        "tests/unit/webmedia_dl/test_fail_closed_followups.py",
        "test_jobs_export_outside_approved_roots_fails_closed",
    ),
    "extra_args rejected": ("tests/unit/webmedia_dl/test_providers.py", "test_extra_args_rejected"),
    "yt-dlp format token": (
        "tests/unit/webmedia_dl/test_providers.py",
        "test_ytdlp_argv_is_allowlisted",
    ),
    "doctor does not install yt-dlp": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_doctor_fail_and_warn_and_missing_skip_install",
    ),
    "YouTube watch page is not fetched as HTTP bytes": (
        "tests/unit/webmedia_dl/test_coverage_gaps.py",
        "test_lossy_plan_and_gallery_acquisition",
    ),
    "remux argv": ("tests/unit/webmedia_dl/test_processing.py", "test_remux_argv_uses_stream_copy"),
    "ImageMagick policy directory": (
        "tests/unit/webmedia_dl/test_processing.py",
        "test_magick_configure_path_is_set",
    ),
    "collector returns no native command": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_extension_collector_returns_no_native_command",
    ),
    "each engine has a capture tree": (
        "tests/unit/webmedia_dl/test_surfaces_inventory.py",
        "test_browser_extension_trees",
    ),
    "default plan keeps original": (
        "tests/unit/webmedia_dl/test_fail_closed_followups.py",
        "test_original_sacred_keeps_original_with_no_loss",
    ),
    "repo cookie rejected": (
        "tests/unit/webmedia_dl/test_security.py",
        "test_cookie_requires_absolute_existing_file_outside_repo",
    ),
    "mutate source fails": (
        "tests/unit/webmedia_dl/test_invariants.py",
        "test_source_artifact_cannot_be_mutated",
    ),
    "original archive preserved": (
        "tests/unit/webmedia_dl/test_compat_transport.py",
        "test_legacy_scan_is_non_destructive",
    ),
    "capture popup markup": (
        "tests/unit/webmedia_dl/test_accessibility_markup.py",
        "test_capture_popup_has_accessible_markup",
    ),
    "CLI help uses canonical name": ("tests/unit/webmedia_dl/test_cli.py", "test_help"),
    "bundle zip uses a fixed timestamp": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_package_bundle_uses_fixed_timestamp",
    ),
    "encrypted HLS refuses before fetch": (
        "tests/unit/webmedia_dl/test_live.py",
        "test_aes128_playlist_refused_before_any_segment_fetch",
    ),
    "default telemetry is rejected": (
        "tests/unit/webmedia_dl/test_invariants.py",
        "test_policy_profile_forbids_drm_and_default_telemetry",
    ),
}


def _openspec_scenario_titles() -> list[str]:
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
    return titles


def _test_defined_in(relative: str, name: str) -> bool:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        return False
    path = (repo_root() / relative).resolve()
    try:
        path.relative_to(repo_root().resolve())
    except ValueError:
        return False
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        tree = ast.parse(text)
        return any(
            isinstance(node, ast.FunctionDef) and node.name == name for node in ast.walk(tree)
        )
    if path.suffix == ".swift":
        return re.search(rf"\bfunc {re.escape(name)}\s*\(", text) is not None
    if path.suffix == ".mjs":
        return re.search(rf'\bit\(\s*"{re.escape(name)}"', text) is not None
    return False


def test_every_openspec_scenario_has_when_then() -> None:
    titles = _openspec_scenario_titles()
    assert len(titles) >= 40
    dupes = [name for name, count in Counter(titles).items() if count > 1]
    assert dupes == [], dupes


def test_every_openspec_scenario_has_named_test() -> None:
    titles = _openspec_scenario_titles()
    missing_map = sorted(set(titles) - set(SCENARIO_EVIDENCE))
    extra_map = sorted(set(SCENARIO_EVIDENCE) - set(titles))
    assert missing_map == [], missing_map
    assert extra_map == [], extra_map
    missing_tests = [
        f"{title} -> {relative}::{name}"
        for title, (relative, name) in SCENARIO_EVIDENCE.items()
        if not _test_defined_in(relative, name)
    ]
    assert missing_tests == [], missing_tests


def test_extension_collector_returns_no_native_command() -> None:
    text = (repo_root() / "extensions/shared/capture.js").read_text(encoding="utf-8")
    assert "Never becomes a generic native command runner" in text
    assert "nativeCommand: null" in text
    assert '!value.toLowerCase().startsWith("javascript:")' in text
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = repo_root() / "tests/unit/extensions/capture.test.mjs"
    completed = subprocess.run(
        [node, "--test", str(script)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(repo_root()),
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_builtin_manifests_never_auto_install_or_accept_argv() -> None:
    for manifest in builtin_manifests().values():
        assert manifest.install_automatic is False, manifest.provider_id
        assert manifest.accepts_user_argv is False, manifest.provider_id


def test_shipped_profiles_forbid_telemetry_drm_and_auto_delegate() -> None:
    from webmedia_dl.policy.profiles import builtin_profiles

    profiles = builtin_profiles()
    assert set(profiles) >= {
        "personal-full",
        "personal-restricted",
        "browser-capture",
        "watch-capture",
        "tv-control",
    }
    for profile in profiles.values():
        assert profile.telemetry_default is False, profile.profile_id
        assert profile.drm_circumvention is False, profile.profile_id
        assert profile.can_delegate is False, profile.profile_id
