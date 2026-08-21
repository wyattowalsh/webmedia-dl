"""Remaining Linux-provable fail-closed coverage for discovery, cookies, probe, and resume."""

from __future__ import annotations

import json
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from webmedia_dl.compat import migrate_legacy
from webmedia_dl.continuity import validate_companion_message
from webmedia_dl.diagnostics import doctor
from webmedia_dl.discovery import candidates_from_manifest_json, discover
from webmedia_dl.domain.enums import (
    ArtifactRole,
    EventType,
    IntakeKind,
    JobState,
    LossClass,
    MediaKind,
    Surface,
)
from webmedia_dl.domain.models import (
    AcquisitionStrategy,
    Artifact,
    ExportIntent,
    MediaSource,
    Operation,
)
from webmedia_dl.errors import CookiePolicyError, DrmRefused, ProviderPolicyError
from webmedia_dl.export import plan_export
from webmedia_dl.live import (
    ManifestPart,
    _expand_dash_template,
    inspect_manifest,
    record_clear_stream,
    recordable_segment_urls,
)
from webmedia_dl.packaging import write_extension_zips
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import get_profile
from webmedia_dl.probe import probe_media
from webmedia_dl.providers import (
    ProviderRequest,
    ProviderRuntime,
    _http_suffix,
    resolve_provider_binary,
)
from webmedia_dl.security import CookieGrantLedger, resolve_cookie_path
from webmedia_dl.service import (
    create_app,
    job_detail_payload,
    load_or_create_token,
    run_next_payload,
)
from webmedia_dl.updates import check_updates
from webmedia_dl.validation import container_matches, normalize_container


def _page() -> MediaSource:
    return MediaSource(
        kind=IntakeKind.URL,
        locator="https://example.com/page",
        normalized_url="https://example.com/page",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )


def test_legacy_download_archive_dict_is_indexed(tmp_path: Path) -> None:
    marker = tmp_path / ".ytdlp-history.json"
    marker.write_text(
        json.dumps({"download_archive": ["keep-me", "", "also-me"]}),
        encoding="utf-8",
    )
    applied = migrate_legacy(tmp_path, apply=True)
    sidecar = json.loads((tmp_path / "webmedia-dl-migrated" / "migration.json").read_text())
    by_name = {Path(item["source_path"]).name: item["ids"] for item in sidecar["archives"]}
    assert by_name[".ytdlp-history.json"] == ["keep-me", "also-me"]
    assert applied["index_entries"] == 2
    scalar = tmp_path / "archive.txt"
    scalar.write_text('{"ids": "one"}\n', encoding="utf-8")
    later = migrate_legacy(tmp_path, apply=True)
    sidecar = json.loads((tmp_path / "webmedia-dl-migrated" / "migration.json").read_text())
    by_name = {Path(item["source_path"]).name: item["ids"] for item in sidecar["archives"]}
    assert '{"ids": "one"}' in by_name["archive.txt"]
    assert later["migrated"] is True


def test_companion_kind_missing_or_unknown_is_refused() -> None:
    with pytest.raises(ProviderPolicyError, match="missing or not allowlisted"):
        validate_companion_message({})
    with pytest.raises(ProviderPolicyError, match="missing or not allowlisted"):
        validate_companion_message({"kind": "explode"})
    with pytest.raises(ProviderPolicyError, match="missing or not allowlisted"):
        validate_companion_message({"kind": 1})


def test_discovery_skips_empty_tokens_and_jsonld_kinds() -> None:
    html = """
    <html>
      <head>
        <title>   </title>
        <title>Album</title>
        <meta property="og:title">
        <meta content="orphan">
        <script type="application/ld+json">not-json</script>
        <script type="application/ld+json">
          [{"@type": "AudioObject", "contentUrl": "https://cdn.example.com/song"}]
        </script>
        <script type="application/ld+json">
          {"@type": "Photograph", "embedUrl": "https://cdn.example.com/photo"}
        </script>
        <link rel="preload" as="track" href="https://cdn.example.com/sub.vtt">
      </head>
      <body>
        <video poster="" src="https://cdn.example.com/clip.mp4"
               srcset=",  , https://cdn.example.com/poster.jpg 1x"></video>
        <picture>
          <source srcset="https://cdn.example.com/plain.jpg">
        </picture>
        <video><source type="application/octet-stream" src="https://cdn.example.com/typed.mp4"></video>
        <track>
        <a>nohref</a>
        <iframe></iframe>
        <link rel="preload" as="video">
      </body>
    </html>
    """
    found = discover(_page(), get_profile("personal-full"), html=html)
    urls = [item.retrieval_urls[0] for item in found if item.retrieval_urls]
    kinds = {item.retrieval_urls[0]: item.media_kind for item in found if item.retrieval_urls}
    assert "https://cdn.example.com/clip.mp4" in urls
    assert "https://cdn.example.com/poster.jpg" in urls
    assert "https://cdn.example.com/song" in urls
    assert "https://cdn.example.com/photo" in urls
    assert kinds["https://cdn.example.com/song"] is MediaKind.AUDIO
    assert kinds["https://cdn.example.com/photo"] is MediaKind.IMAGE
    assert kinds["https://cdn.example.com/plain.jpg"] is MediaKind.IMAGE
    assert kinds["https://cdn.example.com/sub.vtt"] is MediaKind.SUBTITLE
    assert kinds["https://cdn.example.com/typed.mp4"] is MediaKind.VIDEO
    assert not any(item == "" for item in urls)
    assert found[0].title_display == "Album"


def test_manifest_json_ndjson_skips_and_unusable_urls() -> None:
    raw = (
        b"\n"
        b"{not json}\n"
        b"null\n"
        b'{"url": 123}\n'
        b'{"url": "javascript:alert(1)"}\n'
        b'{"webpage_url": "https://cdn.example.com/ok.mp4", "id": "ok",'
        b' "formats": [{"format_id": "18", "vcodec": "null", "acodec": "none"}]}\n'
    )
    found = candidates_from_manifest_json(_page(), raw)
    assert len(found) == 1
    assert found[0].retrieval_urls == ["https://cdn.example.com/ok.mp4"]
    assert found[0].alternatives[0].vcodec is None
    assert found[0].alternatives[0].acodec is None
    listed = candidates_from_manifest_json(
        _page(),
        json.dumps([{"url": "https://cdn.example.com/listed.mp4"}, "skip", None]).encode(),
    )
    assert [item.retrieval_urls[0] for item in listed] == ["https://cdn.example.com/listed.mp4"]
    ndjson = b'not-json\n\n{"url": "https://cdn.example.com/ndjson.mp4"}\n'
    ndjson_found = candidates_from_manifest_json(_page(), ndjson)
    assert [item.retrieval_urls[0] for item in ndjson_found] == [
        "https://cdn.example.com/ndjson.mp4"
    ]


def test_probe_encrypted_field_true_and_non_dict_tags(tmp_path: Path) -> None:
    media = tmp_path / "clip.bin"
    media.write_bytes(b"bytes")

    def runner(*_args: object, **_kwargs: object) -> SimpleNamespace:
        payload = {
            "streams": [
                {"index": 0, "codec_type": "video", "encrypted": True},
                {"index": 1, "codec_type": "audio", "tags": ["not-a-dict"]},
            ],
            "format": {"format_name": "mov,mp4,m4a"},
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload).encode())

    probed = probe_media(media, which=lambda _name: "/usr/bin/ffprobe", runner=runner)
    assert probed is not None
    assert probed.streams[0].encrypted is True
    assert probed.streams[1].encrypted is False


def test_extension_zip_skips_directories(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "ext"
    browser = root / "chromium"
    nested = browser / "icons"
    nested.mkdir(parents=True)
    (browser / "manifest.json").write_text("{}", encoding="utf-8")
    (nested / "icon.png").write_bytes(b"png")
    monkeypatch.setattr("webmedia_dl.packaging.BROWSERS", ("chromium",))
    monkeypatch.setattr("webmedia_dl.packaging.extension_root", lambda: root)
    written = write_extension_zips(dest_root=tmp_path / "zips")
    assert written[0]["browser"] == "chromium"
    with zipfile.ZipFile(written[0]["path"]) as archive:
        names = archive.namelist()
    assert "manifest.json" in names
    assert "icons/icon.png" in names
    assert "icons" not in names
    assert "icons/" not in names


def test_updates_info_must_be_a_version_dict() -> None:
    class _Resp:
        def __init__(self, payload: bytes) -> None:
            self._buf = BytesIO(payload)

        def read(self) -> bytes:
            return self._buf.read()

        def __enter__(self) -> _Resp:
            return self

        def __exit__(self, *_exc: object) -> bool:
            return False

    def info_string(_url: str, timeout: float = 2.5) -> _Resp:
        return _Resp(json.dumps({"info": "9.9.9"}).encode())

    payload = check_updates(current="0.1.0", opener=info_string)
    assert payload["status"] == "WARN"
    assert payload["latest"] is None

    def body_list(_url: str, timeout: float = 2.5) -> _Resp:
        return _Resp(json.dumps(["9.9.9"]).encode())

    listed = check_updates(current="0.1.0", opener=body_list)
    assert listed["status"] == "WARN"


def test_container_normalize_and_generic_image_probe() -> None:
    assert normalize_container(None) is None
    assert normalize_container("") is None
    assert container_matches("mov,mp4,m4a", "") is False
    assert container_matches(None, "mp4") is False
    assert container_matches("image2", "jpg") is True


def test_cookie_deny_name_is_advisory_outside_repo(tmp_path: Path) -> None:
    profile = get_profile("personal-full")
    outside = Path("/tmp") / f"wmdl-cookie-deny-{uuid4().hex}" / "cookies.txt"
    outside.parent.mkdir(parents=True)
    try:
        outside.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
        resolved = resolve_cookie_path(profile, str(outside), repo_root=tmp_path / "repo")
        assert resolved == outside.resolve()
        assert "test" not in resolved.parts
    finally:
        outside.unlink(missing_ok=True)
        outside.parent.rmdir()


def test_cookie_ledger_skips_malformed_store_and_unknown_grants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    store = tmp_path / "cookie-grants.json"
    store.write_text(json.dumps({"grant_id": "not-a-list"}), encoding="utf-8")
    empty = CookieGrantLedger(store)
    with pytest.raises(CookiePolicyError, match="unknown or expired"):
        empty.resolve("missing", job_id=uuid4(), profile_id="personal-full")

    store.write_text(
        json.dumps(
            [
                "skip",
                {"grant_id": "incomplete"},
                {
                    "grant_id": "ok",
                    "job_id": str(uuid4()),
                    "path": str(cookies),
                    "profile_id": "personal-full",
                },
            ]
        ),
        encoding="utf-8",
    )
    loaded = CookieGrantLedger(store)
    assert "ok" in loaded._grants
    handle = loaded._lock()
    assert handle is not None
    handle.close()

    memory = CookieGrantLedger()
    assert memory._lock() is None
    monkeypatch.setattr("webmedia_dl.security.resolve_cookie_path", lambda *_a, **_k: None)
    with pytest.raises(CookiePolicyError, match="absolute paths"):
        memory.issue(uuid4(), cookies, "personal-full")


def test_probe_none_records_blocked_gate(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("webmedia_dl.pipeline.probe_media", lambda *_a, **_k: None)
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=True)
    assert job.state is JobState.COMPLETED
    events = pipeline.queue.events_for(job.job_id)
    assert any(
        event.type is EventType.VALIDATION_RECORDED
        and event.payload.get("gate") == "probe-available"
        and event.payload.get("status") == "BLOCKED"
        for event in events
    )


def test_resume_acquired_kinds_without_sources_fails_closed(
    tmp_data: Path, png_bytes: bytes
) -> None:
    html = """
    <html><body>
      <img src="https://cdn.example.com/hero.png">
    </body></html>
    """
    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(
            which=lambda _name: None,
            http_get=lambda _url: (200, {}, png_bytes),
        ),
    )
    job = pipeline.submit("https://example.com/page", html=html, wait=False)
    pipeline.queue.put_checkpoint(
        job.job_id,
        {
            "stage": "acquiring",
            "source_ids": ["sha256:missing"],
            "acquired_kinds": ["image"],
        },
    )
    result = pipeline.run_next()
    assert result is not None
    assert result.state is JobState.FAILED
    assert result.error is not None
    assert "produced no source artifact" in result.error.lower()


def test_unresolved_cookie_path_fails_closed(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    monkeypatch.setattr("webmedia_dl.pipeline.resolve_cookie_path", lambda *_a, **_k: None)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), cookies=str(cookies))
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "could not be resolved" in job.error.lower()


def test_cancel_unknown_job_and_history_skip(tmp_path: Path, png_bytes: bytes) -> None:
    app_api = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app_api)
    headers = {"Authorization": f"Bearer {token}"}
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    older = client.post("/v1/jobs", headers=headers, json={"locator": str(media)})
    newer = client.post(
        "/v1/jobs",
        headers=headers,
        json={"locator": str(media), "wait": False},
    )
    older_id = older.json()["job"]["job_id"]
    newer_id = newer.json()["job"]["job_id"]
    detail = client.get(f"/v1/jobs/{older_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["artifact_ids"]
    empty = client.get(f"/v1/jobs/{newer_id}", headers=headers)
    assert empty.status_code == 200
    cancelled = client.post(f"/v1/jobs/{uuid4()}/cancel", headers=headers)
    assert cancelled.status_code == 400
    accepted = client.post(
        f"/v1/jobs/{newer_id}/cancel",
        headers=headers,
    )
    assert accepted.status_code == 200
    assert accepted.json()["state"] == "cancelled"
    empty_run = client.post("/v1/queue/run-next", headers=headers)
    assert empty_run.status_code == 200
    assert empty_run.json() == {"job": None, "events": []}


def test_http_suffix_skips_non_content_type_headers() -> None:
    assert (
        _http_suffix(
            "https://cdn.example.com/x",
            {"Accept": "video/mp4", "CONTENT-TYPE": "video/webm"},
            b"",
        )
        == ".webm"
    )


def test_hls_byterange_without_offset_starts_at_zero(tmp_path: Path) -> None:
    playlist = "#EXTM3U\n#EXT-X-BYTERANGE:4\nseg.bin\n#EXT-X-BYTERANGE:2\nseg.bin\n"
    body = {"https://cdn.example.com/live/seg.bin": b"ABCDEF"}

    def fetch(url: str) -> tuple[int, str, bytes]:
        return 200, "video/MP2T", body[url]

    dest = tmp_path / "live.bin"
    record_clear_stream(playlist, "https://cdn.example.com/live/index.m3u8", dest, fetch)
    assert dest.read_bytes() == b"ABCDEF"


def test_inspect_manifest_empty_clear_hls_is_not_drm() -> None:
    inspect_manifest("#EXTM3U\n#EXT-X-VERSION:3\n")


def test_invalid_dash_number_format_falls_back_to_decimal() -> None:
    assert _expand_dash_template("seg$Number%q$.m4s", number=7) == "seg7.m4s"
    assert _expand_dash_template("seg$Number$.m4s", number=7) == "seg7.m4s"


def test_cookie_save_without_lock_handle_still_persists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    store = tmp_path / "cookie-grants.json"
    ledger = CookieGrantLedger(store)
    monkeypatch.setattr(ledger, "_lock", lambda: None)
    grant = ledger.issue(uuid4(), cookies, "personal-full")
    payload = json.loads(store.read_text(encoding="utf-8"))
    assert payload[0]["grant_id"] == grant.grant_id


def test_ffmpeg_ext_template_prefers_matching_stem(tmp_path: Path) -> None:
    def run(_argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        (tmp_path / "other.mkv").write_bytes(b"other")
        (tmp_path / "clip.mkv").write_bytes(b"clip")
        return 0, b"", b""

    runtime = ProviderRuntime(which=lambda name: "/usr/bin/ffmpeg", run=run)
    result = runtime.execute(
        ProviderRequest(
            provider_id="ffmpeg",
            capability_id="process.ffmpeg.remux",
            typed_inputs={
                "input": str(tmp_path / "a.mp4"),
                "output": str(tmp_path / "clip.%(ext)s"),
            },
        ),
        tmp_path,
    )
    assert result.output_path is not None
    assert result.output_path.name == "clip.mkv"


def test_manifest_discovery_nonzero_exit_returns_empty(tmp_data: Path, tmp_path: Path) -> None:
    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        if "--dump-json" in argv:
            return 2, b"", b"fail"
        return 0, b"", b""

    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(
            which=lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None,
            run=run,
        ),
    )
    job = pipeline.submit("https://example.com/watch?v=1", wait=False)
    found = pipeline._manifest_candidates(job, staging=tmp_path)
    assert found == []


def test_leftover_dash_media_without_template_is_recorded() -> None:
    text = """
    <MPD><Period>
      <Foo media="clip.m4s"/>
      <Foo media="clip.m4s"/>
    </Period></MPD>
    """
    assert recordable_segment_urls(text, "https://cdn.example.com/") == [
        "https://cdn.example.com/clip.m4s"
    ]


def test_record_clear_stream_uses_supplied_parts(tmp_path: Path) -> None:
    parts = [ManifestPart("https://cdn.example.com/a.ts")]

    def fetch(url: str) -> tuple[int, str, bytes]:
        assert url == "https://cdn.example.com/a.ts"
        return 200, "video/MP2T", b"SEG"

    dest = tmp_path / "live.bin"
    record_clear_stream(
        "#EXTM3U\n#EXT-X-VERSION:3\n",
        "https://cdn.example.com/live.m3u8",
        dest,
        fetch,
        parts=parts,
    )
    assert dest.read_bytes() == b"SEG"


def test_supplied_parts_do_not_bypass_hls_encryption(tmp_path: Path) -> None:
    parts = [ManifestPart("https://cdn.example.com/a.ts")]
    playlist = '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key"\nseg.ts\n'

    def fetch(url: str) -> tuple[int, str, bytes]:
        raise AssertionError(url)

    with pytest.raises(DrmRefused, match="AES-128"):
        record_clear_stream(
            playlist,
            "https://cdn.example.com/live.m3u8",
            tmp_path / "live.bin",
            fetch,
            parts=parts,
        )


def test_resume_exporting_restores_produced_ids(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    source = pipeline.store.register(
        media,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.IMAGE,
        provenance={"job_id": str(job.job_id)},
    )
    pipeline.queue.put_checkpoint(
        job.job_id,
        {
            "stage": "exporting",
            "source_ids": [source.artifact_id],
            "produced_ids": [source.artifact_id],
            "acquired_kinds": ["image"],
            "completed_operations": [f"{source.artifact_id}:keep-original"],
            "operation_artifacts": {f"{source.artifact_id}:keep-original": source.artifact_id},
        },
    )
    result = pipeline.run_next()
    assert result is not None
    assert result.state is JobState.COMPLETED


def test_segment_timeline_without_t_keeps_running_clock() -> None:
    text = """
    <MPD><Period>
      <SegmentTemplate media="s$Number$-t$Time$.m4s" startNumber="1">
        <SegmentTimeline>
          <S d="1000" r="1"/>
        </SegmentTimeline>
      </SegmentTemplate>
    </Period></MPD>
    """
    urls = recordable_segment_urls(text, "https://cdn.example.com/")
    assert urls == [
        "https://cdn.example.com/s1-t0.m4s",
        "https://cdn.example.com/s2-t1000.m4s",
    ]


def test_forbidden_loss_class_cannot_be_planned(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden_operation(**kwargs: Any) -> Operation:
        kwargs["loss_class"] = LossClass.FORBIDDEN
        return Operation(**kwargs)

    monkeypatch.setattr("webmedia_dl.export.Operation", forbidden_operation)
    artifact = Artifact(
        artifact_id="sha256:ab",
        role=ArtifactRole.SOURCE,
        sha256="ab",
        byte_size=1,
        media_kind=MediaKind.IMAGE,
        storage_relpath="a.png",
        container="png",
    )
    with pytest.raises(ProviderPolicyError, match="Forbidden loss class"):
        plan_export(uuid4(), artifact, ExportIntent())


def test_acquisition_strategy_validator_rejects_extra_args() -> None:
    with pytest.raises(ValueError, match="arbitrary user arguments"):
        AcquisitionStrategy.forbid_user_argv(["-f"])
    assert AcquisitionStrategy.forbid_user_argv([]) == []


def test_tracked_run_finally_skips_unknown_proc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = ProviderRuntime()
    proc = MagicMock()
    proc.returncode = 0

    def communicate(timeout: float | None = None) -> tuple[bytes, bytes]:
        runtime._procs.clear()
        return b"", b""

    proc.communicate.side_effect = communicate
    monkeypatch.setattr("webmedia_dl.providers.subprocess.Popen", lambda *_a, **_k: proc)
    code, _out, _err = runtime._tracked_run(["true"], tmp_path)
    assert code == 0


def test_get_job_history_skip_and_empty_run_next(
    tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    def history(self: Pipeline) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = [
            {"job_id": "00000000-0000-0000-0000-000000000000", "artifact_ids": ["skip"]},
        ]
        for job in self.history():
            entries.append({"job_id": str(job.job_id)})
        return entries

    monkeypatch.setattr(Pipeline, "history_entries", history)
    monkeypatch.setattr(Pipeline, "run_next", lambda self: None)
    app_api = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    client = TestClient(app_api)
    headers = {"Authorization": f"Bearer {token}"}
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    created = client.post(
        "/v1/jobs",
        headers=headers,
        json={"locator": str(media), "wait": False},
    )
    job_id = created.json()["job"]["job_id"]
    detail = client.get(f"/v1/jobs/{job_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["artifact_ids"] == []
    empty = client.post("/v1/queue/run-next", headers=headers)
    assert empty.status_code == 200
    assert empty.json() == {"job": None, "events": []}


def test_tracked_run_cancel_during_timeout_expired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = ProviderRuntime()
    proc = MagicMock()
    proc.pid = 4242
    proc.returncode = None

    def communicate(timeout: float | None = None) -> tuple[bytes, bytes]:
        if timeout is not None:
            runtime._cancel_event("_").set()
            raise subprocess.TimeoutExpired(cmd="sleep", timeout=timeout)
        proc.returncode = 130
        return b"", b"cancelled"

    proc.communicate.side_effect = communicate
    monkeypatch.setattr("webmedia_dl.providers.subprocess.Popen", lambda *_a, **_k: proc)
    monkeypatch.setattr("webmedia_dl.providers._terminate_process", lambda _proc: None)
    code, _out, err = runtime._tracked_run(["sleep", "5"], tmp_path)
    assert code == 130
    assert err == b"cancelled"


def test_tracked_run_pause_during_timeout_expired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = ProviderRuntime()
    proc = MagicMock()
    proc.pid = 4243
    proc.returncode = None

    def communicate(timeout: float | None = None) -> tuple[bytes, bytes]:
        if timeout is not None:
            runtime._pause_event("_").set()
            raise subprocess.TimeoutExpired(cmd="sleep", timeout=timeout)
        proc.returncode = 143
        return b"", b"paused"

    proc.communicate.side_effect = communicate
    monkeypatch.setattr("webmedia_dl.providers.subprocess.Popen", lambda *_a, **_k: proc)
    monkeypatch.setattr("webmedia_dl.providers._terminate_process", lambda _proc: None)
    code, _out, err = runtime._tracked_run(["sleep", "5"], tmp_path)
    assert code == 143
    assert err == b"paused"


def test_export_progress_accepts_null_and_duplicate_keys(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    from webmedia_dl.processing import execute_export_plan as original

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        on_progress = kwargs.get("on_progress")
        produced = original(*args, **kwargs)
        if on_progress is not None and produced:
            artifact = produced[0][0]
            keep = Operation(
                operation_id="keep-original",
                op_type="identity.copy",
                capability_id="export.plan",
                input_artifact_ids=[artifact.artifact_id],
                output_role=ArtifactRole.SOURCE,
                loss_class=LossClass.NONE,
                validator_ids=["hash-match", "size-match"],
                typed_inputs={},
            )
            on_progress(keep, None)
            on_progress(keep, artifact)
        return produced

    monkeypatch.setattr("webmedia_dl.pipeline.execute_export_plan", wrapped)
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    result = pipeline.submit(str(media))
    assert result.state is JobState.COMPLETED


def test_exported_duplicate_produced_ids_still_complete(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media), wait=False)
    source = pipeline.store.register(
        media,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.IMAGE,
        provenance={"job_id": str(job.job_id)},
    )
    pipeline.queue.put_checkpoint(
        job.job_id,
        {
            "stage": "exported",
            "source_ids": [source.artifact_id],
            "produced_ids": [source.artifact_id, source.artifact_id],
            "acquired_kinds": ["image"],
        },
    )
    result = pipeline.run_next()
    assert result is not None
    assert result.state is JobState.COMPLETED


def test_resume_acquired_remote_skips_refetch(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes
) -> None:
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)

    def fetch(url: str) -> tuple[int, str, bytes]:
        raise AssertionError(url)

    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(which=lambda _name: None),
        fetch=fetch,
    )
    job = pipeline.submit(
        "https://cdn.example.com/hero.png",
        wait=False,
        html='<html><img src="https://cdn.example.com/hero.png"></html>',
    )
    source = pipeline.store.register(
        media,
        role=ArtifactRole.SOURCE,
        media_kind=MediaKind.IMAGE,
        provenance={"job_id": str(job.job_id)},
    )
    pipeline.queue.put_checkpoint(
        job.job_id,
        {
            "stage": "acquired",
            "source_ids": [source.artifact_id],
            "produced_ids": [source.artifact_id],
            "acquired_kinds": ["image"],
        },
    )
    result = pipeline.run_next()
    assert result is not None
    assert result.state is JobState.COMPLETED


def test_imagemagick_accepts_convert_alias(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        captured.append(argv)
        Path(argv[-1]).write_bytes(b"ok")
        return 0, b"", b""

    runtime = ProviderRuntime(
        which=lambda name: "/usr/bin/convert" if name == "convert" else None,
        run=run,
    )
    assert runtime.health("imagemagick") == "healthy"
    assert (
        resolve_provider_binary(
            "magick",
            which=lambda name: "/usr/bin/convert" if name == "convert" else None,
        )
        == "/usr/bin/convert"
    )
    result = runtime.execute(
        ProviderRequest(
            provider_id="imagemagick",
            capability_id="process.imagemagick.convert",
            typed_inputs={
                "input": str(tmp_path / "a.png"),
                "output": str(tmp_path / "b.png"),
            },
        ),
        tmp_path,
    )
    assert result.exit_code == 0
    assert captured[0][0] == "/usr/bin/convert"
    assert resolve_provider_binary(None) is None
    assert resolve_provider_binary("") is None


def test_job_detail_skips_unrelated_history_and_run_next_payload(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    pipeline = Pipeline(data_dir=tmp_data)
    empty = run_next_payload(pipeline)
    assert empty == {"job": None, "events": []}
    job = pipeline.submit(str(media), wait=False)
    original = pipeline.history_entries

    def history(_self: Pipeline) -> list[dict[str, Any]]:
        return [
            {"job_id": "00000000-0000-0000-0000-000000000000", "artifact_ids": ["skip"]},
            *original(),
        ]

    monkeypatch.setattr(Pipeline, "history_entries", history)
    detail = job_detail_payload(pipeline, job.job_id)
    assert detail["job"]["job_id"] == str(job.job_id)
    assert "skip" not in detail["artifact_ids"]
    monkeypatch.setattr(Pipeline, "history_entries", lambda _self: [])
    assert job_detail_payload(pipeline, job.job_id)["artifact_ids"] == []
    monkeypatch.setattr(
        Pipeline,
        "history_entries",
        lambda _self: [{"job_id": str(job.job_id)}],
    )
    assert job_detail_payload(pipeline, job.job_id)["artifact_ids"] == []
    ran = run_next_payload(pipeline)
    assert ran["job"] is not None
    assert ran["job"]["job_id"] == str(job.job_id)
    assert ran["events"]


def test_doctor_reports_missing_provider_binaries(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("webmedia_dl.diagnostics.resolve_provider_binary", lambda _name: None)
    payload = doctor()
    assert payload["providers"]["http-direct"]["status"] == "PASS"
    assert payload["providers"]["ytdlp"]["status"] == "BLOCKED"
    assert payload["providers"]["gallery-dl"]["status"] == "BLOCKED"
    assert payload["providers"]["ffmpeg"]["status"] == "BLOCKED"
    assert payload["providers"]["imagemagick"]["status"] == "BLOCKED"
    assert payload["providers"]["ytdlp"]["binary"] is None
