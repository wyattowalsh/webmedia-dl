import SwiftUI
import WebMediaDLCore

/// tvOS capture, status, history, and controls. Not a subprocess worker.
/// The paired Mac forwards companion messages to the loopback worker.
public struct WebMediaDLTVRootView: View {
    private let role = WebMediaDLClientRole.captureAndStatus
    private let bridge = WebMediaDLContinuityBridge()
    @State private var locator = ""
    @State private var status = "Status: idle"

    public init() {}

    public var body: some View {
        NavigationStack {
            List {
                TextField("Clipboard or typed URL", text: $locator)
                    .accessibilityLabel("Media URL")
                Button("Capture from clipboard") {
                    status = bridge.message(kind: "capture", locator: locator).kind
                }
                .accessibilityLabel("Capture from clipboard")
                Text(status)
                    .accessibilityLabel("Job status")
                Button("History") {
                    status = bridge.message(kind: "history").kind
                }
                .accessibilityLabel("Job history")
                Button("Pause queue") {
                    status = bridge.message(kind: "pause").kind
                }
                .accessibilityLabel("Pause queue")
                Button("Resume queue") {
                    status = bridge.message(kind: "resume").kind
                }
                .accessibilityLabel("Resume queue")
                Text("Role \(role.rawValue). Companion to Mac worker.")
            }
            .navigationTitle("WebMedia DL")
        }
    }
}
