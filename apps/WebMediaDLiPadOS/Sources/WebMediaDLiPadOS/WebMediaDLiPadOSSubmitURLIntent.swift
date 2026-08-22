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
        if try await WebMediaDLHttpDirect.saveIfDirect(locator: locator, surface: .ipados) != nil {
            return .result()
        }
        let intake = WebMediaDLShareIntake.fromSavedBookmark(locator: locator)
        let files = intake.filesDestination
        _ = try await WebMediaDLPairedMacSubmit.submit(
            locator: locator,
            surface: .ipados,
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
        if try await WebMediaDLHttpDirect.saveIfDirect(locator: locator, surface: .ipados) != nil {
            return .result()
        }
        let intake = WebMediaDLShareIntake.fromSavedBookmark(locator: locator)
        let files = intake.filesDestination
        _ = try await WebMediaDLPairedMacSubmit.submit(
            locator: locator,
            surface: .ipados,
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

public struct WebMediaDLiPadOSPauseQueueIntent: AppIntent {
    public static let title: LocalizedStringResource = "Pause WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLPairedMacSubmit.pauseQueue(
            credentials: WebMediaDLWorkerCredentials.loadClient()
        )
        return .result()
    }
}

public struct WebMediaDLiPadOSResumeQueueIntent: AppIntent {
    public static let title: LocalizedStringResource = "Resume WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLPairedMacSubmit.resumeQueue(
            credentials: WebMediaDLWorkerCredentials.loadClient()
        )
        return .result()
    }
}

public struct WebMediaDLiPadOSHistoryIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL history"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLPairedMacSubmit.history(
            credentials: WebMediaDLWorkerCredentials.loadClient()
        )
        return .result()
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
        guard let id = UUID(uuidString: jobId) else { return .result() }
        _ = try await WebMediaDLPairedMacSubmit.cancel(
            jobId: id,
            credentials: WebMediaDLWorkerCredentials.loadClient()
        )
        return .result()
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
            intent: WebMediaDLiPadOSCancelIntent(),
            phrases: [
                "Cancel \(.applicationName)",
            ],
            shortTitle: "Cancel WebMedia DL",
            systemImageName: "xmark.circle"
        )
    }
}
