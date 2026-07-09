"""
State Snapshotter — capture complete profile state.
"""

import json
from pathlib import Path
from typing import Dict
from datetime import datetime, timezone

from .api_client import RentMasseurAPI

SNAPSHOT_DIR = Path(__file__).parent / "data" / "profile_snapshots"


def snapshot_state(api: RentMasseurAPI) -> Dict:
    """Capture a full snapshot of profile state."""
    state = api.full_status()
    state["timestamp"] = datetime.now(timezone.utc).isoformat()
    return state


def save_snapshot(state: Dict, snapshot_dir: Path = SNAPSHOT_DIR):
    """Save a snapshot to disk for forensic rollback."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    ts = state["timestamp"].replace(":", "-")
    path = snapshot_dir / f"snapshot_{ts}.json"
    path.write_text(json.dumps(state, indent=2, default=str))
    return path


def load_latest_snapshot(snapshot_dir: Path = SNAPSHOT_DIR) -> Dict:
    """Load the most recent snapshot."""
    files = sorted(snapshot_dir.glob("snapshot_*.json"), reverse=True)
    if not files:
        return {}
    return json.loads(files[0].read_text())
