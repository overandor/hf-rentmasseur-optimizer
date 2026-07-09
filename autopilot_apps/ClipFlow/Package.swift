// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "ClipFlow",
    platforms: [.macOS("14.0")],
    targets: [
        .executableTarget(
            name: "ClipFlow",
            path: "Sources/ClipFlow"
        ),
    ]
)
