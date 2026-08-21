import Foundation
import WebMediaDLCore

/// macOS share-sheet extension adapter. Forwards locators; never runs provider argv.
public enum WebMediaDLMacShareExtension {
    public static func submitShared(_ values: [String], token: String = "") async throws -> String {
        let client = WebMediaDLLoopbackClient(token: token)
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
