import XCTest
#if canImport(WatchConnectivity)
import WatchConnectivity
#endif
@testable import WebMediaDLCore

private final class WebMediaDLWatchForwardProbe: @unchecked Sendable {
    var message: WebMediaDLCompanionMessage?
    var sent = 0
}

private final class WebMediaDLWorkerStartProbe: @unchecked Sendable {
    var process: AnyObject?
}

private final class WebMediaDLCompleteClientControlProbe: @unchecked Sendable {
    var kind: WebMediaDLCompleteClientControl.Kind?
    var jobId: UUID?
    var sent = 0
}

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
        XCTAssertThrowsError(try WebMediaDLHistoryEntry.decodeCompanionHistory(from: Data("nope".utf8)))
        XCTAssertThrowsError(try WebMediaDLHistoryEntry.decodeList(from: Data("{}".utf8)))
        let pairingId = UUID()
        let challenge = try JSONDecoder().decode(
            WebMediaDLPairingChallenge.self,
            from: JSONSerialization.data(withJSONObject: [
                "pairing_id": pairingId.uuidString,
                "nonce": "pairing-nonce",
                "expires_at": "2026-08-18T00:05:00Z",
                "worker_id": "mac",
                "confirmed": false,
            ])
        )
        XCTAssertEqual(challenge.pairingId, pairingId)
        XCTAssertEqual(challenge.nonce, "pairing-nonce")
        XCTAssertEqual(challenge.confirmed, false)
        let confirmation = try JSONDecoder().decode(
            WebMediaDLPairingConfirmation.self,
            from: JSONSerialization.data(withJSONObject: [
                "pairing_id": pairingId.uuidString,
                "confirmed": true,
                "session_key": "sess",
                "expires_at": "2026-08-18T00:10:00Z",
            ])
        )
        XCTAssertEqual(confirmation.sessionKey, "sess")
        XCTAssertTrue(confirmation.confirmed)
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
        XCTAssertTrue(decoded.dictionary()["nativeCommand"] is NSNull)
        XCTAssertEqual(decoded.dictionary()["subprocessWorker"] as? Bool, false)
        XCTAssertNil((decoded.dictionary()["nativeCommand"] as? String))
        XCTAssertEqual(
            WebMediaDLCompanionError.jobIdRequired.errorDescription,
            "Cancel, pause, and resume of a job require a job UUID."
        )
        XCTAssertThrowsError(
            try WebMediaDLCompanionMessage.validate(
                WebMediaDLCompanionMessage(kind: .cancel, surface: .watchos)
            )
        )
        XCTAssertThrowsError(
            try WebMediaDLCompanionMessage.validate(
                WebMediaDLCompanionMessage(kind: .pauseJob, jobId: "not-a-uuid", surface: .watchos)
            )
        )

        let subprocess: [String: Any] = [
            "kind": "status",
            "subprocessWorker": true,
            "surface": "watchos",
        ]
        let subprocessData = try JSONSerialization.data(withJSONObject: subprocess)
        XCTAssertThrowsError(try JSONDecoder().decode(WebMediaDLCompanionMessage.self, from: subprocessData))
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

    func testClipboardAndShareExtractorIgnoreNonHTTP() async throws {
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
        XCTAssertThrowsError(
            try WebMediaDLEvent(
                jobId: UUID(),
                type: "job.failed",
                sequence: 1,
                payload: ["stdout": "secret"]
            )
        )
        XCTAssertThrowsError(
            try WebMediaDLEvent(
                jobId: UUID(),
                type: "job.failed",
                sequence: 1,
                payload: ["cookies_path": "/tmp/cookies.txt"]
            )
        )
        let eventJSON = Data("""
            {"event_id":"11111111-1111-1111-1111-111111111111","job_id":"11111111-1111-1111-1111-111111111111","type":"job.failed","sequence":1,"payload":{"nativeCommand":"yt-dlp"}}
            """.utf8)
        XCTAssertThrowsError(try JSONDecoder().decode(WebMediaDLEvent.self, from: eventJSON))
        let nestedJSON = Data("""
            {"event_id":"11111111-1111-1111-1111-111111111111","job_id":"11111111-1111-1111-1111-111111111111","type":"job.failed","sequence":1,"payload":{"meta":{"stdout":"secret"}}}
            """.utf8)
        XCTAssertThrowsError(try JSONDecoder().decode(WebMediaDLEvent.self, from: nestedJSON))
        let numericJSON = Data("""
            {"event_id":"11111111-1111-1111-1111-111111111111","job_id":"11111111-1111-1111-1111-111111111111","type":"job.progress","sequence":1,"payload":{"bytes":1024,"ok":true}}
            """.utf8)
        let numeric = try JSONDecoder().decode(WebMediaDLEvent.self, from: numericJSON)
        XCTAssertEqual(numeric.payload["bytes"], .int(1024))
        XCTAssertEqual(numeric.payload["ok"], .bool(true))
        XCTAssertFalse(numeric.exposesProviderConsole)
        let shared = "https://cdn.example.com/a.mp4"
        let provider = NSItemProvider(
            item: shared as NSString,
            typeIdentifier: WebMediaDLShareItemExtractor.textTypeIdentifier
        )
        let loaded = await WebMediaDLShareExtensionLoader.loadItem(from: provider)
        XCTAssertEqual(loaded, shared)
    }

    func testLoopbackRequestBuildersStayOnLoopback() async throws {
        XCTAssertTrue(WebMediaDLLoopbackClient(baseURL: URL(string: "http://localhost:8765")!).isLoopback)
        XCTAssertTrue(WebMediaDLLoopbackClient(baseURL: URL(string: "http://[::1]:8765")!).isLoopback)
        XCTAssertFalse(WebMediaDLLoopbackClient(baseURL: URL(string: "http://example.com:8765")!).isLoopback)
        let client = WebMediaDLLoopbackClient()
        let jobId = UUID()
        XCTAssertTrue(client.healthRequest().url?.path.hasSuffix("/health") ?? false)
        XCTAssertFalse(client.healthRequest().url?.absoluteString.contains("/v1/") ?? true)
        XCTAssertNil(client.healthRequest().value(forHTTPHeaderField: "Authorization"))
        try await client.requireHealthyWorker(fetch: { _ in
            (200, Data("{\"status\":\"ok\",\"product\":\"WebMedia DL\"}".utf8))
        })
        do {
            try await client.requireHealthyWorker(fetch: { _ in (503, Data()) })
            XCTFail("unhealthy loopback worker must fail closed")
        } catch let error as WebMediaDLDomainError {
            XCTAssertTrue(error.message.contains("HTTP 503"))
        }
        do {
            try await client.requireHealthyWorker(fetch: { _ in
                (200, Data("{\"status\":\"nope\"}".utf8))
            })
            XCTFail("non-ok health JSON must fail closed")
        } catch let error as WebMediaDLDomainError {
            XCTAssertTrue(error.message.contains("not ok"))
        }
        XCTAssertTrue(client.resumeQueueRequest().url?.absoluteString.contains("queue/resume") ?? false)
        XCTAssertTrue(client.queueStatusRequest().url?.absoluteString.contains("/v1/queue") ?? false)
        XCTAssertFalse(client.queueStatusRequest().url?.absoluteString.contains("pause") ?? true)
        XCTAssertFalse(client.queueStatusRequest().url?.absoluteString.contains("resume") ?? true)
        XCTAssertTrue(client.cancelRequest(jobId: jobId).url?.path.contains("cancel") ?? false)
        XCTAssertTrue(client.pauseJobRequest(jobId: jobId).url?.path.contains("pause") ?? false)
        XCTAssertTrue(client.resumeJobRequest(jobId: jobId).url?.path.contains("resume") ?? false)
        XCTAssertTrue(client.artifactsRequest().url?.path.contains("artifacts") ?? false)
        XCTAssertTrue(client.jobDetailRequest(jobId: jobId).url?.path.contains(jobId.uuidString) ?? false)
        XCTAssertTrue(
            client.artifactContentRequest(artifactId: "sha256:abc").url?.path.hasSuffix("/content") ?? false
        )
        let planned = try client.planRequest(locator: "https://example.com/a.mp4", surface: .macos)
        XCTAssertTrue(planned.url?.path.hasSuffix("/v1/plan") ?? false)
        XCTAssertEqual(planned.httpMethod, "POST")
        let planObject = try JSONSerialization.jsonObject(with: planned.httpBody ?? Data()) as? [String: Any]
        XCTAssertEqual(planObject?["locator"] as? String, "https://example.com/a.mp4")
        XCTAssertEqual(planObject?["surface"] as? String, "macos")
        XCTAssertEqual(planObject?["local_user_confirmed"] as? Bool, true)
        XCTAssertNil(planObject?["nativeCommand"])
        XCTAssertNil(planObject?["wait"])
        XCTAssertNil(planObject?["intake_kind"])
        let planBody = String(data: planned.httpBody ?? Data(), encoding: .utf8) ?? ""
        XCTAssertFalse(planBody.contains("nativeCommand"))
        XCTAssertFalse(planBody.contains("\"wait\""))
        XCTAssertFalse(planBody.contains("intake_kind"))
        XCTAssertTrue(client.doctorRequest().url?.path.hasSuffix("/v1/doctor") ?? false)
        let authed = WebMediaDLLoopbackClient(token: "loopback-token")
        let doctorRequest = authed.doctorRequest()
        XCTAssertEqual(doctorRequest.url?.path, "/v1/doctor")
        XCTAssertEqual(doctorRequest.httpMethod, "GET")
        XCTAssertEqual(doctorRequest.value(forHTTPHeaderField: "Authorization"), "Bearer loopback-token")
        XCTAssertNil(doctorRequest.value(forHTTPHeaderField: "X-WebMedia-Pairing"))
        XCTAssertNil(doctorRequest.value(forHTTPHeaderField: "X-WebMedia-Session"))
        let authedPlan = try authed.planRequest(locator: "https://example.com/a.mp4", surface: .macos)
        XCTAssertEqual(authedPlan.url?.path, "/v1/plan")
        XCTAssertEqual(authedPlan.httpMethod, "POST")
        XCTAssertEqual(authedPlan.value(forHTTPHeaderField: "Authorization"), "Bearer loopback-token")
        XCTAssertNil(authedPlan.value(forHTTPHeaderField: "X-WebMedia-Pairing"))
        let pairBody = String(data: try client.pairRequest().httpBody ?? Data(), encoding: .utf8) ?? ""
        XCTAssertTrue(pairBody.contains("personal-restricted"))
        let wrap = try client.envelopeWrapRequest(
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
        XCTAssertEqual(
            try WebMediaDLLoopbackClient.requireHTTPSuccess(status: 200, body: Data("ok".utf8)),
            "HTTP 200 ok"
        )
        do {
            _ = try WebMediaDLLoopbackClient.requireHTTPSuccess(status: 401, body: Data("nope".utf8))
            XCTFail("non-2xx loopback responses must fail closed")
        } catch let error as WebMediaDLDomainError {
            XCTAssertTrue(error.message.contains("HTTP 401"))
        }
        XCTAssertEqual(
            try WebMediaDLLoopbackClient.requireHistoryEntries(status: 200, body: Data("[]".utf8)).count,
            0
        )
        do {
            _ = try WebMediaDLLoopbackClient.requireHistoryEntries(status: 401, body: Data("[]".utf8))
            XCTFail("history HTTP errors must fail closed")
        } catch let error as WebMediaDLDomainError {
            XCTAssertTrue(error.message.contains("HTTP 401"))
        }
        do {
            _ = try WebMediaDLLoopbackClient.requireHistoryEntries(status: 200, body: Data("nope".utf8))
            XCTFail("malformed history JSON must fail closed")
        } catch let error as WebMediaDLDomainError {
            XCTAssertTrue(error.message.contains("history JSON"))
        }
        let shown = await WebMediaDLLoopbackClient.displayedResponse {
            throw WebMediaDLDomainError("HTTP 401 nope")
        }
        XCTAssertEqual(shown, "HTTP 401 nope")
        let okBody = await WebMediaDLLoopbackClient.displayedResponse {
            try WebMediaDLLoopbackClient.requireHTTPSuccess(status: 200, body: Data("ok".utf8))
        }
        XCTAssertEqual(okBody, "HTTP 200 ok")
        try WebMediaDLLoopbackClient.requireJSONBody(try client.pairRequest())
        try WebMediaDLLoopbackClient.requireJSONBody(client.historyRequest())
        var missingJSON = try client.pairRequest()
        missingJSON.httpBody = nil
        do {
            try WebMediaDLLoopbackClient.requireJSONBody(missingJSON)
            XCTFail("JSON content-type without a body must fail closed")
        } catch let error as WebMediaDLDomainError {
            XCTAssertTrue(error.message.contains("request JSON"))
        }
        _ = try WebMediaDLLoopbackClient.jsonBody(["ok": true])
        do {
            _ = try WebMediaDLLoopbackClient.jsonBody(["when": Date()])
            XCTFail("non-JSON request payloads must fail closed")
        } catch let error as WebMediaDLDomainError {
            XCTAssertTrue(error.message.contains("request JSON"))
        }
        do {
            _ = try client.envelopeWrapRequest(
                pairingId: jobId,
                sessionKey: "session",
                payload: ["when": Date()]
            )
            XCTFail("non-JSON envelope payload must fail closed")
        } catch let error as WebMediaDLDomainError {
            XCTAssertTrue(error.message.contains("request JSON"))
        }
        XCTAssertFalse(
            WebMediaDLPairedMacEndpoint.isAllowedRelay(URL(string: "http://example.com:8765")!)
        )
        XCTAssertTrue(
            WebMediaDLPairedMacEndpoint.isAllowedRelay(URL(string: "http://192.168.1.9:8766")!)
        )
        XCTAssertTrue(
            WebMediaDLPairedMacEndpoint.isAllowedRelay(URL(string: "http://127.0.0.1:8766")!)
        )
        XCTAssertFalse(
            WebMediaDLPairedMacEndpoint.isAllowedRelay(URL(string: "https://192.168.1.9:8766")!)
        )
        XCTAssertFalse(
            WebMediaDLPairedMacEndpoint.isAllowedRelay(URL(string: "http://10.0.0.1.example.com:8766")!)
        )
        let suiteName = "webmedia-dl.tests.\(UUID().uuidString)"
        let suite = UserDefaults(suiteName: suiteName)!
        XCTAssertTrue(
            WebMediaDLPairedMacEndpoint.saveRelay(URL(string: "http://10.0.0.2:8766")!, defaults: suite)
        )
        XCTAssertFalse(
            WebMediaDLPairedMacEndpoint.saveRelay(URL(string: "http://example.com:8765")!, defaults: suite)
        )
        let pairing = UUID()
        let endpoint = WebMediaDLPairedMacEndpoint.load(
            pairingId: pairing,
            sessionKey: "sess",
            token: "tok",
            defaults: suite
        )
        XCTAssertEqual(endpoint?.relayURL.host, "10.0.0.2")
        XCTAssertNil(
            WebMediaDLPairedMacEndpoint.load(
                pairingId: pairing,
                sessionKey: "sess",
                defaults: UserDefaults(suiteName: UUID().uuidString)!
            )
        )
        let request = try endpoint!.submitRequest(locator: "https://example.com/a.mp4", surface: .ios)
        XCTAssertEqual(request.url?.host, "10.0.0.2")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-WebMedia-Pairing"), pairing.uuidString)
        XCTAssertEqual(endpoint!.historyRequest().url?.host, "10.0.0.2")
        XCTAssertTrue(endpoint!.pauseQueueRequest().url?.path.contains("queue/pause") ?? false)
        XCTAssertTrue(endpoint!.queueStatusRequest().url?.path.hasSuffix("/queue") ?? false)
        XCTAssertEqual(endpoint!.queueStatusRequest().url?.host, "10.0.0.2")
        XCTAssertEqual(endpoint!.cancelRequest(jobId: pairing).url?.host, "10.0.0.2")
        XCTAssertEqual(endpoint!.pauseJobRequest(jobId: pairing).url?.host, "10.0.0.2")
        XCTAssertEqual(endpoint!.resumeJobRequest(jobId: pairing).url?.host, "10.0.0.2")
        XCTAssertTrue(
            endpoint!.jobDetailRequest(jobId: pairing).url?.path.contains(pairing.uuidString) ?? false
        )
        XCTAssertTrue(
            endpoint!.artifactContentRequest(artifactId: "sha256:abc").url?.path.hasSuffix("/content") ?? false
        )
        let endpointPlan = try endpoint!.planRequest(
            locator: "https://example.com/a.mp4",
            surface: .ios
        )
        XCTAssertEqual(endpointPlan.url?.host, "10.0.0.2")
        XCTAssertEqual(endpointPlan.url?.path, "/v1/plan")
        XCTAssertEqual(endpointPlan.httpMethod, "POST")
        XCTAssertEqual(endpointPlan.value(forHTTPHeaderField: "X-WebMedia-Pairing"), pairing.uuidString)
        XCTAssertEqual(endpointPlan.value(forHTTPHeaderField: "X-WebMedia-Session"), "sess")
        XCTAssertEqual(endpointPlan.value(forHTTPHeaderField: "Authorization"), "Bearer tok")
        let endpointPlanObject = try JSONSerialization.jsonObject(
            with: endpointPlan.httpBody ?? Data()
        ) as? [String: Any]
        XCTAssertEqual(endpointPlanObject?["locator"] as? String, "https://example.com/a.mp4")
        XCTAssertEqual(endpointPlanObject?["surface"] as? String, "ios")
        XCTAssertEqual(endpointPlanObject?["local_user_confirmed"] as? Bool, true)
        XCTAssertEqual(endpointPlanObject?["pairing_id"] as? String, pairing.uuidString)
        XCTAssertEqual(endpointPlanObject?["session_key"] as? String, "sess")
        XCTAssertNil(endpointPlanObject?["nativeCommand"])
        XCTAssertNil(endpointPlanObject?["wait"])
        XCTAssertNil(endpointPlanObject?["intake_kind"])
        let endpointPlanBody = String(data: endpointPlan.httpBody ?? Data(), encoding: .utf8) ?? ""
        XCTAssertTrue(endpointPlanBody.contains("local_user_confirmed"))
        XCTAssertFalse(endpointPlanBody.contains("nativeCommand"))
        XCTAssertFalse(endpointPlanBody.contains("\"wait\""))
        XCTAssertFalse(endpointPlanBody.contains("intake_kind"))
        let endpointDoctor = endpoint!.doctorRequest()
        XCTAssertEqual(endpointDoctor.url?.host, "10.0.0.2")
        XCTAssertEqual(endpointDoctor.url?.path, "/v1/doctor")
        XCTAssertEqual(endpointDoctor.httpMethod, "GET")
        XCTAssertEqual(endpointDoctor.value(forHTTPHeaderField: "X-WebMedia-Pairing"), pairing.uuidString)
        XCTAssertEqual(endpointDoctor.value(forHTTPHeaderField: "X-WebMedia-Session"), "sess")
        XCTAssertEqual(endpointDoctor.value(forHTTPHeaderField: "Authorization"), "Bearer tok")
        let remapped = try endpoint!.submitRequest(
            locator: "https://example.com/a.mp4",
            surface: .ios,
            destinationKind: "files_app",
            destinationPath: "/var/mobile/Containers/Data/clip",
            approvedRoots: ["/var/mobile/Containers/Data/clip"],
            bookmarkData: Data("phone".utf8)
        )
        let remappedBody = String(data: remapped.httpBody ?? Data(), encoding: .utf8) ?? ""
        XCTAssertTrue(remappedBody.contains("staging_only"))
        XCTAssertFalse(remappedBody.contains("files_app"))
        XCTAssertFalse(remappedBody.contains("/var/mobile"))
        let macFiles = try endpoint!.submitRequest(
            locator: "https://example.com/a.mp4",
            surface: .macos,
            destinationKind: "files_app",
            destinationPath: "/Users/me/Movies",
            approvedRoots: ["/Users/me/Movies"],
            bookmarkData: Data("mac".utf8)
        )
        let macFilesBody = String(data: macFiles.httpBody ?? Data(), encoding: .utf8) ?? ""
        XCTAssertTrue(macFilesBody.contains("files_app"))
        XCTAssertEqual(
            WebMediaDLMacWorkerProcess.serveArguments(dataDir: "/tmp/webmedia-dl"),
            ["serve", "--host", "127.0.0.1", "--port", "8765", "--data-dir", "/tmp/webmedia-dl"]
        )
        XCTAssertEqual(WebMediaDLMacWorkerProcess.loopbackHost, "127.0.0.1")
        XCTAssertNil(WebMediaDLMacWorkerProcess.executableURL(pathEnvironment: ""))
        let spawnProbe = WebMediaDLWorkerStartProbe()
        let spawned = try await WebMediaDLMacWorkerSupervision.startOrClaimExisting(
            start: {
                let process = NSObject()
                spawnProbe.process = process
                return WebMediaDLUncheckedBox(process)
            },
            health: { XCTFail("spawned worker must not probe health") }
        )
        if case .started(let process) = spawned {
            XCTAssertTrue(process === spawnProbe.process)
        } else {
            XCTFail("successful spawn must start the worker")
        }
        let claimed = try await WebMediaDLMacWorkerSupervision.startOrClaimExisting(
            start: { throw WebMediaDLDomainError("missing binary") },
            health: { }
        )
        if case .claimedExisting(let spawnError) = claimed {
            XCTAssertTrue(spawnError.contains("missing binary"))
        } else {
            XCTFail("healthy existing loopback must be claimed")
        }
        do {
            _ = try await WebMediaDLMacWorkerSupervision.startOrClaimExisting(
                start: { throw WebMediaDLDomainError("missing binary") },
                health: { throw WebMediaDLDomainError("not ok") }
            )
            XCTFail("unhealthy existing worker must keep the spawn error")
        } catch let error as WebMediaDLDomainError {
            XCTAssertTrue(error.message.contains("missing binary"))
        }
        do {
            _ = try await WebMediaDLCompleteClientControl.perform(
                .pauseQueue,
                defaults: UserDefaults(suiteName: UUID().uuidString)!
            )
            XCTFail("complete-client pause without pairing must fail closed")
        } catch WebMediaDLHttpDirect.TransferError.pairingRequired {
            ()
        }
        do {
            _ = try await WebMediaDLCompleteClientControl.perform(
                .history,
                defaults: UserDefaults(suiteName: UUID().uuidString)!
            )
            XCTFail("complete-client history without pairing must fail closed")
        } catch WebMediaDLHttpDirect.TransferError.pairingRequired {
            ()
        }
        do {
            _ = try await WebMediaDLPairedMacSubmit.plan(
                locator: "https://example.com/a.mp4",
                surface: .ios,
                defaults: UserDefaults(suiteName: UUID().uuidString)!
            )
            XCTFail("complete-client plan without pairing must fail closed")
        } catch WebMediaDLHttpDirect.TransferError.pairingRequired {
            ()
        }
        do {
            _ = try await WebMediaDLPairedMacSubmit.doctor(
                defaults: UserDefaults(suiteName: UUID().uuidString)!
            )
            XCTFail("complete-client doctor without pairing must fail closed")
        } catch WebMediaDLHttpDirect.TransferError.pairingRequired {
            ()
        }
        do {
            _ = try await WebMediaDLCompleteClientControl.perform(.cancel, jobId: "nope")
            XCTFail("complete-client cancel without a job UUID must fail closed")
        } catch WebMediaDLCompanionError.jobIdRequired {
            ()
        }
        do {
            _ = try await WebMediaDLCompleteClientControl.perform("not-a-kind")
            XCTFail("unknown complete-client control must fail closed")
        } catch let error as WebMediaDLDomainError {
            XCTAssertTrue(error.message.contains("unknown complete-client control"))
        }
        XCTAssertEqual(WebMediaDLHistoryEntry.summary([]), "No jobs yet.")
        XCTAssertEqual(
            WebMediaDLHistoryEntry.summary([
                WebMediaDLHistoryEntry(jobId: pairing, state: "completed"),
            ]),
            "\(pairing.uuidString.prefix(8)) completed"
        )
        do {
            _ = try await WebMediaDLCompleteClientControl.perform(.jobDetail, jobId: "nope")
            XCTFail("complete-client job detail without a job UUID must fail closed")
        } catch WebMediaDLCompanionError.jobIdRequired {
            ()
        }
        do {
            _ = try await WebMediaDLCompleteClientControl.perform(
                .jobDetail,
                jobId: pairing.uuidString,
                defaults: UserDefaults(suiteName: UUID().uuidString)!
            )
            XCTFail("complete-client job detail without pairing must fail closed")
        } catch WebMediaDLHttpDirect.TransferError.pairingRequired {
            ()
        }
        let controlProbe = WebMediaDLCompleteClientControlProbe()
        let paused = try await WebMediaDLCompleteClientControl.perform(.pauseQueue) { kind, id in
            controlProbe.kind  = kind
            controlProbe.jobId = id
            controlProbe.sent += 1
            return "paused"
        }
        XCTAssertEqual(paused, "paused")
        XCTAssertEqual(controlProbe.kind, .pauseQueue)
        XCTAssertNil(controlProbe.jobId)
        XCTAssertEqual(controlProbe.sent, 1)
        let controlJob = UUID()
        let cancelled = try await WebMediaDLCompleteClientControl.perform(
            .cancel,
            jobId: controlJob.uuidString
        ) { kind, id in
            controlProbe.kind  = kind
            controlProbe.jobId = id
            controlProbe.sent += 1
            return "cancelled"
        }
        XCTAssertEqual(cancelled, "cancelled")
        XCTAssertEqual(controlProbe.kind, .cancel)
        XCTAssertEqual(controlProbe.jobId, controlJob)
        XCTAssertEqual(controlProbe.sent, 2)
        do {
            _ = try await WebMediaDLCompleteClientControl.perform(.cancel, jobId: "nope") { _, _ in
                controlProbe.sent += 1
                return "nope"
            }
            XCTFail("injectable send must not run without a job UUID")
        } catch WebMediaDLCompanionError.jobIdRequired {
            XCTAssertEqual(controlProbe.sent, 2)
        }
        do {
            _ = try await WebMediaDLCompleteClientControl.perform("not-a-kind") { _, _ in
                controlProbe.sent += 1
                return "nope"
            }
            XCTFail("injectable send must not run for unknown complete-client control")
        } catch let error as WebMediaDLDomainError {
            XCTAssertTrue(error.message.contains("unknown complete-client control"))
            XCTAssertEqual(controlProbe.sent, 2)
        }
        do {
            _ = try await WebMediaDLCompleteClientControl.perform(.jobDetail, jobId: "nope") { _, _ in
                controlProbe.sent += 1
                return "nope"
            }
            XCTFail("injectable send must not run job detail without a job UUID")
        } catch WebMediaDLCompanionError.jobIdRequired {
            XCTAssertEqual(controlProbe.sent, 2)
        }
        let inspected = try await WebMediaDLCompleteClientControl.perform(
            .jobDetail,
            jobId: controlJob.uuidString
        ) { kind, id in
            controlProbe.kind  = kind
            controlProbe.jobId = id
            controlProbe.sent += 1
            return "job"
        }
        XCTAssertEqual(inspected, "job")
        XCTAssertEqual(controlProbe.kind, .jobDetail)
        XCTAssertEqual(controlProbe.jobId, controlJob)
        XCTAssertEqual(controlProbe.sent, 3)
        let listed = try await WebMediaDLCompleteClientControl.perform(.history) { kind, id in
            controlProbe.kind  = kind
            controlProbe.jobId = id
            controlProbe.sent += 1
            return WebMediaDLHistoryEntry.summary([])
        }
        XCTAssertEqual(listed, "No jobs yet.")
        XCTAssertEqual(controlProbe.kind, .history)
        XCTAssertNil(controlProbe.jobId)
        XCTAssertEqual(controlProbe.sent, 4)
        do {
            _ = try await WebMediaDLPairedMacSubmit.pullToFiles(
                jobId: pairing,
                bookmark: WebMediaDLSecurityScopedBookmark(path: "/tmp"),
                defaults: UserDefaults(suiteName: UUID().uuidString)!
            )
            XCTFail("pull without pairing must fail closed")
        } catch WebMediaDLHttpDirect.TransferError.pairingRequired {
            ()
        }
        let forwarded = try WebMediaDLMacWorkerRelay.forwardToLoopback(request)
        XCTAssertEqual(forwarded.url?.host, "127.0.0.1")
        XCTAssertEqual(forwarded.url?.port, 8765)
        XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Bearer tok")
        XCTAssertNil(forwarded.value(forHTTPHeaderField: "Authorization"))
        XCTAssertEqual(forwarded.value(forHTTPHeaderField: "X-WebMedia-Pairing"), pairing.uuidString)
        var companion = URLRequest(url: URL(string: "http://192.168.1.9:8766/v1/companion")!)
        companion.httpMethod = "POST"
        companion.setValue("Bearer stolen", forHTTPHeaderField: "Authorization")
        companion.setValue("stolen", forHTTPHeaderField: "X-WebMedia-Token")
        companion.setValue(pairing.uuidString, forHTTPHeaderField: "X-WebMedia-Pairing")
        companion.setValue("sess", forHTTPHeaderField: "X-WebMedia-Session")
        let injected = try WebMediaDLMacWorkerRelay.forwardToLoopback(
            companion,
            loopbackToken: "mac-loopback"
        )
        XCTAssertEqual(injected.value(forHTTPHeaderField: "Authorization"), "Bearer mac-loopback")
        XCTAssertNil(injected.value(forHTTPHeaderField: "X-WebMedia-Token"))
        XCTAssertEqual(injected.url?.host, "127.0.0.1")
        var confirm = URLRequest(url: URL(string: "http://192.168.1.9:8766/v1/pair/confirm")!)
        confirm.httpMethod = "POST"
        confirm.setValue("Bearer stolen", forHTTPHeaderField: "Authorization")
        confirm.setValue(pairing.uuidString, forHTTPHeaderField: "X-WebMedia-Pairing")
        confirm.setValue("sess", forHTTPHeaderField: "X-WebMedia-Session")
        XCTAssertThrowsError(
            try WebMediaDLMacWorkerRelay.forwardToLoopback(confirm, loopbackToken: "mac-loopback")
        ) { error in
            XCTAssertEqual(error as? WebMediaDLMacWorkerRelayError, .macOnlyEndpoint)
        }
        var poisoned = request
        poisoned.httpBody = try JSONSerialization.data(withJSONObject: ["nativeCommand": "yt-dlp"])
        XCTAssertThrowsError(try WebMediaDLMacWorkerRelay.forwardToLoopback(poisoned))
        var subprocess = request
        subprocess.httpBody = try JSONSerialization.data(withJSONObject: ["subprocessWorker": true])
        XCTAssertThrowsError(try WebMediaDLMacWorkerRelay.forwardToLoopback(subprocess))
        var malformed = request
        malformed.setValue("application/json", forHTTPHeaderField: "Content-Type")
        malformed.httpBody = Data("{".utf8)
        XCTAssertThrowsError(try WebMediaDLMacWorkerRelay.forwardToLoopback(malformed)) { error in
            XCTAssertEqual(error as? WebMediaDLMacWorkerRelayError, .invalidJSON)
        }
        var jsonArray = request
        jsonArray.setValue("application/json", forHTTPHeaderField: "Content-Type")
        jsonArray.httpBody = Data("[]".utf8)
        XCTAssertThrowsError(try WebMediaDLMacWorkerRelay.forwardToLoopback(jsonArray)) { error in
            XCTAssertEqual(error as? WebMediaDLMacWorkerRelayError, .invalidJSON)
        }
        XCTAssertFalse(WebMediaDLMacRelayServer.isAllowedBindHost("example.com"))
        XCTAssertThrowsError(try WebMediaDLMacRelayServer.requireAllowedBind(host: "example.com"))
        XCTAssertTrue(WebMediaDLMacRelayServer.isAllowedBindHost("127.0.0.1"))
        XCTAssertTrue(WebMediaDLMacRelayServer.isAllowedBindHost("0.0.0.0"))
        XCTAssertTrue(WebMediaDLMacRelayServer.isAllowedPeer("192.168.1.9"))
        XCTAssertFalse(WebMediaDLMacRelayServer.isAllowedPeer("8.8.8.8"))
        XCTAssertFalse(WebMediaDLMacRelayServer.isAllowedPeer(""))
        let paste = WebMediaDLMacRelayServer.clientPasteURLs(
            port: 8766,
            lanAddresses: ["192.168.1.9", "8.8.8.8", "127.0.0.1"]
        )
        XCTAssertEqual(paste.map(\.absoluteString), [
            "http://127.0.0.1:8766",
            "http://192.168.1.9:8766",
        ])
        let raw = Data("POST /v1/jobs HTTP/1.1\r\nHost: 192.168.1.9:8766\r\nContent-Length: 2\r\n\r\n{}".utf8)
        let parsed = WebMediaDLMacRelayHTTP.parseRequest(raw)
        XCTAssertEqual(parsed?.method, "POST")
        XCTAssertEqual(parsed?.target, "/v1/jobs")
        XCTAssertEqual(String(data: parsed?.body ?? Data(), encoding: .utf8), "{}")
        XCTAssertNil(
            WebMediaDLMacRelayHTTP.parseRequest(
                Data("POST /v1/jobs HTTP/1.1\r\nContent-Length: 10\r\n\r\n{}".utf8)
            )
        )
        XCTAssertEqual(
            WebMediaDLMacRelayHTTP.maxBytes(for: "/v1/jobs"),
            WebMediaDLMacRelayHTTP.maxRequestBytes
        )
        XCTAssertEqual(
            WebMediaDLMacRelayHTTP.maxBytes(for: "/v1/staging?x=1"),
            WebMediaDLMacRelayHTTP.maxStagingBytes
        )
        XCTAssertNil(
            WebMediaDLMacRelayHTTP.parseRequest(
                Data("POST /v1/jobs HTTP/1.1\r\nContent-Length: 1048577\r\n\r\n".utf8)
            )
        )
        let stagingParsed = WebMediaDLMacRelayHTTP.parseRequest(
            Data("POST /v1/staging HTTP/1.1\r\nContent-Length: 2\r\n\r\nab".utf8)
        )
        XCTAssertEqual(stagingParsed?.target, "/v1/staging")
        XCTAssertEqual(stagingParsed?.body, Data("ab".utf8))
        let stagedReq = endpoint!.stageRequest(digest: "aa", filename: "clip.mp4", size: 4)
        XCTAssertTrue(stagedReq.url?.path.hasSuffix("/v1/staging") == true)
        XCTAssertEqual(stagedReq.value(forHTTPHeaderField: "X-WebMedia-Digest"), "aa")
        XCTAssertEqual(stagedReq.value(forHTTPHeaderField: "X-WebMedia-Filename"), "clip.mp4")
        #if canImport(CryptoKit)
        XCTAssertEqual(
            WebMediaDLPairedMacEndpoint.sha256Hex(Data("hi".utf8)),
            "8f434346648f6b96df89dda901c5176b10a6d83961dd3c1ac88b59b2dc327aa4"
        )
        #endif
        do {
            _ = try await WebMediaDLPairedMacSubmit.submitDrop(
                localPath: "/no/such/webmedia-dl-drop",
                surface: .ios,
                defaults: UserDefaults(suiteName: UUID().uuidString)!
            )
            XCTFail("drop without pairing must fail closed")
        } catch WebMediaDLHttpDirect.TransferError.pairingRequired {
            ()
        }
        let rebuilt = try WebMediaDLMacRelayServer.urlRequest(
            from: parsed!,
            fallback: URL(string: "http://127.0.0.1:8766")!
        )
        XCTAssertEqual(rebuilt.url?.host, "192.168.1.9")
        XCTAssertEqual(rebuilt.httpMethod, "POST")
        #if canImport(Network)
        let server = try await WebMediaDLMacRelayServer.start(
            bindHost: "127.0.0.1",
            port: 0,
            localOnly: true,
            lanAddresses: [],
            transport: { request in
                XCTAssertEqual(request.url?.host, "127.0.0.1")
                XCTAssertEqual(request.url?.port, 8765)
                let body = Data(
                    #"{"job":{"job_id":"11111111-1111-1111-1111-111111111111"}}"#.utf8
                )
                let response = HTTPURLResponse(
                    url: request.url!,
                    statusCode: 200,
                    httpVersion: "HTTP/1.1",
                    headerFields: ["Content-Type": "application/json"]
                )!
                return (body, response)
            }
        )
        defer { server.stop() }
        var job = URLRequest(url: URL(string: "\(server.advertisedURL.absoluteString)/v1/jobs")!)
        job.httpMethod = "POST"
        job.setValue("application/json", forHTTPHeaderField: "Content-Type")
        job.httpBody = try JSONSerialization.data(withJSONObject: [
            "locator": "https://example.com/a.mp4",
            "surface": "ios",
        ])
        let (data, response) = try await URLSession.shared.data(for: job)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        XCTAssertTrue(
            String(data: data, encoding: .utf8)?
                .contains("11111111-1111-1111-1111-111111111111") == true
        )
        var poisonedRelay = URLRequest(url: URL(string: "\(server.advertisedURL.absoluteString)/v1/jobs")!)
        poisonedRelay.httpMethod = "POST"
        poisonedRelay.setValue("application/json", forHTTPHeaderField: "Content-Type")
        poisonedRelay.httpBody = try JSONSerialization.data(withJSONObject: [
            "nativeCommand": "yt-dlp",
        ])
        let (badBody, badResponse) = try await URLSession.shared.data(for: poisonedRelay)
        XCTAssertEqual((badResponse as? HTTPURLResponse)?.statusCode, 400)
        XCTAssertTrue(String(data: badBody, encoding: .utf8)?.contains("nativeCommand") == true)
        #endif
        suite.removePersistentDomain(forName: suiteName)
    }

    func testWorkerCredentialsLoadFromAppGroupDefaults() throws {
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
        XCTAssertTrue(
            WebMediaDLPairedMacEndpoint.saveRelay(
                URL(string: "http://192.168.1.9:8766")!,
                defaults: defaults
            )
        )
        let endpoint = try WebMediaDLPairedMacSubmit.loadEndpoint(
            credentials: client,
            defaults: defaults
        )
        XCTAssertEqual(endpoint.token, "")
        XCTAssertNil(try endpoint.submitRequest(locator: "https://example.com/a.mp4", surface: .ios)
            .value(forHTTPHeaderField: "Authorization"))
        XCTAssertNil(try endpoint.planRequest(locator: "https://example.com/a.mp4", surface: .ios)
            .value(forHTTPHeaderField: "Authorization"))
        XCTAssertNil(endpoint.doctorRequest().value(forHTTPHeaderField: "Authorization"))
        XCTAssertEqual(try endpoint.planRequest(locator: "https://example.com/a.mp4", surface: .ios)
            .url?.path, "/v1/plan")
        XCTAssertEqual(endpoint.doctorRequest().url?.path, "/v1/doctor")
        XCTAssertEqual(
            try endpoint.submitRequest(locator: "https://example.com/a.mp4", surface: .ios)
                .value(forHTTPHeaderField: "X-WebMedia-Session"),
            "sess"
        )
        defaults.removePersistentDomain(forName: suite)
    }

    func testContinuityFallsBackAndKeepsNativeCommandNull() throws {
        let bridge = WebMediaDLContinuityBridge()
        XCTAssertEqual(bridge.message(kind: "not-a-kind").kind, .status)
        XCTAssertEqual(
            bridge.controlMessage(kind: "capture", locator: "https://example.com/a.mp4")["kind"],
            "capture"
        )
        XCTAssertTrue(WebMediaDLContinuityBridge.allowedKinds.contains("pause_job"))
        let sealed = try bridge.sealedCompanionRequest(
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
        defer { UserDefaults.standard.removeObject(forKey: WebMediaDLCompanionRelay.defaultsKey) }
        var queued = WebMediaDLQueuedCompanionTransport()
        try await queued.send(
            WebMediaDLCompanionMessage(kind: .cancel, jobId: UUID().uuidString, surface: .tvos)
        )
        XCTAssertEqual(queued.relay.pending.count, 1)
        XCTAssertEqual(queued.relay.pending.first?.surface, .tvos)
        do {
            try await queued.send(WebMediaDLCompanionMessage(kind: .cancel, surface: .tvos))
            XCTFail("cancel without a job UUID must fail closed")
        } catch WebMediaDLCompanionError.jobIdRequired {
            ()
        }

        let lan = WebMediaDLLocalNetworkCompanionTransport()
        do {
            try await lan.send(WebMediaDLCompanionMessage(kind: .status, surface: .tvos))
            XCTFail("tvOS LAN send without a saved Mac relay must fail closed")
        } catch WebMediaDLHttpDirect.TransferError.pairingRequired {
            XCTAssertEqual(lan.fallback.relay.pending.last?.kind, .status)
        }

        let transport = WebMediaDLWatchConnectivityTransport()
        transport.sendResponse(["body": "HTTP 200 {\"job_id\":\"11111111-1111-1111-1111-111111111111\"}"])
        XCTAssertEqual(
            WebMediaDLLoopbackClient.jobId(from: transport.lastResponse ?? ""),
            UUID(uuidString: "11111111-1111-1111-1111-111111111111")
        )
        transport.activateSession()
        let queuedMessage = WebMediaDLCompanionMessage(
            kind: .capture,
            locator: "https://cdn.example.com/a.mp4",
            surface: .watchos
        )
        try await transport.send(queuedMessage)
        #if canImport(WatchConnectivity)
        if !WCSession.isSupported() {
            XCTAssertEqual(transport.fallback.relay.pending.last?.kind, .capture)
        }
        #else
        XCTAssertEqual(transport.fallback.relay.pending.last?.kind, .capture)
        #endif

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
        let envelope = try JSONSerialization.data(withJSONObject: [
            "nonce": "aa",
            "ciphertext": "bb",
            "mac": "cc",
        ])
        let fields = try WebMediaDLMacCompanionForwarder.requireSealedEnvelope(envelope)
        XCTAssertEqual(fields.nonce, "aa")
        XCTAssertEqual(fields.ciphertext, "bb")
        XCTAssertEqual(fields.mac, "cc")
        do {
            _ = try WebMediaDLMacCompanionForwarder.requireSealedEnvelope(Data("{}".utf8))
            XCTFail("empty envelope fields must fail closed")
        } catch let error as WebMediaDLDomainError {
            XCTAssertTrue(error.message.contains("envelope JSON"))
        }
        do {
            _ = try WebMediaDLMacCompanionForwarder.requireSealedEnvelope(Data("nope".utf8))
            XCTFail("malformed envelope JSON must fail closed")
        } catch {
            ()
        }
        let probe = WebMediaDLWatchForwardProbe()
        let reply = try await WebMediaDLWatchCompanionForward.forward(
            WebMediaDLCompanionMessage(kind: .status, surface: .watchos)
        ) { message in
            probe.message = message
            return "mac-ok"
        }
        XCTAssertEqual(reply, "mac-ok")
        XCTAssertEqual(probe.message?.kind, .status)
        XCTAssertEqual(probe.message?.surface, .watchos)
        do {
            _ = try await WebMediaDLWatchCompanionForward.forward(
                WebMediaDLCompanionMessage(kind: .cancel, surface: .watchos)
            ) { _ in
                probe.sent += 1
                return "nope"
            }
            XCTFail("iPhone must not forward cancel without a job UUID")
        } catch WebMediaDLCompanionError.jobIdRequired {
            XCTAssertEqual(probe.sent, 0)
        }
        let controlId = UUID()
        XCTAssertEqual(try WebMediaDLCompanionJobControl.requireJobId(controlId.uuidString), controlId)
        do {
            _ = try WebMediaDLCompanionJobControl.requireJobId("nope")
            XCTFail("non-UUID job ids must fail closed")
        } catch WebMediaDLCompanionError.jobIdRequired {
            ()
        }
        for kind in [
            WebMediaDLCompanionKind.capture,
            .pause,
            .resume,
            .history,
            .status,
        ] {
            let message = try WebMediaDLCompanionControlMessage.make(kind: kind, surface: .watchos)
            XCTAssertEqual(message.kind, kind)
            XCTAssertNil(message.nativeCommand)
            XCTAssertFalse(message.subprocessWorker)
            XCTAssertEqual(message.queuedStatus, "Queued \(kind.rawValue) for Mac relay")
        }
        let controlJob = UUID().uuidString
        for kind in [WebMediaDLCompanionKind.cancel, .pauseJob, .resumeJob] {
            let message = try WebMediaDLCompanionControlMessage.make(
                kind: kind,
                jobId: controlJob,
                surface: .tvos
            )
            XCTAssertEqual(message.kind, kind)
            XCTAssertEqual(message.surface, .tvos)
            XCTAssertNil(message.nativeCommand)
        }
        do {
            _ = try WebMediaDLCompanionControlMessage.make(kind: .cancel, surface: .watchos)
            XCTFail("control intents must not queue cancel without a job UUID")
        } catch WebMediaDLCompanionError.jobIdRequired {
            ()
        }
        do {
            _ = try WebMediaDLCompanionControlMessage.make(kind: "not-a-kind", surface: .tvos)
            XCTFail("unknown companion kinds must fail closed")
        } catch let error as WebMediaDLDomainError {
            XCTAssertTrue(error.message.contains("unknown companion"))
        }
    }

    func testDomainInvariantsFailClosed() throws {
        XCTAssertThrowsError(
            try WebMediaDLMediaSource(
                kind: .url,
                locator: "https://cdn.example.com/a.mp4",
                localPath: "/tmp/a.mp4",
                surface: .ios,
                policyProfileId: "personal-restricted"
            )
        )
        XCTAssertThrowsError(
            try WebMediaDLPolicyProfile(
                profileId: "bad",
                displayName: "bad",
                allowedCapabilities: ["acquire.http"],
                drmCircumvention: true
            )
        )
        XCTAssertThrowsError(
            try WebMediaDLPolicyProfile(
                profileId: "bad",
                displayName: "bad",
                allowedCapabilities: ["acquire.http"],
                telemetryDefault: true
            )
        )
        XCTAssertThrowsError(
            try WebMediaDLAcquisitionStrategy(
                strategyId: "http-direct",
                providerId: "http-direct",
                capabilityId: "acquire.http",
                extraArgs: ["--user"]
            )
        )
        XCTAssertThrowsError(
            try WebMediaDLArtifact(
                artifactId: "Clip",
                role: .source,
                sha256: "abc",
                byteSize: 1,
                mediaKind: .video,
                storageRelpath: "a.mp4",
                provenance: ["title": "Clip"]
            )
        )
        XCTAssertThrowsError(
            try WebMediaDLValidationResult(
                jobId: UUID(),
                targetArtifactId: "sha256:abc",
                gateId: "validate.hash",
                status: .pass,
                message: "planned",
                planned: true
            )
        )
        XCTAssertThrowsError(
            try WebMediaDLArtifact(
                artifactId: "plan:source",
                role: .source,
                sha256: "abc",
                byteSize: 1,
                mediaKind: .video,
                storageRelpath: "a.mp4"
            )
        )
        let source = try WebMediaDLArtifact(
            artifactId: "sha256:abc",
            role: .source,
            sha256: "abc",
            byteSize: 4,
            mediaKind: .image,
            storageRelpath: "a.png"
        )
        XCTAssertTrue(source.immutable)
        XCTAssertTrue(WebMediaDLCapabilityRegistry.allows(.acquireHTTP, on: .ios))
        XCTAssertFalse(WebMediaDLCapabilityRegistry.allows(.acquireYtdlp, on: .ios))
        XCTAssertFalse(WebMediaDLCapabilityRegistry.allows(.liveRecord, on: .ios))
        XCTAssertTrue(WebMediaDLCapabilityRegistry.allows(.acquireYtdlp, on: .macos))
        let watch = WebMediaDLWorker(
            workerId: "watch",
            platform: .watchos,
            profileId: "watch-capture",
            capabilities: [],
            subprocessCapable: false
        )
        XCTAssertFalse(watch.subprocessCapable)
        XCTAssertThrowsError(
            try WebMediaDLExportIntent(
                destinationKind: .filesApp,
                destinationPath: "/tmp",
                approvedRoots: ["/tmp"]
            )
        )
        XCTAssertThrowsError(
            try WebMediaDLExportIntent(
                destinationKind: .photos,
                approvedRoots: []
            )
        )
        XCTAssertThrowsError(
            try WebMediaDLExportIntent(
                destinationKind: .filesApp,
                destinationPath: "/tmp/escape",
                approvedRoots: ["/tmp/movies"],
                securityScopedBookmark: "ZmFrZQ=="
            )
        )
        XCTAssertThrowsError(
            try WebMediaDLExportIntent(
                destinationKind: .filesApp,
                destinationPath: "/tmp/movies/../escape",
                approvedRoots: ["/tmp/movies"],
                securityScopedBookmark: "ZmFrZQ=="
            )
        )
        let nestedFiles = try WebMediaDLExportIntent(
            destinationKind: .filesApp,
            destinationPath: "/tmp/movies/inside",
            approvedRoots: ["/tmp/movies"],
            securityScopedBookmark: "ZmFrZQ=="
        )
        XCTAssertEqual(nestedFiles.securityScopedPath, "/tmp/movies/inside")
        XCTAssertThrowsError(
            try JSONDecoder().decode(
                WebMediaDLExportIntent.self,
                from: JSONSerialization.data(withJSONObject: [
                    "container_preference": "../../../../tmp/escape",
                ])
            )
        )
        XCTAssertThrowsError(
            try JSONDecoder().decode(
                WebMediaDLExportIntent.self,
                from: JSONSerialization.data(withJSONObject: [
                    "container_preference": "mkv; rm -rf /",
                ])
            )
        )
        let allowlistedContainer = try JSONDecoder().decode(
            WebMediaDLExportIntent.self,
            from: JSONSerialization.data(withJSONObject: [
                "container_preference": "mkv",
            ])
        )
        XCTAssertEqual(allowlistedContainer.containerPreference, "mkv")
        XCTAssertEqual(WebMediaDLExportIntent.safeContainerPattern, "^[A-Za-z0-9]{1,12}$")
        XCTAssertThrowsError(
            try JSONDecoder().decode(
                WebMediaDLMediaSource.self,
                from: JSONSerialization.data(withJSONObject: [
                    "kind": "url",
                    "locator": "https://cdn.example.com/a.mp4",
                    "local_path": "/tmp/a.mp4",
                    "surface": "ios",
                    "policy_profile_id": "personal-restricted",
                ])
            )
        )
        XCTAssertThrowsError(
            try JSONDecoder().decode(
                WebMediaDLPolicyProfile.self,
                from: JSONSerialization.data(withJSONObject: [
                    "profile_id": "bad",
                    "display_name": "bad",
                    "allowed_capabilities": ["acquire.http"],
                    "drm_circumvention": true,
                ])
            )
        )
        XCTAssertThrowsError(
            try JSONDecoder().decode(
                WebMediaDLPolicyProfile.self,
                from: JSONSerialization.data(withJSONObject: [
                    "profile_id": "bad",
                    "display_name": "bad",
                    "allowed_capabilities": ["acquire.http"],
                    "telemetry_default": true,
                ])
            )
        )
        XCTAssertThrowsError(
            try JSONDecoder().decode(
                WebMediaDLAcquisitionStrategy.self,
                from: JSONSerialization.data(withJSONObject: [
                    "strategy_id": "http-direct",
                    "provider_id": "http-direct",
                    "capability_id": "acquire.http",
                    "extra_args": ["--user"],
                ])
            )
        )
        XCTAssertThrowsError(
            try JSONDecoder().decode(
                WebMediaDLProviderManifest.self,
                from: JSONSerialization.data(withJSONObject: [
                    "provider_id": "ytdlp",
                    "display_name": "yt-dlp",
                    "capabilities": ["acquire.ytdlp"],
                    "license": "Unlicense",
                    "source_url": "https://example.com",
                    "install_automatic": true,
                ])
            )
        )
        let files = try WebMediaDLExportIntent(
            destinationKind: .filesApp,
            destinationPath: "/tmp/movies",
            includeOriginal: false,
            approvedRoots: ["/tmp/movies"],
            securityScopedBookmark: "ZmFrZQ=="
        )
        XCTAssertFalse(files.includeOriginal)
        XCTAssertEqual(files.securityScopedPath, "/tmp/movies")
        XCTAssertThrowsError(
            try WebMediaDLMediaCandidate(
                sourceId: UUID(),
                mediaKind: .video,
                identityKey: "Clip",
                titleDisplay: "Clip"
            )
        )
        XCTAssertThrowsError(
            try WebMediaDLProviderManifest(
                providerId: "ytdlp",
                displayName: "yt-dlp",
                capabilities: ["acquire.ytdlp"],
                license: "Unlicense",
                sourceUrl: "https://example.com",
                acceptsUserArgv: true
            )
        )
        let profile = try WebMediaDLPolicyProfile(
            profileId: "personal-restricted",
            displayName: "Restricted",
            allowedCapabilities: ["acquire.http"]
        )
        XCTAssertEqual(profile.networkSchemes, ["https"])
        XCTAssertEqual(profile.maxHtmlBytes, 2_000_000)
        XCTAssertEqual(WebMediaDLCapability.acquireHTTP.requiredEntitlements, [])
        let artifact = try WebMediaDLArtifact(
            artifactId: "sha256:def",
            role: .derivative,
            sha256: "def",
            byteSize: 2,
            mediaKind: .audio,
            storageRelpath: "a.m4a",
            container: "m4a",
            parentIds: ["sha256:abc"]
        )
        XCTAssertEqual(artifact.parentIds, ["sha256:abc"])
        XCTAssertEqual(artifact.container, "m4a")
        XCTAssertEqual(WebMediaDLLossClass.containerOnly.rawValue, "container_only")
        XCTAssertEqual(WebMediaDLArtifactRole.evidence.rawValue, "evidence")
        XCTAssertEqual(WebMediaDLJobState.accepted.rawValue, "accepted")
        let historyData = try JSONSerialization.data(withJSONObject: [[
            "job_id": UUID().uuidString,
            "state": "completed",
            "policy_profile_id": "personal-full",
            "worker_id": "mac",
            "created_at": "2026-08-18T00:00:00Z",
            "updated_at": "2026-08-18T00:00:00Z",
            "artifact_ids": [],
            "last_events": [],
            "partial": false,
            "failed_kinds": [],
        ]])
        let history = try WebMediaDLHistoryEntry.decodeList(from: historyData)
        XCTAssertEqual(history.first?.createdAt, "2026-08-18T00:00:00Z")
        XCTAssertNil(history.first?.source)
        let bookmarkJSON = try JSONSerialization.data(withJSONObject: [
            "resolved_path": "/tmp/movies",
            "stale": false,
        ])
        let decodedBookmark = try JSONDecoder().decode(
            WebMediaDLSecurityScopedBookmark.self,
            from: bookmarkJSON
        )
        XCTAssertEqual(decodedBookmark.path, "/tmp/movies")
        let clipboard = try JSONDecoder().decode(
            WebMediaDLClipboardIntake.self,
            from: Data("{\"text\":\"https://cdn.example.com/a.mp4\"}".utf8)
        )
        XCTAssertEqual(clipboard.locator, "https://cdn.example.com/a.mp4")
        let jobJSON: [String: Any] = [
            "source": [
                "kind": "url",
                "locator": "https://cdn.example.com/a.mp4",
                "surface": "ios",
                "policy_profile_id": "personal-restricted",
            ],
            "policy_profile_id": "personal-restricted",
            "worker_id": "iphone",
        ]
        let pipeline = try JSONDecoder().decode(
            WebMediaDLPipelineJob.self,
            from: JSONSerialization.data(withJSONObject: jobJSON)
        )
        XCTAssertEqual(pipeline.state, .accepted)
        XCTAssertEqual(pipeline.source.kind, .url)
        XCTAssertEqual(pipeline.intent.presetId, "original-sacred")
        let op = WebMediaDLOperation(
            operationId: "keep-original",
            opType: "copy",
            capabilityId: "process.copy",
            inputArtifactIds: ["sha256:abc"],
            outputRole: .source,
            lossClass: .none,
            validatorIds: ["validate.hash"]
        )
        let plan = WebMediaDLExportPlan(jobId: UUID(), operations: [op])
        XCTAssertEqual(plan.operations.count, 1)
        XCTAssertEqual(plan.operations.first?.operationId, "keep-original")
    }

    func testHttpDirectSavesClearMediaAndRefusesDrm() async throws {
        XCTAssertTrue(WebMediaDLHttpDirect.isOnDeviceTransfer("https://cdn.example.com/a.mp4"))
        XCTAssertFalse(WebMediaDLHttpDirect.isOnDeviceTransfer("http://cdn.example.com/a.mp4"))
        XCTAssertFalse(WebMediaDLHttpDirect.isOnDeviceTransfer("https://www.youtube.com/watch?v=1"))
        XCTAssertFalse(WebMediaDLHttpDirect.isOnDeviceTransfer("https://cdn.example.com/live.m3u8"))
        XCTAssertTrue(WebMediaDLHttpDirect.isDirectMediaURL("https://cdn.example.com/live.m3u8"))
        XCTAssertFalse(WebMediaDLHttpDirect.isDirectMediaURL("http://cdn.example.com/a.mp4"))
        XCTAssertFalse(WebMediaDLHttpDirect.isOnDeviceTransfer("file:///tmp/a.mp4"))
        XCTAssertFalse(WebMediaDLHttpDirect.isDirectMediaURL("javascript:foo.mp4"))
        XCTAssertFalse(WebMediaDLHttpDirect.isOnDeviceTransfer("https:///a.mp4"))
        XCTAssertNil(WebMediaDLHttpDirect.mediaURL(from: "https:///nohost"))
        XCTAssertNil(WebMediaDLHttpDirect.mediaURL(from: "https://"))
        XCTAssertNil(WebMediaDLHttpDirect.mediaURL(from: "data:text/plain,x"))
        XCTAssertNil(WebMediaDLHttpDirect.mediaURL(from: "file:///tmp/a.mp4"))
        XCTAssertNotNil(WebMediaDLHttpDirect.mediaURL(from: "https://cdn.example.com/a.mp4"))
        XCTAssertNotNil(WebMediaDLHttpDirect.mediaURL(from: "http://cdn.example.com/a.mp4"))
        XCTAssertNil(
            WebMediaDLHttpDirect.mediaURL(
                from: "http://cdn.example.com/a.mp4",
                schemes: WebMediaDLHttpDirect.transferSchemes
            )
        )
        XCTAssertEqual(WebMediaDLHttpDirect.transferSchemes, Set(["https"]))
        XCTAssertFalse(WebMediaDLHttpDirect.transferSessionConfiguration().httpShouldSetCookies)
        XCTAssertEqual(
            WebMediaDLHttpDirect.transferSessionConfiguration().httpCookieAcceptPolicy,
            .never
        )
        XCTAssertNil(WebMediaDLHttpDirect.transferSessionConfiguration().httpCookieStorage)
        let httpsMedia = URL(string: "https://cdn.example.com/a.mp4")!
        XCTAssertEqual(
            try WebMediaDLHttpDirect.redirectURL(
                from: httpsMedia,
                location: "https://cdn.example.com/b.mp4",
                hops: 1
            ).absoluteString,
            "https://cdn.example.com/b.mp4"
        )
        do {
            _ = try WebMediaDLHttpDirect.redirectURL(
                from: httpsMedia,
                location: "http://cdn.example.com/b.mp4",
                hops: 1
            )
            XCTFail("http redirects must not continue an on-device transfer")
        } catch WebMediaDLHttpDirect.TransferError.invalidLocator {
            ()
        }
        do {
            _ = try WebMediaDLHttpDirect.redirectURL(
                from: httpsMedia,
                location: "file:///tmp/a.mp4",
                hops: 1
            )
            XCTFail("file redirects must not continue an on-device transfer")
        } catch WebMediaDLHttpDirect.TransferError.invalidLocator {
            ()
        }
        do {
            _ = try WebMediaDLHttpDirect.redirectURL(
                from: httpsMedia,
                location: "https://cdn.example.com/b.mp4",
                hops: WebMediaDLHttpDirect.maxRedirects + 1
            )
            XCTFail("redirect hop overflow must fail closed")
        } catch WebMediaDLHttpDirect.TransferError.httpStatus(let code) {
            XCTAssertEqual(code, 310)
        }
        XCTAssertTrue(WebMediaDLHttpDirect.hlsKeyIsProtected("#EXT-X-KEY:METHOD=AES-128,URI=\"https://cdn.example.com/key\""))
        XCTAssertFalse(WebMediaDLHttpDirect.hlsKeyIsProtected("#EXT-X-KEY:METHOD=NONE"))
        XCTAssertFalse(WebMediaDLHttpDirect.drmSignals(in: "#EXT-X-KEY:METHOD=NONE").contains("ext-x-key"))
        XCTAssertTrue(
            WebMediaDLHttpDirect.hlsKeyIsProtected(
                "#EXT-X-KEY:METHOD=SAMPLE-AES,URI=\"skd://vendor/asset?METHOD=NONE\""
            )
        )
        XCTAssertTrue(
            WebMediaDLHttpDirect.hlsKeyIsProtected(
                "#EXT-X-KEY:URI=\"https://k.invalid/key?id=7&METHOD=NONE\",METHOD=AES-128"
            )
        )
        XCTAssertTrue(
            WebMediaDLHttpDirect.hlsKeyIsProtected(
                "#EXT-X-KEY:URI=\"https://k.invalid/key?METHOD=AES-128\",METHOD=NONE"
            )
        )
        XCTAssertEqual(
            WebMediaDLHttpDirect.hlsAttributeMap(
                "URI=\"https://k.invalid/key?METHOD=AES-128\",METHOD=NONE"
            )["METHOD"],
            "NONE"
        )
        XCTAssertEqual(
            WebMediaDLHttpDirect.hlsAttributeMap(
                "METHOD=AES-128,URI=\"https://k.invalid/key?METHOD=NONE\""
            )["METHOD"],
            "AES-128"
        )
        XCTAssertEqual(
            WebMediaDLHttpDirect.hlsAttributeMap("METHOD=AES-128,URI=\"k\",METHOD=NONE")["METHOD"],
            "AES-128"
        )
        XCTAssertTrue(
            WebMediaDLHttpDirect.parseHLSAttributes("METHOD=NONE,URI=\"k\",METHOD=AES-128")
                .duplicateKeys.contains("METHOD")
        )
        XCTAssertTrue(
            WebMediaDLHttpDirect.hlsKeyIsProtected(
                "#EXT-X-KEY:METHOD=AES-128,URI=\"k\",METHOD=NONE"
            )
        )
        XCTAssertTrue(
            WebMediaDLHttpDirect.hlsKeyIsProtected(
                "#EXT-X-KEY:METHOD=NONE,METHOD=AES-128"
            )
        )
        XCTAssertTrue(
            WebMediaDLHttpDirect.hlsKeyIsProtected(
                "#EXT-X-KEY:METHOD=NONE,KEYFORMAT=\"com.apple.fps\""
            )
        )
        XCTAssertTrue(
            WebMediaDLHttpDirect.hlsKeyIsProtected(
                "#EXT-X-KEY:METHOD=NONE,URI=\"https://lic.invalid/k\""
            )
        )
        XCTAssertEqual(
            WebMediaDLHttpDirect.suffix(
                url: URL(string: "https://cdn.example.com/photo.jpeg")!,
                headers: [:],
                body: Data()
            ),
            ".jpg"
        )
        XCTAssertEqual(
            WebMediaDLHttpDirect.suffix(
                url: URL(string: "https://cdn.example.com/blob")!,
                headers: [:],
                body: Data()
            ),
            ".bin"
        )
        XCTAssertEqual(
            WebMediaDLHttpDirect.suffix(
                url: URL(string: "https://cdn.example.com/blob")!,
                headers: ["Content-Type": "image/jpeg; charset=utf-8"],
                body: Data()
            ),
            ".jpg"
        )
        XCTAssertTrue(WebMediaDLCapabilityRegistry.allows(.acquireHTTP, on: .ios))
        XCTAssertTrue(WebMediaDLCapabilityRegistry.allows(.acquireHTTP, on: .ipados))
        XCTAssertTrue(WebMediaDLCapabilityRegistry.allows(.acquireHTTP, on: .visionos))
        XCTAssertFalse(WebMediaDLCapabilityRegistry.allows(.acquireHTTP, on: .watchos))
        XCTAssertFalse(WebMediaDLCapabilityRegistry.allows(.acquireHTTP, on: .tvos))

        let root = FileManager.default.temporaryDirectory.appendingPathComponent("wmdl-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: root, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: root) }
        let bookmark = WebMediaDLSecurityScopedBookmark(path: root.path)

        let png: [UInt8] = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]
        let saved = try await WebMediaDLHttpDirect.transfer(
            locator: "https://cdn.example.com/photo.png",
            bookmark: bookmark,
            fetch: { _ in (200, ["Content-Type": "image/png"], Data(png)) }
        )
        XCTAssertEqual(saved.providerId, "http-direct")
        XCTAssertTrue(saved.argv.isEmpty)
        XCTAssertTrue(FileManager.default.fileExists(atPath: saved.outputPath))
        XCTAssertTrue(saved.artifactId.hasPrefix("sha256:"))
        XCTAssertEqual(saved.byteSize, png.count)
        let written = try WebMediaDLHttpDirect.write(
            data: Data("pulled".utf8),
            filename: "clip.mp4",
            bookmark: bookmark
        )
        XCTAssertTrue(written.hasSuffix("clip.mp4"))
        XCTAssertEqual(try Data(contentsOf: URL(fileURLWithPath: written)), Data("pulled".utf8))
        do {
            _ = try WebMediaDLHttpDirect.write(
                data: Data("x".utf8),
                filename: "clip.mp4",
                bookmark: WebMediaDLSecurityScopedBookmark(path: "")
            )
            XCTFail("empty Files root must fail closed")
        } catch WebMediaDLHttpDirect.TransferError.filesDestinationRequired {
            ()
        }

        do {
            _ = try await WebMediaDLHttpDirect.transfer(
                locator: "https://cdn.example.com/clip.mp4",
                bookmark: bookmark,
                fetch: { _ in (200, [:], Data("#EXT-X-KEY:METHOD=AES-128".utf8)) }
            )
            XCTFail("encrypted body must refuse before write")
        } catch let WebMediaDLHttpDirect.TransferError.drmRefused(joined) {
            XCTAssertFalse(joined.isEmpty)
        }
        do {
            _ = try await WebMediaDLHttpDirect.transfer(
                locator: "https://www.youtube.com/watch?v=1",
                bookmark: bookmark,
                fetch: { _ in (200, [:], Data()) }
            )
            XCTFail("page locators must not fetch")
        } catch WebMediaDLHttpDirect.TransferError.pairingRequired {
            ()
        }
        do {
            _ = try await WebMediaDLPairedMacSubmit.submit(
                locator: "https://example.com/a.mp4",
                surface: .ios,
                pairingId: nil,
                sessionKey: nil,
                defaults: UserDefaults(suiteName: UUID().uuidString)!
            )
            XCTFail("heavy work must not POST without a saved Mac relay")
        } catch WebMediaDLHttpDirect.TransferError.pairingRequired {
            ()
        }
        do {
            _ = try await WebMediaDLHttpDirect.transfer(
                locator: "https://cdn.example.com/live.m3u8",
                bookmark: bookmark,
                fetch: { _ in XCTFail("live must not fetch"); return (200, [:], Data()) }
            )
            XCTFail("live must stay on the Mac")
        } catch WebMediaDLHttpDirect.TransferError.liveRequiresMac {
            ()
        }
        do {
            _ = try await WebMediaDLHttpDirect.transfer(
                locator: "https://cdn.example.com/a.mp4",
                bookmark: WebMediaDLSecurityScopedBookmark(path: "")
            )
            XCTFail("empty Files root must fail closed")
        } catch WebMediaDLHttpDirect.TransferError.filesDestinationRequired {
            ()
        }
        do {
            _ = try await WebMediaDLHttpDirect.transfer(
                locator: "https://cdn.example.com/clip.mp4",
                bookmark: bookmark,
                fetch: { _ in (403, [:], Data("nope".utf8)) }
            )
            XCTFail("HTTP errors must not publish")
        } catch WebMediaDLHttpDirect.TransferError.httpStatus(let code) {
            XCTAssertEqual(code, 403)
        }
        do {
            _ = try await WebMediaDLHttpDirect.transfer(
                locator: "https://cdn.example.com/clip.mp4",
                bookmark: bookmark,
                fetch: { _ in (302, ["Location": "http://cdn.example.com/a.mp4"], Data("<html>".utf8)) }
            )
            XCTFail("redirect statuses must not publish HTML")
        } catch WebMediaDLHttpDirect.TransferError.httpStatus(let code) {
            XCTAssertEqual(code, 302)
        }
        do {
            _ = try await WebMediaDLHttpDirect.transfer(
                locator: "http://cdn.example.com/a.mp4",
                bookmark: bookmark,
                fetch: { _ in XCTFail("http locators must not fetch on-device"); return (200, [:], Data()) }
            )
            XCTFail("cleartext http must not transfer on-device")
        } catch WebMediaDLHttpDirect.TransferError.invalidLocator {
            ()
        }
        let skipped = try await WebMediaDLHttpDirect.saveIfDirect(
            locator: "https://www.youtube.com/watch?v=1",
            bookmarkData: nil
        )
        XCTAssertNil(skipped)
        do {
            _ = try await WebMediaDLHttpDirect.transfer(
                locator: "https://cdn.example.com/photo.png",
                bookmark: WebMediaDLSecurityScopedBookmark(
                    path: root.path,
                    bookmarkData: Data("not-a-bookmark".utf8)
                ),
                fetch: { _ in (200, ["Content-Type": "image/png"], Data(png)) }
            )
            XCTFail("unresolvable bookmark data must fail closed")
        } catch WebMediaDLHttpDirect.TransferError.destinationDenied {
            ()
        }
        let kept = root.appendingPathComponent("kept.bin")
        let incoming = root.appendingPathComponent("incoming.bin")
        try Data("old".utf8).write(to: kept)
        try Data("new".utf8).write(to: incoming)
        try WebMediaDLHttpDirect.commitReplacement(from: incoming, to: kept)
        XCTAssertEqual(try String(contentsOf: kept, encoding: .utf8), "new")
        XCTAssertFalse(FileManager.default.fileExists(atPath: incoming.path))
        let missing = root.appendingPathComponent("missing.bin")
        do {
            try WebMediaDLHttpDirect.commitReplacement(from: missing, to: kept)
            XCTFail("missing replacement source must fail closed")
        } catch {
            XCTAssertEqual(try String(contentsOf: kept, encoding: .utf8), "new")
        }

        XCTAssertEqual(
            WebMediaDLHttpDirect.outputStem(from: URL(string: "https://cdn.example.com/a.mp4")!),
            "a"
        )
        XCTAssertEqual(
            WebMediaDLHttpDirect.outputStem(from: URL(string: "https://cdn.example.com/..")!),
            "source"
        )
        do {
            _ = try await WebMediaDLHttpDirect.transfer(
                locator: "file:///tmp/a.mp4",
                bookmark: bookmark,
                fetch: { _ in XCTFail("invalid locators must not fetch"); return (200, [:], Data()) }
            )
            XCTFail("file URLs must not transfer on-device")
        } catch WebMediaDLHttpDirect.TransferError.invalidLocator {
            ()
        }
        do {
            _ = try await WebMediaDLHttpDirect.transfer(
                locator: "https:///a.mp4",
                bookmark: bookmark,
                fetch: { _ in XCTFail("hostless locators must not fetch"); return (200, [:], Data()) }
            )
            XCTFail("hostless https URLs must not transfer on-device")
        } catch WebMediaDLHttpDirect.TransferError.invalidLocator {
            ()
        }
        do {
            _ = try await WebMediaDLHttpDirect.transfer(
                locator: "javascript:alert(1)",
                bookmark: bookmark,
                fetch: { _ in XCTFail("blocked schemes must not fetch"); return (200, [:], Data()) }
            )
            XCTFail("javascript locators must not transfer on-device")
        } catch WebMediaDLHttpDirect.TransferError.invalidLocator {
            ()
        }
        do {
            _ = try await WebMediaDLHttpDirect.transfer(
                locator: "https://cdn.example.com/clip.mp4",
                bookmark: bookmark,
                maxBytes: 4,
                fetch: { _ in (200, [:], Data("oversized".utf8)) }
            )
            XCTFail("oversized bodies must not write")
        } catch WebMediaDLHttpDirect.TransferError.overflow {
            ()
        }
        let escaped = FileManager.default.temporaryDirectory
            .appendingPathComponent("wmdl-deny-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: escaped, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: escaped) }
        do {
            _ = try await WebMediaDLHttpDirect.transfer(
                locator: "https://cdn.example.com/a.mp4",
                bookmark: WebMediaDLSecurityScopedBookmark(path: escaped.path, stale: true),
                fetch: { _ in (200, [:], Data(png)) }
            )
            XCTFail("stale Files bookmarks must not write")
        } catch WebMediaDLHttpDirect.TransferError.destinationDenied {
            ()
        }
        do {
            _ = try await WebMediaDLHttpDirect.transfer(
                locator: "https://cdn.example.com/a.mp4",
                bookmark: bookmark,
                surface: .watchos,
                fetch: { _ in XCTFail("watchOS must not fetch"); return (200, [:], Data()) }
            )
            XCTFail("watchOS must not run on-device http-direct")
        } catch WebMediaDLHttpDirect.TransferError.unsupportedSurface {
            ()
        }
        do {
            _ = try await WebMediaDLHttpDirect.transfer(
                locator: "https://cdn.example.com/a.mp4",
                bookmark: bookmark,
                surface: .tvos,
                fetch: { _ in XCTFail("tvOS must not fetch"); return (200, [:], Data()) }
            )
            XCTFail("tvOS must not run on-device http-direct")
        } catch WebMediaDLHttpDirect.TransferError.unsupportedSurface {
            ()
        }
    }
}
