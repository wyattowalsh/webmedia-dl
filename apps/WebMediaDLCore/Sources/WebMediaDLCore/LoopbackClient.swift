import Foundation

public struct WebMediaDLLoopbackClient: Sendable {
    public static let defaultBaseURL = URL(string: "http://127.0.0.1:8765")!

    public var baseURL: URL

    public init(baseURL: URL = WebMediaDLLoopbackClient.defaultBaseURL) {
        self.baseURL = baseURL
    }

    public var isLoopback: Bool {
        let host = baseURL.host ?? ""
        return host == "127.0.0.1" || host == "localhost" || host == "::1"
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
