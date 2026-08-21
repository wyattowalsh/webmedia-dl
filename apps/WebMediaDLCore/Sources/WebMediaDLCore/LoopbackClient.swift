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

    public func submitRequest(
        locator: String,
        surface: WebMediaDLSurface,
        pairingId: UUID? = nil,
        sessionKey: String? = nil,
        evidence: [[String: String]] = []
    ) -> URLRequest {
        precondition(isLoopback, "Clients may only talk to the loopback worker.")
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/jobs"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        var body: [String: Any] = [
            "locator": locator,
            "surface": surface.rawValue,
            "local_user_confirmed": true,
            "evidence": evidence,
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
        precondition(isLoopback, "Clients may only talk to the loopback worker.")
        var request = URLRequest(url: baseURL.appendingPathComponent("v1/jobs"))
        request.httpMethod = "GET"
        if !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    public func cancelRequest(jobId: UUID) -> URLRequest {
        precondition(isLoopback, "Clients may only talk to the loopback worker.")
        let url = baseURL
            .appendingPathComponent("v1/jobs")
            .appendingPathComponent(jobId.uuidString)
            .appendingPathComponent("cancel")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        if !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        return request
    }

    public func submit(
        locator: String,
        surface: WebMediaDLSurface
    ) async throws -> String {
        let (data, response) = try await URLSession.shared.data(
            for: submitRequest(locator: locator, surface: surface)
        )
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
