// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ScreenMirrorPro",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "ScreenMirrorPro", targets: ["ScreenMirrorPro"]),
    ],
    targets: [
        .executableTarget(
            name: "ScreenMirrorPro",
            path: "Sources/ScreenMirrorPro"
        ),
    ]
)
