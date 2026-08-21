import Foundation
import WebMediaDLCore

@objc(WebMediaDLVisionShareExtensionPrincipal)
public final class WebMediaDLVisionShareExtensionPrincipal: NSObject, NSExtensionRequestHandling {
    public func beginRequest(with context: NSExtensionContext) {
        Task {
            let values = await WebMediaDLShareExtensionLoader.loadSharedValues(from: context)
            _ = try? await WebMediaDLVisionShareExtension.submitShared(values)
            context.completeRequest(returningItems: [], completionHandler: nil)
        }
    }
}

/// visionOS share-sheet extension adapter. Heavy work waits for Mac pairing.
public enum WebMediaDLVisionShareExtension {
    public static func submitShared(_ values: [String], token: String? = nil) async throws -> String {
        let client = token.map { WebMediaDLLoopbackClient(token: $0) } ?? WebMediaDLWorkerCredentials.loadClient()
        var last = "no shared locator"
        for locator in WebMediaDLShareItemExtractor.locators(fromShared: values) {
            last = try await client.submit(
                locator: locator,
                surface: .visionos,
                intakeKind: "share_sheet"
            )
        }
        for path in WebMediaDLShareItemExtractor.dropPaths(fromShared: values) {
            last = try await client.submit(
                locator: path,
                surface: .visionos,
                intakeKind: "drop"
            )
        }
        return last
    }
}
