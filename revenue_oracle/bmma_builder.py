"""
BMMA Builder — bridges broll's Bonded Machine Media Asset into the Revenue Oracle.

For video/media artifacts, creates a BMMA object that combines:
- Machine-consumable research video packet (MCRV)
- Fractional revenue or rights ledger (FRVO)
- Sealed grade bond (AGB)
- Standards exports (Schema.org, C2PA)
- Segment marketplace listings

The BMMA is the financeable primitive: content + evidence + rights + revenue
records + quality grade + audit logic + recourse.

Flow:
  artifact → evidence packet → broll compile → BMMA → media_asset record → receipt
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from .schema import OracleDB, ArtifactRecord, EvidencePacket, MediaAssetRecord
from .receipt_ledger import ReceiptLedger


@dataclass
class BMMAResult:
    """Result of building a BMMA from an artifact."""
    media_asset: MediaAssetRecord
    bmma_id: str
    bea_id: str
    grade_claimed: float
    grade_computed: float
    bond_amount: float
    bond_required: float
    rubric_id: str
    audit_probability: float
    producer_tier: str
    schema_org_generated: bool
    c2pa_generated: bool
    segments_listed: int
    segments_available: int
    receipt_hash: str

    def to_dict(self) -> dict:
        return {
            "media_asset_id": self.media_asset.media_asset_id,
            "bmma_id": self.bmma_id,
            "bea_id": self.bea_id,
            "grade_claimed": self.grade_claimed,
            "grade_computed": self.grade_computed,
            "bond_amount": self.bond_amount,
            "bond_required": self.bond_required,
            "rubric_id": self.rubric_id,
            "audit_probability": self.audit_probability,
            "producer_tier": self.producer_tier,
            "schema_org_generated": self.schema_org_generated,
            "c2pa_generated": self.c2pa_generated,
            "segments_listed": self.segments_listed,
            "segments_available": self.segments_available,
            "receipt_hash": self.receipt_hash,
        }


class BMMABuilder:
    """
    Builds Bonded Machine Media Assets from oracle artifacts.

    Bridges the broll stack (AssetCompiler, GradeBondProtocol, StandardsExporter,
    SegmentMarketplace) into the Revenue Oracle's SQLite-backed pipeline.

    For non-media artifacts, the BMMA builder creates a lightweight record
    with just the grade bond and provenance, without video-specific fields.
    """

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger = None):
        self.db = db
        self.receipt_ledger = receipt_ledger or ReceiptLedger(db)

    def build_bmma(
        self,
        artifact: dict,
        packet: dict,
        question: str = "",
        claims: list = None,
        transcript: str = "",
        visual_evidence_segments: list = None,
        truth_labels: list = None,
        rights_labels: list = None,
        revenue_ledger: dict = None,
        machine_scores: dict = None,
        bond_amount_usd: float = 0.0,
        rubric_id: str = "video_evidence_quality_v1",
        offering_mode: str = "PERK_ONLY",
        producer_id: str = "default",
        compile_video: bool = False,
    ) -> BMMAResult:
        """
        Build a BMMA from an oracle artifact + evidence packet.

        This creates the media_asset record in SQLite and writes a receipt.
        It does NOT call broll's AssetCompiler (which requires ffmpeg etc.)
        — instead it creates the BMMA metadata structure directly, using
        the evidence packet's claims and scores to compute a grade.

        Args:
            artifact: Artifact dict from the oracle
            packet: Evidence packet dict
            question: Research question
            claims: List of claim dicts
            transcript: Full transcript text
            visual_evidence_segments: VES records
            truth_labels: Truth status labels
            rights_labels: Rights status labels
            revenue_ledger: FRVO revenue ledger dict
            machine_scores: Machine scoring dict for grade computation
            bond_amount_usd: Bond amount (0 = auto-compute)
            rubric_id: Grade rubric to use
            offering_mode: PERK_ONLY or REVENUE_SHARE
            producer_id: Producer identifier
            compile_video: Whether to attempt video compilation

        Returns:
            BMMAResult with all BMMA metadata
        """
        claims = claims or packet.get("claims", [])
        visual_evidence_segments = visual_evidence_segments or []
        truth_labels = truth_labels or []
        rights_labels = rights_labels or []
        revenue_ledger = revenue_ledger or {}
        machine_scores = machine_scores or {}

        artifact_id = artifact["artifact_id"]
        packet_hash = packet["packet_hash"]

        # Compute grades from machine scores
        grade_claimed, grade_computed = self._compute_grades(machine_scores, claims, rights_labels)

        # Compute required bond using deterrence formula
        grade_premium = max(grade_claimed - grade_computed, 0)
        audit_probability = self._compute_audit_probability(grade_claimed)
        bond_required = self._compute_required_bond(grade_premium, audit_probability, producer_id)
        if bond_amount_usd == 0.0:
            bond_amount_usd = bond_required

        # Generate standards export hashes (metadata only, no actual files)
        schema_org_hash = self._hash_standards_export(question, claims, rights_labels, grade_claimed)
        c2pa_manifest_hash = self._hash_c2pa(question, claims, rights_labels, grade_claimed)

        # Segment listings from VES
        segments_listed = len(visual_evidence_segments)
        segments_available = sum(
            1 for s in visual_evidence_segments
            if s.get("rights_status", "unknown") in ("safe", "fair_use")
        )

        # Revenue ledger hash
        revenue_ledger_hash = ""
        if revenue_ledger:
            revenue_ledger_hash = f"sha256:{hashlib.sha256(
                json.dumps(revenue_ledger, sort_keys=True).encode()
            ).hexdigest()[:16]}"

        # Provenance hash
        provenance_data = {
            "artifact_id": artifact_id,
            "packet_hash": packet_hash,
            "source_hash": artifact.get("source_hash", ""),
            "manifest_hash": artifact.get("manifest_hash", ""),
        }
        provenance_hash = f"sha256:{hashlib.sha256(
            json.dumps(provenance_data, sort_keys=True).encode()
        ).hexdigest()[:16]}"

        # Generate IDs
        bmma_id = f"bmma_{hashlib.sha256(f'{artifact_id}{packet_hash}{time.time()}'.encode()).hexdigest()[:12]}"
        bea_id = f"bea_{hashlib.sha256(f'{bmma_id}{rubric_id}'.encode()).hexdigest()[:12]}"
        media_asset_id = f"ma_{hashlib.sha256(f'{bmma_id}{artifact_id}'.encode()).hexdigest()[:12]}"

        # Compute receipt hash
        receipt_data = {
            "bmma_id": bmma_id,
            "bea_id": bea_id,
            "artifact_id": artifact_id,
            "packet_hash": packet_hash,
            "grade_claimed": grade_claimed,
            "grade_computed": grade_computed,
            "bond_amount": bond_amount_usd,
            "rubric_id": rubric_id,
        }
        receipt_hash = f"sha256:{hashlib.sha256(
            json.dumps(receipt_data, sort_keys=True).encode()
        ).hexdigest()[:16]}"

        # Determine producer tier
        producer_tier = self._get_producer_tier(producer_id)

        # Create media asset record
        media_asset = MediaAssetRecord(
            media_asset_id=media_asset_id,
            artifact_id=artifact_id,
            packet_hash=packet_hash,
            bmma_id=bmma_id,
            bea_id=bea_id,
            question=question,
            transcript=transcript[:5000],
            claims_json=json.dumps(claims[:50]),
            scene_graph_hash="",
            visual_evidence_segments=json.dumps(visual_evidence_segments[:50]),
            truth_labels=json.dumps(truth_labels),
            rights_labels=json.dumps(rights_labels),
            revenue_ledger_hash=revenue_ledger_hash,
            payout_waterfall_hash="",
            quality_grade=grade_claimed,
            computed_grade=grade_computed,
            bond_amount_usd=bond_amount_usd,
            bond_required_usd=bond_required,
            rubric_id=rubric_id,
            audit_probability=audit_probability,
            producer_id=producer_id,
            producer_tier=producer_tier,
            schema_org_hash=schema_org_hash,
            c2pa_manifest_hash=c2pa_manifest_hash,
            segment_listings_count=segments_listed,
            segment_listings_available=segments_available,
            provenance_hash=provenance_hash,
            receipt_hash=receipt_hash,
            created_at=time.time(),
            status="proof_only",
        )

        self.db.insert_media_asset(media_asset)

        # Write receipt
        self.receipt_ledger.write(
            receipt_type="bmma_creation",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
            packet_hash=packet_hash,
        )

        return BMMAResult(
            media_asset=media_asset,
            bmma_id=bmma_id,
            bea_id=bea_id,
            grade_claimed=grade_claimed,
            grade_computed=grade_computed,
            bond_amount=bond_amount_usd,
            bond_required=bond_required,
            rubric_id=rubric_id,
            audit_probability=audit_probability,
            producer_tier=producer_tier,
            schema_org_generated=bool(schema_org_hash),
            c2pa_generated=bool(c2pa_manifest_hash),
            segments_listed=segments_listed,
            segments_available=segments_available,
            receipt_hash=receipt_hash,
        )

    def _compute_grades(self, machine_scores: dict, claims: list, rights_labels: list) -> tuple:
        """Compute claimed and computed grades from machine scores."""
        if not machine_scores:
            # Derive from claims and rights
            claim_count = len(claims)
            safe_count = sum(1 for r in rights_labels if r in ("safe", "fair_use"))
            total = max(len(rights_labels), 1)
            rights_ratio = safe_count / total
            base = min(claim_count * 10, 50) + rights_ratio * 30
            return round(min(base, 100), 1), round(min(base * 0.9, 90), 1)

        # Weighted average of machine scores
        weights = {
            "evidence_strength": 0.20,
            "rights_safety": 0.15,
            "machine_buyability": 0.10,
            "provenance_integrity": 0.10,
            "revenue_receipt_quality": 0.05,
            "ledger_integrity": 0.05,
            "license_clarity": 0.10,
            "copyright_clean": 0.10,
            "receipt_completeness": 0.05,
            "source_quality": 0.05,
            "claim_coverage": 0.05,
        }
        total_weight = 0
        weighted_sum = 0
        for key, weight in weights.items():
            if key in machine_scores:
                weighted_sum += machine_scores[key] * weight
                total_weight += weight

        if total_weight == 0:
            return 50.0, 45.0

        computed = round((weighted_sum / total_weight) * 100, 1)
        # Claimed grade is slightly optimistic (producer claims higher)
        claimed = round(min(computed + 5, 100), 1)
        return claimed, computed

    def _compute_audit_probability(self, grade_claimed: float) -> float:
        """Higher grade claims get higher audit probability."""
        if grade_claimed >= 90:
            return 0.15
        if grade_claimed >= 80:
            return 0.10
        if grade_claimed >= 70:
            return 0.07
        if grade_claimed >= 60:
            return 0.05
        return 0.03

    def _compute_required_bond(self, grade_premium: float, audit_prob: float, producer_id: str) -> float:
        """
        Deterrence formula: required bond >= grade_premium / audit_probability * producer_multiplier.

        For unproven producers, multiplier is 1.5 (higher bond required).
        For proven producers, multiplier is 1.0.
        """
        multiplier = 1.5 if self._get_producer_tier(producer_id) == "unproven" else 1.0
        if audit_prob == 0:
            return 1000.0 * multiplier
        return round(max((grade_premium / audit_prob) * multiplier, 100.0), 2)

    def _get_producer_tier(self, producer_id: str) -> str:
        """Get producer reputation tier. Currently all unproven by default."""
        return "unproven"

    def _hash_standards_export(self, question: str, claims: list, rights_labels: list, grade: float) -> str:
        """Generate a hash representing Schema.org VideoObject metadata."""
        data = {
            "type": "VideoObject",
            "question": question,
            "claims_count": len(claims),
            "rights_safe": sum(1 for r in rights_labels if r == "safe"),
            "grade": grade,
        }
        return f"sha256:{hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]}"

    def _hash_c2pa(self, question: str, claims: list, rights_labels: list, grade: float) -> str:
        """Generate a hash representing C2PA manifest metadata."""
        data = {
            "title": question,
            "claims_count": len(claims),
            "rights_labels": rights_labels,
            "grade": grade,
        }
        return f"sha256:{hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]}"
