import Foundation
import WebMediaDLCore

@objc(WebMediaDLiPadOSShareExtensionPrincipal)
public final class WebMediaDLiPadOSShareExtensionPrincipal: NSObject, NSExtensionRequestHandling {
    public func beginRequest(with context: NSExtensionContext) {
        let boxed = WebMediaDLUncheckedBox(context)
        Task {
            let context = boxed.value
            let values = await WebMediaDLShareExtensionLoader.loadSharedValues(from: context)
            _ = try? await WebMediaDLiPadOSShareExtension.submitShared(values)
            context.completeRequest(returningItems: [], completionHandler: nil)
        }
    }
}

/// iPadOS share-sheet extension adapter. Heavy work waits for Mac pairing.
public enum WebMediaDLiPadOSShareExtension {
    public static func submitShared(_ values: [String], token: String? = nil) async throws -> String {
        let client = token.map { WebMediaDLLoopbackClient(token: $0) } ?? WebMediaDLWorkerCredentials.loadClient()
        var last = "no shared locator"
        for locator in WebMediaDLShareItemExtractor.locators(fromShared: values) {
            if let saved = try await WebMediaDLHttpDirect.saveIfDirect(
                locator: locator,
                surface: .ipados
            ) {
                last = saved.outputPath
                continue
            }
            last = try await WebMediaDLPairedMacSubmit.submit(
                locator: locator,
                surface: .ipados,
                credentials: client,
                intakeKind: "share_sheet"
            )
        }
        for path in WebMediaDLShareItemExtractor.dropPaths(fromShared: values) {
            last = try await WebMediaDLPairedMacSubmit.submit(
                locator: path,
                surface: .ipados,
                credentials: client,
                intakeKind: "drop"
            )
        }
        return last
    }
}
