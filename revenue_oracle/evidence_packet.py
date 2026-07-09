"""
Evidence Packet Builder — creates verifiable evidence packets from artifacts.

For every artifact, creates:
- manifest.json (source_hash, claim list, risk flags, license flags,
  provenance chain, receipt list, reproducibility notes, limitations,
  function_graph_hash, packet_hash)
"""

import hashlib
import json
import os
import time
from typing import Optional

from .schema import OracleDB, ArtifactRecord, EvidencePacket


class EvidencePacketBuilder:
    """Builds verifiable evidence packets from artifact records."""

    def __init__(self, db: OracleDB):
        self.db = db

    def build_packet(self, artifact: ArtifactRecord,
                     claims: list = None,
                     risk_flags: list = None,
                     license_flags: list = None,
                     provenance_chain: list = None,
                     reproducibility_notes: str = "",
                     limitations: str = "",
                     function_graph_hash: str = "",
                     ollama_analysis: dict = None) -> EvidencePacket:
        """
        Build an evidence packet for an artifact.

        Args:
            artifact: The artifact record to build a packet for
            claims: List of claim dicts {claim_id, text, type, confidence, evidence_hash}
            risk_flags: List of risk flag dicts {flag, severity, detail}
            license_flags: List of license flag dicts {flag, status, detail}
            provenance_chain: List of provenance entries
            reproducibility_notes: Notes on how to reproduce
            limitations: Known limitations
            function_graph_hash: Hash of function dependency graph if applicable
            ollama_analysis: Optional Ollama classification result

        Returns:
            EvidencePacket with computed packet_hash
        """
        claims = claims or []
        risk_flags = risk_flags or []
        license_flags = license_flags or []
        provenance_chain = provenance_chain or []

        if ollama_analysis:
            for c in ollama_analysis.get("suggested_claims", []):
                claims.append({
                    "claim_id": hashlib.sha256(
                        f"claim:{c}:{artifact.artifact_id}".encode()
                    ).hexdigest()[:16],
                    "text": c,
                    "type": ollama_analysis.get("category", "other"),
                    "confidence": 0.0,
                    "evidence_hash": artifact.source_hash,
                })
            risk_level = ollama_analysis.get("risk_assessment", "medium")
            if risk_level in ("high", "critical"):
                risk_flags.append({
                    "flag": "ollama_risk_assessment",
                    "severity": risk_level,
                    "detail": f"Ollama classified risk as {risk_level}",
                })

        created_at = time.time()
        manifest = {
            "artifact_id": artifact.artifact_id,
            "source_hash": artifact.source_hash,
            "manifest_hash": artifact.manifest_hash,
            "claims": claims,
            "risk_flags": risk_flags,
            "license_flags": license_flags,
            "provenance_chain": provenance_chain,
            "reproducibility_notes": reproducibility_notes,
            "limitations": limitations,
            "function_graph_hash": function_graph_hash,
            "created_at": created_at,
        }

        packet_hash = hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest()

        packet = EvidencePacket(
            packet_hash=packet_hash,
            artifact_id=artifact.artifact_id,
            source_hash=artifact.source_hash,
            manifest_hash=artifact.manifest_hash,
            claims=claims,
            risk_flags=risk_flags,
            license_flags=license_flags,
            provenance_chain=provenance_chain,
            receipt_list=[],
            reproducibility_notes=reproducibility_notes,
            limitations=limitations,
            function_graph_hash=function_graph_hash,
            created_at=created_at,
            revenue_status="proof_of_financeable_structure_only",
        )

        self.db.insert_evidence_packet(packet)
        return packet

    def verify_packet(self, packet_hash: str) -> dict:
        """Verify a packet by recomputing its hash."""
        stored = self.db.get_evidence_packet(packet_hash)
        if not stored:
            return {"valid": False, "error": "Packet not found"}

        manifest = {
            "artifact_id": stored["artifact_id"],
            "source_hash": stored["source_hash"],
            "manifest_hash": stored["manifest_hash"],
            "claims": stored["claims"],
            "risk_flags": stored["risk_flags"],
            "license_flags": stored["license_flags"],
            "provenance_chain": stored["provenance_chain"],
            "reproducibility_notes": stored["reproducibility_notes"],
            "limitations": stored["limitations"],
            "function_graph_hash": stored["function_graph_hash"],
            "created_at": stored["created_at"],
        }

        recomputed = hashlib.sha256(
            json.dumps(manifest, sort_keys=True).encode()
        ).hexdigest()

        return {
            "valid": recomputed == packet_hash,
            "stored_hash": packet_hash,
            "recomputed_hash": recomputed,
            "packet": stored,
        }

    @staticmethod
    def compute_source_hash(source_uri_or_path: str) -> str:
        """Compute SHA-256 hash of a file or content string."""
        if os.path.isfile(source_uri_or_path):
            with open(source_uri_or_path, "rb") as f:
                return hashlib.sha256(f.read()).hexdigest()
        return hashlib.sha256(source_uri_or_path.encode()).hexdigest()

    @staticmethod
    def compute_manifest_hash(source_hash: str, source_type: str,
                              owner: str) -> str:
        """Compute manifest hash from source hash + metadata."""
        return hashlib.sha256(
            f"{source_hash}:{source_type}:{owner}".encode()
        ).hexdigest()
