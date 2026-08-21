import SwiftUI
import WebMediaDLCore

/// watchOS capture, status, history, and controls. Not a subprocess worker.
public struct WebMediaDLWatchRootView: View {
    private let role = WebMediaDLClientRole.captureAndStatus
    private let client = WebMediaDLLoopbackClient()
    private let bridge = WebMediaDLContinuityBridge()
    @State private var status = "Idle"

    public init() {}

    public var body: some View {
        TabView {
            Button("Capture URL") {
                status = bridge.controlMessage(kind: "capture", locator: nil)["kind"] ?? "capture"
            }
            .accessibilityLabel("Capture URL")
            Text(status)
                .accessibilityLabel("Job status")
            Text("History")
                .accessibilityLabel("Job history")
            Button("Pause") {
                _ = client.pauseQueueRequest()
                status = bridge.controlMessage(kind: "pause", locator: nil)["kind"] ?? "pause"
            }
            .accessibilityLabel("Pause current job")
        }
        .navigationTitle("WebMedia DL")
        .accessibilityLabel("WebMedia DL watch capture and status")
        .onAppear {
            _ = role
            _ = client.isLoopback
            _ = bridge.isSubprocessWorker
        }
    }
}
