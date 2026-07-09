# ProofWallet Concierge

Native macOS/iOS app — Core ML + MLX powered life-proof concierge.

## Architecture

```
proofwallet_concierge/
├── Package.swift                          — Swift Package Manager (mlx-swift dep)
└── Sources/ProofWalletConcierge/
    ├── ProofWalletConciergeApp.swift      — SwiftUI app, theme, tab bar, home view
    ├── ProofModels.swift                  — Codable models matching Python backend
    ├── APIClient.swift                    — Async HTTP client for FastAPI backend
    ├── CoreMLClassifier.swift             — On-device NLP classification + extraction
    ├── MLXEngine.swift                    — MLX inference: chat, summary, reasoning, letters
    ├── ConciergeStore.swift               — Central observable state store
    └── Views.swift                        — Items, Alerts, Chain, Packets, Capture, Chat
```

## Features

### Core ML Classifier (`CoreMLClassifier.swift`)
- On-device document classification using `NaturalLanguage` framework
- 17 proof types: receipt, warranty, subscription, cancellation, refund, chargeback, etc.
- NLP-based merchant extraction (organization name tagging)
- Regex-based amount, date, and deadline hint extraction
- Auto-tagging: recurring, disputed, warranty, urgent

### MLX Engine (`MLXEngine.swift`)
- Concierge chat with intent detection
- Smart wallet summarization
- Deadline urgency reasoning
- Dispute letter drafting (refund, cancellation, chargeback, warranty, general)
- Action routing: capture, build packet, view deadlines, resolve

### SwiftUI Glassmorphic UI
- 430px iPhone-width app shell, centered on desktop
- `.ultraThinMaterial` glass cards with `backdrop-filter` blur
- Ambient breathing background (orange/purple radial gradients)
- Bottom tab bar: Home, Items, Alerts, Chain, Packets
- Floating action buttons: Capture (orange) + Concierge chat (purple)
- Bottom sheet modals with drag handles
- Live Core ML extraction preview during capture
- Concierge chat with thinking animation

## Build

```bash
cd proofwallet_concierge
swift build
```

## Run

Start the backend first:
```bash
python3 proofwallet.py serve --port 7860
```

Then run the app:
```bash
swift run ProofWalletConcierge
```

## Dependencies

- **mlx-swift** (0.12.1+) — Apple's MLX framework for on-device inference
- **NaturalLanguage** — Core ML NLP tagging
- **SwiftUI** — Glassmorphic UI with `.ultraThinMaterial`
- macOS 14+ / iOS 17+
