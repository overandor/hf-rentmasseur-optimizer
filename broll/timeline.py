"""
Timeline — Assemble ranked evidence into a synchronized B-roll timeline.

Takes the best matching video clips and places them at the correct
timestamps in the narration timeline, producing an edited sequence.

Output formats:
    - JSON timeline (machine-readable)
    - EDL (Edit Decision List, for NLE import)
    - Human-readable summary
"""

import json
import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional
from .video_search import VideoCandidate


@dataclass
class TimelineSegment:
    """A single B-roll segment placed in the timeline."""
    segment_id: str
    order: int
    narration_text: str
    narration_start: float
    narration_end: float
    clip_title: str
    clip_url: str
    clip_source: str
    clip_duration: float
    composite_score: float
    score_breakdown: dict = field(default_factory=dict)
    matched_concept: str = ""
    matched_archetype: str = ""
    emotional_tone: str = "neutral"

    def to_dict(self) -> dict:
        return {
            "segment_id": self.segment_id,
            "order": self.order,
            "narration_text": self.narration_text,
            "narration_start": self.narration_start,
            "narration_end": self.narration_end,
            "clip_title": self.clip_title,
            "clip_url": self.clip_url,
            "clip_source": self.clip_source,
            "clip_duration": self.clip_duration,
            "composite_score": self.composite_score,
            "score_breakdown": self.score_breakdown,
            "matched_concept": self.matched_concept,
            "matched_archetype": self.matched_archetype,
            "emotional_tone": self.emotional_tone,
        }

    def to_edl(self) -> str:
        """Generate EDL entry for this segment."""
        # Simple EDL format
        clip_in = "00:00:00:00"
        clip_out = f"00:00:{int(self.clip_duration):02d}:00"
        narr_in = self._frames(self.narration_start)
        narr_out = self._frames(self.narration_end)
        return (
            f"{self.order:03d}  AX       V     C        {clip_in} {clip_out} {narr_in} {narr_out}\n"
            f"FROM CLIP NAME: {self.clip_title}\n"
        )

    def _frames(self, seconds: float, fps: int = 30) -> str:
        """Convert seconds to timecode HH:MM:SS:FF."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        f = int((seconds % 1) * fps)
        return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"


@dataclass
class Timeline:
    """A complete B-roll timeline synchronized to narration."""
    timeline_id: str
    created_at: float
    total_duration: float
    segments: list[TimelineSegment] = field(default_factory=list)
    source_text: str = ""
    average_score: float = 0.0

    def to_dict(self) -> dict:
        return {
            "timeline_id": self.timeline_id,
            "created_at": self.created_at,
            "total_duration": self.total_duration,
            "segments": [s.to_dict() for s in self.segments],
            "source_text": self.source_text,
            "average_score": self.average_score,
            "segment_count": len(self.segments),
        }

    def to_json(self, path: str | None = None) -> str:
        """Export timeline as JSON. Writes to file if path given."""
        data = self.to_dict()
        text = json.dumps(data, indent=2)
        if path:
            with open(path, "w") as f:
                f.write(text)
        return text

    def to_edl(self, path: str | None = None) -> str:
        """Export timeline as EDL (Edit Decision List)."""
        lines = ["TITLE: B-Roll Compiler Output\n"]
        for seg in self.segments:
            lines.append(seg.to_edl())
        edl_text = "".join(lines)
        if path:
            with open(path, "w") as f:
                f.write(edl_text)
        return edl_text

    def to_summary(self) -> str:
        """Human-readable timeline summary."""
        lines = [
            f"B-Roll Timeline ({len(self.segments)} segments, avg score {self.average_score:.2f})",
            "=" * 60,
        ]
        for seg in self.segments:
            lines.append(
                f"\n[{seg.order}] {seg.narration_start:.1f}s - {seg.narration_end:.1f}s"
                f"  (score: {seg.composite_score:.2f})"
            )
            lines.append(f"  Narration: \"{seg.narration_text}\"")
            lines.append(f"  Clip: {seg.clip_title}")
            lines.append(f"  Source: {seg.clip_source}")
            lines.append(f"  Archetype: {seg.matched_archetype}")
            lines.append(f"  Tone: {seg.emotional_tone}")
        return "\n".join(lines)


class TimelineAssembler:
    """
    Assembles video candidates into a synchronized B-roll timeline.

    Takes the best matching clip for each narration concept and places
    it at the correct timestamp, producing an edited sequence.
    """

    def assemble(
        self,
        source_text: str,
        total_duration: float,
        concept_clips: list[dict],
    ) -> Timeline:
        """
        Assemble timeline from concept-clip mappings.

        Args:
            source_text: Full narration text
            total_duration: Total narration duration in seconds
            concept_clips: List of dicts with keys:
                - concept_label
                - timestamp_start
                - timestamp_end
                - best_clip: VideoCandidate
                - archetype_label
                - emotional_tone

        Returns:
            Timeline object with segments
        """
        timeline_id = hashlib.sha256(
            f"{source_text}:{time.time()}".encode()
        ).hexdigest()[:16]

        segments: list[TimelineSegment] = []
        scores: list[float] = []

        for i, cc in enumerate(concept_clips):
            clip: VideoCandidate = cc["best_clip"]
            if clip is None:
                continue

            seg = TimelineSegment(
                segment_id=hashlib.sha256(
                    f"{cc['concept_label']}:{i}".encode()
                ).hexdigest()[:12],
                order=i,
                narration_text=cc.get("concept_label", ""),
                narration_start=cc["timestamp_start"],
                narration_end=cc["timestamp_end"],
                clip_title=clip.title,
                clip_url=clip.url,
                clip_source=clip.source,
                clip_duration=clip.duration_seconds,
                composite_score=clip.composite_score,
                score_breakdown={
                    "semantic_similarity": clip.semantic_similarity,
                    "visual_clarity": clip.visual_clarity,
                    "timing_fit": clip.timing_fit,
                    "copyright_safety": clip.copyright_safety,
                    "emotional_tone_match": clip.emotional_tone_match,
                },
                matched_concept=cc.get("concept_label", ""),
                matched_archetype=clip.matched_archetype,
                emotional_tone=cc.get("emotional_tone", "neutral"),
            )
            segments.append(seg)
            scores.append(clip.composite_score)

        avg_score = sum(scores) / len(scores) if scores else 0.0

        return Timeline(
            timeline_id=timeline_id,
            created_at=time.time(),
            total_duration=total_duration,
            segments=segments,
            source_text=source_text,
            average_score=avg_score,
        )
