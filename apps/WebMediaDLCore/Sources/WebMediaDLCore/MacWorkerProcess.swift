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
    public static func start(dataDir: URL, executable: URL? = nil) throws -> Process {
        guard let binary = executable ?? executableURL() else {
            throw WebMediaDLDomainError(
                "webmedia-dl is not on PATH; start the loopback worker before pairing clients."
            )
        }
        try FileManager.default.createDirectory(at: dataDir, withIntermediateDirectories: true)
        let process = Process()
        process.executableURL = binary
        process.arguments = serveArguments(dataDir: dataDir.path)
        process.standardOutput = FileHandle.nullDevice
        process.standardError = FileHandle.nullDevice
        try process.run()
        return process
    }
    #endif
}
