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
    case evidence
    case quarantine
}

public enum WebMediaDLLossClass: String, Codable, Sendable {
    case none
    case containerOnly      = "container_only"
    case reversibleMetadata = "reversible_metadata"
    case lossyTranscode     = "lossy_transcode"
    case semanticRisk       = "semantic_risk"
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

public enum WebMediaDLJobState: String, Codable, Sendable {
    case accepted
    case discovering
    case planning
    case acquiring
    case exporting
    case validating
    case publishing
    case completed
    case failed
    case cancelled
    case paused
    case quarantined
}

public enum WebMediaDLEventType: String, Codable, Sendable {
    case jobAccepted              = "job.accepted"
    case intakeNormalized         = "intake.normalized"
    case discoveryPartial         = "discovery.partial"
    case discoveryCompleted       = "discovery.completed"
    case graphBuilt               = "graph.built"
    case planRanked               = "plan.ranked"
    case acquisitionStarted       = "acquisition.started"
    case acquisitionQuarantine    = "acquisition.quarantine"
    case artifactSourceRegistered = "artifact.source_registered"
    case artifactEvidenceRegistered = "artifact.evidence_registered"
    case cookieAttached           = "cookie.attached"
    case companionReceived        = "companion.received"
    case exportPlanned            = "export.planned"
    case operationCompleted       = "operation.completed"
    case operationFailed          = "operation.failed"
    case validationRecorded       = "validation.recorded"
    case publicationCommitted     = "publication.committed"
    case jobFailed                = "job.failed"
    case jobCompleted             = "job.completed"
    case jobCancelled             = "job.cancelled"
    case jobPaused                = "job.paused"
    case jobResumed               = "job.resumed"
    case queuePaused              = "queue.paused"
    case queueResumed             = "queue.resumed"
    case mediaProbed              = "media.probed"
}

public enum WebMediaDLGraphRelation: String, Codable, Sendable {
    case alternativeOf = "alternative_of"
    case groupedWith   = "grouped_with"
    case derivedFrom   = "derived_from"
    case conflictsWith = "conflicts_with"
}

/// Typed intake. A source URL never becomes a filesystem path.
public struct WebMediaDLMediaSource: Codable, Sendable {
    public var sourceId: UUID
    public var kind: WebMediaDLIntakeKind
    public var locator: String
    public var normalizedURL: String?
    public var localPath: String?
    public var submittedAt: String?
    public var surface: WebMediaDLSurface
    public var policyProfileId: String
    public var contentTypeHint: String?

    enum CodingKeys: String, CodingKey {
        case sourceId         = "source_id"
        case kind
        case locator
        case normalizedURL    = "normalized_url"
        case localPath        = "local_path"
        case submittedAt      = "submitted_at"
        case surface
        case policyProfileId  = "policy_profile_id"
        case contentTypeHint  = "content_type_hint"
    }

    public init(
        sourceId: UUID = UUID(),
        kind: WebMediaDLIntakeKind,
        locator: String,
        normalizedURL: String? = nil,
        localPath: String? = nil,
        submittedAt: String? = nil,
        surface: WebMediaDLSurface,
        policyProfileId: String,
        contentTypeHint: String? = nil
    ) throws {
        self.sourceId        = sourceId
        self.kind            = kind
        self.locator         = locator
        self.normalizedURL   = normalizedURL
        self.localPath       = localPath
        self.submittedAt     = submittedAt
        self.surface         = surface
        self.policyProfileId = policyProfileId
        self.contentTypeHint = contentTypeHint
        try Self.validate(
            kind: kind,
            localPath: localPath,
            normalizedURL: normalizedURL
        )
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        sourceId        = try container.decodeIfPresent(UUID.self, forKey: .sourceId) ?? UUID()
        kind            = try container.decode(WebMediaDLIntakeKind.self, forKey: .kind)
        locator         = try container.decode(String.self, forKey: .locator)
        normalizedURL   = try container.decodeIfPresent(String.self, forKey: .normalizedURL)
        localPath       = try container.decodeIfPresent(String.self, forKey: .localPath)
        submittedAt     = try container.decodeIfPresent(String.self, forKey: .submittedAt)
        surface         = try container.decode(WebMediaDLSurface.self, forKey: .surface)
        policyProfileId = try container.decode(String.self, forKey: .policyProfileId)
        contentTypeHint = try container.decodeIfPresent(String.self, forKey: .contentTypeHint)
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
    public var requiredEntitlements: [String]

    enum CodingKeys: String, CodingKey {
        case capabilityId         = "capability_id"
        case providerId           = "provider_id"
        case platforms
        case description
        case health
        case requiredEntitlements = "required_entitlements"
    }

    public init(
        capabilityId: String,
        providerId: String,
        platforms: [WebMediaDLSurface],
        description: String,
        health: String = "healthy",
        requiredEntitlements: [String] = []
    ) {
        self.capabilityId         = capabilityId
        self.providerId           = providerId
        self.platforms            = platforms
        self.description          = description
        self.health               = health
        self.requiredEntitlements = requiredEntitlements
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        capabilityId         = try container.decode(String.self, forKey: .capabilityId)
        providerId           = try container.decode(String.self, forKey: .providerId)
        platforms            = try container.decode([WebMediaDLSurface].self, forKey: .platforms)
        description          = try container.decode(String.self, forKey: .description)
        health               = try container.decodeIfPresent(String.self, forKey: .health) ?? "healthy"
        requiredEntitlements = try container.decodeIfPresent([String].self, forKey: .requiredEntitlements) ?? []
    }

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
}

/// Capability intersection used by complete clients. yt-dlp stays Mac/CLI.
public enum WebMediaDLCapabilityRegistry {
    public static let acquireHTTP  = WebMediaDLCapability.acquireHTTP
    public static let acquireYtdlp = WebMediaDLCapability.acquireYtdlp
    public static let liveRecord   = WebMediaDLCapability.liveRecord

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
    public var networkSchemes: [String]
    public var maxHtmlBytes: Int
    public var maxDownloadBytes: Int
    public var maxRedirects: Int

    enum CodingKeys: String, CodingKey {
        case profileId            = "profile_id"
        case displayName          = "display_name"
        case allowedCapabilities  = "allowed_capabilities"
        case cookieAccess         = "cookie_access"
        case drmCircumvention     = "drm_circumvention"
        case canDelegate          = "can_delegate"
        case subprocessWorker     = "subprocess_worker"
        case networkSchemes       = "network_schemes"
        case maxHtmlBytes         = "max_html_bytes"
        case maxDownloadBytes     = "max_download_bytes"
        case maxRedirects         = "max_redirects"
        case telemetryDefault     = "telemetry_default"
    }

    public init(
        profileId: String,
        displayName: String,
        allowedCapabilities: [String],
        cookieAccess: WebMediaDLCookieAccess = .never,
        drmCircumvention: Bool = false,
        canDelegate: Bool = false,
        subprocessWorker: Bool = true,
        telemetryDefault: Bool = false,
        networkSchemes: [String] = ["https"],
        maxHtmlBytes: Int = 2_000_000,
        maxDownloadBytes: Int = 512 * 1024 * 1024,
        maxRedirects: Int = 5
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
        self.networkSchemes      = networkSchemes
        self.maxHtmlBytes        = maxHtmlBytes
        self.maxDownloadBytes    = maxDownloadBytes
        self.maxRedirects        = maxRedirects
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
            subprocessWorker: try container.decodeIfPresent(Bool.self, forKey: .subprocessWorker) ?? true,
            telemetryDefault: telemetry,
            networkSchemes: try container.decodeIfPresent([String].self, forKey: .networkSchemes) ?? ["https"],
            maxHtmlBytes: try container.decodeIfPresent(Int.self, forKey: .maxHtmlBytes) ?? 2_000_000,
            maxDownloadBytes: try container.decodeIfPresent(Int.self, forKey: .maxDownloadBytes) ?? 512 * 1024 * 1024,
            maxRedirects: try container.decodeIfPresent(Int.self, forKey: .maxRedirects) ?? 5
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

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        workerId          = try container.decode(String.self, forKey: .workerId)
        platform          = try container.decode(WebMediaDLSurface.self, forKey: .platform)
        profileId         = try container.decode(String.self, forKey: .profileId)
        capabilities      = try container.decode([String].self, forKey: .capabilities)
        paired            = try container.decodeIfPresent(Bool.self, forKey: .paired) ?? false
        subprocessCapable = try container.decodeIfPresent(Bool.self, forKey: .subprocessCapable) ?? true
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

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        planId      = try container.decodeIfPresent(UUID.self, forKey: .planId) ?? UUID()
        jobId       = try container.decode(UUID.self, forKey: .jobId)
        candidateId = try container.decode(UUID.self, forKey: .candidateId)
        strategies  = try container.decodeIfPresent([WebMediaDLAcquisitionStrategy].self, forKey: .strategies) ?? []
    }
}

public struct WebMediaDLArtifact: Codable, Sendable {
    public var artifactId: String
    public var role: WebMediaDLArtifactRole
    public var sha256: String
    public var byteSize: Int
    public var mediaKind: WebMediaDLMediaKind
    public var container: String?
    public var storageRelpath: String
    public var parentIds: [String]
    public var registeredAt: String?
    public var immutable: Bool
    public var provenance: [String: String]

    enum CodingKeys: String, CodingKey {
        case artifactId     = "artifact_id"
        case role
        case sha256
        case byteSize       = "byte_size"
        case mediaKind      = "media_kind"
        case container
        case storageRelpath = "storage_relpath"
        case parentIds      = "parent_ids"
        case registeredAt   = "registered_at"
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
        container: String? = nil,
        parentIds: [String] = [],
        registeredAt: String? = nil,
        immutable: Bool = false,
        provenance: [String: String] = [:]
    ) throws {
        if artifactId == provenance["title"] {
            throw WebMediaDLDomainError("A display title never becomes artifact identity.")
        }
        if role == .source, artifactId != "sha256:\(sha256)" {
            throw WebMediaDLDomainError("Source artifacts SHALL be identified as sha256:<digest>.")
        }
        self.artifactId     = artifactId
        self.role           = role
        self.sha256         = sha256
        self.byteSize       = byteSize
        self.mediaKind      = mediaKind
        self.container      = container
        self.storageRelpath = storageRelpath
        self.parentIds      = parentIds
        self.registeredAt   = registeredAt
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
            container: try container.decodeIfPresent(String.self, forKey: .container),
            parentIds: try container.decodeIfPresent([String].self, forKey: .parentIds) ?? [],
            registeredAt: try container.decodeIfPresent(String.self, forKey: .registeredAt),
            immutable: try container.decodeIfPresent(Bool.self, forKey: .immutable) ?? false,
            provenance: try container.decodeIfPresent([String: String].self, forKey: .provenance) ?? [:]
        )
    }
}

public struct WebMediaDLExportIntent: Codable, Sendable {
    public var presetId: String
    public var destinationKind: WebMediaDLDestinationKind
    public var destinationPath: String?
    public var includeOriginal: Bool
    public var allowLossy: Bool
    public var containerPreference: String?
    public var approvedRoots: [String]
    public var securityScopedPath: String?
    public var securityScopedBookmark: String?

    enum CodingKeys: String, CodingKey {
        case presetId                = "preset_id"
        case destinationKind         = "destination_kind"
        case destinationPath         = "destination_path"
        case includeOriginal         = "include_original"
        case allowLossy              = "allow_lossy"
        case containerPreference     = "container_preference"
        case approvedRoots           = "approved_roots"
        case securityScopedPath      = "security_scoped_path"
        case securityScopedBookmark  = "security_scoped_bookmark"
    }

    public init(
        presetId: String = "original-sacred",
        destinationKind: WebMediaDLDestinationKind = .stagingOnly,
        destinationPath: String? = nil,
        includeOriginal: Bool = true,
        allowLossy: Bool = false,
        containerPreference: String? = nil,
        approvedRoots: [String] = [],
        securityScopedPath: String? = nil,
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
        if destinationKind == .photos, cleaned.isEmpty {
            throw WebMediaDLDomainError("Photos publication requires a user-approved root.")
        }
        var scoped = (securityScopedPath ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if destinationKind == .filesApp {
            if scoped.isEmpty {
                scoped = (destinationPath ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            }
            let bookmark = (securityScopedBookmark ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if bookmark.isEmpty {
                throw WebMediaDLDomainError("Files destinations require a security-scoped bookmark.")
            }
            let allowed = cleaned.contains { root in
                WebMediaDLSecurityScopedBookmark(path: root).allows(scoped)
            }
            if !allowed {
                throw WebMediaDLDomainError("Files security-scoped path must stay inside approved roots.")
            }
        }
        self.presetId               = presetId
        self.destinationKind        = destinationKind
        self.destinationPath        = destinationPath
        self.includeOriginal        = includeOriginal
        self.allowLossy             = allowLossy
        self.containerPreference    = containerPreference
        self.approvedRoots          = cleaned
        self.securityScopedPath     = destinationKind == .filesApp ? (scoped.isEmpty ? destinationPath : scoped) : securityScopedPath
        self.securityScopedBookmark = securityScopedBookmark
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        try self.init(
            presetId: try container.decodeIfPresent(String.self, forKey: .presetId) ?? "original-sacred",
            destinationKind: try container.decodeIfPresent(WebMediaDLDestinationKind.self, forKey: .destinationKind) ?? .stagingOnly,
            destinationPath: try container.decodeIfPresent(String.self, forKey: .destinationPath),
            includeOriginal: try container.decodeIfPresent(Bool.self, forKey: .includeOriginal) ?? true,
            allowLossy: try container.decodeIfPresent(Bool.self, forKey: .allowLossy) ?? false,
            containerPreference: try container.decodeIfPresent(String.self, forKey: .containerPreference),
            approvedRoots: try container.decodeIfPresent([String].self, forKey: .approvedRoots) ?? [],
            securityScopedPath: try container.decodeIfPresent(String.self, forKey: .securityScopedPath),
            securityScopedBookmark: try container.decodeIfPresent(String.self, forKey: .securityScopedBookmark)
        )
    }

    public static let stagingFallback = try! WebMediaDLExportIntent()
}

public struct WebMediaDLOperation: Codable, Sendable {
    public var operationId: String
    public var opType: String
    public var capabilityId: String
    public var inputArtifactIds: [String]
    public var outputRole: WebMediaDLArtifactRole
    public var lossClass: WebMediaDLLossClass
    public var validatorIds: [String]
    public var typedInputs: [String: String]
    public var optional: Bool

    enum CodingKeys: String, CodingKey {
        case operationId      = "operation_id"
        case opType           = "op_type"
        case capabilityId     = "capability_id"
        case inputArtifactIds = "input_artifact_ids"
        case outputRole       = "output_role"
        case lossClass        = "loss_class"
        case validatorIds     = "validator_ids"
        case typedInputs      = "typed_inputs"
        case optional
    }

    public init(
        operationId: String,
        opType: String,
        capabilityId: String,
        inputArtifactIds: [String],
        outputRole: WebMediaDLArtifactRole,
        lossClass: WebMediaDLLossClass,
        validatorIds: [String],
        typedInputs: [String: String] = [:],
        optional: Bool = false
    ) {
        self.operationId      = operationId
        self.opType           = opType
        self.capabilityId     = capabilityId
        self.inputArtifactIds = inputArtifactIds
        self.outputRole       = outputRole
        self.lossClass        = lossClass
        self.validatorIds     = validatorIds
        self.typedInputs      = typedInputs
        self.optional         = optional
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        operationId      = try container.decode(String.self, forKey: .operationId)
        opType           = try container.decode(String.self, forKey: .opType)
        capabilityId     = try container.decode(String.self, forKey: .capabilityId)
        inputArtifactIds = try container.decode([String].self, forKey: .inputArtifactIds)
        outputRole       = try container.decode(WebMediaDLArtifactRole.self, forKey: .outputRole)
        lossClass        = try container.decode(WebMediaDLLossClass.self, forKey: .lossClass)
        validatorIds     = try container.decode([String].self, forKey: .validatorIds)
        typedInputs      = try container.decodeIfPresent([String: String].self, forKey: .typedInputs) ?? [:]
        optional         = try container.decodeIfPresent(Bool.self, forKey: .optional) ?? false
    }
}

public struct WebMediaDLExportPlan: Codable, Sendable {
    public var planId: UUID
    public var jobId: UUID
    public var operations: [WebMediaDLOperation]
    public var publishSource: Bool

    enum CodingKeys: String, CodingKey {
        case planId        = "plan_id"
        case jobId         = "job_id"
        case operations
        case publishSource = "publish_source"
    }

    public init(
        planId: UUID = UUID(),
        jobId: UUID,
        operations: [WebMediaDLOperation] = [],
        publishSource: Bool = true
    ) {
        self.planId        = planId
        self.jobId         = jobId
        self.operations    = operations
        self.publishSource = publishSource
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        planId        = try container.decodeIfPresent(UUID.self, forKey: .planId) ?? UUID()
        jobId         = try container.decode(UUID.self, forKey: .jobId)
        operations    = try container.decodeIfPresent([WebMediaDLOperation].self, forKey: .operations) ?? []
        publishSource = try container.decodeIfPresent(Bool.self, forKey: .publishSource) ?? true
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
    public var details: [String: String]

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
        case details
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
        executed: Bool = true,
        details: [String: String] = [:]
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
        self.details          = details
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
            executed: try container.decodeIfPresent(Bool.self, forKey: .executed) ?? true,
            details: try container.decodeIfPresent([String: String].self, forKey: .details) ?? [:]
        )
    }
}

public struct WebMediaDLFormatAlternative: Codable, Sendable {
    public var formatId: String
    public var container: String?
    public var codec: String?
    public var vcodec: String?
    public var acodec: String?
    public var width: Int?
    public var height: Int?
    public var bitrate: Int?
    public var note: String?
    public var drm: Bool

    enum CodingKeys: String, CodingKey {
        case formatId = "format_id"
        case container
        case codec
        case vcodec
        case acodec
        case width
        case height
        case bitrate
        case note
        case drm
    }

    public init(
        formatId: String,
        container: String? = nil,
        codec: String? = nil,
        vcodec: String? = nil,
        acodec: String? = nil,
        width: Int? = nil,
        height: Int? = nil,
        bitrate: Int? = nil,
        note: String? = nil,
        drm: Bool = false
    ) {
        self.formatId  = formatId
        self.container = container
        self.codec     = codec
        self.vcodec    = vcodec
        self.acodec    = acodec
        self.width     = width
        self.height    = height
        self.bitrate   = bitrate
        self.note      = note
        self.drm       = drm
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        formatId  = try container.decode(String.self, forKey: .formatId)
        self.container = try container.decodeIfPresent(String.self, forKey: .container)
        codec     = try container.decodeIfPresent(String.self, forKey: .codec)
        vcodec    = try container.decodeIfPresent(String.self, forKey: .vcodec)
        acodec    = try container.decodeIfPresent(String.self, forKey: .acodec)
        width     = try container.decodeIfPresent(Int.self, forKey: .width)
        height    = try container.decodeIfPresent(Int.self, forKey: .height)
        bitrate   = try container.decodeIfPresent(Int.self, forKey: .bitrate)
        note      = try container.decodeIfPresent(String.self, forKey: .note)
        drm       = try container.decodeIfPresent(Bool.self, forKey: .drm) ?? false
    }
}

public struct WebMediaDLMediaCandidate: Codable, Sendable {
    public var candidateId: UUID
    public var sourceId: UUID
    public var mediaKind: WebMediaDLMediaKind
    public var identityKey: String
    public var titleDisplay: String?
    public var groupingKey: String?
    public var retrievalUrls: [String]
    public var alternatives: [WebMediaDLFormatAlternative]
    public var drmSignals: [String]
    public var conflicts: [String]
    public var evidenceRefs: [String]
    public var host: String?

    enum CodingKeys: String, CodingKey {
        case candidateId   = "candidate_id"
        case sourceId      = "source_id"
        case mediaKind     = "media_kind"
        case identityKey   = "identity_key"
        case titleDisplay  = "title_display"
        case groupingKey   = "grouping_key"
        case retrievalUrls = "retrieval_urls"
        case alternatives
        case drmSignals    = "drm_signals"
        case conflicts
        case evidenceRefs  = "evidence_refs"
        case host
    }

    public init(
        candidateId: UUID = UUID(),
        sourceId: UUID,
        mediaKind: WebMediaDLMediaKind,
        identityKey: String,
        titleDisplay: String? = nil,
        groupingKey: String? = nil,
        retrievalUrls: [String] = [],
        alternatives: [WebMediaDLFormatAlternative] = [],
        drmSignals: [String] = [],
        conflicts: [String] = [],
        evidenceRefs: [String] = [],
        host: String? = nil
    ) throws {
        try Self.validate(identityKey: identityKey, titleDisplay: titleDisplay)
        self.candidateId   = candidateId
        self.sourceId      = sourceId
        self.mediaKind     = mediaKind
        self.identityKey   = identityKey
        self.titleDisplay  = titleDisplay
        self.groupingKey   = groupingKey
        self.retrievalUrls = retrievalUrls
        self.alternatives  = alternatives
        self.drmSignals    = drmSignals
        self.conflicts     = conflicts
        self.evidenceRefs  = evidenceRefs
        self.host          = host
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        try self.init(
            candidateId: try container.decodeIfPresent(UUID.self, forKey: .candidateId) ?? UUID(),
            sourceId: try container.decode(UUID.self, forKey: .sourceId),
            mediaKind: try container.decode(WebMediaDLMediaKind.self, forKey: .mediaKind),
            identityKey: try container.decode(String.self, forKey: .identityKey),
            titleDisplay: try container.decodeIfPresent(String.self, forKey: .titleDisplay),
            groupingKey: try container.decodeIfPresent(String.self, forKey: .groupingKey),
            retrievalUrls: try container.decodeIfPresent([String].self, forKey: .retrievalUrls) ?? [],
            alternatives: try container.decodeIfPresent([WebMediaDLFormatAlternative].self, forKey: .alternatives) ?? [],
            drmSignals: try container.decodeIfPresent([String].self, forKey: .drmSignals) ?? [],
            conflicts: try container.decodeIfPresent([String].self, forKey: .conflicts) ?? [],
            evidenceRefs: try container.decodeIfPresent([String].self, forKey: .evidenceRefs) ?? [],
            host: try container.decodeIfPresent(String.self, forKey: .host)
        )
    }

    private static func validate(identityKey: String, titleDisplay: String?) throws {
        if identityKey.lowercased().hasPrefix("title:") {
            throw WebMediaDLDomainError("A display title never becomes artifact identity.")
        }
        if let titleDisplay, identityKey == titleDisplay {
            throw WebMediaDLDomainError("A display title never becomes artifact identity.")
        }
    }
}

public struct WebMediaDLGraphEdge: Codable, Sendable {
    public var fromId: UUID
    public var toId: UUID
    public var relation: WebMediaDLGraphRelation

    enum CodingKeys: String, CodingKey {
        case fromId    = "from_id"
        case toId      = "to_id"
        case relation
    }
}

public struct WebMediaDLCandidateGraph: Codable, Sendable {
    public var graphId: UUID
    public var jobId: UUID
    public var nodes: [WebMediaDLMediaCandidate]
    public var edges: [WebMediaDLGraphEdge]
    public var conflicts: [String]

    enum CodingKeys: String, CodingKey {
        case graphId   = "graph_id"
        case jobId     = "job_id"
        case nodes
        case edges
        case conflicts
    }

    public init(
        graphId: UUID = UUID(),
        jobId: UUID,
        nodes: [WebMediaDLMediaCandidate] = [],
        edges: [WebMediaDLGraphEdge] = [],
        conflicts: [String] = []
    ) {
        self.graphId   = graphId
        self.jobId     = jobId
        self.nodes     = nodes
        self.edges     = edges
        self.conflicts = conflicts
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        graphId   = try container.decodeIfPresent(UUID.self, forKey: .graphId) ?? UUID()
        jobId     = try container.decode(UUID.self, forKey: .jobId)
        nodes     = try container.decodeIfPresent([WebMediaDLMediaCandidate].self, forKey: .nodes) ?? []
        edges     = try container.decodeIfPresent([WebMediaDLGraphEdge].self, forKey: .edges) ?? []
        conflicts = try container.decodeIfPresent([String].self, forKey: .conflicts) ?? []
    }
}

public struct WebMediaDLStreamInfo: Codable, Sendable {
    public var index: Int
    public var codec: String?
    public var mediaKind: WebMediaDLMediaKind
    public var width: Int?
    public var height: Int?
    public var sampleRate: Int?
    public var channels: Int?
    public var encrypted: Bool

    enum CodingKeys: String, CodingKey {
        case index
        case codec
        case mediaKind  = "media_kind"
        case width
        case height
        case sampleRate = "sample_rate"
        case channels
        case encrypted
    }

    public init(
        index: Int,
        codec: String? = nil,
        mediaKind: WebMediaDLMediaKind = .unknown,
        width: Int? = nil,
        height: Int? = nil,
        sampleRate: Int? = nil,
        channels: Int? = nil,
        encrypted: Bool = false
    ) {
        self.index      = index
        self.codec      = codec
        self.mediaKind  = mediaKind
        self.width      = width
        self.height     = height
        self.sampleRate = sampleRate
        self.channels   = channels
        self.encrypted  = encrypted
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        index      = try container.decode(Int.self, forKey: .index)
        codec      = try container.decodeIfPresent(String.self, forKey: .codec)
        mediaKind  = try container.decodeIfPresent(WebMediaDLMediaKind.self, forKey: .mediaKind) ?? .unknown
        width      = try container.decodeIfPresent(Int.self, forKey: .width)
        height     = try container.decodeIfPresent(Int.self, forKey: .height)
        sampleRate = try container.decodeIfPresent(Int.self, forKey: .sampleRate)
        channels   = try container.decodeIfPresent(Int.self, forKey: .channels)
        encrypted  = try container.decodeIfPresent(Bool.self, forKey: .encrypted) ?? false
    }
}

public struct WebMediaDLMediaProbe: Codable, Sendable {
    public var probeId: UUID
    public var candidateId: UUID
    public var durationMs: Int?
    public var streams: [WebMediaDLStreamInfo]
    public var container: String?
    public var formatNames: String?
    public var drmSignals: [String]

    enum CodingKeys: String, CodingKey {
        case probeId     = "probe_id"
        case candidateId = "candidate_id"
        case durationMs  = "duration_ms"
        case streams
        case container
        case formatNames = "format_names"
        case drmSignals  = "drm_signals"
    }

    public init(
        probeId: UUID = UUID(),
        candidateId: UUID,
        durationMs: Int? = nil,
        streams: [WebMediaDLStreamInfo] = [],
        container: String? = nil,
        formatNames: String? = nil,
        drmSignals: [String] = []
    ) {
        self.probeId     = probeId
        self.candidateId = candidateId
        self.durationMs  = durationMs
        self.streams     = streams
        self.container   = container
        self.formatNames = formatNames
        self.drmSignals  = drmSignals
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        probeId     = try container.decodeIfPresent(UUID.self, forKey: .probeId) ?? UUID()
        candidateId = try container.decode(UUID.self, forKey: .candidateId)
        durationMs  = try container.decodeIfPresent(Int.self, forKey: .durationMs)
        streams     = try container.decodeIfPresent([WebMediaDLStreamInfo].self, forKey: .streams) ?? []
        self.container = try container.decodeIfPresent(String.self, forKey: .container)
        formatNames = try container.decodeIfPresent(String.self, forKey: .formatNames)
        drmSignals  = try container.decodeIfPresent([String].self, forKey: .drmSignals) ?? []
    }
}

public struct WebMediaDLPipelineJob: Codable, Sendable {
    public var jobId: UUID
    public var source: WebMediaDLMediaSource
    public var state: WebMediaDLJobState
    public var policyProfileId: String
    public var workerId: String
    public var createdAt: String?
    public var updatedAt: String?
    public var intent: WebMediaDLExportIntent
    public var error: String?

    enum CodingKeys: String, CodingKey {
        case jobId           = "job_id"
        case source
        case state
        case policyProfileId = "policy_profile_id"
        case workerId        = "worker_id"
        case createdAt       = "created_at"
        case updatedAt       = "updated_at"
        case intent
        case error
    }

    public init(
        jobId: UUID = UUID(),
        source: WebMediaDLMediaSource,
        state: WebMediaDLJobState = .accepted,
        policyProfileId: String,
        workerId: String,
        createdAt: String? = nil,
        updatedAt: String? = nil,
        intent: WebMediaDLExportIntent = .stagingFallback,
        error: String? = nil
    ) {
        self.jobId           = jobId
        self.source          = source
        self.state           = state
        self.policyProfileId = policyProfileId
        self.workerId        = workerId
        self.createdAt       = createdAt
        self.updatedAt       = updatedAt
        self.intent          = intent
        self.error           = error
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        jobId           = try container.decodeIfPresent(UUID.self, forKey: .jobId) ?? UUID()
        source          = try container.decode(WebMediaDLMediaSource.self, forKey: .source)
        state           = try container.decodeIfPresent(WebMediaDLJobState.self, forKey: .state) ?? .accepted
        policyProfileId = try container.decode(String.self, forKey: .policyProfileId)
        workerId        = try container.decode(String.self, forKey: .workerId)
        createdAt       = try container.decodeIfPresent(String.self, forKey: .createdAt)
        updatedAt       = try container.decodeIfPresent(String.self, forKey: .updatedAt)
        intent          = try container.decodeIfPresent(WebMediaDLExportIntent.self, forKey: .intent)
            ?? .stagingFallback
        error           = try container.decodeIfPresent(String.self, forKey: .error)
    }
}

public struct WebMediaDLProviderManifest: Codable, Sendable {
    public var providerId: String
    public var displayName: String
    public var binaryName: String?
    public var capabilities: [String]
    public var allowedFlags: [String]
    public var installAutomatic: Bool
    public var license: String
    public var sourceUrl: String
    public var acceptsUserArgv: Bool
    public var notes: String?

    enum CodingKeys: String, CodingKey {
        case providerId        = "provider_id"
        case displayName       = "display_name"
        case binaryName        = "binary_name"
        case capabilities
        case allowedFlags      = "allowed_flags"
        case installAutomatic  = "install_automatic"
        case license
        case sourceUrl         = "source_url"
        case acceptsUserArgv   = "accepts_user_argv"
        case notes
    }

    public init(
        providerId: String,
        displayName: String,
        binaryName: String? = nil,
        capabilities: [String],
        allowedFlags: [String] = [],
        installAutomatic: Bool = false,
        license: String,
        sourceUrl: String,
        acceptsUserArgv: Bool = false,
        notes: String? = nil
    ) throws {
        if acceptsUserArgv {
            throw WebMediaDLDomainError("A provider never receives arbitrary user arguments.")
        }
        if installAutomatic {
            throw WebMediaDLDomainError("Providers are never installed automatically.")
        }
        self.providerId       = providerId
        self.displayName      = displayName
        self.binaryName       = binaryName
        self.capabilities     = capabilities
        self.allowedFlags     = allowedFlags
        self.installAutomatic = false
        self.license          = license
        self.sourceUrl        = sourceUrl
        self.acceptsUserArgv  = false
        self.notes            = notes
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        try self.init(
            providerId: try container.decode(String.self, forKey: .providerId),
            displayName: try container.decode(String.self, forKey: .displayName),
            binaryName: try container.decodeIfPresent(String.self, forKey: .binaryName),
            capabilities: try container.decode([String].self, forKey: .capabilities),
            allowedFlags: try container.decodeIfPresent([String].self, forKey: .allowedFlags) ?? [],
            installAutomatic: try container.decodeIfPresent(Bool.self, forKey: .installAutomatic) ?? false,
            license: try container.decode(String.self, forKey: .license),
            sourceUrl: try container.decode(String.self, forKey: .sourceUrl),
            acceptsUserArgv: try container.decodeIfPresent(Bool.self, forKey: .acceptsUserArgv) ?? false,
            notes: try container.decodeIfPresent(String.self, forKey: .notes)
        )
    }
}
