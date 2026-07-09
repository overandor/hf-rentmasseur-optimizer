#!/usr/bin/env python3
"""
ScreenDB Live Monitor — Real-time view of all systems operating.
Shows: windows, accessibility tree, processes, receipts, KPIs, browser state.
Updates every 2 seconds. Press Ctrl+C to stop.
"""
import sys, os, time, json, sqlite3, subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screendb import (
    capture_accessibility, accessibility_summary, get_receipts,
    verify_receipts, sql as screendb_sql, DB_PATH as SCREENDB_DB,
    RECEIPTS_PATH, SHOTS_DIR
)
from mac_runtime import (
    capture_windows, capture_processes, capture_clipboard,
    query as mr_query, DB_PATH as MR_DB
)
from clientpulse import HourlyMetricsCollector, KPIEngine, DecisionGate

import shutil

TERM_W = shutil.get_terminal_size((120, 40)).columns
TERM_H = shutil.get_terminal_size((120, 40)).lines

def clear():
    print("\033[2J\033[H", end="")

def line(char="─", width=None):
    w = width or TERM_W
    return char * w

def box(title, content_lines, color="\033[36m"):
    print(f"{color}┌─ {title} {'─' * max(1, TERM_W - len(title) - 4)}\033[0m")
    for l in content_lines:
        print(f"{color}│\033[0m {l}")
    print(f"{color}└{'─' * (TERM_W - 1)}\033[0m")

def glyph_state(success, active):
    if success and active: return "◉◆"
    if success: return "◆"
    if active: return "◉"
    return "◌"

def run_live():
    print("\033[?25l", end="")  # hide cursor
    tick = 0

    # Start ClientPulse collector
    collector = HourlyMetricsCollector()
    kpi_engine = KPIEngine()
    gate = DecisionGate()

    try:
        while True:
            clear()
            tick += 1
            now = datetime.now().strftime("%H:%M:%S")

            # ─── Header ─────────────────────────────────────
            print(f"\033[1;33m╔{'═' * (TERM_W - 2)}╗\033[0m")
            title = f" ScreenDB LIVE MONITOR — tick #{tick} — {now} "
            pad = (TERM_W - 2 - len(title)) // 2
            print(f"\033[1;33m║{' ' * pad}{title}{' ' * (TERM_W - 2 - len(title) - pad)}║\033[0m")
            print(f"\033[1;33m╚{'═' * (TERM_W - 2)}╝\033[0m")

            # ─── 1. Windows (Mac Runtime) ───────────────────
            windows = capture_windows()
            win_lines = []
            for w in windows[:8]:
                mark = "◉" if w["focused"] else " "
                mini = " ⧖" if w.get("minimized") else ""
                app = w["app"][:18]
                title_s = w["title"][:35]
                geom = f"({w['x']},{w['y']}) {w['w']}x{w['h']}"
                win_lines.append(f"{mark} {app:<18} │ {title_s:<35} │ {geom}{mini}")
            box("WINDOWS (AXUIElement)", win_lines, "\033[36m")

            # ─── 2. Accessibility Tree ──────────────────────
            ax = capture_accessibility()
            ax_lines = []
            ax_lines.append(f"frontmost: \033[1m{ax.get('frontmost_app','?')}\033[0m │ {ax.get('frontmost_window','?')[:40]}")
            ax_lines.append(f"windows: {ax.get('window_count',0)} │ elements: {ax.get('element_count',0)}")
            for el in ax.get("elements", [])[:8]:
                focus = "◉" if el.get("focused") else " "
                en = "✓" if el.get("enabled") else "✗"
                role = el["role"][:18]
                title_s = el.get("title","")[:20] if el.get("title") else ""
                val = el.get("value","")[:15] if el.get("value") else ""
                val_s = f' val="{val}"' if val else ""
                pos = f"({el['x']},{el['y']})"
                ax_lines.append(f"  {focus} {en} {role:<18} │ {title_s:<20}{val_s:<18} │ {pos}")
            box("ACCESSIBILITY TREE (AXUIElement)", ax_lines, "\033[35m")

            # ─── 3. Processes (top 5 by CPU) ────────────────
            procs = capture_processes()
            proc_lines = []
            sorted_procs = sorted(procs, key=lambda p: p.get("cpu", 0), reverse=True)[:5]
            for p in sorted_procs:
                pid = str(p["pid"])[:7]
                name = p["name"][:22]
                cpu = p.get("cpu", 0)
                mem = p.get("mem", 0)
                bar_len = int(cpu / 5)
                bar = "█" * min(bar_len, 20)
                proc_lines.append(f"  {pid:>7} {name:<22} cpu={cpu:>5.1f}% {bar} mem={mem:>8}")
            box("PROCESSES (top 5 CPU)", proc_lines, "\033[32m")

            # ─── 4. Receipt Ledger ──────────────────────────
            receipts = get_receipts(6)
            v = verify_receipts()
            receipt_lines = []
            receipt_lines.append(f"ledger: {'✓ INTACT' if v['intact'] else '✗ BROKEN'} │ {v['valid']} valid │ {v['broken']} broken │ {v['total']} total")
            for r in receipts:
                ok = "✓" if r["result"]["success"] else "✗"
                rid = r["receipt_id"][:12]
                cursor = r["cursor_id"][:22]
                atype = r["action"]["type"][:14]
                output = r["result"]["output"][:30]
                shot_b = r["screenshot"]["before_hash"][:6]
                shot_a = r["screenshot"]["after_hash"][:6]
                witness = r["witness"]["event_count"]
                changed = "⟁" if shot_b != shot_a else " "
                receipt_lines.append(f"  {ok} [{rid}] {cursor:<22} │ {atype:>14} │ {output:<30} │ shot:{shot_b}→{shot_a} {changed} w:{witness}")
            box("RECEIPT LEDGER (ReceiptOS)", receipt_lines, "\033[33m")

            # ─── 5. ClientPulse KPIs ────────────────────────
            snapshots = collector.get_snapshots(limit=10)
            kpi_lines = []
            if snapshots:
                kpi_vec = kpi_engine.compute(snapshots)
                imm_bar = "█" * int(kpi_vec.immortality * 20)
                vir_bar = "█" * int(kpi_vec.virality * 20)
                conv_bar = "█" * int(kpi_vec.conversion * 20)
                trust_bar = "█" * int(kpi_vec.trust * 20)
                kpi_lines.append(f"  Immortality  {kpi_vec.immortality:.3f} {imm_bar:<20}")
                kpi_lines.append(f"  Virality     {kpi_vec.virality:.3f} {vir_bar:<20}")
                kpi_lines.append(f"  Conversion   {kpi_vec.conversion:.3f} {conv_bar:<20}")
                kpi_lines.append(f"  Trust        {kpi_vec.trust:.3f} {trust_bar:<20}")
                kpi_lines.append(f"  Decision: \033[1m{kpi_vec.decision}\033[0m │ {kpi_vec.reasoning[:50]}")
                kpi_lines.append(f"  Snapshots: {len(snapshots)}")
            else:
                kpi_lines.append("  No snapshots yet. Run clientpulse ingest to populate.")
            box("CLIENTPULSE KPIs", kpi_lines, "\033[34m")

            # ─── 6. ScreenDB SQL ────────────────────────────
            recent = screendb_sql("SELECT receipt_id, action_type, success, screenshot_after_hash FROM actions ORDER BY ts DESC LIMIT 3")
            sql_lines = []
            for r in recent:
                ok = "✓" if r.get("success") else "✗"
                sql_lines.append(f"  {ok} {r.get('receipt_id','')[:12]} │ {r.get('action_type',''):>14} │ shot={r.get('screenshot_after_hash','')[:10]}")
            box("SCREENDB SQL (live query)", sql_lines, "\033[36m")

            # ─── Footer ─────────────────────────────────────
            print()
            print(f"  \033[2mCtrl+C to stop │ tick #{tick} │ {now} │ ScreenCaptureKit sees │ AXUIElement understands │ CursorAgent acts │ ReceiptOS proves\033[0m")

            time.sleep(2)

    except KeyboardInterrupt:
        print("\033[?25h", end="")  # show cursor
        print("\n\nStopped. Ledger verified.")
        v = verify_receipts()
        print(f"  Final: {v['valid']} valid, {v['broken']} broken, {'✓ INTACT' if v['intact'] else '✗ BROKEN'}")

if __name__ == "__main__":
    run_live()
