# AirPlay Agent

A macOS app that splits your screen in half:
- **Left half**: Agent delegation interface — send tasks to LLM agents, see status, browse task log
- **Right half**: Agent stage — large, TV-friendly display of live agent output with streaming

Powered by **Ollama** for local LLM inference. No cloud, no API keys, no mocks.

## AirPlay to Your TV

1. Click the AirPlay button (top-right toolbar)
2. Select your Apple TV
3. macOS extends your display to the TV
4. The app automatically detects the AirPlay display and opens a full-screen stage window on the TV
5. Only the agent output is shown on the TV — your delegation controls stay private on your Mac

## Requirements

- macOS 14.0+ (Sonoma or later)
- Xcode Command Line Tools (`xcode-select --install`)
- [Ollama](https://ollama.ai) installed and running (`ollama serve`)
- At least one Ollama model pulled (`ollama pull llama3`)
- Apple TV or AirPlay-compatible TV (optional, for TV streaming)

## Build & Run

```bash
cd airplay_agent
make run
```

Or build only:

```bash
make
open build/AirPlayAgent.app
```

## Architecture

```
Sources/AirPlayAgent/
├── AirPlayAgentApp.swift       — App entry point (@main)
├── ContentView.swift           — Split view + toolbar with AirPlay, settings, connection status
├── AgentDelegationView.swift   — Left half: task input, agent list, task log, streaming indicator
├── AgentStageView.swift        — Right half: large TV-friendly agent output with streaming state
├── AirPlayManager.swift        — Detects AirPlay displays, routes stage window to TV
├── AgentModel.swift            — ObservableObject: real Ollama delegation, streaming, persistence
├── LLMClient.swift             — Ollama API client: streaming chat, model discovery, error handling
└── SettingsView.swift          — Settings sheet: Ollama URL, model picker, connection test
```

## How It Works

1. On launch, the app connects to your local Ollama server and fetches available models
2. Type a task in the left panel and hit send — it delegates to an agent via Ollama's streaming chat API
3. Response tokens stream in real-time to both the right half (your Mac) and the TV (via AirPlay)
4. **AirPlayManager** monitors `NSScreen.didChangeScreenParametersNotification`
5. When an AirPlay display appears (detected by screen name containing "AirPlay", "Apple TV", or "TV"), it creates a borderless `NSPanel` on that display
6. The panel hosts an `AgentStageView` that mirrors the current agent output
7. When AirPlay disconnects, the stage window closes automatically

## Settings

Click the gear icon in the toolbar to open Settings:
- **Ollama URL**: defaults to `http://localhost:11434`, change if Ollama runs elsewhere
- **Model selection**: pick from models installed in your Ollama instance
- **Test connection**: verify Ollama is reachable before saving
- Settings persist across launches via UserDefaults

## App Store Readiness

- `PrivacyInfo.xcprivacy` — privacy manifest declaring no data collection
- `Info.plist` — proper version, category, copyright, usage descriptions, ATS for local networking
- `AirPlayAgent.entitlements` — network client entitlement for Ollama communication
- No sandbox (requires local network access to Ollama)
- No data collection, no tracking, no third-party SDKs

## Troubleshooting

- **"Disconnected" status**: Make sure Ollama is running (`ollama serve`) and the URL in Settings matches
- **No models in picker**: Pull a model first (`ollama pull llama3`)
- **AirPlay button not showing**: Ensure you're on macOS 14+ and AirPlay is enabled in System Settings > General > AirDrop & Handoff
- **TV not detected**: Make sure your Mac and Apple TV are on the same Wi-Fi network
- **Stage window not appearing on TV**: Click the refresh button in the toolbar to recheck displays
- **Build fails**: Run `xcode-select --install` to ensure Command Line Tools are installed
