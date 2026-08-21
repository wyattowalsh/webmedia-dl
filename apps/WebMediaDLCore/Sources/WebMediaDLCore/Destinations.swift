import Foundation

/// User-granted Files/Share root. Paths outside the bookmark are denied.
public struct WebMediaDLSecurityScopedBookmark: Sendable, Equatable {
    public var path: String
    public var stale: Bool
    public var bookmarkData: Data?

    public init(path: String, stale: Bool = false, bookmarkData: Data? = nil) {
        self.path = path
        self.stale = stale
        self.bookmarkData = bookmarkData
    }

    public static func fromPickedURL(_ url: URL) -> WebMediaDLSecurityScopedBookmark {
        let data: Data?
        do {
            #if os(macOS)
            data = try url.bookmarkData(
                options: .withSecurityScope,
                includingResourceValuesForKeys: nil,
                relativeTo: nil
            )
            #else
            data = try url.bookmarkData(
                options: .minimalBookmark,
                includingResourceValuesForKeys: nil,
                relativeTo: nil
            )
            #endif
        } catch {
            data = nil
        }
        return WebMediaDLSecurityScopedBookmark(path: url.path, bookmarkData: data)
    }

    public static func standardizedPath(_ raw: String) -> String {
        URL(fileURLWithPath: raw).standardizedFileURL.resolvingSymlinksInPath().path
    }

    public func allows(_ candidate: String) -> Bool {
        if stale { return false }
        let trimmed = path.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return false }
        let root = Self.standardizedPath(trimmed)
        let item = Self.standardizedPath(candidate)
        if root.isEmpty || item.isEmpty { return false }
        if item == root { return true }
        let prefix = root.hasSuffix("/") ? root : root + "/"
        return item.hasPrefix(prefix)
    }

    public func resolve() -> WebMediaDLSecurityScopedBookmark {
        guard let bookmarkData else { return self }
        var isStale = false
        let resolved: URL?
        do {
            #if os(macOS)
            resolved = try URL(
                resolvingBookmarkData: bookmarkData,
                options: .withSecurityScope,
                relativeTo: nil,
                bookmarkDataIsStale: &isStale
            )
            #else
            resolved = try URL(
                resolvingBookmarkData: bookmarkData,
                options: [],
                relativeTo: nil,
                bookmarkDataIsStale: &isStale
            )
            #endif
        } catch {
            return WebMediaDLSecurityScopedBookmark(path: path, stale: true, bookmarkData: bookmarkData)
        }
        guard let resolved else {
            return WebMediaDLSecurityScopedBookmark(path: path, stale: true, bookmarkData: bookmarkData)
        }
        return WebMediaDLSecurityScopedBookmark(path: resolved.path, stale: isStale, bookmarkData: bookmarkData)
    }
}

/// Files app destination requires a security-scoped bookmark and never writes home silently.
public struct WebMediaDLFilesDestination: Sendable {
    public var bookmark: WebMediaDLSecurityScopedBookmark

    public init(bookmark: WebMediaDLSecurityScopedBookmark) {
        self.bookmark = bookmark
    }

    public var approvedRoot: String { bookmark.path }

    public func allows(_ candidate: String) -> Bool {
        bookmark.allows(candidate)
    }
}

/// CLOSED: apple-system-integrations — PhotoKit library writes stay closed until a
/// signed Apple Photos API is available. `libraryWriteAvailable` is fail-closed.
public struct WebMediaDLPhotoKitDestination: Sendable {
    public var approvedRoot: String?
    public static let libraryWriteAvailable = false

    public init(approvedRoot: String? = nil) {
        self.approvedRoot = approvedRoot
    }

    public var canPublish: Bool {
        if !Self.libraryWriteAvailable { return false }
        guard let approvedRoot, !approvedRoot.isEmpty else { return false }
        return true
    }
}

/// Extract share-sheet locators. HTTPS stays a URL; file paths use drop intake.
public enum WebMediaDLShareItemExtractor {
    public static let urlTypeIdentifier = "public.url"
    public static let fileURLTypeIdentifier = "public.file-url"
    public static let textTypeIdentifier = "public.plain-text"

    public static func locators(fromShared values: [String]) -> [String] {
        values.compactMap { raw in
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.lowercased().hasPrefix("http://") || trimmed.lowercased().hasPrefix("https://") {
                return trimmed
            }
            return nil
        }
    }

    public static func dropPaths(fromShared values: [String]) -> [String] {
        values.compactMap { raw in
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.hasPrefix("file://"), let url = URL(string: trimmed) {
                return url.path
            }
            if trimmed.hasPrefix("/") {
                return trimmed
            }
            return nil
        }
    }
}

/// Await NSItemProvider.loadItem before submitting so share extensions keep locators.
public enum WebMediaDLShareExtensionLoader {
    public static func loadSharedValues(from context: NSExtensionContext) async -> [String] {
        var values: [String] = []
        for item in context.inputItems {
            guard let extensionItem = item as? NSExtensionItem else { continue }
            for provider in extensionItem.attachments ?? [] {
                if let loaded = await loadItem(from: provider) {
                    values.append(loaded)
                }
            }
        }
        return values
    }

    public static func loadItem(from provider: NSItemProvider) async -> String? {
        let identifiers = [
            WebMediaDLShareItemExtractor.urlTypeIdentifier,
            WebMediaDLShareItemExtractor.fileURLTypeIdentifier,
            WebMediaDLShareItemExtractor.textTypeIdentifier,
        ]
        for identifier in identifiers where provider.hasItemConformingToTypeIdentifier(identifier) {
            return await withCheckedContinuation { continuation in
                provider.loadItem(forTypeIdentifier: identifier, options: nil) { loaded, _ in
                    if let url = loaded as? URL {
                        continuation.resume(returning: url.absoluteString)
                    } else if let text = loaded as? String {
                        continuation.resume(returning: text)
                    } else {
                        continuation.resume(returning: nil)
                    }
                }
            }
        }
        return nil
    }
}

public struct WebMediaDLClipboardIntake: Sendable {
    public var text: String

    public init(text: String) {
        self.text = text
    }

    public var locator: String? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let token = trimmed.split(whereSeparator: \.isWhitespace).first.map(String.init) ?? trimmed
        if token.lowercased().hasPrefix("http://") || token.lowercased().hasPrefix("https://") {
            return token
        }
        guard let match = trimmed.range(
            of: #"https?://[^\s<>"']+"#,
            options: .regularExpression
        ) else {
            return nil
        }
        return String(trimmed[match])
    }

    public var usesURLAsPath: Bool { false }
    public var intakeKind: String { "paste" }
}

/// Typed local lifecycle event. Never a provider console dump.
public struct WebMediaDLEvent: Codable, Sendable, Identifiable {
    public var id: UUID
    public var jobId: UUID
    public var type: String
    public var sequence: Int
    public var payload: [String: String]

    public init(
        id: UUID = UUID(),
        jobId: UUID,
        type: String,
        sequence: Int,
        payload: [String: String] = [:]
    ) {
        self.id = id
        self.jobId = jobId
        self.type = type
        self.sequence = sequence
        self.payload = payload
    }

    public var exposesProviderConsole: Bool {
        payload.keys.contains(where: { ["stdout", "stderr", "argv"].contains($0) })
    }

    enum CodingKeys: String, CodingKey {
        case id = "event_id"
        case jobId = "job_id"
        case type
        case sequence
        case payload
    }
}
