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

    public static let completeClients: Set<WebMediaDLSurface> = [.ios, .ipados, .visionos]

    public var isCompleteClient: Bool { Self.completeClients.contains(self) }

    /// Phone Files bookmarks are not Mac paths. Complete-client `files_app`
    /// jobs become Mac `staging_only` so the client can pull bytes locally.
    public func macJobDestination(
        kind: String?,
        path: String?,
        approvedRoots: [String],
        bookmarkData: Data?
    ) -> (kind: String?, path: String?, roots: [String], bookmark: Data?) {
        guard let kind, !kind.isEmpty else {
            return (nil, nil, [], nil)
        }
        if isCompleteClient, kind == "files_app" {
            return ("staging_only", nil, [], nil)
        }
        return (kind, path, approvedRoots, bookmarkData)
    }
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
    public var createdAt: String?
    public var updatedAt: String?
    public var source: WebMediaDLMediaSource?
    public var intent: WebMediaDLExportIntent?

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
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case source
        case intent
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
        error: String? = nil,
        createdAt: String? = nil,
        updatedAt: String? = nil,
        source: WebMediaDLMediaSource? = nil,
        intent: WebMediaDLExportIntent? = nil
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
        self.createdAt       = createdAt
        self.updatedAt       = updatedAt
        self.source          = source
        self.intent          = intent
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

    public static func summary(_ entries: [WebMediaDLHistoryEntry]) -> String {
        if entries.isEmpty {
            return "No jobs yet."
        }
        return entries.map { "\($0.jobId.uuidString.prefix(8)) \($0.state)" }.joined(separator: "\n")
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
