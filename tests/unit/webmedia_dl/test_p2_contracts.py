"""Contracts for AdaptationSet/live polling, typed events, and destination adapters."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from webmedia_dl.destinations import (
    ClipboardLocator,
    FilesAppDestination,
    PhotoKitDestination,
    SecurityScopedBookmark,
    extract_clipboard_locator,
)
from webmedia_dl.domain.enums import DestinationKind, EventType, IntakeKind, Surface
from webmedia_dl.domain.models import EventRecord, ExportIntent
from webmedia_dl.errors import CancelledError, IntakeError, PauseRequested, PublicationError
from webmedia_dl.live import manifest_is_live, record_clear_stream, recordable_segment_urls
from webmedia_dl.providers import ProviderRequest, ProviderRuntime
from webmedia_dl.publish import publish_artifacts
from webmedia_dl.queue import QueueStore


def test_dash_adaptationset_binds_self_closing_representation() -> None:
    text = """
    <MPD>
      <Period>
        <AdaptationSet>
          <BaseURL>https://cdn.example.com/as/</BaseURL>
          <SegmentTemplate media="$RepresentationID$/seg$Number$.m4s" startNumber="1"/>
          <Representation id="v1" bandwidth="800000"/>
        </AdaptationSet>
      </Period>
    </MPD>
    """
    urls = recordable_segment_urls(text, "https://cdn.example.com/manifest.mpd")
    assert urls == ["https://cdn.example.com/as/v1/seg1.m4s"]


def test_dynamic_mpd_polls_new_segments(tmp_path: Path) -> None:
    first = (
        '<MPD type="dynamic"><Period>'
        '<SegmentTemplate media="seg$Number$.m4s" startNumber="1"/>'
        "</Period></MPD>"
    )
    second = (
        '<MPD type="dynamic"><Period>'
        '<SegmentTemplate media="seg$Number$.m4s" startNumber="2"/>'
        "</Period></MPD>"
    )
    playlists = [second]
    bodies = {
        "https://cdn.example.com/seg1.m4s": b"ONE",
        "https://cdn.example.com/seg2.m4s": b"TWO",
    }

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("live.mpd"):
            payload = playlists.pop(0) if playlists else second
            return 200, "application/dash+xml", payload.encode()
        return 200, "video/mp4", bodies[url]

    assert manifest_is_live(first) is True
    output = tmp_path / "live.bin"
    record_clear_stream(
        first,
        "https://cdn.example.com/live.mpd",
        output,
        fetch,
        live_polls=2,
    )
    assert output.read_bytes() == b"ONETWO"


def test_hls_live_poll_appends_new_segments(tmp_path: Path) -> None:
    first = "#EXTM3U\n#EXTINF:1,\nseg1.ts\n"
    second = "#EXTM3U\n#EXTINF:1,\nseg1.ts\n#EXTINF:1,\nseg2.ts\n"
    state = {"playlist": first}

    def fetch(url: str) -> tuple[int, str, bytes]:
        if url.endswith("index.m3u8"):
            return 200, "application/vnd.apple.mpegurl", state["playlist"].encode()
        if url.endswith("seg1.ts"):
            state["playlist"] = second
            return 200, "video/MP2T", b"A"
        return 200, "video/MP2T", b"B"

    output = tmp_path / "live.ts"
    record_clear_stream(
        first,
        "https://cdn.example.com/live/index.m3u8",
        output,
        fetch,
        live_polls=2,
    )
    assert output.read_bytes() == b"AB"


def test_event_payload_rejects_provider_console() -> None:
    with pytest.raises(ValidationError, match="stdout"):
        EventRecord(
            job_id=uuid4(),
            type=EventType.OPERATION_COMPLETED,
            sequence=1,
            payload={"stdout": "ffmpeg"},
        )


def test_queue_emit_rejects_argv(tmp_path: Path) -> None:
    queue = QueueStore(tmp_path / "queue")
    with pytest.raises(ValueError, match="argv"):
        queue.emit(uuid4(), EventType.JOB_COMPLETED, {"argv": ["yt-dlp"]})


def test_clipboard_locator_extracts_url() -> None:
    clip = ClipboardLocator(text="watch https://cdn.example.com/a.mp4 thanks")
    assert clip.locator() == "https://cdn.example.com/a.mp4"
    source = clip.as_source(surface=Surface.MACOS, policy_profile_id="personal-full")
    assert source.kind is IntakeKind.PASTE
    assert source.local_path is None
    assert source.normalized_url == "https://cdn.example.com/a.mp4"
    with pytest.raises(IntakeError):
        extract_clipboard_locator("no url here")


def test_files_bookmark_and_photokit(tmp_path: Path) -> None:
    dest = tmp_path / "Movies"
    dest.mkdir()
    bookmark = SecurityScopedBookmark(resolved_path=str(dest))
    assert bookmark.allows(str(dest / "clip.mp4"))
    assert not bookmark.allows(str(tmp_path / "Movies-backup" / "clip.mp4"))
    intent = FilesAppDestination(bookmark=bookmark).as_intent()
    assert intent.destination_kind is DestinationKind.FILES_APP
    assert intent.security_scoped_path == str(dest.resolve())
    photos = PhotoKitDestination(approved_root=str(dest))
    assert photos.can_publish is False
    with pytest.raises(PublicationError, match="Photos"):
        photos.assert_publishable()
    outside = tmp_path / "escape"
    outside.mkdir()
    with pytest.raises(Exception, match="outside user-approved"):
        publish_artifacts(
            [],
            ExportIntent(
                destination_kind=DestinationKind.FILES_APP,
                destination_path=str(outside),
                approved_roots=[str(outside)],
                security_scoped_path=str(dest),
            ),
        )


def test_http_direct_cancel_discards_completed_fetch(tmp_path: Path, png_bytes: bytes) -> None:
    runtime = ProviderRuntime()

    def getter(_url: str) -> tuple[int, dict[str, str], bytes]:
        runtime.cancel_running()
        return 200, {"content-type": "image/png"}, png_bytes

    runtime._http_get = getter
    with pytest.raises(CancelledError):
        runtime.execute(
            ProviderRequest(
                provider_id="http-direct",
                capability_id="acquire.http",
                typed_inputs={"url": "https://cdn.example.com/hero.png"},
            ),
            tmp_path,
        )
    assert list(tmp_path.glob("*.png")) == []


def test_http_direct_pause_keeps_completed_fetch(tmp_path: Path, png_bytes: bytes) -> None:
    runtime = ProviderRuntime()

    def getter(_url: str) -> tuple[int, dict[str, str], bytes]:
        runtime.pause_running()
        return 200, {"content-type": "image/png"}, png_bytes

    runtime._http_get = getter
    result = runtime.execute(
        ProviderRequest(
            provider_id="http-direct",
            capability_id="acquire.http",
            typed_inputs={"url": "https://cdn.example.com/hero.png"},
        ),
        tmp_path,
    )
    assert result.output_path is not None
    assert result.output_path.exists()
    with pytest.raises(PauseRequested):
        runtime.execute(
            ProviderRequest(
                provider_id="http-direct",
                capability_id="acquire.http",
                typed_inputs={"url": "https://cdn.example.com/hero2.png"},
            ),
            tmp_path,
        )
