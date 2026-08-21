import XCTest
@testable import WebMediaDLCore

final class IdentityTests: XCTestCase {
    func testURLDoesNotBecomePath() {
        let job = WebMediaDLJob(locator: "https://example.com/a.mp4", surface: .macos)
        XCTAssertFalse(job.usesURLAsPath)
    }

    func testWatchIsCaptureAndStatus() {
        XCTAssertEqual(WebMediaDLClientRole.captureAndStatus.rawValue, "captureAndStatus")
        let share = WebMediaDLShareIntake(locator: "https://example.com/a.mp4")
        XCTAssertFalse(share.canPublishToPhotos)
    }

    func testLoopbackDefaultIsLocalhost() {
        let client = WebMediaDLLoopbackClient()
        XCTAssertTrue(client.isLoopback)
        XCTAssertEqual(client.baseURL.host, "127.0.0.1")
        XCTAssertTrue(client.pauseQueueRequest().url?.absoluteString.contains("queue/pause") ?? false)
        XCTAssertTrue(client.companionRequest(kind: "status").url?.absoluteString.contains("companion") ?? false)
        let paired = WebMediaDLLoopbackClient(
            pairingId: UUID(uuidString: "11111111-1111-1111-1111-111111111111"),
            sessionKey: "session"
        )
        XCTAssertEqual(
            paired.historyRequest().value(forHTTPHeaderField: "X-WebMedia-Pairing"),
            "11111111-1111-1111-1111-111111111111"
        )
        XCTAssertEqual(paired.historyRequest().value(forHTTPHeaderField: "X-WebMedia-Session"), "session")
    }

    func testContinuityIsNotASubprocessWorker() {
        let bridge = WebMediaDLContinuityBridge()
        XCTAssertFalse(bridge.isSubprocessWorker)
        XCTAssertEqual(WebMediaDLContinuityBridge.loopbackURL.host, "127.0.0.1")
        let message = bridge.message(kind: "capture", locator: "https://example.com/a.mp4")
        XCTAssertNil(message.nativeCommand)
        XCTAssertFalse(message.subprocessWorker)
        XCTAssertTrue(bridge.companionRequest().url?.absoluteString.contains("companion") ?? false)
        XCTAssertTrue(WebMediaDLContinuityBridge.allowedKinds.contains("history"))
        var relay = WebMediaDLCompanionRelay()
        relay.enqueue(message)
        XCTAssertEqual(relay.pending.count, 1)
        XCTAssertEqual(relay.drain().count, 1)
        XCTAssertTrue(relay.pending.isEmpty)
        XCTAssertEqual(
            WebMediaDLShareItemExtractor.locators(fromShared: [
                "https://example.com/a.mp4",
                "file:///tmp/secret.png",
            ]),
            ["https://example.com/a.mp4"]
        )
        XCTAssertEqual(
            WebMediaDLShareItemExtractor.dropPaths(fromShared: [
                "https://example.com/a.mp4",
                "file:///tmp/secret.png",
                "/tmp/local.png",
            ]),
            ["/tmp/secret.png", "/tmp/local.png"]
        )
    }

    func testPhotosDestinationRequiresApprovedRoot() {
        let policy = WebMediaDLDestinationPolicy(approvedRoots: ["/Users/me/Movies"])
        XCTAssertTrue(policy.allows("/Users/me/Movies/clip.mp4"))
        XCTAssertFalse(policy.allows("/tmp/escape.mp4"))
        XCTAssertFalse(policy.allows("/Users/me/Movies-backup/clip.mp4"))
        let share = WebMediaDLShareIntake(locator: "https://example.com/a.mp4")
        XCTAssertFalse(share.canPublishToPhotos)
        XCTAssertFalse(share.canPublishToFiles)
        let bookmark = WebMediaDLSecurityScopedBookmark(path: "/Users/me/Movies")
        XCTAssertTrue(bookmark.allows("/Users/me/Movies/clip.mp4"))
        XCTAssertFalse(bookmark.allows("/Users/me/Movies-backup/clip.mp4"))
        XCTAssertFalse(WebMediaDLPhotoKitDestination(approvedRoot: "/Users/me/Movies").canPublish)
        let clip = WebMediaDLClipboardIntake(text: "see https://cdn.example.com/a.mp4 please")
        XCTAssertEqual(clip.locator, "https://cdn.example.com/a.mp4")
        XCTAssertFalse(clip.usesURLAsPath)
        XCTAssertEqual(clip.intakeKind, "paste")
        let event = WebMediaDLEvent(jobId: UUID(), type: "job.completed", sequence: 1)
        XCTAssertFalse(event.exposesProviderConsole)
        let files = WebMediaDLFilesDestination(bookmark: bookmark)
        XCTAssertTrue(files.allows("/Users/me/Movies/out.mp4"))
        let request = WebMediaDLLoopbackClient().submitRequest(
            locator: "https://example.com/a.mp4",
            surface: .macos,
            destinationKind: "files_app",
            destinationPath: "/Users/me/Movies",
            approvedRoots: ["/Users/me/Movies"]
        )
        let body = String(data: request.httpBody ?? Data(), encoding: .utf8) ?? ""
        XCTAssertTrue(body.contains("files_app"))
        XCTAssertTrue(body.contains("security_scoped_path"))
    }
}
