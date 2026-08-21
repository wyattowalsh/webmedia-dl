import Foundation

/// Safari web-extension native handler. Forwards evidence to the loopback worker.
/// Does not expose a generic command runner.
@objc public final class SafariWebExtensionHandler: NSObject {
    public static let loopbackURL = URL(string: "http://127.0.0.1:8765")!

    @objc public func beginRequest(with item: Any?) {
        precondition(SafariWebExtensionHandler.loopbackURL.host == "127.0.0.1")
        var locator = ""
        var evidence: [[String: String]] = []
        if let payload = item as? [String: Any] {
            if let value = payload["locator"] as? String {
                locator = value
            }
            if let rows = payload["evidence"] as? [[String: String]] {
                evidence = rows
            }
        }
        var request = URLRequest(
            url: SafariWebExtensionHandler.loopbackURL.appendingPathComponent("v1/jobs")
        )
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: [
                "locator": locator,
                "surface": "safari",
                "local_user_confirmed": true,
                "wait": false,
                "evidence": evidence,
                "nativeCommand": NSNull(),
            ]
        )
        URLSession.shared.dataTask(with: request).resume()
    }
}
