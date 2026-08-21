import SwiftUI
import UIKit
import WebMediaDLCore

/// iPad complete client with a split inspector and paired-Mac heavy work.
public struct WebMediaDLiPadOSRootView: View {
    @State private var locator = ""
    @State private var pairingId = ""
    @State private var sessionKey = ""
    @State private var status = "Pair with a Mac for yt-dlp and ffmpeg."
    @State private var historyText = "Paired Mac history appears after confirmation."
    @State private var lastJobId: UUID?
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
                        locator = text.trimmingCharacters(in: .whitespacesAndNewlines)
                    }
                }
                .accessibilityLabel("Paste from clipboard")
                Button("Send to paired Mac") {
                    Task {
                        let response = (try? await pairedClient.submit(
                            locator: locator,
                            surface: .ipados,
                            pairingId: UUID(uuidString: pairingId),
                            sessionKey: sessionKey.isEmpty ? nil : sessionKey
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
                Button("Refresh history") {
                    Task {
                        historyText = (try? await pairedClient.history()) ?? "Pairing required"
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
        }
    }
}
