import Foundation

/// Safari web-extension native handler. Forwards evidence to the loopback worker.
/// SubmitBody forbids nativeCommand; this handler never includes it.
@objc(SafariWebExtensionHandler)
public final class SafariWebExtensionHandler: NSObject, NSExtensionRequestHandling {
    public static let loopbackURL = URL(string: "http://127.0.0.1:8765")!

    public func beginRequest(with context: NSExtensionContext) {
        precondition(SafariWebExtensionHandler.loopbackURL.host == "127.0.0.1")
        let item = context.inputItems.first as? NSExtensionItem
        var locator = ""
        var token = ""
        var evidence: [[String: String]] = []
        if let payload = item?.userInfo?["message"] as? [String: Any] {
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
        URLSession.shared.dataTask(with: request) { _, _, _ in
            context.completeRequest(returningItems: [], completionHandler: nil)
        }.resume()
    }
}
