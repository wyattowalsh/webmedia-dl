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

    public func allows(_ candidate: String) -> Bool {
        if stale { return false }
        let prefix = path.hasSuffix("/") ? path : path + "/"
        return candidate == path || candidate.hasPrefix(prefix)
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

/// Photos library writes stay closed without PhotoKit on a signed device.
public struct WebMediaDLPhotoKitDestination: Sendable {
    public var approvedRoot: String?
    public static let libraryWriteAvailable = false

    public init(approvedRoot: String? = nil) {
        self.approvedRoot = approvedRoot
    }

    public var canPublish: Bool {
        guard let approvedRoot, !approvedRoot.isEmpty else { return false }
        return Self.libraryWriteAvailable
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
