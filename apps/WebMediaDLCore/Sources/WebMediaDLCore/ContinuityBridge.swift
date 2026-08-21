import Foundation

/// Cross-device control messages. Never carries provider argv or policy bypass.
public struct WebMediaDLContinuityBridge: Sendable {
    public static let loopbackURL = URL(string: "http://127.0.0.1:8765")!

    public var isSubprocessWorker: Bool { false }

    public func controlMessage(kind: String, locator: String?) -> [String: String] {
        var payload = [
            "kind": kind,
            "nativeCommand": "",
        ]
        if let locator {
            payload["locator"] = locator
        }
        return payload
    }
}
