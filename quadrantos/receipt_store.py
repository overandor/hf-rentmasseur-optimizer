"""SQLite Receipt Store — Durable append-only receipt ledger.

Replaces JSON file receipts with SQLite for:
- Chain verification (previous_receipt linking)
- Tamper detection (hash mismatch)
- Export and replay
- Atomic writes
- Queryable history

Schema:
  receipts(id TEXT PRIMARY KEY, timestamp TEXT, agent TEXT, action TEXT,
           artifact_path TEXT, artifact_hash TEXT, commands_run TEXT,
           result TEXT, details TEXT, previous_receipt TEXT,
           chain_hash TEXT)

The chain_hash is hash(prev_chain_hash + receipt_id + timestamp + artifact_hash),
making tampering detectable across the entire chain.
"""

import os
import json
import hashlib
import uuid
import sqlite3
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any


class SQLiteReceiptStore:
    """Durable append-only receipt ledger backed by SQLite.

    Features:
    - Atomic writes (single transaction)
    - Chain of custody (each receipt links to previous)
    - Tamper detection (chain_hash verification)
    - Export to JSON for portability
    - Replay verification (recompute chain from scratch)
    - Thread-safe (connection per thread)
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS receipts (
        id TEXT PRIMARY KEY,
        timestamp TEXT NOT NULL,
        agent TEXT NOT NULL,
        action TEXT NOT NULL,
        artifact_path TEXT,
        artifact_hash TEXT,
        commands_run TEXT,
        result TEXT DEFAULT 'success',
        details TEXT,
        previous_receipt TEXT,
        chain_hash TEXT NOT NULL,
        session_id TEXT,
        question_id TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_receipts_timestamp ON receipts(timestamp);
    CREATE INDEX IF NOT EXISTS idx_receipts_agent ON receipts(agent);
    CREATE INDEX IF NOT EXISTS idx_receipts_action ON receipts(action);
    CREATE INDEX IF NOT EXISTS idx_receipts_previous ON receipts(previous_receipt);
    CREATE INDEX IF NOT EXISTS idx_receipts_session ON receipts(session_id);
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(os.getcwd(), 'questionos', 'receipts.db')
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._lock = threading.Lock()
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
        return self._local.conn

    def _init_db(self):
        conn = self._get_conn()
        conn.executescript(self.SCHEMA)
        conn.commit()

    def _sha256_file(self, filepath: str) -> Optional[str]:
        try:
            h = hashlib.sha256()
            with open(filepath, 'rb') as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    h.update(chunk)
            return h.hexdigest()
        except Exception:
            return None

    def _compute_chain_hash(self, receipt_id: str, timestamp: str,
                            artifact_hash: str, prev_chain_hash: Optional[str]) -> str:
        """Compute chain hash: hash(prev_chain + receipt_id + timestamp + artifact_hash)."""
        parts = [
            prev_chain_hash or 'GENESIS',
            receipt_id,
            timestamp,
            artifact_hash or 'NULL',
        ]
        return hashlib.sha256('|'.join(parts).encode()).hexdigest()

    def write(self, agent: str, action: str, artifact_path: str = None,
              commands_run: List[str] = None, result: str = 'success',
              details: Dict = None, session_id: str = None,
              question_id: str = None) -> Dict:
        """Write a receipt atomically. Returns the receipt dict."""
        with self._lock:
            conn = self._get_conn()

            receipt_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()

            artifact_hash = None
            if artifact_path and os.path.exists(artifact_path):
                artifact_hash = self._sha256_file(artifact_path)

            # Get previous receipt's chain hash
            prev_row = conn.execute(
                'SELECT id, chain_hash FROM receipts ORDER BY timestamp DESC LIMIT 1'
            ).fetchone()

            prev_id = prev_row['id'] if prev_row else None
            prev_chain = prev_row['chain_hash'] if prev_row else None

            chain_hash = self._compute_chain_hash(
                receipt_id, timestamp, artifact_hash, prev_chain)

            receipt = {
                'id': receipt_id,
                'timestamp': timestamp,
                'agent': agent,
                'action': action,
                'artifact_path': artifact_path,
                'artifact_hash': artifact_hash,
                'commands_run': json.dumps(commands_run or []),
                'result': result,
                'details': json.dumps(details or {}),
                'previous_receipt': prev_id,
                'chain_hash': chain_hash,
                'session_id': session_id,
                'question_id': question_id,
            }

            conn.execute("""
                INSERT INTO receipts
                (id, timestamp, agent, action, artifact_path, artifact_hash,
                 commands_run, result, details, previous_receipt, chain_hash,
                 session_id, question_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                receipt['id'], receipt['timestamp'], receipt['agent'],
                receipt['action'], receipt['artifact_path'], receipt['artifact_hash'],
                receipt['commands_run'], receipt['result'], receipt['details'],
                receipt['previous_receipt'], receipt['chain_hash'],
                receipt['session_id'], receipt['question_id'],
            ))
            conn.commit()

            return self._row_to_dict(receipt)

    def get(self, receipt_id: str) -> Optional[Dict]:
        """Get a receipt by ID."""
        conn = self._get_conn()
        row = conn.execute('SELECT * FROM receipts WHERE id = ?', (receipt_id,)).fetchone()
        return self._row_to_dict(dict(row)) if row else None

    def list_recent(self, limit: int = 20, agent: str = None,
                    action: str = None, session_id: str = None) -> List[Dict]:
        """List recent receipts with optional filters."""
        conn = self._get_conn()
        query = 'SELECT * FROM receipts WHERE 1=1'
        params = []
        if agent:
            query += ' AND agent = ?'
            params.append(agent)
        if action:
            query += ' AND action = ?'
            params.append(action)
        if session_id:
            query += ' AND session_id = ?'
            params.append(session_id)
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(dict(r)) for r in rows]

    def verify_chain(self) -> Dict:
        """Verify the entire receipt chain for tamper detection.

        Recomputes every chain_hash from genesis and checks for mismatch.
        """
        conn = self._get_conn()
        rows = conn.execute(
            'SELECT * FROM receipts ORDER BY timestamp ASC'
        ).fetchall()

        prev_chain = None
        verified = 0
        broken = []

        for row in rows:
            expected = self._compute_chain_hash(
                row['id'], row['timestamp'], row['artifact_hash'], prev_chain)
            if expected != row['chain_hash']:
                broken.append({
                    'receipt_id': row['id'],
                    'expected': expected[:16],
                    'actual': row['chain_hash'][:16],
                    'timestamp': row['timestamp'],
                })
            else:
                verified += 1
            prev_chain = row['chain_hash']

        return {
            'total': len(rows),
            'verified': verified,
            'broken': len(broken),
            'broken_details': broken[:10],
            'chain_intact': len(broken) == 0,
        }

    def export_json(self, output_path: str = None) -> str:
        """Export all receipts as a JSON array for portability."""
        conn = self._get_conn()
        rows = conn.execute('SELECT * FROM receipts ORDER BY timestamp ASC').fetchall()
        receipts = [self._row_to_dict(dict(r)) for r in rows]

        if output_path is None:
            output_path = self.db_path.replace('.db', '_export.json')

        with open(output_path, 'w') as f:
            json.dump(receipts, f, indent=2)

        return output_path

    def export_session(self, session_id: str, output_path: str = None) -> str:
        """Export all receipts for a specific session."""
        conn = self._get_conn()
        rows = conn.execute(
            'SELECT * FROM receipts WHERE session_id = ? ORDER BY timestamp ASC',
            (session_id,)
        ).fetchall()
        receipts = [self._row_to_dict(dict(r)) for r in rows]

        if output_path is None:
            output_path = os.path.join(os.path.dirname(self.db_path),
                                       f'session_{session_id[:8]}_receipts.json')

        with open(output_path, 'w') as f:
            json.dump(receipts, f, indent=2)

        return output_path

    def replay(self, session_id: str = None) -> List[Dict]:
        """Replay receipt history, recomputing hashes to verify integrity."""
        conn = self._get_conn()
        if session_id:
            rows = conn.execute(
                'SELECT * FROM receipts WHERE session_id = ? ORDER BY timestamp ASC',
                (session_id,)
            ).fetchall()
        else:
            rows = conn.execute(
                'SELECT * FROM receipts ORDER BY timestamp ASC'
            ).fetchall()

        replay_log = []
        prev_chain = None
        for row in rows:
            expected = self._compute_chain_hash(
                row['id'], row['timestamp'], row['artifact_hash'], prev_chain)
            ok = expected == row['chain_hash']

            # Verify artifact hash if path exists
            artifact_ok = True
            if row['artifact_path'] and os.path.exists(row['artifact_path']):
                actual = self._sha256_file(row['artifact_path'])
                artifact_ok = actual == row['artifact_hash']

            replay_log.append({
                'receipt_id': row['id'],
                'timestamp': row['timestamp'],
                'agent': row['agent'],
                'action': row['action'],
                'chain_ok': ok,
                'artifact_ok': artifact_ok,
                'result': row['result'],
            })
            prev_chain = row['chain_hash']

        return replay_log

    def summary(self) -> Dict:
        """Get summary statistics."""
        conn = self._get_conn()
        total = conn.execute('SELECT COUNT(*) as c FROM receipts').fetchone()['c']
        by_agent = {}
        for row in conn.execute('SELECT agent, COUNT(*) as c FROM receipts GROUP BY agent'):
            by_agent[row['agent']] = row['c']
        by_action = {}
        for row in conn.execute('SELECT action, COUNT(*) as c FROM receipts GROUP BY action'):
            by_action[row['action']] = row['c']
        failures = conn.execute(
            "SELECT COUNT(*) as c FROM receipts WHERE result != 'success'"
        ).fetchone()['c']

        return {
            'total_receipts': total,
            'by_agent': by_agent,
            'by_action': by_action,
            'failures': failures,
            'db_path': self.db_path,
        }

    def _row_to_dict(self, row: Dict) -> Dict:
        """Convert a DB row to a clean dict with parsed JSON fields."""
        result = dict(row)
        if isinstance(result.get('commands_run'), str):
            try:
                result['commands_run'] = json.loads(result['commands_run'])
            except Exception:
                result['commands_run'] = []
        if isinstance(result.get('details'), str):
            try:
                result['details'] = json.loads(result['details'])
            except Exception:
                result['details'] = {}
        return result
