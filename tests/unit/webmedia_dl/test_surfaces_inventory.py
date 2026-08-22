from __future__ import annotations

import json
import plistlib

from webmedia_dl.capabilities import registry
from webmedia_dl.paths import repo_root
from webmedia_dl.providers import imagemagick_configure_path

SHARE_PRINCIPALS = {
    "apps/WebMediaDLMac/ShareExtension": "WebMediaDLMacShareExtensionPrincipal",
    "apps/WebMediaDLiOS/ShareExtension": "WebMediaDLiOSShareExtensionPrincipal",
    "apps/WebMediaDLiPadOS/ShareExtension": "WebMediaDLiPadOSShareExtensionPrincipal",
    "apps/WebMediaDLVision/ShareExtension": "WebMediaDLVisionShareExtensionPrincipal",
}

ROOT_VIEWS = {
    "macos": "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacApp.swift",
    "ios": "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLiOSRootView.swift",
    "ipados": "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSRootView.swift",
    "visionos": "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionRootView.swift",
    "watchos": "apps/WebMediaDLWatch/Sources/WebMediaDLWatch/WebMediaDLWatchRootView.swift",
    "tvos": "apps/WebMediaDLTV/Sources/WebMediaDLTV/WebMediaDLTVRootView.swift",
}

APP_ENTRIES = [
    "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacApp.swift",
    "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLiOSApp.swift",
    "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSApp.swift",
    "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionApp.swift",
    "apps/WebMediaDLWatch/Sources/WebMediaDLWatch/WebMediaDLWatchApp.swift",
    "apps/WebMediaDLTV/Sources/WebMediaDLTV/WebMediaDLTVApp.swift",
]

CREDENTIAL_ADAPTERS = [
    "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacSubmitURLIntent.swift",
    "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLSubmitURLIntent.swift",
    "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSSubmitURLIntent.swift",
    "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionSubmitURLIntent.swift",
    "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacShareView.swift",
    "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLiOSShareView.swift",
    "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSShareView.swift",
    "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionShareView.swift",
    "apps/WebMediaDLMac/ShareExtension/WebMediaDLMacShareExtension.swift",
    "apps/WebMediaDLiOS/ShareExtension/WebMediaDLiOSShareExtension.swift",
    "apps/WebMediaDLiPadOS/ShareExtension/WebMediaDLiPadOSShareExtension.swift",
    "apps/WebMediaDLVision/ShareExtension/WebMediaDLVisionShareExtension.swift",
    "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLiOSRootView.swift",
    "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSRootView.swift",
    "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionRootView.swift",
]

COMPANION_INTENTS = [
    "apps/WebMediaDLWatch/Sources/WebMediaDLWatch/WebMediaDLWatchSubmitURLIntent.swift",
    "apps/WebMediaDLTV/Sources/WebMediaDLTV/WebMediaDLTVSubmitURLIntent.swift",
]


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
        "apps/WebMediaDLMac/ShareExtension/WebMediaDLMacShareExtension.swift",
        "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLiOSRootView.swift",
        "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLiOSApp.swift",
        "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLSubmitURLIntent.swift",
        "apps/WebMediaDLiOS/ShareExtension/Info.plist",
        "apps/WebMediaDLiOS/ShareExtension/WebMediaDLiOSShareExtension.swift",
        "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSRootView.swift",
        "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSApp.swift",
        "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSSubmitURLIntent.swift",
        "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSShareView.swift",
        "apps/WebMediaDLiPadOS/Resources/Info.plist",
        "apps/WebMediaDLiPadOS/ShareExtension/Info.plist",
        "apps/WebMediaDLiPadOS/ShareExtension/WebMediaDLiPadOSShareExtension.swift",
        "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionRootView.swift",
        "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionApp.swift",
        "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionSubmitURLIntent.swift",
        "apps/WebMediaDLVision/Resources/Info.plist",
        "apps/WebMediaDLVision/ShareExtension/Info.plist",
        "apps/WebMediaDLVision/ShareExtension/WebMediaDLVisionShareExtension.swift",
        "apps/WebMediaDLWatch/Sources/WebMediaDLWatch/WebMediaDLWatchRootView.swift",
        "apps/WebMediaDLWatch/Sources/WebMediaDLWatch/WebMediaDLWatchApp.swift",
        "apps/WebMediaDLWatch/Resources/Info.plist",
        "apps/WebMediaDLTV/Sources/WebMediaDLTV/WebMediaDLTVRootView.swift",
        "apps/WebMediaDLTV/Sources/WebMediaDLTV/WebMediaDLTVApp.swift",
        "apps/WebMediaDLTV/Resources/Info.plist",
        "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionShareView.swift",
        "apps/WebMediaDLCore/Sources/WebMediaDLCore/LoopbackClient.swift",
        "apps/WebMediaDLCore/Sources/WebMediaDLCore/Destinations.swift",
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
            or "SecurityScopedBookmark" in text
            or "canPublish" in text
            or "@main" in text
            or "NSExtensionRequestHandling" in text
        )
    watch = (
        root / "apps/WebMediaDLWatch/Sources/WebMediaDLWatch/WebMediaDLWatchRootView.swift"
    ).read_text(encoding="utf-8")
    assert "Not a subprocess worker" in watch
    assert "yt-dlp" not in watch
    assert "Cancel last job" in watch or "Cancel" in watch
    assert "Resume" in watch
    assert "Queue status" in watch
    assert "Mac relay" in watch
    safari_handler = (root / "extensions/safari/SafariWebExtensionHandler.swift").read_text(
        encoding="utf-8"
    )
    assert "URLSession.shared.dataTask" in safari_handler
    assert "Authorization" in safari_handler
    assert "browser_evidence" in safari_handler
    assert "nativeCommand" in safari_handler
    assert '"nativeCommand"' not in safari_handler
    assert "NSExtensionRequestHandling" in safari_handler
    assert "beginRequest(with context: NSExtensionContext)" in safari_handler
    assert "beginRequest(with item: Any?)" not in safari_handler
    continuity = (
        root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/ContinuityBridge.swift"
    ).read_text(encoding="utf-8")
    assert "isSubprocessWorker" in continuity
    assert "false" in continuity.lower() or "Bool { false }" in continuity
    assert "companion" in continuity.lower()
    assert "nativeCommand" in continuity
    assert "WebMediaDLCompanionRelay" in continuity
    assert "WebMediaDLContinuityBridge" in continuity
    mac = (root / "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacApp.swift").read_text(
        encoding="utf-8"
    )
    assert "onDrop" in mac
    assert "Drop media files" in mac
    tv = (root / "apps/WebMediaDLTV/Sources/WebMediaDLTV/WebMediaDLTVRootView.swift").read_text(
        encoding="utf-8"
    )
    assert "Not a subprocess worker" in tv
    assert "Cancel last job" in tv
    assert "Queue status" in tv
    assert "Mac relay" in tv
    ipad = (
        root / "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSRootView.swift"
    ).read_text(encoding="utf-8")
    vision = (
        root / "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionRootView.swift"
    ).read_text(encoding="utf-8")
    assert "Refresh history" in ipad
    assert "Refresh history" in vision
    assert "Job history" in ipad
    assert "Job history" in vision
    mac_share = (
        root / "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacShareView.swift"
    ).read_text(encoding="utf-8")
    ios_share = (
        root / "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLiOSShareView.swift"
    ).read_text(encoding="utf-8")
    assert ".submit(" in mac_share
    assert ".submit(" in ios_share
    mac_intent = (
        root / "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacSubmitURLIntent.swift"
    ).read_text(encoding="utf-8")
    assert "await client.submit" in mac_intent
    assert "AppShortcutsProvider" in mac_intent
    assert "Speak a media URL" in mac_intent
    assert 'intakeKind: "share_sheet"' in mac_share
    assert 'intakeKind: "share_sheet"' in ios_share
    assert "Cancel last job" in mac
    assert "Pause last job" in mac
    assert "Resume last job" in mac
    assert "Choose Files destination" in mac
    assert "WebMediaDLClipboardIntake" in mac
    assert "Paste from clipboard" in mac
    assert "Paste from clipboard" in ipad
    assert "Paste from clipboard" in vision
    assert "Pause last job" in ipad
    assert "Resume last job" in ipad
    assert "Pause last job" in vision
    assert "Resume last job" in vision
    assert "Pause queue" in ipad
    assert "Pause queue" in vision
    assert "Pause last job" in tv
    assert "Resume last job" in tv
    assert "pause_job" in watch
    ios = (root / "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLiOSRootView.swift").read_text(
        encoding="utf-8"
    )
    assert "Paste from clipboard" in ios
    assert "Pause last job" in ios
    assert "Resume last job" in ios
    assert "Approved Files destination" in ios
    assert "Approved Files destination" in ipad
    assert "Approved Files destination" in vision
    assert 'TextField("Approved Files destination"' not in ios
    assert 'TextField("Approved Files destination"' not in ipad
    assert 'TextField("Approved Files destination"' not in vision
    assert "NSExtensionActivationRule" in (
        root / "apps/WebMediaDLMac/ShareExtension/Info.plist"
    ).read_text(encoding="utf-8")
    assert "NSExtensionActivationRule" in (
        root / "apps/WebMediaDLVision/ShareExtension/Info.plist"
    ).read_text(encoding="utf-8")
    assert "sealedCompanionRequest" in (
        root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/LoopbackClient.swift"
    ).read_text(encoding="utf-8")
    assert "sealedCompanionRequest" in continuity
    assert "func jobId(from" in (
        root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/LoopbackClient.swift"
    ).read_text(encoding="utf-8")
    destinations = (
        root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/Destinations.swift"
    ).read_text(encoding="utf-8")
    assert "WebMediaDLSecurityScopedBookmark" in destinations
    assert "if trimmed.isEmpty { return false }" in destinations
    assert "libraryWriteAvailable" in destinations
    assert "exposesProviderConsole" in destinations
    assert "WebMediaDLShareItemExtractor" in destinations
    assert "fromShared" in destinations
    mac_share_ext = (
        root / "apps/WebMediaDLMac/ShareExtension/WebMediaDLMacShareExtension.swift"
    ).read_text(encoding="utf-8")
    assert "share_sheet" in mac_share_ext
    assert "yt-dlp" not in mac_share_ext


def test_share_extension_principals_match_plists() -> None:
    root = repo_root()
    for rel, principal in SHARE_PRINCIPALS.items():
        plist_path = root / rel / "Info.plist"
        source_path = next((root / rel).glob("*.swift"))
        payload = plistlib.loads(plist_path.read_bytes())
        extension = payload["NSExtension"]
        assert extension["NSExtensionPointIdentifier"] == "com.apple.share-services"
        assert extension["NSExtensionPrincipalClass"] == principal
        source = source_path.read_text(encoding="utf-8")
        assert f"@objc({principal})" in source
        assert "NSExtensionRequestHandling" in source
        assert "beginRequest(with context: NSExtensionContext)" in source
        assert 'intakeKind: "share_sheet"' in source
        assert 'intakeKind: "drop"' in source
        assert "NSItemProvider" in source or "attachments" in source or "loadSharedValues" in source
    for package, share in (
        ("apps/WebMediaDLMac/Package.swift", "WebMediaDLMacShareExtension"),
        ("apps/WebMediaDLiOS/Package.swift", "WebMediaDLiOSShareExtension"),
        ("apps/WebMediaDLiPadOS/Package.swift", "WebMediaDLiPadOSShareExtension"),
        ("apps/WebMediaDLVision/Package.swift", "WebMediaDLVisionShareExtension"),
    ):
        text = (root / package).read_text(encoding="utf-8")
        assert 'path: "ShareExtension"' in text
        assert f'.library(name: "{share}"' in text
        assert f'"{share}"' in text


def test_files_destinations_use_bookmarks_not_typed_paths() -> None:
    root = repo_root()
    destinations = (
        root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/Destinations.swift"
    ).read_text(encoding="utf-8")
    assert "bookmarkData" in destinations
    assert "fromPickedURL" in destinations
    assert ".withSecurityScope" in destinations
    assert ".minimalBookmark" in destinations
    assert "HTTPS stays a URL; file paths use drop intake" in destinations
    assert "static func locators(fromShared" in destinations
    assert "static func dropPaths(fromShared" in destinations
    assert 'hasPrefix("file://")' in destinations
    assert 'hasPrefix("https://")' in destinations
    mac = (root / "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacApp.swift").read_text(
        encoding="utf-8"
    )
    assert "fromPickedURL" in mac
    assert "bookmarkData" in mac
    share_intake = (
        root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/ShareIntake.swift"
    ).read_text(encoding="utf-8")
    assert "bookmarkData: bookmarkData" in share_intake
    assert "bookmarkData: Data? = nil" in share_intake
    for rel in (
        ROOT_VIEWS["ios"],
        ROOT_VIEWS["ipados"],
        ROOT_VIEWS["visionos"],
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "fileImporter" in text
        assert "fromPickedURL" in text
        assert "Choose Files destination" in text
        assert 'TextField("Approved Files destination"' not in text
        assert "bookmarkData: filesBookmark.bookmarkData" in text
        assert "loadBookmark()" in text


def test_companion_transport_and_typed_history() -> None:
    root = repo_root()
    continuity = (
        root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/ContinuityBridge.swift"
    ).read_text(encoding="utf-8")
    assert "enum WebMediaDLCompanionKind" in continuity
    for case in (
        "    case capture\n",
        "    case pause\n",
        "    case resume\n",
        "    case history\n",
        "    case status\n",
        "    case cancel\n",
        '    case pauseJob = "pause_job"\n',
        '    case resumeJob = "resume_job"\n',
    ):
        assert case in continuity
    assert "encodeNil(forKey: .nativeCommand)" in continuity
    assert 'nativeCommand": NSNull()' in continuity
    assert "func dictionary() -> [String: Any]" in continuity
    assert "protocol WebMediaDLCompanionTransport" in continuity
    assert "struct WebMediaDLQueuedCompanionTransport" in continuity
    assert "WCSessionDelegate" in continuity
    assert "extension WebMediaDLWatchConnectivityTransport: WCSessionDelegate" in continuity
    assert "extension WebMediaDLMacWatchConnectivityDelegate: WCSessionDelegate" in continuity
    assert continuity.count("#if os(iOS) || os(macOS) || os(visionOS)") == 2
    assert "sessionDidBecomeInactive" in continuity
    assert "sessionDidDeactivate" in continuity
    assert continuity.count("public final class WebMediaDLWatchConnectivityTransport:") == 1
    assert continuity.count("public final class WebMediaDLMacWatchConnectivityDelegate:") == 1
    assert "#else\npublic final class WebMediaDLWatchConnectivityTransport" not in continuity
    assert "#else\npublic final class WebMediaDLMacWatchConnectivityDelegate" not in continuity
    assert "WCSession.default.delegate" in continuity
    assert "activate()" in continuity
    assert "func activateSession()" in continuity
    assert "didReceiveUserInfo" in continuity
    assert "func sendResponse(" in continuity
    assert "struct WebMediaDLMacCompanionForwarder" in continuity
    assert "func send(_ message: WebMediaDLCompanionMessage)" in continuity
    assert "func forward(" in continuity
    assert "func forward(_ relay: WebMediaDLCompanionRelay)" in continuity
    assert "func forward(_ relay: inout" not in continuity
    assert "_ relay: inout WebMediaDLCompanionRelay" not in continuity
    assert "receiveWatchConnectivityUserInfo" in continuity
    assert "var surface:" in continuity
    watch = (root / ROOT_VIEWS["watchos"]).read_text(encoding="utf-8")
    tv = (root / ROOT_VIEWS["tvos"]).read_text(encoding="utf-8")
    assert "WebMediaDLWatchConnectivityTransport" in watch
    assert "WebMediaDLWatchConnectivityTransport" in tv
    assert 'Data("[]".utf8)' not in watch
    assert 'Data("[]".utf8)' not in tv
    assert "decodeCompanionHistory" in watch
    assert "decodeCompanionHistory" in tv
    assert "surface: .watchos" in watch
    assert "surface: .tvos" in tv
    assert "WebMediaDLClipboardIntake" in tv
    assert "UIPasteboard" not in tv
    assert "Capture URL" in tv
    assert "transport.send" in watch
    assert "transport.send" in tv
    assert "activateSession()" in watch
    assert "activateSession()" in tv
    assert "lastResponse" in watch
    assert "lastResponse" in tv
    assert "status.data(using: .utf8)" not in watch
    assert "status.data(using: .utf8)" not in tv
    assert "relay.enqueue" not in watch
    assert "relay.enqueue" not in tv
    mac = (root / ROOT_VIEWS["macos"]).read_text(encoding="utf-8")
    assert "WebMediaDLMacCompanionForwarder" in mac
    assert "receiveWatchConnectivityUserInfo" in mac
    assert "forwarder.forward" in mac
    assert "activateSession()" in mac
    assert "loadBookmark()" in mac
    assert "sessionKey: token" not in mac
    assert 'nonce: "wrap"' not in mac
    assert "forwardSealed(" in mac
    assert "var relay = companionRelay" in mac
    assert "companionRelay = WebMediaDLCompanionRelay()" in mac
    assert "&companionRelay" not in mac
    assert "sessionKey: sessionKey" in mac
    assert "sendResponse(" in mac
    assert "sessionKey(from:" in mac
    assert mac.count("@State private var historyText") == 1
    assert mac.count("@State private var companionLocator") == 1
    loopback = (root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/LoopbackClient.swift").read_text(
        encoding="utf-8"
    )
    assert "func historyEntries() async throws -> [WebMediaDLHistoryEntry]" in loopback
    assert "func pairRequest(" in loopback
    assert "WebMediaDLPairingChallenge" in loopback or "startPairing" in loopback
    assert "does not require a stored worker token" in loopback
    assert "func sessionKey(from" in loopback
    assert "func jsonObject(from" in loopback
    assert "func derivedSessionKey(nonce" in loopback
    assert 'Data("\\(nonce):\\(confirmation)".utf8)' in loopback
    assert "lastResponse" in continuity
    assert "UserDefaults(suiteName:" in loopback
    assert "group.local.webmedia-dl" in loopback
    assert "func loadBookmark(" in loopback
    assert "data(forKey: bookmarkDefaultsKey)" in loopback
    assert "security_scoped_bookmark" in loopback
    assert "resolvingBookmarkData" in (
        root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/Destinations.swift"
    ).read_text(encoding="utf-8")
    assert "standardizedPath" in (
        root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/Destinations.swift"
    ).read_text(encoding="utf-8")
    assert "CLOSED:" in (
        root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/Destinations.swift"
    ).read_text(encoding="utf-8")
    assert "withCheckedContinuation" in (
        root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/Destinations.swift"
    ).read_text(encoding="utf-8")
    mac = (root / ROOT_VIEWS["macos"]).read_text(encoding="utf-8")
    assert "forwardSealed(" in mac
    assert "WebMediaDLWorkerCredentials.loadBookmark()" in mac
    for rel in ("ios", "ipados", "visionos"):
        text = (root / ROOT_VIEWS[rel]).read_text(encoding="utf-8")
        assert "Start pairing" in text
        assert "startPairing" in text
        assert "clip.intakeKind" in text
        assert "onAppear" in text
        assert "loadBookmark()" in text
        assert "bookmarkData: filesBookmark.bookmarkData" in text
        assert "defaults.string(forKey: WebMediaDLWorkerCredentials.pairingDefaultsKey)" in text
        assert "defaults.string(forKey: WebMediaDLWorkerCredentials.sessionDefaultsKey)" in text
        assert "Pause queue" in text
        assert "Resume queue" in text
        assert "bookmarkDefaultsKey" in text
        assert "derivedSessionKey(nonce:" in text
        assert "challenge.nonce)." not in text
    watch = (root / ROOT_VIEWS["watchos"]).read_text(encoding="utf-8")
    tv = (root / ROOT_VIEWS["tvos"]).read_text(encoding="utf-8")
    assert "history.first?.jobId" in watch
    assert "history.first?.jobId" in tv
    assert "jobId(from:" in watch
    assert "jobId(from:" in tv
    assert "lastJobId = nil" not in watch
    assert "lastJobId = nil" not in tv
    watch_plist = plistlib.loads((root / "apps/WebMediaDLWatch/Resources/Info.plist").read_bytes())
    assert watch_plist["CFBundleIdentifier"] == "local.webmedia-dl.watch"
    assert watch_plist["WKApplication"] is True
    tv_plist = plistlib.loads((root / "apps/WebMediaDLTV/Resources/Info.plist").read_bytes())
    assert tv_plist["CFBundleIdentifier"] == "local.webmedia-dl.tv"
    for rel in (
        "apps/WebMediaDLMac/Resources/WebMediaDL.entitlements",
        "apps/WebMediaDLiOS/Resources/WebMediaDL.entitlements",
        "apps/WebMediaDLiPadOS/Resources/WebMediaDL.entitlements",
        "apps/WebMediaDLVision/Resources/WebMediaDL.entitlements",
        "apps/WebMediaDLWatch/Resources/WebMediaDL.entitlements",
        "apps/WebMediaDLTV/Resources/WebMediaDL.entitlements",
        "apps/WebMediaDLMac/ShareExtension/WebMediaDL.entitlements",
        "apps/WebMediaDLiOS/ShareExtension/WebMediaDL.entitlements",
        "apps/WebMediaDLiPadOS/ShareExtension/WebMediaDL.entitlements",
        "apps/WebMediaDLVision/ShareExtension/WebMediaDL.entitlements",
    ):
        payload = plistlib.loads((root / rel).read_bytes())
        assert "group.local.webmedia-dl" in payload["com.apple.security.application-groups"]
    for rel in (
        "apps/WebMediaDLMac/Resources/Info.plist",
        "apps/WebMediaDLiOS/Resources/Info.plist",
        "apps/WebMediaDLiPadOS/Resources/Info.plist",
        "apps/WebMediaDLVision/Resources/Info.plist",
        "apps/WebMediaDLWatch/Resources/Info.plist",
        "apps/WebMediaDLTV/Resources/Info.plist",
    ):
        info = plistlib.loads((root / rel).read_bytes())
        assert "NSPhotoLibraryAddUsageDescription" not in info
        assert "NSPhotoLibraryUsageDescription" not in info
    vision_share = (
        root / "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionShareView.swift"
    ).read_text(encoding="utf-8")
    assert 'accessibilityLabel("Shared locator")' in vision_share
    assert "WebMediaDLWorkerCredentials.loadClient()" in vision_share
    for rel in (
        "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacSubmitURLIntent.swift",
        "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLSubmitURLIntent.swift",
        "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSSubmitURLIntent.swift",
        "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionSubmitURLIntent.swift",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert 'intakeKind: "speak"' in text
        assert "AppShortcutsProvider" in text
        assert "public static let title" in text
        assert "public static var title" not in text
        assert "public static var appShortcuts: [AppShortcut]" in text
        assert "AppShortcut(" in text
        assert "[\n            AppShortcut(" not in text
        assert "[\n        AppShortcut(" not in text
        assert "),\n            AppShortcut(" not in text
    for rel in COMPANION_INTENTS:
        text = (root / rel).read_text(encoding="utf-8")
        assert 'intakeKind: "speak"' not in text
        assert "classifies the locator as `url`" in text
        assert "AppShortcutsProvider" in text
        assert "public static let title" in text
        assert "public static var title" not in text
        assert "public static var appShortcuts: [AppShortcut]" in text
        assert "AppShortcut(" in text
        assert "[\n            AppShortcut(" not in text
        assert "[\n        AppShortcut(" not in text
        assert "),\n            AppShortcut(" not in text
    for rel in SHARE_PRINCIPALS:
        sources = list((root / rel).glob("*ShareExtension.swift"))
        assert sources, rel
        text = sources[0].read_text(encoding="utf-8")
        assert "WebMediaDLShareExtensionLoader.loadSharedValues" in text
        assert "beginRequest(with context: NSExtensionContext)" in text
        assert 'URLQueryItem(name: "url"' not in text
        assert "form-urlencoded" not in text
    models = (root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/Models.swift").read_text(
        encoding="utf-8"
    )
    assert "JSONDecoder()" in loopback
    assert "JSONDecoder()" in models
    for rel in ROOT_VIEWS.values():
        text = (root / rel).read_text(encoding="utf-8")
        assert "WebMediaDLHistoryEntry" in text
        assert "JSONDecoder()" in text or "decodeCompanionHistory" in text


def test_runtime_assets_match_authored_trees() -> None:
    root = repo_root()
    runtime = root / "src" / "webmedia_dl" / "runtime"
    authored = {
        "policy-profiles.json": root / "resources" / "policy-profiles.json",
        "export-presets.json": root / "resources" / "export-presets.json",
        "platform-capability-matrix.json": root / "resources" / "platform-capability-matrix.json",
        "imagemagick-runtime/policy.xml": root / "resources" / "imagemagick-runtime" / "policy.xml",
    }
    for rel, source in authored.items():
        packaged = runtime / rel
        assert packaged.read_bytes() == source.read_bytes(), rel
    for browser in ("chromium", "chrome", "brave", "edge", "firefox", "safari"):
        for name in ("capture.js", "popup.html", "popup.js", "manifest.json"):
            left = root / "extensions" / browser / name
            right = runtime / "extensions" / browser / name
            if left.is_file() and right.is_file():
                assert left.read_bytes() == right.read_bytes(), f"{browser}/{name}"


def test_platform_app_entry_points() -> None:
    root = repo_root()
    for rel in APP_ENTRIES:
        text = (root / rel).read_text(encoding="utf-8")
        assert "@main" in text
        assert ": App" in text or ":App" in text


def test_intents_and_share_adapters_load_credentials() -> None:
    root = repo_root()
    for rel in CREDENTIAL_ADAPTERS:
        text = (root / rel).read_text(encoding="utf-8")
        assert "WebMediaDLWorkerCredentials.loadClient()" in text
        assert "WebMediaDLLoopbackClient()" not in text
        assert "client.submit" in text or ".submit(" in text or "submitShared" in text
        assert "Process(" not in text
        assert "nativeCommand" not in text
        assert "providerArgv" not in text
    for rel in COMPANION_INTENTS:
        text = (root / rel).read_text(encoding="utf-8")
        assert "WebMediaDLWatchConnectivityTransport" in text
        assert "let transport" in text
        assert "var transport" not in text
        assert "transport.send" in text
        assert "loadClient()" not in text
        assert 'intakeKind: "speak"' not in text
        assert "Process(" not in text
    loopback = (root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/LoopbackClient.swift").read_text(
        encoding="utf-8"
    )
    submit = loopback.split("public func submitRequest(", 1)[1].split(
        "public func historyRequest(", 1
    )[0]
    assert "nativeCommand" not in submit
    assert "providerArgv" not in submit
    assert 'appendingPathComponent("v1/jobs")' in submit


def test_browser_extension_trees() -> None:
    root = repo_root()
    shared = (root / "extensions/shared/capture.js").read_bytes()
    for browser in ("chromium", "chrome", "brave", "edge", "firefox", "safari"):
        folder = root / "extensions" / browser
        assert (folder / "manifest.json").is_file()
        assert (folder / "popup.html").is_file()
        assert (folder / "capture.js").is_file()
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["host_permissions"] == ["http://127.0.0.1:8765/*"]
        assert "nativeMessaging" not in json.dumps(manifest)
        assert "scripting" in manifest["permissions"]
        assert (folder / "capture.js").read_bytes() == shared
    safari_plist = plistlib.loads((root / "extensions/safari/Info.plist").read_bytes())
    assert safari_plist["NSExtension"]["NSExtensionPrincipalClass"] == "SafariWebExtensionHandler"
    handler = (root / "extensions/safari/SafariWebExtensionHandler.swift").read_text(
        encoding="utf-8"
    )
    assert "@objc(SafariWebExtensionHandler)" in handler


def test_imagemagick_runtime_policy_exists() -> None:
    path = imagemagick_configure_path() / "policy.xml"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert 'domain="path"' in text
    assert 'domain="delegate"' in text
    assert "MSL" in text
    assert "MVG" in text
    assert "@*" in text


def test_pack_inventory_count() -> None:
    payload = json.loads((repo_root() / "scripts/pack_inventory.json").read_text(encoding="utf-8"))
    assert payload["count"] == 159
    assert len(payload["paths_relative"]) == 159


def test_github_ci_compiles_apple_packages() -> None:
    workflow = (repo_root() / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    script = (repo_root() / "scripts/build_apple_packages.sh").read_text(encoding="utf-8")
    assert "runs-on: macos-15" in workflow
    assert "bash scripts/build_apple_packages.sh" in workflow
    assert "if: false" not in workflow
    assert "swift test --package-path" in script
    assert "apps/WebMediaDLCore" in script
    assert "swift build --package-path" in script
    assert "apps/WebMediaDLMac" in script
    assert "--target WebMediaDLMacShareExtension" in script
    assert "xcodebuild -list" in script
    assert "library product + target dependency" in script
    assert 'generic/platform=iOS"' in script or "generic/platform=iOS" in script
    assert "generic/platform=watchOS" in script
    assert "generic/platform=tvOS" in script
    assert "generic/platform=visionOS" in script
    for scheme in (
        "WebMediaDLiOS",
        "WebMediaDLiOSShareExtension",
        "WebMediaDLiPadOS",
        "WebMediaDLiPadOSShareExtension",
        "WebMediaDLVision",
        "WebMediaDLVisionShareExtension",
        "WebMediaDLWatch",
        "WebMediaDLTV",
    ):
        assert scheme in script
    contracts = (
        repo_root() / "apps/WebMediaDLCore/Tests/WebMediaDLCoreTests/ContractTests.swift"
    ).read_text(encoding="utf-8")
    assert "testCompanionMessageRejectsNativeCommand" in contracts
    assert 'nativeCommand": "yt-dlp"' in contracts
    assert "libraryWriteAvailable" in contracts
    assert "titleUsedAsIdentity" in contracts
    assert "WebMediaDLUncheckedBox" in (
        repo_root() / "apps/WebMediaDLCore/Sources/WebMediaDLCore/Models.swift"
    ).read_text(encoding="utf-8")
    for rel in (
        "apps/WebMediaDLMac/ShareExtension/WebMediaDLMacShareExtension.swift",
        "apps/WebMediaDLiOS/ShareExtension/WebMediaDLiOSShareExtension.swift",
        "apps/WebMediaDLiPadOS/ShareExtension/WebMediaDLiPadOSShareExtension.swift",
        "apps/WebMediaDLVision/ShareExtension/WebMediaDLVisionShareExtension.swift",
    ):
        assert "WebMediaDLUncheckedBox(context)" in (repo_root() / rel).read_text(encoding="utf-8")
    continuity = (
        repo_root() / "apps/WebMediaDLCore/Sources/WebMediaDLCore/ContinuityBridge.swift"
    ).read_text(encoding="utf-8")
    assert "compactMapValues { $0 is NSNull ? nil : $0 }" in continuity
    for rel, name in (
        ("apps/WebMediaDLiOS/Package.swift", "WebMediaDLiOS"),
        ("apps/WebMediaDLiPadOS/Package.swift", "WebMediaDLiPadOS"),
        ("apps/WebMediaDLVision/Package.swift", "WebMediaDLVision"),
        ("apps/WebMediaDLWatch/Package.swift", "WebMediaDLWatch"),
        ("apps/WebMediaDLTV/Package.swift", "WebMediaDLTV"),
        ("apps/WebMediaDLMac/Package.swift", "WebMediaDLMac"),
    ):
        text = (repo_root() / rel).read_text(encoding="utf-8")
        assert f'.executable(name: "{name}"' in text
        assert ".executableTarget(" in text
        assert f'.library(name: "{name}",' not in text
        assert f'.library(name: "{name}")' not in text
        share = f"{name}ShareExtension"
        if "ShareExtension" in text:
            assert f'.library(name: "{share}"' in text
            assert f'"{share}"' in text
    assert "testHttpDirectSavesClearMediaAndRefusesDrm" in contracts
    assert "TransferError.overflow" in contracts
    assert "invalidLocator" in contracts
    assert "testDomainInvariantsFailClosed" in contracts
    assert "WebMediaDLPipelineJob" in contracts
    assert "container_only" in contracts


def test_complete_clients_http_direct_and_shared_domain() -> None:
    root = repo_root()
    domain = (root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/Domain.swift").read_text(
        encoding="utf-8"
    )
    http_direct = (root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/HttpDirect.swift").read_text(
        encoding="utf-8"
    )
    assert "A source URL never becomes a filesystem path." in domain
    assert "A display title never becomes artifact identity." in domain
    assert "A provider never receives arbitrary user arguments." in domain
    assert "A planned or simulated check never becomes runtime PASS." in domain
    assert "DRM circumvention is forbidden." in domain
    assert 'capabilityId: "acquire.http"' in domain
    assert 'providerId: "http-direct"' in domain
    assert 'capabilityId: "acquire.ytdlp"' in domain
    assert "WebMediaDLCapabilityRegistry" in domain
    assert "required_entitlements" in domain
    assert "network_schemes" in domain
    assert "include_original" in domain
    assert "parent_ids" in domain
    assert "WebMediaDLPipelineJob" in domain
    assert "WebMediaDLOperation" in domain
    assert "never launches yt-dlp, ffmpeg, or gallery-dl" in http_direct
    assert "Process(" not in http_direct
    assert 'providerId = "http-direct"' in http_direct
    assert "isOnDeviceTransfer" in http_direct
    assert "liveRequiresMac" in http_direct
    assert "pairingRequired" in http_direct
    assert "drmRefused" in http_direct
    assert "saveIfDirect" in http_direct
    assert "outputStem" in http_direct
    assert "URLSession.shared.bytes" in http_direct
    assert "data.count >= maxBytes" in http_direct
    assert "TransferError.overflow" in http_direct
    assert "unsupportedSurface" in http_direct
    assert "WebMediaDLCapabilityRegistry.allows(.acquireHTTP, on: surface)" in http_direct
    ios = (root / ROOT_VIEWS["ios"]).read_text(encoding="utf-8")
    ipad = (root / ROOT_VIEWS["ipados"]).read_text(encoding="utf-8")
    vision = (root / ROOT_VIEWS["visionos"]).read_text(encoding="utf-8")
    watch = (root / ROOT_VIEWS["watchos"]).read_text(encoding="utf-8")
    tv = (root / ROOT_VIEWS["tvos"]).read_text(encoding="utf-8")
    mac = (root / ROOT_VIEWS["macos"]).read_text(encoding="utf-8")
    for text in (ios, ipad, vision):
        assert "Save on this device" in text
        assert "WebMediaDLHttpDirect.transfer" in text
        assert "Lightweight HTTP jobs stay on-device" in text
        assert "Send to paired Mac" in text
    assert "Save on this device" not in watch
    assert "Save on this device" not in tv
    assert "WebMediaDLHttpDirect" not in watch
    assert "WebMediaDLHttpDirect" not in tv
    assert "UIPasteboard" not in tv
    assert "autoForward = true" in mac
    assert "bindWatchDelegate" in mac
    continuity = (
        root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/ContinuityBridge.swift"
    ).read_text(encoding="utf-8")
    assert "public var autoForward" in continuity
    assert "forwardSealed" in continuity
    for rel in (
        "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLSubmitURLIntent.swift",
        "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSSubmitURLIntent.swift",
        "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionSubmitURLIntent.swift",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "WebMediaDLHttpDirect.saveIfDirect" in text
        assert "WebMediaDLWorkerCredentials.loadClient()" in text
    for rel, surface in (
        ("apps/WebMediaDLiOS/ShareExtension/WebMediaDLiOSShareExtension.swift", ".ios"),
        ("apps/WebMediaDLiPadOS/ShareExtension/WebMediaDLiPadOSShareExtension.swift", ".ipados"),
        ("apps/WebMediaDLVision/ShareExtension/WebMediaDLVisionShareExtension.swift", ".visionos"),
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "WebMediaDLHttpDirect.saveIfDirect" in text
        assert f"surface: {surface}" in text
    mac_share = (
        root / "apps/WebMediaDLMac/ShareExtension/WebMediaDLMacShareExtension.swift"
    ).read_text(encoding="utf-8")
    assert "WebMediaDLHttpDirect" not in mac_share
