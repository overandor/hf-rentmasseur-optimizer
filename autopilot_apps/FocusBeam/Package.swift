// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "FocusBeam",
    platforms: [.macOS("14.0")],
    targets: [
        .executableTarget(
            name: "FocusBeam",
            path: "Sources/FocusBeam"
        ),
    ]
)
