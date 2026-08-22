import AppIntents
import WebMediaDLCore

/// tvOS App Intent: capture a URL for Mac relay. Not a subprocess worker.
/// Companion `capture` has no intake kind; the Mac classifies the locator as `url`.
public struct WebMediaDLTVSubmitURLIntent: AppIntent {
    public static let title: LocalizedStringResource = "Send to WebMedia DL"

    @Parameter(title: "Media URL")
    public var locator: String

    public init() {}

    public init(locator: String) {
        self.locator = locator
    }

    public func perform() async throws -> some IntentResult {
        let bridge = WebMediaDLContinuityBridge()
        let transport = WebMediaDLLocalNetworkCompanionTransport()
        let message = bridge.message(kind: .capture, locator: locator, surface: .tvos)
        try await transport.send(message)
        return .result()
    }
}

public struct WebMediaDLTVPauseIntent: AppIntent {
    public static let title: LocalizedStringResource = "Pause WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let bridge = WebMediaDLContinuityBridge()
        let transport = WebMediaDLLocalNetworkCompanionTransport()
        try await transport.send(bridge.message(kind: .pause, surface: .tvos))
        return .result()
    }
}

public struct WebMediaDLTVResumeIntent: AppIntent {
    public static let title: LocalizedStringResource = "Resume WebMedia DL"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let bridge = WebMediaDLContinuityBridge()
        let transport = WebMediaDLLocalNetworkCompanionTransport()
        try await transport.send(bridge.message(kind: .resume, surface: .tvos))
        return .result()
    }
}

public struct WebMediaDLTVHistoryIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL history"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let bridge = WebMediaDLContinuityBridge()
        let transport = WebMediaDLLocalNetworkCompanionTransport()
        try await transport.send(bridge.message(kind: .history, surface: .tvos))
        return .result()
    }
}

public struct WebMediaDLTVStatusIntent: AppIntent {
    public static let title: LocalizedStringResource = "WebMedia DL status"

    public init() {}

    public func perform() async throws -> some IntentResult {
        let bridge = WebMediaDLContinuityBridge()
        let transport = WebMediaDLLocalNetworkCompanionTransport()
        try await transport.send(bridge.message(kind: .status, surface: .tvos))
        return .result()
    }
}

public struct WebMediaDLTVCancelIntent: AppIntent {
    public static let title: LocalizedStringResource = "Cancel WebMedia DL"

    @Parameter(title: "Job ID")
    public var jobId: String

    public init() {}

    public init(jobId: String) {
        self.jobId = jobId
    }

    public func perform() async throws -> some IntentResult {
        guard UUID(uuidString: jobId) != nil else { throw WebMediaDLCompanionError.jobIdRequired }
        let bridge = WebMediaDLContinuityBridge()
        let transport = WebMediaDLLocalNetworkCompanionTransport()
        try await transport.send(bridge.message(kind: .cancel, jobId: jobId, surface: .tvos))
        return .result()
    }
}

public struct WebMediaDLTVPauseJobIntent: AppIntent {
    public static let title: LocalizedStringResource = "Pause a WebMedia DL job"

    @Parameter(title: "Job ID")
    public var jobId: String

    public init() {}

    public init(jobId: String) {
        self.jobId = jobId
    }

    public func perform() async throws -> some IntentResult {
        guard UUID(uuidString: jobId) != nil else { throw WebMediaDLCompanionError.jobIdRequired }
        let bridge = WebMediaDLContinuityBridge()
        let transport = WebMediaDLLocalNetworkCompanionTransport()
        try await transport.send(bridge.message(kind: .pauseJob, jobId: jobId, surface: .tvos))
        return .result()
    }
}

public struct WebMediaDLTVResumeJobIntent: AppIntent {
    public static let title: LocalizedStringResource = "Resume a WebMedia DL job"

    @Parameter(title: "Job ID")
    public var jobId: String

    public init() {}

    public init(jobId: String) {
        self.jobId = jobId
    }

    public func perform() async throws -> some IntentResult {
        guard UUID(uuidString: jobId) != nil else { throw WebMediaDLCompanionError.jobIdRequired }
        let bridge = WebMediaDLContinuityBridge()
        let transport = WebMediaDLLocalNetworkCompanionTransport()
        try await transport.send(bridge.message(kind: .resumeJob, jobId: jobId, surface: .tvos))
        return .result()
    }
}

public struct WebMediaDLTVShortcuts: AppShortcutsProvider {
    public static var appShortcuts: [AppShortcut] {
        AppShortcut(
            intent: WebMediaDLTVSubmitURLIntent(),
            phrases: [
                "Speak a media URL to \(.applicationName)",
            ],
            shortTitle: "Send to WebMedia DL",
            systemImageName: "arrow.down.circle"
        )
        AppShortcut(
            intent: WebMediaDLTVPauseIntent(),
            phrases: [
                "Pause \(.applicationName)",
            ],
            shortTitle: "Pause WebMedia DL",
            systemImageName: "pause.circle"
        )
        AppShortcut(
            intent: WebMediaDLTVResumeIntent(),
            phrases: [
                "Resume \(.applicationName)",
            ],
            shortTitle: "Resume WebMedia DL",
            systemImageName: "play.circle"
        )
        AppShortcut(
            intent: WebMediaDLTVHistoryIntent(),
            phrases: [
                "Show \(.applicationName) history",
            ],
            shortTitle: "WebMedia DL history",
            systemImageName: "clock"
        )
        AppShortcut(
            intent: WebMediaDLTVStatusIntent(),
            phrases: [
                "WebMedia DL status",
            ],
            shortTitle: "WebMedia DL status",
            systemImageName: "info.circle"
        )
        AppShortcut(
            intent: WebMediaDLTVCancelIntent(),
            phrases: [
                "Cancel \(.applicationName)",
            ],
            shortTitle: "Cancel WebMedia DL",
            systemImageName: "xmark.circle"
        )
        AppShortcut(
            intent: WebMediaDLTVPauseJobIntent(),
            phrases: [
                "Pause a \(.applicationName) job",
            ],
            shortTitle: "Pause a WebMedia DL job",
            systemImageName: "pause.circle"
        )
        AppShortcut(
            intent: WebMediaDLTVResumeJobIntent(),
            phrases: [
                "Resume a \(.applicationName) job",
            ],
            shortTitle: "Resume a WebMedia DL job",
            systemImageName: "play.circle"
        )
    }
}
