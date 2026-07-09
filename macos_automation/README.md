# MacOS Automation Library

The most comprehensive AppleScript + Swift + Python automation library for macOS.
Built for accessibility, voice control, and hands-free computing.

## Components

- `applescript_lib/` — Reusable AppleScript modules
- `swift_lib/` — Swift + Accessibility API native modules
- `python_bridge.py` — Python interface to AppleScript/Swift
- `cli.py` — Terminal commands for common actions

## Safe Design

- Uses official macOS Accessibility APIs
- No hidden keyloggers or spyware
- No network exploitation
- No bypassing of platform security
- Requires user consent for screen/control permissions

## Quick Start

```bash
cd /Users/alep/Downloads/windsurf-smoke/macos_automation
python3 -m macos_automation.cli list-apps
python3 -m macos_automation.cli type "Hello world"
python3 -m macos_automation.cli hotspot "MyHotspot" "password"
```

## Requirements

- macOS 14+
- Accessibility permissions enabled for Terminal/Python
- Xcode for Swift components

## Modules

- **App Control** — launch, quit, focus, list windows
- **UI Interaction** — click buttons, type text, read labels
- **Network** — Wi-Fi, hotspot, VPN helpers
- **VoiceOver** — speak, read UI elements, navigate
- **Screen** — capture, OCR, find elements
- **Files** — Finder automation, file operations
- **System** — volume, brightness, do-not-disturb
- **Keyboard** — shortcuts, key combinations

## License

MIT — for personal accessibility automation.
