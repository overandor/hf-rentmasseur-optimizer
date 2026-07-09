#!/usr/bin/env python3
"""
ClientPulse OS — Hourly Metrics Collector
Ingests first-party metric packets and appends to the snapshot ledger.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"
INGEST_FILE = CONTENT_DIR / "metrics_ingest.jsonl"


def ingest_snapshot(data: dict) -> str:
    """Append a metric snapshot to the JSONL ingest file."""
    CONTENT_DIR.mkdir(parents=True, exist_ok=True)

    if "timestamp" not in data:
        data["timestamp"] = datetime.now(timezone.utc).isoformat()

    required = ["views", "contact_clicks", "profile_visible", "availability_truthful",
                "days_online", "views_per_day"]
    missing = [f for f in required if f not in data]
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    data.setdefault("bookmarks", 0)
    data.setdefault("returning_visitors", 0)
    data.setdefault("new_visitors", 0)
    data.setdefault("photos_changed", False)
    data.setdefault("price_changed", False)
    data.setdefault("services_changed", False)
    data.setdefault("availability_changed", False)
    data.setdefault("external_link_changed", False)

    with open(INGEST_FILE, "a") as f:
        f.write(json.dumps(data) + "\n")

    return data["timestamp"]


def ingest_from_stdin():
    """Read JSON from stdin and ingest."""
    raw = sys.stdin.read().strip()
    if not raw:
        print("No input provided")
        sys.exit(1)
    data = json.loads(raw)
    ts = ingest_snapshot(data)
    print(f"Ingested snapshot at {ts}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--stdin":
        ingest_from_stdin()
    else:
        print("Usage: echo '{\"views\": 2802, ...}' | python3 hourly_metrics_collector.py --stdin")
