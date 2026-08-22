import Foundation
#if canImport(Darwin)
import Darwin
#endif
#if canImport(Network)
import Network
#endif

/// HTTP/1.1 framing for the Mac LAN relay. One request per connection.
public enum WebMediaDLMacRelayHTTP {
    public static let maxRequestBytes = 1_048_576

    public struct ParsedRequest: Equatable, Sendable {
        public var method: String
        public var target: String
        public var headers: [String: String]
        public var body: Data
        public var consumed: Int
    }

    public static func parseRequest(_ data: Data) -> ParsedRequest? {
        guard data.count <= maxRequestBytes else { return nil }
        let separator = Data("\r\n\r\n".utf8)
        guard let headerEnd = data.range(of: separator) else { return nil }
        let headerData = data.subdata(in: data.startIndex ..< headerEnd.lowerBound)
        guard let headerText = String(data: headerData, encoding: .utf8) else { return nil }
        let lines = headerText.split(separator: "\r\n", omittingEmptySubsequences: false)
        guard let requestLine = lines.first else { return nil }
        let parts = requestLine.split(separator: " ", omittingEmptySubsequences: true)
        guard parts.count >= 2 else { return nil }
        var headers: [String: String] = [:]
        for line in lines.dropFirst() where !line.isEmpty {
            guard let colon = line.firstIndex(of: ":") else { continue }
            let name = String(line[..<colon]).trimmingCharacters(in: .whitespaces)
            let value = String(line[line.index(after: colon)...]).trimmingCharacters(in: .whitespaces)
            headers[name] = value
        }
        let lengthKey = headers.first { $0.key.lowercased() == "content-length" }?.value
        let contentLength = Int(lengthKey ?? "0") ?? 0
        if contentLength < 0 || contentLength > maxRequestBytes { return nil }
        let bodyStart = headerEnd.upperBound
        guard data.count - bodyStart >= contentLength else { return nil }
        let body = data.subdata(in: bodyStart ..< bodyStart + contentLength)
        return ParsedRequest(
            method: String(parts[0]),
            target: String(parts[1]),
            headers: headers,
            body: body,
            consumed: bodyStart + contentLength
        )
    }

    public static func encodeResponse(
        status: Int,
        reason: String,
        headers: [String: String] = [:],
        body: Data
    ) -> Data {
        var header = "HTTP/1.1 \(status) \(reason)\r\n"
        header += "Content-Length: \(body.count)\r\n"
        header += "Connection: close\r\n"
        var sawType = false
        for (name, value) in headers {
            if name.lowercased() == "content-length" || name.lowercased() == "connection" {
                continue
            }
            if name.lowercased() == "content-type" { sawType = true }
            header += "\(name): \(value)\r\n"
        }
        if !sawType {
            header += "Content-Type: application/json\r\n"
        }
        header += "\r\n"
        return Data(header.utf8) + body
    }
}

public enum WebMediaDLMacRelayServerError: Error, Equatable {
    case notAllowedBind
    case listenFailed
    case publicPeer
    case nativeCommand
}

/// Loopback/LAN HTTP listener. Rewrites onto the loopback worker and refuses
/// `nativeCommand`. Public internet peers are rejected.
public final class WebMediaDLMacRelayServer: @unchecked Sendable {
    public static let defaultPort: UInt16 = 8766

    public let bindHost: String
    public let port: UInt16
    public let localOnly: Bool
    public let advertisedURL: URL
    public let clientPasteURLs: [URL]

    private let worker: URL
    private let transport: @Sendable (URLRequest) async throws -> (Data, URLResponse)
    #if canImport(Network)
    private var listener: NWListener?
    private let queue = DispatchQueue(label: "webmedia-dl.mac-relay")
    #endif

    public init(
        bindHost: String,
        port: UInt16,
        localOnly: Bool,
        worker: URL,
        lanAddresses: [String],
        transport: @escaping @Sendable (URLRequest) async throws -> (Data, URLResponse)
    ) {
        self.bindHost = bindHost
        self.port = port
        self.localOnly = localOnly
        self.worker = worker
        self.transport = transport
        self.advertisedURL = URL(string: "http://127.0.0.1:\(port)")!
        self.clientPasteURLs = Self.clientPasteURLs(port: Int(port), lanAddresses: lanAddresses)
    }

    public static func isAllowedBindHost(_ host: String) -> Bool {
        let trimmed = host.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if trimmed.isEmpty { return false }
        if trimmed == "0.0.0.0" || trimmed == "::" || trimmed == "*" { return true }
        guard let url = URL(string: "http://\(trimmed)") else { return false }
        return WebMediaDLPairedMacEndpoint.isAllowedRelay(url)
    }

    public static func requireAllowedBind(host: String) throws {
        guard isAllowedBindHost(host) else { throw WebMediaDLMacRelayServerError.notAllowedBind }
    }

    public static func isAllowedPeer(_ host: String) -> Bool {
        let trimmed = host.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return false }
        if trimmed.contains(":"), !trimmed.hasPrefix("[") {
            return WebMediaDLPairedMacEndpoint.isAllowedRelay(URL(string: "http://[\(trimmed)]")!)
        }
        guard let url = URL(string: "http://\(trimmed)") else { return false }
        return WebMediaDLPairedMacEndpoint.isAllowedRelay(url)
    }

    public static func clientPasteURLs(port: Int, lanAddresses: [String]) -> [URL] {
        var urls: [URL] = []
        if let loopback = URL(string: "http://127.0.0.1:\(port)") {
            urls.append(loopback)
        }
        var seen: Set<String> = ["127.0.0.1"]
        for address in lanAddresses {
            let host = address.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !host.isEmpty, seen.insert(host).inserted else { continue }
            guard let url = URL(string: "http://\(host):\(port)"),
                  WebMediaDLPairedMacEndpoint.isAllowedRelay(url)
            else { continue }
            urls.append(url)
        }
        return urls
    }

    public static func privateLANIPv4Addresses() -> [String] {
        #if canImport(Darwin)
        var results: [String] = []
        var ifaddr: UnsafeMutablePointer<ifaddrs>?
        guard getifaddrs(&ifaddr) == 0 else { return [] }
        defer { freeifaddrs(ifaddr) }
        var ptr = ifaddr
        while let iface = ptr {
            let flags = Int32(iface.pointee.ifa_flags)
            ptr = iface.pointee.ifa_next
            guard flags & IFF_UP != 0 else { continue }
            guard flags & IFF_LOOPBACK == 0 else { continue }
            guard let sa = iface.pointee.ifa_addr, sa.pointee.sa_family == sa_family_t(AF_INET) else {
                continue
            }
            var addr = sa.withMemoryRebound(to: sockaddr_in.self, capacity: 1) { $0.pointee.sin_addr }
            var host = [CChar](repeating: 0, count: Int(INET_ADDRSTRLEN))
            inet_ntop(AF_INET, &addr, &host, socklen_t(INET_ADDRSTRLEN))
            let ip = String(cString: host)
            if let url = URL(string: "http://\(ip)"), WebMediaDLPairedMacEndpoint.isAllowedRelay(url) {
                results.append(ip)
            }
        }
        return results
        #else
        return []
        #endif
    }

    public static func start(
        bindHost: String = "127.0.0.1",
        port: UInt16 = 0,
        localOnly: Bool = true,
        worker: URL = WebMediaDLLoopbackClient.defaultBaseURL,
        lanAddresses: [String]? = nil,
        transport: (@Sendable (URLRequest) async throws -> (Data, URLResponse))? = nil
    ) async throws -> WebMediaDLMacRelayServer {
        try requireAllowedBind(host: bindHost)
        let send = transport ?? { request in
            try await URLSession.shared.data(for: request)
        }
        #if canImport(Network)
        let params = NWParameters.tcp
        params.acceptLocalOnly = localOnly
        let wildcard = bindHost == "0.0.0.0" || bindHost == "*" || bindHost == "::"
        let nwPort: NWEndpoint.Port = port == 0 ? .any : NWEndpoint.Port(rawValue: port)!
        if !wildcard {
            params.requiredLocalEndpoint = NWEndpoint.hostPort(
                host: NWEndpoint.Host(bindHost),
                port: nwPort
            )
        }
        let listener = try (wildcard
            ? NWListener(using: params, on: nwPort)
            : NWListener(using: params))
        let holder = _RelayHolder()
        listener.newConnectionHandler = { connection in
            holder.server?.serve(connection)
        }
        let boundPort: UInt16 = try await withCheckedThrowingContinuation { cont in
            let once = _OnceResume()
            listener.stateUpdateHandler = { state in
                switch state {
                case .ready:
                    let actual = listener.port?.rawValue ?? port
                    once.resume { cont.resume(returning: actual) }
                case .failed, .cancelled:
                    once.resume { cont.resume(throwing: WebMediaDLMacRelayServerError.listenFailed) }
                default:
                    break
                }
            }
            listener.start(queue: DispatchQueue(label: "webmedia-dl.mac-relay.start"))
        }
        let server = WebMediaDLMacRelayServer(
            bindHost: bindHost,
            port: boundPort,
            localOnly: localOnly,
            worker: worker,
            lanAddresses: lanAddresses ?? privateLANIPv4Addresses(),
            transport: send
        )
        server.listener = listener
        holder.server = server
        return server
        #else
        throw WebMediaDLMacRelayServerError.listenFailed
        #endif
    }

    public func stop() {
        #if canImport(Network)
        listener?.cancel()
        listener = nil
        #endif
    }

    #if canImport(Network)
    private func serve(_ connection: NWConnection) {
        connection.start(queue: queue)
        receive(connection, buffer: Data())
    }

    private func receive(_ connection: NWConnection, buffer: Data) {
        if buffer.count > WebMediaDLMacRelayHTTP.maxRequestBytes {
            reply(
                connection,
                status: 413,
                reason: "Payload Too Large",
                body: Data(#"{"detail":"request too large"}"#.utf8)
            )
            return
        }
        connection.receive(minimumIncompleteLength: 1, maximumLength: 65_536) { data, _, isComplete, error in
            if error != nil {
                connection.cancel()
                return
            }
            var next = buffer
            if let data { next.append(data) }
            if let parsed = WebMediaDLMacRelayHTTP.parseRequest(next) {
                Task { await self.handle(parsed, connection: connection) }
                return
            }
            if isComplete {
                connection.cancel()
                return
            }
            self.receive(connection, buffer: next)
        }
    }

    private func handle(
        _ parsed: WebMediaDLMacRelayHTTP.ParsedRequest,
        connection: NWConnection
    ) async {
        if !localOnly {
            if let host = Self.peerHost(connection), !Self.isAllowedPeer(host) {
                reply(
                    connection,
                    status: 403,
                    reason: "Forbidden",
                    body: Data(#"{"detail":"public peer"}"#.utf8)
                )
                return
            }
        }
        do {
            let incoming = try Self.urlRequest(from: parsed, fallback: advertisedURL)
            let forwarded = try WebMediaDLMacWorkerRelay.forwardToLoopback(incoming, worker: worker)
            let (body, response) = try await transport(forwarded)
            let http = response as? HTTPURLResponse
            var headers: [String: String] = [:]
            if let type = http?.value(forHTTPHeaderField: "Content-Type") {
                headers["Content-Type"] = type
            }
            let payload = WebMediaDLMacRelayHTTP.encodeResponse(
                status: http?.statusCode ?? 200,
                reason: "OK",
                headers: headers,
                body: body
            )
            connection.send(
                content: payload,
                contentContext: .defaultMessage,
                isComplete: true,
                completion: .contentProcessed { _ in connection.cancel() }
            )
        } catch WebMediaDLMacWorkerRelayError.nativeCommand {
            reply(
                connection,
                status: 400,
                reason: "Bad Request",
                body: Data(#"{"detail":"nativeCommand"}"#.utf8)
            )
        } catch {
            reply(
                connection,
                status: 502,
                reason: "Bad Gateway",
                body: Data(#"{"detail":"relay failed"}"#.utf8)
            )
        }
    }

    private func reply(_ connection: NWConnection, status: Int, reason: String, body: Data) {
        let payload = WebMediaDLMacRelayHTTP.encodeResponse(status: status, reason: reason, body: body)
        connection.send(
            content: payload,
            contentContext: .defaultMessage,
            isComplete: true,
            completion: .contentProcessed { _ in connection.cancel() }
        )
    }

    private static func peerHost(_ connection: NWConnection) -> String? {
        switch connection.endpoint {
        case .hostPort(let host, _):
            switch host {
            case .ipv4(let address):
                return address.debugDescription
            case .ipv6(let address):
                if let loopback = IPv6Address("::1"), address == loopback { return "::1" }
                return address.debugDescription
            case .name(let name, _):
                return name
            @unknown default:
                return nil
            }
        default:
            return nil
        }
    }
    #endif

    public static func urlRequest(
        from parsed: WebMediaDLMacRelayHTTP.ParsedRequest,
        fallback: URL
    ) throws -> URLRequest {
        let hostHeader = parsed.headers.first { $0.key.lowercased() == "host" }?.value
        var urlString = "http://\(hostHeader ?? (fallback.host ?? "127.0.0.1"))"
        if hostHeader == nil, let port = fallback.port {
            urlString += ":\(port)"
        }
        urlString += parsed.target.hasPrefix("/") ? parsed.target : "/\(parsed.target)"
        guard let url = URL(string: urlString) else {
            throw WebMediaDLMacWorkerRelayError.missingURL
        }
        var request = URLRequest(url: url)
        request.httpMethod = parsed.method
        request.httpBody = parsed.body.isEmpty ? nil : parsed.body
        let hopByHop: Set<String> = [
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailers",
            "transfer-encoding",
            "upgrade",
            "host",
            "content-length",
        ]
        for (name, value) in parsed.headers {
            guard !hopByHop.contains(name.lowercased()) else { continue }
            request.setValue(value, forHTTPHeaderField: name)
        }
        return request
    }
}

private final class _RelayHolder: @unchecked Sendable {
    var server: WebMediaDLMacRelayServer?
}

private final class _OnceResume: @unchecked Sendable {
    private let lock = NSLock()
    private var done = false

    func resume(_ body: () -> Void) {
        lock.lock()
        defer { lock.unlock() }
        guard !done else { return }
        done = true
        body()
    }
}
