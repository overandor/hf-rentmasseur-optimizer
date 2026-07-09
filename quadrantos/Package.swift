// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "QuadrantOS",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "QuadrantOS",
            path: "Sources/QuadrantOS"
        ),
        .testTarget(
            name: "QuadrantOSTests",
            dependencies: ["QuadrantOS"],
            path: "Tests/QuadrantOSTests"
        ),
    ]
)
