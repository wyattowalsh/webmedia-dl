from pathlib import Path

import httpx
import pytest

from webmedia_dl.errors import DiscoveryError, NetworkPolicyError, PauseRequested
from webmedia_dl.fetch import bound_fetch
from webmedia_dl.policy.profiles import get_profile


def test_bound_fetch_truncates_html(tmp_path: Path) -> None:
    profile = get_profile("personal-full")
    profile = profile.model_copy(update={"max_html_bytes": 8, "max_redirects": 2})

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="0123456789abcdef", headers={"content-type": "text/html"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    status, content_type, body = bound_fetch(
        "https://example.com/page",
        profile=profile,
        max_bytes=profile.max_html_bytes,
        on_overflow="truncate",
        client=client,
    )
    assert status == 200
    assert "html" in content_type
    assert body == b"01234567"


def test_bound_fetch_errors_on_oversized_media() -> None:
    profile = get_profile("personal-full")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * 32, headers={"content-type": "video/mp4"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    with pytest.raises(NetworkPolicyError):
        bound_fetch(
            "https://cdn.example.com/a.mp4",
            profile=profile,
            max_bytes=8,
            on_overflow="error",
            client=client,
        )


def test_bound_fetch_rejects_javascript_scheme() -> None:
    with pytest.raises(NetworkPolicyError):
        bound_fetch("javascript:alert(1)", profile=get_profile("personal-full"))


def test_bound_fetch_stop_during_stream() -> None:
    profile = get_profile("personal-full")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"abcdefghij", headers={"content-type": "video/mp4"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    seen = {"n": 0}

    def should_stop() -> None:
        seen["n"] += 1
        if seen["n"] > 1:
            raise PauseRequested("stop mid-stream")

    with pytest.raises(PauseRequested, match="mid-stream"):
        bound_fetch(
            "https://cdn.example.com/a.mp4",
            profile=profile,
            max_bytes=64,
            client=client,
            should_stop=should_stop,
        )


def test_bound_fetch_stream_truncates() -> None:
    profile = get_profile("personal-full")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"0123456789abcdef", headers={"content-type": "text/html"}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    status, _content_type, body = bound_fetch(
        "https://example.com/page",
        profile=profile,
        max_bytes=8,
        on_overflow="truncate",
        client=client,
        should_stop=lambda: None,
    )
    assert status == 200
    assert body == b"01234567"


def test_bound_fetch_stream_errors_on_overflow() -> None:
    profile = get_profile("personal-full")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=b"0123456789abcdef", headers={"content-type": "video/mp4"}
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)
    with pytest.raises(NetworkPolicyError, match="byte bound"):
        bound_fetch(
            "https://cdn.example.com/a.mp4",
            profile=profile,
            max_bytes=8,
            on_overflow="error",
            client=client,
            should_stop=lambda: None,
        )


def test_bound_fetch_transport_error_becomes_discovery_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(DiscoveryError):
        bound_fetch(
            "https://example.com/page",
            profile=get_profile("personal-full"),
            client=client,
        )


def test_authorize_url_rejects_non_https_and_hostless() -> None:
    from webmedia_dl.network_policy import authorize_destination, authorize_url

    profile = get_profile("personal-full")
    with pytest.raises(NetworkPolicyError, match="data"):
        authorize_url("data:text/plain,x", profile)
    with pytest.raises(NetworkPolicyError, match="not allowed by profile"):
        authorize_url("http://example.com/a.mp4", profile)
    with pytest.raises(NetworkPolicyError, match="host"):
        authorize_url("https:///nohost", profile)
    with pytest.raises(NetworkPolicyError, match="approved root"):
        authorize_destination(Path("/tmp/out"), ["relative-root", "", " "])
