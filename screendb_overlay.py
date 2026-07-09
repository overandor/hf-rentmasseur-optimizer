#!/usr/bin/env python3
"""
ScreenDB Overlay — Transparent fullscreen cross dividing screen into 4 quadrants.
Each quadrant shows live ScreenDB data overlaid on top of any desktop window.

Uses tkinter with transparent background on macOS.
"""
import sys, os, json, time, subprocess, threading, tkinter as tk
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from screendb import capture_accessibility, get_receipts, verify_receipts
from mac_runtime import capture_windows, capture_processes


class ScreenDBOverlay:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ScreenDB Overlay")
        self.root.attributes("-fullscreen", True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg="black")
        self.root.attributes("-alpha", 0.85)

        self.screen_w = self.root.winfo_screenwidth()
        self.screen_h = self.root.winfo_screenheight()
        self.cx = self.screen_w // 2
        self.cy = self.screen_h // 2

        self.canvas = tk.Canvas(self.root, bg="black", highlightthickness=0,
                                width=self.screen_w, height=self.screen_h)
        self.canvas.pack(fill="both", expand=True)

        self.running = True
        self.data = {
            "windows": [], "elements": [], "processes": [],
            "receipts": [], "frontmost": "", "frontmost_title": "",
            "ledger_valid": True, "ledger_count": 0, "tick": 0,
        }

        # Colors
        self.ORANGE = "#ff8c00"
        self.CYAN = "#00ddff"
        self.GREEN = "#00ff88"
        self.RED = "#ff3344"
        self.PURPLE = "#aa44ff"
        self.GRAY = "#606070"
        self.WHITE = "#e0e0e8"
        self.DIM = "#303040"

        # Bind Escape to quit
        self.root.bind("<Escape>", lambda e: self.quit())
        self.root.bind("<Button-1>", lambda e: None)  # click-through attempt

        # Start data thread
        self.thread = threading.Thread(target=self._data_loop, daemon=True)
        self.thread.start()

        # Start render loop
        self._render()
        self.root.mainloop()

    def quit(self):
        self.running = False
        self.root.destroy()

    def _data_loop(self):
        while self.running:
            try:
                windows = capture_windows()
                ax = capture_accessibility()
                procs = capture_processes()
                receipts = get_receipts(6)
                v = verify_receipts()

                self.data = {
                    "windows": windows[:10],
                    "elements": ax.get("elements", [])[:12],
                    "processes": sorted(procs, key=lambda p: p.get("cpu", 0), reverse=True)[:8],
                    "receipts": receipts,
                    "frontmost": ax.get("frontmost_app", ""),
                    "frontmost_title": ax.get("frontmost_window", ""),
                    "ledger_valid": v["intact"],
                    "ledger_count": v["total"],
                    "tick": self.data["tick"] + 1,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                }
            except Exception:
                pass
            time.sleep(2)

    def _render(self):
        if not self.running:
            return
        self.canvas.delete("all")
        d = self.data
        cx, cy = self.cx, self.cy

        # ─── The Cross ──────────────────────────────
        # Vertical line
        self.canvas.create_line(cx, 0, cx, self.screen_h, fill=self.ORANGE, width=2, stipple="")
        # Horizontal line
        self.canvas.create_line(0, cy, self.screen_w, cy, fill=self.ORANGE, width=2)

        # Crosshair circle
        self.canvas.create_oval(cx - 15, cy - 15, cx + 15, cy + 15, outline=self.ORANGE, width=1)
        self.canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill=self.ORANGE, outline="")

        # ─── Q0: Top-Left — Windows + Accessibility ─
        qx0, qy0 = 4, 4
        qw, qh = cx - 8, cy - 8
        self._draw_quadrant_header(qx0, qy0, "◇ WINDOWS  ⟡ ACCESSIBILITY", self.CYAN)
        y = qy0 + 25
        if d["frontmost"]:
            self.canvas.create_text(qx0 + 8, y, text=f"◉ {d['frontmost']} | {d['frontmost_title'][:35]}",
                                    fill=self.ORANGE, font=("SF Mono", 11, "bold"), anchor="w")
            y += 18
        for w in d["windows"][:6]:
            mark = "◉" if w["focused"] else "◌"
            color = self.WHITE if w["focused"] else self.GRAY
            self.canvas.create_text(qx0 + 8, y, text=f"  {mark} {w['app'][:18]:<18} {w['title'][:30]}",
                                    fill=color, font=("SF Mono", 10), anchor="w")
            y += 15
        if d["elements"]:
            y += 5
            self.canvas.create_text(qx0 + 8, y, text="⟡ ELEMENTS", fill=self.CYAN, font=("SF Mono", 9, "bold"), anchor="w")
            y += 14
            for e in d["elements"][:6]:
                en = "✓" if e.get("enabled") else "✗"
                en_color = self.GREEN if e.get("enabled") else self.RED
                title = e.get("title", "") or ""
                val = e.get("value", "") or ""
                val_s = f' v="{val[:15]}"' if val and val != "missing value" else ""
                self.canvas.create_text(qx0 + 8, y, text=f"  {en} {e['role'][:16]:<16} {title[:20]}{val_s}",
                                        fill=self.GRAY, font=("SF Mono", 9), anchor="w")
                y += 13

        # ─── Q1: Top-Right — Processes ──────────────
        qx1 = cx + 4
        self._draw_quadrant_header(qx1, qy0, "⌁ PROCESSES  top 8 by CPU", self.GREEN)
        y = qy0 + 25
        for p in d["processes"][:8]:
            name = p["name"][:20]
            cpu = p.get("cpu", 0)
            bar_len = int(min(40, cpu * 2))
            bar = "█" * bar_len
            self.canvas.create_text(qx1 + 8, y, text=f"  {p['pid']:>7} {name:<20} {cpu:>5.1f}% {bar}",
                                    fill=self.GRAY, font=("SF Mono", 9), anchor="w")
            y += 14

        # ─── Q2: Bottom-Left — Receipts ─────────────
        qy2 = cy + 4
        ledger_text = f"✓ INTACT {d['ledger_count']}" if d["ledger_valid"] else "✗ BROKEN"
        ledger_color = self.GREEN if d["ledger_valid"] else self.RED
        self._draw_quadrant_header(qx0, qy2, "◆ RECEIPTS", self.ORANGE, badge=ledger_text, badge_color=ledger_color)
        y = qy2 + 25
        if not d["receipts"]:
            self.canvas.create_text(qx0 + 8, y, text="◌ No receipts yet — run: python3 screendb.py exec notification --target test --value hello",
                                    fill=self.DIM, font=("SF Mono", 8), anchor="w")
            y += 14
        for r in d["receipts"][:6]:
            ok = "✓" if r["result"]["success"] else "✗"
            ok_color = self.GREEN if r["result"]["success"] else self.RED
            changed = "⟁" if r["screenshot"]["before_hash"] != r["screenshot"]["after_hash"] else " "
            shot_b = r["screenshot"]["before_hash"][:6]
            shot_a = r["screenshot"]["after_hash"][:6]
            atype = r["action"]["type"][:14]
            output = r["result"]["output"][:35]

            self.canvas.create_text(qx0 + 8, y, text=f"  {ok} [{r['receipt_id'][:12]}] {atype:>14} {output}",
                                    fill=self.GRAY, font=("SF Mono", 9), anchor="w")
            self.canvas.create_text(qx0 + 8 + 600, y, text=f"{shot_b}→{shot_a} {changed}",
                                    fill=self.ORANGE if changed.strip() else self.DIM, font=("SF Mono", 8), anchor="w")
            y += 14

        # ─── Q3: Bottom-Right — Status ──────────────
        self._draw_quadrant_header(qx1, qy2, "◉ SCREENDB", self.PURPLE, badge=f"tick #{d['tick']}", badge_color=self.GRAY)
        y = qy2 + 25
        ts = d.get("timestamp", "")
        self.canvas.create_text(qx1 + 8, y, text=f"  ◉ LIVE  {ts}", fill=self.GREEN, font=("SF Mono", 12, "bold"), anchor="w")
        y += 22

        self.canvas.create_text(qx1 + 8, y, text=f"  WINDOWS   {len(d['windows'])}", fill=self.CYAN, font=("SF Mono", 14, "bold"), anchor="w")
        self.canvas.create_text(qx1 + 120, y, text=f"  ELEMENTS  {len(d['elements'])}", fill=self.CYAN, font=("SF Mono", 14, "bold"), anchor="w")
        y += 20
        self.canvas.create_text(qx1 + 8, y, text=f"  PROCS     {len(d['processes'])}", fill=self.GREEN, font=("SF Mono", 14, "bold"), anchor="w")
        self.canvas.create_text(qx1 + 120, y, text=f"  RECEIPTS  {d['ledger_count']}", fill=self.ORANGE, font=("SF Mono", 14, "bold"), anchor="w")
        y += 28

        self.canvas.create_text(qx1 + 8, y, text="  ARCHITECTURE", fill=self.DIM, font=("SF Mono", 9, "bold"), anchor="w")
        y += 14
        for line in ["  ScreenCaptureKit sees", "  AXUIElement understands", "  CursorAgent acts", "  ReceiptOS proves"]:
            self.canvas.create_text(qx1 + 8, y, text=line, fill=self.GRAY, font=("SF Mono", 9), anchor="w")
            y += 13

        # ─── Footer ─────────────────────────────────
        self.canvas.create_text(self.screen_w - 10, self.screen_h - 10,
                                text="ESC to quit · tick #%d · %s" % (d["tick"], ts),
                                fill=self.DIM, font=("SF Mono", 8), anchor="se")

        self.root.after(500, self._render)

    def _draw_quadrant_header(self, x, y, title, color, badge="", badge_color=None):
        self.canvas.create_text(x + 8, y, text=title, fill=color, font=("SF Mono", 10, "bold"), anchor="w")
        if badge:
            bc = badge_color or self.GRAY
            self.canvas.create_text(x + self.cx - 20, y, text=badge, fill=bc, font=("SF Mono", 8), anchor="e")
        # Border line under header
        self.canvas.create_line(x, y + 14, x + self.cx - 12, y + 14, fill=self.DIM, width=1)


if __name__ == "__main__":
    overlay = ScreenDBOverlay()
