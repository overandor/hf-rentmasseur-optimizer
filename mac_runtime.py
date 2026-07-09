"""
macOS Runtime — Screen-as-Database + Action Control Plane
=========================================================
Turns the Mac into a queryable, controllable system:

  OBSERVE:  windows, UI elements, processes, clipboard, events → SQLite tables
  QUERY:    SELECT * FROM windows WHERE title LIKE '%Safari%'
  CONTROL:  INSERT INTO actions(type, target, value) → executes click/type/open/run

Tables:
  windows      — every open window (pid, app, title, x, y, w, h, focused)
  elements     — UI elements per window (role, title, value, position, enabled)
  processes    — running processes (pid, name, cpu, mem)
  events       — input events (ts, type, data)
  clipboard    — clipboard history (ts, type, content)
  actions      — action log (ts, type, target, value, result, receipt)
  notifications — system notifications

Control:
  run_action(type, target, value) → executes and logs
  SQL: INSERT INTO actions(type, target, value) VALUES ('click', 'Safari', 'URL bar');
"""

import sqlite3
import subprocess
import json
import time
import hashlib
import os
import threading
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from collections import deque
from typing import Optional

DB_PATH = str(Path.home() / "Library" / "Application Support" / "MacRuntime" / "runtime.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS windows (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, pid INTEGER, app TEXT, title TEXT,
            x INTEGER, y INTEGER, w INTEGER, h INTEGER,
            focused INTEGER, minimized INTEGER, visible INTEGER
        );
        CREATE TABLE IF NOT EXISTS elements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, window_id INTEGER, pid INTEGER,
            role TEXT, subrole TEXT, title TEXT, value TEXT,
            description TEXT, x INTEGER, y INTEGER, w INTEGER, h INTEGER,
            enabled INTEGER, focused INTEGER
        );
        CREATE TABLE IF NOT EXISTS processes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, pid INTEGER, name TEXT, cpu REAL, mem INTEGER, command TEXT
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, type TEXT, source TEXT, data TEXT
        );
        CREATE TABLE IF NOT EXISTS clipboard (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, type TEXT, content TEXT, hash TEXT
        );
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, type TEXT, target TEXT, value TEXT,
            result TEXT, success INTEGER, receipt TEXT
        );
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, app TEXT, title TEXT, body TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_windows_ts ON windows(ts);
        CREATE INDEX IF NOT EXISTS idx_elements_ts ON elements(ts);
        CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
        CREATE INDEX IF NOT EXISTS idx_actions_ts ON actions(ts);
    """)
    return conn


# ─── OBSERVE: Window Enumeration ────────────────────────────────────────

APPLESCRIPT_WINDOWS = """
use framework "AppKit"
set output to ""
set workspace to current application's NSWorkspace's sharedWorkspace()
set runningApps to workspace's runningApplications()
repeat with app in runningApps
    try
        set appName to (name of app) as text
        set appPID to (processIdentifier of app) as text
        set output to output & appName & "|" & appPID & "\\n"
    end try
end repeat
return output
"""

APPLESCRIPT_WINDOW_DETAILS = """
tell application "System Events"
    set output to ""
    repeat with proc in (every process whose background only is false)
        try
            set procName to name of proc
            set procPID to unix id of proc
            set isFront to (proc is frontmost)
            repeat with w in (every window of proc)
                try
                    set wTitle to name of w
                    set wPos to position of w
                    set wSize to size of w
                    set wX to item 1 of wPos
                    set wY to item 2 of wPos
                    set wW to item 1 of wSize
                    set wH to item 2 of wSize
                    try
                        set isMin to (miniaturized of w)
                    on error
                        set isMin to false
                    end try
                    try
                        set isVisible to (visible of w)
                    on error
                        set isVisible to true
                    end try
                    set output to output & procName & "|" & procPID & "|" & wTitle & "|" & wX & "|" & wY & "|" & wW & "|" & wH & "|" & isFront & "|" & isMin & "|" & isVisible & "\\n"
                end try
            end repeat
        end try
    end repeat
end tell
return output
"""

def capture_windows() -> list:
    """Capture all open windows into the database."""
    r = subprocess.run(
        ["osascript", "-e", APPLESCRIPT_WINDOW_DETAILS],
        capture_output=True, text=True, timeout=10
    )
    now = time.time()
    rows = []
    for line in r.stdout.strip().split("\n"):
        if not line or "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) < 10:
            continue
        try:
            app, pid, title, x, y, w, h, front, mini, vis = parts[:10]
            rows.append({
                "ts": now, "pid": int(pid), "app": app, "title": title,
                "x": int(x), "y": int(y), "w": int(w), "h": int(h),
                "focused": 1 if front == "true" else 0,
                "minimized": 1 if mini == "true" else 0,
                "visible": 1 if vis == "true" else 0,
            })
        except (ValueError, IndexError):
            continue

    conn = _db()
    conn.execute("DELETE FROM windows")
    for row in rows:
        conn.execute("""INSERT INTO windows (ts, pid, app, title, x, y, w, h, focused, minimized, visible)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (row["ts"], row["pid"], row["app"], row["title"],
             row["x"], row["y"], row["w"], row["h"],
             row["focused"], row["minimized"], row["visible"]))
    conn.commit()
    conn.close()
    return rows


# ─── OBSERVE: UI Elements via Accessibility API ─────────────────────────

APPLESCRIPT_ELEMENTS = """
tell application "System Events"
    set output to ""
    set frontProc to first process whose frontmost is true
    set procName to name of frontProc
    set procPID to unix id of frontProc
    try
        repeat with w in (every window of frontProc)
            try
                set wTitle to name of w
                set elementList to every UI element of w
                repeat with el in elementList
                    try
                        set elRole to role of el
                        set elTitle to ""
                        try
                            set elTitle to title of el
                        end try
                        set elDesc to ""
                        try
                            set elDesc to description of el
                        end try
                        set elValue to ""
                        try
                            set elValue to value of el
                        end try
                        set elPos to {0, 0}
                        try
                            set elPos to position of el
                        end try
                        set elSize to {0, 0}
                        try
                            set elSize to size of el
                        end try
                        set elEnabled to true
                        try
                            set elEnabled to enabled of el
                        end try
                        set elFocused to false
                        try
                            set elFocused to focused of el
                        end try
                        set output to output & procName & "|" & procPID & "|" & wTitle & "|" & elRole & "|" & elTitle & "|" & elDesc & "|" & elValue & "|" & (item 1 of elPos) & "|" & (item 2 of elPos) & "|" & (item 1 of elSize) & "|" & (item 2 of elSize) & "|" & elEnabled & "|" & elFocused & "\\n"
                    end try
                end repeat
            end try
        end repeat
    end try
    return output
end tell
"""

def capture_elements() -> list:
    """Capture UI elements of the frontmost window."""
    r = subprocess.run(
        ["osascript", "-e", APPLESCRIPT_ELEMENTS],
        capture_output=True, text=True, timeout=10
    )
    now = time.time()
    rows = []
    for line in r.stdout.strip().split("\n"):
        if not line or "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) < 12:
            continue
        try:
            app, pid, wtitle, role, title, desc, value, x, y, w, h, enabled, focused = parts[:13]
            rows.append({
                "ts": now, "app": app, "pid": int(pid), "window": wtitle,
                "role": role, "title": title, "description": desc, "value": value,
                "x": int(x), "y": int(y), "w": int(w), "h": int(h),
                "enabled": 1 if enabled == "true" else 0,
                "focused": 1 if focused == "true" else 0,
            })
        except (ValueError, IndexError):
            continue

    conn = _db()
    conn.execute("DELETE FROM elements")
    for row in rows:
        conn.execute("""INSERT INTO elements (ts, window_id, pid, role, subrole, title, value, description, x, y, w, h, enabled, focused)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (row["ts"], 0, row["pid"], row["role"], "", row["title"],
             row["value"], row["description"], row["x"], row["y"],
             row["w"], row["h"], row["enabled"], row["focused"]))
    conn.commit()
    conn.close()
    return rows


# ─── OBSERVE: Processes ─────────────────────────────────────────────────

def capture_processes() -> list:
    """Capture running processes."""
    r = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
    now = time.time()
    rows = []
    for line in r.stdout.strip().split("\n")[1:]:
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        try:
            user, pid, cpu, mem, vsz, rss, tt, stat, started, time_str, command = parts[:11]
            rows.append({
                "ts": now, "pid": int(pid), "name": command.split("/")[-1].split(" ")[0],
                "cpu": float(cpu), "mem": int(rss), "command": command[:200],
            })
        except (ValueError, IndexError):
            continue

    conn = _db()
    conn.execute("DELETE FROM processes")
    for row in rows:
        conn.execute("INSERT INTO processes (ts, pid, name, cpu, mem, command) VALUES (?,?,?,?,?,?)",
                     (row["ts"], row["pid"], row["name"], row["cpu"], row["mem"], row["command"]))
    conn.commit()
    conn.close()
    return rows


# ─── OBSERVE: Clipboard ─────────────────────────────────────────────────

def capture_clipboard() -> Optional[dict]:
    """Capture current clipboard content."""
    import subprocess as sp
    # Text
    r = sp.run(["pbpaste", "-Prefer", "txt"], capture_output=True, text=True, timeout=2)
    content = r.stdout
    if not content:
        return None
    h = hashlib.sha256(content.encode()).hexdigest()[:16]
    now = time.time()

    conn = _db()
    # Check if this content already exists (last 5 entries)
    recent = conn.execute("SELECT hash FROM clipboard ORDER BY ts DESC LIMIT 5").fetchall()
    if any(h == r[0] for r in recent):
        conn.close()
        return None

    conn.execute("INSERT INTO clipboard (ts, type, content, hash) VALUES (?,?,?,?)",
                 (now, "text", content[:500], h))
    conn.commit()
    conn.close()
    return {"ts": now, "type": "text", "content": content[:100], "hash": h}


# ─── OBSERVE: Event Stream (trackpad, keyboard, mouse) ──────────────────

class EventCapture:
    """Capture system events into the database."""

    def __init__(self):
        self.running = False
        self.thread = None
        self.last_clipboard = ""

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.running = False

    def _loop(self):
        while self.running:
            # Clipboard
            try:
                capture_clipboard()
            except:
                pass

            # System log events (Multitouch/HID)
            try:
                r = subprocess.run(
                    ["log", "show", "--last", "3s",
                     "--predicate", 'eventMessage contains "Multitouch" OR eventMessage contains "Button event"',
                     "--style", "compact"],
                    capture_output=True, text=True, timeout=5
                )
                conn = _db()
                now = time.time()
                for line in r.stdout.strip().split("\n"):
                    if "Multitouch" in line or "Button event" in line:
                        # Parse event type
                        if "digitizer" in line:
                            etype = "trackpad_touch"
                        elif "Button event" in line:
                            if "mask=1" in line:
                                etype = "click_down"
                            else:
                                etype = "click_up"
                        else:
                            etype = "hid_event"
                        conn.execute("INSERT INTO events (ts, type, source, data) VALUES (?,?,?,?)",
                                     (now, etype, "WindowServer", line[:300]))
                conn.commit()
                conn.close()
            except:
                pass

            time.sleep(2)


# ─── CONTROL: Actions ───────────────────────────────────────────────────

def _receipt(action_type: str, target: str, value: str, success: bool) -> str:
    h = hashlib.sha256(f"{action_type}{target}{value}{success}{time.time()}".encode()).hexdigest()[:16]
    return h


def run_action(action_type: str, target: str = "", value: str = "") -> dict:
    """Execute a control action on the Mac and log it."""

    result = ""
    success = False

    try:
        if action_type == "open":
            subprocess.run(["open", "-a", target] if target else ["open", value], timeout=10)
            result = f"Opened {target or value}"
            success = True

        elif action_type == "open_url":
            subprocess.run(["open", target], timeout=10)
            result = f"Opened URL: {target}"
            success = True

        elif action_type == "open_file":
            subprocess.run(["open", target], timeout=10)
            result = f"Opened file: {target}"
            success = True

        elif action_type == "click":
            # Click at coordinates or on element
            if target and "," in target:
                x, y = target.split(",")
                script = f'tell application "System Events" to click at {{{x},{y}}}'
                subprocess.run(["osascript", "-e", script], timeout=5)
                result = f"Clicked at ({x},{y})"
                success = True
            else:
                # Click element by name in frontmost app
                script = f'''
                tell application "System Events"
                    set frontProc to first process whose frontmost is true
                    click (first UI element of front window of frontProc whose title contains "{target}")
                end tell'''
                r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
                success = r.returncode == 0
                result = r.stdout.strip() or r.stderr.strip()[:200]

        elif action_type == "double_click":
            if target and "," in target:
                x, y = target.split(",")
                script = f'tell application "System Events" to double click at {{{x},{y}}}'
                subprocess.run(["osascript", "-e", script], timeout=5)
                result = f"Double-clicked at ({x},{y})"
                success = True

        elif action_type == "type":
            # Type text into focused element
            # Escape double quotes
            escaped = value.replace('"', '\\"')
            script = f'tell application "System Events" to keystroke "{escaped}"'
            subprocess.run(["osascript", "-e", script], timeout=5)
            result = f"Typed: {value[:50]}"
            success = True

        elif action_type == "key":
            # Press key combination (e.g., "cmd+c", "return", "tab")
            keys = value.split("+")
            if len(keys) == 1:
                script = f'tell application "System Events" to key code {_key_code(keys[0])}'
            else:
                modifiers = " using {"
                mod_map = {"cmd": "command down", "shift": "shift down",
                          "ctrl": "control down", "alt": "option down", "fn": "fn down"}
                mod_parts = [mod_map.get(k.lower(), k) for k in keys[:-1]]
                modifiers += ", ".join(mod_parts) + "}"
                script = f'tell application "System Events" to keystroke "{keys[-1]}"{modifiers}'
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            success = r.returncode == 0
            result = f"Key: {value}"

        elif action_type == "scroll":
            # Scroll by amount
            amount = value or "3"
            script = f'tell application "System Events" to scroll down {amount}'
            subprocess.run(["osascript", "-e", script], timeout=5)
            result = f"Scrolled down {amount}"
            success = True

        elif action_type == "set_clipboard":
            escaped = value.replace('"', '\\"')
            script = f'set the clipboard to "{escaped}"'
            subprocess.run(["osascript", "-e", script], timeout=5)
            result = f"Clipboard set to: {value[:50]}"
            success = True

        elif action_type == "run_applescript":
            r = subprocess.run(["osascript", "-e", value], capture_output=True, text=True, timeout=10)
            success = r.returncode == 0
            result = r.stdout.strip()[:200] or r.stderr.strip()[:200]

        elif action_type == "run_shell":
            r = subprocess.run(value, shell=True, capture_output=True, text=True, timeout=10)
            success = r.returncode == 0
            result = r.stdout.strip()[:200] or r.stderr.strip()[:200]

        elif action_type == "quit_app":
            script = f'tell application "{target}" to quit'
            subprocess.run(["osascript", "-e", script], timeout=5)
            result = f"Quit {target}"
            success = True

        elif action_type == "activate_app":
            script = f'tell application "{target}" to activate'
            subprocess.run(["osascript", "-e", script], timeout=5)
            result = f"Activated {target}"
            success = True

        elif action_type == "close_window":
            script = f'''
            tell application "{target}"
                close front window
            end tell'''
            r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
            success = r.returncode == 0
            result = f"Closed window of {target}"

        elif action_type == "minimize_window":
            script = f'''
            tell application "System Events"
                set miniaturized of front window of process "{target}" to true
            end tell'''
            subprocess.run(["osascript", "-e", script], timeout=5)
            result = f"Minimized {target}"
            success = True

        elif action_type == "screenshot":
            path = value or f"/tmp/runtime_screenshot_{int(time.time())}.png"
            subprocess.run(["screencapture", "-x", path], timeout=5)
            result = path
            success = os.path.exists(path)

        elif action_type == "notification":
            escaped_title = target.replace('"', '\\"')
            escaped_body = value.replace('"', '\\"')
            script = f'display notification "{escaped_body}" with title "{escaped_title}"'
            subprocess.run(["osascript", "-e", script], timeout=5)
            result = f"Notification: {target}"
            success = True

        elif action_type == "dialog":
            escaped = value.replace('"', '\\"')
            script = f'display dialog "{escaped}" buttons {{"OK"}} default button "OK"'
            subprocess.run(["osascript", "-e", script], timeout=30)
            result = f"Dialog: {value[:50]}"
            success = True

        elif action_type == "delay":
            delay_s = float(value or "1")
            time.sleep(delay_s)
            result = f"Delayed {delay_s}s"
            success = True

        else:
            result = f"Unknown action: {action_type}"

    except Exception as e:
        result = f"Error: {str(e)[:200]}"
        success = False

    # Log to database
    receipt = _receipt(action_type, target, value, success)
    now = time.time()
    conn = _db()
    conn.execute("INSERT INTO actions (ts, type, target, value, result, success, receipt) VALUES (?,?,?,?,?,?,?)",
                 (now, action_type, target, value[:200], result[:200], 1 if success else 0, receipt))
    conn.commit()
    conn.close()

    return {"type": action_type, "target": target, "value": value[:50],
            "result": result[:200], "success": success, "receipt": receipt, "ts": now}


def _key_code(key: str) -> int:
    """Map key names to macOS key codes."""
    codes = {
        "return": 36, "enter": 36, "tab": 48, "space": 49,
        "delete": 51, "escape": 53, "esc": 53,
        "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96,
        "f6": 97, "f7": 98, "f8": 100, "f9": 101, "f10": 109,
        "f11": 103, "f12": 111,
        "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
        "left": 123, "right": 124, "down": 125, "up": 126,
        "a": 0, "b": 11, "c": 8, "d": 2, "e": 14, "f": 3, "g": 5,
        "h": 4, "i": 34, "j": 38, "k": 40, "l": 37, "m": 46, "n": 45,
        "o": 31, "p": 35, "q": 12, "r": 15, "s": 1, "t": 17, "u": 32,
        "v": 9, "w": 13, "x": 7, "y": 16, "z": 6,
        "0": 29, "1": 18, "2": 19, "3": 20, "4": 21, "5": 23,
        "6": 22, "7": 26, "8": 28, "9": 25,
    }
    return codes.get(key.lower(), 0)


# ─── QUERY: SQL Interface ───────────────────────────────────────────────

def query(sql: str) -> list:
    """Run a SQL query against the runtime database."""
    conn = _db()
    try:
        rows = conn.execute(sql).fetchall()
        cols = [d[0] for d in conn.execute(sql).description] if sql.strip().upper().startswith("SELECT") else []
        conn.close()
        if cols:
            return [dict(zip(cols, row)) for row in rows]
        return [{"affected": conn.total_changes}]
    except Exception as e:
        conn.close()
        return [{"error": str(e)}]


def snapshot() -> dict:
    """Full snapshot of the current Mac state."""
    windows = capture_windows()
    elements = capture_elements()
    processes = capture_processes()

    conn = _db()
    event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    action_count = conn.execute("SELECT COUNT(*) FROM actions").fetchone()[0]
    clipboard_count = conn.execute("SELECT COUNT(*) FROM clipboard").fetchone()[0]
    conn.close()

    return {
        "timestamp": datetime.now().isoformat(),
        "windows": len(windows),
        "elements": len(elements),
        "processes": len(processes),
        "total_events": event_count,
        "total_actions": action_count,
        "clipboard_entries": clipboard_count,
        "frontmost": next((w for w in windows if w["focused"]), None),
    }


# ─── Runtime Loop ───────────────────────────────────────────────────────

class MacRuntime:
    """Continuous runtime — observes and controls the Mac."""

    def __init__(self, poll_interval: float = 5.0):
        self.poll_interval = poll_interval
        self.running = False
        self.thread = None
        self.event_capture = EventCapture()

    def start(self):
        """Start the runtime loop."""
        self.running = True
        self.event_capture.start()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        return self

    def stop(self):
        self.running = False
        self.event_capture.stop()

    def _loop(self):
        while self.running:
            try:
                capture_windows()
                capture_processes()
            except:
                pass
            time.sleep(self.poll_interval)

    def execute(self, action_type: str, target: str = "", value: str = "") -> dict:
        """Execute a control action."""
        return run_action(action_type, target, value)

    def execute_sequence(self, actions: list) -> list:
        """Execute a sequence of actions."""
        results = []
        for a in actions:
            r = run_action(a.get("type", ""), a.get("target", ""), a.get("value", ""))
            results.append(r)
            if not r["success"]:
                break
            if "delay" in a:
                time.sleep(a["delay"])
        return results

    def sql(self, query_str: str) -> list:
        """Query the runtime database."""
        return query(query_str)

    def state(self) -> dict:
        """Get current state summary."""
        return snapshot()


# ─── CLI ────────────────────────────────────────────────────────────────

def cli():
    import argparse
    p = argparse.ArgumentParser(description="macOS Runtime — Screen-as-Database + Control")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("snapshot", help="Capture current Mac state")
    sub.add_parser("windows", help="List all windows")
    sub.add_parser("elements", help="List UI elements of frontmost window")
    sub.add_parser("processes", help="List running processes")
    sub.add_parser("events", help="Show recent events")
    sub.add_parser("actions", help="Show action log")
    sub.add_parser("clipboard", help="Show clipboard history")

    p_sql = sub.add_parser("sql", help="Run SQL query")
    p_sql.add_argument("query", help="SQL query string")

    p_exec = sub.add_parser("exec", help="Execute control action")
    p_exec.add_argument("type", help="Action type: open, click, type, key, run_shell, etc.")
    p_exec.add_argument("--target", default="", help="Target (app name, coordinates, etc.)")
    p_exec.add_argument("--value", default="", help="Value (text to type, command to run, etc.)")

    p_seq = sub.add_parser("sequence", help="Execute action sequence from JSON file")
    p_seq.add_argument("file", help="JSON file with action sequence")

    sub.add_parser("start", help="Start runtime loop (continuous capture)")

    args = p.parse_args()

    if args.cmd == "snapshot":
        s = snapshot()
        print(json.dumps(s, indent=2, default=str))

    elif args.cmd == "windows":
        capture_windows()
        rows = query("SELECT app, title, x, y, w, h, focused, minimized FROM windows ORDER BY focused DESC")
        for r in rows:
            focus = "◉" if r["focused"] else " "
            mini = " [min]" if r["minimized"] else ""
            print(f"  {focus} {r['app']:>20} | {r['title'][:40]:<40} | ({r['x']},{r['y']}) {r['w']}x{r['h']}{mini}")

    elif args.cmd == "elements":
        capture_elements()
        rows = query("SELECT role, title, value, x, y, w, h, enabled, focused FROM elements ORDER BY focused DESC")
        for r in rows:
            focus = "◉" if r["focused"] else " "
            en = "✓" if r["enabled"] else "✗"
            val = f' val="{r["value"][:20]}"' if r["value"] else ""
            print(f"  {focus} {en} {r['role']:>20} | {r['title'][:30]:<30}{val} | ({r['x']},{r['y']})")

    elif args.cmd == "processes":
        capture_processes()
        rows = query("SELECT pid, name, cpu, mem FROM processes ORDER BY cpu DESC LIMIT 30")
        for r in rows:
            print(f"  {r['pid']:>7} {r['name'][:30]:<30} cpu={r['cpu']:>5}% mem={r['mem']:>8}")

    elif args.cmd == "events":
        rows = query("SELECT ts, type, source, data FROM events ORDER BY ts DESC LIMIT 30")
        for r in rows:
            print(f"  [{r['ts']:.0f}] {r['type']:>15} {r['source']:>15} | {r['data'][:80]}")

    elif args.cmd == "actions":
        rows = query("SELECT ts, type, target, value, success, receipt FROM actions ORDER BY ts DESC LIMIT 20")
        for r in rows:
            ok = "✓" if r["success"] else "✗"
            print(f"  {ok} [{r['ts']:.0f}] {r['type']:>15} target={r['target'][:20]} val={r['value'][:20]} receipt={r['receipt']}")

    elif args.cmd == "clipboard":
        rows = query("SELECT ts, type, content, hash FROM clipboard ORDER BY ts DESC LIMIT 10")
        for r in rows:
            print(f"  [{r['ts']:.0f}] {r['type']:>5} hash={r['hash']} | {r['content'][:60]}")

    elif args.cmd == "sql":
        rows = query(args.query)
        print(json.dumps(rows, indent=2, default=str))

    elif args.cmd == "exec":
        r = run_action(args.type, args.target, args.value)
        print(json.dumps(r, indent=2, default=str))

    elif args.cmd == "sequence":
        with open(args.file) as f:
            actions = json.load(f)
        rt = MacRuntime()
        results = rt.execute_sequence(actions)
        for r in results:
            ok = "✓" if r["success"] else "✗"
            print(f"  {ok} {r['type']:>15} → {r['result'][:80]}")

    elif args.cmd == "start":
        print("Starting macOS Runtime loop (Ctrl+C to stop)...")
        rt = MacRuntime(poll_interval=5.0).start()
        try:
            while True:
                time.sleep(10)
                s = snapshot()
                print(f"  [{datetime.now().strftime('%H:%M:%S')}] windows={s['windows']} elements={s['elements']} processes={s['processes']} events={s['total_events']} actions={s['total_actions']}")
        except KeyboardInterrupt:
            rt.stop()
            print("Stopped.")

    else:
        p.print_help()


if __name__ == "__main__":
    cli()
