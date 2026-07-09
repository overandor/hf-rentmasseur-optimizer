"""
Membra Asset Compiler — Unified MCRV + FRVO pipeline.

Binds the four product branches into a single compile command:

    1. VideoLake Compiler      — question → investigation → evidence graph → video packet
    2. Asteroid Belt Prospector — raw measurements → anomaly mining → high-value questions
    3. Video Systems Genome     — public repos → capability graph → adapter routing
    4. Fractional Rights Vault  — video asset → rights packet → revenue ledger → payout waterfall

The output is a single Machine-Consumable Research Video (MCRV) bound to a
Fractional Revenue Video Object (FRVO), producing a watchable, verifiable,
licensable, financeable media asset.

Usage:
    from broll.asset_compiler import AssetCompiler
    compiler = AssetCompiler()
    result = compiler.compile_video_asset(
        question="What does the Hubble tension reveal about cosmology?",
        prospect="astro",
        rights_ledger=True,
        revenue_ledger=True,
    )
    print(result.manifest)

CLI:
    membra compile-video-asset \\
      --question "What does the Hubble tension reveal about cosmology?" \\
      --prospect astro \\
      --render mcrv \\
      --rights-ledger \\
      --revenue-ledger \\
      --operator local-ollama
"""

import base64
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AssetManifest:
    """
    Unified manifest schema (mcrv_frvo_v1).

    Binds the four branches into one machine-readable asset object.
    """
    asset_type: str = "mcrv_frvo_v1"
    question: str = ""
    timestamp: float = 0.0

    # Branch references (hashes/IDs, not raw objects)
    investigation_graph: str = ""
    video_packet: str = ""
    rights_packet: str = ""
    revenue_packet: str = ""
    capability_sources: str = ""
    operator_session: str = ""

    # Embedded data
    investigation_id: str = ""
    videolake_files: list[str] = field(default_factory=list)
    frvo_id: str = ""
    offering_mode: str = ""
    capability_graph_hash: str = ""
    genome_repos_used: list[str] = field(default_factory=list)
    prospect_id: str = ""
    prospect_score: float = 0.0

    # Scores
    confidence_score: float = 0.0
    rights_safety: float = 0.0
    machine_buyability: float = 0.0
    collateral_score: float = 0.0

    # Receipts
    receipts: list[dict] = field(default_factory=list)
    manifest_hash: str = ""

    # Output files
    output_files: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "asset_type": self.asset_type,
            "question": self.question,
            "timestamp": self.timestamp,
            "investigation_graph": self.investigation_graph,
            "video_packet": self.video_packet,
            "rights_packet": self.rights_packet,
            "revenue_packet": self.revenue_packet,
            "capability_sources": self.capability_sources,
            "operator_session": self.operator_session,
            "investigation_id": self.investigation_id,
            "videolake_files": self.videolake_files,
            "frvo_id": self.frvo_id,
            "offering_mode": self.offering_mode,
            "capability_graph_hash": self.capability_graph_hash,
            "genome_repos_used": self.genome_repos_used,
            "prospect_id": self.prospect_id,
            "prospect_score": round(self.prospect_score, 3),
            "confidence_score": round(self.confidence_score, 3),
            "rights_safety": round(self.rights_safety, 3),
            "machine_buyability": round(self.machine_buyability, 3),
            "collateral_score": round(self.collateral_score, 3),
            "receipts": self.receipts,
            "manifest_hash": self.manifest_hash,
            "output_files": list(self.output_files.keys()),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def compute_hash(self) -> str:
        data = json.dumps({
            "asset_type": self.asset_type,
            "question": self.question,
            "investigation_id": self.investigation_id,
            "frvo_id": self.frvo_id,
            "capability_graph_hash": self.capability_graph_hash,
            "prospect_id": self.prospect_id,
            "timestamp": self.timestamp,
        }, sort_keys=True)
        self.manifest_hash = f"sha256:{hashlib.sha256(data.encode()).hexdigest()[:16]}"
        return self.manifest_hash


@dataclass
class AssetCompileResult:
    """Complete output of a compile_video_asset run."""
    manifest: Optional[AssetManifest] = None
    videolake_result: Optional[object] = None
    frvo: Optional[object] = None
    capability_graph: Optional[object] = None
    prospect: Optional[object] = None
    payout_simulation: Optional[object] = None
    proof_packet: Optional[dict] = None
    grade_claim: Optional[object] = None
    bmma: Optional[object] = None
    bea: Optional[object] = None
    standards_exports: dict = field(default_factory=dict)
    segment_marketplace: Optional[object] = None
    asset_packet_b64: str = ""
    output_dir: str = ""

    def summary(self) -> dict:
        s = {}
        if self.manifest:
            s["asset_type"] = self.manifest.asset_type
            s["question"] = self.manifest.question
            s["manifest_hash"] = self.manifest.manifest_hash
            s["files"] = list(self.manifest.output_files.keys())
        if self.videolake_result:
            s["investigation_claims"] = len(self.videolake_result.investigation.claims) if self.videolake_result.investigation else 0
            s["videolake_files"] = len(self.videolake_result.bundle) if hasattr(self.videolake_result, 'bundle') else 0
        if self.frvo:
            s["frvo_id"] = self.frvo.frvo_id
            s["offering_mode"] = self.frvo.offering_mode.value
            s["backers"] = len(self.frvo.backers)
        if self.capability_graph:
            s["genome_repos"] = self.capability_graph.total_repos
            s["genome_coverage"] = round(self.capability_graph.coverage_score, 3)
        if self.prospect:
            s["prospect_score"] = round(self.prospect.overall_score, 3)
        if self.payout_simulation:
            s["simulated_revenue"] = self.payout_simulation.total_gross
            s["simulated_net"] = self.payout_simulation.total_net
        if self.proof_packet:
            s["ledger_valid"] = self.proof_packet.get("ledger_valid", False)
        if self.grade_claim:
            s["claimed_grade"] = self.grade_claim.claimed_grade
            s["computed_grade"] = self.grade_claim.computed_grade
            s["bond_amount"] = self.grade_claim.bond_amount_usd
        if self.bmma:
            s["bmma_id"] = self.bmma.bmma_id
            s["bea_id"] = self.bmma.bea_id
            s["schema_org"] = bool(self.bmma.schema_org_object)
            s["c2pa_manifest"] = bool(self.bmma.c2pa_manifest)
            s["segment_listings"] = len(self.bmma.segment_listings)
        if self.standards_exports:
            s["standards_keys"] = list(self.standards_exports.keys())
        if self.segment_marketplace:
            s["marketplace_listings"] = len(self.segment_marketplace.listings)
        s["packet_size"] = len(self.asset_packet_b64)
        return s


class AssetCompiler:
    """
    Unified MCRV + FRVO + AGB compiler.

    Single entry point that binds:
        - VideoLake (evidence-backed video)
        - BeltProspector (content discovery)
        - VideoSystemsGenome (capability routing)
        - RightsVault (fractional revenue)
        - GradeBondProtocol (sealed grade bond)

    The output is a Bonded Machine Media Asset (BMMA) that is:
        - watchable (video.mp4)
        - verifiable (claims.jsonld, evidence.jsonld)
        - licensable (rights.json, market_terms.json)
        - financeable (revenue_ledger.json, fractional_rights_packet.json)
        - bonded (grade_bond.json, bmma.json)
    """

    def __init__(self):
        from .videolake import VideoLakeCompiler
        from .rights_vault import RightsVault, OfferingMode
        from .video_genome import VideoSystemsGenome
        from .belt_prospector import BeltProspector
        from .grade_bond import GradeBondProtocol

        self.videolake = VideoLakeCompiler()
        self.rights_vault = RightsVault()
        self.genome = VideoSystemsGenome()
        self.prospector = BeltProspector()
        self.grade_bond = GradeBondProtocol()

    def compile_video_asset(
        self,
        question: str = "",
        prospect: str = "",
        render: str = "mcrv",
        rights_ledger: bool = True,
        revenue_ledger: bool = True,
        grade_bond: bool = True,
        bond_amount_usd: float = 5000.0,
        rubric_id: str = "video_evidence_quality_v1",
        operator: str = "",
        offering_mode: str = "PERK_ONLY",
        output_dir: str | None = None,
        compile_video: bool = True,
        simulate_revenue: float = 0.0,
    ) -> AssetCompileResult:
        """
        Compile a complete evidence-backed media asset.

        Args:
            question: Research question. If empty and prospect is set, auto-discovers.
            prospect: Content discovery source ("astro" for Asteroid Belt Prospector).
            render: Output format ("mcrv" for machine-consumable research video).
            rights_ledger: Whether to create a FRVO rights packet.
            revenue_ledger: Whether to create a revenue ledger with payout waterfall.
            operator: Operator session identifier ("local-ollama", etc.).
            offering_mode: Rights offering mode (PERK_ONLY, RIGHTS_RESERVATION,
                          REGULATED_REVENUE_SHARE, MACHINE_RIGHTS_MARKET).
            output_dir: Directory to write output files.
            compile_video: Whether to compile actual video.
            simulate_revenue: If >0, simulate a payout at this revenue level.
            grade_bond: Whether to create a sealed grade bond (AGB).
            bond_amount_usd: Bond amount to stake behind the grade claim.
            rubric_id: Which rubric to use for grading.

        Returns:
            AssetCompileResult with all artifacts bound together, including BMMA.
        """
        from .rights_vault import OfferingMode as OM

        result = AssetCompileResult()
        manifest = AssetManifest(
            question=question,
            timestamp=time.time(),
            operator_session=operator,
        )
        receipts = []

        # 1. Prospect (optional content discovery)
        if prospect == "astro":
            survey = self.prospector.prospect()
            if survey.prospects:
                best = survey.prospects[0]
                if not question:
                    question = best.suggested_question
                    manifest.question = question
                manifest.prospect_id = best.prospect_id
                manifest.prospect_score = best.overall_score
                result.prospect = best
                receipts.append({
                    "action": "prospect",
                    "source": "asteroid_belt",
                    "prospect_id": best.prospect_id,
                    "score": round(best.overall_score, 3),
                    "question": best.suggested_question[:100],
                })

        # 2. VideoLake compilation (evidence-backed video)
        vl_result = self.videolake.compile(
            question=question,
            output_dir=output_dir,
            compile_video=compile_video,
            write_receipts=True,
            export_b64=True,
            pack_mcrv=True,
        )
        result.videolake_result = vl_result
        manifest.investigation_id = (
            vl_result.investigation.investigation_id if vl_result.investigation else ""
        )
        manifest.videolake_files = list(vl_result.bundle.keys())
        manifest.video_packet = vl_result.base64_packet[:64] + "..." if vl_result.base64_packet else ""

        if vl_result.investigation:
            manifest.investigation_graph = vl_result.investigation.receipt_hash

        if vl_result.mevf:
            manifest.confidence_score = vl_result.mevf.avg_machine_buyability

        if vl_result.vrap:
            manifest.machine_buyability = vl_result.vrap.avg_machine_buyability
            manifest.rights_safety = (
                sum(1 for s in vl_result.mevf.segments if s.rights_status == "safe")
                / max(len(vl_result.mevf.segments), 1)
            ) if vl_result.mevf else 0.0

        receipts.append({
            "action": "videolake_compile",
            "investigation_id": manifest.investigation_id,
            "files": len(vl_result.bundle),
            "receipt_hash": vl_result.receipt_hash,
        })

        # 3. Video Systems Genome (capability routing)
        self.genome.discover()
        self.genome.classify()
        cap_graph = self.genome.build_capability_graph()
        result.capability_graph = cap_graph
        manifest.capability_graph_hash = cap_graph.graph_hash

        # Find which genome repos could serve this question's capabilities
        workflow = self.genome.compose_workflow("text_to_video_pipeline")
        manifest.genome_repos_used = [
            s["repo"] for s in workflow.steps if s.get("repo")
        ]
        manifest.capability_sources = workflow.receipt_hash

        receipts.append({
            "action": "genome_build",
            "repos": cap_graph.total_repos,
            "coverage": round(cap_graph.coverage_score, 3),
            "graph_hash": cap_graph.graph_hash,
        })

        # 4. Rights Vault (FRVO)
        if rights_ledger:
            mode = OM(offering_mode) if offering_mode in [m.value for m in OM] else OM.PERK_ONLY
            frvo = self.rights_vault.create_frvo(
                videolake_result=vl_result,
                offering_mode=mode,
            )
            self.rights_vault.open_offering(frvo)
            result.frvo = frvo
            manifest.frvo_id = frvo.frvo_id
            manifest.offering_mode = frvo.offering_mode.value
            manifest.rights_packet = frvo.receipt_hash

            receipts.append({
                "action": "frvo_create",
                "frvo_id": frvo.frvo_id,
                "offering_mode": frvo.offering_mode.value,
                "receipt_hash": frvo.receipt_hash,
            })

            # 5. Revenue ledger
            if revenue_ledger and simulate_revenue > 0:
                payout = self.rights_vault.simulate_payout(frvo, simulate_revenue)
                self.rights_vault.record_payout(frvo, payout)
                result.payout_simulation = payout
                manifest.revenue_packet = payout.receipt_hash

                receipts.append({
                    "action": "revenue_simulation",
                    "total_gross": payout.total_gross,
                    "total_net": payout.total_net,
                    "backers_paid": len(payout.backer_payouts),
                    "receipt_hash": payout.receipt_hash,
                })

            # Generate proof packet
            proof = self.rights_vault.generate_proof_packet(frvo)
            result.proof_packet = proof
            manifest.collateral_score = 1.0 if proof.get("ledger_valid") else 0.0

        # 5b. Grade Bond (AGB) + BEA + Standards + Marketplace
        if grade_bond:
            machine_scores = {
                "evidence_strength": manifest.confidence_score,
                "rights_safety": manifest.rights_safety,
                "machine_buyability": manifest.machine_buyability,
                "provenance_integrity": manifest.collateral_score,
                "revenue_receipt_quality": manifest.collateral_score,
                "ledger_integrity": 1.0 if result.proof_packet and result.proof_packet.get("ledger_valid") else 0.0,
                "license_clarity": manifest.rights_safety,
                "copyright_clean": manifest.rights_safety,
                "license_available": 1.0 if result.frvo and result.frvo.machine_bid_packet.get("license_available") else 0.0,
                "segment_granularity": 0.5,
                "receipt_completeness": min(len(receipts) / 5.0, 1.0),
                "source_quality": manifest.confidence_score,
                "claim_coverage": manifest.confidence_score,
                "counter_evidence": 0.5,
                "peer_review": 0.5,
                "reproducibility": 0.5,
                "confidence_calibration": manifest.confidence_score,
                "payout_traceability": 1.0 if result.payout_simulation else 0.0,
            }

            computed_grade = self.grade_bond.compute_grade(rubric_id, machine_scores)
            claimed_grade = min(computed_grade + 2.0, 100.0)

            claim = self.grade_bond.create_grade_claim(
                media_packet_id=manifest.investigation_id,
                frvo_id=manifest.frvo_id or "no_frvo",
                rubric_id=rubric_id,
                claimed_grade=claimed_grade,
                bond_amount_usd=bond_amount_usd,
                machine_scores=machine_scores,
            )
            result.grade_claim = claim

            # Create BEA (Bonded Evidence Asset) — generalized financeable primitive
            artifact_data = json.dumps({
                "question": question,
                "investigation_id": manifest.investigation_id,
                "manifest_hash": manifest.manifest_hash,
            }, sort_keys=True).encode()
            bea = self.grade_bond.create_bea(
                asset_type="mcrv",
                artifact_data=artifact_data,
                rubric_id=rubric_id,
                claimed_grade=claimed_grade,
                bond_amount_usd=bond_amount_usd,
                machine_scores=machine_scores,
                media_packet_id=manifest.investigation_id,
                frvo_id=manifest.frvo_id or "no_frvo",
            )
            result.bea = bea

            # Standards exports (Schema.org VideoObject + C2PA manifest)
            from .standards_export import StandardsExporter
            exporter = StandardsExporter()
            claims_list = []
            evidence_list = []
            if vl_result.investigation:
                claims_list = [
                    {"claim_id": getattr(c, 'claim_id', str(i)), "text": getattr(c, 'text', str(c))}
                    for i, c in enumerate(vl_result.investigation.claims)
                ]
                evidence_list = [
                    {"paper_id": getattr(p, 'paper_id', str(i)), "title": getattr(p, 'title', str(p))}
                    for i, p in enumerate(vl_result.investigation.papers)
                ]

            schema_org = exporter.to_schema_org_videoobject(
                question=question,
                duration_seconds=0.0,
                transcript="",
                claims=claims_list,
                evidence=evidence_list,
                rights_label="safe" if manifest.rights_safety > 0.5 else "unknown",
                creator="Membra EvidenceOS",
                manifest_hash=manifest.manifest_hash,
                confidence_score=manifest.confidence_score,
                machine_buyability=manifest.machine_buyability,
                bmma_id="",
                grade_claimed=claimed_grade,
                revenue_sources=[s.to_dict().get("source_type", "") for s in result.frvo.revenue_sources] if result.frvo else [],
            )
            c2pa = exporter.to_c2pa_manifest(
                title=question,
                creator="Membra EvidenceOS",
                manifest_hash=manifest.manifest_hash,
                claims=claims_list,
                evidence=evidence_list,
                rights_label="safe" if manifest.rights_safety > 0.5 else "unknown",
                confidence_score=manifest.confidence_score,
                bmma_id="",
                grade_claimed=claimed_grade,
            )
            result.standards_exports = {
                "schema_org_videoobject": schema_org,
                "c2pa_manifest": c2pa.to_dict(),
            }

            # Segment marketplace — register segments from MEVF
            from .segment_marketplace import SegmentMarketplace
            marketplace = SegmentMarketplace()
            segment_listings = []
            if vl_result.mevf and vl_result.mevf.segments:
                for seg in vl_result.mevf.segments:
                    seg_dict = {
                        "segment_id": getattr(seg, 'segment_id', f"seg_{hashlib.sha256(str(time.time()).encode()).hexdigest()[:8]}"),
                        "claim": getattr(seg, 'claim', ''),
                        "claim_type": getattr(seg, 'claim_type', 'unknown'),
                        "transcript_text": getattr(seg, 'transcript_text', ''),
                        "start_sec": getattr(seg, 'start_sec', 0.0),
                        "end_sec": getattr(seg, 'end_sec', 0.0),
                        "visual_concepts": getattr(seg, 'visual_concepts', []),
                        "evidence_relevance_score": getattr(seg, 'evidence_relevance_score', 0.0),
                        "truth_safety_score": getattr(seg, 'truth_safety_score', 0.0),
                        "semantic_match_score": getattr(seg, 'semantic_match_score', 0.0),
                        "machine_buyability": getattr(seg, 'machine_buyability', 0.0),
                        "rights_status": getattr(seg, 'rights_status', 'unknown'),
                    }
                    listing = marketplace.register_segment(
                        seg_dict,
                        media_packet_id=manifest.investigation_id,
                        frvo_id=manifest.frvo_id or "",
                        bmma_id="",
                    )
                    segment_listings.append(listing.to_dict())
            result.segment_marketplace = marketplace

            # Create BMMA with all layers bound
            media_packet_dict = {
                "video": "video.mp4",
                "claims": "claims.jsonld",
                "evidence": "evidence.jsonld",
                "provenance": "provenance.prov.json",
                "rights": "rights.json",
                "receipts": "receipts.jsonl",
            }
            fr_dict = {}
            if result.frvo:
                fr_dict = {
                    "revenue_sources": [s.to_dict() for s in result.frvo.revenue_sources],
                    "participant_registry": [b.to_dict() for b in result.frvo.backers],
                    "payout_waterfall": [w.to_dict() for w in result.frvo.payout_waterfall],
                    "revenue_receipts": [r for r in manifest.receipts if r.get("action") == "revenue_simulation"],
                    "offering_mode": result.frvo.offering_mode.value,
                    "ledger_valid": result.proof_packet.get("ledger_valid", True) if result.proof_packet else True,
                }

            market_summary = marketplace.market_summary() if marketplace.listings else {}

            manifest.receipts = receipts
            manifest.compute_hash()

            bmma = self.grade_bond.create_bmma(
                claim=claim,
                media_packet=media_packet_dict,
                fractional_revenue=fr_dict,
                question=question,
                bea=bea,
                schema_org_object=schema_org,
                c2pa_manifest=c2pa.to_dict(),
                segment_listings=segment_listings,
                marketplace_summary=market_summary,
                provenance_hash=manifest.manifest_hash,
            )
            result.bmma = bmma

            # Patch the schema_org and c2pa with the actual bmma_id
            if bmma.schema_org_object:
                bmma.schema_org_object["membra:bmmaId"] = bmma.bmma_id
            if bmma.c2pa_manifest and bmma.c2pa_manifest.get("claim"):
                bmma.c2pa_manifest["claim"]["assertions"] = bmma.c2pa_manifest["claim"].get("assertions", []) + [
                    {"label": "membra.bmma_id", "value": bmma.bmma_id, "type": "text"}
                ]

            receipts.append({
                "action": "grade_bond_seal",
                "claim_id": claim.claim_id,
                "rubric_id": rubric_id,
                "claimed_grade": claimed_grade,
                "computed_grade": computed_grade,
                "bond_amount_usd": bond_amount_usd,
                "bmma_id": bmma.bmma_id,
                "bea_id": bea.bea_id,
                "schema_org": bool(schema_org),
                "c2pa": bool(c2pa),
                "segments_listed": len(segment_listings),
                "receipt_hash": claim.receipt_hash,
            })

        # 6. Build manifest
        manifest.receipts = receipts
        manifest.compute_hash()

        # 7. Write output files
        output_files = self._write_output_files(
            manifest, vl_result, result, output_dir
        )
        manifest.output_files = output_files
        result.output_dir = output_dir or ""

        # 8. Build unified asset packet (base64)
        result.asset_packet_b64 = self._build_asset_packet(manifest, vl_result, result)
        result.manifest = manifest

        return result

    def _write_output_files(
        self,
        manifest: AssetManifest,
        vl_result,
        result: AssetCompileResult,
        output_dir: str | None,
    ) -> dict[str, str]:
        """Write the expected output file set."""
        import os

        files = {}

        def _write(name: str, content: str):
            if output_dir:
                path = os.path.join(output_dir, name)
                os.makedirs(output_dir, exist_ok=True)
                with open(path, "w") as f:
                    f.write(content)
            files[name] = content

        # Core manifest
        _write("asset_manifest.json", manifest.to_json())

        # VideoLake bundle files (already written by compiler, but record them)
        if hasattr(vl_result, 'bundle'):
            for fname in vl_result.bundle:
                files[fname] = f"<videolake_bundle:{fname}>"

        # MCRV sidecar
        if vl_result.mcrv_sidecar:
            _write("machine_sidecar.jsonld", json.dumps(
                vl_result.mcrv_sidecar.to_dict() if hasattr(vl_result.mcrv_sidecar, 'to_dict')
                else str(vl_result.mcrv_sidecar), indent=2
            ))

        # Claims and evidence (from investigation)
        if vl_result.investigation:
            claims_data = [
                {
                    "claim_id": c.claim_id if hasattr(c, 'claim_id') else str(i),
                    "text": c.text if hasattr(c, 'text') else str(c),
                    "truth_status": c.truth_status.value if hasattr(c, 'truth_status') else "unknown",
                }
                for i, c in enumerate(vl_result.investigation.claims)
            ]
            _write("claims.jsonld", json.dumps(claims_data, indent=2))

            evidence_data = [
                {
                    "paper_id": p.paper_id if hasattr(p, 'paper_id') else str(i),
                    "title": p.title if hasattr(p, 'title') else str(p),
                    "year": p.year if hasattr(p, 'year') else 0,
                    "citation_count": p.citation_count if hasattr(p, 'citation_count') else 0,
                }
                for i, p in enumerate(vl_result.investigation.papers)
            ]
            _write("evidence.jsonld", json.dumps(evidence_data, indent=2))

            counterclaims = [
                {
                    "claim_id": c.claim_id if hasattr(c, 'claim_id') else str(i),
                    "counter_papers": len(c.counter_papers) if hasattr(c, 'counter_papers') else 0,
                }
                for i, c in enumerate(vl_result.investigation.claims)
                if hasattr(c, 'counter_papers') and len(c.counter_papers) > 0
            ]
            _write("counterclaims.jsonl", "\n".join(json.dumps(c) for c in counterclaims))

        # Provenance
        _write("provenance.prov.json", json.dumps({
            "@context": {"prov": "http://www.w3.org/ns/prov#"},
            "@type": "prov:Entity",
            "investigation_id": manifest.investigation_id,
            "generated_at": manifest.timestamp,
        }, indent=2))

        # RO-Crate metadata
        _write("ro-crate-metadata.json", json.dumps({
            "@context": "https://w3id.org/ro/crate/1.1/context",
            "@graph": [
                {
                    "@type": "CreativeWork",
                    "@id": "ro-crate-metadata.json",
                    "conformsTo": {"@id": "https://w3id.org/ro/crate/1.1"},
                    "about": {"@id": "./"},
                },
                {
                    "@id": "./",
                    "@type": "Dataset",
                    "name": "MCRV+FRVO Asset",
                    "question": manifest.question,
                    "manifest_hash": manifest.manifest_hash,
                },
            ],
        }, indent=2))

        # Rights and revenue
        if result.frvo:
            _write("rights.json", json.dumps(result.frvo.to_dict(), indent=2))
            _write("fractional_rights_packet.json", json.dumps(
                result.proof_packet if result.proof_packet
                else self.rights_vault.generate_proof_packet(result.frvo),
                indent=2
            ))
            _write("market_terms.json", json.dumps({
                "offering_mode": result.frvo.offering_mode.value,
                "unit_price_usd": result.frvo.unit_price_usd,
                "units_available": result.frvo.units_available,
                "revenue_sources": [s.to_dict() for s in result.frvo.revenue_sources],
            }, indent=2))

            if result.payout_simulation:
                _write("revenue_ledger.json", json.dumps(
                    result.payout_simulation.to_dict(), indent=2
                ))

        # Receipts
        _write("receipts.jsonl", "\n".join(json.dumps(r) for r in manifest.receipts))

        # Capability sources
        if result.capability_graph:
            _write("capability_sources.json", json.dumps({
                "graph_hash": result.capability_graph.graph_hash,
                "total_repos": result.capability_graph.total_repos,
                "coverage_score": round(result.capability_graph.coverage_score, 3),
                "repos_used": manifest.genome_repos_used,
            }, indent=2))

        # Grade bond and BMMA
        if result.grade_claim:
            _write("grade_bond.json", json.dumps(result.grade_claim.to_dict(), indent=2))
        if result.bmma:
            _write("bmma.json", json.dumps(result.bmma.to_dict(), indent=2))
            _write("bmma_underwriter_view.json", json.dumps(result.bmma.underwriter_view(), indent=2))
            _write("bmma_public_view.json", json.dumps(result.bmma.public_view(), indent=2))
        if result.bea:
            _write("bonded_evidence_asset.json", json.dumps(result.bea.to_dict(), indent=2))
        if result.standards_exports:
            _write("schema_org_videoobject.jsonld", json.dumps(
                result.standards_exports.get("schema_org_videoobject", {}), indent=2
            ))
            _write("c2pa_manifest.json", json.dumps(
                result.standards_exports.get("c2pa_manifest", {}), indent=2
            ))
        if result.segment_marketplace and result.segment_marketplace.listings:
            _write("segment_marketplace.json", json.dumps(
                result.segment_marketplace.market_summary(), indent=2
            ))

        return files

    def _build_asset_packet(
        self,
        manifest: AssetManifest,
        vl_result,
        result: AssetCompileResult,
    ) -> str:
        """Build the unified asset packet as base64."""
        packet_data = {
            "schema": "mcrv_frvo_asset_packet_v1",
            "manifest": manifest.to_dict(),
        }

        if vl_result.base64_packet:
            packet_data["videolake_packet"] = vl_result.base64_packet

        if result.frvo:
            packet_data["frvo"] = result.frvo.to_dict()

        if result.proof_packet:
            packet_data["proof_packet"] = result.proof_packet

        if result.capability_graph:
            packet_data["capability_graph"] = {
                "hash": result.capability_graph.graph_hash,
                "repos": result.capability_graph.total_repos,
            }

        if result.payout_simulation:
            packet_data["payout_simulation"] = result.payout_simulation.to_dict()

        if result.grade_claim:
            packet_data["grade_claim"] = result.grade_claim.to_dict()

        if result.bmma:
            packet_data["bmma"] = result.bmma.to_dict()
            packet_data["bmma_underwriter_view"] = result.bmma.underwriter_view()
        if result.bea:
            packet_data["bea"] = result.bea.to_dict()
        if result.standards_exports:
            packet_data["standards_exports"] = result.standards_exports
        if result.segment_marketplace and result.segment_marketplace.listings:
            packet_data["segment_marketplace"] = result.segment_marketplace.market_summary()

        encoded = json.dumps(packet_data, sort_keys=True).encode()
        packet_hash = hashlib.sha256(encoded).hexdigest()
        packet_data["packet_hash"] = f"sha256:{packet_hash[:16]}"

        return base64.b64encode(
            json.dumps(packet_data, sort_keys=True).encode()
        ).decode()

    @staticmethod
    def verify_asset_packet(packet_b64: str) -> dict:
        """Verify an asset packet's integrity."""
        try:
            decoded = json.loads(base64.b64decode(packet_b64).decode())
            stored_hash = decoded.pop("packet_hash", None)
            recomputed = f"sha256:{hashlib.sha256(json.dumps(decoded, sort_keys=True).encode()).hexdigest()[:16]}"
            return {
                "valid": stored_hash == recomputed,
                "stored_hash": stored_hash,
                "recomputed_hash": recomputed,
                "schema": decoded.get("schema", ""),
                "manifest_hash": decoded.get("manifest", {}).get("manifest_hash", ""),
            }
        except Exception as e:
            return {"valid": False, "error": str(e)}
