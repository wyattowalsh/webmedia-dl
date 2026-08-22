from pathlib import Path

import pytest

from webmedia_dl.errors import CookiePolicyError, DrmRefused
from webmedia_dl.live import inspect_manifest, recordable_segment_urls
from webmedia_dl.policy.profiles import get_profile
from webmedia_dl.security import detect_drm_signals, refuse_drm, resolve_cookie_path


@pytest.mark.parametrize("token", ["widevine", "fairplay", "playready"])
def test_named_drm_systems_refuse_closed(token: str) -> None:
    signals = detect_drm_signals(token)
    assert signals
    with pytest.raises(DrmRefused):
        refuse_drm(signals)


def test_clear_hls_allowed() -> None:
    text = "#EXTM3U\n#EXT-X-KEY:METHOD=NONE\nhttps://cdn.example.com/a.ts\n"
    inspect_manifest(text)
    urls = recordable_segment_urls(text, "https://cdn.example.com/live.m3u8")
    assert urls == ["https://cdn.example.com/a.ts"]


def test_encrypted_hls_refused() -> None:
    text = '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="https://example.com/key"\nseg.ts\n'
    with pytest.raises(DrmRefused):
        inspect_manifest(text)


def test_cookie_requires_absolute_existing_file_outside_repo(tmp_path: Path) -> None:
    profile = get_profile("personal-full")
    repo = tmp_path / "repo"
    repo.mkdir()
    with pytest.raises(CookiePolicyError):
        resolve_cookie_path(profile, "cookies.txt", repo_root=repo)
    inside = repo / "user-cookies.txt"
    inside.write_text("# netscape\n", encoding="utf-8")
    with pytest.raises(CookiePolicyError):
        resolve_cookie_path(profile, str(inside), repo_root=repo)
    outside = tmp_path / "outside-cookies.txt"
    outside.write_text("# netscape\n", encoding="utf-8")
    resolved = resolve_cookie_path(profile, str(outside), repo_root=repo)
    assert resolved == outside.resolve()


def test_restricted_profile_forbids_cookies() -> None:
    profile = get_profile("personal-restricted")
    with pytest.raises(CookiePolicyError):
        resolve_cookie_path(profile, "/tmp/cookies.txt")
