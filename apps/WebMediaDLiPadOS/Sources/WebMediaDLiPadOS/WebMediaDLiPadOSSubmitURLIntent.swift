import AppIntents
import WebMediaDLCore

/// iPadOS App Intent: share, paste, or speak a URL to the paired Mac worker.
public struct WebMediaDLiPadOSSubmitURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Send to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        if let saved = try await WebMediaDLHttpDirect.saveIfDirect(locator: locator, surface: .ipados) {
            return .result(dialog: IntentDialog(stringLiteral: "Saved on this device \(saved.outputPath)"))
        }
        let intake = WebMediaDLShareIntake.fromSavedBookmark(locator: locator)
        let files = intake.filesDestination
        let response = try await WebMediaDLPairedMacSubmit.submit(
            locator: locator,
            surface: .ipados,
            credentials: client,
            intakeKind: "intent",
            destinationKind: files == nil ? nil : "staging_only"
        )
        return .result(dialog: IntentDialog(stringLiteral: response))
    }
}

public struct WebMediaDLiPadOSSpeakURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Speak a media URL to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        if let saved = try await WebMediaDLHttpDirect.saveIfDirect(locator: locator, surface: .ipados) {
            return .result(dialog: IntentDialog(stringLiteral: "Saved on this device \(saved.outputPath)"))
        }
        let intake = WebMediaDLShareIntake.fromSavedBookmark(locator: locator)
        let files = intake.filesDestination
        let response = try await WebMediaDLPairedMacSubmit.submit(
            locator: locator,
            surface: .ipados,
            credentials: client,
            intakeKind: "speak",
            destinationKind: files == nil ? nil : "staging_only"
        )
        return .result(dialog: IntentDialog(stringLiteral: response))
    }
}

public struct WebMediaDLiPadOSPlanURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Explain a WebMedia DL plan"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        let status = try await WebMediaDLPairedMacSubmit.plan(
            locator: locator,
            surface: .ipados,
            credentials: client
        )
        return .result(dialog: IntentDialog(stringLiteral: status))
    }
}

public struct WebMediaDLiPadOSPauseQueueIntent: AppIntent {
    public static let title: LocalizedStringResource = "Pause WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let status = try await WebMediaDLCompleteClientControl.perform(.pauseQueue)
        return .result(dialog: IntentDialog(stringLiteral: status))
    }
}

public struct WebMediaDLiPadOSResumeQueueIntent: AppIntent {
    public static let title: LocalizedStringResource = "Resume WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let status = try await WebMediaDLCompleteClientControl.perform(.resumeQueue)
        return .result(dialog: IntentDialog(stringLiteral: status))
    }
}

public struct WebMediaDLiPadOSHistoryIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL history"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let status = try await WebMediaDLCompleteClientControl.perform(.history)
        return .result(dialog: IntentDialog(stringLiteral: status))
    }
}

public struct WebMediaDLiPadOSCancelIntent: AppIntent {
    public static let title: LocalizedStringResource = "Cancel WebMedia DL"

    @Parameter(title: "Job ID")
    public var jobId: String

    public init() {}

    public init(jobId: String) {
        self.jobId = jobId
    }

    public func perform() async throws -> some IntentResult {
        let status = try await WebMediaDLCompleteClientControl.perform(.cancel, jobId: jobId)
        return .result(dialog: IntentDialog(stringLiteral: status))
    }
}

public struct WebMediaDLiPadOSStatusIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL status"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let status = try await WebMediaDLCompleteClientControl.perform(.queueStatus)
        return .result(dialog: IntentDialog(stringLiteral: status))
    }
}

public struct WebMediaDLiPadOSPauseJobIntent: AppIntent {
    public static let title: LocalizedStringResource = "Pause a WebMedia DL job"

    @Parameter(title: "Job ID")
    public var jobId: String

    public init() {}

    public init(jobId: String) {
        self.jobId = jobId
    }

    public func perform() async throws -> some IntentResult {
        let status = try await WebMediaDLCompleteClientControl.perform(.pauseJob, jobId: jobId)
        return .result(dialog: IntentDialog(stringLiteral: status))
    }
}

public struct WebMediaDLiPadOSResumeJobIntent: AppIntent {
    public static let title: LocalizedStringResource = "Resume a WebMedia DL job"

    @Parameter(title: "Job ID")
    public var jobId: String

    public init() {}

    public init(jobId: String) {
        self.jobId = jobId
    }

    public func perform() async throws -> some IntentResult {
        let status = try await WebMediaDLCompleteClientControl.perform(.resumeJob, jobId: jobId)
        return .result(dialog: IntentDialog(stringLiteral: status))
    }
}

public struct WebMediaDLiPadOSShortcuts: AppShortcutsProvider {
    public static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: WebMediaDLiPadOSSubmitURLIntent(),
            phrases: [
                "Send this URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
        AppShortcut(
            intent: WebMediaDLiPadOSSpeakURLIntent(),
            phrases: [
                "Speak a media URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
        AppShortcut(
            intent: WebMediaDLiPadOSPlanURLIntent(),
            phrases: [
                "Explain this URL with \(.applicationName)",
            ],
            shortTitle: "Explain WebMedia DL plan",
            systemImageName: "list.bullet"
        )
        AppShortcut(
            intent: WebMediaDLiPadOSPauseQueueIntent(),
            phrases: [
                "Pause \(.applicationName)",
            ],
            shortTitle: "Pause WebMedia DL",
            systemImageName: "pause.circle"
        )
        AppShortcut(
            intent: WebMediaDLiPadOSResumeQueueIntent(),
            phrases: [
                "Resume \(.applicationName)",
            ],
            shortTitle: "Resume WebMedia DL",
            systemImageName: "play.circle"
        )
        AppShortcut(
            intent: WebMediaDLiPadOSHistoryIntent(),
            phrases: [
                "Show \(.applicationName) history",
            ],
            shortTitle: "WebMedia DL history",
            systemImageName: "clock"
        )
        AppShortcut(
            intent: WebMediaDLiPadOSStatusIntent(),
            phrases: [
                "WebMedia DL status",
            ],
            shortTitle: "WebMedia DL status",
            systemImageName: "info.circle"
        )
        AppShortcut(
            intent: WebMediaDLiPadOSCancelIntent(),
            phrases: [
                "Cancel \(.applicationName)",
            ],
            shortTitle: "Cancel WebMedia DL",
            systemImageName: "xmark.circle"
        )
        AppShortcut(
            intent: WebMediaDLiPadOSPauseJobIntent(),
            phrases: [
                "Pause a \(.applicationName) job",
            ],
            shortTitle: "Pause a WebMedia DL job",
            systemImageName: "pause.circle"
        )
        AppShortcut(
            intent: WebMediaDLiPadOSResumeJobIntent(),
            phrases: [
                "Resume a \(.applicationName) job",
            ],
            shortTitle: "Resume a WebMedia DL job",
            systemImageName: "play.circle"
        )
    }
}
