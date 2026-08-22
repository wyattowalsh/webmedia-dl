import AppIntents
import WebMediaDLCore

/// watchOS App Intent: capture a URL for Mac relay. Not a subprocess worker.
/// Companion `capture` has no intake kind; the Mac classifies the locator as `url`.
public struct WebMediaDLWatchSubmitURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Send to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let bridge = WebMediaDLContinuityBridge()
        let transport = WebMediaDLWatchConnectivityTransport()
        let message = bridge.message(kind: .capture, locator: locator, surface: .watchos)
        try await transport.send(message)
        return .result()
    }
}

public struct WebMediaDLWatchPauseIntent: AppIntent {
    public static let title: LocalizedStringResource = "Pause WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let bridge = WebMediaDLContinuityBridge()
        let transport = WebMediaDLWatchConnectivityTransport()
        try await transport.send(bridge.message(kind: .pause, surface: .watchos))
        return .result()
    }
}

public struct WebMediaDLWatchResumeIntent: AppIntent {
    public static let title: LocalizedStringResource = "Resume WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let bridge = WebMediaDLContinuityBridge()
        let transport = WebMediaDLWatchConnectivityTransport()
        try await transport.send(bridge.message(kind: .resume, surface: .watchos))
        return .result()
    }
}

public struct WebMediaDLWatchHistoryIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL history"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let bridge = WebMediaDLContinuityBridge()
        let transport = WebMediaDLWatchConnectivityTransport()
        try await transport.send(bridge.message(kind: .history, surface: .watchos))
        return .result()
    }
}

public struct WebMediaDLWatchStatusIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL status"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let bridge = WebMediaDLContinuityBridge()
        let transport = WebMediaDLWatchConnectivityTransport()
        try await transport.send(bridge.message(kind: .status, surface: .watchos))
        return .result()
    }
}

public struct WebMediaDLWatchCancelIntent: AppIntent {
    public static let title: LocalizedStringResource = "Cancel WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let bridge = WebMediaDLContinuityBridge()
        let transport = WebMediaDLWatchConnectivityTransport()
        try await transport.send(bridge.message(kind: .cancel, surface: .watchos))
        return .result()
    }
}

public struct WebMediaDLWatchShortcuts: AppShortcutsProvider {
    public static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: WebMediaDLWatchSubmitURLIntent(),
            phrases: [
                "Speak a media URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
        AppShortcut(
            intent: WebMediaDLWatchPauseIntent(),
            phrases: [
                "Pause \(.applicationName)",
            ],
            shortTitle: "Pause WebMedia DL",
            systemImageName: "pause.circle"
        )
        AppShortcut(
            intent: WebMediaDLWatchResumeIntent(),
            phrases: [
                "Resume \(.applicationName)",
            ],
            shortTitle: "Resume WebMedia DL",
            systemImageName: "play.circle"
        )
        AppShortcut(
            intent: WebMediaDLWatchHistoryIntent(),
            phrases: [
                "Show \(.applicationName) history",
            ],
            shortTitle: "WebMedia DL history",
            systemImageName: "clock"
        )
        AppShortcut(
            intent: WebMediaDLWatchStatusIntent(),
            phrases: [
                "WebMedia DL status",
            ],
            shortTitle: "WebMedia DL status",
            systemImageName: "info.circle"
        )
        AppShortcut(
            intent: WebMediaDLWatchCancelIntent(),
            phrases: [
                "Cancel \(.applicationName)",
            ],
            shortTitle: "Cancel WebMedia DL",
            systemImageName: "xmark.circle"
        )
    }
}
