import SwiftUI
import WebMediaDLCore

/// watchOS capture, status, history, and controls. Not a subprocess worker.
/// Control messages go to the paired Mac over Continuity. This device has no provider runtime.
public struct WebMediaDLWatchRootView: View {
    private let role = WebMediaDLClientRole.captureAndStatus
    private let bridge = WebMediaDLContinuityBridge()
    @State private var locator = ""
    @State private var status = "Idle"

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
                Task { await send(kind: "history") }
            }
            .accessibilityLabel("Job history")
            Button("Pause") {
                Task { await send(kind: "pause") }
            }
            .accessibilityLabel("Pause current job")
        }
        .navigationTitle("WebMedia DL")
        .accessibilityLabel("WebMedia DL watch capture and status")
        .onAppear {
            _ = role
            _ = bridge.isSubprocessWorker
        }
    }

    @MainActor
    private func send(kind: String, locator: String? = nil) async {
        let message = bridge.message(kind: kind, locator: locator)
        status = (try? await bridge.send(message)) ?? message.kind
    }
}
