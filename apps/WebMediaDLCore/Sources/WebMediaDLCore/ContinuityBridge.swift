import Foundation
#if canImport(WatchConnectivity)
import WatchConnectivity
#endif

/// Allowlisted companion kinds. Never a provider argv or native command runner.
public enum WebMediaDLCompanionKind: String, Codable, Sendable, CaseIterable {
    case capture
    case pause
    case resume
    case history
    case status
    case cancel
    case pauseJob = "pause_job"
    case resumeJob = "resume_job"
}

/// Cross-device control messages. Never carries provider argv or a native command runner.
/// watchOS and tvOS send these to the paired Mac, which forwards them to loopback.
public struct WebMediaDLCompanionMessage: Codable, Sendable, Equatable {
    public var kind: WebMediaDLCompanionKind
    public var locator: String?
    public var jobId: String?
    public var surface: WebMediaDLSurface

    public init(
        kind: WebMediaDLCompanionKind,
        locator: String? = nil,
        jobId: String? = nil,
        surface: WebMediaDLSurface = .watchos
    ) {
        self.kind = kind
        self.locator = locator
        self.jobId = jobId
        self.surface = surface
    }

    public init?(kind: String, locator: String? = nil, jobId: String? = nil, surface: WebMediaDLSurface = .watchos) {
        guard let value = WebMediaDLCompanionKind(rawValue: kind) else { return nil }
        self.init(kind: value, locator: locator, jobId: jobId, surface: surface)
    }

    public var nativeCommand: String? { nil }
    public var subprocessWorker: Bool { false }

    enum CodingKeys: String, CodingKey {
        case kind
        case locator
        case jobId
        case surface
        case nativeCommand
        case subprocessWorker
    }

    public func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(kind, forKey: .kind)
        try container.encodeIfPresent(locator, forKey: .locator)
        try container.encodeIfPresent(jobId, forKey: .jobId)
        try container.encode(surface, forKey: .surface)
        try container.encodeNil(forKey: .nativeCommand)
        try container.encode(false, forKey: .subprocessWorker)
    }

    public init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        kind = try container.decode(WebMediaDLCompanionKind.self, forKey: .kind)
        locator = try container.decodeIfPresent(String.self, forKey: .locator)
        jobId = try container.decodeIfPresent(String.self, forKey: .jobId)
        surface = try container.decodeIfPresent(WebMediaDLSurface.self, forKey: .surface) ?? .watchos
        let native = try container.decodeIfPresent(String.self, forKey: .nativeCommand)
        if native != nil {
            throw DecodingError.dataCorruptedError(
                forKey: .nativeCommand,
                in: container,
                debugDescription: "Companion messages cannot carry a native command."
            )
        }
    }

    public func dictionary() -> [String: Any] {
        var payload: [String: Any] = [
            "kind": kind.rawValue,
            "subprocessWorker": "false",
            "surface": surface.rawValue,
            "nativeCommand": NSNull(),
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

/// watchOS/tvOS queue companion messages until the Mac forwards them to loopback.
public struct WebMediaDLCompanionRelay: Sendable {
    public var pending: [WebMediaDLCompanionMessage]

    public init(pending: [WebMediaDLCompanionMessage] = []) {
        self.pending = pending
    }

    public mutating func enqueue(_ message: WebMediaDLCompanionMessage) {
        pending.append(message)
    }

    @discardableResult
    public mutating func drain() -> [WebMediaDLCompanionMessage] {
        let items = pending
        pending = []
        return items
    }
}

public protocol WebMediaDLCompanionTransport: Sendable {
    mutating func send(_ message: WebMediaDLCompanionMessage) async throws
}

/// In-memory queue used until WatchConnectivity or Multipeer delivers to the Mac.
public struct WebMediaDLQueuedCompanionTransport: WebMediaDLCompanionTransport {
    public var relay: WebMediaDLCompanionRelay

    public init(relay: WebMediaDLCompanionRelay = WebMediaDLCompanionRelay()) {
        self.relay = relay
    }

    public mutating func send(_ message: WebMediaDLCompanionMessage) async throws {
        relay.enqueue(message)
    }
}

/// Typed WatchConnectivity userInfo transport. Radio delivery is BLOCKED without a paired Apple device.
public final class WebMediaDLWatchConnectivityTransport: NSObject, WebMediaDLCompanionTransport, @unchecked Sendable {
    public var fallback = WebMediaDLQueuedCompanionTransport()
    public var lastResponse: String?

    public override init() {
        super.init()
    }

    public func activateSession() {
        #if canImport(WatchConnectivity)
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
        #endif
    }

    public func send(_ message: WebMediaDLCompanionMessage) async throws {
        #if canImport(WatchConnectivity)
        if WCSession.isSupported() {
            WCSession.default.transferUserInfo(
                message.dictionary().compactMapValues { $0 is NSNull ? nil : $0 }
            )
            return
        }
        #endif
        var queued = fallback
        try await queued.send(message)
        fallback = queued
    }

    public func sendResponse(_ payload: [String: String]) {
        #if canImport(WatchConnectivity)
        if WCSession.isSupported() {
            WCSession.default.transferUserInfo(payload)
        }
        #endif
        if let body = payload["body"] {
            lastResponse = body
        }
    }
}

#if canImport(WatchConnectivity)
extension WebMediaDLWatchConnectivityTransport: WCSessionDelegate {
    public func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: Error?
    ) {
        _ = (session, activationState, error)
    }

    public func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        if let body = userInfo["body"] as? String {
            lastResponse = body
        }
        _ = session
    }

    #if os(iOS) || os(macOS)
    public func sessionDidBecomeInactive(_ session: WCSession) {
        _ = session
    }

    public func sessionDidDeactivate(_ session: WCSession) {
        session.activate()
    }
    #endif
}
#endif

/// Mac WCSessionDelegate adapter. Converts userInfo dictionaries into typed companion messages.
public final class WebMediaDLMacWatchConnectivityDelegate: NSObject, @unchecked Sendable {
    public var forwarder: WebMediaDLMacCompanionForwarder
    public var relay = WebMediaDLCompanionRelay()

    public init(forwarder: WebMediaDLMacCompanionForwarder) {
        self.forwarder = forwarder
        super.init()
    }

    public func activateSession() {
        #if canImport(WatchConnectivity)
        if WCSession.isSupported() {
            WCSession.default.delegate = self
            WCSession.default.activate()
        }
        #endif
    }

    public func sendResponse(_ payload: [String: String]) {
        #if canImport(WatchConnectivity)
        if WCSession.isSupported() {
            WCSession.default.transferUserInfo(payload)
        }
        #endif
    }

    public func session(_ sessionName: String, didReceiveUserInfo userInfo: [String: Any]) {
        var typed: [String: String] = [:]
        for (key, value) in userInfo {
            if let text = value as? String {
                typed[key] = text
            }
        }
        forwarder.receiveWatchConnectivityUserInfo(typed, into: &relay)
        _ = sessionName
        #if canImport(WatchConnectivity)
        _ = WCSession.default.activationState
        #endif
    }
}

#if canImport(WatchConnectivity)
extension WebMediaDLMacWatchConnectivityDelegate: WCSessionDelegate {
    public func session(
        _ session: WCSession,
        activationDidCompleteWith activationState: WCSessionActivationState,
        error: Error?
    ) {
        _ = (session, activationState, error)
    }

    public func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any] = [:]) {
        self.session("default", didReceiveUserInfo: userInfo)
    }

    #if os(iOS) || os(macOS)
    public func sessionDidBecomeInactive(_ session: WCSession) {
        _ = session
    }

    public func sessionDidDeactivate(_ session: WCSession) {
        session.activate()
    }
    #endif
}
#endif

/// Mac receives drained companion messages and forwards them to loopback.
public struct WebMediaDLMacCompanionForwarder: Sendable {
    public var client: WebMediaDLLoopbackClient

    public init(client: WebMediaDLLoopbackClient) {
        self.client = client
    }

    public func forward(_ relay: inout WebMediaDLCompanionRelay) async throws -> [String] {
        var bodies: [String] = []
        for message in relay.drain() {
            let body = try await client.forwardCompanion(
                kind: message.kind.rawValue,
                locator: message.locator,
                jobId: message.jobId.flatMap(UUID.init(uuidString:)),
                surface: message.surface
            )
            bodies.append(body)
        }
        return bodies
    }

    public func forwardSealed(
        _ relay: inout WebMediaDLCompanionRelay,
        pairingId: UUID,
        sessionKey: String
    ) async throws -> [String] {
        var bodies: [String] = []
        for message in relay.drain() {
            let wrap = client.envelopeWrapRequest(
                pairingId: pairingId,
                sessionKey: sessionKey,
                payload: message.dictionary()
            )
            let (data, _) = try await URLSession.shared.data(for: wrap)
            let object = (try JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
            let body = try await client.send(
                client.sealedCompanionRequest(
                    pairingId: pairingId,
                    sessionKey: sessionKey,
                    nonce: object["nonce"] as? String ?? "",
                    ciphertext: object["ciphertext"] as? String ?? "",
                    mac: object["mac"] as? String ?? ""
                )
            )
            bodies.append(body)
        }
        return bodies
    }

    public mutating func receiveWatchConnectivityUserInfo(
        _ userInfo: [String: String],
        into relay: inout WebMediaDLCompanionRelay
    ) {
        guard let kind = userInfo["kind"].flatMap(WebMediaDLCompanionKind.init(rawValue:)) else {
            return
        }
        let surface = userInfo["surface"].flatMap(WebMediaDLSurface.init(rawValue:)) ?? .watchos
        relay.enqueue(
            WebMediaDLCompanionMessage(
                kind: kind,
                locator: userInfo["locator"],
                jobId: userInfo["jobId"],
                surface: surface
            )
        )
    }
}

public struct WebMediaDLContinuityBridge: Sendable {
    public static let loopbackURL = URL(string: "http://127.0.0.1:8765")!
    public static let allowedKinds: Set<String> = Set(WebMediaDLCompanionKind.allCases.map(\.rawValue))

    /// Watch/tv serialize companion messages. The phone/Mac substitutes the
    /// reachable Mac loopback after WatchConnectivity or Multipeer delivery.
    public var workerURL: URL
    public var isSubprocessWorker: Bool { false }

    public init(workerURL: URL = WebMediaDLContinuityBridge.loopbackURL) {
        self.workerURL = workerURL
    }

    public func message(
        kind: WebMediaDLCompanionKind,
        locator: String? = nil,
        jobId: String? = nil,
        surface: WebMediaDLSurface = .watchos
    ) -> WebMediaDLCompanionMessage {
        WebMediaDLCompanionMessage(kind: kind, locator: locator, jobId: jobId, surface: surface)
    }

    public func message(
        kind: String,
        locator: String? = nil,
        jobId: String? = nil,
        surface: WebMediaDLSurface = .watchos
    ) -> WebMediaDLCompanionMessage {
        WebMediaDLCompanionMessage(kind: kind, locator: locator, jobId: jobId, surface: surface)
            ?? WebMediaDLCompanionMessage(kind: .status, locator: locator, jobId: jobId, surface: surface)
    }

    public func controlMessage(kind: String, locator: String?) -> [String: String] {
        Dictionary(
            uniqueKeysWithValues: message(kind: kind, locator: locator).dictionary()
                .compactMap { key, value in
                    guard let text = value as? String else { return nil }
                    return (key, text)
                }
        )
    }

    public func companionRequest(
        token: String = "",
        kind: String = "status",
        locator: String? = nil,
        jobId: String? = nil
    ) -> URLRequest {
        var request = URLRequest(
            url: workerURL.appendingPathComponent("v1/companion")
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
            "surface": "watchos",
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

    public func sealedCompanionRequest(
        pairingId: String,
        sessionKey: String,
        nonce: String,
        ciphertext: String,
        mac: String
    ) -> URLRequest {
        var request = URLRequest(
            url: workerURL.appendingPathComponent("v1/companion")
        )
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        let body: [String: Any] = [
            "pairing_id": pairingId,
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

    /// Mac forwards a drained companion message to loopback. watchOS/tvOS enqueue
    /// on `WebMediaDLCompanionTransport` instead of opening a subprocess worker.
    public func send(_ message: WebMediaDLCompanionMessage, token: String = "") async throws -> String {
        let request = companionRequest(
            token: token,
            kind: message.kind.rawValue,
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
