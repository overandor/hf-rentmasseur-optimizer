// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ProofPulse",
    platforms: [.iOS(.v17)],
    products: [
        .library(name: "ProofPulse", targets: ["ProofPulse"]),
    ],
    targets: [
        .target(
            name: "ProofPulse",
            path: "Sources/ProofPulse"
        ),
    ]
)
