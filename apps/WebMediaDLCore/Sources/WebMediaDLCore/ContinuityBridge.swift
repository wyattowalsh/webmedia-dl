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
        if try container.decodeIfPresent(Bool.self, forKey: .subprocessWorker) == true {
            throw DecodingError.dataCorruptedError(
                forKey: .subprocessWorker,
                in: container,
                debugDescription: "watchOS and tvOS are not subprocess workers."
            )
        }
    }

    public func dictionary() -> [String: Any] {
        var payload: [String: Any] = [
            "kind": kind.rawValue,
            "subprocessWorker": false,
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

    public static func validate(_ message: WebMediaDLCompanionMessage) throws {
        switch message.kind {
        case .cancel, .pauseJob, .resumeJob:
            guard let raw = message.jobId, UUID(uuidString: raw) != nil else {
                throw WebMediaDLCompanionError.jobIdRequired
            }
        default:
            return
        }
    }
}

public enum WebMediaDLCompanionError: Error, Equatable, LocalizedError {
    case jobIdRequired
    case pairingRequired

    public var errorDescription: String? {
        switch self {
        case .jobIdRequired:
            return "Cancel, pause, and resume of a job require a job UUID."
        case .pairingRequired:
            return "Pair with a Mac before sending companion messages."
        }
    }
}

/// Cancel, pause_job, and resume_job App Intents fail closed without a job UUID.
public enum WebMediaDLCompanionJobControl {
    public static func requireJobId(_ raw: String) throws -> UUID {
        guard let id = UUID(uuidString: raw) else {
            throw WebMediaDLCompanionError.jobIdRequired
        }
        return id
    }
}

/// iPhone hops WatchConnectivity companion messages onto the paired Mac relay.
public enum WebMediaDLWatchCompanionForward {
    public typealias Send = @Sendable (WebMediaDLCompanionMessage) async throws -> String

    public static func forward(
        _ message: WebMediaDLCompanionMessage,
        send: Send
    ) async throws -> String {
        try WebMediaDLCompanionMessage.validate(message)
        return try await send(message)
    }
}

/// watchOS/tvOS Siri and UI controls build typed companion messages. Unknown kinds fail closed.
public enum WebMediaDLCompanionControlMessage {
    public static func make(
        kind: WebMediaDLCompanionKind,
        locator: String? = nil,
        jobId: String? = nil,
        surface: WebMediaDLSurface
    ) throws -> WebMediaDLCompanionMessage {
        let resolvedJobId: String?
        switch kind {
        case .cancel, .pauseJob, .resumeJob:
            resolvedJobId = try WebMediaDLCompanionJobControl.requireJobId(jobId ?? "").uuidString
        default:
            resolvedJobId = jobId
        }
        let message = WebMediaDLCompanionMessage(
            kind: kind,
            locator: locator,
            jobId: resolvedJobId,
            surface: surface
        )
        try WebMediaDLCompanionMessage.validate(message)
        return message
    }

    public static func make(
        kind: String,
        locator: String? = nil,
        jobId: String? = nil,
        surface: WebMediaDLSurface
    ) throws -> WebMediaDLCompanionMessage {
        guard let parsed = WebMediaDLCompanionKind(rawValue: kind) else {
            throw WebMediaDLDomainError("unknown companion kind")
        }
        return try make(kind: parsed, locator: locator, jobId: jobId, surface: surface)
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

    public mutating func persist(defaults: UserDefaults = .standard) throws {
        defaults.set(try JSONEncoder().encode(pending), forKey: WebMediaDLCompanionRelay.defaultsKey)
    }

    public static let defaultsKey = "webmedia-dl.companion-relay"

    public static func load(defaults: UserDefaults = .standard) throws -> WebMediaDLCompanionRelay {
        guard let data = defaults.data(forKey: defaultsKey) else {
            return WebMediaDLCompanionRelay()
        }
        do {
            let pending = try JSONDecoder().decode([WebMediaDLCompanionMessage].self, from: data)
            return WebMediaDLCompanionRelay(pending: pending)
        } catch {
            throw WebMediaDLDomainError("companion relay JSON is not a message list")
        }
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
        try WebMediaDLCompanionMessage.validate(message)
        relay.enqueue(message)
        try relay.persist()
    }
}

/// tvOS companion transport. WatchConnectivity is not a tvOS counterpart; messages
/// go to a saved private/loopback Mac relay, with a durable queue if pairing is missing.
public final class WebMediaDLLocalNetworkCompanionTransport: WebMediaDLCompanionTransport, @unchecked Sendable {
    public var fallback = WebMediaDLQueuedCompanionTransport()
    public var lastResponse: String?

    public init() {}

    public func send(_ message: WebMediaDLCompanionMessage) async throws {
        try WebMediaDLCompanionMessage.validate(message)
        do {
            lastResponse = try await WebMediaDLPairedMacSubmit.companion(message)
        } catch {
            if fallback.relay.pending.isEmpty {
                fallback.relay = try WebMediaDLCompanionRelay.load()
            }
            fallback.relay.enqueue(message)
            try fallback.relay.persist()
            throw error
        }
    }
}

/// Typed WatchConnectivity userInfo transport. Radio delivery is BLOCKED without a paired Apple device.
/// watchOS talks to its iPhone companion; the phone forwards to the Mac LAN relay.
public final class WebMediaDLWatchConnectivityTransport: NSObject, WebMediaDLCompanionTransport, @unchecked Sendable {
    public var fallback = WebMediaDLQueuedCompanionTransport()
    public var lastResponse: String?
    public var onReceivedMessage: (@MainActor (WebMediaDLCompanionMessage) -> Void)?

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
        try WebMediaDLCompanionMessage.validate(message)
        #if canImport(WatchConnectivity)
        if WCSession.isSupported() {
            WCSession.default.transferUserInfo(
                message.dictionary().compactMapValues { $0 is NSNull ? nil : $0 }
            )
            return
        }
        #endif
        var queued = fallback
        if queued.relay.pending.isEmpty {
            queued.relay = try WebMediaDLCompanionRelay.load()
        }
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
        if let kind = (userInfo["kind"] as? String).flatMap(WebMediaDLCompanionKind.init(rawValue:)) {
            let surface = (userInfo["surface"] as? String).flatMap(WebMediaDLSurface.init(rawValue:)) ?? .watchos
            let message = WebMediaDLCompanionMessage(
                kind: kind,
                locator: userInfo["locator"] as? String,
                jobId: userInfo["jobId"] as? String,
                surface: surface
            )
            Task { @MainActor in
                onReceivedMessage?(message)
            }
        }
        _ = session
    }

    #if os(iOS) || os(macOS) || os(visionOS)
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
    public var autoForward = false

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
        if autoForward {
            let queued  = relay
            relay       = WebMediaDLCompanionRelay()
            let current = forwarder
            Task {
                do {
                    let bodies: [String]
                    if let pairingId = current.client.pairingId,
                       let session = current.client.sessionKey,
                       !session.isEmpty {
                        bodies = try await current.forwardSealed(
                            queued,
                            pairingId: pairingId,
                            sessionKey: session
                        )
                    } else {
                        bodies = try await current.forward(queued)
                    }
                    if let body = bodies.last {
                        sendResponse(["kind": "response", "body": body])
                    }
                } catch {
                    sendResponse(["kind": "error", "body": error.localizedDescription])
                }
            }
        }
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

    #if os(iOS) || os(macOS) || os(visionOS)
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

    public func forward(_ relay: WebMediaDLCompanionRelay) async throws -> [String] {
        var copy = relay
        var bodies: [String] = []
        for message in copy.drain() {
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
        _ relay: WebMediaDLCompanionRelay,
        pairingId: UUID,
        sessionKey: String
    ) async throws -> [String] {
        var copy = relay
        var bodies: [String] = []
        for message in copy.drain() {
            let wrap = try client.envelopeWrapRequest(
                pairingId: pairingId,
                sessionKey: sessionKey,
                payload: message.dictionary()
            )
            try WebMediaDLLoopbackClient.requireJSONBody(wrap)
            let (data, response) = try await URLSession.shared.data(for: wrap)
            _ = try WebMediaDLLoopbackClient.requireHTTPSuccess(
                status: (response as? HTTPURLResponse)?.statusCode ?? 0,
                body: data
            )
            let envelope = try Self.requireSealedEnvelope(data)
            let body = try await client.send(
                try client.sealedCompanionRequest(
                    pairingId: pairingId,
                    sessionKey: sessionKey,
                    nonce: envelope.nonce,
                    ciphertext: envelope.ciphertext,
                    mac: envelope.mac
                )
            )
            bodies.append(body)
        }
        return bodies
    }

    public static func requireSealedEnvelope(
        _ data: Data
    ) throws -> (nonce: String, ciphertext: String, mac: String) {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let nonce = object["nonce"] as? String, !nonce.isEmpty,
              let ciphertext = object["ciphertext"] as? String, !ciphertext.isEmpty,
              let mac = object["mac"] as? String, !mac.isEmpty
        else {
            throw WebMediaDLDomainError("envelope JSON is not a sealed companion")
        }
        return (nonce, ciphertext, mac)
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
    ) throws -> URLRequest {
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
        request.httpBody = try WebMediaDLLoopbackClient.jsonBody(body)
        return request
    }

    public func sealedCompanionRequest(
        pairingId: String,
        sessionKey: String,
        nonce: String,
        ciphertext: String,
        mac: String
    ) throws -> URLRequest {
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
        request.httpBody = try WebMediaDLLoopbackClient.jsonBody(body)
        return request
    }

    /// Mac forwards a drained companion message to loopback. watchOS/tvOS enqueue
    /// on `WebMediaDLCompanionTransport` instead of opening a subprocess worker.
    public func send(_ message: WebMediaDLCompanionMessage, token: String = "") async throws -> String {
        let request = try companionRequest(
            token: token,
            kind: message.kind.rawValue,
            locator: message.locator,
            jobId: message.jobId
        )
        try WebMediaDLLoopbackClient.requireJSONBody(request)
        let (data, response) = try await URLSession.shared.data(for: request)
        return try WebMediaDLLoopbackClient.requireHTTPSuccess(
            status: (response as? HTTPURLResponse)?.statusCode ?? 0,
            body: data
        )
    }
}
