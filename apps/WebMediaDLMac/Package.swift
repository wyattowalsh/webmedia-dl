// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "WebMediaDLMac",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "WebMediaDLMac", targets: ["WebMediaDLMac"])],
    dependencies: [.package(path: "../WebMediaDLCore")],
    targets: [
        .executableTarget(
            name: "WebMediaDLMac",
            dependencies: [.product(name: "WebMediaDLCore", package: "WebMediaDLCore")]
        ),
    ]
)
