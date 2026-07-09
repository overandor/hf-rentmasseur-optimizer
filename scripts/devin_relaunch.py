#!/usr/bin/env python3
"""
Devin Relaunch Script — generates a continuation packet for a replacement Devin session.

Usage:
    python3 devin_relaunch.py HF-017
"""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from hydra_watchdog import (
    load_lock, load_latest_receipt, load_task_packet,
    get_git_status, generate_relaunch_packet
)


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 devin_relaunch.py <task_id>")
        sys.exit(1)
    
    task_id = sys.argv[1]
    lock = load_lock(task_id)
    git_status = get_git_status()
    receipt = load_latest_receipt(task_id)
    
    packet = generate_relaunch_packet(task_id, lock, git_status, receipt)
    print(packet)
    
    # Also save to file
    relaunch_path = REPO_ROOT / "RUNS" / task_id / "relaunch_packet.md"
    relaunch_path.parent.mkdir(parents=True, exist_ok=True)
    relaunch_path.write_text(packet)
    print(f"\n--- Saved to {relaunch_path} ---", file=sys.stderr)


if __name__ == "__main__":
    main()
