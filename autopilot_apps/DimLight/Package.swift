// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "DimLight",
    platforms: [.macOS("14.0")],
    targets: [
        .executableTarget(
            name: "DimLight",
            path: "Sources/DimLight"
        ),
    ]
)
