import Foundation
#if canImport(CryptoKit)
import CryptoKit
#endif

/// Worker response after a complete-client drop is staged on the Mac.
public struct WebMediaDLStagedUpload: Codable, Sendable, Equatable {
    public var path: String
    public var sha256: String
    public var bytes: Int

    public init(path: String, sha256: String, bytes: Int) {
        self.path   = path
        self.sha256 = sha256
        self.bytes  = bytes
    }
}

/// Paired-Mac heavy work. The Python worker stays loopback-only; complete
/// clients send jobs to a Mac relay URL saved during pairing, never to the
/// phone's own `127.0.0.1`.
public struct WebMediaDLPairedMacEndpoint: Sendable {
    public static let relayDefaultsKey = "webmedia-dl.mac-relay-url"

    public var relayURL: URL
    public var token: String
    public var pairingId: UUID
    public var sessionKey: String

    public init(relayURL: URL, token: String, pairingId: UUID, sessionKey: String) {
        self.relayURL = relayURL
        self.token = token
        self.pairingId = pairingId
        self.sessionKey = sessionKey
    }

    public static func advertisedRelay(
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) -> URL? {
        guard let raw = defaults.string(forKey: relayDefaultsKey)?.trimmingCharacters(
            in: .whitespacesAndNewlines
        ), !raw.isEmpty, let url = URL(string: raw) else {
            return nil
        }
        return isAllowedRelay(url) ? url : nil
    }

    public static func saveRelay(
        _ url: URL,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) -> Bool {
        guard isAllowedRelay(url) else { return false }
        defaults.set(url.absoluteString, forKey: relayDefaultsKey)
        return true
    }

    public static func isAllowedRelay(_ url: URL) -> Bool {
        guard let host = url.host?.lowercased(), !host.isEmpty else { return false }
        if host == "127.0.0.1" || host == "localhost" || host == "::1" || host == "[::1]" {
            return true
        }
        if host.hasSuffix(".local") { return true }
        let parts = host.split(separator: ".").compactMap { Int($0) }
        if parts.count == 4 {
            if parts[0] == 10 { return true }
            if parts[0] == 192 && parts[1] == 168 { return true }
            if parts[0] == 172 && (16 ... 31).contains(parts[1]) { return true }
        }
        return false
    }

    public static func load(
        pairingId: UUID?,
        sessionKey: String?,
        token: String = "",
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) -> WebMediaDLPairedMacEndpoint? {
        guard let pairingId,
              let session = sessionKey?.trimmingCharacters(in: .whitespacesAndNewlines),
              !session.isEmpty,
              let relay = advertisedRelay(defaults: defaults)
        else {
            return nil
        }
        return WebMediaDLPairedMacEndpoint(
            relayURL: relay,
            token: token,
            pairingId: pairingId,
            sessionKey: session
        )
    }

    public func submitRequest(
        locator: String,
        surface: WebMediaDLSurface,
        intakeKind: String? = nil,
        destinationKind: String? = nil,
        destinationPath: String? = nil,
        approvedRoots: [String] = [],
        bookmarkData: Data? = nil
    ) throws -> URLRequest {
        var request = URLRequest(url: relayURL.appendingPathComponent("v1/jobs"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.setValue(pairingId.uuidString, forHTTPHeaderField: "X-WebMedia-Pairing")
        request.setValue(sessionKey, forHTTPHeaderField: "X-WebMedia-Session")
        var body: [String: Any] = [
            "locator": locator,
            "surface": surface.rawValue,
            "local_user_confirmed": true,
            "wait": false,
            "pairing_id": pairingId.uuidString,
            "session_key": sessionKey,
        ]
        if let intakeKind {
            body["intake_kind"] = intakeKind
        }
        let destination = surface.macJobDestination(
            kind: destinationKind,
            path: destinationPath,
            approvedRoots: approvedRoots,
            bookmarkData: bookmarkData
        )
        if let destinationKind = destination.kind, !destinationKind.isEmpty {
            var intent: [String: Any] = ["destination_kind": destinationKind]
            if let destinationPath = destination.path {
                intent["destination_path"] = destinationPath
            }
            if !destination.roots.isEmpty {
                intent["approved_roots"] = destination.roots
            }
            if destinationKind == "files_app", let destinationPath = destination.path {
                intent["security_scoped_path"] = destinationPath
            }
            if let bookmarkData = destination.bookmark {
                intent["security_scoped_bookmark"] = bookmarkData.base64EncodedString()
            }
            body["intent"] = intent
        }
        request.httpBody = try WebMediaDLLoopbackClient.jsonBody(body)
        return request
    }

    public func historyRequest() -> URLRequest {
        authorized(relayURL.appendingPathComponent("v1/jobs"))
    }

    public func jobDetailRequest(jobId: UUID) -> URLRequest {
        authorized(
            relayURL
                .appendingPathComponent("v1/jobs")
                .appendingPathComponent(jobId.uuidString)
        )
    }

    public func artifactContentRequest(artifactId: String) -> URLRequest {
        authorized(
            relayURL
                .appendingPathComponent("v1/artifacts")
                .appendingPathComponent(artifactId)
                .appendingPathComponent("content")
        )
    }

    public func pauseQueueRequest() -> URLRequest {
        authorized(relayURL.appendingPathComponent("v1/queue/pause"), method: "POST")
    }

    public func resumeQueueRequest() -> URLRequest {
        authorized(relayURL.appendingPathComponent("v1/queue/resume"), method: "POST")
    }

    public func queueStatusRequest() -> URLRequest {
        authorized(relayURL.appendingPathComponent("v1/queue"))
    }

    public func cancelRequest(jobId: UUID) -> URLRequest {
        authorized(
            relayURL
                .appendingPathComponent("v1/jobs")
                .appendingPathComponent(jobId.uuidString)
                .appendingPathComponent("cancel"),
            method: "POST"
        )
    }

    public func pauseJobRequest(jobId: UUID) -> URLRequest {
        authorized(
            relayURL
                .appendingPathComponent("v1/jobs")
                .appendingPathComponent(jobId.uuidString)
                .appendingPathComponent("pause"),
            method: "POST"
        )
    }

    public func resumeJobRequest(jobId: UUID) -> URLRequest {
        authorized(
            relayURL
                .appendingPathComponent("v1/jobs")
                .appendingPathComponent(jobId.uuidString)
                .appendingPathComponent("resume"),
            method: "POST"
        )
    }

    public func historyEntries() async throws -> [WebMediaDLHistoryEntry] {
        let (data, response) = try await URLSession.shared.data(for: historyRequest())
        return try WebMediaDLLoopbackClient.requireHistoryEntries(
            status: (response as? HTTPURLResponse)?.statusCode ?? 0,
            body: data
        )
    }

    public func pauseQueue() async throws -> String { try await send(pauseQueueRequest()) }
    public func resumeQueue() async throws -> String { try await send(resumeQueueRequest()) }
    public func queueStatus() async throws -> String { try await send(queueStatusRequest()) }
    public func cancel(jobId: UUID) async throws -> String { try await send(cancelRequest(jobId: jobId)) }
    public func pauseJob(jobId: UUID) async throws -> String { try await send(pauseJobRequest(jobId: jobId)) }
    public func resumeJob(jobId: UUID) async throws -> String { try await send(resumeJobRequest(jobId: jobId)) }

    public func companionRequest(_ message: WebMediaDLCompanionMessage) throws -> URLRequest {
        var request = authorized(relayURL.appendingPathComponent("v1/companion"), method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var body: [String: Any] = [
            "kind": message.kind.rawValue,
            "nativeCommand": NSNull(),
            "subprocessWorker": false,
            "surface": message.surface.rawValue,
        ]
        if let locator = message.locator {
            body["locator"] = locator
        }
        if let jobId = message.jobId.flatMap(UUID.init(uuidString:)) {
            body["job_id"] = jobId.uuidString
        }
        request.httpBody = try WebMediaDLLoopbackClient.jsonBody(body)
        return request
    }

    public func companion(_ message: WebMediaDLCompanionMessage) async throws -> String {
        try await send(companionRequest(message))
    }

    public func stageRequest(digest: String, filename: String, size: Int) -> URLRequest {
        var request = authorized(relayURL.appendingPathComponent("v1/staging"), method: "POST")
        request.setValue("application/octet-stream", forHTTPHeaderField: "Content-Type")
        request.setValue(digest, forHTTPHeaderField: "X-WebMedia-Digest")
        request.setValue(filename, forHTTPHeaderField: "X-WebMedia-Filename")
        request.setValue(String(size), forHTTPHeaderField: "Content-Length")
        return request
    }

    public func stage(fileURL: URL) async throws -> WebMediaDLStagedUpload {
        let data = try Data(contentsOf: fileURL)
        let digest = Self.sha256Hex(data)
        var request = stageRequest(digest: digest, filename: fileURL.lastPathComponent, size: data.count)
        request.httpBody = data
        let (body, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        guard (200 ..< 300).contains(status) else {
            let detail = String(data: body, encoding: .utf8) ?? "staging failed"
            throw WebMediaDLHttpDirect.TransferError.writeFailed(detail)
        }
        let payload = try JSONDecoder().decode(WebMediaDLStagedUpload.self, from: body)
        if payload.sha256 != digest {
            throw WebMediaDLHttpDirect.TransferError.writeFailed(
                "Staging upload digest does not match the declared sha256."
            )
        }
        return payload
    }

    public func pullToFiles(
        jobId: UUID,
        bookmark: WebMediaDLSecurityScopedBookmark
    ) async throws -> [String] {
        let (detailData, detailResponse) = try await URLSession.shared.data(
            for: jobDetailRequest(jobId: jobId)
        )
        let detailStatus = (detailResponse as? HTTPURLResponse)?.statusCode ?? 0
        guard (200 ..< 300).contains(detailStatus) else {
            throw WebMediaDLHttpDirect.TransferError.writeFailed("Job detail HTTP \(detailStatus)")
        }
        guard let detail = try JSONSerialization.jsonObject(with: detailData) as? [String: Any] else {
            throw WebMediaDLHttpDirect.TransferError.writeFailed("Job detail is not JSON.")
        }
        let artifactIds = (detail["artifact_ids"] as? [String]) ?? []
        if artifactIds.isEmpty {
            throw WebMediaDLHttpDirect.TransferError.writeFailed(
                "Job has no published artifacts yet."
            )
        }
        var written: [String] = []
        for artifactId in artifactIds {
            let (bytes, response) = try await URLSession.shared.data(
                for: artifactContentRequest(artifactId: artifactId)
            )
            let status = (response as? HTTPURLResponse)?.statusCode ?? 0
            guard (200 ..< 300).contains(status) else {
                throw WebMediaDLHttpDirect.TransferError.writeFailed(
                    "Artifact download HTTP \(status)"
                )
            }
            let hex = Self.sha256Hex(bytes)
            let declared = (response as? HTTPURLResponse)?
                .value(forHTTPHeaderField: "X-WebMedia-Digest") ?? ""
            let normalized = declared.hasPrefix("sha256:")
                ? String(declared.dropFirst(7))
                : declared
            if !normalized.isEmpty, normalized != hex {
                throw WebMediaDLHttpDirect.TransferError.writeFailed(
                    "Artifact digest does not match the declared sha256."
                )
            }
            let filename = artifactId.replacingOccurrences(of: ":", with: "-") + ".bin"
            written.append(
                try WebMediaDLHttpDirect.write(
                    data: bytes,
                    filename: filename,
                    bookmark: bookmark
                )
            )
        }
        return written
    }

    public static func sha256Hex(_ data: Data) -> String {
        #if canImport(CryptoKit)
        SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined()
        #else
        ""
        #endif
    }

    private func authorized(_ url: URL, method: String = "GET") -> URLRequest {
        var request = URLRequest(url: url)
        request.httpMethod = method
        if !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.setValue(pairingId.uuidString, forHTTPHeaderField: "X-WebMedia-Pairing")
        request.setValue(sessionKey, forHTTPHeaderField: "X-WebMedia-Session")
        return request
    }

    public func submit(
        locator: String,
        surface: WebMediaDLSurface,
        intakeKind: String? = nil,
        destinationKind: String? = nil,
        destinationPath: String? = nil,
        approvedRoots: [String] = [],
        bookmarkData: Data? = nil
    ) async throws -> String {
        try await send(
            submitRequest(
                locator: locator,
                surface: surface,
                intakeKind: intakeKind,
                destinationKind: destinationKind,
                destinationPath: destinationPath,
                approvedRoots: approvedRoots,
                bookmarkData: bookmarkData
            )
        )
    }

    public func send(_ request: URLRequest) async throws -> String {
        try WebMediaDLLoopbackClient.requireJSONBody(request)
        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        return try WebMediaDLLoopbackClient.requireHTTPSuccess(status: status, body: data)
    }

    public static func startPairing(
        clientProfileId: String = "personal-restricted",
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) async throws -> WebMediaDLPairingChallenge {
        guard let relay = advertisedRelay(defaults: defaults) else {
            throw WebMediaDLHttpDirect.TransferError.pairingRequired
        }
        var request = URLRequest(url: relay.appendingPathComponent("v1/pair"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try WebMediaDLLoopbackClient.jsonBody(
            ["client_profile_id": clientProfileId]
        )
        let (data, response) = try await URLSession.shared.data(for: request)
        _ = try WebMediaDLLoopbackClient.requireHTTPSuccess(
            status: (response as? HTTPURLResponse)?.statusCode ?? 0,
            body: data
        )
        return try JSONDecoder().decode(WebMediaDLPairingChallenge.self, from: data)
    }
}

/// Mac-side rewrite: LAN/companion requests become loopback worker requests.
public enum WebMediaDLMacWorkerRelay {
    public static func forwardToLoopback(
        _ incoming: URLRequest,
        worker: URL = WebMediaDLLoopbackClient.defaultBaseURL,
        loopbackToken: String = ""
    ) throws -> URLRequest {
        let workerClient = WebMediaDLLoopbackClient(baseURL: worker)
        guard workerClient.isLoopback else {
            throw WebMediaDLMacWorkerRelayError.notLoopbackWorker
        }
        guard let incomingURL = incoming.url,
              var components = URLComponents(url: incomingURL, resolvingAgainstBaseURL: false)
        else {
            throw WebMediaDLMacWorkerRelayError.missingURL
        }
        if let body = incoming.httpBody, !body.isEmpty {
            let contentType = incoming.value(forHTTPHeaderField: "Content-Type") ?? ""
            let parsed = try? JSONSerialization.jsonObject(with: body)
            if parsed == nil {
                if contentType.contains("application/json")
                    || body.first == UInt8(ascii: "{")
                    || body.first == UInt8(ascii: "[")
                {
                    throw WebMediaDLMacWorkerRelayError.invalidJSON
                }
            } else {
                guard let json = parsed as? [String: Any] else {
                    throw WebMediaDLMacWorkerRelayError.invalidJSON
                }
                if let native = json["nativeCommand"] as? String, !native.isEmpty {
                    throw WebMediaDLMacWorkerRelayError.nativeCommand
                }
                if json["subprocessWorker"] as? Bool == true {
                    throw WebMediaDLMacWorkerRelayError.nativeCommand
                }
            }
        }
        components.scheme = worker.scheme
        components.host   = worker.host
        components.port   = worker.port
        var forwarded = incoming
        forwarded.url = components.url
        forwarded.setValue(nil, forHTTPHeaderField: "Authorization")
        forwarded.setValue(nil, forHTTPHeaderField: "X-WebMedia-Token")
        let path = forwarded.url?.path ?? ""
        if path == "/v1/pair/confirm" || path.hasPrefix("/v1/pair/confirm/") {
            throw WebMediaDLMacWorkerRelayError.macOnlyEndpoint
        }
        let pairing = forwarded.value(forHTTPHeaderField: "X-WebMedia-Pairing") ?? ""
        let session = forwarded.value(forHTTPHeaderField: "X-WebMedia-Session") ?? ""
        if (path == "/v1/companion" || path.hasPrefix("/v1/companion/")),
           !pairing.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
           !session.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
           !loopbackToken.isEmpty
        {
            forwarded.setValue("Bearer \(loopbackToken)", forHTTPHeaderField: "Authorization")
        }
        return forwarded
    }
}

public enum WebMediaDLMacWorkerRelayError: Error, Equatable {
    case notLoopbackWorker
    case missingURL
    case nativeCommand
    case invalidJSON
    case macOnlyEndpoint
}

/// Complete-client helper: fail closed without a saved Mac relay and pairing.
public enum WebMediaDLPairedMacSubmit {
    public static func submit(
        locator: String,
        surface: WebMediaDLSurface,
        credentials: WebMediaDLLoopbackClient = WebMediaDLWorkerCredentials.loadClient(),
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        intakeKind: String? = nil,
        destinationKind: String? = nil,
        destinationPath: String? = nil,
        approvedRoots: [String] = [],
        bookmarkData: Data? = nil,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) async throws -> String {
        return try await loadEndpoint(
            credentials: credentials,
            pairingId: pairingId,
            sessionKey: sessionKey,
            defaults: defaults
        ).submit(
            locator: locator,
            surface: surface,
            intakeKind: intakeKind,
            destinationKind: destinationKind,
            destinationPath: destinationPath,
            approvedRoots: approvedRoots,
            bookmarkData: bookmarkData
        )
    }

    public static func submitDrop(
        localPath: String,
        surface: WebMediaDLSurface,
        credentials: WebMediaDLLoopbackClient = WebMediaDLWorkerCredentials.loadClient(),
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) async throws -> String {
        let endpoint = try loadEndpoint(
            credentials: credentials,
            pairingId: pairingId,
            sessionKey: sessionKey,
            defaults: defaults
        )
        let url = URL(fileURLWithPath: localPath)
        guard FileManager.default.isReadableFile(atPath: url.path) else {
            throw WebMediaDLHttpDirect.TransferError.writeFailed(
                "File intake requires an existing file."
            )
        }
        let staged = try await endpoint.stage(fileURL: url)
        return try await endpoint.submit(
            locator: staged.path,
            surface: surface,
            intakeKind: "drop",
            destinationKind: "staging_only"
        )
    }

    public static func pullToFiles(
        jobId: UUID,
        bookmark: WebMediaDLSecurityScopedBookmark,
        credentials: WebMediaDLLoopbackClient = WebMediaDLWorkerCredentials.loadClient(),
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) async throws -> [String] {
        try await loadEndpoint(
            credentials: credentials,
            pairingId: pairingId,
            sessionKey: sessionKey,
            defaults: defaults
        ).pullToFiles(jobId: jobId, bookmark: bookmark)
    }

    public static func history(
        credentials: WebMediaDLLoopbackClient = WebMediaDLWorkerCredentials.loadClient(),
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) async throws -> [WebMediaDLHistoryEntry] {
        try await loadEndpoint(
            credentials: credentials,
            pairingId: pairingId,
            sessionKey: sessionKey,
            defaults: defaults
        ).historyEntries()
    }

    public static func pauseQueue(
        credentials: WebMediaDLLoopbackClient = WebMediaDLWorkerCredentials.loadClient(),
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) async throws -> String {
        try await loadEndpoint(
            credentials: credentials,
            pairingId: pairingId,
            sessionKey: sessionKey,
            defaults: defaults
        ).pauseQueue()
    }

    public static func resumeQueue(
        credentials: WebMediaDLLoopbackClient = WebMediaDLWorkerCredentials.loadClient(),
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) async throws -> String {
        try await loadEndpoint(
            credentials: credentials,
            pairingId: pairingId,
            sessionKey: sessionKey,
            defaults: defaults
        ).resumeQueue()
    }

    public static func queueStatus(
        credentials: WebMediaDLLoopbackClient = WebMediaDLWorkerCredentials.loadClient(),
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) async throws -> String {
        try await loadEndpoint(
            credentials: credentials,
            pairingId: pairingId,
            sessionKey: sessionKey,
            defaults: defaults
        ).queueStatus()
    }

    public static func cancel(
        jobId: UUID,
        credentials: WebMediaDLLoopbackClient = WebMediaDLWorkerCredentials.loadClient(),
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) async throws -> String {
        try await loadEndpoint(
            credentials: credentials,
            pairingId: pairingId,
            sessionKey: sessionKey,
            defaults: defaults
        ).cancel(jobId: jobId)
    }

    public static func pauseJob(
        jobId: UUID,
        credentials: WebMediaDLLoopbackClient = WebMediaDLWorkerCredentials.loadClient(),
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) async throws -> String {
        try await loadEndpoint(
            credentials: credentials,
            pairingId: pairingId,
            sessionKey: sessionKey,
            defaults: defaults
        ).pauseJob(jobId: jobId)
    }

    public static func resumeJob(
        jobId: UUID,
        credentials: WebMediaDLLoopbackClient = WebMediaDLWorkerCredentials.loadClient(),
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) async throws -> String {
        try await loadEndpoint(
            credentials: credentials,
            pairingId: pairingId,
            sessionKey: sessionKey,
            defaults: defaults
        ).resumeJob(jobId: jobId)
    }

    public static func companion(
        _ message: WebMediaDLCompanionMessage,
        credentials: WebMediaDLLoopbackClient = WebMediaDLWorkerCredentials.loadClient(),
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) async throws -> String {
        try WebMediaDLCompanionMessage.validate(message)
        return try await loadEndpoint(
            credentials: credentials,
            pairingId: pairingId,
            sessionKey: sessionKey,
            defaults: defaults
        ).companion(message)
    }

    public static func loadEndpoint(
        credentials: WebMediaDLLoopbackClient = WebMediaDLWorkerCredentials.loadClient(),
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) throws -> WebMediaDLPairedMacEndpoint {
        guard let endpoint = WebMediaDLPairedMacEndpoint.load(
            pairingId: pairingId ?? credentials.pairingId,
            sessionKey: sessionKey ?? credentials.sessionKey,
            token: "",
            defaults: defaults
        ) else {
            throw WebMediaDLHttpDirect.TransferError.pairingRequired
        }
        return endpoint
    }
}

/// Complete-client Siri/Shortcuts controls hop onto the saved Mac relay.
public enum WebMediaDLCompleteClientControl {
    public enum Kind: String, Sendable, Equatable {
        case pauseQueue
        case resumeQueue
        case history
        case queueStatus
        case cancel
        case pauseJob
        case resumeJob
    }

    public typealias Send = @Sendable (Kind, UUID?) async throws -> String

    public static func kind(from raw: String) throws -> Kind {
        guard let parsed = Kind(rawValue: raw) else {
            throw WebMediaDLDomainError("unknown complete-client control")
        }
        return parsed
    }

    public static func resolvedJobId(_ kind: Kind, jobId: String?) throws -> UUID? {
        switch kind {
        case .cancel, .pauseJob, .resumeJob:
            return try WebMediaDLCompanionJobControl.requireJobId(jobId ?? "")
        case .pauseQueue, .resumeQueue, .history, .queueStatus:
            return nil
        }
    }

    public static func perform(
        _ kind: Kind,
        jobId: String? = nil,
        send: Send
    ) async throws -> String {
        let resolved = try resolvedJobId(kind, jobId: jobId)
        return try await send(kind, resolved)
    }

    public static func perform(
        _ raw: String,
        jobId: String? = nil,
        send: Send
    ) async throws -> String {
        try await perform(try kind(from: raw), jobId: jobId, send: send)
    }

    public static func perform(
        _ kind: Kind,
        jobId: String? = nil,
        credentials: WebMediaDLLoopbackClient = WebMediaDLWorkerCredentials.loadClient(),
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) async throws -> String {
        let resolved = try resolvedJobId(kind, jobId: jobId)
        switch kind {
        case .pauseQueue:
            return try await WebMediaDLPairedMacSubmit.pauseQueue(
                credentials: credentials,
                pairingId: pairingId,
                sessionKey: sessionKey,
                defaults: defaults
            )
        case .resumeQueue:
            return try await WebMediaDLPairedMacSubmit.resumeQueue(
                credentials: credentials,
                pairingId: pairingId,
                sessionKey: sessionKey,
                defaults: defaults
            )
        case .history:
            _ = try await WebMediaDLPairedMacSubmit.history(
                credentials: credentials,
                pairingId: pairingId,
                sessionKey: sessionKey,
                defaults: defaults
            )
            return "ok"
        case .queueStatus:
            return try await WebMediaDLPairedMacSubmit.queueStatus(
                credentials: credentials,
                pairingId: pairingId,
                sessionKey: sessionKey,
                defaults: defaults
            )
        case .cancel:
            guard let resolved else {
                throw WebMediaDLCompanionError.jobIdRequired
            }
            return try await WebMediaDLPairedMacSubmit.cancel(
                jobId: resolved,
                credentials: credentials,
                pairingId: pairingId,
                sessionKey: sessionKey,
                defaults: defaults
            )
        case .pauseJob:
            guard let resolved else {
                throw WebMediaDLCompanionError.jobIdRequired
            }
            return try await WebMediaDLPairedMacSubmit.pauseJob(
                jobId: resolved,
                credentials: credentials,
                pairingId: pairingId,
                sessionKey: sessionKey,
                defaults: defaults
            )
        case .resumeJob:
            guard let resolved else {
                throw WebMediaDLCompanionError.jobIdRequired
            }
            return try await WebMediaDLPairedMacSubmit.resumeJob(
                jobId: resolved,
                credentials: credentials,
                pairingId: pairingId,
                sessionKey: sessionKey,
                defaults: defaults
            )
        }
    }

    public static func perform(
        _ raw: String,
        jobId: String? = nil,
        credentials: WebMediaDLLoopbackClient = WebMediaDLWorkerCredentials.loadClient(),
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()
    ) async throws -> String {
        try await perform(
            try kind(from: raw),
            jobId: jobId,
            credentials: credentials,
            pairingId: pairingId,
            sessionKey: sessionKey,
            defaults: defaults
        )
    }
}
