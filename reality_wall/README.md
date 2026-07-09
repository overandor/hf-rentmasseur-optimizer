# Reality Wall

**A 10-foot proof dashboard for AI-native work, streaming verified receipts, client intelligence, artifact provenance, and value signals from Reality Compiler to Samsung TV.**

Built with TypeScript + React. Runs on Samsung Smart TVs (Tizen 5.5+ / 2020+).

## Status

```
Reality Wall v0.1
Status: Demo-ready / pilot-ready Tizen proof dashboard
Production status: NOT YET — requires real TV install + WSS + burn-in test
Architecture: production-correct
Security: code-level hardening done, hardware validation pending
```

## Ship Gate Checklist

```
[ ] Tizen Studio installed
[ ] Samsung certificates created
[ ] .wgt signed
[ ] .wgt installed on real Samsung TV
[ ] Real Samsung remote tested (D-pad, color buttons, Back)
[ ] QR pairing creates short-lived token
[ ] WebSocket rejects unpaired clients
[ ] WebSocket uses WSS in production (WALL_TLS=1 + certs)
[ ] Origin allowlist enforced
[ ] Every message has token + timestamp + payload hash
[ ] Server rate-limits and size-limits messages
[ ] Proof card push from Mac works
[ ] Receipt hash visible on every card
[ ] Demo mode clearly labeled cached/read-only
[ ] TV stores no raw secrets
[ ] Backend restart reconnect works
[ ] 24-hour burn-in test passes
```

## Architecture

```
Samsung TV (Tizen Web App)
    ↕ WebSocket
Node.js Bridge Server (port 7863)
    ↕ HTTP + subprocess
Python Systems:
  ├── overagent_control_plane.py (port 7862) — KPIs, receipts, decisions
  ├── clientpulse.py — ClientPulse snapshots, experiments, decisions
  ├── reality_compiler.py — LambdaReceipts, lambda scores, provenance
  └── receipt_ledger.py — tamper-evident receipt chain
```

## Stack

- **Frontend**: TypeScript + React + Vite
- **Backend**: Node.js + WebSocket (ws)
- **Data**: Real SQLite databases + HTTP APIs — no mocks, no placeholders
- **TV**: Tizen Web App (config.xml, 10-foot UI, remote navigation)
- **Design**: Dark, glassy, orange-lit, glyph-based control surface

## Build

```bash
cd reality_wall
npm install
npm run build
```

## Run (development)

```bash
# Terminal 1: Start the Python control plane
python3 overagent_control_plane.py --port 7862

# Terminal 2: Start the WebSocket bridge
npm run server

# Terminal 3: Start the Vite dev server
npm run dev
```

Open `http://localhost:5174` in a browser.

## Tizen packaging

```bash
npm run build
npm run tizen:package
# Then use Tizen Studio to sign and package as .wgt
```

## Views

| View | Glyph | Content |
|------|-------|---------|
| Overview | ◉ | KPIs + operator report + recent receipts + ClientPulse |
| Proof | ◆ | LambdaReceipt cards with transferability scores |
| Receipts | ⧉ | Tamper-evident receipt chain |
| KPI | ▲ | Immortality, Virality, Conversion, Proof scores |
| Experiments | ⟡ | Active experiments with status and verdicts |
| Pairing | ⧉ | QR code + 6-char pairing code for phone/Mac to connect |
| Demo | ◈ | Read-only investor display using cached data (no live backend needed) |

## Remote Navigation

```
↑/↓     — switch between views
←/→     — navigate cards within a view
Enter   — select
Back    — return to overview (or exit pairing)

Samsung color buttons:
  A (Red)    — refresh data
  B (Green)  — next view
  C (Yellow) — previous view
  D (Blue)   — home (overview)
  Play/Pause — refresh
```

## QR Pairing

The pairing screen displays a QR code encoding the WebSocket URL and a 6-character pairing code. A phone or Mac scans the QR to discover the backend address and confirm the connection.

Access via the **pair** button in the header or by navigating to the `pairing` view.

## Investor Demo Mode

Read-only display that uses the last cached state from `localStorage`. Works without a live backend connection — perfect for investor demos on the TV.

The TV displays cached KPIs, receipts, proof cards, and the operator report with a prominent "INVESTOR DEMO MODE" banner showing cache age.

Access via the **demo** button in the header.

## Data Sources (all real)

- `overagent_control_plane.py` — `/api/kpis`, `/api/receipts`, `/api/decision-gate`, `/api/experiments`, `/api/operator-report`
- `clientpulse.py` — SQLite `data/clientpulse.db` (snapshots, experiments, decisions)
- `reality_compiler.py` — SQLite `data/reality_compiler.db` (lambda receipts)
- `receipt_ledger.py` — SQLite `data/receipts.db` + `receipts.jsonl`

No simulated data. No hardcoded values. No placeholders.
