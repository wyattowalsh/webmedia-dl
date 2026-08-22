from html.parser import HTMLParser

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
    "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionShareView.swift",
]


class _PopupParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.html_lang: str | None = None
        self.label_for: list[str] = []
        self.input_ids: list[str] = []
        self.status_live = False
        self.focusable_buttons = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: value for key, value in attrs if value is not None}
        if tag == "html":
            self.html_lang = values.get("lang")
        elif tag == "label":
            target = values.get("for")
            if target:
                self.label_for.append(target)
        elif tag == "input":
            identity = values.get("id")
            if identity:
                self.input_ids.append(identity)
        elif tag == "button":
            self.focusable_buttons += 1
        if values.get("role") == "status" and values.get("aria-live"):
            self.status_live = True


def test_capture_popup_has_accessible_markup() -> None:
    root = repo_root()
    for browser in ("chromium", "chrome", "brave", "edge", "firefox", "safari"):
        html = (root / "extensions" / browser / "popup.html").read_text(encoding="utf-8")
        parser = _PopupParser()
        parser.feed(html)
        parser.close()
        assert parser.html_lang == "en", browser
        assert "token" in parser.label_for, browser
        assert "token" in parser.input_ids, browser
        assert parser.status_live, browser
        assert parser.focusable_buttons >= 1, browser


def test_guide_has_accessible_markup() -> None:
    html = (repo_root() / "guide/index.html").read_text(encoding="utf-8")
    parser = _PopupParser()
    parser.feed(html)
    parser.close()
    assert parser.html_lang == "en"
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
