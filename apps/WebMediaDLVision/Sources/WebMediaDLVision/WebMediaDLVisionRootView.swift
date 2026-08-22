import SwiftUI
import UIKit
import UniformTypeIdentifiers
import WebMediaDLCore

/// visionOS complete client: immersive capture plus paired-Mac heavy work.
public struct WebMediaDLVisionRootView: View {
    @State private var locator = ""
    @State private var pairingId = ""
    @State private var sessionKey = ""
    @State private var status = "Pair with a Mac for heavy work."
    @State private var historyText = "Lightweight HTTP jobs stay on-device. Heavy work waits for Mac confirmation."
    @State private var history: [WebMediaDLHistoryEntry] = []
    @State private var lastJobId: UUID?
    @State private var filesBookmark = WebMediaDLSecurityScopedBookmark(path: "")
    @State private var pickingDestination = false
    @State private var fromClipboard = false
    @State private var macRelay = ""
    private let role = WebMediaDLClientRole.pairedClient

    public init() {}

    private var pairedClient: WebMediaDLLoopbackClient {
        var loaded = WebMediaDLWorkerCredentials.loadClient()
        loaded.pairingId = UUID(uuidString: pairingId) ?? loaded.pairingId
        loaded.sessionKey = sessionKey.isEmpty ? loaded.sessionKey : sessionKey
        return loaded
    }

    public var body: some View {
        VStack(spacing: 16) {
            Text("WebMedia DL")
                .font(.largeTitle)
                .accessibilityAddTraits(.isHeader)
            TextField("Paste a media URL", text: $locator)
                .accessibilityLabel("Media URL")
            Button("Paste from clipboard") {
                if let text = UIPasteboard.general.string {
                    let clip = WebMediaDLClipboardIntake(text: text)
                    locator = clip.locator ?? text.trimmingCharacters(in: .whitespacesAndNewlines)
                    fromClipboard = true
                }
            }
            .accessibilityLabel("Paste from clipboard")
            Button("Choose Files destination") {
                pickingDestination = true
            }
            .accessibilityLabel("Choose Files destination")
            .fileImporter(
                isPresented: $pickingDestination,
                allowedContentTypes: [.folder],
                allowsMultipleSelection: false
            ) { result in
                guard case .success(let urls) = result, let url = urls.first else { return }
                let accessed = url.startAccessingSecurityScopedResource()
                filesBookmark = WebMediaDLSecurityScopedBookmark.fromPickedURL(url)
                if let data = filesBookmark.bookmarkData {
                    WebMediaDLWorkerCredentials.defaults().set(
                        data,
                        forKey: WebMediaDLWorkerCredentials.bookmarkDefaultsKey
                    )
                }
                if accessed {
                    url.stopAccessingSecurityScopedResource()
                }
            }
            if !filesBookmark.path.isEmpty {
                Text(filesBookmark.path)
                    .accessibilityLabel("Approved Files destination")
            }
            Button("Save on this device") {
                Task {
                    do {
                        let result = try await WebMediaDLHttpDirect.transfer(
                            locator: locator,
                            bookmark: filesBookmark,
                            surface: .visionos
                        )
                        status = "Saved on this device \(result.outputPath)"
                        lastJobId = result.jobId
                    } catch {
                        status = error.localizedDescription
                    }
                }
            }
            .accessibilityLabel("Save on this device")
            Button("Send to paired Mac") {
                Task {
                    let files = filesBookmark.path.isEmpty
                        ? nil
                        : WebMediaDLFilesDestination(bookmark: filesBookmark)
                    let clip = WebMediaDLClipboardIntake(text: locator)
                    do {
                        let response = try await WebMediaDLPairedMacSubmit.submit(
                            locator: locator,
                            surface: .visionos,
                            credentials: pairedClient,
                            pairingId: UUID(uuidString: pairingId),
                            sessionKey: sessionKey.isEmpty ? nil : sessionKey,
                            intakeKind: fromClipboard ? clip.intakeKind : nil,
                            destinationKind: files == nil ? nil : "staging_only"
                        )
                        status = response
                        if let id = WebMediaDLLoopbackClient.jobId(from: response) {
                            lastJobId = id
                        }
                    } catch {
                        status = error.localizedDescription
                    }
                }
            }
            .accessibilityLabel("Send to paired Mac")
            TextField("Paired Mac URL", text: $macRelay)
                .accessibilityLabel("Paired Mac URL")
            Button("Save Mac address") {
                if let url = URL(string: macRelay),
                   WebMediaDLPairedMacEndpoint.saveRelay(url) {
                    status = "Saved Mac relay \(url.absoluteString)"
                } else {
                    status = "Mac address must be loopback, .local, or a private LAN URL."
                }
            }
            .accessibilityLabel("Save Mac address")
            TextField("Pairing id", text: $pairingId)
                .accessibilityLabel("Pairing id")
            SecureField("Session key", text: $sessionKey)
                .accessibilityLabel("Session key")
            Button("Start pairing") {
                Task {
                    do {
                        let challenge = try await WebMediaDLPairedMacEndpoint.startPairing()
                        pairingId = challenge.pairingId.uuidString
                        sessionKey = WebMediaDLLoopbackClient.derivedSessionKey(nonce: challenge.nonce)
                        status = "Confirm this pairing on the Mac before \(challenge.expiresAt)."
                    } catch {
                        status = error.localizedDescription
                    }
                }
            }
            .accessibilityLabel("Start pairing")
            Text(status)
                .accessibilityLabel("Job status")
            Text(historyText)
                .accessibilityLabel("Job history")
            List(history) { entry in
                Text("\(entry.jobId.uuidString.prefix(8)) \(entry.state)")
                    .accessibilityLabel("History row")
            }
            Button("Refresh history") {
                Task {
                    do {
                        let entries = try await WebMediaDLPairedMacSubmit.history(
                            credentials: pairedClient,
                            pairingId: UUID(uuidString: pairingId),
                            sessionKey: sessionKey.isEmpty ? nil : sessionKey
                        )
                        history = entries
                        historyText = entries.isEmpty
                            ? "No jobs yet."
                            : entries.map { "\($0.jobId.uuidString.prefix(8)) \($0.state)" }.joined(separator: "\n")
                    } catch {
                        historyText = "Pairing required"
                    }
                }
            }
            .accessibilityLabel("Refresh history")
            Button("Save published files here") {
                Task {
                    guard let lastJobId else {
                        status = "No job to save"
                        return
                    }
                    do {
                        let written = try await WebMediaDLPairedMacSubmit.pullToFiles(
                            jobId: lastJobId,
                            bookmark: filesBookmark,
                            credentials: pairedClient,
                            pairingId: UUID(uuidString: pairingId),
                            sessionKey: sessionKey.isEmpty ? nil : sessionKey
                        )
                        status = "Saved \(written.joined(separator: ", "))"
                    } catch {
                        status = error.localizedDescription
                    }
                }
            }
            .accessibilityLabel("Save published files here")
            Button("Pause queue") {
                Task {
                    do {
                        status = try await WebMediaDLPairedMacSubmit.pauseQueue(
                            credentials: pairedClient,
                            pairingId: UUID(uuidString: pairingId),
                            sessionKey: sessionKey.isEmpty ? nil : sessionKey
                        )
                    } catch {
                        status = error.localizedDescription
                    }
                }
            }
            .accessibilityLabel("Pause queue")
            Button("Resume queue") {
                Task {
                    do {
                        status = try await WebMediaDLPairedMacSubmit.resumeQueue(
                            credentials: pairedClient,
                            pairingId: UUID(uuidString: pairingId),
                            sessionKey: sessionKey.isEmpty ? nil : sessionKey
                        )
                    } catch {
                        status = error.localizedDescription
                    }
                }
            }
            .accessibilityLabel("Resume queue")
            Button("Queue status") {
                Task {
                    do {
                        status = try await WebMediaDLPairedMacSubmit.queueStatus(
                            credentials: pairedClient,
                            pairingId: UUID(uuidString: pairingId),
                            sessionKey: sessionKey.isEmpty ? nil : sessionKey
                        )
                    } catch {
                        status = error.localizedDescription
                    }
                }
            }
            .accessibilityLabel("Queue status")
            Button("Cancel last job") {
                Task {
                    guard let lastJobId else {
                        status = "No job to cancel"
                        return
                    }
                    do {
                        status = try await WebMediaDLPairedMacSubmit.cancel(
                            jobId: lastJobId,
                            credentials: pairedClient,
                            pairingId: UUID(uuidString: pairingId),
                            sessionKey: sessionKey.isEmpty ? nil : sessionKey
                        )
                    } catch {
                        status = error.localizedDescription
                    }
                }
            }
            .accessibilityLabel("Cancel last job")
            Button("Pause last job") {
                Task {
                    guard let lastJobId else {
                        status = "No job to pause"
                        return
                    }
                    do {
                        status = try await WebMediaDLPairedMacSubmit.pauseJob(
                            jobId: lastJobId,
                            credentials: pairedClient,
                            pairingId: UUID(uuidString: pairingId),
                            sessionKey: sessionKey.isEmpty ? nil : sessionKey
                        )
                    } catch {
                        status = error.localizedDescription
                    }
                }
            }
            .accessibilityLabel("Pause last job")
            Button("Resume last job") {
                Task {
                    guard let lastJobId else {
                        status = "No job to resume"
                        return
                    }
                    do {
                        status = try await WebMediaDLPairedMacSubmit.resumeJob(
                            jobId: lastJobId,
                            credentials: pairedClient,
                            pairingId: UUID(uuidString: pairingId),
                            sessionKey: sessionKey.isEmpty ? nil : sessionKey
                        )
                    } catch {
                        status = error.localizedDescription
                    }
                }
            }
            .accessibilityLabel("Resume last job")
            Text("Role \(role.rawValue). Mac \(WebMediaDLPairedMacEndpoint.advertisedRelay()?.absoluteString ?? "not saved")")
        }
        .padding(32)
        .onAppear {
            let defaults = WebMediaDLWorkerCredentials.defaults()
            if pairingId.isEmpty {
                pairingId = defaults.string(forKey: WebMediaDLWorkerCredentials.pairingDefaultsKey) ?? ""
            }
            if sessionKey.isEmpty {
                sessionKey = defaults.string(forKey: WebMediaDLWorkerCredentials.sessionDefaultsKey) ?? ""
            }
            if let data = WebMediaDLWorkerCredentials.loadBookmark() {
                filesBookmark = WebMediaDLSecurityScopedBookmark(path: "", bookmarkData: data).resolve()
            }
        }
        .onChange(of: pairingId) { _, value in
            WebMediaDLWorkerCredentials.defaults().set(value, forKey: WebMediaDLWorkerCredentials.pairingDefaultsKey)
        }
        .onChange(of: sessionKey) { _, value in
            WebMediaDLWorkerCredentials.defaults().set(value, forKey: WebMediaDLWorkerCredentials.sessionDefaultsKey)
        }
    }
}
