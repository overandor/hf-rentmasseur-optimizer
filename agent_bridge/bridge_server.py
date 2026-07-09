#!/usr/bin/env python3
"""
BridgeServer — Always-on FastAPI server for bidirectional agent communication.

Runs on localhost:8766. Both ChatGPT (via poller) and Windsurf (via client) connect here.

Endpoints:
    GET  /health              — server health + queue stats
    POST /tasks               — post a task (direction: to_chatgpt | to_windsurf)
    GET  /tasks/pending       — list pending tasks
    POST /tasks/claim         — claim next task for a direction
    POST /tasks/{id}/complete — mark task complete
    POST /tasks/{id}/fail     — mark task failed
    POST /responses           — post a response to a task
    GET  /responses/{task_id} — get response for a task
    GET  /responses/unread    — get all unread responses
    GET  /stats               — queue statistics
    WS   /ws                  — WebSocket for real-time notifications

    # Workflow endpoints
    POST /workflows           — create a multi-step workflow
    GET  /workflows           — list workflows
    GET  /workflows/{id}      — get workflow state
    POST /workflows/{id}/advance — advance to next step

    # Code execution (safe, bounded)
    POST /execute             — execute a safe command (routed through safety broker)
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from .shared_queue import SharedQueue
from .passport import render_task_passport, render_workflow_passport, groq_chat, groq_analyze_task

REPO_ROOT = Path(__file__).parent.parent
BRIDGE_VERSION = "0.2.0"

# Production logging
LOG_DIR = Path(__file__).parent / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "bridge_server.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("agent_bridge.server")

# Safe command patterns for code execution from ChatGPT
SAFE_PATTERNS = [
    "python3", "python", "pytest", "pip list", "pip show",
    "git status", "git log", "git diff", "git branch", "git add", "git commit",
    "ls", "cat", "head", "tail", "grep", "find", "wc",
    "echo", "pwd", "which", "file", "stat",
    "ruff", "black --check", "mypy",
    "node", "npm list", "npm run",
    "make", "cargo build", "cargo test", "cargo check",
    "swift build", "swift test",
    "xcodebuild -list",
]

BLOCKED_PATTERNS = [
    "rm -rf", "rm -r /", "dd if=", "mkfs", "sudo ",
    "chmod 777", "chown ", "kill -9",
    "curl | bash", "wget | bash", "pip install",
    "npm install -g", "brew install",
    "> /dev/sd", "shutdown", "reboot",
    "git push --force", "git reset --hard",
    "osascript -e",  # prevent nested automation
]

# Commands that need approval
DESTRUCTIVE_PATTERNS = [
    "git push", "git reset", "git rebase", "git merge",
    "rm ", "rmdir", "mv ", "cp ",
    "docker ", "kill ",
]


class SafetyBroker:
    """Classify commands as safe, blocked, or needs-approval."""

    def classify(self, command: str) -> Dict[str, Any]:
        cmd_lower = command.lower().strip()

        for blocked in BLOCKED_PATTERNS:
            if blocked in cmd_lower:
                return {"classification": "blocked", "reason": f"Matches blocked pattern: {blocked}", "command": command}

        for safe in SAFE_PATTERNS:
            if cmd_lower.startswith(safe):
                return {"classification": "safe", "reason": f"Matches safe pattern: {safe}", "command": command}

        for destructive in DESTRUCTIVE_PATTERNS:
            if destructive in cmd_lower:
                return {"classification": "needs_approval", "reason": f"Destructive pattern: {destructive}", "command": command}

        return {"classification": "needs_approval", "reason": "Unknown command — requires approval", "command": command}

    def execute(self, command: str, cwd: str = "", timeout: int = 60, force: bool = False) -> Dict[str, Any]:
        """Execute a command if it's safe. Return result dict."""
        classification = self.classify(command)
        if classification["classification"] == "blocked":
            logger.warning(f"BLOCKED command: {command}")
            return {"success": False, "error": "Command blocked", "detail": classification["reason"], "output": ""}

        if classification["classification"] == "needs_approval" and not force:
            logger.info(f"NEEDS_APPROVAL command: {command}")
            return {"success": False, "error": "Command needs approval", "detail": classification["reason"], "output": ""}

        work_dir = cwd or str(REPO_ROOT)
        logger.info(f"EXECUTING: {command} (cwd={work_dir}, timeout={timeout})")
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=work_dir,
                timeout=timeout,
            )
            logger.info(f"EXIT_CODE={result.returncode} for: {command}")
            return {
                "success": result.returncode == 0,
                "exit_code": result.returncode,
                "output": result.stdout + result.stderr,
                "command": command,
                "cwd": work_dir,
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }
        except subprocess.TimeoutExpired:
            logger.error(f"TIMEOUT for: {command}")
            return {"success": False, "error": "Command timed out", "timeout": timeout, "output": ""}
        except Exception as e:
            logger.error(f"ERROR executing {command}: {e}")
            return {"success": False, "error": str(e), "output": ""}


# Pydantic models
class TaskCreate(BaseModel):
    direction: str  # "to_chatgpt" or "to_windsurf"
    sender: str
    prompt: str
    context: str = ""
    priority: int = 5
    workflow_id: str = ""
    step_index: int = 0


class TaskClaim(BaseModel):
    direction: str
    claimer: str


class TaskComplete(BaseModel):
    task_id: str


class ResponseCreate(BaseModel):
    task_id: str
    sender: str
    content: str
    metadata: Dict[str, Any] = {}


class ExecuteRequest(BaseModel):
    command: str
    cwd: str = ""
    timeout: int = 60
    force: bool = False  # if True, execute even needs_approval commands


class WorkflowCreate(BaseModel):
    workflow_id: str
    name: str
    steps: List[Dict[str, Any]]
    context: Dict[str, Any] = {}


class ConnectionManager:
    """Manage WebSocket connections for real-time notifications."""

    def __init__(self):
        self.active: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket):
        self.active.discard(ws)

    async def broadcast(self, message: Dict[str, Any]):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


def create_app(db_path: Path = None) -> FastAPI:
    """Create the FastAPI bridge server app."""
    queue = SharedQueue(db_path) if db_path else SharedQueue()
    broker = SafetyBroker()
    manager = ConnectionManager()

    app = FastAPI(title="Agent Bridge", version=BRIDGE_VERSION, docs_url="/docs", redoc_url="/redoc")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.time()
        response = await call_next(request)
        elapsed = round((time.time() - start) * 1000, 1)
        logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({elapsed}ms)")
        return response

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        stats = queue.get_stats()
        pending = queue.get_pending_tasks()
        workflows = queue.list_workflows()
        unread = queue.get_unread_responses()
        return _render_dashboard(stats, pending, workflows, unread)

    @app.get("/health")
    async def health():
        stats = queue.get_stats()
        return {
            "server": "agent-bridge",
            "version": BRIDGE_VERSION,
            "status": "healthy",
            "queue": stats,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    @app.post("/tasks")
    async def post_task(task: TaskCreate):
        if task.direction not in ("to_chatgpt", "to_windsurf"):
            return JSONResponse(status_code=400, content={"error": f"Invalid direction: {task.direction}. Must be 'to_chatgpt' or 'to_windsurf'"})
        result = queue.post_task(
            direction=task.direction,
            sender=task.sender,
            prompt=task.prompt,
            context=task.context,
            priority=task.priority,
            workflow_id=task.workflow_id,
            step_index=task.step_index,
        )
        logger.info(f"Task posted: {result['id']} direction={task.direction} sender={task.sender}")
        await manager.broadcast({"type": "new_task", "task": result})
        return result

    @app.get("/tasks/pending")
    async def get_pending(direction: str = ""):
        return {"tasks": queue.get_pending_tasks(direction)}

    @app.post("/tasks/claim")
    async def claim_task(claim: TaskClaim):
        task = queue.claim_task(claim.direction, claim.claimer)
        if task:
            await manager.broadcast({"type": "task_claimed", "task_id": task["id"], "claimer": claim.claimer})
        return {"task": task}

    @app.post("/tasks/{task_id}/complete")
    async def complete_task(task_id: str):
        success = queue.complete_task(task_id)
        return {"success": success, "task_id": task_id}

    @app.post("/tasks/{task_id}/fail")
    async def fail_task(task_id: str):
        success = queue.fail_task(task_id)
        return {"success": success, "task_id": task_id}

    @app.post("/responses")
    async def post_response(resp: ResponseCreate):
        result = queue.post_response(
            task_id=resp.task_id,
            sender=resp.sender,
            content=resp.content,
            metadata=resp.metadata,
        )
        await manager.broadcast({"type": "new_response", "response": result})
        return result

    @app.get("/responses/unread")
    async def get_unread(sender: str = ""):
        return {"responses": queue.get_unread_responses(sender)}

    @app.post("/responses/{response_id}/read")
    async def mark_response_read(response_id: str):
        success = queue.mark_response_read(response_id)
        return {"success": success, "response_id": response_id}

    @app.get("/responses/{task_id}")
    async def get_response(task_id: str):
        resp = queue.get_response(task_id)
        return {"response": resp}

    @app.get("/stats")
    async def get_stats():
        return queue.get_stats()

    @app.get("/tasks/{task_id}/passport", response_class=HTMLResponse)
    async def task_passport(task_id: str):
        task = queue.get_task(task_id)
        if not task:
            return HTMLResponse("<h1>Task not found</h1>", status_code=404)
        responses = queue.get_responses(task_id)
        workflow = queue.get_workflow(task["workflow_id"]) if task.get("workflow_id") else None
        return render_task_passport(task, responses, workflow)

    @app.get("/tasks/{task_id}/analyze", response_class=HTMLResponse)
    async def task_analyze(task_id: str):
        task = queue.get_task(task_id)
        if not task:
            return HTMLResponse("<h1>Task not found</h1>", status_code=404)
        responses = queue.get_responses(task_id)
        workflow = queue.get_workflow(task["workflow_id"]) if task.get("workflow_id") else None
        analysis = groq_analyze_task(task, responses)
        return render_task_passport(task, responses, workflow, llm_analysis=analysis)

    @app.get("/tasks/{task_id}")
    async def get_task(task_id: str):
        task = queue.get_task(task_id)
        if not task:
            return {"error": "Task not found"}
        responses = queue.get_responses(task_id)
        return {"task": task, "responses": responses}

    # === Workflow endpoints ===

    @app.post("/workflows")
    async def create_workflow(wf: WorkflowCreate):
        return queue.create_workflow(wf.workflow_id, wf.name, wf.steps, wf.context)

    @app.get("/workflows")
    async def list_workflows(status: str = ""):
        return {"workflows": queue.list_workflows(status)}

    @app.get("/workflows/{workflow_id}/passport", response_class=HTMLResponse)
    async def workflow_passport(workflow_id: str):
        wf = queue.get_workflow(workflow_id)
        if not wf:
            return HTMLResponse("<h1>Workflow not found</h1>", status_code=404)
        return render_workflow_passport(wf)

    @app.get("/workflows/{workflow_id}")
    async def get_workflow(workflow_id: str):
        wf = queue.get_workflow(workflow_id)
        if not wf:
            return {"error": "Workflow not found"}
        return wf

    @app.post("/workflows/{workflow_id}/advance")
    async def advance_workflow(workflow_id: str):
        result = queue.advance_workflow(workflow_id)
        if result:
            await manager.broadcast({"type": "workflow_advanced", "workflow_id": workflow_id, "result": result})
        return result

    # === Code execution ===

    @app.post("/execute")
    async def execute_command(req: ExecuteRequest):
        classification = broker.classify(req.command)
        if classification["classification"] == "blocked":
            logger.warning(f"Execute blocked: {req.command}")
            return {"success": False, "error": "Command blocked", "detail": classification, "output": ""}

        if classification["classification"] == "needs_approval" and not req.force:
            return {"success": False, "error": "Needs approval", "detail": classification, "output": ""}

        result = broker.execute(req.command, req.cwd, req.timeout, force=req.force)
        return result

    @app.get("/execute/classify")
    async def classify_command(command: str):
        return broker.classify(command)

    # === Groq LLM ===

    class GroqRequest(BaseModel):
        prompt: str
        system: str = ""
        model: str = "llama-3.3-70b-versatile"

    @app.post("/llm/chat")
    async def llm_chat(req: GroqRequest):
        result = groq_chat(req.prompt, req.system, req.model)
        logger.info(f"Groq chat: model={req.model} success={result.get('success')}")
        return result

    @app.get("/llm/models")
    async def llm_models():
        from .passport import GROQ_MODELS
        return {"models": GROQ_MODELS, "api_key_set": bool(os.environ.get("GROQ_API_KEY"))}

    # === ETL Pipeline ===

    class ETLRequest(BaseModel):
        sources: List[str] = ["git", "code", "bridge", "tests", "chatgpt"]

    @app.post("/etl/run")
    async def etl_run(req: ETLRequest):
        from .etl_pipeline import run_etl_cycle
        logger.info(f"ETL run triggered: sources={req.sources}")
        results = run_etl_cycle(req.sources)
        return results

    @app.get("/etl/records")
    async def etl_records(limit: int = 20):
        etl_log = Path(__file__).parent / "data" / "etl_records.jsonl"
        if not etl_log.exists():
            return {"records": []}
        lines = etl_log.read_text().strip().split("\n")
        records = []
        for line in reversed(lines[-limit:]):
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return {"records": records}

    @app.get("/etl/dashboard", response_class=HTMLResponse)
    async def etl_dashboard():
        etl_log = Path(__file__).parent / "data" / "etl_records.jsonl"
        records = []
        if etl_log.exists():
            for line in etl_log.read_text().strip().split("\n")[-20:]:
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return _render_etl_dashboard(records)

    # === WebSocket ===

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket):
        await manager.connect(ws)
        try:
            while True:
                data = await ws.receive_text()
                msg = json.loads(data) if data else {}
                if msg.get("type") == "ping":
                    await ws.send_json({"type": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})
                elif msg.get("type") == "stats":
                    await ws.send_json({"type": "stats", "data": queue.get_stats()})
        except WebSocketDisconnect:
            manager.disconnect(ws)
        except Exception:
            manager.disconnect(ws)

    return app


def _render_dashboard(stats: Dict, pending: List, workflows: List, unread: List) -> str:
    """Render real-time HTML dashboard."""
    def task_rows():
        if not pending:
            return '<tr><td colspan="5" style="text-align:center;color:#666">No pending tasks</td></tr>'
        rows = []
        for t in pending:
            direction_color = "#4a9eff" if t["direction"] == "to_chatgpt" else "#f59e0b"
            rows.append(f'''<tr>
                <td><a href="/tasks/{t['id']}/passport"><code>{t['id'][:20]}</code></a></td>
                <td><span class="badge" style="background:{direction_color}">{t['direction']}</span></td>
                <td>{t['sender']}</td>
                <td style="max-width:400px;overflow:hidden;text-overflow:ellipsis">{t['prompt'][:80]}</td>
                <td>{t['priority']}</td>
            </tr>''')
        return "\n".join(rows)

    def workflow_rows():
        if not workflows:
            return '<tr><td colspan="4" style="text-align:center;color:#666">No active workflows</td></tr>'
        rows = []
        for w in workflows:
            status_color = "#22c55e" if w["status"] == "completed" else "#4a9eff" if w["status"] == "active" else "#999"
            rows.append(f'''<tr>
                <td><a href="/workflows/{w['workflow_id']}/passport"><code>{w['workflow_id'][:24]}</code></a></td>
                <td>{w['name']}</td>
                <td>Step {w['current_step']}/{len(w['steps'])}</td>
                <td><span class="badge" style="background:{status_color}">{w['status']}</span></td>
            </tr>''')
        return "\n".join(rows)

    def unread_rows():
        if not unread:
            return '<tr><td colspan="4" style="text-align:center;color:#666">No unread responses</td></tr>'
        rows = []
        for r in unread:
            rows.append(f'''<tr>
                <td><a href="/tasks/{r['task_id']}/passport"><code>{r['task_id'][:20]}</code></a></td>
                <td>{r['sender']}</td>
                <td style="max-width:400px;overflow:hidden;text-overflow:ellipsis">{r['content'][:80]}</td>
                <td>{r.get('created_at','')[:19]}</td>
            </tr>''')
        return "\n".join(rows)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Agent Bridge — Live Dashboard</title>
    <meta http-equiv="refresh" content="5">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; }}
        h1 {{ font-size: 1.8rem; margin-bottom: 4px; }}
        h2 {{ font-size: 1.2rem; margin: 24px 0 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }}
        .subtitle {{ color: #64748b; font-size: 0.9rem; margin-bottom: 20px; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 24px; }}
        .stat-card {{ background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 16px; text-align: center; }}
        .stat-value {{ font-size: 2rem; font-weight: 700; color: #4a9eff; }}
        .stat-label {{ font-size: 0.75rem; color: #64748b; text-transform: uppercase; margin-top: 4px; }}
        table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 10px; overflow: hidden; }}
        th {{ background: #334155; padding: 10px 14px; text-align: left; font-size: 0.8rem; color: #94a3b8; text-transform: uppercase; }}
        td {{ padding: 10px 14px; border-top: 1px solid #334155; font-size: 0.85rem; }}
        .badge {{ display: inline-block; padding: 2px 10px; border-radius: 9999px; font-size: 0.7rem; font-weight: 600; color: white; }}
        .header-bar {{ display: flex; justify-content: space-between; align-items: center; }}
        .version {{ background: #334155; padding: 4px 12px; border-radius: 9999px; font-size: 0.75rem; color: #94a3b8; }}
        .links {{ margin-top: 16px; }}
        .links a {{ color: #4a9eff; text-decoration: none; margin-right: 16px; font-size: 0.85rem; }}
        .links a:hover {{ text-decoration: underline; }}
        .auto-refresh {{ font-size: 0.75rem; color: #64748b; }}
        a {{ color: #4a9eff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
    </style>
</head>
<body>
    <div class="header-bar">
        <div>
            <h1>Agent Bridge</h1>
            <div class="subtitle">Bidirectional ChatGPT &harr; Windsurf Communication Layer</div>
        </div>
        <span class="version">v{BRIDGE_VERSION}</span>
    </div>

    <div class="stats-grid">
        <div class="stat-card"><div class="stat-value">{stats.get('tasks_pending',0)}</div><div class="stat-label">Pending Tasks</div></div>
        <div class="stat-card"><div class="stat-value">{stats.get('tasks_claimed',0)}</div><div class="stat-label">Claimed</div></div>
        <div class="stat-card"><div class="stat-value">{stats.get('tasks_completed',0)}</div><div class="stat-label">Completed</div></div>
        <div class="stat-card"><div class="stat-value">{stats.get('tasks_failed',0)}</div><div class="stat-label">Failed</div></div>
        <div class="stat-card"><div class="stat-value">{stats.get('responses_total',0)}</div><div class="stat-label">Responses</div></div>
        <div class="stat-card"><div class="stat-value">{stats.get('responses_unread',0)}</div><div class="stat-label">Unread</div></div>
    </div>

    <h2>Pending Tasks <span class="auto-refresh">(auto-refresh 5s)</span></h2>
    <table>
        <thead><tr><th>ID</th><th>Direction</th><th>Sender</th><th>Prompt</th><th>Priority</th></tr></thead>
        <tbody>{task_rows()}</tbody>
    </table>

    <h2>Active Workflows</h2>
    <table>
        <thead><tr><th>ID</th><th>Name</th><th>Progress</th><th>Status</th></tr></thead>
        <tbody>{workflow_rows()}</tbody>
    </table>

    <h2>Unread Responses</h2>
    <table>
        <thead><tr><th>Task ID</th><th>Sender</th><th>Content</th><th>Created</th></tr></thead>
        <tbody>{unread_rows()}</tbody>
    </table>

    <div class="links">
        <a href="/docs">API Docs (Swagger)</a>
        <a href="/health">Health Check</a>
        <a href="/stats">Stats JSON</a>
        <a href="/tasks/pending">Pending Tasks JSON</a>
        <a href="/workflows">Workflows JSON</a>
        <a href="/etl/dashboard">ETL Pipeline</a>
    </div>
</body>
</html>'''


def _render_etl_dashboard(records: List) -> str:
    """Render ETL pipeline dashboard with cycle history."""
    def cycle_rows():
        if not records:
            return '<tr><td colspan="6" style="text-align:center;color:#666">No ETL cycles yet. Run: POST /etl/run</td></tr>'
        rows = []
        for r in records:
            extracted = r.get("extracted", {})
            transformed = r.get("transformed", {})
            loaded = r.get("loaded", [])
            rows.append(f'''<tr>
                <td><code>{r.get("cycle_id","?")}</code></td>
                <td>{r.get("timestamp","")[:19]}</td>
                <td>{sum(extracted.values()) if isinstance(extracted, dict) else 0}</td>
                <td>{sum(transformed.values()) if isinstance(transformed, dict) else 0}</td>
                <td>{len(loaded)}</td>
                <td>{r.get("elapsed_s","?")}s</td>
            </tr>''')
        return "\n".join(rows)

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AGI ETL Pipeline — Agent Bridge</title>
    <meta http-equiv="refresh" content="10">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 20px; max-width: 960px; margin: 0 auto; }}
        h1 {{ font-size: 1.8rem; margin-bottom: 4px; }}
        h2 {{ font-size: 1.2rem; margin: 24px 0 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; }}
        .subtitle {{ color: #64748b; font-size: 0.9rem; margin-bottom: 20px; }}
        table {{ width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 10px; overflow: hidden; }}
        th {{ background: #334155; padding: 10px 14px; text-align: left; font-size: 0.8rem; color: #94a3b8; text-transform: uppercase; }}
        td {{ padding: 10px 14px; border-top: 1px solid #334155; font-size: 0.85rem; }}
        a {{ color: #4a9eff; text-decoration: none; }}
        a:hover {{ text-decoration: underline; }}
        .pipe-vis {{ display: flex; gap: 0; margin: 24px 0; }}
        .pipe-stage {{ flex: 1; padding: 16px; text-align: center; background: #1e293b; border: 1px solid #334155; }}
        .pipe-stage:first-child {{ border-radius: 10px 0 0 10px; }}
        .pipe-stage:last-child {{ border-radius: 0 10px 10px 0; }}
        .pipe-arrow {{ display: flex; align-items: center; color: #4a9eff; font-size: 1.5rem; padding: 0 8px; }}
        .pipe-icon {{ font-size: 1.5rem; margin-bottom: 4px; }}
        .pipe-name {{ font-size: 0.8rem; font-weight: 700; text-transform: uppercase; color: #94a3b8; }}
        .pipe-desc {{ font-size: 0.7rem; color: #64748b; margin-top: 4px; }}
        .actions {{ margin-top: 20px; display: flex; gap: 12px; }}
        .actions a {{ background: #334155; padding: 8px 16px; border-radius: 8px; color: #e2e8f0; text-decoration: none; font-size: 0.85rem; }}
        .actions a:hover {{ background: #475569; }}
        .back-link {{ margin-bottom: 20px; }}
    </style>
</head>
<body>
    <div class="back-link"><a href="/">&larr; Back to Dashboard</a></div>
    <h1>AGI ETL Pipeline</h1>
    <div class="subtitle">Extract &rarr; Transform (Groq LLM) &rarr; Load — autonomous data pipeline</div>

    <div class="pipe-vis">
        <div class="pipe-stage">
            <div class="pipe-icon">&#8962;</div>
            <div class="pipe-name">Extract</div>
            <div class="pipe-desc">git, code, tests, bridge, chatgpt</div>
        </div>
        <div class="pipe-arrow">&rarr;</div>
        <div class="pipe-stage">
            <div class="pipe-icon">&#9881;</div>
            <div class="pipe-name">Transform</div>
            <div class="pipe-desc">Groq LLM: summarize, classify, analyze</div>
        </div>
        <div class="pipe-arrow">&rarr;</div>
        <div class="pipe-stage">
            <div class="pipe-icon">&#9776;</div>
            <div class="pipe-name">Load</div>
            <div class="pipe-desc">bridge queue, SQLite, JSONL log</div>
        </div>
    </div>

    <h2>ETL Cycle History ({len(records)} cycles)</h2>
    <table>
        <thead><tr><th>Cycle ID</th><th>Timestamp</th><th>Extracted</th><th>Transformed</th><th>Loaded</th><th>Duration</th></tr></thead>
        <tbody>{cycle_rows()}</tbody>
    </table>

    <div class="actions">
        <a href="/etl/run" onclick="fetch('/etl/run',{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{sources:['git','code','bridge','tests','chatgpt']}})}}).then(()=>setTimeout(()=>location.reload(),3000));return false">Trigger ETL Cycle</a>
        <a href="/etl/records">Records JSON</a>
        <a href="/">Dashboard</a>
        <a href="/docs">API Docs</a>
    </div>
</body>
</html>'''


# Module-level app for uvicorn
app = create_app()


def serve(port: int = 8766, host: str = "127.0.0.1"):
    """Start the bridge server."""
    import uvicorn
    logger.info(f"Agent Bridge Server v{BRIDGE_VERSION} starting on {host}:{port}")
    logger.info(f"Dashboard: http://{host}:{port}/")
    logger.info(f"API Docs:  http://{host}:{port}/docs")
    logger.info(f"WebSocket: ws://{host}:{port}/ws")
    logger.info(f"Health:    http://{host}:{port}/health")
    logger.info(f"Log file:  {LOG_DIR / 'bridge_server.log'}")
    uvicorn.run(app, host=host, port=port, log_level="info", access_log=False)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Agent Bridge Server")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--host", type=str, default="127.0.0.1")
    args = parser.parse_args()
    serve(args.port, args.host)
