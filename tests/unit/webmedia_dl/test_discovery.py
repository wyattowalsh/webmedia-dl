from uuid import uuid4

from webmedia_dl.candidates import build_graph
from webmedia_dl.discovery import discover
from webmedia_dl.domain.enums import IntakeKind, MediaKind, Surface
from webmedia_dl.domain.models import MediaSource
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
