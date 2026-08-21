// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "WebMediaDLVision",
    platforms: [.visionOS(.v1)],
    products: [.library(name: "WebMediaDLVision", targets: ["WebMediaDLVision"])],
    dependencies: [.package(path: "../WebMediaDLCore")],
    targets: [
        .target(
            name: "WebMediaDLVision",
            dependencies: [.product(name: "WebMediaDLCore", package: "WebMediaDLCore")]
        ),
        .target(
            name: "WebMediaDLVisionShareExtension",
            dependencies: [.product(name: "WebMediaDLCore", package: "WebMediaDLCore")],
            path: "ShareExtension"
        ),
    ]
)
