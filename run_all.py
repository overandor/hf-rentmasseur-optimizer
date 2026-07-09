#!/usr/bin/env python3
"""Run ALL systems end-to-end: ScreenDB + MacAgent + ClientPulse + BrowserTelemetry."""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

results = {}

# ─── 1. ScreenDB ────────────────────────────────────────────────────────
print("=" * 60)
print("1. SCREENDB — State Snapshot + Receipt Mode")
print("=" * 60)

from screendb import (
    state_snapshot, receipt_action, CursorAgent,
    get_receipts, verify_receipts, sql as screendb_sql,
    capture_accessibility, accessibility_summary
)

state = state_snapshot()
print(f"  frontmost: {state['frontmost_app']} | {state['frontmost_window']}")
print(f"  windows: {state['windows']} | elements: {state['elements']}")
print(f"  screenshot_hash: {state['screenshot_hash'][:16]}...")
results["screendb_state"] = state

agent = CursorAgent(agent_name="runall-test")

# Action 1: notification (safe, visible)
r1 = receipt_action(agent, "notification", target="ScreenDB", value="RUN ALL test started")
print(f"\n  Action 1: notification")
print(f"    receipt: {r1['receipt_id']}")
print(f"    success: {r1['result']['success']}")
print(f"    shot: {r1['screenshot']['before_hash'][:8]} → {r1['screenshot']['after_hash'][:8]}")
results["screendb_action_1"] = r1["receipt_id"]

# Action 2: set_clipboard
r2 = receipt_action(agent, "set_clipboard", value="ScreenDB RUN ALL proof")
print(f"\n  Action 2: set_clipboard")
print(f"    receipt: {r2['receipt_id']}")
print(f"    success: {r2['result']['success']}")
print(f"    shot: {r2['screenshot']['before_hash'][:8]} → {r2['screenshot']['after_hash'][:8]}")
results["screendb_action_2"] = r2["receipt_id"]

# Verify ledger
v = verify_receipts()
print(f"\n  Ledger: {'✓ INTACT' if v['intact'] else '✗ BROKEN'} | {v['valid']} valid, {v['broken']} broken")
results["screendb_ledger"] = v

# SQL query
rows = screendb_sql("SELECT receipt_id, action_type, success FROM actions ORDER BY ts DESC LIMIT 5")
print(f"  SQL query returned {len(rows)} action records")
results["screendb_sql_count"] = len(rows)

# ─── 2. Browser Telemetry ───────────────────────────────────────────────
print("\n" + "=" * 60)
print("2. BROWSER TELEMETRY — DOM as Text (no screenshots)")
print("=" * 60)

from browser_telemetry import browser_to_text, extract_interaction_state, interaction_to_text
from browser_automation import selenium_driver

driver = None
try:
    driver = selenium_driver(headless=True)
    driver.get("https://www.python.org")
    time.sleep(3)

    state = extract_interaction_state(driver)
    text = interaction_to_text(state)
    print(f"  URL: {state.get('url', '?')}")
    print(f"  DOM nodes: {state.get('meta', {}).get('dom_nodes', 0)}")
    print(f"  Clickable: {state.get('meta', {}).get('clickable_count', 0)}")
    print(f"  Has captcha: {state.get('meta', {}).get('has_captcha', False)}")
    print(f"  Ready: {state.get('meta', {}).get('ready_state', '?')}")
    results["browser_telemetry"] = {
        "url": state.get("url"),
        "dom_nodes": state.get("meta", {}).get("dom_nodes", 0),
        "clickable": state.get("meta", {}).get("clickable_count", 0),
    }

    # Full text representation
    full_text = browser_to_text(driver, include_lattice=False)
    print(f"  Text representation: {len(full_text)} chars (deterministic, no images)")
    results["browser_text_len"] = len(full_text)

except Exception as e:
    print(f"  ERROR: {e}")
    results["browser_telemetry"] = {"error": str(e)}
finally:
    if driver:
        driver.quit()

# ─── 3. ClientPulse ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("3. CLIENTPULSE — Hourly Evidence Engine")
print("=" * 60)

from clientpulse import HourlyMetricsCollector, KPIEngine, DecisionGate

collector = HourlyMetricsCollector()

# Ingest a test metric snapshot
metrics = {
    "profile_views": 142,
    "contact_clicks": 9,
    "bookmarks": 3,
    "days_online": 45,
    "photos_count": 8,
    "price_visible": 1,
    "availability_hours": 6,
    "services_listed": 5,
    "response_rate": 0.85,
    "last_updated": "2026-06-27",
}
collector.ingest(metrics)
print(f"  Ingested metrics: {len(metrics)} fields")
print(f"    profile_views=142, contact_clicks=9, bookmarks=3, days_online=45")

# Second snapshot (simulating improvement)
metrics2 = dict(metrics)
metrics2["profile_views"] = 168
metrics2["contact_clicks"] = 12
time.sleep(0.1)
collector.ingest(metrics2)
print(f"  Ingested snapshot 2: profile_views=168, contact_clicks=12")

# Get snapshots and compute KPIs
snapshots = collector.get_snapshots(limit=10)
print(f"  Snapshots stored: {len(snapshots)}")

engine = KPIEngine()
kpi_vec = engine.compute(snapshots)
print(f"  KPI Vector:")
print(f"    Immortality: {kpi_vec.immortality:.3f}")
print(f"    Virality:    {kpi_vec.virality:.3f}")
print(f"    Conversion:  {kpi_vec.conversion:.3f}")
print(f"    Trust:       {kpi_vec.trust:.3f}")
results["clientpulse_kpis"] = {
    "immortality": kpi_vec.immortality,
    "virality": kpi_vec.virality,
    "conversion": kpi_vec.conversion,
    "trust": kpi_vec.trust,
}

# Decision gate
gate = DecisionGate()
decision = gate.record(kpi_vec)
print(f"  Decision: {decision.get('state', '?')}")
print(f"    reasoning: {decision.get('reasoning', '')[:80]}")
print(f"    receipt: {decision.get('receipt_hash', '')[:16]}")
results["clientpulse_decision"] = decision.get("state")

# ─── 4. Mac Runtime ─────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("4. MAC RUNTIME — Screen-as-Database")
print("=" * 60)

from mac_runtime import capture_windows, capture_processes, query as mr_query

windows = capture_windows()
print(f"  Windows captured: {len(windows)}")
for w in windows:
    mark = "◉" if w["focused"] else " "
    print(f"    {mark} {w['app']:>16} | {w['title'][:35]:<35} | ({w['x']},{w['y']}) {w['w']}x{w['h']}")

procs = capture_processes()
print(f"  Processes captured: {len(procs)}")

# SQL query
focused = mr_query("SELECT app, title FROM windows WHERE focused = 1")
print(f"  SQL: SELECT app, title FROM windows WHERE focused=1")
print(f"    → {focused}")
results["mac_runtime_windows"] = len(windows)
results["mac_runtime_processes"] = len(procs)

# ─── 5. Receipt Summary ────────────────────────────────────────────────
print("\n" + "=" * 60)
print("5. RECEIPT LEDGER — All Systems")
print("=" * 60)

receipts = get_receipts(20)
print(f"  Total receipts: {len(receipts)}")
for r in receipts:
    ok = "✓" if r["result"]["success"] else "✗"
    print(f"    {ok} [{r['receipt_id']}] {r['cursor_id'][:25]:<25} | {r['action']['type']:>15} → {r['result']['output'][:40]}")
    print(f"         shot: {r['screenshot']['before_hash'][:8]}→{r['screenshot']['after_hash'][:8]} | witness: {r['witness']['event_count']} events")

v = verify_receipts()
print(f"\n  Ledger integrity: {'✓ INTACT' if v['intact'] else '✗ BROKEN'}")
print(f"  Valid: {v['valid']} | Broken: {v['broken']} | Total: {v['total']}")
results["receipt_total"] = v["total"]
results["receipt_intact"] = v["intact"]

# ─── Final ──────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("RUN ALL COMPLETE")
print("=" * 60)
print(json.dumps({k: v for k, v in results.items() if not isinstance(v, dict) or len(str(v)) < 200}, indent=2, default=str))
