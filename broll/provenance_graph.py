"""
Provenance Graph — Software provenance specialization of EvidenceGraphCore.

Turns a repository/system into a queryable provenance intelligence layer.

Node types: Repository, Snapshot, File, Commit, Contributor, Dependency,
            License, Secret, BuildArtifact, Receipt
Edge types: CONTAINS, HAS_COMMIT, AUTHORED, MODIFIED, DEPENDS_ON,
            HAS_SECRET, HAS_LICENSE, GENERATED_BY, ATTESTS,
            ARCHIVED_ON, ANCHORED_ON, EVOLVED_FROM

This is not "files in a folder." It is a knowledge graph you can interrogate.

Same graph grammar as investigation_graph.py — both are specializations
of EvidenceGraphCore.

Standards: W3C PROV, SLSA, Sigstore/Rekor, RO-Crate, SPDX
"""

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


@dataclass
class FileArtifact:
    """A file in a repository snapshot."""
    path: str = ""
    size: int = 0
    sha256: str = ""
    language: str = ""
    lines: int = 0

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256,
            "language": self.language,
            "lines": self.lines,
        }


@dataclass
class CommitRecord:
    """A git commit in the provenance graph."""
    commit_hash: str = ""
    author: str = ""
    message: str = ""
    timestamp: float = 0.0
    files_changed: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "commit_hash": self.commit_hash,
            "author": self.author,
            "message": self.message,
            "timestamp": self.timestamp,
            "files_changed": self.files_changed,
        }


@dataclass
class DependencyRecord:
    """A dependency in the provenance graph."""
    name: str = ""
    version: str = ""
    source: str = ""  # pypi, npm, etc.
    license: str = ""
    is_direct: bool = True

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "source": self.source,
            "license": self.license,
            "is_direct": self.is_direct,
        }


class ProvenanceGraph:
    """
    Software provenance graph — a queryable intelligence layer above evidence files.

    This is the ProvenanceOS specialization of EvidenceGraphCore.

    Usage:
        graph = ProvenanceGraph(repo_name="my-repo")
        graph.add_repository("my-repo", url="https://github.com/user/repo")
        graph.add_file("src/main.py", size=1024, sha256="abc123", language="python")
        graph.add_commit("abc123", author="alice", message="initial commit")
        graph.add_dependency("requests", version="2.28.0", license="Apache-2.0")
        graph.add_contributor("alice", email="alice@example.com")
        graph.finalize()
        print(graph.graph_hash)
        print(graph.stats)
    """

    def __init__(self, repo_name: str = ""):
        self._core = EvidenceGraphCore(
            graph_id=hashlib.sha256(
                f"provenance:{repo_name}:{time.time()}".encode()
            ).hexdigest()[:16]
        )
        self.repo_name = repo_name
        self._receipt_ledger = EvidenceReceipt()
        self._files: dict[str, FileArtifact] = {}
        self._commits: dict[str, CommitRecord] = {}
        self._dependencies: dict[str, DependencyRecord] = {}
        self._contributors: dict[str, str] = {}  # name → email
        self._secrets: list[str] = []  # detected secret patterns
        self._build_artifacts: list[str] = []
        self._manifest: Optional[EvidenceManifest] = None

    @property
    def graph_id(self) -> str:
        return self._core.graph_id

    @property
    def graph_hash(self) -> str:
        return self._core.graph_hash

    @property
    def nodes(self) -> list[EvidenceNode]:
        return self._core.nodes

    @property
    def edges(self) -> list[EvidenceEdge]:
        return self._core.edges

    @property
    def node_count(self) -> int:
        return self._core.node_count

    @property
    def edge_count(self) -> int:
        return self._core.edge_count

    @property
    def stats(self) -> dict:
        s = self._core.stats()
        s.update({
            "repo_name": self.repo_name,
            "files": len(self._files),
            "commits": len(self._commits),
            "dependencies": len(self._dependencies),
            "contributors": len(self._contributors),
            "secrets_detected": len(self._secrets),
            "build_artifacts": len(self._build_artifacts),
        })
        return s

    def add_repository(self, name: str, url: str = "") -> str:
        """Add a repository node."""
        node_id = f"repo_{name}"
        self._core.add_node(EvidenceNode(
            node_id=node_id,
            node_type=EvidenceNodeType.REPOSITORY,
            label=name,
            content={"url": url, "name": name},
            rights_or_license="",
        ))
        self._receipt_ledger.create("repository_added", f"Repository: {name}")
        return node_id

    def add_snapshot(self, snapshot_id: str, timestamp: float = 0.0) -> str:
        """Add a snapshot node."""
        node_id = f"snap_{snapshot_id}"
        self._core.add_node(EvidenceNode(
            node_id=node_id,
            node_type=EvidenceNodeType.SNAPSHOT,
            label=snapshot_id,
            content={"timestamp": timestamp or time.time()},
        ))
        # Link to repo
        repo_id = f"repo_{self.repo_name}"
        if repo_id in self._core._nodes:
            self._core.add_edge(EvidenceEdge(
                source_id=repo_id,
                target_id=node_id,
                edge_type=EvidenceEdgeType.CONTAINS,
            ))
        self._receipt_ledger.create("snapshot_added", f"Snapshot: {snapshot_id}")
        return node_id

    def add_file(
        self,
        path: str,
        size: int = 0,
        sha256: str = "",
        language: str = "",
        lines: int = 0,
    ) -> str:
        """Add a file node."""
        file_id = f"file_{path.replace('/', '_')}"
        artifact = FileArtifact(
            path=path, size=size, sha256=sha256,
            language=language, lines=lines,
        )
        self._files[path] = artifact

        self._core.add_node(EvidenceNode(
            node_id=file_id,
            node_type=EvidenceNodeType.FILE,
            label=path,
            content=artifact.to_dict(),
            risk_score=self._assess_file_risk(path, language),
        ))
        return file_id

    def add_commit(
        self,
        commit_hash: str,
        author: str = "",
        message: str = "",
        timestamp: float = 0.0,
        files_changed: list[str] | None = None,
    ) -> str:
        """Add a commit node."""
        node_id = f"commit_{commit_hash[:8]}"
        record = CommitRecord(
            commit_hash=commit_hash, author=author,
            message=message, timestamp=timestamp,
            files_changed=files_changed or [],
        )
        self._commits[commit_hash] = record

        self._core.add_node(EvidenceNode(
            node_id=node_id,
            node_type=EvidenceNodeType.COMMIT,
            label=commit_hash[:8],
            content=record.to_dict(),
        ))

        # Link author
        if author:
            contributor_id = self.add_contributor(author)
            self._core.add_edge(EvidenceEdge(
                source_id=contributor_id,
                target_id=node_id,
                edge_type=EvidenceEdgeType.AUTHORED,
            ))

        # Link changed files
        for filepath in files_changed or []:
            file_id = f"file_{filepath.replace('/', '_')}"
            if file_id in self._core._nodes:
                self._core.add_edge(EvidenceEdge(
                    source_id=node_id,
                    target_id=file_id,
                    edge_type=EvidenceEdgeType.MODIFIED,
                ))

        return node_id

    def add_dependency(
        self,
        name: str,
        version: str = "",
        source: str = "",
        license: str = "",
        is_direct: bool = True,
    ) -> str:
        """Add a dependency node."""
        node_id = f"dep_{name}"
        record = DependencyRecord(
            name=name, version=version, source=source,
            license=license, is_direct=is_direct,
        )
        self._dependencies[name] = record

        self._core.add_node(EvidenceNode(
            node_id=node_id,
            node_type=EvidenceNodeType.DEPENDENCY,
            label=f"{name}@{version}",
            content=record.to_dict(),
            rights_or_license=license,
            risk_score=self._assess_dependency_risk(name, license),
        ))

        # Link to repo
        repo_id = f"repo_{self.repo_name}"
        if repo_id in self._core._nodes:
            self._core.add_edge(EvidenceEdge(
                source_id=repo_id,
                target_id=node_id,
                edge_type=EvidenceEdgeType.DEPENDS_ON,
            ))

        return node_id

    def add_contributor(self, name: str, email: str = "") -> str:
        """Add a contributor node."""
        node_id = f"contrib_{name}"
        if name not in self._contributors:
            self._contributors[name] = email
            self._core.add_node(EvidenceNode(
                node_id=node_id,
                node_type=EvidenceNodeType.CONTRIBUTOR,
                label=name,
                content={"email": email, "name": name},
            ))
        return node_id

    def add_license(self, license_type: str, file_path: str = "") -> str:
        """Add a license node."""
        node_id = f"license_{license_type}"
        self._core.add_node(EvidenceNode(
            node_id=node_id,
            node_type=EvidenceNodeType.LICENSE,
            label=license_type,
            content={"type": license_type, "file": file_path},
            rights_or_license=license_type,
        ))

        # Link to repo
        repo_id = f"repo_{self.repo_name}"
        if repo_id in self._core._nodes:
            self._core.add_edge(EvidenceEdge(
                source_id=repo_id,
                target_id=node_id,
                edge_type=EvidenceEdgeType.HAS_LICENSE,
            ))

        return node_id

    def add_secret(self, pattern_type: str, file_path: str = "") -> str:
        """Add a detected secret node."""
        node_id = f"secret_{len(self._secrets)}"
        self._secrets.append(pattern_type)

        self._core.add_node(EvidenceNode(
            node_id=node_id,
            node_type=EvidenceNodeType.SECRET,
            label=f"Secret: {pattern_type}",
            content={"type": pattern_type, "file": file_path},
            risk_score=1.0,  # Secrets are maximum risk
        ))

        # Link to file
        if file_path:
            file_id = f"file_{file_path.replace('/', '_')}"
            if file_id in self._core._nodes:
                self._core.add_edge(EvidenceEdge(
                    source_id=file_id,
                    target_id=node_id,
                    edge_type=EvidenceEdgeType.HAS_SECRET,
                ))

        return node_id

    def add_build_artifact(
        self,
        name: str,
        artifact_type: str = "",
        sha256: str = "",
    ) -> str:
        """Add a build artifact node."""
        node_id = f"build_{name}"
        self._build_artifacts.append(name)

        self._core.add_node(EvidenceNode(
            node_id=node_id,
            node_type=EvidenceNodeType.BUILD_ARTIFACT,
            label=name,
            content={"type": artifact_type, "sha256": sha256},
        ))

        # Link to repo (generated by)
        repo_id = f"repo_{self.repo_name}"
        if repo_id in self._core._nodes:
            self._core.add_edge(EvidenceEdge(
                source_id=node_id,
                target_id=repo_id,
                edge_type=EvidenceEdgeType.GENERATED_BY,
            ))

        return node_id

    def add_receipt_node(self, receipt_hash: str, action: str = "") -> str:
        """Add a receipt node to the graph."""
        node_id = f"receipt_{receipt_hash[:8]}"
        self._core.add_node(EvidenceNode(
            node_id=node_id,
            node_type=EvidenceNodeType.RECEIPT,
            label=f"Receipt: {action}",
            content={"hash": receipt_hash, "action": action},
            receipt_hash=receipt_hash,
        ))
        return node_id

    def link_evolution(self, from_snapshot: str, to_snapshot: str) -> None:
        """Link two snapshots showing evolution."""
        from_id = f"snap_{from_snapshot}"
        to_id = f"snap_{to_snapshot}"
        self._core.add_edge(EvidenceEdge(
            source_id=to_id,
            target_id=from_id,
            edge_type=EvidenceEdgeType.EVOLVED_FROM,
        ))

    def _assess_file_risk(self, path: str, language: str) -> float:
        """Assess risk score for a file (0.0 = safe, 1.0 = high risk)."""
        risk = 0.0
        if any(s in path.lower() for s in ["secret", "key", "token", "password", "credential"]):
            risk = 0.8
        if any(s in path.lower() for s in ["config", "env", ".env"]):
            risk = max(risk, 0.5)
        return risk

    def _assess_dependency_risk(self, name: str, license: str) -> float:
        """Assess risk score for a dependency."""
        risk = 0.1  # Base risk
        if not license:
            risk = 0.4  # No license = risky
        if license in ("GPL-3.0", "AGPL-3.0"):
            risk = max(risk, 0.3)  # Copyleft risk
        return risk

    @property
    def overall_risk_score(self) -> float:
        """Compute overall risk score for the repository."""
        if not self._core.nodes:
            return 0.0
        risks = [n.risk_score for n in self._core.nodes if n.risk_score > 0]
        if not risks:
            return 0.0
        return sum(risks) / len(risks)

    @property
    def collateral_score(self) -> float:
        """
        Compute collateral score — how valuable this repo is as evidence.

        Based on: has license, has contributors, has build artifacts,
        has receipts, low risk, has dependencies documented.
        """
        score = 0.0
        if self._contributors:
            score += 0.15
        if any(n.node_type == EvidenceNodeType.LICENSE for n in self._core.nodes):
            score += 0.15
        if self._build_artifacts:
            score += 0.15
        if self._core.receipts:
            score += 0.15
        if self._dependencies:
            score += 0.10
        if self._files:
            score += 0.10
        if self._commits:
            score += 0.10
        if self.overall_risk_score < 0.3:
            score += 0.10
        return min(1.0, score)

    def finalize(self) -> str:
        """Compute graph hash and create final receipt."""
        self._core.finalize()
        self._receipt_ledger.create(
            "graph_finalized",
            f"Provenance graph: {self.node_count} nodes, {self.edge_count} edges",
            {"graph_hash": self.graph_hash},
        )
        return self.graph_hash

    def build_manifest(self, previous_manifest_hash: str = "") -> EvidenceManifest:
        """Build a content-addressed manifest with Merkle root."""
        manifest = EvidenceManifest(
            graph_hash=self.graph_hash,
            previous_manifest_hash=previous_manifest_hash,
        )

        # Add all node contents as artifacts
        for node in self._core.nodes:
            manifest.add_artifact(
                f"nodes/{node.node_id}.json",
                json.dumps(node.to_dict(), sort_keys=True),
            )

        # Add edges
        manifest.add_artifact(
            "edges.csv",
            self._core.to_csv_edges(),
        )

        # Add graph summary
        manifest.add_artifact(
            "graph_summary.json",
            json.dumps(self.stats, sort_keys=True),
        )

        manifest.finalize()
        self._manifest = manifest
        return manifest

    @property
    def manifest(self) -> Optional[EvidenceManifest]:
        return self._manifest

    @property
    def receipt_ledger(self) -> EvidenceReceipt:
        return self._receipt_ledger

    def to_dict(self) -> dict:
        return {
            "repo_name": self.repo_name,
            "graph": self._core.to_dict(),
            "stats": self.stats,
            "overall_risk_score": round(self.overall_risk_score, 3),
            "collateral_score": round(self.collateral_score, 3),
            "receipt_chain_valid": self._receipt_ledger.verify_chain(),
            "manifest": self._manifest.to_dict() if self._manifest else None,
        }

    def to_json_ld(self) -> dict:
        """Export as JSON-LD with W3C PROV + SLSA context."""
        ld = self._core.to_json_ld()
        ld["@context"].update({
            "slsa": "https://slsa.dev/spec/v1.0/provenance",
            "buildType": "slsa:buildType",
            "materials": "slsa:materials",
        })
        ld["repo_name"] = self.repo_name
        ld["risk_score"] = round(self.overall_risk_score, 3)
        ld["collateral_score"] = round(self.collateral_score, 3)
        return ld

    def to_cypher(self) -> str:
        """Export as Neo4j Cypher statements."""
        return self._core.to_cypher()

    def query(self, node_type: str | None = None, min_confidence: float = 0.0,
              max_risk: float = 1.0) -> list[EvidenceNode]:
        """Query nodes by type and score thresholds."""
        results = []
        for node in self._core.nodes:
            if node_type and node.node_type.value != node_type:
                continue
            if node.confidence_score < min_confidence:
                continue
            if node.risk_score > max_risk:
                continue
            results.append(node)
        return results
