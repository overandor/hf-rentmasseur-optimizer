// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "ProofWalletConcierge",
    platforms: [.macOS(.v14), .iOS(.v17)],
    products: [
        .executable(name: "ProofWalletConcierge", targets: ["ProofWalletConcierge"]),
    ],
    dependencies: [
        .package(url: "https://github.com/ml-explore/mlx-swift", from: "0.12.1"),
    ],
    targets: [
        .executableTarget(
            name: "ProofWalletConcierge",
            dependencies: [
                .product(name: "MLX", package: "mlx-swift"),
                .product(name: "MLXNN", package: "mlx-swift"),
                .product(name: "MLXOptimizers", package: "mlx-swift"),
            ],
            path: "Sources/ProofWalletConcierge"
        ),
    ]
)
