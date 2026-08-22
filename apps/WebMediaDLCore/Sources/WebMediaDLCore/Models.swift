import Foundation

public struct WebMediaDLUncheckedBox<Value>: @unchecked Sendable {
    public let value: Value

    public init(_ value: Value) {
        self.value = value
    }
}

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

    public init(
        jobId: UUID,
        state: String,
        policyProfileId: String = "",
        workerId: String = "",
        artifactIds: [String] = [],
        lastEvents: [String] = [],
        partial: Bool = false,
        failedKinds: [String] = [],
        error: String? = nil
    ) {
        self.jobId           = jobId
        self.state           = state
        self.policyProfileId = policyProfileId
        self.workerId        = workerId
        self.artifactIds     = artifactIds
        self.lastEvents      = lastEvents
        self.partial         = partial
        self.failedKinds     = failedKinds
        self.error           = error
    }

    public static func decodeList(from data: Data) throws -> [WebMediaDLHistoryEntry] {
        try JSONDecoder().decode([WebMediaDLHistoryEntry].self, from: data)
    }

    public static func decodeCompanionHistory(from data: Data) throws -> [WebMediaDLHistoryEntry] {
        if let wrapped = try? JSONDecoder().decode(WebMediaDLCompanionHistoryEnvelope.self, from: data) {
            return wrapped.jobs
        }
        return try decodeList(from: data)
    }
}

public struct WebMediaDLCompanionHistoryEnvelope: Codable, Sendable {
    public var kind: String?
    public var jobs: [WebMediaDLHistoryEntry]
}

public struct WebMediaDLPairingChallenge: Codable, Sendable {
    public var pairingId: UUID
    public var nonce: String
    public var expiresAt: String
    public var workerId: String?
    public var confirmed: Bool?

    enum CodingKeys: String, CodingKey {
        case pairingId = "pairing_id"
        case nonce
        case expiresAt = "expires_at"
        case workerId = "worker_id"
        case confirmed
    }
}

public struct WebMediaDLPairingConfirmation: Codable, Sendable {
    public var pairingId: UUID
    public var confirmed: Bool
    public var sessionKey: String?
    public var expiresAt: String?

    enum CodingKeys: String, CodingKey {
        case pairingId = "pairing_id"
        case confirmed
        case sessionKey = "session_key"
        case expiresAt = "expires_at"
    }
}

/// watchOS and tvOS expose capture/status/history/controls, not subprocess workers.
public enum WebMediaDLClientRole: String, Codable, Sendable {
    case fullWorker
    case pairedClient
    case captureAndStatus
}
