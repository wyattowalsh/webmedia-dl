import AppIntents
import WebMediaDLCore

/// macOS App Intent: paste, speak, or share a URL to the local worker. No provider argv.
public struct WebMediaDLMacSubmitURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Send to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        let intake = WebMediaDLShareIntake.fromSavedBookmark(locator: locator)
        let files = intake.filesDestination
        _ = try await client.submit(
            locator: locator,
            surface: .macos,
            intakeKind: "intent",
            destinationKind: files == nil ? nil : "files_app",
            destinationPath: files?.approvedRoot,
            approvedRoots: files.map { [$0.approvedRoot] } ?? [],
            bookmarkData: files?.bookmark.bookmarkData ?? intake.bookmarkData
        )
        return .result()
    }
}

public struct WebMediaDLMacSpeakURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Speak a media URL to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let client = WebMediaDLWorkerCredentials.loadClient()
        let intake = WebMediaDLShareIntake.fromSavedBookmark(locator: locator)
        let files = intake.filesDestination
        _ = try await client.submit(
            locator: locator,
            surface: .macos,
            intakeKind: "speak",
            destinationKind: files == nil ? nil : "files_app",
            destinationPath: files?.approvedRoot,
            approvedRoots: files.map { [$0.approvedRoot] } ?? [],
            bookmarkData: files?.bookmark.bookmarkData ?? intake.bookmarkData
        )
        return .result()
    }
}

public struct WebMediaDLMacPauseQueueIntent: AppIntent {
    public static let title: LocalizedStringResource = "Pause WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLWorkerCredentials.loadClient().pauseQueue()
        return .result()
    }
}

public struct WebMediaDLMacResumeQueueIntent: AppIntent {
    public static let title: LocalizedStringResource = "Resume WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLWorkerCredentials.loadClient().resumeQueue()
        return .result()
    }
}

public struct WebMediaDLMacHistoryIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL history"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLWorkerCredentials.loadClient().history()
        return .result()
    }
}

public struct WebMediaDLMacCancelIntent: AppIntent {
    public static let title: LocalizedStringResource = "Cancel WebMedia DL"

    @Parameter(title: "Job ID")
    public var jobId: String

    public init() {}

    public init(jobId: String) {
        self.jobId = jobId
    }

    public func perform() async throws -> some IntentResult {
        guard let id = UUID(uuidString: jobId) else { throw WebMediaDLCompanionError.jobIdRequired }
        _ = try await WebMediaDLWorkerCredentials.loadClient().cancel(jobId: id)
        return .result()
    }
}

public struct WebMediaDLMacStatusIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL status"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLWorkerCredentials.loadClient().queueStatus()
        return .result()
    }
}

public struct WebMediaDLMacPauseJobIntent: AppIntent {
    public static let title: LocalizedStringResource = "Pause a WebMedia DL job"

    @Parameter(title: "Job ID")
    public var jobId: String

    public init() {}

    public init(jobId: String) {
        self.jobId = jobId
    }

    public func perform() async throws -> some IntentResult {
        guard let id = UUID(uuidString: jobId) else { throw WebMediaDLCompanionError.jobIdRequired }
        _ = try await WebMediaDLWorkerCredentials.loadClient().pauseJob(jobId: id)
        return .result()
    }
}

public struct WebMediaDLMacResumeJobIntent: AppIntent {
    public static let title: LocalizedStringResource = "Resume a WebMedia DL job"

    @Parameter(title: "Job ID")
    public var jobId: String

    public init() {}

    public init(jobId: String) {
        self.jobId = jobId
    }

    public func perform() async throws -> some IntentResult {
        guard let id = UUID(uuidString: jobId) else { throw WebMediaDLCompanionError.jobIdRequired }
        _ = try await WebMediaDLWorkerCredentials.loadClient().resumeJob(jobId: id)
        return .result()
    }
}

public struct WebMediaDLMacShortcuts: AppShortcutsProvider {
    public static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: WebMediaDLMacSubmitURLIntent(),
            phrases: [
                "Send this URL to \(.applicationName)",
                "Download with \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
        AppShortcut(
            intent: WebMediaDLMacSpeakURLIntent(),
            phrases: [
                "Speak a media URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
        AppShortcut(
            intent: WebMediaDLMacPauseQueueIntent(),
            phrases: [
                "Pause \(.applicationName)",
            ],
            shortTitle: "Pause WebMedia DL",
            systemImageName: "pause.circle"
        )
        AppShortcut(
            intent: WebMediaDLMacResumeQueueIntent(),
            phrases: [
                "Resume \(.applicationName)",
            ],
            shortTitle: "Resume WebMedia DL",
            systemImageName: "play.circle"
        )
        AppShortcut(
            intent: WebMediaDLMacHistoryIntent(),
            phrases: [
                "Show \(.applicationName) history",
            ],
            shortTitle: "WebMedia DL history",
            systemImageName: "clock"
        )
        AppShortcut(
            intent: WebMediaDLMacStatusIntent(),
            phrases: [
                "WebMedia DL status",
            ],
            shortTitle: "WebMedia DL status",
            systemImageName: "info.circle"
        )
        AppShortcut(
            intent: WebMediaDLMacCancelIntent(),
            phrases: [
                "Cancel \(.applicationName)",
            ],
            shortTitle: "Cancel WebMedia DL",
            systemImageName: "xmark.circle"
        )
        AppShortcut(
            intent: WebMediaDLMacPauseJobIntent(),
            phrases: [
                "Pause a \(.applicationName) job",
            ],
            shortTitle: "Pause a WebMedia DL job",
            systemImageName: "pause.circle"
        )
        AppShortcut(
            intent: WebMediaDLMacResumeJobIntent(),
            phrases: [
                "Resume a \(.applicationName) job",
            ],
            shortTitle: "Resume a WebMedia DL job",
            systemImageName: "play.circle"
        )
    }
}
