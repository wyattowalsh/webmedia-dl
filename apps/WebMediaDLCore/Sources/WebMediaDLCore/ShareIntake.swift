import Foundation

/// Share sheet / Photos / Files destinations never write without an approved root.
public struct WebMediaDLShareIntake: Sendable {
    public var locator: String
    public var approvedRoot: String?

    public init(locator: String, approvedRoot: String? = nil) {
        self.locator = locator
        self.approvedRoot = approvedRoot
    }

    public var filesDestination: WebMediaDLFilesDestination? {
        guard let approvedRoot, !approvedRoot.isEmpty else { return nil }
        return WebMediaDLFilesDestination(
            bookmark: WebMediaDLSecurityScopedBookmark(path: approvedRoot)
        )
    }

    public var canPublishToFiles: Bool {
        filesDestination != nil
    }

    public var canPublishToPhotos: Bool {
        WebMediaDLPhotoKitDestination(approvedRoot: approvedRoot).canPublish
    }
}
