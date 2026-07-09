"""
ProofBook — Auditable Evidence System

Turns decision memos, receipts, and proofs into hashed, recorded, tamper-evident
evidence entries. Each entry is chained to the previous one.

Flow:
  1. Hash and record underwriting memos
  2. Attach signed reuse receipts from memory or compute runs
  3. Feed those receipts into the node valuation model
  4. Rerun the underwriting pipeline with real proof, not claims
"""

import hashlib
import json
import sqlite3
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE = Path(__file__).parent
DB_PATH = str(BASE / 'data' / 'proofbook.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS proof_entries (
        id TEXT PRIMARY KEY,
        entry_type TEXT NOT NULL,
        subject TEXT NOT NULL,
        content_hash TEXT NOT NULL,
        content_json TEXT NOT NULL,
        prev_hash TEXT,
        chain_hash TEXT NOT NULL,
        signature TEXT,
        signer_id TEXT,
        timestamp TEXT NOT NULL,
        tags TEXT,
        metadata TEXT
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_entry_type ON proof_entries(entry_type)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_subject ON proof_entries(subject)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_chain ON proof_entries(chain_hash)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON proof_entries(timestamp)')
    conn.commit()
    conn.close()


def _content_hash(content: dict) -> str:
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, default=str).encode()
    ).hexdigest()


def _chain_hash(content_hash: str, prev_hash: Optional[str]) -> str:
    data = f"{prev_hash or ''}:{content_hash}"
    return hashlib.sha256(data.encode()).hexdigest()


def _sign(content_hash: str, signer_id: str) -> str:
    return hashlib.sha256(
        f"{content_hash}:{signer_id}:{datetime.now().isoformat()}".encode()
    ).hexdigest()[:32]


def get_last_hash(db_path: str = DB_PATH) -> Optional[str]:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT chain_hash FROM proof_entries ORDER BY timestamp DESC LIMIT 1")
    row = c.fetchone()
    conn.close()
    return row[0] if row else None


def record_entry(
    entry_type: str,
    subject: str,
    content: dict,
    signer_id: str = 'system',
    tags: list = None,
    metadata: dict = None,
    db_path: str = DB_PATH,
) -> dict:
    """
    Record a proof entry in the ProofBook.

    entry_type: 'memo', 'receipt', 'valuation', 'audit', 'decision', 'proof'
    subject: what this entry is about (repo name, machine id, workflow id)
    content: the actual evidence/memo/receipt data
    signer_id: who signed this entry
    tags: searchable tags
    metadata: additional context
    """
    init_db(db_path)

    chash = _content_hash(content)
    prev = get_last_hash(db_path)
    chain = _chain_hash(chash, prev)
    sig = _sign(chash, signer_id)
    entry_id = chain[:16]
    ts = datetime.now().isoformat()

    entry = {
        'id': entry_id,
        'entry_type': entry_type,
        'subject': subject,
        'content_hash': chash,
        'content_json': json.dumps(content, sort_keys=True, default=str),
        'prev_hash': prev,
        'chain_hash': chain,
        'signature': sig,
        'signer_id': signer_id,
        'timestamp': ts,
        'tags': json.dumps(tags or []),
        'metadata': json.dumps(metadata or {}),
    }

    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO proof_entries
        (id, entry_type, subject, content_hash, content_json, prev_hash, chain_hash,
         signature, signer_id, timestamp, tags, metadata)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
        (entry['id'], entry['entry_type'], entry['subject'], entry['content_hash'],
         entry['content_json'], entry['prev_hash'], entry['chain_hash'],
         entry['signature'], entry['signer_id'], entry['timestamp'],
         entry['tags'], entry['metadata']))
    conn.commit()
    conn.close()

    return {
        'id': entry_id,
        'entry_type': entry_type,
        'subject': subject,
        'content_hash': chash,
        'chain_hash': chain,
        'prev_hash': prev,
        'signature': sig,
        'signer_id': signer_id,
        'timestamp': ts,
        'tags': tags or [],
        'verified': True,
    }


def verify_chain(db_path: str = DB_PATH) -> dict:
    """Verify the entire proof chain is tamper-evident."""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT id, content_hash, prev_hash, chain_hash FROM proof_entries ORDER BY timestamp ASC")
    rows = c.fetchall()
    conn.close()

    expected_prev = None
    broken = []
    for row in rows:
        eid, chash, prev, chain = row
        if prev != expected_prev:
            broken.append({'id': eid, 'reason': 'prev_hash_mismatch'})
        expected_chain = _chain_hash(chash, prev)
        if chain != expected_chain:
            broken.append({'id': eid, 'reason': 'chain_hash_mismatch'})
        expected_prev = chain

    return {
        'total_entries': len(rows),
        'chain_intact': len(broken) == 0,
        'broken_entries': broken,
    }


def query_entries(
    subject: str = '',
    entry_type: str = '',
    limit: int = 50,
    offset: int = 0,
    db_path: str = DB_PATH,
) -> list:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    q = "SELECT id, entry_type, subject, content_hash, chain_hash, signature, signer_id, timestamp, tags FROM proof_entries"
    conditions = []
    params = []
    if subject:
        conditions.append("subject=?")
        params.append(subject)
    if entry_type:
        conditions.append("entry_type=?")
        params.append(entry_type)
    if conditions:
        q += " WHERE " + " AND ".join(conditions)
    q += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    c.execute(q, params)
    rows = c.fetchall()
    conn.close()
    return [{
        'id': r[0], 'entry_type': r[1], 'subject': r[2],
        'content_hash': r[3], 'chain_hash': r[4], 'signature': r[5],
        'signer_id': r[6], 'timestamp': r[7],
        'tags': json.loads(r[8]) if r[8] else [],
    } for r in rows]


def get_entry_content(entry_id: str, db_path: str = DB_PATH) -> Optional[dict]:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT content_json FROM proof_entries WHERE id=?", (entry_id,))
    row = c.fetchone()
    conn.close()
    if row:
        return json.loads(row[0])
    return None


def get_stats(db_path: str = DB_PATH) -> dict:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM proof_entries")
    total = c.fetchone()[0]
    c.execute("SELECT entry_type, COUNT(*) FROM proof_entries GROUP BY entry_type")
    by_type = dict(c.fetchall())
    c.execute("SELECT subject, COUNT(*) FROM proof_entries GROUP BY subject ORDER BY COUNT(*) DESC LIMIT 10")
    by_subject = dict(c.fetchall())
    c.execute("SELECT COUNT(DISTINCT signer_id) FROM proof_entries")
    signers = c.fetchone()[0]
    conn.close()
    return {
        'total_entries': total,
        'by_type': by_type,
        'by_subject': by_subject,
        'unique_signers': signers,
    }


init_db()
