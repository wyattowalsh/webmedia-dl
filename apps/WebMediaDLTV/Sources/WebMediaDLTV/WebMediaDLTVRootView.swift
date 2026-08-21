import SwiftUI
import WebMediaDLCore

/// tvOS capture, status, history, and controls. Not a subprocess worker.
public struct WebMediaDLTVRootView: View {
    private let role = WebMediaDLClientRole.captureAndStatus
    private let client = WebMediaDLLoopbackClient()

    public init() {}

    public var body: some View {
        NavigationStack {
            List {
                Button("Capture from clipboard") {}
                    .accessibilityLabel("Capture from clipboard")
                Text("Status: idle")
                    .accessibilityLabel("Job status")
                Text("History")
                    .accessibilityLabel("Job history")
                Button("Pause queue") {}
                    .accessibilityLabel("Pause queue")
                Text("Role \(role.rawValue). Loopback \(client.baseURL.absoluteString)")
            }
            .navigationTitle("WebMedia DL")
        }
    }
}
