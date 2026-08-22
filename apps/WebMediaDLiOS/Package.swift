// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "WebMediaDLiOS",
    platforms: [.iOS(.v17)],
    products: [.executable(name: "WebMediaDLiOS", targets: ["WebMediaDLiOS"])],
    dependencies: [.package(path: "../WebMediaDLCore")],
    targets: [
        .executableTarget(
            name: "WebMediaDLiOS",
            dependencies: [.product(name: "WebMediaDLCore", package: "WebMediaDLCore")]
        ),
        .target(
            name: "WebMediaDLiOSShareExtension",
            dependencies: [.product(name: "WebMediaDLCore", package: "WebMediaDLCore")],
            path: "ShareExtension",
            exclude: ["Info.plist", "WebMediaDL.entitlements"]
        ),
    ]
)
