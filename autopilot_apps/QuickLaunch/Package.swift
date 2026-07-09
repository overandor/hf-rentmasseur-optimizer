// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "QuickLaunch",
    platforms: [.macOS("14.0")],
    targets: [
        .executableTarget(
            name: "QuickLaunch",
            path: "Sources/QuickLaunch"
        ),
    ]
)
