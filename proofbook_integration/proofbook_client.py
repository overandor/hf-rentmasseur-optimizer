"""
ProofBook Integration for underwriting pipeline.
Hashes, stores, and references decision memos, receipts, and proofs as auditable evidence.
"""

import hashlib
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from enum import Enum


class ProofType(Enum):
    UNDERWRITING_MEMO = "underwriting_memo"
    COMPUTE_RECEIPT = "compute_receipt"
    VALUATION_RECEIPT = "valuation_receipt"
    RISK_ASSESSMENT = "risk_assessment"
    CRAWLER_EVIDENCE = "crawler_evidence"
    SCORE_RESULT = "score_result"
    ACTION_RESULT = "action_result"


class ProofStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    REJECTED = "rejected"


@dataclass
class ProofEntry:
    """Represents a proof entry in ProofBook."""
    proof_id: str
    proof_type: ProofType
    content_hash: str
    content: Dict
    source_id: Optional[str] = None
    status: ProofStatus = ProofStatus.PENDING
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict = field(default_factory=dict)
    signature: Optional[str] = None
    previous_hash: Optional[str] = None  # For chain integrity
    
    def to_dict(self) -> Dict:
        return {
            "proof_id": self.proof_id,
            "proof_type": self.proof_type.value,
            "content_hash": self.content_hash,
            "content": self.content,
            "source_id": self.source_id,
            "status": self.status.value,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
            "signature": self.signature,
            "previous_hash": self.previous_hash
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "ProofEntry":
        return cls(
            proof_id=data["proof_id"],
            proof_type=ProofType(data["proof_type"]),
            content_hash=data["content_hash"],
            content=data["content"],
            source_id=data.get("source_id"),
            status=ProofStatus(data["status"]),
            timestamp=data.get("timestamp", datetime.utcnow().isoformat()),
            metadata=data.get("metadata", {}),
            signature=data.get("signature"),
            previous_hash=data.get("previous_hash")
        )


@dataclass
class ProofChain:
    """Represents a chain of proof entries for integrity verification."""
    chain_id: str
    entries: List[ProofEntry] = field(default_factory=list)
    root_hash: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict:
        return {
            "chain_id": self.chain_id,
            "entries": [e.to_dict() for e in self.entries],
            "root_hash": self.root_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }


class ProofBook:
    """
    ProofBook: Tamper-evident ledger for storing and verifying proofs.
    
    This implementation provides a local file-based ledger. In production,
    this could be extended to use:
    - Blockchain-based storage (e.g., Ethereum, Solana)
    - IPFS for decentralized content storage
    - Merkle trees for efficient verification
    - Digital signatures for authenticity
    """
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("proofbook_integration/storage/ledger")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.chains_path = self.storage_path / "chains"
        self.chains_path.mkdir(parents=True, exist_ok=True)
        self.proofs_path = self.storage_path / "proofs"
        self.proofs_path.mkdir(parents=True, exist_ok=True)
    
    def _compute_hash(self, content: Dict) -> str:
        """Compute SHA-256 hash of content."""
        content_str = json.dumps(content, sort_keys=True)
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    def _generate_proof_id(self) -> str:
        """Generate unique proof ID."""
        import uuid
        return str(uuid.uuid4())
    
    def submit_proof(
        self,
        proof_type: ProofType,
        content: Dict,
        source_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        chain_id: Optional[str] = None
    ) -> ProofEntry:
        """
        Submit a new proof to the ledger.
        
        Args:
            proof_type: Type of proof
            content: Proof content
            source_id: Associated source ID
            metadata: Additional metadata
            chain_id: Optional chain ID for linking proofs
        
        Returns:
            ProofEntry with computed hash and ID
        """
        proof_id = self._generate_proof_id()
        content_hash = self._compute_hash(content)
        
        # Get previous hash if chain_id provided
        previous_hash = None
        if chain_id:
            chain = self.get_chain(chain_id)
            if chain and chain.entries:
                previous_hash = chain.entries[-1].content_hash
        
        entry = ProofEntry(
            proof_id=proof_id,
            proof_type=proof_type,
            content_hash=content_hash,
            content=content,
            source_id=source_id,
            status=ProofStatus.SUBMITTED,
            metadata=metadata or {},
            previous_hash=previous_hash
        )
        
        # Save proof
        self._save_proof(entry)
        
        # Update chain if provided
        if chain_id:
            self._add_to_chain(chain_id, entry)
        
        return entry
    
    def _save_proof(self, entry: ProofEntry):
        """Save proof to storage."""
        proof_file = self.proofs_path / f"{entry.proof_id}.json"
        with open(proof_file, "w") as f:
            json.dump(entry.to_dict(), f, indent=2)
    
    def _add_to_chain(self, chain_id: str, entry: ProofEntry):
        """Add proof to a chain."""
        chain = self.get_chain(chain_id)
        
        if not chain:
            chain = ProofChain(chain_id=chain_id)
        
        chain.entries.append(entry)
        chain.updated_at = datetime.utcnow().isoformat()
        
        # Compute root hash
        chain.root_hash = self._compute_chain_root_hash(chain)
        
        self._save_chain(chain)
    
    def _compute_chain_root_hash(self, chain: ProofChain) -> str:
        """Compute root hash of chain (simplified Merkle-like computation)."""
        if not chain.entries:
            return hashlib.sha256(b"").hexdigest()
        
        # Simple concatenation of all hashes (in production, use proper Merkle tree)
        combined = "".join(e.content_hash for e in chain.entries)
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def _save_chain(self, chain: ProofChain):
        """Save chain to storage."""
        chain_file = self.chains_path / f"{chain.chain_id}.json"
        with open(chain_file, "w") as f:
            json.dump(chain.to_dict(), f, indent=2)
    
    def get_proof(self, proof_id: str) -> Optional[ProofEntry]:
        """Retrieve proof by ID."""
        proof_file = self.proofs_path / f"{proof_id}.json"
        if not proof_file.exists():
            return None
        
        with open(proof_file, "r") as f:
            return ProofEntry.from_dict(json.load(f))
    
    def get_chain(self, chain_id: str) -> Optional[ProofChain]:
        """Retrieve chain by ID."""
        chain_file = self.chains_path / f"{chain_id}.json"
        if not chain_file.exists():
            return None
        
        with open(chain_file, "r") as f:
            data = json.load(f)
            chain = ProofChain(
                chain_id=data["chain_id"],
                entries=[ProofEntry.from_dict(e) for e in data["entries"]],
                root_hash=data.get("root_hash"),
                created_at=data.get("created_at", datetime.utcnow().isoformat()),
                updated_at=data.get("updated_at", datetime.utcnow().isoformat())
            )
            return chain
    
    def verify_proof(self, proof_id: str) -> bool:
        """
        Verify proof integrity by checking hash.
        
        Returns:
            True if proof is valid, False otherwise
        """
        entry = self.get_proof(proof_id)
        if not entry:
            return False
        
        computed_hash = self._compute_hash(entry.content)
        return computed_hash == entry.content_hash
    
    def verify_chain(self, chain_id: str) -> bool:
        """
        Verify chain integrity by checking hash chain.
        
        Returns:
            True if chain is valid, False otherwise
        """
        chain = self.get_chain(chain_id)
        if not chain:
            return False
        
        # Verify each proof
        for entry in chain.entries:
            if not self.verify_proof(entry.proof_id):
                return False
        
        # Verify hash chain linkage
        for i in range(1, len(chain.entries)):
            current = chain.entries[i]
            previous = chain.entries[i-1]
            if current.previous_hash != previous.content_hash:
                return False
        
        # Verify root hash
        computed_root = self._compute_chain_root_hash(chain)
        if computed_root != chain.root_hash:
            return False
        
        return True
    
    def get_proofs_by_source(self, source_id: str) -> List[ProofEntry]:
        """Get all proofs for a specific source."""
        proofs = []
        for proof_file in self.proofs_path.glob("*.json"):
            with open(proof_file, "r") as f:
                entry = ProofEntry.from_dict(json.load(f))
                if entry.source_id == source_id:
                    proofs.append(entry)
        return proofs
    
    def get_proofs_by_type(self, proof_type: ProofType) -> List[ProofEntry]:
        """Get all proofs of a specific type."""
        proofs = []
        for proof_file in self.proofs_path.glob("*.json"):
            with open(proof_file, "r") as f:
                entry = ProofEntry.from_dict(json.load(f))
                if entry.proof_type == proof_type:
                    proofs.append(entry)
        return proofs
    
    def get_stats(self) -> Dict:
        """Get ledger statistics."""
        total_proofs = len(list(self.proofs_path.glob("*.json")))
        total_chains = len(list(self.chains_path.glob("*.json")))
        
        type_counts = {}
        for proof_type in ProofType:
            type_counts[proof_type.value] = len(self.get_proofs_by_type(proof_type))
        
        return {
            "total_proofs": total_proofs,
            "total_chains": total_chains,
            "by_type": type_counts
        }


class UnderwritingProofBook(ProofBook):
    """
    Specialized ProofBook for underwriting pipeline.
    Provides convenience methods for underwriting-specific proofs.
    """
    
    def submit_underwriting_memo(
        self,
        source_id: str,
        memo: Dict,
        chain_id: Optional[str] = None
    ) -> ProofEntry:
        """Submit an underwriting memo as proof."""
        return self.submit_proof(
            ProofType.UNDERWRITING_MEMO,
            memo,
            source_id=source_id,
            chain_id=chain_id
        )
    
    def submit_score_result(
        self,
        source_id: str,
        score_result: Dict,
        chain_id: Optional[str] = None
    ) -> ProofEntry:
        """Submit a scoring result as proof."""
        return self.submit_proof(
            ProofType.SCORE_RESULT,
            score_result,
            source_id=source_id,
            chain_id=chain_id
        )
    
    def submit_action_result(
        self,
        source_id: str,
        action_result: Dict,
        chain_id: Optional[str] = None
    ) -> ProofEntry:
        """Submit an action result as proof."""
        return self.submit_proof(
            ProofType.ACTION_RESULT,
            action_result,
            source_id=source_id,
            chain_id=chain_id
        )
    
    def submit_crawler_evidence(
        self,
        source_id: str,
        crawl_result: Dict,
        chain_id: Optional[str] = None
    ) -> ProofEntry:
        """Submit crawler evidence as proof."""
        return self.submit_proof(
            ProofType.CRAWLER_EVIDENCE,
            crawl_result,
            source_id=source_id,
            chain_id=chain_id
        )
    
    def create_underwriting_chain(self, source_id: str) -> str:
        """Create a new chain for an underwriting workflow."""
        import uuid
        chain_id = f"underwriting_{source_id}_{uuid.uuid4().hex[:8]}"
        chain = ProofChain(chain_id=chain_id)
        self._save_chain(chain)
        return chain_id
    
    def get_underwriting_chain(self, source_id: str) -> Optional[ProofChain]:
        """Get the underwriting chain for a source."""
        # Find chains that start with the source_id prefix
        for chain_file in self.chains_path.glob(f"underwriting_{source_id}_*.json"):
            with open(chain_file, "r") as f:
                data = json.load(f)
                return ProofChain(
                    chain_id=data["chain_id"],
                    entries=[ProofEntry.from_dict(e) for e in data["entries"]],
                    root_hash=data.get("root_hash"),
                    created_at=data.get("created_at"),
                    updated_at=data.get("updated_at")
                )
        return None
