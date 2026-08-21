"""Provider manifests and bounded execution. No public behavior contracts leak to argv."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from webmedia_dl.domain.models import PolicyProfile, ProviderManifest
from webmedia_dl.errors import (
    CancelledError,
    CookiePolicyError,
    PauseRequested,
    ProviderPolicyError,
)
from webmedia_dl.fetch import bound_fetch
from webmedia_dl.identity import is_safe_format_id
from webmedia_dl.paths import runtime_file
from webmedia_dl.policy.profiles import get_profile
from webmedia_dl.security import CookieGrantLedger

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


HTTP_CONTENT_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
    "video/mp4": ".mp4",
    "video/webm": ".webm",
    "application/pdf": ".pdf",
    "text/vtt": ".vtt",
    "application/vnd.apple.mpegurl": ".m3u8",
    "application/dash+xml": ".mpd",
}


def imagemagick_configure_path() -> Path:
    return runtime_file("imagemagick-runtime")


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
    url: str,
    *,
    profile: PolicyProfile | None = None,
    should_stop: Callable[[], None] | None = None,
) -> tuple[int, dict[str, str], bytes]:
    policy = profile or get_profile("personal-full")
    status, content_type, body = bound_fetch(
        url,
        profile=policy,
        max_bytes=policy.max_download_bytes,
        on_overflow="error",
        should_stop=should_stop,
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
    job_id: UUID | str | None = None


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
        cookie_ledger: CookieGrantLedger | None = None,
    ) -> None:
        self._manifests = builtin_manifests()
        self._which = which or shutil.which
        self._run = run if run is not None else self._tracked_run
        self._http_get = http_get
        self.cookie_ledger = cookie_ledger or CookieGrantLedger()
        self._lock = threading.Lock()
        self._procs: dict[str, list[subprocess.Popen[bytes]]] = defaultdict(list)
        self._cancels: dict[str, threading.Event] = {}
        self._pauses: dict[str, threading.Event] = {}
        self._tls = threading.local()

    def _job_key(self, job_id: UUID | str | None) -> str:
        return str(job_id) if job_id is not None else "_"

    def _cancel_event(self, key: str) -> threading.Event:
        with self._lock:
            return self._cancels.setdefault(key, threading.Event())

    def _pause_event(self, key: str) -> threading.Event:
        with self._lock:
            return self._pauses.setdefault(key, threading.Event())

    def cancel_running(self, job_id: UUID | str | None = None) -> None:
        self._signal_running(job_id, pause=False)

    def pause_running(self, job_id: UUID | str | None = None) -> None:
        self._signal_running(job_id, pause=True)

    def clear_stop_flags(self, job_id: UUID | str | None = None) -> None:
        with self._lock:
            keys = (
                set(self._cancels) | set(self._pauses)
                if job_id is None
                else {self._job_key(job_id)}
            )
            for key in keys:
                if key in self._cancels:
                    self._cancels[key].clear()
                if key in self._pauses:
                    self._pauses[key].clear()

    def _signal_running(self, job_id: UUID | str | None, *, pause: bool) -> None:
        with self._lock:
            if job_id is None:
                keys = set(self._procs) | set(self._cancels) | set(self._pauses) | {"_"}
            else:
                keys = {self._job_key(job_id)}
            events = self._pauses if pause else self._cancels
            procs: list[subprocess.Popen[bytes]] = []
            for key in keys:
                events.setdefault(key, threading.Event()).set()
                procs.extend(list(self._procs.get(key, [])))
        for proc in procs:
            _terminate_process(proc)

    def _raise_if_stopped(self, key: str) -> None:
        if self._cancel_event(key).is_set():
            self._cancel_event(key).clear()
            msg = "Provider execution was cancelled."
            raise CancelledError(msg)
        if self._pause_event(key).is_set():
            self._pause_event(key).clear()
            msg = "Provider execution was paused."
            raise PauseRequested(msg)

    def _tracked_run(self, argv: list[str], staging: Path) -> tuple[int, bytes, bytes]:
        key = getattr(self._tls, "job_key", "_")
        self._raise_if_stopped(key)
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
            self._procs[key].append(proc)
        try:
            deadline = 600.0
            waited = 0.0
            while True:
                try:
                    stdout, stderr = proc.communicate(timeout=0.2)
                    return proc.returncode or 0, stdout, stderr
                except subprocess.TimeoutExpired:
                    waited += 0.2
                    if self._cancel_event(key).is_set() or self._pause_event(key).is_set():
                        _terminate_process(proc)
                        stdout, stderr = proc.communicate()
                        return proc.returncode or 130, stdout, stderr
                    if waited >= deadline:
                        _terminate_process(proc)
                        stdout, stderr = proc.communicate()
                        return proc.returncode or 124, stdout, stderr
        finally:
            with self._lock:
                if proc in self._procs.get(key, []):
                    self._procs[key].remove(proc)

    def health(self, provider_id: str) -> str:
        manifest = self._manifests[provider_id]
        if manifest.binary_name is None:
            return "healthy"
        return "healthy" if self._which(manifest.binary_name) else "missing"

    def execute(self, request: ProviderRequest, staging: Path) -> ProviderResult:
        key = self._job_key(request.job_id)
        self._raise_if_stopped(key)
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
        previous = getattr(self._tls, "job_key", "_")
        self._tls.job_key = key
        try:
            if request.provider_id == "http-direct":
                return self._http_direct(request, staging)
            argv = self._build_argv(manifest, request, staging)
            before = {path.resolve() for path in staging.rglob("*") if path.is_file()}
            code, stdout, stderr = self._run(argv, staging)
            self._raise_if_stopped(key)
            output = request.typed_inputs.get("output")
            output_path = Path(output) if output else None
            extra_paths: tuple[Path, ...] = ()
            created = [
                path
                for path in staging.rglob("*")
                if path.is_file() and path.resolve() not in before
            ]
            if request.provider_id in {"gallery-dl", "ytdlp"} and created:
                extra_paths = tuple(sorted(created, key=lambda path: str(path)))
                output_path = max(created, key=lambda path: path.stat().st_mtime)
            elif output_path is not None:
                if "%(ext)s" in str(output_path):
                    stem = Path(str(output).replace("%(ext)s", "")).stem
                    matches = [path for path in created if path.stem == stem]
                    if matches:
                        output_path = matches[0]
                    elif created:
                        output_path = created[0]
                extra_paths = (output_path,) if output_path.exists() else tuple(created)
            return ProviderResult(
                exit_code=code,
                stdout=stdout,
                stderr=stderr,
                output_path=output_path,
                argv=tuple(argv),
                output_paths=extra_paths,
            )
        finally:
            self._tls.job_key = previous

    def _http_direct(self, request: ProviderRequest, staging: Path) -> ProviderResult:
        url = request.typed_inputs.get("url")
        if not isinstance(url, str):
            msg = "http-direct requires typed input 'url'."
            raise ProviderPolicyError(msg)
        key = self._job_key(request.job_id)
        self._raise_if_stopped(key)
        getter = self._http_get
        if getter is None:
            status, headers, body = default_http_get(
                url, should_stop=lambda: self._raise_if_stopped(key)
            )
        else:
            status, headers, body = getter(url)
        if self._cancel_event(key).is_set():
            self._raise_if_stopped(key)
        requested = request.typed_inputs.get("output")
        base = Path(requested) if isinstance(requested, str) else staging / "source.bin"
        output = base.with_suffix(_http_suffix(url, headers, body))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(body)
        if status >= 400:
            return ProviderResult(status, b"", body, output, argv=("http-get", url))
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
            return _ytdlp_argv(
                resolved,
                inputs,
                manifest,
                request.capability_id,
                job_id=request.job_id,
                ledger=self.cookie_ledger,
                profile_id=getattr(self._tls, "profile_id", None),
            )
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
    *,
    job_id: UUID | str | None = None,
    ledger: CookieGrantLedger | None = None,
    profile_id: str | None = None,
) -> list[str]:
    url = inputs.get("url")
    if not isinstance(url, str):
        msg = "yt-dlp requires typed input 'url'."
        raise ProviderPolicyError(msg)
    cookie_flags = _cookie_argv_flags(
        inputs,
        job_id=job_id,
        ledger=ledger,
        profile_id=profile_id,
    )
    if capability_id == "discover.manifest":
        argv = [
            binary,
            "--dump-json",
            "--no-playlist",
            "--no-progress",
            "--no-mtime",
            *cookie_flags,
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
        _ytdlp_output_template(output),
    ]
    format_id = inputs.get("format_id")
    if format_id:
        if not isinstance(format_id, str) or not is_safe_format_id(format_id):
            msg = "yt-dlp format_id must match the allowlisted token pattern."
            raise ProviderPolicyError(msg)
        argv.extend(["--format", format_id])
    argv.extend(cookie_flags)
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


def _cookie_argv_flags(
    inputs: dict[str, Any],
    *,
    job_id: UUID | str | None,
    ledger: CookieGrantLedger | None,
    profile_id: str | None,
) -> list[str]:
    if inputs.get("cookies"):
        msg = "Raw cookie paths are not accepted; issue a job-bound cookie grant."
        raise CookiePolicyError(msg)
    grant_id = inputs.get("cookie_grant_id")
    if not grant_id:
        return []
    if ledger is None:
        msg = "Cookie grant ledger is unavailable."
        raise CookiePolicyError(msg)
    cookie_path = ledger.resolve(
        str(grant_id),
        job_id=job_id,
        profile_id=profile_id,
    )
    return ["--cookies", str(cookie_path)]


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


def _ytdlp_output_template(output: str) -> str:
    path = Path(output)
    if path.suffix.lower() in {"", ".bin"}:
        return str(path.with_name(f"{path.stem or 'download'}.%(ext)s"))
    return output


def _http_suffix(url: str, headers: dict[str, str], body: bytes) -> str:
    content_type = ""
    for key, value in headers.items():
        if key.lower() == "content-type":
            content_type = value.split(";")[0].strip().lower()
            break
    if content_type in HTTP_CONTENT_TYPES:
        return HTTP_CONTENT_TYPES[content_type]
    path = urlparse(url).path.lower()
    for ext in (
        ".mp4",
        ".webm",
        ".mkv",
        ".mov",
        ".m4v",
        ".mp3",
        ".m4a",
        ".aac",
        ".flac",
        ".wav",
        ".ogg",
        ".opus",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".avif",
        ".pdf",
        ".vtt",
        ".srt",
        ".m3u8",
        ".mpd",
    ):
        if path.endswith(ext):
            return ".jpg" if ext == ".jpeg" else ext
    if body.startswith(b"\x89PNG"):
        return ".png"
    if body.startswith(b"\xff\xd8"):
        return ".jpg"
    return ".bin"


def _terminate_process(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()
        return
    try:
        proc.wait(timeout=2)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()
