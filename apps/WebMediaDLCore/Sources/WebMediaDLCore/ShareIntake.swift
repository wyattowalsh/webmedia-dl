import Foundation

/// Share sheet / Photos / Files destinations never write without an approved root.
public struct WebMediaDLShareIntake: Sendable {
    public var locator: String
    public var approvedRoot: String?

    public init(locator: String, approvedRoot: String? = nil) {
        self.locator = locator
        self.approvedRoot = approvedRoot
    }

    public var canPublishToPhotos: Bool {
        approvedRoot != nil && !(approvedRoot?.isEmpty ?? true)
    }
}
