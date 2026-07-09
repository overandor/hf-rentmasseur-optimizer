"""
OverLanguage 2.0 — Glyph-Native Meta-Language for AI Production
===============================================================
Program = instructions for machines.
OverProgram = instructions for production reality.

Root glyph: ⧉◇@L → H@L Æ R Æ λ⁻¹ = ◎ → $

Seven layers:
  L0: Glyph — compressed symbolic substrate
  L1: Intent — human-level objective
  L2: Contract — enforceable requirements
  L3: Agent — production operators
  L4: Substrate — latent compute capture
  L5: Receipt — proof binding
  L6: Transfer — lambda friction / transferability
  L7: Economic — buyer / value / price

Compiler passes:
  parse → expand → contract → assign → execute → capture → hash → receipt → score → package
"""

import json
import time
import hashlib
import re
import os
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path


@dataclass
class OverProgram:
    name: str = ""
    intent: str = ""
    object_desc: str = ""
    anchor: str = ""
    capture: list = field(default_factory=list)
    prove: list = field(default_factory=list)
    score: dict = field(default_factory=dict)
    output: list = field(default_factory=list)
    success: str = ""
    economic: dict = field(default_factory=dict)
    agents: dict = field(default_factory=dict)
    raw: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CompilationResult:
    program: dict = field(default_factory=dict)
    build_plan: dict = field(default_factory=dict)
    artifact_manifest: dict = field(default_factory=dict)
    receipt: dict = field(default_factory=dict)
    lambda_score: dict = field(default_factory=dict)
    buyer_packet: dict = field(default_factory=dict)
    glyph: str = ""
    compiled_at: float = 0.0
    status: str = "compiled"

    def to_dict(self) -> dict:
        return asdict(self)


class OverLanguageParser:
    """Parses .over files into OverProgram objects."""

    def parse(self, source: str) -> OverProgram:
        prog = OverProgram(raw=source)

        # Extract name
        m = re.search(r'overprogram\s+(\w+)', source)
        if m:
            prog.name = m.group(1)

        # Extract intent
        m = re.search(r'intent:\s*(.*?)(?:\n\s*\n|\n\s*\w+:)', source, re.DOTALL)
        if m:
            prog.intent = m.group(1).strip().strip('"').strip("'")

        # Extract object
        m = re.search(r'object:\s*(.*?)(?:\n\s*\n|\n\s*\w+:)', source, re.DOTALL)
        if m:
            prog.object_desc = m.group(1).strip().strip('"').strip("'")

        # Extract anchor
        m = re.search(r'anchor:\s*(.*?)(?:\n\s*\n|\n\s*\w+:)', source, re.DOTALL)
        if m:
            prog.anchor = m.group(1).strip()

        # Extract capture
        m = re.search(r'capture:\s*(.*?)(?:\n\s*\n|\n\s*\w+:)', source, re.DOTALL)
        if m:
            prog.capture = [c.strip() for c in m.group(1).strip().split('\n') if c.strip()]

        # Extract prove
        m = re.search(r'prove:\s*(.*?)(?:\n\s*\n|\n\s*\w+:)', source, re.DOTALL)
        if m:
            prog.prove = [p.strip() for p in m.group(1).strip().split('\n') if p.strip()]

        # Extract score
        m = re.search(r'score:\s*(.*?)(?:\n\s*\n|\n\s*\w+:)', source, re.DOTALL)
        if m:
            score_block = m.group(1).strip()
            for line in score_block.split('\n'):
                if '=' in line:
                    key, val = line.split('=', 1)
                    prog.score[key.strip()] = val.strip()

        # Extract output
        m = re.search(r'output:\s*(.*?)(?:\n\s*\n|\n\s*\w+:)', source, re.DOTALL)
        if m:
            prog.output = [o.strip() for o in m.group(1).strip().split('\n') if o.strip()]

        # Extract success
        m = re.search(r'success:\s*(.*?)(?:\n\s*\n|\n\s*\w+:)', source, re.DOTALL)
        if m:
            prog.success = m.group(1).strip()

        # Extract economic
        m = re.search(r'economic:\s*(.*?)(?:\n\s*\n|\n\s*\w+:|\Z)', source, re.DOTALL)
        if m:
            econ_block = m.group(1).strip()
            for line in econ_block.split('\n'):
                if '=' in line:
                    key, val = line.split('=', 1)
                    prog.economic[key.strip()] = val.strip().strip('"').strip("'")

        return prog


class OverLanguageCompiler:
    """Compiles OverProgram into production artifacts."""

    def __init__(self):
        self.parser = OverLanguageParser()

    def compile(self, source: str) -> CompilationResult:
        prog = self.parser.parse(source)

        # Build plan
        build_plan = {
            "program": prog.name,
            "intent": prog.intent,
            "object": prog.object_desc,
            "steps": self._generate_steps(prog),
            "agents": self._assign_agents(prog),
            "capture_planes": prog.capture,
            "proof_claims": prog.prove,
        }

        # Artifact manifest
        artifact_manifest = {
            "name": prog.name,
            "object": prog.object_desc,
            "anchor": prog.anchor or "⧉◇@L",
            "outputs": prog.output,
            "success_condition": prog.success,
        }

        # Receipt
        receipt_hash = hashlib.sha256(json.dumps(build_plan, sort_keys=True).encode()).hexdigest()
        receipt = {
            "receipt_id": receipt_hash[:16],
            "program": prog.name,
            "intent": prog.intent,
            "proof_claims": prog.prove,
            "artifact_hash": receipt_hash,
            "created_at": time.time(),
            "protocol": "OverLanguage/2.0",
            "glyph": "⧉◇@L → H@L Æ R Æ λ⁻¹ = ◎ → $",
        }

        # Lambda score
        lambda_components = {
            "local_path_dependency": 0.20,
            "secret_dependency": 0.00,
            "runtime_drift": 0.15,
            "documentation_gap": 0.10,
            "test_gap": 0.05,
        }
        lambda_total = sum(lambda_components.values())
        transferability = 1.0 / (1.0 + lambda_total)
        lambda_score = {
            "components": lambda_components,
            "lambda_total": round(lambda_total, 4),
            "transferability": round(transferability, 4),
            "interpretation": "medium_friction",
            "formula": "τ = R / (1 + λ)",
        }

        # Buyer packet
        buyer_packet = {
            "program": prog.name,
            "artifact": prog.object_desc,
            "proof_claims": prog.prove,
            "transferability": lambda_score["transferability"],
            "price": prog.economic.get("price", "TBD"),
            "buyer": prog.economic.get("buyer", "TBD"),
            "receipt_id": receipt["receipt_id"],
            "glyph": "◇ Æ R Æ λ⁻¹ → $",
        }

        return CompilationResult(
            program=prog.to_dict(),
            build_plan=build_plan,
            artifact_manifest=artifact_manifest,
            receipt=receipt,
            lambda_score=lambda_score,
            buyer_packet=buyer_packet,
            glyph="⧉◇@L → H@L Æ R Æ λ⁻¹ = ◎ → $",
            compiled_at=time.time(),
            status="compiled",
        )

    def _generate_steps(self, prog: OverProgram) -> list[str]:
        steps = [
            f"1. Find or create artifact: {prog.object_desc}",
            f"2. Anchor artifact at canonical location: {prog.anchor or '⧉◇@L'}",
            "3. Hash artifact (H@L)",
            "4. Bind to receipt (H Æ R)",
            "5. Measure lambda friction (λ)",
            "6. Verify proof state (◎)",
            "7. Package for buyer/investor/client ($)",
        ]
        return steps

    def _assign_agents(self, prog: OverProgram) -> dict[str, str]:
        agents = {
            "CHATGPT": "architecture / spec / critique",
            "WINDSURF": "code edits / repo operations",
            "CODEX": "patch generation / tests",
            "CLAUDE": "deep refactor / reasoning",
            "XCODE": "native build / signing / diagnostics",
            "TERMINAL": "commands / receipts / verification",
        }
        return agents


# --- Layer4Meter: Latent Compute Substrate ---
# 5-plane capture: visual, file, process, power, time/snapshot
# 3-mode baseline: idle, human, agent workload
# Hidden Compute Lift = Agent LCI - Human Baseline - Idle Baseline

@dataclass
class SubstrateSample:
    timestamp: float = 0.0
    # Plane 1: Visual
    screen_state_changes: int = 0
    active_app: str = ""
    windows_visible: int = 0
    # Plane 2: File
    file_event_count: int = 0
    files_created: int = 0
    files_modified: int = 0
    files_deleted: int = 0
    git_commits: int = 0
    git_files_staged: int = 0
    # Plane 3: Process
    process_spawn_count: int = 0
    child_processes: int = 0
    # Plane 4: Power/Performance
    cpu_seconds: float = 0.0
    gpu_activity: float = 0.0
    disk_write_mb: float = 0.0
    network_bytes: int = 0
    memory_pressure: float = 0.0
    # Plane 5: Time/Snapshot
    snapshot_delta_mb: float = 0.0
    # Agent telemetry
    agent_idle_seconds: float = 0.0
    agent_retries: int = 0
    prompts_sent: int = 0
    build_attempts: int = 0
    builds_passed: int = 0
    useful_outputs: int = 0
    mode: str = "agent"  # idle, human, agent


class Layer4Meter:
    """Captures and quantifies latent compute substrate behind AI work.

    5 planes: Visual, File, Process, Power, Time/Snapshot
    3 modes: idle baseline, human baseline, agent workload
    LCI = α·CPU + β·GPU + γ·disk + δ·files + ε·procs + ζ·net + η·mem + θ·snap + ι·screen + κ·idle
    Hidden Compute Lift = Agent LCI - Human Baseline - Idle Baseline
    """

    def __init__(self):
        self.samples: list[SubstrateSample] = []
        self.baselines: dict[str, float] = {}
        self.workflows: dict[str, dict] = {}
        self.weights = {
            "cpu_seconds": 1.0,       # α
            "gpu_activity": 2.0,      # β
            "disk_write_mb": 0.5,     # γ
            "file_event_count": 0.01, # δ
            "process_spawn_count": 0.1, # ε
            "network_bytes": 0.0001,  # ζ
            "memory_pressure": 5.0,   # η
            "snapshot_delta_mb": 0.3, # θ
            "screen_state_changes": 0.5, # ι
            "agent_idle_seconds": 0.2,  # κ
        }

    def sample(self, mode: str = "agent") -> SubstrateSample:
        """Capture a substrate sample across all 5 planes.
        In production: ScreenCaptureKit, FSEvents, Endpoint Security, MetricKit, Time Machine."""
        import random as _r
        s = SubstrateSample(
            timestamp=time.time(),
            mode=mode,
            # Plane 1: Visual
            screen_state_changes=_r.randint(0, 15),
            active_app=_r.choice(["Windsurf", "Xcode", "Terminal", "Safari", "Finder"]),
            windows_visible=_r.randint(2, 8),
            # Plane 2: File
            file_event_count=_r.randint(5, 120),
            files_created=_r.randint(0, 10),
            files_modified=_r.randint(2, 40),
            files_deleted=_r.randint(0, 5),
            git_commits=_r.randint(0, 3),
            git_files_staged=_r.randint(0, 20),
            # Plane 3: Process
            process_spawn_count=_r.randint(2, 50),
            child_processes=_r.randint(5, 150),
            # Plane 4: Power
            cpu_seconds=_r.uniform(0.1, 8.0),
            gpu_activity=_r.uniform(0, 40),
            disk_write_mb=_r.uniform(1, 100),
            network_bytes=_r.randint(1000, 2000000),
            memory_pressure=_r.uniform(0.1, 0.9),
            # Plane 5: Time/Snapshot
            snapshot_delta_mb=_r.uniform(0, 50),
            # Agent telemetry
            agent_idle_seconds=_r.uniform(0, 180) if mode == "agent" else 0,
            agent_retries=_r.randint(0, 5) if mode == "agent" else 0,
            prompts_sent=_r.randint(0, 15) if mode == "agent" else 0,
            build_attempts=_r.randint(0, 3),
            builds_passed=_r.randint(0, 2),
            useful_outputs=_r.randint(0, 3),
        )
        self.samples.append(s)
        return s

    def compute_lci(self, sample: SubstrateSample) -> float:
        """LCI = α·CPU + β·GPU + γ·disk + δ·files + ε·procs + ζ·net + η·mem + θ·snap + ι·screen + κ·idle"""
        d = asdict(sample)
        lci = 0.0
        for key, weight in self.weights.items():
            lci += weight * d.get(key, 0)
        return round(lci, 2)

    def set_baseline(self, mode: str, lci: float):
        """Set baseline LCI for idle or human mode."""
        self.baselines[mode] = lci

    def capture_baseline(self, mode: str, samples: int = 5) -> dict:
        """Capture baseline LCI by sampling N times in given mode."""
        total = 0
        for _ in range(samples):
            s = self.sample(mode=mode)
            total += self.compute_lci(s)
        avg = round(total / samples, 2)
        self.baselines[mode] = avg
        return {
            "mode": mode,
            "samples": samples,
            "avg_lci": avg,
            "total_lci": round(total, 2),
            "status": "baseline_set",
        }

    def hidden_compute_lift(self, workload_lci: float = None) -> dict:
        """Hidden Compute Lift = Agent LCI - Human Baseline - Idle Baseline"""
        if workload_lci is None:
            agent_samples = [s for s in self.samples if s.mode == "agent"]
            if agent_samples:
                workload_lci = round(sum(self.compute_lci(s) for s in agent_samples) / len(agent_samples), 2)
            else:
                workload_lci = 0
        idle = self.baselines.get("idle", 0)
        human = self.baselines.get("human", 0)
        lift = round(workload_lci - human - idle, 2)
        return {
            "agent_workload_lci": workload_lci,
            "idle_baseline_lci": idle,
            "human_baseline_lci": human,
            "hidden_compute_lift": lift,
            "formula": "Hidden Compute Lift = Agent LCI - Human Baseline - Idle Baseline",
            "interpretation": "positive" if lift > 0 else "negative" if lift < 0 else "neutral",
        }

    def business_metrics(self, artifact_value: float = 0, lci: float = 0,
                         useful_outputs: int = 0, retries: int = 0,
                         total_events: int = 0, agent_idle: float = 0) -> dict:
        """Compute business metrics from substrate data."""
        if lci == 0 and self.samples:
            agent_samples = [s for s in self.samples if s.mode == "agent"]
            lci = sum(self.compute_lci(s) for s in agent_samples) if agent_samples else 1
        if useful_outputs == 0:
            useful_outputs = sum(s.useful_outputs for s in self.samples if s.mode == "agent")
        if retries == 0:
            retries = sum(s.agent_retries for s in self.samples if s.mode == "agent")
        if total_events == 0:
            total_events = sum(s.file_event_count + s.process_spawn_count for s in self.samples if s.mode == "agent")
        if agent_idle == 0:
            agent_idle = sum(s.agent_idle_seconds for s in self.samples if s.mode == "agent")
        return {
            "cost_per_artifact": round(lci / max(useful_outputs, 1), 2),
            "proof_density": round(useful_outputs / max(total_events, 1), 4),
            "agent_efficiency": round(useful_outputs / max(lci, 1), 4),
            "waste_ratio": round(retries / max(total_events, 1), 4),
            "agent_waste_seconds": round(agent_idle, 1),
            "revenue_readiness": round(artifact_value / max(lci, 1), 2),
            "value_per_lci": round(artifact_value / max(lci, 1), 2),
        }

    def rank_workflows(self, workflows: list[dict]) -> list[dict]:
        """Rank workflows by value per LCI. Each workflow: {name, lci, artifact_value}."""
        ranked = []
        for wf in workflows:
            vpl = round(wf["artifact_value"] / max(wf["lci"], 1), 2)
            ranked.append({
                "name": wf["name"],
                "lci": wf["lci"],
                "artifact_value": wf["artifact_value"],
                "value_per_lci": vpl,
            })
        ranked.sort(key=lambda x: x["value_per_lci"], reverse=True)
        if len(ranked) >= 2:
            ratio = round(ranked[0]["value_per_lci"] / max(ranked[1]["value_per_lci"], 0.01), 1)
            ranked[0]["advantage_vs_next"] = f"{ratio}x more valuable per LCI"
        return ranked

    def receipt(self, project: str, session_start: float = 0) -> dict:
        """Generate an L4 substrate receipt with 5-plane breakdown."""
        agent_samples = [s for s in self.samples if s.mode == "agent"]
        all_samples = self.samples
        total_lci = sum(self.compute_lci(s) for s in all_samples)
        agent_lci = sum(self.compute_lci(s) for s in agent_samples) if agent_samples else total_lci

        # 5-plane breakdown
        planes = {
            "visual": sum(s.screen_state_changes * self.weights["screen_state_changes"] for s in all_samples),
            "file": sum(s.file_event_count * self.weights["file_event_count"] for s in all_samples),
            "process": sum(s.process_spawn_count * self.weights["process_spawn_count"] for s in all_samples),
            "power": sum(
                s.cpu_seconds * self.weights["cpu_seconds"] +
                s.gpu_activity * self.weights["gpu_activity"] +
                s.disk_write_mb * self.weights["disk_write_mb"] +
                s.network_bytes * self.weights["network_bytes"] +
                s.memory_pressure * self.weights["memory_pressure"]
                for s in all_samples
            ),
            "time_snapshot": sum(s.snapshot_delta_mb * self.weights["snapshot_delta_mb"] for s in all_samples),
        }

        # Aggregate stats
        stats = {
            "files_changed": sum(s.files_created + s.files_modified + s.files_deleted for s in all_samples),
            "files_created": sum(s.files_created for s in all_samples),
            "git_commits": sum(s.git_commits for s in all_samples),
            "child_processes": sum(s.child_processes for s in all_samples),
            "disk_written_mb": round(sum(s.disk_write_mb for s in all_samples), 1),
            "prompts_sent": sum(s.prompts_sent for s in all_samples),
            "build_attempts": sum(s.build_attempts for s in all_samples),
            "builds_passed": sum(s.builds_passed for s in all_samples),
            "useful_outputs": sum(s.useful_outputs for s in all_samples),
            "agent_waste_seconds": round(sum(s.agent_idle_seconds for s in agent_samples), 1),
            "agent_retries": sum(s.agent_retries for s in agent_samples),
        }

        sample_hashes = [hashlib.sha256(json.dumps(asdict(s), sort_keys=True).encode()).hexdigest()[:12] for s in all_samples]
        merkle_input = "".join(sample_hashes).encode()
        proof_root = hashlib.sha256(merkle_input).hexdigest()[:16]

        return {
            "type": "L4_SUBSTRATE_RECEIPT",
            "session": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(session_start or time.time())),
            "project": project,
            "samples": len(all_samples),
            "agent_samples": len(agent_samples),
            "lci_total": round(total_lci, 2),
            "lci_agent": round(agent_lci, 2),
            "lci_avg": round(total_lci / max(len(all_samples), 1), 2),
            "planes": {k: round(v, 2) for k, v in planes.items()},
            "stats": stats,
            "baselines": self.baselines,
            "hidden_compute_lift": self.hidden_compute_lift(agent_lci),
            "business_metrics": self.business_metrics(),
            "sample_hashes": sample_hashes[:8],
            "proof_root": proof_root,
            "protocol": "Layer4Meter/1.0",
            "shard_format": ".l4receipt/{manifest.json, events.sqlite, shards/*, hashes/merkle_root.txt, proofs/*}",
            "generated_at": time.time(),
        }
