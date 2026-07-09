#!/usr/bin/env python3
"""
ProofWallet — Life proof wallet. Never lose the proof.

Turns messy life records into shareable proof packets.

    Capture → classify → deadline → proof packet → reminder → export

Stores and verifies:
    receipts, warranties, subscriptions, cancellations, refunds,
    chargebacks, landlord messages, repair records, medical bills,
    insurance claims, employment docs, screenshots, emails, contracts,
    delivery proof, scam evidence.

Core features:
    1. Item capture — upload files, forward emails, manual entry
    2. AI extraction — merchant, date, amount, deadline, policy
    3. Timeline builder — chronological evidence chain
    4. Deadline tracker — warranty, return, trial, cancel, claim deadlines
    5. Proof packet — zip/pdf with all evidence + Merkle proof + dispute letter
    6. Reminder engine — alerts before deadlines expire
    7. Dispute letter generator — refund, cancellation, chargeback, warranty

Evidence is stored with SHA-256 hashes and Merkle tree proofs for
tamper-evidence, aligned with W3C PROV and Verifiable Credentials concepts.

CLI:
    python3 proofwallet.py capture --file receipt.pdf --type receipt
    python3 proofwallet.py capture --text "Canceled Netflix subscription" --type cancellation
    python3 proofwallet.py list
    python3 proofwallet.py item <id>
    python3 proofwallet.py packet <id> --output proof.zip
    python3 proofwallet.py deadlines
    python3 proofwallet.py letter <id> --type refund --output letter.txt
    python3 proofwallet.py stats
    python3 proofwallet.py serve --port 7860
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import time
import zipfile
import io
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Optional, Any

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

PW_DIR = Path(os.environ.get("PW_DIR", ".proofwallet_data"))
PW_DIR.mkdir(parents=True, exist_ok=True)
PW_DB = PW_DIR / "proofwallet.db"
PW_FILES = PW_DIR / "files"
PW_FILES.mkdir(parents=True, exist_ok=True)
PW_RECEIPTS = PW_DIR / "receipts.jsonl"
PW_LOG = PW_DIR / "proofwallet.log"

VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ItemType(str, Enum):
    RECEIPT = "receipt"
    WARRANTY = "warranty"
    SUBSCRIPTION = "subscription"
    CANCELLATION = "cancellation"
    REFUND = "refund"
    CHARGEBACK = "chargeback"
    LANDLORD = "landlord"
    REPAIR = "repair"
    MEDICAL = "medical"
    INSURANCE = "insurance"
    EMPLOYMENT = "employment"
    SCREENSHOT = "screenshot"
    EMAIL = "email"
    CONTRACT = "contract"
    DELIVERY = "delivery"
    SCAM_EVIDENCE = "scam_evidence"
    INVOICE = "invoice"
    OTHER = "other"


class DeadlineType(str, Enum):
    RETURN = "return"
    WARRANTY = "warranty"
    TRIAL = "trial"
    CANCEL = "cancel"
    CLAIM = "claim"
    CHARGEBACK = "chargeback"
    DISPUTE = "dispute"
    RESPONSE = "response"
    STATUTE = "statute"


class LetterType(str, Enum):
    REFUND = "refund"
    CANCELLATION = "cancellation"
    CHARGEBACK = "chargeback"
    WARRANTY = "warranty"
    DISPUTE = "dispute"
    SMALL_CLAIMS = "small_claims"
    IDENTITY_THEFT = "identity_theft"


class PacketFormat(str, Enum):
    ZIP = "zip"
    JSON = "json"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class EvidenceItem:
    """A single piece of evidence in the wallet."""
    id: str
    type: str
    title: str
    merchant: str = ""
    amount: float = 0.0
    currency: str = "USD"
    date: float = 0.0  # transaction/event date (unix timestamp)
    captured_at: float = 0.0  # when added to wallet
    file_hash: str = ""
    file_path: str = ""
    file_size: int = 0
    file_type: str = ""
    raw_text: str = ""
    notes: str = ""
    tags: list[str] = field(default_factory=list)
    deadlines: list[dict] = field(default_factory=list)
    timeline: list[dict] = field(default_factory=list)
    related_items: list[str] = field(default_factory=list)
    proof_hash: str = ""
    receipt_hash: str = ""
    status: str = "active"  # active, resolved, expired, disputed
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "EvidenceItem":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class Deadline:
    """A deadline attached to an evidence item."""
    item_id: str
    type: str  # DeadlineType
    label: str
    due: float  # unix timestamp
    created_at: float = 0.0
    notified: bool = False
    resolved: bool = False
    notes: str = ""

    @property
    def is_expired(self) -> bool:
        return time.time() > self.due and not self.resolved

    @property
    def days_remaining(self) -> int:
        return int((self.due - time.time()) / 86400)

    @property
    def urgency(self) -> str:
        days = self.days_remaining
        if days < 0:
            return "expired"
        if days <= 3:
            return "critical"
        if days <= 7:
            return "urgent"
        if days <= 30:
            return "soon"
        return "normal"


@dataclass
class ProofPacket:
    """Exportable proof packet with Merkle tree proof."""
    packet_id: str
    item_ids: list[str]
    created_at: float
    items: list[dict]
    timeline: list[dict]
    merkle_root: str
    merkle_proofs: dict[str, list[dict]]
    dispute_letter: str = ""
    letter_type: str = ""
    summary: dict = field(default_factory=dict)
    version: str = VERSION


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class Database:
    """SQLite-backed storage for ProofWallet."""

    def __init__(self, path: Path = PW_DB):
        self.path = path
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                merchant TEXT DEFAULT '',
                amount REAL DEFAULT 0,
                currency TEXT DEFAULT 'USD',
                date REAL DEFAULT 0,
                captured_at REAL DEFAULT 0,
                file_hash TEXT DEFAULT '',
                file_path TEXT DEFAULT '',
                file_size INTEGER DEFAULT 0,
                file_type TEXT DEFAULT '',
                raw_text TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                tags TEXT DEFAULT '[]',
                deadlines TEXT DEFAULT '[]',
                timeline TEXT DEFAULT '[]',
                related_items TEXT DEFAULT '[]',
                proof_hash TEXT DEFAULT '',
                receipt_hash TEXT DEFAULT '',
                status TEXT DEFAULT 'active',
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS deadlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_id TEXT NOT NULL,
                type TEXT NOT NULL,
                label TEXT NOT NULL,
                due REAL NOT NULL,
                created_at REAL DEFAULT 0,
                notified INTEGER DEFAULT 0,
                resolved INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                FOREIGN KEY (item_id) REFERENCES items(id)
            );

            CREATE TABLE IF NOT EXISTS packets (
                id TEXT PRIMARY KEY,
                item_ids TEXT NOT NULL,
                created_at REAL NOT NULL,
                merkle_root TEXT NOT NULL,
                summary TEXT DEFAULT '{}',
                letter_type TEXT DEFAULT '',
                letter_text TEXT DEFAULT '',
                file_path TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
            CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
            CREATE INDEX IF NOT EXISTS idx_items_date ON items(date);
            CREATE INDEX IF NOT EXISTS idx_deadlines_due ON deadlines(due);
            CREATE INDEX IF NOT EXISTS idx_deadlines_item ON deadlines(item_id);
        """)
        self.conn.commit()

    def save_item(self, item: EvidenceItem):
        self.conn.execute(
            """INSERT OR REPLACE INTO items
            (id, type, title, merchant, amount, currency, date, captured_at,
             file_hash, file_path, file_size, file_type, raw_text, notes,
             tags, deadlines, timeline, related_items, proof_hash, receipt_hash,
             status, metadata)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (item.id, item.type, item.title, item.merchant, item.amount,
             item.currency, item.date, item.captured_at, item.file_hash,
             item.file_path, item.file_size, item.file_type, item.raw_text,
             item.notes, json.dumps(item.tags), json.dumps(item.deadlines),
             json.dumps(item.timeline), json.dumps(item.related_items),
             item.proof_hash, item.receipt_hash, item.status,
             json.dumps(item.metadata))
        )
        self.conn.commit()

    def get_item(self, item_id: str) -> Optional[EvidenceItem]:
        row = self.conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        if not row:
            return None
        return self._row_to_item(row)

    def list_items(self, item_type: str = "", status: str = "") -> list[EvidenceItem]:
        query = "SELECT * FROM items"
        params = []
        conditions = []
        if item_type:
            conditions.append("type=?")
            params.append(item_type)
        if status:
            conditions.append("status=?")
            params.append(status)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY date DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [self._row_to_item(r) for r in rows]

    def delete_item(self, item_id: str) -> bool:
        cur = self.conn.execute("DELETE FROM items WHERE id=?", (item_id,))
        self.conn.execute("DELETE FROM deadlines WHERE item_id=?", (item_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def save_deadline(self, dl: Deadline):
        self.conn.execute(
            """INSERT OR REPLACE INTO deadlines
            (item_id, type, label, due, created_at, notified, resolved, notes)
            VALUES (?,?,?,?,?,?,?,?)""",
            (dl.item_id, dl.type, dl.label, dl.due, dl.created_at,
             int(dl.notified), int(dl.resolved), dl.notes)
        )
        self.conn.commit()

    def list_deadlines(self, include_expired: bool = True) -> list[Deadline]:
        query = "SELECT * FROM deadlines"
        if not include_expired:
            query += " WHERE due > ? AND resolved = 0"
            rows = self.conn.execute(query, (time.time(),)).fetchall()
        else:
            query += " WHERE resolved = 0"
            rows = self.conn.execute(query).fetchall()
        result = []
        for r in rows:
            result.append(Deadline(
                item_id=r["item_id"], type=r["type"], label=r["label"],
                due=r["due"], created_at=r["created_at"],
                notified=bool(r["notified"]), resolved=bool(r["resolved"]),
                notes=r["notes"] or ""
            ))
        return result

    def resolve_deadline(self, item_id: str, deadline_type: str):
        self.conn.execute(
            "UPDATE deadlines SET resolved=1 WHERE item_id=? AND type=?",
            (item_id, deadline_type)
        )
        self.conn.commit()

    def save_packet(self, packet: ProofPacket, file_path: str = ""):
        self.conn.execute(
            """INSERT OR REPLACE INTO packets
            (id, item_ids, created_at, merkle_root, summary, letter_type, letter_text, file_path)
            VALUES (?,?,?,?,?,?,?,?)""",
            (packet.packet_id, json.dumps(packet.item_ids),
             packet.created_at, packet.merkle_root,
             json.dumps(packet.summary), packet.letter_type,
             packet.dispute_letter, file_path)
        )
        self.conn.commit()

    def list_packets(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM packets ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def _row_to_item(self, row: sqlite3.Row) -> EvidenceItem:
        return EvidenceItem(
            id=row["id"], type=row["type"], title=row["title"],
            merchant=row["merchant"] or "", amount=row["amount"] or 0,
            currency=row["currency"] or "USD", date=row["date"] or 0,
            captured_at=row["captured_at"] or 0,
            file_hash=row["file_hash"] or "", file_path=row["file_path"] or "",
            file_size=row["file_size"] or 0, file_type=row["file_type"] or "",
            raw_text=row["raw_text"] or "", notes=row["notes"] or "",
            tags=json.loads(row["tags"] or "[]"),
            deadlines=json.loads(row["deadlines"] or "[]"),
            timeline=json.loads(row["timeline"] or "[]"),
            related_items=json.loads(row["related_items"] or "[]"),
            proof_hash=row["proof_hash"] or "",
            receipt_hash=row["receipt_hash"] or "",
            status=row["status"] or "active",
            metadata=json.loads(row["metadata"] or "{}")
        )

    def close(self):
        self.conn.close()


# ---------------------------------------------------------------------------
# Merkle tree for tamper-evidence
# ---------------------------------------------------------------------------


class MerkleTree:
    """Binary Merkle tree for tamper-evident proof."""

    @staticmethod
    def hash_data(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    @staticmethod
    def hash_str(s: str) -> str:
        return hashlib.sha256(s.encode()).hexdigest()

    @staticmethod
    def build_tree(leaves: list[str]) -> tuple[str, dict[str, list[dict]]]:
        """
        Build Merkle tree from leaf hashes.
        Returns (root_hash, proof_map) where proof_map[leaf] = [{hash, direction}].
        """
        if not leaves:
            return ("0" * 64, {})

        # Ensure even number of leaves
        tree_levels = [leaves[:]]
        proofs: dict[str, list[dict]] = {l: [] for l in leaves}

        current = leaves[:]
        level_idx = 0
        while len(current) > 1:
            next_level = []
            for i in range(0, len(current), 2):
                left = current[i]
                right = current[i + 1] if i + 1 < len(current) else current[i]
                combined = left + right
                parent = MerkleTree.hash_str(combined)
                next_level.append(parent)

                # Record proof for leaves
                if level_idx == 0:
                    if i + 1 < len(current):
                        proofs[current[i]].append({"hash": current[i + 1], "side": "right"})
                        proofs[current[i + 1]].append({"hash": current[i], "side": "left"})
                else:
                    # Update proofs for all leaves under this node
                    for leaf in proofs:
                        if any(p["hash"] == current[i] for p in proofs[leaf]):
                            if i + 1 < len(current):
                                proofs[leaf].append({"hash": current[i + 1], "side": "right"})
                        elif any(p["hash"] == current[i + 1] for p in proofs[leaf]) if i + 1 < len(current) else False:
                            proofs[leaf].append({"hash": current[i], "side": "left"})

            tree_levels.append(next_level)
            current = next_level
            level_idx += 1

        return (current[0], proofs)

    @staticmethod
    def verify_proof(leaf: str, proof: list[dict], root: str) -> bool:
        current = leaf
        for step in proof:
            if step["side"] == "right":
                current = MerkleTree.hash_str(current + step["hash"])
            else:
                current = MerkleTree.hash_str(step["hash"] + current)
        return current == root


# ---------------------------------------------------------------------------
# Receipt chain
# ---------------------------------------------------------------------------


class ReceiptChain:
    """Tamper-evident receipt chain for all wallet actions."""

    def __init__(self, path: Path = PW_RECEIPTS):
        self.path = path
        self.prev_hash = "0" * 64
        self._load_prev()

    def _load_prev(self):
        if self.path.exists():
            lines = self.path.read_text().strip().split("\n")
            if lines and lines[-1]:
                try:
                    last = json.loads(lines[-1])
                    self.prev_hash = last.get("hash", "0" * 64)
                except json.JSONDecodeError:
                    pass

    def write(self, action: str, item_id: str = "", details: dict = None) -> str:
        ts = time.time()
        entry = json.dumps({
            "prev_hash": self.prev_hash,
            "action": action,
            "item_id": item_id,
            "details": details or {},
            "ts": ts,
        }, sort_keys=True)
        h = hashlib.sha256(entry.encode()).hexdigest()
        receipt = {
            "hash": h,
            "prev_hash": self.prev_hash,
            "action": action,
            "item_id": item_id,
            "details": details or {},
            "ts": ts,
        }
        with open(self.path, "a") as f:
            f.write(json.dumps(receipt) + "\n")
        self.prev_hash = h
        return h

    def verify(self) -> tuple[bool, list[str]]:
        if not self.path.exists():
            return (True, [])
        lines = self.path.read_text().strip().split("\n")
        prev = "0" * 64
        errors = []
        for i, line in enumerate(lines):
            try:
                r = json.loads(line)
                entry = json.dumps({
                    "prev_hash": r["prev_hash"],
                    "action": r["action"],
                    "item_id": r["item_id"],
                    "details": r["details"],
                    "ts": r["ts"],
                }, sort_keys=True)
                h = hashlib.sha256(entry.encode()).hexdigest()
                if h != r["hash"]:
                    errors.append(f"Line {i}: hash mismatch")
                if r["prev_hash"] != prev:
                    errors.append(f"Line {i}: prev_hash chain broken")
                prev = r["hash"]
            except (json.JSONDecodeError, KeyError) as e:
                errors.append(f"Line {i}: parse error: {e}")
                break
        return (len(errors) == 0, errors)

    def list_all(self) -> list[dict]:
        if not self.path.exists():
            return []
        lines = self.path.read_text().strip().split("\n")
        return [json.loads(l) for l in lines if l]


# ---------------------------------------------------------------------------
# Content classifier — extracts merchant, date, amount, deadlines
# ---------------------------------------------------------------------------


class ContentClassifier:
    """Extracts structured data from raw text, emails, receipts."""

    # Merchant patterns
    MERCHANT_PATTERNS = [
        (r"(?:from|at|to)\s+([A-Z][a-zA-Z0-9\s&'.]{2,30})(?:\s+(?:on|for|via|using))", "context"),
        (r"([A-Z][a-zA-Z0-9\s&'.]{2,30})\s+(?:receipt|invoice|order|confirmation|statement)", "prefix"),
        (r"(?:merchant|seller|vendor|store|company):\s*(.+?)(?:\n|$)", "labeled"),
        (r"(?:paid|purchased|bought|ordered)\s+(?:from\s+)?(.+?)(?:\s+(?:on|for|via|\$))", "action"),
    ]

    # Amount patterns
    AMOUNT_PATTERNS = [
        r"\$(\d{1,6}(?:,\d{3})*(?:\.\d{2})?)",
        r"USD\s*(\d{1,6}(?:,\d{3})*(?:\.\d{2})?)",
        r"Total:?\s+\$?(\d{1,6}(?:,\d{3})*(?:\.\d{2})?)",
        r"Amount:?\s+\$?(\d{1,6}(?:,\d{3})*(?:\.\d{2})?)",
        r"Charged:?\s+\$?(\d{1,6}(?:,\d{3})*(?:\.\d{2})?)",
        r"(?:price|cost|fee):?\s+\$?(\d{1,6}(?:,\d{3})*(?:\.\d{2})?)",
    ]

    # Date patterns (returns unix timestamp)
    DATE_PATTERNS = [
        (r"(\d{1,2})/(\d{1,2})/(\d{4})", "us_date"),
        (r"(\d{4})-(\d{2})-(\d{2})", "iso_date"),
        (r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})", "month_name"),
        (r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})", "month_first"),
    ]

    MONTH_MAP = {
        "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
        "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
    }

    # Deadline detection
    DEADLINE_KEYWORDS = {
        "return": [r"return\s*(?:policy|window|period|within)\s*(\d+)\s*days", r"(\d+)\s*day\s*return"],
        "warranty": [r"warranty:?\s*(\d+)\s*(?:year|month|day)", r"(\d+)\s*year\s*warranty", r"guaranteed?\s*(\d+)\s*(?:year|month)"],
        "trial": [r"trial\s*(?:period|ends|expires?)\s*(?:in|after|within)\s*(\d+)\s*days", r"(\d+)\s*day\s*(?:free\s*)?trial"],
        "cancel": [r"cancel\s*(?:anytime|before|by|until)", r"next\s*billing\s*(?:date|cycle)"],
        "claim": [r"claim\s*(?:deadline|expires?|within)\s*(\d+)\s*days", r"must\s*file\s*within\s*(\d+)\s*days"],
        "chargeback": [r"chargeback\s*(?:window|deadline|within)\s*(\d+)\s*days", r"dispute\s*(?:within|deadline)\s*(\d+)\s*days"],
    }

    # Subscription detection
    SUBSCRIPTION_INDICATORS = [
        r"subscription", r"monthly", r"annual", r"recurring", r"auto.?renew",
        r"billing\s*cycle", r"membership", r"plan", r"renews?",
    ]

    # Cancellation detection
    CANCELLATION_INDICATORS = [
        r"cancell?ed?", r"cancel\s*subscription", r"end\s*membership",
        r"stop\s*recurring", r"turn\s*off\s*auto.?renew", r"opt.?out",
    ]

    @classmethod
    def classify(cls, text: str, file_name: str = "") -> dict:
        """Extract structured data from raw text."""
        result = {
            "merchant": "",
            "amount": 0.0,
            "currency": "USD",
            "date": 0.0,
            "type": ItemType.OTHER.value,
            "deadlines": [],
            "tags": [],
            "metadata": {},
        }

        text_lower = text.lower()

        # Detect type
        result["type"] = cls._detect_type(text_lower, file_name)

        # Extract merchant
        result["merchant"] = cls._extract_merchant(text, file_name)

        # Extract amount
        result["amount"] = cls._extract_amount(text)

        # Extract date
        result["date"] = cls._extract_date(text)

        # Extract deadlines
        result["deadlines"] = cls._extract_deadlines(text_lower, result["date"])

        # Extract tags
        result["tags"] = cls._extract_tags(text_lower)

        # Subscription metadata
        if any(re.search(p, text_lower) for p in cls.SUBSCRIPTION_INDICATORS):
            result["metadata"]["is_subscription"] = True
            result["tags"].append("subscription")

        if any(re.search(p, text_lower) for p in cls.CANCELLATION_INDICATORS):
            result["metadata"]["is_cancellation"] = True
            result["tags"].append("cancellation")

        return result

    @classmethod
    def _detect_type(cls, text_lower: str, file_name: str) -> str:
        fn_lower = file_name.lower()
        combined = text_lower + " " + fn_lower

        if any(w in combined for w in ["receipt", "purchase", "order confirmation", "paid"]):
            return ItemType.RECEIPT.value
        if any(w in combined for w in ["warranty", "guarantee"]):
            return ItemType.WARRANTY.value
        if any(w in combined for w in ["subscription", "membership", "billing", "recurring"]):
            return ItemType.SUBSCRIPTION.value
        if any(w in combined for w in ["cancel", "cancellation", "end membership"]):
            return ItemType.CANCELLATION.value
        if any(w in combined for w in ["refund", "reimburse"]):
            return ItemType.REFUND.value
        if any(w in combined for w in ["chargeback", "dispute"]):
            return ItemType.CHARGEBACK.value
        if any(w in combined for w in ["landlord", "lease", "rent", "tenant"]):
            return ItemType.LANDLORD.value
        if any(w in combined for w in ["repair", "service", "fix", "technician"]):
            return ItemType.REPAIR.value
        if any(w in combined for w in ["medical", "hospital", "doctor", "clinic", "bill"]):
            return ItemType.MEDICAL.value
        if any(w in combined for w in ["insurance", "claim", "coverage"]):
            return ItemType.INSURANCE.value
        if any(w in combined for w in ["employment", "paystub", "w2", "offer letter"]):
            return ItemType.EMPLOYMENT.value
        if any(w in combined for w in ["screenshot", "capture"]):
            return ItemType.SCREENSHOT.value
        if any(w in combined for w in ["email", "from:", "subject:", "re:"]):
            return ItemType.EMAIL.value
        if any(w in combined for w in ["contract", "agreement", "terms"]):
            return ItemType.CONTRACT.value
        if any(w in combined for w in ["delivery", "shipped", "tracking", "package"]):
            return ItemType.DELIVERY.value
        if any(w in combined for w in ["scam", "fraud", "phishing", "suspicious"]):
            return ItemType.SCAM_EVIDENCE.value
        if any(w in combined for w in ["invoice", "bill from"]):
            return ItemType.INVOICE.value
        return ItemType.OTHER.value

    @classmethod
    def _extract_merchant(cls, text: str, file_name: str) -> str:
        for pattern, ptype in cls.MERCHANT_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                merchant = m.group(1).strip().rstrip(".")
                if len(merchant) > 2 and not merchant.lower() in {"the", "this", "that", "your"}:
                    return merchant
        # Try file name
        if file_name:
            base = Path(file_name).stem
            if len(base) > 2 and not base.lower().startswith("screenshot"):
                return base.replace("_", " ").title()
        return ""

    @classmethod
    def _extract_amount(cls, text: str) -> float:
        for pattern in cls.AMOUNT_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                try:
                    return float(m.group(1).replace(",", ""))
                except ValueError:
                    continue
        return 0.0

    @classmethod
    def _extract_date(cls, text: str) -> float:
        import calendar
        for pattern, dtype in cls.DATE_PATTERNS:
            m = re.search(pattern, text)
            if m:
                try:
                    if dtype == "us_date":
                        mo, day, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    elif dtype == "iso_date":
                        yr, mo, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    elif dtype == "month_name":
                        day, mon_name, yr = int(m.group(1)), m.group(2), int(m.group(3))
                        mo = cls.MONTH_MAP.get(mon_name, 1)
                    elif dtype == "month_first":
                        mon_name, day, yr = m.group(1), int(m.group(2)), int(m.group(3))
                        mo = cls.MONTH_MAP.get(mon_name, 1)
                    else:
                        continue
                    return time.mktime((yr, mo, day, 0, 0, 0, 0, 0, 0))
                except (ValueError, KeyError):
                    continue
        return time.time()

    @classmethod
    def _extract_deadlines(cls, text_lower: str, base_date: float) -> list[dict]:
        deadlines = []
        for dl_type, patterns in cls.DEADLINE_KEYWORDS.items():
            for pattern in patterns:
                m = re.search(pattern, text_lower)
                if m:
                    try:
                        num = int(m.group(1))
                        if "year" in pattern:
                            days = num * 365
                        elif "month" in pattern:
                            days = num * 30
                        else:
                            days = num
                        due = base_date + (days * 86400) if base_date else time.time() + (days * 86400)
                        deadlines.append({
                            "type": dl_type,
                            "label": f"{dl_type.title()} deadline ({days} days)",
                            "due": due,
                            "days": days,
                        })
                    except (ValueError, IndexError):
                        continue

        # Chargeback default: 120 days from transaction
        if not any(d["type"] == "chargeback" for d in deadlines) and base_date:
            deadlines.append({
                "type": "chargeback",
                "label": "Chargeback window (120 days)",
                "due": base_date + (120 * 86400),
                "days": 120,
            })

        return deadlines

    @classmethod
    def _extract_tags(cls, text_lower: str) -> list[str]:
        tags = []
        tag_keywords = {
            "digital": ["digital", "download", "online", "app store", "in-app"],
            "physical": ["shipped", "delivery", "package", "tracking"],
            "recurring": ["subscription", "recurring", "auto-renew", "monthly", "annual"],
            "refund": ["refund", "reimburse", "money back"],
            "disputed": ["dispute", "chargeback", "fraud", "unauthorized"],
            "warranty": ["warranty", "guarantee", "defect"],
            "urgent": ["urgent", "asap", "immediately", "deadline"],
            "legal": ["legal", "attorney", "lawyer", "court", "sue"],
        }
        for tag, keywords in tag_keywords.items():
            if any(kw in text_lower for kw in keywords):
                tags.append(tag)
        return list(set(tags))


# ---------------------------------------------------------------------------
# Dispute letter generator
# ---------------------------------------------------------------------------


class LetterGenerator:
    """Generates dispute, refund, cancellation, and warranty letters."""

    TEMPLATES = {
        LetterType.REFUND.value: """\
{date}

To: {merchant}
Subject: Request for Refund — {title}

Dear {merchant},

I am writing to request a refund for the following transaction:

  Item: {title}
  Date: {event_date}
  Amount: {currency} {amount:.2f}
  Reference: {item_id}

Reason for refund request:
{reason}

I have attached the following evidence:
{evidence_list}

I expect a response within 14 business days. If this matter is not resolved
satisfactorily, I will file a dispute with my credit card issuer and report
to the Federal Trade Commission.

Sincerely,
{name}
{contact}
""",

        LetterType.CANCELLATION.value: """\
{date}

To: {merchant}
Subject: Cancellation of Subscription/Membership — {title}

Dear {merchant},

I am writing to formally cancel the following subscription/membership:

  Service: {title}
  Account: {metadata_account}
  Date of request: {date}

Please cancel this subscription immediately and confirm in writing.
Do not charge my payment method for any future billing cycles.

I have documented this cancellation request for my records.

Sincerely,
{name}
{contact}
""",

        LetterType.CHARGEBACK.value: """\
{date}

To: {card_issuer}
Subject: Chargeback Dispute — {title}

Dear {card_issuer},

I am disputing the following charge on my account:

  Merchant: {merchant}
  Date: {event_date}
  Amount: {currency} {amount:.2f}
  Reason: {reason}

I did not authorize this charge / the merchant failed to deliver / the
product was not as described / the charge is fraudulent.

I have attempted to resolve this with the merchant on {attempt_date}
without success.

Attached evidence:
{evidence_list}

Please process this chargeback dispute and credit my account.

Sincerely,
{name}
{contact}
""",

        LetterType.WARRANTY.value: """\
{date}

To: {merchant}
Subject: Warranty Claim — {title}

Dear {merchant},

I am filing a warranty claim for the following product:

  Product: {title}
  Purchase date: {event_date}
  Purchase amount: {currency} {amount:.2f}
  Warranty period: {warranty_period}

The product has developed the following defect:
{defect_description}

The defect occurred within the warranty period. I am requesting:
  [ ] Repair
  [ ] Replacement
  [ ] Refund

I have attached the original receipt and warranty documentation.

Sincerely,
{name}
{contact}
""",

        LetterType.DISPUTE.value: """\
{date}

To: {merchant}
Subject: Formal Dispute — {title}

Dear {merchant},

I am formally disputing the following matter:

  Transaction: {title}
  Date: {event_date}
  Amount: {currency} {amount:.2f}

Nature of dispute:
{reason}

I have documented the following evidence:
{evidence_list}

I request that this matter be resolved within 30 days. If not resolved,
I will escalate to:
  - Better Business Bureau (bbb.org)
  - Federal Trade Commission (ftc.gov)
  - Consumer Financial Protection Bureau (cfpb.gov)
  - Small claims court

Sincerely,
{name}
{contact}
""",

        LetterType.SMALL_CLAIMS.value: """\
{date}

To: {merchant}
Subject: Notice of Small Claims Court Filing — {title}

Dear {merchant},

This is notice that I intend to file a claim in small claims court regarding:

  Matter: {title}
  Date: {event_date}
  Amount in dispute: {currency} {amount:.2f}

Basis for claim:
{reason}

Evidence supporting my claim:
{evidence_list}

I will file this claim in the appropriate jurisdiction within 30 days
unless this matter is resolved.

Sincerely,
{name}
{contact}
""",

        LetterType.IDENTITY_THEFT.value: """\
{date}

To: {merchant}
Subject: Identity Theft Report — Fraudulent Charge

Dear {merchant},

I am reporting that my identity was used without my authorization for
the following transaction:

  Transaction: {title}
  Date: {event_date}
  Amount: {currency} {amount:.2f}

I did not authorize this transaction. My identity may have been compromised.

I have:
  [ ] Filed a report with the FTC at IdentityTheft.gov
  [ ] Filed a police report
  [ ] Placed a fraud alert with credit bureaus
  [ ] Notified my bank

Please remove this charge and provide written confirmation.

Sincerely,
{name}
{contact}
""",
    }

    @classmethod
    def generate(
        cls,
        item: EvidenceItem,
        letter_type: str,
        name: str = "[Your Name]",
        contact: str = "[Your Phone/Email]",
        reason: str = "[Describe the issue]",
        defect_description: str = "[Describe the defect]",
        warranty_period: str = "[Warranty period]",
        card_issuer: str = "[Card issuer name]",
        attempt_date: str = "[Date you contacted merchant]",
        metadata_account: str = "[Account/subscription ID]",
    ) -> str:
        template = cls.TEMPLATES.get(letter_type, cls.TEMPLATES[LetterType.DISPUTE.value])

        evidence_list = "  - Proof of purchase (receipt)"
        if item.file_hash:
            evidence_list += f"\n  - Document hash: {item.file_hash}"
        if item.timeline:
            evidence_list += "\n  - Timeline of events:"
            for event in item.timeline:
                evidence_list += f"\n    • {event.get('ts_label', '')}: {event.get('action', '')}"

        event_date_str = time.strftime("%B %d, %Y", time.localtime(item.date)) if item.date else "[Date]"
        date_str = time.strftime("%B %d, %Y", time.localtime(time.time()))

        return template.format(
            date=date_str,
            merchant=item.merchant or "[Merchant]",
            title=item.title,
            event_date=event_date_str,
            amount=item.amount,
            currency=item.currency,
            item_id=item.id,
            reason=reason,
            evidence_list=evidence_list,
            name=name,
            contact=contact,
            defect_description=defect_description,
            warranty_period=warranty_period,
            card_issuer=card_issuer,
            attempt_date=attempt_date,
            metadata_account=metadata_account,
        )


# ---------------------------------------------------------------------------
# Proof packet builder
# ---------------------------------------------------------------------------


class PacketBuilder:
    """Builds exportable proof packets with Merkle proofs."""

    def __init__(self, db: Database):
        self.db = db

    def build(
        self,
        item_ids: list[str],
        letter_type: str = "",
        letter_params: dict = None,
        fmt: str = "zip",
    ) -> tuple[ProofPacket, bytes]:
        """Build a proof packet for one or more items."""
        items = []
        for item_id in item_ids:
            item = self.db.get_item(item_id)
            if item:
                items.append(item)

        if not items:
            raise ValueError("No valid items found")

        # Build timeline across all items
        timeline = self._build_timeline(items)

        # Compute Merkle tree
        leaf_hashes = [item.proof_hash or item.file_hash or MerkleTree.hash_str(item.id) for item in items]
        merkle_root, merkle_proofs = MerkleTree.build_tree(leaf_hashes)

        # Generate dispute letter if requested
        dispute_letter = ""
        if letter_type and items:
            primary = items[0]
            dispute_letter = LetterGenerator.generate(primary, letter_type, **(letter_params or {}))

        # Summary
        summary = {
            "item_count": len(items),
            "total_amount": sum(i.amount for i in items),
            "currency": items[0].currency if items else "USD",
            "merchants": list(set(i.merchant for i in items if i.merchant)),
            "types": list(set(i.type for i in items)),
            "date_range": {
                "earliest": min((i.date for i in items if i.date), default=0),
                "latest": max((i.date for i in items if i.date), default=0),
            },
            "has_files": any(i.file_path for i in items),
        }

        packet = ProofPacket(
            packet_id=hashlib.sha256(
                f"{''.join(item_ids)}:{time.time()}".encode()
            ).hexdigest()[:16],
            item_ids=item_ids,
            created_at=time.time(),
            items=[i.to_dict() for i in items],
            timeline=timeline,
            merkle_root=merkle_root,
            merkle_proofs=merkle_proofs,
            dispute_letter=dispute_letter,
            letter_type=letter_type,
            summary=summary,
        )

        # Serialize
        if fmt == "zip":
            data = self._build_zip(packet, items)
        else:
            data = json.dumps(packet.to_dict() if hasattr(packet, 'to_dict') else asdict(packet),
                              indent=2, sort_keys=True).encode()

        # Save packet record
        self.db.save_packet(packet)

        return packet, data

    def _build_timeline(self, items: list[EvidenceItem]) -> list[dict]:
        events = []
        for item in items:
            if item.date:
                events.append({
                    "ts": item.date,
                    "ts_label": time.strftime("%Y-%m-%d", time.localtime(item.date)),
                    "action": f"{item.type.title()}: {item.title}",
                    "item_id": item.id,
                    "merchant": item.merchant,
                    "amount": item.amount,
                })
            if item.captured_at:
                events.append({
                    "ts": item.captured_at,
                    "ts_label": time.strftime("%Y-%m-%d", time.localtime(item.captured_at)),
                    "action": f"Captured: {item.title}",
                    "item_id": item.id,
                })
            for dl in item.deadlines:
                events.append({
                    "ts": dl.get("due", 0),
                    "ts_label": time.strftime("%Y-%m-%d", time.localtime(dl.get("due", 0))),
                    "action": f"Deadline: {dl.get('label', dl.get('type', 'unknown'))}",
                    "item_id": item.id,
                })
        events.sort(key=lambda e: e.get("ts", 0))
        return events

    def _build_zip(self, packet: ProofPacket, items: list[EvidenceItem]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            # Manifest
            manifest = {
                "packet_id": packet.packet_id,
                "created_at": packet.created_at,
                "version": VERSION,
                "merkle_root": packet.merkle_root,
                "summary": packet.summary,
                "item_count": len(items),
            }
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))

            # Items
            for item in items:
                item_json = json.dumps(item.to_dict(), indent=2, sort_keys=True, default=str)
                zf.writestr(f"items/{item.id}.json", item_json)

                # Include original files
                if item.file_path and Path(item.file_path).exists():
                    zf.write(item.file_path, f"files/{item.id}_{Path(item.file_path).name}")

            # Timeline
            zf.writestr("timeline.json", json.dumps(packet.timeline, indent=2, sort_keys=True))

            # Merkle proofs
            zf.writestr("merkle_proofs.json", json.dumps(packet.merkle_proofs, indent=2, sort_keys=True))

            # Dispute letter
            if packet.dispute_letter:
                zf.writestr("dispute_letter.txt", packet.dispute_letter)

            # Summary
            zf.writestr("summary.json", json.dumps(packet.summary, indent=2, sort_keys=True))

        return buf.getvalue()


# ---------------------------------------------------------------------------
# Core wallet engine
# ---------------------------------------------------------------------------


class ProofWallet:
    """Main ProofWallet engine."""

    def __init__(self):
        self.db = Database()
        self.receipts = ReceiptChain()
        self.classifier = ContentClassifier()
        self.packets = PacketBuilder(self.db)

    def capture(
        self,
        title: str = "",
        item_type: str = "",
        text: str = "",
        file_path: str = "",
        merchant: str = "",
        amount: float = 0.0,
        currency: str = "USD",
        date: float = 0.0,
        notes: str = "",
        tags: list[str] = None,
    ) -> EvidenceItem:
        """Capture a new evidence item."""
        item_id = hashlib.sha256(f"{time.time()}:{text or file_path}:{title}".encode()).hexdigest()[:16]

        raw_text = text
        file_hash = ""
        file_size = 0
        file_type = ""
        stored_path = ""

        # Handle file
        if file_path and Path(file_path).exists():
            file_data = Path(file_path).read_bytes()
            file_hash = hashlib.sha256(file_data).hexdigest()
            file_size = len(file_data)
            file_type = Path(file_path).suffix.lstrip(".")
            stored_path = str(PW_FILES / f"{item_id}_{Path(file_path).name}")
            Path(stored_path).write_bytes(file_data)

            # Try to extract text from file
            if file_type in ("txt", "json", "csv", "html", "htm", "md", "eml"):
                raw_text = file_data.decode("utf-8", errors="replace")

        # Classify
        classified = self.classifier.classify(raw_text, file_path or title)

        # Override with explicit values
        final_type = item_type or classified["type"]
        final_merchant = merchant or classified["merchant"]
        final_amount = amount if amount else classified["amount"]
        final_date = date if date else classified["date"]
        final_tags = tags if tags else classified["tags"]
        final_deadlines = classified["deadlines"]
        final_metadata = classified["metadata"]

        if not title:
            title = final_merchant or f"{final_type.title()} item"
            if final_amount:
                title += f" — ${final_amount:.2f}"

        # Compute proof hash
        proof_input = f"{item_id}:{file_hash}:{raw_text[:500]}:{final_type}:{final_merchant}:{final_amount}"
        proof_hash = hashlib.sha256(proof_input.encode()).hexdigest()

        # Build timeline
        timeline = []
        if final_date:
            timeline.append({
                "ts": final_date,
                "ts_label": time.strftime("%Y-%m-%d", time.localtime(final_date)),
                "action": f"{final_type.title()} occurred",
                "merchant": final_merchant,
                "amount": final_amount,
            })
        timeline.append({
            "ts": time.time(),
            "ts_label": time.strftime("%Y-%m-%d", time.localtime()),
            "action": "Captured to ProofWallet",
        })

        item = EvidenceItem(
            id=item_id,
            type=final_type,
            title=title,
            merchant=final_merchant,
            amount=final_amount,
            currency=currency,
            date=final_date,
            captured_at=time.time(),
            file_hash=file_hash,
            file_path=stored_path,
            file_size=file_size,
            file_type=file_type,
            raw_text=raw_text[:5000],
            notes=notes,
            tags=final_tags,
            deadlines=final_deadlines,
            timeline=timeline,
            proof_hash=proof_hash,
            metadata=final_metadata,
        )

        # Write receipt
        item.receipt_hash = self.receipts.write("captured", item_id, {
            "type": final_type,
            "merchant": final_merchant,
            "amount": final_amount,
            "title": title,
        })

        # Save
        self.db.save_item(item)

        # Save deadlines
        for dl in final_deadlines:
            deadline = Deadline(
                item_id=item_id,
                type=dl["type"],
                label=dl["label"],
                due=dl["due"],
                created_at=time.time(),
            )
            self.db.save_deadline(deadline)

        return item

    def list_items(self, item_type: str = "", status: str = "") -> list[EvidenceItem]:
        return self.db.list_items(item_type, status)

    def get_item(self, item_id: str) -> Optional[EvidenceItem]:
        return self.db.get_item(item_id)

    def delete_item(self, item_id: str) -> bool:
        item = self.db.get_item(item_id)
        if item:
            self.receipts.write("deleted", item_id, {"title": item.title})
            # Delete file
            if item.file_path and Path(item.file_path).exists():
                Path(item.file_path).unlink()
            return self.db.delete_item(item_id)
        return False

    def get_deadlines(self, include_expired: bool = True) -> list[Deadline]:
        return self.db.list_deadlines(include_expired)

    def resolve_deadline(self, item_id: str, deadline_type: str):
        self.db.resolve_deadline(item_id, deadline_type)
        self.receipts.write("deadline_resolved", item_id, {"type": deadline_type})

    def build_packet(
        self,
        item_ids: list[str],
        letter_type: str = "",
        letter_params: dict = None,
        fmt: str = "zip",
    ) -> tuple[ProofPacket, bytes]:
        packet, data = self.packets.build(item_ids, letter_type, letter_params, fmt)
        self.receipts.write("packet_built", packet.packet_id, {
            "item_ids": item_ids,
            "merkle_root": packet.merkle_root,
            "letter_type": letter_type,
        })
        return packet, data

    def generate_letter(
        self,
        item_id: str,
        letter_type: str,
        **kwargs,
    ) -> str:
        item = self.db.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        letter = LetterGenerator.generate(item, letter_type, **kwargs)
        self.receipts.write("letter_generated", item_id, {"type": letter_type})
        return letter

    def get_statistics(self) -> dict:
        items = self.db.list_items()
        deadlines = self.db.list_deadlines(include_expired=False)
        expired = [d for d in self.db.list_deadlines(include_expired=True) if d.is_expired]

        type_counts = {}
        total_amount = 0.0
        for item in items:
            type_counts[item.type] = type_counts.get(item.type, 0) + 1
            total_amount += item.amount

        return {
            "total_items": len(items),
            "type_breakdown": type_counts,
            "total_amount": total_amount,
            "active_deadlines": len(deadlines),
            "expired_deadlines": len(expired),
            "critical_deadlines": len([d for d in deadlines if d.urgency == "critical"]),
            "urgent_deadlines": len([d for d in deadlines if d.urgency == "urgent"]),
            "packets_built": len(self.db.list_packets()),
            "receipt_chain_verified": self.receipts.verify()[0],
        }

    def get_dashboard(self) -> dict:
        stats = self.get_statistics()
        deadlines = self.db.list_deadlines(include_expired=False)
        items = self.db.list_items()

        # Upcoming deadlines (sorted by urgency)
        upcoming = []
        for dl in deadlines:
            item = self.db.get_item(dl.item_id)
            upcoming.append({
                "item_id": dl.item_id,
                "item_title": item.title if item else "Unknown",
                "type": dl.type,
                "label": dl.label,
                "due": dl.due,
                "days_remaining": dl.days_remaining,
                "urgency": dl.urgency,
            })
        upcoming.sort(key=lambda d: d["due"])

        # Recent items
        recent = [
            {
                "id": i.id,
                "type": i.type,
                "title": i.title,
                "merchant": i.merchant,
                "amount": i.amount,
                "date": i.date,
                "status": i.status,
                "has_file": bool(i.file_path),
            }
            for i in items[:10]
        ]

        return {
            "stats": stats,
            "upcoming_deadlines": upcoming[:10],
            "recent_items": recent,
            "version": VERSION,
        }

    def get_reminders(self) -> list[dict]:
        """Check all deadlines and return reminders sorted by urgency."""
        deadlines = self.db.list_deadlines(include_expired=True)
        reminders = []
        for dl in deadlines:
            if dl.resolved:
                continue
            item = self.db.get_item(dl.item_id)
            title = item.title if item else "Unknown"
            merchant = item.merchant if item else ""
            days = dl.days_remaining
            urgency = dl.urgency

            # Determine notification level
            if urgency == "expired":
                level = "expired"
                message = f"OVERDUE: {dl.label} for '{title}' was due {time.strftime('%Y-%m-%d', time.localtime(dl.due))}"
                action = "Review and resolve or file dispute now"
            elif urgency == "critical":
                level = "critical"
                message = f"URGENT: {dl.label} for '{title}' expires in {days} days"
                action = "Act now — build proof packet and dispute letter"
            elif urgency == "urgent":
                level = "urgent"
                message = f"SOON: {dl.label} for '{title}' due in {days} days"
                action = "Prepare documentation and evidence"
            elif urgency == "soon":
                level = "soon"
                message = f"Reminder: {dl.label} for '{title}' due in {days} days"
                action = "Gather receipts and documentation"
            else:
                level = "normal"
                message = f"Note: {dl.label} for '{title}' due in {days} days"
                action = "No action needed yet"

            # Suggested actions based on deadline type
            suggestions = self._deadline_suggestions(dl.type, days, urgency)

            reminders.append({
                "item_id": dl.item_id,
                "item_title": title,
                "merchant": merchant,
                "deadline_type": dl.type,
                "label": dl.label,
                "due": dl.due,
                "due_date": time.strftime("%Y-%m-%d", time.localtime(dl.due)),
                "days_remaining": days,
                "urgency": urgency,
                "level": level,
                "message": message,
                "action": action,
                "suggestions": suggestions,
            })

        reminders.sort(key=lambda r: r["due"])
        return reminders

    def _deadline_suggestions(self, dl_type: str, days: int, urgency: str) -> list[str]:
        """Generate context-aware suggestions based on deadline type and urgency."""
        suggestions = []
        if dl_type == "return":
            suggestions.append("Package item with original packaging if possible")
            suggestions.append("Include proof of purchase in return package")
            if urgency in ("critical", "expired"):
                suggestions.append("Contact merchant immediately about late return")
        elif dl_type == "warranty":
            suggestions.append("Gather original receipt and warranty card")
            suggestions.append("Document the defect with photos")
            suggestions.append("Write a warranty claim letter")
        elif dl_type == "trial":
            suggestions.append("Cancel before trial ends to avoid charges")
            suggestions.append("Screenshot cancellation confirmation")
            if urgency in ("critical", "urgent"):
                suggestions.append("Cancel NOW — trial ending soon")
        elif dl_type == "cancel":
            suggestions.append("Cancel subscription through official channel")
            suggestions.append("Screenshot cancellation confirmation page")
            suggestions.append("Save cancellation email as evidence")
        elif dl_type == "chargeback":
            suggestions.append("Contact your bank's dispute department")
            suggestions.append("Build proof packet with all evidence")
            if urgency in ("critical", "expired"):
                suggestions.append("File chargeback immediately — window closing")
        elif dl_type == "claim":
            suggestions.append("File claim with supporting documentation")
            suggestions.append("Keep copies of all submitted materials")
        elif dl_type == "dispute":
            suggestions.append("Prepare dispute letter with evidence timeline")
            suggestions.append("Submit through appropriate channel (BBB, CFPB, court)")
        return suggestions


# ---------------------------------------------------------------------------
# Dashboard HTML — iPhone glassmorphic living control surface
# ---------------------------------------------------------------------------

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="ProofWallet">
<title>ProofWallet</title>
<style>
:root{
  --bg:#000;--bg2:#0a0a0f;
  --glass:rgba(255,255,255,0.06);
  --glass2:rgba(255,255,255,0.04);
  --glass3:rgba(255,255,255,0.08);
  --glass-bd:rgba(255,255,255,0.1);
  --glass-bd2:rgba(255,255,255,0.15);
  --tx:#f5f5f7;--tx2:#8e8e93;--tx3:#48484a;
  --or:#ff8c00;--or2:#ff6b00;--or3:#ffaa33;--or-glow:rgba(255,140,0,0.3);
  --gr:#30d158;--rd:#ff453a;--yl:#ffd60a;--bl:#0a84ff;--pr:#bf5af2;
  --mono:'SF Mono','JetBrains Mono','Fira Code',monospace;
  --sans:-apple-system,'SF Pro Display','SF Pro Text','Inter',system-ui,sans-serif;
  --safe-t:env(safe-area-inset-top,0px);
  --safe-b:env(safe-area-inset-bottom,0px);
}
*{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html,body{height:100%;overflow:hidden}
body{
  background:#000;
  color:var(--tx);
  font-family:var(--sans);
  font-size:15px;
  -webkit-font-smoothing:antialiased;
  user-select:none;
  -webkit-user-select:none;
}
::-webkit-scrollbar{display:none}

/* Ambient background */
.ambient{
  position:fixed;inset:0;z-index:0;overflow:hidden;
  background:radial-gradient(ellipse at top,#1a0a00 0%,#000 50%),
             radial-gradient(circle at 80% 20%,rgba(255,140,0,0.08) 0%,transparent 40%),
             radial-gradient(circle at 20% 80%,rgba(255,107,0,0.05) 0%,transparent 40%);
}
.ambient::before{
  content:'';position:absolute;inset:0;
  background:radial-gradient(circle at 50% 0%,rgba(255,140,0,0.12) 0%,transparent 60%);
  animation:breathe 8s ease-in-out infinite;
}
@keyframes breathe{0%,100%{opacity:0.6;transform:scale(1)}50%{opacity:1;transform:scale(1.05)}}

/* App shell — iPhone frame */
.app{
  position:relative;z-index:1;
  max-width:430px;margin:0 auto;
  height:100dvh;
  display:flex;flex-direction:column;
  padding-top:var(--safe-t);padding-bottom:var(--safe-b);
}

/* Header */
.hdr{
  padding:12px 20px 8px;
  display:flex;align-items:center;justify-content:space-between;
  flex-shrink:0;
}
.hdr-logo{
  font-size:24px;font-weight:800;
  background:linear-gradient(135deg,var(--or3),var(--or2));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  letter-spacing:-0.5px;
}
.hdr-tag{font-size:10px;color:var(--tx3);font-weight:600;letter-spacing:1px;text-transform:uppercase}
.hdr-stats{display:flex;gap:12px;align-items:center}
.hdr-pill{
  display:flex;align-items:center;gap:4px;
  font-size:11px;font-weight:600;color:var(--tx2);
  background:var(--glass);border:1px solid var(--glass-bd);
  padding:4px 10px;border-radius:20px;
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
}
.hdr-pill .v{color:var(--tx)}
.hdr-pill .dot{width:6px;height:6px;border-radius:50%;background:var(--gr);box-shadow:0 0 6px var(--gr);animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.3}}

/* Scrollable content */
.content{flex:1;overflow-y:auto;overflow-x:hidden;-webkit-overflow-scrolling:touch;padding:0 16px 100px}

/* Views */
.view{display:none;animation:fadeIn 0.3s ease}
.view.act{display:block}
@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}

/* Section */
.section{margin-bottom:20px}
.section-h{display:flex;align-items:center;justify-content:space-between;margin:20px 4px 10px}
.section-h h2{font-size:13px;font-weight:700;color:var(--tx2);text-transform:uppercase;letter-spacing:1px}
.section-h .link{font-size:13px;color:var(--or);font-weight:600}

/* Stat cards — glass */
.stat-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:12px}
.stat-card{
  background:var(--glass);
  border:1px solid var(--glass-bd);
  border-radius:16px;padding:16px;
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  position:relative;overflow:hidden;
  transition:transform 0.2s,border-color 0.2s;
}
.stat-card:active{transform:scale(0.96);border-color:var(--glass-bd2)}
.stat-card::before{
  content:'';position:absolute;top:0;left:0;right:0;height:1px;
  background:linear-gradient(90deg,transparent,rgba(255,255,255,0.15),transparent);
}
.stat-card .glyph{font-size:22px;margin-bottom:6px;display:block}
.stat-card .lbl{font-size:10px;font-weight:600;color:var(--tx3);text-transform:uppercase;letter-spacing:0.8px}
.stat-card .val{font-size:28px;font-weight:800;color:var(--tx);margin-top:2px;letter-spacing:-1px}
.stat-card .sub{font-size:11px;color:var(--tx2);margin-top:2px}
.stat-card.accent{border-color:rgba(255,140,0,0.2);background:linear-gradient(135deg,rgba(255,140,0,0.08),var(--glass))}
.stat-card.accent .glyph{color:var(--or)}

/* Item card — glass */
.item{
  background:var(--glass);
  border:1px solid var(--glass-bd);
  border-radius:14px;padding:14px 16px;
  display:flex;align-items:center;gap:12px;
  margin-bottom:8px;cursor:pointer;
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  transition:transform 0.15s,border-color 0.15s,background 0.15s;
  position:relative;overflow:hidden;
}
.item:active{transform:scale(0.97);background:var(--glass3)}
.item::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.1),transparent)}
.item .ig{font-size:20px;width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;background:rgba(255,140,0,0.1);flex-shrink:0}
.item .ib{flex:1;min-width:0}
.item .it{font-size:15px;font-weight:600;color:var(--tx);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.item .im{font-size:12px;color:var(--tx2);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.item .ia{font-size:15px;font-weight:700;color:var(--or3);flex-shrink:0}
.item .ist{font-size:9px;font-weight:700;text-transform:uppercase;padding:3px 8px;border-radius:6px;letter-spacing:0.5px;flex-shrink:0}
.st-active{background:rgba(48,209,88,0.15);color:var(--gr)}
.st-resolved{background:rgba(255,140,0,0.12);color:var(--or)}
.st-expired{background:rgba(255,69,58,0.12);color:var(--rd)}
.st-disputed{background:rgba(255,69,58,0.18);color:var(--rd)}

/* Deadline card — glass */
.dl{
  background:var(--glass);
  border:1px solid var(--glass-bd);
  border-radius:14px;padding:14px 16px;
  display:flex;align-items:center;gap:12px;
  margin-bottom:8px;
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  transition:transform 0.15s;
}
.dl:active{transform:scale(0.97)}
.dl .dg{font-size:18px;width:32px;text-align:center;flex-shrink:0}
.dl .db{flex:1;min-width:0}
.dl .dt{font-size:14px;font-weight:600;color:var(--tx);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dl .dd{font-size:11px;color:var(--tx2);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dl .ddays{font-size:12px;font-weight:700;padding:4px 10px;border-radius:8px;flex-shrink:0}
.dd-critical{background:rgba(255,69,58,0.15);color:var(--rd)}
.dd-urgent{background:rgba(255,214,10,0.12);color:var(--yl)}
.dd-soon{background:rgba(255,140,0,0.1);color:var(--or)}
.dd-normal{background:rgba(142,142,147,0.1);color:var(--tx2)}
.dd-expired{background:rgba(255,69,58,0.2);color:var(--rd)}

/* Reminder card — glass expanded */
.rem{
  background:var(--glass);
  border:1px solid var(--glass-bd);
  border-radius:14px;padding:16px;
  margin-bottom:10px;
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
}
.rem .rem-top{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.rem .rem-g{font-size:18px;width:32px;text-align:center;flex-shrink:0}
.rem .rem-t{font-size:14px;font-weight:600;flex:1;min-width:0;color:var(--tx)}
.rem .rem-days{font-size:11px;font-weight:700;padding:4px 10px;border-radius:8px;flex-shrink:0}
.rem .rem-msg{font-size:13px;color:var(--tx2);margin-bottom:6px}
.rem .rem-action{font-size:12px;color:var(--or3);font-weight:600;margin-bottom:6px}
.rem .rem-sug{font-size:12px;color:var(--tx2);line-height:1.6}
.rem .rem-sug div{color:var(--or3);margin-top:2px}
.rem .rem-btn{margin-top:10px}

/* Buttons */
.btn{
  background:var(--glass);border:1px solid var(--glass-bd);
  color:var(--tx);padding:10px 20px;border-radius:12px;
  font-size:14px;font-weight:600;cursor:pointer;
  transition:all 0.15s;font-family:var(--sans);
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
}
.btn:active{transform:scale(0.95)}
.btn-p{
  background:linear-gradient(135deg,var(--or),var(--or2));
  border:none;color:#fff;font-weight:700;
  box-shadow:0 4px 20px var(--or-glow);
}
.btn-p:active{transform:scale(0.95);box-shadow:0 2px 10px var(--or-glow)}

/* Bottom tab bar — glass */
.tabbar{
  position:fixed;bottom:0;left:50%;transform:translateX(-50%);
  width:100%;max-width:430px;
  background:rgba(0,0,0,0.6);
  border-top:1px solid var(--glass-bd);
  backdrop-filter:blur(40px);-webkit-backdrop-filter:blur(40px);
  display:flex;justify-content:space-around;align-items:center;
  padding:8px 0 calc(8px + var(--safe-b));
  z-index:100;
}
.tab{
  display:flex;flex-direction:column;align-items:center;gap:2px;
  padding:6px 14px;border-radius:10px;cursor:pointer;
  transition:all 0.15s;min-width:56px;
}
.tab:active{transform:scale(0.9)}
.tab .tg{font-size:20px;color:var(--tx3);transition:color 0.15s}
.tab .tl{font-size:9px;font-weight:600;color:var(--tx3);text-transform:uppercase;letter-spacing:0.5px}
.tab.act .tg{color:var(--or)}
.tab.act .tl{color:var(--or)}
.tab .badge{
  position:absolute;top:2px;right:8px;
  background:var(--rd);color:#fff;
  font-size:9px;font-weight:700;
  min-width:16px;height:16px;border-radius:8px;
  display:flex;align-items:center;justify-content:center;
  padding:0 4px;
}
.tab{position:relative}

/* FAB — floating capture button */
.fab{
  position:fixed;bottom:90px;left:50%;transform:translateX(-50%);
  width:56px;height:56px;border-radius:50%;
  background:linear-gradient(135deg,var(--or3),var(--or2));
  border:none;color:#fff;font-size:28px;
  cursor:pointer;z-index:99;
  box-shadow:0 8px 32px var(--or-glow);
  display:flex;align-items:center;justify-content:center;
  transition:transform 0.2s;
}
.fab:active{transform:translateX(-50%) scale(0.88)}

/* Modal — glass sheet */
.sheet-bg{
  position:fixed;inset:0;background:rgba(0,0,0,0.5);
  display:none;align-items:flex-end;justify-content:center;
  z-index:200;backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);
}
.sheet-bg.act{display:flex;animation:fadeIn 0.2s}
.sheet{
  background:rgba(20,20,25,0.85);
  border:1px solid var(--glass-bd);
  border-radius:24px 24px 0 0;
  padding:24px 20px calc(24px + var(--safe-b));
  max-width:430px;width:100%;max-height:85vh;overflow-y:auto;
  backdrop-filter:blur(40px);-webkit-backdrop-filter:blur(40px);
  animation:slideUp 0.3s cubic-bezier(0.32,0.72,0,1);
}
@keyframes slideUp{from{transform:translateY(100%)}to{transform:translateY(0)}}
.sheet-handle{
  width:36px;height:5px;border-radius:3px;
  background:var(--tx3);margin:0 auto 20px;
}
.sheet h3{font-size:20px;font-weight:700;color:var(--or);margin-bottom:20px}
.field{margin-bottom:16px}
.field label{display:block;font-size:11px;font-weight:600;color:var(--tx3);text-transform:uppercase;letter-spacing:0.8px;margin-bottom:6px}
.field input,.field select,.field textarea{
  width:100%;background:var(--glass2);
  border:1px solid var(--glass-bd);color:var(--tx);
  padding:12px 16px;border-radius:12px;
  font-size:16px;font-family:var(--sans);
  transition:border-color 0.15s;
}
.field input:focus,.field select:focus,.field textarea:focus{border-color:var(--or);outline:none}
.field textarea{min-height:80px;resize:none;font-family:var(--mono);font-size:14px}
.field select{appearance:none;-webkit-appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='8' viewBox='0 0 12 8'%3E%3Cpath fill='%238e8e93' d='M6 8L0 0h12z'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 16px center;padding-right:40px}
.sheet-btns{display:flex;gap:10px;margin-top:24px}
.sheet-btns .btn{flex:1;text-align:center;padding:14px}

/* Empty state */
.empty{text-align:center;padding:80px 20px;color:var(--tx3)}
.empty .g{font-size:40px;margin-bottom:12px;opacity:0.3}
.empty .t{font-size:15px;font-weight:500}

/* Receipt chain */
.rc-list{display:flex;flex-direction:column;gap:6px}
.rc{
  display:flex;gap:10px;align-items:center;
  padding:10px 14px;border-radius:10px;
  background:var(--glass);border:1px solid var(--glass-bd);
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
  font-size:12px;
}
.rc .rh{color:var(--or3);font-family:var(--mono);width:70px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rc .ra{color:var(--tx);flex:1;font-weight:600}
.rc .rt{color:var(--tx2);font-size:11px}
.rc .rr{color:var(--gr);font-size:10px}

/* Packet */
.pkt{
  background:var(--glass);border:1px solid var(--glass-bd);
  border-radius:14px;padding:16px;margin-bottom:8px;
  display:flex;align-items:center;gap:12px;
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
}
.pkt .pg{font-size:20px;color:var(--or3);width:36px;text-align:center}
.pkt .pb{flex:1}
.pkt .pt{font-size:14px;font-weight:600;color:var(--tx)}
.pkt .pm{font-size:11px;color:var(--tx2);margin-top:2px}

/* Tags */
.tag{display:inline-block;font-size:9px;font-weight:600;text-transform:uppercase;padding:2px 7px;border-radius:5px;background:var(--glass3);color:var(--tx2);margin-right:4px}
.tag-recurring{color:var(--or3);background:rgba(255,170,51,0.1)}
.tag-disputed{color:var(--rd);background:rgba(255,69,58,0.1)}
.tag-urgent{color:var(--yl);background:rgba(255,214,10,0.1)}
.tag-warranty{color:var(--gr);background:rgba(48,209,88,0.1)}

/* Verify badge */
.verify-badge{
  display:inline-flex;align-items:center;gap:6px;
  padding:6px 14px;border-radius:20px;
  font-size:12px;font-weight:600;
  margin-bottom:12px;
}
.verify-ok{background:rgba(48,209,88,0.12);color:var(--gr);border:1px solid rgba(48,209,88,0.2)}
.verify-bad{background:rgba(255,69,58,0.12);color:var(--rd);border:1px solid rgba(255,69,58,0.2)}

/* Item detail */
.detail-glyph{font-size:40px;text-align:center;margin:12px 0}
.detail-title{font-size:20px;font-weight:700;text-align:center;margin-bottom:16px}
.detail-meta{background:var(--glass2);border:1px solid var(--glass-bd);border-radius:12px;padding:16px;margin-bottom:16px;font-size:13px;line-height:1.8;color:var(--tx2)}
.detail-meta strong{color:var(--tx)}
.detail-section{margin-bottom:16px}
.detail-section h4{font-size:12px;font-weight:600;color:var(--tx3);text-transform:uppercase;letter-spacing:0.8px;margin-bottom:8px}
.detail-timeline{font-size:13px;color:var(--tx2);line-height:1.8}
.detail-timeline .te{padding:6px 0;border-bottom:1px solid var(--glass-bd)}
.detail-timeline .te:last-child{border:none}
</style>
</head>
<body>
<div class="ambient"></div>
<div class="app">
  <div class="hdr">
    <div>
      <div class="hdr-logo">ProofWallet</div>
      <div class="hdr-tag">Never lose the proof</div>
    </div>
    <div class="hdr-stats">
      <div class="hdr-pill"><span class="dot"></span><span class="v" id="hdr-items">0</span></div>
      <div class="hdr-pill"><span style="color:var(--or)">◆</span><span class="v" id="hdr-amount">$0</span></div>
    </div>
  </div>
  <div class="content">
    <!-- Overview -->
    <div class="view act" id="view-overview">
      <div class="stat-grid" id="stats-grid"></div>
      <div class="section">
        <div class="section-h"><h2>Recent</h2><span class="link" onclick="switchView('items')">All →</span></div>
        <div id="recent-items"></div>
      </div>
      <div class="section">
        <div class="section-h"><h2>Deadlines</h2><span class="link" onclick="switchView('deadlines')">All →</span></div>
        <div id="upcoming-deadlines"></div>
      </div>
    </div>
    <!-- Items -->
    <div class="view" id="view-items">
      <div class="section">
        <div class="section-h"><h2>All Items</h2></div>
        <div id="all-items"></div>
      </div>
    </div>
    <!-- Deadlines -->
    <div class="view" id="view-deadlines">
      <div class="section">
        <div class="section-h"><h2>Deadlines</h2></div>
        <div id="all-deadlines"></div>
      </div>
    </div>
    <!-- Reminders -->
    <div class="view" id="view-reminders">
      <div class="section">
        <div class="section-h"><h2>Reminders</h2></div>
        <div id="reminders-list"></div>
      </div>
    </div>
    <!-- Receipts -->
    <div class="view" id="view-receipts">
      <div class="section">
        <div class="section-h"><h2>Receipt Chain</h2><span class="link" onclick="verifyReceipts()">Verify</span></div>
        <div id="receipt-verify"></div>
        <div class="rc-list" id="receipt-list"></div>
      </div>
    </div>
    <!-- Packets -->
    <div class="view" id="view-packets">
      <div class="section">
        <div class="section-h"><h2>Proof Packets</h2></div>
        <div id="packet-list"></div>
      </div>
    </div>
  </div>
  <!-- Tab bar -->
  <div class="tabbar">
    <div class="tab act" data-view="overview"><span class="tg">◈</span><span class="tl">Home</span></div>
    <div class="tab" data-view="items"><span class="tg">◉</span><span class="tl">Items</span><span class="badge" id="badge-items" style="display:none">0</span></div>
    <div class="tab" data-view="reminders"><span class="tg">⟁</span><span class="tl">Alerts</span><span class="badge" id="badge-reminders" style="display:none">0</span></div>
    <div class="tab" data-view="receipts"><span class="tg">◆</span><span class="tl">Chain</span></div>
    <div class="tab" data-view="packets"><span class="tg">⤓</span><span class="tl">Packets</span></div>
  </div>
  <!-- FAB -->
  <button class="fab" onclick="openCapture()">+</button>
</div>
<!-- Capture sheet -->
<div class="sheet-bg" id="sheet-capture">
  <div class="sheet">
    <div class="sheet-handle"></div>
    <h3>Capture Evidence</h3>
    <div class="field"><label>Title</label><input id="cap-title" placeholder="Netflix, Amazon order…"></div>
    <div class="field"><label>Type</label><select id="cap-type">
      <option value="">Auto-detect</option>
      <option value="receipt">Receipt</option>
      <option value="warranty">Warranty</option>
      <option value="subscription">Subscription</option>
      <option value="cancellation">Cancellation</option>
      <option value="refund">Refund</option>
      <option value="chargeback">Chargeback</option>
      <option value="landlord">Landlord</option>
      <option value="repair">Repair</option>
      <option value="medical">Medical</option>
      <option value="insurance">Insurance</option>
      <option value="employment">Employment</option>
      <option value="screenshot">Screenshot</option>
      <option value="email">Email</option>
      <option value="contract">Contract</option>
      <option value="delivery">Delivery</option>
      <option value="scam_evidence">Scam Evidence</option>
      <option value="invoice">Invoice</option>
    </select></div>
    <div class="field"><label>Text / Email Content</label><textarea id="cap-text" placeholder="Paste receipt text, email, or message…"></textarea></div>
    <div class="field"><label>Merchant</label><input id="cap-merchant" placeholder="Amazon, Netflix…"></div>
    <div class="field"><label>Amount</label><input id="cap-amount" type="number" step="0.01" placeholder="0.00"></div>
    <div class="field"><label>Notes</label><input id="cap-notes" placeholder="Additional context…"></div>
    <div class="sheet-btns">
      <button class="btn" onclick="closeSheet('sheet-capture')">Cancel</button>
      <button class="btn btn-p" onclick="submitCapture()">Capture</button>
    </div>
  </div>
</div>
<!-- Item detail sheet -->
<div class="sheet-bg" id="sheet-item">
  <div class="sheet" id="sheet-item-content"></div>
</div>
<!-- Packet builder sheet -->
<div class="sheet-bg" id="sheet-packet">
  <div class="sheet">
    <div class="sheet-handle"></div>
    <h3>Prove It</h3>
    <div class="field"><label>Item</label><input id="pkt-item-id" readonly></div>
    <div class="field"><label>Letter Type</label><select id="pkt-letter">
      <option value="">No letter</option>
      <option value="refund">Refund Request</option>
      <option value="cancellation">Cancellation</option>
      <option value="chargeback">Chargeback Dispute</option>
      <option value="warranty">Warranty Claim</option>
      <option value="dispute">General Dispute</option>
      <option value="small_claims">Small Claims</option>
      <option value="identity_theft">Identity Theft</option>
    </select></div>
    <div class="field"><label>Your Name</label><input id="pkt-name" placeholder="Your name"></div>
    <div class="field"><label>Contact</label><input id="pkt-contact" placeholder="Phone / Email"></div>
    <div class="field"><label>Reason</label><textarea id="pkt-reason" placeholder="Describe the issue…"></textarea></div>
    <div class="sheet-btns">
      <button class="btn" onclick="closeSheet('sheet-packet')">Cancel</button>
      <button class="btn btn-p" onclick="buildPacket()">Build Packet</button>
    </div>
  </div>
</div>
<script>
const GLYPHS={receipt:'◉',warranty:'◆',subscription:'⌁',cancellation:'✕',refund:'↩',chargeback:'⟁',landlord:'🏠',repair:'🔧',medical:'⚕',insurance:'🛡',employment:'💼',screenshot:'◍',email:'✉',contract:'□',delivery:'⤓',scam_evidence:'⚠',invoice:'🧾',other:'◇'};
const DLG={critical:'⟁',urgent:'▲',soon:'◇',normal:'◌',expired:'✕'};
const DLC={expired:'var(--rd)',critical:'var(--rd)',urgent:'var(--yl)',soon:'var(--or)',normal:'var(--tx2)'};

async function api(p,o){const r=await fetch(p,o);if(!r.ok)throw new Error(r.status);return r}
function fmtDate(ts){if(!ts)return'—';return new Date(ts*1000).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'})}
function fmtMoney(v){return'$'+(v||0).toFixed(2)}
function esc(s){return String(s||'').replace(/[<>&"]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;','"':'&quot;'}[c]))}

function switchView(v){
  document.querySelectorAll('.view').forEach(e=>e.classList.remove('act'));
  document.querySelectorAll('.tab').forEach(e=>e.classList.remove('act'));
  document.getElementById('view-'+v).classList.add('act');
  const t=document.querySelector(`.tab[data-view="${v}"]`);if(t)t.classList.add('act');
  document.querySelector('.content').scrollTop=0;
}
document.querySelectorAll('.tab[data-view]').forEach(e=>e.addEventListener('click',()=>switchView(e.dataset.view)));

function openCapture(){document.getElementById('sheet-capture').classList.add('act')}
function closeSheet(id){document.getElementById(id).classList.remove('act')}
document.querySelectorAll('.sheet-bg').forEach(e=>e.addEventListener('click',e=>{if(e.target===e.currentTarget)e.currentTarget.classList.remove('act')}));

async function submitCapture(){
  const fd=new FormData();
  fd.append('title',document.getElementById('cap-title').value);
  fd.append('type',document.getElementById('cap-type').value);
  fd.append('text',document.getElementById('cap-text').value);
  fd.append('merchant',document.getElementById('cap-merchant').value);
  fd.append('amount',document.getElementById('cap-amount').value||'0');
  fd.append('notes',document.getElementById('cap-notes').value);
  try{
    await api('/api/capture',{method:'POST',body:fd});
    closeSheet('sheet-capture');
    ['cap-title','cap-text','cap-merchant','cap-amount','cap-notes'].forEach(id=>document.getElementById(id).value='');
    loadAll();
  }catch(e){alert('Capture failed: '+e.message)}
}

function itemHTML(i){
  const g=GLYPHS[i.type]||'◇';
  return `<div class="item" onclick="showItem('${i.id}')">
    <div class="ig">${g}</div>
    <div class="ib"><div class="it">${esc(i.title)}</div>
    <div class="im">${esc(i.merchant)||'—'} · ${fmtDate(i.date)}${i.tags&&i.tags.length?' · '+i.tags.map(t=>`<span class="tag tag-${t}">${t}</span>`).join(''):''}</div></div>
    ${i.amount?`<div class="ia">${fmtMoney(i.amount)}</div>`:''}
    <div class="ist st-${i.status}">${i.status}</div>
  </div>`
}

function dlHTML(d){
  const g=DLG[d.urgency]||'◌',c=DLC[d.urgency]||'var(--tx2)';
  const ds=d.days_remaining>=0?`${d.days_remaining}d`:`${Math.abs(d.days_remaining)}d`;
  return `<div class="dl" onclick="showItem('${d.item_id}')">
    <div class="dg" style="color:${c}">${g}</div>
    <div class="db"><div class="dt">${esc(d.item_title)}</div><div class="dd">${esc(d.type)}: ${esc(d.label)} · ${fmtDate(d.due)}</div></div>
    <div class="ddays dd-${d.urgency}">${ds}</div>
  </div>`
}

async function showItem(id){
  try{
    const r=await api('/api/items/'+id);
    const i=await r.json();
    const g=GLYPHS[i.type]||'◇';
    document.getElementById('sheet-item-content').innerHTML=`
      <div class="sheet-handle"></div>
      <div class="detail-glyph">${g}</div>
      <div class="detail-title">${esc(i.title)}</div>
      <div class="detail-meta">
        <strong>Merchant:</strong> ${esc(i.merchant)||'—'}<br>
        <strong>Amount:</strong> ${i.amount?fmtMoney(i.amount):'—'}<br>
        <strong>Date:</strong> ${fmtDate(i.date)}<br>
        <strong>Status:</strong> <span class="ist st-${i.status}" style="display:inline">${i.status}</span><br>
        <strong>Tags:</strong> ${(i.tags||[]).map(t=>`<span class="tag tag-${t}">${t}</span>`).join(' ')||'—'}<br>
        <strong>Proof:</strong> <span style="font-family:var(--mono);font-size:11px">${(i.proof_hash||'').slice(0,24)}…</span><br>
        <strong>Receipt:</strong> <span style="font-family:var(--mono);font-size:11px">${(i.receipt_hash||'').slice(0,24)}…</span>
      </div>
      ${i.notes?`<div class="detail-section"><h4>Notes</h4><div style="font-size:14px;color:var(--tx2)">${esc(i.notes)}</div></div>`:''}
      ${i.deadlines&&i.deadlines.length?`<div class="detail-section"><h4>Deadlines</h4>${i.deadlines.map(d=>`<div style="font-size:13px;color:var(--tx2);padding:4px 0">⧖ ${esc(d.label)} — ${fmtDate(d.due)}</div>`).join('')}</div>`:''}
      ${i.timeline&&i.timeline.length?`<div class="detail-section"><h4>Timeline</h4><div class="detail-timeline">${i.timeline.map(t=>`<div class="te"><strong>${esc(t.ts_label)}</strong> — ${esc(t.action)}</div>`).join('')}</div></div>`:''}
      <div class="sheet-btns">
        <button class="btn" onclick="closeSheet('sheet-item')">Close</button>
        <button class="btn btn-p" onclick="openPacket('${i.id}')">Prove It</button>
      </div>`;
    document.getElementById('sheet-item').classList.add('act');
  }catch(e){alert('Failed: '+e.message)}
}

function openPacket(id){
  closeSheet('sheet-item');
  document.getElementById('pkt-item-id').value=id;
  document.getElementById('sheet-packet').classList.add('act');
}

async function buildPacket(){
  const id=document.getElementById('pkt-item-id').value;
  const fd=new FormData();
  fd.append('item_ids',id);
  fd.append('letter_type',document.getElementById('pkt-letter').value);
  fd.append('fmt','zip');
  try{
    const r=await fetch('/api/packet',{method:'POST',body:fd});
    if(!r.ok)throw new Error(r.status);
    const blob=await r.blob();
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');a.href=url;a.download='proof_packet.zip';a.click();
    URL.revokeObjectURL(url);
    closeSheet('sheet-packet');
  }catch(e){alert('Packet failed: '+e.message)}
}

async function verifyReceipts(){
  try{
    const r=await api('/api/receipts/verify');
    const d=await r.json();
    document.getElementById('receipt-verify').innerHTML=d.valid?
      '<div class="verify-badge verify-ok">✓ Chain intact</div>':
      '<div class="verify-badge verify-bad">✗ Broken: '+d.errors.join('; ')+'</div>';
  }catch(e){alert('Verify failed: '+e.message)}
}

async function loadAll(){
  try{
    const r=await api('/api/dashboard');
    const d=await r.json(),s=d.stats;
    document.getElementById('hdr-items').textContent=s.total_items;
    document.getElementById('hdr-amount').textContent=fmtMoney(s.total_amount);
    // Stats
    document.getElementById('stats-grid').innerHTML=[
      {g:'◉',l:'Items',v:s.total_items,accent:true},
      {g:'$',l:'Value',v:fmtMoney(s.total_amount)},
      {g:'⧖',l:'Deadlines',v:s.active_deadlines,sub:s.critical_deadlines+' critical'},
      {g:'⟁',l:'Expired',v:s.expired_deadlines},
      {g:'⤓',l:'Packets',v:s.packets_built},
      {g:'◆',l:'Chain',v:s.receipt_chain_verified?'✓':'✗'},
    ].map(c=>`<div class="stat-card ${c.accent?'accent':''}"><span class="glyph" style="color:${c.accent?'var(--or)':'var(--tx2)'}">${c.g}</span><div class="lbl">${c.l}</div><div class="val">${c.v}</div>${c.sub?`<div class="sub">${c.sub}</div>`:''}</div>`).join('');
    // Recent
    document.getElementById('recent-items').innerHTML=d.recent_items.length?
      d.recent_items.map(itemHTML).join(''):
      '<div class="empty"><div class="g">◇</div><div class="t">No items yet. Tap + to capture.</div></div>';
    // Deadlines
    document.getElementById('upcoming-deadlines').innerHTML=d.upcoming_deadlines.length?
      d.upcoming_deadlines.map(dlHTML).join(''):
      '<div class="empty"><div class="g">⧖</div><div class="t">No deadlines.</div></div>';
  }catch(e){console.error('Dashboard:',e)}
  // Items
  try{
    const r=await api('/api/items');const items=await r.json();
    document.getElementById('all-items').innerHTML=items.length?
      items.map(itemHTML).join(''):
      '<div class="empty"><div class="g">◉</div><div class="t">No items in wallet.</div></div>';
  }catch(e){console.error('Items:',e)}
  // Deadlines all
  try{
    const r=await api('/api/deadlines');const dls=await r.json();
    document.getElementById('all-deadlines').innerHTML=dls.length?
      dls.map(dlHTML).join(''):
      '<div class="empty"><div class="g">⧖</div><div class="t">No deadlines tracked.</div></div>';
  }catch(e){console.error('Deadlines:',e)}
  // Reminders
  try{
    const r=await api('/api/reminders');const rems=await r.json();
    const badge=document.getElementById('badge-reminders');
    if(rems.length){badge.textContent=rems.length;badge.style.display='flex'}else{badge.style.display='none'}
    document.getElementById('reminders-list').innerHTML=rems.length?
      rems.map(r=>{
        const g=DLG[r.level]||'◌',c=DLC[r.level]||'var(--tx2)';
        return `<div class="rem">
          <div class="rem-top"><span class="rem-g" style="color:${c}">${g}</span>
          <span class="rem-t">${esc(r.item_title)}</span>
          <span class="rem-days dd-${r.urgency}">${r.days_remaining>=0?r.days_remaining+'d':Math.abs(r.days_remaining)+'d'}</span></div>
          <div class="rem-msg">${esc(r.message)}</div>
          <div class="rem-action">${esc(r.action)}</div>
          ${r.suggestions&&r.suggestions.length?`<div class="rem-sug">${r.suggestions.map(s=>`<div>→ ${esc(s)}</div>`).join('')}</div>`:''}
          <div class="rem-btn"><button class="btn" onclick="showItem('${r.item_id}')">View Item</button></div>
        </div>`
      }).join(''):
      '<div class="empty"><div class="g">◇</div><div class="t">All clear. No reminders.</div></div>';
  }catch(e){console.error('Reminders:',e)}
  // Receipts
  try{
    const r=await api('/api/receipts');const recs=await r.json();
    document.getElementById('receipt-list').innerHTML=recs.length?
      recs.slice(-30).reverse().map(r=>`<div class="rc"><span class="rh">${r.hash.slice(0,10)}</span><span class="ra">${esc(r.action)}</span><span class="rt">${fmtDate(r.ts)}</span><span class="rr">◆</span></div>`).join(''):
      '<div class="empty"><div class="g">◆</div><div class="t">No receipts yet.</div></div>';
  }catch(e){console.error('Receipts:',e)}
  // Packets
  try{
    const r=await api('/api/packets');const pkts=await r.json();
    document.getElementById('packet-list').innerHTML=pkts.length?
      pkts.map(p=>`<div class="pkt"><div class="pg">⤓</div><div class="pb"><div class="pt">Packet ${p.id.slice(0,12)}</div><div class="pm">${fmtDate(p.created_at)} · ${(JSON.parse(p.item_ids||'[]')).length} items</div></div></div>`).join(''):
      '<div class="empty"><div class="g">⤓</div><div class="t">No packets built yet.</div></div>';
  }catch(e){console.error('Packets:',e)}
}

loadAll();
setInterval(loadAll,15000);
</script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# FastAPI server
# ---------------------------------------------------------------------------


def create_server():
    """Create FastAPI server for ProofWallet."""
    from fastapi import FastAPI, UploadFile, File, Form, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import Response, JSONResponse, HTMLResponse
    from typing import Optional as TypingOptional
    import uvicorn

    app = FastAPI(title="ProofWallet", version=VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    wallet = ProofWallet()

    @app.get("/", response_class=HTMLResponse)
    async def dashboard_html():
        return DASHBOARD_HTML

    @app.get("/api/health")
    async def health():
        return {"status": "alive", "version": VERSION, "service": "proofwallet"}

    @app.get("/api/dashboard")
    async def dashboard():
        return wallet.get_dashboard()

    @app.get("/api/stats")
    async def stats():
        return wallet.get_statistics()

    @app.get("/api/items")
    async def list_items(type: str = "", status: str = ""):
        items = wallet.list_items(type, status)
        return [
            {
                "id": i.id, "type": i.type, "title": i.title,
                "merchant": i.merchant, "amount": i.amount,
                "currency": i.currency, "date": i.date,
                "captured_at": i.captured_at, "status": i.status,
                "tags": i.tags, "has_file": bool(i.file_path),
                "file_type": i.file_type, "file_size": i.file_size,
                "deadlines": i.deadlines, "notes": i.notes,
            }
            for i in items
        ]

    @app.get("/api/items/{item_id}")
    async def get_item(item_id: str):
        item = wallet.get_item(item_id)
        if not item:
            raise HTTPException(404, "Item not found")
        return item.to_dict()

    @app.post("/api/capture")
    async def capture(
        title: str = Form(""),
        type: str = Form(""),
        text: str = Form(""),
        merchant: str = Form(""),
        amount: float = Form(0.0),
        currency: str = Form("USD"),
        notes: str = Form(""),
        file: TypingOptional[UploadFile] = File(None),
    ):
        file_path = ""
        if file:
            file_path = str(PW_FILES / f"upload_{int(time.time())}_{file.filename}")
            with open(file_path, "wb") as f:
                f.write(await file.read())

        item = wallet.capture(
            title=title, item_type=type, text=text, file_path=file_path,
            merchant=merchant, amount=amount, currency=currency, notes=notes,
        )
        return item.to_dict()

    @app.delete("/api/items/{item_id}")
    async def delete_item(item_id: str):
        if not wallet.delete_item(item_id):
            raise HTTPException(404, "Item not found")
        return {"deleted": True}

    @app.get("/api/deadlines")
    async def get_deadlines(include_expired: bool = True):
        deadlines = wallet.get_deadlines(include_expired)
        result = []
        for dl in deadlines:
            item = wallet.get_item(dl.item_id)
            result.append({
                "item_id": dl.item_id,
                "item_title": item.title if item else "Unknown",
                "type": dl.type,
                "label": dl.label,
                "due": dl.due,
                "days_remaining": dl.days_remaining,
                "urgency": dl.urgency,
                "resolved": dl.resolved,
            })
        return result

    @app.post("/api/deadlines/{item_id}/resolve")
    async def resolve_deadline(item_id: str, type: str = ""):
        wallet.resolve_deadline(item_id, type)
        return {"resolved": True}

    @app.get("/api/reminders")
    async def get_reminders():
        return wallet.get_reminders()

    @app.post("/api/packet")
    async def build_packet(
        item_ids: str = Form(...),
        letter_type: str = Form(""),
        fmt: str = Form("zip"),
    ):
        ids = item_ids.split(",")
        try:
            packet, data = wallet.build_packet(ids, letter_type, fmt=fmt)
            media_type = "application/zip" if fmt == "zip" else "application/json"
            ext = "zip" if fmt == "zip" else "json"
            return Response(
                content=data,
                media_type=media_type,
                headers={
                    "Content-Disposition": f"attachment; filename=proof_packet_{packet.packet_id}.{ext}"
                }
            )
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/letter")
    async def generate_letter(
        item_id: str = Form(...),
        letter_type: str = Form(...),
        name: str = Form("[Your Name]"),
        contact: str = Form("[Your Phone/Email]"),
        reason: str = Form("[Describe the issue]"),
    ):
        try:
            letter = wallet.generate_letter(
                item_id, letter_type,
                name=name, contact=contact, reason=reason,
            )
            return Response(
                content=letter,
                media_type="text/plain",
                headers={
                    "Content-Disposition": f"attachment; filename=letter_{letter_type}_{item_id}.txt"
                }
            )
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.get("/api/receipts")
    async def receipts():
        return wallet.receipts.list_all()

    @app.get("/api/receipts/verify")
    async def verify_receipts():
        valid, errors = wallet.receipts.verify()
        return {"valid": valid, "errors": errors}

    @app.get("/api/packets")
    async def list_packets():
        return wallet.db.list_packets()

    return app, uvicorn


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def cmd_capture(args):
    wallet = ProofWallet()
    file_path = args.file if args.file else ""
    item = wallet.capture(
        title=args.title or "",
        item_type=args.type or "",
        text=args.text or "",
        file_path=file_path,
        merchant=args.merchant or "",
        amount=args.amount or 0.0,
        currency=args.currency or "USD",
        notes=args.notes or "",
    )
    print(f"◆ Captured: {item.id}")
    print(f"  Type: {item.type}")
    print(f"  Title: {item.title}")
    print(f"  Merchant: {item.merchant or '—'}")
    print(f"  Amount: {item.currency} {item.amount:.2f}" if item.amount else "  Amount: —")
    print(f"  Date: {time.strftime('%Y-%m-%d', time.localtime(item.date))}" if item.date else "  Date: —")
    print(f"  Tags: {', '.join(item.tags) if item.tags else '—'}")
    if item.deadlines:
        print(f"  Deadlines:")
        for dl in item.deadlines:
            print(f"    ⧖ {dl['label']} — due {time.strftime('%Y-%m-%d', time.localtime(dl['due']))}")
    print(f"  Receipt: {item.receipt_hash[:16]}…")


def cmd_list(args):
    wallet = ProofWallet()
    items = wallet.list_items(args.type or "", args.status or "")
    if not items:
        print("No items in wallet.")
        return
    print(f"◈ ProofWallet — {len(items)} items\n")
    for item in items:
        glyph = {"receipt": "◉", "warranty": "◆", "subscription": "⌁", "cancellation": "✕",
                 "refund": "↩", "chargeback": "⟁", "email": "✉", "screenshot": "◍",
                 "contract": "□", "delivery": "⤓", "scam_evidence": "⚠"}.get(item.type, "◇")
        date_str = time.strftime("%Y-%m-%d", time.localtime(item.date)) if item.date else "—"
        amount_str = f"${item.amount:.2f}" if item.amount else "—"
        status_glyph = {"active": "◉", "resolved": "◆", "expired": "⧖", "disputed": "⟁"}.get(item.status, "◌")
        print(f"  {glyph} [{item.id[:8]}] {item.title}")
        print(f"    {item.merchant or '—'} · {date_str} · {amount_str} · {status_glyph} {item.status}")
        if item.tags:
            print(f"    tags: {', '.join(item.tags)}")


def cmd_item(args):
    wallet = ProofWallet()
    item = wallet.get_item(args.id)
    if not item:
        print(f"Item not found: {args.id}")
        return
    print(f"◈ {item.id}")
    print(f"  Type: {item.type}")
    print(f"  Title: {item.title}")
    print(f"  Merchant: {item.merchant or '—'}")
    print(f"  Amount: {item.currency} {item.amount:.2f}" if item.amount else "  Amount: —")
    print(f"  Date: {time.strftime('%Y-%m-%d %H:%M', time.localtime(item.date))}" if item.date else "  Date: —")
    print(f"  Captured: {time.strftime('%Y-%m-%d %H:%M', time.localtime(item.captured_at))}")
    print(f"  Status: {item.status}")
    print(f"  Tags: {', '.join(item.tags) if item.tags else '—'}")
    print(f"  File: {item.file_path or '—'} ({item.file_size} bytes)" if item.file_path else "  File: —")
    print(f"  File hash: {item.file_hash[:32]}…" if item.file_hash else "  File hash: —")
    print(f"  Proof hash: {item.proof_hash[:32]}…")
    print(f"  Receipt: {item.receipt_hash[:32]}…")
    if item.notes:
        print(f"  Notes: {item.notes}")
    if item.deadlines:
        print(f"  Deadlines:")
        for dl in item.deadlines:
            due_str = time.strftime('%Y-%m-%d', time.localtime(dl['due']))
            print(f"    ⧖ {dl['label']} — due {due_str}")
    if item.timeline:
        print(f"  Timeline:")
        for event in item.timeline:
            print(f"    {event.get('ts_label', '—')}: {event.get('action', '—')}")


def cmd_packet(args):
    wallet = ProofWallet()
    item_ids = args.ids.split(",")
    letter_type = args.letter or ""
    fmt = args.format or "zip"
    try:
        packet, data = wallet.build_packet(item_ids, letter_type, fmt=fmt)
    except ValueError as e:
        print(f"Error: {e}")
        return
    output = args.output or f"proof_packet_{packet.packet_id}.{fmt}"
    Path(output).write_bytes(data)
    print(f"◆ Proof packet: {output}")
    print(f"  Packet ID: {packet.packet_id}")
    print(f"  Items: {len(packet.item_ids)}")
    print(f"  Merkle root: {packet.merkle_root[:32]}…")
    print(f"  Total amount: ${packet.summary.get('total_amount', 0):.2f}")
    if packet.dispute_letter:
        print(f"  Letter: {packet.letter_type}")
    print(f"  Size: {len(data)} bytes")


def cmd_deadlines(args):
    wallet = ProofWallet()
    deadlines = wallet.get_deadlines(include_expired=not args.active_only)
    if not deadlines:
        print("No deadlines.")
        return
    print(f"⧖ Deadlines — {len(deadlines)} active\n")
    for dl in deadlines:
        item = wallet.get_item(dl.item_id)
        title = item.title if item else "Unknown"
        urgency_glyph = {"critical": "⟁", "urgent": "▲", "soon": "◇", "normal": "◌", "expired": "✕"}.get(dl.urgency, "◌")
        days = dl.days_remaining
        days_str = f"{days}d remaining" if days >= 0 else f"{abs(days)}d OVERDUE"
        print(f"  {urgency_glyph} [{dl.item_id[:8]}] {title}")
        print(f"    {dl.type}: {dl.label}")
        print(f"    Due: {time.strftime('%Y-%m-%d', time.localtime(dl.due))} — {days_str}")


def cmd_reminders(args):
    wallet = ProofWallet()
    reminders = wallet.get_reminders()
    if not reminders:
        print("No reminders. All deadlines resolved.")
        return
    print(f"⧖ ProofWallet Reminders — {len(reminders)} pending\n")
    for r in reminders:
        glyph = {"expired": "✕", "critical": "⟁", "urgent": "▲", "soon": "◇", "normal": "◌"}.get(r["level"], "◌")
        color = {"expired": "red", "critical": "red", "urgent": "yellow", "soon": "orange", "normal": "gray"}.get(r["level"], "gray")
        print(f"  {glyph} [{r['item_id'][:8]}] {r['item_title']}")
        print(f"    {r['message']}")
        print(f"    Action: {r['action']}")
        if r["suggestions"]:
            for s in r["suggestions"]:
                print(f"    → {s}")
        print()


def cmd_letter(args):
    wallet = ProofWallet()
    try:
        letter = wallet.generate_letter(
            args.id, args.type,
            name=args.name or "[Your Name]",
            contact=args.contact or "[Your Phone/Email]",
            reason=args.reason or "[Describe the issue]",
        )
    except ValueError as e:
        print(f"Error: {e}")
        return
    if args.output:
        Path(args.output).write_text(letter)
        print(f"◆ Letter written: {args.output}")
    else:
        print(letter)


def cmd_stats(args):
    wallet = ProofWallet()
    stats = wallet.get_statistics()
    print(f"◈ ProofWallet Statistics\n")
    print(f"  Total items: {stats['total_items']}")
    print(f"  Total amount: ${stats['total_amount']:.2f}")
    print(f"  Active deadlines: {stats['active_deadlines']}")
    print(f"  Critical deadlines: {stats['critical_deadlines']}")
    print(f"  Expired deadlines: {stats['expired_deadlines']}")
    print(f"  Packets built: {stats['packets_built']}")
    print(f"  Receipt chain: {'✓ verified' if stats['receipt_chain_verified'] else '✗ broken'}")
    print(f"\n  Type breakdown:")
    for t, count in sorted(stats["type_breakdown"].items()):
        print(f"    {t}: {count}")


def cmd_serve(args):
    app, uvicorn = create_server()
    print(f"◈ ProofWallet serving on port {args.port}")
    uvicorn.run(app, host="0.0.0.0", port=args.port)


def cmd_receipts(args):
    wallet = ProofWallet()
    if args.verify:
        valid, errors = wallet.receipts.verify()
        if valid:
            print("✓ Receipt chain intact")
        else:
            print("✗ Receipt chain broken:")
            for e in errors:
                print(f"  {e}")
        return
    receipts = wallet.receipts.list_all()
    if not receipts:
        print("No receipts.")
        return
    print(f"◆ Receipt chain — {len(receipts)} entries\n")
    for r in receipts[-20:]:
        ts_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(r['ts']))
        print(f"  [{ts_str}] {r['action']:20s} {r['item_id'][:12] if r['item_id'] else '—':12s} {r['hash'][:16]}…")


def main():
    parser = argparse.ArgumentParser(
        prog="proofwallet",
        description="ProofWallet — Never lose the proof. Life proof wallet.",
    )
    sub = parser.add_subparsers(dest="command")

    # capture
    p_cap = sub.add_parser("capture", help="Capture a new evidence item")
    p_cap.add_argument("--title", default="")
    p_cap.add_argument("--type", default="")
    p_cap.add_argument("--text", default="")
    p_cap.add_argument("--file", default="")
    p_cap.add_argument("--merchant", default="")
    p_cap.add_argument("--amount", type=float, default=0.0)
    p_cap.add_argument("--currency", default="USD")
    p_cap.add_argument("--notes", default="")
    p_cap.set_defaults(func=cmd_capture)

    # list
    p_list = sub.add_parser("list", help="List all items")
    p_list.add_argument("--type", default="")
    p_list.add_argument("--status", default="")
    p_list.set_defaults(func=cmd_list)

    # item
    p_item = sub.add_parser("item", help="Show item details")
    p_item.add_argument("id")
    p_item.set_defaults(func=cmd_item)

    # packet
    p_pkt = sub.add_parser("packet", help="Build proof packet")
    p_pkt.add_argument("ids", help="Comma-separated item IDs")
    p_pkt.add_argument("--letter", default="", help="Letter type: refund, cancellation, chargeback, warranty, dispute, small_claims, identity_theft")
    p_pkt.add_argument("--format", default="zip", choices=["zip", "json"])
    p_pkt.add_argument("--output", default="")
    p_pkt.set_defaults(func=cmd_packet)

    # deadlines
    p_dl = sub.add_parser("deadlines", help="Show deadlines")
    p_dl.add_argument("--active-only", action="store_true")
    p_dl.set_defaults(func=cmd_deadlines)

    # reminders
    p_rem = sub.add_parser("reminders", help="Show deadline reminders with suggested actions")
    p_rem.set_defaults(func=cmd_reminders)

    # letter
    p_letter = sub.add_parser("letter", help="Generate dispute letter")
    p_letter.add_argument("id")
    p_letter.add_argument("--type", default="dispute", choices=[t.value for t in LetterType])
    p_letter.add_argument("--name", default="")
    p_letter.add_argument("--contact", default="")
    p_letter.add_argument("--reason", default="")
    p_letter.add_argument("--output", default="")
    p_letter.set_defaults(func=cmd_letter)

    # stats
    p_stats = sub.add_parser("stats", help="Show statistics")
    p_stats.set_defaults(func=cmd_stats)

    # receipts
    p_rec = sub.add_parser("receipts", help="Show or verify receipt chain")
    p_rec.add_argument("--verify", action="store_true")
    p_rec.set_defaults(func=cmd_receipts)

    # serve
    p_serve = sub.add_parser("serve", help="Start API server")
    p_serve.add_argument("--port", type=int, default=7860)
    p_serve.set_defaults(func=cmd_serve)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return

    args.func(args)


if __name__ == "__main__":
    main()
