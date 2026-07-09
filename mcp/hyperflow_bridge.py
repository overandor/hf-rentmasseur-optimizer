#!/usr/bin/env python3
"""
HyperFlow MCP Bridge — Windsurf MCP tool server.
Exposes task ledger, receipt creation, and build status to Windsurf Cascade.
"""

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
TASK_LEDGER = REPO_ROOT / "TASK_LEDGER.md"
RECEIPTS_DIR = REPO_ROOT / "RECEIPTS"
SCRIPTS_DIR = REPO_ROOT / "scripts"


def get_task_ledger() -> str:
    """Return current TASK_LEDGER.md contents."""
    if TASK_LEDGER.exists():
        return TASK_LEDGER.read_text()
    return "TASK_LEDGER.md not found"


def get_next_task() -> Optional[Dict[str, str]]:
    """Parse TASK_LEDGER.md and return the next TODO task."""
    if not TASK_LEDGER.exists():
        return None
    
    content = TASK_LEDGER.read_text()
    lines = content.split("\n")
    
    current_task = {}
    for line in lines:
        if line.startswith("## TASK-"):
            if current_task.get("status") == "TODO":
                return current_task
            task_id = line.split("—")[0].strip().replace("## ", "")
            current_task = {"id": task_id, "title": line.split("—", 1)[-1].strip()}
        elif line.startswith("Status:"):
            current_task["status"] = line.replace("Status:", "").strip()
        elif line.startswith("Owner:"):
            current_task["owner"] = line.replace("Owner:", "").strip()
        elif line.startswith("Goal:"):
            current_task["goal"] = line.replace("Goal:", "").strip()
    
    if current_task.get("status") == "TODO":
        return current_task
    return None


def create_receipt(
    task_id: str,
    agent: str,
    objective: str,
    files_changed: List[str],
    commands_run: List[str],
    results: Dict[str, str],
    pass_fail: str,
    evidence: List[str],
    known_limitations: str = "",
    next_task: str = "",
    branch: str = "",
    commit: str = "",
) -> str:
    """Write a receipt file and return its path."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # Determine receipt subdirectory
    if "test" in task_id.lower():
        receipt_dir = RECEIPTS_DIR / "test_receipts"
    elif "build" in task_id.lower():
        receipt_dir = RECEIPTS_DIR / "build_receipts"
    elif "qa" in task_id.lower():
        receipt_dir = RECEIPTS_DIR / "qa_receipts"
    else:
        receipt_dir = RECEIPTS_DIR / "build_receipts"
    
    receipt_dir.mkdir(parents=True, exist_ok=True)
    
    receipt_path = receipt_dir / f"{task_id}.md"
    
    content = f"""# Receipt

Task ID: {task_id}
Agent: {agent}
Date: {timestamp}
Repo: {REPO_ROOT}
Branch: {branch or 'main'}
Commit: {commit or 'none'}

Objective: {objective}

Files changed:
{chr(10).join(f'- {f}' for f in files_changed)}

Commands run:
```bash
{chr(10).join(commands_run)}
```

Results:
- Build: {results.get('build', 'N/A')}
- Tests: {results.get('tests', 'N/A')}
- Lint: {results.get('lint', 'N/A')}

Pass/fail: {pass_fail}

Evidence:
{chr(10).join(f'- {e}' for e in evidence)}

Known limitations:
{known_limitations or 'None'}

Next recommended task:
{next_task or 'TBD'}
"""
    
    receipt_path.write_text(content)
    return str(receipt_path)


def run_build() -> Dict[str, Any]:
    """Execute scripts/build.sh and return results."""
    build_script = SCRIPTS_DIR / "build.sh"
    if not build_script.exists():
        return {"success": False, "error": "build.sh not found", "output": ""}
    
    result = subprocess.run(
        ["bash", str(build_script)],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=300
    )
    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "output": result.stdout + result.stderr,
    }


def run_tests() -> Dict[str, Any]:
    """Execute scripts/test.sh and return results."""
    test_script = SCRIPTS_DIR / "test.sh"
    if not test_script.exists():
        return {"success": False, "error": "test.sh not found", "output": ""}
    
    result = subprocess.run(
        ["bash", str(test_script)],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=300
    )
    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "output": result.stdout + result.stderr,
    }


def get_latest_receipts(count: int = 5) -> List[Dict[str, str]]:
    """Return the latest N receipts."""
    receipts = []
    for subdir in RECEIPTS_DIR.iterdir():
        if subdir.is_dir():
            for receipt_file in subdir.glob("*.md"):
                if receipt_file.name == "receipt_template.md":
                    continue
                stat = receipt_file.stat()
                receipts.append({
                    "path": str(receipt_file),
                    "name": receipt_file.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                })
    
    receipts.sort(key=lambda r: r["modified"], reverse=True)
    return receipts[:count]


def update_task_status(task_id: str, status: str) -> bool:
    """Update a task's status in TASK_LEDGER.md."""
    if not TASK_LEDGER.exists():
        return False
    
    content = TASK_LEDGER.read_text()
    # Find the task and update its status
    lines = content.split("\n")
    in_task = False
    for i, line in enumerate(lines):
        if line.startswith(f"## {task_id}"):
            in_task = True
        elif in_task and line.startswith("Status:"):
            lines[i] = f"Status: {status}"
            TASK_LEDGER.write_text("\n".join(lines))
            return True
    return False


# MCP Tool Definitions (for Windsurf Cascade integration)
MCP_TOOLS = {
    "get_task_ledger": {
        "description": "Get the current task ledger contents",
        "handler": get_task_ledger,
    },
    "get_next_task": {
        "description": "Get the next TODO task from the ledger",
        "handler": get_next_task,
    },
    "create_receipt": {
        "description": "Create a receipt for a completed task",
        "handler": create_receipt,
    },
    "run_build": {
        "description": "Run the build script and return results",
        "handler": run_build,
    },
    "run_tests": {
        "description": "Run the test script and return results",
        "handler": run_tests,
    },
    "get_latest_receipts": {
        "description": "Get the latest N receipts",
        "handler": get_latest_receipts,
    },
    "update_task_status": {
        "description": "Update a task's status in the ledger",
        "handler": update_task_status,
    },
}


if __name__ == "__main__":
    # CLI interface for testing
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python3 hyperflow_bridge.py <command> [args]")
        print(f"Available commands: {list(MCP_TOOLS.keys())}")
        sys.exit(1)
    
    cmd = sys.argv[1]
    if cmd in MCP_TOOLS:
        handler = MCP_TOOLS[cmd]["handler"]
        if cmd == "get_next_task":
            result = handler()
            print(json.dumps(result, indent=2) if result else "No TODO tasks found")
        elif cmd == "get_latest_receipts":
            result = handler(10)
            print(json.dumps(result, indent=2))
        elif cmd == "run_build":
            result = handler()
            print(json.dumps(result, indent=2))
        elif cmd == "run_tests":
            result = handler()
            print(json.dumps(result, indent=2))
        elif cmd == "get_task_ledger":
            print(handler())
        else:
            print(f"Command: {cmd}")
            print(f"Handler: {handler}")
    else:
        print(f"Unknown command: {cmd}")
        print(f"Available: {list(MCP_TOOLS.keys())}")
