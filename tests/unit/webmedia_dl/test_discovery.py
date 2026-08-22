from uuid import uuid4

import pytest

from webmedia_dl.candidates import build_graph
from webmedia_dl.discovery import candidates_from_manifest_json, discover
from webmedia_dl.domain.enums import IntakeKind, MediaKind, Surface
from webmedia_dl.domain.models import BrowserEvidence, MediaSource
from webmedia_dl.errors import DiscoveryError
from webmedia_dl.policy.profiles import get_profile

HTML = """
<html>
  <head>
    <title>Gallery Page</title>
    <meta property="og:image" content="https://cdn.example.com/hero.png">
    <script type="application/ld+json">
      {"contentUrl": "https://cdn.example.com/clip.mp4"}
    </script>
  </head>
  <body>
    <img src="/photos/a.jpg">
    <video src="https://cdn.example.com/clip.mp4"></video>
  </body>
</html>
"""


def _source() -> MediaSource:
    return MediaSource(
        kind=IntakeKind.URL,
        locator="https://example.com/page",
        normalized_url="https://example.com/page",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )


def test_html_discovery_extracts_media_without_using_title_as_id() -> None:
    profile = get_profile("personal-full")
    candidates = discover(_source(), profile, html=HTML)
    assert candidates
    identities = {item.identity_key for item in candidates}
    assert "Gallery Page" not in identities
    kinds = {item.media_kind for item in candidates}
    assert MediaKind.IMAGE in kinds
    assert MediaKind.VIDEO in kinds
    graph = build_graph(uuid4(), candidates)
    assert graph.nodes
    urls = [item.retrieval_urls[0] for item in candidates if item.retrieval_urls]
    assert "https://example.com/photos/a.jpg" in urls
    assert "https://cdn.example.com/clip.mp4" in urls
    assert "https://cdn.example.com/hero.png" in urls


def test_html_discovery_resolves_relative_locators_against_base_href() -> None:
    html = """
    <html>
      <head>
        <base target="_blank">
        <base href="https://cdn.example.com/media/">
        <base href="https://evil.example/ignore/">
        <script type="application/ld+json">
          {"@type": "VideoObject", "contentUrl": "ld.mp4"}
        </script>
      </head>
      <body>
        <video src="clip.mp4"></video>
      </body>
    </html>
    """
    profile = get_profile("personal-full")
    candidates = discover(_source(), profile, html=html)
    urls = [item.retrieval_urls[0] for item in candidates if item.retrieval_urls]
    assert "https://cdn.example.com/media/clip.mp4" in urls
    assert "https://cdn.example.com/media/ld.mp4" in urls
    assert "https://example.com/clip.mp4" not in urls
    assert "https://evil.example/ignore/clip.mp4" not in urls
    evidenced = discover(
        _source(),
        profile,
        html='<html><head><base href="https://cdn.example.com/media/"></head></html>',
        evidence=[BrowserEvidence(url="captured.mp4", kind=MediaKind.VIDEO)],
    )
    evidenced_urls = [item.retrieval_urls[0] for item in evidenced if item.retrieval_urls]
    assert "https://cdn.example.com/media/captured.mp4" in evidenced_urls
    blocked = """
    <html>
      <head><base href="javascript:alert(1)"></head>
      <body><video src="clip.mp4"></video></body>
    </html>
    """
    fallback = discover(_source(), profile, html=blocked)
    fallback_urls = [item.retrieval_urls[0] for item in fallback if item.retrieval_urls]
    assert "https://example.com/clip.mp4" in fallback_urls
    data_base = discover(
        _source(),
        profile,
        html='<html><head><base href="data:text/html,x"></head><body><img src="a.jpg"></body></html>',
    )
    data_urls = [item.retrieval_urls[0] for item in data_base if item.retrieval_urls]
    assert "https://example.com/a.jpg" in data_urls
    ftp_base = discover(
        _source(),
        profile,
        html='<html><head><base href="ftp://cdn.example.com/media/"></head><body><img src="a.jpg"></body></html>',
    )
    ftp_urls = [item.retrieval_urls[0] for item in ftp_base if item.retrieval_urls]
    assert "https://example.com/a.jpg" in ftp_urls
    empty_host = discover(
        _source(),
        profile,
        html='<html><head><base href="https://"></head><body><img src="a.jpg"></body></html>',
    )
    empty_urls = [item.retrieval_urls[0] for item in empty_host if item.retrieval_urls]
    assert "https://example.com/a.jpg" in empty_urls
    blank = discover(
        _source(),
        profile,
        html='<html><head><base href="  "></head><body><img src="a.jpg"></body></html>',
    )
    blank_urls = [item.retrieval_urls[0] for item in blank if item.retrieval_urls]
    assert "https://example.com/a.jpg" in blank_urls
    rooted = discover(
        _source(),
        profile,
        html='<html><head><base href="/media/"></head><body><video src="clip.mp4"></video></body></html>',
    )
    rooted_urls = [item.retrieval_urls[0] for item in rooted if item.retrieval_urls]
    assert "https://example.com/media/clip.mp4" in rooted_urls
    direct = MediaSource(
        kind=IntakeKind.URL,
        locator="https://cdn.example.com/direct.mp4",
        normalized_url="https://cdn.example.com/direct.mp4",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )
    mixed = discover(
        direct,
        profile,
        evidence=[BrowserEvidence(url="sidecar.jpg", kind=MediaKind.IMAGE)],
    )
    mixed_urls = [item.retrieval_urls[0] for item in mixed if item.retrieval_urls]
    assert "https://cdn.example.com/direct.mp4" in mixed_urls
    assert "https://cdn.example.com/sidecar.jpg" in mixed_urls


def test_html_discovery_extracts_track_and_media_anchors() -> None:
    html = """
    <html><body>
      <video src="https://cdn.example.com/clip.mp4">
        <track src="https://cdn.example.com/clip.vtt" kind="subtitles">
      </video>
      <a href="https://cdn.example.com/notes.pdf">PDF</a>
      <a href="/about">About</a>
    </body></html>
    """
    profile = get_profile("personal-full")
    candidates = discover(_source(), profile, html=html)
    kinds = {item.media_kind for item in candidates}
    urls = [item.retrieval_urls[0] for item in candidates if item.retrieval_urls]
    assert MediaKind.SUBTITLE in kinds
    assert MediaKind.DOCUMENT in kinds
    assert "https://cdn.example.com/clip.vtt" in urls
    assert "https://cdn.example.com/notes.pdf" in urls
    assert not any(item.endswith("/about") for item in urls)


def test_html_discovery_extracts_iframe_link_and_jsonld_type() -> None:
    html = """
    <html>
      <head>
        <meta property="og:video:secure_url" content="https://cdn.example.com/secure.mp4">
        <link rel="preload" as="video" href="https://cdn.example.com/pre.mp4">
        <link type="application/dash+xml;charset=utf-8" href="https://cdn.example.com/alt.mpd">
        <link type="application/vnd.apple.mpegurl" href="https://cdn.example.com/alt.m3u8">
        <script type="application/ld+json">
          {"@type": "VideoObject", "embedUrl": "https://example.com/watch?v=1"}
        </script>
      </head>
      <body>
        <iframe src="https://cdn.example.com/player.m3u8"></iframe>
      </body>
    </html>
    """
    profile = get_profile("personal-full")
    candidates = discover(_source(), profile, html=html)
    urls = [item.retrieval_urls[0] for item in candidates if item.retrieval_urls]
    kinds = {item.retrieval_urls[0]: item.media_kind for item in candidates if item.retrieval_urls}
    assert "https://cdn.example.com/secure.mp4" in urls
    assert "https://cdn.example.com/pre.mp4" in urls
    assert "https://cdn.example.com/player.m3u8" in urls
    assert kinds["https://example.com/watch?v=1"] is MediaKind.VIDEO
    assert kinds["https://cdn.example.com/player.m3u8"] is MediaKind.LIVE_STREAM
    assert kinds["https://cdn.example.com/alt.mpd"] is MediaKind.LIVE_STREAM
    assert kinds["https://cdn.example.com/alt.m3u8"] is MediaKind.LIVE_STREAM
    object_id = """
    <html><body>
      <script type="application/ld+json">
        {"@type": "VideoObject", "contentUrl": [
          "https://cdn.example.com/a.mp4",
          {"@id": "https://cdn.example.com/oid.mp4"},
          {"@id": 1},
          7
        ]}
      </script>
      <script type="application/ld+json">
        {"@type": "AudioObject", "embedUrl": {"url": "https://cdn.example.com/a.m4a"}}
      </script>
    </body></html>
    """
    object_found = discover(_source(), profile, html=object_id)
    object_urls = [item.retrieval_urls[0] for item in object_found if item.retrieval_urls]
    assert "https://cdn.example.com/a.mp4" in object_urls
    assert "https://cdn.example.com/oid.mp4" in object_urls
    assert "https://cdn.example.com/a.m4a" in object_urls
    both = """
    <html><body>
      <script>ignored()</script>
      <script type="text/javascript">ignored()</script>
      <script type="application/ld+json">
        {"@type": "VideoObject",
         "contentUrl": "https://example.com/watch?v=1",
         "embedUrl": "https://cdn.example.com/direct.mp4"}
      </script>
      <script type="application/ld+json;charset=utf-8">
        {"@type": "VideoObject", "contentUrl": "https://cdn.example.com/charset.mp4"}
      </script>
      <script type="application/ld+json">1</script>
      <script type="application/ld+json">
        <!--{"@type": "VideoObject", "contentUrl": "https://cdn.example.com/commented.mp4"}-->
      </script>
      <script type="application/ld+json">
        <!--{"@type": "VideoObject", "contentUrl": "https://cdn.example.com/open-comment.mp4"}
      </script>
      <script type="application/ld+json"><![CDATA[
        {"@type": "VideoObject", "contentUrl": "https://cdn.example.com/cdata.mp4"}
      ]]></script>
      <script type="application/ld+json"><![CDATA[
        {"@type": "VideoObject", "contentUrl": "https://cdn.example.com/open-cdata.mp4"}
      </script>
      <script type="application/ld+json">{&quot;@type&quot;:&quot;VideoObject&quot;,&quot;contentUrl&quot;:&quot;https://cdn.example.com/escaped.mp4&quot;}</script>
    </body></html>
    """
    both_found = discover(_source(), profile, html=both)
    both_urls = [item.retrieval_urls[0] for item in both_found if item.retrieval_urls]
    assert "https://example.com/watch?v=1" in both_urls
    assert "https://cdn.example.com/direct.mp4" in both_urls
    assert "https://cdn.example.com/charset.mp4" in both_urls
    assert "https://cdn.example.com/commented.mp4" in both_urls
    assert "https://cdn.example.com/open-comment.mp4" in both_urls
    assert "https://cdn.example.com/cdata.mp4" in both_urls
    assert "https://cdn.example.com/open-cdata.mp4" in both_urls
    assert "https://cdn.example.com/escaped.mp4" in both_urls


def test_direct_png_skips_html() -> None:
    profile = get_profile("personal-full")
    source = MediaSource(
        kind=IntakeKind.URL,
        locator="https://cdn.example.com/a.png",
        normalized_url="https://cdn.example.com/a.png",
        surface=Surface.CLI,
        policy_profile_id="personal-full",
    )
    candidates = discover(source, profile)
    assert len(candidates) == 1
    assert candidates[0].media_kind is MediaKind.IMAGE
    assert candidates[0].identity_key.startswith("host:cdn.example.com")


def test_html_link_audio_image_track_and_jsonld_kinds() -> None:
    html = """
    <html>
      <head>
        <meta property="og:audio:secure_url" content="https://cdn.example.com/og.m4a">
        <link rel="preload" as="audio" href="https://cdn.example.com/a.mp3">
        <link rel="preload" as="image" href="https://cdn.example.com/i.png">
        <link rel="preload" as="track" href="https://cdn.example.com/t.vtt">
        <script type="application/ld+json">
          [
            {"@type": "AudioObject", "contentUrl": "https://example.com/listen"},
            {"@type": "ImageObject", "contentUrl": "https://example.com/photo"}
          ]
        </script>
      </head>
    </html>
    """
    profile = get_profile("personal-full")
    candidates = discover(_source(), profile, html=html)
    kinds = {item.retrieval_urls[0]: item.media_kind for item in candidates if item.retrieval_urls}
    assert kinds["https://cdn.example.com/og.m4a"] is MediaKind.AUDIO
    assert kinds["https://cdn.example.com/a.mp3"] is MediaKind.AUDIO
    assert kinds["https://cdn.example.com/i.png"] is MediaKind.IMAGE
    assert kinds["https://cdn.example.com/t.vtt"] is MediaKind.SUBTITLE
    assert kinds["https://example.com/listen"] is MediaKind.AUDIO
    assert kinds["https://example.com/photo"] is MediaKind.IMAGE


def test_html_discovery_amp_img_and_twitter_player() -> None:
    html = """
    <html>
      <head>
        <meta name="twitter:player" content="https://cdn.example.com/player.mp4">
      </head>
      <body>
        <amp-img src="https://cdn.example.com/amp.png"></amp-img>
      </body>
    </html>
    """
    profile = get_profile("personal-full")
    candidates = discover(_source(), profile, html=html)
    urls = [item.retrieval_urls[0] for item in candidates if item.retrieval_urls]
    kinds = {item.retrieval_urls[0]: item.media_kind for item in candidates if item.retrieval_urls}
    assert "https://cdn.example.com/amp.png" in urls
    assert "https://cdn.example.com/player.mp4" in urls
    assert kinds["https://cdn.example.com/amp.png"] is MediaKind.IMAGE
    assert kinds["https://cdn.example.com/player.mp4"] is MediaKind.VIDEO


def test_manifest_jsonl_skips_malformed_lines() -> None:
    source = _source()
    raw = (
        b'{"url":"https://cdn.example.com/a.mp4"}\n'
        b"not-json\n"
        b'{"webpage_url":"https://cdn.example.com/b.webm","formats":[{"format_id":"1"}]}\n'
        b'{"formats":[{"format_id":"x"}]}\n'
    )
    found = candidates_from_manifest_json(source, raw)
    urls = [item.retrieval_urls[0] for item in found]
    assert "https://cdn.example.com/a.mp4" in urls
    assert "https://cdn.example.com/b.webm" in urls
    assert source.normalized_url in urls


def test_page_discovery_http_error_non_html_and_jsonld_podcast() -> None:
    profile = get_profile("personal-full")
    with pytest.raises(DiscoveryError, match="HTTP 403"):
        discover(_source(), profile, fetch=lambda url: (403, "text/html", b"no"))
    with pytest.raises(DiscoveryError, match="fetch function"):
        discover(_source(), profile)
    sniffed = discover(
        _source(),
        profile,
        fetch=lambda url: (200, "application/octet-stream", b"\x00\x01not-html"),
    )
    assert sniffed[0].evidence_refs == ["intake:bytes"]
    html = """
    <html>
      <script type="application/ld+json">{not-json</script>
      <script type="application/ld+json">{&quot;not-json</script>
      <script type="application/ld+json">
        {"@type": "PodcastEpisode", "contentUrl": "https://cdn.example.com/episode"}
      </script>
    </html>
    """
    candidates = discover(_source(), profile, html=html)
    kinds = {item.retrieval_urls[0]: item.media_kind for item in candidates if item.retrieval_urls}
    assert kinds["https://cdn.example.com/episode"] is MediaKind.AUDIO
