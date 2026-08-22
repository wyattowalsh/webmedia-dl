"""Fail-closed API, live, probe, publish, and CLI proofs for remaining OpenSpec gaps."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi.testclient import TestClient
from pydantic import ValidationError
from typer.testing import CliRunner

from webmedia_dl.cli import app
from webmedia_dl.continuity import CompanionRelay, companion_message
from webmedia_dl.domain.enums import (
    ArtifactRole,
    DestinationKind,
    EventType,
    JobState,
    LossClass,
    MediaKind,
    Surface,
)
from webmedia_dl.domain.models import Artifact, BrowserEvidence, ExportIntent
from webmedia_dl.envelope import _NONCE_SIZE, _TAG_SIZE, _key_bytes, open_payload, seal_payload
from webmedia_dl.errors import DelegationDenied, DiscoveryError, NetworkPolicyError
from webmedia_dl.export import plan_export
from webmedia_dl.live import record_clear_stream, record_kind_streams
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.providers import ProviderRuntime
from webmedia_dl.service import create_app, load_or_create_token, serve_worker

runner = CliRunner()
UNKNOWN_JOB = "11111111-1111-1111-1111-111111111111"
DRM_HTML = """
<html><body>
  <video src="https://cdn.example.com/widevine-stream.mpd"></video>
  <p>com.widevine.alpha</p>
</body></html>
"""


def _auth_client(tmp_path: Path) -> tuple[TestClient, dict[str, str]]:
    api = create_app(tmp_path)
    token = load_or_create_token(tmp_path)
    return TestClient(api), {"Authorization": f"Bearer {token}"}


def _seal_raw(session_key: str, raw: bytes) -> dict[str, str]:
    nonce = secrets.token_bytes(_NONCE_SIZE)
    packed = AESGCM(_key_bytes(session_key)).encrypt(nonce, raw, None)
    return {
        "nonce": nonce.hex(),
        "ciphertext": packed[:-_TAG_SIZE].hex(),
        "mac": packed[-_TAG_SIZE:].hex(),
    }


def test_pair_start_rejects_full_and_unknown_profiles(tmp_path: Path) -> None:
    client, headers = _auth_client(tmp_path)
    full = client.post("/v1/pair", headers=headers, json={"client_profile_id": "personal-full"})
    assert full.status_code == 400
    assert "full profile" in full.json()["detail"]
    unknown = client.post("/v1/pair", headers=headers, json={"client_profile_id": "not-a-profile"})
    assert unknown.status_code == 400
    assert "Unknown client profile" in unknown.json()["detail"]


def test_unconfirmed_pairing_job_does_not_execute_providers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executed: list[str] = []

    def boom(self: object, *args: object, **kwargs: object) -> None:
        executed.append("execute")
        raise AssertionError("unconfirmed pairing must not run providers")

    monkeypatch.setattr("webmedia_dl.providers.ProviderRuntime.execute", boom)
    client, headers = _auth_client(tmp_path)
    created = client.post("/v1/pair", json={"client_profile_id": "personal-restricted"})
    pairing_id = created.json()["pairing_id"]
    denied = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "locator": "https://example.com/watch",
            "html": "<html><title>Video</title></html>",
            "surface": "ios",
            "pairing_id": pairing_id,
        },
    )
    assert denied.status_code == 400
    assert executed == []


@pytest.mark.parametrize("kind", ["cancel", "pause_job", "resume_job"])
def test_companion_unknown_job_is_404(tmp_path: Path, kind: str) -> None:
    client, headers = _auth_client(tmp_path)
    response = client.post(
        "/v1/companion",
        headers=headers,
        json={
            "kind": kind,
            "job_id": UNKNOWN_JOB,
            "nativeCommand": None,
            "subprocessWorker": False,
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Unknown job"


def test_envelope_non_object_json_is_refused(tmp_path: Path) -> None:
    client, headers = _auth_client(tmp_path)
    created = client.post("/v1/pair", headers=headers)
    pairing_id = created.json()["pairing_id"]
    confirmed = client.post("/v1/pair/confirm", headers=headers, json={"pairing_id": pairing_id})
    session_key = confirmed.json()["session_key"]
    sealed = _seal_raw(session_key, json.dumps([1, 2, 3]).encode())
    with pytest.raises(DelegationDenied, match="must be an object"):
        open_payload(session_key, sealed)
    opened = client.post(
        "/v1/pair/envelope/open",
        headers=headers,
        json={"pairing_id": pairing_id, "session_key": session_key, **sealed},
    )
    assert opened.status_code in {400, 401}
    scalar = _seal_raw(session_key, json.dumps("nope").encode())
    denied = client.post(
        "/v1/pair/envelope/open",
        headers=headers,
        json={"pairing_id": pairing_id, "session_key": session_key, **scalar},
    )
    assert denied.status_code in {400, 401}
    garbage = _seal_raw(session_key, b"not-json")
    with pytest.raises(DelegationDenied, match="not JSON"):
        open_payload(session_key, garbage)


def test_open_envelope_non_object_adapter_is_400(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, headers = _auth_client(tmp_path)
    created = client.post("/v1/pair", headers=headers)
    pairing_id = created.json()["pairing_id"]
    confirmed = client.post("/v1/pair/confirm", headers=headers, json={"pairing_id": pairing_id})
    session_key = confirmed.json()["session_key"]

    def fake_open(*_args: object, **_kwargs: object) -> list[int]:
        return [1, 2]

    monkeypatch.setattr("webmedia_dl.service.open_payload", fake_open)
    opened = client.post(
        "/v1/pair/envelope/open",
        headers=headers,
        json={
            "pairing_id": pairing_id,
            "session_key": session_key,
            "nonce": "aa",
            "ciphertext": "bb",
            "mac": "cc",
        },
    )
    assert opened.status_code == 400
    assert "object" in opened.json()["detail"].lower()


def test_companion_envelope_list_payload_is_400(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, headers = _auth_client(tmp_path)
    created = client.post("/v1/pair", headers=headers)
    pairing_id = created.json()["pairing_id"]
    confirmed = client.post("/v1/pair/confirm", headers=headers, json={"pairing_id": pairing_id})
    session_key = confirmed.json()["session_key"]

    def fake_open(*_args: object, **_kwargs: object) -> list[int]:
        return [1, 2]

    monkeypatch.setattr("webmedia_dl.service.open_payload", fake_open)
    response = client.post(
        "/v1/companion",
        headers=headers,
        json={
            "pairing_id": pairing_id,
            "session_key": session_key,
            "nonce": "aa",
            "ciphertext": "bb",
            "mac": "cc",
        },
    )
    assert response.status_code == 400
    assert "invalid" in response.json()["detail"].lower()


def test_plan_drm_is_side_effect_free(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    executed: list[str] = []

    def boom(self: object, *args: object, **kwargs: object) -> None:
        executed.append("execute")
        raise AssertionError("plan must not execute providers")

    monkeypatch.setattr("webmedia_dl.providers.ProviderRuntime.execute", boom)
    client, headers = _auth_client(tmp_path)
    planned = client.post(
        "/v1/plan",
        headers=headers,
        json={"locator": "https://example.com/drm", "html": DRM_HTML},
    )
    assert planned.status_code == 400
    assert executed == []
    history = client.get("/v1/jobs", headers=headers)
    assert history.status_code == 200
    assert history.json() == []
    artifacts = client.get("/v1/artifacts", headers=headers)
    assert artifacts.json() == []


def test_jobs_export_outside_approved_roots_fails_closed(tmp_path: Path, png_bytes: bytes) -> None:
    client, headers = _auth_client(tmp_path)
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    response = client.post(
        "/v1/jobs",
        headers=headers,
        json={
            "locator": str(media),
            "intent": {
                "destination_kind": DestinationKind.USER_APPROVED_PATH.value,
                "destination_path": str(outside),
                "approved_roots": [str(allowed)],
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["job"]["state"] == JobState.FAILED.value
    assert body["job"]["error"]
    types = [event["type"] for event in body["events"]]
    assert EventType.JOB_FAILED.value in types
    assert not any(path.is_file() for path in outside.rglob("*"))


def test_dynamic_dash_stops_remaining_kinds_after_late_drm(tmp_path: Path) -> None:
    clear = """
    <MPD type="dynamic">
      <Period>
        <AdaptationSet mimeType="video/mp4">
          <Representation id="v" bandwidth="800000">
            <BaseURL>video.m4s</BaseURL>
          </Representation>
        </AdaptationSet>
        <AdaptationSet mimeType="audio/mp4">
          <Representation id="a" bandwidth="128000">
            <BaseURL>audio.m4s</BaseURL>
          </Representation>
        </AdaptationSet>
      </Period>
    </MPD>
    """
    protected = clear.replace(
        '<MPD type="dynamic">',
        '<MPD type="dynamic"><ContentProtection schemeIdUri="urn:mpeg:cenc"/>',
    )
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        if url.endswith("manifest.mpd"):
            return 200, "application/dash+xml", protected.encode()
        if url.endswith("audio.m4s"):
            raise AssertionError("audio must not be fetched after ContentProtection")
        return 200, "video/mp4", b"VID"

    dest = tmp_path / "live.bin"
    recorded = record_kind_streams(
        clear,
        "https://cdn.example.com/manifest.mpd",
        dest,
        fetch,
        live_polls=2,
    )
    kinds = {kind for kind, _path in recorded}
    assert MediaKind.VIDEO in kinds
    assert MediaKind.AUDIO not in kinds
    assert not any(item.endswith("audio.m4s") for item in fetched)
    video_path = next(path for kind, path in recorded if kind is MediaKind.VIDEO)
    assert video_path.read_bytes() == b"VID"


def test_live_hls_refetches_growing_byte_range(tmp_path: Path) -> None:
    first = "#EXTM3U\n#EXT-X-BYTERANGE:3@0\nseg.ts\n"
    later = "#EXTM3U\n#EXT-X-BYTERANGE:6@0\nseg.ts\n"
    playlist_fetches = {"n": 0}
    object_fetches = {"n": 0}

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("index.m3u8"):
            playlist_fetches["n"] += 1
            text = later if playlist_fetches["n"] else first
            return 200, "application/vnd.apple.mpegurl", text.encode()
        object_fetches["n"] += 1
        body = b"AAA" if object_fetches["n"] == 1 else b"AAABBB"
        return 200, "video/MP2T", body

    output = tmp_path / "live.ts"
    record_clear_stream(
        first,
        "https://cdn.example.com/live/index.m3u8",
        output,
        fetch,
        live_polls=2,
    )
    assert output.read_bytes() == b"AAABBB"
    assert object_fetches["n"] == 2
    skip_first = (
        "#EXTM3U\n"
        "#EXT-X-MEDIA-SEQUENCE:1\n"
        "#EXT-X-BYTERANGE:3@0\n"
        "seg.ts\n"
        "#EXT-X-BYTERANGE:3@3\n"
        "seg.ts\n"
    )
    skip_later = (
        "#EXTM3U\n"
        "#EXT-X-MEDIA-SEQUENCE:1\n"
        "#EXT-X-SKIP:SKIPPED-SEGMENTS=1\n"
        "#EXT-X-BYTERANGE:3@3\n"
        "seg.ts\n"
        "#EXT-X-BYTERANGE:3@6\n"
        "seg.ts\n"
    )
    skip_playlists = [skip_later]

    def fetch_skip_range(url: str) -> tuple[int, str, bytes]:
        if url.endswith("index.m3u8"):
            payload = skip_playlists.pop(0) if skip_playlists else skip_later
            return 200, "application/vnd.apple.mpegurl", payload.encode()
        return 200, "video/MP2T", b"AAABBBCCC"

    skip_range_out = tmp_path / "skip-range.ts"
    record_clear_stream(
        skip_first,
        "https://cdn.example.com/live/index.m3u8",
        skip_range_out,
        fetch_skip_range,
        live_polls=2,
    )
    assert skip_range_out.read_bytes() == b"AAABBBCCC"


def test_http_probe_encryption_is_terminal_without_fallback(
    tmp_data: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ytdlp_argv: list[list[str]] = []

    class Result:
        returncode = 0
        stdout = json.dumps(
            {
                "streams": [
                    {
                        "index": 0,
                        "codec_type": "video",
                        "codec_name": "h264",
                        "encrypted": True,
                    }
                ],
                "format": {"format_name": "mp4"},
                "drm_signals": ["probe:encrypted-stream"],
            }
        )
        stderr = b""

    monkeypatch.setattr(
        "webmedia_dl.probe.shutil.which",
        lambda name: "/usr/bin/ffprobe" if name == "ffprobe" else None,
    )
    monkeypatch.setattr("webmedia_dl.probe.subprocess.run", lambda *_args, **_kwargs: Result())

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        ytdlp_argv.append(argv)
        if "--dump-json" in argv:
            return 1, b"{}", b"unavailable"
        raise AssertionError("encrypted HTTP acquisition must not fall back to yt-dlp")

    runtime = ProviderRuntime(
        which=lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None,
        run=run,
        http_get=lambda url: (200, {"content-type": "video/mp4"}, b"fake-mp4-bytes"),
    )
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit("https://cdn.example.com/clip.mp4")
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "drm" in job.error.lower() or "encrypted" in job.error.lower()
    assert not any("--output" in argv for argv in ytdlp_argv)
    roles = {item.role for item in pipeline.store.list_artifacts()}
    assert ArtifactRole.SOURCE not in roles
    assert ArtifactRole.QUARANTINE in roles
    types = [event.type for event in pipeline.queue.events_for(job.job_id)]
    assert EventType.ACQUISITION_QUARANTINE in types
    assert EventType.JOB_FAILED in types
    assert EventType.SOURCE_REGISTERED not in types


def test_publish_oserror_fails_job(
    tmp_data: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    media = tmp_data.parent / "hero.png"
    media.write_bytes(png_bytes)

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("webmedia_dl.pipeline.publish_artifacts", boom)
    pipeline = Pipeline(data_dir=tmp_data)
    job = pipeline.submit(str(media))
    assert job.state is JobState.FAILED
    assert job.error is not None
    assert "disk full" in job.error
    types = [event.type for event in pipeline.queue.events_for(job.job_id)]
    assert EventType.JOB_FAILED in types
    assert EventType.PUBLISHED not in types


def test_run_next_restores_browser_evidence(tmp_data: Path, png_bytes: bytes) -> None:
    runtime = ProviderRuntime(http_get=lambda url: (200, {"content-type": "image/png"}, png_bytes))
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit(
        "https://example.com/page",
        html="<html><body>no media tags</body></html>",
        wait=False,
        evidence=[
            BrowserEvidence(url="https://cdn.example.com/captured.png", kind=MediaKind.IMAGE)
        ],
    )
    assert job.state is JobState.ACCEPTED
    completed = pipeline.run_next()
    assert completed is not None
    assert completed.state is JobState.COMPLETED
    assert completed.job_id == job.job_id


@pytest.mark.parametrize(
    "args",
    [
        ["job", UNKNOWN_JOB],
        ["cancel", UNKNOWN_JOB],
        ["pause", "--job", UNKNOWN_JOB],
        ["resume", "--job", UNKNOWN_JOB],
        ["companion", "cancel", "--job", UNKNOWN_JOB],
        ["companion", "pause_job", "--job", UNKNOWN_JOB],
        ["companion", "resume_job", "--job", UNKNOWN_JOB],
    ],
)
def test_cli_unknown_job_exits_nonzero(tmp_path: Path, args: list[str]) -> None:
    result = runner.invoke(app, [*args, "--data-dir", str(tmp_path / "data")])
    assert result.exit_code == 1
    assert "Unknown job" in result.stdout


def test_cli_plan_drm_exits_nonzero(tmp_path: Path) -> None:
    html = tmp_path / "drm.html"
    html.write_text(DRM_HTML, encoding="utf-8")
    result = runner.invoke(
        app,
        [
            "plan",
            "https://example.com/drm",
            "--html",
            str(html),
            "--data-dir",
            str(tmp_path / "data"),
        ],
    )
    assert result.exit_code == 1
    assert result.stdout.strip()
    lowered = result.stdout.lower()
    assert "drm" in lowered or "widevine" in lowered or "encrypted" in lowered


def test_live_growing_range_refetch_http_error_fails_closed(tmp_path: Path) -> None:
    first = "#EXTM3U\n#EXT-X-BYTERANGE:3@0\nseg.ts\n"
    later = "#EXTM3U\n#EXT-X-BYTERANGE:6@0\nseg.ts\n"
    object_fetches = {"n": 0}

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("index.m3u8"):
            return 200, "application/vnd.apple.mpegurl", later.encode()
        object_fetches["n"] += 1
        if object_fetches["n"] == 1:
            return 200, "video/MP2T", b"AAA"
        return 404, "", b""

    with pytest.raises(DiscoveryError, match="HTTP 404"):
        record_clear_stream(
            first,
            "https://cdn.example.com/live/index.m3u8",
            tmp_path / "live.ts",
            fetch,
            live_polls=2,
        )


def test_live_already_written_range_is_not_rewound(tmp_path: Path) -> None:
    first = "#EXTM3U\n#EXT-X-BYTERANGE:6@0\nseg.ts\n"
    later = "#EXTM3U\n#EXT-X-BYTERANGE:3@0\nseg.ts\n"

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("index.m3u8"):
            return 200, "application/vnd.apple.mpegurl", later.encode()
        return 200, "video/MP2T", b"AAABBB"

    output = tmp_path / "live.ts"
    record_clear_stream(
        first,
        "https://cdn.example.com/live/index.m3u8",
        output,
        fetch,
        live_polls=2,
    )
    assert output.read_bytes() == b"AAABBB"


def test_run_next_restores_cookie_grant(tmp_data: Path, tmp_path: Path, ytdlp_run_ok) -> None:
    cookies = tmp_path / "user-cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
    captured: list[list[str]] = []

    def run(argv: list[str], cwd: Path) -> tuple[int, bytes, bytes]:
        captured.append(list(argv))
        return ytdlp_run_ok(argv, cwd)

    runtime = ProviderRuntime(
        which=lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None,
        run=run,
        http_get=lambda _url: (404, {}, b""),
    )
    pipeline = Pipeline(data_dir=tmp_data, runtime=runtime)
    job = pipeline.submit(
        "https://example.com/watch",
        html="<html><title>Video</title></html>",
        cookies=str(cookies),
        wait=False,
    )
    assert pipeline.queue.get_context(job.job_id).cookies
    completed = pipeline.run_next()
    assert completed is not None
    assert completed.state is JobState.COMPLETED
    cookie_argv = [argv for argv in captured if "--cookies" in argv]
    assert cookie_argv
    resolved = str(cookies.resolve())
    assert any(resolved in argv for argv in cookie_argv)
    types = [event.type.value for event in pipeline.queue.events_for(job.job_id)]
    assert "cookie.attached" in types


def test_user_approved_path_omits_approved_roots() -> None:
    with pytest.raises(ValidationError, match="approved"):
        ExportIntent(
            destination_kind=DestinationKind.USER_APPROVED_PATH,
            destination_path="/tmp/webmedia-dl-out",
        )


def test_original_sacred_keeps_original_with_no_loss() -> None:
    source = Artifact(
        artifact_id="sha256:ab",
        role=ArtifactRole.SOURCE,
        sha256="ab",
        byte_size=1,
        media_kind=MediaKind.VIDEO,
        storage_relpath="a.mp4",
        container="mp4",
    )
    sacred = plan_export(uuid4(), source, ExportIntent(preset_id="original-sacred"))
    assert sacred.operations[0].operation_id == "keep-original"
    assert sacred.operations[0].loss_class is LossClass.NONE
    assert all(item.operation_id != "transcode" for item in sacred.operations)
    remux_only = plan_export(
        uuid4(),
        source,
        ExportIntent(preset_id="original-sacred", container_preference="mkv"),
    )
    ids = [item.operation_id for item in remux_only.operations]
    assert "keep-original" in ids
    assert "remux" in ids
    assert "transcode" not in ids
    assert remux_only.operations[0].loss_class is LossClass.NONE


def test_sealed_companion_native_command_is_refused(tmp_path: Path) -> None:
    client, headers = _auth_client(tmp_path)
    created = client.post("/v1/pair", headers=headers)
    pairing_id = created.json()["pairing_id"]
    confirmed = client.post("/v1/pair/confirm", headers=headers, json={"pairing_id": pairing_id})
    session_key = confirmed.json()["session_key"]
    sealed = seal_payload(
        session_key,
        {
            "kind": "capture",
            "locator": "https://cdn.example.com/a.mp4",
            "nativeCommand": "yt-dlp",
            "subprocessWorker": False,
            "surface": Surface.WATCHOS.value,
        },
    )
    refused = client.post(
        "/v1/companion",
        json={"pairing_id": pairing_id, "session_key": session_key, **sealed},
        headers=headers,
    )
    assert refused.status_code == 400
    assert "native command" in refused.json()["detail"].lower()
    replay = client.post(
        "/v1/companion",
        json={"pairing_id": pairing_id, "session_key": session_key, **sealed},
        headers=headers,
    )
    assert replay.status_code in {400, 401}


@pytest.mark.parametrize("surface", [Surface.WATCHOS, Surface.TVOS])
def test_watch_tv_capture_queues_without_ytdlp(
    surface: Surface, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[str] = []

    def which(name: str) -> str | None:
        opened.append(name)
        return None

    monkeypatch.setattr("shutil.which", which)
    message = companion_message(
        "capture",
        locator="https://cdn.example.com/a.mp4",
        surface=surface,
    )
    queued = CompanionRelay().enqueue(message)
    assert queued["nativeCommand"] is None
    assert queued["subprocessWorker"] is False
    assert message["surface"] == surface.value
    assert "yt-dlp" not in opened


def test_serve_worker_rejects_non_loopback(tmp_path: Path) -> None:
    with pytest.raises(NetworkPolicyError, match="loopback"):
        serve_worker(data_dir=tmp_path, host="0.0.0.0", port=8765)


def test_publish_stages_under_approved_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, png_bytes: bytes
) -> None:
    from webmedia_dl.identity import sha256_file
    from webmedia_dl.publish import publish_artifacts
    from webmedia_dl.validation import validate_artifact

    src = tmp_path / "hero.png"
    src.write_bytes(png_bytes)
    digest = sha256_file(str(src))
    artifact = Artifact(
        artifact_id=f"sha256:{digest}",
        role=ArtifactRole.SOURCE,
        sha256=digest,
        byte_size=len(png_bytes),
        media_kind=MediaKind.IMAGE,
        storage_relpath="hero.png",
        container="png",
    )
    dest = tmp_path / "out"
    dest.mkdir()
    staged_dirs: list[Path] = []
    replaced: list[tuple[Path, Path]] = []
    real_mkdtemp = __import__("tempfile").mkdtemp
    real_replace = __import__("os").replace

    def spy_mkdtemp(
        suffix: str | None = None,
        prefix: str | None = None,
        dir: str | Path | None = None,
    ) -> str:
        path = real_mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
        staged_dirs.append(Path(path))
        return path

    def spy_replace(src_path: str | Path, dest_path: str | Path) -> None:
        replaced.append((Path(src_path), Path(dest_path)))
        real_replace(src_path, dest_path)

    monkeypatch.setattr("webmedia_dl.publish.tempfile.mkdtemp", spy_mkdtemp)
    monkeypatch.setattr("webmedia_dl.publish.os.replace", spy_replace)
    published = publish_artifacts(
        [(artifact, src, validate_artifact(uuid4(), artifact, src))],
        ExportIntent(
            destination_kind=DestinationKind.USER_APPROVED_PATH,
            destination_path=str(dest),
            approved_roots=[str(dest)],
        ),
    )
    assert published
    assert staged_dirs
    assert staged_dirs[0].is_relative_to(dest)
    assert replaced
    assert replaced[0][1].is_relative_to(dest)
    assert replaced[0][1] == published[0]
