"""
Investigation Visualizer — Seven visualization forms for MEVF.

Most videos visualize conclusions. This system visualizes epistemic state:
what is known, what is guessed, what is missing, what failed, what changed
the confidence score.

Seven visualization forms:

1. Claim Heatmap — which parts of the video are verified, disputed, speculative, unknown
2. Evidence Density Timeline — how much source-backed evidence appears per second
3. Contradiction Map — where sources disagree and which claims are unstable
4. Replication Ladder — claim → experiment → reproduction → failure → confidence shift
5. Rights Safety Timeline — which visual segments are safe, review-required, blocked, owned
6. Machine Trust Curve — how algorithmic confidence changes as the investigation unfolds
7. Uncertainty Cinema — a video where unknowns, gaps, and missing experiments are first-class visuals

Each visualization is a structured data object that a rendering engine
can turn into actual graphics. This module produces the data, not the pixels.
"""

import json
from dataclasses import dataclass, field
from typing import Optional

from .investigation_graph import InvestigationGraph
from .scientific_claim import ScientificClaim, ScientificStatus
from .mevf import MEVFObject, MEVFSegment


@dataclass
class VisualizationData:
    """Base class for visualization data."""
    viz_type: str = ""
    title: str = ""
    description: str = ""
    data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "viz_type": self.viz_type,
            "title": self.title,
            "description": self.description,
            "data": self.data,
        }


def claim_heatmap(mevf: MEVFObject) -> VisualizationData:
    """
    Claim Heatmap — which parts of the video are verified, disputed, speculative, unknown.

    Output: list of time segments with color labels:
        green = verified, yellow = speculative, red = disputed, gray = unknown
    """
    segments = []
    for seg in mevf.segments:
        color = {
            "verified": "green",
            "replicated": "green",
            "partially_replicated": "yellow",
            "disputed": "red",
            "speculative": "yellow",
            "unverified": "gray",
            "retracted": "black",
        }.get(seg.claim_status, "gray")

        segments.append({
            "start": seg.timestamp_in_video,
            "end": seg.timestamp_in_video + seg.duration_seconds,
            "claim": seg.claim[:60],
            "status": seg.claim_status,
            "color": color,
        })

    return VisualizationData(
        viz_type="claim_heatmap",
        title="Claim Heatmap",
        description="Which parts of the video are verified, disputed, speculative, or unknown",
        data={"segments": segments},
    )


def evidence_density_timeline(mevf: MEVFObject) -> VisualizationData:
    """
    Evidence Density Timeline — how much source-backed evidence appears per second.

    Output: time series of evidence density (papers per segment).
    """
    timeline = []
    for seg in mevf.segments:
        density = 0
        if seg.source_paper_title:
            density += 1
        if seg.scores.provenance_completeness_score > 0.5:
            density += 1
        if seg.scores.truth_safety_score > 0.5:
            density += 1

        timeline.append({
            "time": seg.timestamp_in_video,
            "density": density,
            "claim": seg.claim[:40],
            "has_source": bool(seg.source_paper_title),
        })

    return VisualizationData(
        viz_type="evidence_density_timeline",
        title="Evidence Density Timeline",
        description="How much source-backed evidence appears per second",
        data={"timeline": timeline},
    )


def contradiction_map(mevf: MEVFObject) -> VisualizationData:
    """
    Contradiction Map — where sources disagree and which claims are unstable.

    Output: list of contradictions with claim, supporting count, counter count.
    """
    contradictions = []
    for seg in mevf.segments:
        if seg.claim_status in ("disputed", "partially_replicated"):
            contradictions.append({
                "claim": seg.claim[:60],
                "status": seg.claim_status,
                "timestamp": seg.timestamp_in_video,
                "trust_grade": seg.scores.trust_grade,
                "not_status": seg.not_status,
            })

    return VisualizationData(
        viz_type="contradiction_map",
        title="Contradiction Map",
        description="Where sources disagree and which claims are unstable",
        data={"contradictions": contradictions, "count": len(contradictions)},
    )


def replication_ladder(investigation: InvestigationGraph) -> VisualizationData:
    """
    Replication Ladder — claim → experiment → reproduction → failure → confidence shift.

    Output: ladder structure showing the replication journey for each claim.
    """
    ladders = []
    for claim in investigation.claims:
        rungs = []
        rungs.append({"step": "claim", "text": claim.claim_text[:60], "confidence": claim.confidence})
        rungs.append({"step": "supporting", "count": len(claim.supporting_papers), "confidence": claim.confidence})
        rungs.append({"step": "counter", "count": len(claim.counter_papers), "confidence": claim.confidence})

        if claim.replications > 0:
            rungs.append({"step": "replication", "result": "succeeded", "count": claim.replications})
        if claim.failed_replications > 0:
            rungs.append({"step": "replication", "result": "failed", "count": claim.failed_replications})

        rungs.append({"step": "final_status", "status": claim.status.value, "confidence": claim.confidence})

        ladders.append({
            "claim": claim.claim_text[:60],
            "rungs": rungs,
            "final_confidence": claim.confidence,
            "final_status": claim.status.value,
        })

    return VisualizationData(
        viz_type="replication_ladder",
        title="Replication Ladder",
        description="Claim → experiment → reproduction → failure → confidence shift",
        data={"ladders": ladders},
    )


def rights_safety_timeline(mevf: MEVFObject) -> VisualizationData:
    """
    Rights Safety Timeline — which visual segments are safe, review-required, blocked, owned.

    Output: timeline with rights status per segment.
    """
    timeline = []
    for seg in mevf.segments:
        timeline.append({
            "start": seg.timestamp_in_video,
            "end": seg.timestamp_in_video + seg.duration_seconds,
            "rights_status": seg.rights_status,
            "license_type": seg.license_type,
            "visual_type": seg.visual_type,
            "is_for_sale": seg.is_for_sale,
        })

    safe_count = sum(1 for s in mevf.segments if s.rights_status == "safe")
    review_count = sum(1 for s in mevf.segments if s.rights_status == "needs_review")
    blocked_count = sum(1 for s in mevf.segments if s.rights_status == "blocked")

    return VisualizationData(
        viz_type="rights_safety_timeline",
        title="Rights Safety Timeline",
        description="Which visual segments are safe, review-required, blocked, or owned",
        data={
            "timeline": timeline,
            "safe": safe_count,
            "needs_review": review_count,
            "blocked": blocked_count,
        },
    )


def machine_trust_curve(mevf: MEVFObject) -> VisualizationData:
    """
    Machine Trust Curve — how algorithmic confidence changes as the investigation unfolds.

    Output: time series of machine buyability scores.
    """
    curve = []
    for seg in mevf.segments:
        curve.append({
            "time": seg.timestamp_in_video,
            "buyability": seg.scores.machine_buyability_score,
            "trust_grade": seg.scores.trust_grade,
            "claim": seg.claim[:40],
        })

    return VisualizationData(
        viz_type="machine_trust_curve",
        title="Machine Trust Curve",
        description="How algorithmic confidence changes as the investigation unfolds",
        data={
            "curve": curve,
            "avg_buyability": mevf.avg_machine_buyability,
            "overall_grade": mevf.trust_grade,
        },
    )


def uncertainty_cinema(investigation: InvestigationGraph) -> VisualizationData:
    """
    Uncertainty Cinema — a video where unknowns, gaps, and missing experiments
    are first-class visuals.

    Instead of hiding uncertainty, this visualization makes it the centerpiece.
    Output: list of uncertainty moments that should be visualized prominently.
    """
    moments = []

    for claim in investigation.claims:
        if claim.status in (ScientificStatus.UNVERIFIED, ScientificStatus.SPECULATIVE):
            moments.append({
                "type": "unknown_claim",
                "claim": claim.claim_text[:60],
                "status": claim.status.value,
                "message": f"This claim is {claim.status.value} — no evidence found",
                "visual": "question mark overlay on dark background",
            })

        if claim.status == ScientificStatus.DISPUTED:
            moments.append({
                "type": "contradiction",
                "claim": claim.claim_text[:60],
                "supporting": len(claim.supporting_papers),
                "counter": len(claim.counter_papers),
                "message": f"Sources disagree: {len(claim.supporting_papers)} for, {len(claim.counter_papers)} against",
                "visual": "split screen showing opposing evidence",
            })

        if claim.failed_replications > 0:
            moments.append({
                "type": "failed_replication",
                "claim": claim.claim_text[:60],
                "failed": claim.failed_replications,
                "message": f"{claim.failed_replications} replication attempt(s) failed",
                "visual": "red X overlay on experiment footage",
            })

        if claim.confidence < 0.3:
            moments.append({
                "type": "low_confidence",
                "claim": claim.claim_text[:60],
                "confidence": claim.confidence,
                "message": f"Very low confidence: {claim.confidence:.0%}",
                "visual": "confidence gauge showing red zone",
            })

    return VisualizationData(
        viz_type="uncertainty_cinema",
        title="Uncertainty Cinema",
        description="A video where unknowns, gaps, and missing experiments are first-class visuals",
        data={"moments": moments, "count": len(moments)},
    )


def generate_all_visualizations(
    mevf: MEVFObject,
    investigation: InvestigationGraph,
) -> list[VisualizationData]:
    """Generate all seven visualization forms."""
    return [
        claim_heatmap(mevf),
        evidence_density_timeline(mevf),
        contradiction_map(mevf),
        replication_ladder(investigation),
        rights_safety_timeline(mevf),
        machine_trust_curve(mevf),
        uncertainty_cinema(investigation),
    ]
