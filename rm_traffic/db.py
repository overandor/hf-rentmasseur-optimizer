"""
ProfileOps database — SQLite persistence for receipts, traffic snapshots,
content variants, experiments, and endpoint map.
"""

import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List

DB_PATH = Path(__file__).parent / "profileops.db"


def get_conn():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = get_conn()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS receipts (
        receipt_hash TEXT PRIMARY KEY,
        receipt_type TEXT NOT NULL,
        action TEXT NOT NULL,
        input_hash TEXT,
        output_hash TEXT,
        verified INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        raw_json TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS traffic_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        profile_views INTEGER,
        contact_clicks INTEGER,
        new_visits INTEGER,
        new_emails INTEGER,
        is_hidden INTEGER,
        is_available INTEGER,
        availability_valid_to INTEGER,
        headline TEXT,
        description_len INTEGER,
        raw_json TEXT
    );

    CREATE TABLE IF NOT EXISTS content_variants (
        variant_id TEXT PRIMARY KEY,
        kind TEXT NOT NULL,
        headline TEXT,
        description TEXT,
        title TEXT,
        body TEXT,
        status TEXT NOT NULL,
        hypothesis TEXT,
        created_at TEXT NOT NULL,
        applied_at TEXT,
        removed_at TEXT
    );

    CREATE TABLE IF NOT EXISTS experiments (
        experiment_id TEXT PRIMARY KEY,
        variant_id TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        baseline_views INTEGER,
        baseline_clicks INTEGER,
        final_views INTEGER,
        final_clicks INTEGER,
        result_json TEXT
    );

    CREATE TABLE IF NOT EXISTS endpoint_map (
        endpoint_id TEXT PRIMARY KEY,
        method TEXT NOT NULL,
        path TEXT NOT NULL,
        action_name TEXT,
        request_schema TEXT,
        response_schema TEXT,
        discovered_at TEXT NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_receipts_created_at ON receipts(created_at);
    CREATE INDEX IF NOT EXISTS idx_traffic_snapshots_created_at ON traffic_snapshots(created_at);
    CREATE INDEX IF NOT EXISTS idx_experiments_variant_id ON experiments(variant_id);
    """)
    conn.commit()
    conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha_hash(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()


def write_receipt(receipt_type: str, action: str, before: Any, after: Any, verified: bool = False) -> str:
    created_at = now_iso()
    before_json = json.dumps(before, sort_keys=True, default=str)
    after_json = json.dumps(after, sort_keys=True, default=str)
    input_hash = sha_hash(before_json)
    output_hash = sha_hash(after_json)
    receipt_hash = sha_hash(f"{created_at}|{receipt_type}|{action}|{input_hash}|{output_hash}")
    raw = json.dumps({
        "receipt_hash": receipt_hash,
        "receipt_type": receipt_type,
        "action": action,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "verified": int(verified),
        "created_at": created_at,
        "before": before,
        "after": after,
    }, sort_keys=True, default=str)
    conn = get_conn()
    conn.execute(
        "INSERT INTO receipts (receipt_hash, receipt_type, action, input_hash, output_hash, verified, created_at, raw_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (receipt_hash, receipt_type, action, input_hash, output_hash, int(verified), created_at, raw)
    )
    conn.commit()
    conn.close()
    return receipt_hash


def write_traffic_snapshot(data: Dict[str, Any]):
    created_at = now_iso()
    raw = json.dumps(data, sort_keys=True, default=str)
    conn = get_conn()
    conn.execute(
        "INSERT INTO traffic_snapshots (created_at, profile_views, contact_clicks, new_visits, new_emails, "
        "is_hidden, is_available, availability_valid_to, headline, description_len, raw_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            created_at,
            data.get("profile_views"),
            data.get("contact_clicks"),
            data.get("new_visits"),
            data.get("new_emails"),
            data.get("is_hidden"),
            data.get("is_available"),
            data.get("availability_valid_to"),
            data.get("headline"),
            data.get("description_len"),
            raw,
        )
    )
    conn.commit()
    conn.close()


def get_latest_traffic_snapshot(limit: int = 1) -> List[Dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM traffic_snapshots ORDER BY created_at DESC LIMIT ?",
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_content_variant(variant_id: str, kind: str, headline: str, description: str,
                           title: str = "", body: str = "", status: str = "draft",
                           hypothesis: str = ""):
    created_at = now_iso()
    conn = get_conn()
    conn.execute(
        "INSERT INTO content_variants (variant_id, kind, headline, description, title, body, status, hypothesis, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(variant_id) DO UPDATE SET "
        "headline=excluded.headline, description=excluded.description, title=excluded.title, "
        "body=excluded.body, status=excluded.status, hypothesis=excluded.hypothesis",
        (variant_id, kind, headline, description, title, body, status, hypothesis, created_at)
    )
    conn.commit()
    conn.close()


def set_variant_status(variant_id: str, status: str, timestamp_field: str = "applied_at"):
    conn = get_conn()
    now = now_iso()
    if timestamp_field == "applied_at":
        conn.execute("UPDATE content_variants SET status=?, applied_at=? WHERE variant_id=?", (status, now, variant_id))
    elif timestamp_field == "removed_at":
        conn.execute("UPDATE content_variants SET status=?, removed_at=? WHERE variant_id=?", (status, now, variant_id))
    else:
        conn.execute("UPDATE content_variants SET status=? WHERE variant_id=?", (status, variant_id))
    conn.commit()
    conn.close()


def get_active_variant(kind: str) -> Optional[Dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM content_variants WHERE kind=? AND status='active' ORDER BY applied_at DESC LIMIT 1",
        (kind,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_variant_history(kind: str, limit: int = 20) -> List[Dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM content_variants WHERE kind=? ORDER BY created_at DESC LIMIT ?",
        (kind, limit)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def start_experiment(experiment_id: str, variant_id: str, baseline_views: int, baseline_clicks: int):
    conn = get_conn()
    conn.execute(
        "INSERT INTO experiments (experiment_id, variant_id, started_at, baseline_views, baseline_clicks) "
        "VALUES (?, ?, ?, ?, ?)",
        (experiment_id, variant_id, now_iso(), baseline_views, baseline_clicks)
    )
    conn.commit()
    conn.close()


def end_experiment(experiment_id: str, final_views: int, final_clicks: int, result: Dict):
    conn = get_conn()
    conn.execute(
        "UPDATE experiments SET ended_at=?, final_views=?, final_clicks=?, result_json=? WHERE experiment_id=?",
        (now_iso(), final_views, final_clicks, json.dumps(result, sort_keys=True, default=str), experiment_id)
    )
    conn.commit()
    conn.close()


def get_open_experiments() -> List[Dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM experiments WHERE ended_at IS NULL").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_endpoint(method: str, path: str, action_name: str, request_schema: str = "", response_schema: str = ""):
    endpoint_id = sha_hash(f"{method}:{path}")
    conn = get_conn()
    conn.execute(
        "INSERT INTO endpoint_map (endpoint_id, method, path, action_name, request_schema, response_schema, discovered_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(endpoint_id) DO UPDATE SET "
        "action_name=excluded.action_name, request_schema=excluded.request_schema, response_schema=excluded.response_schema",
        (endpoint_id, method, path, action_name, request_schema, response_schema, now_iso())
    )
    conn.commit()
    conn.close()


def get_endpoints() -> List[Dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM endpoint_map ORDER BY discovered_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]
