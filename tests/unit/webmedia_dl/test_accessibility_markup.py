from webmedia_dl.paths import repo_root

ROOT_VIEWS = [
    "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacApp.swift",
    "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLiOSRootView.swift",
    "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSRootView.swift",
    "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionRootView.swift",
    "apps/WebMediaDLWatch/Sources/WebMediaDLWatch/WebMediaDLWatchRootView.swift",
    "apps/WebMediaDLTV/Sources/WebMediaDLTV/WebMediaDLTVRootView.swift",
]

SHARE_VIEWS = [
    "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacShareView.swift",
    "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLiOSShareView.swift",
    "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSShareView.swift",
]


def test_capture_popup_has_accessible_markup() -> None:
    root = repo_root()
    for browser in ("chromium", "chrome", "brave", "edge", "firefox", "safari"):
        html = (root / "extensions" / browser / "popup.html").read_text(encoding="utf-8")
        assert 'lang="en"' in html
        assert 'for="token"' in html
        assert 'role="status"' in html
        assert "aria-live" in html
        assert "Paste the token once" in html
        assert "<button" in html


def test_guide_has_accessible_markup() -> None:
    html = (repo_root() / "guide/index.html").read_text(encoding="utf-8")
    assert 'lang="en"' in html
    assert "<h1>" in html
    assert "aria-label" in html


def test_apple_views_have_accessibility_labels() -> None:
    root = repo_root()
    for rel in ROOT_VIEWS:
        text = (root / rel).read_text(encoding="utf-8")
        assert "accessibilityLabel" in text, rel
        assert 'accessibilityLabel("Media URL")' in text, rel
        assert (
            'accessibilityLabel("Job status")' in text
            or 'accessibilityLabel("Watch status")' in text
        ), rel
        assert "Job history" in text or 'accessibilityLabel("History")' in text, rel
    for rel in SHARE_VIEWS:
        text = (root / rel).read_text(encoding="utf-8")
        assert "accessibilityLabel" in text, rel
        assert 'accessibilityLabel("Shared locator")' in text, rel
