import AppIntents
import WebMediaDLCore

/// watchOS App Intent: speak or capture a URL for Mac relay. Not a subprocess worker.
/// Speak intake uses intakeKind: "speak" on the Mac after companion transport delivery.
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
        var transport = WebMediaDLWatchConnectivityTransport()
        let message = bridge.message(kind: .capture, locator: locator, surface: .watchos)
        try await transport.send(message)
        return .result()
    }
}

public struct WebMediaDLWatchShortcuts: AppShortcutsProvider {
    public static var appShortcuts: [AppShortcut] {
        [
            AppShortcut(
                intent: WebMediaDLWatchSubmitURLIntent(),
                phrases: [
                    "Speak a media URL to \(.applicationName)",
                ],
                shortTitle: "Send to WebMedia DL",
                systemImageName: "arrow.down.circle"
            ),
        ]
    }
}
