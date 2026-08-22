import Foundation

/// Shared domain errors. Messages stay user-facing and fail closed.
public struct WebMediaDLDomainError: Error, LocalizedError, Equatable, Sendable {
    public var message: String

    public init(_ message: String) {
        self.message = message
    }

    public var errorDescription: String? { message }
}

public enum WebMediaDLMediaKind: String, Codable, Sendable {
    case video
    case audio
    case image
    case document
    case subtitle
    case liveStream = "live_stream"
    case gallery
    case page
    case unknown
}

public enum WebMediaDLIntakeKind: String, Codable, Sendable {
    case url
    case paste
    case shareSheet      = "share_sheet"
    case intent
    case cli
    case file
    case drop
    case browserEvidence = "browser_evidence"
    case liveManifest    = "live_manifest"
    case speak
}

public enum WebMediaDLArtifactRole: String, Codable, Sendable {
    case source
    case derivative
    case preview
}

public enum WebMediaDLLossClass: String, Codable, Sendable {
    case none
    case acceptable
    case forbidden
}

public enum WebMediaDLEvidenceStatus: String, Codable, Sendable {
    case pass    = "PASS"
    case fail    = "FAIL"
    case blocked = "BLOCKED"
    case warn    = "WARN"
}

public enum WebMediaDLCookieAccess: String, Codable, Sendable {
    case never
    case explicitPath = "explicit_path"
}

public enum WebMediaDLDestinationKind: String, Codable, Sendable {
    case stagingOnly      = "staging_only"
    case userApprovedPath = "user_approved_path"
    case filesApp         = "files_app"
    case photos
    case share
}

/// Typed intake. A source URL never becomes a filesystem path.
public struct WebMediaDLMediaSource: Codable, Sendable {
    public var sourceId: UUID
    public var kind: WebMediaDLIntakeKind
    public var locator: String
    public var normalizedURL: String?
    public var localPath: String?
    public var surface: WebMediaDLSurface
    public var policyProfileId: String

    enum CodingKeys: String, CodingKey {
        case sourceId         = "source_id"
        case kind
        case locator
        case normalizedURL    = "normalized_url"
        case localPath        = "local_path"
        case surface
        case policyProfileId  = "policy_profile_id"
    }

    public init(
        sourceId: UUID = UUID(),
        kind: WebMediaDLIntakeKind,
        locator: String,
        normalizedURL: String? = nil,
        localPath: String? = nil,
        surface: WebMediaDLSurface,
        policyProfileId: String
    ) throws {
        self.sourceId        = sourceId
        self.kind            = kind
        self.locator         = locator
        self.normalizedURL   = normalizedURL
        self.localPath       = localPath
        self.surface         = surface
        self.policyProfileId = policyProfileId
        try Self.validate(
            kind: kind,
            localPath: localPath,
            normalizedURL: normalizedURL
        )
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        sourceId        = try container.decode(UUID.self, forKey: .sourceId)
        kind            = try container.decode(WebMediaDLIntakeKind.self, forKey: .kind)
        locator         = try container.decode(String.self, forKey: .locator)
        normalizedURL   = try container.decodeIfPresent(String.self, forKey: .normalizedURL)
        localPath       = try container.decodeIfPresent(String.self, forKey: .localPath)
        surface         = try container.decode(WebMediaDLSurface.self, forKey: .surface)
        policyProfileId = try container.decode(String.self, forKey: .policyProfileId)
        try Self.validate(kind: kind, localPath: localPath, normalizedURL: normalizedURL)
    }

    private static let urlKinds: Set<WebMediaDLIntakeKind> = [
        .url, .paste, .shareSheet, .intent, .cli, .browserEvidence, .liveManifest, .speak,
    ]

    private static func validate(
        kind: WebMediaDLIntakeKind,
        localPath: String?,
        normalizedURL: String?
    ) throws {
        if urlKinds.contains(kind), localPath != nil {
            throw WebMediaDLDomainError("A source URL never becomes a filesystem path.")
        }
        if localPath != nil,
           normalizedURL != nil,
           kind != .file,
           kind != .drop {
            throw WebMediaDLDomainError("A source URL never becomes a filesystem path.")
        }
        if let normalizedURL, normalizedURL.hasPrefix("file:") {
            throw WebMediaDLDomainError("A source URL never becomes a filesystem path.")
        }
    }
}

public struct WebMediaDLCapability: Codable, Sendable {
    public var capabilityId: String
    public var providerId: String
    public var platforms: [WebMediaDLSurface]
    public var description: String
    public var health: String

    enum CodingKeys: String, CodingKey {
        case capabilityId = "capability_id"
        case providerId   = "provider_id"
        case platforms
        case description
        case health
    }

    public init(
        capabilityId: String,
        providerId: String,
        platforms: [WebMediaDLSurface],
        description: String,
        health: String = "healthy"
    ) {
        self.capabilityId = capabilityId
        self.providerId   = providerId
        self.platforms    = platforms
        self.description  = description
        self.health       = health
    }
}

/// Capability intersection used by complete clients. yt-dlp stays Mac/CLI.
public enum WebMediaDLCapabilityRegistry {
    public static let acquireHTTP = WebMediaDLCapability(
        capabilityId: "acquire.http",
        providerId: "http-direct",
        platforms: [.macos, .ios, .ipados, .visionos, .cli],
        description: "acquire http"
    )
    public static let acquireYtdlp = WebMediaDLCapability(
        capabilityId: "acquire.ytdlp",
        providerId: "ytdlp",
        platforms: [.macos, .cli],
        description: "acquire ytdlp"
    )
    public static let liveRecord = WebMediaDLCapability(
        capabilityId: "live.record_clear_manifest",
        providerId: "http-direct",
        platforms: [.macos, .cli],
        description: "live record clear manifest"
    )

    public static func allows(_ capability: WebMediaDLCapability, on surface: WebMediaDLSurface) -> Bool {
        capability.platforms.contains(surface)
    }
}

public struct WebMediaDLPolicyProfile: Codable, Sendable {
    public var profileId: String
    public var displayName: String
    public var allowedCapabilities: [String]
    public var cookieAccess: WebMediaDLCookieAccess
    public var drmCircumvention: Bool
    public var canDelegate: Bool
    public var subprocessWorker: Bool
    public var telemetryDefault: Bool
    public var maxDownloadBytes: Int

    enum CodingKeys: String, CodingKey {
        case profileId            = "profile_id"
        case displayName          = "display_name"
        case allowedCapabilities  = "allowed_capabilities"
        case cookieAccess         = "cookie_access"
        case drmCircumvention     = "drm_circumvention"
        case canDelegate          = "can_delegate"
        case subprocessWorker     = "subprocess_worker"
        case telemetryDefault     = "telemetry_default"
        case maxDownloadBytes     = "max_download_bytes"
    }

    public init(
        profileId: String,
        displayName: String,
        allowedCapabilities: [String],
        cookieAccess: WebMediaDLCookieAccess = .never,
        drmCircumvention: Bool = false,
        canDelegate: Bool = false,
        subprocessWorker: Bool = false,
        telemetryDefault: Bool = false,
        maxDownloadBytes: Int = 512 * 1024 * 1024
    ) throws {
        if drmCircumvention {
            throw WebMediaDLDomainError("DRM circumvention is forbidden.")
        }
        if telemetryDefault {
            throw WebMediaDLDomainError("Default telemetry is forbidden.")
        }
        self.profileId           = profileId
        self.displayName         = displayName
        self.allowedCapabilities = allowedCapabilities
        self.cookieAccess        = cookieAccess
        self.drmCircumvention    = false
        self.canDelegate         = canDelegate
        self.subprocessWorker    = subprocessWorker
        self.telemetryDefault    = false
        self.maxDownloadBytes    = maxDownloadBytes
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        let drm = try container.decodeIfPresent(Bool.self, forKey: .drmCircumvention) ?? false
        let telemetry = try container.decodeIfPresent(Bool.self, forKey: .telemetryDefault) ?? false
        try self.init(
            profileId: try container.decode(String.self, forKey: .profileId),
            displayName: try container.decode(String.self, forKey: .displayName),
            allowedCapabilities: try container.decodeIfPresent([String].self, forKey: .allowedCapabilities) ?? [],
            cookieAccess: try container.decodeIfPresent(WebMediaDLCookieAccess.self, forKey: .cookieAccess) ?? .never,
            drmCircumvention: drm,
            canDelegate: try container.decodeIfPresent(Bool.self, forKey: .canDelegate) ?? false,
            subprocessWorker: try container.decodeIfPresent(Bool.self, forKey: .subprocessWorker) ?? false,
            telemetryDefault: telemetry,
            maxDownloadBytes: try container.decodeIfPresent(Int.self, forKey: .maxDownloadBytes) ?? 512 * 1024 * 1024
        )
    }
}

public struct WebMediaDLWorker: Codable, Sendable {
    public var workerId: String
    public var platform: WebMediaDLSurface
    public var profileId: String
    public var capabilities: [String]
    public var paired: Bool
    public var subprocessCapable: Bool

    enum CodingKeys: String, CodingKey {
        case workerId           = "worker_id"
        case platform
        case profileId          = "profile_id"
        case capabilities
        case paired
        case subprocessCapable  = "subprocess_capable"
    }

    public init(
        workerId: String,
        platform: WebMediaDLSurface,
        profileId: String,
        capabilities: [String],
        paired: Bool = false,
        subprocessCapable: Bool = true
    ) {
        self.workerId           = workerId
        self.platform           = platform
        self.profileId          = profileId
        self.capabilities       = capabilities
        self.paired             = paired
        self.subprocessCapable  = subprocessCapable
    }
}

public struct WebMediaDLAcquisitionStrategy: Codable, Sendable {
    public var strategyId: String
    public var providerId: String
    public var capabilityId: String
    public var typedInputs: [String: String]
    public var estimatedLoss: WebMediaDLLossClass
    public var rank: Int
    public var extraArgs: [String]

    enum CodingKeys: String, CodingKey {
        case strategyId     = "strategy_id"
        case providerId     = "provider_id"
        case capabilityId   = "capability_id"
        case typedInputs    = "typed_inputs"
        case estimatedLoss  = "estimated_loss"
        case rank
        case extraArgs      = "extra_args"
    }

    public init(
        strategyId: String,
        providerId: String,
        capabilityId: String,
        typedInputs: [String: String] = [:],
        estimatedLoss: WebMediaDLLossClass = .none,
        rank: Int = 0,
        extraArgs: [String] = []
    ) throws {
        try Self.validate(extraArgs: extraArgs)
        self.strategyId    = strategyId
        self.providerId    = providerId
        self.capabilityId  = capabilityId
        self.typedInputs   = typedInputs
        self.estimatedLoss = estimatedLoss
        self.rank          = rank
        self.extraArgs     = []
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        strategyId    = try container.decode(String.self, forKey: .strategyId)
        providerId    = try container.decode(String.self, forKey: .providerId)
        capabilityId  = try container.decode(String.self, forKey: .capabilityId)
        typedInputs   = try container.decodeIfPresent([String: String].self, forKey: .typedInputs) ?? [:]
        estimatedLoss = try container.decodeIfPresent(WebMediaDLLossClass.self, forKey: .estimatedLoss) ?? .none
        rank          = try container.decodeIfPresent(Int.self, forKey: .rank) ?? 0
        extraArgs     = try container.decodeIfPresent([String].self, forKey: .extraArgs) ?? []
        try Self.validate(extraArgs: extraArgs)
        extraArgs = []
    }

    private static func validate(extraArgs: [String]) throws {
        if !extraArgs.isEmpty {
            throw WebMediaDLDomainError("A provider never receives arbitrary user arguments.")
        }
    }
}

public struct WebMediaDLAcquisitionPlan: Codable, Sendable {
    public var planId: UUID
    public var jobId: UUID
    public var candidateId: UUID
    public var strategies: [WebMediaDLAcquisitionStrategy]

    enum CodingKeys: String, CodingKey {
        case planId      = "plan_id"
        case jobId       = "job_id"
        case candidateId = "candidate_id"
        case strategies
    }

    public init(
        planId: UUID = UUID(),
        jobId: UUID,
        candidateId: UUID,
        strategies: [WebMediaDLAcquisitionStrategy] = []
    ) {
        self.planId      = planId
        self.jobId       = jobId
        self.candidateId = candidateId
        self.strategies  = strategies
    }
}

public struct WebMediaDLArtifact: Codable, Sendable {
    public var artifactId: String
    public var role: WebMediaDLArtifactRole
    public var sha256: String
    public var byteSize: Int
    public var mediaKind: WebMediaDLMediaKind
    public var storageRelpath: String
    public var immutable: Bool
    public var provenance: [String: String]

    enum CodingKeys: String, CodingKey {
        case artifactId     = "artifact_id"
        case role
        case sha256
        case byteSize       = "byte_size"
        case mediaKind      = "media_kind"
        case storageRelpath = "storage_relpath"
        case immutable
        case provenance
    }

    public init(
        artifactId: String,
        role: WebMediaDLArtifactRole,
        sha256: String,
        byteSize: Int,
        mediaKind: WebMediaDLMediaKind,
        storageRelpath: String,
        immutable: Bool = false,
        provenance: [String: String] = [:]
    ) throws {
        if artifactId == provenance["title"] {
            throw WebMediaDLDomainError("A display title never becomes artifact identity.")
        }
        self.artifactId     = artifactId
        self.role           = role
        self.sha256         = sha256
        self.byteSize       = byteSize
        self.mediaKind      = mediaKind
        self.storageRelpath = storageRelpath
        self.immutable      = role == .source ? true : immutable
        self.provenance     = provenance
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        try self.init(
            artifactId: try container.decode(String.self, forKey: .artifactId),
            role: try container.decode(WebMediaDLArtifactRole.self, forKey: .role),
            sha256: try container.decode(String.self, forKey: .sha256),
            byteSize: try container.decode(Int.self, forKey: .byteSize),
            mediaKind: try container.decode(WebMediaDLMediaKind.self, forKey: .mediaKind),
            storageRelpath: try container.decode(String.self, forKey: .storageRelpath),
            immutable: try container.decodeIfPresent(Bool.self, forKey: .immutable) ?? false,
            provenance: try container.decodeIfPresent([String: String].self, forKey: .provenance) ?? [:]
        )
    }
}

public struct WebMediaDLExportIntent: Codable, Sendable {
    public var presetId: String
    public var destinationKind: WebMediaDLDestinationKind
    public var destinationPath: String?
    public var approvedRoots: [String]
    public var securityScopedBookmark: String?

    enum CodingKeys: String, CodingKey {
        case presetId                = "preset_id"
        case destinationKind         = "destination_kind"
        case destinationPath         = "destination_path"
        case approvedRoots           = "approved_roots"
        case securityScopedBookmark  = "security_scoped_bookmark"
    }

    public init(
        presetId: String = "original-sacred",
        destinationKind: WebMediaDLDestinationKind = .stagingOnly,
        destinationPath: String? = nil,
        approvedRoots: [String] = [],
        securityScopedBookmark: String? = nil
    ) throws {
        let cleaned = approvedRoots.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        let pathKinds: Set<WebMediaDLDestinationKind> = [.userApprovedPath, .filesApp, .share]
        if pathKinds.contains(destinationKind) {
            let dest = (destinationPath ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if dest.isEmpty || cleaned.isEmpty {
                throw WebMediaDLDomainError("Publication destinations require an approved path and root.")
            }
        }
        if destinationKind == .filesApp, (securityScopedBookmark ?? "").trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            throw WebMediaDLDomainError("Files destinations require a security-scoped bookmark.")
        }
        self.presetId               = presetId
        self.destinationKind        = destinationKind
        self.destinationPath        = destinationPath
        self.approvedRoots          = cleaned
        self.securityScopedBookmark = securityScopedBookmark
    }
}

public struct WebMediaDLExportPlan: Codable, Sendable {
    public var planId: UUID
    public var jobId: UUID
    public var publishSource: Bool

    enum CodingKeys: String, CodingKey {
        case planId        = "plan_id"
        case jobId         = "job_id"
        case publishSource = "publish_source"
    }

    public init(planId: UUID = UUID(), jobId: UUID, publishSource: Bool = true) {
        self.planId        = planId
        self.jobId         = jobId
        self.publishSource = publishSource
    }
}

public struct WebMediaDLValidationResult: Codable, Sendable {
    public var resultId: UUID
    public var jobId: UUID
    public var targetArtifactId: String
    public var gateId: String
    public var status: WebMediaDLEvidenceStatus
    public var message: String
    public var simulated: Bool
    public var planned: Bool
    public var executed: Bool

    enum CodingKeys: String, CodingKey {
        case resultId         = "result_id"
        case jobId            = "job_id"
        case targetArtifactId = "target_artifact_id"
        case gateId           = "gate_id"
        case status
        case message
        case simulated
        case planned
        case executed
    }

    public init(
        resultId: UUID = UUID(),
        jobId: UUID,
        targetArtifactId: String,
        gateId: String,
        status: WebMediaDLEvidenceStatus,
        message: String,
        simulated: Bool = false,
        planned: Bool = false,
        executed: Bool = true
    ) throws {
        if status == .pass, simulated || planned || !executed {
            throw WebMediaDLDomainError("A planned or simulated check never becomes runtime PASS.")
        }
        self.resultId         = resultId
        self.jobId            = jobId
        self.targetArtifactId = targetArtifactId
        self.gateId           = gateId
        self.status           = status
        self.message          = message
        self.simulated        = simulated
        self.planned          = planned
        self.executed         = executed
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        try self.init(
            resultId: try container.decodeIfPresent(UUID.self, forKey: .resultId) ?? UUID(),
            jobId: try container.decode(UUID.self, forKey: .jobId),
            targetArtifactId: try container.decode(String.self, forKey: .targetArtifactId),
            gateId: try container.decode(String.self, forKey: .gateId),
            status: try container.decode(WebMediaDLEvidenceStatus.self, forKey: .status),
            message: try container.decode(String.self, forKey: .message),
            simulated: try container.decodeIfPresent(Bool.self, forKey: .simulated) ?? false,
            planned: try container.decodeIfPresent(Bool.self, forKey: .planned) ?? false,
            executed: try container.decodeIfPresent(Bool.self, forKey: .executed) ?? true
        )
    }
}
