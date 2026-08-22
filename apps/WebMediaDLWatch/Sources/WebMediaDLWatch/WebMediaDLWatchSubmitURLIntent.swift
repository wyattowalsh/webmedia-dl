import AppIntents
import WebMediaDLCore

/// watchOS App Intent: capture a URL for Mac relay. Not a subprocess worker.
/// Companion `capture` has no intake kind; the Mac classifies the locator as `url`.
public struct WebMediaDLWatchSubmitURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Send to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let transport = WebMediaDLWatchConnectivityTransport()
        let message = try WebMediaDLCompanionControlMessage.make(
            kind: .capture, locator: locator, surface: .watchos
        )
        try await transport.send(message)
        return .result(dialog: IntentDialog(stringLiteral: message.queuedStatus))
    }
}

public struct WebMediaDLWatchPauseIntent: AppIntent {
    public static let title: LocalizedStringResource = "Pause WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let transport = WebMediaDLWatchConnectivityTransport()
        let message = try WebMediaDLCompanionControlMessage.make(kind: .pause, surface: .watchos)
        try await transport.send(message)
        return .result(dialog: IntentDialog(stringLiteral: message.queuedStatus))
    }
}

public struct WebMediaDLWatchResumeIntent: AppIntent {
    public static let title: LocalizedStringResource = "Resume WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let transport = WebMediaDLWatchConnectivityTransport()
        let message = try WebMediaDLCompanionControlMessage.make(kind: .resume, surface: .watchos)
        try await transport.send(message)
        return .result(dialog: IntentDialog(stringLiteral: message.queuedStatus))
    }
}

public struct WebMediaDLWatchHistoryIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL history"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let transport = WebMediaDLWatchConnectivityTransport()
        let message = try WebMediaDLCompanionControlMessage.make(kind: .history, surface: .watchos)
        try await transport.send(message)
        return .result(dialog: IntentDialog(stringLiteral: message.queuedStatus))
    }
}

public struct WebMediaDLWatchStatusIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL status"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let transport = WebMediaDLWatchConnectivityTransport()
        let message = try WebMediaDLCompanionControlMessage.make(kind: .status, surface: .watchos)
        try await transport.send(message)
        return .result(dialog: IntentDialog(stringLiteral: message.queuedStatus))
    }
}

public struct WebMediaDLWatchCancelIntent: AppIntent {
    public static let title: LocalizedStringResource = "Cancel WebMedia DL"

    @Parameter(title: "Job ID")
    public var jobId: String

    public init() {}

    public init(jobId: String) {
        self.jobId = jobId
    }

    public func perform() async throws -> some IntentResult {
        let transport = WebMediaDLWatchConnectivityTransport()
        let message = try WebMediaDLCompanionControlMessage.make(kind: .cancel, jobId: jobId, surface: .watchos)
        try await transport.send(message)
        return .result(dialog: IntentDialog(stringLiteral: message.queuedStatus))
    }
}

public struct WebMediaDLWatchPauseJobIntent: AppIntent {
    public static let title: LocalizedStringResource = "Pause a WebMedia DL job"

    @Parameter(title: "Job ID")
    public var jobId: String

    public init() {}

    public init(jobId: String) {
        self.jobId = jobId
    }

    public func perform() async throws -> some IntentResult {
        let transport = WebMediaDLWatchConnectivityTransport()
        let message = try WebMediaDLCompanionControlMessage.make(kind: .pauseJob, jobId: jobId, surface: .watchos)
        try await transport.send(message)
        return .result(dialog: IntentDialog(stringLiteral: message.queuedStatus))
    }
}

public struct WebMediaDLWatchResumeJobIntent: AppIntent {
    public static let title: LocalizedStringResource = "Resume a WebMedia DL job"

    @Parameter(title: "Job ID")
    public var jobId: String

    public init() {}

    public init(jobId: String) {
        self.jobId = jobId
    }

    public func perform() async throws -> some IntentResult {
        let transport = WebMediaDLWatchConnectivityTransport()
        let message = try WebMediaDLCompanionControlMessage.make(kind: .resumeJob, jobId: jobId, surface: .watchos)
        try await transport.send(message)
        return .result(dialog: IntentDialog(stringLiteral: message.queuedStatus))
    }
}

public struct WebMediaDLWatchShortcuts: AppShortcutsProvider {
    public static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: WebMediaDLWatchSubmitURLIntent(),
            phrases: [
                "Speak a media URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
        AppShortcut(
            intent: WebMediaDLWatchPauseIntent(),
            phrases: [
                "Pause \(.applicationName)",
            ],
            shortTitle: "Pause WebMedia DL",
            systemImageName: "pause.circle"
        )
        AppShortcut(
            intent: WebMediaDLWatchResumeIntent(),
            phrases: [
                "Resume \(.applicationName)",
            ],
            shortTitle: "Resume WebMedia DL",
            systemImageName: "play.circle"
        )
        AppShortcut(
            intent: WebMediaDLWatchHistoryIntent(),
            phrases: [
                "Show \(.applicationName) history",
            ],
            shortTitle: "WebMedia DL history",
            systemImageName: "clock"
        )
        AppShortcut(
            intent: WebMediaDLWatchStatusIntent(),
            phrases: [
                "WebMedia DL status",
            ],
            shortTitle: "WebMedia DL status",
            systemImageName: "info.circle"
        )
        AppShortcut(
            intent: WebMediaDLWatchCancelIntent(),
            phrases: [
                "Cancel \(.applicationName)",
            ],
            shortTitle: "Cancel WebMedia DL",
            systemImageName: "xmark.circle"
        )
        AppShortcut(
            intent: WebMediaDLWatchPauseJobIntent(),
            phrases: [
                "Pause a \(.applicationName) job",
            ],
            shortTitle: "Pause a WebMedia DL job",
            systemImageName: "pause.circle"
        )
        AppShortcut(
            intent: WebMediaDLWatchResumeJobIntent(),
            phrases: [
                "Resume a \(.applicationName) job",
            ],
            shortTitle: "Resume a WebMedia DL job",
            systemImageName: "play.circle"
        )
    }
}
