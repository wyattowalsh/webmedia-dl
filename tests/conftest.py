"""Shared fixtures. Network, clock, and provider binaries are mocked at unit boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from webmedia_dl.providers import ProviderRuntime


@pytest.fixture
def tmp_data(tmp_path: Path) -> Path:
    return tmp_path / "worker-data"


@pytest.fixture
def png_bytes() -> bytes:
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00"
        b"\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )


@pytest.fixture
def http_runtime(png_bytes: bytes) -> ProviderRuntime:
    def http_get(url: str) -> tuple[int, dict[str, str], bytes]:
        if "missing" in url:
            return 404, {}, b"not found"
        return 200, {"content-type": "image/png"}, png_bytes

    return ProviderRuntime(http_get=http_get)


def fake_ytdlp_run(
    output_bytes: bytes = b"video-bytes",
    *,
    acquire_code: int = 0,
):
    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        if "--dump-json" in argv:
            url = argv[-1]
            body = {
                "id": "vid",
                "title": "Clip",
                "webpage_url": url,
                "formats": [
                    {"format_id": "137", "ext": "mp4", "height": 1080, "tbr": 2500},
                ],
            }
            return 0, json.dumps(body).encode(), b""
        output = argv[argv.index("--output") + 1]
        dest = Path(str(output).replace("%(ext)s", "mp4"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(output_bytes)
        return acquire_code, b"", b"fail" if acquire_code else b""

    return run


@pytest.fixture
def ytdlp_run_ok():
    return fake_ytdlp_run()


@pytest.fixture
def ytdlp_run_fail():
    return fake_ytdlp_run(b"partial", acquire_code=2)


@pytest.fixture
def pass_container_probe(monkeypatch):
    """Executed container evidence for fake ffmpeg/ImageMagick bytes."""
    from uuid import uuid4

    from webmedia_dl.domain.models import MediaProbe

    def fake(path, **_kwargs):
        suffix = Path(path).suffix.lstrip(".").lower() or "bin"
        names = {
            "mkv": "matroska,webm",
            "mp4": "mov,mp4,m4a",
            "m4a": "mov,mp4,m4a",
        }.get(suffix, suffix)
        return MediaProbe(candidate_id=uuid4(), container=suffix, format_names=names)

    monkeypatch.setattr("webmedia_dl.validation.probe_media", fake)
    monkeypatch.setattr("webmedia_dl.processing.probe_media", fake)
    return fake
