import SwiftUI
import AppKit
import UniformTypeIdentifiers
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
    @State private var sessionKey = ""
    @State private var status = "Ready"
    @State private var historyText = "Jobs appear after the loopback worker accepts them."
    @State private var history: [WebMediaDLHistoryEntry] = []
    @State private var companionLocator = ""
    @State private var companionRelay = WebMediaDLCompanionRelay()
    @State private var lastJobId: UUID?
    @State private var approvedRoot = ""
    @State private var filesBookmark = WebMediaDLSecurityScopedBookmark(path: "")
    @State private var fromClipboard = false
    @State private var advertisedAddresses = "Mac relay is starting…"
    @State private var relayServer: WebMediaDLMacRelayServer?
    @State private var workerProcess: AnyObject?
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
                    Button("Explain plan") {
                        Task { await explainPlan() }
                    }
                    .accessibilityLabel("Explain plan")
                    Button("Paste from clipboard") {
                        #if os(macOS)
                        if let text = NSPasteboard.general.string(forType: .string) {
                            let clip = WebMediaDLClipboardIntake(text: text)
                            locator = clip.locator ?? text.trimmingCharacters(in: .whitespacesAndNewlines)
                            fromClipboard = true
                        }
                        #endif
                    }
                    .accessibilityLabel("Paste from clipboard")
                    Button("Choose Files destination") {
                        chooseFilesDestination()
                    }
                    .accessibilityLabel("Choose Files destination")
                    if !approvedRoot.isEmpty {
                        Text(approvedRoot)
                            .accessibilityLabel("Approved Files destination")
                    }
                }
                Section("Status") {
                    Text(status)
                        .accessibilityElement()
                        .accessibilityLabel("Job status")
                    Text("Worker: \(role.rawValue) at \(WebMediaDLLoopbackClient.defaultBaseURL.absoluteString)")
                    Button("Worker doctor") {
                        Task {
                            do {
                                status = try await WebMediaDLLoopbackClient(token: token).doctor()
                            } catch {
                                status = error.localizedDescription
                            }
                        }
                    }
                    .accessibilityLabel("Worker doctor")
                }
                Section("History") {
                    Text(historyText)
                        .accessibilityLabel("Job history")
                    List(history) { entry in
                        Text("\(entry.jobId.uuidString.prefix(8)) \(entry.state)")
                            .accessibilityLabel("History row")
                    }
                    Button("Refresh history") {
                        Task { await refreshHistory() }
                    }
                    .accessibilityLabel("Refresh history")
                    Button("Show artifacts") {
                        Task {
                            do {
                                status = try await WebMediaDLLoopbackClient(token: token).artifacts()
                            } catch {
                                status = error.localizedDescription
                            }
                        }
                    }
                    .accessibilityLabel("Show artifacts")
                    Button("Show last job") {
                        Task {
                            guard let lastJobId else {
                                status = "No job to inspect"
                                return
                            }
                            do {
                                status = try await WebMediaDLLoopbackClient(token: token).jobDetail(jobId: lastJobId)
                            } catch {
                                status = error.localizedDescription
                            }
                        }
                    }
                    .accessibilityLabel("Show last job")
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
                    Button("Queue status") {
                        Task {
                            do {
                                status = try await WebMediaDLLoopbackClient(token: token).queueStatus()
                            } catch {
                                status = error.localizedDescription
                            }
                        }
                    }
                    .accessibilityLabel("Queue status")
                    Button("Cancel last job") {
                        Task {
                            guard let lastJobId else {
                                status = "No job to cancel"
                                return
                            }
                            do {
                                status = try await WebMediaDLLoopbackClient(token: token).cancel(jobId: lastJobId)
                            } catch {
                                status = error.localizedDescription
                            }
                        }
                    }
                    .accessibilityLabel("Cancel last job")
                    Button("Pause last job") {
                        Task {
                            guard let lastJobId else {
                                status = "No job to pause"
                                return
                            }
                            do {
                                status = try await WebMediaDLLoopbackClient(token: token).pauseJob(jobId: lastJobId)
                            } catch {
                                status = error.localizedDescription
                            }
                        }
                    }
                    .accessibilityLabel("Pause last job")
                    Button("Resume last job") {
                        Task {
                            guard let lastJobId else {
                                status = "No job to resume"
                                return
                            }
                            do {
                                status = try await WebMediaDLLoopbackClient(token: token).resumeJob(jobId: lastJobId)
                            } catch {
                                status = error.localizedDescription
                            }
                        }
                    }
                    .accessibilityLabel("Resume last job")
                }
                Section("Paired devices") {
                    Text(advertisedAddresses)
                        .textSelection(.enabled)
                        .accessibilityLabel("This Mac's address")
                    Text("Paste a private LAN or loopback URL on iPhone, iPad, or visionOS.")
                }
                Section("Pairing") {
                    TextField("Pairing id to confirm", text: $pairingId)
                        .accessibilityLabel("Pairing id")
                    SecureField("Pairing session key", text: $sessionKey)
                        .accessibilityLabel("Pairing session key")
                    Button("Confirm pairing") {
                        Task {
                            guard let id = UUID(uuidString: pairingId) else {
                                status = "Pairing id is not a UUID"
                                return
                            }
                            do {
                                let response = try await WebMediaDLLoopbackClient(token: token).confirmPairing(id)
                                status = response
                                if let key = WebMediaDLLoopbackClient.sessionKey(from: response) {
                                    sessionKey = key
                                }
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
                            do {
                                let client = WebMediaDLLoopbackClient(
                                    token: token,
                                    pairingId: UUID(uuidString: pairingId),
                                    sessionKey: sessionKey.isEmpty ? nil : sessionKey
                                )
                                var forwarder = WebMediaDLMacCompanionForwarder(client: client)
                                var relay = companionRelay
                                forwarder.receiveWatchConnectivityUserInfo(
                                    ["kind": "capture", "locator": companionLocator, "surface": "watchos"],
                                    into: &relay
                                )
                                if let id = UUID(uuidString: pairingId), !pairingId.isEmpty, !sessionKey.isEmpty {
                                    let bodies = try await forwarder.forwardSealed(
                                        relay,
                                        pairingId: id,
                                        sessionKey: sessionKey
                                    )
                                    status = bodies.last ?? "Forwarded companion capture"
                                } else {
                                    let bodies = try await forwarder.forward(relay)
                                    status = bodies.last ?? "Forwarded companion capture"
                                }
                                companionRelay = WebMediaDLCompanionRelay()
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
            .onDrop(of: [UTType.fileURL], isTargeted: nil) { providers in
                handleDrop(providers)
            }
            .accessibilityLabel("Drop media files")
            .onAppear {
                let defaults = WebMediaDLWorkerCredentials.defaults()
                if token.isEmpty {
                    token = defaults.string(forKey: WebMediaDLWorkerCredentials.tokenDefaultsKey) ?? ""
                }
                if pairingId.isEmpty {
                    pairingId = defaults.string(forKey: WebMediaDLWorkerCredentials.pairingDefaultsKey) ?? ""
                }
                if sessionKey.isEmpty {
                    sessionKey = defaults.string(forKey: WebMediaDLWorkerCredentials.sessionDefaultsKey) ?? ""
                }
                if let data = WebMediaDLWorkerCredentials.loadBookmark() {
                    filesBookmark = WebMediaDLSecurityScopedBookmark(path: "", bookmarkData: data).resolve()
                    approvedRoot = filesBookmark.path
                }
                startMacWorker()
                Task { await startMacRelay() }
            }
            .onDisappear {
                WebMediaDLMacWorkerProcess.terminate(workerProcess)
                relayServer?.stop()
            }
            .onChange(of: token) { _, value in
                WebMediaDLWorkerCredentials.defaults().set(value, forKey: WebMediaDLWorkerCredentials.tokenDefaultsKey)
                relayServer?.loopbackToken = value
            }
            .onChange(of: pairingId) { _, value in
                WebMediaDLWorkerCredentials.defaults().set(value, forKey: WebMediaDLWorkerCredentials.pairingDefaultsKey)
            }
            .onChange(of: sessionKey) { _, value in
                WebMediaDLWorkerCredentials.defaults().set(value, forKey: WebMediaDLWorkerCredentials.sessionDefaultsKey)
            }
        }
        .frame(minWidth: 480, minHeight: 320)
    }

    @MainActor
    private func startMacWorker() {
        Task {
            do {
                let launch = try await WebMediaDLMacWorkerSupervision.startOrClaimExisting(
                    start: {
                        WebMediaDLUncheckedBox(
                            try WebMediaDLMacWorkerProcess.start(
                                dataDir: WebMediaDLMacWorkerProcess.defaultDataDirectory()
                            )
                        )
                    },
                    health: { try await WebMediaDLLoopbackClient().requireHealthyWorker() }
                )
                await MainActor.run {
                    switch launch {
                    case .started(let process):
                        workerProcess = process
                        status = "Local worker started on \(WebMediaDLLoopbackClient.defaultBaseURL.absoluteString)"
                    case .claimedExisting(let spawnError):
                        status = "Using existing loopback worker (\(spawnError))"
                    }
                }
            } catch {
                await MainActor.run {
                    status = error.localizedDescription
                }
            }
        }
    }

    @MainActor
    private func startMacRelay() async {
        do {
            let server = try await WebMediaDLMacRelayServer.start(
                bindHost: "0.0.0.0",
                port: WebMediaDLMacRelayServer.defaultPort,
                localOnly: false,
                loopbackToken: token
            )
            relayServer = server
            let pasted = server.clientPasteURLs.map(\.absoluteString).joined(separator: "\n")
            advertisedAddresses = pasted.isEmpty ? server.advertisedURL.absoluteString : pasted
        } catch {
            advertisedAddresses = "Mac relay failed: \(error.localizedDescription)"
        }
    }

    @MainActor
    private func submit() async {
        let client = WebMediaDLLoopbackClient(token: token)
        let clip = WebMediaDLClipboardIntake(text: locator)
        let files = filesBookmark.path.isEmpty
            ? nil
            : WebMediaDLFilesDestination(bookmark: filesBookmark)
        do {
            status = try await client.submit(
                locator: clip.locator ?? locator,
                surface: .macos,
                intakeKind: fromClipboard ? clip.intakeKind : nil,
                destinationKind: files == nil ? nil : "files_app",
                destinationPath: files?.approvedRoot,
                approvedRoots: files.map { [$0.approvedRoot] } ?? [],
                bookmarkData: filesBookmark.bookmarkData
            )
            lastJobId = WebMediaDLLoopbackClient.jobId(from: status)
            await refreshHistory()
        } catch {
            status = error.localizedDescription
        }
    }

    @MainActor
    private func explainPlan() async {
        let client = WebMediaDLLoopbackClient(token: token)
        let clip = WebMediaDLClipboardIntake(text: locator)
        do {
            status = try await client.plan(
                locator: clip.locator ?? locator,
                surface: .macos
            )
        } catch {
            status = error.localizedDescription
        }
    }

    private func chooseFilesDestination() {
        #if os(macOS)
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.message = "Choose a WebMedia DL Files destination"
        guard panel.runModal() == .OK, let url = panel.url else { return }
        let accessed = url.startAccessingSecurityScopedResource()
        filesBookmark = WebMediaDLSecurityScopedBookmark.fromPickedURL(url).resolve()
        approvedRoot = filesBookmark.path
        if let data = filesBookmark.bookmarkData {
            WebMediaDLWorkerCredentials.defaults().set(data, forKey: WebMediaDLWorkerCredentials.bookmarkDefaultsKey)
        }
        if accessed {
            url.stopAccessingSecurityScopedResource()
        }
        #endif
    }

    @MainActor
    private func submitDropped(path: String) async {
        let client = WebMediaDLLoopbackClient(token: token)
        do {
            status = try await client.submit(
                locator: path,
                surface: .macos,
                intakeKind: "drop"
            )
            lastJobId = WebMediaDLLoopbackClient.jobId(from: status)
            await refreshHistory()
        } catch {
            status = error.localizedDescription
        }
    }

    private func handleDrop(_ providers: [NSItemProvider]) -> Bool {
        guard let provider = providers.first else { return false }
        _ = provider.loadObject(ofClass: URL.self) { url, _ in
            guard let url, url.isFileURL else { return }
            Task { @MainActor in
                locator = url.path
                await submitDropped(path: url.path)
            }
        }
        return true
    }

    @MainActor
    private func refreshHistory() async {
        let client = WebMediaDLLoopbackClient(token: token)
        do {
            history = try await client.historyEntries()
            historyText = WebMediaDLHistoryEntry.summary(history)
        } catch {
            historyText = error.localizedDescription
        }
    }
}
