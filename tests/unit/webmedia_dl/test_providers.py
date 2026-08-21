from pathlib import Path

import pytest

from webmedia_dl.errors import ProviderPolicyError
from webmedia_dl.providers import ProviderRequest, ProviderRuntime


def test_extra_args_rejected(tmp_path: Path) -> None:
    runtime = ProviderRuntime()
    with pytest.raises(ProviderPolicyError, match="arbitrary user arguments"):
        runtime.execute(
            ProviderRequest(
                provider_id="ytdlp",
                capability_id="acquire.ytdlp",
                typed_inputs={"url": "https://example.com/v", "output": str(tmp_path / "o")},
                extra_args=("--add-header", "X:1"),
            ),
            tmp_path,
        )


def test_ytdlp_argv_is_allowlisted(tmp_path: Path) -> None:
    captured: list[list[str]] = []

    def which(name: str) -> str | None:
        return "/usr/bin/yt-dlp" if name == "yt-dlp" else None

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        captured.append(argv)
        output = argv[argv.index("--output") + 1]
        Path(str(output).replace("%(ext)s", "mp4")).write_bytes(b"ok")
        return 0, b"", b""

    runtime = ProviderRuntime(which=which, run=run)
    runtime.execute(
        ProviderRequest(
            provider_id="ytdlp",
            capability_id="acquire.ytdlp",
            typed_inputs={
                "url": "https://example.com/watch?v=1",
                "output": str(tmp_path / "source.bin"),
                "format_id": "137+140",
            },
        ),
        tmp_path,
    )
    argv = captured[0]
    assert argv[0] == "/usr/bin/yt-dlp"
    assert "--format" in argv
    assert "137+140" in argv
    assert "--exec" not in argv
    assert argv[-1] == "https://example.com/watch?v=1"
    assert "%(ext)s" in argv[argv.index("--output") + 1]


def test_unsafe_format_id_rejected(tmp_path: Path) -> None:
    runtime = ProviderRuntime(which=lambda name: "/usr/bin/yt-dlp")
    with pytest.raises(ProviderPolicyError):
        runtime.execute(
            ProviderRequest(
                provider_id="ytdlp",
                capability_id="acquire.ytdlp",
                typed_inputs={
                    "url": "https://example.com/v",
                    "output": str(tmp_path / "o"),
                    "format_id": "137; rm -rf /",
                },
            ),
            tmp_path,
        )


def test_http_direct(tmp_path: Path, http_runtime: ProviderRuntime) -> None:
    result = http_runtime.execute(
        ProviderRequest(
            provider_id="http-direct",
            capability_id="acquire.http",
            typed_inputs={"url": "https://cdn.example.com/a.png"},
        ),
        tmp_path,
    )
    assert result.exit_code == 0
    assert result.output_path is not None
    assert result.output_path.suffix == ".png"
    assert result.output_path.read_bytes().startswith(b"\x89PNG")


def test_unknown_provider_and_capability_fail_closed(tmp_path: Path) -> None:
    runtime = ProviderRuntime(which=lambda name: f"/usr/bin/{name}")
    with pytest.raises(ProviderPolicyError, match="Unknown provider"):
        runtime.execute(
            ProviderRequest(
                provider_id="curl",
                capability_id="acquire.http",
                typed_inputs={"url": "https://cdn.example.com/a.mp4"},
            ),
            tmp_path,
        )
    with pytest.raises(ProviderPolicyError, match="does not expose"):
        runtime.execute(
            ProviderRequest(
                provider_id="http-direct",
                capability_id="acquire.ytdlp",
                typed_inputs={"url": "https://cdn.example.com/a.mp4"},
            ),
            tmp_path,
        )


def test_default_http_get_uses_profile_byte_bound(monkeypatch: pytest.MonkeyPatch) -> None:
    from webmedia_dl.providers import default_http_get

    seen: dict[str, object] = {}

    def fake_fetch(url: str, **kwargs: object) -> tuple[int, str, bytes]:
        seen["url"] = url
        seen["on_overflow"] = kwargs.get("on_overflow")
        return 200, "video/mp4", b"ok"

    monkeypatch.setattr("webmedia_dl.providers.bound_fetch", fake_fetch)
    status, headers, body = default_http_get("https://cdn.example.com/a.mp4")
    assert status == 200
    assert body == b"ok"
    assert headers["content-type"] == "video/mp4"
    assert seen["url"] == "https://cdn.example.com/a.mp4"
    assert seen["on_overflow"] == "error"
