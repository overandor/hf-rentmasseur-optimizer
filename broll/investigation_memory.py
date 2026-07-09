"""
Investigation Memory — The compounding asset.

Every completed investigation makes future investigations faster, richer,
and easier to verify. This module stores and retrieves reusable artifacts
from prior investigations:

    Claims
    Evidence
    Sources
    Experiments
    Visual Archetypes
    Narration Segments
    Verification Results

The growing graph of verified investigations is the leverage point:
one autonomous investigation creates many media products, and every
completed investigation makes future ones faster.

Usage:
    memory = InvestigationMemory()
    memory.store(investigation)

    # Later, in a new investigation:
    reusable = memory.find_relevant("resonance")
    for claim in reusable.claims:
        print(f"Reusing verified claim: {claim.claim_text}")
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from .investigation_graph import InvestigationGraph
from .scientific_claim import ScientificClaim, ScientificStatus, Paper


@dataclass
class ReusableArtifact:
    """A reusable artifact from a prior investigation."""
    artifact_type: str  # "claim", "evidence", "source", "experiment", "verification"
    content: str
    investigation_id: str = ""
    confidence: float = 0.0
    status: str = ""
    source: str = ""
    timestamp: float = 0.0
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "artifact_type": self.artifact_type,
            "content": self.content,
            "investigation_id": self.investigation_id,
            "confidence": self.confidence,
            "status": self.status,
            "source": self.source,
            "timestamp": self.timestamp,
            "tags": self.tags,
        }


@dataclass
class ReusableBundle:
    """A bundle of reusable artifacts relevant to a new investigation."""
    claims: list[ReusableArtifact] = field(default_factory=list)
    evidence: list[ReusableArtifact] = field(default_factory=list)
    sources: list[ReusableArtifact] = field(default_factory=list)
    experiments: list[ReusableArtifact] = field(default_factory=list)
    verifications: list[ReusableArtifact] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.claims) + len(self.evidence) + len(self.sources) + \
               len(self.experiments) + len(self.verifications)

    def to_dict(self) -> dict:
        return {
            "claims": [a.to_dict() for a in self.claims],
            "evidence": [a.to_dict() for a in self.evidence],
            "sources": [a.to_dict() for a in self.sources],
            "experiments": [a.to_dict() for a in self.experiments],
            "verifications": [a.to_dict() for a in self.verifications],
            "total": self.total,
        }


class InvestigationMemory:
    """
    Stores and retrieves reusable artifacts from prior investigations.

    The compounding asset: every completed investigation contributes
    verified claims, evidence, sources, and experiments that can be
    reused by future investigations.

    Usage:
        memory = InvestigationMemory()
        memory.store(investigation)

        # In a new investigation:
        bundle = memory.find_relevant("resonance effects in ancient structures")
        print(f"Reusing {bundle.total} artifacts from prior investigations")
    """

    def __init__(self):
        self._artifacts: list[ReusableArtifact] = []
        self._investigations: dict[str, InvestigationGraph] = {}
        self._index: dict[str, list[int]] = {}  # tag -> artifact indices

    def store(self, investigation: InvestigationGraph) -> int:
        """
        Store all reusable artifacts from an investigation.

        Returns the number of artifacts stored.
        """
        inv_id = investigation.investigation_id
        self._investigations[inv_id] = investigation
        count = 0

        for claim in investigation.claims:
            tags = self._extract_tags(claim.claim_text)
            self._add_artifact(ReusableArtifact(
                artifact_type="claim",
                content=claim.claim_text,
                investigation_id=inv_id,
                confidence=claim.confidence,
                status=claim.status.value,
                timestamp=time.time(),
                tags=tags,
            ))
            count += 1

            for paper in claim.source_papers:
                self._add_artifact(ReusableArtifact(
                    artifact_type="source",
                    content=paper.title,
                    investigation_id=inv_id,
                    confidence=0.7 if paper.is_peer_reviewed else 0.4,
                    status="peer_reviewed" if paper.is_peer_reviewed else "preprint",
                    source=paper.source,
                    timestamp=time.time(),
                    tags=self._extract_tags(paper.title + " " + paper.abstract),
                ))
                count += 1

            for counter in claim.counter_papers:
                self._add_artifact(ReusableArtifact(
                    artifact_type="evidence",
                    content=f"COUNTER: {counter.title}",
                    investigation_id=inv_id,
                    confidence=0.7,
                    status="counter_evidence",
                    source=counter.source,
                    timestamp=time.time(),
                    tags=self._extract_tags(counter.title),
                ))
                count += 1

            if claim.replications > 0 or claim.failed_replications > 0:
                self._add_artifact(ReusableArtifact(
                    artifact_type="verification",
                    content=f"Replication: {claim.replications} succeeded, {claim.failed_replications} failed for: {claim.claim_text[:60]}",
                    investigation_id=inv_id,
                    confidence=claim.confidence,
                    status=claim.status.value,
                    timestamp=time.time(),
                    tags=tags,
                ))
                count += 1

        return count

    def find_relevant(self, query: str, min_confidence: float = 0.0) -> ReusableBundle:
        """
        Find reusable artifacts relevant to a new investigation query.

        Args:
            query: The new investigation question or topic
            min_confidence: Minimum confidence threshold for reuse

        Returns:
            ReusableBundle with claims, evidence, sources, experiments, verifications
        """
        query_tags = self._extract_tags(query)
        query_lower = query.lower()

        bundle = ReusableBundle()

        for artifact in self._artifacts:
            if artifact.confidence < min_confidence:
                continue

            relevance = self._compute_relevance(artifact, query_tags, query_lower)
            if relevance > 0.1:
                if artifact.artifact_type == "claim":
                    bundle.claims.append(artifact)
                elif artifact.artifact_type == "evidence":
                    bundle.evidence.append(artifact)
                elif artifact.artifact_type == "source":
                    bundle.sources.append(artifact)
                elif artifact.artifact_type == "experiment":
                    bundle.experiments.append(artifact)
                elif artifact.artifact_type == "verification":
                    bundle.verifications.append(artifact)

        return bundle

    def get_verified_claims(self, topic: str | None = None) -> list[ReusableArtifact]:
        """Get all verified or replicated claims, optionally filtered by topic."""
        results = []
        for artifact in self._artifacts:
            if artifact.artifact_type != "claim":
                continue
            if artifact.status not in ("verified", "replicated"):
                continue
            if topic and topic.lower() not in artifact.content.lower():
                continue
            results.append(artifact)
        return results

    def get_known_sources(self, topic: str | None = None) -> list[ReusableArtifact]:
        """Get all known sources, optionally filtered by topic."""
        results = []
        for artifact in self._artifacts:
            if artifact.artifact_type != "source":
                continue
            if topic and topic.lower() not in artifact.content.lower():
                continue
            results.append(artifact)
        return results

    def _add_artifact(self, artifact: ReusableArtifact) -> None:
        """Add an artifact to the memory and update the index."""
        idx = len(self._artifacts)
        self._artifacts.append(artifact)
        for tag in artifact.tags:
            if tag not in self._index:
                self._index[tag] = []
            self._index[tag].append(idx)

    def _extract_tags(self, text: str) -> list[str]:
        """Extract topic tags from text."""
        stop = {"the", "a", "an", "is", "are", "was", "were", "be", "been",
                "have", "has", "had", "do", "does", "did", "will", "would",
                "could", "should", "may", "might", "can", "of", "in", "on",
                "at", "to", "for", "with", "by", "from", "as", "and", "or",
                "but", "not", "no", "yes", "this", "that", "these", "those",
                "it", "they", "we", "you", "he", "she", "i", "what", "which",
                "who", "whom", "whose", "when", "where", "why", "how", "all",
                "each", "every", "both", "few", "more", "most", "other",
                "some", "such", "than", "too", "very", "can", "also"}
        words = [w.lower().strip(".,;:!?\"'()[]{}") for w in text.split()]
        tags = [w for w in words if len(w) > 3 and w not in stop]
        return list(set(tags))[:10]

    def _compute_relevance(
        self,
        artifact: ReusableArtifact,
        query_tags: list[str],
        query_lower: str,
    ) -> float:
        """Compute relevance of an artifact to a query."""
        # Tag overlap
        artifact_tags = set(artifact.tags)
        q_tags = set(query_tags)
        overlap = artifact_tags & q_tags
        tag_score = len(overlap) / max(len(q_tags), 1) if q_tags else 0

        # Content substring match
        content_lower = artifact.content.lower()
        content_score = 0.0
        for tag in query_tags:
            if tag in content_lower:
                content_score += 0.1
        content_score = min(1.0, content_score)

        return max(tag_score, content_score)

    @property
    def stats(self) -> dict:
        """Memory statistics."""
        type_counts: dict[str, int] = {}
        for a in self._artifacts:
            type_counts[a.artifact_type] = type_counts.get(a.artifact_type, 0) + 1

        verified = sum(1 for a in self._artifacts
                       if a.artifact_type == "claim" and a.status in ("verified", "replicated"))

        return {
            "total_artifacts": len(self._artifacts),
            "total_investigations": len(self._investigations),
            "by_type": type_counts,
            "verified_claims": verified,
            "unique_tags": len(self._index),
        }

    def to_dict(self) -> dict:
        return {
            "stats": self.stats,
            "artifacts": [a.to_dict() for a in self._artifacts],
        }
