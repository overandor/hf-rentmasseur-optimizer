"""
Claim Extractor — Speech reformer + claim extraction + truth-status classification.

Two layers:
1. Semantic-match layer: finds footage matching what the speaker is saying
2. Truth-status layer: labels the spoken claim as verified, speculative, symbolic,
   folklore, pseudoscientific, entertainment, or unknown

This transforms the system from "auto-B-roll" into a Narration-to-Evidence
Video Compiler that asks:
    - What is the speaker claiming?
    - What visual material represents that claim?
    - What available video matches it?
    - What is the confidence?
    - What is the rights status?
    - What is the truth status?
"""

import re
import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TruthStatus(Enum):
    """Truth status of a spoken claim."""
    VERIFIED = "verified"              # backed by measurable evidence, peer review, instruments
    SPECULATIVE = "speculative"        # plausible but unproven; uses hedging language
    SYMBOLIC = "symbolic"              # metaphorical / allegorical, not literal claim
    FOLKLORE = "folklore"             # cultural tradition / oral history, not scientific
    PSEUDOSCIENTIFIC = "pseudoscientific"  # uses science-like language but lacks evidence
    ENTERTAINMENT = "entertainment"    # show narration / dramatic framing
    UNKNOWN = "unknown"               # insufficient information to classify


@dataclass
class Claim:
    """A claim extracted from narration, with truth-status classification."""
    claim_id: str
    text: str
    reformed_text: str  # speech-reformed version (cleaned, normalized)
    truth_status: TruthStatus
    truth_confidence: float  # 0.0 to 1.0
    truth_reasoning: str
    evidence_indicators: list[str] = field(default_factory=list)
    hedge_indicators: list[str] = field(default_factory=list)
    scientific_terms: list[str] = field(default_factory=list)
    speculative_terms: list[str] = field(default_factory=list)
    timestamp_start: float = 0.0
    timestamp_end: float = 0.0

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "text": self.text,
            "reformed_text": self.reformed_text,
            "truth_status": self.truth_status.value,
            "truth_confidence": self.truth_confidence,
            "truth_reasoning": self.truth_reasoning,
            "evidence_indicators": self.evidence_indicators,
            "hedge_indicators": self.hedge_indicators,
            "scientific_terms": self.scientific_terms,
            "speculative_terms": self.speculative_terms,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
        }


# Hedge words that indicate speculation, not assertion
_HEDGE_WORDS = {
    "could", "might", "may", "possibly", "perhaps", "allegedly", "supposedly",
    "purportedly", "reportedly", "said to be", "believed to be", "thought to be",
    "theorized", "hypothesized", "suggested", "proposed", "claimed", "argued",
    "some say", "many believe", "according to", "legend has it", "it is said",
    "could have", "might have", "may have", "must have", "would have",
    "appears to", "seems to", "looks like", "feels like",
}

# Scientific / evidence-based terms
_SCIENTIFIC_TERMS = {
    "frequency", "resonance", "wavelength", "electromagnetic", "hertz", "hz",
    "measured", "detected", "observed", "recorded", "calibrated", "instrument",
    "peer-reviewed", "study", "research", "experiment", "data", "evidence",
    "schumann", "geomagnetic", "seismic", "acoustic", "spectrum", "amplitude",
    "oscillation", "vibration", "conductivity", "magnetometer", "spectrometer",
    "nasa", "noaa", "usgs", "published", "journal", "doi", "arxiv",
}

# Speculative / pseudoscientific indicators
_SPECULATIVE_TERMS = {
    "ancient aliens", "lost technology", "hidden knowledge", "secret energy",
    "forbidden archaeology", "suppressed", "they don't want you to know",
    "mainstream science", "alternative", "fringe", "rediscovered",
    "ancient wisdom", "sacred knowledge", "mystery school", "esoteric",
    "occult", "metaphysical", "supernatural", "paranormal", "otherworldly",
    "interdimensional", "stargate", "portal", "vortex", "ley lines",
    "earth energy", "planetary consciousness", "crystal power",
    "vibrational healing", "frequency healing", "energy healing",
    "consciousness field", "morphic resonance", "quantum consciousness",
}

# Folklore / cultural tradition indicators
_FOLKLORE_TERMS = {
    "legend", "myth", "folklore", "oral tradition", "ancient peoples believed",
    "according to legend", "story goes", "tales of", "sacred stories",
    "indigenous", "ancestral", "ceremonial", "ritual", "shaman",
}

# Entertainment / show narration indicators
_ENTERTAINMENT_TERMS = {
    "what if", "imagine", "picture this", "consider this", "what could be",
    "mystery", "enigma", "riddle", "puzzle", "secret", "hidden",
    "unexplained", "unsolved", "bizarre", "strange", "incredible",
    "amazing", "shocking", "unbelievable", "astounding",
}

# Verified / evidence-backed indicators
_VERIFIED_INDICATORS = {
    "nasa", "noaa", "usgs", "published in", "peer-reviewed", "measured",
    "detected by", "recorded at", "observed using", "data shows",
    "study found", "research indicates", "experiment confirmed",
    "instrument reading", "frequency of", "hertz", "hz",
}


class ClaimExtractor:
    """
    Extracts and classifies claims from narration.

    Pipeline:
        1. Speech reformer — clean and normalize the transcript
        2. Claim extraction — identify assertion units
        3. Truth-status classification — label each claim

    The truth-status layer is what separates this from simple auto-B-roll.
    It asks "What is the truth status of this claim?" not just "What clip looks right?"
    """

    def __init__(self):
        self.hedge_words = set(_HEDGE_WORDS)
        self.scientific_terms = set(_SCIENTIFIC_TERMS)
        self.speculative_terms = set(_SPECULATIVE_TERMS)
        self.folklore_terms = set(_FOLKLORE_TERMS)
        self.entertainment_terms = set(_ENTERTAINMENT_TERMS)
        self.verified_indicators = set(_VERIFIED_INDICATORS)

    def reform_speech(self, text: str) -> str:
        """
        Speech reformer — clean and normalize transcript text.

        - Remove filler words and phrases
        - Normalize whitespace
        - Fix common transcription artifacts
        - Preserve meaning
        """
        # Remove multi-word filler phrases first
        multi_word_fillers = [
            "you know", "sort of", "kind of", "i mean", "or something",
            "and stuff", "and things", "and whatever",
        ]
        result = text
        for phrase in multi_word_fillers:
            result = re.sub(re.escape(phrase), "", result, flags=re.IGNORECASE)

        # Remove single-word fillers
        fillers = {"um", "uh", "er", "ah", "like"}
        words = result.split()
        cleaned = [w for w in words if w.lower().strip(",.") not in fillers]

        # Normalize whitespace
        result = " ".join(cleaned)
        result = re.sub(r"\s+", " ", result).strip()

        # Fix common transcription artifacts
        result = re.sub(r"\bi\b", "I", result)  # standalone i → I
        result = re.sub(r"\s+([,.!?])", r"\1", result)  # space before punctuation

        return result

    def extract_claims(
        self,
        text: str,
        timestamp_start: float = 0.0,
        timestamp_end: float | None = None,
    ) -> list[Claim]:
        """
        Extract claims from narration text.

        A claim is an assertion unit — a sentence or clause that
        makes a statement about reality.
        """
        if timestamp_end is None:
            timestamp_end = timestamp_start + 10.0

        reformed = self.reform_speech(text)

        # Split into sentences / assertion units
        sentences = re.split(r"[.!?]+", reformed)
        sentences = [s.strip() for s in sentences if s.strip()]

        claims: list[Claim] = []
        for i, sentence in enumerate(sentences):
            claim = self._classify_claim(
                sentence,
                original_text=text,
                timestamp_start=timestamp_start + (i / max(len(sentences), 1)) * (timestamp_end - timestamp_start),
                timestamp_end=timestamp_start + ((i + 1) / max(len(sentences), 1)) * (timestamp_end - timestamp_start),
            )
            claims.append(claim)

        return claims

    def _classify_claim(
        self,
        sentence: str,
        original_text: str,
        timestamp_start: float,
        timestamp_end: float,
    ) -> Claim:
        """Classify a single claim's truth status."""
        sentence_lower = sentence.lower()
        words = set(re.findall(r"[a-zA-Z]+", sentence_lower))

        # Collect indicators
        evidence_indicators = [w for w in self.verified_indicators if w in sentence_lower]
        hedge_indicators = [w for w in self.hedge_words if w in sentence_lower]
        scientific_terms = [w for w in self.scientific_terms if w in sentence_lower]
        speculative_terms = [w for w in self.speculative_terms if w in sentence_lower]
        folklore_terms = [w for w in self.folklore_terms if w in sentence_lower]
        entertainment_terms = [w for w in self.entertainment_terms if w in sentence_lower]

        # Scoring for each truth status
        scores: dict[TruthStatus, float] = {
            TruthStatus.VERIFIED: 0.0,
            TruthStatus.SPECULATIVE: 0.0,
            TruthStatus.SYMBOLIC: 0.0,
            TruthStatus.FOLKLORE: 0.0,
            TruthStatus.PSEUDOSCIENTIFIC: 0.0,
            TruthStatus.ENTERTAINMENT: 0.0,
            TruthStatus.UNKNOWN: 0.1,  # baseline
        }

        # Verified: needs evidence indicators + scientific terms, low hedges
        if evidence_indicators and scientific_terms and not hedge_indicators:
            scores[TruthStatus.VERIFIED] = 0.7 + len(evidence_indicators) * 0.1
        elif evidence_indicators and scientific_terms:
            scores[TruthStatus.VERIFIED] = 0.4 + len(evidence_indicators) * 0.1

        # Speculative: hedges present, some scientific terms
        if hedge_indicators:
            scores[TruthStatus.SPECULATIVE] = 0.4 + len(hedge_indicators) * 0.1
            if scientific_terms:
                scores[TruthStatus.SPECULATIVE] += 0.1

        # Pseudoscientific: speculative terms + science-like language but no evidence
        if speculative_terms:
            scores[TruthStatus.PSEUDOSCIENTIFIC] = 0.3 + len(speculative_terms) * 0.15
            if scientific_terms and not evidence_indicators:
                scores[TruthStatus.PSEUDOSCIENTIFIC] += 0.2
            if hedge_indicators:
                scores[TruthStatus.PSEUDOSCIENTIFIC] += 0.1

        # Folklore
        if folklore_terms:
            scores[TruthStatus.FOLKLORE] = 0.4 + len(folklore_terms) * 0.15

        # Entertainment
        if entertainment_terms:
            scores[TruthStatus.ENTERTAINMENT] = 0.3 + len(entertainment_terms) * 0.1

        # Symbolic: metaphorical language
        symbolic_indicators = {"like", "as if", "represents", "symbolizes", "metaphor", "echoes"}
        if any(ind in sentence_lower for ind in symbolic_indicators):
            scores[TruthStatus.SYMBOLIC] = 0.5

        # Pick highest score
        best_status = max(scores, key=scores.get)
        best_score = scores[best_status]
        confidence = min(1.0, best_score)

        # Build reasoning
        reasoning = self._build_reasoning(
            best_status, evidence_indicators, hedge_indicators,
            scientific_terms, speculative_terms, folklore_terms, entertainment_terms,
        )

        claim_id = hashlib.sha256(
            f"{sentence}:{timestamp_start}".encode()
        ).hexdigest()[:12]

        return Claim(
            claim_id=claim_id,
            text=sentence,
            reformed_text=self.reform_speech(sentence),
            truth_status=best_status,
            truth_confidence=confidence,
            truth_reasoning=reasoning,
            evidence_indicators=evidence_indicators,
            hedge_indicators=hedge_indicators,
            scientific_terms=scientific_terms,
            speculative_terms=speculative_terms,
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_end,
        )

    def _build_reasoning(
        self,
        status: TruthStatus,
        evidence: list[str],
        hedges: list[str],
        scientific: list[str],
        speculative: list[str],
        folklore: list[str],
        entertainment: list[str],
    ) -> str:
        """Build human-readable reasoning for the truth-status classification."""
        parts: list[str] = []

        if status == TruthStatus.VERIFIED:
            parts.append(f"Classified as VERIFIED: evidence indicators {evidence}, scientific terms {scientific}, no hedges.")
        elif status == TruthStatus.SPECULATIVE:
            parts.append(f"Classified as SPECULATIVE: hedge language {hedges}")
            if scientific:
                parts.append(f"Contains scientific terms {scientific} but lacks evidence backing.")
        elif status == TruthStatus.PSEUDOSCIENTIFIC:
            parts.append(f"Classified as PSEUDOSCIENTIFIC: speculative terms {speculative}")
            if scientific:
                parts.append(f"Uses science-like language {scientific} but without evidence indicators.")
            if hedges:
                parts.append(f"Hedge language present: {hedges}")
        elif status == TruthStatus.FOLKLORE:
            parts.append(f"Classified as FOLKLORE: cultural/traditional indicators {folklore}")
        elif status == TruthStatus.ENTERTAINMENT:
            parts.append(f"Classified as ENTERTAINMENT: show narration indicators {entertainment}")
        elif status == TruthStatus.SYMBOLIC:
            parts.append("Classified as SYMBOLIC: metaphorical/allegorical language detected.")
        else:
            parts.append("Classified as UNKNOWN: insufficient indicators to classify.")

        return " ".join(parts)

    def classify_text(self, text: str) -> TruthStatus:
        """Quick classification — returns just the truth status for a text."""
        claims = self.extract_claims(text)
        if not claims:
            return TruthStatus.UNKNOWN
        return claims[0].truth_status
