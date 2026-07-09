"""
EvidenceOS — One graph grammar for research claims, software provenance,
media evidence, receipts, manifests, and collateralization.

Membra EvidenceOS is a local-first operating system for turning questions,
repos, investigations, and media into verifiable evidence graphs, hash-chained
receipts, and machine-consumable asset packets.

The key bridge: a research claim and a software artifact are both
evidence-bearing objects. Both follow the same primitive:

    Thing observed
    → claims extracted
    → evidence collected
    → provenance recorded
    → graph built
    → receipt hashed
    → manifest chained
    → outputs rendered

EvidenceOS/
├── graph_core/          ← evidence_core.py (shared kernel)
├── investigation/       ← investigation_graph.py, investigation_engine.py
├── provenance/          ← provenance_graph.py
├── renderers/           ← media_compiler.py, videolake.py
└── underwriter/         ← evidence_os.py (this module)

Usage:
    eos = EvidenceOS()
    result = eos.compile(
        question="Can ancient stone structures exhibit measurable resonance effects?",
        repo_path="/path/to/repo",
    )
    print(result.unified_summary())
"""

import base64
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from .evidence_core import (
    EvidenceGraphCore,
    EvidenceNode,
    EvidenceEdge,
    EvidenceNodeType,
    EvidenceEdgeType,
    EvidenceManifest,
    EvidenceReceipt,
)
from .investigation_engine import InvestigationEngine
from .investigation_graph import InvestigationGraph
from .mevf import MEVFBuilder, MEVFObject
from .vrap import VRAPBuilder, VRAPManifest
from .videolake import VideoLakeCompiler, VideoLakeResult
from .provenance_graph import ProvenanceGraph
from .machine_attention import machine_attention_track, claim_lattice


@dataclass
class UnifiedScores:
    """Shared scoring across research and software evidence."""
    confidence_score: float = 0.0      # How well-supported are the claims
    risk_score: float = 0.0            # What is the overall risk
    collateral_score: float = 0.0      # How valuable as collateral
    rights_safety: float = 0.0         # Are rights/licenses clear
    provenance_completeness: float = 0.0  # Is the provenance chain complete
    machine_buyability: float = 0.0    # Can a machine safely consume this

    def to_dict(self) -> dict:
        return {
            "confidence_score": round(self.confidence_score, 3),
            "risk_score": round(self.risk_score, 3),
            "collateral_score": round(self.collateral_score, 3),
            "rights_safety": round(self.rights_safety, 3),
            "provenance_completeness": round(self.provenance_completeness, 3),
            "machine_buyability": round(self.machine_buyability, 3),
        }


@dataclass
class EvidenceOSResult:
    """The complete output of an EvidenceOS compilation."""
    question: str = ""
    timestamp: float = 0.0

    # Investigation track
    investigation: Optional[InvestigationGraph] = None
    mevf: Optional[MEVFObject] = None
    vrap: Optional[VRAPManifest] = None
    videolake_result: Optional[VideoLakeResult] = None

    # Provenance track
    provenance: Optional[ProvenanceGraph] = None

    # Unified
    unified_graph: Optional[EvidenceGraphCore] = None
    unified_manifest: Optional[EvidenceManifest] = None
    unified_receipt: Optional[EvidenceReceipt] = None
    scores: Optional[UnifiedScores] = None

    # Packet
    base64_packet: str = ""
    receipt_hash: str = ""

    def unified_summary(self) -> dict:
        """Human-readable summary of the unified compilation."""
        summary = {
            "question": self.question,
            "timestamp": self.timestamp,
            "receipt_hash": self.receipt_hash,
        }

        if self.investigation:
            summary["investigation"] = {
                "claims": len(self.investigation.claims),
                "papers": len(self.investigation.papers),
                "receipt": self.investigation.receipt_hash,
            }

        if self.mevf:
            summary["mevf"] = {
                "segments": len(self.mevf.segments),
                "trust_grade": self.mevf.trust_grade,
                "avg_buyability": round(self.mevf.avg_machine_buyability, 3),
            }

        if self.vrap:
            summary["vrap"] = {
                "asset_type": self.vrap.asset_type,
                "total_price": self.vrap.total_price_usd,
            }

        if self.videolake_result:
            summary["videolake"] = {
                "files": len(self.videolake_result.bundle),
                "size_bytes": self.videolake_result.total_size_bytes,
            }

        if self.provenance:
            summary["provenance"] = self.provenance.stats

        if self.unified_graph:
            summary["unified_graph"] = self.unified_graph.stats()

        if self.scores:
            summary["unified_scores"] = self.scores.to_dict()

        if self.unified_manifest:
            summary["manifest"] = {
                "merkle_root": self.unified_manifest.merkle_root,
                "artifact_count": self.unified_manifest.artifact_count,
                "manifest_hash": self.unified_manifest.manifest_hash,
                "verified": self.unified_manifest.verify(),
            }

        summary["base64_packet_size"] = len(self.base64_packet)

        return summary


class EvidenceOS:
    """
    Evidence Operating System — unifies investigation and provenance.

    One graph grammar for research claims, software provenance, media evidence,
    receipts, manifests, and collateralization.

    Usage:
        eos = EvidenceOS()
        result = eos.compile(
            question="Can ancient stone structures exhibit measurable resonance effects?",
            repo_path="/path/to/repo",  # optional
        )
        print(result.unified_summary())
    """

    def __init__(self):
        self.investigation_engine = InvestigationEngine()
        self.mevf_builder = MEVFBuilder()
        self.vrap_builder = VRAPBuilder()
        self.videolake_compiler = VideoLakeCompiler()

    def compile(
        self,
        question: str,
        repo_path: str | None = None,
        repo_name: str = "",
        output_dir: str | None = None,
        export_b64: bool = True,
    ) -> EvidenceOSResult:
        """
        Compile a question (and optionally a repo) into a unified evidence packet.

        Args:
            question: The research question to investigate
            repo_path: Optional path to a repository for provenance analysis
            repo_name: Optional repository name
            output_dir: Directory to write files to
            export_b64: Whether to generate Base64 packet

        Returns:
            EvidenceOSResult with all artifacts
        """
        result = EvidenceOSResult(
            question=question,
            timestamp=time.time(),
        )

        # 1. Investigation track
        result.investigation = self.investigation_engine.investigate(question)
        result.mevf = self.mevf_builder.build(result.investigation)
        result.vrap = self.vrap_builder.build(result.mevf, result.investigation)
        result.videolake_result = self.videolake_compiler.compile(
            question=question,
            output_dir=output_dir,
            export_b64=export_b64,
        )

        # 2. Provenance track (if repo provided)
        if repo_path:
            result.provenance = self._scan_repository(repo_path, repo_name)

        # 3. Build unified graph
        result.unified_graph = self._build_unified_graph(result)

        # 4. Build unified manifest
        result.unified_manifest = self._build_unified_manifest(result)

        # 5. Build unified receipt ledger
        result.unified_receipt = self._build_unified_receipts(result)

        # 6. Compute unified scores
        result.scores = self._compute_unified_scores(result)

        # 7. Base64 packet
        if export_b64:
            result.base64_packet = self._encode_packet(result)

        # 8. Final receipt hash
        result.receipt_hash = self._compute_final_receipt(result)

        return result

    def _scan_repository(self, repo_path: str, repo_name: str = "") -> ProvenanceGraph:
        """Scan a repository and build a provenance graph."""
        import os

        name = repo_name or os.path.basename(repo_path.rstrip("/"))
        graph = ProvenanceGraph(repo_name=name)
        graph.add_repository(name, url=f"file://{repo_path}")

        # Walk the repository
        for root, dirs, files in os.walk(repo_path):
            # Skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith(".") and d != "__pycache__"]

            for filename in files:
                filepath = os.path.join(root, filename)
                rel_path = os.path.relpath(filepath, repo_path)

                try:
                    size = os.path.getsize(filepath)
                except OSError:
                    size = 0

                # Determine language
                ext = os.path.splitext(filename)[1].lower()
                lang_map = {
                    ".py": "python", ".js": "javascript", ".ts": "typescript",
                    ".go": "go", ".rs": "rust", ".java": "java",
                    ".md": "markdown", ".json": "json", ".yaml": "yaml",
                    ".yml": "yaml", ".toml": "toml", ".txt": "text",
                }
                language = lang_map.get(ext, "unknown")

                # Compute hash
                try:
                    with open(filepath, "rb") as f:
                        sha = hashlib.sha256(f.read()).hexdigest()[:16]
                except (OSError, PermissionError):
                    sha = ""

                # Count lines
                lines = 0
                try:
                    with open(filepath, "r", errors="ignore") as f:
                        lines = sum(1 for _ in f)
                except (OSError, PermissionError):
                    pass

                graph.add_file(
                    path=rel_path, size=size, sha256=sha,
                    language=language, lines=lines,
                )

                # Detect secrets
                if any(s in filename.lower() for s in [".env", "secret", "key", "token"]):
                    graph.add_secret("potential_secret_file", rel_path)

        # Add real git commits if available, otherwise record scan metadata
        git_commits = self._get_git_commits(repo_path)
        if git_commits:
            for c in git_commits[:5]:
                graph.add_commit(
                    commit_hash=c["hash"],
                    author=c["author"],
                    message=c["message"],
                    files_changed=c.get("files_changed", []),
                )
        else:
            graph.add_commit(
                commit_hash=hashlib.sha256(f"scan:{repo_path}:{time.time()}".encode()).hexdigest()[:16],
                author="evidence_os",
                message="Repository scan (no git history available)",
                files_changed=list(graph._files.keys())[:5],
            )

        # Add license if found
        for filepath in graph._files:
            if "license" in filepath.lower() or filepath == "LICENSE":
                graph.add_license("detected", filepath)
                break
        else:
            graph.add_license("unknown")

        # Add build artifact
        graph.add_build_artifact("evidence_packet", "evidence", "pending")

        graph.finalize()
        graph.build_manifest()

        return graph

    @staticmethod
    def _get_git_commits(repo_path: str) -> list[dict]:
        """Get recent git commits from the repository."""
        import subprocess
        try:
            result = subprocess.run(
                ["git", "log", "--pretty=format:%H|%an|%s", "--name-only", "-5"],
                cwd=repo_path, capture_output=True, text=True, timeout=10,
            )
            if result.returncode != 0:
                return []

            commits: list[dict] = []
            current: dict | None = None
            for line in result.stdout.split("\n"):
                if "|" in line and line.count("|") >= 2:
                    if current:
                        commits.append(current)
                    parts = line.split("|", 2)
                    current = {"hash": parts[0][:16], "author": parts[1], "message": parts[2], "files_changed": []}
                elif line.strip() and current is not None:
                    current["files_changed"].append(line.strip())
            if current:
                commits.append(current)
            return commits
        except Exception:
            return []

    def _build_unified_graph(self, result: EvidenceOSResult) -> EvidenceGraphCore:
        """Build a unified evidence graph combining investigation + provenance."""
        graph = EvidenceGraphCore(
            graph_id=hashlib.sha256(
                f"evidenceos:{result.question}:{time.time()}".encode()
            ).hexdigest()[:16]
        )

        # Add investigation claims as nodes
        if result.investigation:
            for i, claim in enumerate(result.investigation.claims):
                claim_id = f"inv_claim_{i+1}"
                graph.add_node(EvidenceNode(
                    node_id=claim_id,
                    node_type=EvidenceNodeType.CLAIM,
                    label=claim.claim_text[:60],
                    content={
                        "status": claim.status.value,
                        "confidence": claim.confidence,
                        "supporting": len(claim.supporting_papers),
                        "counter": len(claim.counter_papers),
                    },
                    confidence_score=claim.confidence,
                    receipt_hash=claim.receipt_hash,
                ))

                # Add supporting papers
                for j, paper in enumerate(claim.supporting_papers):
                    paper_id = f"inv_paper_{i+1}_{j+1}"
                    graph.add_node(EvidenceNode(
                        node_id=paper_id,
                        node_type=EvidenceNodeType.PAPER,
                        label=paper.title[:50],
                        content={"source": paper.source, "citations": paper.citation_count},
                        confidence_score=0.7 if paper.is_peer_reviewed else 0.4,
                    ))
                    graph.add_edge(EvidenceEdge(
                        source_id=paper_id,
                        target_id=claim_id,
                        edge_type=EvidenceEdgeType.SUPPORTS,
                        weight=0.7 if paper.is_peer_reviewed else 0.4,
                    ))

                # Add counter papers
                for j, paper in enumerate(claim.counter_papers):
                    counter_id = f"inv_counter_{i+1}_{j+1}"
                    graph.add_node(EvidenceNode(
                        node_id=counter_id,
                        node_type=EvidenceNodeType.COUNTER_PAPER,
                        label=paper.title[:50],
                        content={"source": paper.source, "citations": paper.citation_count},
                    ))
                    graph.add_edge(EvidenceEdge(
                        source_id=counter_id,
                        target_id=claim_id,
                        edge_type=EvidenceEdgeType.CONTRADICTS,
                        weight=0.6,
                    ))

        # Add provenance nodes
        if result.provenance:
            for node in result.provenance.nodes:
                # Prefix to avoid ID collision
                unified_id = f"prov_{node.node_id}"
                node_copy = EvidenceNode(
                    node_id=unified_id,
                    node_type=node.node_type,
                    label=node.label,
                    content=node.content,
                    receipt_hash=node.receipt_hash,
                    timestamp=node.timestamp,
                    confidence_score=node.confidence_score,
                    risk_score=node.risk_score,
                    collateral_score=node.collateral_score,
                    rights_or_license=node.rights_or_license,
                )
                graph.add_node(node_copy)

            # Add provenance edges (with prefixed IDs)
            for edge in result.provenance.edges:
                graph.add_edge(EvidenceEdge(
                    source_id=f"prov_{edge.source_id}",
                    target_id=f"prov_{edge.target_id}",
                    edge_type=edge.edge_type,
                    weight=edge.weight,
                    metadata=edge.metadata,
                ))

        # Link investigation to provenance (if both exist)
        if result.investigation and result.provenance:
            # The investigation DERIVES FROM the repository (it used the code)
            inv_receipt_id = f"inv_receipt_0"
            prov_repo_id = f"prov_repo_{result.provenance.repo_name}"
            if prov_repo_id in graph._nodes:
                graph.add_edge(EvidenceEdge(
                    source_id=inv_receipt_id,
                    target_id=prov_repo_id,
                    edge_type=EvidenceEdgeType.WAS_DERIVED_FROM,
                    weight=1.0,
                ))

        graph.finalize()
        return graph

    def _build_unified_manifest(self, result: EvidenceOSResult) -> EvidenceManifest:
        """Build a Merkle manifest across all artifacts."""
        manifest = EvidenceManifest(
            graph_hash=result.unified_graph.graph_hash if result.unified_graph else "",
        )

        # Add investigation artifacts
        if result.investigation:
            manifest.add_artifact(
                "investigation.json",
                json.dumps(result.investigation.to_dict(), sort_keys=True),
            )

        if result.mevf:
            manifest.add_artifact(
                "mevf_manifest.json",
                json.dumps(result.mevf.to_machine_manifest(), sort_keys=True),
            )

        # Add VideoLake bundle files
        if result.videolake_result:
            for filename, content in result.videolake_result.bundle.items():
                manifest.add_artifact(f"videolake/{filename}", content)

        # Add provenance
        if result.provenance:
            manifest.add_artifact(
                "provenance.json",
                json.dumps(result.provenance.to_dict(), sort_keys=True),
            )

        # Add unified graph
        if result.unified_graph:
            manifest.add_artifact(
                "unified_graph.json",
                json.dumps(result.unified_graph.to_dict(), sort_keys=True),
            )

        manifest.finalize()
        return manifest

    def _build_unified_receipts(self, result: EvidenceOSResult) -> EvidenceReceipt:
        """Build a unified receipt ledger chaining all actions."""
        ledger = EvidenceReceipt()

        ledger.create("evidenceos_started", f"Question: {result.question}")

        if result.investigation:
            ledger.create(
                "investigation_complete",
                f"{len(result.investigation.claims)} claims, {len(result.investigation.papers)} papers",
                {"receipt": result.investigation.receipt_hash},
            )

        if result.mevf:
            ledger.create(
                "mevf_built",
                f"{len(result.mevf.segments)} segments, grade {result.mevf.trust_grade}",
                {"receipt": result.mevf.receipt_hash},
            )

        if result.vrap:
            ledger.create(
                "vrap_built",
                f"Asset packet: {result.vrap.asset_type}",
                {"receipt": result.vrap.receipt_hash},
            )

        if result.provenance:
            ledger.create(
                "provenance_scanned",
                f"{result.provenance.node_count} nodes, {result.provenance.edge_count} edges",
                {"graph_hash": result.provenance.graph_hash},
            )

        if result.unified_graph:
            ledger.create(
                "unified_graph_built",
                f"{result.unified_graph.node_count} unified nodes",
                {"graph_hash": result.unified_graph.graph_hash},
            )

        if result.unified_manifest:
            ledger.create(
                "manifest_built",
                f"{result.unified_manifest.artifact_count} artifacts, Merkle root: {result.unified_manifest.merkle_root}",
                {"manifest_hash": result.unified_manifest.manifest_hash},
            )

        return ledger

    def _compute_unified_scores(self, result: EvidenceOSResult) -> UnifiedScores:
        """Compute unified scores across investigation + provenance."""
        scores = UnifiedScores()

        # Confidence: from investigation claims
        if result.investigation and result.investigation.claims:
            scores.confidence_score = sum(
                c.confidence for c in result.investigation.claims
            ) / len(result.investigation.claims)

        # Risk: from provenance
        if result.provenance:
            scores.risk_score = result.provenance.overall_risk_score
        else:
            scores.risk_score = 0.1  # Low risk without repo

        # Collateral: from provenance
        if result.provenance:
            scores.collateral_score = result.provenance.collateral_score
        else:
            scores.collateral_score = 0.3  # Base collateral from investigation

        # Rights safety: from MEVF
        if result.mevf and result.mevf.segments:
            safe_count = sum(1 for s in result.mevf.segments if s.rights_status == "safe")
            scores.rights_safety = safe_count / len(result.mevf.segments)

        # Provenance completeness: from unified graph
        if result.unified_manifest:
            scores.provenance_completeness = min(1.0, result.unified_manifest.artifact_count / 10.0)

        # Machine buyability: composite
        if result.mevf:
            scores.machine_buyability = result.mevf.avg_machine_buyability

        return scores

    def _encode_packet(self, result: EvidenceOSResult) -> str:
        """Encode the full EvidenceOS result as a Base64 packet."""
        packet = {
            "packet_type": "evidenceos_unified_packet_v1",
            "timestamp": time.time(),
            "question": result.question,
            "scores": result.scores.to_dict() if result.scores else {},
            "unified_graph": result.unified_graph.to_dict() if result.unified_graph else {},
            "manifest": result.unified_manifest.to_dict() if result.unified_manifest else {},
            "receipts": result.unified_receipt.entries if result.unified_receipt else [],
            "receipt_chain_valid": result.unified_receipt.verify_chain() if result.unified_receipt else False,
            "videolake_bundle": {
                filename: base64.b64encode(content.encode()).decode("utf-8")
                for filename, content in (result.videolake_result.bundle.items() if result.videolake_result else {})
            },
            "provenance": result.provenance.to_dict() if result.provenance else None,
        }

        packet["packet_hash"] = f"sha256:{hashlib.sha256(
            json.dumps(packet, sort_keys=True).encode()
        ).hexdigest()[:16]}"

        packet_json = json.dumps(packet, indent=2)
        return base64.b64encode(packet_json.encode()).decode("utf-8")

    def _compute_final_receipt(self, result: EvidenceOSResult) -> str:
        """Compute the final receipt hash for the entire compilation."""
        data = {
            "question": result.question,
            "timestamp": result.timestamp,
            "investigation_receipt": result.investigation.receipt_hash if result.investigation else "",
            "mevf_receipt": result.mevf.receipt_hash if result.mevf else "",
            "vrap_receipt": result.vrap.receipt_hash if result.vrap else "",
            "provenance_hash": result.provenance.graph_hash if result.provenance else "",
            "unified_graph_hash": result.unified_graph.graph_hash if result.unified_graph else "",
            "manifest_hash": result.unified_manifest.manifest_hash if result.unified_manifest else "",
            "receipt_chain_valid": result.unified_receipt.verify_chain() if result.unified_receipt else False,
            "packet_size": len(result.base64_packet),
        }
        return f"sha256:{hashlib.sha256(
            json.dumps(data, sort_keys=True).encode()
        ).hexdigest()[:16]}"

    def verify_packet(self, base64_packet: str) -> dict:
        """Verify a Base64 EvidenceOS packet."""
        try:
            packet_json = base64.b64decode(base64_packet).decode("utf-8")
            packet = json.loads(packet_json)
        except Exception as e:
            return {"valid": False, "error": f"Decode failed: {e}"}

        stored_hash = packet.pop("packet_hash", None)
        computed_hash = f"sha256:{hashlib.sha256(
            json.dumps(packet, sort_keys=True).encode()
        ).hexdigest()[:16]}"

        if stored_hash != computed_hash:
            return {"valid": False, "error": "Packet hash mismatch"}

        return {
            "valid": True,
            "packet_type": packet.get("packet_type"),
            "question": packet.get("question"),
            "scores": packet.get("scores"),
            "receipt_count": len(packet.get("receipts", [])),
            "receipt_chain_valid": packet.get("receipt_chain_valid"),
            "videolake_files": list(packet.get("videolake_bundle", {}).keys()),
            "has_provenance": packet.get("provenance") is not None,
            "manifest_artifacts": packet.get("manifest", {}).get("artifact_count", 0),
        }
