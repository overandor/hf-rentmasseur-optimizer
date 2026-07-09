"""
MCRV — Machine-Consumable Research Video

The non-existent primitive: a video format where every second of video
is bound to machine-readable claims, sources, confidence scores, rights
metadata, provenance receipts, embeddings, and reproduction artifacts.

Humans watch the video. Machines verify, rank, buy, cite, reuse, and
route the evidence.

A normal YouTube video says:
    Watch this.

An MCRV object says:
    Here are the claims.
    Here is the evidence.
    Here is the counterevidence.
    Here are the sources.
    Here are the timestamps.
    Here are the embeddings.
    Here is the rights status.
    Here is the confidence score.
    Here is the reproduction attempt.
    Here is the provenance trail.
    Here is why a machine should rank, buy, cite, reuse, or route this artifact.

Five primitives:

1. MachinePersuasionVector — why a machine should prefer this artifact
2. AgentPurchaseSurface — machine-to-machine licensing and pricing
3. ReproductionCapsule — structured reproduction attempt record
4. MachineNativeTimeline — dual-use timeline (human scene + machine scene)
5. MCRVSidecar — the bundled machine-readable object alongside video.mp4

Usage:
    from broll.mcrv import MCRVCompiler
    sidecar = MCRVCompiler().compile(videolake_result)
    print(sidecar.machine_persuasion_vector.evidence_density)
    print(sidecar.agent_purchase_surface.price_full_video)
"""

import hashlib
import json
import os
import time
import zipfile
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MachinePersuasionVector:
    """
    Why a machine should prefer this artifact over competing media.

    Not addiction. Not manipulation. Algorithmic trust.

    A recommendation system, tutor agent, research agent, or licensing agent
    should prefer the video not because it is emotionally addictive, but
    because it is cleaner to parse, safer to reuse, easier to verify, and
    more valuable per second.
    """
    parseability: float = 0.0
    evidence_density: float = 0.0
    provenance_depth: float = 0.0
    rights_clarity: float = 0.0
    reproduction_strength: float = 0.0
    novelty_score: float = 0.0
    visual_retention_score: float = 0.0
    machine_reuse_score: float = 0.0

    @property
    def composite(self) -> float:
        weights = {
            "parseability": 0.15,
            "evidence_density": 0.20,
            "provenance_depth": 0.15,
            "rights_clarity": 0.15,
            "reproduction_strength": 0.10,
            "novelty_score": 0.05,
            "visual_retention_score": 0.05,
            "machine_reuse_score": 0.15,
        }
        return max(0.0, min(1.0, sum(getattr(self, k) * v for k, v in weights.items())))

    @property
    def grade(self) -> str:
        c = self.composite
        if c >= 0.9:
            return "A"
        elif c >= 0.8:
            return "B"
        elif c >= 0.7:
            return "C"
        elif c >= 0.5:
            return "D"
        else:
            return "F"

    def to_dict(self) -> dict:
        return {
            "parseability": round(self.parseability, 3),
            "evidence_density": round(self.evidence_density, 3),
            "provenance_depth": round(self.provenance_depth, 3),
            "rights_clarity": round(self.rights_clarity, 3),
            "reproduction_strength": round(self.reproduction_strength, 3),
            "novelty_score": round(self.novelty_score, 3),
            "visual_retention_score": round(self.visual_retention_score, 3),
            "machine_reuse_score": round(self.machine_reuse_score, 3),
            "composite": round(self.composite, 3),
            "grade": self.grade,
        }


@dataclass
class AgentPurchaseSurface:
    """
    Machine-to-machine licensing and pricing for the video object.

    The buyer is not necessarily a human viewer. The buyer can be:
    - research agent
    - education agent
    - scientific review agent
    - search index
    - enterprise knowledge base
    - compliance system
    - underwriting engine
    - AI tutor
    - recommendation system
    - citation graph
    - media licensing agent
    """
    license_available: bool = False
    allowed_uses: list[str] = field(default_factory=list)
    forbidden_uses: list[str] = field(default_factory=list)
    price_per_segment: float = 0.0
    price_full_video: float = 0.0
    machine_license_url: str = ""
    rights_receipt: str = ""
    currency: str = "USD"
    segment_count_buyable: int = 0
    segment_count_total: int = 0

    def to_dict(self) -> dict:
        return {
            "license_available": self.license_available,
            "allowed_uses": self.allowed_uses,
            "forbidden_uses": self.forbidden_uses,
            "price_per_segment": round(self.price_per_segment, 2),
            "price_full_video": round(self.price_full_video, 2),
            "machine_license_url": self.machine_license_url,
            "rights_receipt": self.rights_receipt,
            "currency": self.currency,
            "segment_count_buyable": self.segment_count_buyable,
            "segment_count_total": self.segment_count_total,
        }


@dataclass
class ReproductionCapsule:
    """
    Structured reproduction attempt record.

    This is what makes the video different from AI slop. The investigation
    is not hidden behind the video. The investigation is the computational
    substrate of the video.
    """
    claim_id: str = ""
    claim_text: str = ""
    paper_ids: list[str] = field(default_factory=list)
    data_files: list[str] = field(default_factory=list)
    code_files: list[str] = field(default_factory=list)
    commands_run: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    graphs: list[str] = field(default_factory=list)
    screen_recording_segments: list[str] = field(default_factory=list)
    result: str = "not_tested"  # replicated, failed, partial, not_tested
    confidence: float = 0.0
    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "claim_text": self.claim_text[:100],
            "paper_ids": self.paper_ids,
            "data_files": self.data_files,
            "code_files": self.code_files,
            "commands_run": self.commands_run,
            "outputs": self.outputs,
            "graphs": self.graphs,
            "screen_recording_segments": self.screen_recording_segments,
            "result": self.result,
            "confidence": round(self.confidence, 3),
            "receipt_hash": self.receipt_hash,
        }


@dataclass
class MachineNativeTimelineEntry:
    """
    A single entry in the machine-native timeline.

    Dual-use: human scene (what the viewer sees) + machine scene
    (what the agent parses).
    """
    timestamp: str = ""
    start_sec: float = 0.0
    human_scene: str = ""
    machine_scene: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "t": self.timestamp,
            "start_sec": self.start_sec,
            "human_scene": self.human_scene,
            "machine_scene": self.machine_scene,
        }


@dataclass
class MCRVSidecar:
    """
    The complete Machine-Consumable Research Video sidecar object.

    This is the machine-readable object that accompanies video.mp4.
    It contains everything a machine needs to verify, rank, buy, cite,
    reuse, and route the evidence in the video.

    Format: .mcrv (JSON-LD sidecar)
    """
    schema: str = "mcrv.v1"
    media_id: str = ""
    human_video: str = "video.mp4"
    machine_sidecar: str = "video.mcrv.jsonld"
    timestamp: float = 0.0

    claims: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    counter_sources: list[dict] = field(default_factory=list)
    evidence_segments: list[dict] = field(default_factory=list)
    visual_segments: list[dict] = field(default_factory=list)
    embeddings: list[dict] = field(default_factory=list)
    rights: list[dict] = field(default_factory=list)
    provenance: list[dict] = field(default_factory=list)
    reproduction_attempts: list[dict] = field(default_factory=list)
    confidence_scores: list[dict] = field(default_factory=list)
    receipts: list[dict] = field(default_factory=list)

    machine_persuasion_vector: Optional[MachinePersuasionVector] = None
    agent_purchase_surface: Optional[AgentPurchaseSurface] = None
    reproduction_capsules: list[ReproductionCapsule] = field(default_factory=list)
    machine_native_timeline: list[MachineNativeTimelineEntry] = field(default_factory=list)

    available_renderers: list[str] = field(default_factory=lambda: [
        "video", "report", "dataset", "slides", "podcast", "api",
    ])

    visualizations: list[dict] = field(default_factory=list)
    render_manifest: dict = field(default_factory=dict)
    ro_crate_metadata: dict = field(default_factory=dict)

    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "media_id": self.media_id,
            "human_video": self.human_video,
            "machine_sidecar": self.machine_sidecar,
            "timestamp": self.timestamp,
            "claims": self.claims,
            "sources": self.sources,
            "counter_sources": self.counter_sources,
            "evidence_segments": self.evidence_segments,
            "visual_segments": self.visual_segments,
            "embeddings": self.embeddings,
            "rights": self.rights,
            "provenance": self.provenance,
            "reproduction_attempts": self.reproduction_attempts,
            "confidence_scores": self.confidence_scores,
            "receipts": self.receipts,
            "machine_persuasion_vector": self.machine_persuasion_vector.to_dict() if self.machine_persuasion_vector else None,
            "agent_purchase_surface": self.agent_purchase_surface.to_dict() if self.agent_purchase_surface else None,
            "reproduction_capsules": [r.to_dict() for r in self.reproduction_capsules],
            "machine_native_timeline": [t.to_dict() for t in self.machine_native_timeline],
            "available_renderers": self.available_renderers,
            "visualizations": self.visualizations,
            "render_manifest": self.render_manifest,
            "ro_crate_metadata": self.ro_crate_metadata,
            "receipt_hash": self.receipt_hash,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_jsonld(self) -> str:
        d = self.to_dict()
        d["@context"] = {
            "mcrv": "https://videolake.dev/mcrv/v1#",
            "prov": "http://www.w3.org/ns/prov#",
            "schema": "https://schema.org/",
            "dcterms": "http://purl.org/dc/terms/",
        }
        d["@type"] = "mcrv:MachineConsumableResearchVideo"
        return json.dumps(d, indent=2)

    def to_ro_crate(self) -> str:
        """Generate RO-Crate metadata JSON."""
        return json.dumps(self.ro_crate_metadata, indent=2)

    def to_render_manifest(self) -> str:
        """Generate render manifest JSON."""
        return json.dumps(self.render_manifest, indent=2)


class MCRVCompiler:
    """
    Compiles a VideoLakeResult into an MCRV sidecar.

    The sidecar is the machine-readable object that makes the video
    machine-consumable: parseable, verifiable, citable, reusable,
    licensable, rankable, routable, and buyable.
    """

    def compile(self, videolake_result) -> MCRVSidecar:
        sidecar = MCRVSidecar()
        inv = videolake_result.investigation
        mevf = videolake_result.mevf
        vrap = videolake_result.vrap
        scenes = videolake_result.scene_graph

        sidecar.timestamp = time.time()

        media_id_data = f"{videolake_result.question}:{sidecar.timestamp}"
        sidecar.media_id = f"sha256:{hashlib.sha256(media_id_data.encode()).hexdigest()[:16]}"

        if inv:
            sidecar.claims = self._extract_claims(inv)
            sidecar.sources = self._extract_sources(inv)
            sidecar.counter_sources = self._extract_counter_sources(inv)
            sidecar.confidence_scores = self._extract_confidence_scores(inv)
            sidecar.provenance = self._extract_provenance(inv)
            sidecar.reproduction_capsules = self._extract_reproduction_capsules(inv)

        if mevf:
            sidecar.evidence_segments = [seg.to_dict() for seg in mevf.segments]
            sidecar.visual_segments = self._extract_visual_segments(mevf)
            sidecar.rights = self._extract_rights(mevf)
            sidecar.embeddings = self._extract_embeddings(mevf)
            sidecar.receipts = self._extract_receipts(mevf)

        sidecar.reproduction_attempts = [r.to_dict() for r in sidecar.reproduction_capsules]

        sidecar.machine_persuasion_vector = self._compute_persuasion_vector(inv, mevf, vrap)
        sidecar.agent_purchase_surface = self._compute_purchase_surface(mevf, vrap)
        sidecar.machine_native_timeline = self._build_machine_timeline(mevf, scenes)
        sidecar.visualizations = self._generate_visualizations(mevf, inv)
        sidecar.render_manifest = self._generate_render_manifest(sidecar, videolake_result)
        sidecar.ro_crate_metadata = self._generate_ro_crate(sidecar, videolake_result)

        sidecar.receipt_hash = self._compute_receipt_hash(sidecar)

        return sidecar

    def _extract_claims(self, inv) -> list[dict]:
        claims = []
        for i, claim in enumerate(inv.claims):
            claims.append({
                "claim_id": f"claim_{i+1}",
                "text": claim.claim_text,
                "status": claim.status.value,
                "confidence": round(claim.confidence, 3),
                "citation_count": claim.citation_count,
                "replications": claim.replications,
                "failed_replications": claim.failed_replications,
                "supporting_papers": len(claim.supporting_papers),
                "counter_papers": len(claim.counter_papers),
            })
        return claims

    def _extract_sources(self, inv) -> list[dict]:
        sources = []
        for paper in inv.papers:
            sources.append({
                "title": paper.title,
                "authors": paper.authors,
                "year": paper.year,
                "doi": paper.doi,
                "url": paper.url,
                "citation_count": paper.citation_count,
                "source": paper.source,
                "is_peer_reviewed": paper.is_peer_reviewed,
            })
        return sources

    def _extract_counter_sources(self, inv) -> list[dict]:
        counter = []
        for claim in inv.claims:
            for paper in claim.counter_papers:
                counter.append({
                    "counter_to": claim.claim_text[:60],
                    "title": paper.title,
                    "authors": paper.authors,
                    "year": paper.year,
                    "citation_count": paper.citation_count,
                    "source": paper.source,
                })
        return counter

    def _extract_confidence_scores(self, inv) -> list[dict]:
        scores = []
        for i, claim in enumerate(inv.claims):
            scores.append({
                "claim_id": f"claim_{i+1}",
                "confidence": round(claim.confidence, 3),
                "status": claim.status.value,
            })
        return scores

    def _extract_provenance(self, inv) -> list[dict]:
        prov = []
        for i, step in enumerate(inv.steps):
            prov.append({
                "step_id": f"step_{i+1}",
                "action": step.step_type,
                "description": step.description,
                "timestamp": step.timestamp,
            })
        return prov

    def _extract_reproduction_capsules(self, inv) -> list[ReproductionCapsule]:
        capsules = []
        for i, claim in enumerate(inv.claims):
            if claim.experiments:
                for exp in claim.experiments:
                    result = "not_tested"
                    if exp.result == "succeeded":
                        result = "replicated"
                    elif exp.result == "failed":
                        result = "failed"
                    elif exp.result == "inconclusive":
                        result = "partial"

                    capsules.append(ReproductionCapsule(
                        claim_id=f"claim_{i+1}",
                        claim_text=claim.claim_text,
                        paper_ids=[p.title for p in claim.source_papers],
                        outputs=[exp.description],
                        result=result,
                        confidence=claim.confidence,
                        receipt_hash=claim.receipt_hash,
                    ))
            else:
                if claim.replications > 0 or claim.failed_replications > 0:
                    if claim.failed_replications == 0 and claim.replications > 0:
                        result = "replicated"
                    elif claim.replications == 0 and claim.failed_replications > 0:
                        result = "failed"
                    else:
                        result = "partial"
                else:
                    result = "not_tested"

                capsules.append(ReproductionCapsule(
                    claim_id=f"claim_{i+1}",
                    claim_text=claim.claim_text,
                    paper_ids=[p.title for p in claim.source_papers],
                    result=result,
                    confidence=claim.confidence,
                    receipt_hash=claim.receipt_hash,
                ))
        return capsules

    def _extract_visual_segments(self, mevf) -> list[dict]:
        segments = []
        for seg in mevf.segments:
            segments.append({
                "segment_id": seg.segment_id,
                "time_start": seg.timestamp_in_video,
                "time_end": seg.timestamp_in_video + seg.duration_seconds,
                "spoken_claim": seg.claim,
                "claim_status": seg.claim_status,
                "visual_asset": seg.visual_description,
                "visual_type": seg.visual_type,
                "rights_status": seg.rights_status,
                "semantic_match_score": round(seg.scores.semantic_match_score, 3),
                "evidence_relevance_score": round(seg.scores.evidence_relevance_score, 3),
                "truth_safety_score": round(seg.scores.truth_safety_score, 3),
                "rights_safety_score": round(seg.scores.rights_safety_score, 3),
                "provenance_completeness_score": round(seg.scores.provenance_completeness_score, 3),
                "machine_buyability_score": round(seg.scores.machine_buyability_score, 3),
            })
        return segments

    def _extract_rights(self, mevf) -> list[dict]:
        rights = []
        for seg in mevf.segments:
            rights.append({
                "segment_id": seg.segment_id,
                "rights_status": seg.rights_status,
                "license_type": seg.license_type,
                "source": seg.source,
                "source_url": seg.source_url,
            })
        return rights

    def _extract_embeddings(self, mevf) -> list[dict]:
        embeddings = []
        for seg in mevf.segments:
            emb_id = f"vec_{hashlib.sha256(seg.segment_id.encode()).hexdigest()[:8]}"
            embeddings.append({
                "embedding_id": emb_id,
                "segment_id": seg.segment_id,
                "claim": seg.claim[:80],
                "visual_type": seg.visual_type,
            })
        return embeddings

    def _extract_receipts(self, mevf) -> list[dict]:
        receipts = []
        for seg in mevf.segments:
            if seg.receipt_hash:
                receipts.append({
                    "segment_id": seg.segment_id,
                    "receipt_hash": seg.receipt_hash,
                    "investigation_id": seg.investigation_id,
                })
        return receipts

    def _compute_persuasion_vector(self, inv, mevf, vrap) -> MachinePersuasionVector:
        vec = MachinePersuasionVector()

        if not mevf or not mevf.segments:
            return vec

        total = len(mevf.segments)

        # parseability: all segments have structured data
        vec.parseability = 1.0

        # evidence_density: ratio of verified/replicated claims to total
        if inv:
            verified = len(inv.get_verified_claims())
            total_claims = len(inv.claims)
            vec.evidence_density = verified / total_claims if total_claims > 0 else 0.0
        else:
            vec.evidence_density = 0.0

        # provenance_depth: average provenance completeness across segments
        vec.provenance_depth = sum(s.scores.provenance_completeness_score for s in mevf.segments) / total

        # rights_clarity: ratio of safe rights to total
        safe = sum(1 for s in mevf.segments if s.rights_status == "safe")
        vec.rights_clarity = safe / total

        # reproduction_strength: ratio of replicated claims to total
        if inv:
            replicated = sum(1 for c in inv.claims if c.replications > 0 and c.failed_replications == 0)
            vec.reproduction_strength = replicated / len(inv.claims) if inv.claims else 0.0
        else:
            vec.reproduction_strength = 0.0

        # novelty_score: based on question uniqueness (simplified)
        vec.novelty_score = 0.5  # neutral default

        # visual_retention_score: average visual clarity proxy
        vec.visual_retention_score = sum(s.scores.semantic_match_score for s in mevf.segments) / total

        # machine_reuse_score: average machine buyability
        vec.machine_reuse_score = sum(s.scores.machine_buyability_score for s in mevf.segments) / total

        return vec

    def _compute_purchase_surface(self, mevf, vrap) -> AgentPurchaseSurface:
        surface = AgentPurchaseSurface()

        if not mevf or not mevf.segments:
            return surface

        total = len(mevf.segments)
        buyable = sum(1 for s in mevf.segments if s.scores.is_machine_buyable)
        all_safe = all(s.rights_status == "safe" for s in mevf.segments)

        surface.segment_count_total = total
        surface.segment_count_buyable = buyable
        surface.license_available = all_safe and buyable > 0

        surface.allowed_uses = ["education", "research", "embedding_index"]
        if all_safe:
            surface.allowed_uses.append("commercial_summary")
        surface.forbidden_uses = ["misleading_edit", "unattributed_reupload"]

        if vrap:
            surface.price_full_video = vrap.total_price_usd
        else:
            surface.price_full_video = buyable * 0.05

        surface.price_per_segment = 0.05
        surface.rights_receipt = f"sha256:{hashlib.sha256(str(total + buyable).encode()).hexdigest()[:16]}"

        return surface

    def _build_machine_timeline(self, mevf, scenes) -> list[MachineNativeTimelineEntry]:
        timeline = []

        for scene in scenes:
            ts = scene.timestamp
            hours = int(ts // 3600)
            minutes = int((ts % 3600) // 60)
            seconds = ts % 60
            timestamp = f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"

            human_scene = scene.description[:80]

            machine_scene = {
                "scene_id": scene.scene_id,
                "scene_type": scene.scene_type,
                "mood": scene.mood,
            }

            if scene.claim_ref:
                machine_scene["claim_id"] = scene.claim_ref
                machine_scene["visual_segment_id"] = scene.claim_ref
            elif mevf:
                for seg in mevf.segments:
                    if abs(seg.timestamp_in_video + 5.0 - ts) < 0.1:
                        machine_scene["claim_id"] = seg.segment_id
                        machine_scene["evidence_ids"] = [seg.source_paper_title] if seg.source_paper_title else []
                        machine_scene["rights_id"] = seg.rights_status
                        machine_scene["confidence"] = round(seg.scores.truth_safety_score, 3)
                        emb_id = f"vec_{hashlib.sha256(seg.segment_id.encode()).hexdigest()[:8]}"
                        machine_scene["embedding_id"] = emb_id
                        break

            timeline.append(MachineNativeTimelineEntry(
                timestamp=timestamp,
                start_sec=ts,
                human_scene=human_scene,
                machine_scene=machine_scene,
            ))

        return timeline

    def _generate_visualizations(self, mevf, inv) -> list[dict]:
        """Generate visualization metadata from MEVF and investigation."""
        from .investigation_visualizer import (
            claim_heatmap, evidence_density_timeline, contradiction_map,
            replication_ladder, rights_safety_timeline, machine_trust_curve,
            uncertainty_cinema, generate_all_visualizations,
        )

        vizs = []
        if mevf and inv:
            all_viz = generate_all_visualizations(mevf, inv)
            for v in all_viz:
                vizs.append(v.to_dict())
        return vizs

    def _generate_render_manifest(self, sidecar: MCRVSidecar, videolake_result) -> dict:
        """Generate render manifest declaring available renderers and their outputs."""
        bundle_files = list(videolake_result.bundle.keys())

        renderers = {
            "video": {
                "output": "video.mp4",
                "available": "video.mp4" in videolake_result.bundle or (
                    videolake_result.render_result is not None
                ),
                "description": "Human-consumable MP4 with text overlays and narration",
            },
            "report": {
                "output": "report.md",
                "available": True,
                "description": "Markdown research report with claims, evidence, and citations",
            },
            "dataset": {
                "output": "dataset.json",
                "available": True,
                "description": "Structured JSON dataset of all claims, sources, and scores",
            },
            "slides": {
                "output": "slides.json",
                "available": True,
                "description": "Slide deck specification with scene-to-slide mappings",
            },
            "podcast": {
                "output": "podcast.txt",
                "available": "narration.txt" in videolake_result.bundle,
                "description": "Audio narration script for podcast rendering",
            },
            "api": {
                "output": "api_schema.json",
                "available": True,
                "description": "OpenAPI schema for machine query of claims, evidence, and scores",
            },
        }

        return {
            "schema": "render_manifest.v1",
            "media_id": sidecar.media_id,
            "bundle_files": bundle_files,
            "bundle_file_count": len(bundle_files),
            "renderers": renderers,
            "available_renderers": [r for r, info in renderers.items() if info["available"]],
            "receipt_hash": sidecar.receipt_hash,
        }

    def _generate_ro_crate(self, sidecar: MCRVSidecar, videolake_result) -> dict:
        """Generate RO-Crate metadata (JSON-LD research object packaging)."""
        inv = videolake_result.investigation
        mevf = videolake_result.mevf

        parts = []
        for filename in videolake_result.bundle.keys():
            parts.append({"@id": filename, "@type": "File"})

        parts.append({"@id": "video.mcrv.jsonld", "@type": "File"})
        parts.append({"@id": "mcrv_machine_persuasion.json", "@type": "File"})
        parts.append({"@id": "mcrv_agent_purchase.json", "@type": "File"})
        parts.append({"@id": "mcrv_machine_timeline.json", "@type": "File"})

        return {
            "@context": "https://w3id.org/ro/crate/1.1/context",
            "@graph": [
                {
                    "@id": "ro-crate-metadata.json",
                    "@type": "CreativeWork",
                    "about": {"@id": "./"},
                    "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
                },
                {
                    "@id": "./",
                    "@type": "Dataset",
                    "name": videolake_result.question[:100] if videolake_result.question else "MCRV Research Object",
                    "description": sidecar.machine_persuasion_vector.__class__.__name__ if sidecar.machine_persuasion_vector else "",
                    "datePublished": time.strftime("%Y-%m-%d", time.gmtime()),
                    "hasPart": [{"@id": p["@id"]} for p in parts],
                    "author": {"@id": "https://videolake.dev/"},
                    "license": {"@id": "https://creativecommons.org/licenses/by/4.0/"},
                    "encoding": {"@id": "video.mcrv.jsonld"},
                },
                {
                    "@id": "video.mcrv.jsonld",
                    "@type": ["File", "SoftwareSourceCode"],
                    "name": "MCRV Machine-Consumable Sidecar",
                    "encodingFormat": "application/ld+json",
                    "description": "Machine-readable evidence graph, claims, rights, provenance, and purchase surface",
                },
                *parts,
            ],
        }

    def _compute_receipt_hash(self, sidecar: MCRVSidecar) -> str:
        data = {
            "schema": sidecar.schema,
            "media_id": sidecar.media_id,
            "timestamp": sidecar.timestamp,
            "claim_count": len(sidecar.claims),
            "segment_count": len(sidecar.evidence_segments),
            "mpv_composite": sidecar.machine_persuasion_vector.composite if sidecar.machine_persuasion_vector else 0.0,
        }
        return f"sha256:{hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]}"


class MCRVPacker:
    """
    Packs/unpacks/verifies .mcrv files.

    A .mcrv file is a tar.gz archive containing:
        video.mp4                    — human surface (real MP4)
        narration.txt                — narration script
        machine_sidecar.jsonld       — the machine-consumable sidecar (main object)
        render_manifest.json         — manifest of all files with SHA-256 hashes
        + all VRAP bundle files (claims.jsonl, evidence.jsonld, etc.)

    Usage:
        path = MCRVPacker.pack(videolake_result, "out.mcrv")
        valid = MCRVPacker.verify("out.mcrv")
        files = MCRVPacker.unpack("out.mcrv", "/tmp/extracted")
    """

    FORMAT_VERSION = "mcrv_v1"
    SIDECAR_NAME = "machine_sidecar.jsonld"
    MANIFEST_NAME = "mcrv_manifest.json"

    @staticmethod
    def pack(videolake_result, output_path: str = None) -> str:
        """Pack a VideoLakeResult into a .mcrv tar.gz archive."""
        import tarfile
        import io

        result = videolake_result
        inv = result.investigation
        mevf = result.mevf
        vrap = result.vrap

        if output_path is None:
            safe_q = "".join(c if c.isalnum() else "_" for c in result.question[:40])
            output_path = f"{safe_q}.mcrv"

        # Compile sidecar
        compiler = MCRVCompiler()
        sidecar = compiler.compile(result)

        # Build manifest
        manifest = {
            "format_version": MCRVPacker.FORMAT_VERSION,
            "media_id": sidecar.media_id,
            "question": result.question,
            "created_at": time.time(),
            "files": {},
            "receipt_hash": result.receipt_hash,
            "trust_grade": mevf.trust_grade if mevf else "",
            "claim_count": len(inv.claims) if inv else 0,
            "paper_count": len(inv.papers) if inv else 0,
            "segment_count": len(mevf.segments) if mevf else 0,
            "duration_seconds": sum(s.duration_seconds for s in mevf.segments) if mevf else 0,
            "has_video": result.render_result is not None and bool(result.render_result.mp4_path),
            "has_audio": result.render_result is not None and result.render_result.audio_generated,
            "available_renderers": sidecar.available_renderers,
            "mpv_composite": sidecar.machine_persuasion_vector.composite if sidecar.machine_persuasion_vector else 0,
            "mpv_grade": sidecar.machine_persuasion_vector.grade if sidecar.machine_persuasion_vector else "F",
        }

        # Collect text files from bundle (skip binary file references)
        text_files = {}
        for filename, content in result.bundle.items():
            if content.startswith("[binary file:"):
                continue
            text_files[filename] = content

        # Add sidecar
        text_files[MCRVPacker.SIDECAR_NAME] = sidecar.to_jsonld()

        # Compute hashes for manifest
        for filename, content in text_files.items():
            h = hashlib.sha256(content.encode()).hexdigest()
            manifest["files"][filename] = f"sha256:{h}"

        # Add video.mp4 hash if it exists
        video_path = None
        if result.render_result and result.render_result.mp4_path:
            video_path = result.render_result.mp4_path
            if os.path.exists(video_path):
                with open(video_path, "rb") as f:
                    h = hashlib.sha256(f.read()).hexdigest()
                manifest["files"]["video.mp4"] = f"sha256:{h}"

        # Add audio.wav hash if it exists
        audio_path = None
        if result.render_result and result.render_result.audio_path:
            audio_path = result.render_result.audio_path
            if os.path.exists(audio_path):
                with open(audio_path, "rb") as f:
                    h = hashlib.sha256(f.read()).hexdigest()
                manifest["files"]["audio.wav"] = f"sha256:{h}"

        manifest["total_size_bytes"] = sum(len(v.encode()) for v in text_files.values())
        if video_path and os.path.exists(video_path):
            manifest["total_size_bytes"] += os.path.getsize(video_path)
        if audio_path and os.path.exists(audio_path):
            manifest["total_size_bytes"] += os.path.getsize(audio_path)

        text_files[MCRVPacker.MANIFEST_NAME] = json.dumps(manifest, indent=2)

        # Write tar.gz
        with tarfile.open(output_path, "w:gz") as tar:
            # Add text files
            for filename, content in text_files.items():
                data = content.encode()
                info = tarfile.TarInfo(name=filename)
                info.size = len(data)
                info.mtime = time.time()
                tar.addfile(info, io.BytesIO(data))

            # Add video.mp4 as binary if it exists
            if video_path and os.path.exists(video_path):
                tar.add(video_path, arcname="video.mp4")

            # Add audio.wav as binary if it exists
            if audio_path and os.path.exists(audio_path):
                tar.add(audio_path, arcname="audio.wav")

        return output_path

    @staticmethod
    def unpack(mcrv_path: str, extract_dir: str = None) -> dict:
        """Unpack a .mcrv file and return the manifest."""
        import tarfile

        if extract_dir is None:
            extract_dir = mcrv_path.replace(".mcrv", "_extracted")

        os.makedirs(extract_dir, exist_ok=True)

        with tarfile.open(mcrv_path, "r:gz") as tar:
            tar.extractall(extract_dir, filter="data")

        manifest_path = os.path.join(extract_dir, MCRVPacker.MANIFEST_NAME)
        if os.path.exists(manifest_path):
            with open(manifest_path) as f:
                return json.load(f)
        return {}

    @staticmethod
    def verify(mcrv_path: str) -> dict:
        """Verify a .mcrv file by checking all file hashes in the manifest."""
        import tarfile
        import tempfile

        result = {
            "valid": True,
            "format_version": "",
            "media_id": "",
            "files_checked": 0,
            "files_valid": 0,
            "files_failed": [],
            "manifest_found": False,
            "sidecar_found": False,
            "video_found": False,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            with tarfile.open(mcrv_path, "r:gz") as tar:
                tar.extractall(tmpdir, filter="data")

            # Check manifest
            manifest_path = os.path.join(tmpdir, MCRVPacker.MANIFEST_NAME)
            if not os.path.exists(manifest_path):
                result["valid"] = False
                return result

            result["manifest_found"] = True
            with open(manifest_path) as f:
                manifest = json.load(f)

            result["format_version"] = manifest.get("format_version", "")
            result["media_id"] = manifest.get("media_id", "")

            # Check sidecar
            sidecar_path = os.path.join(tmpdir, MCRVPacker.SIDECAR_NAME)
            result["sidecar_found"] = os.path.exists(sidecar_path)

            # Check video
            video_path = os.path.join(tmpdir, "video.mp4")
            result["video_found"] = os.path.exists(video_path)

            # Verify file hashes
            for filename, expected_hash in manifest.get("files", {}).items():
                filepath = os.path.join(tmpdir, filename)
                result["files_checked"] += 1

                if not os.path.exists(filepath):
                    result["files_failed"].append(f"{filename}: missing")
                    result["valid"] = False
                    continue

                if filename == "video.mp4":
                    with open(filepath, "rb") as f:
                        actual = f"sha256:{hashlib.sha256(f.read()).hexdigest()}"
                else:
                    with open(filepath, "rb") as f:
                        actual = f"sha256:{hashlib.sha256(f.read()).hexdigest()}"

                if actual == expected_hash:
                    result["files_valid"] += 1
                else:
                    result["files_failed"].append(f"{filename}: hash mismatch")
                    result["valid"] = False

        return result
