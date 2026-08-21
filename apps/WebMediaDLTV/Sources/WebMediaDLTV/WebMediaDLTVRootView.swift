import SwiftUI
import WebMediaDLCore

/// tvOS capture, status, history, and controls. Not a subprocess worker.
public struct WebMediaDLTVRootView: View {
    private let role = WebMediaDLClientRole.captureAndStatus
    private let client = WebMediaDLLoopbackClient()
    private let bridge = WebMediaDLContinuityBridge()
    @State private var status = "Status: idle"

    public init() {}

    public var body: some View {
        NavigationStack {
            List {
                Button("Capture from clipboard") {
                    status = "Capture queued on loopback \(client.baseURL.absoluteString)"
                }
                .accessibilityLabel("Capture from clipboard")
                Text(status)
                    .accessibilityLabel("Job status")
                Text("History")
                    .accessibilityLabel("Job history")
                Button("Pause queue") {
                    _ = client.cancelRequest(jobId: UUID())
                    _ = bridge.controlMessage(kind: "pause", locator: nil)
                    status = "Pause requested"
                }
                .accessibilityLabel("Pause queue")
                Text("Role \(role.rawValue). Loopback \(client.baseURL.absoluteString)")
            }
            .navigationTitle("WebMedia DL")
        }
    }
}
