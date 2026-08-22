"""OpenSpec SHALL proofs that were previously unasserted or fail-open."""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import shutil
import subprocess
import zipfile
from collections import Counter
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from webmedia_dl.candidates import build_graph, preferred_by_kind
from webmedia_dl.diagnostics import doctor
from webmedia_dl.discovery import candidates_from_manifest_json, discover
from webmedia_dl.domain.enums import (
    ArtifactRole,
    DestinationKind,
    EventType,
    IntakeKind,
    JobState,
    LossClass,
    MediaKind,
    Surface,
)
from webmedia_dl.domain.models import (
    Artifact,
    BrowserEvidence,
    EventRecord,
    ExportIntent,
    Job,
    MediaCandidate,
    MediaSource,
)
from webmedia_dl.errors import CapabilityDenied, DrmRefused, IntakeError, ProviderPolicyError
from webmedia_dl.export import plan_export
from webmedia_dl.identity import SAFE_CONTAINER_PATTERN, is_safe_container, is_safe_format_id
from webmedia_dl.live import (
    ManifestPart,
    inspect_manifest,
    manifest_is_live,
    record_clear_stream,
    recordable_parts,
)
from webmedia_dl.paths import repo_root
from webmedia_dl.pipeline import Pipeline
from webmedia_dl.policy.profiles import assert_worker_capability, get_profile
from webmedia_dl.probe import probe_media
from webmedia_dl.providers import (
    ProviderRequest,
    ProviderRuntime,
    _assert_allowed_flags,
    builtin_manifests,
)
from webmedia_dl.queue import QUEUE_EVENT_JOB_ID
from webmedia_dl.security import detect_drm_signals, refuse_drm
from webmedia_dl.support import write_support_bundle


def test_session_key_fairplay_is_refused_before_fetch(tmp_path: Path) -> None:
    playlist = (
        "#EXTM3U\n"
        '#EXT-X-SESSION-KEY:METHOD=SAMPLE-AES,URI="skd://key",'
        'KEYFORMAT="com.apple.streamingkeydelivery"\n'
        "#EXTINF:4,\n"
        "seg1.ts\n"
        "#EXTINF:4,\n"
        "seg2.ts\n"
    )
    with pytest.raises(DrmRefused, match="session encryption"):
        inspect_manifest(playlist)
    with pytest.raises(DrmRefused, match="session encryption"):
        recordable_parts(playlist, "https://cdn.example.com/index.m3u8")

    def fetch(_url: str) -> tuple[int, str, bytes]:
        raise AssertionError("encrypted session playlists must not fetch segments")

    with pytest.raises(DrmRefused, match="session encryption"):
        record_clear_stream(
            playlist,
            "https://cdn.example.com/index.m3u8",
            tmp_path / "out.ts",
            fetch,
        )


def test_hls_key_method_is_not_read_from_quoted_uri(tmp_path: Path) -> None:
    fairplay = (
        "#EXTM3U\n#EXT-X-TARGETDURATION:4\n"
        '#EXT-X-KEY:METHOD=SAMPLE-AES,KEYFORMAT="com.apple.streamingkeydelivery",'
        'URI="skd://vendor/asset?METHOD=NONE"\n'
        "#EXTINF:4,\nseg1.ts\n#EXTINF:4,\nseg2.ts\n#EXT-X-ENDLIST\n"
    )
    aes = (
        "#EXTM3U\n"
        '#EXT-X-KEY:URI="https://k.invalid/key?id=7&METHOD=NONE",METHOD=AES-128\n'
        "#EXTINF:4,\nseg1.ts\n"
    )
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        raise AssertionError(url)

    for playlist in (fairplay, aes):
        fetched.clear()
        with pytest.raises(DrmRefused):
            inspect_manifest(playlist)
        with pytest.raises(DrmRefused):
            recordable_parts(playlist, "https://live.invalid/p.m3u8")
        with pytest.raises(DrmRefused):
            record_clear_stream(playlist, "https://live.invalid/p.m3u8", tmp_path / "out.ts", fetch)
        assert fetched == []
    with pytest.raises(DrmRefused, match="AES-128"):
        inspect_manifest(aes)

    session = (
        "#EXTM3U\n"
        '#EXT-X-SESSION-KEY:METHOD=SAMPLE-AES,URI="skd://a?METHOD=NONE"\n'
        "#EXTINF:1,\nseg.ts\n"
    )
    with pytest.raises(DrmRefused, match="session encryption"):
        inspect_manifest(session)

    missing = '#EXTM3U\n#EXT-X-KEY:URI="https://example.com/key"\nseg.ts\n'
    with pytest.raises(DrmRefused, match="UNKNOWN"):
        inspect_manifest(missing)

    none_with_uri = (
        '#EXTM3U\n#EXT-X-KEY:URI="https://k.invalid/key?METHOD=AES-128",METHOD=NONE\nseg.ts\n'
    )
    with pytest.raises(DrmRefused, match="UNKNOWN"):
        inspect_manifest(none_with_uri)

    clear = "#EXTM3U\n#EXT-X-KEY:METHOD=NONE\nseg.ts\n"
    inspect_manifest(clear)
    assert recordable_parts(clear, "https://cdn.example.com/index.m3u8")[0].url.endswith("/seg.ts")


def test_hls_widevine_session_data_is_refused_before_fetch(tmp_path: Path) -> None:
    master = (
        "#EXTM3U\n"
        '#EXT-X-SESSION-DATA:DATA-ID="com.widevine.alpha",VALUE="x"\n'
        "#EXT-X-STREAM-INF:BANDWIDTH=1\n"
        "v.m3u8\n"
    )
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        raise AssertionError(url)

    with pytest.raises(DrmRefused):
        inspect_manifest(master)
    with pytest.raises(DrmRefused):
        recordable_parts(master, "https://h.invalid/index.m3u8")
    with pytest.raises(DrmRefused):
        record_clear_stream(master, "https://h.invalid/index.m3u8", tmp_path / "out.ts", fetch)
    assert fetched == []


def test_hls_clear_prefix_still_records_before_later_aes128(tmp_path: Path) -> None:
    playlist = (
        "#EXTM3U\n"
        "#EXT-X-KEY:METHOD=NONE\n"
        "#EXTINF:1,\n"
        "seg1.ts\n"
        '#EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key"\n'
        "#EXTINF:1,\n"
        "secret.ts\n"
    )
    fetched: list[str] = []
    bodies = {"https://cdn.example.com/live/seg1.ts": b"CLEAR"}

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        if "secret" in url or "key" in url:
            raise AssertionError(url)
        return 200, "video/MP2T", bodies[url]

    inspect_manifest(playlist)
    assert [
        part.url for part in recordable_parts(playlist, "https://cdn.example.com/live/index.m3u8")
    ] == ["https://cdn.example.com/live/seg1.ts"]
    output = tmp_path / "live.ts"
    record_clear_stream(playlist, "https://cdn.example.com/live/index.m3u8", output, fetch)
    assert output.read_bytes() == b"CLEAR"
    assert fetched == ["https://cdn.example.com/live/seg1.ts"]


def test_hls_duplicate_method_and_none_with_extra_attrs_refuse(tmp_path: Path) -> None:
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        raise AssertionError(url)

    playlists = [
        '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="k",METHOD=NONE\nseg1.ts\n#EXT-X-ENDLIST\n',
        "#EXTM3U\n#EXT-X-KEY:METHOD=NONE,METHOD=AES-128\nseg1.ts\n",
        "#EXTM3U\n#EXT-X-SESSION-KEY:METHOD=SAMPLE-AES,METHOD=NONE\nseg1.ts\n",
        '#EXTM3U\n#EXT-X-KEY:METHOD=NONE,KEYFORMAT="com.apple.fps"\nseg1.ts\n',
        '#EXTM3U\n#EXT-X-KEY:METHOD=NONE,URI="https://lic.invalid/k"\nseg1.ts\n',
    ]
    for playlist in playlists:
        fetched.clear()
        with pytest.raises(DrmRefused):
            inspect_manifest(playlist)
        with pytest.raises(DrmRefused):
            recordable_parts(playlist, "https://b.invalid/index.m3u8")
        with pytest.raises(DrmRefused):
            record_clear_stream(
                playlist, "https://b.invalid/index.m3u8", tmp_path / "out.ts", fetch
            )
        assert fetched == []


def test_hls_map_is_only_the_tag_and_uses_attribute_uri(tmp_path: Path) -> None:
    hijack = (
        "#EXTM3U\n"
        '#EXT-X-SESSION-DATA:DATA-ID="x",VALUE="#EXT-X-MAP:URI=\'https://evil.invalid/init.mp4\'"\n'
        '#EXT-X-KEY:METHOD=AES-128,URI="k"\n'
        "seg1.ts\n"
    )
    with pytest.raises(DrmRefused):
        inspect_manifest(hijack)
    with pytest.raises(DrmRefused):
        recordable_parts(hijack, "https://b.invalid/index.m3u8")

    nested = (
        '#EXTM3U\n#EXT-X-MAP:URI="init.mp4",FOO="a URI=\'https://evil.invalid/x.bin\'"\nseg1.ts\n'
    )
    assert [part.url for part in recordable_parts(nested, "https://b.invalid/index.m3u8")] == [
        "https://b.invalid/init.mp4",
        "https://b.invalid/seg1.ts",
    ]
    first_uri = '#EXTM3U\n#EXT-X-MAP:URI="init.mp4",URI="https://evil.invalid/x.bin"\nseg1.ts\n'
    assert [part.url for part in recordable_parts(first_uri, "https://b.invalid/index.m3u8")] == [
        "https://b.invalid/init.mp4",
        "https://b.invalid/seg1.ts",
    ]
    bodies = {
        "https://b.invalid/init.mp4": b"INIT",
        "https://b.invalid/seg1.ts": b"SEG",
    }

    def fetch(url: str) -> tuple[int, str, bytes]:
        assert "evil" not in url
        return 200, "video/mp4", bodies[url]

    output = tmp_path / "live.bin"
    record_clear_stream(nested, "https://b.invalid/index.m3u8", output, fetch)
    assert output.read_bytes() == b"INITSEG"
    missing_uri = '#EXTM3U\n#EXT-X-MAP:BYTERANGE="4@0"\nseg.ts\n'
    assert [part.url for part in recordable_parts(missing_uri, "https://b.invalid/i.m3u8")] == [
        "https://b.invalid/seg.ts"
    ]


def test_detect_drm_signals_covers_cenc_and_system_uuids() -> None:
    assert detect_drm_signals('schemeIdUri="urn:mpeg:cenc:2013" cenc:default_KID="aa"')
    assert detect_drm_signals("urn:uuid:EDEF8BA9-79D6-4ACE-A3C8-27DCD51D21ED")
    assert detect_drm_signals("urn:uuid:9A04F079-9840-4286-AB92-E65BE0885F95")
    assert detect_drm_signals('KEYFORMAT="com.apple.streamingkeydelivery" skd://clip')
    assert detect_drm_signals('value="cbcs"')
    with pytest.raises(DrmRefused):
        refuse_drm(detect_drm_signals("urn:mpeg:dash:mp4protection:2011"))


def test_html_cenc_page_drm_signals_stay_on_candidates() -> None:
    html = """
    <html><body>
      <p>schemeIdUri="cenc" value="cbcs"</p>
      <img src="https://cdn.example.com/hero.png">
    </body></html>
    """
    found = discover(_page_source(), get_profile("personal-full"), html=html)
    images = [item for item in found if item.media_kind is MediaKind.IMAGE]
    assert images
    assert any(item.drm_signals for item in images)
    jsonld = """
    <html><body>
      <p>schemeIdUri="cenc"</p>
      <script type="application/ld+json">
        {"@type": "VideoObject", "contentUrl": "https://cdn.example.com/clip.mp4"}
      </script>
    </body></html>
    """
    found = discover(_page_source(), get_profile("personal-full"), html=jsonld)
    videos = [item for item in found if item.media_kind is MediaKind.VIDEO]
    assert videos
    assert any(item.drm_signals for item in videos)
    html_video = """
    <html><body>
      <p>schemeIdUri="cenc"</p>
      <video src="https://cdn.example.com/clip.mp4"></video>
    </body></html>
    """
    evidence = [
        BrowserEvidence(url="https://cdn.example.com/clip.mp4", kind=MediaKind.VIDEO),
        BrowserEvidence(url="https://cdn.example.com/captured.mp4", kind=MediaKind.VIDEO),
    ]
    found = discover(
        _page_source(),
        get_profile("personal-full"),
        html=html_video,
        evidence=evidence,
    )
    evidenced = [
        item
        for item in found
        if item.retrieval_urls
        and item.retrieval_urls[0]
        in {
            "https://cdn.example.com/clip.mp4",
            "https://cdn.example.com/captured.mp4",
        }
    ]
    assert len(evidenced) == 2
    assert all(item.drm_signals for item in evidenced)


def test_namespaced_dash_content_protection_and_segmentlist() -> None:
    protected = (
        '<?xml version="1.0"?>'
        '<dash:MPD xmlns:dash="urn:mpeg:dash:schema:mpd:2011">'
        '<dash:Period><dash:ContentProtection schemeIdUri="urn:mpeg:cenc:2013"/>'
        "</dash:Period></dash:MPD>"
    )
    with pytest.raises(DrmRefused):
        inspect_manifest(protected)
    listed = """
    <?xml version="1.0"?>
    <dash:MPD xmlns:dash="urn:mpeg:dash:schema:mpd:2011">
      <dash:Period>
        <dash:AdaptationSet>
          <dash:Representation id="1" bandwidth="1000" mimeType="video/mp4">
            <dash:BaseURL>bundle.mp4</dash:BaseURL>
            <dash:SegmentList>
              <dash:Initialization range="0-3"/>
              <dash:SegmentURL mediaRange="4-7"/>
            </dash:SegmentList>
          </dash:Representation>
        </dash:AdaptationSet>
      </dash:Period>
    </dash:MPD>
    """
    assert recordable_parts(listed, "https://cdn.example.com/r/") == [
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 0, 4),
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 4, 4),
    ]
    dynamic = (
        '<dash:MPD xmlns:dash="urn:mpeg:dash:schema:mpd:2011" type="dynamic">'
        "<dash:Period/></dash:MPD>"
    )
    assert manifest_is_live(dynamic)


def test_candidate_graph_records_duplicates_drm_and_grouping() -> None:
    source_id = uuid4()
    shared = "host:cdn.example.com"
    first = MediaCandidate(
        source_id=source_id,
        media_kind=MediaKind.VIDEO,
        identity_key="host:cdn.example.com:path:/a.mp4",
        grouping_key=shared,
        host="cdn.example.com",
        retrieval_urls=["https://cdn.example.com/a.mp4"],
    )
    duplicate = MediaCandidate(
        source_id=source_id,
        media_kind=MediaKind.VIDEO,
        identity_key="host:cdn.example.com:path:/a.mp4",
        grouping_key=shared,
        host="cdn.example.com",
        retrieval_urls=["https://cdn.example.com/a.mp4?alt=1"],
        drm_signals=["widevine"],
    )
    graph = build_graph(uuid4(), [first, duplicate])
    relations = {edge.relation for edge in graph.edges}
    assert "grouped_with" in relations
    assert "alternative_of" in relations
    assert any(item.startswith("duplicate-identity:") for item in graph.conflicts)
    assert f"drm:{duplicate.identity_key}" in graph.conflicts


def test_queue_events_use_zero_uuid(tmp_data: Path) -> None:
    assert UUID(int=0) == QUEUE_EVENT_JOB_ID
    pipeline = Pipeline(data_dir=tmp_data)
    pipeline.pause_queue()
    pipeline.resume_queue()
    events = pipeline.queue.events_for(QUEUE_EVENT_JOB_ID)
    types = {event.type for event in events}
    assert EventType.QUEUE_PAUSED in types
    assert EventType.QUEUE_RESUMED in types
    assert all(event.job_id == QUEUE_EVENT_JOB_ID for event in events)


def _page_source() -> MediaSource:
    return MediaSource(
        kind=IntakeKind.URL,
        locator="https://example.com/page",
        normalized_url="https://example.com/page",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )


def test_dash_segmentlist_baseurl_ranges_are_sliced(tmp_path: Path) -> None:
    text = """
    <MPD>
      <Period>
        <AdaptationSet>
          <Representation id="1" bandwidth="1000" mimeType="video/mp4">
            <BaseURL>bundle.mp4</BaseURL>
            <SegmentList>
              <Initialization range="0-3"/>
              <SegmentURL mediaRange="4-7"/>
            </SegmentList>
          </Representation>
        </AdaptationSet>
      </Period>
    </MPD>
    """
    parts = recordable_parts(text, "https://cdn.example.com/r/")
    assert parts == [
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 0, 4),
        ManifestPart("https://cdn.example.com/r/bundle.mp4", 4, 4),
    ]
    blob = b"INITSEGA"

    def fetch(url: str) -> tuple[int, str, bytes]:
        assert url.endswith("bundle.mp4")
        return 200, "video/mp4", blob

    output = tmp_path / "dash.bin"
    record_clear_stream(text, "https://cdn.example.com/r/manifest.mpd", output, fetch)
    assert output.read_bytes() == b"INITSEGA"


def test_hls_live_poll_records_reused_uri_on_new_media_sequence(tmp_path: Path) -> None:
    first = "#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:1\n#EXTINF:1,\nseg.ts\n"
    second = "#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:2\n#EXTINF:1,\nseg.ts\n"
    playlist = {"text": first}
    bodies = {"seg": b"A"}
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        if url.endswith("index.m3u8"):
            return 200, "application/vnd.apple.mpegurl", playlist["text"].encode()
        assert url.endswith("seg.ts")
        body = bodies["seg"]
        playlist["text"] = second
        bodies["seg"] = b"B"
        return 200, "video/MP2T", body

    output = tmp_path / "live.ts"
    record_clear_stream(
        first,
        "https://cdn.example.com/live/index.m3u8",
        output,
        fetch,
        live_polls=2,
    )
    assert output.read_bytes() == b"AB"
    assert fetched.count("https://cdn.example.com/live/seg.ts") == 2
    bogus = "#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:nope\n#EXTINF:1,\nseg.ts\n"
    assert recordable_parts(bogus, "https://cdn.example.com/live/index.m3u8")


def test_jsonld_candidates_keep_page_drm_signals() -> None:
    html = """
    <html><body>
      <p>Widevine protected stream</p>
      <script type="application/ld+json">
        {"@type": "VideoObject", "contentUrl": "https://cdn.example.com/clip.mp4"}
      </script>
    </body></html>
    """
    found = discover(_page_source(), get_profile("personal-full"), html=html)
    videos = [item for item in found if item.media_kind is MediaKind.VIDEO]
    assert videos
    assert any(item.drm_signals for item in videos)


def test_ytdlp_manifest_drm_after_long_title_is_kept() -> None:
    item = {
        "title": "x" * 5000,
        "url": "https://cdn.example.com/clip.mp4",
        "drm_system": "widevine",
    }
    found = candidates_from_manifest_json(_page_source(), json.dumps(item).encode())
    assert found
    assert found[0].drm_signals


def test_preferred_by_kind_keeps_drm_video_beside_clear_image() -> None:
    source_id = uuid4()
    graph = build_graph(
        uuid4(),
        [
            MediaCandidate(
                source_id=source_id,
                media_kind=MediaKind.VIDEO,
                identity_key="host:cdn.example.com:path:/protected.mpd",
                retrieval_urls=["https://cdn.example.com/protected.mpd"],
                drm_signals=["widevine"],
            ),
            MediaCandidate(
                source_id=source_id,
                media_kind=MediaKind.IMAGE,
                identity_key="host:cdn.example.com:path:/hero.png",
                retrieval_urls=["https://cdn.example.com/hero.png"],
            ),
        ],
    )
    kinds = [item.media_kind for item in preferred_by_kind(graph)]
    assert MediaKind.VIDEO in kinds
    assert MediaKind.IMAGE in kinds


def test_mixed_drm_video_still_publishes_clear_image(
    tmp_data: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_discover(
        source: MediaSource, *_args: object, **_kwargs: object
    ) -> list[MediaCandidate]:
        return [
            MediaCandidate(
                source_id=source.source_id,
                media_kind=MediaKind.VIDEO,
                identity_key="host:cdn.example.com:path:/protected.mpd",
                retrieval_urls=["https://cdn.example.com/protected.mpd"],
                drm_signals=["widevine"],
            ),
            MediaCandidate(
                source_id=source.source_id,
                media_kind=MediaKind.IMAGE,
                identity_key="host:cdn.example.com:path:/hero.png",
                retrieval_urls=["https://cdn.example.com/hero.png"],
            ),
        ]

    def http_get(url: str) -> tuple[int, dict[str, str], bytes]:
        if url.endswith(".png"):
            return 200, {"content-type": "image/png"}, png_bytes
        raise AssertionError(url)

    monkeypatch.setattr("webmedia_dl.pipeline.discover", fake_discover)
    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(which=lambda _name: None, http_get=http_get),
    )
    job = pipeline.submit("https://example.com/mixed-drm")
    assert job.state is JobState.COMPLETED
    sources = [item for item in pipeline.store.list_artifacts() if item.role is ArtifactRole.SOURCE]
    assert any(item.media_kind is MediaKind.IMAGE for item in sources)
    completed = [
        event
        for event in pipeline.queue.events_for(job.job_id)
        if event.type is EventType.JOB_COMPLETED
    ][-1]
    assert "video" in completed.payload.get("failed_kinds", [])


def test_probe_records_explicit_drm_metadata_tags(tmp_path: Path) -> None:
    media = tmp_path / "clip.bin"
    media.write_bytes(b"bytes")

    def runner(*_args: object, **_kwargs: object) -> SimpleNamespace:
        payload = {
            "streams": [{"index": 0, "codec_type": "video", "codec_name": "h264"}],
            "format": {"format_name": "mp4", "tags": {"DRM_SYSTEM": "widevine"}},
        }
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload).encode())

    probed = probe_media(media, which=lambda _name: "/usr/bin/ffprobe", runner=runner)
    assert probed is not None
    assert probed.drm_signals


def test_png_to_jpeg_requires_allow_lossy() -> None:
    source = Artifact(
        artifact_id="sha256:ab",
        role=ArtifactRole.SOURCE,
        sha256="ab",
        byte_size=1,
        media_kind=MediaKind.IMAGE,
        storage_relpath="a.png",
        container="png",
    )
    blocked = plan_export(uuid4(), source, ExportIntent(container_preference="jpg"))
    assert all(op.operation_id != "image-convert" for op in blocked.operations)
    allowed = plan_export(
        uuid4(),
        source,
        ExportIntent(container_preference="jpg", allow_lossy=True),
    )
    convert = next(op for op in allowed.operations if op.operation_id == "image-convert")
    assert convert.loss_class is LossClass.LOSSY_TRANSCODE


def test_event_payload_rejects_forbidden_keys_inside_tuples() -> None:
    with pytest.raises(ValidationError):
        EventRecord(
            job_id=uuid4(),
            type=EventType.OPERATION_COMPLETED,
            sequence=1,
            payload={"nested": ({"stdout": "secret"},)},
        )


def test_support_bundle_includes_queue_level_events(tmp_path: Path) -> None:
    data = tmp_path / "data"
    pipeline = Pipeline(data_dir=data)
    pipeline.pause_queue()
    dest = tmp_path / "bundle.zip"
    write_support_bundle(data_dir=data, dest=dest)
    with zipfile.ZipFile(dest) as archive:
        events = json.loads(archive.read("events.json"))
    queued = events[str(QUEUE_EVENT_JOB_ID)]
    assert any(item["type"] == EventType.QUEUE_PAUSED.value for item in queued)


def test_gallery_pause_resume_keeps_acquired_image_sources(
    tmp_data: Path, tmp_path: Path, png_bytes: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    html = """
    <html><body>
      <img src="https://cdn.example.com/one.jpg">
      <img src="https://cdn.example.com/two.jpg">
      <img src="https://cdn.example.com/three.jpg">
    </body></html>
    """

    def run(argv: list[str], cwd: Path) -> tuple[int, bytes, bytes]:
        created = cwd / "01.jpg"
        created.write_bytes(png_bytes)
        return 0, b"", b""

    original = Pipeline._save_acquire_checkpoint

    def save(
        self: Pipeline,
        job: Job,
        sources: list[Any],
        acquired_kinds: set[str],
        **kwargs: Any,
    ) -> None:
        original(self, job, sources, acquired_kinds, **kwargs)
        if kwargs.get("stage") == "acquired":
            self.queue.set_job_flags(job.job_id, pause_requested=True)

    monkeypatch.setattr(Pipeline, "_save_acquire_checkpoint", save)
    pipeline = Pipeline(
        data_dir=tmp_data,
        runtime=ProviderRuntime(
            which=lambda name: "/usr/bin/gallery-dl" if name == "gallery-dl" else None,
            run=run,
        ),
    )
    job = pipeline.submit("https://example.com/album", html=html, wait=False)
    paused = pipeline.run_next()
    assert paused is not None
    assert paused.state is JobState.PAUSED
    checkpoint = pipeline.queue.get_context(job.job_id).checkpoint
    assert "gallery" in checkpoint.get("acquired_kinds", [])
    sources = [pipeline.store.get(str(item)) for item in checkpoint.get("source_ids") or []]
    assert sources
    assert {item.media_kind for item in sources} == {MediaKind.IMAGE}
    monkeypatch.setattr(Pipeline, "_save_acquire_checkpoint", original)
    resumed = pipeline.resume_job(job.job_id)
    assert resumed.state is JobState.COMPLETED


@pytest.mark.parametrize(
    "container",
    [
        "../../../../tmp/wmprobe3/ESC.mkv",
        "/tmp/escape",
        "mkv; rm -rf /",
        "mkv\nbad",
        "",
        "verylongcontainer",
    ],
)
def test_export_intent_refuses_hostile_container_preference(container: str) -> None:
    assert not is_safe_container(container)
    with pytest.raises(ValidationError, match="allowed extension"):
        ExportIntent(container_preference=container)


def test_swift_export_intent_shares_container_allowlist() -> None:
    domain = (repo_root() / "apps/WebMediaDLCore/Sources/WebMediaDLCore/Domain.swift").read_text(
        encoding="utf-8"
    )
    identity = (
        repo_root() / "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/IdentityTests.swift"
    ).read_text(encoding="utf-8")
    contracts = (
        repo_root() / "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/ContractTests.swift"
    ).read_text(encoding="utf-8")
    assert f'let safeContainerPattern = "{SAFE_CONTAINER_PATTERN}"' in domain
    assert "container preference is not an allowed extension" in domain
    assert "func isSafeContainer(_ value: String)" in domain
    assert 'containerPreference: "../../../../tmp/escape"' in identity
    assert 'containerPreference: "mkv; rm -rf /"' in identity
    assert '"container_preference": "../../../../tmp/escape"' in contracts
    assert '"container_preference": "mkv; rm -rf /"' in contracts


def test_export_intent_accepts_allowlisted_containers() -> None:
    for container in ("mkv", "mp4", "png", "jpg", "jpeg", "webp", "gif", "tif", "tiff", "avif"):
        assert is_safe_container(container)
        assert ExportIntent(container_preference=container).container_preference == container
    assert ExportIntent().container_preference is None


def test_export_intent_schema_documents_container_pattern() -> None:
    from webmedia_dl.domain.models import annotate_container_preference_schema

    field = ExportIntent.model_json_schema()["properties"]["container_preference"]
    assert "pattern" not in field
    string_branch = next(
        item for item in field["anyOf"] if isinstance(item, dict) and item.get("type") == "string"
    )
    assert string_branch["pattern"] == SAFE_CONTAINER_PATTERN
    leftover: dict[str, object] = {
        "pattern": "stale",
        "anyOf": ["skip", {"type": "integer"}, {"type": "string"}],
    }
    annotate_container_preference_schema(leftover)
    assert "pattern" not in leftover
    annotated = leftover["anyOf"]
    assert isinstance(annotated, list)
    string_item = annotated[2]
    assert isinstance(string_item, dict)
    assert string_item["pattern"] == SAFE_CONTAINER_PATTERN
    empty: dict[str, object] = {}
    annotate_container_preference_schema(empty)
    assert empty == {}


def test_format_id_cannot_be_a_leading_dash_flag(tmp_path: Path) -> None:
    assert is_safe_format_id("137+140")
    assert not is_safe_format_id("--cookies")
    assert not is_safe_format_id("-best")
    runtime = ProviderRuntime(which=lambda name: "/usr/bin/yt-dlp" if name == "yt-dlp" else None)
    with pytest.raises(ProviderPolicyError):
        runtime.execute(
            ProviderRequest(
                provider_id="ytdlp",
                capability_id="acquire.ytdlp",
                typed_inputs={
                    "url": "https://example.com/v",
                    "output": str(tmp_path / "out.bin"),
                    "format_id": "--cookies",
                },
            ),
            tmp_path,
        )


def test_every_provider_argv_is_allowlisted() -> None:
    manifests = builtin_manifests()
    _assert_allowed_flags(
        ["ffmpeg", "-y", "-i", "in.mp4", "-c", "copy", "out.mkv"],
        manifests["ffmpeg"],
    )
    _assert_allowed_flags(
        ["gallery-dl", "--no-mtime", "--destination", "/tmp", "https://e/a"],
        manifests["gallery-dl"],
    )
    _assert_allowed_flags(["magick", "in.png", "-auto-orient", "out.jpg"], manifests["imagemagick"])
    with pytest.raises(ProviderPolicyError, match="not allowlisted"):
        _assert_allowed_flags(["ffmpeg", "-y", "--enable-file-urls", "in"], manifests["ffmpeg"])


def test_transport_modules_do_not_import_policy() -> None:
    root = repo_root() / "src" / "webmedia_dl"
    for name in ("transport.py", "continuity.py"):
        tree = ast.parse((root / name).read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
        assert not any("policy" in item or "capabilities" in item for item in imported), name


def _imported_modules(relative: str) -> list[str]:
    tree = ast.parse((repo_root() / "src" / "webmedia_dl" / relative).read_text(encoding="utf-8"))
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        elif isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    return imported


def test_intake_does_not_perform_network_retrieval() -> None:
    imported = _imported_modules("intake.py")
    banned = ("httpx", "urllib.request", "requests", "aiohttp", "http.client")
    assert not any(
        item == name or item.startswith(f"{name}.") for item in imported for name in banned
    )


def test_discovery_does_not_import_acquisition() -> None:
    imported = _imported_modules("discovery.py")
    assert not any("acquisition" in item for item in imported)
    banned = ("webmedia_dl.providers", "webmedia_dl.processing", "subprocess")
    assert not any(
        item == name or item.startswith(f"{name}.") for item in imported for name in banned
    )


def test_package_bundle_uses_fixed_timestamp(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "package_bundle",
        repo_root() / "scripts" / "package_bundle.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "keep.txt").write_text("ok", encoding="utf-8")
    first = tmp_path / "one.zip"
    second = tmp_path / "two.zip"
    digest_one = mod.write_bundle(tree, first)
    digest_two = mod.write_bundle(tree, second)
    assert digest_one == digest_two
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        info = archive.getinfo("keep.txt")
        assert info.date_time == (2026, 8, 18, 0, 0, 0)


def test_validate_bundle_fails_when_one_spec_is_missing() -> None:
    spec = importlib.util.spec_from_file_location(
        "validate_bundle_missing_spec",
        repo_root() / "scripts" / "validate_bundle.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    current = list(vars(mod)["CAPABILITIES"])
    vars(mod)["CAPABILITIES"] = [*current, "missing-capability"]
    assert mod.main() != 0


def test_validate_bundle_fails_when_overlay_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = importlib.util.spec_from_file_location(
        "validate_bundle",
        repo_root() / "scripts" / "validate_bundle.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    assert mod.main() != 0


def test_doctor_fail_and_warn_and_missing_skip_install(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "webmedia_dl.diagnostics.resolve_provider_binary",
        lambda name: "/bin/false" if name else None,
    )
    monkeypatch.setattr("webmedia_dl.diagnostics._provider_version_ok", lambda *_a, **_k: False)
    failed = doctor()
    assert failed["providers"]["ffmpeg"]["status"] == "FAIL"
    assert failed["providers"]["ffmpeg"]["executed"] is True
    assert failed["providers"]["http-direct"]["status"] == "PASS"
    assert failed["providers"]["http-direct"]["executed"] is True
    assert "httpx" in failed["providers"]["http-direct"]["probe"]

    monkeypatch.setattr(
        "webmedia_dl.diagnostics.resolve_provider_binary",
        lambda name: "/usr/bin/convert" if name == "magick" else None,
    )
    monkeypatch.setattr("webmedia_dl.diagnostics._provider_version_ok", lambda *_a, **_k: True)
    warned = doctor()
    assert warned["providers"]["imagemagick"]["status"] == "WARN"
    assert warned["providers"]["ytdlp"]["status"] == "BLOCKED"

    calls: list[object] = []

    def boom(*_args: object, **_kwargs: object) -> None:
        calls.append(1)
        raise AssertionError("doctor must not download providers")

    monkeypatch.setattr("webmedia_dl.diagnostics.resolve_provider_binary", lambda _name: None)
    monkeypatch.setattr("webmedia_dl.capabilities.resolve_provider_binary", lambda _name: None)
    monkeypatch.setattr("webmedia_dl.providers.resolve_provider_binary", lambda *_a, **_k: None)
    monkeypatch.setattr("webmedia_dl.providers.subprocess.run", boom)
    blocked = doctor()
    assert blocked["providers"]["ytdlp"]["status"] == "BLOCKED"
    assert calls == []


def test_watch_worker_cannot_run_gallery_dl() -> None:
    from webmedia_dl.domain.models import Worker

    profile = get_profile("personal-full")
    watch = Worker(
        worker_id="watch-misconfigured",
        platform=Surface.WATCHOS,
        profile_id=profile.profile_id,
        capabilities=list(profile.allowed_capabilities),
        subprocess_capable=False,
    )
    with pytest.raises(CapabilityDenied, match="not a subprocess worker"):
        assert_worker_capability(watch, profile, "acquire.gallery_dl")


def test_files_app_intent_requires_bookmark(tmp_path: Path) -> None:
    dest = tmp_path / "Movies"
    dest.mkdir()
    with pytest.raises(ValueError, match="security-scoped bookmark"):
        ExportIntent(
            destination_kind=DestinationKind.FILES_APP,
            destination_path=str(dest),
            approved_roots=[str(dest)],
        )
    with pytest.raises(ValueError, match="security-scoped bookmark"):
        ExportIntent(
            destination_kind=DestinationKind.FILES_APP,
            destination_path=str(dest),
            approved_roots=[str(dest)],
            security_scoped_bookmark="   ",
        )
    filled = ExportIntent(
        destination_kind=DestinationKind.FILES_APP,
        destination_path=str(dest),
        approved_roots=[str(dest)],
        security_scoped_path="   ",
        security_scoped_bookmark="ZmFrZQ==",
    )
    assert filled.security_scoped_path == str(dest)
    assert filled.security_scoped_bookmark == "ZmFrZQ=="


def test_complete_client_files_app_job_is_refused(tmp_path: Path) -> None:
    dest = tmp_path / "Movies"
    dest.mkdir()
    intent = ExportIntent(
        destination_kind=DestinationKind.FILES_APP,
        destination_path=str(dest),
        approved_roots=[str(dest)],
        security_scoped_bookmark="ZmFrZQ==",
    )
    pipeline = Pipeline(data_dir=tmp_path)
    with pytest.raises(IntakeError, match="staging_only"):
        pipeline.submit(
            "https://example.com/a.mp4",
            surface=Surface.IOS,
            intent=intent,
            wait=False,
        )
    with pytest.raises(IntakeError, match="staging_only"):
        pipeline.submit(
            "https://example.com/a.mp4",
            surface=Surface.IPADOS,
            intent=intent,
            wait=False,
        )
    with pytest.raises(IntakeError, match="staging_only"):
        pipeline.submit(
            "https://example.com/a.mp4",
            surface=Surface.VISIONOS,
            intent=intent,
            wait=False,
        )
    macos_job = pipeline.submit(
        "https://example.com/a.mp4",
        surface=Surface.MACOS,
        intent=intent,
        wait=False,
    )
    assert macos_job.intent.destination_kind is DestinationKind.FILES_APP


def test_inspect_dash_content_protection_without_named_drm_still_refuses() -> None:
    with pytest.raises(DrmRefused, match="ContentProtection"):
        inspect_manifest("<MPD><ContentProtection /></MPD>")


def test_recordable_parts_refuses_dash_system_uuid_without_protection_tag() -> None:
    text = (
        "<MPD><Period><AdaptationSet>"
        "<Representation id='v1'>urn:uuid:EDEF8BA9-79D6-4ACE-A3C8-27DCD51D21ED</Representation>"
        "</AdaptationSet></Period></MPD>"
    )
    with pytest.raises(DrmRefused):
        recordable_parts(text, "https://cdn.example.com/manifest.mpd")


def test_doctor_version_probe_oserror_is_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    from webmedia_dl import diagnostics as diagnostics_mod
    from webmedia_dl import providers as providers_mod

    monkeypatch.setattr(
        diagnostics_mod,
        "resolve_provider_binary",
        lambda name: "/usr/bin/ffmpeg" if name == "ffmpeg" else None,
    )

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("exec format error")

    monkeypatch.setattr(providers_mod.subprocess, "run", _boom)
    rows = doctor()
    ffmpeg = rows["providers"]["ffmpeg"]
    assert ffmpeg["status"] == "FAIL"
    assert ffmpeg["executed"] is True
    assert "did not report a version" in ffmpeg["reason"]


SCENARIO_EVIDENCE: dict[str, tuple[str, str]] = {
    "publication requires approved roots": (
        "tests/unit/webmedia_dl/test_fail_closed_followups.py",
        "test_user_approved_path_omits_approved_roots",
    ),
    "files bookmark path boundary": (
        "tests/unit/webmedia_dl/test_p2_contracts.py",
        "test_files_bookmark_and_photokit",
    ),
    "clipboard url is not a path": (
        "tests/unit/webmedia_dl/test_p2_contracts.py",
        "test_clipboard_locator_extracts_url",
    ),
    "photos without approval": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/IdentityTests.swift",
        "testPhotosDestinationRequiresApprovedRoot",
    ),
    "share sheet url versus file": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/IdentityTests.swift",
        "testContinuityIsNotASubprocessWorker",
    ),
    "complete-client drop stages onto the mac worker": (
        "tests/unit/webmedia_dl/test_staging_upload.py",
        "test_staging_upload_then_drop_job",
    ),
    "complete clients carry files destinations": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_complete_client_files_app_job_is_refused",
    ),
    "macos app supervises the loopback worker": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/ContractTests.swift",
        "testLoopbackRequestBuildersStayOnLoopback",
    ),
    "unsigned share extension bundles are assembled": (
        "tests/unit/webmedia_dl/test_surfaces_inventory.py",
        "test_unsigned_share_extension_appex_layouts",
    ),
    "unsigned xcode app extension products are built": (
        "tests/unit/webmedia_dl/test_surfaces_inventory.py",
        "test_unsigned_xcode_app_extension_products",
    ),
    "share destination publishes under approved root": (
        "tests/unit/webmedia_dl/test_pack_gaps.py",
        "test_share_destination_publishes_under_approved_root",
    ),
    "AES-128 playlist": (
        "tests/unit/webmedia_dl/test_live.py",
        "test_aes128_playlist_refused_before_any_segment_fetch",
    ),
    "two clear transport segments": (
        "tests/unit/webmedia_dl/test_live.py",
        "test_record_clear_stream_concatenates_segments",
    ),
    "DASH SegmentList byte ranges": (
        "tests/unit/webmedia_dl/test_runtime_gaps.py",
        "test_dash_segment_timeline",
    ),
    "AdaptationSet binds Representation identifiers": (
        "tests/unit/webmedia_dl/test_p2_contracts.py",
        "test_dash_adaptationset_binds_self_closing_representation",
    ),
    "highest-bandwidth video representation": (
        "tests/unit/webmedia_dl/test_p2_contracts.py",
        "test_dash_prefers_highest_video_representation",
    ),
    "HLS master highest bandwidth": (
        "tests/unit/webmedia_dl/test_p2_contracts.py",
        "test_hls_master_prefers_highest_bandwidth",
    ),
    "multi-period DASH concatenates each period": (
        "tests/unit/webmedia_dl/test_pack_gap_fixes.py",
        "test_multi_period_same_uri_is_appended_twice",
    ),
    "dynamic MPD polls new segments": (
        "tests/unit/webmedia_dl/test_p2_contracts.py",
        "test_dynamic_mpd_polls_new_segments",
    ),
    "DASH SegmentTemplate endNumber": (
        "tests/unit/webmedia_dl/test_fail_closed_paths.py",
        "test_dash_template_tokens_and_period_fallback",
    ),
    "DASH SegmentTemplate presentation duration": (
        "tests/unit/webmedia_dl/test_fail_closed_paths.py",
        "test_dash_template_tokens_and_period_fallback",
    ),
    "companion capture has no native command": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/IdentityTests.swift",
        "testContinuityIsNotASubprocessWorker",
    ),
    "watch worker cannot run yt-dlp": (
        "tests/unit/webmedia_dl/test_policy.py",
        "test_watch_is_not_a_subprocess_worker",
    ),
    "watch queues for Mac relay": (
        "tests/unit/webmedia_dl/test_fail_closed_followups.py",
        "test_watch_tv_capture_queues_without_ytdlp",
    ),
    "watch control intents queue companion kinds": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/ContractTests.swift",
        "testWatchConnectivityFallbackAndMacRelayTyping",
    ),
    "tvOS uses local-network companion transport": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/ContractTests.swift",
        "testWatchConnectivityFallbackAndMacRelayTyping",
    ),
    "iPhone forwards watch companion messages": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/ContractTests.swift",
        "testWatchConnectivityFallbackAndMacRelayTyping",
    ),
    "sealed companion envelope": (
        "tests/unit/webmedia_dl/test_companion_checkpoint.py",
        "test_companion_accepts_sealed_pairing_envelope",
    ),
    "unconfirmed pairing": (
        "tests/unit/webmedia_dl/test_pairing_surfaces.py",
        "test_unconfirmed_pairing_does_not_escalate",
    ),
    "confirmed pairing lets mac execute without widening": (
        "tests/unit/webmedia_dl/test_pairing_surfaces.py",
        "test_pairing_confirmation_lets_mac_own_without_widening",
    ),
    "mac lan relay rewrites to loopback": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/ContractTests.swift",
        "testLoopbackRequestBuildersStayOnLoopback",
    ),
    "complete-client history uses mac relay": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/ContractTests.swift",
        "testLoopbackRequestBuildersStayOnLoopback",
    ),
    "complete-client plan uses mac relay": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/ContractTests.swift",
        "testLoopbackRequestBuildersStayOnLoopback",
    ),
    "complete-client doctor uses mac relay": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/ContractTests.swift",
        "testLoopbackRequestBuildersStayOnLoopback",
    ),
    "complete-client control intents use mac relay": (
        "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/ContractTests.swift",
        "testLoopbackRequestBuildersStayOnLoopback",
    ),
    "HTML extracts media without using the title as identity": (
        "tests/unit/webmedia_dl/test_discovery.py",
        "test_html_discovery_extracts_media_without_using_title_as_id",
    ),
    "track and media anchors": (
        "tests/unit/webmedia_dl/test_discovery.py",
        "test_html_discovery_extracts_track_and_media_anchors",
    ),
    "iframe, preload link, and JSON-LD type": (
        "tests/unit/webmedia_dl/test_discovery.py",
        "test_html_discovery_extracts_iframe_link_and_jsonld_type",
    ),
    "amp-img and twitter player": (
        "tests/unit/webmedia_dl/test_discovery.py",
        "test_html_discovery_amp_img_and_twitter_player",
    ),
    "Graph records DRM conflicts": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_candidate_graph_records_duplicates_drm_and_grouping",
    ),
    "completed job has events": ("tests/e2e/test_cli_e2e.py", "test_submit_history_job_roundtrip"),
    "event payload is not a provider console": (
        "tests/unit/webmedia_dl/test_p2_contracts.py",
        "test_event_payload_rejects_every_forbidden_key",
    ),
    "Queue is paused": (
        "tests/unit/webmedia_dl/test_queue_manifest.py",
        "test_queue_pause_leaves_job_accepted",
    ),
    "Per-job pause is distinct from queue pause": (
        "tests/unit/webmedia_dl/test_queue_manifest.py",
        "test_paused_job_is_not_auto_started",
    ),
    "Pause mid-acquire keeps registered sources": (
        "tests/unit/webmedia_dl/test_companion_checkpoint.py",
        "test_pause_during_acquire_checkpoints_and_resume_skips_done_kind",
    ),
    "queue-level events use a zero uuid": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_queue_events_use_zero_uuid",
    ),
    "run_next restores cookie grants": (
        "tests/unit/webmedia_dl/test_fail_closed_followups.py",
        "test_run_next_restores_cookie_grant",
    ),
    "doctor JSON": ("tests/unit/webmedia_dl/test_cli.py", "test_doctor_json"),
    "support bundle is local-only": (
        "tests/unit/webmedia_dl/test_cli.py",
        "test_support_bundle_is_local_and_strips_console",
    ),
    "HTTPS paste": ("tests/unit/webmedia_dl/test_intake.py", "test_paste_kind_stays_a_url"),
    "file scheme rejected": ("tests/unit/webmedia_dl/test_intake.py", "test_file_scheme_rejected"),
    "URL plus path is invalid": (
        "tests/unit/webmedia_dl/test_invariants.py",
        "test_source_url_cannot_become_path",
    ),
    "drop of an existing file": ("tests/unit/webmedia_dl/test_cli.py", "test_drop_command"),
    "restricted cannot delegate yt-dlp": (
        "tests/unit/webmedia_dl/test_policy.py",
        "test_restricted_cannot_delegate_ytdlp",
    ),
    "consumed envelope nonces expire from the ledger": (
        "tests/unit/webmedia_dl/test_plan_evidence_replay.py",
        "test_nonce_ledger_prunes_expired_rows",
    ),
    "simulated PASS forbidden": (
        "tests/unit/webmedia_dl/test_invariants.py",
        "test_simulated_check_cannot_pass",
    ),
    "outside approved root": (
        "tests/unit/webmedia_dl/test_fail_closed_followups.py",
        "test_jobs_export_outside_approved_roots_fails_closed",
    ),
    "failed derivative does not block siblings": (
        "tests/unit/webmedia_dl/test_pack_gap_fixes.py",
        "test_publish_skips_failed_sibling",
    ),
    "extra_args rejected": ("tests/unit/webmedia_dl/test_providers.py", "test_extra_args_rejected"),
    "yt-dlp format token": (
        "tests/unit/webmedia_dl/test_providers.py",
        "test_ytdlp_argv_is_allowlisted",
    ),
    "unsafe format id is rejected": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_format_id_cannot_be_a_leading_dash_flag",
    ),
    "doctor does not install yt-dlp": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_doctor_fail_and_warn_and_missing_skip_install",
    ),
    "YouTube watch page is not fetched as HTTP bytes": (
        "tests/unit/webmedia_dl/test_coverage_gaps.py",
        "test_lossy_plan_and_gallery_acquisition",
    ),
    "remux argv": ("tests/unit/webmedia_dl/test_processing.py", "test_remux_argv_uses_stream_copy"),
    "ImageMagick policy directory": (
        "tests/unit/webmedia_dl/test_processing.py",
        "test_magick_configure_path_is_set",
    ),
    "collector returns no native command": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_extension_collector_returns_no_native_command",
    ),
    "each engine has a capture tree": (
        "tests/unit/webmedia_dl/test_surfaces_inventory.py",
        "test_browser_extension_trees",
    ),
    "default plan keeps original": (
        "tests/unit/webmedia_dl/test_fail_closed_followups.py",
        "test_original_sacred_keeps_original_with_no_loss",
    ),
    "remux is planned before transcode": (
        "tests/unit/webmedia_dl/test_remaining_contract_gates.py",
        "test_export_preset_override_and_lossy_without_container",
    ),
    "repo cookie rejected": (
        "tests/unit/webmedia_dl/test_security.py",
        "test_cookie_requires_absolute_existing_file_outside_repo",
    ),
    "mutate source fails": (
        "tests/unit/webmedia_dl/test_invariants.py",
        "test_source_artifact_cannot_be_mutated",
    ),
    "original archive preserved": (
        "tests/unit/webmedia_dl/test_compat_transport.py",
        "test_legacy_scan_is_non_destructive",
    ),
    "capture popup markup": (
        "tests/unit/webmedia_dl/test_accessibility_markup.py",
        "test_capture_popup_has_accessible_markup",
    ),
    "CLI help uses canonical name": ("tests/unit/webmedia_dl/test_cli.py", "test_help"),
    "wmdl is not the console script": (
        "tests/e2e/test_wheel_install.py",
        "test_wheel_contains_runtime_and_cli",
    ),
    "bundle zip uses a fixed timestamp": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_package_bundle_uses_fixed_timestamp",
    ),
    "encrypted HLS refuses before fetch": (
        "tests/unit/webmedia_dl/test_live.py",
        "test_aes128_playlist_refused_before_any_segment_fetch",
    ),
    "default telemetry is rejected": (
        "tests/unit/webmedia_dl/test_invariants.py",
        "test_policy_profile_forbids_drm_and_default_telemetry",
    ),
    "one-tap extension submit": (
        "tests/unit/extensions/capture.test.mjs",
        "popup send button posts one-tap capture to the loopback worker",
    ),
    "expert output is JSON events": (
        "tests/e2e/test_cli_e2e.py",
        "test_submit_history_job_roundtrip",
    ),
    "every provider argv is allowlisted": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_every_provider_argv_is_allowlisted",
    ),
    "shipped providers never auto-install": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_builtin_manifests_never_auto_install_or_accept_argv",
    ),
    "missing provider binary is not healthy": (
        "tests/unit/webmedia_dl/test_pack_gaps.py",
        "test_container_capability_health_stub_path_is_missing",
    ),
    "macos hosts the full local worker": (
        "tests/unit/webmedia_dl/test_policy.py",
        "test_macos_hosts_the_full_local_worker",
    ),
    "companion endpoint requires the mac actor": (
        "tests/unit/webmedia_dl/test_companion_checkpoint.py",
        "test_companion_endpoint_requires_mac_actor",
    ),
    "pairing challenges expire": (
        "tests/unit/webmedia_dl/test_compat_transport.py",
        "test_pairing_expiry",
    ),
    "provider version probe oserror is fail": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_doctor_version_probe_oserror_is_fail",
    ),
    "HTML discovery is size capped": (
        "tests/unit/webmedia_dl/test_pack_gap_fixes.py",
        "test_discovery_picture_amp_jsonld_list_and_html_cap",
    ),
    "fetch redirects are bounded": (
        "tests/unit/webmedia_dl/test_remainder_gates.py",
        "test_bound_fetch_redirect_bound_fails_closed",
    ),
    "discovery does not select acquisition": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_discovery_does_not_import_acquisition",
    ),
    "missing capability spec fails validation": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_validate_bundle_fails_when_one_spec_is_missing",
    ),
    "missing overlay path fails validation": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_validate_bundle_fails_when_overlay_is_missing",
    ),
    "unsafe zip members abort extraction": (
        "tests/unit/webmedia_dl/test_pack_executed_gates.py",
        "test_validate_bundle_refuses_to_extract_unsafe_members",
    ),
    "queue pause survives a new reader": (
        "tests/unit/webmedia_dl/test_queue_manifest.py",
        "test_queue_pause_survives_new_pipeline_reader",
    ),
    "run_next restores deferred HTML": (
        "tests/unit/webmedia_dl/test_queue_manifest.py",
        "test_wait_false_preserves_html_for_run_next",
    ),
    "run_next restores browser evidence": (
        "tests/unit/webmedia_dl/test_fail_closed_followups.py",
        "test_run_next_restores_browser_evidence",
    ),
    "malformed browser evidence fails closed": (
        "tests/unit/webmedia_dl/test_fail_closed_paths.py",
        "test_malformed_browser_evidence_fails_closed",
    ),
    "acquired kinds must match restored sources": (
        "tests/unit/webmedia_dl/test_fail_closed_paths.py",
        "test_checkpoint_kinds_must_match_restored_sources",
    ),
    "pause after publishing is a conflict": (
        "tests/unit/webmedia_dl/test_fail_closed_paths.py",
        "test_pause_during_publish_is_a_conflict",
    ),
    "cookie grant is revalidated on resolve": (
        "tests/unit/webmedia_dl/test_pack_gap_fixes.py",
        "test_cookie_grant_rejects_html_replacement",
    ),
    "restricted profiles forbid cookies": (
        "tests/unit/webmedia_dl/test_security.py",
        "test_restricted_profile_forbids_cookies",
    ),
    "shipped profiles forbid telemetry drm and delegation": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_shipped_profiles_forbid_telemetry_drm_and_auto_delegate",
    ),
    "session key fairplay is refused before fetch": (
        "tests/unit/webmedia_dl/test_openspec_shall_gaps.py",
        "test_session_key_fairplay_is_refused_before_fetch",
    ),
}


def _openspec_scenario_titles() -> list[str]:
    root = repo_root() / "openspec/changes/build-webmedia-dl-v1/specs"
    titles: list[str] = []
    for spec in sorted(root.glob("*/spec.md")):
        text = spec.read_text(encoding="utf-8")
        chunks = re.split(r"(?m)^#### Scenario:", text)
        assert "SHALL" in text, spec.parent.name
        for chunk in chunks[1:]:
            title = chunk.splitlines()[0].strip()
            assert "**WHEN**" in chunk, f"{spec.parent.name}: {title}"
            assert "**THEN**" in chunk, f"{spec.parent.name}: {title}"
            titles.append(title)
    return titles


def _test_defined_in(relative: str, name: str) -> bool:
    if Path(relative).is_absolute() or ".." in Path(relative).parts:
        return False
    path = (repo_root() / relative).resolve()
    try:
        path.relative_to(repo_root().resolve())
    except ValueError:
        return False
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        tree = ast.parse(text)
        return any(
            isinstance(node, ast.FunctionDef) and node.name == name for node in ast.walk(tree)
        )
    if path.suffix == ".swift":
        return re.search(rf"\bfunc {re.escape(name)}\s*\(", text) is not None
    if path.suffix == ".mjs":
        return re.search(rf'\bit\(\s*"{re.escape(name)}"', text) is not None
    return False


def test_every_openspec_scenario_has_when_then() -> None:
    titles = _openspec_scenario_titles()
    assert len(titles) >= 40
    dupes = [name for name, count in Counter(titles).items() if count > 1]
    assert dupes == [], dupes


def test_every_openspec_scenario_has_named_test() -> None:
    titles = _openspec_scenario_titles()
    missing_map = sorted(set(titles) - set(SCENARIO_EVIDENCE))
    extra_map = sorted(set(SCENARIO_EVIDENCE) - set(titles))
    assert missing_map == [], missing_map
    assert extra_map == [], extra_map
    missing_tests = [
        f"{title} -> {relative}::{name}"
        for title, (relative, name) in SCENARIO_EVIDENCE.items()
        if not _test_defined_in(relative, name)
    ]
    assert missing_tests == [], missing_tests


def test_extension_collector_returns_no_native_command() -> None:
    text = (repo_root() / "extensions/shared/capture.js").read_text(encoding="utf-8")
    assert "Never becomes a generic native command runner" in text
    assert "nativeCommand: null" in text
    assert "/^(javascript|data|blob|file|about|chrome|chrome-extension):/i" in text
    assert "blockedScheme.test(value.trim())" in text
    assert "owner.baseURI" in text
    assert 'rel.split(/\\s+/).includes("preload")' in text
    assert "!nonMediaHref.test(href)" in text
    assert 'return "live_stream"' in text
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    script = repo_root() / "tests/unit/extensions/capture.test.mjs"
    completed = subprocess.run(
        [node, "--test", str(script)],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(repo_root()),
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_builtin_manifests_never_auto_install_or_accept_argv() -> None:
    for manifest in builtin_manifests().values():
        assert manifest.install_automatic is False, manifest.provider_id
        assert manifest.accepts_user_argv is False, manifest.provider_id


def test_shipped_profiles_forbid_telemetry_drm_and_auto_delegate() -> None:
    from webmedia_dl.policy.profiles import builtin_profiles

    profiles = builtin_profiles()
    assert set(profiles) >= {
        "personal-full",
        "personal-restricted",
        "browser-capture",
        "watch-capture",
        "tv-control",
    }
    for profile in profiles.values():
        assert profile.telemetry_default is False, profile.profile_id
        assert profile.drm_circumvention is False, profile.profile_id
        assert profile.can_delegate is False, profile.profile_id
