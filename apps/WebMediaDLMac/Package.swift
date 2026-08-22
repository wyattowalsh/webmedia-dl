// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "WebMediaDLMac",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "WebMediaDLMac", targets: ["WebMediaDLMac"]),
        .library(name: "WebMediaDLMacShareExtension", targets: ["WebMediaDLMacShareExtension"]),
    ],
    dependencies: [.package(path: "../WebMediaDLCore")],
    targets: [
        .executableTarget(
            name: "WebMediaDLMac",
            dependencies: [
                .product(name: "WebMediaDLCore", package: "WebMediaDLCore"),
                "WebMediaDLMacShareExtension",
            ]
        ),
        .target(
            name: "WebMediaDLMacShareExtension",
            dependencies: [.product(name: "WebMediaDLCore", package: "WebMediaDLCore")],
            path: "ShareExtension",
            exclude: ["Info.plist", "WebMediaDL.entitlements", "PrivacyInfo.xcprivacy"]
        ),
    ]
)
