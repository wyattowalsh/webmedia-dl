from __future__ import annotations

import importlib.util
import json
import plistlib
import shutil
from pathlib import Path

import pytest

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
    assert ytdlp.health in {"healthy", "missing", "unhealthy"}


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
    assert "enum WebMediaDLJSONValue" in destinations
    assert "[String: WebMediaDLJSONValue]" in destinations
    assert "forbiddenEventKeys" in destinations
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
        assert payload["CFBundlePackageType"] == "XPC!"
        assert payload["CFBundleExecutable"] == source_path.stem
        source = source_path.read_text(encoding="utf-8")
        assert f"@objc({principal})" in source
        assert "NSExtensionRequestHandling" in source
        assert "beginRequest(with context: NSExtensionContext)" in source
        assert 'intakeKind: "share_sheet"' in source
        if "WebMediaDLMac" in rel:
            assert 'intakeKind: "drop"' in source
            assert "submitDrop" not in source
        else:
            assert "WebMediaDLPairedMacSubmit.submitDrop" in source
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
    http_direct = (root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/HttpDirect.swift").read_text(
        encoding="utf-8"
    )
    assert "if resolved.stale" in http_direct
    assert "TransferError.destinationDenied" in http_direct
    assert "startAccessingSecurityScopedResource" in http_direct
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
        assert "bookmark: filesBookmark" in text
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
    assert "class WebMediaDLLocalNetworkCompanionTransport" in continuity
    assert "func validate(_ message: WebMediaDLCompanionMessage)" in continuity
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
    assert "WebMediaDLLocalNetworkCompanionTransport" in tv
    assert "WebMediaDLWatchConnectivityTransport" not in tv
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
    assert "activateSession()" not in tv
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
        assert "bookmark: filesBookmark" in text
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
    mac_entitlements = plistlib.loads(
        (root / "apps/WebMediaDLMac/Resources/WebMediaDL.entitlements").read_bytes()
    )
    assert mac_entitlements.get("com.apple.security.network.server") is True
    for rel in (
        "apps/WebMediaDLMac/Resources/Info.plist",
        "apps/WebMediaDLiOS/Resources/Info.plist",
        "apps/WebMediaDLiPadOS/Resources/Info.plist",
        "apps/WebMediaDLVision/Resources/Info.plist",
        "apps/WebMediaDLTV/Resources/Info.plist",
        "apps/WebMediaDLMac/ShareExtension/Info.plist",
        "apps/WebMediaDLiOS/ShareExtension/Info.plist",
        "apps/WebMediaDLiPadOS/ShareExtension/Info.plist",
        "apps/WebMediaDLVision/ShareExtension/Info.plist",
    ):
        info = plistlib.loads((root / rel).read_bytes())
        assert "NSLocalNetworkUsageDescription" in info
        assert info["NSAppTransportSecurity"].get("NSAllowsLocalNetworking") is True
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
        assert (
            "JSONDecoder()" in text
            or "decodeCompanionHistory" in text
            or "WebMediaDLPairedMacSubmit.history" in text
        )


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
        if "WebMediaDLWatch" in rel:
            assert "WebMediaDLWatchConnectivityTransport" in text
            assert "WebMediaDLLocalNetworkCompanionTransport" not in text
        else:
            assert "WebMediaDLLocalNetworkCompanionTransport" in text
            assert "WebMediaDLWatchConnectivityTransport" not in text
        assert "let transport" in text
        assert "var transport" not in text
        assert "transport.send" in text
        assert "loadClient()" not in text
        assert 'intakeKind: "speak"' not in text
        assert "Process(" not in text
        assert "kind: .pause" in text
        assert "kind: .resume" in text
        assert "kind: .history" in text
        assert "kind: .status" in text
        assert "kind: .cancel, jobId:" in text
        assert "kind: .pauseJob" in text
        assert "kind: .resumeJob" in text
        assert "Pause WebMedia DL" in text
        assert "Resume WebMedia DL" in text
        assert "WebMedia DL history" in text
        assert "WebMedia DL status" in text
        assert "Cancel WebMedia DL" in text
        assert "Pause a WebMedia DL job" in text
        assert "Resume a WebMedia DL job" in text
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
    python_job = workflow.split("swift:")[0]
    assert python_job.index("scripts/validate_bundle.py") < python_job.index("git diff --exit-code")
    assert "swift test --package-path" in script
    assert "apps/WebMediaDLCore" in script
    assert "swift build --package-path" in script
    assert "apps/WebMediaDLMac" in script
    assert "--target WebMediaDLMacShareExtension" in script
    assert "xcodebuild -list" in script
    assert "library product + target dependency" in script
    assert "assemble_unsigned_appex.py" in script
    assert ".ci-derived-appex" in script
    assert "WebMediaDLiOSShareExtension.appex" in script or "${name}.appex" in script
    assert "WebMediaDLShareExtensions.xcodeproj" in script
    assert "com.apple.product-type.app-extension" in script
    assert "--inspect-derived" in script
    assert "--require-macho" in script
    assert ".ci-derived-appex-xcode" in script
    assert "generate_unsigned_appex_xcodeproj.py" in script
    assert 'generic/platform=iOS"' in script or "generic/platform=iOS" in script
    assert "generic/platform=watchOS" in script
    assert "generic/platform=tvOS" in script
    assert "generic/platform=visionOS" in script
    assert "SafariWebExtensionHandler.swift" in script
    assert "swiftc -typecheck" in script
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
        text = (repo_root() / rel).read_text(encoding="utf-8")
        assert "WebMediaDLUncheckedBox(context)" in text
        assert "cancelRequest(withError:" in text
        assert "try? await" not in text
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
    assert "unresolvable bookmark data must fail closed" in contracts
    assert "TransferError.destinationDenied" in contracts
    assert "TransferError.overflow" in contracts
    assert "invalidLocator" in contracts
    assert "testDomainInvariantsFailClosed" in contracts
    assert "WebMediaDLPipelineJob" in contracts
    assert "container_only" in contracts
    assert "WebMediaDLPairedMacEndpoint" in contracts
    assert "forwardToLoopback" in contracts
    assert "WebMediaDLMacRelayServer" in contracts
    assert "isAllowedPeer" in contracts
    assert (repo_root() / "apps/WebMediaDLCore/Sources/WebMediaDLCore/PairedMac.swift").is_file()
    assert (
        repo_root() / "apps/WebMediaDLCore/Sources/WebMediaDLCore/MacRelayServer.swift"
    ).is_file()
    paired_mac = (
        repo_root() / "apps/WebMediaDLCore/Sources/WebMediaDLCore/PairedMac.swift"
    ).read_text(encoding="utf-8")
    relay_http = (
        repo_root() / "apps/WebMediaDLCore/Sources/WebMediaDLCore/MacRelayServer.swift"
    ).read_text(encoding="utf-8")
    assert "func submitDrop(" in paired_mac
    assert 'appendingPathComponent("v1/staging")' in paired_mac
    assert 'destinationKind: "staging_only"' in paired_mac
    assert "func pullToFiles(" in paired_mac
    assert "artifactContentRequest" in paired_mac
    assert "X-WebMedia-Digest" in paired_mac
    assert 'token: ""' in paired_mac
    assert "token: credentials.token" not in paired_mac
    assert "macOnlyEndpoint" in paired_mac
    assert "loopbackToken" in paired_mac
    assert 'forHTTPHeaderField: "X-WebMedia-Token"' in paired_mac
    assert "maxStagingBytes" in relay_http
    assert "func maxBytes(for target: String)" in relay_http
    assert "func requestByteLimit(buffer: Data)" in relay_http
    assert "loopbackToken" in relay_http
    assert '"authorization"' in relay_http
    assert '"x-webmedia-token"' in relay_http
    assert "mac-only endpoint" in relay_http


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
    assert "Source artifacts SHALL be identified as sha256:<digest>." in domain
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
    assert "destinationDenied" in http_direct
    assert "filesDestinationRequired" in http_direct
    assert "saveIfDirect" in http_direct
    assert "func write(" in http_direct
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
    for text in (ios, ipad, vision, watch, tv, mac):
        assert 'accessibilityLabel("History row")' in text
    for text in (ios, ipad, vision):
        assert "Save on this device" in text
        assert "WebMediaDLHttpDirect.transfer" in text
        assert "Lightweight HTTP jobs stay on-device" in text
        assert "Send to paired Mac" in text
        assert "WebMediaDLPairedMacSubmit.submit" in text
        assert "WebMediaDLPairedMacSubmit.history" in text
        assert "WebMediaDLPairedMacSubmit.pauseQueue" in text
        assert "WebMediaDLPairedMacSubmit.queueStatus" in text
        assert "WebMediaDLPairedMacSubmit.pullToFiles" in text
        assert "Save published files here" in text
        assert 'destinationKind: files == nil ? nil : "staging_only"' in text
        assert 'destinationKind: files == nil ? nil : "files_app"' not in text
        assert "client.historyRequest()" not in text
        assert "pairedClient.historyRequest()" not in text
        assert "client.pauseQueue()" not in text
        assert "pairedClient.pauseQueue()" not in text
        assert "client.queueStatus()" not in text
        assert "pairedClient.queueStatus()" not in text
        assert "Paired Mac URL" in text
        assert "Save Mac address" in text
        assert "WebMediaDLPairedMacEndpoint.startPairing" in text
    assert "Save on this device" not in watch
    assert "Save on this device" not in tv
    assert "WebMediaDLHttpDirect" not in watch
    assert "WebMediaDLHttpDirect" not in tv
    assert "UIPasteboard" not in tv
    assert "watchRelay.activateSession()" in ios
    assert "onReceivedMessage" in ios
    assert "WebMediaDLPairedMacSubmit.companion" in ios
    assert "WebMediaDLLocalNetworkCompanionTransport" in tv
    assert "autoForward = true" in mac
    assert "bindWatchDelegate" in mac
    assert "WebMediaDLMacRelayServer.start" in mac
    assert "WebMediaDLMacWorkerProcess.start" in mac
    assert "startMacWorker" in mac
    assert "loopbackToken: token" in mac
    assert "relayServer?.loopbackToken = value" in mac
    worker_launch = (
        root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/MacWorkerProcess.swift"
    ).read_text(encoding="utf-8")
    assert '"serve"' in worker_launch
    assert '"--host"' in worker_launch
    assert '"127.0.0.1"' in worker_launch
    assert '"--port"' in worker_launch
    assert "loopbackPort" in worker_launch
    assert "8765" in worker_launch
    assert '"--data-dir"' in worker_launch
    assert "func start(dataDir:" in worker_launch
    assert 'NSClassFromString("NSTask")' in worker_launch
    assert "Process(" not in worker_launch
    assert worker_launch.index("#if os(macOS)") < worker_launch.index("homeDirectoryForCurrentUser")
    assert "This Mac's address" in mac
    assert "localOnly: false" in mac
    assert "WebMediaDLPairedMacSubmit.history" not in mac
    assert "WebMediaDLPairedMacSubmit.queueStatus" not in mac
    assert ".queueStatus()" in mac
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
        assert "WebMediaDLPairedMacSubmit.submit" in text
        assert "WebMediaDLShareIntake.fromSavedBookmark" in text
        assert 'destinationKind: files == nil ? nil : "staging_only"' in text
        assert "WebMediaDLPairedMacSubmit.pauseQueue" in text
        assert "WebMediaDLPairedMacSubmit.resumeQueue" in text
        assert "WebMediaDLPairedMacSubmit.history" in text
        assert "WebMediaDLPairedMacSubmit.cancel" in text
        assert "WebMediaDLPairedMacSubmit.queueStatus" in text
        assert "WebMediaDLPairedMacSubmit.pauseJob" in text
        assert "WebMediaDLPairedMacSubmit.resumeJob" in text
    mac_intent = (
        root / "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacSubmitURLIntent.swift"
    ).read_text(encoding="utf-8")
    assert "WebMediaDLHttpDirect" not in mac_intent
    assert "WebMediaDLShareIntake.fromSavedBookmark" in mac_intent
    assert 'destinationKind: files == nil ? nil : "files_app"' in mac_intent
    assert ".pauseQueue()" in mac_intent
    assert ".resumeQueue()" in mac_intent
    assert ".history()" in mac_intent
    assert ".cancel(jobId:" in mac_intent
    assert ".queueStatus()" in mac_intent
    assert ".pauseJob(jobId:" in mac_intent
    assert ".resumeJob(jobId:" in mac_intent
    for rel, surface in (
        ("apps/WebMediaDLiOS/ShareExtension/WebMediaDLiOSShareExtension.swift", ".ios"),
        ("apps/WebMediaDLiPadOS/ShareExtension/WebMediaDLiPadOSShareExtension.swift", ".ipados"),
        ("apps/WebMediaDLVision/ShareExtension/WebMediaDLVisionShareExtension.swift", ".visionos"),
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "WebMediaDLHttpDirect.saveIfDirect" in text
        assert f"surface: {surface}" in text
        assert "WebMediaDLPairedMacSubmit.submit" in text
        assert "WebMediaDLPairedMacSubmit.submitDrop" in text
        assert "WebMediaDLShareIntake.fromSavedBookmark" in text
        assert 'destinationKind: files == nil ? nil : "staging_only"' in text
    mac_share = (
        root / "apps/WebMediaDLMac/ShareExtension/WebMediaDLMacShareExtension.swift"
    ).read_text(encoding="utf-8")
    assert "WebMediaDLHttpDirect" not in mac_share
    assert "WebMediaDLShareIntake.fromSavedBookmark" in mac_share
    assert 'destinationKind: files == nil ? nil : "files_app"' in mac_share
    share_intake = (
        root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/ShareIntake.swift"
    ).read_text(encoding="utf-8")
    assert "fromSavedBookmark" in share_intake
    assert "resolvedForSubmit" in share_intake
    mac_share_view = (
        root / "apps/WebMediaDLMac/Sources/WebMediaDLMac/WebMediaDLMacShareView.swift"
    ).read_text(encoding="utf-8")
    assert "resolvedForSubmit" in mac_share_view
    assert 'destinationKind: files == nil ? nil : "files_app"' in mac_share_view
    for rel in (
        "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLiOSShareView.swift",
        "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSShareView.swift",
        "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionShareView.swift",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "resolvedForSubmit" in text
        assert 'destinationKind: files == nil ? nil : "staging_only"' in text


def test_privacy_manifests_declare_user_defaults() -> None:
    root = repo_root()
    manifests = [
        "apps/WebMediaDLMac/Resources/PrivacyInfo.xcprivacy",
        "apps/WebMediaDLMac/ShareExtension/PrivacyInfo.xcprivacy",
        "apps/WebMediaDLiOS/Resources/PrivacyInfo.xcprivacy",
        "apps/WebMediaDLiOS/ShareExtension/PrivacyInfo.xcprivacy",
        "apps/WebMediaDLiPadOS/Resources/PrivacyInfo.xcprivacy",
        "apps/WebMediaDLiPadOS/ShareExtension/PrivacyInfo.xcprivacy",
        "apps/WebMediaDLVision/Resources/PrivacyInfo.xcprivacy",
        "apps/WebMediaDLVision/ShareExtension/PrivacyInfo.xcprivacy",
        "apps/WebMediaDLWatch/Resources/PrivacyInfo.xcprivacy",
        "apps/WebMediaDLTV/Resources/PrivacyInfo.xcprivacy",
    ]
    for rel in manifests:
        payload = plistlib.loads((root / rel).read_bytes())
        assert payload["NSPrivacyTracking"] is False
        assert payload["NSPrivacyTrackingDomains"] == []
        assert payload["NSPrivacyCollectedDataTypes"] == []
        accessed = payload["NSPrivacyAccessedAPITypes"]
        assert accessed[0]["NSPrivacyAccessedAPIType"] == (
            "NSPrivacyAccessedAPICategoryUserDefaults"
        )
        assert accessed[0]["NSPrivacyAccessedAPITypeReasons"] == ["1C8F.1"]


def test_macos_app_supervises_the_loopback_worker() -> None:
    root = repo_root()
    mac = (root / ROOT_VIEWS["macos"]).read_text(encoding="utf-8")
    worker = (root / "apps/WebMediaDLCore/Sources/WebMediaDLCore/MacWorkerProcess.swift").read_text(
        encoding="utf-8"
    )
    assert "WebMediaDLMacWorkerProcess.start" in mac
    assert "startMacWorker" in mac
    assert "loopbackToken: token" in mac
    assert worker.index("#if os(macOS)") < worker.index("homeDirectoryForCurrentUser")
    assert '"serve"' in worker
    assert '"--host"' in worker
    assert '"127.0.0.1"' in worker
    assert "loopbackPort" in worker
    assert "8765" in worker
    assert "func start(dataDir:" in worker
    assert 'NSClassFromString("NSTask")' in worker
    assert "Process(" not in worker
    assert "WebMediaDLMacWorkerProcess.terminate" in mac
    for rel in (
        ROOT_VIEWS["ios"],
        ROOT_VIEWS["ipados"],
        ROOT_VIEWS["visionos"],
        ROOT_VIEWS["watchos"],
        ROOT_VIEWS["tvos"],
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "WebMediaDLMacWorkerProcess.start" not in text
        assert "homeDirectoryForCurrentUser" not in text
        assert "Process(" not in text


def test_iphone_forwards_watch_companion_messages() -> None:
    root = repo_root()
    ios = (root / ROOT_VIEWS["ios"]).read_text(encoding="utf-8")
    tv = (root / ROOT_VIEWS["tvos"]).read_text(encoding="utf-8")
    assert "watchRelay.activateSession()" in ios
    assert "onReceivedMessage" in ios
    assert "WebMediaDLPairedMacSubmit.companion" in ios
    assert "WebMediaDLWatchConnectivityTransport" not in tv
    assert "WebMediaDLLocalNetworkCompanionTransport" in tv


def test_complete_client_control_intents_use_mac_relay() -> None:
    root = repo_root()
    for rel in (
        "apps/WebMediaDLiOS/Sources/WebMediaDLiOS/WebMediaDLSubmitURLIntent.swift",
        "apps/WebMediaDLiPadOS/Sources/WebMediaDLiPadOS/WebMediaDLiPadOSSubmitURLIntent.swift",
        "apps/WebMediaDLVision/Sources/WebMediaDLVision/WebMediaDLVisionSubmitURLIntent.swift",
    ):
        text = (root / rel).read_text(encoding="utf-8")
        assert "WebMediaDLPairedMacSubmit.submit" in text
        assert "WebMediaDLPairedMacSubmit.pauseQueue" in text
        assert "WebMediaDLPairedMacSubmit.resumeQueue" in text
        assert "WebMediaDLPairedMacSubmit.history" in text
        assert "WebMediaDLPairedMacSubmit.cancel" in text
        assert "WebMediaDLPairedMacSubmit.queueStatus" in text
        assert "WebMediaDLPairedMacSubmit.pauseJob" in text
        assert "WebMediaDLPairedMacSubmit.resumeJob" in text


def _load_assemble_unsigned_appex():
    path = repo_root() / "scripts/assemble_unsigned_appex.py"
    spec = importlib.util.spec_from_file_location("assemble_unsigned_appex", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load assemble_unsigned_appex.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unsigned_share_extension_appex_layouts(tmp_path: Path) -> None:
    module = _load_assemble_unsigned_appex()
    dest = tmp_path / "appex"
    created = module.assemble(repo_root(), dest)
    assert len(created) == 4
    expected = {item[1]: item[2] for item in module.SHARE_EXTENSIONS}
    for bundle in created:
        assert bundle.suffix == ".appex"
        assert bundle.is_dir()
        payload = plistlib.loads((bundle / "Info.plist").read_bytes())
        name = bundle.name.removesuffix(".appex")
        assert payload["CFBundlePackageType"] == "XPC!"
        assert payload["CFBundleExecutable"] == name
        assert payload["NSExtension"]["NSExtensionPointIdentifier"] == ("com.apple.share-services")
        assert payload["NSExtension"]["NSExtensionPrincipalClass"] == expected[name]
        privacy = plistlib.loads((bundle / "PrivacyInfo.xcprivacy").read_bytes())
        assert privacy["NSPrivacyTracking"] is False
        assert privacy["NSPrivacyAccessedAPITypes"][0]["NSPrivacyAccessedAPITypeReasons"] == [
            "1C8F.1"
        ]
    script = (repo_root() / "scripts/assemble_unsigned_appex.py").read_text(encoding="utf-8")
    assert 'payload["CFBundlePackageType"] = "XPC!"' in script
    assert "Signed Xcode NSExtension wrapping stays BLOCKED" in script


def _load_unsigned_appex_xcode():
    path = repo_root() / "scripts/generate_unsigned_appex_xcodeproj.py"
    spec = importlib.util.spec_from_file_location("generate_unsigned_appex_xcodeproj", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load generate_unsigned_appex_xcodeproj.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unsigned_xcode_app_extension_products(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = repo_root()
    module = _load_unsigned_appex_xcode()
    committed = root / "apps/WebMediaDLShareExtensions/WebMediaDLShareExtensions.xcodeproj"
    assert module.main(["--root", str(root), "--check"]) == 0
    dest = tmp_path / "WebMediaDLShareExtensions.xcodeproj"
    written = module.write_xcodeproj(root, dest)
    assert written.is_file()
    expected = module.generated_files(root)
    assert set(expected) == {
        "project.pbxproj",
        *(
            f"xcshareddata/xcschemes/{name}.xcscheme"
            for _, name, _ in module.load_share_extensions()
        ),
    }
    for relative, text in expected.items():
        assert (dest / relative).read_text(encoding="utf-8") == text
        assert (committed / relative).read_text(encoding="utf-8") == text
    pbxproj = (committed / "project.pbxproj").read_text(encoding="utf-8")
    assert pbxproj.count('productType = "com.apple.product-type.app-extension"') == 4
    assert pbxproj.count("WRAPPER_EXTENSION = appex") == 8
    assert pbxproj.count("APPLICATION_EXTENSION_API_ONLY = YES") == 8
    assert "APPLICATION_EXTENSION_API_ONLY = NO" not in pbxproj
    assert "CODE_SIGNING_ALLOWED = NO" in pbxproj
    assert 'relativePath = "../WebMediaDLCore"' in pbxproj
    assert "XCLocalSwiftPackageReference" in pbxproj
    for _, name, _ in module.load_share_extensions():
        assert f"{name}.swift" in pbxproj
        assert (dest / f"xcshareddata/xcschemes/{name}.xcscheme").is_file()
    script = (root / "scripts/build_apple_packages.sh").read_text(encoding="utf-8")
    assert "WebMediaDLShareExtensions.xcodeproj" in script
    assert "com.apple.product-type.app-extension" in script
    assert "--inspect-derived" in script
    assert "--require-macho" in script
    for name, destination in module.destinations():
        assert name in script
        assert destination in script

    layouts = _load_assemble_unsigned_appex().assemble(root, tmp_path / "layouts")
    derived = tmp_path / "derived" / "Build" / "Products" / "Debug-iphoneos"
    derived.mkdir(parents=True)
    for bundle in layouts:
        report = module.inspect_bundle(bundle, require_macho=False)
        assert report["macho"] is None
        with pytest.raises(FileNotFoundError, match="Mach-O"):
            module.inspect_bundle(bundle, require_macho=True)
        name = bundle.name.removesuffix(".appex")
        exe = bundle / name
        exe.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 8)
        macho = module.inspect_bundle(bundle, require_macho=True)
        assert macho["macho"] == "64"
        copied = derived / bundle.name
        copied.mkdir()
        (copied / "Info.plist").write_bytes((bundle / "Info.plist").read_bytes())
        (copied / "PrivacyInfo.xcprivacy").write_bytes(
            (bundle / "PrivacyInfo.xcprivacy").read_bytes()
        )
        (copied / name).write_bytes(exe.read_bytes())
    reports = module.inspect_derived(derived, require_macho=True)
    assert {item["name"] for item in reports} == {
        item[1] for item in module.load_share_extensions()
    }
    assert module.main(["--inspect-derived", str(derived), "--require-macho"]) == 0
    assert module.main(["--inspect-bundle", str(layouts[0]), "--require-macho"]) == 0

    assert module.macho_kind(exe) == "64"
    fat = tmp_path / "fat-bin"
    fat.write_bytes(b"\xca\xfe\xba\xbe")
    assert module.macho_kind(fat) == "fat"
    bit32 = tmp_path / "macho32"
    bit32.write_bytes(b"\xfe\xed\xfa\xce")
    assert module.macho_kind(bit32) == "32"
    assert module.macho_kind(tmp_path / "missing-bin") is None
    text = tmp_path / "not-macho"
    text.write_bytes(b"notm")
    assert module.macho_kind(text) is None

    stale = tmp_path / "stale.xcodeproj"
    module.write_xcodeproj(root, stale)
    (stale / "project.pbxproj").write_text("stale\n", encoding="utf-8")
    with pytest.raises(ValueError, match="stale"):
        module.check_xcodeproj(root, stale)
    missing = tmp_path / "missing.xcodeproj"
    missing.mkdir()
    with pytest.raises(FileNotFoundError, match="missing generated"):
        module.check_xcodeproj(root, missing)
    with pytest.raises(ValueError, match=r"not an \.appex"):
        module.inspect_bundle(tmp_path / "not-an-appex")
    empty = tmp_path / "Empty.appex"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match=r"Info\.plist"):
        module.inspect_bundle(empty)
    unknown = tmp_path / "UnknownShare.appex"
    unknown.mkdir()
    (unknown / "Info.plist").write_bytes((layouts[0] / "Info.plist").read_bytes())
    with pytest.raises(ValueError, match="unexpected"):
        module.inspect_bundle(unknown)
    broken = tmp_path / "WebMediaDLiOSShareExtension.appex"
    broken.mkdir()
    (broken / "Info.plist").write_bytes(plistlib.dumps({"CFBundlePackageType": "APPL"}))
    with pytest.raises(ValueError, match="package type"):
        module.inspect_bundle(broken)
    missing_ext = tmp_path / "WebMediaDLMacShareExtension.appex"
    missing_ext.mkdir()
    (missing_ext / "Info.plist").write_bytes(
        plistlib.dumps(
            {
                "CFBundlePackageType": "XPC!",
                "CFBundleExecutable": "WebMediaDLMacShareExtension",
            }
        )
    )
    with pytest.raises(ValueError, match="NSExtension"):
        module.inspect_bundle(missing_ext)
    nested = tmp_path / "nested-mac" / "WebMediaDLMacShareExtension.appex"
    (nested / "Contents" / "MacOS").mkdir(parents=True)
    (nested / "Contents" / "Resources").mkdir(parents=True)
    mac = next(item for item in layouts if item.name == "WebMediaDLMacShareExtension.appex")
    shutil.copy2(mac / "Info.plist", nested / "Contents" / "Info.plist")
    shutil.copy2(
        mac / "PrivacyInfo.xcprivacy",
        nested / "Contents" / "Resources" / "PrivacyInfo.xcprivacy",
    )
    shutil.copy2(
        mac / "WebMediaDLMacShareExtension",
        nested / "Contents" / "MacOS" / "WebMediaDLMacShareExtension",
    )
    nested_report = module.inspect_bundle(nested, require_macho=True)
    assert nested_report["macho"] == "64"
    wrong_exe = tmp_path / "wrong-exe" / "WebMediaDLiOSShareExtension.appex"
    wrong_exe.mkdir(parents=True)
    payload = plistlib.loads((layouts[0] / "Info.plist").read_bytes())
    payload["CFBundleExecutable"] = "Other"
    (wrong_exe / "Info.plist").write_bytes(plistlib.dumps(payload))
    with pytest.raises(ValueError, match="executable"):
        module.inspect_bundle(wrong_exe)
    no_privacy = tmp_path / "no-privacy" / "WebMediaDLiOSShareExtension.appex"
    no_privacy.mkdir(parents=True)
    shutil.copy2(layouts[0] / "Info.plist", no_privacy / "Info.plist")
    with pytest.raises(FileNotFoundError, match="PrivacyInfo"):
        module.inspect_bundle(no_privacy)
    point = tmp_path / "point" / "WebMediaDLiOSShareExtension.appex"
    point.mkdir(parents=True)
    point_payload = plistlib.loads((layouts[0] / "Info.plist").read_bytes())
    point_payload["NSExtension"]["NSExtensionPointIdentifier"] = "com.apple.widget-extension"
    (point / "Info.plist").write_bytes(plistlib.dumps(point_payload))
    shutil.copy2(layouts[0] / "PrivacyInfo.xcprivacy", point / "PrivacyInfo.xcprivacy")
    with pytest.raises(ValueError, match="share-services"):
        module.inspect_bundle(point)
    principal = tmp_path / "principal" / "WebMediaDLiOSShareExtension.appex"
    principal.mkdir(parents=True)
    principal_payload = plistlib.loads((layouts[0] / "Info.plist").read_bytes())
    principal_payload["NSExtension"]["NSExtensionPrincipalClass"] = "OtherPrincipal"
    (principal / "Info.plist").write_bytes(plistlib.dumps(principal_payload))
    shutil.copy2(layouts[0] / "PrivacyInfo.xcprivacy", principal / "PrivacyInfo.xcprivacy")
    with pytest.raises(ValueError, match="principal"):
        module.inspect_bundle(principal)
    with pytest.raises(FileNotFoundError, match=r"unsigned \.appex products"):
        module.inspect_derived(tmp_path / "empty-derived", require_macho=True)
    with pytest.raises(FileNotFoundError, match="missing share-extension file"):
        module.extension_rows(tmp_path / "empty-root")
    validator = (root / "scripts/validate_bundle.py").read_text(encoding="utf-8")
    assert '".ci-derived-appex-xcode"' in validator
    monkeypatch.setattr(module.plistlib, "loads", lambda *_args, **_kwargs: {})
    with pytest.raises(ValueError, match="CFBundleIdentifier"):
        module.extension_rows(root)
    monkeypatch.undo()
    monkeypatch.setattr(module, "oid", lambda *_parts: "A" * 24)
    with pytest.raises(RuntimeError, match="object id collision"):
        module.render_pbxproj(root)
    monkeypatch.setattr(module, "PLATFORM", {})
    with pytest.raises(KeyError, match="no unsigned xcode platform mapping"):
        module.extension_rows(root)
