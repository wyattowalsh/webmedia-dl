// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "WebMediaDLWatch",
    platforms: [.watchOS(.v10)],
    products: [.library(name: "WebMediaDLWatch", targets: ["WebMediaDLWatch"])],
    dependencies: [.package(path: "../WebMediaDLCore")],
    targets: [
        .target(
            name: "WebMediaDLWatch",
            dependencies: [.product(name: "WebMediaDLCore", package: "WebMediaDLCore")]
        ),
    ]
)
