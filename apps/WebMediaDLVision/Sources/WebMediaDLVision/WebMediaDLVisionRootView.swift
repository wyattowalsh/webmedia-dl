import SwiftUI
import WebMediaDLCore

/// visionOS complete client: immersive capture plus paired-Mac heavy work.
public struct WebMediaDLVisionRootView: View {
    @State private var locator = ""
    private let role = WebMediaDLClientRole.pairedClient
    private let client = WebMediaDLLoopbackClient()

    public init() {}

    public var body: some View {
        VStack(spacing: 16) {
            Text("WebMedia DL")
                .font(.largeTitle)
                .accessibilityAddTraits(.isHeader)
            TextField("Paste a media URL", text: $locator)
                .accessibilityLabel("Media URL")
            Button("Send to paired Mac") {}
                .accessibilityLabel("Send to paired Mac")
            Text("Role \(role.rawValue). Loopback \(client.baseURL.absoluteString)")
                .accessibilityLabel("Job status")
        }
        .padding(32)
    }
}
