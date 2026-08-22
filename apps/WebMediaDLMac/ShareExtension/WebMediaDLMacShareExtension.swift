import Foundation
import WebMediaDLCore

@objc(WebMediaDLMacShareExtensionPrincipal)
public final class WebMediaDLMacShareExtensionPrincipal: NSObject, NSExtensionRequestHandling {
    public func beginRequest(with context: NSExtensionContext) {
        let boxed = WebMediaDLUncheckedBox(context)
        Task {
            let context = boxed.value
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
            let intake = WebMediaDLShareIntake.fromSavedBookmark(locator: locator)
            let files = intake.filesDestination
            last = try await client.submit(
                locator: locator,
                surface: .macos,
                intakeKind: "share_sheet",
                destinationKind: files == nil ? nil : "files_app",
                destinationPath: files?.approvedRoot,
                approvedRoots: files.map { [$0.approvedRoot] } ?? [],
                bookmarkData: files?.bookmark.bookmarkData ?? intake.bookmarkData
            )
        }
        for path in WebMediaDLShareItemExtractor.dropPaths(fromShared: values) {
            let intake = WebMediaDLShareIntake.fromSavedBookmark(locator: path)
            let files = intake.filesDestination
            last = try await client.submit(
                locator: path,
                surface: .macos,
                intakeKind: "drop",
                destinationKind: files == nil ? nil : "files_app",
                destinationPath: files?.approvedRoot,
                approvedRoots: files.map { [$0.approvedRoot] } ?? [],
                bookmarkData: files?.bookmark.bookmarkData ?? intake.bookmarkData
            )
        }
        return last
    }
}
