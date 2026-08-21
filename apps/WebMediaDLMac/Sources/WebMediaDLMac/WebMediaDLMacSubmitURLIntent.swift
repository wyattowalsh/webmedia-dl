import AppIntents
import WebMediaDLCore

/// macOS App Intent: paste or share a URL to the local worker. No provider argv.
public struct WebMediaDLMacSubmitURLIntent: AppIntent {
    public static var title: LocalizedStringResource = "Send to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLLoopbackClient()
        _ = try await client.submit(locator: locator, surface: .macos)
        return .result()
    }
}
