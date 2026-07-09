// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "NetSignal",
    platforms: [.macOS("14.0")],
    targets: [
        .executableTarget(
            name: "NetSignal",
            path: "Sources/NetSignal"
        ),
    ]
)
