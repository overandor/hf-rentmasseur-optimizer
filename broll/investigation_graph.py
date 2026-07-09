"""
Investigation Graph — The primary asset of the Research-to-Video Compiler.

The Investigation Graph ties together:
    Question → Searches → Papers → Claims → Evidence → Counter-evidence
    → Experiments → Conclusions → Visual Assets → Timeline → Outputs

One investigation can generate:
    Video, Blog, Paper, Slides, Podcast, Dataset, Course, FAQ,
    Landing Page, Knowledge Base

Video is just one renderer among many. The investigation and evidence
graph become the primary asset, and every media format is compiled
from that source of truth.

Architecture:
    Reality → Observation → Investigation → Evidence → Knowledge Graph
    → Media Compiler → Any Output Format
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from .scientific_claim import (
    ScientificClaim,
    ScientificStatus,
    Paper,
    Experiment,
    determine_status,
    compute_confidence,
)
from .claim_extractor import TruthStatus


@dataclass
class SearchRecord:
    """Record of a search performed during investigation."""
    source: str  # arXiv, PubMed, Semantic Scholar, GitHub, etc.
    query: str
    results_count: int = 0
    timestamp: float = 0.0
    papers_found: list[Paper] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "query": self.query,
            "results_count": self.results_count,
            "timestamp": self.timestamp,
            "papers_found": [p.to_dict() for p in self.papers_found],
        }


@dataclass
class InvestigationStep:
    """A single step in the investigation process."""
    step_type: str  # "search", "extract", "verify", "experiment", "conclude"
    description: str
    timestamp: float = 0.0
    inputs: dict = field(default_factory=dict)
    outputs: dict = field(default_factory=dict)
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "step_type": self.step_type,
            "description": self.description,
            "timestamp": self.timestamp,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "duration_seconds": self.duration_seconds,
        }


@dataclass
class InvestigationGraph:
    """
    The Investigation Graph — the primary asset.

    Contains the full provenance chain from question to conclusion:
        question → searches → papers → claims → evidence → conclusions

    This graph is the source of truth from which all media outputs
    (video, blog, paper, slides, podcast) are compiled.
    """
    investigation_id: str = ""
    question: str = ""
    timestamp: float = 0.0
    searches: list[SearchRecord] = field(default_factory=list)
    papers: list[Paper] = field(default_factory=list)
    claims: list[ScientificClaim] = field(default_factory=list)
    steps: list[InvestigationStep] = field(default_factory=list)
    conclusions: list[str] = field(default_factory=list)
    visual_assets: list[str] = field(default_factory=list)
    receipt_hash: str = ""

    # Summary stats
    @property
    def stats(self) -> dict:
        status_counts: dict[str, int] = {}
        for claim in self.claims:
            status_counts[claim.status.value] = status_counts.get(claim.status.value, 0) + 1

        return {
            "question": self.question[:80],
            "search_count": len(self.searches),
            "paper_count": len(self.papers),
            "claim_count": len(self.claims),
            "step_count": len(self.steps),
            "conclusion_count": len(self.conclusions),
            "status_distribution": status_counts,
            "avg_confidence": (
                sum(c.confidence for c in self.claims) / len(self.claims)
                if self.claims else 0.0
            ),
            "total_citations": sum(c.citation_count for c in self.claims),
            "total_replications": sum(c.replications for c in self.claims),
            "total_failed_replications": sum(c.failed_replications for c in self.claims),
        }

    def to_dict(self) -> dict:
        return {
            "investigation_id": self.investigation_id,
            "question": self.question,
            "timestamp": self.timestamp,
            "searches": [s.to_dict() for s in self.searches],
            "papers": [p.to_dict() for p in self.papers],
            "claims": [c.to_dict() for c in self.claims],
            "steps": [s.to_dict() for s in self.steps],
            "conclusions": self.conclusions,
            "visual_assets": self.visual_assets,
            "receipt_hash": self.receipt_hash,
            "stats": self.stats,
        }

    def to_json(self, path: str | None = None) -> str:
        data = self.to_dict()
        text = json.dumps(data, indent=2)
        if path:
            with open(path, "w") as f:
                f.write(text)
        return text

    def compute_receipt_hash(self) -> str:
        """Compute SHA-256 hash of the entire investigation."""
        data = json.dumps(self.to_dict(), sort_keys=True)
        self.receipt_hash = f"sha256:{hashlib.sha256(data.encode()).hexdigest()[:16]}"
        return self.receipt_hash

    def add_search(self, source: str, query: str, papers: list[Paper] | None = None) -> SearchRecord:
        """Add a search record to the investigation."""
        record = SearchRecord(
            source=source,
            query=query,
            results_count=len(papers) if papers else 0,
            timestamp=time.time(),
            papers_found=papers or [],
        )
        self.searches.append(record)
        if papers:
            self.papers.extend(papers)
        return record

    def add_step(self, step_type: str, description: str, **kwargs) -> InvestigationStep:
        """Add an investigation step."""
        step = InvestigationStep(
            step_type=step_type,
            description=description,
            timestamp=time.time(),
            inputs=kwargs.get("inputs", {}),
            outputs=kwargs.get("outputs", {}),
            duration_seconds=kwargs.get("duration_seconds", 0.0),
        )
        self.steps.append(step)
        return step

    def add_claim(self, claim: ScientificClaim) -> None:
        """Add a scientific claim to the investigation."""
        claim.investigation_id = self.investigation_id
        claim.compute_receipt_hash()
        self.claims.append(claim)

    def add_conclusion(self, conclusion: str) -> None:
        """Add a conclusion drawn from the investigation."""
        self.conclusions.append(conclusion)

    def get_claims_by_status(self, status: ScientificStatus) -> list[ScientificClaim]:
        """Filter claims by verification status."""
        return [c for c in self.claims if c.status == status]

    def get_disputed_claims(self) -> list[ScientificClaim]:
        """Get all disputed or partially replicated claims."""
        return [
            c for c in self.claims
            if c.status in (ScientificStatus.DISPUTED, ScientificStatus.PARTIALLY_REPLICATED)
        ]

    def get_verified_claims(self) -> list[ScientificClaim]:
        """Get all verified or replicated claims."""
        return [
            c for c in self.claims
            if c.status in (ScientificStatus.VERIFIED, ScientificStatus.REPLICATED)
        ]

    def to_narrative(self) -> str:
        """
        Generate a narrative summary of the investigation.

        The viewer watches:
            Question → Search → Discovery → Confusion → Contradiction
            → Verification → Experiment → Conclusion
        """
        parts: list[str] = []
        parts.append(f"Investigation: {self.question}")
        parts.append(f"\nSearched {len(self.searches)} sources, found {len(self.papers)} papers.")

        if self.claims:
            verified = self.get_verified_claims()
            disputed = self.get_disputed_claims()
            parts.append(f"\nExtracted {len(self.claims)} claims:")
            if verified:
                parts.append(f"  {len(verified)} verified/replicated")
            if disputed:
                parts.append(f"  {len(disputed)} disputed/partially replicated")

            parts.append("\nKey findings:")
            for claim in self.claims[:5]:
                parts.append(
                    f"  [{claim.status.value}] {claim.claim_text[:80]}... "
                    f"(confidence: {claim.confidence:.2f})"
                )

        if self.conclusions:
            parts.append(f"\nConclusions:")
            for c in self.conclusions:
                parts.append(f"  - {c}")

        return "\n".join(parts)
