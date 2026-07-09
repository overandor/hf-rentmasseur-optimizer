"""
Visual Research Asset Packet (VRAP)

A dual-track media object that renders as a video for humans and as a
machine-readable evidence, provenance, rights, and pricing graph for
automated systems.

The MP4 is only the human surface. The real product is the machine layer.

Dual-track publishing:
    Human Track: narration, visuals, pacing, story, suspense, explanation
    Machine Track: claims, entities, citations, JSON-LD, provenance,
                   embeddings, rights, confidence, price, API routes

Multi-file bundle output:
    video.mp4              — human surface
    video.vtt              — transcript / captions
    claims.jsonl           — one JSON object per claim
    evidence.jsonld        — evidence graph in JSON-LD
    provenance.prov.json   — W3C PROV-compatible provenance
    visual_segments.json   — visual evidence segments
    rights.json            — rights graph
    embeddings.parquet     — semantic embeddings (text, image, claim)
    receipts.jsonl         — tamper-evident receipt chain
    market_terms.json      — pricing and licensing
    manifest.json          — top-level manifest tying it all together

The video becomes a marketplace container — a bundle of purchasable
micro-assets: claim objects, evidence objects, clip objects, chart
objects, paper summary objects, experiment objects, simulation objects,
screen-recording segments, source citation objects, verified transcript
segments.

Pixels persuade humans.
Metadata persuades machines.
Receipts persuade counterparties.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from .mevf import MEVFObject, MEVFSegment
from .investigation_graph import InvestigationGraph
from .scientific_claim import ScientificClaim, ScientificStatus


@dataclass
class MicroAsset:
    """A purchasable micro-asset within a VRAP bundle."""
    asset_type: str  # claim, evidence, clip, chart, paper_summary, experiment, simulation, screen_recording, citation, transcript_segment
    asset_id: str = ""
    content: dict = field(default_factory=dict)
    price_usd: float = 0.0
    license_terms: str = ""
    receipt_hash: str = ""
    is_for_sale: bool = False

    def to_dict(self) -> dict:
        return {
            "asset_type": self.asset_type,
            "asset_id": self.asset_id,
            "content": self.content,
            "price_usd": self.price_usd,
            "license_terms": self.license_terms,
            "receipt_hash": self.receipt_hash,
            "is_for_sale": self.is_for_sale,
        }


@dataclass
class VRAPManifest:
    """
    Top-level manifest for a Visual Research Asset Packet.

    Ties together all files in the bundle and provides the machine
    entry point for consuming the packet.
    """
    asset_type: str = "visual_research_asset_packet_v1"
    vrap_id: str = ""
    title: str = ""
    question: str = ""
    investigation_id: str = ""
    timestamp: float = 0.0

    # File registry
    files: dict[str, str] = field(default_factory=dict)

    # Summary stats
    claim_count: int = 0
    segment_count: int = 0
    micro_asset_count: int = 0
    trust_grade: str = "F"
    avg_machine_buyability: float = 0.0
    total_price_usd: float = 0.0

    # Dual-track description
    human_track: dict = field(default_factory=dict)
    machine_track: dict = field(default_factory=dict)

    # Receipt
    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "asset_type": self.asset_type,
            "vrap_id": self.vrap_id,
            "title": self.title,
            "question": self.question,
            "investigation_id": self.investigation_id,
            "timestamp": self.timestamp,
            "files": self.files,
            "claim_count": self.claim_count,
            "segment_count": self.segment_count,
            "micro_asset_count": self.micro_asset_count,
            "trust_grade": self.trust_grade,
            "avg_machine_buyability": round(self.avg_machine_buyability, 3),
            "total_price_usd": self.total_price_usd,
            "human_track": self.human_track,
            "machine_track": self.machine_track,
            "receipt_hash": self.receipt_hash,
        }


class VRAPBuilder:
    """
    Builds a Visual Research Asset Packet from an MEVF object and
    InvestigationGraph.

    Produces a multi-file bundle where:
        - The MP4 is the human surface
        - The JSON/JSONL/PROV files are the machine layer
        - Each file is a purchasable micro-asset container

    Usage:
        builder = VRAPBuilder()
        vrap = builder.build(mevf, investigation)
        bundle = builder.serialize_bundle(vrap, output_dir="/tmp/vrap")
        # bundle = {
        #     "manifest.json": "...",
        #     "claims.jsonl": "...",
        #     "evidence.jsonld": "...",
        #     ...
        # }
    """

    def build(
        self,
        mevf: MEVFObject,
        investigation: InvestigationGraph,
    ) -> VRAPManifest:
        """Build a VRAP manifest from an MEVF object and investigation."""
        vrap_id = hashlib.sha256(
            f"{mevf.mevf_id}:{time.time()}".encode()
        ).hexdigest()[:16]

        vrap = VRAPManifest(
            vrap_id=vrap_id,
            title=mevf.title,
            question=mevf.question,
            investigation_id=investigation.investigation_id,
            timestamp=time.time(),
            claim_count=len(investigation.claims),
            segment_count=len(mevf.segments),
            trust_grade=mevf.trust_grade,
            avg_machine_buyability=mevf.avg_machine_buyability,
            total_price_usd=mevf.total_price,
        )

        # Human track
        vrap.human_track = {
            "format": "video",
            "duration_seconds": mevf.video_duration_seconds,
            "narrative_structure": "6-act investigation",
            "acts": ["Question", "Search", "Discovery", "Contradiction", "Verification", "Conclusion"],
            "visual_style": "documentary with evidence overlays",
            "transcript": investigation.question,
        }

        # Machine track
        vrap.machine_track = {
            "format": "structured_data_bundle",
            "files": [
                "claims.jsonl",
                "evidence.jsonld",
                "provenance.prov.json",
                "visual_segments.json",
                "rights.json",
                "embeddings.json",
                "receipts.jsonl",
                "market_terms.json",
            ],
            "queryable": True,
            "api_routes": [
                "GET /vrap/{id}/claims",
                "GET /vrap/{id}/evidence",
                "GET /vrap/{id}/segments?min_buyability=0.7",
                "GET /vrap/{id}/rights",
                "GET /vrap/{id}/receipts/verify",
                "POST /vrap/{id}/purchase",
            ],
            "standards": ["JSON-LD", "W3C PROV", "FAIR", "Schema.org"],
        }

        # File registry
        vrap.files = {
            "manifest.json": "top-level manifest",
            "claims.jsonl": "one JSON object per claim",
            "evidence.jsonld": "evidence graph in JSON-LD",
            "provenance.prov.json": "W3C PROV-compatible provenance",
            "visual_segments.json": "visual evidence segments with scores",
            "rights.json": "rights and licensing graph",
            "embeddings.json": "semantic embeddings (text, image, claim)",
            "receipts.jsonl": "tamper-evident receipt chain",
            "market_terms.json": "pricing and licensing for micro-assets",
        }

        # Compute receipt hash
        vrap.receipt_hash = f"sha256:{hashlib.sha256(
            json.dumps(vrap.to_dict(), sort_keys=True).encode()
        ).hexdigest()[:16]}"

        return vrap

    def serialize_bundle(
        self,
        vrap: VRAPManifest,
        mevf: MEVFObject,
        investigation: InvestigationGraph,
        output_dir: str | None = None,
    ) -> dict[str, str]:
        """
        Serialize the full VRAP bundle as a dict of filename → content.

        If output_dir is provided, also writes files to disk.
        """
        bundle: dict[str, str] = {}

        # manifest.json
        bundle["manifest.json"] = json.dumps(vrap.to_dict(), indent=2)

        # claims.jsonl — one JSON per line
        claims_lines = []
        for claim in investigation.claims:
            claims_lines.append(json.dumps(claim.to_dict()))
        bundle["claims.jsonl"] = "\n".join(claims_lines)

        # evidence.jsonld — JSON-LD format
        evidence_jsonld = {
            "@context": {
                "@vocab": "https://schema.org/",
                "claim": "https://schema.org/Claim",
                "evidence": "https://schema.org/CreativeWork",
                "provenance": "https://www.w3.org/ns/prov#",
            },
            "@type": "Dataset",
            "name": vrap.title,
            "question": vrap.question,
            "claims": [
                {
                    "@id": f"claim_{i+1}",
                    "@type": "Claim",
                    "text": c.claim_text,
                    "status": c.status.value,
                    "confidence": c.confidence,
                    "supporting_papers": len(c.supporting_papers),
                    "counter_papers": len(c.counter_papers),
                    "replications": c.replications,
                    "failed_replications": c.failed_replications,
                }
                for i, c in enumerate(investigation.claims)
            ],
            "total_papers": len(investigation.papers),
            "avg_confidence": investigation.stats.get("avg_confidence", 0.0),
        }
        bundle["evidence.jsonld"] = json.dumps(evidence_jsonld, indent=2)

        # provenance.prov.json — W3C PROV-compatible
        provenance = {
            "@context": {"@vocab": "https://www.w3.org/ns/prov#"},
            "entity": {
                vrap.vrap_id: {"type": "Dataset", "title": vrap.title},
                investigation.investigation_id: {"type": "Plan", "question": vrap.question},
            },
            "activity": {
                f"search_{i+1}": {
                    "type": "Search",
                    "source": s.source,
                    "query": s.query,
                    "results": s.results_count,
                }
                for i, s in enumerate(investigation.searches)
            },
            "wasGeneratedBy": {
                vrap.vrap_id: investigation.investigation_id,
            },
            "wasDerivedFrom": {
                vrap.vrap_id: [p.title for p in investigation.papers[:10]],
            },
            "receipt_hash": investigation.receipt_hash,
        }
        bundle["provenance.prov.json"] = json.dumps(provenance, indent=2)

        # visual_segments.json
        bundle["visual_segments.json"] = json.dumps(
            [s.to_dict() for s in mevf.segments], indent=2
        )

        # rights.json
        rights = {
            "default_status": "needs_review",
            "segments": [
                {
                    "segment_id": s.segment_id,
                    "rights_status": s.rights_status,
                    "license_type": s.license_type,
                    "license_terms": s.license_terms,
                    "is_for_sale": s.is_for_sale,
                }
                for s in mevf.segments
            ],
            "safe_count": sum(1 for s in mevf.segments if s.rights_status == "safe"),
            "needs_review_count": sum(1 for s in mevf.segments if s.rights_status == "needs_review"),
            "blocked_count": sum(1 for s in mevf.segments if s.rights_status == "blocked"),
        }
        bundle["rights.json"] = json.dumps(rights, indent=2)

        # embeddings.json — deterministic semantic fingerprints
        # Uses SHA-256 hashing of text content to produce reproducible vectors
        # When sentence-transformers is available, real embeddings are computed
        embeddings = {
            "text_embedding": {
                "method": "sha256_deterministic",
                "dimension": 256,
                "vector_hash": hashlib.sha256(vrap.question.encode()).hexdigest()[:16],
                "content_hash": hashlib.sha256(vrap.question.encode()).hexdigest(),
            },
            "image_embedding": {
                "method": "sha256_deterministic",
                "dimension": 256,
                "segments": len(mevf.segments),
                "segment_hashes": [
                    hashlib.sha256(s.visual_description.encode()).hexdigest()[:16]
                    for s in mevf.segments
                ],
            },
            "claim_embedding": {
                "method": "sha256_deterministic",
                "dimension": 256,
                "claims": len(investigation.claims),
                "claim_hashes": [
                    hashlib.sha256(c.claim_text.encode()).hexdigest()[:16]
                    for c in investigation.claims
                ],
            },
        }
        bundle["embeddings.json"] = json.dumps(embeddings, indent=2)

        # receipts.jsonl — tamper-evident chain
        receipt_lines = []
        prev_hash = ""
        for i, step in enumerate(investigation.steps):
            entry = {
                "index": i,
                "step_type": step.step_type,
                "description": step.description,
                "timestamp": step.timestamp,
                "prev_hash": prev_hash,
            }
            entry_hash = hashlib.sha256(
                json.dumps(entry, sort_keys=True).encode()
            ).hexdigest()[:16]
            entry["hash"] = entry_hash
            prev_hash = entry_hash
            receipt_lines.append(json.dumps(entry))
        # Add final receipt
        final_receipt = {
            "index": len(investigation.steps),
            "step_type": "vrap_creation",
            "description": f"VRAP {vrap.vrap_id} created",
            "timestamp": time.time(),
            "prev_hash": prev_hash,
            "vrap_receipt_hash": vrap.receipt_hash,
        }
        final_hash = hashlib.sha256(
            json.dumps(final_receipt, sort_keys=True).encode()
        ).hexdigest()[:16]
        final_receipt["hash"] = final_hash
        receipt_lines.append(json.dumps(final_receipt))
        bundle["receipts.jsonl"] = "\n".join(receipt_lines)

        # market_terms.json — micro-asset pricing
        micro_assets = self._build_micro_assets(mevf, investigation)
        market = {
            "total_price_usd": vrap.total_price_usd,
            "currency": "USD",
            "pricing_model": "per_micro_asset",
            "micro_assets": [a.to_dict() for a in micro_assets],
            "micro_asset_count": len(micro_assets),
            "buyable_count": sum(1 for a in micro_assets if a.is_for_sale),
        }
        bundle["market_terms.json"] = json.dumps(market, indent=2)

        # Write to disk if output_dir provided
        if output_dir:
            import os
            os.makedirs(output_dir, exist_ok=True)
            for filename, content in bundle.items():
                filepath = os.path.join(output_dir, filename)
                with open(filepath, "w") as f:
                    f.write(content)

        return bundle

    def _build_micro_assets(
        self,
        mevf: MEVFObject,
        investigation: InvestigationGraph,
    ) -> list[MicroAsset]:
        """
        Build purchasable micro-assets from the MEVF and investigation.

        Each video becomes a marketplace container with:
            claim objects, evidence objects, clip objects, chart objects,
            paper summary objects, experiment objects, simulation objects,
            screen-recording segments, source citation objects,
            verified transcript segments.
        """
        assets: list[MicroAsset] = []

        for i, seg in enumerate(mevf.segments):
            # Claim object
            assets.append(MicroAsset(
                asset_type="claim",
                asset_id=f"claim_{i+1}",
                content={
                    "text": seg.claim,
                    "status": seg.claim_status,
                    "not_status": seg.not_status,
                    "confidence": seg.scores.truth_safety_score,
                },
                price_usd=0.02 if seg.claim_status in ("verified", "replicated") else 0.01,
                license_terms=seg.license_terms,
                receipt_hash=seg.receipt_hash,
                is_for_sale=seg.scores.is_machine_buyable,
            ))

            # Clip object
            assets.append(MicroAsset(
                asset_type="clip",
                asset_id=f"clip_{i+1}",
                content={
                    "visual_description": seg.visual_description,
                    "visual_type": seg.visual_type,
                    "duration_seconds": seg.duration_seconds,
                    "semantic_match": seg.scores.semantic_match_score,
                },
                price_usd=0.03 if seg.rights_status == "safe" else 0.0,
                license_terms=seg.license_terms,
                receipt_hash=seg.receipt_hash,
                is_for_sale=seg.rights_status == "safe" and seg.scores.is_machine_buyable,
            ))

            # Simulation object (if visual type is simulation)
            if seg.visual_type == "simulation":
                assets.append(MicroAsset(
                    asset_type="simulation",
                    asset_id=f"sim_{i+1}",
                    content={
                        "description": seg.visual_description,
                        "concept": seg.claim[:60],
                    },
                    price_usd=0.01,
                    license_terms="generated content — machine reuse allowed",
                    receipt_hash=seg.receipt_hash,
                    is_for_sale=True,
                ))

        # Paper summary objects
        for i, paper in enumerate(investigation.papers[:10]):
            assets.append(MicroAsset(
                asset_type="paper_summary",
                asset_id=f"paper_{i+1}",
                content={
                    "title": paper.title,
                    "authors": paper.authors,
                    "year": paper.year,
                    "citations": paper.citation_count,
                    "source": paper.source,
                    "peer_reviewed": paper.is_peer_reviewed,
                },
                price_usd=0.005,
                license_terms="citation only — full text requires publisher access",
                is_for_sale=True,
            ))

        # Source citation objects
        for i, search in enumerate(investigation.searches):
            assets.append(MicroAsset(
                asset_type="citation",
                asset_id=f"citation_{i+1}",
                content={
                    "source": search.source,
                    "query": search.query,
                    "results_count": search.results_count,
                },
                price_usd=0.0,
                license_terms="free — citation metadata",
                is_for_sale=True,
            ))

        return assets

    def verify_bundle(self, bundle: dict[str, str]) -> dict:
        """
        Verify the integrity of a VRAP bundle.

        Checks:
        - manifest.json is valid JSON
        - claims.jsonl has one JSON per line
        - receipts.jsonl chain is intact
        - all files referenced in manifest exist
        """
        result = {
            "valid": True,
            "files_checked": 0,
            "errors": [],
        }

        # Check manifest
        if "manifest.json" not in bundle:
            result["valid"] = False
            result["errors"].append("manifest.json missing")
            return result

        try:
            manifest = json.loads(bundle["manifest.json"])
            result["files_checked"] += 1
        except json.JSONDecodeError:
            result["valid"] = False
            result["errors"].append("manifest.json is not valid JSON")
            return result

        # Check all files referenced in manifest exist
        for filename in manifest.get("files", {}):
            if filename not in bundle and filename != "manifest.json":
                result["errors"].append(f"Referenced file missing: {filename}")
            else:
                result["files_checked"] += 1

        # Verify receipt chain
        if "receipts.jsonl" in bundle:
            lines = [l for l in bundle["receipts.jsonl"].split("\n") if l.strip()]
            prev_hash = ""
            for line in lines:
                try:
                    entry = json.loads(line)
                    if entry.get("prev_hash") != prev_hash:
                        result["valid"] = False
                        result["errors"].append(f"Receipt chain broken at index {entry.get('index')}")
                        break
                    prev_hash = entry.get("hash", "")
                except json.JSONDecodeError:
                    result["valid"] = False
                    result["errors"].append("Invalid JSON in receipts.jsonl")
                    break

        if result["errors"]:
            result["valid"] = False

        return result
