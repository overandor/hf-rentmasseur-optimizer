"""
VideoLake → BMMA Bridge

Takes a compiled VideoLakeResult (from broll/videolake.py) and runs it
through the full Revenue Oracle pipeline:

  VideoLakeResult
    → ArtifactRecord (SQLite)
    → EvidencePacket (with claims, rights, provenance from VideoLake)
    → BMMABuilder.build_bmma() (grade, bond, segments, standards, receipt)
    → MediaAssetRecord (SQLite)

This is the concrete integration that makes the VideoLake output
financeable rather than just viewable. The VisualEvidenceSegment is
the novel primitive — not media, but claim + visual + truth + rights + receipt.

Usage:
  from broll import VideoLakeCompiler
  from revenue_oracle.videolake_bmma_bridge import VideoLakeBMMABridge

  compiler = VideoLakeCompiler()
  vlk_result = compiler.compile("Does Schumann resonance have measurable properties?")

  bridge = VideoLakeBMMABridge(db, receipt_ledger)
  bmma = bridge.import_videolake(vlk_result)
  # bmma is a BMMAResult with grade, bond, segments, receipt
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from .schema import OracleDB, ArtifactRecord, EvidencePacket
from .receipt_ledger import ReceiptLedger
from .evidence_packet import EvidencePacketBuilder
from .bmma_builder import BMMABuilder, BMMAResult


@dataclass
class VideoLakeBMMAImport:
    """Result of importing a VideoLake compilation into the Oracle."""
    artifact_id: str = ""
    packet_hash: str = ""
    bmma: Optional[BMMAResult] = None
    import_receipt_hash: str = ""
    status: str = ""

    def to_dict(self) -> dict:
        return {
            "artifact_id": self.artifact_id,
            "packet_hash": self.packet_hash,
            "bmma": self.bmma.to_dict() if self.bmma else None,
            "import_receipt_hash": self.import_receipt_hash,
            "status": self.status,
        }


class VideoLakeBMMABridge:
    """
    Bridge between VideoLake (broll/videolake.py) and the Revenue Oracle.

    Takes a compiled VideoLakeResult and:
    1. Creates an ArtifactRecord in the Oracle DB
    2. Builds an EvidencePacket from the VideoLake investigation data
    3. Runs the BMMA builder to produce a grade, bond, and media asset record
    4. Writes receipts for each step

    The VideoLake output becomes financeable: not just a video, but a
    Bonded Machine Media Asset with quality grade, audit probability,
    segment marketplace listings, and standards hashes.
    """

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger = None):
        self.db = db
        self.receipt_ledger = receipt_ledger or ReceiptLedger(db)
        self.packet_builder = EvidencePacketBuilder(db)
        self.bmma_builder = BMMABuilder(db, self.receipt_ledger)

    def import_videolake(self, vlk_result) -> VideoLakeBMMAImport:
        """
        Import a VideoLakeResult into the Oracle and build a BMMA.

        Args:
            vlk_result: VideoLakeResult from broll.videolake.VideoLakeCompiler.compile()

        Returns:
            VideoLakeBMMAImport with artifact_id, packet_hash, and BMMAResult
        """
        question = vlk_result.question or "unknown"
        investigation = vlk_result.investigation
        mevf = vlk_result.mevf
        vrap = vlk_result.vrap

        # 1. Create artifact from VideoLake output
        source_hash = hashlib.sha256(
            f"vlk:{question}:{vlk_result.receipt_hash}".encode()
        ).hexdigest()
        manifest_hash = hashlib.sha256(
            f"{source_hash}:videolake:{time.time()}".encode()
        ).hexdigest()
        artifact_id = hashlib.sha256(
            f"art:{source_hash}:{time.time()}".encode()
        ).hexdigest()[:16]

        artifact = ArtifactRecord(
            artifact_id=artifact_id,
            source_type="videolake_compilation",
            source_uri_or_path=vlk_result.output_dir or f"vlk://{question[:50]}",
            owner="videolake",
            created_at=time.time(),
            source_hash=source_hash,
            manifest_hash=manifest_hash,
        )
        self.db.insert_artifact(artifact)

        self.receipt_ledger.write(
            receipt_type="videolake_artifact_intake",
            artifact_id=artifact_id,
            data={
                "question": question,
                "source_hash": source_hash,
                "vlk_receipt_hash": vlk_result.receipt_hash,
                "bundle_files": len(vlk_result.bundle),
                "bundle_size": vlk_result.total_size_bytes,
            },
            output_hash=f"sha256:{source_hash[:16]}",
        )

        # 2. Build evidence packet from investigation + MEVF data
        claims = []
        if investigation:
            for c in investigation.claims:
                claims.append({
                    "claim_id": hashlib.sha256(
                        f"claim:{c.claim_text[:50]}:{artifact_id}".encode()
                    ).hexdigest()[:16],
                    "text": c.claim_text,
                    "type": c.status.value if hasattr(c.status, 'value') else str(c.status),
                    "confidence": c.confidence,
                    "evidence_hash": c.receipt_hash or source_hash,
                })

        risk_flags = []
        license_flags = []
        provenance_chain = []

        if investigation:
            provenance_chain.append({
                "step": "investigation",
                "investigation_id": investigation.investigation_id,
                "receipt_hash": investigation.receipt_hash,
            })

        if mevf:
            provenance_chain.append({
                "step": "mevf_compilation",
                "mevf_id": mevf.mevf_id,
                "receipt_hash": mevf.receipt_hash,
                "segment_count": len(mevf.segments),
            })

        if vrap:
            provenance_chain.append({
                "step": "vrap_manifest",
                "trust_grade": vrap.trust_grade,
                "avg_buyability": vrap.avg_machine_buyability,
            })

        # Extract rights info from MEVF segments
        rights_labels = []
        truth_labels = []
        visual_evidence_segments = []

        if mevf:
            for seg in mevf.segments:
                rights_labels.append(seg.rights_status)
                truth_labels.append(seg.claim_status)
                visual_evidence_segments.append({
                    "segment_id": seg.segment_id,
                    "claim": seg.claim,
                    "rights_status": seg.rights_status,
                    "license_type": seg.license_type,
                    "visual_type": seg.visual_type,
                    "duration_seconds": seg.duration_seconds,
                    "is_for_sale": seg.is_for_sale,
                    "price_per_render": seg.price_per_render,
                    "scores": seg.scores.to_dict(),
                })

        # License flags from rights
        unsafe_count = sum(1 for r in rights_labels if r not in ("safe", "fair_use"))
        if unsafe_count > 0:
            license_flags.append({
                "flag": "rights_review_needed",
                "status": "needs_review",
                "detail": f"{unsafe_count} segments with non-safe rights status",
            })

        packet = self.packet_builder.build_packet(
            artifact=artifact,
            claims=claims,
            risk_flags=risk_flags,
            license_flags=license_flags,
            provenance_chain=provenance_chain,
            reproducibility_notes=f"VideoLake compilation with {len(visual_evidence_segments)} segments",
            limitations="Video is placeholder; evidence graph is the asset",
        )

        self.receipt_ledger.write(
            receipt_type="videolake_packet_built",
            artifact_id=artifact_id,
            data={
                "packet_hash": packet.packet_hash,
                "claim_count": len(claims),
                "segment_count": len(visual_evidence_segments),
            },
            output_hash=packet.packet_hash,
        )

        # 3. Build BMMA from the packet + VideoLake data
        machine_scores = {}
        if mevf:
            machine_scores = {
                "evidence_strength": mevf.avg_machine_buyability,
                "rights_safety": 1.0 - (unsafe_count / max(len(rights_labels), 1)),
                "machine_buyability": mevf.avg_machine_buyability,
                "trust_grade": mevf.trust_grade,
            }
        if vrap:
            machine_scores["avg_buyability"] = vrap.avg_machine_buyability
            machine_scores["total_price"] = vrap.total_price_usd

        revenue_ledger = {}
        if vrap and vrap.total_price_usd > 0:
            revenue_ledger = {
                "total_price_usd": vrap.total_price_usd,
                "license_summary": vrap.license_summary,
                "segment_count": len(visual_evidence_segments),
            }

        transcript = mevf.transcript if mevf else ""

        bmma_result = self.bmma_builder.build_bmma(
            artifact=artifact.to_dict(),
            packet=packet.to_dict(),
            question=question,
            claims=claims,
            transcript=transcript,
            visual_evidence_segments=visual_evidence_segments,
            truth_labels=truth_labels,
            rights_labels=rights_labels,
            revenue_ledger=revenue_ledger,
            machine_scores=machine_scores,
            rubric_id="video_evidence_quality_v1",
            producer_id="videolake",
        )

        import_receipt = self.receipt_ledger.write(
            receipt_type="videolake_bmma_imported",
            artifact_id=artifact_id,
            data={
                "bmma_id": bmma_result.bmma_id,
                "grade_claimed": bmma_result.grade_claimed,
                "grade_computed": bmma_result.grade_computed,
                "bond_required": bmma_result.bond_required,
                "segments_listed": bmma_result.segments_listed,
                "segments_available": bmma_result.segments_available,
                "packet_hash": packet.packet_hash,
                "vlk_receipt_hash": vlk_result.receipt_hash,
            },
            output_hash=bmma_result.receipt_hash,
        )

        return VideoLakeBMMAImport(
            artifact_id=artifact_id,
            packet_hash=packet.packet_hash,
            bmma=bmma_result,
            import_receipt_hash=import_receipt.receipt_hash,
            status="imported_and_bonded",
        )

    def import_from_dict(self, vlk_summary: dict) -> VideoLakeBMMAImport:
        """
        Import a VideoLake result from a summary dict (when the full
        VideoLakeResult object is not available, e.g. from a saved bundle).

        Expected fields: question, claims, segments, machine_scores, etc.
        """
        question = vlk_summary.get("question", "unknown")
        claims = vlk_summary.get("claims", [])
        segments = vlk_summary.get("segments", [])
        machine_scores = vlk_summary.get("machine_scores", {})

        source_hash = hashlib.sha256(
            f"vlk_dict:{question}:{json.dumps(vlk_summary, sort_keys=True)}".encode()
        ).hexdigest()
        manifest_hash = hashlib.sha256(
            f"{source_hash}:videolake:{time.time()}".encode()
        ).hexdigest()
        artifact_id = hashlib.sha256(
            f"art:{source_hash}:{time.time()}".encode()
        ).hexdigest()[:16]

        artifact = ArtifactRecord(
            artifact_id=artifact_id,
            source_type="videolake_summary",
            source_uri_or_path=vlk_summary.get("output_dir", ""),
            owner="videolake",
            created_at=time.time(),
            source_hash=source_hash,
            manifest_hash=manifest_hash,
        )
        self.db.insert_artifact(artifact)

        rights_labels = [s.get("rights_status", "unknown") for s in segments]
        truth_labels = [s.get("claim_status", "unverified") for s in segments]

        packet = self.packet_builder.build_packet(
            artifact=artifact,
            claims=claims,
            provenance_chain=[{"step": "videolake_summary_import"}],
        )

        bmma_result = self.bmma_builder.build_bmma(
            artifact=artifact.to_dict(),
            packet=packet.to_dict(),
            question=question,
            claims=claims,
            visual_evidence_segments=segments,
            truth_labels=truth_labels,
            rights_labels=rights_labels,
            machine_scores=machine_scores,
            producer_id="videolake",
        )

        return VideoLakeBMMAImport(
            artifact_id=artifact_id,
            packet_hash=packet.packet_hash,
            bmma=bmma_result,
            status="imported_from_dict",
        )
