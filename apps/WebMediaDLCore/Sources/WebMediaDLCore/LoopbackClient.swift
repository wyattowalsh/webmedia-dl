import CryptoKit
import Foundation

public struct WebMediaDLLoopbackClient: Sendable {
    public static let defaultBaseURL = URL(string: "http://127.0.0.1:8765")!

    public var baseURL: URL
    public var token: String
    public var pairingId: UUID?
    public var sessionKey: String?

    public init(
        baseURL: URL = WebMediaDLLoopbackClient.defaultBaseURL,
        token: String = "",
        pairingId: UUID? = nil,
        sessionKey: String? = nil
    ) {
        self.baseURL = baseURL
        self.token = token
        self.pairingId = pairingId
        self.sessionKey = sessionKey
    }

    public var isLoopback: Bool {
        let host = baseURL.host ?? ""
        return host == "127.0.0.1" || host == "localhost" || host == "::1"
    }

    public typealias HealthFetch = @Sendable (URLRequest) async throws -> (Int, Data)

    public func healthRequest() -> URLRequest {
        precondition(isLoopback, "Clients may only talk to the loopback worker.")
        var request = URLRequest(url: baseURL.appendingPathComponent("health"))
        request.httpMethod = "GET"
        return request
    }

    public func requireHealthyWorker(fetch: HealthFetch? = nil) async throws {
        let request = healthRequest()
        let status: Int
        let data: Data
        if let fetch {
            (status, data) = try await fetch(request)
        } else {
            let (body, response) = try await URLSession.shared.data(for: request)
            status = (response as? HTTPURLResponse)?.statusCode ?? 0
            data   = body
        }
        guard status == 200 else {
            throw WebMediaDLDomainError("loopback worker health returned HTTP \(status)")
        }
        let object = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        guard (object?["status"] as? String) == "ok" else {
            throw WebMediaDLDomainError("loopback worker health is not ok")
        }
    }

    private func authorized(_ url: URL, method: String = "GET") -> URLRequest {
        precondition(isLoopback, "Clients may only talk to the loopback worker.")
        var request = URLRequest(url: url)
        request.httpMethod = method
        if !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        if let pairingId {
            request.setValue(pairingId.uuidString, forHTTPHeaderField: "X-WebMedia-Pairing")
        }
        if let sessionKey, !sessionKey.isEmpty {
            request.setValue(sessionKey, forHTTPHeaderField: "X-WebMedia-Session")
        }
        return request
    }

    public func submitRequest(
        locator: String,
        surface: WebMediaDLSurface,
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        evidence: [[String: String]] = [],
        wait: Bool = false,
        intakeKind: String? = nil,
        destinationKind: String? = nil,
        destinationPath: String? = nil,
        approvedRoots: [String] = [],
        bookmarkData: Data? = nil
    ) -> URLRequest {
        var request = authorized(baseURL.appendingPathComponent("v1/jobs"), method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var body: [String: Any] = [
            "locator": locator,
            "surface": surface.rawValue,
            "local_user_confirmed": true,
            "evidence": evidence,
            "wait": wait,
        ]
        if let pairingId {
            body["pairing_id"] = pairingId.uuidString
        }
        if let sessionKey {
            body["session_key"] = sessionKey
        }
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
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        return request
    }

    public func historyRequest() -> URLRequest {
        authorized(baseURL.appendingPathComponent("v1/jobs"))
    }

    public func cancelRequest(jobId: UUID) -> URLRequest {
        let url = baseURL
            .appendingPathComponent("v1/jobs")
            .appendingPathComponent(jobId.uuidString)
            .appendingPathComponent("cancel")
        return authorized(url, method: "POST")
    }

    public func pauseQueueRequest() -> URLRequest {
        authorized(baseURL.appendingPathComponent("v1/queue/pause"), method: "POST")
    }

    public func resumeQueueRequest() -> URLRequest {
        authorized(baseURL.appendingPathComponent("v1/queue/resume"), method: "POST")
    }

    public func queueStatusRequest() -> URLRequest {
        authorized(baseURL.appendingPathComponent("v1/queue"))
    }

    public func pauseJobRequest(jobId: UUID) -> URLRequest {
        let url = baseURL
            .appendingPathComponent("v1/jobs")
            .appendingPathComponent(jobId.uuidString)
            .appendingPathComponent("pause")
        return authorized(url, method: "POST")
    }

    public func pairRequest(clientProfileId: String = "personal-restricted") -> URLRequest {
        // Fresh clients bootstrap pairing without a worker token. Confirm stays Mac-owned.
        var request = authorized(baseURL.appendingPathComponent("v1/pair"), method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: ["client_profile_id": clientProfileId]
        )
        return request
    }

    public func pairConfirmRequest(pairingId: UUID) -> URLRequest {
        var request = authorized(baseURL.appendingPathComponent("v1/pair/confirm"), method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: ["pairing_id": pairingId.uuidString]
        )
        return request
    }

    public func artifactsRequest() -> URLRequest {
        authorized(baseURL.appendingPathComponent("v1/artifacts"))
    }

    public func jobDetailRequest(jobId: UUID) -> URLRequest {
        authorized(
            baseURL
                .appendingPathComponent("v1/jobs")
                .appendingPathComponent(jobId.uuidString)
        )
    }

    public func artifactContentRequest(artifactId: String) -> URLRequest {
        authorized(
            baseURL
                .appendingPathComponent("v1/artifacts")
                .appendingPathComponent(artifactId)
                .appendingPathComponent("content")
        )
    }

    public func resumeJobRequest(jobId: UUID) -> URLRequest {
        let url = baseURL
            .appendingPathComponent("v1/jobs")
            .appendingPathComponent(jobId.uuidString)
            .appendingPathComponent("resume")
        return authorized(url, method: "POST")
    }

    public func companionRequest(
        kind: String,
        locator: String? = nil,
        jobId: UUID? = nil,
        surface: WebMediaDLSurface = .watchos
    ) -> URLRequest {
        var request = authorized(baseURL.appendingPathComponent("v1/companion"), method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var body: [String: Any] = [
            "kind": kind,
            "nativeCommand": NSNull(),
            "subprocessWorker": false,
            "surface": surface.rawValue,
        ]
        if let locator {
            body["locator"] = locator
        }
        if let jobId {
            body["job_id"] = jobId.uuidString
        }
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        return request
    }

    public func envelopeWrapRequest(
        pairingId: UUID,
        sessionKey: String,
        payload: [String: Any]
    ) -> URLRequest {
        var request = authorized(baseURL.appendingPathComponent("v1/pair/envelope"), method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: [
                "pairing_id": pairingId.uuidString,
                "session_key": sessionKey,
                "payload": payload,
            ]
        )
        return request
    }

    public func sealedCompanionRequest(
        pairingId: UUID,
        sessionKey: String,
        nonce: String,
        ciphertext: String,
        mac: String
    ) -> URLRequest {
        var request = authorized(baseURL.appendingPathComponent("v1/companion"), method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = [
            "pairing_id": pairingId.uuidString,
            "session_key": sessionKey,
            "nonce": nonce,
            "ciphertext": ciphertext,
            "mac": mac,
            "nativeCommand": NSNull(),
            "subprocessWorker": false,
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        return request
    }

    public static func requireHTTPSuccess(status: Int, body: Data) throws -> String {
        let text = String(data: body, encoding: .utf8) ?? ""
        let summary = "HTTP \(status) \(text)"
        guard (200 ..< 300).contains(status) else {
            throw WebMediaDLDomainError(summary)
        }
        return summary
    }

    public static func requireHistoryEntries(status: Int, body: Data) throws -> [WebMediaDLHistoryEntry] {
        _ = try requireHTTPSuccess(status: status, body: body)
        do {
            return try WebMediaDLHistoryEntry.decodeCompanionHistory(from: body)
        } catch {
            throw WebMediaDLDomainError("history JSON is not a job list")
        }
    }

    public static func displayedResponse(_ work: @Sendable () async throws -> String) async -> String {
        do {
            return try await work()
        } catch {
            return error.localizedDescription
        }
    }

    public func send(_ request: URLRequest) async throws -> String {
        let (data, response) = try await URLSession.shared.data(for: request)
        let status = (response as? HTTPURLResponse)?.statusCode ?? 0
        return try Self.requireHTTPSuccess(status: status, body: data)
    }

    public func submit(
        locator: String,
        surface: WebMediaDLSurface,
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
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
                pairingId: pairingId ?? self.pairingId,
                sessionKey: sessionKey ?? self.sessionKey,
                intakeKind: intakeKind,
                destinationKind: destinationKind,
                destinationPath: destinationPath,
                approvedRoots: approvedRoots,
                bookmarkData: bookmarkData
            )
        )
    }

    public func history() async throws -> String {
        try await send(historyRequest())
    }

    public func historyEntries() async throws -> [WebMediaDLHistoryEntry] {
        let (data, response) = try await URLSession.shared.data(for: historyRequest())
        return try Self.requireHistoryEntries(
            status: (response as? HTTPURLResponse)?.statusCode ?? 0,
            body: data
        )
    }

    public func historySummary() async throws -> String {
        let entries = try await historyEntries()
        if entries.isEmpty {
            return "No jobs yet."
        }
        return entries.map { "\($0.jobId.uuidString.prefix(8)) \($0.state)" }.joined(separator: "\n")
    }

    public func pauseQueue() async throws -> String {
        try await send(pauseQueueRequest())
    }

    public func resumeQueue() async throws -> String {
        try await send(resumeQueueRequest())
    }

    public func queueStatus() async throws -> String {
        try await send(queueStatusRequest())
    }

    public func startPairing(clientProfileId: String = "personal-restricted") async throws -> WebMediaDLPairingChallenge {
        // Loopback pairing start does not require a stored worker token.
        let (data, response) = try await URLSession.shared.data(for: pairRequest(clientProfileId: clientProfileId))
        _ = try Self.requireHTTPSuccess(
            status: (response as? HTTPURLResponse)?.statusCode ?? 0,
            body: data
        )
        return try JSONDecoder().decode(WebMediaDLPairingChallenge.self, from: data)
    }

    public func confirmPairing(_ pairingId: UUID) async throws -> String {
        try await send(pairConfirmRequest(pairingId: pairingId))
    }

    public func forwardCompanion(
        kind: String,
        locator: String? = nil,
        jobId: UUID? = nil,
        surface: WebMediaDLSurface = .watchos
    ) async throws -> String {
        try await send(companionRequest(kind: kind, locator: locator, jobId: jobId, surface: surface))
    }

    public func artifacts() async throws -> String {
        try await send(artifactsRequest())
    }

    public func cancel(jobId: UUID) async throws -> String {
        try await send(cancelRequest(jobId: jobId))
    }

    public func pauseJob(jobId: UUID) async throws -> String {
        try await send(pauseJobRequest(jobId: jobId))
    }

    public func resumeJob(jobId: UUID) async throws -> String {
        try await send(resumeJobRequest(jobId: jobId))
    }

    public func provenance(artifactId: String) async throws -> String {
        let encoded = artifactId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? artifactId
        let url = baseURL
            .appendingPathComponent("v1/artifacts")
            .appendingPathComponent(encoded)
            .appendingPathComponent("provenance")
        return try await send(authorized(url))
    }

    public static func derivedSessionKey(nonce: String, confirmation: String = "mac-confirm") -> String {
        let digest = SHA256.hash(data: Data("\(nonce):\(confirmation)".utf8))
        return digest.map { String(format: "%02x", $0) }.joined()
    }

    public static func jsonObject(from response: String) -> [String: Any]? {
        guard let start = response.firstIndex(of: "{") else { return nil }
        let json = String(response[start...])
        guard let data = json.data(using: .utf8) else { return nil }
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }

    public static func sessionKey(from response: String) -> String? {
        guard let root = jsonObject(from: response),
              let key = root["session_key"] as? String
        else {
            return nil
        }
        let trimmed = key.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }

    public static func jobId(from response: String) -> UUID? {
        guard let root = jsonObject(from: response) else { return nil }
        if let job = root["job"] as? [String: Any], let value = job["job_id"] as? String {
            return UUID(uuidString: value)
        }
        if let value = root["job_id"] as? String {
            return UUID(uuidString: value)
        }
        return nil
    }
}

/// App Group / UserDefaults-backed worker token and pairing. Intents and share
/// extensions must not construct a bare unauthenticated client.
public enum WebMediaDLWorkerCredentials {
    public static let tokenDefaultsKey = "webmedia-dl.worker-token"
    public static let pairingDefaultsKey = "webmedia-dl.pairing-id"
    public static let sessionDefaultsKey = "webmedia-dl.session-key"

    public static let appGroupIdentifier = "group.local.webmedia-dl"
    public static let bookmarkDefaultsKey = "webmedia-dl.files-bookmark"

    public static func defaults() -> UserDefaults {
        UserDefaults(suiteName: appGroupIdentifier) ?? .standard
    }

    public static func loadClient(defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()) -> WebMediaDLLoopbackClient {
        WebMediaDLLoopbackClient(
            token: defaults.string(forKey: tokenDefaultsKey) ?? "",
            pairingId: defaults.string(forKey: pairingDefaultsKey).flatMap(UUID.init(uuidString:)),
            sessionKey: defaults.string(forKey: sessionDefaultsKey)
        )
    }

    public static func loadBookmark(defaults: UserDefaults = WebMediaDLWorkerCredentials.defaults()) -> Data? {
        defaults.data(forKey: bookmarkDefaultsKey)
    }
}

/// Photos / Files / Share destinations require an explicit user-approved root.
public struct WebMediaDLDestinationPolicy: Sendable {
    public var approvedRoots: [String]

    public init(approvedRoots: [String] = []) {
        self.approvedRoots = approvedRoots
    }

    public func allows(_ path: String) -> Bool {
        approvedRoots.contains { root in
            let trimmed = root.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty { return false }
            if !trimmed.hasPrefix("/") { return false }
            let normalizedRoot = WebMediaDLSecurityScopedBookmark.standardizedPath(trimmed)
            let item = WebMediaDLSecurityScopedBookmark.standardizedPath(path)
            if normalizedRoot.isEmpty || item.isEmpty { return false }
            if item == normalizedRoot { return true }
            let prefix = normalizedRoot.hasSuffix("/") ? normalizedRoot : normalizedRoot + "/"
            return item.hasPrefix(prefix)
        }
    }
}
