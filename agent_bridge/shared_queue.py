#!/usr/bin/env python3
"""
SharedQueue — SQLite-backed durable message queue for agent-to-agent communication.

Two queues:
1. tasks: requests waiting to be picked up by an agent
2. responses: completed work waiting to be read by the requesting agent

Each message has a direction:
- "to_chatgpt": Windsurf → ChatGPT (task for ChatGPT to process)
- "to_windsurf": ChatGPT → Windsurf (task for Windsurf to execute)
- "response": reply to a previous task

Messages flow:
    Windsurf posts task (to_chatgpt) → ChatGPTPoller claims it → processes → posts response
    ChatGPT posts task (to_windsurf) → Windsurf claims it → processes → posts response
"""

import hashlib
import json
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).parent / "data" / "agent_bridge.db"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


class SharedQueue:
    """Thread-safe SQLite message queue for inter-agent communication."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(
                str(self.db_path),
                timeout=30,
                check_same_thread=False,
            )
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA busy_timeout=5000")
        return self._local.conn

    def _init_db(self):
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                direction TEXT NOT NULL,
                sender TEXT NOT NULL,
                prompt TEXT NOT NULL,
                context TEXT DEFAULT '',
                status TEXT DEFAULT 'pending',
                claimed_by TEXT DEFAULT NULL,
                claimed_at TEXT DEFAULT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                priority INTEGER DEFAULT 5,
                workflow_id TEXT DEFAULT NULL,
                step_index INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS responses (
                id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                sender TEXT NOT NULL,
                content TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                status TEXT DEFAULT 'delivered',
                created_at TEXT NOT NULL,
                read_at TEXT DEFAULT NULL,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS workflow_state (
                workflow_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                steps TEXT NOT NULL,
                current_step INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                context TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_tasks_direction ON tasks(direction);
            CREATE INDEX IF NOT EXISTS idx_responses_task ON responses(task_id);
            CREATE INDEX IF NOT EXISTS idx_responses_read ON responses(read_at);
        """)
        conn.commit()

    def post_task(
        self,
        direction: str,
        sender: str,
        prompt: str,
        context: str = "",
        priority: int = 5,
        workflow_id: str = "",
        step_index: int = 0,
    ) -> Dict[str, Any]:
        """Post a new task to the queue."""
        task_id = f"task_{_hash_content(prompt + str(time.time()))}"
        now = now_iso()
        conn = self._conn()
        conn.execute(
            """INSERT INTO tasks (id, direction, sender, prompt, context, status, created_at, updated_at, priority, workflow_id, step_index)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)""",
            (task_id, direction, sender, prompt, context, now, now, priority, workflow_id, step_index),
        )
        conn.commit()
        return {"id": task_id, "direction": direction, "sender": sender, "prompt": prompt, "status": "pending", "created_at": now}

    def claim_task(self, direction: str, claimer: str) -> Optional[Dict[str, Any]]:
        """Atomically claim the next pending task for a given direction."""
        conn = self._conn()
        row = conn.execute(
            """SELECT * FROM tasks WHERE direction = ? AND status = 'pending'
               ORDER BY priority ASC, created_at ASC LIMIT 1""",
            (direction,),
        ).fetchone()
        if row is None:
            return None
        now = now_iso()
        conn.execute(
            "UPDATE tasks SET status = 'claimed', claimed_by = ?, claimed_at = ?, updated_at = ? WHERE id = ?",
            (claimer, now, now, row["id"]),
        )
        conn.commit()
        result = dict(row)
        result["status"] = "claimed"
        result["claimed_by"] = claimer
        result["claimed_at"] = now
        result["updated_at"] = now
        return result

    def complete_task(self, task_id: str) -> bool:
        """Mark a task as completed."""
        conn = self._conn()
        now = now_iso()
        conn.execute(
            "UPDATE tasks SET status = 'completed', updated_at = ? WHERE id = ?",
            (now, task_id),
        )
        conn.commit()
        return conn.total_changes > 0

    def fail_task(self, task_id: str, error: str = "") -> bool:
        """Mark a task as failed."""
        conn = self._conn()
        now = now_iso()
        conn.execute(
            "UPDATE tasks SET status = 'failed', updated_at = ? WHERE id = ?",
            (now, task_id),
        )
        conn.commit()
        return conn.total_changes > 0

    def post_response(
        self,
        task_id: str,
        sender: str,
        content: str,
        metadata: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Post a response to a completed task."""
        resp_id = f"resp_{_hash_content(content + str(time.time()))}"
        now = now_iso()
        conn = self._conn()
        conn.execute(
            """INSERT INTO responses (id, task_id, sender, content, content_hash, status, created_at, metadata)
               VALUES (?, ?, ?, ?, ?, 'delivered', ?, ?)""",
            (resp_id, task_id, sender, content, _hash_content(content), now, json.dumps(metadata or {})),
        )
        conn.commit()
        return {"id": resp_id, "task_id": task_id, "sender": sender, "status": "delivered", "created_at": now}

    def get_response(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get the response for a task (marks it as read)."""
        conn = self._conn()
        row = conn.execute(
            "SELECT * FROM responses WHERE task_id = ? AND read_at IS NULL ORDER BY created_at DESC LIMIT 1",
            (task_id,),
        ).fetchone()
        if row is None:
            return None
        now = now_iso()
        conn.execute("UPDATE responses SET read_at = ? WHERE id = ?", (now, row["id"]))
        conn.commit()
        return dict(row)

    def get_responses(self, task_id: str) -> List[Dict[str, Any]]:
        """Get all responses for a task."""
        conn = self._conn()
        rows = conn.execute(
            "SELECT * FROM responses WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_response_read(self, response_id: str) -> bool:
        """Mark a specific response as read by ID."""
        conn = self._conn()
        now = now_iso()
        conn.execute("UPDATE responses SET read_at = ? WHERE id = ? AND read_at IS NULL", (now, response_id))
        conn.commit()
        return conn.total_changes > 0

    def get_pending_tasks(self, direction: str = "") -> List[Dict[str, Any]]:
        """Get all pending tasks, optionally filtered by direction."""
        conn = self._conn()
        if direction:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = 'pending' AND direction = ? ORDER BY priority ASC, created_at ASC",
                (direction,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM tasks WHERE status = 'pending' ORDER BY priority ASC, created_at ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_unread_responses(self, sender: str = "") -> List[Dict[str, Any]]:
        """Get all unread responses, optionally filtered by sender."""
        conn = self._conn()
        if sender:
            rows = conn.execute(
                "SELECT * FROM responses WHERE read_at IS NULL AND sender = ? ORDER BY created_at ASC",
                (sender,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM responses WHERE read_at IS NULL ORDER BY created_at ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific task by ID."""
        conn = self._conn()
        row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def get_stats(self) -> Dict[str, Any]:
        """Get queue statistics."""
        conn = self._conn()
        stats = {}
        for status in ["pending", "claimed", "completed", "failed"]:
            count = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = ?", (status,)).fetchone()[0]
            stats[f"tasks_{status}"] = count
        stats["responses_total"] = conn.execute("SELECT COUNT(*) FROM responses").fetchone()[0]
        stats["responses_unread"] = conn.execute("SELECT COUNT(*) FROM responses WHERE read_at IS NULL").fetchone()[0]
        stats["timestamp"] = now_iso()
        return stats

    def create_workflow(self, workflow_id: str, name: str, steps: List[Dict[str, Any]], context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Create a multi-step collaborative workflow."""
        now = now_iso()
        conn = self._conn()
        conn.execute(
            """INSERT OR REPLACE INTO workflow_state (workflow_id, name, steps, current_step, status, context, created_at, updated_at)
               VALUES (?, ?, ?, 0, 'active', ?, ?, ?)""",
            (workflow_id, name, json.dumps(steps), json.dumps(context or {}), now, now),
        )
        conn.commit()
        return {"workflow_id": workflow_id, "name": name, "steps": len(steps), "status": "active"}

    def advance_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Advance workflow to next step. Returns next step or None if complete."""
        conn = self._conn()
        row = conn.execute("SELECT * FROM workflow_state WHERE workflow_id = ?", (workflow_id,)).fetchone()
        if row is None:
            return None
        steps = json.loads(row["steps"])
        next_step = row["current_step"] + 1
        now = now_iso()
        if next_step >= len(steps):
            conn.execute("UPDATE workflow_state SET status = 'completed', updated_at = ? WHERE workflow_id = ?", (now, workflow_id))
            conn.commit()
            return {"workflow_id": workflow_id, "status": "completed", "step": None}
        conn.execute("UPDATE workflow_state SET current_step = ?, updated_at = ? WHERE workflow_id = ?", (next_step, now, workflow_id))
        conn.commit()
        return {"workflow_id": workflow_id, "step_index": next_step, "step": steps[next_step], "status": "active"}

    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get workflow state."""
        conn = self._conn()
        row = conn.execute("SELECT * FROM workflow_state WHERE workflow_id = ?", (workflow_id,)).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["steps"] = json.loads(result["steps"])
        result["context"] = json.loads(result["context"])
        return result

    def list_workflows(self, status: str = "") -> List[Dict[str, Any]]:
        """List workflows, optionally filtered by status."""
        conn = self._conn()
        if status:
            rows = conn.execute("SELECT * FROM workflow_state WHERE status = ? ORDER BY created_at DESC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM workflow_state ORDER BY created_at DESC").fetchall()
        results = []
        for r in rows:
            item = dict(r)
            item["steps"] = json.loads(item["steps"])
            item["context"] = json.loads(item["context"])
            results.append(item)
        return results

    def reset(self):
        """Clear all data (for testing)."""
        conn = self._conn()
        conn.executescript("DELETE FROM tasks; DELETE FROM responses; DELETE FROM workflow_state;")
        conn.commit()
