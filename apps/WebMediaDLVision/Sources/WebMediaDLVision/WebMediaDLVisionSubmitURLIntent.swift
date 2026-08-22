import AppIntents
import WebMediaDLCore

/// visionOS App Intent: share, paste, or speak a URL to the paired Mac worker.
public struct WebMediaDLVisionSubmitURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Send to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        if try await WebMediaDLHttpDirect.saveIfDirect(locator: locator, surface: .visionos) != nil {
            return .result()
        }
        let intake = WebMediaDLShareIntake.fromSavedBookmark(locator: locator)
        let files = intake.filesDestination
        _ = try await WebMediaDLPairedMacSubmit.submit(
            locator: locator,
            surface: .visionos,
            credentials: client,
            intakeKind: "intent",
            destinationKind: files == nil ? nil : "staging_only"
        )
        return .result()
    }
}

public struct WebMediaDLVisionSpeakURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Speak a media URL to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        if try await WebMediaDLHttpDirect.saveIfDirect(locator: locator, surface: .visionos) != nil {
            return .result()
        }
        let intake = WebMediaDLShareIntake.fromSavedBookmark(locator: locator)
        let files = intake.filesDestination
        _ = try await WebMediaDLPairedMacSubmit.submit(
            locator: locator,
            surface: .visionos,
            credentials: client,
            intakeKind: "speak",
            destinationKind: files == nil ? nil : "staging_only"
        )
        return .result()
    }
}

public struct WebMediaDLVisionPauseQueueIntent: AppIntent {
    public static let title: LocalizedStringResource = "Pause WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLCompleteClientControl.perform(.pauseQueue)
        return .result()
    }
}

public struct WebMediaDLVisionResumeQueueIntent: AppIntent {
    public static let title: LocalizedStringResource = "Resume WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLCompleteClientControl.perform(.resumeQueue)
        return .result()
    }
}

public struct WebMediaDLVisionHistoryIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL history"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLCompleteClientControl.perform(.history)
        return .result()
    }
}

public struct WebMediaDLVisionCancelIntent: AppIntent {
    public static let title: LocalizedStringResource = "Cancel WebMedia DL"

    @Parameter(title: "Job ID")
    public var jobId: String

    public init() {}

    public init(jobId: String) {
        self.jobId = jobId
    }

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLCompleteClientControl.perform(.cancel, jobId: jobId)
        return .result()
    }
}

public struct WebMediaDLVisionStatusIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL status"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLCompleteClientControl.perform(.queueStatus)
        return .result()
    }
}

public struct WebMediaDLVisionPauseJobIntent: AppIntent {
    public static let title: LocalizedStringResource = "Pause a WebMedia DL job"

    @Parameter(title: "Job ID")
    public var jobId: String

    public init() {}

    public init(jobId: String) {
        self.jobId = jobId
    }

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLCompleteClientControl.perform(.pauseJob, jobId: jobId)
        return .result()
    }
}

public struct WebMediaDLVisionResumeJobIntent: AppIntent {
    public static let title: LocalizedStringResource = "Resume a WebMedia DL job"

    @Parameter(title: "Job ID")
    public var jobId: String

    public init() {}

    public init(jobId: String) {
        self.jobId = jobId
    }

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLCompleteClientControl.perform(.resumeJob, jobId: jobId)
        return .result()
    }
}

public struct WebMediaDLVisionShortcuts: AppShortcutsProvider {
    public static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: WebMediaDLVisionSubmitURLIntent(),
            phrases: [
                "Send this URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
        AppShortcut(
            intent: WebMediaDLVisionSpeakURLIntent(),
            phrases: [
                "Speak a media URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
        AppShortcut(
            intent: WebMediaDLVisionPauseQueueIntent(),
            phrases: [
                "Pause \(.applicationName)",
            ],
            shortTitle: "Pause WebMedia DL",
            systemImageName: "pause.circle"
        )
        AppShortcut(
            intent: WebMediaDLVisionResumeQueueIntent(),
            phrases: [
                "Resume \(.applicationName)",
            ],
            shortTitle: "Resume WebMedia DL",
            systemImageName: "play.circle"
        )
        AppShortcut(
            intent: WebMediaDLVisionHistoryIntent(),
            phrases: [
                "Show \(.applicationName) history",
            ],
            shortTitle: "WebMedia DL history",
            systemImageName: "clock"
        )
        AppShortcut(
            intent: WebMediaDLVisionStatusIntent(),
            phrases: [
                "WebMedia DL status",
            ],
            shortTitle: "WebMedia DL status",
            systemImageName: "info.circle"
        )
        AppShortcut(
            intent: WebMediaDLVisionCancelIntent(),
            phrases: [
                "Cancel \(.applicationName)",
            ],
            shortTitle: "Cancel WebMedia DL",
            systemImageName: "xmark.circle"
        )
        AppShortcut(
            intent: WebMediaDLVisionPauseJobIntent(),
            phrases: [
                "Pause a \(.applicationName) job",
            ],
            shortTitle: "Pause a WebMedia DL job",
            systemImageName: "pause.circle"
        )
        AppShortcut(
            intent: WebMediaDLVisionResumeJobIntent(),
            phrases: [
                "Resume a \(.applicationName) job",
            ],
            shortTitle: "Resume a WebMedia DL job",
            systemImageName: "play.circle"
        )
    }
}
