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
    }

    func testContinuityIsNotASubprocessWorker() {
        let bridge = WebMediaDLContinuityBridge()
        XCTAssertFalse(bridge.isSubprocessWorker)
        XCTAssertEqual(WebMediaDLContinuityBridge.loopbackURL.host, "127.0.0.1")
    }

    func testPhotosDestinationRequiresApprovedRoot() {
        let policy = WebMediaDLDestinationPolicy(approvedRoots: ["/Users/me/Movies"])
        XCTAssertTrue(policy.allows("/Users/me/Movies/clip.mp4"))
        XCTAssertFalse(policy.allows("/tmp/escape.mp4"))
        let share = WebMediaDLShareIntake(locator: "https://example.com/a.mp4")
        XCTAssertFalse(share.canPublishToPhotos)
    }
}
