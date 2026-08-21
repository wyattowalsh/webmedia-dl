import SwiftUI
import WebMediaDLCore

@main
struct WebMediaDLMacApp: App {
    var body: some Scene {
        WindowGroup {
            MacRootView()
        }
    }
}

struct MacRootView: View {
    @State private var locator = ""
    @State private var token = ""
    @State private var status = "Ready"
    @State private var historyText = "Jobs appear after the loopback worker accepts them."
    private let role = WebMediaDLClientRole.fullWorker

    var body: some View {
        NavigationStack {
            Form {
                Section("Capture") {
                    TextField("Paste a media URL", text: $locator)
                        .textFieldStyle(.roundedBorder)
                        .accessibilityLabel("Media URL")
                    SecureField("Worker token", text: $token)
                        .accessibilityLabel("Worker token")
                    Button("Submit to local worker") {
                        Task { await submit() }
                    }
                    .accessibilityLabel("Submit to local worker")
                    .keyboardShortcut(.defaultAction)
                }
                Section("Status") {
                    Text(status)
                        .accessibilityElement()
                        .accessibilityLabel("Job status")
                    Text("Worker: \(role.rawValue) at \(WebMediaDLLoopbackClient.defaultBaseURL.absoluteString)")
                }
                Section("History") {
                    Text(historyText)
                        .accessibilityLabel("Job history")
                }
            }
            .navigationTitle("WebMedia DL")
            .padding()
        }
        .frame(minWidth: 480, minHeight: 320)
    }

    @MainActor
    private func submit() async {
        let client = WebMediaDLLoopbackClient(token: token)
        do {
            status = try await client.submit(locator: locator, surface: .macos)
        } catch {
            status = error.localizedDescription
        }
    }
}
