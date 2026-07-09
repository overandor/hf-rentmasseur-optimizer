"""
Evidence Graph Core — Shared kernel for research claims and software provenance.

A research claim and a software artifact are both evidence-bearing objects.

For a research claim:
    Who said it? What paper supports it? What counterclaim disputes it?
    Was it reproduced? What visual evidence illustrates it? What is the confidence?

For a software artifact:
    Who authored it? What commit introduced it? What dependencies does it use?
    Was it built? Was it signed? What receipt proves it? What risk does it carry?

Same graph grammar.

Shared schema:
    entity, activity, agent, claim, evidence, counter_evidence,
    receipt_hash, graph_hash, previous_graph_hash,
    rights_or_license, risk_score, confidence_score, collateral_score

This module provides the shared kernel used by both:
    investigation_graph.py (research specialization)
    provenance_graph.py (software specialization)

Standards: W3C PROV, RO-Crate, SLSA, Sigstore/Rekor, FAIR
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class EvidenceNodeType(Enum):
    """Shared node types for both research and software evidence."""
    # Research
    CLAIM = "claim"
    PAPER = "paper"
    COUNTER_PAPER = "counter_paper"
    EXPERIMENT = "experiment"
    VISUAL_SEGMENT = "visual_segment"
    # Software
    REPOSITORY = "repository"
    SNAPSHOT = "snapshot"
    FILE = "file"
    COMMIT = "commit"
    CONTRIBUTOR = "contributor"
    DEPENDENCY = "dependency"
    LICENSE = "license"
    SECRET = "secret"
    BUILD_ARTIFACT = "build_artifact"
    # Shared
    AGENT = "agent"
    ACTIVITY = "activity"
    RECEIPT = "receipt"
    MANIFEST = "manifest"


class EvidenceEdgeType(Enum):
    """Shared edge types for both research and software evidence."""
    # Research
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    ILLUSTRATES = "illustrates"
    PROVES = "proves"
    REPRODUCES = "reproduces"
    # Software
    CONTAINS = "contains"
    HAS_COMMIT = "has_commit"
    AUTHORED = "authored"
    MODIFIED = "modified"
    DEPENDS_ON = "depends_on"
    HAS_SECRET = "has_secret"
    HAS_LICENSE = "has_license"
    GENERATED_BY = "generated_by"
    ATTESTS = "attests"
    ARCHIVED_ON = "archived_on"
    ANCHORED_ON = "anchored_on"
    EVOLVED_FROM = "evolved_from"
    # Shared
    DERIVES = "derives"
    USED = "used"
    WAS_GENERATED_BY = "was_generated_by"
    WAS_DERIVED_FROM = "was_derived_from"


@dataclass
class EvidenceNode:
    """
    A node in the evidence graph.

    Shared between research claims and software artifacts.
    """
    node_id: str = ""
    node_type: EvidenceNodeType = EvidenceNodeType.CLAIM
    label: str = ""
    content: dict = field(default_factory=dict)
    receipt_hash: str = ""
    timestamp: float = 0.0

    # Shared scoring
    confidence_score: float = 0.0
    risk_score: float = 0.0
    collateral_score: float = 0.0

    # Rights/license
    rights_or_license: str = ""

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type.value,
            "label": self.label,
            "content": self.content,
            "receipt_hash": self.receipt_hash,
            "timestamp": self.timestamp,
            "confidence_score": round(self.confidence_score, 3),
            "risk_score": round(self.risk_score, 3),
            "collateral_score": round(self.collateral_score, 3),
            "rights_or_license": self.rights_or_license,
        }

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of this node (excluding timestamp for determinism)."""
        d = self.to_dict()
        d.pop("timestamp", None)
        data = json.dumps(d, sort_keys=True)
        return f"sha256:{hashlib.sha256(data.encode()).hexdigest()[:16]}"


@dataclass
class EvidenceEdge:
    """
    An edge in the evidence graph connecting two nodes.
    """
    source_id: str = ""
    target_id: str = ""
    edge_type: EvidenceEdgeType = EvidenceEdgeType.SUPPORTS
    weight: float = 1.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "type": self.edge_type.value,
            "weight": round(self.weight, 3),
            "metadata": self.metadata,
        }


class EvidenceGraphCore:
    """
    Shared graph kernel for evidence-bearing objects.

    Used by both InvestigationGraph (research) and ProvenanceGraph (software).
    Provides:
        - Node/edge management
        - Deterministic graph hash
        - Previous graph hash chaining
        - Receipt generation
        - Manifest with Merkle root
        - Query API (by type, by relationship, by score)
        - Export (JSON, JSON-LD, Cypher)

    Usage:
        graph = EvidenceGraphCore()
        graph.add_node(EvidenceNode(node_id="c1", node_type=EvidenceNodeType.CLAIM, label="..."))
        graph.add_edge(EvidenceEdge(source_id="p1", target_id="c1", edge_type=EvidenceEdgeType.SUPPORTS))
        graph.finalize()  # compute graph hash
        print(graph.graph_hash)
    """

    def __init__(self, graph_id: str = ""):
        self.graph_id = graph_id or hashlib.sha256(
            str(time.time()).encode()
        ).hexdigest()[:16]
        self._nodes: dict[str, EvidenceNode] = {}
        self._edges: list[EvidenceEdge] = []
        self.graph_hash: str = ""
        self.previous_graph_hash: str = ""
        self.timestamp: float = time.time()
        self._receipts: list[dict] = []

    @property
    def nodes(self) -> list[EvidenceNode]:
        return list(self._nodes.values())

    @property
    def edges(self) -> list[EvidenceEdge]:
        return list(self._edges)

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return len(self._edges)

    def add_node(self, node: EvidenceNode) -> None:
        """Add a node to the graph."""
        if not node.timestamp:
            node.timestamp = time.time()
        if not node.receipt_hash:
            node.receipt_hash = node.compute_hash()
        self._nodes[node.node_id] = node

    def add_edge(self, edge: EvidenceEdge) -> None:
        """Add an edge to the graph."""
        self._edges.append(edge)

    def get_node(self, node_id: str) -> Optional[EvidenceNode]:
        return self._nodes.get(node_id)

    def get_neighbors(self, node_id: str, edge_type: EvidenceEdgeType | None = None) -> list[EvidenceNode]:
        """Get neighboring nodes connected to a node."""
        neighbor_ids = set()
        for edge in self._edges:
            if edge.source_id == node_id:
                if edge_type is None or edge.edge_type == edge_type:
                    neighbor_ids.add(edge.target_id)
            elif edge.target_id == node_id:
                if edge_type is None or edge.edge_type == edge_type:
                    neighbor_ids.add(edge.source_id)
        return [self._nodes[nid] for nid in neighbor_ids if nid in self._nodes]

    def get_nodes_by_type(self, node_type: EvidenceNodeType) -> list[EvidenceNode]:
        """Get all nodes of a specific type."""
        return [n for n in self._nodes.values() if n.node_type == node_type]

    def get_claims(self) -> list[EvidenceNode]:
        """Get all claim nodes."""
        return self.get_nodes_by_type(EvidenceNodeType.CLAIM)

    def get_supporting_evidence(self, claim_id: str) -> list[EvidenceNode]:
        """Get nodes that support a claim."""
        return self.get_neighbors(claim_id, EvidenceEdgeType.SUPPORTS)

    def get_counter_evidence(self, claim_id: str) -> list[EvidenceNode]:
        """Get nodes that contradict a claim."""
        return self.get_neighbors(claim_id, EvidenceEdgeType.CONTRADICTS)

    def compute_graph_hash(self) -> str:
        """
        Compute a deterministic hash of the entire graph.

        The hash is based on all node and edge content, sorted by ID.
        This makes the hash reproducible and tamper-evident.
        """
        sorted_nodes = sorted(
            [{k: v for k, v in n.to_dict().items() if k != "timestamp"} for n in self._nodes.values()],
            key=lambda x: x["node_id"]
        )
        sorted_edges = sorted(
            [e.to_dict() for e in self._edges],
            key=lambda x: (x["source"], x["target"], x["type"])
        )
        graph_data = {
            "graph_id": self.graph_id,
            "nodes": sorted_nodes,
            "edges": sorted_edges,
            "previous_graph_hash": self.previous_graph_hash,
        }
        data = json.dumps(graph_data, sort_keys=True)
        return f"sha256:{hashlib.sha256(data.encode()).hexdigest()[:16]}"

    def finalize(self) -> str:
        """Compute and store the graph hash. Call after all nodes/edges are added."""
        self.graph_hash = self.compute_graph_hash()
        return self.graph_hash

    def create_receipt(self, action: str, description: str = "") -> dict:
        """Create a receipt for an action on this graph."""
        receipt = {
            "receipt_id": hashlib.sha256(
                f"{self.graph_id}:{action}:{time.time()}".encode()
            ).hexdigest()[:16],
            "graph_id": self.graph_id,
            "graph_hash": self.graph_hash,
            "action": action,
            "description": description,
            "timestamp": time.time(),
        }
        receipt["receipt_hash"] = f"sha256:{hashlib.sha256(
            json.dumps(receipt, sort_keys=True).encode()
        ).hexdigest()[:16]}"
        self._receipts.append(receipt)
        return receipt

    @property
    def receipts(self) -> list[dict]:
        return list(self._receipts)

    def to_dict(self) -> dict:
        return {
            "graph_id": self.graph_id,
            "graph_hash": self.graph_hash,
            "previous_graph_hash": self.previous_graph_hash,
            "timestamp": self.timestamp,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges],
            "receipts": self._receipts,
        }

    def to_json_ld(self) -> dict:
        """Export as JSON-LD with W3C PROV context."""
        return {
            "@context": {
                "@vocab": "https://schema.org/",
                "prov": "https://www.w3.org/ns/prov#",
                "entity": "prov:Entity",
                "activity": "prov:Activity",
                "agent": "prov:Agent",
                "wasGeneratedBy": "prov:wasGeneratedBy",
                "wasDerivedFrom": "prov:wasDerivedFrom",
            },
            "@type": "Dataset",
            "@id": self.graph_id,
            "graph_hash": self.graph_hash,
            "previous_graph_hash": self.previous_graph_hash,
            "entities": [
                {"@id": n.node_id, "@type": n.node_type.value, "label": n.label}
                for n in self._nodes.values()
            ],
            "relationships": [
                {"@source": e.source_id, "@target": e.target_id, "@type": e.edge_type.value}
                for e in self._edges
            ],
        }

    def to_cypher(self) -> str:
        """Export as Neo4j Cypher statements."""
        lines = []
        for node in self._nodes.values():
            props = json.dumps(node.to_dict()).replace('"', '\\"')
            lines.append(
                f'CREATE (n:{node.node_type.value} {{id: "{node.node_id}", label: "{node.label}"}})'
            )
        for edge in self._edges:
            lines.append(
                f'MATCH (a {{id: "{edge.source_id}"}}), (b {{id: "{edge.target_id}"}}) '
                f'CREATE (a)-[:{edge.edge_type.value.upper()}]->(b)'
            )
        return ";\n".join(lines) + ";"

    def to_csv_edges(self) -> str:
        """Export edges as CSV for graph tools."""
        lines = ["source,target,type,weight"]
        for edge in self._edges:
            lines.append(f"{edge.source_id},{edge.target_id},{edge.edge_type.value},{edge.weight:.3f}")
        return "\n".join(lines)

    def stats(self) -> dict:
        """Graph statistics."""
        type_counts: dict[str, int] = {}
        for n in self._nodes.values():
            type_counts[n.node_type.value] = type_counts.get(n.node_type.value, 0) + 1

        edge_type_counts: dict[str, int] = {}
        for e in self._edges:
            edge_type_counts[e.edge_type.value] = edge_type_counts.get(e.edge_type.value, 0) + 1

        return {
            "graph_id": self.graph_id,
            "graph_hash": self.graph_hash,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "node_types": type_counts,
            "edge_types": edge_type_counts,
            "receipt_count": len(self._receipts),
        }


@dataclass
class MerkleNode:
    """A node in a Merkle tree."""
    hash: str = ""
    left: Optional["MerkleNode"] = None
    right: Optional["MerkleNode"] = None
    content_hash: str = ""  # For leaf nodes


class EvidenceManifest:
    """
    Recursive content-addressed manifest with Merkle root.

    SHA-256 hashes all artifacts, builds a Merkle tree across them,
    links to the previous manifest, and references receipt and graph hashes.

    This is the same design family as modern supply-chain attestation
    (Sigstore, SLSA, Rekor).

    Usage:
        manifest = EvidenceManifest(graph_hash="sha256:...")
        manifest.add_artifact("claims.jsonl", content="...")
        manifest.add_artifact("evidence.jsonld", content="...")
        root = manifest.compute_merkle_root()
        manifest.finalize()
        print(manifest.merkle_root)
        print(manifest.manifest_hash)
        assert manifest.verify()
    """

    def __init__(self, graph_hash: str = "", previous_manifest_hash: str = ""):
        self.manifest_id = hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]
        self.graph_hash = graph_hash
        self.previous_manifest_hash = previous_manifest_hash
        self.timestamp: float = time.time()
        self._artifacts: dict[str, str] = {}  # filename → sha256 hash
        self._contents: dict[str, str] = {}   # filename → actual content
        self.merkle_root: str = ""
        self.manifest_hash: str = ""
        self._merkle_tree: Optional[MerkleNode] = None

    def add_artifact(self, filename: str, content: str) -> str:
        """Add an artifact to the manifest. Returns its hash."""
        artifact_hash = f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"
        self._artifacts[filename] = artifact_hash
        self._contents[filename] = content
        return artifact_hash

    def compute_merkle_root(self) -> str:
        """
        Build a Merkle tree from all artifact hashes and compute the root.

        The tree is built bottom-up:
            1. Leaf nodes = SHA-256 of each artifact hash
            2. Internal nodes = SHA-256 of left + right child
            3. Root = top of tree
        """
        if not self._artifacts:
            return ""

        # Sort artifacts for determinism
        sorted_hashes = sorted(self._artifacts.values())

        # Build leaf nodes
        leaves: list[MerkleNode] = []
        for h in sorted_hashes:
            leaf_hash = hashlib.sha256(h.encode()).hexdigest()[:16]
            leaves.append(MerkleNode(hash=leaf_hash, content_hash=h))

        # Build tree bottom-up
        level = leaves
        while len(level) > 1:
            next_level: list[MerkleNode] = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else level[i]
                combined = left.hash + right.hash
                parent_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]
                parent = MerkleNode(hash=parent_hash, left=left, right=right)
                next_level.append(parent)
            level = next_level

        self._merkle_tree = level[0]
        self.merkle_root = f"sha256:{self._merkle_tree.hash}"
        return self.merkle_root

    def finalize(self) -> str:
        """Compute the manifest hash after all artifacts are added."""
        self.compute_merkle_root()
        manifest_data = {
            "manifest_id": self.manifest_id,
            "graph_hash": self.graph_hash,
            "previous_manifest_hash": self.previous_manifest_hash,
            "merkle_root": self.merkle_root,
            "artifacts": self._artifacts,
            "timestamp": self.timestamp,
        }
        self.manifest_hash = f"sha256:{hashlib.sha256(
            json.dumps(manifest_data, sort_keys=True).encode()
        ).hexdigest()[:16]}"
        return self.manifest_hash

    def verify(self) -> bool:
        """Verify manifest integrity: recompute Merkle root and check all hashes."""
        if not self._artifacts:
            return True

        # Recompute Merkle root
        sorted_hashes = sorted(self._artifacts.values())
        leaves = [
            hashlib.sha256(h.encode()).hexdigest()[:16]
            for h in sorted_hashes
        ]
        level = leaves
        while len(level) > 1:
            next_level = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else level[i]
                combined = left + right
                next_level.append(hashlib.sha256(combined.encode()).hexdigest()[:16])
            level = next_level
        computed_root = f"sha256:{level[0]}"

        if computed_root != self.merkle_root:
            return False

        # Verify each artifact hash matches content
        for filename, stored_hash in self._artifacts.items():
            content = self._contents.get(filename, "")
            computed = f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"
            if computed != stored_hash:
                return False

        return True

    def verify_artifact(self, filename: str, content: str) -> bool:
        """Verify a single artifact against its stored hash."""
        stored = self._artifacts.get(filename)
        if not stored:
            return False
        computed = f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"
        return stored == computed

    @property
    def artifact_count(self) -> int:
        return len(self._artifacts)

    @property
    def artifacts(self) -> dict[str, str]:
        return dict(self._artifacts)

    def to_dict(self) -> dict:
        return {
            "manifest_id": self.manifest_id,
            "manifest_hash": self.manifest_hash,
            "graph_hash": self.graph_hash,
            "previous_manifest_hash": self.previous_manifest_hash,
            "merkle_root": self.merkle_root,
            "artifact_count": self.artifact_count,
            "artifacts": self._artifacts,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


class EvidenceReceipt:
    """
    Tamper-evident receipt for evidence-bearing actions.

    Each receipt chains to the previous one via SHA-256.
    This is the same pattern used by Sigstore/Rekor transparency logs.

    Usage:
        receipt_ledger = EvidenceReceipt()
        r1 = receipt_ledger.create("investigation_started", "Question: ...")
        r2 = receipt_ledger.create("claim_verified", "Claim: ...")
        assert receipt_ledger.verify_chain()
    """

    def __init__(self):
        self._entries: list[dict] = []
        self._prev_hash: str = ""

    def create(self, action: str, description: str = "", data: dict | None = None) -> dict:
        """Create a new receipt entry chained to the previous one."""
        entry = {
            "index": len(self._entries),
            "action": action,
            "description": description,
            "data": data or {},
            "timestamp": time.time(),
            "prev_hash": self._prev_hash,
        }
        entry["hash"] = hashlib.sha256(
            json.dumps(entry, sort_keys=True).encode()
        ).hexdigest()[:16]
        self._prev_hash = entry["hash"]
        self._entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        """Verify the entire receipt chain is intact."""
        prev = ""
        for entry in self._entries:
            if entry["prev_hash"] != prev:
                return False
            # Recompute hash
            check = {k: v for k, v in entry.items() if k != "hash"}
            computed = hashlib.sha256(
                json.dumps(check, sort_keys=True).encode()
            ).hexdigest()[:16]
            if computed != entry["hash"]:
                return False
            prev = entry["hash"]
        return True

    @property
    def entries(self) -> list[dict]:
        return list(self._entries)

    @property
    def count(self) -> int:
        return len(self._entries)

    @property
    def latest_hash(self) -> str:
        return self._prev_hash

    def to_dict(self) -> dict:
        return {
            "entry_count": self.count,
            "chain_valid": self.verify_chain(),
            "latest_hash": self.latest_hash,
            "entries": self._entries,
        }
