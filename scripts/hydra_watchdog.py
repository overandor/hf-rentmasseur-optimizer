#!/usr/bin/env python3
"""
Hydra Watchdog — anti-timeout nervous system for AI software workers.

Checks active tasks on a fixed interval. Snapshots Git diff and logs.
Detects expired heartbeats. Generates relaunch packets. Routes failed
tasks to alternate workers. Requires verification before commit.

Usage:
    python3 hydra_watchdog.py                    # single check
    python3 hydra_watchdog.py --daemon           # continuous mode
    python3 hydra_watchdog.py --task HF-017      # check specific task
    python3 hydra_watchdog.py --relaunch HF-017  # generate relaunch packet
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
TASKS_DIR = REPO_ROOT / "TASKS"
RUNS_DIR = REPO_ROOT / "RUNS"
LOGS_DIR = REPO_ROOT / "LOGS"
RECEIPTS_DIR = REPO_ROOT / "RECEIPTS"
HYPERFLOW_DIR = REPO_ROOT / "hyperflow"

# Heartbeat timeout: 12 minutes (in seconds)
HEARTBEAT_TIMEOUT = 12 * 60
# Stall detection: no diff change for 10 minutes
STALL_TIMEOUT = 10 * 60
# Max failures before rerouting
MAX_FAILURES = 2

STATE_COLORS = {
    "GREEN": "Worker active, verifiable progress",
    "YELLOW": "Changes made, no verification",
    "ORANGE": "Stalled, looping, or drifting",
    "RED": "Broke build or edited forbidden files",
    "BLACK": "Provider/session failure",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_git(cmd: List[str]) -> str:
    try:
        result = subprocess.run(
            ["git"] + cmd,
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=30
        )
        return result.stdout.strip()
    except Exception:
        return ""


def get_git_status() -> Dict[str, Any]:
    porcelain = run_git(["status", "--porcelain"])
    diff_stat = run_git(["diff", "--stat"])
    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    commit = run_git(["rev-parse", "HEAD"])
    
    changed_files = []
    for line in porcelain.split("\n"):
        if line.strip():
            changed_files.append(line.strip()[3:])
    
    return {
        "branch": branch,
        "commit": commit[:12] if commit else "none",
        "changed_files": changed_files,
        "diff_stat": diff_stat,
        "porcelain": porcelain,
    }


def load_lock(task_id: str) -> Optional[Dict[str, Any]]:
    lock_path = RUNS_DIR / task_id / "lock.json"
    if lock_path.exists():
        return json.loads(lock_path.read_text())
    return None


def save_lock(task_id: str, lock: Dict[str, Any]) -> None:
    lock_path = RUNS_DIR / task_id / "lock.json"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(lock, indent=2))


def load_task_packet(task_id: str) -> Optional[Dict[str, Any]]:
    task_path = TASKS_DIR / f"{task_id}.json"
    if task_path.exists():
        return json.loads(task_path.read_text())
    
    # Also check .md format
    md_path = TASKS_DIR / f"{task_id}.md"
    if md_path.exists():
        return {"id": task_id, "content": md_path.read_text()}
    
    return None


def load_latest_receipt(task_id: str) -> Optional[Dict[str, Any]]:
    receipt_dir = RECEIPTS_DIR / task_id
    if not receipt_dir.exists():
        # Check hyperflow receipts
        receipts_file = HYPERFLOW_DIR / "receipts.jsonl"
        if receipts_file.exists():
            for line in reversed(receipts_file.read_text().strip().split("\n")):
                if line.strip():
                    r = json.loads(line)
                    if r.get("task_id") == task_id:
                        return r
        return None
    
    receipts = sorted(receipt_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
    if receipts:
        return {"path": str(receipts[0]), "content": receipts[0].read_text()}
    return None


def classify_state(task_id: str, lock: Optional[Dict[str, Any]], git_status: Dict[str, Any]) -> str:
    """Classify worker state: GREEN, YELLOW, ORANGE, RED, BLACK."""
    if not lock:
        return "GREEN"  # No active worker, nothing to classify
    
    # Check heartbeat
    heartbeat_str = lock.get("heartbeat_at", "")
    if heartbeat_str:
        try:
            heartbeat = datetime.fromisoformat(heartbeat_str.replace("Z", "+00:00"))
            elapsed = (datetime.now(timezone.utc) - heartbeat).total_seconds()
            
            if elapsed > HEARTBEAT_TIMEOUT:
                # Worker likely dead
                if lock.get("status") == "failed":
                    return "BLACK"
                return "ORANGE"
        except:
            pass
    
    # Check if build was broken
    if lock.get("status") == "build_broken":
        return "RED"
    
    # Check if worker made changes but no verification
    has_changes = len(git_status["changed_files"]) > 0
    has_receipt = lock.get("last_receipt") is not None
    verified = lock.get("status") == "verified"
    
    if verified and has_changes:
        return "GREEN"
    elif has_changes and not verified:
        return "YELLOW"
    elif not has_changes and lock.get("status") == "active":
        return "ORANGE"
    
    return "GREEN"


def write_checkpoint(task_id: str, lock: Optional[Dict[str, Any]], git_status: Dict[str, Any], state: str) -> str:
    """Write a checkpoint receipt for the task."""
    checkpoint_dir = RECEIPTS_DIR / task_id
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = now_iso()
    checkpoint_path = checkpoint_dir / f"checkpoint_{timestamp.replace(':', '-')}.md"
    
    content = f"""# Checkpoint Receipt

Task ID: {task_id}
Timestamp: {timestamp}
State: {state}
Worker: {lock.get('active_worker', 'unknown') if lock else 'none'}
Branch: {git_status['branch']}
Commit: {git_status['commit']}

Files changed:
{chr(10).join(f'- {f}' for f in git_status['changed_files'])}

Diff stat:
```
{git_status['diff_stat']}
```

Lock status: {lock.get('status', 'none') if lock else 'none'}
Heartbeat: {lock.get('heartbeat_at', 'none') if lock else 'none'}

Next action: {_next_action_for_state(state, task_id, lock)}
"""
    
    checkpoint_path.write_text(content)
    return str(checkpoint_path)


def generate_relaunch_packet(task_id: str, lock: Optional[Dict[str, Any]], git_status: Dict[str, Any], receipt: Optional[Dict[str, Any]]) -> str:
    """Generate a relaunch prompt for a replacement worker."""
    task = load_task_packet(task_id)
    
    objective = "Unknown"
    allowed_files = []
    forbidden_files = []
    verify_cmd = ""
    next_step = ""
    
    if task:
        objective = task.get("objective", task.get("request", "Unknown"))
        allowed_files = task.get("allowed_files", task.get("target_files", []))
        forbidden_files = task.get("forbidden_files", [])
        verify_cmd = task.get("verify_command", task.get("build_command", ""))
        next_step = task.get("next_step", task.get("current_blocker", ""))
    
    receipt_summary = "No previous receipt"
    if receipt:
        if isinstance(receipt, dict):
            receipt_summary = json.dumps(receipt, indent=2)[:500]
        else:
            receipt_summary = str(receipt)[:500]
    
    packet = f"""Continue task {task_id} from the existing repository state. Do not restart from scratch.

Read these files first:
- TASKS/{task_id}.md (or .json)
- RECEIPTS/{task_id}/ (latest checkpoint)
- RUNS/{task_id}/lock.json

Current branch: {git_status['branch']}
Last known commit: {git_status['commit']}

Your assignment is only the next bounded step:
{next_step or objective}

Allowed files:
{chr(10).join(f'- {f}' for f in allowed_files) or '- (as needed for the task)'}

Forbidden files:
{chr(10).join(f'- {f}' for f in forbidden_files) or '- (none specified)'}

Previous receipt summary:
{receipt_summary}

Current Git diff:
{git_status['diff_stat'][:500]}

Before editing, summarize the current task state in five lines. Then inspect the current diff. Preserve useful existing changes. Do not rewrite unrelated architecture. Do not change dependencies unless the task packet explicitly allows it.

You must produce a checkpoint before stopping. The checkpoint must include:
- files changed
- commands run
- test/build result
- current blocker
- exact next continuation step

Completion requires verification. Do not claim completion unless the required command passes:
{verify_cmd or 'scripts/test.sh'}

If verification fails, record the failure exactly and make the smallest corrective patch.
"""
    
    return packet


def _next_action_for_state(state: str, task_id: str, lock: Optional[Dict[str, Any]]) -> str:
    actions = {
        "GREEN": f"Continue {task_id}. Snapshot diff. Allow continuation.",
        "YELLOW": f"Run verification for {task_id}. Request test/build output.",
        "ORANGE": f"Pause {task_id}. Snapshot state. Prepare relaunch packet. Check for stall.",
        "RED": f"Revoke lock for {task_id}. Audit changes. Revert unsafe files. Relaunch or hand off.",
        "BLACK": f"Switch worker for {task_id}. Preserve state. Route to alternate worker head.",
    }
    return actions.get(state, "No action defined.")


def check_task(task_id: str) -> Dict[str, Any]:
    """Check a single task and return its state."""
    lock = load_lock(task_id)
    git_status = get_git_status()
    state = classify_state(task_id, lock, git_status)
    receipt = load_latest_receipt(task_id)
    
    result = {
        "task_id": task_id,
        "state": state,
        "state_description": STATE_COLORS.get(state, "Unknown"),
        "lock": lock,
        "git": {
            "branch": git_status["branch"],
            "commit": git_status["commit"],
            "changed_files": git_status["changed_files"],
        },
        "has_receipt": receipt is not None,
    }
    
    # Write checkpoint
    checkpoint_path = write_checkpoint(task_id, lock, git_status, state)
    result["checkpoint"] = checkpoint_path
    
    # Generate relaunch packet if needed
    if state in ("ORANGE", "RED", "BLACK"):
        packet = generate_relaunch_packet(task_id, lock, git_status, receipt)
        relaunch_path = RUNS_DIR / task_id / "relaunch_packet.md"
        relaunch_path.parent.mkdir(parents=True, exist_ok=True)
        relaunch_path.write_text(packet)
        result["relaunch_packet"] = str(relaunch_path)
        
        # Update lock failures
        if lock:
            failures = lock.get("failure_count", 0) + 1
            lock["failure_count"] = failures
            lock["status"] = "failed"
            lock["revoked"] = failures >= MAX_FAILURES
            save_lock(task_id, lock)
            result["failure_count"] = failures
            result["reroute"] = failures >= MAX_FAILURES
    
    return result


def get_active_tasks() -> List[str]:
    """Get all task IDs that have active locks."""
    active = []
    if RUNS_DIR.exists():
        for task_dir in RUNS_DIR.iterdir():
            if task_dir.is_dir():
                lock_path = task_dir / "lock.json"
                if lock_path.exists():
                    lock = json.loads(lock_path.read_text())
                    if lock.get("status") in ("active", "stalled", "failed"):
                        active.append(task_dir.name)
    return active


def run_daemon(interval: int = 300):
    """Run watchdog in continuous mode."""
    print(f"Hydra Watchdog starting. Check interval: {interval}s")
    print(f"Heartbeat timeout: {HEARTBEAT_TIMEOUT}s")
    print(f"Max failures before reroute: {MAX_FAILURES}")
    print()
    
    while True:
        active = get_active_tasks()
        print(f"[{now_iso()}] Checking {len(active)} active tasks...")
        
        for task_id in active:
            result = check_task(task_id)
            state = result["state"]
            print(f"  {task_id}: {state} — {result['state_description']}")
            
            if result.get("relaunch_packet"):
                print(f"    RELAUNCH PACKET: {result['relaunch_packet']}")
            if result.get("reroute"):
                print(f"    REROUTE: Max failures reached. Switch worker head.")
        
        if not active:
            print("  No active tasks.")
        
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description="Hydra Watchdog — anti-timeout nervous system")
    parser.add_argument("--daemon", action="store_true", help="Run in continuous mode")
    parser.add_argument("--task", help="Check specific task ID")
    parser.add_argument("--relaunch", help="Generate relaunch packet for task ID")
    parser.add_argument("--interval", type=int, default=300, help="Check interval in seconds (daemon mode)")
    
    args = parser.parse_args()
    
    if args.relaunch:
        task_id = args.relaunch
        lock = load_lock(task_id)
        git_status = get_git_status()
        receipt = load_latest_receipt(task_id)
        packet = generate_relaunch_packet(task_id, lock, git_status, receipt)
        print(packet)
        return
    
    if args.task:
        result = check_task(args.task)
        print(json.dumps(result, indent=2, default=str))
        if result.get("relaunch_packet"):
            print(f"\nRelaunch packet written to: {result['relaunch_packet']}")
        return
    
    if args.daemon:
        run_daemon(args.interval)
        return
    
    # Single check of all active tasks
    active = get_active_tasks()
    if not active:
        print("No active tasks. Use 'hyperflow new' to create one.")
        return
    
    print(f"Checking {len(active)} active tasks...")
    for task_id in active:
        result = check_task(task_id)
        print(f"  {task_id}: {result['state']} — {result['state_description']}")
        if result.get("relaunch_packet"):
            print(f"    RELAUNCH: {result['relaunch_packet']}")


if __name__ == "__main__":
    main()
