"""
SERL — Self-Evolving Runtime Ledger
MEMBRA — Intellectual Capital Operating System

A stateful patch-and-evidence operating system whose native primitive is:

    thought -> evidence -> artifact -> receipt -> valuation -> liquidity

Every state transition is an immutable ledger object with SHA-256 provenance.
The defensible moat is the growing causal graph, not the software.

State S(t) -> Observation -> Hypothesis -> Patch -> Simulation -> Benchmark -> Risk -> Approval -> Promotion -> State S(t+1)

Each transition links to its parent, creating a causal chain that cannot be
reproduced by anyone who did not live through the same sequence of decisions.
"""

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ─── Storage ─────────────────────────────────────────────────────────────────

STORAGE = Path(os.environ.get("SERL_STORAGE", "serl_data"))
STORAGE.mkdir(parents=True, exist_ok=True)

_DIRS = [
    "states", "patches", "benchmarks", "artifacts", "observations",
    "hypotheses", "memory", "receipts", "causal_edges", "valuations",
    "thoughts", "counterfactuals",
]
for d in _DIRS:
    (STORAGE / d).mkdir(exist_ok=True)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _save(obj_type: str, obj_id: str, data: dict) -> None:
    p = STORAGE / obj_type / f"{obj_id}.json"
    p.write_text(json.dumps(data, indent=2, default=str))


def _load(obj_type: str, obj_id: str) -> Optional[dict]:
    p = STORAGE / obj_type / f"{obj_id}.json"
    if not p.exists():
        return None
    return json.loads(p.read_text())


def _list(obj_type: str, limit: int = 50) -> List[dict]:
    d = STORAGE / obj_type
    if not d.exists():
        return []
    files = sorted(d.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    return [json.loads(f.read_text()) for f in files[:limit]]


def _chain_hash(parent_hash: str, data: dict) -> str:
    """Cryptographic chaining — each entry incorporates its parent's hash."""
    content = json.dumps(data, sort_keys=True, default=str)
    return _sha256(parent_hash + content)


# ─── Causal Edge ─────────────────────────────────────────────────────────────

class CausalEdge:
    """Records a causal relationship between two ledger objects.

    This is the core of the Personal Causal Ledger.
    Not 'what happened' but 'what caused what.'
    """

    @staticmethod
    def create(source_id: str, source_type: str, target_id: str, target_type: str,
               relation: str, evidence: Optional[dict] = None) -> dict:
        edge_id = f"edge_{int(time.time() * 1000)}"
        data = {
            "edge_id": edge_id,
            "source_id": source_id,
            "source_type": source_type,
            "target_id": target_id,
            "target_type": target_type,
            "relation": relation,
            "evidence": evidence or {},
            "timestamp": _utc_now(),
        }
        data["content_hash"] = _sha256(json.dumps(data, sort_keys=True, default=str))
        _save("causal_edges", edge_id, data)
        return data

    @staticmethod
    def from_object(obj_id: str) -> List[dict]:
        """Get all causal edges originating from an object."""
        return [e for e in _list("causal_edges", limit=500)
                if e["source_id"] == obj_id]

    @staticmethod
    def to_object(obj_id: str) -> List[dict]:
        """Get all causal edges pointing to an object."""
        return [e for e in _list("causal_edges", limit=500)
                if e["target_id"] == obj_id]

    @staticmethod
    def all_edges(limit: int = 200) -> List[dict]:
        return _list("causal_edges", limit=limit)


# ─── Core Ledger Objects ─────────────────────────────────────────────────────

class State:
    """A system state snapshot. S(t) in the transition model."""

    @staticmethod
    def create(parent_state_id: Optional[str], description: str,
               metadata: Optional[dict] = None) -> dict:
        state_id = f"state_{int(time.time() * 1000)}"
        parent = State.get(parent_state_id) if parent_state_id else None
        parent_hash = parent["chain_hash"] if parent else ""
        data = {
            "state_id": state_id,
            "parent_state": parent_state_id,
            "description": description,
            "metadata": metadata or {},
            "timestamp": _utc_now(),
        }
        data["chain_hash"] = _chain_hash(parent_hash, data)
        _save("states", state_id, data)
        return data

    @staticmethod
    def get(state_id: str) -> Optional[dict]:
        return _load("states", state_id)

    @staticmethod
    def current() -> Optional[dict]:
        states = _list("states", limit=1)
        return states[0] if states else None

    @staticmethod
    def history(limit: int = 50) -> List[dict]:
        return _list("states", limit=limit)


class Thought:
    """A thought — the atomic unit of intellectual production.

    Thoughts are the origin of the causal chain:
    thought -> evidence -> artifact -> receipt -> valuation
    """

    @staticmethod
    def create(content: str, thought_type: str = "idea",
               parent_thought_id: Optional[str] = None,
               context: Optional[dict] = None) -> dict:
        thought_id = f"thought_{int(time.time() * 1000)}"
        parent = Thought.get(parent_thought_id) if parent_thought_id else None
        parent_hash = parent["chain_hash"] if parent else ""
        data = {
            "thought_id": thought_id,
            "parent_thought": parent_thought_id,
            "content": content,
            "thought_type": thought_type,
            "context": context or {},
            "status": "raw",
            "timestamp": _utc_now(),
        }
        data["chain_hash"] = _chain_hash(parent_hash, data)
        _save("thoughts", thought_id, data)
        return data

    @staticmethod
    def get(thought_id: str) -> Optional[dict]:
        return _load("thoughts", thought_id)

    @staticmethod
    def list(limit: int = 50) -> List[dict]:
        return _list("thoughts", limit)

    @staticmethod
    def update_status(thought_id: str, status: str, **extra) -> dict:
        t = _load("thoughts", thought_id)
        if not t:
            raise ValueError(f"Thought {thought_id} not found")
        t["status"] = status
        t.update(extra)
        t["timestamp"] = _utc_now()
        t["chain_hash"] = _sha256(json.dumps(t, sort_keys=True, default=str))
        _save("thoughts", thought_id, t)
        return t


class Observation:
    """An observation about the system or external world."""

    @staticmethod
    def create(state_id: str, observation_type: str, data: dict) -> dict:
        obs_id = f"obs_{int(time.time() * 1000)}"
        entry = {
            "obs_id": obs_id,
            "state_id": state_id,
            "observation_type": observation_type,
            "data": data,
            "timestamp": _utc_now(),
        }
        entry["content_hash"] = _sha256(json.dumps(entry, sort_keys=True, default=str))
        _save("observations", obs_id, entry)
        CausalEdge.create(state_id, "state", obs_id, "observation", "observed")
        return entry

    @staticmethod
    def list(limit: int = 50) -> List[dict]:
        return _list("observations", limit)


class Hypothesis:
    """A hypothesis generated from observations."""

    @staticmethod
    def create(obs_id: str, hypothesis: str, confidence: float = 0.0) -> dict:
        hyp_id = f"hyp_{int(time.time() * 1000)}"
        data = {
            "hyp_id": hyp_id,
            "observation_id": obs_id,
            "hypothesis": hypothesis,
            "confidence": confidence,
            "status": "untested",
            "timestamp": _utc_now(),
        }
        data["content_hash"] = _sha256(json.dumps(data, sort_keys=True, default=str))
        _save("hypotheses", hyp_id, data)
        CausalEdge.create(obs_id, "observation", hyp_id, "hypothesis", "hypothesized")
        return data

    @staticmethod
    def list(limit: int = 50) -> List[dict]:
        return _list("hypotheses", limit)

    @staticmethod
    def update_status(hyp_id: str, status: str, **extra) -> dict:
        h = _load("hypotheses", hyp_id)
        if not h:
            raise ValueError(f"Hypothesis {hyp_id} not found")
        h["status"] = status
        h.update(extra)
        h["timestamp"] = _utc_now()
        _save("hypotheses", hyp_id, h)
        return h


class Patch:
    """A proposed modification to the system."""

    @staticmethod
    def create(parent_state_id: str, target_file: str, description: str,
               sha_before: str = "", patch_content: str = "",
               risk_score: float = 0.0,
               source_hypothesis_id: Optional[str] = None) -> dict:
        patch_id = f"patch_{int(time.time() * 1000)}"
        data = {
            "patch_id": patch_id,
            "parent_state": parent_state_id,
            "target_file": target_file,
            "description": description,
            "sha_before": sha_before,
            "sha_after": _sha256(patch_content) if patch_content else "",
            "patch_content": patch_content,
            "risk_score": risk_score,
            "status": "proposed",
            "benchmark_id": None,
            "source_hypothesis": source_hypothesis_id,
            "timestamp": _utc_now(),
        }
        data["content_hash"] = _sha256(json.dumps(data, sort_keys=True, default=str))
        _save("patches", patch_id, data)
        CausalEdge.create(parent_state_id, "state", patch_id, "patch", "proposed")
        if source_hypothesis_id:
            CausalEdge.create(source_hypothesis_id, "hypothesis", patch_id, "patch", "generated")
        return data

    @staticmethod
    def get(patch_id: str) -> Optional[dict]:
        return _load("patches", patch_id)

    @staticmethod
    def list(limit: int = 50) -> List[dict]:
        return _list("patches", limit)

    @staticmethod
    def update_status(patch_id: str, status: str, **extra) -> dict:
        p = _load("patches", patch_id)
        if not p:
            raise ValueError(f"Patch {patch_id} not found")
        p["status"] = status
        p.update(extra)
        p["timestamp"] = _utc_now()
        p["content_hash"] = _sha256(json.dumps(p, sort_keys=True, default=str))
        _save("patches", patch_id, p)
        return p


class Benchmark:
    """A benchmark run against a patch or state."""

    @staticmethod
    def create(target_id: str, target_type: str, metrics: dict) -> dict:
        bench_id = f"bench_{int(time.time() * 1000)}"
        data = {
            "bench_id": bench_id,
            "target_id": target_id,
            "target_type": target_type,
            "metrics": metrics,
            "timestamp": _utc_now(),
        }
        data["content_hash"] = _sha256(json.dumps(data, sort_keys=True, default=str))
        _save("benchmarks", bench_id, data)
        CausalEdge.create(target_id, target_type, bench_id, "benchmark", "measured")
        return data

    @staticmethod
    def get(bench_id: str) -> Optional[dict]:
        return _load("benchmarks", bench_id)

    @staticmethod
    def list(limit: int = 50) -> List[dict]:
        return _list("benchmarks", limit)


class Artifact:
    """A build artifact or output — every file becomes a live-priced instrument."""

    @staticmethod
    def create(artifact_type: str, content: dict,
               metadata: Optional[dict] = None,
               source_patch_id: Optional[str] = None) -> dict:
        artifact_id = f"artifact_{int(time.time() * 1000)}"
        data = {
            "artifact_id": artifact_id,
            "artifact_type": artifact_type,
            "content": content,
            "metadata": metadata or {},
            "source_patch": source_patch_id,
            "timestamp": _utc_now(),
            "content_hash": _sha256(json.dumps(content, sort_keys=True, default=str)),
        }
        _save("artifacts", artifact_id, data)
        if source_patch_id:
            CausalEdge.create(source_patch_id, "patch", artifact_id, "artifact", "produced")
        return data

    @staticmethod
    def get(artifact_id: str) -> Optional[dict]:
        return _load("artifacts", artifact_id)

    @staticmethod
    def list(limit: int = 50) -> List[dict]:
        return _list("artifacts", limit)


class Counterfactual:
    """A rejected idea, abandoned branch, or failed hypothesis.

    The Time Machine for Research — stores paths NOT taken.
    """

    @staticmethod
    def create(description: str, parent_id: str, parent_type: str,
               reason: str, counterfactual_type: str = "abandoned") -> dict:
        cf_id = f"cf_{int(time.time() * 1000)}"
        data = {
            "cf_id": cf_id,
            "description": description,
            "parent_id": parent_id,
            "parent_type": parent_type,
            "reason": reason,
            "counterfactual_type": counterfactual_type,
            "timestamp": _utc_now(),
        }
        data["content_hash"] = _sha256(json.dumps(data, sort_keys=True, default=str))
        _save("counterfactuals", cf_id, data)
        CausalEdge.create(parent_id, parent_type, cf_id, "counterfactual", "rejected")
        return data

    @staticmethod
    def list(limit: int = 50) -> List[dict]:
        return _list("counterfactuals", limit)

    @staticmethod
    def search(query: str, limit: int = 20) -> List[dict]:
        results = []
        for cf in _list("counterfactuals", limit=500):
            if query.lower() in cf.get("description", "").lower() or \
               query.lower() in cf.get("reason", "").lower():
                results.append(cf)
                if len(results) >= limit:
                    break
        return results


class Memory:
    """Persistent memory store — sticky notes, not law."""

    @staticmethod
    def store(key: str, value: Any, tags: Optional[List[str]] = None) -> dict:
        mem_id = f"mem_{int(time.time() * 1000)}"
        data = {
            "mem_id": mem_id,
            "key": key,
            "value": value,
            "tags": tags or [],
            "timestamp": _utc_now(),
        }
        _save("memory", mem_id, data)
        return data

    @staticmethod
    def search(query: str, limit: int = 20) -> List[dict]:
        results = []
        for f in (STORAGE / "memory").glob("*.json"):
            entry = json.loads(f.read_text())
            if query.lower() in entry.get("key", "").lower() or \
               query.lower() in str(entry.get("value", "")).lower() or \
               any(query.lower() in t.lower() for t in entry.get("tags", [])):
                results.append(entry)
            if len(results) >= limit:
                break
        return results


class Receipt:
    """Immutable evidence receipt for a transition.

    No receipt = artifact doesn't exist.
    Every transition must produce a receipt.
    """

    @staticmethod
    def create(object_type: str, object_id: str, evidence: dict) -> dict:
        receipt_id = f"receipt_{_sha256(object_type + object_id + _utc_now())[:12]}"
        data = {
            "receipt_id": receipt_id,
            "object_type": object_type,
            "object_id": object_id,
            "evidence": evidence,
            "timestamp": _utc_now(),
            "content_hash": _sha256(json.dumps(evidence, sort_keys=True, default=str)),
        }
        _save("receipts", receipt_id, data)
        return data

    @staticmethod
    def get(receipt_id: str) -> Optional[dict]:
        return _load("receipts", receipt_id)

    @staticmethod
    def list(limit: int = 50) -> List[dict]:
        return _list("receipts", limit)


# ─── IP Valuation Engine ─────────────────────────────────────────────────────

class Valuation:
    """Self-Valuing IP Market — continuous estimation for every artifact.

    Estimates four value types:
    - liquidation_value: fire-sale price
    - replacement_cost: cost to recreate from scratch
    - licensing_value: annual licensing revenue potential
    - acquisition_value: strategic acquisition premium
    """

    @staticmethod
    def create(artifact_id: str, valuations: dict,
               methodology: str = "heuristic_v1") -> dict:
        val_id = f"val_{int(time.time() * 1000)}"
        data = {
            "val_id": val_id,
            "artifact_id": artifact_id,
            "valuations": valuations,
            "methodology": methodology,
            "timestamp": _utc_now(),
        }
        data["content_hash"] = _sha256(json.dumps(data, sort_keys=True, default=str))
        _save("valuations", val_id, data)
        CausalEdge.create(artifact_id, "artifact", val_id, "valuation", "valued")
        return data

    @staticmethod
    def for_artifact(artifact_id: str) -> List[dict]:
        return [v for v in _list("valuations", limit=200)
                if v["artifact_id"] == artifact_id]

    @staticmethod
    def list(limit: int = 50) -> List[dict]:
        return _list("valuations", limit)

    @staticmethod
    def estimate_heuristic(artifact_type: str, content_size: int,
                           causal_depth: int, receipt_count: int) -> dict:
        """Rough heuristic valuation based on artifact properties.

        causal_depth = how many causal edges link to this artifact
        receipt_count = how many verified receipts exist
        """
        base = max(content_size / 1024, 1.0)
        provenance_multiplier = 1.0 + (causal_depth * 0.1) + (receipt_count * 0.05)
        return {
            "liquidation_value": round(base * 0.1 * provenance_multiplier, 2),
            "replacement_cost": round(base * 10 * provenance_multiplier, 2),
            "licensing_value": round(base * 2 * provenance_multiplier, 2),
            "acquisition_value": round(base * 5 * provenance_multiplier, 2),
            "provenance_multiplier": round(provenance_multiplier, 3),
            "causal_depth": causal_depth,
            "receipt_count": receipt_count,
        }


# ─── Causal Graph Query ──────────────────────────────────────────────────────

class CausalGraph:
    """Query the causal graph — the core of the Personal Causal Ledger."""

    @staticmethod
    def ancestors(obj_id: str, depth: int = 10) -> List[dict]:
        """Trace causal ancestry of an object."""
        results = []
        seen = set()
        queue = [(obj_id, 0)]
        while queue:
            current_id, current_depth = queue.pop(0)
            if current_depth >= depth or current_id in seen:
                continue
            seen.add(current_id)
            edges = CausalEdge.to_object(current_id)
            for e in edges:
                results.append({
                    "edge": e,
                    "depth": current_depth,
                })
                queue.append((e["source_id"], current_depth + 1))
        return results

    @staticmethod
    def descendants(obj_id: str, depth: int = 10) -> List[dict]:
        """Trace causal descendants of an object."""
        results = []
        seen = set()
        queue = [(obj_id, 0)]
        while queue:
            current_id, current_depth = queue.pop(0)
            if current_depth >= depth or current_id in seen:
                continue
            seen.add(current_id)
            edges = CausalEdge.from_object(current_id)
            for e in edges:
                results.append({
                    "edge": e,
                    "depth": current_depth,
                })
                queue.append((e["target_id"], current_depth + 1))
        return results

    @staticmethod
    def stats() -> dict:
        """Summary statistics for the entire causal graph."""
        return {
            "states": len(list((STORAGE / "states").glob("*.json"))),
            "thoughts": len(list((STORAGE / "thoughts").glob("*.json"))),
            "observations": len(list((STORAGE / "observations").glob("*.json"))),
            "hypotheses": len(list((STORAGE / "hypotheses").glob("*.json"))),
            "patches": len(list((STORAGE / "patches").glob("*.json"))),
            "benchmarks": len(list((STORAGE / "benchmarks").glob("*.json"))),
            "artifacts": len(list((STORAGE / "artifacts").glob("*.json"))),
            "counterfactuals": len(list((STORAGE / "counterfactuals").glob("*.json"))),
            "causal_edges": len(list((STORAGE / "causal_edges").glob("*.json"))),
            "valuations": len(list((STORAGE / "valuations").glob("*.json"))),
            "receipts": len(list((STORAGE / "receipts").glob("*.json"))),
            "memories": len(list((STORAGE / "memory").glob("*.json"))),
        }

    @staticmethod
    def timeline(start: Optional[str] = None, end: Optional[str] = None,
                 limit: int = 100) -> List[dict]:
        """Replay the evolution — the Time Machine for Research."""
        all_items = []
        for obj_type in _DIRS:
            for item in _list(obj_type, limit=500):
                ts = item.get("timestamp", "")
                if start and ts < start:
                    continue
                if end and ts > end:
                    continue
                item["_type"] = obj_type
                all_items.append(item)
        all_items.sort(key=lambda x: x.get("timestamp", ""))
        return all_items[:limit]


# ─── API Models ──────────────────────────────────────────────────────────────

class ObserveRequest(BaseModel):
    observation_type: str = Field(..., description="Type of observation")
    data: Dict[str, Any] = Field(..., description="Observation data")
    state_id: Optional[str] = Field(None, description="Parent state ID")


class HypothesisRequest(BaseModel):
    observation_id: str = Field(..., description="Observation to hypothesize from")
    hypothesis: str = Field(..., description="The hypothesis text")
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class PatchProposeRequest(BaseModel):
    target_file: str = Field(..., description="File to modify")
    description: str = Field(..., description="What the patch does")
    patch_content: str = Field("", description="The actual patch content")
    sha_before: str = Field("", description="SHA of file before patch")
    risk_score: float = Field(0.0, ge=0.0, le=1.0, description="Estimated risk")
    parent_state_id: Optional[str] = Field(None, description="Parent state")
    source_hypothesis_id: Optional[str] = Field(None, description="Hypothesis that generated this patch")


class PatchActionRequest(BaseModel):
    patch_id: str = Field(..., description="Patch to act on")


class BenchmarkRunRequest(BaseModel):
    target_id: str = Field(..., description="ID of patch or state to benchmark")
    target_type: str = Field("patch", description="patch or state")
    metrics: Dict[str, Any] = Field(..., description="Benchmark metrics")


class ArtifactCreateRequest(BaseModel):
    artifact_type: str = Field(..., description="Type of artifact")
    content: Dict[str, Any] = Field(..., description="Artifact content")
    metadata: Optional[Dict[str, Any]] = Field(None)
    source_patch_id: Optional[str] = Field(None)


class MemoryStoreRequest(BaseModel):
    key: str = Field(...)
    value: Any = Field(...)
    tags: Optional[List[str]] = Field(None)


class MemorySearchRequest(BaseModel):
    query: str = Field(...)
    limit: int = Field(20, ge=1, le=100)


class StateCreateRequest(BaseModel):
    description: str = Field(...)
    parent_state_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class ThoughtCreateRequest(BaseModel):
    content: str = Field(..., description="The thought content")
    thought_type: str = Field("idea", description="idea, hypothesis, question, decision, failure")
    parent_thought_id: Optional[str] = Field(None)
    context: Optional[Dict[str, Any]] = Field(None)


class CounterfactualCreateRequest(BaseModel):
    description: str = Field(..., description="What was the rejected/abandoned path")
    parent_id: str = Field(..., description="Parent object ID")
    parent_type: str = Field(..., description="Parent object type")
    reason: str = Field(..., description="Why it was rejected/abandoned")
    counterfactual_type: str = Field("abandoned", description="abandoned, rejected, failed")


class ValuationCreateRequest(BaseModel):
    artifact_id: str = Field(...)
    valuations: Dict[str, Any] = Field(..., description="liquidation_value, replacement_cost, licensing_value, acquisition_value")
    methodology: str = Field("heuristic_v1")


class CausalGraphQueryRequest(BaseModel):
    obj_id: str = Field(...)
    direction: str = Field("ancestors", description="ancestors or descendants")
    depth: int = Field(10, ge=1, le=50)


class TimelineRequest(BaseModel):
    start: Optional[str] = Field(None, description="ISO timestamp start")
    end: Optional[str] = Field(None, description="ISO timestamp end")
    limit: int = Field(100, ge=1, le=500)


# ─── Router ──────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/serl", tags=["SERL — Self-Evolving Runtime Ledger"])


# ─── State Endpoints ─────────────────────────────────────────────────────────

@router.get("/state/current")
async def get_current_state():
    s = State.current()
    if not s:
        return {"state": None, "message": "No states exist yet. POST /serl/state/create"}
    return s


@router.get("/state/history")
async def get_state_history(limit: int = 50):
    return {"states": State.history(limit=limit)}


@router.post("/state/create")
async def create_state(req: StateCreateRequest):
    return State.create(
        parent_state_id=req.parent_state_id,
        description=req.description,
        metadata=req.metadata,
    )


# ─── Thought Endpoints ───────────────────────────────────────────────────────

@router.post("/thought")
async def create_thought(req: ThoughtCreateRequest):
    return Thought.create(
        content=req.content,
        thought_type=req.thought_type,
        parent_thought_id=req.parent_thought_id,
        context=req.context,
    )


@router.get("/thoughts")
async def list_thoughts(limit: int = 50):
    return {"thoughts": Thought.list(limit=limit)}


# ─── Observation Endpoints ───────────────────────────────────────────────────

@router.post("/observe")
async def observe(req: ObserveRequest):
    state_id = req.state_id
    if not state_id:
        s = State.current()
        state_id = s["state_id"] if s else State.create(None, "initial")["state_id"]
    return Observation.create(state_id, req.observation_type, req.data)


@router.get("/observations")
async def list_observations(limit: int = 50):
    return {"observations": Observation.list(limit=limit)}


# ─── Hypothesis Endpoints ────────────────────────────────────────────────────

@router.post("/hypothesis")
async def create_hypothesis(req: HypothesisRequest):
    return Hypothesis.create(req.observation_id, req.hypothesis, req.confidence)


@router.get("/hypotheses")
async def list_hypotheses(limit: int = 50):
    return {"hypotheses": Hypothesis.list(limit=limit)}


# ─── Patch Endpoints ─────────────────────────────────────────────────────────

@router.post("/patch/propose")
async def propose_patch(req: PatchProposeRequest):
    parent_state = req.parent_state_id
    if not parent_state:
        s = State.current()
        parent_state = s["state_id"] if s else State.create(None, "initial")["state_id"]
    patch = Patch.create(
        parent_state_id=parent_state,
        target_file=req.target_file,
        description=req.description,
        sha_before=req.sha_before,
        patch_content=req.patch_content,
        risk_score=req.risk_score,
        source_hypothesis_id=req.source_hypothesis_id,
    )
    Receipt.create("patch", patch["patch_id"], {
        "action": "proposed",
        "target_file": req.target_file,
        "risk_score": req.risk_score,
    })
    return patch


@router.post("/patch/simulate")
async def simulate_patch(req: PatchActionRequest):
    p = Patch.get(req.patch_id)
    if not p:
        raise HTTPException(404, f"Patch {req.patch_id} not found")
    sim_result = {
        "simulated": True,
        "target_file": p["target_file"],
        "estimated_impact": "unknown",
        "warnings": [],
    }
    p = Patch.update_status(req.patch_id, "simulated", simulation=sim_result)
    Receipt.create("patch", req.patch_id, {
        "action": "simulated",
        "result": sim_result,
    })
    return p


@router.post("/patch/benchmark")
async def benchmark_patch(req: BenchmarkRunRequest):
    p = Patch.get(req.target_id)
    if not p and req.target_type == "patch":
        raise HTTPException(404, f"Patch {req.target_id} not found")
    bench = Benchmark.create(req.target_id, req.target_type, req.metrics)
    if req.target_type == "patch":
        Patch.update_status(req.target_id, "benchmarked", benchmark_id=bench["bench_id"])
    Receipt.create("benchmark", bench["bench_id"], {
        "target_id": req.target_id,
        "metrics": req.metrics,
    })
    return bench


@router.post("/patch/promote")
async def promote_patch(req: PatchActionRequest):
    p = Patch.get(req.patch_id)
    if not p:
        raise HTTPException(404, f"Patch {req.patch_id} not found")
    if p["status"] not in ("simulated", "benchmarked"):
        raise HTTPException(400, f"Patch must be simulated or benchmarked first (current: {p['status']})")
    new_state = State.create(
        parent_state_id=p["parent_state"],
        description=f"Promoted patch: {p['description']}",
        metadata={"patch_id": p["patch_id"], "target_file": p["target_file"]},
    )
    p = Patch.update_status(req.patch_id, "promoted", promoted_state=new_state["state_id"])
    Receipt.create("patch", p["patch_id"], {
        "action": "promoted",
        "new_state": new_state["state_id"],
    })
    return {"patch": p, "new_state": new_state}


@router.post("/patch/revert")
async def revert_patch(req: PatchActionRequest):
    p = Patch.get(req.patch_id)
    if not p:
        raise HTTPException(404, f"Patch {req.patch_id} not found")
    parent = State.get(p["parent_state"])
    if not parent:
        raise HTTPException(404, f"Parent state {p['parent_state']} not found")
    p = Patch.update_status(req.patch_id, "reverted")
    new_state = State.create(
        parent_state_id=parent["state_id"],
        description=f"Reverted patch: {p['description']}",
        metadata={"reverted_patch_id": p["patch_id"]},
    )
    Receipt.create("patch", p["patch_id"], {
        "action": "reverted",
        "restored_state": new_state["state_id"],
    })
    return {"patch": p, "restored_state": new_state}


@router.get("/patches")
async def list_patches(limit: int = 50):
    return {"patches": Patch.list(limit=limit)}


# ─── Benchmark Endpoints ─────────────────────────────────────────────────────

@router.get("/benchmark/results")
async def get_benchmark_results(limit: int = 50):
    return {"benchmarks": Benchmark.list(limit=limit)}


@router.get("/benchmark/{bench_id}")
async def get_benchmark(bench_id: str):
    b = Benchmark.get(bench_id)
    if not b:
        raise HTTPException(404, f"Benchmark {bench_id} not found")
    return b


# ─── Artifact Endpoints ──────────────────────────────────────────────────────

@router.post("/artifact/create")
async def create_artifact(req: ArtifactCreateRequest):
    artifact = Artifact.create(
        artifact_type=req.artifact_type,
        content=req.content,
        metadata=req.metadata,
        source_patch_id=req.source_patch_id,
    )
    Receipt.create("artifact", artifact["artifact_id"], {
        "artifact_type": req.artifact_type,
        "content_hash": artifact["content_hash"],
    })
    return artifact


@router.get("/artifact/{artifact_id}")
async def get_artifact(artifact_id: str):
    a = Artifact.get(artifact_id)
    if not a:
        raise HTTPException(404, f"Artifact {artifact_id} not found")
    return a


@router.get("/artifacts")
async def list_artifacts(limit: int = 50):
    return {"artifacts": Artifact.list(limit=limit)}


# ─── Valuation Endpoints (Self-Valuing IP Market) ────────────────────────────

@router.post("/valuation/create")
async def create_valuation(req: ValuationCreateRequest):
    return Valuation.create(
        artifact_id=req.artifact_id,
        valuations=req.valuations,
        methodology=req.methodology,
    )


@router.get("/valuation/{artifact_id}")
async def get_valuations_for_artifact(artifact_id: str):
    return {"valuations": Valuation.for_artifact(artifact_id)}


@router.post("/valuation/estimate")
async def estimate_valuation(artifact_id: str):
    """Auto-estimate valuation using heuristic model."""
    a = Artifact.get(artifact_id)
    if not a:
        raise HTTPException(404, f"Artifact {artifact_id} not found")
    content_size = len(json.dumps(a["content"], default=str))
    causal_in = CausalEdge.to_object(artifact_id)
    causal_out = CausalEdge.from_object(artifact_id)
    causal_depth = len(causal_in) + len(causal_out)
    receipts = [r for r in Receipt.list(limit=200) if r["object_id"] == artifact_id]
    estimates = Valuation.estimate_heuristic(
        artifact_type=a["artifact_type"],
        content_size=content_size,
        causal_depth=causal_depth,
        receipt_count=len(receipts),
    )
    val = Valuation.create(artifact_id, estimates, methodology="auto_heuristic_v1")
    return val


@router.get("/valuations")
async def list_valuations(limit: int = 50):
    return {"valuations": Valuation.list(limit=limit)}


# ─── Counterfactual Endpoints (Time Machine for Research) ────────────────────

@router.post("/counterfactual")
async def create_counterfactual(req: CounterfactualCreateRequest):
    cf = Counterfactual.create(
        description=req.description,
        parent_id=req.parent_id,
        parent_type=req.parent_type,
        reason=req.reason,
        counterfactual_type=req.counterfactual_type,
    )
    Receipt.create("counterfactual", cf["cf_id"], {
        "reason": req.reason,
        "parent_id": req.parent_id,
    })
    return cf


@router.get("/counterfactuals")
async def list_counterfactuals(limit: int = 50):
    return {"counterfactuals": Counterfactual.list(limit=limit)}


@router.post("/counterfactuals/search")
async def search_counterfactuals(query: str, limit: int = 20):
    return {"results": Counterfactual.search(query, limit=limit)}


# ─── Receipt Endpoints ───────────────────────────────────────────────────────

@router.get("/receipt/{receipt_id}")
async def get_receipt(receipt_id: str):
    r = Receipt.get(receipt_id)
    if not r:
        raise HTTPException(404, f"Receipt {receipt_id} not found")
    return r


@router.get("/receipts")
async def list_receipts(limit: int = 50):
    return {"receipts": Receipt.list(limit=limit)}


# ─── Memory Endpoints ────────────────────────────────────────────────────────

@router.post("/memory/store")
async def store_memory(req: MemoryStoreRequest):
    return Memory.store(req.key, req.value, req.tags)


@router.post("/memory/search")
async def search_memory(req: MemorySearchRequest):
    return {"results": Memory.search(req.query, req.limit)}


# ─── Causal Graph Endpoints ──────────────────────────────────────────────────

@router.get("/causal/stats")
async def causal_stats():
    return CausalGraph.stats()


@router.get("/causal/edges")
async def causal_edges(limit: int = 200):
    return {"edges": CausalEdge.all_edges(limit=limit)}


@router.post("/causal/trace")
async def causal_trace(req: CausalGraphQueryRequest):
    if req.direction == "ancestors":
        return {"traces": CausalGraph.ancestors(req.obj_id, req.depth)}
    else:
        return {"traces": CausalGraph.descendants(req.obj_id, req.depth)}


# ─── Timeline Endpoint (Time Machine) ───────────────────────────────────────

@router.post("/timeline")
async def timeline(req: TimelineRequest):
    return {"timeline": CausalGraph.timeline(req.start, req.end, req.limit)}


# ─── Runtime Inspect ─────────────────────────────────────────────────────────

@router.get("/runtime/inspect")
async def runtime_inspect():
    return {
        "storage_path": str(STORAGE),
        "object_counts": CausalGraph.stats(),
        "current_state": State.current(),
        "timestamp": _utc_now(),
    }
