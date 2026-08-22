import AppIntents
import WebMediaDLCore

/// iOS App Intent: share, paste, or speak a URL to the paired Mac worker.
public struct WebMediaDLSubmitURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Send to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        if try await WebMediaDLHttpDirect.saveIfDirect(locator: locator, surface: .ios) != nil {
            return .result()
        }
        _ = try await client.submit(locator: locator, surface: .ios, intakeKind: "intent")
        let intake = WebMediaDLShareIntake(locator: locator)
        _ = intake.canPublishToPhotos
        return .result()
    }
}

public struct WebMediaDLiOSSpeakURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Speak a media URL to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        if try await WebMediaDLHttpDirect.saveIfDirect(locator: locator, surface: .ios) != nil {
            return .result()
        }
        _ = try await client.submit(locator: locator, surface: .ios, intakeKind: "speak")
        return .result()
    }
}

public struct WebMediaDLiOSShortcuts: AppShortcutsProvider {
    public static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: WebMediaDLSubmitURLIntent(),
            phrases: [
                "Send this URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
        AppShortcut(
            intent: WebMediaDLiOSSpeakURLIntent(),
            phrases: [
                "Speak a media URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
    }
}
