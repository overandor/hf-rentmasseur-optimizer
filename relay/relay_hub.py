#!/usr/bin/env python3
"""
HyperFlow Relay Hub v2 — Pipeline-Based Multi-Agent Control Plane
=================================================================
ChatGPT is the brain. Claude, Codex, Devin, Windsurf are the hands.
Work flows through a deterministic pipeline with clear role assignments.

Pipeline: IDEA → SPEC → ARCHITECT → CODE → BUILD → TEST → RECEIPT → SHIP

Each stage has a designated agent:
  IDEA       → ChatGPT    (product architect, decides what to build)
  SPEC       → ChatGPT    (writes spec, acceptance criteria)
  ARCHITECT  → Claude     (reviews spec, designs architecture, identifies risks)
  CODE       → Codex      (generates minimal patches, writes tests)
  BUILD      → Windsurf   (applies edits, runs builds, resolves integration)
  TEST       → Windsurf   (runs tests, captures results)
  RECEIPT    → Windsurf   (writes structured receipt)
  SHIP       → ChatGPT    (reviews receipt, decides if ready to ship)
"""

import json
import os
import re
import subprocess
import sys
import time
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
RELAY_DB = REPO_ROOT / "relay" / "relay_hub.db"
RELAY_LOG = REPO_ROOT / "relay" / "relay.log"

PIPELINE_STAGES = ["IDEA", "SPEC", "ARCHITECT", "CODE", "BUILD", "TEST", "RECEIPT", "SHIP"]

STAGE_AGENTS = {
    "IDEA":      "chatgpt",
    "SPEC":      "chatgpt",
    "ARCHITECT": "claude",
    "CODE":      "codex",
    "BUILD":     "windsurf",
    "TEST":      "windsurf",
    "RECEIPT":   "windsurf",
    "SHIP":      "chatgpt",
}

STAGE_DESCRIPTIONS = {
    "IDEA":      "ChatGPT decides what to build based on user intent",
    "SPEC":      "ChatGPT writes product spec with acceptance criteria",
    "ARCHITECT": "Claude reviews spec, designs architecture, identifies risks",
    "CODE":      "Codex generates minimal patches and writes tests",
    "BUILD":     "Windsurf applies edits and runs builds",
    "TEST":      "Windsurf runs tests and captures results",
    "RECEIPT":   "Windsurf writes structured receipt with evidence",
    "SHIP":      "ChatGPT reviews receipt and decides if ready to ship",
}

AGENT_PROFILES = {
    "chatgpt": {
        "name": "ChatGPT",
        "role": "Brain / Strategist",
        "capabilities": ["product design", "spec writing", "architecture review", "valuation", "audit", "final approval"],
        "can_execute": False,
        "color": "#a855f7",
        "icon": "🧠",
        "description": "The smartest agent. Can't touch the computer. Commands the others via the relay.",
    },
    "claude": {
        "name": "Claude",
        "role": "Architect / Reviewer",
        "capabilities": ["deep planning", "refactoring", "architecture review", "risk analysis"],
        "can_execute": True,
        "color": "#3b82f6",
        "icon": "🔧",
        "description": "Long-context refactorer. Reviews specs, designs architecture, identifies risks.",
    },
    "codex": {
        "name": "Codex",
        "role": "Patch Generator",
        "capabilities": ["code generation", "TDD", "minimal diffs", "test writing"],
        "can_execute": True,
        "color": "#10b981",
        "icon": "⚡",
        "description": "Test-driven implementer. Generates minimal patches and writes tests.",
    },
    "devin": {
        "name": "Devin",
        "role": "Autonomous Worker",
        "capabilities": ["autonomous coding", "multi-step tasks", "session-based work"],
        "can_execute": True,
        "color": "#f59e0b",
        "icon": "🤖",
        "description": "Autonomous coding agent. Disposable worker — state persists in relay.",
    },
    "windsurf": {
        "name": "Windsurf",
        "role": "IDE Operator",
        "capabilities": ["file editing", "build execution", "test running", "repo navigation", "receipt writing"],
        "can_execute": True,
        "color": "#06b6d4",
        "icon": "🏄",
        "description": "Persistent IDE agent. Keeps project context, applies edits, runs builds.",
    },
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def get_db():
    import sqlite3
    conn = sqlite3.connect(str(RELAY_DB))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    import sqlite3
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            current_stage TEXT DEFAULT 'IDEA',
            status TEXT DEFAULT 'active',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            stage_results TEXT DEFAULT '{}'
        );
        CREATE TABLE IF NOT EXISTS stage_history (
            id TEXT PRIMARY KEY,
            project_id TEXT NOT NULL,
            stage TEXT NOT NULL,
            agent TEXT NOT NULL,
            input TEXT,
            output TEXT,
            status TEXT DEFAULT 'pending',
            started_at TEXT,
            completed_at TEXT,
            duration_ms INTEGER
        );
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            from_agent TEXT NOT NULL,
            to_agent TEXT NOT NULL,
            message_type TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT DEFAULT 'pending',
            result TEXT,
            timestamp TEXT NOT NULL,
            completed_at TEXT
        );
        CREATE TABLE IF NOT EXISTS agent_status (
            agent TEXT PRIMARY KEY,
            status TEXT DEFAULT 'idle',
            current_task TEXT,
            current_project TEXT,
            last_seen TEXT,
            tasks_completed INTEGER DEFAULT 0,
            tasks_failed INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS receipts (
            id TEXT PRIMARY KEY,
            project_id TEXT,
            action TEXT NOT NULL,
            agent TEXT NOT NULL,
            stage TEXT,
            details TEXT,
            timestamp TEXT NOT NULL
        );
    """)
    for agent in AGENT_PROFILES:
        conn.execute(
            "INSERT OR IGNORE INTO agent_status (agent, status, last_seen) VALUES (?, 'idle', ?)",
            (agent, now_iso())
        )
    conn.commit()
    conn.close()


def log(msg):
    ts = now_iso()
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(RELAY_LOG, "a") as f:
        f.write(line + "\n")


# --- Executor Adapters ---

class ClaudeAdapter:
    def is_available(self) -> bool:
        r = subprocess.run(["which", "claude"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0 and r.stdout.strip()

    def execute(self, task: str, context: str = "", timeout: int = 120) -> Dict:
        prompt = f"Context: {context}\n\nTask: {task}" if context else task
        try:
            r = subprocess.run(["claude", "--print", prompt], capture_output=True, text=True, timeout=timeout, cwd=str(REPO_ROOT))
            return {"agent": "claude", "success": r.returncode == 0, "output": r.stdout[:8000], "error": r.stderr[:2000]}
        except Exception as e:
            return {"agent": "claude", "success": False, "error": str(e), "output": ""}


class CodexAdapter:
    def is_available(self) -> bool:
        r = subprocess.run(["which", "codex"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0 and r.stdout.strip()

    def execute(self, task: str, context: str = "", timeout: int = 120) -> Dict:
        prompt = f"Context: {context}\n\nTask: {task}" if context else task
        try:
            r = subprocess.run(["codex", "exec", prompt], capture_output=True, text=True, timeout=timeout, cwd=str(REPO_ROOT))
            return {"agent": "codex", "success": r.returncode == 0, "output": r.stdout[:8000], "error": r.stderr[:2000]}
        except Exception as e:
            return {"agent": "codex", "success": False, "error": str(e), "output": ""}


class DevinAdapter:
    def is_available(self) -> bool:
        r = subprocess.run(["which", "devin"], capture_output=True, text=True, timeout=5)
        return r.returncode == 0 and r.stdout.strip()

    def execute(self, task: str, context: str = "", timeout: int = 120) -> Dict:
        prompt = f"Context: {context}\n\nTask: {task}" if context else task
        try:
            r = subprocess.run(["devin", "-p", prompt], capture_output=True, text=True, timeout=timeout, cwd=str(REPO_ROOT))
            return {"agent": "devin", "success": r.returncode == 0, "output": r.stdout[:8000], "error": r.stderr[:2000]}
        except Exception as e:
            return {"agent": "devin", "success": False, "error": str(e), "output": ""}


class WindsurfAdapter:
    SAFE = ["ls", "cat", "echo", "python3", "pytest", "make", "git", "pip", "mkdir", "touch", "grep", "find", "wc", "head", "tail", "diff"]

    def is_available(self) -> bool:
        return True

    def execute(self, task: str, context: str = "", timeout: int = 120) -> Dict:
        if not any(task.strip().lower().startswith(p) for p in self.SAFE):
            return {"agent": "windsurf", "success": False, "error": f"Unsafe: {task[:80]}", "output": ""}
        try:
            r = subprocess.run(task.split(), capture_output=True, text=True, timeout=timeout, cwd=str(REPO_ROOT))
            return {"agent": "windsurf", "success": r.returncode == 0, "output": r.stdout[:8000], "error": r.stderr[:2000]}
        except Exception as e:
            return {"agent": "windsurf", "success": False, "error": str(e), "output": ""}


class ChatGPTBridge:
    def is_available(self) -> bool:
        r = subprocess.run(["osascript", "-e", 'tell application "System Events" to (name of processes) contains "ChatGPT"'],
                          capture_output=True, text=True, timeout=5)
        return "true" in r.stdout.lower()

    def send_prompt(self, prompt: str, wait_seconds: int = 35) -> Dict:
        try:
            subprocess.run(["open", "-a", "ChatGPT"], capture_output=True, timeout=10)
            time.sleep(2)
            def ascript(s):
                r = subprocess.run(["osascript", "-e", s], capture_output=True, text=True, timeout=30)
                return r.stdout.strip(), r.stderr.strip()
            ascript('tell application "ChatGPT" to activate')
            time.sleep(2)
            ascript('tell application "System Events" to keystroke "n" using command down')
            time.sleep(1.5)
            subprocess.run(["pbcopy"], input=prompt, text=True, timeout=10)
            time.sleep(0.3)
            ascript('tell application "System Events" to keystroke "v" using command down')
            time.sleep(0.5)
            ascript('tell application "System Events" to keystroke return')
            time.sleep(1)
            time.sleep(wait_seconds)
            pos, _ = ascript('tell application "System Events" to tell process "ChatGPT" to get position of window 1')
            size, _ = ascript('tell application "System Events" to tell process "ChatGPT" to get size of window 1')
            pp = [int(x) for x in pos.split(", ")]
            sp = [int(x) for x in size.split(", ")]
            shot = f"/tmp/relay_chatgpt_{int(time.time())}.png"
            subprocess.run(["screencapture", "-R", f"{pp[0]},{pp[1]},{sp[0]},{sp[1]}", shot], capture_output=True, timeout=10)
            time.sleep(0.5)
            from PIL import Image
            import pytesseract
            img = Image.open(shot)
            w, h = img.size
            text = pytesseract.image_to_string(img.crop((280, 50, w, h - 120)))
            return {"success": len(text) > 20, "response": text, "screenshot": shot}
        except Exception as e:
            return {"success": False, "response": "", "error": str(e)}


# --- Relay Hub ---

class RelayHub:
    def __init__(self):
        init_db()
        self.executors = {
            "claude": ClaudeAdapter(),
            "codex": CodexAdapter(),
            "devin": DevinAdapter(),
            "windsurf": WindsurfAdapter(),
        }
        self.chatgpt = ChatGPTBridge()

    def create_project(self, name: str, description: str = "") -> Dict:
        pid = str(uuid.uuid4())[:8]
        ts = now_iso()
        conn = get_db()
        conn.execute(
            "INSERT INTO projects (id, name, description, current_stage, status, created_at, updated_at, stage_results) "
            "VALUES (?, ?, ?, 'IDEA', 'active', ?, ?, '{}')",
            (pid, name, description, ts, ts)
        )
        conn.execute(
            "INSERT INTO receipts (id, project_id, action, agent, stage, details, timestamp) "
            "VALUES (?, ?, 'project_created', 'chatgpt', 'IDEA', ?, ?)",
            (str(uuid.uuid4())[:12], pid, json.dumps({"name": name}), ts)
        )
        conn.commit()
        conn.close()
        log(f"Project {pid}: {name}")
        return {"id": pid, "name": name, "stage": "IDEA", "status": "active"}

    def get_projects(self) -> List[Dict]:
        conn = get_db()
        rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_project(self, pid: str) -> Optional[Dict]:
        conn = get_db()
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def advance_stage(self, pid: str, stage: str, task_input: str = "",
                      execute: bool = True, timeout: int = 60) -> Dict:
        project = self.get_project(pid)
        if not project:
            return {"error": "Project not found"}

        agent = STAGE_AGENTS.get(stage, "windsurf")
        sid = str(uuid.uuid4())[:12]
        ts = now_iso()
        t0 = time.time()

        conn = get_db()
        conn.execute(
            "INSERT INTO stage_history (id, project_id, stage, agent, input, status, started_at) "
            "VALUES (?, ?, ?, ?, ?, 'running', ?)",
            (sid, pid, stage, agent, task_input[:2000], ts)
        )
        conn.execute("UPDATE projects SET current_stage = ?, updated_at = ? WHERE id = ?", (stage, ts, pid))
        conn.execute(
            "UPDATE agent_status SET status='busy', current_task=?, current_project=?, last_seen=? WHERE agent=?",
            (f"{stage}: {project['name']}", pid, ts, agent)
        )
        conn.commit()
        conn.close()

        log(f"Project {pid} → {stage} → {agent}")

        result = {"agent": agent, "stage": stage, "project_id": pid, "project_name": project["name"]}

        if not execute:
            result["status"] = "skipped"
            result["output"] = "Dry run"
        elif agent == "chatgpt":
            result["status"] = "needs_chatgpt"
            result["message"] = f"Send this prompt to ChatGPT for {stage}"
            result["prompt"] = task_input
        elif agent in self.executors:
            if not self.executors[agent].is_available():
                result["status"] = "agent_unavailable"
                result["error"] = f"{agent} offline"
            else:
                context = self._build_context(pid, stage)
                r = self.executors[agent].execute(task_input, context, timeout)
                result.update(r)
                result["status"] = "completed" if r.get("success") else "failed"
        else:
            result["status"] = "no_agent"

        dur = int((time.time() - t0) * 1000)
        conn = get_db()
        conn.execute(
            "UPDATE stage_history SET status=?, output=?, completed_at=?, duration_ms=? WHERE id=?",
            (result.get("status", "unknown"), json.dumps(result, ensure_ascii=False)[:4000], now_iso(), dur, sid)
        )
        # Update stage_results JSON in project
        stage_results = json.loads(project.get("stage_results", "{}"))
        stage_results[stage] = {"agent": agent, "status": result.get("status"), "duration_ms": dur,
                                "output": (result.get("output") or "")[:500]}
        conn.execute("UPDATE projects SET stage_results=?, updated_at=? WHERE id=?",
                     (json.dumps(stage_results), now_iso(), pid))
        status = result.get("status", "unknown")
        is_success = status in ("completed", "skipped", "needs_chatgpt")
        conn.execute(
            "UPDATE agent_status SET status='idle', current_task=NULL, current_project=NULL, last_seen=?, "
            "tasks_completed=tasks_completed+?, tasks_failed=tasks_failed+? WHERE agent=?",
            (now_iso(), 1 if is_success else 0, 0 if is_success else 1, agent)
        )
        conn.execute(
            "INSERT INTO receipts (id, project_id, action, agent, stage, details, timestamp) "
            "VALUES (?, ?, 'stage_complete', ?, ?, ?, ?)",
            (str(uuid.uuid4())[:12], pid, agent, stage,
             json.dumps({"status": result.get("status"), "dur_ms": dur}), now_iso())
        )
        conn.commit()
        conn.close()

        log(f"Stage {stage}: {result.get('status')} ({dur}ms)")
        return result

    def _build_context(self, pid: str, current: str) -> str:
        conn = get_db()
        rows = conn.execute(
            "SELECT stage, agent, output FROM stage_history WHERE project_id=? AND status='completed' ORDER BY started_at",
            (pid,)
        ).fetchall()
        conn.close()
        parts = []
        for r in rows:
            if r["stage"] != current:
                out = (r["output"] or "")[:200]
                parts.append(f"[{r['stage']}/{r['agent']}]: {out}")
        return "\n".join(parts) if parts else "No prior context"

    def get_stage_history(self, pid: str) -> List[Dict]:
        conn = get_db()
        rows = conn.execute("SELECT * FROM stage_history WHERE project_id=? ORDER BY started_at", (pid,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def ask_chatgpt(self, prompt: str, wait: int = 35) -> Dict:
        mid = str(uuid.uuid4())[:12]
        conn = get_db()
        conn.execute(
            "INSERT INTO messages (id, from_agent, to_agent, message_type, content, status, timestamp) "
            "VALUES (?, 'relay', 'chatgpt', 'query', ?, 'pending', ?)",
            (mid, prompt[:2000], now_iso())
        )
        conn.commit()
        conn.close()
        result = self.chatgpt.send_prompt(prompt, wait)
        conn = get_db()
        conn.execute("UPDATE messages SET status=?, result=?, completed_at=? WHERE id=?",
                     ("completed" if result.get("success") else "failed",
                      json.dumps(result, ensure_ascii=False)[:4000], now_iso(), mid))
        conn.execute("UPDATE agent_status SET status='idle', last_seen=?, tasks_completed=tasks_completed+? WHERE agent='chatgpt'",
                     (now_iso(), 1 if result.get("success") else 0))
        conn.commit()
        conn.close()
        result["message_id"] = mid
        return result

    def get_status(self) -> Dict:
        conn = get_db()
        agents = {}
        for row in conn.execute("SELECT * FROM agent_status").fetchall():
            a = dict(row)
            a["profile"] = AGENT_PROFILES.get(a["agent"], {})
            a["available"] = True
            if a["agent"] in self.executors:
                a["available"] = self.executors[a["agent"]].is_available()
            elif a["agent"] == "chatgpt":
                a["available"] = self.chatgpt.is_available()
            agents[a["agent"]] = a
        projects = [dict(r) for r in conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()]
        pending = conn.execute("SELECT COUNT(*) as c FROM messages WHERE status='pending'").fetchone()["c"]
        completed = conn.execute("SELECT COUNT(*) as c FROM messages WHERE status='completed'").fetchone()["c"]
        failed = conn.execute("SELECT COUNT(*) as c FROM messages WHERE status='failed'").fetchone()["c"]
        total_r = conn.execute("SELECT COUNT(*) as c FROM receipts").fetchone()["c"]
        stages = conn.execute("SELECT COUNT(*) as c FROM stage_history").fetchone()["c"]
        conn.close()
        return {
            "agents": agents, "projects": projects,
            "pipeline": PIPELINE_STAGES, "stage_agents": STAGE_AGENTS,
            "stage_descriptions": STAGE_DESCRIPTIONS,
            "messages": {"pending": pending, "completed": completed, "failed": failed},
            "total_receipts": total_r, "total_stages_run": stages,
            "timestamp": now_iso(),
        }

    def get_messages(self, limit=20):
        conn = get_db()
        rows = conn.execute("SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_receipts(self, limit=20):
        conn = get_db()
        rows = conn.execute("SELECT * FROM receipts ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def execute_manual(self, agent: str, task: str, timeout=60) -> Dict:
        if agent not in self.executors:
            return {"error": f"Unknown: {agent}"}
        if not self.executors[agent].is_available():
            return {"error": f"{agent} offline"}
        return self.executors[agent].execute(task, timeout=timeout)
