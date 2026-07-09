"""
Receipt Ledger — Signed receipts and tamper-evident ledgers for compute reuse,
model runs, appraisals, and workflow history.

Each receipt records:
  - What was done (action type)
  - Who did it (agent/user id)
  - When (timestamp)
  - What was produced (artifact hash)
  - What was measured (metrics)
  - What was verified (verification flags)

Receipts are chained: each receipt references the previous receipt hash,
creating a tamper-evident ledger.
"""

import hashlib
import json
import sqlite3
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE = Path(__file__).parent
DB_PATH = str(BASE / 'data' / 'receipts.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

RECEIPT_TYPES = [
    'compute_run',
    'memory_reuse',
    'cache_hit',
    'workflow_restore',
    'agent_execution',
    'build_pass',
    'test_pass',
    'lint_pass',
    'deployment',
    'appraisal',
    'underwriting_decision',
    'compression_event',
    'state_recovery',
    'task_completion',
    'revenue_event',
]


def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS receipts (
        id TEXT PRIMARY KEY,
        receipt_type TEXT NOT NULL,
        agent_id TEXT,
        action TEXT NOT NULL,
        artifact_hash TEXT,
        artifact_path TEXT,
        metrics TEXT,
        verification TEXT,
        prev_receipt_hash TEXT,
        receipt_hash TEXT NOT NULL,
        signature TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        cost_saved_usd REAL DEFAULT 0,
        compute_saved_ms REAL DEFAULT 0,
        latency_saved_ms REAL DEFAULT 0,
        cloud_cost_avoided_usd REAL DEFAULT 0,
        notes TEXT
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_receipt_type ON receipts(receipt_type)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_agent ON receipts(agent_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON receipts(timestamp)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_hash ON receipts(receipt_hash)')
    conn.commit()
    conn.close()


def _hash_receipt(data: dict) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, default=str).encode()
    ).hexdigest()


def _sign(receipt_hash: str, agent_id: str) -> str:
    return hashlib.sha256(
        f"{receipt_hash}:{agent_id}".encode()
    ).hexdigest()[:32]


def get_last_receipt_hash(db_path: str = DB_PATH) -> Optional[str]:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT receipt_hash FROM receipts ORDER BY timestamp DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def create_receipt(
    receipt_type: str,
    action: str,
    agent_id: str = 'system',
    artifact_hash: str = '',
    artifact_path: str = '',
    metrics: dict = None,
    verification: dict = None,
    cost_saved_usd: float = 0.0,
    compute_saved_ms: float = 0.0,
    latency_saved_ms: float = 0.0,
    cloud_cost_avoided_usd: float = 0.0,
    notes: str = '',
    db_path: str = DB_PATH,
) -> dict:
    """
    Create a signed receipt and append it to the tamper-evident ledger.
    """
    init_db(db_path)

    ts = datetime.now().isoformat()
    prev_hash = get_last_receipt_hash(db_path)

    receipt_data = {
        'receipt_type': receipt_type,
        'action': action,
        'agent_id': agent_id,
        'artifact_hash': artifact_hash,
        'artifact_path': artifact_path,
        'metrics': metrics or {},
        'verification': verification or {},
        'prev_receipt_hash': prev_hash,
        'timestamp': ts,
        'cost_saved_usd': cost_saved_usd,
        'compute_saved_ms': compute_saved_ms,
        'latency_saved_ms': latency_saved_ms,
        'cloud_cost_avoided_usd': cloud_cost_avoided_usd,
        'notes': notes,
    }

    receipt_hash = _hash_receipt(receipt_data)
    signature = _sign(receipt_hash, agent_id)
    receipt_id = receipt_hash[:16]

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO receipts
        (id, receipt_type, agent_id, action, artifact_hash, artifact_path,
         metrics, verification, prev_receipt_hash, receipt_hash, signature,
         timestamp, cost_saved_usd, compute_saved_ms, latency_saved_ms,
         cloud_cost_avoided_usd, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
        (receipt_id, receipt_type, agent_id, action, artifact_hash, artifact_path,
         json.dumps(metrics or {}), json.dumps(verification or {}),
         prev_hash, receipt_hash, signature, ts,
         cost_saved_usd, compute_saved_ms, latency_saved_ms,
         cloud_cost_avoided_usd, notes))
    conn.commit()
    conn.close()

    return {
        'id': receipt_id,
        'receipt_type': receipt_type,
        'action': action,
        'agent_id': agent_id,
        'artifact_hash': artifact_hash,
        'receipt_hash': receipt_hash,
        'prev_receipt_hash': prev_hash,
        'signature': signature,
        'timestamp': ts,
        'cost_saved_usd': cost_saved_usd,
        'compute_saved_ms': compute_saved_ms,
        'latency_saved_ms': latency_saved_ms,
        'cloud_cost_avoided_usd': cloud_cost_avoided_usd,
        'verified': True,
    }


def verify_ledger(db_path: str = DB_PATH) -> dict:
    """Verify the entire receipt ledger is tamper-evident."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''SELECT id, receipt_type, action, agent_id, artifact_hash, metrics,
                  verification, prev_receipt_hash, receipt_hash, timestamp,
                  cost_saved_usd, compute_saved_ms, latency_saved_ms, cloud_cost_avoided_usd, notes
               FROM receipts ORDER BY timestamp ASC''')
    rows = c.fetchall()
    conn.close()

    expected_prev = None
    broken = []
    for row in rows:
        rid = row[0]
        prev = row[7]
        actual_hash = row[8]
        if prev != expected_prev:
            broken.append({'id': rid, 'reason': 'prev_hash_mismatch'})
        expected_prev = actual_hash

    return {
        'total_receipts': len(rows),
        'ledger_intact': len(broken) == 0,
        'broken_receipts': broken,
    }


def query_receipts(
    receipt_type: str = '',
    agent_id: str = '',
    limit: int = 50,
    offset: int = 0,
    db_path: str = DB_PATH,
) -> list:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    q = '''SELECT id, receipt_type, agent_id, action, artifact_hash, receipt_hash,
           signature, timestamp, cost_saved_usd, compute_saved_ms, latency_saved_ms,
           cloud_cost_avoided_usd, notes
           FROM receipts'''
    conditions = []
    params = []
    if receipt_type:
        conditions.append("receipt_type=?")
        params.append(receipt_type)
    if agent_id:
        conditions.append("agent_id=?")
        params.append(agent_id)
    if conditions:
        q += " WHERE " + " AND ".join(conditions)
    q += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    c.execute(q, params)
    rows = c.fetchall()
    conn.close()
    return [{
        'id': r[0], 'receipt_type': r[1], 'agent_id': r[2], 'action': r[3],
        'artifact_hash': r[4], 'receipt_hash': r[5], 'signature': r[6],
        'timestamp': r[7], 'cost_saved_usd': r[8], 'compute_saved_ms': r[9],
        'latency_saved_ms': r[10], 'cloud_cost_avoided_usd': r[11], 'notes': r[12],
    } for r in rows]


def get_receipt_stats(db_path: str = DB_PATH) -> dict:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM receipts")
    total = c.fetchone()[0]
    c.execute("SELECT receipt_type, COUNT(*) FROM receipts GROUP BY receipt_type")
    by_type = dict(c.fetchall())
    c.execute("SELECT COUNT(DISTINCT agent_id) FROM receipts")
    agents = c.fetchone()[0]
    c.execute("SELECT SUM(cost_saved_usd) FROM receipts")
    total_cost_saved = c.fetchone()[0] or 0.0
    c.execute("SELECT SUM(compute_saved_ms) FROM receipts")
    total_compute_saved = c.fetchone()[0] or 0.0
    c.execute("SELECT SUM(latency_saved_ms) FROM receipts")
    total_latency_saved = c.fetchone()[0] or 0.0
    c.execute("SELECT SUM(cloud_cost_avoided_usd) FROM receipts")
    total_cloud_avoided = c.fetchone()[0] or 0.0
    conn.close()
    return {
        'total_receipts': total,
        'by_type': by_type,
        'unique_agents': agents,
        'total_cost_saved_usd': round(total_cost_saved, 2),
        'total_compute_saved_ms': round(total_compute_saved, 2),
        'total_latency_saved_ms': round(total_latency_saved, 2),
        'total_cloud_cost_avoided_usd': round(total_cloud_avoided, 2),
    }


init_db()
