# MirrorMind

**Before you mirror, know what you're showing.**

A Mac menu bar app that diagnoses AirPlay issues, scans your screen for privacy risks, and uses a local LLM to recommend the safest way to share your screen.

## What It Does

```
1. Diagnoses why AirPlay is not working
2. Shows exact fix steps in priority order
3. Checks network/VPN/firewall/display state
4. Scans visible windows for privacy risks
5. Recommends safest share mode (window/mirror/extend/HDMI)
6. Local LLM explains diagnosis and privacy assessment
7. Logs receipts of what was shown and when
```

## Architecture

```
MirrorMind.app
SwiftUI menu bar app (Mac M-series)
├── AirPlay Readiness Checker
│   ├── Wi-Fi power/state
│   ├── Network IP + subnet
│   ├── VPN detection (scutil)
│   ├── Firewall state (socketfilterfw)
│   ├── AirPlay Receiver settings
│   ├── TV discovery (Bonjour _airplay._tcp)
│   ├── Bluetooth state
│   ├── Screen capture permission (TCC)
│   └── Audio output
├── TV-Safe Scanner
│   ├── Visible window enumeration (CGWindowList)
│   ├── Risky app detection (Messages, Mail, banking, etc.)
│   ├── Browser/tab title keyword scan
│   ├── Terminal token-like string detection
│   └── Desktop/Downloads filename leakage
├── Local LLM (Ollama)
│   ├── Diagnose explanation
│   ├── Privacy assessment
│   └── Rule-based fallback if Ollama unavailable
├── Receipt Logger
│   ├── SHA-256 hashed receipts
│   ├── JSON persistence
│   └── 200-entry ring buffer
└── UI
    ├── Diagnose Mode
    ├── Safe Mirror Mode
    └── Receipts Mode
```

## Build

```bash
cd mirrormind
swift build
swift run MirrorMind
```

## LLM Setup (Optional)

MirrorMind works without an LLM using rule-based fallbacks. For AI-powered explanations:

```bash
# Install Ollama
brew install ollama
ollama serve

# Pull a model
ollama pull llama3.2
```

MirrorMind auto-detects Ollama at localhost:11434.

## What It Does NOT Do

```
Does not reverse-engineer AirPlay
Does not spoof receivers
Does not bypass Apple security prompts
Does not stream desktop to cloud LLMs
Does not automate Control Center UI
```

AirPlay moves pixels. MirrorMind decides whether the screen should be shown.

## Product Modes

```
Diagnose Mode      — Fix why TV does not appear or connect
Safe Mirror Mode   — Prevent private screen leakage
Receipts Mode      — Record what was shown, when, under what safety state
```

## Future

```
V2: TV-safe card renderer (big typography, no private details, QR handoff)
V3: Reality Wall bridge (stream proof cards to Samsung/Sony TV)
V4: Presentation mode (turn messy desktop into TV-safe cards)
```

## Status

```
MirrorMind v0.1
Status: MVP / pilot-ready
Build: passing (Swift 5.9, macOS 14+)
LLM: Ollama integration with rule-based fallback
```
