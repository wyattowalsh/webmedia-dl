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

public struct WebMediaDLHistoryEntry: Codable, Sendable, Identifiable {
    public var id: UUID { jobId }
    public var jobId: UUID
    public var state: String
    public var policyProfileId: String
    public var workerId: String
    public var artifactIds: [String]
    public var lastEvents: [String]
    public var partial: Bool
    public var failedKinds: [String]
    public var error: String?

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case state
        case policyProfileId = "policy_profile_id"
        case workerId = "worker_id"
        case artifactIds = "artifact_ids"
        case lastEvents = "last_events"
        case partial
        case failedKinds = "failed_kinds"
        case error
    }
}

/// watchOS and tvOS expose capture/status/history/controls, not subprocess workers.
public enum WebMediaDLClientRole: String, Codable, Sendable {
    case fullWorker
    case pairedClient
    case captureAndStatus
}
