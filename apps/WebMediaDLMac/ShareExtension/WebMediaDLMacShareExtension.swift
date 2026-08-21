import Foundation
import WebMediaDLCore

@objc(WebMediaDLMacShareExtensionPrincipal)
public final class WebMediaDLMacShareExtensionPrincipal: NSObject, NSExtensionRequestHandling {
    public func beginRequest(with context: NSExtensionContext) {
        var values: [String] = []
        for item in context.inputItems {
            guard let extensionItem = item as? NSExtensionItem else { continue }
            for provider in extensionItem.attachments ?? [] {
                for identifier in [
                    WebMediaDLShareItemExtractor.urlTypeIdentifier,
                    WebMediaDLShareItemExtractor.fileURLTypeIdentifier,
                    WebMediaDLShareItemExtractor.textTypeIdentifier,
                ] where provider.hasItemConformingToTypeIdentifier(identifier) {
                    provider.loadItem(forTypeIdentifier: identifier, options: nil) { loaded, _ in
                        if let url = loaded as? URL {
                            values.append(url.absoluteString)
                        } else if let text = loaded as? String {
                            values.append(text)
                        }
                    }
                }
            }
        }
        Task {
            _ = try? await WebMediaDLMacShareExtension.submitShared(values)
            context.completeRequest(returningItems: [], completionHandler: nil)
        }
    }
}

/// macOS share-sheet extension adapter. Forwards locators; never runs provider argv.
public enum WebMediaDLMacShareExtension {
    public static func submitShared(_ values: [String], token: String? = nil) async throws -> String {
        let client = token.map { WebMediaDLLoopbackClient(token: $0) } ?? WebMediaDLWorkerCredentials.loadClient()
        var last = "no shared locator"
        for locator in WebMediaDLShareItemExtractor.locators(fromShared: values) {
            last = try await client.submit(
                locator: locator,
                surface: .macos,
                intakeKind: "share_sheet"
            )
        }
        for path in WebMediaDLShareItemExtractor.dropPaths(fromShared: values) {
            last = try await client.submit(
                locator: path,
                surface: .macos,
                intakeKind: "drop"
            )
        }
        return last
    }
}
