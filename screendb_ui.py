#!/usr/bin/env python3
"""
ScreenDB Control Surface — Production UI
FastAPI backend serving a living control surface for all systems.
"""
import sys, os, json, time, asyncio, threading
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from screendb import (
    capture_accessibility, accessibility_summary, get_receipts,
    verify_receipts, sql as screendb_sql, state_snapshot,
    receipt_action, CursorAgent, DB_PATH as SCREENDB_DB
)
from mac_runtime import (
    capture_windows, capture_processes, capture_clipboard,
    query as mr_query, DB_PATH as MR_DB, run_action
)
from clientpulse import HourlyMetricsCollector, KPIEngine, DecisionGate

app = FastAPI(title="ScreenDB Control Surface")

# Shared state
collector = HourlyMetricsCollector()
kpi_engine = KPIEngine()
gate = DecisionGate()
cursor_agent = CursorAgent(agent_name="ui-operator")
connected_clients = set()
polling = False
poll_thread = None

# ─── API Routes ─────────────────────────────────────────────────────────

@app.get("/api/state")
async def api_state():
    """Full system state snapshot."""
    windows = capture_windows()
    ax = capture_accessibility()
    procs = capture_processes()
    procs_sorted = sorted(procs, key=lambda p: p.get("cpu", 0), reverse=True)[:10]
    receipts = get_receipts(10)
    v = verify_receipts()

    snapshots = collector.get_snapshots(limit=10)
    kpi_vec = kpi_engine.compute(snapshots) if snapshots else None

    return {
        "timestamp": datetime.now().isoformat(),
        "windows": windows,
        "accessibility": {
            "frontmost_app": ax.get("frontmost_app", ""),
            "frontmost_window": ax.get("frontmost_window", ""),
            "window_count": ax.get("window_count", 0),
            "element_count": ax.get("element_count", 0),
            "elements": ax.get("elements", [])[:20],
        },
        "processes": procs_sorted,
        "receipts": receipts,
        "ledger": v,
        "kpis": {
            "immortality": kpi_vec.immortality if kpi_vec else 0,
            "virality": kpi_vec.virality if kpi_vec else 0,
            "conversion": kpi_vec.conversion if kpi_vec else 0,
            "trust": kpi_vec.trust if kpi_vec else 0,
            "decision": kpi_vec.decision if kpi_vec else "INSUFFICIENT_DATA",
            "reasoning": kpi_vec.reasoning if kpi_vec else "",
        } if kpi_vec else None,
        "snapshot_count": len(snapshots),
    }


@app.post("/api/action")
async def api_action(body: dict):
    """Execute an action with ScreenDB receipt."""
    atype = body.get("type", "")
    target = body.get("target", "")
    value = body.get("value", "")
    if not atype:
        return {"error": "No action type"}
    receipt = receipt_action(cursor_agent, atype, target, value)
    return {
        "receipt_id": receipt["receipt_id"],
        "success": receipt["result"]["success"],
        "output": receipt["result"]["output"],
        "screenshot_before": receipt["screenshot"]["before_hash"][:12],
        "screenshot_after": receipt["screenshot"]["after_hash"][:12],
        "cursor_id": receipt["cursor_id"],
        "accessibility_after": receipt["accessibility"]["after_summary"][:200],
    }


@app.post("/api/ingest")
async def api_ingest(body: dict):
    """Ingest metrics into ClientPulse."""
    record = collector.ingest(body)
    return {"success": True, "record_id": record.get("id")}


@app.get("/api/receipts")
async def api_receipts(limit: int = 20):
    return get_receipts(limit)


@app.get("/api/verify")
async def api_verify():
    return verify_receipts()


@app.get("/api/sql/{db}")
async def api_sql(db: str, q: str = ""):
    if not q:
        return {"error": "No query"}
    if db == "screendb":
        return screendb_sql(q)
    elif db == "macruntime":
        return mr_query(q)
    return {"error": "Unknown database"}


# ─── WebSocket for live updates ─────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_clients.add(ws)
    try:
        while True:
            windows = capture_windows()
            ax = capture_accessibility()
            procs = capture_processes()
            procs_sorted = sorted(procs, key=lambda p: p.get("cpu", 0), reverse=True)[:8]
            receipts = get_receipts(6)
            v = verify_receipts()
            snapshots = collector.get_snapshots(limit=10)
            kpi_vec = kpi_engine.compute(snapshots) if snapshots else None

            data = {
                "ts": datetime.now().strftime("%H:%M:%S"),
                "windows": [{
                    "app": w["app"], "title": w["title"][:40],
                    "focused": w["focused"], "minimized": w.get("minimized", False),
                    "x": w["x"], "y": w["y"], "w": w["w"], "h": w["h"],
                } for w in windows[:10]],
                "frontmost": ax.get("frontmost_app", ""),
                "frontmost_title": ax.get("frontmost_window", ""),
                "elements": ax.get("element_count", 0),
                "element_list": [{
                    "role": e["role"], "title": e.get("title","")[:20],
                    "value": e.get("value","")[:15], "enabled": e.get("enabled",False),
                    "focused": e.get("focused",False), "x": e["x"], "y": e["y"],
                } for e in ax.get("elements", [])[:12]],
                "procs": [{"pid": p["pid"], "name": p["name"][:20],
                           "cpu": p.get("cpu",0), "mem": p.get("mem",0)} for p in procs_sorted],
                "receipts": [{
                    "id": r["receipt_id"][:12], "success": r["result"]["success"],
                    "type": r["action"]["type"], "output": r["result"]["output"][:40],
                    "shot_b": r["screenshot"]["before_hash"][:6],
                    "shot_a": r["screenshot"]["after_hash"][:6],
                    "changed": r["screenshot"]["before_hash"] != r["screenshot"]["after_hash"],
                    "witness": r["witness"]["event_count"],
                    "cursor": r["cursor_id"][:20],
                } for r in receipts],
                "ledger": v,
                "kpis": {
                    "immortality": kpi_vec.immortality if kpi_vec else 0,
                    "virality": kpi_vec.virality if kpi_vec else 0,
                    "conversion": kpi_vec.conversion if kpi_vec else 0,
                    "trust": kpi_vec.trust if kpi_vec else 0,
                    "decision": kpi_vec.decision if kpi_vec else "—",
                    "reasoning": kpi_vec.reasoning[:60] if kpi_vec else "",
                } if kpi_vec else None,
            }
            await ws.send_json(data)
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        connected_clients.discard(ws)
    except Exception:
        connected_clients.discard(ws)


# ─── UI ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return UI_HTML


UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ScreenDB Control Surface</title>
<style>
:root {
  --bg: #0a0a0f;
  --panel: rgba(20,20,30,0.85);
  --border: rgba(255,140,0,0.15);
  --border-active: rgba(255,140,0,0.4);
  --text: #e0e0e8;
  --text-dim: #606070;
  --orange: #ff8c00;
  --orange-dim: #cc6f00;
  --green: #00ff88;
  --red: #ff3344;
  --cyan: #00ddff;
  --purple: #aa44ff;
  --mono: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
}

* { margin:0; padding:0; box-sizing:border-box; }

body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--mono);
  font-size: 13px;
  overflow: hidden;
  height: 100vh;
}

#app {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  grid-template-rows: auto 1fr 1fr auto;
  gap: 8px;
  padding: 8px;
  height: 100vh;
}

.header {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  background: linear-gradient(90deg, rgba(255,140,0,0.08), transparent);
  border: 1px solid var(--border);
  border-radius: 6px;
}
.header .title {
  font-size: 16px; font-weight: bold; color: var(--orange);
  letter-spacing: 2px; text-transform: uppercase;
}
.header .ts { color: var(--text-dim); font-size: 12px; }
.header .status { display: flex; gap: 12px; align-items: center; }
.header .dot {
  width: 8px; height: 8px; border-radius: 50%;
  background: var(--green); box-shadow: 0 0 8px var(--green);
  animation: pulse 2s infinite;
}
@keyframes pulse { 0%,100% { opacity:1; } 50% { opacity:0.4; } }

.panel {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 10px;
  overflow: hidden;
  display: flex; flex-direction: column;
  transition: border-color 0.3s;
}
.panel:hover { border-color: var(--border-active); }
.panel-title {
  font-size: 11px; color: var(--orange); text-transform: uppercase;
  letter-spacing: 1.5px; margin-bottom: 8px; display: flex;
  justify-content: space-between; align-items: center;
}
.panel-title .count { color: var(--text-dim); font-size: 10px; }
.panel-body { flex: 1; overflow-y: auto; }

/* Windows panel */
.win-row {
  display: flex; align-items: center; gap: 8px;
  padding: 4px 6px; margin-bottom: 2px; border-radius: 4px;
  transition: background 0.2s;
}
.win-row:hover { background: rgba(255,140,0,0.05); }
.win-row.focused { background: rgba(255,140,0,0.08); border-left: 2px solid var(--orange); }
.win-glyph { color: var(--orange); width: 16px; }
.win-glyph.dim { color: var(--text-dim); }
.win-app { min-width: 100px; font-weight: bold; }
.win-title { color: var(--text-dim); flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.win-geom { color: var(--text-dim); font-size: 10px; }

/* Elements panel */
.el-row {
  display: flex; align-items: center; gap: 6px;
  padding: 3px 6px; font-size: 11px;
}
.el-glyph { width: 14px; text-align: center; }
.el-role { min-width: 90px; color: var(--cyan); }
.el-title { color: var(--text-dim); flex: 1; }
.el-val { color: var(--purple); font-size: 10px; }

/* Processes */
.proc-row {
  display: flex; align-items: center; gap: 8px;
  padding: 3px 6px; font-size: 11px;
}
.proc-pid { color: var(--text-dim); width: 50px; }
.proc-name { min-width: 120px; }
.proc-bar {
  flex: 1; height: 4px; background: rgba(255,255,255,0.05);
  border-radius: 2px; overflow: hidden;
}
.proc-bar-fill {
  height: 100%; background: linear-gradient(90deg, var(--orange), var(--red));
  transition: width 0.5s;
}
.proc-cpu { width: 50px; text-align: right; color: var(--orange); }

/* Receipts */
.receipt-row {
  display: grid; grid-template-columns: 16px 80px 80px 1fr 60px 20px;
  gap: 6px; padding: 3px 6px; font-size: 11px; align-items: center;
  border-bottom: 1px solid rgba(255,255,255,0.03);
}
.r-ok { color: var(--green); }
.r-fail { color: var(--red); }
.r-id { color: var(--text-dim); font-size: 10px; }
.r-type { color: var(--cyan); }
.r-out { color: var(--text-dim); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.r-shot { color: var(--text-dim); font-size: 10px; }
.r-changed { color: var(--orange); }

/* KPIs */
.kpi-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.kpi-card {
  padding: 8px; border-radius: 4px;
  background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05);
}
.kpi-label { font-size: 10px; color: var(--text-dim); text-transform: uppercase; letter-spacing: 1px; }
.kpi-value { font-size: 20px; font-weight: bold; margin: 4px 0; }
.kpi-bar {
  height: 6px; background: rgba(255,255,255,0.05); border-radius: 3px; overflow: hidden;
}
.kpi-bar-fill { height: 100%; transition: width 0.5s; }
.kpi-immortality .kpi-value { color: var(--green); }
.kpi-immortality .kpi-bar-fill { background: var(--green); }
.kpi-virality .kpi-value { color: var(--cyan); }
.kpi-virality .kpi-bar-fill { background: var(--cyan); }
.kpi-conversion .kpi-value { color: var(--orange); }
.kpi-conversion .kpi-bar-fill { background: var(--orange); }
.kpi-trust .kpi-value { color: var(--purple); }
.kpi-trust .kpi-bar-fill { background: var(--purple); }

.decision-box {
  margin-top: 8px; padding: 8px; border-radius: 4px;
  background: rgba(255,140,0,0.08); border: 1px solid var(--border-active);
  text-align: center;
}
.decision-label { font-size: 10px; color: var(--text-dim); }
.decision-value { font-size: 16px; font-weight: bold; color: var(--orange); margin-top: 4px; }
.decision-reason { font-size: 10px; color: var(--text-dim); margin-top: 2px; }

/* Action bar */
.action-bar {
  grid-column: 1 / -1;
  display: flex; gap: 8px; align-items: center;
  padding: 8px 12px; background: var(--panel);
  border: 1px solid var(--border); border-radius: 6px;
}
.action-bar select, .action-bar input, .action-bar button {
  background: rgba(255,255,255,0.05); border: 1px solid var(--border);
  color: var(--text); padding: 6px 10px; border-radius: 4px;
  font-family: var(--mono); font-size: 12px;
}
.action-bar select:focus, .action-bar input:focus {
  outline: none; border-color: var(--orange);
}
.action-bar button {
  background: rgba(255,140,0,0.15); border-color: var(--border-active);
  color: var(--orange); cursor: pointer; font-weight: bold;
  transition: all 0.2s;
}
.action-bar button:hover {
  background: rgba(255,140,0,0.3); box-shadow: 0 0 12px rgba(255,140,0,0.2);
}
.action-bar button:active { transform: scale(0.97); }
.action-bar input { flex: 1; }
.action-result {
  font-size: 11px; color: var(--text-dim); margin-left: 8px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 300px;
}
.action-result.ok { color: var(--green); }
.action-result.fail { color: var(--red); }

/* Scrollbar */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,140,0,0.2); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,140,0,0.4); }

/* Ledger badge */
.ledger-badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 8px; border-radius: 3px; font-size: 10px;
}
.ledger-badge.intact { background: rgba(0,255,136,0.1); color: var(--green); }
.ledger-badge.broken { background: rgba(255,51,68,0.1); color: var(--red); }

/* Connection */
.conn-status { font-size: 10px; color: var(--text-dim); }
.conn-status.live { color: var(--green); }
.conn-status.dead { color: var(--red); }
</style>
</head>
<body>
<div id="app">
  <!-- Header -->
  <div class="header">
    <div class="title">◉ ScreenDB Control Surface</div>
    <div class="status">
      <span class="ts" id="ts">—</span>
      <span class="conn-status" id="conn">connecting</span>
      <div class="dot"></div>
    </div>
  </div>

  <!-- Windows -->
  <div class="panel">
    <div class="panel-title">◇ Windows <span class="count" id="win-count">0</span></div>
    <div class="panel-body" id="windows"></div>
  </div>

  <!-- Accessibility -->
  <div class="panel">
    <div class="panel-title">⟡ Accessibility <span class="count" id="el-count">0</span></div>
    <div class="panel-body" id="elements"></div>
  </div>

  <!-- KPIs -->
  <div class="panel">
    <div class="panel-title">▲ KPIs <span class="count" id="snap-count">0</span></div>
    <div class="panel-body" id="kpis"></div>
  </div>

  <!-- Processes -->
  <div class="panel" style="grid-column: 1 / 3;">
    <div class="panel-title">⌁ Processes <span class="count">top 8</span></div>
    <div class="panel-body" id="procs"></div>
  </div>

  <!-- Receipts -->
  <div class="panel">
    <div class="panel-title">
      ◆ Receipts
      <span class="ledger-badge intact" id="ledger-badge">✓ INTACT</span>
    </div>
    <div class="panel-body" id="receipts"></div>
  </div>

  <!-- Action Bar -->
  <div class="action-bar">
    <select id="action-type">
      <option value="notification">notification</option>
      <option value="activate_app">activate_app</option>
      <option value="open_url">open_url</option>
      <option value="type">type</option>
      <option value="key">key</option>
      <option value="set_clipboard">set_clipboard</option>
      <option value="run_shell">run_shell</option>
      <option value="quit_app">quit_app</option>
      <option value="delay">delay</option>
    </select>
    <input type="text" id="action-target" placeholder="target (app name / x,y / title)" />
    <input type="text" id="action-value" placeholder="value (text / url / command)" />
    <button onclick="execAction()">◉ EXECUTE</button>
    <span class="action-result" id="action-result">ready</span>
  </div>
</div>

<script>
let ws = null;

function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  const connEl = document.getElementById('conn');

  ws.onopen = () => { connEl.textContent = 'live'; connEl.className = 'conn-status live'; };
  ws.onclose = () => { connEl.textContent = 'reconnecting'; connEl.className = 'conn-status dead'; setTimeout(connect, 2000); };
  ws.onerror = () => { ws.close(); };
  ws.onmessage = (ev) => update(JSON.parse(ev.data));
}

function update(d) {
  document.getElementById('ts').textContent = d.ts;

  // Windows
  let winHtml = '';
  d.windows.forEach(w => {
    const g = w.focused ? '◉' : '◌';
    const cls = w.focused ? 'win-row focused' : 'win-row';
    const gcls = w.focused ? 'win-glyph' : 'win-glyph dim';
    winHtml += `<div class="${cls}">
      <span class="${gcls}">${g}</span>
      <span class="win-app">${esc(w.app)}</span>
      <span class="win-title">${esc(w.title)}</span>
      <span class="win-geom">${w.x},${w.y} ${w.w}×${w.h}</span>
    </div>`;
  });
  document.getElementById('windows').innerHTML = winHtml;
  document.getElementById('win-count').textContent = d.windows.length;

  // Elements
  let elHtml = `<div style="color:var(--text-dim);font-size:11px;margin-bottom:4px">
    frontmost: <span style="color:var(--orange)">${esc(d.frontmost)}</span> | ${esc(d.frontmost_title)}
  </div>`;
  d.element_list.forEach(e => {
    const g = e.focused ? '◉' : (e.enabled ? '✓' : '✗');
    const gc = e.focused ? 'var(--orange)' : (e.enabled ? 'var(--green)' : 'var(--red)');
    elHtml += `<div class="el-row">
      <span class="el-glyph" style="color:${gc}">${g}</span>
      <span class="el-role">${esc(e.role)}</span>
      <span class="el-title">${esc(e.title)}</span>
      <span class="el-val">${e.value ? 'val="' + esc(e.value) + '"' : ''}</span>
    </div>`;
  });
  document.getElementById('elements').innerHTML = elHtml;
  document.getElementById('el-count').textContent = d.elements;

  // Processes
  let procHtml = '';
  d.procs.forEach(p => {
    const barW = Math.min(100, p.cpu * 2);
    procHtml += `<div class="proc-row">
      <span class="proc-pid">${p.pid}</span>
      <span class="proc-name">${esc(p.name)}</span>
      <div class="proc-bar"><div class="proc-bar-fill" style="width:${barW}%"></div></div>
      <span class="proc-cpu">${p.cpu.toFixed(1)}%</span>
    </div>`;
  });
  document.getElementById('procs').innerHTML = procHtml;

  // Receipts
  let rHtml = '';
  d.receipts.forEach(r => {
    const ok = r.success ? '✓' : '✗';
    const okCls = r.success ? 'r-ok' : 'r-fail';
    const changed = r.changed ? '⟁' : '';
    rHtml += `<div class="receipt-row">
      <span class="${okCls}">${ok}</span>
      <span class="r-id">${r.id}</span>
      <span class="r-type">${r.type}</span>
      <span class="r-out">${esc(r.output)}</span>
      <span class="r-shot">${r.shot_b}→${r.shot_a}</span>
      <span class="r-changed">${changed}</span>
    </div>`;
  });
  document.getElementById('receipts').innerHTML = rHtml;

  // Ledger
  const lb = document.getElementById('ledger-badge');
  if (d.ledger.intact) {
    lb.textContent = `✓ INTACT ${d.ledger.valid}/${d.ledger.total}`;
    lb.className = 'ledger-badge intact';
  } else {
    lb.textContent = `✗ BROKEN ${d.ledger.broken} broken`;
    lb.className = 'ledger-badge broken';
  }

  // KPIs
  let kpiHtml = '';
  if (d.kpis) {
    const k = d.kpis;
    kpiHtml = `<div class="kpi-grid">
      <div class="kpi-card kpi-immortality">
        <div class="kpi-label">Immortality</div>
        <div class="kpi-value">${k.immortality.toFixed(3)}</div>
        <div class="kpi-bar"><div class="kpi-bar-fill" style="width:${k.immortality*100}%"></div></div>
      </div>
      <div class="kpi-card kpi-virality">
        <div class="kpi-label">Virality</div>
        <div class="kpi-value">${k.virality.toFixed(3)}</div>
        <div class="kpi-bar"><div class="kpi-bar-fill" style="width:${k.virality*100}%"></div></div>
      </div>
      <div class="kpi-card kpi-conversion">
        <div class="kpi-label">Conversion</div>
        <div class="kpi-value">${k.conversion.toFixed(3)}</div>
        <div class="kpi-bar"><div class="kpi-bar-fill" style="width:${k.conversion*100}%"></div></div>
      </div>
      <div class="kpi-card kpi-trust">
        <div class="kpi-label">Trust</div>
        <div class="kpi-value">${k.trust.toFixed(3)}</div>
        <div class="kpi-bar"><div class="kpi-bar-fill" style="width:${k.trust*100}%"></div></div>
      </div>
    </div>
    <div class="decision-box">
      <div class="decision-label">DECISION</div>
      <div class="decision-value">${k.decision}</div>
      <div class="decision-reason">${esc(k.reasoning)}</div>
    </div>`;
  } else {
    kpiHtml = '<div style="color:var(--text-dim);padding:20px;text-align:center">No KPI data yet.<br>Ingest metrics to populate.</div>';
  }
  document.getElementById('kpis').innerHTML = kpiHtml;
  document.getElementById('snap-count').textContent = d.snapshot_count || 0;
}

function esc(s) {
  if (!s) return '';
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function execAction() {
  const type = document.getElementById('action-type').value;
  const target = document.getElementById('action-target').value;
  const value = document.getElementById('action-value').value;
  const resultEl = document.getElementById('action-result');

  resultEl.textContent = 'executing...';
  resultEl.className = 'action-result';

  try {
    const r = await fetch('/api/action', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({type, target, value})
    });
    const data = await r.json();
    if (data.success) {
      resultEl.textContent = `✓ ${data.receipt_id} | ${data.output} | ${data.screenshot_before}→${data.screenshot_after}`;
      resultEl.className = 'action-result ok';
    } else {
      resultEl.textContent = `✗ ${data.receipt_id || 'failed'} | ${data.output || data.error}`;
      resultEl.className = 'action-result fail';
    }
  } catch(e) {
    resultEl.textContent = `✗ ${e.message}`;
    resultEl.className = 'action-result fail';
  }
}

connect();
</script>
</body>
</html>"""


def cli():
    import argparse
    p = argparse.ArgumentParser(description="ScreenDB Control Surface — Production UI")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8777)
    args = p.parse_args()

    import uvicorn
    print(f"\n  ◉ ScreenDB Control Surface")
    print(f"  → http://{args.host}:{args.port}\n")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    cli()
