from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from webmedia_dl.acquisition import plan_acquisition
from webmedia_dl.domain.enums import DestinationKind, MediaKind
from webmedia_dl.domain.models import ExportIntent, FormatAlternative, MediaCandidate
from webmedia_dl.errors import DelegationDenied, DrmRefused, ProviderPolicyError, PublicationError
from webmedia_dl.export import plan_export
from webmedia_dl.fetch import fetch_fn_for_profile
from webmedia_dl.live import inspect_manifest
from webmedia_dl.pairing import PairingStore
from webmedia_dl.policy.profiles import get_profile
from webmedia_dl.processing import provider_for_operation
from webmedia_dl.providers import ProviderRequest, ProviderRuntime
from webmedia_dl.publish import publish_artifacts
from webmedia_dl.transport import create_challenge, expired


def test_gallery_and_magick_argv(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        captured.append(argv)
        output = argv[-1] if argv[-1].endswith(".png") else tmp_path / "x"
        Path(str(output)).write_bytes(b"ok")
        return 0, b"", b""

    runtime = ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run)
    runtime.execute(
        ProviderRequest(
            provider_id="gallery-dl",
            capability_id="acquire.gallery_dl",
            typed_inputs={"url": "https://example.com/album"},
        ),
        tmp_path,
    )
    runtime.execute(
        ProviderRequest(
            provider_id="imagemagick",
            capability_id="process.imagemagick.convert",
            typed_inputs={"input": str(tmp_path / "a.png"), "output": str(tmp_path / "b.png")},
        ),
        tmp_path,
    )
    assert captured[0][0] == "/usr/bin/gallery-dl"
    assert "--destination" in captured[0]
    assert captured[1][-2] == "-auto-orient"


def test_transcode_allowlisted_and_rejected(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        captured.append(argv)
        Path(argv[-1]).write_bytes(b"x")
        return 0, b"", b""

    runtime = ProviderRuntime(which=lambda name: "/usr/bin/ffmpeg", run=run)
    runtime.execute(
        ProviderRequest(
            provider_id="ffmpeg",
            capability_id="process.ffmpeg.transcode",
            typed_inputs={"input": "/tmp/a.mp4", "output": str(tmp_path / "b.mp4")},
        ),
        tmp_path,
    )
    assert "-c:v" in captured[0]
    assert "libx264" in captured[0]
    with pytest.raises(ProviderPolicyError):
        runtime.execute(
            ProviderRequest(
                provider_id="ffmpeg",
                capability_id="process.ffmpeg.transcode",
                typed_inputs={
                    "input": "/tmp/a.mp4",
                    "output": str(tmp_path / "b.mp4"),
                    "video_codec": "not-a-codec",
                },
            ),
            tmp_path,
        )


def test_ytdlp_cookies_and_merge(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        captured.append(argv)
        Path(argv[argv.index("--output") + 1]).write_bytes(b"v")
        return 0, b"", b""

    runtime = ProviderRuntime(which=lambda name: "/usr/bin/yt-dlp", run=run)
    runtime.execute(
        ProviderRequest(
            provider_id="ytdlp",
            capability_id="acquire.ytdlp",
            typed_inputs={
                "url": "https://example.com/v",
                "output": str(tmp_path / "o"),
                "cookies": "/tmp/outside-cookies.txt",
                "merge_output_format": "mkv",
            },
        ),
        tmp_path,
    )
    assert "--cookies" in captured[0]
    assert "--merge-output-format" in captured[0]
    with pytest.raises(ProviderPolicyError):
        runtime.execute(
            ProviderRequest(
                provider_id="ytdlp",
                capability_id="acquire.ytdlp",
                typed_inputs={
                    "url": "https://example.com/v",
                    "output": str(tmp_path / "o"),
                    "merge_output_format": "exe",
                },
            ),
            tmp_path,
        )


def test_lossy_plan_and_gallery_acquisition() -> None:
    artifact = __import__("webmedia_dl.domain.models", fromlist=["Artifact"]).Artifact(
        artifact_id="sha256:ab",
        role="source",
        sha256="ab",
        byte_size=1,
        media_kind=MediaKind.VIDEO,
        storage_relpath="a.mp4",
        container="mp4",
    )
    plan = plan_export(
        uuid4(),
        artifact,
        ExportIntent(allow_lossy=True, container_preference="mkv"),
    )
    assert any(op.operation_id == "transcode" for op in plan.operations)
    gallery = MediaCandidate(
        source_id=uuid4(),
        media_kind=MediaKind.GALLERY,
        identity_key="host:example.com:path:/album",
        retrieval_urls=["https://example.com/album"],
    )
    acquired = plan_acquisition(uuid4(), gallery, get_profile("personal-full"))
    assert any(item.strategy_id == "gallery-dl" for item in acquired.strategies)
    watch = MediaCandidate(
        source_id=uuid4(),
        media_kind=MediaKind.VIDEO,
        identity_key="host:example.com:path:/watch",
        retrieval_urls=["https://example.com/watch"],
        alternatives=[
            FormatAlternative(format_id="137", container="mp4", height=1080, bitrate=2_500_000)
        ],
    )
    watch_plan = plan_acquisition(uuid4(), watch, get_profile("personal-full"))
    assert all(item.strategy_id != "http-direct" for item in watch_plan.strategies)
    assert any(item.typed_inputs.get("format_id") == "137" for item in watch_plan.strategies)


def test_dash_cenc_refused() -> None:
    with pytest.raises(DrmRefused):
        inspect_manifest(
            "<MPD><ContentProtection schemeIdUri='urn:mpeg:cenc'></ContentProtection></MPD>"
        )


def test_photos_destination_blocked(tmp_path: Path) -> None:
    from webmedia_dl.domain.models import Artifact
    from webmedia_dl.identity import sha256_file
    from webmedia_dl.validation import validate_artifact

    src = tmp_path / "a.bin"
    src.write_bytes(b"data")
    digest = sha256_file(str(src))
    artifact = Artifact(
        artifact_id=f"sha256:{digest}",
        role="source",
        sha256=digest,
        byte_size=4,
        media_kind=MediaKind.UNKNOWN,
        storage_relpath="a.bin",
    )
    intent = ExportIntent(destination_kind=DestinationKind.PHOTOS, approved_roots=[str(tmp_path)])
    with pytest.raises(PublicationError):
        publish_artifacts([(artifact, src, validate_artifact(uuid4(), artifact, src))], intent)


def test_expired_and_unknown_pairing(tmp_path: Path) -> None:
    store = PairingStore(tmp_path)
    challenge = create_challenge("personal-restricted", "local-macos", ttl_seconds=0)
    assert expired(challenge, now=datetime.now(UTC) + timedelta(seconds=1))
    with pytest.raises(DelegationDenied):
        store.confirm(challenge.pairing_id)
    with pytest.raises(DelegationDenied):
        store.require_confirmed(uuid4())


def test_fetch_fn_for_profile_and_unknown_operation() -> None:
    import httpx

    profile = get_profile("personal-full")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>", headers={"content-type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    fetch = fetch_fn_for_profile(profile, client=client)
    status, content_type, body = fetch("https://example.com/")
    assert status == 200
    assert b"html" in body
    assert "html" in content_type
    from webmedia_dl.domain.models import Operation

    with pytest.raises(ProviderPolicyError):
        provider_for_operation(
            Operation(
                operation_id="x",
                op_type="unknown.op",
                capability_id="x",
                input_artifact_ids=["a"],
                output_role="derivative",
                loss_class="none",
                validator_ids=[],
            )
        )


def test_serve_rejects_non_loopback() -> None:
    from typer.testing import CliRunner

    from webmedia_dl.cli import app

    result = CliRunner().invoke(app, ["serve", "--host", "0.0.0.0"])
    assert result.exit_code == 2
