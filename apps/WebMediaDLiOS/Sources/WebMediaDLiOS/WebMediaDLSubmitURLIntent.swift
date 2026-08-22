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
        if try await WebMediaDLHttpDirect.saveIfDirect(locator: locator, surface: .ios) != nil {
            return .result()
        }
        let intake = WebMediaDLShareIntake.fromSavedBookmark(locator: locator)
        let files = intake.filesDestination
        _ = try await WebMediaDLPairedMacSubmit.submit(
            locator: locator,
            surface: .ios,
            credentials: client,
            intakeKind: "intent",
            destinationKind: files == nil ? nil : "files_app",
            destinationPath: files?.approvedRoot,
            approvedRoots: files.map { [$0.approvedRoot] } ?? [],
            bookmarkData: files?.bookmark.bookmarkData ?? intake.bookmarkData
        )
        return .result()
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
        if try await WebMediaDLHttpDirect.saveIfDirect(locator: locator, surface: .ios) != nil {
            return .result()
        }
        let intake = WebMediaDLShareIntake.fromSavedBookmark(locator: locator)
        let files = intake.filesDestination
        _ = try await WebMediaDLPairedMacSubmit.submit(
            locator: locator,
            surface: .ios,
            credentials: client,
            intakeKind: "speak",
            destinationKind: files == nil ? nil : "files_app",
            destinationPath: files?.approvedRoot,
            approvedRoots: files.map { [$0.approvedRoot] } ?? [],
            bookmarkData: files?.bookmark.bookmarkData ?? intake.bookmarkData
        )
        return .result()
    }
}

public struct WebMediaDLiOSPauseQueueIntent: AppIntent {
    public static let title: LocalizedStringResource = "Pause WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLPairedMacSubmit.pauseQueue(
            credentials: WebMediaDLWorkerCredentials.loadClient()
        )
        return .result()
    }
}

public struct WebMediaDLiOSResumeQueueIntent: AppIntent {
    public static let title: LocalizedStringResource = "Resume WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLPairedMacSubmit.resumeQueue(
            credentials: WebMediaDLWorkerCredentials.loadClient()
        )
        return .result()
    }
}

public struct WebMediaDLiOSHistoryIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL history"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLPairedMacSubmit.history(
            credentials: WebMediaDLWorkerCredentials.loadClient()
        )
        return .result()
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
        guard let id = UUID(uuidString: jobId) else { return .result() }
        _ = try await WebMediaDLPairedMacSubmit.cancel(
            jobId: id,
            credentials: WebMediaDLWorkerCredentials.loadClient()
        )
        return .result()
    }
}

public struct WebMediaDLiOSStatusIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL status"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLPairedMacSubmit.queueStatus(
            credentials: WebMediaDLWorkerCredentials.loadClient()
        )
        return .result()
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
        guard let id = UUID(uuidString: jobId) else { return .result() }
        _ = try await WebMediaDLPairedMacSubmit.pauseJob(
            jobId: id,
            credentials: WebMediaDLWorkerCredentials.loadClient()
        )
        return .result()
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
        guard let id = UUID(uuidString: jobId) else { return .result() }
        _ = try await WebMediaDLPairedMacSubmit.resumeJob(
            jobId: id,
            credentials: WebMediaDLWorkerCredentials.loadClient()
        )
        return .result()
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
