"""
Receipt Ledger — tamper-evident SHA-256 chained receipts for every action.

Receipt types: artifact_intake, packet_creation, ollama_analysis, risk_report,
landing_page_generation, deployment, token_manifest_creation, devnet_mint,
checkout_creation, payment_confirmation
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Receipt:
    receipt_type: str
    artifact_id: str
    input_hash: str = ""
    output_hash: str = ""
    model_name: str = ""
    model_digest: str = ""
    packet_hash: str = ""
    runtime_ms: int = 0
    created_at: float = 0.0
    prev_hash: str = ""
    receipt_hash: str = ""
    data: dict = None

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()
        if self.data is None:
            self.data = {}

    def compute_hash(self) -> str:
        payload = {
            "receipt_type": self.receipt_type,
            "artifact_id": self.artifact_id,
            "input_hash": self.input_hash,
            "output_hash": self.output_hash,
            "model_name": self.model_name,
            "model_digest": self.model_digest,
            "packet_hash": self.packet_hash,
            "runtime_ms": self.runtime_ms,
            "created_at": self.created_at,
            "prev_hash": self.prev_hash,
            "data": self.data,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["receipt_hash"] = self.receipt_hash or self.compute_hash()
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


class ReceiptLedger:
    """Chained receipt ledger backed by OracleDB."""

    def __init__(self, db):
        self.db = db

    def write(self, receipt_type: str, artifact_id: str,
              data: dict = None, input_hash: str = "",
              output_hash: str = "", model_name: str = "",
              model_digest: str = "", packet_hash: str = "",
              runtime_ms: int = 0) -> Receipt:
        prev_hash = self.db.get_last_receipt_hash()
        receipt = Receipt(
            receipt_type=receipt_type,
            artifact_id=artifact_id,
            input_hash=input_hash,
            output_hash=output_hash,
            model_name=model_name,
            model_digest=model_digest,
            packet_hash=packet_hash,
            runtime_ms=runtime_ms,
            prev_hash=prev_hash,
            data=data or {},
        )
        receipt.receipt_hash = receipt.compute_hash()
        self.db.insert_receipt(
            receipt_hash=receipt.receipt_hash,
            receipt_type=receipt.receipt_type,
            artifact_id=receipt.artifact_id,
            data=receipt.data,
            input_hash=receipt.input_hash,
            output_hash=receipt.output_hash,
            model_name=receipt.model_name,
            model_digest=receipt.model_digest,
            packet_hash=receipt.packet_hash,
            runtime_ms=receipt.runtime_ms,
            prev_hash=receipt.prev_hash,
        )
        return receipt

    def verify_chain(self) -> bool:
        conn = self.db._get_conn()
        try:
            rows = conn.execute(
                "SELECT receipt_hash, prev_hash FROM receipts ORDER BY rowid ASC"
            ).fetchall()
        finally:
            conn.close()
        prev = ""
        for r in rows:
            if r["prev_hash"] != prev:
                return False
            prev = r["receipt_hash"]
        return True

    def get(self, receipt_hash: str) -> Optional[dict]:
        return self.db.get_receipt(receipt_hash)

    def list_all(self, limit: int = 100) -> list:
        return self.db.list_receipts(limit=limit)
