import Foundation

/// Share sheet / Photos / Files destinations never write without an approved root.
public struct WebMediaDLShareIntake: Sendable {
    public var locator: String
    public var approvedRoot: String?
    public var bookmarkData: Data?

    public init(locator: String, approvedRoot: String? = nil, bookmarkData: Data? = nil) {
        self.locator = locator
        self.approvedRoot = approvedRoot
        self.bookmarkData = bookmarkData
    }

    public var filesDestination: WebMediaDLFilesDestination? {
        guard let approvedRoot, !approvedRoot.isEmpty else { return nil }
        return WebMediaDLFilesDestination(
            bookmark: WebMediaDLSecurityScopedBookmark(path: approvedRoot, bookmarkData: bookmarkData)
        )
    }

    public var canPublishToFiles: Bool {
        filesDestination != nil
    }

    public var canPublishToPhotos: Bool {
        WebMediaDLPhotoKitDestination(approvedRoot: approvedRoot).canPublish
    }
}
