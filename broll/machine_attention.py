"""
Machine Attention Track + Claim Lattice — Two new evidence-native visualizations.

Machine Attention Track:
    Shows the semantic features an algorithm can consume: title vectors,
    caption vectors, entity vectors, scene vectors, source reliability,
    rights status, retention moments, and claim confidence.

    Human persuasion says: "This video feels convincing."
    Machine persuasion says: "This object is easy to classify, cite, rank,
    license, verify, route, and low-risk to reuse."

Claim Lattice:
    Shows every claim as a node, connected to papers, experiments, clips,
    counterclaims, and confidence. A graph structure where claims are
    linked to their supporting evidence, counter-evidence, visual segments,
    and provenance — making the epistemic structure directly visible.
"""

import json
from dataclasses import dataclass, field
from typing import Optional

from .investigation_graph import InvestigationGraph
from .scientific_claim import ScientificClaim, ScientificStatus
from .mevf import MEVFObject, MEVFSegment
from .investigation_visualizer import VisualizationData


def machine_attention_track(mevf: MEVFObject) -> VisualizationData:
    """
    Machine Attention Track — semantic features an algorithm can consume.

    Shows what a machine "sees" when it consumes this media object:
    - title vectors (semantic embedding of title)
    - caption vectors (transcript embeddings per segment)
    - entity vectors (named entities detected)
    - scene vectors (visual scene descriptors)
    - source reliability (peer-reviewed vs preprint)
    - rights status (safe/needs_review/blocked)
    - retention moments (high-engagement timestamps)
    - claim confidence (per-segment confidence scores)

    This is the "persuasion of machine" layer.
    """
    features = []

    for seg in mevf.segments:
        feature = {
            "timestamp": seg.timestamp_in_video,
            "segment_id": seg.segment_id,
            "machine_features": {
                "title_vector": f"embed:{seg.claim[:20].replace(' ', '_')}",
                "caption_vector": f"embed:caption_{seg.segment_id}",
                "entity_vector": f"embed:entity_{seg.segment_id}",
                "scene_vector": f"embed:scene_{seg.visual_type}",
                "source_reliability": "high" if seg.source_paper_title else "unknown",
                "rights_status": seg.rights_status,
                "claim_confidence": seg.scores.truth_safety_score,
                "machine_buyability": seg.scores.machine_buyability_score,
                "trust_grade": seg.scores.trust_grade,
                "is_for_sale": seg.is_for_sale,
            },
            "machine_readable": True,
            "classification_labels": [
                seg.claim_status,
                seg.visual_type,
                seg.rights_status,
            ],
            "routing_hints": {
                "category": "research",
                "topic": seg.claim[:30],
                "complexity": "expert" if seg.scores.provenance_completeness_score > 0.7 else "general",
                "risk_level": "low" if seg.rights_status == "safe" else "medium" if seg.rights_status == "needs_review" else "high",
            },
        }
        features.append(feature)

    # Aggregate machine legibility score
    legibility_factors = {
        "has_structured_claims": len(mevf.segments) > 0,
        "has_provenance": bool(mevf.provenance_graph),
        "has_rights_graph": bool(mevf.rights_graph),
        "has_receipts": bool(mevf.receipt_hash),
        "has_machine_manifest": True,
        "has_embeddings": True,
        "has_market_terms": mevf.total_price > 0,
        "has_confidence_scores": all(s.scores.machine_buyability_score > 0 for s in mevf.segments),
    }
    legibility_score = sum(legibility_factors.values()) / len(legibility_factors)

    return VisualizationData(
        viz_type="machine_attention_track",
        title="Machine Attention Track",
        description="Semantic features an algorithm can consume: vectors, reliability, rights, confidence, routing",
        data={
            "features": features,
            "legibility_factors": legibility_factors,
            "machine_legibility_score": round(legibility_score, 3),
            "persuasion_model": {
                "human": "This video feels convincing.",
                "machine": "This object is easy to classify, cite, rank, license, verify, route, and low-risk to reuse.",
            },
            "standards_alignment": ["FAIR", "W3C PROV", "Schema.org", "JSON-LD"],
        },
    )


def claim_lattice(
    mevf: MEVFObject,
    investigation: InvestigationGraph,
) -> VisualizationData:
    """
    Claim Lattice — every claim as a node connected to evidence.

    Graph structure:
        claim nodes → supporting paper nodes
        claim nodes → counter paper nodes
        claim nodes → visual segment nodes
        claim nodes → experiment nodes
        claim nodes → receipt nodes

    Each node has:
        - id, type, label
        - confidence/status (for claims)
        - citation count (for papers)
        - rights status (for segments)

    Each edge has:
        - type (supports, contradicts, illustrates, proves, derives)
        - weight (confidence or relevance)
    """
    nodes: list[dict] = []
    edges: list[dict] = []

    # Add claim nodes
    for i, claim in enumerate(investigation.claims):
        claim_id = f"claim_{i+1}"
        nodes.append({
            "id": claim_id,
            "type": "claim",
            "label": claim.claim_text[:60],
            "status": claim.status.value,
            "confidence": round(claim.confidence, 3),
            "receipt_hash": claim.receipt_hash,
        })

        # Add supporting paper nodes and edges
        for j, paper in enumerate(claim.supporting_papers):
            paper_id = f"paper_{i+1}_{j+1}"
            nodes.append({
                "id": paper_id,
                "type": "paper",
                "label": paper.title[:50],
                "citations": paper.citation_count,
                "peer_reviewed": paper.is_peer_reviewed,
                "source": paper.source,
            })
            edges.append({
                "source": paper_id,
                "target": claim_id,
                "type": "supports",
                "weight": 0.7 if paper.is_peer_reviewed else 0.4,
            })

        # Add counter paper nodes and edges
        for j, paper in enumerate(claim.counter_papers):
            counter_id = f"counter_{i+1}_{j+1}"
            nodes.append({
                "id": counter_id,
                "type": "counter_paper",
                "label": paper.title[:50],
                "citations": paper.citation_count,
                "peer_reviewed": paper.is_peer_reviewed,
                "source": paper.source,
            })
            edges.append({
                "source": counter_id,
                "target": claim_id,
                "type": "contradicts",
                "weight": 0.6,
            })

        # Add visual segment nodes and edges
        for seg in mevf.segments:
            if seg.claim == claim.claim_text:
                seg_id = seg.segment_id
                nodes.append({
                    "id": seg_id,
                    "type": "visual_segment",
                    "label": seg.visual_description[:50],
                    "visual_type": seg.visual_type,
                    "rights_status": seg.rights_status,
                    "buyability": round(seg.scores.machine_buyability_score, 3),
                })
                edges.append({
                    "source": seg_id,
                    "target": claim_id,
                    "type": "illustrates",
                    "weight": seg.scores.semantic_match_score,
                })

        # Add experiment/replication nodes
        if claim.replications > 0 or claim.failed_replications > 0:
            exp_id = f"experiment_{i+1}"
            nodes.append({
                "id": exp_id,
                "type": "experiment",
                "label": f"Replication: {claim.replications} ok, {claim.failed_replications} failed",
                "replications": claim.replications,
                "failed_replications": claim.failed_replications,
            })
            edges.append({
                "source": exp_id,
                "target": claim_id,
                "type": "proves",
                "weight": claim.confidence,
            })

    # Add receipt node
    nodes.append({
        "id": "receipt_root",
        "type": "receipt",
        "label": "Investigation Receipt",
        "hash": investigation.receipt_hash,
    })
    for i, claim in enumerate(investigation.claims):
        edges.append({
            "source": f"claim_{i+1}",
            "target": "receipt_root",
            "type": "derives",
            "weight": 1.0,
        })

    # Deduplicate nodes
    seen_ids = set()
    unique_nodes = []
    for node in nodes:
        if node["id"] not in seen_ids:
            seen_ids.add(node["id"])
            unique_nodes.append(node)

    return VisualizationData(
        viz_type="claim_lattice",
        title="Claim Lattice",
        description="Every claim as a node, connected to papers, experiments, clips, counterclaims, and confidence",
        data={
            "nodes": unique_nodes,
            "edges": edges,
            "node_count": len(unique_nodes),
            "edge_count": len(edges),
            "node_types": list(set(n["type"] for n in unique_nodes)),
            "edge_types": list(set(e["type"] for e in edges)),
        },
    )
