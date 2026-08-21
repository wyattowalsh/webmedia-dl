import XCTest
@testable import WebMediaDLCore

final class IdentityTests: XCTestCase {
    func testURLDoesNotBecomePath() {
        let job = WebMediaDLJob(locator: "https://example.com/a.mp4", surface: .macos)
        XCTAssertFalse(job.usesURLAsPath)
    }

    func testWatchIsCaptureAndStatus() {
        XCTAssertEqual(WebMediaDLClientRole.captureAndStatus.rawValue, "captureAndStatus")
    }
}
