// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "WebMediaDLCore",
    platforms: [
        .macOS(.v14),
        .iOS(.v17),
        .tvOS(.v17),
        .watchOS(.v10),
        .visionOS(.v1),
    ],
    products: [
        .library(name: "WebMediaDLCore", targets: ["WebMediaDLCore"]),
    ],
    targets: [
        .target(name: "WebMediaDLCore"),
        .testTarget(name: "WebMediaDLCoreTests", dependencies: ["WebMediaDLCore"]),
    ]
)
