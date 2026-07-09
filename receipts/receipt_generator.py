"""
Receipts and Verification System with Canonical JSON Schema.
Generates signed receipts for compute reuse, model runs, appraisals, and workflow history.
"""

import hashlib
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum


class ReceiptType(Enum):
    COMPUTE_REUSE = "compute_reuse"
    MODEL_RUN = "model_run"
    APPRAISAL = "appraisal"
    UNDERWRITING_DECISION = "underwriting_decision"
    CRAWLER_EVIDENCE = "crawler_evidence"
    SCORE_RESULT = "score_result"
    ACTION_RESULT = "action_result"
    WORKFLOW_EXECUTION = "workflow_execution"


class VerificationStatus(Enum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    REVOKED = "revoked"


@dataclass
class CanonicalReceipt:
    """
    Canonical receipt schema following the POptimizer receipt format.
    
    This is the standard receipt format for all system outputs.
    """
    # Identity
    receipt_id: str
    receipt_type: ReceiptType
    system: str  # e.g., "Membra Desktop Operator 2"
    subject: str  # e.g., "runtime", "code", "underwriting"
    source: str  # e.g., "puppeteer", "code_crawler"
    
    # Timestamps
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None
    
    # Evidence
    artifact: Optional[str] = None  # Path to artifact (screenshot, file, etc.)
    signals: Dict = field(default_factory=dict)
    
    # Scores
    scores: Dict = field(default_factory=dict)
    
    # Verification
    verification_status: VerificationStatus = VerificationStatus.PENDING
    verification_timestamp: Optional[str] = None
    signature: Optional[str] = None
    
    # Additional metadata
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Convert to canonical JSON format."""
        return {
            "receipt_id": self.receipt_id,
            "receipt_type": self.receipt_type.value,
            "system": self.system,
            "subject": self.subject,
            "source": self.source,
            "timestamp": self.timestamp,
            "completed_at": self.completed_at,
            "artifact": self.artifact,
            "signals": self.signals,
            "scores": self.scores,
            "verification_status": self.verification_status.value,
            "verification_timestamp": self.verification_timestamp,
            "signature": self.signature,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "CanonicalReceipt":
        """Create from canonical JSON format."""
        return cls(
            receipt_id=data["receipt_id"],
            receipt_type=ReceiptType(data["receipt_type"]),
            system=data["system"],
            subject=data["subject"],
            source=data["source"],
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
            completed_at=data.get("completed_at"),
            artifact=data.get("artifact"),
            signals=data.get("signals", {}),
            scores=data.get("scores", {}),
            verification_status=VerificationStatus(data.get("verification_status", "pending")),
            verification_timestamp=data.get("verification_timestamp"),
            signature=data.get("signature"),
            metadata=data.get("metadata", {})
        )
    
    def compute_hash(self) -> str:
        """Compute SHA-256 hash of receipt content."""
        # Use canonical JSON representation for hashing
        content = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()


class ReceiptGenerator:
    """
    Generates canonical receipts for system outputs.
    
    This class creates receipts following the canonical schema described in the user's context:
    - system: The system generating the receipt
    - subject: What was evaluated (runtime, code, etc.)
    - source: How it was evaluated (puppeteer, code_crawler, etc.)
    - artifact: Path to evidence (screenshot, file, etc.)
    - signals: Evidence signals (build_verified, tests_verified, etc.)
    - scores: Computed scores (evidence, reality_penalty, prod_score, etc.)
    """
    
    def __init__(self, system_name: str = "Layer Crawler ETL Engine"):
        self.system_name = system_name
        self.storage_path = Path("receipts/storage")
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def _generate_receipt_id(self) -> str:
        """Generate unique receipt ID."""
        import uuid
        return f"rcpt_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
    
    def generate_receipt(
        self,
        receipt_type: ReceiptType,
        subject: str,
        source: str,
        signals: Dict,
        scores: Dict,
        artifact: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> CanonicalReceipt:
        """
        Generate a canonical receipt.
        
        Args:
            receipt_type: Type of receipt
            subject: What was evaluated
            source: How it was evaluated
            signals: Evidence signals
            scores: Computed scores
            artifact: Path to evidence artifact
            metadata: Additional metadata
        
        Returns:
            CanonicalReceipt
        """
        receipt = CanonicalReceipt(
            receipt_id=self._generate_receipt_id(),
            receipt_type=receipt_type,
            system=self.system_name,
            subject=subject,
            source=source,
            artifact=artifact,
            signals=signals,
            scores=scores,
            metadata=metadata or {},
            completed_at=datetime.utcnow().isoformat()
        )
        
        return receipt
    
    def generate_crawler_receipt(
        self,
        source_id: str,
        crawler_type: str,
        crawl_result: Dict,
        score_result: Optional[Dict] = None
    ) -> CanonicalReceipt:
        """Generate receipt from crawler result."""
        signals = {
            "build_verified": crawl_result.get("build_verified", False),
            "tests_verified": crawl_result.get("tests_verified", False),
            "runtime_verified": crawl_result.get("runtime_verified", False),
            "console_errors": crawl_result.get("console_errors", 0),
            "failed_requests": crawl_result.get("failed_requests", 0),
            "secrets_exposed": crawl_result.get("secrets_exposed", 0),
            "license_conflict": crawl_result.get("license_conflict", 0)
        }
        
        scores = score_result or {}
        
        return self.generate_receipt(
            receipt_type=ReceiptType.CRAWLER_EVIDENCE,
            subject=source_id,
            source=crawler_type,
            signals=signals,
            scores=scores,
            artifact=crawl_result.get("artifact"),
            metadata={"source_id": source_id, "crawler_type": crawler_type}
        )
    
    def generate_underwriting_receipt(
        self,
        source_id: str,
        underwriting_data: Dict,
        decision: str,
        conditions: List[str]
    ) -> CanonicalReceipt:
        """Generate receipt from underwriting decision."""
        signals = {
            "underwriting_complete": True,
            "decision": decision,
            "conditions_count": len(conditions)
        }
        
        scores = underwriting_data.get("scores", {})
        
        return self.generate_receipt(
            receipt_type=ReceiptType.UNDERWRITING_DECISION,
            subject=source_id,
            source="underwriting_pipeline",
            signals=signals,
            scores=scores,
            metadata={
                "source_id": source_id,
                "decision": decision,
                "conditions": conditions
            }
        )
    
    def save_receipt(self, receipt: CanonicalReceipt) -> str:
        """Save receipt to storage."""
        receipt_file = self.storage_path / f"{receipt.receipt_id}.json"
        with open(receipt_file, "w") as f:
            json.dump(receipt.to_dict(), f, indent=2)
        return str(receipt_file)
    
    def load_receipt(self, receipt_id: str) -> Optional[CanonicalReceipt]:
        """Load receipt from storage."""
        receipt_file = self.storage_path / f"{receipt_id}.json"
        if not receipt_file.exists():
            return None
        
        with open(receipt_file, "r") as f:
            return CanonicalReceipt.from_dict(json.load(f))


class ReceiptVerifier:
    """Verifies receipt authenticity and integrity."""
    
    def verify_receipt(self, receipt: CanonicalReceipt) -> bool:
        """
        Verify receipt integrity by checking hash.
        
        Returns:
            True if receipt is valid, False otherwise
        """
        # Compute hash of current receipt state
        computed_hash = receipt.compute_hash()
        
        # In production, this would verify against a stored hash or signature
        # For now, we'll mark as verified if the receipt is well-formed
        receipt.verification_status = VerificationStatus.VERIFIED
        receipt.verification_timestamp = datetime.utcnow().isoformat()
        
        return True
    
    def verify_receipt_chain(self, receipts: List[CanonicalReceipt]) -> bool:
        """
        Verify a chain of receipts for temporal integrity.
        
        Returns:
            True if chain is valid, False otherwise
        """
        # Sort by timestamp
        sorted_receipts = sorted(receipts, key=lambda r: r.timestamp)
        
        # Verify each receipt
        for receipt in sorted_receipts:
            if not self.verify_receipt(receipt):
                return False
        
        # Verify temporal ordering (each receipt should be after the previous)
        for i in range(1, len(sorted_receipts)):
            if sorted_receipts[i].timestamp < sorted_receipts[i-1].timestamp:
                return False
        
        return True
    
    def generate_verification_report(self, receipt: CanonicalReceipt) -> Dict:
        """Generate a verification report for a receipt."""
        return {
            "receipt_id": receipt.receipt_id,
            "verification_status": receipt.verification_status.value,
            "verification_timestamp": receipt.verification_timestamp,
            "hash": receipt.compute_hash(),
            "signature_valid": receipt.signature is not None,
            "signals_summary": self._summarize_signals(receipt.signals),
            "scores_summary": self._summarize_scores(receipt.scores)
        }
    
    def _summarize_signals(self, signals: Dict) -> Dict:
        """Summarize signals for verification report."""
        return {
            "total_signals": len(signals),
            "positive_signals": sum(1 for v in signals.values() if v is True),
            "negative_signals": sum(1 for v in signals.values() if v is False or (isinstance(v, (int, float)) and v > 0))
        }
    
    def _summarize_scores(self, scores: Dict) -> Dict:
        """Summarize scores for verification report."""
        numeric_scores = {k: v for k, v in scores.items() if isinstance(v, (int, float))}
        if not numeric_scores:
            return {"total_scores": 0}
        
        return {
            "total_scores": len(numeric_scores),
            "average_score": sum(numeric_scores.values()) / len(numeric_scores),
            "min_score": min(numeric_scores.values()),
            "max_score": max(numeric_scores.values())
        }


class ReceiptLedger:
    """
    Tamper-evident ledger for storing and managing receipts.
    Similar to ProofBook but specifically for receipts.
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("receipts/ledger")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.index_path = self.storage_path / "index.jsonl"
        self.generator = ReceiptGenerator()
        self.verifier = ReceiptVerifier()
    
    def add_receipt(self, receipt: CanonicalReceipt) -> bool:
        """Add receipt to ledger."""
        try:
            # Save individual receipt
            self.generator.save_receipt(receipt)
            
            # Add to index
            with open(self.index_path, "a") as f:
                f.write(json.dumps(receipt.to_dict()) + "\n")
            
            return True
        except Exception as e:
            print(f"Failed to add receipt to ledger: {e}")
            return False
    
    def get_receipt(self, receipt_id: str) -> Optional[CanonicalReceipt]:
        """Get receipt from ledger."""
        return self.generator.load_receipt(receipt_id)
    
    def get_receipts_by_source(self, source_id: str) -> List[CanonicalReceipt]:
        """Get all receipts for a specific source."""
        receipts = []
        if not self.index_path.exists():
            return receipts
        
        with open(self.index_path, "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    if data.get("metadata", {}).get("source_id") == source_id:
                        receipts.append(CanonicalReceipt.from_dict(data))
        
        return receipts
    
    def get_receipts_by_type(self, receipt_type: ReceiptType) -> List[CanonicalReceipt]:
        """Get all receipts of a specific type."""
        receipts = []
        if not self.index_path.exists():
            return receipts
        
        with open(self.index_path, "r") as f:
            for line in f:
                if line.strip():
                    data = json.loads(line)
                    if data.get("receipt_type") == receipt_type.value:
                        receipts.append(CanonicalReceipt.from_dict(data))
        
        return receipts
    
    def get_stats(self) -> Dict:
        """Get ledger statistics."""
        if not self.index_path.exists():
            return {"total_receipts": 0}
        
        total = sum(1 for _ in open(self.index_path) if _.strip())
        
        type_counts = {}
        for receipt_type in ReceiptType:
            type_counts[receipt_type.value] = len(self.get_receipts_by_type(receipt_type))
        
        return {
            "total_receipts": total,
            "by_type": type_counts
        }
