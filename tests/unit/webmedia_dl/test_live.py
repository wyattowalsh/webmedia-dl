from pathlib import Path

import pytest

from webmedia_dl.domain.enums import MediaKind
from webmedia_dl.errors import DiscoveryError, DrmRefused, PauseRequested
from webmedia_dl.live import (
    MAX_PLAYLIST_NESTING,
    ManifestPart,
    _preferred_hls_variant,
    _select_dash_group,
    inspect_manifest,
    manifest_is_live,
    record_clear_stream,
    record_kind_streams,
    recordable_parts,
    recordable_segment_urls,
)


def test_record_clear_stream_concatenates_segments(tmp_path: Path) -> None:
    playlist = "#EXTM3U\n#EXTINF:1,\nseg1.ts\n#EXTINF:1,\nseg2.ts\n"
    inspect_manifest(playlist)
    bodies = {
        "https://cdn.example.com/live/seg1.ts": b"AAA",
        "https://cdn.example.com/live/seg2.ts": b"BBB",
    }

    def fetch(url: str) -> tuple[int, str, bytes]:
        return 200, "video/MP2T", bodies[url]

    output = tmp_path / "live.ts"
    record_clear_stream(playlist, "https://cdn.example.com/live/index.m3u8", output, fetch)
    assert output.read_bytes() == b"AAABBB"
    part_playlist = (
        "#EXTM3U\n"
        "#EXTINF:1,\n"
        '#EXT-X-PART:DURATION=0.5,URI="a.m4s"\n'
        "#EXTINF:1,\n"
        '#EXT-X-PART:DURATION=0.5,URI="b.m4s"\n'
    )
    part_bodies = {
        "https://cdn.example.com/live/a.m4s": b"AAA",
        "https://cdn.example.com/live/b.m4s": b"BBB",
    }

    def fetch_parts(url: str) -> tuple[int, str, bytes]:
        return 200, "video/mp4", part_bodies[url]

    part_out = tmp_path / "parts.ts"
    record_clear_stream(
        part_playlist, "https://cdn.example.com/live/index.m3u8", part_out, fetch_parts
    )
    assert part_out.read_bytes() == b"AAABBB"
    gapped = "#EXTM3U\n#EXTINF:1,\nseg1.ts\n#EXT-X-GAP\n#EXTINF:1,\ngap.ts\n#EXTINF:1,\nseg2.ts\n"

    def fetch_gapped(url: str) -> tuple[int, str, bytes]:
        if url.endswith("gap.ts"):
            raise AssertionError(url)
        return 200, "video/MP2T", bodies[url]

    gap_out = tmp_path / "gap.ts"
    record_clear_stream(gapped, "https://cdn.example.com/live/index.m3u8", gap_out, fetch_gapped)
    assert gap_out.read_bytes() == b"AAABBB"
    discontinuous = "#EXTM3U\n#EXTINF:1,\nseg1.ts\n#EXT-X-DISCONTINUITY\n#EXTINF:1,\nseg2.ts\n"
    disc_out = tmp_path / "disc.ts"
    record_clear_stream(discontinuous, "https://cdn.example.com/live/index.m3u8", disc_out, fetch)
    assert disc_out.read_bytes() == b"AAABBB"
    sequenced = (
        "#EXTM3U\n#EXT-X-DISCONTINUITY-SEQUENCE:0\n#EXTINF:1,\nseg1.ts\n#EXTINF:1,\nseg2.ts\n"
    )
    seq_out = tmp_path / "seq.ts"
    record_clear_stream(sequenced, "https://cdn.example.com/live/index.m3u8", seq_out, fetch)
    assert seq_out.read_bytes() == b"AAABBB"
    sequence_parent = (
        "#EXTM3U\n"
        '#EXT-X-PART:DURATION=0.5,URI="a.m4s"\n'
        '#EXT-X-PART:DURATION=0.5,URI="b.m4s"\n'
        "#EXT-X-DISCONTINUITY-SEQUENCE:0\n"
        "seg.ts\n"
    )
    sequence_parent_bodies = {"https://cdn.example.com/live/seg.ts": b"PARENT"}

    def fetch_sequence_parent(url: str) -> tuple[int, str, bytes]:
        if url.endswith(("a.m4s", "b.m4s")):
            raise AssertionError(url)
        return 200, "video/mp4", sequence_parent_bodies[url]

    seq_parent_out = tmp_path / "seq-parent.ts"
    record_clear_stream(
        sequence_parent,
        "https://cdn.example.com/live/index.m3u8",
        seq_parent_out,
        fetch_sequence_parent,
    )
    assert seq_parent_out.read_bytes() == b"PARENT"


def test_record_follows_master_playlist(tmp_path: Path) -> None:
    master = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\nlow.m3u8\n"
    media = "#EXTM3U\n#EXTINF:1,\nseg.ts\n"

    def fetch(url: str) -> tuple[int, str, bytes]:
        path = url.split("?", 1)[0].rstrip("/").lower()
        if path.endswith((".m3u8", ".m3u", ".mpd")):
            return 200, "application/vnd.apple.mpegurl", media.encode()
        if url.endswith("seg.ts"):
            return 200, "video/MP2T", b"SEG"
        raise AssertionError(url)

    output = tmp_path / "live.ts"
    record_clear_stream(master, "https://cdn.example.com/master.m3u8", output, fetch)
    assert output.read_bytes() == b"SEG"
    queried = tmp_path / "query.ts"
    record_clear_stream(
        "#EXTM3U\nhttps://cdn.example.com/media.m3u8?hdnea=exp\n",
        "https://cdn.example.com/index.m3u8",
        queried,
        fetch,
    )
    assert queried.read_bytes() == b"SEG"
    classic = tmp_path / "classic.ts"
    record_clear_stream(
        "#EXTM3U\nchild.m3u\n",
        "https://cdn.example.com/index.m3u",
        classic,
        fetch,
    )
    assert classic.read_bytes() == b"SEG"
    upper = tmp_path / "upper.ts"
    record_clear_stream(
        "#EXTM3U\nCHILD.M3U8\n",
        "https://cdn.example.com/index.m3u8",
        upper,
        fetch,
    )
    assert upper.read_bytes() == b"SEG"
    defined_master = (
        "#EXTM3U\n"
        '#EXT-X-DEFINE:NAME="base",VALUE="https://cdn.example.com/media"\n'
        "#EXT-X-STREAM-INF:BANDWIDTH=800000\n"
        "{$base}/child.m3u8\n"
    )
    defined_child = '#EXTM3U\n#EXT-X-DEFINE:IMPORT="base"\n#EXTINF:1,\n{$base}/seg.ts\n'
    defined_bodies = {
        "https://cdn.example.com/media/child.m3u8": defined_child.encode(),
        "https://cdn.example.com/media/seg.ts": b"DEF",
    }

    def fetch_defined(url: str) -> tuple[int, str, bytes]:
        if url in defined_bodies:
            mime = "application/vnd.apple.mpegurl" if url.endswith(".m3u8") else "video/MP2T"
            return 200, mime, defined_bodies[url]
        raise AssertionError(url)

    defined_out = tmp_path / "define.ts"
    record_clear_stream(
        defined_master, "https://cdn.example.com/master.m3u8", defined_out, fetch_defined
    )
    assert defined_out.read_bytes() == b"DEF"
    leftover_stream = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\n{$missing}/child.m3u8\n"
    assert _preferred_hls_variant(leftover_stream, "https://cdn.example.com/master.m3u8") is None
    mixed_leftover = (
        "#EXTM3U\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=900000\n"
        "{$missing}/skip.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=400000\n"
        "keep.m3u8\n"
    )
    assert (
        _preferred_hls_variant(mixed_leftover, "https://cdn.example.com/master.m3u8")
        == "https://cdn.example.com/keep.m3u8"
    )
    mixed_out = tmp_path / "mixed-define.ts"

    def fetch_mixed(url: str) -> tuple[int, str, bytes]:
        if "skip" in url or "missing" in url:
            raise AssertionError(url)
        return fetch(url)

    record_clear_stream(
        mixed_leftover, "https://cdn.example.com/master.m3u8", mixed_out, fetch_mixed
    )
    assert mixed_out.read_bytes() == b"SEG"
    with pytest.raises(DiscoveryError, match="no recordable segments"):
        record_clear_stream(
            leftover_stream,
            "https://cdn.example.com/master.m3u8",
            tmp_path / "leftover.ts",
            lambda url: (_ for _ in ()).throw(AssertionError(url)),
        )
    slashed = tmp_path / "slash.ts"
    record_clear_stream(
        "#EXTM3U\nhttps://cdn.example.com/media.m3u8/\n",
        "https://cdn.example.com/index.m3u8",
        slashed,
        fetch,
    )
    assert slashed.read_bytes() == b"SEG"
    chain = {
        "https://cdn.example.com/l0.m3u8": ("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nl1.m3u8\n"),
        "https://cdn.example.com/l1.m3u8": ("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nl2.m3u8\n"),
        "https://cdn.example.com/l2.m3u8": ("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nl3.m3u8\n"),
        "https://cdn.example.com/l3.m3u8": "#EXTM3U\n#EXTINF:1,\nseg.ts\n",
    }

    def fetch_chain(url: str) -> tuple[int, str, bytes]:
        if url.endswith("seg.ts"):
            return 200, "video/MP2T", b"DEEP"
        return 200, "application/vnd.apple.mpegurl", chain[url].encode()

    four = tmp_path / "four.ts"
    record_clear_stream(
        chain["https://cdn.example.com/l0.m3u8"],
        "https://cdn.example.com/l0.m3u8",
        four,
        fetch_chain,
    )
    assert four.read_bytes() == b"DEEP"
    deep = {
        f"https://cdn.example.com/d{index}.m3u8": (
            f"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nd{index + 1}.m3u8\n"
        )
        for index in range(MAX_PLAYLIST_NESTING)
    }
    deep[f"https://cdn.example.com/d{MAX_PLAYLIST_NESTING}.m3u8"] = "#EXTM3U\n#EXTINF:1,\nseg.ts\n"

    def fetch_deep(url: str) -> tuple[int, str, bytes]:
        if url.endswith("seg.ts"):
            return 200, "video/MP2T", b"CAP"
        return 200, "application/vnd.apple.mpegurl", deep[url].encode()

    capped = tmp_path / "cap.ts"
    record_clear_stream(
        deep["https://cdn.example.com/d0.m3u8"],
        "https://cdn.example.com/d0.m3u8",
        capped,
        fetch_deep,
    )
    assert capped.read_bytes() == b"CAP"


def test_relative_segment_urls_join_base() -> None:
    text = "#EXTM3U\n#EXT-X-KEY:METHOD=NONE\nseg.ts\n"
    urls = recordable_segment_urls(text, "https://cdn.example.com/live/index.m3u8")
    assert urls == ["https://cdn.example.com/live/seg.ts"]
    prefixed = "#EXTM3U\nhttp-seg.ts\nhttps-clip.ts\n"
    urls = recordable_segment_urls(prefixed, "https://cdn.example.com/live/index.m3u8")
    assert urls == [
        "https://cdn.example.com/live/http-seg.ts",
        "https://cdn.example.com/live/https-clip.ts",
    ]
    absolute = "#EXTM3U\nhttps://cdn.example.com/abs.ts\n"
    assert recordable_segment_urls(absolute, "https://cdn.example.com/live/index.m3u8") == [
        "https://cdn.example.com/abs.ts"
    ]
    assert recordable_segment_urls(
        "#EXTM3U\nseg.ts\n", "https://cdn.example.com/live/index.m3u8/"
    ) == ["https://cdn.example.com/live/seg.ts"]
    assert recordable_segment_urls(
        "#EXTM3U\nseg.ts\n", "https://cdn.example.com/live/index.m3u8/?token=1"
    ) == ["https://cdn.example.com/live/seg.ts"]
    assert recordable_segment_urls(
        "\ufeff#EXTM3U\n#EXTINF:1,\nseg.ts\n", "https://cdn.example.com/live.m3u8"
    ) == ["https://cdn.example.com/seg.ts"]
    defined = (
        "#EXTM3U\n"
        '#EXT-X-DEFINE:NAME="dir",VALUE="live"\n'
        '#EXT-X-DEFINE:NAME="dir",VALUE="other"\n'
        "{$dir}/seg.ts\n"
    )
    assert recordable_segment_urls(defined, "https://cdn.example.com/index.m3u8") == [
        "https://cdn.example.com/live/seg.ts"
    ]
    assert (
        recordable_segment_urls(
            "#EXTM3U\n{$missing}/seg.ts\n", "https://cdn.example.com/index.m3u8"
        )
        == []
    )
    nested_value = '#EXTM3U\n#EXT-X-DEFINE:NAME="dir",VALUE="{$nested}"\n{$dir}/seg.ts\n'
    assert recordable_segment_urls(nested_value, "https://cdn.example.com/index.m3u8") == []
    dup_attrs = '#EXTM3U\n#EXT-X-DEFINE:NAME="dir",NAME="alt",VALUE="live"\n{$dir}/seg.ts\n'
    assert recordable_segment_urls(dup_attrs, "https://cdn.example.com/index.m3u8") == []
    queried = '#EXTM3U\n#EXT-X-DEFINE:QUERYPARAM="token"\n{$token}/seg.ts\n'
    assert recordable_segment_urls(queried, "https://cdn.example.com/index.m3u8?token=live") == [
        "https://cdn.example.com/live/seg.ts"
    ]
    assert recordable_segment_urls(queried, "https://cdn.example.com/index.m3u8") == []
    imported = '#EXTM3U\n#EXT-X-DEFINE:IMPORT="dir"\n{$dir}/seg.ts\n'
    assert (
        recordable_parts(imported, "https://cdn.example.com/index.m3u8", hls_env={"dir": "live"})[
            0
        ].url
        == "https://cdn.example.com/live/seg.ts"
    )
    assert recordable_segment_urls(imported, "https://cdn.example.com/index.m3u8") == []
    named_then_query = (
        "#EXTM3U\n"
        '#EXT-X-DEFINE:NAME="token",VALUE="live"\n'
        '#EXT-X-DEFINE:QUERYPARAM="token"\n'
        "{$token}/seg.ts\n"
    )
    assert recordable_segment_urls(
        named_then_query, "https://cdn.example.com/index.m3u8?token=other"
    ) == ["https://cdn.example.com/live/seg.ts"]
    named_then_import = (
        "#EXTM3U\n"
        '#EXT-X-DEFINE:NAME="dir",VALUE="live"\n'
        '#EXT-X-DEFINE:IMPORT="dir"\n'
        "{$dir}/seg.ts\n"
    )
    assert (
        recordable_parts(
            named_then_import, "https://cdn.example.com/index.m3u8", hls_env={"dir": "other"}
        )[0].url
        == "https://cdn.example.com/live/seg.ts"
    )
    nameless = '#EXTM3U\n#EXT-X-DEFINE:NAME="dir"\n{$dir}/seg.ts\n'
    assert recordable_segment_urls(nameless, "https://cdn.example.com/index.m3u8") == []


def test_encrypted_master_refused_before_fetch(tmp_path: Path) -> None:
    text = '#EXTM3U\n#EXT-X-KEY:METHOD=SAMPLE-AES,URI="https://example.com/key"\nseg.ts\n'
    with pytest.raises(DrmRefused):
        inspect_manifest(text)
    with pytest.raises(DrmRefused):
        record_clear_stream(
            text,
            "https://cdn.example.com/live.m3u8",
            tmp_path / "x.ts",
            lambda url: (200, "", b""),
        )


def test_aes128_playlist_refused_before_any_segment_fetch(tmp_path: Path) -> None:
    text = '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key"\nseg.ts\n'
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        raise AssertionError(url)

    with pytest.raises(DrmRefused, match="AES-128"):
        inspect_manifest(text)
    with pytest.raises(DrmRefused, match="AES-128"):
        record_clear_stream(text, "https://cdn.example.com/live.m3u8", tmp_path / "x.ts", fetch)
    assert fetched == []
    bom_aes = f"\ufeff{text}"
    with pytest.raises(DrmRefused, match="AES-128"):
        inspect_manifest(bom_aes)
    with pytest.raises(DrmRefused, match="AES-128"):
        record_clear_stream(
            bom_aes, "https://cdn.example.com/live.m3u8", tmp_path / "bom.ts", fetch
        )
    assert fetched == []
    secret = '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key"\nseg.ts\n'
    nested_fetched: list[str] = []

    def fetch_nested(url: str) -> tuple[int, str, bytes]:
        nested_fetched.append(url)
        if "secret.m3u8" in url:
            return 200, "application/vnd.apple.mpegurl", b"\xef\xbb\xbf" + secret.encode()
        raise AssertionError(url)

    with pytest.raises(DrmRefused, match="AES-128"):
        record_clear_stream(
            "#EXTM3U\nhttps://cdn.example.com/secret.m3u8?token=1\n",
            "https://cdn.example.com/wrap.m3u8",
            tmp_path / "wrap.ts",
            fetch_nested,
        )
    assert nested_fetched == ["https://cdn.example.com/secret.m3u8?token=1"]
    deep_fetched: list[str] = []

    def fetch_four_level(url: str) -> tuple[int, str, bytes]:
        deep_fetched.append(url)
        if url.endswith("l1.m3u8"):
            return (
                200,
                "application/vnd.apple.mpegurl",
                b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nl2.m3u8\n",
            )
        if url.endswith("l2.m3u8"):
            return (
                200,
                "application/vnd.apple.mpegurl",
                b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nsecret.m3u8\n",
            )
        if "secret.m3u8" in url:
            return 200, "application/vnd.apple.mpegurl", secret.encode()
        raise AssertionError(url)

    with pytest.raises(DrmRefused, match="AES-128"):
        record_clear_stream(
            "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\nl1.m3u8\n",
            "https://cdn.example.com/l0.m3u8",
            tmp_path / "four-aes.ts",
            fetch_four_level,
        )
    assert deep_fetched == [
        "https://cdn.example.com/l1.m3u8",
        "https://cdn.example.com/l2.m3u8",
        "https://cdn.example.com/secret.m3u8",
    ]
    assert not any(item.endswith("seg.ts") for item in deep_fetched)


def test_live_segment_http_error_fails_closed(tmp_path: Path) -> None:
    from webmedia_dl.errors import DiscoveryError

    playlist = "#EXTM3U\n#EXTINF:1,\nseg.ts\n"

    def fetch(url: str) -> tuple[int, str, bytes]:
        return 404, "", b""

    with pytest.raises(DiscoveryError, match="HTTP 404"):
        record_clear_stream(playlist, "https://cdn.example.com/live.m3u8", tmp_path / "x.ts", fetch)


def test_inspect_manifest_aes128_without_clear_prefix() -> None:
    with pytest.raises(DrmRefused, match="AES-128"):
        inspect_manifest('#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key"\n')


def test_hls_map_invalid_byterange_and_blank_lines(tmp_path: Path) -> None:
    playlist = '#EXTM3U\n\n#EXT-X-MAP:URI="init.mp4",BYTERANGE="nope"\nseg.ts\n'
    bodies = {
        "https://cdn.example.com/live/init.mp4": b"INIT",
        "https://cdn.example.com/live/seg.ts": b"SEG",
    }

    def fetch(url: str) -> tuple[int, str, bytes]:
        return 200, "video/mp4", bodies[url]

    output = tmp_path / "live.bin"
    record_clear_stream(playlist, "https://cdn.example.com/live/index.m3u8", output, fetch)
    assert output.read_bytes() == b"INITSEG"


def test_dash_directory_baseurl_without_slash() -> None:
    from webmedia_dl.live import recordable_segment_urls

    text = """
    <MPD><Period>
      <BaseURL>https://cdn.example.com/dash</BaseURL>
      <SegmentTemplate media="seg$Number$.m4s" startNumber="1"/>
    </Period></MPD>
    """
    urls = recordable_segment_urls(text, "https://cdn.example.com/manifest.mpd")
    assert urls == ["https://cdn.example.com/dash/seg1.m4s"]
    cdata = """
    <MPD><Period>
      <BaseURL><![CDATA[]]></BaseURL>
      <dash:BaseURL>
        <![CDATA[https://cdn.example.com/dash/]]>
      </dash:BaseURL>
      <SegmentTemplate media="http-seg$Number$.m4s" startNumber="1"/>
    </Period></MPD>
    """
    assert recordable_segment_urls(cdata, "https://origin.example.com/manifest.mpd") == [
        "https://cdn.example.com/dash/http-seg1.m4s"
    ]
    wrapped = """
    <MPD><Period>
      <BaseURL>https://cdn.example.com/very/long/
path/</BaseURL>
      <SegmentTemplate media="seg$Number$.m4s" startNumber="1"/>
    </Period></MPD>
    """
    assert recordable_segment_urls(wrapped, "https://origin.example.com/manifest.mpd") == [
        "https://cdn.example.com/very/long/path/seg1.m4s"
    ]
    encoded = """
    <MPD><Period>
      <SegmentList>
        <SegmentURL media="https://cdn.example.com/a.m4s?token=1&amp;exp=2"/>
      </SegmentList>
    </Period></MPD>
    """
    assert recordable_segment_urls(encoded, "https://origin.example.com/manifest.mpd") == [
        "https://cdn.example.com/a.m4s?token=1&exp=2"
    ]


def test_time_token_without_timeline_is_skipped() -> None:
    from webmedia_dl.live import recordable_segment_urls

    text = """
    <MPD><Period>
      <SegmentTemplate media="t_$Time$.m4s" startNumber="1"/>
    </Period></MPD>
    """
    assert recordable_segment_urls(text, "https://cdn.example.com/") == []


def test_dash_segmentbase_media_range(tmp_path: Path) -> None:
    text = """
    <MPD><Period>
      <Representation id="v1" bandwidth="800000" mimeType="video/mp4">
        <BaseURL>video.mp4</BaseURL>
        <SegmentBase indexRange="10-15" mediaRange="16-20">
          <Initialization range="0-9"/>
        </SegmentBase>
      </Representation>
    </Period></MPD>
    """
    parts = recordable_parts(text, "https://cdn.example.com/")
    assert [(part.url, part.start, part.length) for part in parts] == [
        ("https://cdn.example.com/video.mp4", 0, 10),
        ("https://cdn.example.com/video.mp4", 10, 6),
        ("https://cdn.example.com/video.mp4", 16, 5),
    ]
    bare = """
    <MPD><Period>
      <Representation id="v1" bandwidth="800000" mimeType="video/mp4">
        <BaseURL>https://cdn.example.com/video123</BaseURL>
        <SegmentBase indexRange="10-15" mediaRange="16-20">
          <Initialization range="0-9"/>
        </SegmentBase>
      </Representation>
    </Period></MPD>
    """
    bare_parts = recordable_parts(bare, "https://cdn.example.com/manifest.mpd")
    assert [(part.url, part.start, part.length) for part in bare_parts] == [
        ("https://cdn.example.com/video123", 0, 10),
        ("https://cdn.example.com/video123", 10, 6),
        ("https://cdn.example.com/video123", 16, 5),
    ]
    fetched: list[str] = []
    blob = bytes(range(21))

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        return 200, "video/mp4", blob

    dest = tmp_path / "dash.bin"
    record_clear_stream(bare, "https://cdn.example.com/manifest.mpd", dest, fetch)
    assert fetched == ["https://cdn.example.com/video123"]
    assert dest.read_bytes() == blob[0:10] + blob[10:16] + blob[16:21]


def test_select_dash_group_prefers_video_then_audio() -> None:
    video = [ManifestPart("https://cdn.example.com/v.m4s")]
    audio = [ManifestPart("https://cdn.example.com/a.m4a")]
    assert _select_dash_group([(1, "video", video), (9, "audio", audio)]) == video
    assert _select_dash_group([(9, "audio", audio)]) == audio
    assert _select_dash_group([]) == []


def test_manifest_is_live_requires_mpd_open_or_hls_without_endlist() -> None:
    assert manifest_is_live("see <MPD without a closing bracket") is False
    assert manifest_is_live('<MPD type="dynamic">') is True
    assert manifest_is_live('<MPD type="static">') is False
    assert manifest_is_live("#EXTM3U\n#EXTINF:1,\nseg.ts\n") is True
    assert manifest_is_live("#EXTM3U\n#EXT-X-ENDLIST\n") is False
    assert manifest_is_live("not a playlist") is False


def test_record_refuses_dash_content_protection_before_fetch(tmp_path: Path) -> None:
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        raise AssertionError(url)

    with pytest.raises(DrmRefused, match="ContentProtection"):
        record_clear_stream(
            "<MPD><ContentProtection schemeIdUri='urn:mpeg:cenc'/></MPD>",
            "https://cdn.example.com/manifest.mpd",
            tmp_path / "x.bin",
            fetch,
        )
    assert fetched == []


def test_empty_live_segments_fail_closed(tmp_path: Path) -> None:
    playlist = "#EXTM3U\n#EXTINF:1,\nseg.ts\n"
    with pytest.raises(DiscoveryError, match="empty artifact"):
        record_clear_stream(
            playlist,
            "https://cdn.example.com/live.m3u8",
            tmp_path / "x.ts",
            lambda url: (200, "", b""),
        )


def test_record_kind_streams_hls_without_audio_stays_live(tmp_path: Path) -> None:
    playlist = "#EXTM3U\n#EXTINF:1,\nseg.ts\n"
    dest = tmp_path / "live.ts"
    recorded = record_kind_streams(
        playlist,
        "https://cdn.example.com/live.m3u8",
        dest,
        lambda url: (200, "", b"SEG"),
    )
    assert recorded == [(MediaKind.LIVE_STREAM, dest)]
    assert dest.read_bytes() == b"SEG"


def test_nested_playlist_respects_should_stop(tmp_path: Path) -> None:
    master = "#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=800000\nlow.m3u8\n"
    fetched: list[str] = []

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        return 200, "", b"#EXTM3U\n#EXTINF:1,\nseg.ts\n"

    def should_stop() -> None:
        raise PauseRequested("nested")

    with pytest.raises(PauseRequested, match="nested"):
        record_clear_stream(
            master,
            "https://cdn.example.com/master.m3u8",
            tmp_path / "x.ts",
            fetch,
            should_stop=should_stop,
        )
    assert fetched == []


def test_record_kind_streams_stops_before_audio_fetch(tmp_path: Path) -> None:
    master = (
        "#EXTM3U\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aac",URI="audio.m3u8"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=1,AUDIO="aac"\n'
        "video.m3u8\n"
    )
    dest = tmp_path / "live.bin"
    fetched: list[str] = []

    def should_stop() -> None:
        if dest.exists() and dest.stat().st_size > 0:
            raise PauseRequested("stop before audio")

    def fetch(url: str) -> tuple[int, str, bytes]:
        fetched.append(url)
        if url.endswith("video.m3u8"):
            return 200, "application/vnd.apple.mpegurl", b"#EXTM3U\n#EXTINF:1,\nv.ts\n"
        if url.endswith("v.ts"):
            return 200, "video/MP2T", b"V"
        if url.endswith("audio.m3u8"):
            return 200, "application/vnd.apple.mpegurl", b"#EXTM3U\n#EXTINF:1,\na.ts\n"
        if url.endswith("a.ts"):
            return 200, "audio/aac", b"A"
        return 200, "application/vnd.apple.mpegurl", master.encode()

    with pytest.raises(PauseRequested, match="before audio"):
        record_kind_streams(
            master,
            "https://cdn.example.com/master.m3u8",
            dest,
            fetch,
            should_stop=should_stop,
        )
    assert not any(item.endswith("audio.m3u8") for item in fetched)
