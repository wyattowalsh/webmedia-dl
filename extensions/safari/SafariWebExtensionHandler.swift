import Foundation

/// Safari web-extension native handler. Forwards evidence to the loopback worker.
/// SubmitBody forbids `nativeCommand`; this handler never includes it.
@objc public final class SafariWebExtensionHandler: NSObject {
    public static let loopbackURL = URL(string: "http://127.0.0.1:8765")!

    @objc public func beginRequest(with item: Any?) {
        precondition(SafariWebExtensionHandler.loopbackURL.host == "127.0.0.1")
        var locator = ""
        var token = ""
        var evidence: [[String: String]] = []
        if let payload = item as? [String: Any] {
            if let value = payload["locator"] as? String {
                locator = value
            }
            if let value = payload["token"] as? String {
                token = value
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
        if !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.httpBody = try? JSONSerialization.data(
            withJSONObject: [
                "locator": locator,
                "surface": "safari",
                "local_user_confirmed": true,
                "wait": false,
                "intake_kind": "browser_evidence",
                "evidence": evidence,
            ]
        )
        URLSession.shared.dataTask(with: request).resume()
    }
}
