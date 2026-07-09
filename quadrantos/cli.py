"""QuadrantOS CLI — Start, stop, and monitor the 4-quadrant agent loop.

Usage:
  python3 -m quadrantos.cli start --mission "review code and fix bugs"
  python3 -m quadrantos.cli start --model llama3.2 --fps 1.0
  python3 -m quadrantos.cli start --no-llm  # observation-only mode
  python3 -m quadrantos.cli status
  python3 -m quadrantos.cli demo
"""

import argparse
import json
import sys
import os
import time
import signal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from quadrantos.loop import QuadrantAgentLoop


def cmd_start(args):
    """Start the quadrant agent loop."""
    loop = QuadrantAgentLoop(
        mission=args.mission,
        ollama_host=args.host,
        ollama_model=args.model,
        fps=args.fps,
        max_iterations=args.max_iterations,
        work_dir=args.work_dir,
        approved=args.approved,
    )

    # Handle Ctrl+C cleanly
    def handler(sig, frame):
        print("\n  [Ctrl+C] Stopping...")
        loop.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handler)

    loop.start(blocking=True)


def cmd_status(args):
    """Print current status of a running loop (or start one briefly to check)."""
    loop = QuadrantAgentLoop(
        ollama_host=args.host,
        ollama_model=args.model,
        work_dir=args.work_dir,
    )

    status = loop.status()
    print(json.dumps(status, indent=2, default=str))


def cmd_demo(args):
    """Run a quick 3-iteration demo to verify the system works."""
    print("  Running 3-iteration demo...")
    loop = QuadrantAgentLoop(
        mission="Demo: observe all 4 quadrants and report",
        fps=1.0,
        max_iterations=3,
        work_dir=args.work_dir,
    )
    loop.start(blocking=True)
    print()
    print("  Demo complete. Check receipts and improvement ledger.")


def cmd_receipts(args):
    """Show recent receipts."""
    from quadrantos.receipt_store import SQLiteReceiptStore
    store = SQLiteReceiptStore(
        os.path.join(args.work_dir or os.getcwd(), "quadrantos", "receipts.db")
    )
    receipts = store.list_recent(limit=args.limit)
    for r in receipts:
        print(f"  {r['timestamp'][:19]}  {r['agent']:20s}  {r['action']:25s}  "
              f"result={r['result']}  chain={r['chain_hash'][:12]}")

    print()
    chain = store.verify_chain()
    print(f"  Chain: {chain['total']} receipts, verified={chain['verified']}, "
          f"intact={chain['chain_intact']}")


def main():
    parser = argparse.ArgumentParser(
        description="QuadrantOS — 4-quadrant autonomous agent loop"
    )
    parser.add_argument("--work-dir", default=None, help="Working directory")
    parser.add_argument("--host", default="http://localhost:11434", help="Ollama host")
    parser.add_argument("--model", default="llama3.2", help="Ollama model")

    sub = parser.add_subparsers(dest="command")

    # start
    p_start = sub.add_parser("start", help="Start the agent loop")
    p_start.add_argument("--mission", default="Observe and assist. Report what you see.",
                         help="Mission for all agents")
    p_start.add_argument("--fps", type=float, default=0.5, help="Observation frequency")
    p_start.add_argument("--max-iterations", type=int, default=0,
                         help="Max iterations (0=infinite)")
    p_start.add_argument("--approved", action="store_true",
                         help="Pre-approve destructive commands (dangerous)")
    p_start.set_defaults(func=cmd_start)

    # status
    p_status = sub.add_parser("status", help="Show system status")
    p_status.set_defaults(func=cmd_status)

    # demo
    p_demo = sub.add_parser("demo", help="Run a 3-iteration demo")
    p_demo.set_defaults(func=cmd_demo)

    # receipts
    p_receipts = sub.add_parser("receipts", help="Show recent receipts")
    p_receipts.add_argument("--limit", type=int, default=20, help="Number of receipts")
    p_receipts.set_defaults(func=cmd_receipts)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
