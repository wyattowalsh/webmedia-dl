import json
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

import pytest

from webmedia_dl.artifacts import ArtifactStore
from webmedia_dl.domain.enums import ArtifactRole, IntakeKind, JobState, MediaKind, Surface
from webmedia_dl.domain.models import Artifact, ExportPlan, Job, MediaProbe, MediaSource, Operation
from webmedia_dl.errors import DiscoveryError, PauseRequested, ProviderPolicyError
from webmedia_dl.intake import normalize_source
from webmedia_dl.live import (
    MAX_TIMELINE_SEGMENTS,
    ManifestPart,
    record_clear_stream,
    recordable_parts,
    recordable_segment_urls,
)
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.probe import probe_media
from webmedia_dl.processing import execute_export_plan, ordered_operations
from webmedia_dl.providers import ProviderRuntime
from webmedia_dl.queue import QueueStore
from webmedia_dl.validation import validate_artifact, validate_probe


def _job(queue: QueueStore, src: Path) -> Job:
    job = Job(
        source=MediaSource(
            kind=IntakeKind.FILE,
            locator=str(src),
            local_path=str(src),
            surface="cli",
            policy_profile_id="personal-full",
        ),
        policy_profile_id="personal-full",
        worker_id="local-macos",
    )
    queue.put_job(job)
    return job


def test_probe_parses_ffprobe_json(monkeypatch, tmp_path: Path) -> None:
    media = tmp_path / "clip.bin"
    media.write_bytes(b"bytes")
    payload = {
        "streams": [
            {
                "index": 0,
                "codec_type": "video",
                "codec_name": "h264",
                "width": 16,
                "height": 16,
                "tags": {"ENCRYPTED": "0"},
            },
            {
                "index": 1,
                "codec_type": "audio",
                "codec_name": "aac",
                "sample_rate": "48000",
                "channels": 2,
            },
            {"index": 2, "codec_type": "subtitle", "codec_name": "webvtt"},
            {"index": 3, "codec_type": "data"},
        ],
        "format": {"duration": "1.5", "format_name": "mov,mp4,m4a"},
    }

    monkeypatch.setattr("webmedia_dl.probe.shutil.which", lambda _name: "/usr/bin/ffprobe")

    class Result:
        returncode = 0
        stdout = json.dumps(payload).encode()

    monkeypatch.setattr("webmedia_dl.probe.subprocess.run", lambda *_args, **_kwargs: Result())
    probe = probe_media(media)
    assert probe is not None
    assert probe.duration_ms == 1500
    assert len(probe.streams) == 4
    assert probe.streams[1].sample_rate == 48000
    results = validate_probe(
        uuid4(),
        Artifact(
            artifact_id="sha256:ab",
            role=ArtifactRole.SOURCE,
            sha256="ab",
            byte_size=1,
            media_kind=MediaKind.VIDEO,
            storage_relpath="a.bin",
        ),
        probe,
    )
    assert results[0].status.value == "PASS"


def test_probe_missing_binary_and_invalid_json(monkeypatch, tmp_path: Path) -> None:
    media = tmp_path / "clip.bin"
    media.write_bytes(b"x")
    monkeypatch.setattr("webmedia_dl.probe.shutil.which", lambda _name: None)
    assert probe_media(media) is None
    monkeypatch.setattr("webmedia_dl.probe.shutil.which", lambda _name: "/usr/bin/ffprobe")

    class Bad:
        returncode = 0
        stdout = b"not-json"

    monkeypatch.setattr("webmedia_dl.probe.subprocess.run", lambda *_args, **_kwargs: Bad())
    assert probe_media(media) is None
    blocked = validate_probe(
        uuid4(),
        Artifact(
            artifact_id="sha256:ab",
            role=ArtifactRole.SOURCE,
            sha256="ab",
            byte_size=1,
            media_kind=MediaKind.VIDEO,
            storage_relpath="a.bin",
        ),
        None,
    )
    assert blocked[0].status.value == "BLOCKED"
    warn = validate_probe(
        uuid4(),
        Artifact(
            artifact_id="sha256:ab",
            role=ArtifactRole.SOURCE,
            sha256="ab",
            byte_size=1,
            media_kind=MediaKind.VIDEO,
            storage_relpath="a.bin",
        ),
        MediaProbe(probe_id=uuid4(), candidate_id=uuid4(), streams=[]),
    )
    assert warn[0].status.value == "WARN"


def test_validate_artifact_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "gone.bin"
    artifact = Artifact(
        artifact_id="sha256:ab",
        role=ArtifactRole.SOURCE,
        sha256="ab",
        byte_size=1,
        media_kind=MediaKind.UNKNOWN,
        storage_relpath="gone.bin",
    )
    results = validate_artifact(uuid4(), artifact, missing)
    assert results[0].gate_id == "exists"
    assert results[0].status.value == "FAIL"


def test_hls_map_and_byterange(tmp_path: Path) -> None:
    playlist = (
        "#EXTM3U\n"
        '#EXT-X-MAP:URI="init.mp4",BYTERANGE="4@0"\n'
        "#EXT-X-BYTERANGE:3@0\n"
        "seg.ts\n"
        "#EXT-X-BYTERANGE:3@3\n"
        "seg.ts\n"
        '#EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key"\n'
        "secret.ts\n"
    )
    urls = recordable_segment_urls(playlist, "https://cdn.example.com/live/index.m3u8")
    assert urls[0] == "https://cdn.example.com/live/init.mp4"
    assert "secret.ts" not in "".join(urls)
    bodies = {
        "https://cdn.example.com/live/init.mp4": b"INITXXXX",
        "https://cdn.example.com/live/seg.ts": b"ABCDEF",
    }

    def fetch(url: str) -> tuple[int, str, bytes]:
        if "key" in url or url.endswith("secret.ts"):
            raise AssertionError(url)
        return 200, "video/mp4", bodies[url]

    output = tmp_path / "live.bin"
    record_clear_stream(playlist, "https://cdn.example.com/live/index.m3u8", output, fetch)
    assert output.read_bytes() == b"INITABCDEF"
    spaced = (
        "#EXTM3U\n"
        '#EXT-X-MAP:URI="init.mp4",BYTERANGE="4 @ 0"\n'
        "#EXT-X-BYTERANGE: 3@0\n"
        "seg.ts\n"
        "#EXT-X-BYTERANGE:3 @ 3\n"
        "seg.ts\n"
    )
    spaced_out = tmp_path / "live-spaces.bin"
    record_clear_stream(spaced, "https://cdn.example.com/live/index.m3u8", spaced_out, fetch)
    assert spaced_out.read_bytes() == b"INITABCDEF"
    parts_only = (
        "#EXTM3U\n"
        '#EXT-X-MAP:URI="init.mp4",BYTERANGE="4@0"\n'
        "#EXTINF:1.0,\n"
        '#EXT-X-PART:DURATION=0.5,URI="p0.m4s"\n'
        '#EXT-X-PART:DURATION=0.5,URI="p1.m4s"\n'
        '#EXT-X-PART:DURATION=0.5,GAP=YES,URI="gap.m4s"\n'
        '#EXT-X-PRELOAD-HINT:TYPE=PART,URI="hint.m4s"\n'
    )
    part_bodies = {
        "https://cdn.example.com/live/init.mp4": b"INITXXXX",
        "https://cdn.example.com/live/p0.m4s": b"AA",
        "https://cdn.example.com/live/p1.m4s": b"BB",
    }

    def fetch_parts(url: str) -> tuple[int, str, bytes]:
        if url.endswith("gap.m4s") or url.endswith("hint.m4s"):
            raise AssertionError(url)
        return 200, "video/mp4", part_bodies[url]

    part_out = tmp_path / "live-parts.bin"
    record_clear_stream(
        parts_only, "https://cdn.example.com/live/index.m3u8", part_out, fetch_parts
    )
    assert part_out.read_bytes() == b"INITAABB"
    completed = (
        "#EXTM3U\n"
        '#EXT-X-MAP:URI="init.mp4",BYTERANGE="4@0"\n'
        "#EXTINF:1.0,\n"
        '#EXT-X-PART:DURATION=0.5,URI="p0.m4s"\n'
        '#EXT-X-PART:DURATION=0.5,URI="p1.m4s"\n'
        "seg.ts\n"
    )

    def fetch_completed(url: str) -> tuple[int, str, bytes]:
        if url.endswith("p0.m4s") or url.endswith("p1.m4s"):
            raise AssertionError(url)
        return 200, "video/mp4", bodies[url]

    completed_out = tmp_path / "live-completed.bin"
    record_clear_stream(
        completed, "https://cdn.example.com/live/index.m3u8", completed_out, fetch_completed
    )
    assert completed_out.read_bytes() == b"INITABCDEF"
    inf_after_parts = (
        "#EXTM3U\n"
        '#EXT-X-MAP:URI="init.mp4",BYTERANGE="4@0"\n'
        '#EXT-X-PART:DURATION=0.5,URI="p0.m4s"\n'
        '#EXT-X-PART:DURATION=0.5,URI="p1.m4s"\n'
        "#EXTINF:1.0,\n"
        "seg.ts\n"
    )
    inf_out = tmp_path / "live-inf.bin"
    record_clear_stream(
        inf_after_parts, "https://cdn.example.com/live/index.m3u8", inf_out, fetch_completed
    )
    assert inf_out.read_bytes() == b"INITABCDEF"
    inf_names = [
        part.url.rsplit("/", 1)[-1]
        for part in recordable_parts(inf_after_parts, "https://cdn.example.com/live/index.m3u8")
    ]
    assert inf_names == ["init.mp4", "seg.ts"]
    gapped_parts = (
        "#EXTM3U\n"
        '#EXT-X-MAP:URI="init.mp4",BYTERANGE="4@0"\n'
        '#EXT-X-PART:DURATION=0.5,URI="p0.m4s"\n'
        "#EXT-X-GAP\n"
        "#EXT-X-BYTERANGE:3@0\n"
        "gap.ts\n"
        "#EXTINF:1.0,\n"
        "seg.ts\n"
    )

    def fetch_gapped_parts(url: str) -> tuple[int, str, bytes]:
        if url.endswith("p0.m4s") or url.endswith("gap.ts"):
            raise AssertionError(url)
        return 200, "video/mp4", bodies[url]

    gapped_out = tmp_path / "live-gap.bin"
    record_clear_stream(
        gapped_parts,
        "https://cdn.example.com/live/index.m3u8",
        gapped_out,
        fetch_gapped_parts,
    )
    assert gapped_out.read_bytes() == b"INITABCDEF"
    defined_map = (
        "#EXTM3U\n"
        '#EXT-X-DEFINE:NAME="init",VALUE="init.mp4"\n'
        '#EXT-X-DEFINE:NAME="part",VALUE="p0.m4s"\n'
        '#EXT-X-MAP:URI="{$init}",BYTERANGE="4@0"\n'
        '#EXT-X-PART:DURATION=0.5,URI="{$part}"\n'
        '#EXT-X-PART:DURATION=0.5,URI="p1.m4s"\n'
    )
    defined_out = tmp_path / "live-define.bin"
    record_clear_stream(
        defined_map, "https://cdn.example.com/live/index.m3u8", defined_out, fetch_parts
    )
    assert defined_out.read_bytes() == b"INITAABB"
    leftover_map = '#EXTM3U\n#EXT-X-MAP:URI="{$missing}"\n#EXTINF:1.0,\nseg.ts\n'
    leftover_out = tmp_path / "live-leftover-map.bin"
    record_clear_stream(
        leftover_map, "https://cdn.example.com/live/index.m3u8", leftover_out, fetch_completed
    )
    assert leftover_out.read_bytes() == b"ABCDEF"
    leftover_part = (
        "#EXTM3U\n"
        '#EXT-X-MAP:URI="init.mp4",BYTERANGE="4@0"\n'
        '#EXT-X-PART:DURATION=0.5,URI="{$missing}"\n'
        '#EXT-X-PART:DURATION=0.5,URI="p1.m4s"\n'
    )
    leftover_part_out = tmp_path / "live-leftover-part.bin"
    record_clear_stream(
        leftover_part, "https://cdn.example.com/live/index.m3u8", leftover_part_out, fetch_parts
    )
    assert leftover_part_out.read_bytes() == b"INITBB"


def test_dash_segment_timeline(tmp_path: Path) -> None:
    text = """
    <MPD>
      <Period>
        <SegmentTemplate timescale="90000" initialization="init.mp4"
          media="chunk_$Number$.m4s" startNumber="1">
          <SegmentTimeline>
            <S t="0" d="90000" r="2"/>
          </SegmentTimeline>
        </SegmentTemplate>
      </Period>
    </MPD>
    """
    urls = recordable_segment_urls(text, "https://cdn.example.com/dash/")
    assert urls[0] == "https://cdn.example.com/dash/init.mp4"
    assert "https://cdn.example.com/dash/chunk_1.m4s" in urls
    assert "https://cdn.example.com/dash/chunk_3.m4s" in urls
    numbered = """
    <MPD>
      <Period>
        <SegmentTemplate timescale="90000" initialization="init.mp4"
          media="chunk_$Number$.m4s" startNumber="1">
          <SegmentTimeline>
            <S t="0" d="90000" r="1" n="10"/>
          </SegmentTimeline>
        </SegmentTemplate>
      </Period>
    </MPD>
    """
    numbered_urls = recordable_segment_urls(numbered, "https://cdn.example.com/dash/")
    assert numbered_urls == [
        "https://cdn.example.com/dash/init.mp4",
        "https://cdn.example.com/dash/chunk_10.m4s",
        "https://cdn.example.com/dash/chunk_11.m4s",
    ]
    numbered_blob = {"init.mp4": b"INIT", "chunk_10.m4s": b"A", "chunk_11.m4s": b"B"}

    def fetch_numbered(url: str) -> tuple[int, str, bytes]:
        name = url.rsplit("/", 1)[-1]
        if name not in numbered_blob:
            raise AssertionError(url)
        return 200, "video/mp4", numbered_blob[name]

    numbered_out = tmp_path / "dash-n.bin"
    record_clear_stream(
        numbered, "https://cdn.example.com/dash/manifest.mpd", numbered_out, fetch_numbered
    )
    assert numbered_out.read_bytes() == b"INITAB"
    subnumbered = """
    <MPD>
      <Period>
        <SegmentTemplate timescale="90000" initialization="init.mp4"
          media="chunk_$Number$_$SubNumber$.m4s" startNumber="1">
          <SegmentTimeline>
            <S t="0" d="90000" k="2"/>
            <S d="90000" n="5" k="2"/>
          </SegmentTimeline>
        </SegmentTemplate>
      </Period>
    </MPD>
    """
    sub_urls = recordable_segment_urls(subnumbered, "https://cdn.example.com/dash/")
    assert sub_urls == [
        "https://cdn.example.com/dash/init.mp4",
        "https://cdn.example.com/dash/chunk_1_1.m4s",
        "https://cdn.example.com/dash/chunk_1_2.m4s",
        "https://cdn.example.com/dash/chunk_5_1.m4s",
        "https://cdn.example.com/dash/chunk_5_2.m4s",
    ]
    padded = """
    <MPD>
      <Period>
        <SegmentTemplate initialization="init.mp4"
          media="s$Number$_$SubNumber%02d$.m4s" startNumber="1">
          <SegmentTimeline>
            <S t="0" d="1" k="2"/>
          </SegmentTimeline>
        </SegmentTemplate>
      </Period>
    </MPD>
    """
    assert recordable_segment_urls(padded, "https://cdn.example.com/dash/") == [
        "https://cdn.example.com/dash/init.mp4",
        "https://cdn.example.com/dash/s1_01.m4s",
        "https://cdn.example.com/dash/s1_02.m4s",
    ]
    leftover_sub = """
    <MPD>
      <Period>
        <SegmentTemplate initialization="init.mp4"
          media="s$Number$_$SubNumber$.m4s" startNumber="1">
          <SegmentTimeline>
            <S t="0" d="90000" r="1"/>
          </SegmentTimeline>
        </SegmentTemplate>
      </Period>
    </MPD>
    """
    assert recordable_segment_urls(leftover_sub, "https://cdn.example.com/dash/") == [
        "https://cdn.example.com/dash/init.mp4",
    ]
    capped = """
    <MPD>
      <Period>
        <SegmentTemplate initialization="init.mp4"
          media="c$Number$_$SubNumber$.m4s" startNumber="1">
          <SegmentTimeline>
            <S t="0" d="1" k="80"/>
            <S d="1" k="2"/>
          </SegmentTimeline>
        </SegmentTemplate>
      </Period>
    </MPD>
    """
    capped_urls = recordable_segment_urls(capped, "https://cdn.example.com/dash/")
    assert capped_urls[0] == "https://cdn.example.com/dash/init.mp4"
    assert len(capped_urls) == 1 + MAX_TIMELINE_SEGMENTS
    assert capped_urls[-1] == "https://cdn.example.com/dash/c1_64.m4s"
    assert all("c2_" not in url for url in capped_urls)
    sub_blob = {
        "init.mp4": b"INIT",
        "chunk_1_1.m4s": b"A",
        "chunk_1_2.m4s": b"B",
        "chunk_5_1.m4s": b"C",
        "chunk_5_2.m4s": b"D",
    }

    def fetch_sub(url: str) -> tuple[int, str, bytes]:
        name = url.rsplit("/", 1)[-1]
        if name not in sub_blob:
            raise AssertionError(url)
        return 200, "video/mp4", sub_blob[name]

    sub_out = tmp_path / "dash-sub.bin"
    record_clear_stream(
        subnumbered, "https://cdn.example.com/dash/manifest.mpd", sub_out, fetch_sub
    )
    assert sub_out.read_bytes() == b"INITABCD"
    child_init = """
    <MPD mediaPresentationDuration="PT4S"><Period>
      <SegmentTemplate media="s$Number$.m4s" startNumber="1" duration="2" timescale="1">
        <Initialization sourceURL="init.mp4"/>
      </SegmentTemplate>
    </Period></MPD>
    """
    assert recordable_segment_urls(child_init, "https://cdn.example.com/") == [
        "https://cdn.example.com/init.mp4",
        "https://cdn.example.com/s1.m4s",
        "https://cdn.example.com/s2.m4s",
    ]
    child_init_range = """
    <MPD mediaPresentationDuration="PT4S"><Period>
      <SegmentTemplate media="s$Number$.m4s" startNumber="1" duration="2" timescale="1">
        <Initialization sourceURL="bundle.mp4" range="0-3"/>
      </SegmentTemplate>
    </Period></MPD>
    """
    ranged_init = recordable_parts(child_init_range, "https://cdn.example.com/")
    assert ranged_init[0] == ManifestPart("https://cdn.example.com/bundle.mp4", 0, 4)
    assert [part.url for part in ranged_init[1:]] == [
        "https://cdn.example.com/s1.m4s",
        "https://cdn.example.com/s2.m4s",
    ]
    skipped_init = """
    <MPD><Period>
      <SegmentTemplate media="s$Number$.m4s" startNumber="1">
        <Initialization sourceURL="$Time$.mp4"/>
      </SegmentTemplate>
    </Period></MPD>
    """
    assert recordable_segment_urls(skipped_init, "https://cdn.example.com/") == [
        "https://cdn.example.com/s1.m4s",
    ]
    missing_href = """
    <MPD><Period>
      <SegmentTemplate media="s$Number$.m4s" startNumber="1">
        <Initialization range="0-3"/>
      </SegmentTemplate>
    </Period></MPD>
    """
    assert recordable_segment_urls(missing_href, "https://cdn.example.com/") == [
        "https://cdn.example.com/s1.m4s",
    ]
    timed = """
    <MPD><SegmentTemplate media="t_$Time$.m4s" startNumber="0">
      <SegmentTimeline><S t="100" d="50" r="1"/></SegmentTimeline>
    </SegmentTemplate></MPD>
    """
    times = recordable_segment_urls(timed, "https://cdn.example.com/d/")
    assert "https://cdn.example.com/d/t_100.m4s" in times
    assert "https://cdn.example.com/d/t_150.m4s" in times
    listed = """
    <MPD><Period><SegmentList>
      <Initialization sourceURL="init.mp4"/>
      <SegmentURL media="a.m4s"/>
      <SegmentURL media="b.m4s"/>
    </SegmentList></Period></MPD>
    """
    segs = recordable_segment_urls(listed, "https://cdn.example.com/l/")
    assert segs == [
        "https://cdn.example.com/l/init.mp4",
        "https://cdn.example.com/l/a.m4s",
        "https://cdn.example.com/l/b.m4s",
    ]
    ranged = """
    <MPD><Period><SegmentList>
      <Initialization sourceURL="bundle.mp4" range="0-3"/>
      <SegmentURL media="bundle.mp4" mediaRange="4-7"/>
      <SegmentURL media="bundle.mp4" mediaRange="8-11"/>
    </SegmentList></Period></MPD>
    """
    parts = recordable_parts(ranged, "https://cdn.example.com/r/")
    assert parts == [
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 0, 4),
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 4, 4),
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 8, 4),
    ]
    blob = b"INITSEGASEGBXXXX"

    def fetch_bundle(url: str) -> tuple[int, str, bytes]:
        assert url.endswith("bundle.mp4")
        return 200, "video/mp4", blob

    output = tmp_path / "dash.bin"
    record_clear_stream(ranged, "https://cdn.example.com/r/manifest.mpd", output, fetch_bundle)
    assert output.read_bytes() == b"INITSEGASEGB"
    spaced = """
    <MPD><Period><SegmentList>
      <Initialization sourceURL="bundle.mp4" range="0 - 3"/>
      <SegmentURL media="bundle.mp4" mediaRange="4 - 7"/>
      <SegmentURL media="bundle.mp4" mediaRange="8 - 11"/>
    </SegmentList></Period></MPD>
    """
    assert recordable_parts(spaced, "https://cdn.example.com/r/") == [
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 0, 4),
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 4, 4),
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 8, 4),
    ]
    spaced_out = tmp_path / "dash-spaces.bin"
    record_clear_stream(spaced, "https://cdn.example.com/r/manifest.mpd", spaced_out, fetch_bundle)
    assert spaced_out.read_bytes() == b"INITSEGASEGB"
    ranged_alias = """
    <MPD><Period><SegmentList>
      <Initialization sourceURL="bundle.mp4" range="0-3"/>
      <SegmentURL media="bundle.mp4" range="4-7"/>
      <SegmentURL media="bundle.mp4" range="8-11"/>
    </SegmentList></Period></MPD>
    """
    assert recordable_parts(ranged_alias, "https://cdn.example.com/r/") == [
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 0, 4),
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 4, 4),
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 8, 4),
    ]
    alias_out = tmp_path / "dash-range-alias.bin"
    record_clear_stream(
        ranged_alias, "https://cdn.example.com/r/manifest.mpd", alias_out, fetch_bundle
    )
    assert alias_out.read_bytes() == b"INITSEGASEGB"
    open_end = """
    <MPD><Period><SegmentList>
      <Initialization sourceURL="bundle.mp4" range="0-3"/>
      <SegmentURL media="bundle.mp4" mediaRange="4-"/>
    </SegmentList></Period></MPD>
    """
    assert recordable_parts(open_end, "https://cdn.example.com/r/") == [
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 0, 4),
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 4, None),
    ]
    open_out = tmp_path / "dash-open.bin"
    record_clear_stream(open_end, "https://cdn.example.com/r/manifest.mpd", open_out, fetch_bundle)
    assert open_out.read_bytes() == b"INITSEGASEGBXXXX"
    spaced_open = """
    <MPD><Period><SegmentList>
      <Initialization sourceURL="bundle.mp4" range="0-3"/>
      <SegmentURL media="bundle.mp4" mediaRange="4 - "/>
    </SegmentList></Period></MPD>
    """
    assert recordable_parts(spaced_open, "https://cdn.example.com/r/") == [
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 0, 4),
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 4, None),
    ]
    suffix_end = """
    <MPD><Period><SegmentList>
      <Initialization sourceURL="bundle.mp4" range="0-3"/>
      <SegmentURL media="bundle.mp4" mediaRange="-4"/>
    </SegmentList></Period></MPD>
    """
    assert recordable_parts(suffix_end, "https://cdn.example.com/r/") == [
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 0, 4),
        ManifestPart("https://cdn.example.com/r/bundle.mp4", -4, None),
    ]
    suffix_out = tmp_path / "dash-suffix.bin"
    record_clear_stream(
        suffix_end, "https://cdn.example.com/r/manifest.mpd", suffix_out, fetch_bundle
    )
    assert suffix_out.read_bytes() == b"INITXXXX"


def test_live_empty_and_nested_failure(tmp_path: Path) -> None:
    with pytest.raises(DiscoveryError, match="no recordable"):
        record_clear_stream(
            "#EXTM3U\n",
            "https://cdn.example.com/live.m3u8",
            tmp_path / "x.ts",
            lambda _url: (200, "", b""),
        )
    master = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nlow.m3u8\n"

    def fetch(url: str) -> tuple[int, str, bytes]:
        return 404, "", b""

    with pytest.raises(DiscoveryError, match="Nested"):
        record_clear_stream(master, "https://cdn.example.com/master.m3u8", tmp_path / "y.ts", fetch)


def test_export_skips_completed_ops_and_cycles(tmp_path: Path, pass_container_probe) -> None:
    src = tmp_path / "source.bin"
    src.write_bytes(b"src")
    store = ArtifactStore(tmp_path / "data")
    source = store.register(
        src, role=ArtifactRole.SOURCE, media_kind=MediaKind.VIDEO, container="mp4"
    )
    queue = QueueStore(tmp_path / "data" / "queue")
    job = _job(queue, src)
    calls: list[str] = []

    def run(argv: list[str], _cwd: Path) -> tuple[int, bytes, bytes]:
        calls.append(Path(argv[-1]).name)
        Path(argv[-1]).write_bytes(b"out")
        return 0, b"", b""

    keep = Operation(
        operation_id="keep-original",
        op_type="identity.copy",
        capability_id="export.plan",
        input_artifact_ids=[source.artifact_id],
        output_role=ArtifactRole.SOURCE,
        loss_class="none",
        validator_ids=[],
    )
    remux = Operation(
        operation_id="remux",
        op_type="ffmpeg.remux",
        capability_id="process.ffmpeg.remux",
        input_artifact_ids=[source.artifact_id],
        output_role=ArtifactRole.DERIVATIVE,
        loss_class="container_only",
        validator_ids=[],
        typed_inputs={"container": "mkv"},
    )
    plan = ExportPlan(job_id=job.job_id, operations=[keep, remux])
    completed: list[str] = []

    def check() -> None:
        if completed:
            raise PauseRequested("pause before remux")

    with pytest.raises(PauseRequested):
        execute_export_plan(
            plan,
            job_id=job.job_id,
            source=source,
            source_path=store.resolve(source),
            store=store,
            runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
            staging=tmp_path / "stage",
            queue=queue,
            authorize=lambda _cap: None,
            check_control=check,
            on_progress=lambda op, _art: completed.append(op.operation_id),
        )
    assert completed == ["keep-original"]
    assert calls == []
    execute_export_plan(
        plan,
        job_id=job.job_id,
        source=source,
        source_path=store.resolve(source),
        store=store,
        runtime=ProviderRuntime(which=lambda name: f"/usr/bin/{name}", run=run),
        staging=tmp_path / "stage2",
        queue=queue,
        authorize=lambda _cap: None,
        existing={"keep-original": (source, store.resolve(source))},
        skip_operation_ids={"keep-original"},
    )
    assert calls == ["remux.mkv"]
    cyclic = ExportPlan(
        job_id=job.job_id,
        operations=[
            remux.model_copy(update={"operation_id": "a", "input_artifact_ids": ["b"]}),
            remux.model_copy(update={"operation_id": "b", "input_artifact_ids": ["a"]}),
        ],
    )
    with pytest.raises(ProviderPolicyError, match="DAG"):
        ordered_operations(cyclic)


def test_cancel_stops_in_flight_subprocess(tmp_path: Path) -> None:
    runtime = ProviderRuntime()
    finished = {"ok": False}

    def worker() -> None:
        code, _out, _err = runtime._tracked_run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            tmp_path,
        )
        finished["ok"] = code != 0

    thread = threading.Thread(target=worker)
    thread.start()
    time.sleep(0.25)
    runtime.cancel_running()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert finished["ok"] is True


def test_pause_stops_in_flight_subprocess(tmp_path: Path) -> None:
    runtime = ProviderRuntime()
    finished = {"code": None}

    def worker() -> None:
        code, _out, _err = runtime._tracked_run(
            [sys.executable, "-c", "import time; time.sleep(30)"],
            tmp_path,
        )
        finished["code"] = code

    thread = threading.Thread(target=worker)
    thread.start()
    time.sleep(0.25)
    runtime.pause_running()
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert finished["code"] not in {0, None}


def test_execute_raises_when_cancel_flag_set(tmp_path: Path) -> None:
    from webmedia_dl.errors import CancelledError
    from webmedia_dl.providers import ProviderRequest

    runtime = ProviderRuntime(
        which=lambda name: f"/usr/bin/{name}",
        run=lambda argv, _cwd: (Path(argv[-1]).write_bytes(b"x") or 0, b"", b""),
    )
    runtime.cancel_running()
    with pytest.raises(CancelledError):
        runtime.execute(
            ProviderRequest(
                provider_id="ffmpeg",
                capability_id="process.ffmpeg.remux",
                typed_inputs={"input": "/tmp/a.mp4", "output": str(tmp_path / "a.mkv")},
            ),
            tmp_path,
        )


def test_speak_intake_is_never_a_path() -> None:
    source = normalize_source(
        "https://cdn.example.com/a.png",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
        kind=IntakeKind.SPEAK,
    )
    assert source.kind is IntakeKind.SPEAK
    assert source.local_path is None
    assert source.normalized_url == "https://cdn.example.com/a.png"


def test_checkpoint_keeps_evidence_id(tmp_path: Path, png_bytes: bytes) -> None:
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    pipeline = Pipeline(data_dir=tmp_path / "data")
    job = pipeline.submit(str(media), html="<html><body>page</body></html>")
    assert job.state is JobState.COMPLETED
    ctx = pipeline.queue.get_context(job.job_id)
    assert ctx.checkpoint.get("evidence_id")
    assert ctx.checkpoint.get("stage") in {"exported", "validating", "publishing"}


def test_pipeline_skips_reexport_when_stage_exported(tmp_path: Path, png_bytes: bytes) -> None:
    media = tmp_path / "hero.png"
    media.write_bytes(png_bytes)
    pipeline = Pipeline(data_dir=tmp_path / "data")
    job = pipeline.submit(str(media))
    assert job.state is JobState.COMPLETED
    pipeline.queue.set_state(job.job_id, JobState.ACCEPTED)
    again = pipeline._execute_stored(pipeline.queue.get_job(job.job_id))
    assert again.state is JobState.COMPLETED
    remuxes = [
        event
        for event in pipeline.queue.events_for(job.job_id)
        if event.type.value == "export.planned"
    ]
    assert len(remuxes) == 1
