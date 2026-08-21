import AppIntents
import WebMediaDLCore

/// watchOS App Intent: speak or capture a URL for Mac relay. Not a subprocess worker.
public struct WebMediaDLWatchSubmitURLIntent: AppIntent {
    public static var title: LocalizedStringResource = "Send to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        _ = try await client.submit(locator: locator, surface: .watchos, intakeKind: "speak")
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
    }
}
