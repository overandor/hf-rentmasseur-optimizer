// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "CleanSweep",
    platforms: [.macOS("14.0")],
    targets: [
        .executableTarget(
            name: "CleanSweep",
            path: "Sources/CleanSweep"
        ),
    ]
)
