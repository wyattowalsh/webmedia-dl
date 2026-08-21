import SwiftUI
import WebMediaDLCore

/// iPhone complete client: lightweight local transfer plus paired-Mac heavy work.
public struct WebMediaDLiOSRootView: View {
    @State private var locator = ""
    @State private var pairingId = ""
    @State private var sessionKey = ""
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
                    Button("Send to paired Mac") {
                        Task {
                            status = (try? await client.submit(
                                locator: locator,
                                surface: .ios,
                                pairingId: UUID(uuidString: pairingId),
                                sessionKey: sessionKey.isEmpty ? nil : sessionKey
                            )) ?? "Pairing required"
                        }
                    }
                    .accessibilityLabel("Send to paired Mac")
                }
                Section("Pairing") {
                    TextField("Pairing id", text: $pairingId)
                        .textInputAutocapitalization(.never)
                        .accessibilityLabel("Pairing id")
                    SecureField("Session key", text: $sessionKey)
                        .accessibilityLabel("Session key")
                    Text("The Mac user must confirm pairing. This client cannot self-confirm.")
                }
                Section("Status") {
                    Text(status)
                        .accessibilityLabel("Job status")
                    Text("Role \(role.rawValue). Loopback \(client.baseURL.absoluteString)")
                }
                Section("History") {
                    Text("Lightweight HTTP jobs stay on-device. Heavy work waits for Mac confirmation.")
                        .accessibilityLabel("Job history")
                }
            }
            .navigationTitle("WebMedia DL")
        }
    }
}
