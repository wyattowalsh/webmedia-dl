"""Media probe. Records executed stream facts; never a simulated PASS."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from uuid import UUID, uuid4

from webmedia_dl.domain.enums import MediaKind
from webmedia_dl.domain.models import MediaProbe, StreamInfo


def probe_media(path: Path, *, candidate_id: UUID | None = None) -> MediaProbe | None:
    binary = shutil.which("ffprobe")
    if binary is None:
        return None
    completed = subprocess.run(
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
    if completed.returncode != 0:
        return None
    try:
        payload = json.loads(completed.stdout.decode() or "{}")
    except json.JSONDecodeError:
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
                index=int(item.get("index") or 0),
                codec=item.get("codec_name"),
                media_kind=kind,
                width=item.get("width"),
                height=item.get("height"),
                sample_rate=int(item["sample_rate"])
                if str(item.get("sample_rate") or "").isdigit()
                else None,
                channels=item.get("channels"),
                encrypted=bool(item.get("tags", {}).get("ENCRYPTED")),
            )
        )
    fmt = payload.get("format") or {}
    duration = fmt.get("duration")
    duration_ms = int(float(duration) * 1000) if duration else None
    return MediaProbe(
        probe_id=uuid4(),
        candidate_id=candidate_id or uuid4(),
        duration_ms=duration_ms,
        streams=streams,
        container=Path(str(fmt.get("format_name") or path.suffix.lstrip(".") or "")).name or None,
    )
