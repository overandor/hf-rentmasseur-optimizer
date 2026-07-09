"""
Scientific Claim — A claim object with verification metadata.

Extends the basic Claim with scientific evidence tracking:
    - source paper
    - citation count
    - replications (successful and failed)
    - confidence score
    - counterarguments
    - experiments
    - visual assets
    - receipt hash
    - verification status (VERIFIED, REPLICATED, DISPUTED, etc.)

The key difference from a regular Claim:
    A Claim says "this sentence asserts X"
    A ScientificClaim says "this assertion has N supporting papers,
    M replications, K counterarguments, and confidence C"

This is the object that the Investigation Engine produces after
searching papers, extracting claims, and verifying evidence.
"""

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ScientificStatus(Enum):
    """
    Verification status for a scientific claim.

    VERIFIED — multiple independent sources confirm
    REPLICATED — experimentally reproduced by independent parties
    PARTIALLY_REPLICATED — some replications succeeded, some failed
    DISPUTED — significant counter-evidence exists
    SPECULATIVE — no evidence found, claim is hypothetical
    UNVERIFIED — no evidence found either way
    RETRACTED — original source retracted the claim
    """
    VERIFIED = "verified"
    REPLICATED = "replicated"
    PARTIALLY_REPLICATED = "partially_replicated"
    DISPUTED = "disputed"
    SPECULATIVE = "speculative"
    UNVERIFIED = "unverified"
    RETRACTED = "retracted"


@dataclass
class Paper:
    """A research paper reference."""
    title: str
    authors: list[str] = field(default_factory=list)
    year: int = 0
    doi: str = ""
    url: str = ""
    citation_count: int = 0
    source: str = ""  # arXiv, PubMed, Semantic Scholar, etc.
    abstract: str = ""
    is_peer_reviewed: bool = False

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "authors": self.authors,
            "year": self.year,
            "doi": self.doi,
            "url": self.url,
            "citation_count": self.citation_count,
            "source": self.source,
            "abstract": self.abstract[:200] if self.abstract else "",
            "is_peer_reviewed": self.is_peer_reviewed,
        }


@dataclass
class Experiment:
    """An experiment or reproduction attempt."""
    description: str
    result: str = ""  # "succeeded", "failed", "inconclusive"
    source: str = ""
    parameters: dict = field(default_factory=dict)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "result": self.result,
            "source": self.source,
            "parameters": self.parameters,
            "notes": self.notes,
        }


@dataclass
class ScientificClaim:
    """
    A scientific claim with full verification metadata.

    {
      "claim": "...",
      "source_paper": "...",
      "citation_count": 123,
      "replications": 7,
      "failed_replications": 2,
      "confidence": 0.81,
      "counterarguments": [],
      "experiments": [],
      "visual_assets": [],
      "receipt_hash": "..."
    }
    """
    claim_text: str
    status: ScientificStatus = ScientificStatus.UNVERIFIED
    source_papers: list[Paper] = field(default_factory=list)
    supporting_papers: list[Paper] = field(default_factory=list)
    counter_papers: list[Paper] = field(default_factory=list)
    citation_count: int = 0
    replications: int = 0
    failed_replications: int = 0
    confidence: float = 0.0
    counterarguments: list[str] = field(default_factory=list)
    experiments: list[Experiment] = field(default_factory=list)
    visual_assets: list[str] = field(default_factory=list)
    receipt_hash: str = ""
    investigation_id: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "claim": self.claim_text,
            "status": self.status.value,
            "source_papers": [p.to_dict() for p in self.source_papers],
            "supporting_papers": [p.to_dict() for p in self.supporting_papers],
            "counter_papers": [p.to_dict() for p in self.counter_papers],
            "citation_count": self.citation_count,
            "replications": self.replications,
            "failed_replications": self.failed_replications,
            "confidence": round(self.confidence, 3),
            "counterarguments": self.counterarguments,
            "experiments": [e.to_dict() for e in self.experiments],
            "visual_assets": self.visual_assets,
            "receipt_hash": self.receipt_hash,
            "investigation_id": self.investigation_id,
            "notes": self.notes,
        }

    def to_overlay(self) -> dict:
        """
        Overlay format for video display.

        The audience sees:
            Claim: Schumann resonance influences biological systems.
            Status: DISPUTED
            Evidence: 12 supporting papers
            Counter Evidence: 18 papers
            Replication: Weak
            Confidence: 0.42
        """
        replication_label = "None"
        if self.replications > 0 and self.failed_replications == 0:
            replication_label = "Confirmed"
        elif self.replications > 0 and self.failed_replications > 0:
            replication_label = "Weak"
        elif self.failed_replications > 0 and self.replications == 0:
            replication_label = "Failed"

        return {
            "claim": self.claim_text,
            "status": self.status.value,
            "supporting_evidence": f"{len(self.supporting_papers)} supporting papers",
            "counter_evidence": f"{len(self.counter_papers)} papers",
            "replication": replication_label,
            "confidence": f"{self.confidence:.2f}",
        }

    def compute_receipt_hash(self) -> str:
        """Compute SHA-256 hash of the claim's evidence state."""
        import json
        data = json.dumps(self.to_dict(), sort_keys=True)
        self.receipt_hash = f"sha256:{hashlib.sha256(data.encode()).hexdigest()[:16]}"
        return self.receipt_hash


def determine_status(
    supporting_count: int,
    counter_count: int,
    replications: int,
    failed_replications: int,
    is_retracted: bool = False,
) -> ScientificStatus:
    """
    Determine the verification status of a claim based on evidence.

    Logic:
    - RETRACTED if source is retracted
    - REPLICATED if multiple successful independent replications
    - PARTIALLY_REPLICATED if some succeeded and some failed
    - DISPUTED if counter-evidence is significant (>= 50% of supporting)
    - VERIFIED if multiple independent supporting sources
    - SPECULATIVE if no evidence but claim is hypothetical
    - UNVERIFIED if no evidence found
    """
    if is_retracted:
        return ScientificStatus.RETRACTED

    if replications >= 3 and failed_replications == 0:
        return ScientificStatus.REPLICATED

    if replications > 0 and failed_replications > 0:
        return ScientificStatus.PARTIALLY_REPLICATED

    if counter_count > 0 and counter_count >= supporting_count * 0.5:
        return ScientificStatus.DISPUTED

    if supporting_count >= 3:
        return ScientificStatus.VERIFIED

    if supporting_count == 0 and counter_count == 0:
        return ScientificStatus.UNVERIFIED

    if supporting_count > 0 and supporting_count < 3:
        return ScientificStatus.SPECULATIVE

    return ScientificStatus.UNVERIFIED


def compute_confidence(
    supporting_count: int,
    counter_count: int,
    replications: int,
    failed_replications: int,
    citation_count: int,
    is_peer_reviewed: bool,
) -> float:
    """
    Compute confidence score for a scientific claim.

    Formula:
        confidence = (
            supporting_weight * 0.30
            + replication_weight * 0.25
            + citation_weight * 0.15
            + peer_review_weight * 0.10
            - counter_weight * 0.20
        )
    """
    # Supporting papers weight (diminishing returns)
    supporting_weight = min(1.0, supporting_count / 10)

    # Replication weight
    total_replications = replications + failed_replications
    if total_replications == 0:
        replication_weight = 0.0
    else:
        replication_weight = replications / total_replications

    # Citation weight (log scale)
    citation_weight = min(1.0, (citation_count / 100) ** 0.5) if citation_count > 0 else 0.0

    # Peer review weight
    peer_review_weight = 1.0 if is_peer_reviewed else 0.3

    # Counter weight
    counter_weight = min(1.0, counter_count / 10)

    confidence = (
        supporting_weight * 0.30
        + replication_weight * 0.25
        + citation_weight * 0.15
        + peer_review_weight * 0.10
        - counter_weight * 0.20
    )

    return max(0.0, min(1.0, confidence))
