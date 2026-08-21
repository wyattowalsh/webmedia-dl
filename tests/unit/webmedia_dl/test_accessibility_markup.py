from webmedia_dl.paths import repo_root


def test_capture_popup_has_accessible_markup() -> None:
    root = repo_root()
    for browser in ("chromium", "chrome", "brave", "edge", "firefox", "safari"):
        html = (root / "extensions" / browser / "popup.html").read_text(encoding="utf-8")
        assert 'lang="en"' in html
        assert 'for="token"' in html
        assert 'role="status"' in html
        assert "aria-live" in html
        assert "Paste the token once" in html


def test_guide_has_accessible_markup() -> None:
    html = (repo_root() / "guide/index.html").read_text(encoding="utf-8")
    assert 'lang="en"' in html
    assert "<h1>" in html
    assert "aria-label" in html


def test_apple_views_have_accessibility_labels() -> None:
    root = repo_root()
    mac = (root / "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacApp.swift").read_text(
        encoding="utf-8"
    )
    assert "accessibilityLabel" in mac
    ios = (root / "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLiOSRootView.swift").read_text(
        encoding="utf-8"
    )
    assert "accessibilityLabel" in ios
