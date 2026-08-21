import SwiftUI
import WebMediaDLCore

/// visionOS complete client: immersive capture plus paired-Mac heavy work.
public struct WebMediaDLVisionRootView: View {
    @State private var locator = ""
    @State private var status = "Pair with a Mac for heavy work."
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
            Button("Send to paired Mac") {
                Task {
                    status = (try? await client.submit(locator: locator, surface: .visionos))
                        ?? "Pairing required"
                }
            }
            .accessibilityLabel("Send to paired Mac")
            Text(status)
                .accessibilityLabel("Job status")
            Text("Role \(role.rawValue). Loopback \(client.baseURL.absoluteString)")
        }
        .padding(32)
    }
}
