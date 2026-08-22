import Foundation

/// macOS hosts the loopback Python worker. Complete clients never spawn it.
public enum WebMediaDLMacWorkerProcess {
    public static let executableName = "webmedia-dl"
    public static let loopbackHost   = "127.0.0.1"
    public static let loopbackPort   = 8765

    public static func serveArguments(dataDir: String) -> [String] {
        [
            "serve",
            "--host", loopbackHost,
            "--port", String(loopbackPort),
            "--data-dir", dataDir,
        ]
    }

    public static func executableURL(
        pathEnvironment: String? = ProcessInfo.processInfo.environment["PATH"]
    ) -> URL? {
        let path = pathEnvironment ?? ""
        for directory in path.split(separator: ":") {
            let candidate = URL(fileURLWithPath: String(directory), isDirectory: true)
                .appendingPathComponent(executableName)
            if FileManager.default.isExecutableFile(atPath: candidate.path) {
                return candidate
            }
        }
        return nil
    }

    #if os(macOS)
    public static func defaultDataDirectory() -> URL {
        FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library", isDirectory: true)
            .appendingPathComponent("Application Support", isDirectory: true)
            .appendingPathComponent("WebMedia DL", isDirectory: true)
    }

    @discardableResult
    public static func start(dataDir: URL, executable: URL? = nil) throws -> AnyObject {
        guard let binary = executable ?? executableURL() else {
            throw WebMediaDLDomainError(
                "webmedia-dl is not on PATH; start the loopback worker before pairing clients."
            )
        }
        try FileManager.default.createDirectory(at: dataDir, withIntermediateDirectories: true)
        guard let taskClass = NSClassFromString("NSTask") as? NSObject.Type else {
            throw WebMediaDLDomainError("host process launcher is unavailable")
        }
        let task = taskClass.init()
        task.setValue(binary.path, forKey: "launchPath")
        task.setValue(serveArguments(dataDir: dataDir.path), forKey: "arguments")
        task.setValue(FileHandle.nullDevice, forKey: "standardOutput")
        task.setValue(FileHandle.nullDevice, forKey: "standardError")
        let launch = NSSelectorFromString("launch")
        guard task.responds(to: launch) else {
            throw WebMediaDLDomainError("host process launcher cannot start")
        }
        task.perform(launch)
        return task
    }

    public static func terminate(_ process: AnyObject?) {
        guard let process else { return }
        let selector = NSSelectorFromString("terminate")
        if process.responds(to: selector) {
            process.perform(selector)
        }
    }
#endif
}

/// Mac app launches `webmedia-dl serve` or claims a healthy existing loopback worker.
public enum WebMediaDLMacWorkerLaunch {
    case started(AnyObject)
    case claimedExisting(spawnError: String)
}

public enum WebMediaDLMacWorkerSupervision {
    public static func startOrClaimExisting(
        start: () throws -> AnyObject,
        health: @Sendable () async throws -> Void
    ) async throws -> WebMediaDLMacWorkerLaunch {
        do {
            return .started(try start())
        } catch {
            let spawnError = error
            do {
                try await health()
                return .claimedExisting(spawnError: spawnError.localizedDescription)
            } catch {
                throw spawnError
            }
        }
    }
}
