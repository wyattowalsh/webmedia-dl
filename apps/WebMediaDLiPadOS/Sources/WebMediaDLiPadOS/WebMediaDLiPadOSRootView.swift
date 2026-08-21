import SwiftUI
import WebMediaDLCore

/// iPad complete client with a split inspector and paired-Mac heavy work.
public struct WebMediaDLiPadOSRootView: View {
    @State private var locator = ""
    @State private var status = "Pair with a Mac for yt-dlp and ffmpeg."
    private let role = WebMediaDLClientRole.pairedClient
    private let client = WebMediaDLLoopbackClient()

    public init() {}

    public var body: some View {
        NavigationSplitView {
            List {
                Text("Capture")
                Text("Status")
                Text("History")
            }
            .navigationTitle("WebMedia DL")
            .accessibilityLabel("WebMedia DL iPad sidebar")
        } detail: {
            VStack(alignment: .leading, spacing: 12) {
                TextField("Paste a media URL", text: $locator)
                    .accessibilityLabel("Media URL")
                    .textFieldStyle(.roundedBorder)
                Button("Send to paired Mac") {
                    Task {
                        status = (try? await client.submit(locator: locator, surface: .ipados))
                            ?? "Pairing required"
                    }
                }
                .accessibilityLabel("Send to paired Mac")
                Text(status)
                    .accessibilityLabel("Job status")
                Text("Role \(role.rawValue) at \(client.baseURL.absoluteString)")
                Spacer()
            }
            .padding()
        }
    }
}
