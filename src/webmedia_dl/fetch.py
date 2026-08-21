"""Bounded HTTP fetch. Discovery size-caps HTML; acquisition fails closed on oversized bodies."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from webmedia_dl.domain.models import PolicyProfile
from webmedia_dl.errors import DiscoveryError, NetworkPolicyError
from webmedia_dl.network_policy import authorize_url

OverflowMode = Literal["truncate", "error"]


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.15, min=0.15, max=1.5),
    retry=retry_if_exception_type((httpx.TransportError, httpx.TimeoutException)),
)
def _send(client: httpx.Client, url: str) -> httpx.Response:
    return client.get(url)


def bound_fetch(
    url: str,
    *,
    profile: PolicyProfile,
    max_bytes: int | None = None,
    on_overflow: OverflowMode = "error",
    client: httpx.Client | None = None,
    timeout_s: float = 30.0,
    should_stop: Callable[[], None] | None = None,
) -> tuple[int, str, bytes]:
    """Return ``(status, content_type, body)`` under profile network and size bounds."""
    authorize_url(url, profile)
    limit = max_bytes if max_bytes is not None else profile.max_download_bytes
    own_client = client is None
    http = client or httpx.Client(
        follow_redirects=True,
        max_redirects=profile.max_redirects,
        timeout=timeout_s,
        headers={
            "User-Agent": "WebMedia-DL/0.1 (local-first; +https://github.com/wyattowalsh/webmedia-dl)"
        },
    )
    try:
        if should_stop is None:
            response = _send(http, url)
            content_type = response.headers.get("content-type", "")
            body = response.content
        else:
            should_stop()
            with http.stream("GET", url) as response:
                content_type = response.headers.get("content-type", "")
                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    should_stop()
                    total += len(chunk)
                    if total > limit:
                        if on_overflow == "truncate":
                            remain = limit - (total - len(chunk))
                            if remain > 0:
                                chunks.append(chunk[:remain])
                            body = b"".join(chunks)
                            return response.status_code, content_type, body
                        msg = f"Response from {url!r} exceeds the {limit} byte bound."
                        raise NetworkPolicyError(msg)
                    chunks.append(chunk)
                body = b"".join(chunks)
            return response.status_code, content_type, body
        if len(body) > limit:
            if on_overflow == "truncate":
                body = body[:limit]
            else:
                msg = f"Response from {url!r} exceeds the {limit} byte bound."
                raise NetworkPolicyError(msg)
        return response.status_code, content_type, body
    except httpx.TooManyRedirects as exc:
        raise NetworkPolicyError(f"Redirect bound exceeded for {url!r}.") from exc
    except httpx.HTTPError as exc:
        raise DiscoveryError(f"Fetch failed for {url!r}: {exc}") from exc
    finally:
        if own_client:
            http.close()


def fetch_fn_for_profile(
    profile: PolicyProfile,
    *,
    max_bytes: int | None = None,
    on_overflow: OverflowMode = "truncate",
    client: httpx.Client | None = None,
):
    def _fetch(url: str) -> tuple[int, str, bytes]:
        return bound_fetch(
            url,
            profile=profile,
            max_bytes=max_bytes if max_bytes is not None else profile.max_html_bytes,
            on_overflow=on_overflow,
            client=client,
        )

    return _fetch
