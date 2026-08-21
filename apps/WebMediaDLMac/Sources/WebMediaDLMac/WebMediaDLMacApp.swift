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
    @State private var status = "Ready"
    private let client = WebMediaDLLoopbackClient()
    private let role = WebMediaDLClientRole.fullWorker

    var body: some View {
        NavigationStack {
            Form {
                Section("Capture") {
                    TextField("Paste a media URL", text: $locator)
                        .textFieldStyle(.roundedBorder)
                        .accessibilityLabel("Media URL")
                    Button("Submit to local worker") {}
                        .accessibilityLabel("Submit to local worker")
                        .keyboardShortcut(.defaultAction)
                }
                Section("Status") {
                    Text(status)
                        .accessibilityElement()
                        .accessibilityLabel("Job status")
                    Text("Worker: \(role.rawValue) at \(client.baseURL.absoluteString)")
                }
                Section("History") {
                    Text("Jobs appear after the loopback worker accepts them.")
                }
            }
            .navigationTitle("WebMedia DL")
            .padding()
        }
        .frame(minWidth: 480, minHeight: 320)
    }
}
