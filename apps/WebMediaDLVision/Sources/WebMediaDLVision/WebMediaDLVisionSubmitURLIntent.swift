import AppIntents
import WebMediaDLCore

/// visionOS App Intent: share, paste, or speak a URL to the paired Mac worker.
public struct WebMediaDLVisionSubmitURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Send to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        if try await WebMediaDLHttpDirect.saveIfDirect(locator: locator, surface: .visionos) != nil {
            return .result()
        }
        _ = try await WebMediaDLPairedMacSubmit.submit(
            locator: locator,
            surface: .visionos,
            credentials: client,
            intakeKind: "intent"
        )
        return .result()
    }
}

public struct WebMediaDLVisionSpeakURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Speak a media URL to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        if try await WebMediaDLHttpDirect.saveIfDirect(locator: locator, surface: .visionos) != nil {
            return .result()
        }
        _ = try await WebMediaDLPairedMacSubmit.submit(
            locator: locator,
            surface: .visionos,
            credentials: client,
            intakeKind: "speak"
        )
        return .result()
    }
}

public struct WebMediaDLVisionShortcuts: AppShortcutsProvider {
    public static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: WebMediaDLVisionSubmitURLIntent(),
            phrases: [
                "Send this URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
        AppShortcut(
            intent: WebMediaDLVisionSpeakURLIntent(),
            phrases: [
                "Speak a media URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
    }
}
