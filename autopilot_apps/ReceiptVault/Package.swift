// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "ReceiptVault",
    platforms: [.macOS("14.0")],
    targets: [
        .executableTarget(
            name: "ReceiptVault",
            path: "Sources/ReceiptVault"
        ),
    ]
)
