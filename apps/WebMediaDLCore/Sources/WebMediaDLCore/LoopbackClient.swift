import Foundation

public struct WebMediaDLLoopbackClient: Sendable {
    public static let defaultBaseURL = URL(string: "http://127.0.0.1:8765")!

    public var baseURL: URL
    public var token: String

    public init(baseURL: URL = WebMediaDLLoopbackClient.defaultBaseURL, token: String = "") {
        self.baseURL = baseURL
        self.token = token
    }

    public var isLoopback: Bool {
        let host = baseURL.host ?? ""
        return host == "127.0.0.1" || host == "localhost" || host == "::1"
    }

    private func authorized(_ url: URL, method: String = "GET") -> URLRequest {
        precondition(isLoopback, "Clients may only talk to the loopback worker.")
        var request = URLRequest(url: url)
        request.httpMethod = method
        if !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    public func submitRequest(
        locator: String,
        surface: WebMediaDLSurface,
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        evidence: [[String: String]] = [],
        wait: Bool = false
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

    public func pauseJobRequest(jobId: UUID) -> URLRequest {
        let url = baseURL
            .appendingPathComponent("v1/jobs")
            .appendingPathComponent(jobId.uuidString)
            .appendingPathComponent("pause")
        return authorized(url, method: "POST")
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

    public func resumeJobRequest(jobId: UUID) -> URLRequest {
        let url = baseURL
            .appendingPathComponent("v1/jobs")
            .appendingPathComponent(jobId.uuidString)
            .appendingPathComponent("resume")
        return authorized(url, method: "POST")
    }

    public func companionRequest(kind: String, locator: String? = nil, jobId: UUID? = nil) -> URLRequest {
        var request = authorized(baseURL.appendingPathComponent("v1/companion"), method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var body: [String: Any] = [
            "kind": kind,
            "nativeCommand": NSNull(),
            "subprocessWorker": false,
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

    public func submit(
        locator: String,
        surface: WebMediaDLSurface,
        pairingId: UUID? = nil,
        sessionKey: String? = nil
    ) async throws -> String {
        let (data, response) = try await URLSession.shared.data(
            for: submitRequest(
                locator: locator,
                surface: surface,
                pairingId: pairingId,
                sessionKey: sessionKey
            )
        )
        guard let http = response as? HTTPURLResponse else {
            return String(data: data, encoding: .utf8) ?? "no response"
        }
        return "HTTP \(http.statusCode) \(String(data: data, encoding: .utf8) ?? "")"
    }

    public func history() async throws -> String {
        let (data, response) = try await URLSession.shared.data(for: historyRequest())
        guard let http = response as? HTTPURLResponse else {
            return String(data: data, encoding: .utf8) ?? "no response"
        }
        return "HTTP \(http.statusCode) \(String(data: data, encoding: .utf8) ?? "")"
    }
}

/// Photos / Files / Share destinations require an explicit user-approved root.
public struct WebMediaDLDestinationPolicy: Sendable {
    public var approvedRoots: [String]

    public init(approvedRoots: [String] = []) {
        self.approvedRoots = approvedRoots
    }

    public func allows(_ path: String) -> Bool {
        approvedRoots.contains { path.hasPrefix($0) }
    }
}
