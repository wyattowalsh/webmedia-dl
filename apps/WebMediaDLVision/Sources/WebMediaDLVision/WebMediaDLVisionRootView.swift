import SwiftUI
import WebMediaDLCore

/// visionOS complete client: immersive capture plus paired-Mac heavy work.
public struct WebMediaDLVisionRootView: View {
    @State private var locator = ""
    @State private var pairingId = ""
    @State private var sessionKey = ""
    @State private var status = "Pair with a Mac for heavy work."
    @State private var historyText = "Paired Mac history appears after confirmation."
    @State private var lastJobId: UUID?
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
        VStack(spacing: 16) {
            Text("WebMedia DL")
                .font(.largeTitle)
                .accessibilityAddTraits(.isHeader)
            TextField("Paste a media URL", text: $locator)
                .accessibilityLabel("Media URL")
            Button("Send to paired Mac") {
                Task {
                    let response = (try? await pairedClient.submit(
                        locator: locator,
                        surface: .visionos,
                        pairingId: UUID(uuidString: pairingId),
                        sessionKey: sessionKey.isEmpty ? nil : sessionKey
                    )) ?? "Pairing required"
                    status = response
                    lastJobId = WebMediaDLLoopbackClient.jobId(from: response)
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
            Button("Cancel last job") {
                Task {
                    guard let lastJobId else {
                        status = "No job to cancel"
                        return
                    }
                    status = (try? await pairedClient.cancel(jobId: lastJobId)) ?? "Pairing required"
                }
            }
            .accessibilityLabel("Cancel last job")
            Text("Role \(role.rawValue). Loopback \(client.baseURL.absoluteString)")
        }
        .padding(32)
    }
}
