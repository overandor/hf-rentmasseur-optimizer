"""
Mac Agent Loop — LLM-driven control of macOS.
=============================================
Observe → LLM decides → Act → Verify → Repeat.

The LLM never sees pixels. It sees:
  - SQL query results (windows, elements, processes)
  - Event stream (trackpad, keyboard, mutations)
  - Action results + receipts

It responds with:
  - SQL queries to gather more context
  - Actions to execute (click, type, key, open, run_shell, etc.)
  - "done" when task is complete

Protocol:
  SYSTEM: You are a macOS controller. You see the screen as SQL tables.
          Available actions: open, click, type, key, scroll, activate_app,
          quit_app, set_clipboard, run_shell, run_applescript, screenshot,
          notification, delay, close_window, minimize_window
          Available queries: any SQL against the runtime database
          Tables: windows, elements, processes, events, clipboard, actions
          Respond in JSON: {"action": "query|exec|done", ...}

  USER:   <current state snapshot>

  ASSISTANT: {"action": "query", "sql": "SELECT app, title FROM windows WHERE focused=1"}
  → returns rows

  ASSISTANT: {"action": "exec", "type": "activate_app", "target": "Safari"}
  → returns receipt

  ASSISTANT: {"action": "exec", "type": "type", "value": "github.com"}
  → returns receipt

  ASSISTANT: {"action": "done", "summary": "Opened Safari and navigated to github.com"}
"""

import json
import time
import os
import subprocess
import sqlite3
from pathlib import Path
from typing import Optional, Any

# Local imports
from mac_runtime import (
    _db, DB_PATH, capture_windows, capture_elements, capture_processes,
    capture_clipboard, run_action, query, snapshot, MacRuntime, EventCapture
)
from screendb import (
    CursorAgent as ScreenCursorAgent,
    receipt_action as screendb_receipt_action,
    capture_accessibility as screendb_capture_ax,
    accessibility_summary as screendb_ax_summary,
    state_snapshot as screendb_state,
    get_receipts as screendb_get_receipts,
    verify_receipts as screendb_verify,
    sql as screendb_sql,
)


# ─── LLM Interface ──────────────────────────────────────────────────────

def _call_ollama(prompt: str, system: str = "", model: str = "llama3.2") -> str:
    """Call local Ollama for LLM reasoning."""
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": 0.1, "num_predict": 512}
    }
    import urllib.request
    req = urllib.request.Request(
        "http://localhost:11434/api/generate",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("response", "")
    except Exception as e:
        return f"ERROR: {e}"


def _call_openai(prompt: str, system: str = "", model: str = "gpt-4o-mini") -> str:
    """Call OpenAI API for LLM reasoning."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return "ERROR: No OPENAI_API_KEY set"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 512
    }
    import urllib.request
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"ERROR: {e}"


def call_llm(prompt: str, system: str, provider: str = "ollama", model: str = "") -> str:
    """Call LLM with fallback."""
    if provider == "openai":
        return _call_openai(prompt, system, model or "gpt-4o-mini")
    elif provider == "anthropic":
        return _call_anthropic(prompt, system, model or "claude-sonnet-4-20250514")
    else:
        return _call_ollama(prompt, system, model or "llama3.2")


def _call_anthropic(prompt: str, system: str, model: str = "claude-sonnet-4-20250514") -> str:
    """Call Anthropic API."""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return "ERROR: No ANTHROPIC_API_KEY set"

    payload = {
        "model": model,
        "max_tokens": 1024,
        "system": system,
        "messages": [{"role": "user", "content": prompt}]
    }
    import urllib.request
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data["content"][0]["text"]
    except Exception as e:
        return f"ERROR: {e}"


# ─── Agent Protocol ─────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a macOS controller agent. You control a Mac through a runtime database.

You NEVER see pixels. You see the screen as SQL tables and text snapshots.

DATABASE TABLES:
- windows(id, ts, pid, app, title, x, y, w, h, focused, minimized, visible)
- elements(id, ts, window_id, pid, role, subrole, title, value, description, x, y, w, h, enabled, focused)
- processes(id, ts, pid, name, cpu, mem, command)
- events(id, ts, type, source, data)
- clipboard(id, ts, type, content, hash)
- actions(id, ts, type, target, value, result, success, receipt)

ACTIONS YOU CAN EXECUTE:
- open: open an app (target=app name)
- open_url: open URL in browser (target=url)
- click: click at coordinates (target="x,y") or element by name (target=button text)
- double_click: double-click at coordinates
- type: type text into focused element (value=text)
- key: press key combo (value="cmd+c", "return", "tab", "shift+a")
- scroll: scroll down (value=amount)
- set_clipboard: set clipboard (value=text)
- activate_app: bring app to front (target=app name)
- quit_app: quit application (target=app name)
- close_window: close front window (target=app name)
- minimize_window: minimize window (target=app name)
- run_shell: run shell command (value=command)
- run_applescript: run AppleScript (value=script)
- screenshot: take screenshot (value=file path)
- notification: show notification (target=title, value=body)
- delay: wait (value=seconds)

RESPONSE FORMAT — always respond with a single JSON object on one line:

To query the database:
{"action": "query", "sql": "SELECT app, title FROM windows WHERE focused=1"}

To execute a control action:
{"action": "exec", "type": "activate_app", "target": "Safari"}

To execute multiple actions in sequence:
{"action": "exec_sequence", "steps": [{"type": "activate_app", "target": "Safari"}, {"type": "delay", "value": "1"}, {"type": "type", "value": "github.com"}, {"type": "key", "value": "return"}]}

To report task complete:
{"action": "done", "summary": "Opened Safari and searched for cats"}

RULES:
- Always query state before acting. Know what windows are open.
- After actions, query again to verify the result changed.
- Use delay between actions that need time (opening apps, loading pages).
- Be precise with coordinates — query the elements table for positions.
- If something fails, try an alternative approach.
- Never claim success without verifying via query.
"""


def _state_snapshot_text() -> str:
    """Build a text snapshot of current Mac state for the LLM."""
    capture_windows()
    capture_processes()

    conn = _db()
    windows = conn.execute(
        "SELECT app, title, x, y, w, h, focused, minimized FROM windows ORDER BY focused DESC"
    ).fetchall()
    elements = conn.execute(
        "SELECT role, title, value, x, y, enabled, focused FROM elements ORDER BY focused DESC LIMIT 20"
    ).fetchall()
    top_procs = conn.execute(
        "SELECT pid, name, cpu, mem FROM processes ORDER BY cpu DESC LIMIT 10"
    ).fetchall()
    recent_actions = conn.execute(
        "SELECT type, target, value, success, result FROM actions ORDER BY ts DESC LIMIT 5"
    ).fetchall()
    conn.close()

    lines = ["=== CURRENT MAC STATE ===", ""]

    lines.append("WINDOWS:")
    for w in windows:
        app, title, x, y, w_, h, focused, mini = w
        mark = "◉" if focused else " "
        mini_s = " [min]" if mini else ""
        lines.append(f"  {mark} {app} | {title[:40]} | ({x},{y}) {w_}x{h}{mini_s}")

    if elements:
        lines.append("")
        lines.append("UI ELEMENTS (frontmost window):")
        for e in elements:
            role, title, value, x, y, enabled, focused = e
            en = "✓" if enabled else "✗"
            focus = "◉" if focused else " "
            val = f' val="{value[:20]}"' if value and value != "missing value" else ""
            title_s = title[:25] if title and title != "missing value" else ""
            lines.append(f"  {focus} {en} {role} | {title_s}{val} | ({x},{y})")

    lines.append("")
    lines.append("TOP PROCESSES:")
    for p in top_procs:
        pid, name, cpu, mem = p
        lines.append(f"  {pid:>7} {name[:25]:<25} cpu={cpu:>5}% mem={mem:>8}")

    if recent_actions:
        lines.append("")
        lines.append("RECENT ACTIONS:")
        for a in recent_actions:
            atype, target, value, success, result = a
            ok = "✓" if success else "✗"
            lines.append(f"  {ok} {atype} target={target[:15]} → {result[:60]}")

    return "\n".join(lines)


def _parse_llm_response(text: str) -> dict:
    """Extract JSON from LLM response."""
    # Try to find JSON in the response
    text = text.strip()

    # Remove markdown code fences
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

    # Try direct parse
    try:
        return json.loads(text)
    except:
        pass

    # Try to find JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except:
            pass

    return {"action": "error", "message": f"Could not parse: {text[:200]}"}


def _execute_parsed(parsed: dict, cursor_agent: ScreenCursorAgent = None) -> str:
    """Execute a parsed LLM response and return result text.
    If cursor_agent is provided, all exec actions get ScreenDB receipts."""
    action = parsed.get("action", "")

    if action == "query":
        sql_q = parsed.get("sql", "")
        if not sql_q:
            return "ERROR: No SQL provided"
        # Try ScreenDB first, fall back to mac_runtime
        if "screenshot" in sql_q.lower() or "receipt" in sql_q.lower() or "approval" in sql_q.lower():
            rows = screendb_sql(sql_q)
        else:
            rows = query(sql_q)
        return json.dumps(rows, indent=2, default=str)[:2000]

    elif action == "exec":
        atype = parsed.get("type", "")
        target = parsed.get("target", "")
        value = parsed.get("value", "")
        if not atype:
            return "ERROR: No action type provided"
        if cursor_agent:
            receipt = screendb_receipt_action(cursor_agent, atype, target, value,
                                               command=parsed.get("command", ""))
            return json.dumps({"receipt_id": receipt["receipt_id"],
                              "success": receipt["result"]["success"],
                              "output": receipt["result"]["output"],
                              "screenshot_before": receipt["screenshot"]["before_hash"][:12],
                              "screenshot_after": receipt["screenshot"]["after_hash"][:12],
                              "cursor_id": receipt["cursor_id"]}, default=str)
        result = run_action(atype, target, value)
        return json.dumps(result, default=str)

    elif action == "exec_sequence":
        steps = parsed.get("steps", [])
        if cursor_agent:
            receipts = []
            for step in steps:
                atype = step.get("type", "")
                target = step.get("target", "")
                value = step.get("value", "")
                delay = step.get("delay", 0)
                if atype:
                    r = screendb_receipt_action(cursor_agent, atype, target, value)
                    receipts.append({"receipt_id": r["receipt_id"],
                                    "success": r["result"]["success"],
                                    "output": r["result"]["output"][:80]})
                    if not r["result"]["success"]:
                        break
                if delay:
                    time.sleep(delay)
            return json.dumps(receipts, default=str)[:2000]
        results = []
        for step in steps:
            atype = step.get("type", "")
            target = step.get("target", "")
            value = step.get("value", "")
            delay = step.get("delay", 0)
            if atype:
                r = run_action(atype, target, value)
                results.append(r)
                if not r["success"]:
                    break
            if delay:
                time.sleep(delay)
        return json.dumps(results, indent=2, default=str)[:2000]

    elif action == "done":
        return f"DONE: {parsed.get('summary', '')}"

    elif action == "error":
        return f"ERROR: {parsed.get('message', '')}"

    return f"UNKNOWN ACTION: {action}"


# ─── Agent Loop ─────────────────────────────────────────────────────────

class MacAgent:
    """LLM-driven macOS controller."""

    def __init__(self, provider: str = "ollama", model: str = "",
                 max_steps: int = 20, verbose: bool = True,
                 agent_name: str = "llm-agent"):
        self.provider = provider
        self.model = model
        self.max_steps = max_steps
        self.verbose = verbose
        self.history = []
        self.runtime = MacRuntime(poll_interval=5.0)
        self.cursor_agent = ScreenCursorAgent(agent_name=agent_name)

    def _log(self, msg: str):
        if self.verbose:
            print(msg)

    def run(self, task: str) -> dict:
        """Execute a task on the Mac via LLM control loop."""
        self._log(f"\n{'='*60}")
        self._log(f"TASK: {task}")
        self._log(f"{'='*60}\n")

        self.runtime.start()

        try:
            for step in range(self.max_steps):
                self._log(f"--- Step {step+1}/{self.max_steps} ---")

                # 1. OBSERVE — get current state
                state_text = _state_snapshot_text()

                # 2. BUILD PROMPT with history
                history_text = ""
                if self.history:
                    history_text = "\n\nPREVIOUS STEPS:\n"
                    for i, (obs, decision, result) in enumerate(self.history[-6:]):
                        history_text += f"\nStep {i+1}:\n"
                        history_text += f"  Decision: {json.dumps(decision)[:200]}\n"
                        history_text += f"  Result: {result[:200]}\n"

                prompt = f"""TASK: {task}

{state_text}
{history_text}

What is your next action? Respond with a single JSON object."""

                # 3. DECIDE — LLM decides next action
                self._log(f"  Querying {self.provider}...")
                response = call_llm(prompt, SYSTEM_PROMPT, self.provider, self.model)

                if response.startswith("ERROR:"):
                    self._log(f"  LLM ERROR: {response}")
                    break

                # 4. PARSE
                parsed = _parse_llm_response(response)
                self._log(f"  Decision: {json.dumps(parsed)[:200]}")

                if parsed.get("action") == "done":
                    summary = parsed.get("summary", "Task complete")
                    self._log(f"\n✓ DONE: {summary}")
                    self.history.append((state_text, parsed, f"DONE: {summary}"))
                    return {"success": True, "steps": step + 1, "summary": summary, "history": self.history}

                if parsed.get("action") == "error":
                    self._log(f"  Parse error: {parsed.get('message')}")
                    self.history.append((state_text, parsed, parsed.get("message", "")))
                    continue

                # 5. ACT — execute the action (with ScreenDB receipt)
                result = _execute_parsed(parsed, cursor_agent=self.cursor_agent)
                self._log(f"  Result: {result[:200]}")

                # 6. RECORD
                self.history.append((state_text, parsed, result))

                # 7. VERIFY — small delay then re-observe next loop

                # Check if action failed
                if "ERROR" in result:
                    self._log(f"  ⚠ Action failed, will retry with different approach")

            self._log(f"\n✗ Max steps ({self.max_steps}) reached without completion")
            return {"success": False, "steps": self.max_steps, "summary": "Max steps reached", "history": self.history}

        finally:
            self.runtime.stop()

    def interactive(self):
        """Interactive mode — user gives tasks, agent executes."""
        self._log("Mac Agent Interactive Mode (ScreenDB Receipt Mode)")
        self._log("Type 'quit' to exit, 'state' for state, 'receipts' for receipt ledger, 'verify' to check ledger\n")

        self.runtime.start()
        try:
            while True:
                try:
                    task = input("\n> ").strip()
                except (EOFError, KeyboardInterrupt):
                    break

                if not task:
                    continue
                if task.lower() in ("quit", "exit", "q"):
                    break
                if task.lower() == "state":
                    print(_state_snapshot_text())
                    continue
                if task.lower() == "elements":
                    capture_elements()
                    rows = query("SELECT role, title, value, x, y FROM elements")
                    print(json.dumps(rows, indent=2, default=str))
                    continue
                if task.lower() == "receipts":
                    receipts = screendb_get_receipts(20)
                    for r in receipts:
                        ok = "✓" if r["result"]["success"] else "✗"
                        print(f"  {ok} [{r['receipt_id']}] {r['cursor_id']} | {r['action']['type']} → {r['result']['output'][:60]}")
                    continue
                if task.lower() == "verify":
                    v = screendb_verify()
                    print(f"  Ledger: {'✓ INTACT' if v['intact'] else '✗ BROKEN'} | {v['valid']} valid, {v['broken']} broken")
                    continue
                if task.lower() == "ax":
                    ax = screendb_capture_ax()
                    print(screendb_ax_summary(ax))
                    continue

                result = self.run(task)
                print(f"\nResult: {'✓' if result['success'] else '✗'} {result['summary']}")
        finally:
            self.runtime.stop()


# ─── Receipt ────────────────────────────────────────────────────────────

def agent_receipt(task: str, result: dict) -> str:
    """Generate a receipt for an agent run."""
    import hashlib
    h = hashlib.sha256(
        f"{task}{result['success']}{result['steps']}{time.time()}".encode()
    ).hexdigest()[:16]

    receipt = {
        "receipt_id": h,
        "task": task,
        "success": result["success"],
        "steps": result["steps"],
        "summary": result["summary"],
        "timestamp": time.time(),
    }

    # Append to receipt ledger
    ledger_path = Path.home() / "Library" / "Application Support" / "MacRuntime" / "agent_receipts.jsonl"
    with open(ledger_path, "a") as f:
        f.write(json.dumps(receipt) + "\n")

    return h


# ─── CLI ────────────────────────────────────────────────────────────────

def cli():
    import argparse
    p = argparse.ArgumentParser(description="Mac Agent — LLM-driven macOS control")
    sub = p.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="Execute a task")
    p_run.add_argument("task", help="Natural language task description")
    p_run.add_argument("--provider", default="ollama", choices=["ollama", "openai", "anthropic"])
    p_run.add_argument("--model", default="")
    p_run.add_argument("--max-steps", type=int, default=20)
    p_run.add_argument("--quiet", action="store_true")

    sub.add_parser("interactive", help="Interactive mode")
    p_inter = sub.add_parser("interactive", help="Interactive mode")
    p_inter.add_argument("--provider", default="ollama", choices=["ollama", "openai", "anthropic"])
    p_inter.add_argument("--model", default="")

    p_state = sub.add_parser("state", help="Show current Mac state as text")
    p_state.add_argument("--elements", action="store_true", help="Include UI elements")

    p_receipts = sub.add_parser("receipts", help="Show agent receipts")

    args = p.parse_args()

    if args.cmd == "run":
        agent = MacAgent(
            provider=args.provider, model=args.model,
            max_steps=args.max_steps, verbose=not args.quiet
        )
        result = agent.run(args.task)
        receipt = agent_receipt(args.task, result)
        print(f"\nReceipt: {receipt}")
        print(json.dumps({k: v for k, v in result.items() if k != "history"}, indent=2, default=str))

    elif args.cmd == "interactive":
        agent = MacAgent(provider=args.provider, model=args.model)
        agent.interactive()

    elif args.cmd == "state":
        if args.elements:
            capture_elements()
        print(_state_snapshot_text())

    elif args.cmd == "receipts":
        ledger = Path.home() / "Library" / "Application Support" / "MacRuntime" / "agent_receipts.jsonl"
        if ledger.exists():
            for line in ledger.read_text().strip().split("\n"):
                r = json.loads(line)
                ok = "✓" if r["success"] else "✗"
                print(f"  {ok} [{r['receipt_id']}] {r['task'][:50]} → {r['summary'][:60]}")
        else:
            print("No receipts yet.")

    else:
        p.print_help()


if __name__ == "__main__":
    cli()
