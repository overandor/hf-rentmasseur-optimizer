"""
ProofBook Integration Planner
Plans how to hash, store, and reference decision memos, receipts, and proofs
"""
import hashlib
import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

@dataclass
class ProofEntry:
    """A single proof entry in ProofBook"""
    hash: str
    content_hash: str
    content_type: str
    timestamp: str
    source_system: str
    metadata: Dict[str, Any]
    previous_hash: Optional[str] = None
    signature: Optional[str] = None

@dataclass
class ProofChain:
    """A chain of proofs forming an audit trail"""
    entries: List[ProofEntry]
    root_hash: str
    chain_id: str

class ProofBookIntegration:
    """
    Plans and implements ProofBook integration for auditable evidence
    
    Sequence:
    1. Hash and record underwriting memos
    2. Attach signed reuse receipts from memory or compute runs
    3. Feed receipts into node valuation model
    4. Rerun underwriting pipeline with real proof, not claims
    """
    
    def __init__(self, storage_path: Path):
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.chain_index: Dict[str, ProofChain] = {}
    
    def hash_content(self, content: Any) -> str:
        """Hash content for integrity verification"""
        if isinstance(content, (dict, list)):
            content_str = json.dumps(content, sort_keys=True)
        else:
            content_str = str(content)
        return hashlib.sha256(content_str.encode()).hexdigest()
    
    def create_proof_entry(self, content: Any, content_type: str, 
                          source_system: str, metadata: Dict[str, Any],
                          previous_hash: Optional[str] = None) -> ProofEntry:
        """Create a single proof entry"""
        content_hash = self.hash_content(content)
        entry_hash = self.hash_content({
            'content_hash': content_hash,
            'timestamp': datetime.now().isoformat(),
            'previous_hash': previous_hash
        })
        
        return ProofEntry(
            hash=entry_hash,
            content_hash=content_hash,
            content_type=content_type,
            timestamp=datetime.now().isoformat(),
            source_system=source_system,
            metadata=metadata,
            previous_hash=previous_hash
        )
    
    def start_chain(self, chain_id: str, initial_content: Any, 
                   content_type: str, source_system: str,
                   metadata: Dict[str, Any]) -> ProofChain:
        """Start a new proof chain"""
        entry = self.create_proof_entry(
            initial_content, content_type, source_system, metadata
        )
        
        chain = ProofChain(
            entries=[entry],
            root_hash=entry.hash,
            chain_id=chain_id
        )
        
        self.chain_index[chain_id] = chain
        self._save_chain(chain)
        
        return chain
    
    def append_to_chain(self, chain_id: str, content: Any, 
                       content_type: str, metadata: Dict[str, Any]) -> ProofChain:
        """Append to existing proof chain"""
        if chain_id not in self.chain_index:
            raise ValueError(f"Chain {chain_id} not found")
        
        chain = self.chain_index[chain_id]
        previous_hash = chain.entries[-1].hash
        
        entry = self.create_proof_entry(
            content, content_type, chain.entries[0].source_system,
            metadata, previous_hash
        )
        
        chain.entries.append(entry)
        self._save_chain(chain)
        
        return chain
    
    def _save_chain(self, chain: ProofChain):
        """Save chain to storage"""
        chain_path = self.storage_path / f"{chain.chain_id}.json"
        with open(chain_path, 'w') as f:
            json.dump({
                'chain_id': chain.chain_id,
                'root_hash': chain.root_hash,
                'entries': [e.__dict__ for e in chain.entries]
            }, f, indent=2)
    
    def load_chain(self, chain_id: str) -> Optional[ProofChain]:
        """Load chain from storage"""
        chain_path = self.storage_path / f"{chain_id}.json"
        if not chain_path.exists():
            return None
        
        with open(chain_path) as f:
            data = json.load(f)
        
        entries = [ProofEntry(**e) for e in data['entries']]
        chain = ProofChain(
            entries=entries,
            root_hash=data['root_hash'],
            chain_id=data['chain_id']
        )
        
        self.chain_index[chain_id] = chain
        return chain
    
    def verify_chain(self, chain_id: str) -> bool:
        """Verify chain integrity"""
        chain = self.load_chain(chain_id)
        if not chain:
            return False
        
        # Verify root hash matches first entry
        if chain.root_hash != chain.entries[0].hash:
            return False
        
        # Verify chain links
        for i in range(1, len(chain.entries)):
            if chain.entries[i].previous_hash != chain.entries[i-1].hash:
                return False
        
        return True
    
    def plan_underwriting_integration(self, underwriting_output: Dict[str, Any]) -> Dict[str, Any]:
        """
        Plan how to integrate underwriting decision into ProofBook
        
        Step 1: Hash and record underwriting memos
        """
        plan = {
            'step': 'hash_underwriting_memo',
            'chain_id': f"underwriting-{datetime.now().strftime('%Y%m%d')}",
            'content_type': 'underwriting_decision',
            'source_system': 'underwriting_pipeline',
            'metadata': {
                'risk_grade': underwriting_output.get('risk_grade'),
                'borrowing_base': underwriting_output.get('borrowing_base'),
                'timestamp': underwriting_output.get('timestamp')
            },
            'actions': [
                'Create proof chain with underwriting decision',
                'Hash decision memo with SHA-256',
                'Store in ProofBook with metadata',
                'Generate receipt hash reference'
            ]
        }
        return plan
    
    def plan_receipt_integration(self, receipt: Dict[str, Any]) -> Dict[str, Any]:
        """
        Plan how to integrate compute receipts into ProofBook
        
        Step 2: Attach signed reuse receipts from memory or compute runs
        """
        plan = {
            'step': 'attach_compute_receipt',
            'chain_id': f"receipts-{datetime.now().strftime('%Y%m%d')}",
            'content_type': 'compute_receipt',
            'source_system': 'layer_crawler',
            'metadata': {
                'system': receipt.get('system'),
                'prod_score': receipt.get('scores', {}).get('prod_score'),
                'ip_risk': receipt.get('scores', {}).get('ip_risk'),
                'timestamp': receipt.get('timestamp')
            },
            'actions': [
                'Append receipt to existing underwriting chain',
                'Hash receipt with SHA-256',
                'Link to previous underwriting decision',
                'Store runtime screenshot hash'
            ]
        }
        return plan
    
    def plan_valuation_integration(self, valuation: Dict[str, Any]) -> Dict[str, Any]:
        """
        Plan how to integrate valuation into ProofBook
        
        Step 3: Feed receipts into node valuation model
        """
        plan = {
            'step': 'feed_valuation',
            'chain_id': f"valuation-{datetime.now().strftime('%Y%m%d')}",
            'content_type': 'machine_valuation',
            'source_system': 'compute_capital_valuation',
            'metadata': {
                'total_value': valuation.get('total_value'),
                'productivity_multiplier': valuation.get('productivity_multiplier'),
                'timestamp': valuation.get('timestamp')
            },
            'actions': [
                'Append valuation to chain',
                'Link to compute receipts',
                'Hash appraisal memo',
                'Store capital improvement evidence'
            ]
        }
        return plan
    
    def plan_rerun_underwriting(self, chain_id: str) -> Dict[str, Any]:
        """
        Plan how to rerun underwriting with real proof
        
        Step 4: Rerun underwriting pipeline with real proof, not claims
        """
        plan = {
            'step': 'rerun_with_proof',
            'chain_id': chain_id,
            'content_type': 'verified_underwriting',
            'source_system': 'underwriting_pipeline',
            'metadata': {
                'verification_method': 'proof_chain',
                'chain_verified': self.verify_chain(chain_id)
            },
            'actions': [
                'Load full proof chain',
                'Verify all hashes and links',
                'Extract verified evidence',
                'Rerun underwriting with proof-backed inputs',
                'Generate verified decision memo'
            ]
        }
        return plan

# Example usage
if __name__ == "__main__":
    proofbook = ProofBookIntegration(Path("proofbook_storage"))
    
    # Start underwriting chain
    underwriting_decision = {
        'risk_grade': 'C',
        'borrowing_base': 41645,
        'timestamp': datetime.now().isoformat()
    }
    
    plan = proofbook.plan_underwriting_integration(underwriting_decision)
    chain = proofbook.start_chain(
        plan['chain_id'],
        underwriting_decision,
        plan['content_type'],
        plan['source_system'],
        plan['metadata']
    )
    
    print(f"Started chain: {chain.chain_id}")
    print(f"Root hash: {chain.root_hash}")
    
    # Append receipt
    receipt = {
        'system': 'Membra Desktop Operator 2',
        'scores': {'prod_score': 70, 'ip_risk': 0},
        'timestamp': datetime.now().isoformat()
    }
    
    receipt_plan = proofbook.plan_receipt_integration(receipt)
    updated_chain = proofbook.append_to_chain(
        chain.chain_id,
        receipt,
        receipt_plan['content_type'],
        receipt_plan['metadata']
    )
    
    print(f"Appended receipt. Chain length: {len(updated_chain.entries)}")
    
    # Verify chain
    is_valid = proofbook.verify_chain(chain.chain_id)
    print(f"Chain valid: {is_valid}")
