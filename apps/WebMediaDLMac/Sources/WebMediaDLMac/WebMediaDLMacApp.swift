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
                    Button("Refresh history") {
                        Task { await refreshHistory() }
                    }
                    .accessibilityLabel("Refresh history")
                }
                Section("Queue") {
                    Button("Pause queue") {
                        _ = WebMediaDLLoopbackClient(token: token).pauseQueueRequest()
                        status = "Pause requested"
                    }
                    .accessibilityLabel("Pause queue")
                    Button("Resume queue") {
                        _ = WebMediaDLLoopbackClient(token: token).resumeQueueRequest()
                        status = "Resume requested"
                    }
                    .accessibilityLabel("Resume queue")
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
            historyText = try await client.history()
        } catch {
            status = error.localizedDescription
        }
    }

    @MainActor
    private func refreshHistory() async {
        let client = WebMediaDLLoopbackClient(token: token)
        do {
            historyText = try await client.history()
        } catch {
            historyText = error.localizedDescription
        }
    }
}
