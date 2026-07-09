#!/usr/bin/env python3
"""
HyperFlow receipt append tool.
Appends a receipt entry to hyperflow/receipts.jsonl.

Usage:
    python3 append_receipt.py --task-id HF-0001 --agent windsurf \
        --files-changed file1.py file2.py \
        --commands "python3 test.py" \
        --build-result PASS --test-result PASS \
        --artifact-output "Working build" \
        --next-action "HF-0002: Create validation script"
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent
RECEIPTS_FILE = REPO_ROOT / "hyperflow" / "receipts.jsonl"


def append_receipt(args):
    receipt = {
        "task_id": args.task_id,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "agent": args.agent,
        "files_changed": args.files_changed,
        "commands_run": args.commands,
        "build_result": args.build_result,
        "test_result": args.test_result,
        "errors": args.errors or [],
        "fixes": args.fixes or [],
        "commit_hash": args.commit_hash or "none",
        "artifact_output": args.artifact_output or "",
        "economic_value": {
            "time_saved_hours": args.time_saved or 0,
            "artifact_class": args.artifact_class or "patch",
            "reusability": args.reusability or "low",
            "sellable": args.sellable or False,
            "financeable": args.financeable or False,
        },
        "confidence": args.confidence or "medium",
        "next_action": args.next_action or "TBD",
    }
    
    RECEIPTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with open(RECEIPTS_FILE, "a") as f:
        f.write(json.dumps(receipt) + "\n")
    
    print(f"Receipt appended for {args.task_id}")
    print(f"Location: {RECEIPTS_FILE}")


def main():
    parser = argparse.ArgumentParser(description="Append a HyperFlow receipt")
    parser.add_argument("--task-id", required=True, help="Task ID (e.g., HF-0001)")
    parser.add_argument("--agent", required=True, help="Agent name")
    parser.add_argument("--files-changed", nargs="+", default=[], help="Files changed")
    parser.add_argument("--commands", nargs="+", default=[], help="Commands run")
    parser.add_argument("--build-result", default="N/A", help="Build result")
    parser.add_argument("--test-result", default="N/A", help="Test result")
    parser.add_argument("--errors", nargs="+", default=[], help="Errors encountered")
    parser.add_argument("--fixes", nargs="+", default=[], help="Fixes applied")
    parser.add_argument("--commit-hash", default="", help="Git commit hash")
    parser.add_argument("--artifact-output", default="", help="Artifact produced")
    parser.add_argument("--time-saved", type=int, default=0, help="Time saved in hours")
    parser.add_argument("--artifact-class", default="patch", help="Artifact class")
    parser.add_argument("--reusability", default="low", help="Reusability level")
    parser.add_argument("--sellable", action="store_true", help="Is sellable")
    parser.add_argument("--financeable", action="store_true", help="Is financeable")
    parser.add_argument("--confidence", default="medium", help="Confidence level")
    parser.add_argument("--next-action", default="", help="Next recommended action")
    
    args = parser.parse_args()
    append_receipt(args)


if __name__ == "__main__":
    main()
