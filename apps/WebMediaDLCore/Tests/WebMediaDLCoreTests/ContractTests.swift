import XCTest
#if canImport(WatchConnectivity)
import WatchConnectivity
#endif
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
        XCTAssertEqual(decoded.dictionary()["subprocessWorker"] as? String, "false")
        XCTAssertNil((decoded.dictionary()["nativeCommand"] as? String))

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

    func testClipboardAndShareExtractorIgnoreNonHTTP() async {
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
        XCTAssertTrue(client.resumeQueueRequest().url?.absoluteString.contains("queue/resume") ?? false)
        XCTAssertTrue(client.queueStatusRequest().url?.absoluteString.contains("/v1/queue") ?? false)
        XCTAssertFalse(client.queueStatusRequest().url?.absoluteString.contains("pause") ?? true)
        XCTAssertFalse(client.queueStatusRequest().url?.absoluteString.contains("resume") ?? true)
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
        XCTAssertFalse(
            WebMediaDLPairedMacEndpoint.isAllowedRelay(URL(string: "http://example.com:8765")!)
        )
        XCTAssertTrue(
            WebMediaDLPairedMacEndpoint.isAllowedRelay(URL(string: "http://192.168.1.9:8766")!)
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
        let request = endpoint!.submitRequest(locator: "https://example.com/a.mp4", surface: .ios)
        XCTAssertEqual(request.url?.host, "10.0.0.2")
        XCTAssertEqual(request.value(forHTTPHeaderField: "X-WebMedia-Pairing"), pairing.uuidString)
        XCTAssertEqual(endpoint!.historyRequest().url?.host, "10.0.0.2")
        XCTAssertTrue(endpoint!.pauseQueueRequest().url?.path.contains("queue/pause") ?? false)
        XCTAssertTrue(endpoint!.queueStatusRequest().url?.path.hasSuffix("/queue") ?? false)
        XCTAssertEqual(endpoint!.queueStatusRequest().url?.host, "10.0.0.2")
        XCTAssertEqual(endpoint!.cancelRequest(jobId: pairing).url?.host, "10.0.0.2")
        XCTAssertEqual(endpoint!.pauseJobRequest(jobId: pairing).url?.host, "10.0.0.2")
        XCTAssertEqual(endpoint!.resumeJobRequest(jobId: pairing).url?.host, "10.0.0.2")
        let forwarded = try WebMediaDLMacWorkerRelay.forwardToLoopback(request)
        XCTAssertEqual(forwarded.url?.host, "127.0.0.1")
        XCTAssertEqual(forwarded.url?.port, 8765)
        var poisoned = request
        poisoned.httpBody = try JSONSerialization.data(withJSONObject: ["nativeCommand": "yt-dlp"])
        XCTAssertThrowsError(try WebMediaDLMacWorkerRelay.forwardToLoopback(poisoned))
        var subprocess = request
        subprocess.httpBody = try JSONSerialization.data(withJSONObject: ["subprocessWorker": true])
        XCTAssertThrowsError(try WebMediaDLMacWorkerRelay.forwardToLoopback(subprocess))
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
        XCTAssertFalse(WebMediaDLHttpDirect.isOnDeviceTransfer("https://www.youtube.com/watch?v=1"))
        XCTAssertFalse(WebMediaDLHttpDirect.isOnDeviceTransfer("https://cdn.example.com/live.m3u8"))
        XCTAssertTrue(WebMediaDLHttpDirect.isDirectMediaURL("https://cdn.example.com/live.m3u8"))
        XCTAssertTrue(WebMediaDLHttpDirect.hlsKeyIsProtected("#EXT-X-KEY:METHOD=AES-128,URI=\"https://cdn.example.com/key\""))
        XCTAssertFalse(WebMediaDLHttpDirect.hlsKeyIsProtected("#EXT-X-KEY:METHOD=NONE"))
        XCTAssertFalse(WebMediaDLHttpDirect.drmSignals(in: "#EXT-X-KEY:METHOD=NONE").contains("ext-x-key"))
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
        } catch WebMediaDLHttpDirect.TransferError.filesDestinationRequired {
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
