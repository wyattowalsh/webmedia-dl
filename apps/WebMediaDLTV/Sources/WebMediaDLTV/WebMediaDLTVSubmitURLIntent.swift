import AppIntents
import WebMediaDLCore

/// tvOS App Intent: speak or capture a URL for Mac relay. Not a subprocess worker.
/// Speak intake uses intakeKind: "speak" on the Mac after companion transport delivery.
public struct WebMediaDLTVSubmitURLIntent: AppIntent {
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
        let message = bridge.message(kind: .capture, locator: locator, surface: .tvos)
        try await transport.send(message)
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
