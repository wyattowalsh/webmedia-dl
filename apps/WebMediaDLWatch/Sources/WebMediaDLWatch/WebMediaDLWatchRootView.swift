import SwiftUI
import WebMediaDLCore

/// watchOS capture, status, history, and controls. Not a subprocess worker.
public struct WebMediaDLWatchRootView: View {
    private let role = WebMediaDLClientRole.captureAndStatus
    private let client = WebMediaDLLoopbackClient()

    public init() {}

    public var body: some View {
        TabView {
            Button("Capture URL") {}
                .accessibilityLabel("Capture URL")
            Text("Status")
                .accessibilityLabel("Job status")
            Text("History")
                .accessibilityLabel("Job history")
            Button("Pause") {}
                .accessibilityLabel("Pause current job")
        }
        .navigationTitle("WebMedia DL")
        .accessibilityLabel("WebMedia DL watch capture and status")
        .onAppear {
            _ = role
            _ = client.isLoopback
        }
    }
}
