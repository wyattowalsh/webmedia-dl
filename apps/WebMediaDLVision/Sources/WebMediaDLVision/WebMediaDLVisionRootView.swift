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
                    let response = (try? await pairedClient.submit(
                        locator: locator,
                        surface: .visionos,
                        pairingId: UUID(uuidString: pairingId),
                        sessionKey: sessionKey.isEmpty ? nil : sessionKey,
                        intakeKind: fromClipboard ? clip.intakeKind : nil,
                        destinationKind: files == nil ? nil : "files_app",
                        destinationPath: files?.approvedRoot,
                        approvedRoots: files.map { [$0.approvedRoot] } ?? [],
                        bookmarkData: filesBookmark.bookmarkData
                    )) ?? "Pairing required"
                    status = response
                    lastJobId = WebMediaDLLoopbackClient.jobId(from: response)
                }
            }
            .accessibilityLabel("Send to paired Mac")
            TextField("Pairing id", text: $pairingId)
                .accessibilityLabel("Pairing id")
            SecureField("Session key", text: $sessionKey)
                .accessibilityLabel("Session key")
            Button("Start pairing") {
                Task {
                    do {
                        let challenge = try await pairedClient.startPairing()
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
            }
            Button("Refresh history") {
                Task {
                    do {
                        let (data, _) = try await URLSession.shared.data(for: pairedClient.historyRequest())
                        history = (try? WebMediaDLHistoryEntry.decodeCompanionHistory(from: data))
                            ?? ((try? JSONDecoder().decode([WebMediaDLHistoryEntry].self, from: data)) ?? [])
                        historyText = history.isEmpty
                            ? "No jobs yet."
                            : history.map { "\($0.jobId.uuidString.prefix(8)) \($0.state)" }.joined(separator: "\n")
                    } catch {
                        historyText = "Pairing required"
                    }
                }
            }
            .accessibilityLabel("Refresh history")
            Button("Pause queue") {
                Task { status = (try? await pairedClient.pauseQueue()) ?? "Pairing required" }
            }
            .accessibilityLabel("Pause queue")
            Button("Resume queue") {
                Task { status = (try? await pairedClient.resumeQueue()) ?? "Pairing required" }
            }
            .accessibilityLabel("Resume queue")
            Button("Cancel last job") {
                Task {
                    guard let lastJobId else {
                        status = "No job to cancel"
                        return
                    }
                    status = (try? await pairedClient.cancel(jobId: lastJobId)) ?? "Pairing required"
                }
            }
            .accessibilityLabel("Cancel last job")
            Button("Pause last job") {
                Task {
                    guard let lastJobId else {
                        status = "No job to pause"
                        return
                    }
                    status = (try? await pairedClient.pauseJob(jobId: lastJobId)) ?? "Pairing required"
                }
            }
            .accessibilityLabel("Pause last job")
            Button("Resume last job") {
                Task {
                    guard let lastJobId else {
                        status = "No job to resume"
                        return
                    }
                    status = (try? await pairedClient.resumeJob(jobId: lastJobId)) ?? "Pairing required"
                }
            }
            .accessibilityLabel("Resume last job")
            Text("Role \(role.rawValue). Loopback \(pairedClient.baseURL.absoluteString)")
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
