import Foundation

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
    ) -> URLRequest {
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
        if let destinationKind, !destinationKind.isEmpty {
            var intent: [String: Any] = ["destination_kind": destinationKind]
            if let destinationPath {
                intent["destination_path"] = destinationPath
            }
            if !approvedRoots.isEmpty {
                intent["approved_roots"] = approvedRoots
            }
            if destinationKind == "files_app", let destinationPath {
                intent["security_scoped_path"] = destinationPath
            }
            if let bookmarkData {
                intent["security_scoped_bookmark"] = bookmarkData.base64EncodedString()
            }
            body["intent"] = intent
        }
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        return request
    }

    public func historyRequest() -> URLRequest {
        var request = URLRequest(url: relayURL.appendingPathComponent("v1/jobs"))
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
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            return String(data: data, encoding: .utf8) ?? "no response"
        }
        return "HTTP \(http.statusCode) \(String(data: data, encoding: .utf8) ?? "")"
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
        request.httpBody = try JSONSerialization.data(
            withJSONObject: ["client_profile_id": clientProfileId]
        )
        let (data, _) = try await URLSession.shared.data(for: request)
        return try JSONDecoder().decode(WebMediaDLPairingChallenge.self, from: data)
    }
}

/// Mac-side rewrite: LAN/companion requests become loopback worker requests.
public enum WebMediaDLMacWorkerRelay {
    public static func forwardToLoopback(
        _ incoming: URLRequest,
        worker: URL = WebMediaDLLoopbackClient.defaultBaseURL
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
        if let body = incoming.httpBody,
           let json = try? JSONSerialization.jsonObject(with: body) as? [String: Any]
        {
            if let native = json["nativeCommand"] as? String, !native.isEmpty {
                throw WebMediaDLMacWorkerRelayError.nativeCommand
            }
            if json["subprocessWorker"] as? Bool == true {
                throw WebMediaDLMacWorkerRelayError.nativeCommand
            }
        }
        components.scheme = worker.scheme
        components.host = worker.host
        components.port = worker.port
        var forwarded = incoming
        forwarded.url = components.url
        return forwarded
    }
}

public enum WebMediaDLMacWorkerRelayError: Error, Equatable {
    case notLoopbackWorker
    case missingURL
    case nativeCommand
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
        guard let endpoint = WebMediaDLPairedMacEndpoint.load(
            pairingId: pairingId ?? credentials.pairingId,
            sessionKey: sessionKey ?? credentials.sessionKey,
            token: credentials.token,
            defaults: defaults
        ) else {
            throw WebMediaDLHttpDirect.TransferError.pairingRequired
        }
        return try await endpoint.submit(
            locator: locator,
            surface: surface,
            intakeKind: intakeKind,
            destinationKind: destinationKind,
            destinationPath: destinationPath,
            approvedRoots: approvedRoots,
            bookmarkData: bookmarkData
        )
    }
}
