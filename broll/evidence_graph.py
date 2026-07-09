"""
Evidence Graph — Links claims to evidence, counter-evidence, confidence,
missing proof, and uncertainty.

The Evidence Graph answers:
    "What would prove this claim?"
    "What would disprove it?"
    "What evidence exists?"
    "What evidence is missing?"
    "How confident are we?"

Each claim becomes a node in the evidence graph with:
    - supporting evidence (sources, measurements, citations)
    - counter-evidence (contradictions, refutations)
    - missing evidence (what would need to exist to verify)
    - confidence score (how well-supported is the claim)
    - uncertainty level (how much we don't know)

This is NOT fact-checking against a database. It is structured uncertainty
mapping — the system explicitly tracks what it doesn't know.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .claim_extractor import Claim, TruthStatus


class EvidenceType(Enum):
    """Type of evidence."""
    MEASUREMENT = "measurement"
    CITATION = "citation"
    OBSERVATION = "observation"
    EXPERIMENT = "experiment"
    STATISTIC = "statistic"
    EXPERT_TESTIMONY = "expert_testimony"
    DOCUMENTARY_FOOTAGE = "documentary_footage"
    VISUAL_DEMONSTRATION = "visual_demonstration"
    MISSING = "missing"
    COUNTER = "counter"


class ConfidenceLevel(Enum):
    """Confidence level for a claim's evidence state."""
    HIGH = "high"           # Multiple independent sources, verifiable
    MODERATE = "moderate"   # Some evidence, not fully verified
    LOW = "low"             # Minimal or circumstantial evidence
    NONE = "none"           # No evidence found
    CONTRADICTED = "contradicted"  # Evidence exists against the claim


@dataclass
class EvidenceNode:
    """A single piece of evidence linked to a claim."""
    evidence_type: EvidenceType
    description: str
    source: str = ""
    confidence: float = 0.0  # 0.0-1.0
    available: bool = True   # False = missing evidence
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "evidence_type": self.evidence_type.value,
            "description": self.description,
            "source": self.source,
            "confidence": self.confidence,
            "available": self.available,
            "notes": self.notes,
        }


@dataclass
class EvidenceAssessment:
    """Complete evidence assessment for a claim."""
    claim_text: str
    truth_status: TruthStatus
    supporting_evidence: list[EvidenceNode] = field(default_factory=list)
    counter_evidence: list[EvidenceNode] = field(default_factory=list)
    missing_evidence: list[EvidenceNode] = field(default_factory=list)
    confidence_level: ConfidenceLevel = ConfidenceLevel.NONE
    confidence_score: float = 0.0
    uncertainty: float = 1.0  # 1.0 = completely uncertain, 0.0 = certain
    summary: str = ""

    def to_dict(self) -> dict:
        return {
            "claim_text": self.claim_text,
            "truth_status": self.truth_status.value,
            "supporting_evidence": [e.to_dict() for e in self.supporting_evidence],
            "counter_evidence": [e.to_dict() for e in self.counter_evidence],
            "missing_evidence": [e.to_dict() for e in self.missing_evidence],
            "confidence_level": self.confidence_level.value,
            "confidence_score": round(self.confidence_score, 3),
            "uncertainty": round(self.uncertainty, 3),
            "summary": self.summary,
        }


# Evidence patterns — what types of evidence would support different claim types
_EVIDENCE_REQUIREMENTS: dict[TruthStatus, list[EvidenceType]] = {
    TruthStatus.VERIFIED: [
        EvidenceType.MEASUREMENT,
        EvidenceType.CITATION,
        EvidenceType.EXPERIMENT,
    ],
    TruthStatus.SPECULATIVE: [
        EvidenceType.MEASUREMENT,
        EvidenceType.EXPERIMENT,
        EvidenceType.OBSERVATION,
    ],
    TruthStatus.PSEUDOSCIENTIFIC: [
        EvidenceType.EXPERIMENT,
        EvidenceType.MEASUREMENT,
        EvidenceType.CITATION,
    ],
    TruthStatus.FOLKLORE: [
        EvidenceType.CITATION,
        EvidenceType.OBSERVATION,
    ],
    TruthStatus.ENTERTAINMENT: [],
    TruthStatus.SYMBOLIC: [
        EvidenceType.OBSERVATION,
        EvidenceType.CITATION,
    ],
    TruthStatus.UNKNOWN: [
        EvidenceType.MEASUREMENT,
        EvidenceType.OBSERVATION,
        EvidenceType.CITATION,
    ],
}

# Domain-specific evidence templates
_DOMAIN_EVIDENCE: dict[str, list[str]] = {
    "resonance": [
        "frequency readings from accelerometer sensors",
        "acoustic testing of stone structures",
        "vibration measurement data",
        "repeatable resonance experiment",
    ],
    "energy": [
        "electromagnetic field measurements",
        "energy spectrum analysis",
        "calibrated instrument readings",
    ],
    "ancient": [
        "archaeological dating results",
        "material composition analysis",
        "peer-reviewed archaeological publication",
    ],
    "earth": [
        "geomagnetic field survey data",
        "geological measurements",
        "NASA/USGS scientific data",
    ],
    "frequency": [
        "spectrum analyzer readings",
        "oscilloscope measurements",
        "peer-reviewed frequency analysis",
    ],
    "megalithic": [
        "archaeological site survey",
        "stone structure analysis",
        "alignment verification with astronomical data",
    ],
    "cave": [
        "geological cave survey",
        "acoustic properties measurement",
    ],
    "solar": [
        "solar alignment measurement",
        "astronomical alignment verification",
        "solstice/equinox observation data",
    ],
}


class EvidenceGraph:
    """
    Evidence Graph — structured uncertainty mapping for claims.

    For each claim, determines:
    - What evidence would support it
    - What evidence would counter it
    - What evidence is missing
    - Overall confidence and uncertainty

    Usage:
        graph = EvidenceGraph()
        assessment = graph.assess_claim(claim)
        print(assessment.confidence_level, assessment.missing_evidence)
    """

    def __init__(self):
        self.evidence_requirements = dict(_EVIDENCE_REQUIREMENTS)
        self.domain_evidence = dict(_DOMAIN_EVIDENCE)
        self._assessments: list[EvidenceAssessment] = []

    def assess_claim(self, claim: Claim) -> EvidenceAssessment:
        """
        Assess the evidence state for a single claim.

        Args:
            claim: A Claim object with text, truth_status, and indicators

        Returns:
            EvidenceAssessment with supporting, counter, and missing evidence
        """
        # Determine what evidence would be needed
        required_types = self.evidence_requirements.get(claim.truth_status, [])

        # Find domain-specific evidence needs
        claim_lower = claim.text.lower()
        domain_missing: list[EvidenceNode] = []
        domain_supporting: list[EvidenceNode] = []

        for domain, evidence_list in self.domain_evidence.items():
            if domain in claim_lower:
                for ev_desc in evidence_list:
                    # Check if this evidence is indicated in the claim
                    if self._evidence_present(ev_desc, claim):
                        domain_supporting.append(EvidenceNode(
                            evidence_type=EvidenceType.OBSERVATION,
                            description=ev_desc,
                            confidence=0.6,
                            available=True,
                            notes="Evidence referenced in claim text",
                        ))
                    else:
                        domain_missing.append(EvidenceNode(
                            evidence_type=EvidenceType.MISSING,
                            description=ev_desc,
                            confidence=0.0,
                            available=False,
                            notes="Required evidence not found in claim",
                        ))

        # Generate counter-evidence for speculative/pseudoscientific claims
        counter: list[EvidenceNode] = []
        if claim.truth_status in (TruthStatus.SPECULATIVE, TruthStatus.PSEUDOSCIENTIFIC):
            counter.append(EvidenceNode(
                evidence_type=EvidenceType.COUNTER,
                description="No peer-reviewed publication found supporting this claim",
                confidence=0.8,
                available=True,
                notes="Absence of scientific literature",
            ))
            if claim.truth_status == TruthStatus.PSEUDOSCIENTIFIC:
                counter.append(EvidenceNode(
                    evidence_type=EvidenceType.COUNTER,
                    description="Claim uses terminology that mimics science without scientific method",
                    confidence=0.7,
                    available=True,
                    notes="Pseudoscientific indicator detected",
                ))

        # Check for evidence indicators in the claim
        if claim.evidence_indicators:
            for indicator in claim.evidence_indicators:
                domain_supporting.append(EvidenceNode(
                    evidence_type=EvidenceType.CITATION,
                    description=f"Evidence indicator: {indicator}",
                    confidence=0.7,
                    available=True,
                    notes="Detected in claim text",
                ))

        # Compute confidence
        supporting_count = len(domain_supporting)
        missing_count = len(domain_missing)
        counter_count = len(counter)

        if claim.truth_status == TruthStatus.VERIFIED:
            base_confidence = 0.8
        elif claim.truth_status == TruthStatus.SPECULATIVE:
            base_confidence = 0.3
        elif claim.truth_status == TruthStatus.PSEUDOSCIENTIFIC:
            base_confidence = 0.1
        elif claim.truth_status == TruthStatus.FOLKLORE:
            base_confidence = 0.2
        elif claim.truth_status == TruthStatus.ENTERTAINMENT:
            base_confidence = 0.5  # Entertainment doesn't need evidence
        elif claim.truth_status == TruthStatus.SYMBOLIC:
            base_confidence = 0.4
        else:
            base_confidence = 0.0

        # Adjust based on evidence availability
        evidence_boost = min(0.15, supporting_count * 0.05)
        evidence_penalty = min(0.3, counter_count * 0.15)
        confidence_score = max(0.0, min(1.0,
            base_confidence + evidence_boost - evidence_penalty
        ))

        # Determine confidence level
        if counter_count > 0 and confidence_score < 0.2:
            confidence_level = ConfidenceLevel.CONTRADICTED
        elif confidence_score >= 0.7:
            confidence_level = ConfidenceLevel.HIGH
        elif confidence_score >= 0.4:
            confidence_level = ConfidenceLevel.MODERATE
        elif confidence_score >= 0.1:
            confidence_level = ConfidenceLevel.LOW
        else:
            confidence_level = ConfidenceLevel.NONE

        uncertainty = 1.0 - confidence_score

        # Generate summary
        summary = self._generate_summary(
            claim, confidence_level, supporting_count, missing_count, counter_count
        )

        assessment = EvidenceAssessment(
            claim_text=claim.text,
            truth_status=claim.truth_status,
            supporting_evidence=domain_supporting,
            counter_evidence=counter,
            missing_evidence=domain_missing,
            confidence_level=confidence_level,
            confidence_score=confidence_score,
            uncertainty=uncertainty,
            summary=summary,
        )

        self._assessments.append(assessment)
        return assessment

    def _evidence_present(self, evidence_desc: str, claim: Claim) -> bool:
        """
        Check if evidence is indicated in the claim text.

        For speculative/pseudoscientific claims, scientific-sounding words
        in the claim text do NOT count as evidence — the claim itself is
        the assertion, not the proof. Only explicit evidence indicators
        (citations, references, studies) count.
        """
        claim_lower = claim.text.lower()

        # Check for explicit evidence indicators (citations, references)
        if claim.evidence_indicators:
            return True

        # For non-speculative claims, measurement-like language can indicate evidence
        if claim.truth_status not in (TruthStatus.SPECULATIVE, TruthStatus.PSEUDOSCIENTIFIC,
                                       TruthStatus.UNKNOWN):
            measurement_patterns = ["measured", "recorded", "published",
                                    "peer-reviewed", "verified", "tested",
                                    "demonstrated", "shown", "proven"]
            for pattern in measurement_patterns:
                if pattern in claim_lower:
                    return True

        return False

    def _generate_summary(
        self,
        claim: Claim,
        level: ConfidenceLevel,
        supporting: int,
        missing: int,
        counter: int,
    ) -> str:
        """Generate a human-readable evidence summary."""
        parts = [f"Claim truth status: {claim.truth_status.value}."]
        parts.append(f"Confidence: {level.value} ({'high' if level == ConfidenceLevel.HIGH else 'limited' if level in (ConfidenceLevel.MODERATE, ConfidenceLevel.LOW) else 'no'} evidence).")
        if supporting > 0:
            parts.append(f"{supporting} supporting evidence item(s) found.")
        if missing > 0:
            parts.append(f"{missing} required evidence item(s) missing.")
        if counter > 0:
            parts.append(f"{counter} counter-evidence item(s) identified.")
        if missing > 0 and level in (ConfidenceLevel.NONE, ConfidenceLevel.LOW):
            parts.append("Claim remains unverified without additional evidence.")
        return " ".join(parts)

    def assess_claims(self, claims: list[Claim]) -> list[EvidenceAssessment]:
        """Assess multiple claims."""
        return [self.assess_claim(c) for c in claims]

    @property
    def assessments(self) -> list[EvidenceAssessment]:
        """All assessments made so far."""
        return self._assessments

    def get_missing_evidence_summary(self) -> list[str]:
        """Get a summary of all missing evidence across all claims."""
        missing: list[str] = []
        for assessment in self._assessments:
            for ev in assessment.missing_evidence:
                if ev.description not in missing:
                    missing.append(ev.description)
        return missing
