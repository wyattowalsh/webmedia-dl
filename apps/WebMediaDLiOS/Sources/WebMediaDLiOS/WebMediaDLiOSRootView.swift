import SwiftUI
import UIKit
import WebMediaDLCore

/// iPhone complete client: lightweight local transfer plus paired-Mac heavy work.
public struct WebMediaDLiOSRootView: View {
    @State private var locator = ""
    @State private var pairingId = ""
    @State private var sessionKey = ""
    @State private var status = "Pair with a Mac to run yt-dlp or ffmpeg jobs."
    @State private var historyText = "Lightweight HTTP jobs stay on-device. Heavy work waits for Mac confirmation."
    @State private var lastJobId: UUID?
    private let role = WebMediaDLClientRole.pairedClient

    public init() {}

    private var client: WebMediaDLLoopbackClient {
        WebMediaDLLoopbackClient(
            pairingId: UUID(uuidString: pairingId),
            sessionKey: sessionKey.isEmpty ? nil : sessionKey
        )
    }

    public var body: some View {
        NavigationStack {
            Form {
                Section("Capture") {
                    TextField("Share or paste a URL", text: $locator)
                        .textInputAutocapitalization(.never)
                        .accessibilityLabel("Media URL")
                    Button("Paste from clipboard") {
                        if let text = UIPasteboard.general.string {
                            let clip = WebMediaDLClipboardIntake(text: text)
                            locator = clip.locator ?? text.trimmingCharacters(in: .whitespacesAndNewlines)
                        }
                    }
                    .accessibilityLabel("Paste from clipboard")
                    Button("Send to paired Mac") {
                        Task {
                            let response = (try? await client.submit(
                                locator: locator,
                                surface: .ios,
                                pairingId: UUID(uuidString: pairingId),
                                sessionKey: sessionKey.isEmpty ? nil : sessionKey
                            )) ?? "Pairing required"
                            status = response
                            lastJobId = WebMediaDLLoopbackClient.jobId(from: response)
                        }
                    }
                    .accessibilityLabel("Send to paired Mac")
                }
                Section("Pairing") {
                    TextField("Pairing id", text: $pairingId)
                        .textInputAutocapitalization(.never)
                        .accessibilityLabel("Pairing id")
                    SecureField("Session key", text: $sessionKey)
                        .accessibilityLabel("Session key")
                    Text("The Mac user must confirm pairing. This client cannot self-confirm.")
                }
                Section("Status") {
                    Text(status)
                        .accessibilityLabel("Job status")
                    Text("Role \(role.rawValue). Loopback \(client.baseURL.absoluteString)")
                }
                Section("History") {
                    Text(historyText)
                        .accessibilityLabel("Job history")
                    Button("Refresh history") {
                        Task {
                            historyText = (try? await client.history()) ?? "Pairing required"
                        }
                    }
                    .accessibilityLabel("Refresh history")
                }
                Section("Queue") {
                    Button("Pause queue") {
                        Task { status = (try? await client.pauseQueue()) ?? "Pairing required" }
                    }
                    .accessibilityLabel("Pause queue")
                    Button("Resume queue") {
                        Task { status = (try? await client.resumeQueue()) ?? "Pairing required" }
                    }
                    .accessibilityLabel("Resume queue")
                    Button("Cancel last job") {
                        Task {
                            guard let lastJobId else {
                                status = "No job to cancel"
                                return
                            }
                            status = (try? await client.cancel(jobId: lastJobId)) ?? "Pairing required"
                        }
                    }
                    .accessibilityLabel("Cancel last job")
                    Button("Pause last job") {
                        Task {
                            guard let lastJobId else {
                                status = "No job to pause"
                                return
                            }
                            status = (try? await client.pauseJob(jobId: lastJobId)) ?? "Pairing required"
                        }
                    }
                    .accessibilityLabel("Pause last job")
                    Button("Resume last job") {
                        Task {
                            guard let lastJobId else {
                                status = "No job to resume"
                                return
                            }
                            status = (try? await client.resumeJob(jobId: lastJobId)) ?? "Pairing required"
                        }
                    }
                    .accessibilityLabel("Resume last job")
                }
            }
            .navigationTitle("WebMedia DL")
        }
    }
}
