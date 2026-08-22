// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "WebMediaDLTV",
    platforms: [.tvOS(.v17)],
    products: [.executable(name: "WebMediaDLTV", targets: ["WebMediaDLTV"])],
    dependencies: [.package(path: "../WebMediaDLCore")],
    targets: [
        .executableTarget(
            name: "WebMediaDLTV",
            dependencies: [.product(name: "WebMediaDLCore", package: "WebMediaDLCore")]
        ),
    ]
)
