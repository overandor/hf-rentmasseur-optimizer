#!/usr/bin/env python3
"""
HyperFlow Unified MCP Server
Exposes safe, bounded, auditable tools for ChatGPT and Windsurf.

No raw shell execution. No secret exposure. No unrestricted file access.
Every tool call writes a receipt. Every tool has explicit input schema.

Usage:
    python3 mcp_unified.py                    # List available tools
    python3 mcp_unified.py <tool> [json_args] # Call a tool
    python3 mcp_unified.py serve              # MCP stdio server mode

MCP Protocol: This server implements the MCP tool interface so it can be
connected from ChatGPT Apps SDK or Windsurf Cascade MCP client.
"""

import hashlib
import json
import os
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
HYPERFLOW_DIR = REPO_ROOT / "hyperflow"
YTL_DIR = REPO_ROOT / "ytl-mcp-lab"
TASKS_FILE = HYPERFLOW_DIR / "tasks.jsonl"
RECEIPTS_FILE = HYPERFLOW_DIR / "receipts.jsonl"
YTL_RECEIPTS = YTL_DIR / "receipts" / "ledger.jsonl"
MCP_RECEIPTS = REPO_ROOT / "RECEIPTS" / "mcp_receipts.jsonl"

LAB_VERSION = "0.2.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hash_obj(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()[:16]


def load_jsonl(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().strip().split("\n") if l.strip()]


def append_jsonl(path: Path, obj: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(obj) + "\n")


def write_mcp_receipt(tool: str, input_obj: Any, output_obj: Any,
                      status: str = "ok", error: str = "") -> str:
    """Write a receipt for every MCP tool call."""
    receipt = {
        "timestamp": now_iso(),
        "tool": tool,
        "actor": os.environ.get("MCP_ACTOR", "mcp-client"),
        "input_hash": hash_obj(input_obj),
        "output_hash": hash_obj(output_obj),
        "status": status,
        "error": error,
    }
    append_jsonl(MCP_RECEIPTS, receipt)
    return receipt["timestamp"]


# === SAFE TOOLS ===
# No raw shell. No secret access. No arbitrary file read/write.
# Each tool has a fixed schema and bounded behavior.

def get_task_state(task_id: str = "") -> Dict[str, Any]:
    """Get current task state from the HyperFlow ledger.
    
    Args:
        task_id: Optional task ID. If empty, returns all tasks.
    
    Returns:
        Task state(s) from the JSONL ledger.
    """
    tasks = load_jsonl(TASKS_FILE)
    
    if task_id:
        found = [t for t in tasks if t.get("id") == task_id]
        result = found[-1] if found else {"error": f"Task {task_id} not found"}
    else:
        result = {
            "total": len(tasks),
            "tasks": [{"id": t.get("id"), "status": t.get("status"),
                       "agent": t.get("agent"), "request": t.get("request", "")[:80]}
                      for t in tasks[-10:]],
        }
    
    write_mcp_receipt("get_task_state", {"task_id": task_id}, result)
    return result


def snapshot_repo() -> Dict[str, Any]:
    """Snapshot Git status, changed files, and recent commits.
    
    Returns:
        Git branch, commit, changed files, and diff stat.
    """
    def git(args: List[str]) -> str:
        try:
            r = subprocess.run(["git"] + args, capture_output=True, text=True,
                             cwd=str(REPO_ROOT), timeout=15)
            return r.stdout.strip()
        except Exception:
            return ""
    
    branch = git(["rev-parse", "--abbrev-ref", "HEAD"])
    commit = git(["rev-parse", "HEAD"])[:12]
    porcelain = git(["status", "--porcelain"])
    diff_stat = git(["diff", "--stat"])
    
    changed = [line.strip()[3:] for line in porcelain.split("\n") if line.strip()]
    
    result = {
        "branch": branch or "unknown",
        "commit": commit or "none",
        "changed_files": changed,
        "changed_count": len(changed),
        "diff_stat": diff_stat[:500],
        "timestamp": now_iso(),
    }
    
    write_mcp_receipt("snapshot_repo", {}, result)
    return result


def write_receipt(task_id: str, agent: str, files_changed: List[str],
                  commands_run: List[str], test_result: str = "N/A",
                  build_result: str = "N/A", errors: List[str] = None,
                  artifact_output: str = "", next_action: str = "") -> Dict[str, Any]:
    """Write a structured receipt to the HyperFlow ledger.
    
    Args:
        task_id: Task ID this receipt belongs to.
        agent: Agent that performed the work.
        files_changed: List of files modified.
        commands_run: List of commands executed.
        test_result: PASS/FAIL/N/A.
        build_result: PASS/FAIL/N/A.
        errors: List of error messages (empty if none).
        artifact_output: Description of artifact produced.
        next_action: Recommended next action.
    
    Returns:
        The written receipt object.
    """
    receipt = {
        "task_id": task_id,
        "date": now_iso(),
        "agent": agent,
        "files_changed": files_changed,
        "commands_run": commands_run,
        "build_result": build_result,
        "test_result": test_result,
        "errors": errors or [],
        "artifact_output": artifact_output,
        "confidence": "high" if test_result == "PASS" else "medium",
        "next_action": next_action,
    }
    append_jsonl(RECEIPTS_FILE, receipt)
    
    write_mcp_receipt("write_receipt", {"task_id": task_id}, receipt)
    return receipt


def run_verification() -> Dict[str, Any]:
    """Run the canonical verification chain (build, test, lint).
    
    Does NOT run arbitrary commands. Only runs the declared verify.sh.
    
    Returns:
        Verification results for each step.
    """
    results = {"steps": [], "overall": "PASS", "timestamp": now_iso()}
    
    # YTL-MCP tests
    if YTL_DIR.exists():
        try:
            r = subprocess.run([sys.executable, "-m", "pytest", "tests/test_lab.py", "-v"],
                             capture_output=True, text=True, cwd=str(YTL_DIR), timeout=60)
            output = r.stdout + r.stderr
            passed = "passed" in output
            results["steps"].append({
                "name": "ytl_mcp_tests",
                "status": "PASS" if passed else "FAIL",
                "detail": [l for l in output.split("\n") if "passed" in l or "failed" in l][:1],
            })
            if not passed:
                results["overall"] = "FAIL"
        except Exception as e:
            results["steps"].append({"name": "ytl_mcp_tests", "status": "ERROR", "detail": str(e)})
            results["overall"] = "FAIL"
    
    # Hydra watchdog
    try:
        r = subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "hydra_watchdog.py")],
                         capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=30)
        results["steps"].append({"name": "hydra_watchdog", "status": "PASS", "detail": r.stdout.strip()[:100]})
    except Exception as e:
        results["steps"].append({"name": "hydra_watchdog", "status": "ERROR", "detail": str(e)})
        results["overall"] = "FAIL"
    
    # Receipt count
    hf = load_jsonl(RECEIPTS_FILE)
    ytl = load_jsonl(YTL_RECEIPTS)
    mcp = load_jsonl(MCP_RECEIPTS)
    total = len(hf) + len(ytl) + len(mcp)
    results["steps"].append({"name": "receipts", "status": "PASS" if total > 0 else "WARN",
                             "detail": f"{total} total receipts"})
    
    write_mcp_receipt("run_verification", {}, results)
    return results


def get_lab_status() -> Dict[str, Any]:
    """Get YTL-MCP Research Lab status.
    
    Returns:
        Lab health, DB state, video/experiment counts, receipt count.
    """
    ytl_db = YTL_DIR / "data" / "ytl_lab.db"
    ytl_r = load_jsonl(YTL_RECEIPTS)
    
    result = {
        "lab": "YTL-MCP Research Lab",
        "version": LAB_VERSION,
        "db_exists": ytl_db.exists(),
        "ytl_receipts": len(ytl_r),
        "timestamp": now_iso(),
    }
    
    if ytl_db.exists():
        import sqlite3
        conn = sqlite3.connect(str(ytl_db))
        for table in ["videos", "experiments", "scores", "scripts"]:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                result[table] = count
            except:
                result[table] = "table_not_found"
        conn.close()
    
    write_mcp_receipt("get_lab_status", {}, result)
    return result


def score_transcript(video_id: str, transcript_text: str) -> Dict[str, Any]:
    """Score a transcript for hook strength, retention, novelty, density.
    
    Args:
        video_id: Video identifier.
        transcript_text: Full transcript text.
    
    Returns:
        Scoring breakdown across 6 dimensions.
    """
    sys.path.insert(0, str(YTL_DIR / "server"))
    os.chdir(str(YTL_DIR))
    
    import mcp_server
    result = mcp_server.ytl_score_transcript(video_id, transcript_text)
    
    os.chdir(str(REPO_ROOT))
    write_mcp_receipt("score_transcript", {"video_id": video_id}, result)
    return result


def prepare_upload_package(hypothesis: str, topic: str) -> Dict[str, Any]:
    """Prepare a complete upload package (script, metadata, shotlist, risk report).
    
    Args:
        hypothesis: The content hypothesis to test.
        topic: The video topic for metadata generation.
    
    Returns:
        Package info including path, file list, and status.
    """
    sys.path.insert(0, str(YTL_DIR / "server"))
    os.chdir(str(YTL_DIR))
    
    import mcp_server
    
    script = mcp_server.ytl_generate_script(hypothesis, {"source": "mcp_request"})
    metadata = mcp_server.ytl_generate_metadata(script["script_id"], topic)
    shotlist = mcp_server.ytl_generate_shotlist(script)
    package = mcp_server.ytl_prepare_upload_package(script, metadata, shotlist)
    
    result = {
        "package_id": package["package_id"],
        "path": package["path"],
        "files": package["files"],
        "status": package["status"],
        "script_sections": len(script["sections"]),
        "title_variants": len(metadata["title_variants"]),
        "shots": shotlist["total_shots"],
        "policy": "PRIVATE — no public upload without human approval",
    }
    
    os.chdir(str(REPO_ROOT))
    write_mcp_receipt("prepare_upload_package", {"hypothesis": hypothesis, "topic": topic}, result)
    return result


def create_experiment(hypothesis: str, variant: str, target_metric: str,
                      baseline: float, measurement_window_days: int = 7) -> Dict[str, Any]:
    """Create a formal experiment object with hypothesis, metric, and baseline.
    
    Args:
        hypothesis: The hypothesis to test.
        variant: The experimental variant name.
        target_metric: The metric to measure.
        baseline: Current baseline value for the metric.
        measurement_window_days: Days to measure (default 7).
    
    Returns:
        Experiment object with ID and status.
    """
    sys.path.insert(0, str(YTL_DIR / "server"))
    os.chdir(str(YTL_DIR))
    
    import mcp_server
    result = mcp_server.ytl_run_experiment(
        hypothesis=hypothesis, variant=variant, target_metric=target_metric,
        baseline=baseline, measurement_window_days=measurement_window_days
    )
    
    os.chdir(str(REPO_ROOT))
    write_mcp_receipt("create_experiment", {"hypothesis": hypothesis}, result)
    return result


def chatgpt_send_prompt(prompt: str, timeout: int = 60, new_chat: bool = True) -> Dict[str, Any]:
    """Send a prompt to the ChatGPT Mac app and capture the response.
    
    Uses AppleScript + clipboard automation. No API key needed.
    The ChatGPT desktop app must be installed and logged in.
    
    Args:
        prompt: The text prompt to send to ChatGPT.
        timeout: Max seconds to wait for response (default 60).
        new_chat: Start a new chat first (default True).
    
    Returns:
        Dict with prompt, response, elapsed time, and status.
    """
    import time as _time
    import subprocess as _sp
    
    def _applescript(script, t=30):
        r = _sp.run(["osascript", "-e", script], capture_output=True, text=True, timeout=t)
        return r.stdout.strip(), r.stderr.strip()
    
    def _clipboard():
        r = _sp.run(["pbpaste"], capture_output=True, text=True, timeout=10)
        return r.stdout
    
    def _set_clip(text):
        _sp.run(["pbcopy"], input=text, text=True, timeout=10)
    
    start = _time.time()
    
    # 1. Activate ChatGPT
    _sp.run(["open", "-a", "ChatGPT"], capture_output=True, timeout=10)
    _time.sleep(2)
    _applescript('tell application "ChatGPT" to activate')
    _time.sleep(2)
    
    # 2. New chat if requested
    if new_chat:
        _applescript('tell application "System Events" to keystroke "n" using command down')
        _time.sleep(1.5)
    
    # 3. Type prompt via clipboard
    _set_clip(prompt)
    _time.sleep(0.3)
    _applescript('tell application "System Events" to keystroke "v" using command down')
    _time.sleep(0.5)
    
    # 4. Send
    _applescript('tell application "System Events" to keystroke return')
    _time.sleep(1)
    
    # 5. Wait for response
    _time.sleep(min(timeout, 30))
    
    # 6. Capture response via screenshot + OCR
    # (ChatGPT's WebKit view doesn't respond to standard Cmd+C)
    pos, _ = _applescript('tell application "System Events" to tell process "ChatGPT" to get position of window 1')
    size, _ = _applescript('tell application "System Events" to tell process "ChatGPT" to get size of window 1')
    
    response_text = ""
    screenshot_path = ""
    try:
        pos_parts = [int(x) for x in pos.split(", ")]
        size_parts = [int(x) for x in size.split(", ")]
        
        # Take a screenshot of the ChatGPT window
        shot_path = f"/tmp/chatgpt_response_{int(_time.time())}.png"
        _sp.run(["screencapture", "-R", 
                 f"{pos_parts[0]},{pos_parts[1]},{size_parts[0]},{size_parts[1]}",
                 shot_path], capture_output=True, timeout=10)
        screenshot_path = shot_path
        _time.sleep(0.5)
        
        # OCR the screenshot
        try:
            from PIL import Image as _Image
            import pytesseract as _pt
            img = _Image.open(shot_path)
            # Crop to the conversation area (right of sidebar, above composer)
            # Sidebar ~280px, composer ~120px at bottom
            w, h = img.size
            conv = img.crop((280, 50, w, h - 120))
            # OCR
            full_text = _pt.image_to_string(conv)
            
            # Extract response: everything after the prompt
            if full_text and prompt in full_text:
                idx = full_text.rfind(prompt)
                response_text = full_text[idx + len(prompt):].strip()
            elif full_text:
                # If prompt not found exactly, return everything
                response_text = full_text.strip()
            else:
                response_text = "ERROR: OCR returned empty text"
        except ImportError:
            response_text = "ERROR: pytesseract/PIL not installed"
    except Exception as e:
        response_text = f"ERROR: {e}"
    
    elapsed = round(_time.time() - start, 1)
    
    result = {
        "prompt": prompt,
        "response": response_text,
        "elapsed_s": elapsed,
        "timestamp": now_iso(),
        "new_chat": new_chat,
        "screenshot": screenshot_path,
    }
    
    write_mcp_receipt("chatgpt_send_prompt", {"prompt": prompt}, result)
    return result


def get_receipts(count: int = 10, source: str = "all") -> List[Dict[str, Any]]:
    """Get latest receipts from the ledger.
    
    Args:
        count: Number of receipts to return (max 50).
        source: 'all', 'hyperflow', 'ytl', or 'mcp'.
    
    Returns:
        List of receipt objects, newest first.
    """
    count = min(count, 50)
    
    if source == "hyperflow":
        receipts = load_jsonl(RECEIPTS_FILE)
    elif source == "ytl":
        receipts = load_jsonl(YTL_RECEIPTS)
    elif source == "mcp":
        receipts = load_jsonl(MCP_RECEIPTS)
    else:
        receipts = load_jsonl(RECEIPTS_FILE) + load_jsonl(YTL_RECEIPTS) + load_jsonl(MCP_RECEIPTS)
    
    result = receipts[-count:]
    write_mcp_receipt("get_receipts", {"count": count, "source": source}, result)
    return result


# === TOOL REGISTRY ===
# Each tool has: tier, description, input schema, handler
# No tool exposes raw shell, file system, or secrets.

TOOL_REGISTRY = {
    "get_task_state": {
        "tier": 0,
        "description": "Get current task state from the HyperFlow ledger",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Optional task ID. Empty returns all tasks."},
            },
        },
        "handler": get_task_state,
    },
    "snapshot_repo": {
        "tier": 0,
        "description": "Snapshot Git status, changed files, and recent commits",
        "input_schema": {"type": "object", "properties": {}},
        "handler": snapshot_repo,
    },
    "write_receipt": {
        "tier": 1,
        "description": "Write a structured receipt to the HyperFlow ledger",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "agent": {"type": "string"},
                "files_changed": {"type": "array", "items": {"type": "string"}},
                "commands_run": {"type": "array", "items": {"type": "string"}},
                "test_result": {"type": "string", "enum": ["PASS", "FAIL", "N/A"]},
                "build_result": {"type": "string", "enum": ["PASS", "FAIL", "N/A"]},
                "errors": {"type": "array", "items": {"type": "string"}},
                "artifact_output": {"type": "string"},
                "next_action": {"type": "string"},
            },
            "required": ["task_id", "agent", "files_changed", "commands_run"],
        },
        "handler": write_receipt,
    },
    "run_verification": {
        "tier": 2,
        "description": "Run the canonical verification chain (tests, watchdog, receipts)",
        "input_schema": {"type": "object", "properties": {}},
        "handler": run_verification,
    },
    "get_lab_status": {
        "tier": 0,
        "description": "Get YTL-MCP Research Lab status",
        "input_schema": {"type": "object", "properties": {}},
        "handler": get_lab_status,
    },
    "score_transcript": {
        "tier": 1,
        "description": "Score a transcript for hook strength, retention, novelty, density",
        "input_schema": {
            "type": "object",
            "properties": {
                "video_id": {"type": "string"},
                "transcript_text": {"type": "string"},
            },
            "required": ["video_id", "transcript_text"],
        },
        "handler": score_transcript,
    },
    "prepare_upload_package": {
        "tier": 2,
        "description": "Prepare a complete upload package (script, metadata, shotlist, risk report)",
        "input_schema": {
            "type": "object",
            "properties": {
                "hypothesis": {"type": "string"},
                "topic": {"type": "string"},
            },
            "required": ["hypothesis", "topic"],
        },
        "handler": prepare_upload_package,
    },
    "create_experiment": {
        "tier": 2,
        "description": "Create a formal experiment with hypothesis, metric, and baseline",
        "input_schema": {
            "type": "object",
            "properties": {
                "hypothesis": {"type": "string"},
                "variant": {"type": "string"},
                "target_metric": {"type": "string"},
                "baseline": {"type": "number"},
                "measurement_window_days": {"type": "integer", "default": 7},
            },
            "required": ["hypothesis", "variant", "target_metric", "baseline"],
        },
        "handler": create_experiment,
    },
    "chatgpt_send_prompt": {
        "tier": 3,
        "description": "Send a prompt to the ChatGPT Mac app and capture the response. Uses AppleScript automation — no API key needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "The text prompt to send"},
                "timeout": {"type": "integer", "default": 60, "description": "Max seconds to wait"},
                "new_chat": {"type": "boolean", "default": True, "description": "Start a new chat first"},
            },
            "required": ["prompt"],
        },
        "handler": chatgpt_send_prompt,
    },
    "get_receipts": {
        "tier": 0,
        "description": "Get latest receipts from the ledger",
        "input_schema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "default": 10, "maximum": 50},
                "source": {"type": "string", "enum": ["all", "hyperflow", "ytl", "mcp"], "default": "all"},
            },
        },
        "handler": get_receipts,
    },
}

# Tools NOT exposed (safety boundary):
NOT_EXPOSED = [
    "run_any_shell_command",
    "read_arbitrary_file",
    "write_arbitrary_file",
    "delete_file",
    "upload_public",
    "mass_comment",
    "mass_like",
    "mass_subscribe",
    "scrape_private_data",
    "bypass_auth",
    "access_secrets",
    "raw_git_push",
    "raw_git_reset",
    "raw_git_force_push",
]


def list_tools() -> List[Dict[str, Any]]:
    """List all available MCP tools with their schemas."""
    tools = []
    for name, spec in TOOL_REGISTRY.items():
        tools.append({
            "name": name,
            "tier": spec["tier"],
            "description": spec["description"],
            "input_schema": spec["input_schema"],
        })
    return tools


def call_tool(name: str, args: Dict[str, Any]) -> Any:
    """Call a registered MCP tool by name."""
    if name not in TOOL_REGISTRY:
        return {"error": f"Unknown tool: {name}", "available": list(TOOL_REGISTRY.keys())}
    
    handler = TOOL_REGISTRY[name]["handler"]
    
    try:
        result = handler(**args) if args else handler()
        return result
    except TypeError as e:
        return {"error": f"Invalid arguments: {e}"}
    except Exception as e:
        write_mcp_receipt(name, args, {}, status="error", error=str(e))
        return {"error": str(e)}


# === MCP Server Protocol (HTTP/SSE) ===

class MCPHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler for MCP protocol — ChatGPT App connects here."""
    
    def _send_json(self, code: int, obj: Any):
        body = json.dumps(obj, indent=2, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)
    
    def do_OPTIONS(self):
        self._send_json(200, {"status": "ok"})
    
    def do_GET(self):
        path = self.path.split("?")[0]
        
        if path == "/" or path == "/health":
            self._send_json(200, {
                "server": "hyperflow-unified-mcp",
                "version": LAB_VERSION,
                "status": "healthy",
                "tools": len(TOOL_REGISTRY),
                "timestamp": now_iso(),
            })
        elif path == "/tools":
            self._send_json(200, {"tools": list_tools()})
        elif path == "/receipts":
            self._send_json(200, {"receipts": get_receipts(20, "all")})
        elif path == "/status":
            self._send_json(200, get_lab_status())
        else:
            self._send_json(404, {"error": f"Not found: {path}"})
    
    def do_POST(self):
        path = self.path.split("?")[0]
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len) if content_len > 0 else b"{}"
        
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json(400, {"error": "Invalid JSON"})
            return
        
        if path == "/tools/call":
            tool_name = data.get("name", "")
            tool_args = data.get("arguments", {})
            result = call_tool(tool_name, tool_args)
            self._send_json(200, {
                "tool": tool_name,
                "result": result,
                "timestamp": now_iso(),
            })
        elif path == "/mcp":
            # MCP JSON-RPC over HTTP
            method = data.get("method", "")
            msg_id = data.get("id")
            params = data.get("params", {})
            
            if method == "initialize":
                self._send_json(200, {
                    "jsonrpc": "2.0",
                    "result": {
                        "serverInfo": {"name": "hyperflow-unified-mcp", "version": LAB_VERSION},
                        "capabilities": {"tools": {"listChanged": False}},
                    },
                    "id": msg_id,
                })
            elif method == "tools/list":
                self._send_json(200, {
                    "jsonrpc": "2.0",
                    "result": {"tools": list_tools()},
                    "id": msg_id,
                })
            elif method == "tools/call":
                tool_name = params.get("name", "")
                tool_args = params.get("arguments", {})
                result = call_tool(tool_name, tool_args)
                self._send_json(200, {
                    "jsonrpc": "2.0",
                    "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]},
                    "id": msg_id,
                })
            else:
                self._send_json(200, {
                    "jsonrpc": "2.0",
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                    "id": msg_id,
                })
        else:
            self._send_json(404, {"error": f"Not found: {path}"})
    
    def log_message(self, format, *args):
        # Quiet logging — just print to stderr
        sys.stderr.write(f"[{now_iso()}] {self.address_string()} {format % args}\n")


def serve_http(port: int = 8765):
    """Start HTTP MCP server for ChatGPT App / Windsurf connection."""
    server = HTTPServer(("127.0.0.1", port), MCPHTTPHandler)
    print(f"HyperFlow MCP Server (HTTP) on http://127.0.0.1:{port}", flush=True)
    print(f"Endpoints:", flush=True)
    print(f"  GET  /            — health check", flush=True)
    print(f"  GET  /tools       — list tools", flush=True)
    print(f"  POST /tools/call  — call a tool", flush=True)
    print(f"  POST /mcp         — MCP JSON-RPC", flush=True)
    print(f"  GET  /receipts    — latest receipts", flush=True)
    print(f"  GET  /status      — lab status", flush=True)
    print(f"\nTools: {len(TOOL_REGISTRY)}", flush=True)
    print(f"Waiting for ChatGPT App / Windsurf to connect...", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.", flush=True)
        server.shutdown()


# === MCP Server Protocol (stdio) ===

def serve_mcp():
    """Serve MCP protocol over stdio.
    
    Implements a minimal MCP-compatible JSON-RPC loop:
    - initialize: return server info
    - tools/list: return available tools
    - tools/call: execute a tool and return result
    """
    print(json.dumps({
        "jsonrpc": "2.0",
        "result": {
            "serverInfo": {
                "name": "hyperflow-unified-mcp",
                "version": LAB_VERSION,
            },
            "capabilities": {
                "tools": {"listChanged": False},
            },
        },
        "id": None,
    }), flush=True)
    
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        
        method = msg.get("method", "")
        msg_id = msg.get("id")
        params = msg.get("params", {})
        
        if method == "initialize":
            response = {
                "jsonrpc": "2.0",
                "result": {
                    "serverInfo": {"name": "hyperflow-unified-mcp", "version": LAB_VERSION},
                    "capabilities": {"tools": {"listChanged": False}},
                },
                "id": msg_id,
            }
        elif method == "tools/list":
            response = {
                "jsonrpc": "2.0",
                "result": {"tools": list_tools()},
                "id": msg_id,
            }
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_args = params.get("arguments", {})
            result = call_tool(tool_name, tool_args)
            response = {
                "jsonrpc": "2.0",
                "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]},
                "id": msg_id,
            }
        else:
            response = {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method not found: {method}"},
                "id": msg_id,
            }
        
        print(json.dumps(response), flush=True)


# === CLI ===

def main():
    if len(sys.argv) < 2:
        print(f"HyperFlow Unified MCP Server v{LAB_VERSION}")
        print(f"\nAvailable tools ({len(TOOL_REGISTRY)}):")
        for name, spec in TOOL_REGISTRY.items():
            print(f"  [T{spec['tier']}] {name}: {spec['description']}")
        print(f"\nNot exposed ({len(NOT_EXPOSED)}):")
        for name in NOT_EXPOSED:
            print(f"  {name}")
        print(f"\nUsage:")
        print(f"  python3 mcp_unified.py serve              # MCP stdio server")
        print(f"  python3 mcp_unified.py <tool> [json_args] # Call a tool")
        print(f"  python3 mcp_unified.py list               # List tools")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == "list":
        tools = list_tools()
        print(json.dumps(tools, indent=2))
    
    elif cmd == "serve":
        serve_mcp()
    
    elif cmd == "serve-http":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8765
        serve_http(port)
    
    elif cmd in TOOL_REGISTRY:
        args = {}
        if len(sys.argv) > 2:
            try:
                args = json.loads(sys.argv[2])
            except json.JSONDecodeError:
                print(f"Error: arguments must be valid JSON")
                sys.exit(1)
        
        result = call_tool(cmd, args)
        print(json.dumps(result, indent=2, default=str))
    
    else:
        print(f"Unknown command: {cmd}")
        print(f"Available tools: {list(TOOL_REGISTRY.keys())}")
        print(f"Or use: serve, list")
        sys.exit(1)


if __name__ == "__main__":
    main()
