import Foundation

/// Cross-device control messages. Never carries provider argv or a native command runner.
/// watchOS and tvOS send these to the paired Mac, which forwards them to loopback.
public struct WebMediaDLCompanionMessage: Sendable, Equatable {
    public var kind: String
    public var locator: String?
    public var jobId: String?

    public init(kind: String, locator: String? = nil, jobId: String? = nil) {
        self.kind = kind
        self.locator = locator
        self.jobId = jobId
    }

    public var nativeCommand: String? { nil }
    public var subprocessWorker: Bool { false }

    public func dictionary() -> [String: String] {
        var payload = [
            "kind": kind,
            "subprocessWorker": "false",
        ]
        if let locator {
            payload["locator"] = locator
        }
        if let jobId {
            payload["jobId"] = jobId
        }
        return payload
    }
}

public struct WebMediaDLContinuityBridge: Sendable {
    public static let loopbackURL = URL(string: "http://127.0.0.1:8765")!
    public static let allowedKinds: Set<String> = [
        "capture", "pause", "resume", "history", "status", "cancel", "pause_job", "resume_job",
    ]

    public var isSubprocessWorker: Bool { false }

    public func message(kind: String, locator: String? = nil, jobId: String? = nil) -> WebMediaDLCompanionMessage {
        WebMediaDLCompanionMessage(kind: kind, locator: locator, jobId: jobId)
    }

    public func controlMessage(kind: String, locator: String?) -> [String: String] {
        message(kind: kind, locator: locator).dictionary()
    }

    public func companionRequest(
        token: String = "",
        kind: String = "status",
        locator: String? = nil,
        jobId: String? = nil
    ) -> URLRequest {
        var request = URLRequest(
            url: WebMediaDLContinuityBridge.loopbackURL.appendingPathComponent("v1/companion")
        )
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        var body: [String: Any] = [
            "kind": kind,
            "nativeCommand": NSNull(),
            "subprocessWorker": false,
        ]
        if let locator {
            body["locator"] = locator
        }
        if let jobId {
            body["job_id"] = jobId
        }
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        return request
    }

    public func send(_ message: WebMediaDLCompanionMessage, token: String = "") async throws -> String {
        let request = companionRequest(
            token: token,
            kind: message.kind,
            locator: message.locator,
            jobId: message.jobId
        )
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            return String(data: data, encoding: .utf8) ?? "no response"
        }
        return "HTTP \(http.statusCode) \(String(data: data, encoding: .utf8) ?? "")"
    }
}
