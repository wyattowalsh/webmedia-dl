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
    @State private var pairingId = ""
    @State private var status = "Ready"
    @State private var historyText = "Jobs appear after the loopback worker accepts them."
    @State private var companionLocator = ""
    private let role = WebMediaDLClientRole.fullWorker
    private let bridge = WebMediaDLContinuityBridge()

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
                        Task {
                            do {
                                status = try await WebMediaDLLoopbackClient(token: token).pauseQueue()
                            } catch {
                                status = error.localizedDescription
                            }
                        }
                    }
                    .accessibilityLabel("Pause queue")
                    Button("Resume queue") {
                        Task {
                            do {
                                status = try await WebMediaDLLoopbackClient(token: token).resumeQueue()
                            } catch {
                                status = error.localizedDescription
                            }
                        }
                    }
                    .accessibilityLabel("Resume queue")
                }
                Section("Pairing") {
                    TextField("Pairing id to confirm", text: $pairingId)
                        .accessibilityLabel("Pairing id")
                    Button("Confirm pairing") {
                        Task {
                            guard let id = UUID(uuidString: pairingId) else {
                                status = "Pairing id is not a UUID"
                                return
                            }
                            do {
                                status = try await WebMediaDLLoopbackClient(token: token).confirmPairing(id)
                            } catch {
                                status = error.localizedDescription
                            }
                        }
                    }
                    .accessibilityLabel("Confirm pairing")
                    Text("Restricted clients cannot self-confirm.")
                }
                Section("Companion") {
                    TextField("Watch or TV locator", text: $companionLocator)
                        .accessibilityLabel("Companion locator")
                    Button("Forward companion capture") {
                        Task {
                            _ = bridge.message(kind: "capture", locator: companionLocator)
                            do {
                                status = try await WebMediaDLLoopbackClient(token: token).forwardCompanion(
                                    kind: "capture",
                                    locator: companionLocator
                                )
                            } catch {
                                status = error.localizedDescription
                            }
                        }
                    }
                    .accessibilityLabel("Forward companion capture")
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
