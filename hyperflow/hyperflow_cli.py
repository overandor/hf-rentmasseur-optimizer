#!/usr/bin/env python3
"""
HyperFlow CLI — command-line interface for the HyperFlow Ledger OS.

Usage:
    hyperflow new "Build provider verification MVP"
    hyperflow list
    hyperflow assign HF-0001 claude
    hyperflow patch HF-0001 codex
    hyperflow build HF-0001 xcode
    hyperflow audit HF-0001 chatgpt
    hyperflow receipt HF-0001
    hyperflow commit HF-0001
    hyperflow value HF-0001
    hyperflow status
    hyperflow next
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
HYPERFLOW_DIR = REPO_ROOT / "hyperflow"
TASKS_FILE = HYPERFLOW_DIR / "tasks.jsonl"
RECEIPTS_FILE = HYPERFLOW_DIR / "receipts.jsonl"
NEXT_FILE = HYPERFLOW_DIR / "next.md"
MEMORY_FILE = HYPERFLOW_DIR / "memory.md"
VALUATION_FILE = HYPERFLOW_DIR / "valuation.md"

STATES = [
    "RAW_IDEA", "SPECIFIED", "PLANNED", "PATCHED", "BUILT",
    "TESTED", "AUDITED", "COMMITED", "PACKAGED", "VALUED", "SOLD"
]

AGENTS = ["chatgpt", "claude", "codex", "windsurf", "xcode", "human", "github"]

ARTIFACT_CLASSES = [
    "residue", "note", "spec", "patch", "verified build",
    "reusable module", "product component", "sellable asset",
    "financeable artifact", "protocol primitive", "platform kernel"
]


def load_tasks():
    tasks = []
    if TASKS_FILE.exists():
        for line in TASKS_FILE.read_text().strip().split("\n"):
            if line.strip():
                tasks.append(json.loads(line))
    return tasks


def save_tasks(tasks):
    with open(TASKS_FILE, "w") as f:
        for t in tasks:
            f.write(json.dumps(t) + "\n")


def load_receipts():
    receipts = []
    if RECEIPTS_FILE.exists():
        for line in RECEIPTS_FILE.read_text().strip().split("\n"):
            if line.strip():
                receipts.append(json.loads(line))
    return receipts


def save_receipts(receipts):
    with open(RECEIPTS_FILE, "w") as f:
        for r in receipts:
            f.write(json.dumps(r) + "\n")


def next_task_id(tasks):
    if not tasks:
        return "HF-0001"
    max_id = 0
    for t in tasks:
        try:
            num = int(t["id"].split("-")[1])
            if num > max_id:
                max_id = num
        except (KeyError, IndexError, ValueError):
            pass
    return f"HF-{max_id + 1:04d}"


def cmd_new(args):
    """Create a new task."""
    tasks = load_tasks()
    task_id = next_task_id(tasks)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    task = {
        "id": task_id,
        "date": now,
        "request": args.request,
        "agent": "unassigned",
        "target_files": [],
        "expected_output": "spec",
        "acceptance_tests": [],
        "risk_level": "medium",
        "status": "RAW_IDEA",
        "artifact_score": 0,
        "artifact_class": "residue",
    }
    tasks.append(task)
    save_tasks(tasks)
    print(f"Created {task_id}: {args.request}")
    print(f"Status: RAW_IDEA")
    print(f"Next: hyperflow assign {task_id} <agent>")


def cmd_list(args):
    """List all tasks."""
    tasks = load_tasks()
    if not tasks:
        print("No tasks found. Use 'hyperflow new' to create one.")
        return
    
    print(f"{'ID':<10} {'Status':<12} {'Agent':<12} {'Score':<6} {'Request'}")
    print("-" * 80)
    for t in tasks:
        print(f"{t['id']:<10} {t['status']:<12} {t.get('agent', '?'):<12} {t.get('artifact_score', 0):<6} {t['request'][:50]}")


def cmd_assign(args):
    """Assign a task to an agent."""
    if args.agent not in AGENTS:
        print(f"Invalid agent: {args.agent}")
        print(f"Valid agents: {', '.join(AGENTS)}")
        return
    
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == args.task_id:
            t["agent"] = args.agent
            if t["status"] == "RAW_IDEA":
                t["status"] = "SPECIFIED"
            save_tasks(tasks)
            print(f"Assigned {args.task_id} to {args.agent}")
            print(f"Status: {t['status']}")
            return
    print(f"Task {args.task_id} not found")


def cmd_status(args):
    """Show overall hyperflow status."""
    tasks = load_tasks()
    receipts = load_receipts()
    
    print("=" * 60)
    print("HyperFlow Ledger OS — Status")
    print("=" * 60)
    print(f"Total tasks: {len(tasks)}")
    print(f"Total receipts: {len(receipts)}")
    print()
    
    state_counts = {}
    for t in tasks:
        s = t.get("status", "UNKNOWN")
        state_counts[s] = state_counts.get(s, 0) + 1
    
    print("Tasks by state:")
    for state in STATES:
        count = state_counts.get(state, 0)
        if count > 0:
            print(f"  {state}: {count}")
    
    print()
    print("Recent receipts:")
    for r in receipts[-5:]:
        print(f"  {r['task_id']}: {r.get('build_result', '?')}/{r.get('test_result', '?')} — {r.get('artifact_output', '?')[:50]}")
    
    print()
    avg_score = sum(t.get("artifact_score", 0) for t in tasks) / max(len(tasks), 1)
    print(f"Average artifact score: {avg_score:.1f}")
    print(f"Financeable artifacts: {sum(1 for t in tasks if t.get('artifact_score', 0) >= 8)}")


def cmd_next(args):
    """Show next actions."""
    if NEXT_FILE.exists():
        print(NEXT_FILE.read_text())
    else:
        print("No next actions file found")


def cmd_receipt(args):
    """Generate or show a receipt."""
    if args.task_id:
        receipts = load_receipts()
        for r in receipts:
            if r["task_id"] == args.task_id:
                print(json.dumps(r, indent=2))
                return
        print(f"No receipt found for {args.task_id}")
    else:
        receipts = load_receipts()
        print(f"Total receipts: {len(receipts)}")
        for r in receipts:
            print(f"  {r['task_id']}: {r.get('build_result', '?')}/{r.get('test_result', '?')}")


def cmd_value(args):
    """Show or update valuation."""
    if VALUATION_FILE.exists():
        print(VALUATION_FILE.read_text())
    else:
        print("No valuation file found")


def cmd_state(args):
    """Update task state."""
    if args.state not in STATES:
        print(f"Invalid state: {args.state}")
        print(f"Valid states: {', '.join(STATES)}")
        return
    
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == args.task_id:
            old_state = t["status"]
            t["status"] = args.state
            save_tasks(tasks)
            print(f"{args.task_id}: {old_state} → {args.state}")
            return
    print(f"Task {args.task_id} not found")


def cmd_build(args):
    """Run build and capture result."""
    build_script = REPO_ROOT / "scripts" / "build.sh"
    if not build_script.exists():
        print("No build.sh found")
        return
    
    print(f"Running build for {args.task_id}...")
    result = subprocess.run(
        ["bash", str(build_script)],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=300
    )
    
    build_log = HYPERFLOW_DIR / "build_logs" / f"{args.task_id}_build.log"
    build_log.parent.mkdir(parents=True, exist_ok=True)
    build_log.write_text(result.stdout + result.stderr)
    
    build_result = "PASS" if result.returncode == 0 else "FAIL"
    print(f"Build: {build_result}")
    print(f"Log: {build_log}")
    
    # Update task state
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == args.task_id:
            t["status"] = "BUILT" if build_result == "PASS" else t["status"]
            save_tasks(tasks)
            break


def cmd_test(args):
    """Run tests and capture result."""
    test_script = REPO_ROOT / "scripts" / "test.sh"
    if not test_script.exists():
        print("No test.sh found")
        return
    
    print(f"Running tests for {args.task_id}...")
    result = subprocess.run(
        ["bash", str(test_script)],
        capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=300
    )
    
    test_log = HYPERFLOW_DIR / "test_logs" / f"{args.task_id}_test.log"
    test_log.parent.mkdir(parents=True, exist_ok=True)
    test_log.write_text(result.stdout + result.stderr)
    
    test_result = "PASS" if result.returncode == 0 else "FAIL"
    print(f"Tests: {test_result}")
    print(f"Log: {test_log}")
    
    # Update task state
    tasks = load_tasks()
    for t in tasks:
        if t["id"] == args.task_id:
            t["status"] = "TESTED" if test_result == "PASS" else t["status"]
            save_tasks(tasks)
            break


def main():
    parser = argparse.ArgumentParser(description="HyperFlow Ledger OS CLI")
    subparsers = parser.add_subparsers(dest="command")
    
    # new
    p_new = subparsers.add_parser("new", help="Create a new task")
    p_new.add_argument("request", help="Task description")
    
    # list
    subparsers.add_parser("list", help="List all tasks")
    
    # assign
    p_assign = subparsers.add_parser("assign", help="Assign task to agent")
    p_assign.add_argument("task_id", help="Task ID")
    p_assign.add_argument("agent", help="Agent name")
    
    # state
    p_state = subparsers.add_parser("state", help="Update task state")
    p_state.add_argument("task_id", help="Task ID")
    p_state.add_argument("state", help="New state")
    
    # build
    p_build = subparsers.add_parser("build", help="Run build for task")
    p_build.add_argument("task_id", help="Task ID")
    
    # test
    p_test = subparsers.add_parser("test", help="Run tests for task")
    p_test.add_argument("task_id", help="Task ID")
    
    # receipt
    p_receipt = subparsers.add_parser("receipt", help="Show receipts")
    p_receipt.add_argument("task_id", nargs="?", help="Task ID")
    
    # status
    subparsers.add_parser("status", help="Show overall status")
    
    # next
    subparsers.add_parser("next", help="Show next actions")
    
    # value
    subparsers.add_parser("value", help="Show valuation")
    
    args = parser.parse_args()
    
    commands = {
        "new": cmd_new,
        "list": cmd_list,
        "assign": cmd_assign,
        "state": cmd_state,
        "build": cmd_build,
        "test": cmd_test,
        "receipt": cmd_receipt,
        "status": cmd_status,
        "next": cmd_next,
        "value": cmd_value,
    }
    
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
