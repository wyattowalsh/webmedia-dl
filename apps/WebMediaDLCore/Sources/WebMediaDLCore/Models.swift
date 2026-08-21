import Foundation

public enum WebMediaDLSurface: String, Codable, Sendable {
    case macos, ios, ipados, visionos, watchos, tvos
    case safari, chrome, brave, edge, chromium, firefox, cli
}

public struct WebMediaDLJob: Codable, Sendable, Identifiable {
    public var id: UUID
    public var locator: String
    public var localPath: String?
    public var titleDisplay: String?
    public var surface: WebMediaDLSurface

    public init(
        id: UUID = UUID(),
        locator: String,
        localPath: String? = nil,
        titleDisplay: String? = nil,
        surface: WebMediaDLSurface
    ) {
        self.id = id
        self.locator = locator
        self.localPath = localPath
        self.titleDisplay = titleDisplay
        self.surface = surface
    }

    public var usesURLAsPath: Bool {
        locator.hasPrefix("http://") || locator.hasPrefix("https://") ? localPath != nil : false
    }

    public var titleUsedAsIdentity: Bool {
        guard let titleDisplay else { return false }
        return id.uuidString == titleDisplay
    }
}

/// watchOS and tvOS expose capture/status/history/controls, not subprocess workers.
public enum WebMediaDLClientRole: String, Codable, Sendable {
    case fullWorker
    case pairedClient
    case captureAndStatus
}
