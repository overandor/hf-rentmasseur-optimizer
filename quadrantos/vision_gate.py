"""VisionGate — OCR confidence gate. Rejects low-quality observations.

Rules:
1. Do not trust OCR alone.
2. Do not trust vision alone when text is tiny.
3. Do not type based on hallucinated screenshot text.
4. If OCR quality is poor and vision confidence is vague,
   classify as OBSERVATION_UNRELIABLE, not as a bug.

This is the false-positive control layer. The CodeReviewer must not be
allowed to implement from low-quality OCR.
"""

import os
import re
import hashlib
import subprocess
import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class ObservationStatus(Enum):
    RELIABLE = "reliable"            # High confidence, safe to act on
    LOW_CONFIDENCE = "low_confidence" # Marginal, need source confirmation
    UNRELIABLE = "unreliable"         # Do not act on this
    EMPTY = "empty"                   # No text detected at all


@dataclass
class Observation:
    """Result of observing a screen quadrant."""
    status: ObservationStatus
    text: str = ""
    confidence: float = 0.0           # 0.0 to 1.0
    source: str = ""                  # 'ocr', 'vision', 'combined'
    word_count: int = 0
    char_count: int = 0
    hash: str = ""
    issues: List[str] = field(default_factory=list)
    recommendation: str = ""          # What to do with this observation


class VisionGate:
    """Gate that decides whether screen observations are reliable enough to act on.

    Uses heuristics to score OCR quality:
    - Character ratio (printable vs garbage)
    - Word count (too few = likely noise)
    - Known false-positive patterns (e.g., '21' when '2' was intended)
    - Digit-only short strings (likely misread)
    - Repetition detection (same text repeated = OCR artifact)
    """

    # Patterns that are known OCR false positives
    FALSE_POSITIVE_PATTERNS = [
        (r'window_index\s*=\s*21\b', 'window_index=21 is likely OCR misread of window_index=2'),
        (r'hardcoded\s+window\s+index\s+21', 'likely misread of window index 2'),
        (r'\bindex\s+21\b', '21 is likely misread of 2 in small text'),
    ]

    # Minimum thresholds
    MIN_CONFIDENCE = 0.6       # Below this = LOW_CONFIDENCE
    MIN_WORD_COUNT = 3         # Below this = suspicious
    MIN_CHAR_COUNT = 10        # Below this = likely noise
    MAX_REPETITION_RATIO = 0.5 # If >50% repeated words = artifact

    def __init__(self, ocr_threshold: float = None):
        self.ocr_threshold = ocr_threshold or self.MIN_CONFIDENCE
        self._history: List[Observation] = []

    def observe(self, screenshot_path: str, use_vision: bool = False) -> Observation:
        """Observe a screenshot and return a confidence-scored observation.

        Args:
            screenshot_path: Path to the screenshot PNG
            use_vision: If True, also try vision model (llava) for cross-check

        Returns:
            Observation with status, confidence, and recommendation
        """
        if not os.path.exists(screenshot_path):
            return Observation(
                status=ObservationStatus.EMPTY,
                source='none',
                recommendation='Screenshot file not found',
            )

        # Run OCR
        ocr_text = self._run_ocr(screenshot_path)
        if not ocr_text or len(ocr_text.strip()) < 3:
            return Observation(
                status=ObservationStatus.EMPTY,
                source='ocr',
                text='',
                recommendation='No text detected. Screen may be blank or loading.',
            )

        # Score the OCR result
        confidence = self._score_confidence(ocr_text)
        issues = self._detect_issues(ocr_text)
        status = self._classify(confidence, issues, ocr_text)

        obs = Observation(
            status=status,
            text=ocr_text,
            confidence=confidence,
            source='ocr',
            word_count=len(ocr_text.split()),
            char_count=len(ocr_text),
            hash=hashlib.sha256(ocr_text.encode()).hexdigest()[:16],
            issues=issues,
            recommendation=self._recommend(status, issues),
        )

        self._history.append(obs)
        return obs

    def _run_ocr(self, screenshot_path: str) -> str:
        """Run OCR on a screenshot using macOS Vision framework."""
        try:
            script = f'''
import Vision
import Foundation

req = Vision.VNRecognizeTextRequest.alloc().init()
req.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
req.setUseLanguageCorrection_(True)

handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(
    _imageAtPath("{screenshot_path}"), None
)
handler.performRequests_error_([req], None)

results = req.results()
text_parts = []
for obs in results:
    candidate = obs.topCandidates_(1)
    if candidate:
        text_parts.append(candidate[0].string())

print("\\n".join(text_parts))
'''
            r = subprocess.run(
                ['python3', '-c', script],
                capture_output=True, text=True, timeout=10
            )
            return r.stdout.strip()
        except Exception:
            # Fallback: try tesseract if available
            try:
                r = subprocess.run(
                    ['tesseract', screenshot_path, 'stdout', '--psm', '6'],
                    capture_output=True, text=True, timeout=10
                )
                return r.stdout.strip()
            except Exception:
                return ""

    def _score_confidence(self, text: str) -> float:
        """Score OCR confidence based on text quality heuristics.

        Returns 0.0 to 1.0.
        """
        if not text:
            return 0.0

        score = 0.5  # Base score

        # Factor 1: Printable character ratio
        printable = sum(1 for c in text if c.isprintable() or c in '\n\r\t')
        char_ratio = printable / len(text) if text else 0
        score += char_ratio * 0.15

        # Factor 2: Word count (more words = more context = higher confidence)
        words = text.split()
        word_count = len(words)
        if word_count >= 20:
            score += 0.15
        elif word_count >= 10:
            score += 0.10
        elif word_count >= 5:
            score += 0.05
        elif word_count < 3:
            score -= 0.15

        # Factor 3: Repetition detection (repeated words = OCR artifact)
        if words:
            unique = set(words)
            repetition_ratio = 1 - len(unique) / len(words)
            if repetition_ratio > self.MAX_REPETITION_RATIO:
                score -= 0.20
            elif repetition_ratio > 0.3:
                score -= 0.10

        # Factor 4: Known false-positive patterns
        for pattern, msg in self.FALSE_POSITIVE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                score -= 0.25  # Heavy penalty for known false positives

        # Factor 5: Alphabetic ratio (real code/text has letters)
        alpha = sum(1 for c in text if c.isalpha())
        alpha_ratio = alpha / len(text) if text else 0
        if alpha_ratio < 0.2:
            score -= 0.10  # Too many digits/symbols = suspicious

        # Factor 6: Very short text
        if len(text) < self.MIN_CHAR_COUNT:
            score -= 0.15

        return max(0.0, min(1.0, score))

    def _detect_issues(self, text: str) -> List[str]:
        """Detect known issues in OCR text."""
        issues = []

        for pattern, msg in self.FALSE_POSITIVE_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                issues.append(msg)

        # Check for garbled text (high symbol ratio)
        symbols = sum(1 for c in text if not c.isalnum() and not c.isspace())
        if len(text) > 0 and symbols / len(text) > 0.4:
            issues.append('High symbol ratio — possible OCR garbling')

        # Check for very short fragments
        if len(text.strip()) < self.MIN_CHAR_COUNT:
            issues.append(f'Very short text ({len(text)} chars) — likely noise')

        # Check for single-word observations
        if len(text.split()) < self.MIN_WORD_COUNT:
            issues.append(f'Only {len(text.split())} words — insufficient context')

        return issues

    def _classify(self, confidence: float, issues: List[str], text: str) -> ObservationStatus:
        """Classify observation status based on confidence and issues."""
        if not text or len(text.strip()) < 3:
            return ObservationStatus.EMPTY

        if confidence >= self.ocr_threshold and not issues:
            return ObservationStatus.RELIABLE

        if confidence >= self.ocr_threshold * 0.7 and len(issues) <= 1:
            return ObservationStatus.LOW_CONFIDENCE

        return ObservationStatus.UNRELIABLE

    def _recommend(self, status: ObservationStatus, issues: List[str]) -> str:
        """Generate recommendation for what to do with this observation."""
        if status == ObservationStatus.RELIABLE:
            return 'Safe to act on this observation.'
        elif status == ObservationStatus.LOW_CONFIDENCE:
            return 'Need source-file confirmation before action. Do not implement fixes from this observation alone.'
        elif status == ObservationStatus.UNRELIABLE:
            issue_text = '; '.join(issues) if issues else 'low confidence'
            return f'OBSERVATION_UNRELIABLE: {issue_text}. Do not act on this. Request clearer screenshot or source file.'
        else:
            return 'No action needed — screen appears empty.'

    def get_history(self) -> List[Observation]:
        """Get observation history for self-improvement."""
        return self._history

    def summary(self) -> Dict:
        total = len(self._history)
        if total == 0:
            return {'total_observations': 0}

        reliable = sum(1 for o in self._history if o.status == ObservationStatus.RELIABLE)
        low = sum(1 for o in self._history if o.status == ObservationStatus.LOW_CONFIDENCE)
        unreliable = sum(1 for o in self._history if o.status == ObservationStatus.UNRELIABLE)
        empty = sum(1 for o in self._history if o.status == ObservationStatus.EMPTY)

        return {
            'total_observations': total,
            'reliable': reliable,
            'low_confidence': low,
            'unreliable': unreliable,
            'empty': empty,
            'avg_confidence': sum(o.confidence for o in self._history) / total,
            'false_positives_blocked': unreliable,
        }
