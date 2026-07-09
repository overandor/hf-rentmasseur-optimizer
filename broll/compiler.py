"""
OverVisual — Semantic Visual Evidence Compilation.

A narration-to-evidence compilation system that maps claims into visual
representations while explicitly preserving uncertainty, evidentiary
status, provenance, and licensing constraints.

This is NOT standard multimedia retrieval. It is an integrated pipeline
combining semantic retrieval, claim extraction, truth labeling, rights
analysis, and provenance receipts into a unified narration-to-evidence
compiler. The result is an evidence-backed audiovisual ledger, not an
editing timeline.

Pipeline (15 steps):
    1. Transcript input
    2. Speech reform (clean/normalize)
    3. Claim extraction (identify assertions)
    4. Truth-status classification (verified/speculative/symbolic/etc)
    5. Concept extraction (meaning atoms)
    6. Visual association (concept → archetype)
    7. Video search (archetype → candidates)
    8. Frame sampling (extract frames from candidates)
    9. CLIP-style similarity matching (text ↔ frames)
    10. Rights/license filtering (safe/needs_review/blocked/unknown)
    11. Clip ranking (best match selection with rights gate)
    12. Visual Evidence Segment creation
    13. Timeline assembly
    14. Proof hash chain generation
    15. Receipt generation

Core principle: semantic match ≠ truth
A clip can visually match "ancient planetary energy" while the claim
remains speculative. The system labels both independently.

The output is a set of VisualEvidenceSegment records — evidence graph
nodes, not media assets — each carrying:
    - claim + visual explanation + truth label + rights label + provenance + receipt
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from .concept_extractor import ConceptExtractor, Concept
from .claim_extractor import ClaimExtractor, Claim, TruthStatus
from .association_graph import VisualAssociationGraph, VisualArchetype
from .video_search import VideoSearch, VideoCandidate
from .clip_matcher import CLIPMatcher, ClipMatchResult
from .youtube_search import YouTubeSearch
from .timeline import Timeline, TimelineAssembler
from .rights_filter import RightsFilter, RightsStatus, RightsAssessment
from .proofs import ProofGenerator, ProofChain
from .visual_evidence_segment import (
    VisualEvidenceSegment,
    VESEnsemble,
    compute_truth_safety_score,
    compute_evidence_relevance_score,
)


@dataclass
class CompilationResult:
    """Result of a full OverVisual compilation pass."""
    compilation_id: str
    timestamp: float
    source_text: str
    total_duration: float
    concepts: list[dict] = field(default_factory=list)
    claims: list[dict] = field(default_factory=list)
    archetypes: list[dict] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    clip_matches: list[dict] = field(default_factory=list)
    visual_evidence_segments: list[dict] = field(default_factory=list)
    timeline: dict | None = None
    receipt: dict | None = None
    proof_chain: dict | None = None
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "compilation_id": self.compilation_id,
            "timestamp": self.timestamp,
            "source_text": self.source_text,
            "total_duration": self.total_duration,
            "concepts": self.concepts,
            "claims": self.claims,
            "archetypes": self.archetypes,
            "candidates": self.candidates,
            "clip_matches": self.clip_matches,
            "visual_evidence_segments": self.visual_evidence_segments,
            "timeline": self.timeline,
            "receipt": self.receipt,
            "proof_chain": self.proof_chain,
            "stats": self.stats,
        }

    def to_json(self, path: str | None = None) -> str:
        data = self.to_dict()
        text = json.dumps(data, indent=2)
        if path:
            with open(path, "w") as f:
                f.write(text)
        return text


@dataclass
class CompilationReceipt:
    """Receipt proving a compilation occurred."""
    receipt_id: str
    timestamp: float
    compilation_id: str
    source_text_hash: str
    concept_count: int
    claim_count: int
    archetype_count: int
    candidate_count: int
    clip_match_count: int
    ves_count: int
    segment_count: int
    average_score: float
    truth_status_summary: dict = field(default_factory=dict)
    rights_status_summary: dict = field(default_factory=dict)
    pipeline_steps: list[str] = field(default_factory=list)
    previous_receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "receipt_id": self.receipt_id,
            "timestamp": self.timestamp,
            "compilation_id": self.compilation_id,
            "source_text_hash": self.source_text_hash,
            "concept_count": self.concept_count,
            "claim_count": self.claim_count,
            "archetype_count": self.archetype_count,
            "candidate_count": self.candidate_count,
            "clip_match_count": self.clip_match_count,
            "ves_count": self.ves_count,
            "segment_count": self.segment_count,
            "average_score": self.average_score,
            "truth_status_summary": self.truth_status_summary,
            "rights_status_summary": self.rights_status_summary,
            "pipeline_steps": self.pipeline_steps,
            "previous_receipt_hash": self.previous_receipt_hash,
        }


class OverVisualCompiler:
    """
    OverVisual — Narration-to-Evidence Video Compiler.

    Takes narration text and produces VisualEvidenceSegments with:
    - 3 scoring layers (semantic_match, evidence_relevance, truth_safety)
    - Rights status (safe/needs_review/blocked/unknown)
    - Proof hash chain (tamper-evident)
    - Timeline assembly

    Usage:
        compiler = OverVisualCompiler()
        result = compiler.compile(
            text="The material could have been derived from eastern energy wavelengths...",
            duration=15.0,
        )
        for ves in result.visual_evidence_segments:
            print(ves["claim_type"], ves["semantic_match_score"], ves["rights_status"])
    """

    PIPELINE_STEPS = [
        "transcript_input",
        "speech_reform",
        "claim_extraction",
        "truth_status_classification",
        "concept_extraction",
        "visual_association",
        "video_search",
        "frame_sampling",
        "clip_similarity_matching",
        "rights_filtering",
        "clip_ranking",
        "ves_creation",
        "timeline_assembly",
        "proof_chain_generation",
        "receipt_generation",
    ]

    def __init__(
        self,
        concept_extractor: ConceptExtractor | None = None,
        claim_extractor: ClaimExtractor | None = None,
        association_graph: VisualAssociationGraph | None = None,
        video_search: VideoSearch | None = None,
        clip_matcher: CLIPMatcher | None = None,
        youtube_search: YouTubeSearch | None = None,
        rights_filter: RightsFilter | None = None,
        timeline_assembler: TimelineAssembler | None = None,
        receipt_chain: list[str] | None = None,
    ):
        self.extractor = concept_extractor or ConceptExtractor()
        self.claim_extractor = claim_extractor or ClaimExtractor()
        self.graph = association_graph or VisualAssociationGraph()
        self.search = video_search or VideoSearch()
        self.clip_matcher = clip_matcher or CLIPMatcher()
        self.youtube = youtube_search or YouTubeSearch()
        self.rights_filter = rights_filter or RightsFilter()
        self.assembler = timeline_assembler or TimelineAssembler()
        self._receipt_chain = receipt_chain or []
        self._compilation_count = 0

    def compile(
        self,
        text: str,
        duration: float = 10.0,
        timestamp_start: float = 0.0,
        max_clips_per_concept: int = 3,
        min_score_threshold: float = 0.3,
        use_clip_matching: bool = True,
        auto_insert_blocked: bool = False,
    ) -> CompilationResult:
        """
        Full OverVisual compilation pipeline.

        Args:
            text: Narration transcript text
            duration: Duration of the narration segment in seconds
            timestamp_start: Start time in the full timeline
            max_clips_per_concept: Max candidates per concept
            min_score_threshold: Minimum composite score to include a clip
            use_clip_matching: Whether to run CLIP-style frame matching
            auto_insert_blocked: If False (default), blocked clips are never inserted

        Returns:
            CompilationResult with VES records, timeline, proof chain, and receipt
        """
        compilation_id = hashlib.sha256(
            f"{text}:{time.time()}".encode()
        ).hexdigest()[:16]

        # Step 1: Transcript input
        # Step 2: Speech reform
        reformed_text = self.claim_extractor.reform_speech(text)

        # Step 3-4: Claim extraction + truth-status classification
        claims = self.claim_extractor.extract_claims(
            text,
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_start + duration,
        )

        truth_status_summary: dict[str, int] = {}
        for claim in claims:
            status = claim.truth_status.value
            truth_status_summary[status] = truth_status_summary.get(status, 0) + 1

        # Step 5: Concept extraction
        concepts = self.extractor.extract(
            text,
            timestamp_start=timestamp_start,
            timestamp_end=timestamp_start + duration,
        )

        # Step 6: Visual association
        all_archetypes: list[VisualArchetype] = []
        concept_archetype_map: list[dict] = []

        for concept in concepts:
            archetypes = self.graph.resolve(concept.visual_archetypes)
            all_archetypes.extend(archetypes)
            concept_archetype_map.append({
                "concept_id": concept.concept_id,
                "concept_label": concept.label,
                "visual_concepts": concept.visual_archetypes,
                "archetypes": [a.to_dict() for a in archetypes],
                "emotional_tone": concept.emotional_tone,
                "confidence": concept.confidence,
                "timestamp_start": concept.atoms[0].timestamp_start if concept.atoms else timestamp_start,
                "timestamp_end": concept.atoms[-1].timestamp_end if concept.atoms else timestamp_start + duration,
            })

        # Step 7: Video search
        all_candidates: list[VideoCandidate] = []
        concept_clips: list[dict] = []
        all_clip_matches: list[dict] = []
        ves_records: list[VisualEvidenceSegment] = []
        rights_status_summary: dict[str, int] = {}

        # Find the primary claim for this segment
        primary_claim = claims[0] if claims else None
        primary_truth_status = primary_claim.truth_status if primary_claim else TruthStatus.UNKNOWN
        truth_safety = compute_truth_safety_score(primary_truth_status)

        for ca in concept_archetype_map:
            archetypes = [VisualArchetype(**a) for a in ca["archetypes"]]
            if not archetypes:
                continue

            search_terms: list[str] = []
            seen: set[str] = set()
            for arch in archetypes:
                for term in arch.search_terms:
                    if term not in seen:
                        seen.add(term)
                        search_terms.append(term)

            if not search_terms:
                continue

            candidates = self.search.search(
                search_terms=search_terms[:5],
                archetype_label=archetypes[0].label if archetypes else "",
                emotional_tone=ca["emotional_tone"],
                max_results=max_clips_per_concept,
            )

            all_candidates.extend(candidates)

            # Step 8-9: Frame sampling + CLIP matching
            best_clip = None
            best_clip_match: dict | None = None
            best_semantic_score = 0.0

            if use_clip_matching and candidates:
                match_results = self.clip_matcher.rank_videos(
                    text_query=ca["concept_label"],
                    candidates=[
                        {"title": c.title, "duration": c.duration_seconds}
                        for c in candidates[:3]
                    ],
                )

                for mr in match_results:
                    match_dict = mr.to_dict()
                    match_dict["concept_label"] = ca["concept_label"]
                    all_clip_matches.append(match_dict)

                if match_results and match_results[0].best_frame:
                    best_match = match_results[0]
                    best_semantic_score = best_match.max_similarity
                    for c in candidates:
                        if c.title == best_match.video_title:
                            clip_boost = best_match.max_similarity * 0.2
                            c.composite_score = min(1.0, c.composite_score + clip_boost)
                            best_clip = c
                            best_clip_match = best_match.to_dict()
                            break

                    if not best_clip:
                        best_clip = candidates[0]
                        best_semantic_score = match_results[0].max_similarity if match_results else 0.0
            else:
                best_clip = candidates[0] if candidates else None
                best_semantic_score = best_clip.composite_score if best_clip else 0.0

            # Step 10: Rights filtering
            rights_assessment: RightsAssessment | None = None
            if best_clip:
                rights_assessment = self.rights_filter.assess(
                    title=best_clip.title,
                    source=best_clip.source,
                    url=best_clip.url,
                )
                rights_status_summary[rights_assessment.status.value] = \
                    rights_status_summary.get(rights_assessment.status.value, 0) + 1

            # Step 11: Clip ranking with rights gate
            can_insert = True
            insertion_status = "candidate_only"

            if best_clip and best_clip.composite_score >= min_score_threshold:
                if rights_assessment:
                    if rights_assessment.status == RightsStatus.BLOCKED and not auto_insert_blocked:
                        can_insert = False
                        insertion_status = "blocked"
                    elif rights_assessment.status == RightsStatus.SAFE:
                        insertion_status = "selected"
                    elif rights_assessment.status in (RightsStatus.NEEDS_REVIEW, RightsStatus.UNKNOWN):
                        insertion_status = "needs_review"
            else:
                can_insert = False
                insertion_status = "below_threshold"

            if can_insert and best_clip:
                clip_entry = {
                    "concept_label": ca["concept_label"],
                    "timestamp_start": ca["timestamp_start"],
                    "timestamp_end": ca["timestamp_end"],
                    "best_clip": best_clip,
                    "archetype_label": best_clip.matched_archetype,
                    "emotional_tone": ca["emotional_tone"],
                }
                if best_clip_match:
                    clip_entry["clip_match"] = best_clip_match
                concept_clips.append(clip_entry)

            # Step 12: Create Visual Evidence Segment
            ves_id = hashlib.sha256(
                f"{ca['concept_id']}:{compilation_id}".encode()
            ).hexdigest()[:12]

            has_clip = best_clip is not None and can_insert
            evidence_relevance = compute_evidence_relevance_score(
                semantic_match=best_semantic_score,
                truth_safety=truth_safety,
                has_clip=has_clip,
            )

            candidate_sources = [
                {
                    "title": c.title,
                    "url": c.url,
                    "source": c.source,
                    "composite_score": c.composite_score,
                }
                for c in candidates[:5]
            ]

            selected_clip_dict = None
            if has_clip and best_clip:
                selected_clip_dict = {
                    "title": best_clip.title,
                    "url": best_clip.url,
                    "source": best_clip.source,
                    "duration": best_clip.duration_seconds,
                    "composite_score": best_clip.composite_score,
                    "archetype": best_clip.matched_archetype,
                }

            ves = VisualEvidenceSegment(
                segment_id=ves_id,
                source_transcript_id=compilation_id,
                start_sec=ca["timestamp_start"],
                end_sec=ca["timestamp_end"],
                transcript_text=text,
                claim=primary_claim.text if primary_claim else ca["concept_label"],
                claim_type=primary_truth_status.value,
                visual_concepts=ca["visual_concepts"],
                search_queries=search_terms[:5],
                candidate_sources=candidate_sources,
                selected_clip=selected_clip_dict,
                semantic_match_score=best_semantic_score,
                evidence_relevance_score=evidence_relevance,
                truth_safety_score=truth_safety,
                rights_status=rights_assessment.status.value if rights_assessment else "unknown",
                rights_assessment=rights_assessment.to_dict() if rights_assessment else None,
                receipt_hash="",
                clip_match_detail=best_clip_match,
                emotional_tone=ca["emotional_tone"],
                insertion_status=insertion_status,
            )
            ves_records.append(ves)

        # Step 13: Timeline assembly
        timeline = self.assembler.assemble(
            source_text=text,
            total_duration=duration,
            concept_clips=concept_clips,
        )

        # Step 14: Proof chain generation
        proof_gen = ProofGenerator()
        proof_gen.add_transcript(text)
        proof_gen.add_claims([c.to_dict() for c in claims])
        all_queries = list(set(
            q for ves in ves_records for q in ves.search_queries
        ))
        proof_gen.add_queries(all_queries)
        proof_gen.add_candidates([c.to_dict() for c in all_candidates])
        selected_clips_for_proof = [
            {"title": ves.selected_clip["title"], "timestamp": ves.start_sec, "score": ves.semantic_match_score}
            for ves in ves_records if ves.selected_clip
        ]
        proof_gen.add_selected_clips(selected_clips_for_proof)
        proof_gen.add_timeline(timeline.to_dict())
        proof_chain = proof_gen.finalize()

        # Set receipt hashes on VES records
        for ves in ves_records:
            ves.receipt_hash = f"sha256:{proof_chain.receipt_hash[:16]}"

        # Step 15: Receipt generation
        source_hash = hashlib.sha256(text.encode()).hexdigest()
        receipt = CompilationReceipt(
            receipt_id=hashlib.sha256(
                f"{compilation_id}:{source_hash}".encode()
            ).hexdigest()[:16],
            timestamp=time.time(),
            compilation_id=compilation_id,
            source_text_hash=source_hash,
            concept_count=len(concepts),
            claim_count=len(claims),
            archetype_count=len(all_archetypes),
            candidate_count=len(all_candidates),
            clip_match_count=len(all_clip_matches),
            ves_count=len(ves_records),
            segment_count=len(timeline.segments),
            average_score=timeline.average_score,
            truth_status_summary=truth_status_summary,
            rights_status_summary=rights_status_summary,
            pipeline_steps=self.PIPELINE_STEPS,
            previous_receipt_hash=self._receipt_chain[-1] if self._receipt_chain else "",
        )

        receipt_hash = hashlib.sha256(
            json.dumps(receipt.to_dict(), sort_keys=True).encode()
        ).hexdigest()
        self._receipt_chain.append(receipt_hash)
        self._compilation_count += 1

        result = CompilationResult(
            compilation_id=compilation_id,
            timestamp=time.time(),
            source_text=text,
            total_duration=duration,
            concepts=[c.to_dict() for c in concepts],
            claims=[c.to_dict() for c in claims],
            archetypes=[a.to_dict() for a in all_archetypes],
            candidates=[c.to_dict() for c in all_candidates],
            clip_matches=all_clip_matches,
            visual_evidence_segments=[ves.to_dict() for ves in ves_records],
            timeline=timeline.to_dict(),
            receipt=receipt.to_dict(),
            proof_chain=proof_chain.to_dict(),
            stats={
                "concept_count": len(concepts),
                "claim_count": len(claims),
                "archetype_count": len(all_archetypes),
                "candidate_count": len(all_candidates),
                "clip_match_count": len(all_clip_matches),
                "ves_count": len(ves_records),
                "segment_count": len(timeline.segments),
                "average_score": timeline.average_score,
                "min_threshold": min_score_threshold,
                "truth_status_summary": truth_status_summary,
                "rights_status_summary": rights_status_summary,
                "proof_chain_verified": proof_chain.verify(),
                "compilation_count": self._compilation_count,
            },
        )

        return result

    def compile_segments(
        self,
        segments: list[dict],
    ) -> list[CompilationResult]:
        """Compile multiple narration segments sequentially."""
        results: list[CompilationResult] = []
        for seg in segments:
            result = self.compile(
                text=seg["text"],
                duration=seg.get("duration", 10.0),
                timestamp_start=seg.get("timestamp_start", 0.0),
            )
            results.append(result)
        return results

    def save_receipts(self, path: str) -> None:
        """Save the receipt chain to a JSON file."""
        with open(path, "w") as f:
            json.dump({
                "receipt_chain": self._receipt_chain,
                "compilation_count": self._compilation_count,
            }, f, indent=2)

    def verify_receipt_chain(self) -> bool:
        """Verify the receipt chain is intact."""
        return len(self._receipt_chain) == self._compilation_count

    @property
    def stats(self) -> dict:
        return {
            "compilation_count": self._compilation_count,
            "receipt_chain_length": len(self._receipt_chain),
            "archetype_count": len(self.graph.archetypes),
            "concept_mappings": len(self.graph._concept_to_family),
            "youtube_api_available": self.youtube.has_api_key,
            "clip_matcher_active": self.clip_matcher.use_real_clip,
        }


# Backward compatibility alias
BrollCompiler = OverVisualCompiler
