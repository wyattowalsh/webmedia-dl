"""Provider manifests and bounded execution. No public behavior contracts leak to argv."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from webmedia_dl.domain.models import PolicyProfile, ProviderManifest
from webmedia_dl.errors import CancelledError, ProviderPolicyError
from webmedia_dl.fetch import bound_fetch
from webmedia_dl.identity import is_safe_format_id
from webmedia_dl.paths import repo_root
from webmedia_dl.policy.profiles import get_profile

MAGICK_FORMATS = {
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "png": "png",
    "webp": "webp",
    "gif": "gif",
    "tif": "tiff",
    "tiff": "tiff",
    "avif": "avif",
}

RunFn = Callable[[list[str], Path], tuple[int, bytes, bytes]]


def imagemagick_configure_path() -> Path:
    return repo_root() / "resources" / "imagemagick-runtime"


def default_subprocess_run(argv: list[str], staging: Path) -> tuple[int, bytes, bytes]:
    env = os.environ.copy()
    env["MAGICK_CONFIGURE_PATH"] = str(imagemagick_configure_path())
    completed = subprocess.run(
        argv,
        cwd=staging,
        capture_output=True,
        timeout=600,
        env=env,
        check=False,
    )
    return completed.returncode, completed.stdout, completed.stderr


def default_http_get(
    url: str, *, profile: PolicyProfile | None = None
) -> tuple[int, dict[str, str], bytes]:
    policy = profile or get_profile("personal-full")
    status, content_type, body = bound_fetch(
        url,
        profile=policy,
        max_bytes=policy.max_download_bytes,
        on_overflow="error",
    )
    return status, {"content-type": content_type}, body


def builtin_manifests() -> dict[str, ProviderManifest]:
    return {
        "http-direct": ProviderManifest(
            provider_id="http-direct",
            display_name="Direct HTTP",
            binary_name=None,
            capabilities=["acquire.http", "discover.direct"],
            license="MIT",
            source_url="https://github.com/wyattowalsh/webmedia-dl",
        ),
        "ytdlp": ProviderManifest(
            provider_id="ytdlp",
            display_name="yt-dlp",
            binary_name="yt-dlp",
            capabilities=["acquire.ytdlp", "discover.manifest"],
            allowed_flags=[
                "--dump-json",
                "--no-playlist",
                "--no-progress",
                "--newline",
                "--output",
                "--merge-output-format",
                "--format",
                "--cookies",
                "--no-mtime",
                "--restrict-filenames",
            ],
            license="Unlicense",
            source_url="https://github.com/yt-dlp/yt-dlp",
        ),
        "gallery-dl": ProviderManifest(
            provider_id="gallery-dl",
            display_name="gallery-dl",
            binary_name="gallery-dl",
            capabilities=["acquire.gallery_dl"],
            allowed_flags=["--no-mtime", "--destination", "--filename"],
            license="GPL-2.0",
            source_url="https://github.com/mikf/gallery-dl",
        ),
        "ffmpeg": ProviderManifest(
            provider_id="ffmpeg",
            display_name="ffmpeg",
            binary_name="ffmpeg",
            capabilities=["process.ffmpeg.remux", "process.ffmpeg.transcode"],
            allowed_flags=["-i", "-c", "copy", "-y", "-c:v", "-c:a"],
            license="GPL/LGPL",
            source_url="https://ffmpeg.org",
        ),
        "imagemagick": ProviderManifest(
            provider_id="imagemagick",
            display_name="ImageMagick",
            binary_name="magick",
            capabilities=["process.imagemagick.convert"],
            allowed_flags=["-auto-orient"],
            license="ImageMagick",
            source_url="https://imagemagick.org",
        ),
    }


@dataclass(frozen=True)
class ProviderRequest:
    provider_id: str
    capability_id: str
    typed_inputs: dict[str, Any]
    extra_args: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProviderResult:
    exit_code: int
    stdout: bytes
    stderr: bytes
    output_path: Path | None
    argv: tuple[str, ...]
    output_paths: tuple[Path, ...] = field(default_factory=tuple)


class ProviderRuntime:
    def __init__(
        self,
        *,
        which: Callable[[str], str | None] | None = None,
        run: RunFn | None = None,
        http_get: Callable[[str], tuple[int, dict[str, str], bytes]] | None = None,
    ) -> None:
        self._manifests = builtin_manifests()
        self._which = which or shutil.which
        self._run = run if run is not None else self._tracked_run
        self._http_get = http_get
        self._lock = threading.Lock()
        self._procs: list[subprocess.Popen[bytes]] = []
        self._cancel = threading.Event()

    def cancel_running(self) -> None:
        self._cancel.set()
        with self._lock:
            procs = list(self._procs)
        for proc in procs:
            _terminate_process(proc)

    def _tracked_run(self, argv: list[str], staging: Path) -> tuple[int, bytes, bytes]:
        env = os.environ.copy()
        env["MAGICK_CONFIGURE_PATH"] = str(imagemagick_configure_path())
        proc = subprocess.Popen(
            argv,
            cwd=staging,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        with self._lock:
            self._procs.append(proc)
        try:
            stdout, stderr = proc.communicate(timeout=600)
            return proc.returncode or 0, stdout, stderr
        except subprocess.TimeoutExpired:
            _terminate_process(proc)
            stdout, stderr = proc.communicate()
            return proc.returncode or 124, stdout, stderr
        finally:
            with self._lock:
                if proc in self._procs:
                    self._procs.remove(proc)

    def health(self, provider_id: str) -> str:
        manifest = self._manifests[provider_id]
        if manifest.binary_name is None:
            return "healthy"
        return "healthy" if self._which(manifest.binary_name) else "missing"

    def execute(self, request: ProviderRequest, staging: Path) -> ProviderResult:
        if request.extra_args:
            msg = "A provider never receives arbitrary user arguments."
            raise ProviderPolicyError(msg)
        manifest = self._manifests.get(request.provider_id)
        if manifest is None:
            msg = f"Unknown provider {request.provider_id!r}."
            raise ProviderPolicyError(msg)
        if request.capability_id not in manifest.capabilities:
            msg = f"Provider {manifest.provider_id!r} does not expose {request.capability_id!r}."
            raise ProviderPolicyError(msg)
        if request.provider_id == "http-direct":
            return self._http_direct(request, staging)
        argv = self._build_argv(manifest, request, staging)
        before = {path.resolve() for path in staging.rglob("*") if path.is_file()}
        code, stdout, stderr = self._run(argv, staging)
        if self._cancel.is_set():
            self._cancel.clear()
            msg = "Provider execution was cancelled."
            raise CancelledError(msg)
        output = request.typed_inputs.get("output")
        output_path = Path(output) if output else None
        extra_paths: tuple[Path, ...] = ()
        if request.provider_id == "gallery-dl":
            created = [
                path
                for path in staging.rglob("*")
                if path.is_file() and path.resolve() not in before
            ]
            if created:
                extra_paths = tuple(sorted(created, key=lambda path: str(path)))
                output_path = max(created, key=lambda path: path.stat().st_mtime)
        elif output_path is not None:
            extra_paths = (output_path,)
        return ProviderResult(
            exit_code=code,
            stdout=stdout,
            stderr=stderr,
            output_path=output_path,
            argv=tuple(argv),
            output_paths=extra_paths,
        )

    def _http_direct(self, request: ProviderRequest, staging: Path) -> ProviderResult:
        url = request.typed_inputs.get("url")
        if not isinstance(url, str):
            msg = "http-direct requires typed input 'url'."
            raise ProviderPolicyError(msg)
        getter = self._http_get or default_http_get
        status, _headers, body = getter(url)
        output = staging / "source.bin"
        if status >= 400:
            output.write_bytes(body)
            return ProviderResult(status, b"", body, output, argv=("http-get", url))
        output.write_bytes(body)
        return ProviderResult(0, b"", b"", output, argv=("http-get", url), output_paths=(output,))

    def _build_argv(
        self,
        manifest: ProviderManifest,
        request: ProviderRequest,
        staging: Path,
    ) -> list[str]:
        binary = manifest.binary_name
        if not binary:
            msg = f"Provider {manifest.provider_id!r} has no binary."
            raise ProviderPolicyError(msg)
        resolved = self._which(binary)
        if not resolved:
            msg = f"Provider binary {binary!r} is not installed."
            raise ProviderPolicyError(msg)
        inputs = request.typed_inputs
        if manifest.provider_id == "ytdlp":
            return _ytdlp_argv(resolved, inputs, manifest, request.capability_id)
        if manifest.provider_id == "ffmpeg":
            return _ffmpeg_argv(resolved, inputs, request.capability_id)
        if manifest.provider_id == "gallery-dl":
            return _gallery_argv(resolved, inputs, staging)
        if manifest.provider_id == "imagemagick":
            return _magick_argv(resolved, inputs)
        msg = f"No argv builder for {manifest.provider_id!r}."
        raise ProviderPolicyError(msg)


def _ytdlp_argv(
    binary: str,
    inputs: dict[str, Any],
    manifest: ProviderManifest,
    capability_id: str,
) -> list[str]:
    url = inputs.get("url")
    if not isinstance(url, str):
        msg = "yt-dlp requires typed input 'url'."
        raise ProviderPolicyError(msg)
    if capability_id == "discover.manifest":
        argv = [
            binary,
            "--dump-json",
            "--no-playlist",
            "--no-progress",
            "--no-mtime",
            url,
        ]
        for flag in argv[1:-1]:
            if flag.startswith("-") and flag not in manifest.allowed_flags:
                msg = f"Flag {flag!r} is not allowlisted for yt-dlp."
                raise ProviderPolicyError(msg)
        return argv
    output = inputs.get("output")
    if not isinstance(output, str):
        msg = "yt-dlp acquire requires typed inputs 'url' and 'output'."
        raise ProviderPolicyError(msg)
    argv = [
        binary,
        "--no-playlist",
        "--no-progress",
        "--newline",
        "--no-mtime",
        "--restrict-filenames",
        "--output",
        output,
    ]
    format_id = inputs.get("format_id")
    if format_id:
        if not isinstance(format_id, str) or not is_safe_format_id(format_id):
            msg = "yt-dlp format_id must match the allowlisted token pattern."
            raise ProviderPolicyError(msg)
        argv.extend(["--format", format_id])
    cookies = inputs.get("cookies")
    if cookies:
        argv.extend(["--cookies", str(cookies)])
    merge = inputs.get("merge_output_format")
    if merge:
        if merge not in {"mp4", "mkv", "webm", "mov"}:
            msg = "merge_output_format is not allowlisted."
            raise ProviderPolicyError(msg)
        argv.extend(["--merge-output-format", merge])
    for flag in argv[1:]:
        if flag.startswith("-") and flag not in manifest.allowed_flags:
            msg = f"Flag {flag!r} is not allowlisted for yt-dlp."
            raise ProviderPolicyError(msg)
    argv.append(url)
    return argv


def _ffmpeg_argv(binary: str, inputs: dict[str, Any], capability_id: str) -> list[str]:
    source = inputs.get("input")
    output = inputs.get("output")
    if not isinstance(source, str) or not isinstance(output, str):
        msg = "ffmpeg requires typed inputs 'input' and 'output'."
        raise ProviderPolicyError(msg)
    argv = [binary, "-y", "-i", source]
    if capability_id == "process.ffmpeg.remux":
        argv.extend(["-c", "copy", output])
        return argv
    if capability_id == "process.ffmpeg.transcode":
        video_codec = inputs.get("video_codec", "libx264")
        audio_codec = inputs.get("audio_codec", "aac")
        if video_codec not in {"libx264", "libx265", "copy"} or audio_codec not in {
            "aac",
            "copy",
            "libopus",
        }:
            msg = "Transcode codecs are not allowlisted."
            raise ProviderPolicyError(msg)
        argv.extend(["-c:v", video_codec, "-c:a", audio_codec, output])
        return argv
    msg = f"Unsupported ffmpeg capability {capability_id!r}."
    raise ProviderPolicyError(msg)


def _gallery_argv(binary: str, inputs: dict[str, Any], staging: Path) -> list[str]:
    url = inputs.get("url")
    if not isinstance(url, str):
        msg = "gallery-dl requires typed input 'url'."
        raise ProviderPolicyError(msg)
    return [binary, "--no-mtime", "--destination", str(staging), url]


def _magick_argv(binary: str, inputs: dict[str, Any]) -> list[str]:
    source = inputs.get("input")
    output = inputs.get("output")
    if not isinstance(source, str) or not isinstance(output, str):
        msg = "ImageMagick requires typed inputs 'input' and 'output'."
        raise ProviderPolicyError(msg)
    argv = [binary, source, "-auto-orient"]
    container = inputs.get("container")
    if isinstance(container, str) and container.lower() in MAGICK_FORMATS:
        argv.append(f"{MAGICK_FORMATS[container.lower()]}:{output}")
    else:
        argv.append(output)
    return argv


def _terminate_process(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()
