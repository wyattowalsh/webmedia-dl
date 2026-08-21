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
                    Task { await send(kind: "capture", locator: locator) }
                }
                .accessibilityLabel("Capture from clipboard")
                Text(status)
                    .accessibilityLabel("Job status")
                Button("History") {
                    Task { await send(kind: "history") }
                }
                .accessibilityLabel("Job history")
                Button("Pause queue") {
                    Task { await send(kind: "pause") }
                }
                .accessibilityLabel("Pause queue")
                Button("Resume queue") {
                    Task { await send(kind: "resume") }
                }
                .accessibilityLabel("Resume queue")
                Text("Role \(role.rawValue). Companion to Mac worker.")
            }
            .navigationTitle("WebMedia DL")
        }
    }

    @MainActor
    private func send(kind: String, locator: String? = nil) async {
        let message = bridge.message(kind: kind, locator: locator)
        status = (try? await bridge.send(message)) ?? message.kind
    }
}
