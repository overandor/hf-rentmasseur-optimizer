"""
Machine Evidence Video Format (MEVF)

A MEVF object is not just an .mp4. It is:

    mp4
    + transcript
    + claim graph
    + evidence graph
    + visual evidence segments
    + rights graph
    + provenance graph
    + source graph
    + embeddings
    + confidence scores
    + receipts
    + market terms

For humans, it looks like a documentary, investigation, short, lecture,
or screen-recorded research journey.

For machines, it is a structured package that says:

    Claim A occurs at 00:01:42
    Claim A is speculative
    Claim A is supported by papers X and Y
    Claim A is contradicted by paper Z
    Clip B visually illustrates Claim A
    Clip B has rights status: needs review
    Graph C was generated from reproduction attempt D
    Receipt hash E proves the transformation chain
    Embedding vector F allows semantic retrieval
    License G allows reuse under condition H

The saleable object becomes the MEVF Segment — each segment can be
priced, queried, reused, ranked, licensed, and bought by another agent.

A machine buyer asks:
    "Give me verified visual evidence segments about Schumann resonance with:
     confidence > 0.7, rights_status = safe, source_quality > 0.8,
     duration < 12 seconds, machine provenance complete"
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from .machine_scores import MachineScoreSet, compute_all_machine_scores
from .scientific_claim import ScientificClaim, ScientificStatus
from .investigation_graph import InvestigationGraph


@dataclass
class MEVFSegment:
    """
    A single Machine Evidence Video Format segment.

    This is the saleable, queryable, reusable unit. Each segment is:
        claim + visual + scores + rights + provenance + receipt + market terms

    A machine buyer can query, filter, price, and purchase segments.
    """
    segment_id: str = ""
    claim: str = ""
    claim_status: str = "unverified"
    not_status: str = ""  # What the claim does NOT prove (important for honest representation)
    visual_description: str = ""
    visual_type: str = "footage"  # footage, simulation, diagram, experiment
    source: str = ""
    source_url: str = ""
    rights_status: str = "unknown"
    license_type: str = "unknown"
    duration_seconds: float = 10.0
    timestamp_in_video: float = 0.0  # When this segment appears in the full video

    # Six machine scores
    scores: MachineScoreSet = field(default_factory=MachineScoreSet)

    # Provenance
    receipt_hash: str = ""
    investigation_id: str = ""
    source_paper_title: str = ""
    source_paper_doi: str = ""

    # Market terms
    price_per_render: float = 0.0
    license_terms: str = ""  # "machine reuse allowed", "attribution required", etc.
    is_for_sale: bool = False

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "claim": self.claim,
            "claim_status": self.claim_status,
            "not_status": self.not_status,
            "visual_description": self.visual_description,
            "visual_type": self.visual_type,
            "source": self.source,
            "source_url": self.source_url,
            "rights_status": self.rights_status,
            "license_type": self.license_type,
            "duration_seconds": self.duration_seconds,
            "timestamp_in_video": self.timestamp_in_video,
            "scores": self.scores.to_dict(),
            "receipt_hash": self.receipt_hash,
            "investigation_id": self.investigation_id,
            "source_paper_title": self.source_paper_title,
            "source_paper_doi": self.source_paper_doi,
            "price_per_render": self.price_per_render,
            "license_terms": self.license_terms,
            "is_for_sale": self.is_for_sale,
        }

    def to_machine_query(self) -> dict:
        """
        Machine-queryable format for agent marketplace.

        A machine buyer filters on these fields:
        """
        return {
            "segment_id": self.segment_id,
            "claim": self.claim,
            "claim_status": self.claim_status,
            "rights_status": self.rights_status,
            "trust_grade": self.scores.trust_grade,
            "machine_buyability_score": self.scores.machine_buyability_score,
            "is_machine_buyable": self.scores.is_machine_buyable,
            "duration_seconds": self.duration_seconds,
            "is_for_sale": self.is_for_sale,
            "price_per_render": self.price_per_render,
            "license_terms": self.license_terms,
            "receipt_hash": self.receipt_hash,
        }


@dataclass
class MEVFObject:
    """
    A complete Machine Evidence Video Format object.

    This is the full package: video + structured metadata + machine manifest.

    For humans: renders as a video (documentary, investigation, lecture, etc.)
    For machines: renders as a structured proof packet

    The object bundles:
        - transcript
        - claim graph (all claims with statuses)
        - evidence graph (supporting, counter, missing)
        - visual evidence segments (with 6 machine scores each)
        - rights graph
        - provenance graph (source chain)
        - confidence scores
        - receipts (hash chain)
        - market terms (pricing, licensing)
    """
    mevf_id: str = ""
    title: str = ""
    question: str = ""
    investigation_id: str = ""
    timestamp: float = 0.0

    # Content
    transcript: str = ""
    segments: list[MEVFSegment] = field(default_factory=list)

    # Graphs (serialized from InvestigationGraph)
    claim_graph: dict = field(default_factory=dict)
    evidence_graph: dict = field(default_factory=dict)
    rights_graph: dict = field(default_factory=dict)
    provenance_graph: dict = field(default_factory=dict)

    # Aggregate scores
    avg_machine_buyability: float = 0.0
    trust_grade: str = "F"

    # Receipts
    receipt_hash: str = ""
    proof_chain_hash: str = ""

    # Market
    total_price: float = 0.0
    license_summary: str = ""

    # Render info
    video_duration_seconds: float = 0.0
    output_formats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "mevf_id": self.mevf_id,
            "title": self.title,
            "question": self.question,
            "investigation_id": self.investigation_id,
            "timestamp": self.timestamp,
            "transcript": self.transcript,
            "segments": [s.to_dict() for s in self.segments],
            "claim_graph": self.claim_graph,
            "evidence_graph": self.evidence_graph,
            "rights_graph": self.rights_graph,
            "provenance_graph": self.provenance_graph,
            "avg_machine_buyability": round(self.avg_machine_buyability, 3),
            "trust_grade": self.trust_grade,
            "receipt_hash": self.receipt_hash,
            "proof_chain_hash": self.proof_chain_hash,
            "total_price": self.total_price,
            "license_summary": self.license_summary,
            "video_duration_seconds": self.video_duration_seconds,
            "output_formats": self.output_formats,
            "segment_count": len(self.segments),
            "machine_buyable_count": sum(1 for s in self.segments if s.scores.is_machine_buyable),
        }

    def to_machine_manifest(self) -> dict:
        """
        Machine-readable manifest for agent consumption.

        This is what a machine sees instead of a video.
        """
        return {
            "mevf_id": self.mevf_id,
            "title": self.title,
            "question": self.question,
            "trust_grade": self.trust_grade,
            "avg_machine_buyability": round(self.avg_machine_buyability, 3),
            "segment_count": len(self.segments),
            "machine_buyable_count": sum(1 for s in self.segments if s.scores.is_machine_buyable),
            "segments": [s.to_machine_query() for s in self.segments],
            "receipt_hash": self.receipt_hash,
            "total_price": self.total_price,
            "license_summary": self.license_summary,
            "video_duration_seconds": self.video_duration_seconds,
        }

    def to_json(self, path: str | None = None) -> str:
        data = json.dumps(self.to_dict(), indent=2)
        if path:
            with open(path, "w") as f:
                f.write(data)
        return data


class MEVFBuilder:
    """
    Builds MEVF objects from InvestigationGraphs.

    Takes an investigation and compiles it into a Machine Evidence Video
    Format object — the unified media+evidence package.

    Usage:
        builder = MEVFBuilder()
        mevf = builder.build(investigation)
        print(mevf.trust_grade, mevf.avg_machine_buyability)
        manifest = mevf.to_machine_manifest()
    """

    def __init__(self):
        self.segment_counter = 0

    def build(
        self,
        investigation: InvestigationGraph,
        title: str | None = None,
        output_formats: list[str] | None = None,
    ) -> MEVFObject:
        """
        Build a MEVF object from an investigation.

        For each scientific claim, creates a MEVF Segment with:
            - claim + status + not_status
            - visual description
            - 6 machine scores
            - provenance
            - market terms
        """
        self.segment_counter = 0
        mevf_id = hashlib.sha256(
            f"{investigation.investigation_id}:{time.time()}".encode()
        ).hexdigest()[:16]

        mevf = MEVFObject(
            mevf_id=mevf_id,
            title=title or investigation.question[:80],
            question=investigation.question,
            investigation_id=investigation.investigation_id,
            timestamp=time.time(),
            output_formats=output_formats or ["video", "blog", "report", "podcast"],
        )

        # Build claim graph
        mevf.claim_graph = {
            "question": investigation.question,
            "claims": [c.to_dict() for c in investigation.claims],
            "conclusions": investigation.conclusions,
        }

        # Build evidence graph
        mevf.evidence_graph = {
            "total_papers": len(investigation.papers),
            "total_claims": len(investigation.claims),
            "verified_claims": len(investigation.get_verified_claims()),
            "disputed_claims": len(investigation.get_disputed_claims()),
            "avg_confidence": investigation.stats.get("avg_confidence", 0.0),
        }

        # Build rights graph
        mevf.rights_graph = {
            "default_status": "needs_review",
            "local_footage_safe": True,
            "youtube_footage_needs_review": True,
            "generated_content_safe": True,
        }

        # Build provenance graph
        mevf.provenance_graph = {
            "investigation_id": investigation.investigation_id,
            "search_count": len(investigation.searches),
            "paper_count": len(investigation.papers),
            "step_count": len(investigation.steps),
            "receipt_hash": investigation.receipt_hash,
            "sources": [s.source for s in investigation.searches],
        }

        # Create segments from claims
        for claim in investigation.claims:
            segment = self._create_segment(claim, investigation)
            mevf.segments.append(segment)

        # Compute aggregate scores
        if mevf.segments:
            buyable_scores = [s.scores.machine_buyability_score for s in mevf.segments]
            mevf.avg_machine_buyability = sum(buyable_scores) / len(buyable_scores)
            mevf.trust_grade = self._compute_grade(mevf.avg_machine_buyability)
            mevf.total_price = sum(s.price_per_render for s in mevf.segments if s.is_for_sale)
            mevf.video_duration_seconds = sum(s.duration_seconds for s in mevf.segments)

        # Determine license summary
        buyable = sum(1 for s in mevf.segments if s.scores.is_machine_buyable)
        total = len(mevf.segments)
        mevf.license_summary = f"{buyable}/{total} segments machine-buyable"

        # Compute receipt hash
        mevf.receipt_hash = f"sha256:{hashlib.sha256(
            json.dumps(mevf.to_dict(), sort_keys=True).encode()
        ).hexdigest()[:16]}"
        mevf.proof_chain_hash = investigation.receipt_hash

        return mevf

    def _create_segment(
        self,
        claim: ScientificClaim,
        investigation: InvestigationGraph,
    ) -> MEVFSegment:
        """Create a MEVF segment from a scientific claim."""
        self.segment_counter += 1
        segment_id = f"mevf_seg_{self.segment_counter:03d}"

        # Determine visual description based on claim content
        visual_desc = self._generate_visual_description(claim)
        visual_type = self._determine_visual_type(claim)

        # Determine rights status
        rights_status = "needs_review"
        if visual_type == "simulation":
            rights_status = "safe"  # Generated content is rights-safe
        elif visual_type == "diagram":
            rights_status = "safe"

        # Determine source
        source = "investigation"
        if claim.source_papers:
            source = claim.source_papers[0].source or "research"
        source_paper_title = claim.source_papers[0].title if claim.source_papers else ""
        source_paper_doi = claim.source_papers[0].doi if claim.source_papers else ""

        # Compute not_status (what the claim does NOT prove)
        not_status = self._compute_not_status(claim)

        # Compute machine scores
        truth_safety = self._truth_safety_from_status(claim.status)
        scores = compute_all_machine_scores(
            semantic_match=0.7,  # Would come from CLIP matching
            evidence_relevance=0.6,  # Would come from evidence scoring
            truth_safety=truth_safety,
            rights_status=rights_status,
            has_source=bool(source),
            has_source_paper=bool(claim.source_papers),
            has_receipt_hash=bool(claim.receipt_hash),
            has_proof_chain=bool(investigation.receipt_hash),
            has_citation=claim.citation_count > 0,
            has_author_info=any(p.authors for p in claim.source_papers),
            has_timestamp=True,
            has_investigation_id=True,
            scientific_status=claim.status.value,
            has_receipt=True,
            duration_seconds=10.0,
        )

        # Market terms
        price = 0.0
        is_for_sale = False
        if scores.is_machine_buyable and rights_status == "safe":
            price = 0.03 if claim.status.value in ("verified", "replicated") else 0.01
            is_for_sale = True

        license_terms = ""
        if rights_status == "safe":
            license_terms = "machine reuse allowed"
        elif rights_status == "needs_review":
            license_terms = "requires manual rights review before reuse"
        else:
            license_terms = "blocked — no reuse permitted"

        return MEVFSegment(
            segment_id=segment_id,
            claim=claim.claim_text,
            claim_status=claim.status.value,
            not_status=not_status,
            visual_description=visual_desc,
            visual_type=visual_type,
            source=source,
            rights_status=rights_status,
            license_type="unknown" if rights_status == "needs_review" else "owned",
            duration_seconds=10.0,
            timestamp_in_video=(self.segment_counter - 1) * 10.0,
            scores=scores,
            receipt_hash=claim.receipt_hash or f"sha256:{hashlib.sha256(claim.claim_text.encode()).hexdigest()[:16]}",
            investigation_id=investigation.investigation_id,
            source_paper_title=source_paper_title,
            source_paper_doi=source_paper_doi,
            price_per_render=price,
            license_terms=license_terms,
            is_for_sale=is_for_sale,
        )

    def _generate_visual_description(self, claim: ScientificClaim) -> str:
        """Generate a visual description for a claim."""
        claim_lower = claim.claim_text.lower()
        if "resonance" in claim_lower:
            return "Standing wave animation showing resonance pattern in ancient structure"
        elif "energy" in claim_lower:
            return "Electromagnetic field visualization around ancient site"
        elif "earth" in claim_lower:
            return "3D Earth globe with electromagnetic field lines"
        elif "ancient" in claim_lower or "stone" in claim_lower:
            return "Documentary footage of ancient stone structures"
        else:
            return f"Visual representation of: {claim.claim_text[:60]}"

    def _determine_visual_type(self, claim: ScientificClaim) -> str:
        """Determine the visual type for a claim."""
        claim_lower = claim.claim_text.lower()
        if any(w in claim_lower for w in ["resonance", "frequency", "field", "energy"]):
            return "simulation"
        elif any(w in claim_lower for w in ["measurement", "data", "analysis"]):
            return "diagram"
        elif any(w in claim_lower for w in ["experiment", "test", "reproduction"]):
            return "experiment"
        else:
            return "footage"

    def _compute_not_status(self, claim: ScientificClaim) -> str:
        """
        Compute what the claim does NOT prove.

        This is critical for honest representation — the system must
        distinguish between what is shown and what is not shown.
        """
        if claim.status == ScientificStatus.VERIFIED:
            return "verified phenomenon — does not imply all related claims are also verified"
        elif claim.status == ScientificStatus.REPLICATED:
            return "replicated result — does not imply mechanism is fully understood"
        elif claim.status == ScientificStatus.PARTIALLY_REPLICATED:
            return "partially replicated — does not constitute full verification"
        elif claim.status == ScientificStatus.DISPUTED:
            return "disputed claim — does not represent scientific consensus"
        elif claim.status == ScientificStatus.SPECULATIVE:
            return "speculative — does not prove the phenomenon exists"
        elif claim.status == ScientificStatus.UNVERIFIED:
            return "unverified — no evidence found either way"
        elif claim.status == ScientificStatus.RETRACTED:
            return "retracted — original source withdrew the claim"
        return "unknown status"

    def _truth_safety_from_status(self, status: ScientificStatus) -> float:
        """Map scientific status to truth safety score."""
        mapping = {
            ScientificStatus.VERIFIED: 1.0,
            ScientificStatus.REPLICATED: 0.9,
            ScientificStatus.PARTIALLY_REPLICATED: 0.5,
            ScientificStatus.DISPUTED: 0.3,
            ScientificStatus.SPECULATIVE: 0.2,
            ScientificStatus.UNVERIFIED: 0.1,
            ScientificStatus.RETRACTED: 0.0,
        }
        return mapping.get(status, 0.1)

    def _compute_grade(self, score: float) -> str:
        """Compute trust grade from buyability score."""
        if score >= 0.9:
            return "A"
        elif score >= 0.8:
            return "B"
        elif score >= 0.7:
            return "C"
        elif score >= 0.5:
            return "D"
        else:
            return "F"


def query_segments(
    mevf: MEVFObject,
    min_confidence: float = 0.0,
    rights_status: str | None = None,
    min_buyability: float = 0.0,
    max_duration: float = float("inf"),
    scientific_status: str | None = None,
    for_sale_only: bool = False,
) -> list[MEVFSegment]:
    """
    Query MEVF segments with machine filters.

    This is what a machine buyer uses:
        "Give me verified visual evidence segments about Schumann resonance with:
         confidence > 0.7, rights_status = safe, duration < 12 seconds"
    """
    results = []
    for seg in mevf.segments:
        if min_confidence > 0 and seg.scores.truth_safety_score < min_confidence:
            continue
        if rights_status and seg.rights_status != rights_status:
            continue
        if min_buyability > 0 and seg.scores.machine_buyability_score < min_buyability:
            continue
        if seg.duration_seconds > max_duration:
            continue
        if scientific_status and seg.claim_status != scientific_status:
            continue
        if for_sale_only and not seg.is_for_sale:
            continue
        results.append(seg)
    return results
