import Foundation
import WebMediaDLCore

@objc(WebMediaDLMacShareExtensionPrincipal)
public final class WebMediaDLMacShareExtensionPrincipal: NSObject, NSExtensionRequestHandling {
    public func beginRequest(with context: NSExtensionContext) {
        Task {
            let values = await WebMediaDLShareExtensionLoader.loadSharedValues(from: context)
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
