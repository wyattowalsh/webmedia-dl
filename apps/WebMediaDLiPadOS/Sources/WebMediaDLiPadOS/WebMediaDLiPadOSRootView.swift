import SwiftUI
import WebMediaDLCore

/// iPad complete client with a split inspector and paired-Mac heavy work.
public struct WebMediaDLiPadOSRootView: View {
    @State private var locator = ""
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
                Button("Send to paired Mac") {}
                    .accessibilityLabel("Send to paired Mac")
                Text("Role \(role.rawValue) at \(client.baseURL.absoluteString)")
                Spacer()
            }
            .padding()
        }
    }
}
