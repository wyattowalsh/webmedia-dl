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

    func testLoopbackDefaultIsLocalhost() throws {
        let client = WebMediaDLLoopbackClient()
        XCTAssertTrue(client.isLoopback)
        XCTAssertEqual(client.baseURL.host, "127.0.0.1")
        XCTAssertTrue(client.pauseQueueRequest().url?.absoluteString.contains("queue/pause") ?? false)
        XCTAssertTrue(client.healthRequest().url?.path.hasSuffix("/health") ?? false)
        XCTAssertTrue(client.queueStatusRequest().url?.absoluteString.contains("/v1/queue") ?? false)
        XCTAssertTrue(try client.companionRequest(kind: "status").url?.absoluteString.contains("companion") ?? false)
        XCTAssertTrue(
            try client.sealedCompanionRequest(
                pairingId: UUID(),
                sessionKey: "session",
                nonce: "aa",
                ciphertext: "bb",
                mac: "cc"
            ).url?.absoluteString.contains("companion") ?? false
        )
        let paired = WebMediaDLLoopbackClient(
            pairingId: UUID(uuidString: "11111111-1111-1111-1111-111111111111"),
            sessionKey: "session"
        )
        XCTAssertEqual(
            paired.historyRequest().value(forHTTPHeaderField: "X-WebMedia-Pairing"),
            "11111111-1111-1111-1111-111111111111"
        )
        XCTAssertEqual(paired.historyRequest().value(forHTTPHeaderField: "X-WebMedia-Session"), "session")
        XCTAssertEqual(
            WebMediaDLLoopbackClient.sessionKey(from: "HTTP 200 {\"session_key\":\"abc\",\"confirmed\":true}"),
            "abc"
        )
        XCTAssertNil(WebMediaDLLoopbackClient.sessionKey(from: "HTTP 400 {\"detail\":\"no\"}"))
        XCTAssertNil(WebMediaDLLoopbackClient.sessionKey(from: "HTTP 200 {\"session_key\":\"  \"}"))
        XCTAssertEqual(
            WebMediaDLLoopbackClient.derivedSessionKey(nonce: "pairing-nonce"),
            "bc863f6d9e1fc62a49c474506a660ac0a6f44a19d97e41348d3a2e682c1cdf63"
        )
    }

    func testContinuityIsNotASubprocessWorker() throws {
        let bridge = WebMediaDLContinuityBridge()
        XCTAssertFalse(bridge.isSubprocessWorker)
        XCTAssertEqual(WebMediaDLContinuityBridge.loopbackURL.host, "127.0.0.1")
        let message = bridge.message(kind: "capture", locator: "https://example.com/a.mp4")
        XCTAssertNil(message.nativeCommand)
        XCTAssertFalse(message.subprocessWorker)
        XCTAssertTrue(try bridge.companionRequest().url?.absoluteString.contains("companion") ?? false)
        XCTAssertTrue(WebMediaDLContinuityBridge.allowedKinds.contains("history"))
        XCTAssertEqual(
            Set(WebMediaDLCompanionKind.allCases.map(\.rawValue)),
            Set(["capture", "pause", "resume", "history", "status", "cancel", "pause_job", "resume_job"])
        )
        var relay = WebMediaDLCompanionRelay()
        relay.enqueue(message)
        XCTAssertEqual(relay.pending.count, 1)
        XCTAssertEqual(relay.drain().count, 1)
        XCTAssertTrue(relay.pending.isEmpty)
        relay.enqueue(message)
        let suiteName = "webmedia-dl.relay.\(UUID().uuidString)"
        let suite = UserDefaults(suiteName: suiteName)!
        try relay.persist(defaults: suite)
        XCTAssertEqual(try WebMediaDLCompanionRelay.load(defaults: suite).pending, [message])
        suite.set(Data("nope".utf8), forKey: WebMediaDLCompanionRelay.defaultsKey)
        do {
            _ = try WebMediaDLCompanionRelay.load(defaults: suite)
            XCTFail("corrupt companion relay JSON must fail closed")
        } catch let error as WebMediaDLDomainError {
            XCTAssertTrue(error.message.contains("companion relay JSON"))
        }
        XCTAssertEqual(suite.data(forKey: WebMediaDLCompanionRelay.defaultsKey), Data("nope".utf8))
        suite.removePersistentDomain(forName: suiteName)
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

    func testPhotosDestinationRequiresApprovedRoot() throws {
        let policy = WebMediaDLDestinationPolicy(approvedRoots: ["/Users/me/Movies"])
        XCTAssertTrue(policy.allows("/Users/me/Movies/clip.mp4"))
        XCTAssertFalse(policy.allows("/tmp/escape.mp4"))
        XCTAssertFalse(policy.allows("/Users/me/Movies-backup/clip.mp4"))
        XCTAssertFalse(WebMediaDLDestinationPolicy(approvedRoots: ["Movies"]).allows("Movies/clip.mp4"))
        let share = WebMediaDLShareIntake(locator: "https://example.com/a.mp4")
        XCTAssertFalse(share.canPublishToPhotos)
        XCTAssertFalse(share.canPublishToFiles)
        let bookmark = WebMediaDLSecurityScopedBookmark(path: "/Users/me/Movies")
        XCTAssertTrue(bookmark.allows("/Users/me/Movies/clip.mp4"))
        XCTAssertFalse(bookmark.allows("/Users/me/Movies-backup/clip.mp4"))
        XCTAssertFalse(bookmark.allows("/Users/me/Movies/../Movies-backup/clip.mp4"))
        XCTAssertThrowsError(
            try WebMediaDLExportIntent(
                destinationKind: .filesApp,
                destinationPath: "/Users/me/Movies/../Movies-backup",
                approvedRoots: ["/Users/me/Movies"],
                securityScopedBookmark: "ZmFrZQ=="
            )
        )
        XCTAssertThrowsError(
            try WebMediaDLExportIntent(containerPreference: "../../../../tmp/escape")
        )
        XCTAssertThrowsError(
            try WebMediaDLExportIntent(containerPreference: "mkv; rm -rf /")
        )
        XCTAssertThrowsError(
            try WebMediaDLExportIntent(containerPreference: "")
        )
        XCTAssertFalse(WebMediaDLExportIntent.isSafeContainer("verylongcontainer"))
        XCTAssertTrue(WebMediaDLExportIntent.isSafeContainer("mkv"))
        XCTAssertEqual(
            try WebMediaDLExportIntent(containerPreference: "mkv").containerPreference,
            "mkv"
        )
        XCTAssertFalse(WebMediaDLSecurityScopedBookmark(path: "Movies").allows("Movies/clip.mp4"))
        XCTAssertFalse(WebMediaDLPhotoKitDestination(approvedRoot: "/Users/me/Movies").canPublish)
        let clip = WebMediaDLClipboardIntake(text: "see https://cdn.example.com/a.mp4 please")
        XCTAssertEqual(clip.locator, "https://cdn.example.com/a.mp4")
        XCTAssertFalse(clip.usesURLAsPath)
        XCTAssertEqual(clip.intakeKind, "paste")
        let event = try WebMediaDLEvent(jobId: UUID(), type: "job.completed", sequence: 1)
        XCTAssertFalse(event.exposesProviderConsole)
        let files = WebMediaDLFilesDestination(bookmark: bookmark)
        XCTAssertTrue(files.allows("/Users/me/Movies/out.mp4"))
        for surface in [WebMediaDLSurface.macos] {
            let request = try WebMediaDLLoopbackClient().submitRequest(
                locator: "https://example.com/a.mp4",
                surface: surface,
                destinationKind: "files_app",
                destinationPath: "/Users/me/Movies",
                approvedRoots: ["/Users/me/Movies"],
                bookmarkData: Data("bookmark".utf8)
            )
            let body = String(data: request.httpBody ?? Data(), encoding: .utf8) ?? ""
            XCTAssertTrue(body.contains("files_app"), surface.rawValue)
            XCTAssertTrue(body.contains("security_scoped_path"), surface.rawValue)
            XCTAssertTrue(body.contains("security_scoped_bookmark"), surface.rawValue)
            XCTAssertTrue(body.contains(surface.rawValue), surface.rawValue)
        }
        for surface in WebMediaDLSurface.completeClients {
            XCTAssertTrue(surface.isCompleteClient)
            let request = try WebMediaDLLoopbackClient().submitRequest(
                locator: "https://example.com/a.mp4",
                surface: surface,
                destinationKind: "files_app",
                destinationPath: "/var/mobile/Containers/Data/clip",
                approvedRoots: ["/var/mobile/Containers/Data/clip"],
                bookmarkData: Data("bookmark".utf8)
            )
            let body = String(data: request.httpBody ?? Data(), encoding: .utf8) ?? ""
            XCTAssertTrue(body.contains("staging_only"), surface.rawValue)
            XCTAssertFalse(body.contains("files_app"), surface.rawValue)
            XCTAssertFalse(body.contains("/var/mobile"), surface.rawValue)
        }
        let request = try WebMediaDLLoopbackClient().submitRequest(
            locator: "https://example.com/a.mp4",
            surface: .macos,
            destinationKind: "files_app",
            destinationPath: "/Users/me/Movies",
            approvedRoots: ["/Users/me/Movies"]
        )
        let body = String(data: request.httpBody ?? Data(), encoding: .utf8) ?? ""
        XCTAssertTrue(body.contains("files_app"))
        XCTAssertTrue(body.contains("security_scoped_path"))
        let bookmarked = try WebMediaDLLoopbackClient().submitRequest(
            locator: "https://example.com/a.mp4",
            surface: .macos,
            destinationKind: "files_app",
            destinationPath: "/Users/me/Movies",
            approvedRoots: ["/Users/me/Movies"],
            bookmarkData: Data("bookmark".utf8)
        )
        let bookmarkedBody = String(data: bookmarked.httpBody ?? Data(), encoding: .utf8) ?? ""
        XCTAssertTrue(bookmarkedBody.contains("security_scoped_bookmark"))
        XCTAssertFalse(WebMediaDLSecurityScopedBookmark(path: "").allows("/Users/me/Movies/clip.mp4"))
        XCTAssertFalse(WebMediaDLSecurityScopedBookmark(path: "   ").allows("/Users/me/Movies/clip.mp4"))
        XCTAssertFalse(WebMediaDLDestinationPolicy(approvedRoots: ["", " "]).allows("/Users/me/Movies/clip.mp4"))
        _ = WebMediaDLWorkerCredentials.loadBookmark()
        let suiteName = "webmedia-dl.share-intake.\(UUID().uuidString)"
        let suite = UserDefaults(suiteName: suiteName)!
        let empty = WebMediaDLShareIntake.fromSavedBookmark(
            locator: "https://example.com/a.mp4",
            defaults: suite
        )
        XCTAssertNil(empty.filesDestination)
        XCTAssertFalse(empty.canPublishToFiles)
        suite.set("/Users/me/Movies".data(using: .utf8), forKey: WebMediaDLWorkerCredentials.bookmarkDefaultsKey)
        let saved = WebMediaDLShareIntake.fromSavedBookmark(
            locator: "https://example.com/a.mp4",
            defaults: suite
        )
        XCTAssertEqual(saved.bookmarkData, "/Users/me/Movies".data(using: .utf8))
        let explicit = WebMediaDLShareIntake(
            locator: "https://example.com/a.mp4",
            approvedRoot: "/Users/me/Movies",
            bookmarkData: Data("bookmark".utf8)
        )
        XCTAssertEqual(explicit.resolvedForSubmit(defaults: suite).filesDestination?.approvedRoot, "/Users/me/Movies")
        XCTAssertTrue(explicit.canPublishToFiles)
        XCTAssertEqual(
            explicit.resolvedForSubmit(defaults: suite).filesDestination?.bookmark.bookmarkData,
            Data("bookmark".utf8)
        )
        suite.removePersistentDomain(forName: suiteName)
    }

    func testCompanionKindEncodesNullNativeCommand() throws {
        XCTAssertEqual(WebMediaDLCompanionKind.pauseJob.rawValue, "pause_job")
        XCTAssertEqual(WebMediaDLCompanionKind.capture.rawValue, "capture")
        let encoded = try JSONEncoder().encode(WebMediaDLCompanionMessage(kind: .history))
        let object = try JSONSerialization.jsonObject(with: encoded) as? [String: Any]
        XCTAssertTrue(object?["nativeCommand"] is NSNull)
        XCTAssertFalse(WebMediaDLCompanionMessage(kind: .status).subprocessWorker)
        XCTAssertNotNil(WebMediaDLWorkerCredentials.loadClient().baseURL)
    }
}
