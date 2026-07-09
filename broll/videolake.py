"""
VideoLake Compiler — Research-to-Asset Compiler

Turns investigations into machine-readable research media.

QRC turns questions into executable software capsules.
SystemLake turns files into collateral evidence.
VideoLake turns investigations into machine-readable research media.

One command:

    python -m broll investigate "Does Schumann resonance have measurable properties?" \\
        --out investigation_packet \\
        --compile-video \\
        --write-receipts \\
        --export-b64

Output bundle:
    video.mp4                  (human surface — placeholder)
    transcript.vtt             (WebVTT captions)
    claims.jsonl               (one JSON per claim)
    counterclaims.jsonl        (counter-evidence)
    papers.jsonl               (source papers)
    evidence_graph.json        (evidence graph)
    visual_evidence_segments.jsonl  (VES with 6 scores)
    scene_graph.json           (scene descriptions per timestamp)
    simulations.json           (simulation specs for invisible systems)
    rights.json                (rights and licensing)
    timeline.edl               (EDL for video editing)
    receipts.jsonl             (tamper-evident receipt chain)
    market_terms.json          (micro-asset pricing)
    manifest.json              (top-level manifest)
    asset_packet.b64           (Base64 encoded full packet for machine audit)

The video is the human interface.
The evidence graph is the asset.
"""

import base64
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from .investigation_engine import InvestigationEngine
from .investigation_graph import InvestigationGraph
from .mevf import MEVFBuilder, MEVFObject, MEVFSegment
from .vrap import VRAPBuilder, VRAPManifest, MicroAsset
from .machine_attention import machine_attention_track, claim_lattice
from .simulation_engine import SimulationEngine
from .media_compiler import MediaCompiler
from .renderer import MP4Renderer, RenderResult
from .youtube_metadata import YouTubeMetadataGenerator, YouTubeMetadata
from .mcrv import MCRVCompiler, MCRVSidecar, MCRVPacker
from .multi_renderer import MultiRenderer
from .rights_vault import RightsVault, FRVO, OfferingMode


@dataclass
class SceneNode:
    """A scene in the scene graph — what visually happens at a given time."""
    scene_id: str = ""
    timestamp: float = 0.0
    duration: float = 10.0
    scene_type: str = ""  # footage, simulation, diagram, experiment, text_overlay
    description: str = ""
    claim_ref: str = ""
    visual_elements: list[str] = field(default_factory=list)
    mood: str = ""  # investigative, tense, revelatory, uncertain, conclusive

    def to_dict(self) -> dict:
        return {
            "scene_id": self.scene_id,
            "timestamp": self.timestamp,
            "duration": self.duration,
            "scene_type": self.scene_type,
            "description": self.description,
            "claim_ref": self.claim_ref,
            "visual_elements": self.visual_elements,
            "mood": self.mood,
        }


@dataclass
class VideoLakeResult:
    """The complete output of a VideoLake compilation."""
    question: str = ""
    investigation: Optional[InvestigationGraph] = None
    mevf: Optional[MEVFObject] = None
    vrap: Optional[VRAPManifest] = None
    bundle: dict[str, str] = field(default_factory=dict)
    scene_graph: list[SceneNode] = field(default_factory=list)
    base64_packet: str = ""
    receipt_hash: str = ""
    output_dir: str = ""
    render_result: Optional[RenderResult] = None
    youtube_metadata: Optional[YouTubeMetadata] = None
    mcrv_sidecar: Optional[MCRVSidecar] = None
    frvo: Optional[FRVO] = None

    @property
    def files(self) -> list[str]:
        return list(self.bundle.keys())

    @property
    def total_size_bytes(self) -> int:
        return sum(len(v.encode()) for v in self.bundle.values())

    def summary(self) -> dict:
        """Human-readable summary of the compilation."""
        if not self.investigation or not self.mevf or not self.vrap:
            return {"error": "Incomplete compilation"}

        return {
            "question": self.question,
            "investigation_id": self.investigation.investigation_id,
            "claims": len(self.investigation.claims),
            "papers": len(self.investigation.papers),
            "segments": len(self.mevf.segments),
            "trust_grade": self.vrap.trust_grade,
            "avg_buyability": round(self.vrap.avg_machine_buyability, 3),
            "total_price_usd": self.vrap.total_price_usd,
            "files": len(self.bundle),
            "total_size_bytes": self.total_size_bytes,
            "base64_packet_size": len(self.base64_packet),
            "receipt_hash": self.receipt_hash,
            "scene_count": len(self.scene_graph),
        }


class VideoLakeCompiler:
    """
    Research-to-Asset Compiler.

    Compiles a question into a complete dual-track research media packet:
        Human track: video timeline, transcript, scene graph
        Machine track: claims, evidence, provenance, rights, embeddings, receipts, market terms

    Usage:
        compiler = VideoLakeCompiler()
        result = compiler.compile("Does Schumann resonance have measurable properties?")
        print(result.summary())
        print(f"Files: {result.files}")
        print(f"Base64 packet: {len(result.base64_packet)} chars")
    """

    def __init__(self):
        self.investigation_engine = InvestigationEngine()
        self.mevf_builder = MEVFBuilder()
        self.vrap_builder = VRAPBuilder()
        self.simulation_engine = SimulationEngine()
        self.media_compiler = MediaCompiler()
        self.video_renderer = MP4Renderer()
        self.youtube_metadata_gen = YouTubeMetadataGenerator()
        self.mcrv_compiler = MCRVCompiler()

    def compile(
        self,
        question: str,
        output_dir: str | None = None,
        compile_video: bool = True,
        write_receipts: bool = True,
        export_b64: bool = True,
        pack_mcrv: bool = False,
        render_all: bool = False,
        create_frvo: bool = False,
        offering_mode: OfferingMode = OfferingMode.PERK_ONLY,
    ) -> VideoLakeResult:
        """
        Compile a question into a complete research media packet.

        Args:
            question: The research question to investigate
            output_dir: Directory to write files to (None = in-memory only)
            compile_video: Whether to include video timeline in output
            write_receipts: Whether to include receipt chain
            export_b64: Whether to generate Base64 asset packet

        Returns:
            VideoLakeResult with all artifacts
        """
        result = VideoLakeResult(question=question, output_dir=output_dir or "")

        # 1. Investigation
        result.investigation = self.investigation_engine.investigate(question)

        # 2. MEVF
        result.mevf = self.mevf_builder.build(result.investigation)

        # 3. VRAP
        result.vrap = self.vrap_builder.build(result.mevf, result.investigation)

        # 4. Scene graph
        result.scene_graph = self._build_scene_graph(result.mevf, result.investigation)

        # 5. Serialize bundle (VRAP 9 files)
        result.bundle = self.vrap_builder.serialize_bundle(
            result.vrap, result.mevf, result.investigation, output_dir=None
        )

        # 6. Add VideoLake-specific files
        self._add_videolake_files(result, compile_video, write_receipts)

        # 7. YouTube metadata if compile_video
        if compile_video:
            result.youtube_metadata = self.youtube_metadata_gen.generate(result)
            result.bundle["youtube_metadata.json"] = result.youtube_metadata.to_json()
            result.bundle["youtube_chapters.txt"] = result.youtube_metadata.to_chapters_text()
            result.bundle["youtube_thumbnail_spec.json"] = json.dumps(
                self.youtube_metadata_gen.generate_thumbnail_spec(result), indent=2
            )

        # 7b. MCRV sidecar (machine-consumable research video)
        result.mcrv_sidecar = self.mcrv_compiler.compile(result)
        result.bundle["video.mcrv.jsonld"] = result.mcrv_sidecar.to_jsonld()
        result.bundle["mcrv_machine_persuasion.json"] = json.dumps(
            result.mcrv_sidecar.machine_persuasion_vector.to_dict(), indent=2
        )
        result.bundle["mcrv_agent_purchase.json"] = json.dumps(
            result.mcrv_sidecar.agent_purchase_surface.to_dict(), indent=2
        )
        result.bundle["mcrv_machine_timeline.json"] = json.dumps(
            [t.to_dict() for t in result.mcrv_sidecar.machine_native_timeline], indent=2
        )
        result.bundle["ro-crate-metadata.json"] = result.mcrv_sidecar.to_ro_crate()
        result.bundle["render_manifest.json"] = result.mcrv_sidecar.to_render_manifest()

        # 7c. FRVO (Fractional Revenue Video Object)
        if create_frvo:
            vault = RightsVault()
            result.frvo = vault.create_frvo(
                videolake_result=result,
                offering_mode=offering_mode,
            )
            result.bundle["frvo.json"] = result.frvo.to_json()
            result.bundle["rights_proof_packet.json"] = json.dumps(
                vault.generate_proof_packet(result.frvo), indent=2
            )
            result.bundle["machine_rights_inspection.json"] = json.dumps(
                vault.machine_inspect(result.frvo), indent=2
            )

        # 8. Base64 packet (after all bundle files are added)
        if export_b64:
            result.base64_packet = self._encode_base64_packet(result.bundle)

        # 9. Write to disk if output_dir
        if output_dir:
            import os
            os.makedirs(output_dir, exist_ok=True)
            for filename, content in result.bundle.items():
                filepath = os.path.join(output_dir, filename)
                with open(filepath, "w") as f:
                    f.write(content)
            if export_b64:
                b64_path = os.path.join(output_dir, "asset_packet.b64")
                with open(b64_path, "w") as f:
                    f.write(result.base64_packet)
            # Render actual MP4 if output_dir and compile_video
            if compile_video:
                scene_dicts = [s.to_dict() for s in result.scene_graph]
                mp4_path = os.path.join(output_dir, "video.mp4")
                result.render_result = self.video_renderer.render(
                    scene_dicts, output_path=mp4_path, narration=True,
                )
                if result.render_result.mp4_path and os.path.exists(result.render_result.mp4_path):
                    result.bundle["video.mp4"] = f"[binary file: {result.render_result.mp4_path}]"
                if result.render_result.narration_text:
                    result.bundle["narration.txt"] = result.render_result.narration_text
                    narration_path = os.path.join(output_dir, "narration.txt")
                    with open(narration_path, "w") as f:
                        f.write(result.render_result.narration_text)
                if result.render_result.audio_path and os.path.exists(result.render_result.audio_path):
                    audio_dest = os.path.join(output_dir, "audio.wav")
                    import shutil as _sh
                    _sh.copy2(result.render_result.audio_path, audio_dest)
                    result.bundle["audio.wav"] = f"[binary file: {audio_dest}]"

            # Multi-renderer: report, dataset, slides, podcast, api
            if render_all:
                mr = MultiRenderer()
                artifacts = mr.render_all(result, output_dir=output_dir)
                for name, artifact in artifacts.items():
                    result.bundle[artifact.filename] = artifact.content

            # Pack .mcrv file
            if pack_mcrv:
                mcrv_path = os.path.join(output_dir, "investigation.mcrv")
                MCRVPacker.pack(result, output_path=mcrv_path)
                result.bundle["investigation.mcrv"] = f"[binary file: {mcrv_path}]"

        # 10. Final receipt
        result.receipt_hash = self._compute_final_receipt(result)

        return result

    def _build_scene_graph(
        self,
        mevf: MEVFObject,
        investigation: InvestigationGraph,
    ) -> list[SceneNode]:
        """Build a scene graph describing what visually happens at each timestamp."""
        scenes: list[SceneNode] = []

        # Opening scene: the question
        scenes.append(SceneNode(
            scene_id="scene_000",
            timestamp=0.0,
            duration=5.0,
            scene_type="text_overlay",
            description=f"Title card: {investigation.question[:80]}",
            visual_elements=["title", "question text", "dark background"],
            mood="investigative",
        ))

        # Scene per segment
        for i, seg in enumerate(mevf.segments):
            scene_type = seg.visual_type
            mood = self._determine_mood(seg)

            visual_elements = self._extract_visual_elements(seg)

            scenes.append(SceneNode(
                scene_id=f"scene_{i+1:03d}",
                timestamp=seg.timestamp_in_video + 5.0,  # After title card
                duration=seg.duration_seconds,
                scene_type=scene_type,
                description=seg.visual_description,
                claim_ref=seg.segment_id,
                visual_elements=visual_elements,
                mood=mood,
            ))

        # Closing scene: conclusions
        scenes.append(SceneNode(
            scene_id="scene_final",
            timestamp=sum(s.duration for s in scenes),
            duration=10.0,
            scene_type="text_overlay",
            description="Conclusions and evidence summary",
            visual_elements=["conclusion text", "evidence count", "confidence score", "receipt hash"],
            mood="conclusive",
        ))

        return scenes

    def _determine_mood(self, seg: MEVFSegment) -> str:
        """Determine the narrative mood for a segment."""
        if seg.claim_status in ("verified", "replicated"):
            return "revelatory"
        elif seg.claim_status == "disputed":
            return "tense"
        elif seg.claim_status in ("speculative", "unverified"):
            return "uncertain"
        elif seg.claim_status == "retracted":
            return "somber"
        else:
            return "investigative"

    def _extract_visual_elements(self, seg: MEVFSegment) -> list[str]:
        """Extract visual elements from a segment."""
        elements = []
        if seg.visual_type == "simulation":
            elements.extend(["animation", "waveform", "field visualization"])
        elif seg.visual_type == "footage":
            elements.extend(["documentary footage", "location shot"])
        elif seg.visual_type == "diagram":
            elements.extend(["chart", "data visualization"])
        elif seg.visual_type == "experiment":
            elements.extend(["experiment setup", "measurement device"])

        # Add status overlay
        elements.append(f"status overlay: {seg.claim_status}")
        if seg.not_status:
            elements.append("not-status disclaimer")

        return elements

    def _add_videolake_files(
        self,
        result: VideoLakeResult,
        compile_video: bool,
        write_receipts: bool,
    ) -> None:
        """Add VideoLake-specific files to the bundle."""
        inv = result.investigation
        mevf = result.mevf

        # transcript.vtt — WebVTT format
        vtt_lines = ["WEBVTT", ""]
        for i, seg in enumerate(mevf.segments):
            start = self._format_vtt_time(seg.timestamp_in_video)
            end = self._format_vtt_time(seg.timestamp_in_video + seg.duration_seconds)
            vtt_lines.append(f"{i+1}")
            vtt_lines.append(f"{start} --> {end}")
            vtt_lines.append(f"[{seg.claim_status.upper()}] {seg.claim}")
            if seg.not_status:
                vtt_lines.append(f"NOTE: {seg.not_status}")
            vtt_lines.append("")
        result.bundle["transcript.vtt"] = "\n".join(vtt_lines)

        # counterclaims.jsonl
        counter_lines = []
        for claim in inv.claims:
            for counter in claim.counter_papers:
                counter_lines.append(json.dumps({
                    "counter_to": claim.claim_text[:60],
                    "paper": counter.title,
                    "authors": counter.authors,
                    "year": counter.year,
                    "source": counter.source,
                    "citations": counter.citation_count,
                }))
        result.bundle["counterclaims.jsonl"] = "\n".join(counter_lines) if counter_lines else ""

        # papers.jsonl
        paper_lines = []
        for paper in inv.papers:
            paper_lines.append(json.dumps({
                "title": paper.title,
                "authors": paper.authors,
                "year": paper.year,
                "citations": paper.citation_count,
                "source": paper.source,
                "peer_reviewed": paper.is_peer_reviewed,
                "doi": paper.doi,
            }))
        result.bundle["papers.jsonl"] = "\n".join(paper_lines)

        # evidence_graph.json
        result.bundle["evidence_graph.json"] = json.dumps({
            "question": inv.question,
            "total_claims": len(inv.claims),
            "verified": len(inv.get_verified_claims()),
            "disputed": len(inv.get_disputed_claims()),
            "claims": [
                {
                    "claim": c.claim_text[:80],
                    "status": c.status.value,
                    "confidence": c.confidence,
                    "supporting": len(c.supporting_papers),
                    "counter": len(c.counter_papers),
                    "replications": c.replications,
                    "failed": c.failed_replications,
                }
                for c in inv.claims
            ],
        }, indent=2)

        # visual_evidence_segments.jsonl
        ves_lines = []
        for seg in mevf.segments:
            ves_lines.append(json.dumps(seg.to_dict()))
        result.bundle["visual_evidence_segments.jsonl"] = "\n".join(ves_lines)

        # scene_graph.json
        result.bundle["scene_graph.json"] = json.dumps(
            [s.to_dict() for s in result.scene_graph], indent=2
        )

        # simulations.json
        sims = []
        for seg in mevf.segments:
            if seg.visual_type == "simulation":
                sim = self.simulation_engine.generate_for_concept(
                    self._extract_concept(seg.claim),
                    seg.visual_description,
                )
                sims.append(sim.to_dict())
        result.bundle["simulations.json"] = json.dumps(sims, indent=2)

        # timeline.edl
        if compile_video:
            edl_lines = ["TITLE: VideoLake Investigation", "FCM: NON-DROP FRAME", ""]
            for i, seg in enumerate(mevf.segments):
                start_tc = self._format_edl_tc(seg.timestamp_in_video)
                end_tc = self._format_edl_tc(seg.timestamp_in_video + seg.duration_seconds)
                edl_lines.append(f"CLIP NAME: {seg.segment_id}")
                edl_lines.append(f"SOURCE IN: {start_tc}")
                edl_lines.append(f"SOURCE OUT: {end_tc}")
                edl_lines.append(f"COMMENT: {seg.claim[:40]}")
                edl_lines.append("")
            result.bundle["timeline.edl"] = "\n".join(edl_lines)

        # claims.jsonld — nanopublication-compatible JSON-LD claims
        claims_jsonld = {
            "@context": {
                "np": "http://www.nanopub.org/nschema#",
                "prov": "http://www.w3.org/ns/prov#",
                "schema": "https://schema.org/",
                "dcterms": "http://purl.org/dc/terms/",
            },
            "@graph": [],
        }
        for i, claim in enumerate(inv.claims):
            claims_jsonld["@graph"].append({
                "@id": f"np:claim_{i+1}",
                "@type": "np:Nanopublication",
                "np:hasAssertion": {
                    "@id": f"np:claim_{i+1}_assertion",
                    "schema:text": claim.claim_text,
                    "schema:status": claim.status.value,
                    "schema:confidence": round(claim.confidence, 3),
                },
                "np:hasProvenance": {
                    "@id": f"np:claim_{i+1}_provenance",
                    "prov:wasDerivedFrom": [p.title for p in claim.source_papers],
                    "dcterms:isReferencedBy": [p.title for p in claim.counter_papers],
                },
                "np:hasPublicationInfo": {
                    "@id": f"np:claim_{i+1}_pubinfo",
                    "dcterms:created": inv.investigation_id,
                    "schema:replicationCount": claim.replications,
                    "schema:failedReplicationCount": claim.failed_replications,
                },
            })
        result.bundle["claims.jsonld"] = json.dumps(claims_jsonld, indent=2)

        # transcript.json — structured transcript with timestamps and claim bindings
        transcript_entries = []
        for seg in mevf.segments:
            transcript_entries.append({
                "start_sec": round(seg.timestamp_in_video, 2),
                "end_sec": round(seg.timestamp_in_video + seg.duration_seconds, 2),
                "timestamp": self._format_vtt_time(seg.timestamp_in_video),
                "text": seg.claim,
                "claim_status": seg.claim_status,
                "not_status": seg.not_status or "",
                "segment_id": seg.segment_id,
                "visual_type": seg.visual_type,
                "rights_status": seg.rights_status,
                "confidence": round(seg.scores.truth_safety_score, 3),
            })
        result.bundle["transcript.json"] = json.dumps({
            "schema": "videolake.transcript.v1",
            "question": inv.question,
            "total_segments": len(transcript_entries),
            "total_duration": sum(s.duration_seconds for s in mevf.segments),
            "entries": transcript_entries,
        }, indent=2)

        # embeddings.json — semantic embedding index (FAISS-compatible schema)
        embedding_records = []
        for seg in mevf.segments:
            emb_id = f"vec_{hashlib.sha256(seg.segment_id.encode()).hexdigest()[:8]}"
            embedding_records.append({
                "id": emb_id,
                "segment_id": seg.segment_id,
                "claim": seg.claim[:100],
                "visual_type": seg.visual_type,
                "embedding_dim": 0,
                "embedding": [],
                "metadata": {
                    "rights_status": seg.rights_status,
                    "claim_status": seg.claim_status,
                    "confidence": round(seg.scores.truth_safety_score, 3),
                    "machine_buyability": round(seg.scores.machine_buyability_score, 3),
                },
            })
        result.bundle["embeddings.json"] = json.dumps({
            "schema": "videolake.embeddings.v1",
            "format": "faiss-compatible",
            "count": len(embedding_records),
            "dimension": 0,
            "index_type": "flat",
            "records": embedding_records,
        }, indent=2)

        # Update manifest with new files
        manifest = json.loads(result.bundle["manifest.json"])
        manifest["files"].update({
            "transcript.vtt": "WebVTT captions with status overlays",
            "transcript.json": "structured transcript with claim bindings",
            "claims.jsonld": "nanopublication-compatible JSON-LD claims",
            "counterclaims.jsonl": "counter-evidence papers",
            "papers.jsonl": "source papers",
            "evidence_graph.json": "evidence graph summary",
            "visual_evidence_segments.jsonl": "VES with 6 machine scores",
            "scene_graph.json": "scene descriptions per timestamp",
            "simulations.json": "simulation specs for invisible systems",
            "embeddings.json": "FAISS-compatible semantic embedding index",
            "timeline.edl": "EDL for video editing" if compile_video else "not compiled",
        })
        manifest["scene_count"] = len(result.scene_graph)
        manifest["total_files"] = len(result.bundle)
        result.bundle["manifest.json"] = json.dumps(manifest, indent=2)

    def _extract_concept(self, text: str) -> str:
        """Extract a concept keyword from text for simulation generation."""
        text_lower = text.lower()
        for concept in ["resonance", "energy", "field", "frequency", "wave", "earth"]:
            if concept in text_lower:
                return concept
        return "abstract"

    def _format_vtt_time(self, seconds: float) -> str:
        """Format seconds as WebVTT timestamp (HH:MM:SS.mmm)."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

    def _format_edl_tc(self, seconds: float) -> str:
        """Format seconds as EDL timecode (HH:MM:SS:FF)."""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        f = int((seconds % 1) * 30)  # 30fps
        return f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"

    def _encode_base64_packet(self, bundle: dict[str, str]) -> str:
        """
        Encode the full bundle as a Base64 packet for machine audit.

        The packet format:
            {
                "packet_type": "videolake_asset_packet_v1",
                "timestamp": ...,
                "file_count": N,
                "files": {
                    "filename": base64_content,
                    ...
                },
                "packet_hash": "sha256:..."
            }

        The entire packet is then Base64 encoded.
        """
        packet = {
            "packet_type": "videolake_asset_packet_v1",
            "timestamp": time.time(),
            "file_count": len(bundle),
            "files": {
                filename: base64.b64encode(content.encode()).decode("utf-8")
                for filename, content in bundle.items()
            },
        }

        # Compute packet hash
        packet["packet_hash"] = f"sha256:{hashlib.sha256(
            json.dumps(packet, sort_keys=True).encode()
        ).hexdigest()[:16]}"

        packet_json = json.dumps(packet, indent=2)
        return base64.b64encode(packet_json.encode()).decode("utf-8")

    def _compute_final_receipt(self, result: VideoLakeResult) -> str:
        """Compute the final receipt hash for the entire compilation."""
        receipt_data = {
            "question": result.question,
            "investigation_id": result.investigation.investigation_id if result.investigation else "",
            "mevf_id": result.mevf.mevf_id if result.mevf else "",
            "vrap_id": result.vrap.vrap_id if result.vrap else "",
            "file_count": len(result.bundle),
            "total_size_bytes": result.total_size_bytes,
            "base64_size": len(result.base64_packet),
            "timestamp": time.time(),
        }
        return f"sha256:{hashlib.sha256(
            json.dumps(receipt_data, sort_keys=True).encode()
        ).hexdigest()[:16]}"

    def verify_packet(self, base64_packet: str) -> dict:
        """
        Verify a Base64 asset packet.

        Decodes the packet, checks the hash, and returns the contents.
        """
        try:
            packet_json = base64.b64decode(base64_packet).decode("utf-8")
            packet = json.loads(packet_json)
        except Exception as e:
            return {"valid": False, "error": f"Decode failed: {e}"}

        # Verify hash
        stored_hash = packet.pop("packet_hash", None)
        computed_hash = f"sha256:{hashlib.sha256(
            json.dumps(packet, sort_keys=True).encode()
        ).hexdigest()[:16]}"

        if stored_hash != computed_hash:
            return {"valid": False, "error": "Packet hash mismatch", "stored": stored_hash, "computed": computed_hash}

        # Decode files
        files = {}
        for filename, b64_content in packet.get("files", {}).items():
            files[filename] = base64.b64decode(b64_content).decode("utf-8")

        return {
            "valid": True,
            "packet_type": packet.get("packet_type"),
            "file_count": packet.get("file_count"),
            "timestamp": packet.get("timestamp"),
            "files": list(files.keys()),
            "decoded_files": files,
        }
