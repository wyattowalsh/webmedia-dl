// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "WebMediaDLiPadOS",
    platforms: [.iOS(.v17)],
    products: [
        .executable(name: "WebMediaDLiPadOS", targets: ["WebMediaDLiPadOS"]),
        .library(name: "WebMediaDLiPadOSShareExtension", targets: ["WebMediaDLiPadOSShareExtension"]),
    ],
    dependencies: [.package(path: "../WebMediaDLCore")],
    targets: [
        .executableTarget(
            name: "WebMediaDLiPadOS",
            dependencies: [
                .product(name: "WebMediaDLCore", package: "WebMediaDLCore"),
                "WebMediaDLiPadOSShareExtension",
            ]
        ),
        .target(
            name: "WebMediaDLiPadOSShareExtension",
            dependencies: [.product(name: "WebMediaDLCore", package: "WebMediaDLCore")],
            path: "ShareExtension",
            exclude: ["Info.plist", "WebMediaDL.entitlements"]
        ),
    ]
)
