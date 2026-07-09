// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "GlyphBoard",
    platforms: [.macOS("14.0")],
    targets: [
        .executableTarget(
            name: "GlyphBoard",
            path: "Sources/GlyphBoard"
        ),
    ]
)
