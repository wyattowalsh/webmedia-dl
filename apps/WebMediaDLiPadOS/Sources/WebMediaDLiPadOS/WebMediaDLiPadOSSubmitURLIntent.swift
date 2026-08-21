import AppIntents
import WebMediaDLCore

/// iPadOS App Intent: share or paste a URL to the paired Mac worker.
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
        _ = try await client.submit(locator: locator, surface: .ipados)
        return .result()
    }
}
