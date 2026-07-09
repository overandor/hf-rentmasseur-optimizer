"""
Missing Visual Detector — Identifies footage that should exist but doesn't.

After the system retrieves candidate videos and assesses evidence, this
module detects gaps: visual material that would be needed to properly
illustrate the claim but is not available in the candidate pool.

Example:
    Claim: "Ancient material used planetary resonance"
    Available: Stonehenge footage, cave footage, sunrise footage
    Missing: scientist placing sensors on stone structure and measuring vibration

The missing detector identifies what footage SHOULD exist to verify or
illustrate the claim, based on the evidence graph's missing evidence items.

This is critical because it tells the production team:
    "You need to film THIS to complete the evidence chain."
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from .claim_extractor import Claim, TruthStatus
from .evidence_graph import EvidenceAssessment, EvidenceNode, EvidenceType


@dataclass
class MissingVisual:
    """A visual that should exist but doesn't."""
    description: str
    reason: str  # Why this visual is needed
    claim_text: str = ""
    visual_type: str = "footage"  # footage, simulation, experiment, diagram
    priority: str = "should_have"  # must_have, should_have, nice_to_have
    suggested_source: str = ""  # Where to get it (film, generate, archive)

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "reason": self.reason,
            "claim_text": self.claim_text,
            "visual_type": self.visual_type,
            "priority": self.priority,
            "suggested_source": self.suggested_source,
        }


@dataclass
class MissingVisualReport:
    """Report of all missing visuals for a compilation."""
    missing_visuals: list[MissingVisual] = field(default_factory=list)
    available_visuals: list[str] = field(default_factory=list)
    coverage_score: float = 0.0  # 1.0 = everything available, 0.0 = nothing
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "missing_visuals": [v.to_dict() for v in self.missing_visuals],
            "available_visuals": self.available_visuals,
            "coverage_score": round(self.coverage_score, 3),
            "summary": self.summary,
        }


# Visual templates for different evidence types
_EVIDENCE_VISUALS: dict[EvidenceType, dict[str, str]] = {
    EvidenceType.MEASUREMENT: {
        "description": "scientist using instruments to take measurements",
        "visual_type": "footage",
        "suggested_source": "film or scientific archive",
    },
    EvidenceType.EXPERIMENT: {
        "description": "controlled experiment demonstrating the claim",
        "visual_type": "experiment",
        "suggested_source": "film or generate simulation",
    },
    EvidenceType.CITATION: {
        "description": "source document or publication showing the evidence",
        "visual_type": "diagram",
        "suggested_source": "screen recording or archive",
    },
    EvidenceType.OBSERVATION: {
        "description": "direct observation of the phenomenon",
        "visual_type": "footage",
        "suggested_source": "archive or film",
    },
}

# Domain-specific missing visuals
_DOMAIN_MISSING_VISUALS: dict[str, list[dict]] = {
    "resonance": [
        {"description": "scientist placing sensors on stone structure and measuring vibration over time",
         "visual_type": "experiment", "priority": "must_have",
         "suggested_source": "film on-site experiment"},
        {"description": "frequency spectrum analyzer showing resonance peaks",
         "visual_type": "footage", "priority": "should_have",
         "suggested_source": "laboratory footage"},
    ],
    "energy": [
        {"description": "electromagnetic field measurement device in operation",
         "visual_type": "experiment", "priority": "must_have",
         "suggested_source": "film or simulation"},
        {"description": "energy spectrum visualization with labeled axes",
         "visual_type": "simulation", "priority": "should_have",
         "suggested_source": "generate animation"},
    ],
    "ancient": [
        {"description": "archaeologist examining material composition in laboratory",
         "visual_type": "footage", "priority": "should_have",
         "suggested_source": "documentary archive"},
    ],
    "earth": [
        {"description": "satellite view of Earth's electromagnetic field",
         "visual_type": "simulation", "priority": "should_have",
         "suggested_source": "NASA visualization archive"},
    ],
    "frequency": [
        {"description": "oscilloscope showing frequency waveform",
         "visual_type": "footage", "priority": "should_have",
         "suggested_source": "laboratory footage"},
    ],
}


class MissingVisualDetector:
    """
    Detects what footage should exist but doesn't.

    Compares available candidate videos against the evidence requirements
    from the Evidence Graph to identify gaps.

    Usage:
        detector = MissingVisualDetector()
        report = detector.detect(
            claim=claim,
            evidence_assessment=assessment,
            available_visuals=["Stonehenge footage", "cave footage"],
        )
        for missing in report.missing_visuals:
            print(f"MISSING: {missing.description}")
    """

    def __init__(self):
        self.evidence_visuals = dict(_EVIDENCE_VISUALS)
        self.domain_missing = dict(_DOMAIN_MISSING_VISUALS)

    def detect(
        self,
        claim: Claim,
        evidence_assessment: EvidenceAssessment,
        available_visuals: list[str] | None = None,
    ) -> MissingVisualReport:
        """
        Detect missing visuals for a claim.

        Args:
            claim: The claim being analyzed
            evidence_assessment: Evidence assessment from EvidenceGraph
            available_visuals: List of available visual descriptions (candidate titles, etc.)

        Returns:
            MissingVisualReport with gaps identified
        """
        available = available_visuals or []
        available_lower = [v.lower() for v in available]
        missing: list[MissingVisual] = []

        # 1. Check missing evidence items from the evidence graph
        for ev in evidence_assessment.missing_evidence:
            visual_template = self.evidence_visuals.get(ev.evidence_type)
            if visual_template:
                missing.append(MissingVisual(
                    description=visual_template["description"],
                    reason=f"Required evidence: {ev.description}",
                    claim_text=claim.text,
                    visual_type=visual_template["visual_type"],
                    priority="must_have",
                    suggested_source=visual_template["suggested_source"],
                ))

        # 2. Check domain-specific missing visuals
        claim_lower = claim.text.lower()
        for domain, visuals in self.domain_missing.items():
            if domain in claim_lower:
                for v in visuals:
                    # Check if something similar is already available
                    desc_lower = v["description"].lower()
                    is_available = any(
                        self._similar(desc_lower, av) for av in available_lower
                    )
                    if not is_available:
                        missing.append(MissingVisual(
                            description=v["description"],
                            reason=f"Domain requirement: {domain} evidence",
                            claim_text=claim.text,
                            visual_type=v["visual_type"],
                            priority=v.get("priority", "should_have"),
                            suggested_source=v.get("suggested_source", ""),
                        ))

        # 3. For speculative/pseudoscientific claims, suggest verification visuals
        if claim.truth_status in (TruthStatus.SPECULATIVE, TruthStatus.PSEUDOSCIENTIFIC):
            missing.append(MissingVisual(
                description="expert or scientist commenting on the claim's validity",
                reason="Speculative claims need expert context for responsible presentation",
                claim_text=claim.text,
                visual_type="footage",
                priority="should_have",
                suggested_source="interview or expert commentary",
            ))

        # 4. Deduplicate
        seen: set[str] = set()
        unique_missing: list[MissingVisual] = []
        for m in missing:
            if m.description not in seen:
                seen.add(m.description)
                unique_missing.append(m)

        # 5. Compute coverage score
        total_needed = len(available) + len(unique_missing)
        coverage = len(available) / total_needed if total_needed > 0 else 1.0

        # 6. Generate summary
        must_have = [m for m in unique_missing if m.priority == "must_have"]
        should_have = [m for m in unique_missing if m.priority == "should_have"]
        summary_parts = [
            f"Coverage: {coverage:.0%} of needed visuals available.",
            f"{len(unique_missing)} missing visual(s) identified.",
        ]
        if must_have:
            summary_parts.append(f"{len(must_have)} must-have (critical for evidence chain).")
        if should_have:
            summary_parts.append(f"{len(should_have)} should-have (improves completeness).")
        if not unique_missing:
            summary_parts.append("All needed visuals appear to be available.")

        return MissingVisualReport(
            missing_visuals=unique_missing,
            available_visuals=available,
            coverage_score=coverage,
            summary=" ".join(summary_parts),
        )

    def _similar(self, desc: str, available: str) -> bool:
        """Check if a description is similar to an available visual."""
        desc_words = set(desc.split())
        avail_words = set(available.split())
        overlap = desc_words & avail_words
        # If more than 30% of description words appear in available, consider it covered
        return len(overlap) / max(len(desc_words), 1) > 0.3

    def detect_for_claims(
        self,
        claims: list[Claim],
        assessments: list[EvidenceAssessment],
        available_visuals_by_claim: dict[str, list[str]] | None = None,
    ) -> list[MissingVisualReport]:
        """Detect missing visuals for multiple claims."""
        reports = []
        visuals_map = available_visuals_by_claim or {}
        for claim, assessment in zip(claims, assessments):
            available = visuals_map.get(claim.text, [])
            reports.append(self.detect(claim, assessment, available))
        return reports
