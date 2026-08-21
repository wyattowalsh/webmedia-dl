import SwiftUI
import WebMediaDLCore

/// watchOS capture, status, history, and controls. Not a subprocess worker.
/// Control messages go to the paired Mac over Continuity. This device has no provider runtime.
public struct WebMediaDLWatchRootView: View {
    private let role = WebMediaDLClientRole.captureAndStatus
    private let bridge = WebMediaDLContinuityBridge()
    @State private var locator = ""
    @State private var status = "Idle"
    @State private var lastJobId: String?
    @State private var transport = WebMediaDLWatchConnectivityTransport()
    @State private var history: [WebMediaDLHistoryEntry] = []

    public init() {}

    public var body: some View {
        TabView {
            VStack {
                TextField("URL", text: $locator)
                    .accessibilityLabel("Media URL")
                Button("Capture URL") {
                    Task { await send(kind: "capture", locator: locator) }
                }
                .accessibilityLabel("Capture URL")
            }
            Text(status)
                .accessibilityLabel("Job status")
            Button("History") {
                Task {
                    await send(kind: "history")
                    if let data = transport.lastResponse?.data(using: .utf8) {
                        history = (try? WebMediaDLHistoryEntry.decodeCompanionHistory(from: data)) ?? []
                        lastJobId = history.first?.jobId.uuidString ?? lastJobId
                    }
                }
            }
            .accessibilityLabel("Job history")
            List(history) { entry in
                Text("\(entry.state)")
                    .accessibilityLabel("History row")
            }
            Button("Status") {
                Task { await send(kind: "status") }
            }
            .accessibilityLabel("Queue status")
            Button("Pause") {
                Task {
                    if let lastJobId {
                        await send(kind: "pause_job", jobId: lastJobId)
                    } else {
                        await send(kind: "pause")
                    }
                }
            }
            .accessibilityLabel("Pause current job")
            Button("Resume") {
                Task {
                    if let lastJobId {
                        await send(kind: "resume_job", jobId: lastJobId)
                    } else {
                        await send(kind: "resume")
                    }
                }
            }
            .accessibilityLabel("Resume current job")
            Button("Cancel") {
                Task { await send(kind: "cancel", jobId: lastJobId) }
            }
            .accessibilityLabel("Cancel last job")
        }
        .navigationTitle("WebMedia DL")
        .accessibilityLabel("WebMedia DL watch capture and status")
        .onAppear {
            _ = role
            _ = bridge.isSubprocessWorker
            transport.activateSession()
        }
    }

    @MainActor
    private func send(kind: String, locator: String? = nil, jobId: String? = nil) async {
        let message = bridge.message(kind: kind, locator: locator, jobId: jobId, surface: .watchos)
        try? await transport.send(message)
        status = "Queued \(message.kind) for Mac relay"
        if let body = transport.lastResponse,
           let parsed = WebMediaDLLoopbackClient.jobId(from: body) {
            lastJobId = parsed.uuidString
        }
    }
}
