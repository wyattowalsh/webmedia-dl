import SwiftUI
import WebMediaDLCore

/// iPad complete client with a split inspector and paired-Mac heavy work.
public struct WebMediaDLiPadOSRootView: View {
    @State private var locator = ""
    @State private var pairingId = ""
    @State private var sessionKey = ""
    @State private var status = "Pair with a Mac for yt-dlp and ffmpeg."
    @State private var historyText = "Paired Mac history appears after confirmation."
    private let role = WebMediaDLClientRole.pairedClient
    private let client = WebMediaDLLoopbackClient()

    public init() {}

    private var pairedClient: WebMediaDLLoopbackClient {
        WebMediaDLLoopbackClient(
            pairingId: UUID(uuidString: pairingId),
            sessionKey: sessionKey.isEmpty ? nil : sessionKey
        )
    }

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
                        status = (try? await pairedClient.submit(
                            locator: locator,
                            surface: .ipados,
                            pairingId: UUID(uuidString: pairingId),
                            sessionKey: sessionKey.isEmpty ? nil : sessionKey
                        )) ?? "Pairing required"
                    }
                }
                .accessibilityLabel("Send to paired Mac")
                TextField("Pairing id", text: $pairingId)
                    .accessibilityLabel("Pairing id")
                SecureField("Session key", text: $sessionKey)
                    .accessibilityLabel("Session key")
                Text(status)
                    .accessibilityLabel("Job status")
                Text(historyText)
                    .accessibilityLabel("Job history")
                Button("Refresh history") {
                    Task {
                        historyText = (try? await pairedClient.history()) ?? "Pairing required"
                    }
                }
                .accessibilityLabel("Refresh history")
                Text("Role \(role.rawValue) at \(client.baseURL.absoluteString)")
                Spacer()
            }
            .padding()
        }
    }
}
