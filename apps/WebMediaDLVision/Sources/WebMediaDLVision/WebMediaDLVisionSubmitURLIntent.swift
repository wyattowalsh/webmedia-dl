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
            destinationKind: files == nil ? nil : "files_app",
            destinationPath: files?.approvedRoot,
            approvedRoots: files.map { [$0.approvedRoot] } ?? [],
            bookmarkData: files?.bookmark.bookmarkData ?? intake.bookmarkData
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
            destinationKind: files == nil ? nil : "files_app",
            destinationPath: files?.approvedRoot,
            approvedRoots: files.map { [$0.approvedRoot] } ?? [],
            bookmarkData: files?.bookmark.bookmarkData ?? intake.bookmarkData
        )
        return .result()
    }
}

public struct WebMediaDLVisionPauseQueueIntent: AppIntent {
    public static let title: LocalizedStringResource = "Pause WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLPairedMacSubmit.pauseQueue(
            credentials: WebMediaDLWorkerCredentials.loadClient()
        )
        return .result()
    }
}

public struct WebMediaDLVisionResumeQueueIntent: AppIntent {
    public static let title: LocalizedStringResource = "Resume WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLPairedMacSubmit.resumeQueue(
            credentials: WebMediaDLWorkerCredentials.loadClient()
        )
        return .result()
    }
}

public struct WebMediaDLVisionHistoryIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL history"

    public init() {}

    public func perform() async throws -> some IntentResult {
        _ = try await WebMediaDLPairedMacSubmit.history(
            credentials: WebMediaDLWorkerCredentials.loadClient()
        )
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
        guard let id = UUID(uuidString: jobId) else { return .result() }
        _ = try await WebMediaDLPairedMacSubmit.cancel(
            jobId: id,
            credentials: WebMediaDLWorkerCredentials.loadClient()
        )
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
            intent: WebMediaDLVisionCancelIntent(),
            phrases: [
                "Cancel \(.applicationName)",
            ],
            shortTitle: "Cancel WebMedia DL",
            systemImageName: "xmark.circle"
        )
    }
}
