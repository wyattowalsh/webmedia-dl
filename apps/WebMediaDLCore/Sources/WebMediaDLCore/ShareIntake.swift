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

    /// Restore the App Group Files bookmark chosen in the complete-client UI.
    public static func fromSavedBookmark(
        locator: String,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) -> WebMediaDLShareIntake {
        guard let data = WebMediaDLWorkerCredentials.loadBookmark(defaults: defaults) else {
            return WebMediaDLShareIntake(locator: locator)
        }
        let resolved = WebMediaDLSecurityScopedBookmark(path: "", bookmarkData: data).resolve()
        let root = resolved.path.trimmingCharacters(in: .whitespacesAndNewlines)
        return WebMediaDLShareIntake(
            locator: locator,
            approvedRoot: root.isEmpty ? nil : root,
            bookmarkData: resolved.bookmarkData ?? data
        )
    }

    /// Prefer an explicit intake root, otherwise the saved App Group bookmark.
    public func resolvedForSubmit(
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) -> WebMediaDLShareIntake {
        if filesDestination != nil { return self }
        let saved = Self.fromSavedBookmark(locator: locator, defaults: defaults)
        return saved.filesDestination == nil ? self : saved
    }
}
