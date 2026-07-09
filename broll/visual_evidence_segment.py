"""
Visual Evidence Segment — the core object of OverVisual.

A VisualEvidenceSegment (VES) is NOT a VideoClip. A VideoClip is media.
A VES is:

    claim + visual explanation + truth label + rights label + provenance + receipt

It is closer to an evidence graph node than a media asset.

Each VES records one narration segment processed through the full pipeline:

    transcript span → claim → truth status → visual concepts → search queries
    → candidate sources → selected clip → 3 scoring layers → rights status → receipt hash

The three scoring layers are:
    1. semantic_match_score — how well the clip visually matches the narration meaning
    2. evidence_relevance_score — how well the clip supports/illustrates/contextualizes the claim
    3. truth_safety_score — whether the narration claim is verified/speculative/symbolic/etc

Critical distinction: semantic match ≠ truth
A clip can visually match "ancient planetary energy" while the claim remains speculative.
The system labels both independently — this is what separates it from standard
multimedia retrieval (CLIP, CLIP4Clip) which only answers "what image matches this sentence?"

OverVisual answers: "What visual evidence should accompany this claim,
and what is the epistemic status of that claim?"
"""

import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional

from .rights_filter import RightsStatus
from .claim_extractor import TruthStatus


@dataclass
class VisualEvidenceSegment:
    """
    The core object: one narration segment fully processed.

    Schema matches the OverVisual specification:
    {
      "segment_id": "...",
      "source_transcript_id": "...",
      "start_sec": 0.0,
      "end_sec": 0.0,
      "transcript_text": "...",
      "claim": "...",
      "claim_type": "verified | speculative | symbolic | folklore | entertainment | unknown",
      "visual_concepts": [],
      "search_queries": [],
      "candidate_sources": [],
      "selected_clip": null,
      "semantic_match_score": 0.0,
      "evidence_relevance_score": 0.0,
      "truth_safety_score": 0.0,
      "rights_status": "safe | needs_review | blocked | unknown",
      "receipt_hash": "sha256:..."
    }
    """
    segment_id: str
    source_transcript_id: str = ""
    start_sec: float = 0.0
    end_sec: float = 0.0
    transcript_text: str = ""
    claim: str = ""
    claim_type: str = "unknown"  # truth_status.value
    visual_concepts: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    candidate_sources: list[dict] = field(default_factory=list)
    selected_clip: dict | None = None
    # Three scoring layers
    semantic_match_score: float = 0.0
    evidence_relevance_score: float = 0.0
    truth_safety_score: float = 0.0
    # Rights
    rights_status: str = "unknown"  # RightsStatus.value
    rights_assessment: dict | None = None
    # Proof
    receipt_hash: str = ""
    # Additional metadata
    clip_match_detail: dict | None = None
    emotional_tone: str = "neutral"
    insertion_status: str = "candidate_only"  # candidate_only, selected, inserted

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "source_transcript_id": self.source_transcript_id,
            "start_sec": self.start_sec,
            "end_sec": self.end_sec,
            "transcript_text": self.transcript_text,
            "claim": self.claim,
            "claim_type": self.claim_type,
            "visual_concepts": self.visual_concepts,
            "search_queries": self.search_queries,
            "candidate_sources": self.candidate_sources,
            "selected_clip": self.selected_clip,
            "semantic_match_score": self.semantic_match_score,
            "evidence_relevance_score": self.evidence_relevance_score,
            "truth_safety_score": self.truth_safety_score,
            "rights_status": self.rights_status,
            "rights_assessment": self.rights_assessment,
            "receipt_hash": self.receipt_hash,
            "clip_match_detail": self.clip_match_detail,
            "emotional_tone": self.emotional_tone,
            "insertion_status": self.insertion_status,
        }

    def to_compact_dict(self) -> dict:
        """Compact representation for dashboard display."""
        return {
            "segment_id": self.segment_id,
            "start_sec": self.start_sec,
            "end_sec": self.end_sec,
            "claim": self.claim[:80] + "..." if len(self.claim) > 80 else self.claim,
            "claim_type": self.claim_type,
            "semantic_match_score": round(self.semantic_match_score, 3),
            "evidence_relevance_score": round(self.evidence_relevance_score, 3),
            "truth_safety_score": round(self.truth_safety_score, 3),
            "rights_status": self.rights_status,
            "insertion_status": self.insertion_status,
            "selected_clip": self.selected_clip["title"] if self.selected_clip else None,
        }

    def to_dashboard_label(self) -> dict:
        """
        Dashboard label format as specified:
        VISUAL MATCH: strong
        CLAIM STATUS: speculative
        RIGHTS STATUS: needs review
        INSERTION STATUS: candidate only
        """
        def match_label(score: float) -> str:
            if score >= 0.75: return "strong"
            if score >= 0.50: return "moderate"
            if score >= 0.25: return "weak"
            return "none"

        return {
            "VISUAL_MATCH": match_label(self.semantic_match_score),
            "CLAIM_STATUS": self.claim_type,
            "RIGHTS_STATUS": self.rights_status,
            "INSERTION_STATUS": self.insertion_status,
        }


class VESEnsemble:
    """
    A collection of VisualEvidenceSegments forming a complete compilation.

    Manages the full set of VES records for one narration input,
    including timeline assembly and export.
    """

    def __init__(self, transcript_id: str = ""):
        self.transcript_id = transcript_id
        self.segments: list[VisualEvidenceSegment] = []

    def add_segment(self, segment: VisualEvidenceSegment) -> None:
        """Add a VES to the ensemble."""
        self.segments.append(segment)

    def to_dict(self) -> dict:
        return {
            "transcript_id": self.transcript_id,
            "segment_count": len(self.segments),
            "segments": [s.to_dict() for s in self.segments],
        }

    def to_json(self, path: str | None = None) -> str:
        """Export the full ensemble as JSON."""
        data = self.to_dict()
        text = json.dumps(data, indent=2)
        if path:
            with open(path, "w") as f:
                f.write(text)
        return text

    def to_dashboard(self) -> list[dict]:
        """Export dashboard labels for all segments."""
        return [s.to_dashboard_label() for s in self.segments]

    def to_compact(self) -> list[dict]:
        """Export compact representations for table display."""
        return [s.to_compact_dict() for s in self.segments]

    @property
    def stats(self) -> dict:
        """Summary statistics."""
        if not self.segments:
            return {"segment_count": 0}

        claim_types: dict[str, int] = {}
        rights_statuses: dict[str, int] = {}
        insertion_statuses: dict[str, int] = {}
        semantic_scores: list[float] = []
        evidence_scores: list[float] = []
        truth_scores: list[float] = []

        for seg in self.segments:
            claim_types[seg.claim_type] = claim_types.get(seg.claim_type, 0) + 1
            rights_statuses[seg.rights_status] = rights_statuses.get(seg.rights_status, 0) + 1
            insertion_statuses[seg.insertion_status] = insertion_statuses.get(seg.insertion_status, 0) + 1
            semantic_scores.append(seg.semantic_match_score)
            evidence_scores.append(seg.evidence_relevance_score)
            truth_scores.append(seg.truth_safety_score)

        n = len(self.segments)
        return {
            "segment_count": n,
            "claim_types": claim_types,
            "rights_statuses": rights_statuses,
            "insertion_statuses": insertion_statuses,
            "avg_semantic_match": sum(semantic_scores) / n,
            "avg_evidence_relevance": sum(evidence_scores) / n,
            "avg_truth_safety": sum(truth_scores) / n,
            "selected_count": sum(1 for s in self.segments if s.selected_clip is not None),
        }


def compute_truth_safety_score(truth_status: TruthStatus) -> float:
    """
    Compute truth safety score from truth status.

    Higher = safer (more verified).
    Lower = more speculative / pseudoscientific.

    VERIFIED: 1.0
    SPECULATIVE: 0.4
    SYMBOLIC: 0.5
    FOLKLORE: 0.3
    ENTERTAINMENT: 0.2
    PSEUDOSCIENTIFIC: 0.1
    UNKNOWN: 0.0
    """
    scores = {
        TruthStatus.VERIFIED: 1.0,
        TruthStatus.SYMBOLIC: 0.5,
        TruthStatus.SPECULATIVE: 0.4,
        TruthStatus.FOLKLORE: 0.3,
        TruthStatus.ENTERTAINMENT: 0.2,
        TruthStatus.PSEUDOSCIENTIFIC: 0.1,
        TruthStatus.UNKNOWN: 0.0,
    }
    return scores.get(truth_status, 0.0)


def compute_evidence_relevance_score(
    semantic_match: float,
    truth_safety: float,
    has_clip: bool,
) -> float:
    """
    Compute evidence relevance score.

    How well the clip supports, illustrates, or contextualizes the claim.

    A clip that visually matches AND is from a verified source is more
    relevant than one that matches but the claim is pseudoscientific.

    Formula:
        evidence_relevance = semantic_match * (0.5 + 0.5 * truth_safety)
        if has_clip else 0.0
    """
    if not has_clip:
        return 0.0
    return semantic_match * (0.5 + 0.5 * truth_safety)
