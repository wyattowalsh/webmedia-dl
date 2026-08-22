import XCTest
@testable import WebMediaDLCore

final class ContractTests: XCTestCase {
    func testTitleIsNeverArtifactIdentity() {
        let id = UUID()
        let colliding = WebMediaDLJob(
            id: id,
            locator: "https://example.com/a.mp4",
            titleDisplay: id.uuidString,
            surface: .macos
        )
        XCTAssertTrue(colliding.titleUsedAsIdentity)
        let job = WebMediaDLJob(
            locator: "https://example.com/a.mp4",
            titleDisplay: "Clip",
            surface: .macos
        )
        XCTAssertFalse(job.titleUsedAsIdentity)
        XCTAssertNil(WebMediaDLJob(locator: "https://example.com/a.mp4", surface: .cli).titleDisplay)
    }

    func testHistoryDecodesListAndCompanionEnvelope() throws {
        let jobId = UUID()
        let row: [String: Any] = [
            "job_id": jobId.uuidString,
            "state": "completed",
            "policy_profile_id": "personal-full",
            "worker_id": "mac",
            "artifact_ids": ["sha256:abc"],
            "last_events": ["job.completed"],
            "partial": true,
            "failed_kinds": ["audio"],
            "error": "partial",
        ]
        let listData = try JSONSerialization.data(withJSONObject: [row])
        let listed = try WebMediaDLHistoryEntry.decodeList(from: listData)
        XCTAssertEqual(listed.first?.jobId, jobId)
        XCTAssertEqual(listed.first?.id, jobId)
        XCTAssertTrue(listed.first?.partial ?? false)
        XCTAssertEqual(listed.first?.failedKinds, ["audio"])

        let envelope = try JSONSerialization.data(withJSONObject: [
            "kind": "history",
            "jobs": [row],
        ])
        let wrapped = try WebMediaDLHistoryEntry.decodeCompanionHistory(from: envelope)
        XCTAssertEqual(wrapped.first?.state, "completed")
        let raw = try WebMediaDLHistoryEntry.decodeCompanionHistory(from: listData)
        XCTAssertEqual(raw.first?.workerId, "mac")
    }

    func testCompanionMessageRejectsNativeCommand() throws {
        XCTAssertNil(WebMediaDLCompanionMessage(kind: "yt-dlp"))
        XCTAssertEqual(WebMediaDLCompanionMessage(kind: "pause_job")?.kind, .pauseJob)
        let payload: [String: Any] = [
            "kind": "capture",
            "nativeCommand": "yt-dlp",
            "subprocessWorker": false,
            "surface": "watchos",
        ]
        let data = try JSONSerialization.data(withJSONObject: payload)
        XCTAssertThrowsError(try JSONDecoder().decode(WebMediaDLCompanionMessage.self, from: data))

        let allowed = try JSONSerialization.data(withJSONObject: [
            "kind": "status",
            "surface": "tvos",
        ])
        let decoded = try JSONDecoder().decode(WebMediaDLCompanionMessage.self, from: allowed)
        XCTAssertNil(decoded.nativeCommand)
        XCTAssertFalse(decoded.subprocessWorker)
        XCTAssertEqual(decoded.surface, .tvos)
        XCTAssertNil(decoded.dictionary()["nativeCommand"])
        XCTAssertEqual(decoded.dictionary()["subprocessWorker"], "false")
    }

    func testShareIntakeFilesOpenPhotosStayClosed() {
        XCTAssertFalse(WebMediaDLPhotoKitDestination.libraryWriteAvailable)
        let share = WebMediaDLShareIntake(
            locator: "https://example.com/a.mp4",
            approvedRoot: "/Users/me/Movies"
        )
        XCTAssertTrue(share.canPublishToFiles)
        XCTAssertFalse(share.canPublishToPhotos)
        XCTAssertEqual(share.filesDestination?.approvedRoot, "/Users/me/Movies")
        XCTAssertNil(WebMediaDLShareIntake(locator: "https://example.com/a.mp4", approvedRoot: "").filesDestination)
        XCTAssertFalse(WebMediaDLPhotoKitDestination(approvedRoot: "/Users/me/Movies").canPublish)
        XCTAssertFalse(WebMediaDLPhotoKitDestination(approvedRoot: nil).canPublish)
    }

    func testBookmarkStaleAndInvalidDataDenyPaths() {
        XCTAssertFalse(
            WebMediaDLSecurityScopedBookmark(path: "/Users/me/Movies", stale: true)
                .allows("/Users/me/Movies/clip.mp4")
        )
        let invalid = WebMediaDLSecurityScopedBookmark(
            path: "/tmp/wmdl",
            bookmarkData: Data("not-a-bookmark".utf8)
        ).resolve()
        XCTAssertTrue(invalid.stale)
        XCTAssertFalse(invalid.allows("/tmp/wmdl/clip.mp4"))
        let picked = WebMediaDLSecurityScopedBookmark.fromPickedURL(FileManager.default.temporaryDirectory)
        XCTAssertFalse(picked.path.isEmpty)
        XCTAssertNotNil(picked.bookmarkData)
        XCTAssertTrue(picked.allows(picked.path))
        XCTAssertFalse(picked.resolve().stale)
    }

    func testClipboardAndShareExtractorIgnoreNonHTTP() {
        XCTAssertNil(WebMediaDLClipboardIntake(text: "not a locator").locator)
        XCTAssertEqual(
            WebMediaDLShareItemExtractor.locators(fromShared: [
                "  ",
                "javascript:alert(1)",
                "HTTPS://CDN.EXAMPLE.COM/a.mp4",
            ]),
            ["HTTPS://CDN.EXAMPLE.COM/a.mp4"]
        )
        XCTAssertEqual(
            WebMediaDLShareItemExtractor.dropPaths(fromShared: [
                "javascript:alert(1)",
                "not-a-path",
            ]),
            []
        )
        let noisy = WebMediaDLEvent(
            jobId: UUID(),
            type: "job.failed",
            sequence: 1,
            payload: ["stdout": "secret"]
        )
        XCTAssertTrue(noisy.exposesProviderConsole)
    }

    func testLoopbackRequestBuildersStayOnLoopback() {
        XCTAssertTrue(WebMediaDLLoopbackClient(baseURL: URL(string: "http://localhost:8765")!).isLoopback)
        XCTAssertTrue(WebMediaDLLoopbackClient(baseURL: URL(string: "http://[::1]:8765")!).isLoopback)
        XCTAssertFalse(WebMediaDLLoopbackClient(baseURL: URL(string: "http://example.com:8765")!).isLoopback)
        let client = WebMediaDLLoopbackClient()
        let jobId = UUID()
        XCTAssertTrue(client.resumeQueueRequest().url?.absoluteString.contains("queue/resume") ?? false)
        XCTAssertTrue(client.cancelRequest(jobId: jobId).url?.path.contains("cancel") ?? false)
        XCTAssertTrue(client.pauseJobRequest(jobId: jobId).url?.path.contains("pause") ?? false)
        XCTAssertTrue(client.resumeJobRequest(jobId: jobId).url?.path.contains("resume") ?? false)
        XCTAssertTrue(client.artifactsRequest().url?.path.contains("artifacts") ?? false)
        let pairBody = String(data: client.pairRequest().httpBody ?? Data(), encoding: .utf8) ?? ""
        XCTAssertTrue(pairBody.contains("personal-restricted"))
        let wrap = client.envelopeWrapRequest(
            pairingId: jobId,
            sessionKey: "session",
            payload: ["kind": "status"]
        )
        XCTAssertTrue(wrap.url?.absoluteString.contains("envelope") ?? false)
        XCTAssertEqual(
            WebMediaDLLoopbackClient.jobId(from: "HTTP 200 {\"job\":{\"job_id\":\"\(jobId.uuidString)\"}}"),
            jobId
        )
        XCTAssertEqual(
            WebMediaDLLoopbackClient.jobId(from: "HTTP 200 {\"job_id\":\"\(jobId.uuidString)\"}"),
            jobId
        )
        XCTAssertNil(WebMediaDLLoopbackClient.jobId(from: "HTTP 200 nope"))
        XCTAssertNil(WebMediaDLLoopbackClient.jsonObject(from: "no-brace"))
    }

    func testWorkerCredentialsLoadFromAppGroupDefaults() {
        let suite = "webmedia-dl.tests.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        let pairing = UUID()
        defaults.set("tok", forKey: WebMediaDLWorkerCredentials.tokenDefaultsKey)
        defaults.set(pairing.uuidString, forKey: WebMediaDLWorkerCredentials.pairingDefaultsKey)
        defaults.set("sess", forKey: WebMediaDLWorkerCredentials.sessionDefaultsKey)
        defaults.set(Data("bm".utf8), forKey: WebMediaDLWorkerCredentials.bookmarkDefaultsKey)
        let client = WebMediaDLWorkerCredentials.loadClient(defaults: defaults)
        XCTAssertEqual(client.token, "tok")
        XCTAssertEqual(client.pairingId, pairing)
        XCTAssertEqual(client.sessionKey, "sess")
        XCTAssertEqual(WebMediaDLWorkerCredentials.loadBookmark(defaults: defaults), Data("bm".utf8))
        XCTAssertEqual(WebMediaDLWorkerCredentials.appGroupIdentifier, "group.local.webmedia-dl")
        defaults.removePersistentDomain(forName: suite)
    }

    func testContinuityFallsBackAndKeepsNativeCommandNull() {
        let bridge = WebMediaDLContinuityBridge()
        XCTAssertEqual(bridge.message(kind: "not-a-kind").kind, .status)
        XCTAssertEqual(
            bridge.controlMessage(kind: "capture", locator: "https://example.com/a.mp4")["kind"],
            "capture"
        )
        XCTAssertTrue(WebMediaDLContinuityBridge.allowedKinds.contains("pause_job"))
        let sealed = bridge.sealedCompanionRequest(
            pairingId: "pairing",
            sessionKey: "session",
            nonce: "aa",
            ciphertext: "bb",
            mac: "cc"
        )
        let body = String(data: sealed.httpBody ?? Data(), encoding: .utf8) ?? ""
        XCTAssertTrue(body.contains("nativeCommand"))
        XCTAssertTrue(body.contains("pairing"))
        XCTAssertFalse(body.contains("yt-dlp"))
    }

    func testWatchConnectivityFallbackAndMacRelayTyping() async throws {
        var queued = WebMediaDLQueuedCompanionTransport()
        try await queued.send(
            WebMediaDLCompanionMessage(kind: .cancel, jobId: UUID().uuidString, surface: .tvos)
        )
        XCTAssertEqual(queued.relay.pending.count, 1)
        XCTAssertEqual(queued.relay.pending.first?.surface, .tvos)

        let transport = WebMediaDLWatchConnectivityTransport()
        transport.sendResponse(["body": "HTTP 200 {\"job_id\":\"11111111-1111-1111-1111-111111111111\"}"])
        XCTAssertEqual(
            WebMediaDLLoopbackClient.jobId(from: transport.lastResponse ?? ""),
            UUID(uuidString: "11111111-1111-1111-1111-111111111111")
        )
        transport.activateSession()

        var forwarder = WebMediaDLMacCompanionForwarder(client: WebMediaDLLoopbackClient())
        let delegate = WebMediaDLMacWatchConnectivityDelegate(forwarder: forwarder)
        delegate.session("default", didReceiveUserInfo: [
            "kind": "status",
            "surface": "tvos",
            "ignored": 1,
        ])
        XCTAssertEqual(delegate.relay.pending.count, 1)
        XCTAssertEqual(delegate.relay.pending.first?.surface, .tvos)
        delegate.session("default", didReceiveUserInfo: ["kind": "not-a-kind"])
        XCTAssertEqual(delegate.relay.pending.count, 1)
        forwarder.receiveWatchConnectivityUserInfo(
            ["kind": "history", "surface": "watchos"],
            into: &delegate.relay
        )
        XCTAssertEqual(delegate.relay.pending.last?.kind, .history)
        delegate.activateSession()
        delegate.sendResponse(["kind": "response", "body": "ok"])
    }
}
