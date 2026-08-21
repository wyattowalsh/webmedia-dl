import AppIntents
import WebMediaDLCore

/// tvOS App Intent: speak or capture a URL for Mac relay. Not a subprocess worker.
public struct WebMediaDLTVSubmitURLIntent: AppIntent {
    public static var title: LocalizedStringResource = "Send to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        _ = try await client.submit(locator: locator, surface: .tvos, intakeKind: "speak")
        return .result()
    }
}

public struct WebMediaDLTVShortcuts: AppShortcutsProvider {
    public static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: WebMediaDLTVSubmitURLIntent(),
            phrases: [
                "Speak a media URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
    }
}
