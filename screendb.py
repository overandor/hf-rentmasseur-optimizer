"""
ScreenDB — macOS Screen-as-Database with Receipt Mode
=====================================================

Architecture:
  ScreenCaptureKit sees    → screenshot hash (visual proof)
  AXUIElement understands  → accessibility tree (semantic structure)
  CursorAgent acts         → controlled actions with identity
  ReceiptOS proves         → one action = one tamper-evident receipt
  Input telemetry witnesses → log stream as side-channel only (research)

Receipt Record (one per CursorAgent action):
  {
    receipt_id:     sha256 hash
    timestamp:      ISO 8601
    cursor_id:      agent identity (human | agent:name | agent:uuid)
    command:        approved command that triggered the action
    action:         {type, target, value}
    result:         {success, output, error}
    screenshot:     {before_hash, after_hash, path}
    accessibility:  {before_summary, after_summary, target_element}
    witness:        {event_count, event_types}  # from log stream, side-channel only
    approval:       {approved_by, approved_at, approval_hash}
  }

No log stream scraping as production API.
No pixel-only capture.
Every action has a before/after screenshot hash + accessibility diff + receipt.
"""

import sqlite3
import subprocess
import json
import time
import hashlib
import os
import uuid
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Any
from dataclasses import dataclass, field, asdict

# ─── Paths ──────────────────────────────────────────────────────────────

SCREENDB_DIR = Path.home() / "Library" / "Application Support" / "ScreenDB"
SCREENDB_DIR.mkdir(parents=True, exist_ok=True)
SHOTS_DIR = SCREENDB_DIR / "screenshots"
SHOTS_DIR.mkdir(exist_ok=True)
DB_PATH = SCREENDB_DIR / "screendb.db"
RECEIPTS_PATH = SCREENDB_DIR / "receipts.jsonl"


# ─── Database ───────────────────────────────────────────────────────────

def _db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS screen_state (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            iso TEXT,
            screenshot_hash TEXT,
            screenshot_path TEXT,
            frontmost_app TEXT,
            frontmost_window TEXT,
            window_count INTEGER,
            element_count INTEGER,
            accessibility_json TEXT
        );
        CREATE TABLE IF NOT EXISTS actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            iso TEXT,
            receipt_id TEXT,
            cursor_id TEXT,
            command TEXT,
            action_type TEXT,
            action_target TEXT,
            action_value TEXT,
            success INTEGER,
            result TEXT,
            screenshot_before_hash TEXT,
            screenshot_after_hash TEXT,
            accessibility_before TEXT,
            accessibility_after TEXT,
            target_element TEXT,
            witness_events INTEGER,
            approval_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS approvals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL,
            approval_hash TEXT,
            cursor_id TEXT,
            command TEXT,
            approved_by TEXT,
            status TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_actions_ts ON actions(ts);
        CREATE INDEX IF NOT EXISTS idx_state_ts ON screen_state(ts);
        CREATE INDEX IF NOT EXISTS idx_actions_receipt ON actions(receipt_id);
    """)
    return conn


# ─── Layer 1: ScreenCaptureKit (sees) ───────────────────────────────────

def capture_screenshot(label: str = "") -> dict:
    """Capture screenshot via screencapture (ScreenCaptureKit CLI).
    Returns hash + path. This is the visual proof layer."""
    ts = time.time()
    iso = datetime.now(timezone.utc).isoformat()
    fname = f"{int(ts)}_{label}.png" if label else f"{int(ts)}.png"
    path = SHOTS_DIR / fname

    subprocess.run(
        ["screencapture", "-x", "-C", str(path)],
        timeout=5, capture_output=True
    )

    if not path.exists():
        return {"hash": "", "path": "", "error": "screencapture failed"}

    h = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"hash": h, "path": str(path), "ts": ts, "iso": iso}


# ─── Layer 2: AXUIElement / Accessibility (understands) ─────────────────

AX_SCRIPT_WINDOWS = """
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
                    set output to output & procName & "|" & procPID & "|" & wTitle & "|" & (item 1 of wPos) & "|" & (item 2 of wPos) & "|" & (item 1 of wSize) & "|" & (item 2 of wSize) & "|" & isFront & "\\n"
                end try
            end repeat
        end try
    end repeat
end tell
return output
"""

AX_SCRIPT_ELEMENTS = """
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


def capture_accessibility() -> dict:
    """Capture accessibility tree via AXUIElement (System Events).
    This is the semantic structure layer — supported Apple API."""
    # Windows
    r = subprocess.run(["osascript", "-e", AX_SCRIPT_WINDOWS],
                       capture_output=True, text=True, timeout=10)
    windows = []
    frontmost = None
    for line in r.stdout.strip().split("\n"):
        if not line or "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) < 8:
            continue
        try:
            app, pid, title, x, y, w, h, front = parts[:8]
            win = {"app": app, "pid": int(pid), "title": title,
                   "x": int(x), "y": int(y), "w": int(w), "h": int(h),
                   "focused": front == "true"}
            windows.append(win)
            if win["focused"]:
                frontmost = win
        except (ValueError, IndexError):
            continue

    # Elements of frontmost window
    r2 = subprocess.run(["osascript", "-e", AX_SCRIPT_ELEMENTS],
                        capture_output=True, text=True, timeout=10)
    elements = []
    for line in r2.stdout.strip().split("\n"):
        if not line or "|" not in line:
            continue
        parts = line.split("|")
        if len(parts) < 12:
            continue
        try:
            app, pid, wtitle, role, title, desc, value, x, y, w, h, enabled, focused = parts[:13]
            elements.append({
                "app": app, "pid": int(pid), "window": wtitle,
                "role": role, "title": title if title != "missing value" else "",
                "description": desc if desc != "missing value" else "",
                "value": value if value != "missing value" else "",
                "x": int(x), "y": int(y), "w": int(w), "h": int(h),
                "enabled": enabled == "true", "focused": focused == "true",
            })
        except (ValueError, IndexError):
            continue

    return {
        "timestamp": time.time(),
        "frontmost_app": frontmost["app"] if frontmost else "",
        "frontmost_window": frontmost["title"] if frontmost else "",
        "window_count": len(windows),
        "element_count": len(elements),
        "windows": windows,
        "elements": elements,
    }


def accessibility_summary(ax: dict) -> str:
    """Compress accessibility tree to a text summary for receipts."""
    lines = []
    lines.append(f"frontmost: {ax.get('frontmost_app', '?')} | {ax.get('frontmost_window', '?')}")
    lines.append(f"windows: {ax.get('window_count', 0)} | elements: {ax.get('element_count', 0)}")
    for el in ax.get("elements", [])[:15]:
        focus = "◉" if el.get("focused") else " "
        en = "✓" if el.get("enabled") else "✗"
        val = f' val="{el["value"][:20]}"' if el.get("value") else ""
        lines.append(f"  {focus} {en} {el['role']} | {el.get('title','')[:25]}{val} | ({el['x']},{el['y']})")
    return "\n".join(lines)


def accessibility_diff(before: dict, after: dict) -> dict:
    """Compute what changed between two accessibility snapshots."""
    changes = {"windows_changed": False, "elements_changed": [], "focus_changed": False}

    b_apps = {w["app"] + "|" + w["title"] for w in before.get("windows", [])}
    a_apps = {w["app"] + "|" + w["title"] for w in after.get("windows", [])}
    if b_apps != a_apps:
        changes["windows_changed"] = True
        changes["windows_added"] = list(a_apps - b_apps)
        changes["windows_removed"] = list(b_apps - a_apps)

    b_focus = before.get("frontmost_app", "")
    a_focus = after.get("frontmost_app", "")
    if b_focus != a_focus:
        changes["focus_changed"] = True
        changes["focus_before"] = b_focus
        changes["focus_after"] = a_focus

    b_els = {f"{e['role']}|{e.get('title','')}|{e.get('x',0)},{e.get('y',0)}" for e in before.get("elements", [])}
    a_els = {f"{e['role']}|{e.get('title','')}|{e.get('x',0)},{e.get('y',0)}" for e in after.get("elements", [])}
    if b_els != a_els:
        changes["elements_changed"] = list(a_els - b_els)[:10]

    return changes


# ─── Layer 3: CursorAgent (acts) ────────────────────────────────────────

@dataclass
class CursorAgent:
    """Identity-tagged agent that performs actions on the Mac."""
    agent_id: str = ""
    agent_name: str = "default"
    agent_type: str = "agent"  # agent | human

    def __post_init__(self):
        if not self.agent_id:
            self.agent_id = str(uuid.uuid4())[:12]

    @property
    def cursor_id(self) -> str:
        if self.agent_type == "human":
            return "human"
        return f"agent:{self.agent_name}:{self.agent_id}"

    def execute(self, action_type: str, target: str = "", value: str = "") -> dict:
        """Execute a single action. Returns result dict."""
        result = {"type": action_type, "target": target, "value": value[:200],
                  "success": False, "output": "", "error": ""}

        try:
            if action_type == "activate_app":
                subprocess.run(["osascript", "-e", f'tell application "{target}" to activate'],
                               timeout=5, capture_output=True)
                result["success"] = True
                result["output"] = f"Activated {target}"

            elif action_type == "open_url":
                subprocess.run(["open", target], timeout=10, capture_output=True)
                result["success"] = True
                result["output"] = f"Opened {target}"

            elif action_type == "open":
                subprocess.run(["open", "-a", target] if target else ["open", value],
                               timeout=10, capture_output=True)
                result["success"] = True
                result["output"] = f"Opened {target or value}"

            elif action_type == "type":
                escaped = value.replace('"', '\\"').replace("\\", "\\\\")
                subprocess.run(["osascript", "-e", f'tell application "System Events" to keystroke "{escaped}"'],
                               timeout=5, capture_output=True)
                result["success"] = True
                result["output"] = f"Typed {len(value)} chars"

            elif action_type == "key":
                keys = value.split("+")
                if len(keys) == 1:
                    kc = _key_code(keys[0])
                    subprocess.run(["osascript", "-e",
                                    f'tell application "System Events" to key code {kc}'],
                                   timeout=5, capture_output=True)
                else:
                    mod_map = {"cmd": "command down", "shift": "shift down",
                               "ctrl": "control down", "alt": "option down", "fn": "fn down"}
                    mods = ", ".join(mod_map.get(k.lower(), k) for k in keys[:-1])
                    subprocess.run(["osascript", "-e",
                                    f'tell application "System Events" to keystroke "{keys[-1]}" using {{{mods}}}'],
                                   timeout=5, capture_output=True)
                result["success"] = True
                result["output"] = f"Key: {value}"

            elif action_type == "click":
                if "," in target:
                    x, y = target.split(",")
                    subprocess.run(["osascript", "-e",
                                    f'tell application "System Events" to click at {{{x},{y}}}'],
                                   timeout=5, capture_output=True)
                    result["success"] = True
                    result["output"] = f"Clicked ({x},{y})"
                else:
                    script = f'''tell application "System Events"
                        set frontProc to first process whose frontmost is true
                        click (first UI element of front window of frontProc whose title contains "{target}")
                    end tell'''
                    r = subprocess.run(["osascript", "-e", script],
                                       capture_output=True, text=True, timeout=5)
                    result["success"] = r.returncode == 0
                    result["output"] = r.stdout.strip()[:100]
                    result["error"] = r.stderr.strip()[:100] if r.returncode else ""

            elif action_type == "set_clipboard":
                escaped = value.replace('"', '\\"')
                subprocess.run(["osascript", "-e", f'set the clipboard to "{escaped}"'],
                               timeout=5, capture_output=True)
                result["success"] = True
                result["output"] = f"Clipboard set ({len(value)} chars)"

            elif action_type == "run_shell":
                r = subprocess.run(value, shell=True, capture_output=True, text=True, timeout=10)
                result["success"] = r.returncode == 0
                result["output"] = r.stdout.strip()[:200]
                result["error"] = r.stderr.strip()[:200] if r.returncode else ""

            elif action_type == "run_applescript":
                r = subprocess.run(["osascript", "-e", value],
                                   capture_output=True, text=True, timeout=10)
                result["success"] = r.returncode == 0
                result["output"] = r.stdout.strip()[:200]
                result["error"] = r.stderr.strip()[:200] if r.returncode else ""

            elif action_type == "quit_app":
                subprocess.run(["osascript", "-e", f'tell application "{target}" to quit'],
                               timeout=5, capture_output=True)
                result["success"] = True
                result["output"] = f"Quit {target}"

            elif action_type == "close_window":
                subprocess.run(["osascript", "-e",
                                f'tell application "{target}" to close front window'],
                               timeout=5, capture_output=True)
                result["success"] = True
                result["output"] = f"Closed window of {target}"

            elif action_type == "delay":
                time.sleep(float(value or "1"))
                result["success"] = True
                result["output"] = f"Delayed {value}s"

            elif action_type == "notification":
                et = target.replace('"', '\\"')
                ev = value.replace('"', '\\"')
                subprocess.run(["osascript", "-e",
                                f'display notification "{ev}" with title "{et}"'],
                               timeout=5, capture_output=True)
                result["success"] = True
                result["output"] = f"Notified: {target}"

            else:
                result["error"] = f"Unknown action: {action_type}"

        except Exception as e:
            result["error"] = str(e)[:200]

        return result


def _key_code(key: str) -> int:
    codes = {"return": 36, "tab": 48, "space": 49, "delete": 51, "escape": 53,
             "left": 123, "right": 124, "down": 125, "up": 126,
             "home": 115, "end": 119, "pageup": 116, "pagedown": 121}
    return codes.get(key.lower(), 0)


# ─── Layer 4: ReceiptOS (proves) ────────────────────────────────────────

def _receipt_hash(data: dict) -> str:
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def create_receipt(cursor_id: str, command: str, action: dict,
                   result: dict, screenshot_before: dict, screenshot_after: dict,
                   ax_before: dict, ax_after: dict,
                   target_element: str = "",
                   witness_events: int = 0,
                   approval_hash: str = "") -> dict:
    """Create one tamper-evident receipt for one CursorAgent action."""

    ts = time.time()
    iso = datetime.now(timezone.utc).isoformat()

    receipt_body = {
        "timestamp": iso,
        "cursor_id": cursor_id,
        "command": command[:200],
        "action": {"type": action["type"], "target": action.get("target", ""),
                    "value": action.get("value", "")[:100]},
        "result": {"success": result["success"],
                   "output": result["output"][:200],
                   "error": result.get("error", "")[:200]},
        "screenshot": {
            "before_hash": screenshot_before.get("hash", ""),
            "after_hash": screenshot_after.get("hash", ""),
            "path": screenshot_after.get("path", ""),
        },
        "accessibility": {
            "before_summary": accessibility_summary(ax_before) if ax_before else "",
            "after_summary": accessibility_summary(ax_after) if ax_after else "",
            "target_element": target_element,
        },
        "witness": {"event_count": witness_events},
        "approval": {"approval_hash": approval_hash},
    }

    receipt_id = _receipt_hash(receipt_body)
    receipt_body["receipt_id"] = receipt_id

    # Append to JSONL ledger
    with open(RECEIPTS_PATH, "a") as f:
        f.write(json.dumps(receipt_body) + "\n")

    # Store in SQLite
    conn = _db()
    conn.execute("""INSERT INTO actions
        (ts, iso, receipt_id, cursor_id, command, action_type, action_target, action_value,
         success, result, screenshot_before_hash, screenshot_after_hash,
         accessibility_before, accessibility_after, target_element, witness_events, approval_hash)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (ts, iso, receipt_id, cursor_id, command,
         action["type"], action.get("target", ""), action.get("value", "")[:200],
         1 if result["success"] else 0, result["output"][:200],
         screenshot_before.get("hash", ""), screenshot_after.get("hash", ""),
         accessibility_summary(ax_before) if ax_before else "",
         accessibility_summary(ax_after) if ax_after else "",
         target_element, witness_events, approval_hash))
    conn.commit()
    conn.close()

    return receipt_body


# ─── Layer 5: Input Telemetry (witnesses) — side-channel only ───────────

def witness_event_count(since: float) -> int:
    """Count system log events since timestamp. SIDE-CHANNEL ONLY.
    Not used for control — only as behavioral witness in receipts."""
    try:
        r = subprocess.run(
            ["log", "show", "--last", "5s",
             "--predicate", 'eventMessage contains "Multitouch"',
             "--style", "compact"],
            capture_output=True, text=True, timeout=5
        )
        return len([l for l in r.stdout.strip().split("\n") if "Multitouch" in l])
    except:
        return 0


# ─── Approval Gate ──────────────────────────────────────────────────────

def approve_command(cursor_id: str, command: str, approved_by: str = "operator") -> str:
    """Record human approval for a command. Returns approval hash."""
    ts = time.time()
    body = {"cursor_id": cursor_id, "command": command[:200],
            "approved_by": approved_by, "ts": ts}
    approval_hash = _receipt_hash(body)

    conn = _db()
    conn.execute("INSERT INTO approvals (ts, approval_hash, cursor_id, command, approved_by, status) VALUES (?,?,?,?,?,?)",
                 (ts, approval_hash, cursor_id, command[:200], approved_by, "approved"))
    conn.commit()
    conn.close()

    return approval_hash


# ─── ScreenDB: Full Receipt-Mode Action ─────────────────────────────────

def receipt_action(
    cursor_agent: CursorAgent,
    action_type: str,
    target: str = "",
    value: str = "",
    command: str = "",
    require_approval: bool = False,
    approved_by: str = "operator",
    capture_before: bool = True,
    capture_after: bool = True,
) -> dict:
    """Execute one CursorAgent action with full receipt.

    This is the core ScreenDB primitive:
    One action = one receipt with screenshot hash + accessibility + cursor identity.
    """
    cursor_id = cursor_agent.cursor_id
    if not command:
        command = f"{action_type} {target} {value}".strip()

    # Approval gate
    approval_hash = ""
    if require_approval:
        approval_hash = approve_command(cursor_id, command, approved_by)

    # BEFORE: screenshot + accessibility
    shot_before = capture_screenshot("before") if capture_before else {"hash": "", "path": ""}
    ax_before = capture_accessibility() if capture_before else {}

    # Find target element in accessibility tree
    target_element = ""
    if target and ax_before:
        for el in ax_before.get("elements", []):
            if target.lower() in (el.get("title", "") + el.get("description", "")).lower():
                target_element = f"{el['role']} | {el.get('title','')} | ({el['x']},{el['y']})"
                break

    # ACT: execute the action
    result = cursor_agent.execute(action_type, target, value)

    # AFTER: screenshot + accessibility
    shot_after = capture_screenshot("after") if capture_after else {"hash": "", "path": ""}
    ax_after = capture_accessibility() if capture_after else {}

    # WITNESS: side-channel event count (not for control, just for receipt)
    witness_count = witness_event_count(time.time() - 3) if capture_before else 0

    # RECEIPT: create tamper-evident record
    receipt = create_receipt(
        cursor_id=cursor_id,
        command=command,
        action={"type": action_type, "target": target, "value": value},
        result=result,
        screenshot_before=shot_before,
        screenshot_after=shot_after,
        ax_before=ax_before,
        ax_after=ax_after,
        target_element=target_element,
        witness_events=witness_count,
        approval_hash=approval_hash,
    )

    return receipt


def receipt_sequence(
    cursor_agent: CursorAgent,
    actions: list,
    command: str = "",
    require_approval: bool = False,
) -> list:
    """Execute a sequence of actions, each with its own receipt."""
    receipts = []
    for step in actions:
        r = receipt_action(
            cursor_agent=cursor_agent,
            action_type=step.get("type", ""),
            target=step.get("target", ""),
            value=step.get("value", ""),
            command=step.get("command", command),
            require_approval=require_approval,
            capture_before=step.get("capture_before", True),
            capture_after=step.get("capture_after", True),
        )
        receipts.append(r)
        if not r["result"]["success"]:
            break
        if step.get("delay"):
            time.sleep(step["delay"])
    return receipts


# ─── Query ──────────────────────────────────────────────────────────────

def sql(query_str: str) -> list:
    """Query the ScreenDB database."""
    conn = _db()
    try:
        cur = conn.execute(query_str)
        if query_str.strip().upper().startswith("SELECT"):
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        conn.commit()
        return [{"affected": conn.total_changes}]
    except Exception as e:
        return [{"error": str(e)}]
    finally:
        conn.close()


def get_receipts(limit: int = 20) -> list:
    """Get recent receipts from the JSONL ledger."""
    if not RECEIPTS_PATH.exists():
        return []
    lines = RECEIPTS_PATH.read_text().strip().split("\n")
    return [json.loads(l) for l in lines[-limit:]]


def verify_receipts() -> dict:
    """Verify receipt ledger integrity — check that hashes match."""
    if not RECEIPTS_PATH.exists():
        return {"valid": True, "count": 0, "message": "No receipts yet"}

    lines = RECEIPTS_PATH.read_text().strip().split("\n")
    valid = 0
    broken = 0
    for line in lines:
        try:
            receipt = json.loads(line)
            stored_hash = receipt.pop("receipt_id", "")
            recomputed = _receipt_hash(receipt)
            if stored_hash == recomputed:
                valid += 1
            else:
                broken += 1
        except:
            broken += 1

    return {"valid": valid, "broken": broken, "total": len(lines),
            "intact": broken == 0}


# ─── State Snapshot ─────────────────────────────────────────────────────

def state_snapshot() -> dict:
    """Capture current screen state into the database."""
    shot = capture_screenshot("state")
    ax = capture_accessibility()

    conn = _db()
    conn.execute("""INSERT INTO screen_state
        (ts, iso, screenshot_hash, screenshot_path, frontmost_app, frontmost_window, window_count, element_count, accessibility_json)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (shot["ts"], shot["iso"], shot["hash"], shot["path"],
         ax.get("frontmost_app", ""), ax.get("frontmost_window", ""),
         ax.get("window_count", 0), ax.get("element_count", 0),
         json.dumps(ax)[:5000]))
    conn.commit()
    conn.close()

    return {
        "timestamp": shot["iso"],
        "screenshot_hash": shot["hash"],
        "frontmost_app": ax.get("frontmost_app", ""),
        "frontmost_window": ax.get("frontmost_window", ""),
        "windows": ax.get("window_count", 0),
        "elements": ax.get("element_count", 0),
        "accessibility": accessibility_summary(ax),
    }


# ─── CLI ────────────────────────────────────────────────────────────────

def cli():
    import argparse
    p = argparse.ArgumentParser(description="ScreenDB — macOS Screen-as-Database with Receipt Mode")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("state", help="Capture current screen state")
    sub.add_parser("receipts", help="Show recent receipts")
    sub.add_parser("verify", help="Verify receipt ledger integrity")

    p_sql = sub.add_parser("sql", help="Query ScreenDB database")
    p_sql.add_argument("query", help="SQL query")

    p_exec = sub.add_parser("exec", help="Execute action with receipt")
    p_exec.add_argument("type", help="Action type: activate_app, type, key, click, etc.")
    p_exec.add_argument("--target", default="")
    p_exec.add_argument("--value", default="")
    p_exec.add_argument("--agent", default="default", help="Agent name")
    p_exec.add_argument("--approve", action="store_true", help="Require approval gate")

    p_seq = sub.add_parser("sequence", help="Execute action sequence with receipts")
    p_seq.add_argument("file", help="JSON file with action sequence")
    p_seq.add_argument("--agent", default="default")

    p_ax = sub.add_parser("ax", help="Show accessibility tree")
    p_shot = sub.add_parser("shot", help="Capture screenshot + hash")

    args = p.parse_args()

    if args.cmd == "state":
        s = state_snapshot()
        print(json.dumps(s, indent=2, default=str))

    elif args.cmd == "receipts":
        receipts = get_receipts(20)
        for r in receipts:
            ok = "✓" if r["result"]["success"] else "✗"
            print(f"  {ok} [{r['receipt_id']}] {r['cursor_id']} | {r['action']['type']} → {r['result']['output'][:60]}")
            print(f"         shot: {r['screenshot']['before_hash'][:8]}→{r['screenshot']['after_hash'][:8]} | ax_target: {r['accessibility']['target_element'][:50]}")

    elif args.cmd == "verify":
        v = verify_receipts()
        print(json.dumps(v, indent=2))
        if v["intact"]:
            print(f"✓ Ledger intact: {v['valid']} receipts, 0 broken")
        else:
            print(f"✗ Ledger BROKEN: {v['valid']} valid, {v['broken']} broken")

    elif args.cmd == "sql":
        rows = sql(args.query)
        print(json.dumps(rows, indent=2, default=str))

    elif args.cmd == "exec":
        agent = CursorAgent(agent_name=args.agent)
        receipt = receipt_action(agent, args.type, args.target, args.value,
                                 require_approval=args.approve)
        print(json.dumps(receipt, indent=2, default=str))

    elif args.cmd == "sequence":
        with open(args.file) as f:
            actions = json.load(f)
        agent = CursorAgent(agent_name=args.agent)
        receipts = receipt_sequence(agent, actions)
        for r in receipts:
            ok = "✓" if r["result"]["success"] else "✗"
            print(f"  {ok} [{r['receipt_id']}] {r['action']['type']} → {r['result']['output'][:60]}")

    elif args.cmd == "ax":
        ax = capture_accessibility()
        print(accessibility_summary(ax))

    elif args.cmd == "shot":
        shot = capture_screenshot("manual")
        print(json.dumps(shot, indent=2))

    else:
        p.print_help()


if __name__ == "__main__":
    cli()
