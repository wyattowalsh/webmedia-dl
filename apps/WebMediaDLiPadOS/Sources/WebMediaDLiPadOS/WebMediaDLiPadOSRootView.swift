import SwiftUI
import UIKit
import UniformTypeIdentifiers
import WebMediaDLCore

/// iPad complete client with a split inspector and paired-Mac heavy work.
public struct WebMediaDLiPadOSRootView: View {
    @State private var locator = ""
    @State private var pairingId = ""
    @State private var sessionKey = ""
    @State private var status = "Pair with a Mac for yt-dlp and ffmpeg."
    @State private var historyText = "Paired Mac history appears after confirmation."
    @State private var history: [WebMediaDLHistoryEntry] = []
    @State private var lastJobId: UUID?
    @State private var filesBookmark = WebMediaDLSecurityScopedBookmark(path: "")
    @State private var pickingDestination = false
    private let role = WebMediaDLClientRole.pairedClient
    private let client = WebMediaDLLoopbackClient()

    public init() {}

    private var pairedClient: WebMediaDLLoopbackClient {
        WebMediaDLLoopbackClient(
            pairingId: UUID(uuidString: pairingId),
            sessionKey: sessionKey.isEmpty ? nil : sessionKey
        )
    }

    public var body: some View {
        NavigationSplitView {
            List {
                Text("Capture")
                Text("Status")
                Text("History")
            }
            .navigationTitle("WebMedia DL")
            .accessibilityLabel("WebMedia DL iPad sidebar")
        } detail: {
            VStack(alignment: .leading, spacing: 12) {
                TextField("Paste a media URL", text: $locator)
                    .accessibilityLabel("Media URL")
                    .textFieldStyle(.roundedBorder)
                Button("Paste from clipboard") {
                    if let text = UIPasteboard.general.string {
                        let clip = WebMediaDLClipboardIntake(text: text)
                        locator = clip.locator ?? text.trimmingCharacters(in: .whitespacesAndNewlines)
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
                    if accessed {
                        url.stopAccessingSecurityScopedResource()
                    }
                }
                if !filesBookmark.path.isEmpty {
                    Text(filesBookmark.path)
                        .accessibilityLabel("Approved Files destination")
                }
                Button("Send to paired Mac") {
                    Task {
                        let roots = filesBookmark.path.isEmpty ? [] : [filesBookmark.path]
                        let response = (try? await pairedClient.submit(
                            locator: locator,
                            surface: .ipados,
                            pairingId: UUID(uuidString: pairingId),
                            sessionKey: sessionKey.isEmpty ? nil : sessionKey,
                            destinationKind: roots.isEmpty ? nil : "files_app",
                            destinationPath: roots.first,
                            approvedRoots: roots
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
                            history = (try? JSONDecoder().decode([WebMediaDLHistoryEntry].self, from: data)) ?? []
                            historyText = history.isEmpty
                                ? "No jobs yet."
                                : history.map { "\($0.jobId.uuidString.prefix(8)) \($0.state)" }.joined(separator: "\n")
                        } catch {
                            historyText = "Pairing required"
                        }
                    }
                }
                .accessibilityLabel("Refresh history")
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
                Text("Role \(role.rawValue) at \(client.baseURL.absoluteString)")
                Spacer()
            }
            .padding()
            .onChange(of: pairingId) { _, value in
                UserDefaults.standard.set(value, forKey: WebMediaDLWorkerCredentials.pairingDefaultsKey)
            }
            .onChange(of: sessionKey) { _, value in
                UserDefaults.standard.set(value, forKey: WebMediaDLWorkerCredentials.sessionDefaultsKey)
            }
        }
    }
}
