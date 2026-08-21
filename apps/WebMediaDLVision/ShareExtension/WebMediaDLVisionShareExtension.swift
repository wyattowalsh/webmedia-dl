import Foundation
import WebMediaDLCore

/// visionOS share-sheet extension adapter. Heavy work waits for Mac pairing.
public enum WebMediaDLVisionShareExtension {
    public static func submitShared(_ values: [String], token: String = "") async throws -> String {
        let client = WebMediaDLLoopbackClient(token: token)
        var last = "no shared locator"
        for locator in WebMediaDLShareItemExtractor.locators(fromShared: values) {
            last = try await client.submit(
                locator: locator,
                surface: .visionos,
                intakeKind: "share_sheet"
            )
        }
        return last
    }
}
