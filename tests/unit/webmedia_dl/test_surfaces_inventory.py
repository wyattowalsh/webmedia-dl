from webmedia_dl.capabilities import registry
from webmedia_dl.paths import repo_root
from webmedia_dl.providers import imagemagick_configure_path


def test_capability_registry_includes_live_and_ffmpeg() -> None:
    ids = {item.capability_id for item in registry()}
    assert "live.record_clear_manifest" in ids
    assert "process.ffmpeg.remux" in ids
    assert "acquire.ytdlp" in ids
    ytdlp = next(item for item in registry() if item.capability_id == "acquire.ytdlp")
    assert ytdlp.health in {"healthy", "missing"}


def test_apple_app_shells_exist() -> None:
    root = repo_root()
    expected = [
        "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacApp.swift",
        "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacShareView.swift",
        "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacSubmitURLIntent.swift",
        "apps/WebMediaDLMac/Resources/Info.plist",
        "apps/WebMediaDLMac/ShareExtension/Info.plist",
        "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLiOSRootView.swift",
        "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLSubmitURLIntent.swift",
        "apps/WebMediaDLiOS/ShareExtension/Info.plist",
        "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSRootView.swift",
        "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSSubmitURLIntent.swift",
        "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSShareView.swift",
        "apps/WebMediaDLiPadOS/Resources/Info.plist",
        "apps/WebMediaDLiPadOS/ShareExtension/Info.plist",
        "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionRootView.swift",
        "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionSubmitURLIntent.swift",
        "apps/WebMediaDLVision/Resources/Info.plist",
        "apps/WebMediaDLWatch/Sources/WebMediaDLWatch/WebMediaDLWatchRootView.swift",
        "apps/WebMediaDLTV/Sources/WebMediaDLTV/WebMediaDLTVRootView.swift",
        "apps/WebMediaDLCore/Sources/WebMediaDLCore/LoopbackClient.swift",
        "apps/WebMediaDLCore/Sources/WebMediaDLCore/ShareIntake.swift",
        "apps/WebMediaDLCore/Sources/WebMediaDLCore/ContinuityBridge.swift",
        "extensions/safari/SafariWebExtensionHandler.swift",
    ]
    for rel in expected:
        path = root / rel
        assert path.is_file(), rel
        text = path.read_text(encoding="utf-8")
        assert (
            "127.0.0.1" in text
            or "WebMediaDLLoopbackClient" in text
            or "Loopback" in text
            or "captureAndStatus" in text
            or "canPublishToPhotos" in text
            or "AppIntent" in text
            or "ShareIntake" in text
            or "share-services" in text
            or "NSAppTransportSecurity" in text
            or "pauseQueueRequest" in text
            or "pairing" in text.lower()
        )
    watch = (
        root / "apps/WebMediaDLWatch/Sources/WebMediaDLWatch/WebMediaDLWatchRootView.swift"
    ).read_text(encoding="utf-8")
    assert "Not a subprocess worker" in watch
    assert "yt-dlp" not in watch
    continuity = (
        root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/ContinuityBridge.swift"
    ).read_text(encoding="utf-8")
    assert "isSubprocessWorker" in continuity
    assert "false" in continuity.lower() or "Bool { false }" in continuity
    tv = (root / "apps/WebMediaDLTV/Sources/WebMediaDLTV/WebMediaDLTVRootView.swift").read_text(
        encoding="utf-8"
    )
    assert "Not a subprocess worker" in tv


def test_browser_extension_trees() -> None:
    root = repo_root()
    for browser in ("chromium", "chrome", "brave", "edge", "firefox", "safari"):
        folder = root / "extensions" / browser
        assert (folder / "manifest.json").is_file()
        assert (folder / "popup.html").is_file()
        assert (folder / "capture.js").is_file()
        manifest = (folder / "manifest.json").read_text(encoding="utf-8")
        assert "127.0.0.1:8765" in manifest
        assert "nativeMessaging" not in manifest
        assert "scripting" in manifest
    assert (root / "extensions/safari/Info.plist").is_file()


def test_imagemagick_runtime_policy_exists() -> None:
    path = imagemagick_configure_path() / "policy.xml"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert 'domain="path"' in text
    assert "@*" in text


def test_pack_inventory_count() -> None:
    import json

    payload = json.loads((repo_root() / "scripts/pack_inventory.json").read_text(encoding="utf-8"))
    assert payload["count"] == 159
    assert len(payload["paths_relative"]) == 159
