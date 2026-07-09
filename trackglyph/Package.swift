// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "TrackGlyphKit",
    platforms: [.macOS(.v14)],
    targets: [
        .executableTarget(
            name: "TrackGlyph",
            path: "Sources/TrackGlyph"
        ),
    ]
)
