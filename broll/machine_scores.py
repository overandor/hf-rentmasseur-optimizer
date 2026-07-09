"""
Machine Scores — Six machine-consumable scores for MEVF segments.

A normal video persuades by narrative, emotion, editing.
MEVF persuades machines through scores they can verify:

    1. semantic_match_score — how well visual matches claim (exists)
    2. evidence_relevance_score — how well visual supports claim (exists)
    3. truth_safety_score — whether claim is verified/speculative/etc (exists)
    4. rights_safety_score — whether media can legally be reused (NEW)
    5. provenance_completeness_score — whether source chain is traceable (NEW)
    6. machine_buyability_score — whether another agent can safely purchase/reuse (NEW)

The machine_buyability_score is the composite — it determines whether
a segment is market-ready for agent-to-agent purchase.

A machine buyer does not ask:
    "Give me a cool video about resonance."

It asks:
    "Give me verified visual evidence segments about Schumann resonance with:
     confidence > 0.7
     rights_status = safe
     source_quality > 0.8
     duration < 12 seconds
     human comprehension score > 0.75
     machine provenance complete"
"""

from dataclasses import dataclass
from typing import Optional

from .rights_filter import RightsStatus
from .scientific_claim import ScientificStatus


def compute_rights_safety_score(
    rights_status: str,
    license_type: str = "unknown",
    has_explicit_license: bool = False,
) -> float:
    """
    Compute rights safety score (0.0-1.0).

    safe = 1.0, needs_review = 0.5, blocked = 0.0, unknown = 0.3
    Bonus for explicit license detection.
    """
    base = {
        "safe": 1.0,
        "needs_review": 0.5,
        "blocked": 0.0,
        "unknown": 0.3,
    }
    score = base.get(rights_status, 0.3)
    if has_explicit_license and rights_status == "safe":
        score = min(1.0, score + 0.0)  # Already at max
    return score


def compute_provenance_completeness_score(
    has_source: bool = False,
    has_source_paper: bool = False,
    has_receipt_hash: bool = False,
    has_proof_chain: bool = False,
    has_citation: bool = False,
    has_author_info: bool = False,
    has_timestamp: bool = False,
    has_investigation_id: bool = False,
) -> float:
    """
    Compute provenance completeness score (0.0-1.0).

    Measures whether the source chain is fully traceable.
    Each provenance element contributes equally (1/8 = 0.125).
    """
    elements = [
        has_source,
        has_source_paper,
        has_receipt_hash,
        has_proof_chain,
        has_citation,
        has_author_info,
        has_timestamp,
        has_investigation_id,
    ]
    return sum(elements) / len(elements)


def compute_machine_buyability_score(
    semantic_match: float,
    evidence_relevance: float,
    truth_safety: float,
    rights_safety: float,
    provenance_completeness: float,
    scientific_status: str = "unverified",
    has_receipt: bool = True,
    duration_seconds: float = 10.0,
) -> float:
    """
    Compute machine buyability score (0.0-1.0).

    This is the composite score that determines whether a segment
    is market-ready for agent-to-agent purchase.

    Formula:
        buyability = (
            semantic_match * 0.10
            + evidence_relevance * 0.15
            + truth_safety * 0.20
            + rights_safety * 0.20
            + provenance_completeness * 0.20
            + status_bonus * 0.10
            + receipt_bonus * 0.05
        ) * duration_penalty

    A segment is machine-buyable if buyability >= 0.7
    """
    # Status bonus: verified/replicated claims are more buyable
    status_bonuses = {
        "verified": 1.0,
        "replicated": 1.0,
        "partially_replicated": 0.6,
        "disputed": 0.3,
        "speculative": 0.2,
        "unverified": 0.1,
        "retracted": 0.0,
    }
    status_bonus = status_bonuses.get(scientific_status, 0.1)

    # Receipt bonus
    receipt_bonus = 1.0 if has_receipt else 0.0

    # Duration penalty: very long segments are less buyable
    if duration_seconds <= 0:
        duration_penalty = 0.0
    elif duration_seconds <= 30:
        duration_penalty = 1.0
    elif duration_seconds <= 60:
        duration_penalty = 0.8
    elif duration_seconds <= 120:
        duration_penalty = 0.6
    else:
        duration_penalty = 0.4

    buyability = (
        semantic_match * 0.10
        + evidence_relevance * 0.15
        + truth_safety * 0.20
        + rights_safety * 0.20
        + provenance_completeness * 0.20
        + status_bonus * 0.10
        + receipt_bonus * 0.05
    ) * duration_penalty

    return max(0.0, min(1.0, buyability))


@dataclass
class MachineScoreSet:
    """All six machine scores for a segment."""
    semantic_match_score: float = 0.0
    evidence_relevance_score: float = 0.0
    truth_safety_score: float = 0.0
    rights_safety_score: float = 0.0
    provenance_completeness_score: float = 0.0
    machine_buyability_score: float = 0.0

    @property
    def is_machine_buyable(self) -> bool:
        """Whether this segment is market-ready for agent purchase."""
        return self.machine_buyability_score >= 0.7

    @property
    def trust_grade(self) -> str:
        """Letter grade for machine trust."""
        s = self.machine_buyability_score
        if s >= 0.9:
            return "A"
        elif s >= 0.8:
            return "B"
        elif s >= 0.7:
            return "C"
        elif s >= 0.5:
            return "D"
        else:
            return "F"

    def to_dict(self) -> dict:
        return {
            "semantic_match_score": round(self.semantic_match_score, 3),
            "evidence_relevance_score": round(self.evidence_relevance_score, 3),
            "truth_safety_score": round(self.truth_safety_score, 3),
            "rights_safety_score": round(self.rights_safety_score, 3),
            "provenance_completeness_score": round(self.provenance_completeness_score, 3),
            "machine_buyability_score": round(self.machine_buyability_score, 3),
            "is_machine_buyable": self.is_machine_buyable,
            "trust_grade": self.trust_grade,
        }


def compute_all_machine_scores(
    semantic_match: float,
    evidence_relevance: float,
    truth_safety: float,
    rights_status: str = "unknown",
    license_type: str = "unknown",
    has_explicit_license: bool = False,
    has_source: bool = False,
    has_source_paper: bool = False,
    has_receipt_hash: bool = False,
    has_proof_chain: bool = False,
    has_citation: bool = False,
    has_author_info: bool = False,
    has_timestamp: bool = False,
    has_investigation_id: bool = False,
    scientific_status: str = "unverified",
    has_receipt: bool = True,
    duration_seconds: float = 10.0,
) -> MachineScoreSet:
    """Compute all six machine scores at once."""
    rights = compute_rights_safety_score(rights_status, license_type, has_explicit_license)
    provenance = compute_provenance_completeness_score(
        has_source, has_source_paper, has_receipt_hash, has_proof_chain,
        has_citation, has_author_info, has_timestamp, has_investigation_id,
    )
    buyability = compute_machine_buyability_score(
        semantic_match, evidence_relevance, truth_safety,
        rights, provenance, scientific_status, has_receipt, duration_seconds,
    )
    return MachineScoreSet(
        semantic_match_score=semantic_match,
        evidence_relevance_score=evidence_relevance,
        truth_safety_score=truth_safety,
        rights_safety_score=rights,
        provenance_completeness_score=provenance,
        machine_buyability_score=buyability,
    )
