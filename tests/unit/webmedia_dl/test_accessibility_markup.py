from pathlib import Path

from webmedia_dl.paths import repo_root


def test_capture_popup_has_accessible_markup() -> None:
    html = (repo_root() / "extensions/chromium/popup.html").read_text(encoding="utf-8")
    assert 'lang="en"' in html
    assert 'for="token"' in html
    assert 'role="status"' in html
    assert "aria-live" in html


def test_guide_has_accessible_markup() -> None:
    html = (repo_root() / "guide/index.html").read_text(encoding="utf-8")
    assert 'lang="en"' in html
    assert "<h1>" in html
    assert "aria-label" in html
