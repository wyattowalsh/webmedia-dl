import AppIntents
import WebMediaDLCore

/// iOS App Intent: share, paste, or speak a URL to the paired Mac worker.
public struct WebMediaDLSubmitURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Send to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        if let saved = try await WebMediaDLHttpDirect.saveIfDirect(locator: locator, surface: .ios) {
            return .result(dialog: IntentDialog(stringLiteral: "Saved on this device \(saved.outputPath)"))
        }
        let intake = WebMediaDLShareIntake.fromSavedBookmark(locator: locator)
        let files = intake.filesDestination
        let response = try await WebMediaDLPairedMacSubmit.submit(
            locator: locator,
            surface: .ios,
            credentials: client,
            intakeKind: "intent",
            destinationKind: files == nil ? nil : "staging_only"
        )
        return .result(dialog: IntentDialog(stringLiteral: response))
    }
}

public struct WebMediaDLiOSSpeakURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Speak a media URL to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        if let saved = try await WebMediaDLHttpDirect.saveIfDirect(locator: locator, surface: .ios) {
            return .result(dialog: IntentDialog(stringLiteral: "Saved on this device \(saved.outputPath)"))
        }
        let intake = WebMediaDLShareIntake.fromSavedBookmark(locator: locator)
        let files = intake.filesDestination
        let response = try await WebMediaDLPairedMacSubmit.submit(
            locator: locator,
            surface: .ios,
            credentials: client,
            intakeKind: "speak",
            destinationKind: files == nil ? nil : "staging_only"
        )
        return .result(dialog: IntentDialog(stringLiteral: response))
    }
}

public struct WebMediaDLiOSPlanURLIntent: AppIntent {
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
            surface: .ios,
            credentials: client
        )
        return .result(dialog: IntentDialog(stringLiteral: status))
    }
}

public struct WebMediaDLiOSPauseQueueIntent: AppIntent {
    public static let title: LocalizedStringResource = "Pause WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let status = try await WebMediaDLCompleteClientControl.perform(.pauseQueue)
        return .result(dialog: IntentDialog(stringLiteral: status))
    }
}

public struct WebMediaDLiOSResumeQueueIntent: AppIntent {
    public static let title: LocalizedStringResource = "Resume WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let status = try await WebMediaDLCompleteClientControl.perform(.resumeQueue)
        return .result(dialog: IntentDialog(stringLiteral: status))
    }
}

public struct WebMediaDLiOSHistoryIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL history"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let status = try await WebMediaDLCompleteClientControl.perform(.history)
        return .result(dialog: IntentDialog(stringLiteral: status))
    }
}

public struct WebMediaDLiOSCancelIntent: AppIntent {
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

public struct WebMediaDLiOSStatusIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL status"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let status = try await WebMediaDLCompleteClientControl.perform(.queueStatus)
        return .result(dialog: IntentDialog(stringLiteral: status))
    }
}

public struct WebMediaDLiOSPauseJobIntent: AppIntent {
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

public struct WebMediaDLiOSResumeJobIntent: AppIntent {
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

public struct WebMediaDLiOSShortcuts: AppShortcutsProvider {
    public static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: WebMediaDLSubmitURLIntent(),
            phrases: [
                "Send this URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
        AppShortcut(
            intent: WebMediaDLiOSSpeakURLIntent(),
            phrases: [
                "Speak a media URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
        AppShortcut(
            intent: WebMediaDLiOSPlanURLIntent(),
            phrases: [
                "Explain this URL with \(.applicationName)",
            ],
            shortTitle: "Explain WebMedia DL plan",
            systemImageName: "list.bullet"
        )
        AppShortcut(
            intent: WebMediaDLiOSPauseQueueIntent(),
            phrases: [
                "Pause \(.applicationName)",
            ],
            shortTitle: "Pause WebMedia DL",
            systemImageName: "pause.circle"
        )
        AppShortcut(
            intent: WebMediaDLiOSResumeQueueIntent(),
            phrases: [
                "Resume \(.applicationName)",
            ],
            shortTitle: "Resume WebMedia DL",
            systemImageName: "play.circle"
        )
        AppShortcut(
            intent: WebMediaDLiOSHistoryIntent(),
            phrases: [
                "Show \(.applicationName) history",
            ],
            shortTitle: "WebMedia DL history",
            systemImageName: "clock"
        )
        AppShortcut(
            intent: WebMediaDLiOSStatusIntent(),
            phrases: [
                "WebMedia DL status",
            ],
            shortTitle: "WebMedia DL status",
            systemImageName: "info.circle"
        )
        AppShortcut(
            intent: WebMediaDLiOSCancelIntent(),
            phrases: [
                "Cancel \(.applicationName)",
            ],
            shortTitle: "Cancel WebMedia DL",
            systemImageName: "xmark.circle"
        )
        AppShortcut(
            intent: WebMediaDLiOSPauseJobIntent(),
            phrases: [
                "Pause a \(.applicationName) job",
            ],
            shortTitle: "Pause a WebMedia DL job",
            systemImageName: "pause.circle"
        )
        AppShortcut(
            intent: WebMediaDLiOSResumeJobIntent(),
            phrases: [
                "Resume a \(.applicationName) job",
            ],
            shortTitle: "Resume a WebMedia DL job",
            systemImageName: "play.circle"
        )
    }
}
