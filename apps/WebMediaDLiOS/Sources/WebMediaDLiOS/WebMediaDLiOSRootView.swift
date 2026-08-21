import SwiftUI
import WebMediaDLCore

/// iPhone complete client: lightweight local transfer plus paired-Mac heavy work.
public struct WebMediaDLiOSRootView: View {
    @State private var locator = ""
    @State private var status = "Pair with a Mac to run yt-dlp or ffmpeg jobs."
    private let client = WebMediaDLLoopbackClient()
    private let role = WebMediaDLClientRole.pairedClient

    public init() {}

    public var body: some View {
        NavigationStack {
            Form {
                Section("Capture") {
                    TextField("Share or paste a URL", text: $locator)
                        .textInputAutocapitalization(.never)
                        .accessibilityLabel("Media URL")
                    Button("Send to paired Mac") {}
                        .accessibilityLabel("Send to paired Mac")
                }
                Section("Status") {
                    Text(status)
                        .accessibilityLabel("Job status")
                    Text("Role \(role.rawValue). Loopback \(client.baseURL.absoluteString)")
                }
                Section("History") {
                    Text("Lightweight HTTP jobs stay on-device. Heavy work waits for Mac confirmation.")
                }
            }
            .navigationTitle("WebMedia DL")
        }
    }
}
