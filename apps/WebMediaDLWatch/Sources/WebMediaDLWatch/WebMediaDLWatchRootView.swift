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
                    let message = bridge.message(kind: "capture", locator: locator)
                    status = message.kind
                }
                .accessibilityLabel("Capture URL")
            }
            Text(status)
                .accessibilityLabel("Job status")
            Button("History") {
                status = bridge.message(kind: "history").kind
            }
            .accessibilityLabel("Job history")
            Button("Pause") {
                status = bridge.message(kind: "pause").kind
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
}
