import AppIntents
import WebMediaDLCore

/// iOS App Intent: share or paste a URL to the paired Mac worker.
public struct WebMediaDLSubmitURLIntent: AppIntent {
    public static var title: LocalizedStringResource = "Send to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLLoopbackClient()
        _ = client.submitRequest(locator: locator, surface: .ios)
        let intake = WebMediaDLShareIntake(locator: locator)
        _ = intake.canPublishToPhotos
        return .result()
    }
}
