import CryptoKit
import Foundation

/// On-device `http-direct` for complete clients (iPhone, iPad, visionOS).
/// Direct media URLs download through URLSession into a user-approved Files
/// bookmark. Page locators and live manifests require a paired Mac. This path
/// never launches yt-dlp, ffmpeg, or gallery-dl.
public enum WebMediaDLHttpDirect {
    public static let providerId = "http-direct"
    public static let capabilityId = "acquire.http"
    public static let defaultMaxBytes = 512 * 1024 * 1024

    public static let directExtensions: [String: WebMediaDLMediaKind] = [
        ".mp4": .video,
        ".webm": .video,
        ".mkv": .video,
        ".mov": .video,
        ".m4v": .video,
        ".mp3": .audio,
        ".m4a": .audio,
        ".aac": .audio,
        ".flac": .audio,
        ".wav": .audio,
        ".ogg": .audio,
        ".opus": .audio,
        ".jpg": .image,
        ".jpeg": .image,
        ".png": .image,
        ".gif": .image,
        ".webp": .image,
        ".avif": .image,
        ".svg": .image,
        ".pdf": .document,
        ".vtt": .subtitle,
        ".srt": .subtitle,
        ".m3u8": .liveStream,
        ".mpd": .liveStream,
    ]

    public static let contentTypes: [String: String] = [
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/avif": ".avif",
        "audio/mpeg": ".mp3",
        "audio/mp4": ".m4a",
        "audio/aac": ".aac",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "application/pdf": ".pdf",
        "text/vtt": ".vtt",
        "application/vnd.apple.mpegurl": ".m3u8",
        "application/dash+xml": ".mpd",
    ]

    public enum TransferError: Error, LocalizedError, Equatable {
        case invalidLocator
        case pairingRequired
        case liveRequiresMac
        case filesDestinationRequired
        case destinationDenied
        case drmRefused(String)
        case httpStatus(Int)
        case overflow
        case writeFailed(String)
        case unsupportedSurface

        public var errorDescription: String? {
            switch self {
            case .invalidLocator:
                return "The locator is not an http(s) URL."
            case .pairingRequired:
                return "Pair with a Mac for yt-dlp or ffmpeg jobs."
            case .liveRequiresMac:
                return "Clear live manifests record on the paired Mac."
            case .filesDestinationRequired:
                return "Choose a Files destination first."
            case .destinationDenied:
                return "The Files destination bookmark is stale or outside the approved root."
            case .drmRefused(let joined):
                return "This source appears to use encrypted or DRM-protected media (\(joined)). WebMedia DL refuses DRM circumvention."
            case .httpStatus(let code):
                return "HTTP \(code) refused the media object."
            case .overflow:
                return "The download exceeded the complete-client byte bound."
            case .writeFailed(let message):
                return message
            case .unsupportedSurface:
                return "On-device http-direct runs on iPhone, iPad, visionOS, Mac, and CLI only."
            }
        }
    }

    public struct Result: Sendable {
        public var jobId: UUID
        public var outputPath: String
        public var sha256: String
        public var byteSize: Int
        public var mediaKind: WebMediaDLMediaKind
        public var artifactId: String
        public var providerId: String
        public var argv: [String]

        public init(
            jobId: UUID,
            outputPath: String,
            sha256: String,
            byteSize: Int,
            mediaKind: WebMediaDLMediaKind,
            artifactId: String,
            providerId: String = WebMediaDLHttpDirect.providerId,
            argv: [String] = []
        ) {
            self.jobId      = jobId
            self.outputPath = outputPath
            self.sha256     = sha256
            self.byteSize   = byteSize
            self.mediaKind  = mediaKind
            self.artifactId = artifactId
            self.providerId = providerId
            self.argv       = argv
        }
    }

    public typealias Fetch = @Sendable (URL) async throws -> (Int, [String: String], Data)

    public static func kind(for locator: String) -> WebMediaDLMediaKind {
        let path = (URL(string: locator)?.path ?? locator).lowercased()
        for (ext, kind) in directExtensions where path.hasSuffix(ext) {
            return kind
        }
        return .page
    }

    public static func isDirectMediaURL(_ locator: String) -> Bool {
        let kind = kind(for: locator)
        return kind != .page && kind != .unknown
    }

    public static func isOnDeviceTransfer(_ locator: String) -> Bool {
        let kind = kind(for: locator)
        return kind != .page && kind != .unknown && kind != .liveStream
    }

    public static func drmSignals(in texts: String...) -> [String] {
        drmSignals(in: texts)
    }

    public static func drmSignals(in texts: [String]) -> [String] {
        var hits: [String] = []
        let needles = [
            "widevine",
            "fairplay",
            "playready",
            "com.widevine.alpha",
            "streamingkeydelivery",
            "skd://",
            "urn:mpeg:cenc",
            "urn:mpeg:dash:mp4protection",
            "cenc:default_kid",
            "edef8ba9-79d6-4ace-a3c8-27dcd51d21ed",
            "9a04f079-9840-4286-ab92-e65be0885f95",
            "94ce86fb-cfb1-4a2e-967b-0374299925eb",
            "pssh",
            "encrypted-media",
            "clearkey",
        ]
        for text in texts {
            let lower = text.lowercased()
            for needle in needles where lower.contains(needle) {
                hits.append(needle)
            }
            if hlsKeyIsProtected(text) {
                hits.append("ext-x-key")
            }
            if lower.contains("value=\"cenc\"")
                || lower.contains("value='cenc'")
                || (lower.contains("schemeiduri") && lower.contains("cenc")) {
                hits.append("cenc")
            }
            if lower.contains("value=\"cbcs\"") || lower.contains("value='cbcs'") {
                hits.append("cbcs")
            }
        }
        return Array(Set(hits)).sorted()
    }

    public static func hlsKeyIsProtected(_ text: String) -> Bool {
        for raw in text.split(whereSeparator: \.isNewline) {
            let line = raw.uppercased()
            guard line.contains("EXT-X-KEY:") || line.contains("EXT-X-SESSION-KEY:") else { continue }
            guard let range = line.range(of: "METHOD=") else { continue }
            let rest = line[range.upperBound...]
            if !rest.hasPrefix("NONE") {
                return true
            }
        }
        return false
    }

    /// Filename stem under the Files bookmark. `.` / `..` / empty names become `source`.
    public static func outputStem(from url: URL) -> String {
        let raw = url.deletingPathExtension().lastPathComponent
        let safe = raw
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "\\", with: "_")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if safe.isEmpty || safe == "." || safe == ".." || safe == "/" {
            return "source"
        }
        return safe
    }

    public static func suffix(url: URL, headers: [String: String], body: Data) -> String {
        for (key, value) in headers where key.lowercased() == "content-type" {
            let type = value.split(separator: ";").first.map(String.init)?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
            if let mapped = contentTypes[type] {
                return mapped
            }
        }
        let path = url.path.lowercased()
        for ext in directExtensions.keys.sorted(by: { $0.count > $1.count }) where path.hasSuffix(ext) {
            return ext == ".jpeg" ? ".jpg" : ext
        }
        if body.starts(with: [0x89, 0x50, 0x4E, 0x47]) { return ".png" }
        if body.starts(with: [0xFF, 0xD8]) { return ".jpg" }
        return ".bin"
    }

    public static func transfer(
        locator: String,
        bookmark: WebMediaDLSecurityScopedBookmark,
        surface: WebMediaDLSurface = .ios,
        maxBytes: Int = defaultMaxBytes,
        fetch: Fetch? = nil
    ) async throws -> Result {
        if !WebMediaDLCapabilityRegistry.allows(.acquireHTTP, on: surface) {
            throw TransferError.unsupportedSurface
        }
        let trimmed = locator.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let url = URL(string: trimmed),
              let scheme = url.scheme?.lowercased(),
              scheme == "http" || scheme == "https"
        else {
            throw TransferError.invalidLocator
        }
        let kind = kind(for: trimmed)
        if kind == .liveStream {
            throw TransferError.liveRequiresMac
        }
        if kind == .page || kind == .unknown {
            throw TransferError.pairingRequired
        }
        let resolved = bookmark.resolve()
        let root = resolved.path.trimmingCharacters(in: .whitespacesAndNewlines)
        if root.isEmpty || resolved.stale {
            throw TransferError.filesDestinationRequired
        }
        let urlSignals = drmSignals(in: trimmed)
        if !urlSignals.isEmpty {
            throw TransferError.drmRefused(urlSignals.joined(separator: ", "))
        }
        let getter = fetch ?? defaultFetch(maxBytes: maxBytes)
        let (status, headers, body) = try await getter(url)
        if body.count > maxBytes {
            throw TransferError.overflow
        }
        if status >= 400 {
            throw TransferError.httpStatus(status)
        }
        let bodySignals = drmSignals(in: String(decoding: body, as: UTF8.self))
        if !bodySignals.isEmpty {
            throw TransferError.drmRefused(bodySignals.joined(separator: ", "))
        }
        let destRoot = URL(fileURLWithPath: root, isDirectory: true)
        let ext = suffix(url: url, headers: headers, body: body)
        let final = destRoot.appendingPathComponent(outputStem(from: url) + ext)
        if !resolved.allows(final.path) {
            throw TransferError.destinationDenied
        }
        let tmp = destRoot.appendingPathComponent(".webmedia-dl-\(UUID().uuidString).tmp")
        if !resolved.allows(tmp.path) {
            throw TransferError.destinationDenied
        }
        try withSecurityScope(resolved) {
            do {
                try FileManager.default.createDirectory(at: destRoot, withIntermediateDirectories: true)
                try body.write(to: tmp, options: .atomic)
                if FileManager.default.fileExists(atPath: final.path) {
                    try FileManager.default.removeItem(at: final)
                }
                try FileManager.default.moveItem(at: tmp, to: final)
            } catch let error as TransferError {
                try? FileManager.default.removeItem(at: tmp)
                throw error
            } catch {
                try? FileManager.default.removeItem(at: tmp)
                throw TransferError.writeFailed(error.localizedDescription)
            }
        }
        let digest = SHA256.hash(data: body)
        let hex = digest.map { String(format: "%02x", $0) }.joined()
        let jobId = UUID()
        return Result(
            jobId: jobId,
            outputPath: final.path,
            sha256: hex,
            byteSize: body.count,
            mediaKind: kind,
            artifactId: "sha256:\(hex)",
            providerId: providerId,
            argv: []
        )
    }

    /// Complete-client intents: save a direct object when a Files bookmark exists.
    /// Returns nil when the locator needs a paired Mac.
    public static func saveIfDirect(
        locator: String,
        bookmarkData: Data? = WebMediaDLWorkerCredentials.loadBookmark(),
        surface: WebMediaDLSurface = .ios,
        fetch: Fetch? = nil
    ) async throws -> Result? {
        guard isOnDeviceTransfer(locator) else { return nil }
        guard let bookmarkData else { return nil }
        let bookmark = WebMediaDLSecurityScopedBookmark(path: "", bookmarkData: bookmarkData).resolve()
        guard !bookmark.path.isEmpty, !bookmark.stale else { return nil }
        return try await transfer(locator: locator, bookmark: bookmark, surface: surface, fetch: fetch)
    }

    private static func withSecurityScope<T>(
        _ bookmark: WebMediaDLSecurityScopedBookmark,
        _ work: () throws -> T
    ) throws -> T {
        guard let data = bookmark.bookmarkData, !data.isEmpty else {
            return try work()
        }
        var stale = false
        let scoped: URL
        do {
            scoped = try URL(
                resolvingBookmarkData: data,
                options: [],
                relativeTo: nil,
                bookmarkDataIsStale: &stale
            )
        } catch {
            throw TransferError.destinationDenied
        }
        if stale {
            throw TransferError.destinationDenied
        }
        let accessed = scoped.startAccessingSecurityScopedResource()
        defer {
            if accessed {
                scoped.stopAccessingSecurityScopedResource()
            }
        }
        guard accessed else {
            throw TransferError.destinationDenied
        }
        return try work()
    }

    private static func defaultFetch(maxBytes: Int) -> Fetch {
        { url in
            var request = URLRequest(url: url)
            request.httpMethod = "GET"
            let (bytes, response) = try await URLSession.shared.bytes(for: request)
            guard let http = response as? HTTPURLResponse else {
                throw TransferError.httpStatus(0)
            }
            if let length = http.value(forHTTPHeaderField: "Content-Length"),
               let listed = Int(length),
               listed > maxBytes {
                throw TransferError.overflow
            }
            var headers: [String: String] = [:]
            for (key, value) in http.allHeaderFields {
                if let name = key as? String, let text = value as? String {
                    headers[name] = text
                }
            }
            var data = Data()
            data.reserveCapacity(min(maxBytes, 1_048_576))
            let chunkLimit = 65_536
            var chunk = [UInt8]()
            chunk.reserveCapacity(chunkLimit)
            for try await byte in bytes {
                chunk.append(byte)
                if chunk.count == chunkLimit {
                    data.append(contentsOf: chunk)
                    chunk.removeAll(keepingCapacity: true)
                    if data.count >= maxBytes {
                        throw TransferError.overflow
                    }
                }
            }
            if !chunk.isEmpty {
                data.append(contentsOf: chunk)
                if data.count >= maxBytes {
                    throw TransferError.overflow
                }
            }
            return (http.statusCode, headers, data)
        }
    }
}
