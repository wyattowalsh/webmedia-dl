import Foundation
import WebMediaDLCore

@objc(WebMediaDLiOSShareExtensionPrincipal)
public final class WebMediaDLiOSShareExtensionPrincipal: NSObject, NSExtensionRequestHandling {
    public func beginRequest(with context: NSExtensionContext) {
        let boxed = WebMediaDLUncheckedBox(context)
        Task {
            let context = boxed.value
            let values = await WebMediaDLShareExtensionLoader.loadSharedValues(from: context)
            do {
                _ = try await WebMediaDLiOSShareExtension.submitShared(values)
                context.completeRequest(returningItems: [], completionHandler: nil)
            } catch {
                context.cancelRequest(withError: error)
            }
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
            let intake = WebMediaDLShareIntake.fromSavedBookmark(locator: locator)
            let files = intake.filesDestination
            last = try await WebMediaDLPairedMacSubmit.submit(
                locator: locator,
                surface: .ios,
                credentials: client,
                intakeKind: "share_sheet",
                destinationKind: files == nil ? nil : "files_app",
                destinationPath: files?.approvedRoot,
                approvedRoots: files.map { [$0.approvedRoot] } ?? [],
                bookmarkData: files?.bookmark.bookmarkData ?? intake.bookmarkData
            )
        }
        for path in WebMediaDLShareItemExtractor.dropPaths(fromShared: values) {
            last = try await WebMediaDLPairedMacSubmit.submitDrop(
                localPath: path,
                surface: .ios,
                credentials: client
            )
        }
        return last
    }
}
