// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "SnapBarrier",
    platforms: [.macOS("14.0")],
    targets: [
        .executableTarget(
            name: "SnapBarrier",
            path: "Sources/SnapBarrier"
        ),
    ]
)
