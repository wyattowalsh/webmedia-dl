"""Media probe. Records executed stream facts; never a simulated PASS."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from uuid import UUID, uuid4

from webmedia_dl.domain.enums import MediaKind
from webmedia_dl.domain.models import MediaProbe, StreamInfo


def probe_media(
    path: Path,
    *,
    candidate_id: UUID | None = None,
    which: Callable[[str], str | None] | None = None,
    runner: Callable[..., object] | None = None,
) -> MediaProbe | None:
    locate = which or shutil.which
    binary = locate("ffprobe")
    if binary is None:
        return None
    run = runner or subprocess.run
    try:
        completed = run(
            [
                binary,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if getattr(completed, "returncode", 1) != 0:
        return None
    try:
        raw = getattr(completed, "stdout", None)
        if raw in (None, b"", ""):
            raw = "{}"
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        payload = json.loads(raw)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    streams: list[StreamInfo] = []
    for item in payload.get("streams") or []:
        codec_type = str(item.get("codec_type") or "unknown")
        kind = {
            "video": MediaKind.VIDEO,
            "audio": MediaKind.AUDIO,
            "subtitle": MediaKind.SUBTITLE,
        }.get(codec_type, MediaKind.UNKNOWN)
        streams.append(
            StreamInfo(
                index=_as_int(item.get("index")) or 0,
                codec=item.get("codec_name"),
                media_kind=kind,
                width=_as_int(item.get("width")),
                height=_as_int(item.get("height")),
                sample_rate=_as_int(item.get("sample_rate")),
                channels=_as_int(item.get("channels")),
                encrypted=_stream_is_encrypted(item),
            )
        )
    fmt = payload.get("format") or {}
    duration = fmt.get("duration")
    try:
        duration_ms = int(float(duration) * 1000) if duration not in (None, "") else None
    except (TypeError, ValueError):
        duration_ms = None
    names = str(fmt.get("format_name") or "").strip()
    container = names.split(",")[0].strip() or None
    return MediaProbe(
        probe_id=uuid4(),
        candidate_id=candidate_id or uuid4(),
        duration_ms=duration_ms,
        streams=streams,
        container=container,
        format_names=names.strip() or None,
    )


def _truthy_flag(value: object) -> bool:
    if value is None or value is False:
        return False
    if value is True:
        return True
    text = str(value).strip().lower()
    return text in {"1", "true", "yes", "on"}


def _stream_is_encrypted(item: dict) -> bool:
    if _truthy_flag(item.get("encrypted")):
        return True
    tags = item.get("tags") or {}
    if not isinstance(tags, dict):
        return False
    for key in ("ENCRYPTED", "encrypted", "ENCRYPTION", "encryption"):
        if _truthy_flag(tags.get(key)):
            return True
    return False


def _as_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    text = str(value).strip()
    try:
        return int(text)
    except ValueError:
        try:
            return int(float(text))
        except ValueError:
            return None
