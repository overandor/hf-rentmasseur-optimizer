"""SelfImprovementLedger — Tracks agent suggestion quality over time.

Every agent suggestion becomes: accepted, rejected, duplicate, false_positive, or implemented.

When an agent emits a false bug, the ledger records it and reduces that
agent's confidence for similar future observations. This is the missing
self-improvement loop.

Also includes ScreenshotBuffer: 1fps capture, keep last 100, delete old frames.
"""

import os
import json
import time
import hashlib
import sqlite3
import threading
import subprocess
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class SuggestionStatus(Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    FALSE_POSITIVE = "false_positive"
    IMPLEMENTED = "implemented"
    PENDING = "pending"


@dataclass
class Suggestion:
    """An agent suggestion tracked for self-improvement."""
    id: str = ""
    agent: str = ""
    timestamp: str = ""
    observation_hash: str = ""  # Hash of the observation that triggered this
    suggestion_text: str = ""
    status: SuggestionStatus = SuggestionStatus.PENDING
    rejection_reason: str = ""
    confidence_at_time: float = 0.0
    similarity_key: str = ""  # For detecting duplicates


class SelfImprovementLedger:
    """Tracks every agent suggestion and learns from false positives.

    When an agent repeatedly produces false positives for similar observations,
    its confidence score is reduced for that category of observation.

    Confidence adjustment formula:
        agent_confidence[category] *= (1 - false_positive_rate[category] * penalty_factor)

    This means an agent that is wrong 50% of the time about "window_index" issues
    gets its confidence halved for that category.
    """

    PENALTY_FACTOR = 0.5  # How much false positives reduce confidence
    MIN_CONFIDENCE = 0.1  # Floor — never go below this

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(os.getcwd(), 'questionos', 'self_improvement.db')
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
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS suggestions (
                id TEXT PRIMARY KEY,
                agent TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                observation_hash TEXT,
                suggestion_text TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                rejection_reason TEXT DEFAULT '',
                confidence_at_time REAL DEFAULT 0.5,
                similarity_key TEXT DEFAULT '',
                category TEXT DEFAULT 'general'
            );

            CREATE TABLE IF NOT EXISTS agent_confidence (
                agent TEXT NOT NULL,
                category TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                total_suggestions INTEGER DEFAULT 0,
                false_positives INTEGER DEFAULT 0,
                accepted INTEGER DEFAULT 0,
                rejected INTEGER DEFAULT 0,
                implemented INTEGER DEFAULT 0,
                duplicates INTEGER DEFAULT 0,
                PRIMARY KEY (agent, category)
            );

            CREATE INDEX IF NOT EXISTS idx_suggestions_agent ON suggestions(agent);
            CREATE INDEX IF NOT EXISTS idx_suggestions_status ON suggestions(status);
            CREATE INDEX IF NOT EXISTS idx_suggestions_category ON suggestions(category);
        """)
        conn.commit()

    def record_suggestion(self, agent: str, suggestion_text: str,
                          observation_hash: str = None,
                          confidence: float = 0.5,
                          category: str = 'general') -> Dict:
        """Record a new agent suggestion."""
        import uuid
        with self._lock:
            conn = self._get_conn()
            sid = str(uuid.uuid4())
            ts = datetime.now().isoformat()

            # Generate similarity key for duplicate detection
            sim_key = self._similarity_key(suggestion_text)

            conn.execute("""
                INSERT INTO suggestions
                (id, agent, timestamp, observation_hash, suggestion_text,
                 status, confidence_at_time, similarity_key, category)
                VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)
            """, (sid, agent, ts, observation_hash, suggestion_text,
                  confidence, sim_key, category))

            # Update agent confidence stats
            conn.execute("""
                INSERT OR IGNORE INTO agent_confidence
                (agent, category, confidence, total_suggestions,
                 false_positives, accepted, rejected, implemented, duplicates)
                VALUES (?, ?, 0.5, 0, 0, 0, 0, 0, 0)
            """, (agent, category))

            conn.execute("""
                UPDATE agent_confidence
                SET total_suggestions = total_suggestions + 1
                WHERE agent = ? AND category = ?
            """, (agent, category))

            conn.commit()

            return {
                'id': sid,
                'agent': agent,
                'timestamp': ts,
                'status': 'pending',
                'similarity_key': sim_key,
            }

    def update_status(self, suggestion_id: str, status: SuggestionStatus,
                      reason: str = "") -> bool:
        """Update a suggestion's status and adjust agent confidence."""
        with self._lock:
            conn = self._get_conn()

            row = conn.execute(
                'SELECT agent, category FROM suggestions WHERE id = ?',
                (suggestion_id,)
            ).fetchone()

            if not row:
                return False

            agent = row['agent']
            category = row['category']

            conn.execute(
                'UPDATE suggestions SET status = ?, rejection_reason = ? WHERE id = ?',
                (status.value, reason, suggestion_id)
            )

            # Update confidence stats
            stat_map = {
                SuggestionStatus.FALSE_POSITIVE: 'false_positives',
                SuggestionStatus.ACCEPTED: 'accepted',
                SuggestionStatus.REJECTED: 'rejected',
                SuggestionStatus.IMPLEMENTED: 'implemented',
                SuggestionStatus.DUPLICATE: 'duplicates',
            }

            stat_col = stat_map.get(status)
            if stat_col:
                conn.execute(f"""
                    UPDATE agent_confidence
                    SET {stat_col} = {stat_col} + 1
                    WHERE agent = ? AND category = ?
                """, (agent, category))

            # Adjust confidence if false positive
            if status == SuggestionStatus.FALSE_POSITIVE:
                self._reduce_confidence(conn, agent, category)
            elif status == SuggestionStatus.ACCEPTED or status == SuggestionStatus.IMPLEMENTED:
                self._boost_confidence(conn, agent, category)

            conn.commit()
            return True

    def _reduce_confidence(self, conn, agent: str, category: str):
        """Reduce agent confidence for a category after false positive."""
        row = conn.execute(
            'SELECT confidence, total_suggestions, false_positives FROM agent_confidence WHERE agent = ? AND category = ?',
            (agent, category)
        ).fetchone()

        if not row:
            return

        fp_rate = row['false_positives'] / max(1, row['total_suggestions'])
        new_conf = row['confidence'] * (1 - fp_rate * self.PENALTY_FACTOR)
        new_conf = max(self.MIN_CONFIDENCE, new_conf)

        conn.execute(
            'UPDATE agent_confidence SET confidence = ? WHERE agent = ? AND category = ?',
            (new_conf, agent, category)
        )

    def _boost_confidence(self, conn, agent: str, category: str):
        """Slightly boost agent confidence after accepted suggestion."""
        row = conn.execute(
            'SELECT confidence FROM agent_confidence WHERE agent = ? AND category = ?',
            (agent, category)
        ).fetchone()

        if not row:
            return

        new_conf = min(1.0, row['confidence'] + 0.05)
        conn.execute(
            'UPDATE agent_confidence SET confidence = ? WHERE agent = ? AND category = ?',
            (new_conf, agent, category)
        )

    def get_confidence(self, agent: str, category: str = 'general') -> float:
        """Get current confidence score for an agent in a category."""
        conn = self._get_conn()
        row = conn.execute(
            'SELECT confidence FROM agent_confidence WHERE agent = ? AND category = ?',
            (agent, category)
        ).fetchone()
        return row['confidence'] if row else 0.5

    def check_duplicate(self, agent: str, suggestion_text: str,
                        category: str = 'general') -> Optional[Dict]:
        """Check if a similar suggestion was already made."""
        conn = self._get_conn()
        sim_key = self._similarity_key(suggestion_text)

        row = conn.execute(
            'SELECT id, status, timestamp FROM suggestions WHERE agent = ? AND similarity_key = ? AND category = ? ORDER BY timestamp DESC LIMIT 1',
            (agent, sim_key, category)
        ).fetchone()

        if row:
            return {
                'duplicate': True,
                'original_id': row['id'],
                'original_status': row['status'],
                'original_timestamp': row['timestamp'],
            }
        return None

    def _similarity_key(self, text: str) -> str:
        """Generate a similarity key for duplicate detection.

        Normalizes text: lowercase, remove numbers, strip whitespace,
        keep only significant words.
        """
        words = text.lower().split()
        # Remove common words and numbers
        stop = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'to', 'in', 'on',
                'at', 'for', 'of', 'with', 'and', 'or', 'not', 'this', 'that',
                'it', 'be', 'has', 'have', 'had', 'do', 'does', 'did'}
        significant = [w for w in words if w not in stop and not w.isdigit()]
        return hashlib.sha256(' '.join(significant).encode()).hexdigest()[:16]

    def summary(self) -> Dict:
        conn = self._get_conn()
        total = conn.execute('SELECT COUNT(*) as c FROM suggestions').fetchone()['c']
        by_status = {}
        for row in conn.execute('SELECT status, COUNT(*) as c FROM suggestions GROUP BY status'):
            by_status[row['status']] = row['c']

        agents = []
        for row in conn.execute('SELECT * FROM agent_confidence'):
            agents.append({
                'agent': row['agent'],
                'category': row['category'],
                'confidence': round(row['confidence'], 3),
                'total': row['total_suggestions'],
                'false_positives': row['false_positives'],
                'accepted': row['accepted'],
                'implemented': row['implemented'],
            })

        return {
            'total_suggestions': total,
            'by_status': by_status,
            'agent_confidence': agents,
            'false_positives_blocked': by_status.get('false_positive', 0),
        }


class ScreenshotBuffer:
    """Rolling screenshot buffer: 1fps capture, keep last 100, delete old frames.

    Used for:
    - Vision gate observation
    - Motion detection (skip if screen hasn't changed)
    - Debug replay (what did the screen look like when X happened?)
    """

    def __init__(self, buffer_dir: str = None, max_frames: int = 100,
                 fps: float = 1.0):
        self.buffer_dir = buffer_dir or os.path.join(os.getcwd(), 'questionos', 'screenshots')
        os.makedirs(self.buffer_dir, exist_ok=True)
        self.max_frames = max_frames
        self.fps = fps
        self._running = False
        self._thread = None
        self._lock = threading.Lock()
        self._frames: List[Dict] = []
        self._last_hash = None

    def start(self):
        """Start the screenshot capture loop in a background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop the capture loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _capture_loop(self):
        """Main capture loop — runs at configured fps."""
        interval = 1.0 / self.fps
        while self._running:
            try:
                self._capture_one()
            except Exception:
                pass
            time.sleep(interval)

    def _capture_one(self) -> Optional[Dict]:
        """Capture one screenshot and add to buffer."""
        timestamp = time.time()
        filepath = os.path.join(self.buffer_dir, f'frame_{int(timestamp * 1000)}.png')

        try:
            subprocess.run(
                ['screencapture', '-x', filepath],
                capture_output=True, timeout=5
            )
            if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
                return None
        except Exception:
            return None

        # Compute hash for motion detection
        file_hash = self._hash_file(filepath)

        frame = {
            'timestamp': timestamp,
            'filepath': filepath,
            'hash': file_hash,
            'changed': file_hash != self._last_hash,
        }

        with self._lock:
            self._frames.append(frame)
            self._last_hash = file_hash

            # Enforce max frames — delete oldest
            while len(self._frames) > self.max_frames:
                old = self._frames.pop(0)
                try:
                    os.remove(old['filepath'])
                except Exception:
                    pass

        return frame

    def _hash_file(self, filepath: str) -> str:
        """Compute a quick hash of a screenshot for change detection."""
        try:
            h = hashlib.sha256()
            with open(filepath, 'rb') as f:
                # Read first 4096 bytes only for speed
                h.update(f.read(4096))
            return h.hexdigest()[:16]
        except Exception:
            return ""

    def latest(self) -> Optional[Dict]:
        """Get the most recent frame."""
        with self._lock:
            if self._frames:
                return self._frames[-1]
        return None

    def has_changed(self) -> bool:
        """Check if the screen has changed since last capture."""
        latest = self.latest()
        return latest['changed'] if latest else True

    def get_frames(self, count: int = 10) -> List[Dict]:
        """Get the last N frames."""
        with self._lock:
            return list(self._frames[-count:])

    def cleanup(self):
        """Delete all buffered frames."""
        with self._lock:
            for frame in self._frames:
                try:
                    os.remove(frame['filepath'])
                except Exception:
                    pass
            self._frames.clear()

    def summary(self) -> Dict:
        with self._lock:
            return {
                'buffered_frames': len(self._frames),
                'max_frames': self.max_frames,
                'fps': self.fps,
                'running': self._running,
                'last_change': self._frames[-1]['timestamp'] if self._frames else None,
            }
