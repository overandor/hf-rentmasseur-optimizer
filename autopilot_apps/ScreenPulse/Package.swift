// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "ScreenPulse",
    platforms: [.macOS("14.0")],
    targets: [
        .executableTarget(
            name: "ScreenPulse",
            path: "Sources/ScreenPulse"
        ),
    ]
)
