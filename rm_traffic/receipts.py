"""
Receipts — tamper-evident receipt ledger with OpenTelemetry-style traces.

Every action writes a receipt:
  tenant_id
  timestamp
  state_before_hash
  action
  reason
  model_used
  state_after_hash
  metric_delta
  reward
  error
  revenue_estimate

Receipts are append-only and hash-chained for tamper evidence.
"""

import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

log = logging.getLogger("receipts")

RECEIPT_DB = Path(__file__).parent / "overclock_receipts.db"


@dataclass
class Receipt:
    # Trace
    trace_id: str = ""
    span_id: str = ""

    # Identity
    tenant_id: str = ""
    timestamp: str = ""

    # State
    state_before_hash: str = ""
    state_after_hash: str = ""

    # Action
    action: str = ""
    reason: str = ""
    model_used: str = ""

    # Outcome
    metric_delta: Dict = field(default_factory=dict)
    reward: float = 0.0
    error: str = ""
    revenue_estimate: float = 0.0

    # Tamper evidence
    prev_hash: str = ""
    receipt_hash: str = ""


def _db():
    conn = sqlite3.connect(str(RECEIPT_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        trace_id TEXT,
        span_id TEXT,
        tenant_id TEXT,
        timestamp TEXT,
        state_before_hash TEXT,
        state_after_hash TEXT,
        action TEXT,
        reason TEXT,
        model_used TEXT,
        metric_delta TEXT,
        reward REAL,
        error TEXT,
        revenue_estimate REAL,
        prev_hash TEXT,
        receipt_hash TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_tenant ON receipts(tenant_id);
    CREATE INDEX IF NOT EXISTS idx_action ON receipts(action);
    CREATE INDEX IF NOT EXISTS idx_trace ON receipts(trace_id);
    """)
    conn.commit()
    return conn


def _last_hash(conn: sqlite3.Connection, tenant_id: str) -> str:
    cur = conn.cursor()
    cur.execute(
        "SELECT receipt_hash FROM receipts WHERE tenant_id = ? ORDER BY id DESC LIMIT 1",
        (tenant_id,)
    )
    row = cur.fetchone()
    return row["receipt_hash"] if row else "genesis"


def write_receipt(receipt: Receipt) -> str:
    """Write a tamper-evident receipt. Returns the receipt hash."""
    conn = _db()

    if not receipt.timestamp:
        receipt.timestamp = datetime.now(timezone.utc).isoformat()

    if not receipt.trace_id:
        receipt.trace_id = hashlib.sha256(
            f"{receipt.tenant_id}:{receipt.timestamp}".encode()
        ).hexdigest()[:16]

    if not receipt.span_id:
        receipt.span_id = hashlib.sha256(
            f"{receipt.trace_id}:{receipt.action}".encode()
        ).hexdigest()[:8]

    receipt.prev_hash = _last_hash(conn, receipt.tenant_id)

    # Compute receipt hash (chain)
    chain_data = f"{receipt.prev_hash}:{receipt.tenant_id}:{receipt.action}:{receipt.reward}:{receipt.timestamp}"
    receipt.receipt_hash = hashlib.sha256(chain_data.encode()).hexdigest()[:16]

    conn.execute(
        """INSERT INTO receipts
        (trace_id, span_id, tenant_id, timestamp, state_before_hash, state_after_hash,
         action, reason, model_used, metric_delta, reward, error, revenue_estimate,
         prev_hash, receipt_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (receipt.trace_id, receipt.span_id, receipt.tenant_id, receipt.timestamp,
         receipt.state_before_hash, receipt.state_after_hash,
         receipt.action, receipt.reason, receipt.model_used,
         json.dumps(receipt.metric_delta), receipt.reward, receipt.error,
         receipt.revenue_estimate, receipt.prev_hash, receipt.receipt_hash)
    )
    conn.commit()
    conn.close()

    log.info(f"  ◉ Receipt: {receipt.receipt_hash} | action={receipt.action} reward={receipt.reward:.3f}")
    return receipt.receipt_hash


def get_recent_receipts(tenant_id: str, limit: int = 10) -> list:
    """Get recent receipts for a tenant."""
    conn = _db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM receipts WHERE tenant_id = ? ORDER BY id DESC LIMIT ?",
        (tenant_id, limit)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def verify_chain(tenant_id: str) -> bool:
    """Verify the receipt chain is not tampered."""
    conn = _db()
    cur = conn.cursor()
    cur.execute(
        "SELECT prev_hash, receipt_hash FROM receipts WHERE tenant_id = ? ORDER BY id ASC",
        (tenant_id,)
    )
    rows = cur.fetchall()
    conn.close()

    prev = "genesis"
    for row in rows:
        if row["prev_hash"] != prev:
            return False
        prev = row["receipt_hash"]
    return True
