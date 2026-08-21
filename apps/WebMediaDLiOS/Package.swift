// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "WebMediaDLiOS",
    platforms: [.iOS(.v17)],
    products: [.library(name: "WebMediaDLiOS", targets: ["WebMediaDLiOS"])],
    dependencies: [.package(path: "../WebMediaDLCore")],
    targets: [
        .target(
            name: "WebMediaDLiOS",
            dependencies: [.product(name: "WebMediaDLCore", package: "WebMediaDLCore")]
        ),
        .target(
            name: "WebMediaDLiOSShareExtension",
            dependencies: [.product(name: "WebMediaDLCore", package: "WebMediaDLCore")],
            path: "ShareExtension"
        ),
    ]
)
