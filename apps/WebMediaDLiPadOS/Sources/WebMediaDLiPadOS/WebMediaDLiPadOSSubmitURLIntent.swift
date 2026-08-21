import AppIntents
import WebMediaDLCore

/// iPadOS App Intent: share, paste, or speak a URL to the paired Mac worker.
public struct WebMediaDLiPadOSSubmitURLIntent: AppIntent {
    public static var title: LocalizedStringResource = "Send to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLLoopbackClient()
        _ = try await client.submit(locator: locator, surface: .ipados, intakeKind: "intent")
        return .result()
    }
}

public struct WebMediaDLiPadOSShortcuts: AppShortcutsProvider {
    public static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: WebMediaDLiPadOSSubmitURLIntent(),
            phrases: [
                "Send this URL to \(.applicationName)",
                "Speak a media URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
    }
}
