// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "WebMediaDLiPadOS",
    platforms: [.iOS(.v17)],
    products: [.library(name: "WebMediaDLiPadOS", targets: ["WebMediaDLiPadOS"])],
    dependencies: [.package(path: "../WebMediaDLCore")],
    targets: [
        .target(
            name: "WebMediaDLiPadOS",
            dependencies: [.product(name: "WebMediaDLCore", package: "WebMediaDLCore")]
        ),
        .target(
            name: "WebMediaDLiPadOSShareExtension",
            dependencies: [.product(name: "WebMediaDLCore", package: "WebMediaDLCore")],
            path: "ShareExtension"
        ),
    ]
)
