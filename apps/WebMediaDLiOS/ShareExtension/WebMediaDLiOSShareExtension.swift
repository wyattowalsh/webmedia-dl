import Foundation
import WebMediaDLCore

@objc(WebMediaDLiOSShareExtensionPrincipal)
public final class WebMediaDLiOSShareExtensionPrincipal: NSObject, NSExtensionRequestHandling {
    public func beginRequest(with context: NSExtensionContext) {
        let boxed = WebMediaDLUncheckedBox(context)
        Task {
            let context = boxed.value
            let values = await WebMediaDLShareExtensionLoader.loadSharedValues(from: context)
            _ = try? await WebMediaDLiOSShareExtension.submitShared(values)
            context.completeRequest(returningItems: [], completionHandler: nil)
        }
    }
}

/// iOS share-sheet extension adapter. Heavy work waits for Mac pairing.
public enum WebMediaDLiOSShareExtension {
    public static func submitShared(_ values: [String], token: String? = nil) async throws -> String {
        let client = token.map { WebMediaDLLoopbackClient(token: $0) } ?? WebMediaDLWorkerCredentials.loadClient()
        var last = "no shared locator"
        for locator in WebMediaDLShareItemExtractor.locators(fromShared: values) {
            if let saved = try await WebMediaDLHttpDirect.saveIfDirect(
                locator: locator,
                surface: .ios
            ) {
                last = saved.outputPath
                continue
            }
            last = try await client.submit(
                locator: locator,
                surface: .ios,
                intakeKind: "share_sheet"
            )
        }
        for path in WebMediaDLShareItemExtractor.dropPaths(fromShared: values) {
            last = try await client.submit(
                locator: path,
                surface: .ios,
                intakeKind: "drop"
            )
        }
        return last
    }
}
