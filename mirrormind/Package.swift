// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "MirrorMind",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "MirrorMind",
            path: "Sources/MirrorMind"
        ),
    ]
)
