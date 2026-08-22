import SwiftUI
import WebMediaDLCore

/// tvOS capture, status, history, and controls. Not a subprocess worker.
/// tvOS has no pasteboard string API; capture is typed URL only.
/// The paired Mac receives companion messages over LAN HTTP, not WatchConnectivity.
public struct WebMediaDLTVRootView: View {
    private let role = WebMediaDLClientRole.captureAndStatus
    private let bridge = WebMediaDLContinuityBridge()
    @State private var locator = ""
    @State private var status = "Status: idle"
    @State private var lastJobId: String?
    @State private var transport = WebMediaDLLocalNetworkCompanionTransport()
    @State private var history: [WebMediaDLHistoryEntry] = []

    public init() {}

    public var body: some View {
        NavigationStack {
            List {
                TextField("URL", text: $locator)
                    .accessibilityLabel("Media URL")
                Button("Capture URL") {
                    Task {
                        let clip = WebMediaDLClipboardIntake(text: locator)
                        locator = clip.locator ?? locator
                        await send(kind: "capture", locator: locator)
                    }
                }
                .accessibilityLabel("Capture URL")
                Text(status)
                    .accessibilityLabel("Job status")
                Button("History") {
                    Task {
                        await send(kind: "history")
                        if let data = transport.lastResponse?.data(using: .utf8) {
                            do {
                                history = try WebMediaDLHistoryEntry.decodeCompanionHistory(from: data)
                                lastJobId = history.first?.jobId.uuidString ?? lastJobId
                            } catch {
                                status = error.localizedDescription
                            }
                        }
                    }
                }
                .accessibilityLabel("Job history")
                ForEach(history) { entry in
                    Text("\(entry.state)")
                        .accessibilityLabel("History row")
                }
                Button("Status") {
                    Task { await send(kind: "status") }
                }
                .accessibilityLabel("Queue status")
                Button("Pause queue") {
                    Task { await send(kind: "pause") }
                }
                .accessibilityLabel("Pause queue")
                Button("Resume queue") {
                    Task { await send(kind: "resume") }
                }
                .accessibilityLabel("Resume queue")
                Button("Cancel last job") {
                    Task { await send(kind: "cancel", jobId: lastJobId) }
                }
                .accessibilityLabel("Cancel last job")
                Button("Pause last job") {
                    Task { await send(kind: "pause_job", jobId: lastJobId) }
                }
                .accessibilityLabel("Pause last job")
                Button("Resume last job") {
                    Task { await send(kind: "resume_job", jobId: lastJobId) }
                }
                .accessibilityLabel("Resume last job")
                Text("Role \(role.rawValue). Companion to Mac worker.")
            }
            .navigationTitle("WebMedia DL")
            .onAppear {
                _ = role
            }
        }
    }

    @MainActor
    private func send(kind: String, locator: String? = nil, jobId: String? = nil) async {
        do {
            let message = try WebMediaDLCompanionControlMessage.make(
                kind: kind,
                locator: locator,
                jobId: jobId,
                surface: .tvos
            )
            try await transport.send(message)
            status = "Queued \(message.kind) for Mac relay"
            if let body = transport.lastResponse,
               let parsed = WebMediaDLLoopbackClient.jobId(from: body) {
                lastJobId = parsed.uuidString
            }
        } catch {
            status = error.localizedDescription
        }
    }
}
