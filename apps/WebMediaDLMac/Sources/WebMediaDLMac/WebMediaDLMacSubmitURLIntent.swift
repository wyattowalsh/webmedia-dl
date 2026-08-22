import AppIntents
import WebMediaDLCore

/// macOS App Intent: paste, speak, or share a URL to the local worker. No provider argv.
public struct WebMediaDLMacSubmitURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Send to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        _ = try await client.submit(locator: locator, surface: .macos, intakeKind: "intent")
        return .result()
    }
}

public struct WebMediaDLMacSpeakURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Speak a media URL to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        _ = try await client.submit(locator: locator, surface: .macos, intakeKind: "speak")
        return .result()
    }
}

public struct WebMediaDLMacShortcuts: AppShortcutsProvider {
    public static var appShortcuts: [AppShortcut] {
        [
            AppShortcut(
                intent: WebMediaDLMacSubmitURLIntent(),
                phrases: [
                    "Send this URL to \(.applicationName)",
                    "Download with \(.applicationName)",
                ],
                shortTitle: "Send to WebMedia DL",
                systemImageName: "arrow.down.circle"
            ),
            AppShortcut(
                intent: WebMediaDLMacSpeakURLIntent(),
                phrases: [
                    "Speak a media URL to \(.applicationName)",
                ],
                shortTitle: "Send to WebMedia DL",
                systemImageName: "arrow.down.circle"
            ),
        ]
    }
}
