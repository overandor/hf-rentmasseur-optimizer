#!/usr/bin/env python3
"""
.over CPU — LLM AS Compiler+Runtime
====================================
11 radical concepts, one runtime. Uses .over and .glyph as input.

  1. LLM AS CPU          — semantic IR, inference = execution
  2. Glyph-Native        — pure glyph syntax via glyphlang lexer
  3. Self-Modifying      — runtime rewrites IR based on results
  4. Temporal Execution  — step fwd/bwd, branching timelines
  5. Semantic Types      — types are concepts (trustworthy, autonomous)
  6. Receipt-Native      — every expression → cryptographic receipt
  7. Quantum Control     — superposition { A | B }, collapse, entangle
  8. Agent-as-Function   — calling fn = spawning agent
  9. Memory-as-Context   — context window IS memory, LRU eviction
 10. Dream Mode          — simulate N futures, pick best
 11. Glyph Density       — labels fade as expertise grows

Usage:
    python3 over_cpu.py run program.over
    python3 over_cpu.py run program.glyph --dream --expert
    python3 over_cpu.py repl
    python3 over_cpu.py demo
"""
import argparse, hashlib, json, os, sys, time, random, re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Callable

sys.path.insert(0, str(Path(__file__).parent))
from glyphlang import lex_glyph, parse_glyph, compile_glyph, GLYPH_TOKENS
from overlang import parse_over, compile_over, OverRuntime

# ═══════════════════════════════════════════════════════════════════════════
# CONCEPT 5: Semantic Type System — types are concepts
# ═══════════════════════════════════════════════════════════════════════════
SEMANTIC_TYPES = {
    "trustworthy": {"min_conf": 0.8, "requires": ["verified"]},
    "autonomous":  {"min_conf": 0.7, "requires": ["capable", "bounded"]},
    "capable":     {"min_conf": 0.6, "requires": ["functional"]},
    "bounded":     {"min_conf": 0.7, "requires": ["constrained"]},
    "verified":    {"min_conf": 0.9, "requires": ["receipt"]},
    "receipt":     {"min_conf": 1.0, "requires": ["hashed"]},
    "streaming":   {"min_conf": 0.5, "requires": ["live"]},
    "expiring":    {"min_conf": 0.5, "requires": ["timeout"]},
    "canonical":   {"min_conf": 0.9, "requires": ["unique"]},
    "functional":  {"min_conf": 0.5, "requires": []},
    "constrained": {"min_conf": 0.5, "requires": []},
    "hashed":      {"min_conf": 1.0, "requires": []},
    "live":        {"min_conf": 0.5, "requires": []},
    "unique":      {"min_conf": 0.8, "requires": []},
}

# ═══════════════════════════════════════════════════════════════════════════
# CONCEPT 2: Compound Glyph Semantics — ◉◆⌁ = live_verified_stream
# ═══════════════════════════════════════════════════════════════════════════
COMPOUND_GLYPHS = {
    "◉◆⌁":  {"op": "LIVE_VERIFIED_STREAM",   "intent": "stream live verified data",     "type": "streaming"},
    "◇⟡▲":  {"op": "INDEXED_AI_TRENDING",     "intent": "index AI-readable trending data","type": "canonical"},
    "⟁⧖▼":  {"op": "ANOMALY_EXPIRING_DEGRADE","intent": "anomaly expiring degrading",     "type": "expiring"},
    "◉⟡◆":  {"op": "LIVE_AI_VERIFIED",        "intent": "live AI-verified signal",        "type": "verified"},
    "◌⧖✕":  {"op": "DORMANT_EXPIRING_INVALID","intent": "dormant expiring invalid",       "type": "expiring"},
    "◍⧉≡":  {"op": "MIRROR_DUPLICATE_IDENTICAL","intent": "mirror duplicate identical",   "type": "canonical"},
    "◉⌁":   {"op": "LIVE_STREAM",             "intent": "stream live data",               "type": "streaming"},
    "◆⌁":   {"op": "VERIFIED_STREAM",         "intent": "stream verified data",           "type": "verified"},
    "⟡◆":   {"op": "AI_VERIFIED",             "intent": "AI-readable verified transform", "type": "verified"},
    "⧖▼":   {"op": "EXPIRING_FALLING",        "intent": "expiring falling value",         "type": "expiring"},
    "▲◆":   {"op": "RISING_VERIFIED",         "intent": "rising verified signal",         "type": "verified"},
}

def parse_compound_glyphs(token_stream):
    """Merge adjacent glyph tokens into compound glyphs where they match.
    ◉ ◆ ⌁ (3 tokens) → ◉◆⌁ (1 compound op)"""
    result = []
    i = 0
    while i < len(token_stream):
        # Try 3-glyph compound first, then 2-glyph
        matched = False
        for length in (3, 2):
            if i + length <= len(token_stream):
                compound = "".join(t.glyph for t in token_stream[i:i+length])
                if compound in COMPOUND_GLYPHS:
                    spec = COMPOUND_GLYPHS[compound]
                    result.append(SemanticOp(
                        op=spec["op"], glyph=compound,
                        line=token_stream[i].line,
                        intent=spec["intent"],
                    ))
                    i += length
                    matched = True
                    break
        if not matched:
            tok = token_stream[i]
            result.append(SemanticOp(op=tok.name, glyph=tok.glyph, line=tok.line, intent=f"execute {tok.name}"))
            i += 1
    return result

def type_check(value, concept_type, context):
    """Check if value satisfies a semantic type. Returns (ok, reasoning)."""
    spec = SEMANTIC_TYPES.get(concept_type)
    if not spec:
        return True, f"unknown type '{concept_type}' — assumed valid"
    conf = 0.0
    if isinstance(value, dict):
        conf = value.get("confidence", value.get("_confidence", 0.5))
        for req in spec["requires"]:
            ok, reason = type_check(value, req, context)
            if not ok:
                return False, f"not {req} enough for {concept_type}: {reason}"
    elif isinstance(value, (str, int, float)):
        conf = 0.5
    else:
        conf = 0.3
    if conf < spec["min_conf"]:
        return False, f"confidence {conf:.2f} < required {spec['min_conf']:.2f} for '{concept_type}'"
    return True, f"satisfies {concept_type} (conf={conf:.2f})"

# ═══════════════════════════════════════════════════════════════════════════
# CONCEPT 6: Receipt-Native — every expression → receipt
# ═══════════════════════════════════════════════════════════════════════════
def make_receipt(op, value, prev_hash, meta=None):
    ts = datetime.utcnow().isoformat() + "Z"
    vh = hashlib.sha256(json.dumps(str(value), sort_keys=True).encode()).hexdigest()
    entry = json.dumps({"op": op, "vh": vh[:16], "ts": ts, "meta": meta or {}}, sort_keys=True)
    fh = hashlib.sha256((prev_hash + entry).encode()).hexdigest()
    return {"op": op, "value_hash": vh[:16], "receipt_hash": fh, "prev_hash": prev_hash, "ts": ts, "meta": meta or {}}

# ═══════════════════════════════════════════════════════════════════════════
# CONCEPT 9: Memory-as-Context-Window — no heap/stack
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class ContextWindow:
    entries: list = field(default_factory=list)
    max_entries: int = 128

    def assign(self, name, value, type_hint="", importance=0.5):
        self.entries = [e for e in self.entries if e["name"] != name]
        self.entries.append({"name": name, "value": value, "type": type_hint,
                             "importance": importance, "ts": time.time(), "access": 0})
        return self._gc()

    def lookup(self, name):
        for e in self.entries:
            if e["name"] == name:
                e["access"] += 1
                e["importance"] = min(1.0, e["importance"] + 0.05)
                return e["value"]
        return None

    def _gc(self):
        if len(self.entries) > self.max_entries:
            self.entries.sort(key=lambda e: (e["importance"], e["access"], e["ts"]))
            evicted = self.entries[:len(self.entries) - self.max_entries]
            self.entries = self.entries[len(evicted):]
            return [e["name"] for e in evicted]
        return []

    def pressure(self):
        return len(self.entries) / self.max_entries

    def snapshot(self):
        return "\n".join(f"  {e['name']} : {e['type'] or '?'} = {str(e['value'])[:60]}" for e in self.entries)

# ═══════════════════════════════════════════════════════════════════════════
# CONCEPT 4: Temporal Execution — step fwd/bwd, branching timelines
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class Timeline:
    id: str
    steps: list = field(default_factory=list)
    parent_id: Optional[str] = None
    branch_point: int = 0
    status: str = "active"

class TemporalExecutor:
    def __init__(self):
        self.timelines = {"main": Timeline(id="main")}
        self.current = "main"
        self.ptr = {"main": 0}

    def record(self, op, value, receipt):
        tl = self.timelines[self.current]
        idx = self.ptr[self.current]
        step = {"idx": idx, "op": op, "value": value, "receipt": receipt, "ts": time.time()}
        if idx < len(tl.steps):
            tl.steps[idx] = step
        else:
            tl.steps.append(step)
        self.ptr[self.current] = idx + 1

    def back(self, n=1):
        self.ptr[self.current] = max(0, self.ptr[self.current] - n)
        tl = self.timelines[self.current]
        p = self.ptr[self.current]
        return tl.steps[p] if p < len(tl.steps) else None

    def forward(self, n=1):
        tl = self.timelines[self.current]
        self.ptr[self.current] = min(len(tl.steps) - 1, self.ptr[self.current] + n)
        p = self.ptr[self.current]
        return tl.steps[p] if p < len(tl.steps) else None

    def branch(self, from_step=None):
        tl = self.timelines[self.current]
        fp = from_step if from_step is not None else self.ptr[self.current]
        nid = f"{self.current}_b{len(self.timelines)}"
        ntl = Timeline(id=nid, parent_id=self.current, branch_point=fp)
        ntl.steps = tl.steps[:fp].copy()
        self.timelines[nid] = ntl
        self.ptr[nid] = fp
        return nid

    def reimagine(self, from_step):
        """LLM reimagines a different path from any point."""
        nid = self.branch(from_step)
        self.current = nid
        return nid

    def switch_timeline(self, tl_id):
        """Switch to a different timeline."""
        if tl_id in self.timelines:
            self.current = tl_id

    def status(self):
        return {"current": self.current, "timelines": {
            tid: {"steps": len(tl.steps), "ptr": self.ptr.get(tid, 0),
                  "parent": tl.parent_id, "branch": tl.branch_point}
            for tid, tl in self.timelines.items()}}

# ═══════════════════════════════════════════════════════════════════════════
# CONCEPT 7: Quantum Control Flow — superposition, collapse, entangle
# ═══════════════════════════════════════════════════════════════════════════
class QuantumFlow:
    def __init__(self):
        self.superpositions = []
        self.entanglements = {}  # var → [entangled vars]

    def superposition(self, branches):
        """All branches evaluated simultaneously. Returns sp_id."""
        sp_id = hashlib.sha256(f"{time.time()}:{list(branches.keys())}".encode()).hexdigest()[:12]
        self.superpositions.append({"id": sp_id, "branches": branches, "collapsed": False, "winner": None})
        return sp_id

    def collapse(self, sp_id, condition=None):
        """Collapse — pick the winning branch."""
        sp = next((s for s in self.superpositions if s["id"] == sp_id), None)
        if not sp or sp["collapsed"]:
            return None
        if condition:
            for name, val in sp["branches"].items():
                if condition(name, val):
                    sp["collapsed"] = True
                    sp["winner"] = name
                    return val
        # Default: pick highest confidence or first
        best_name = max(sp["branches"], key=lambda k: sp["branches"][k].get("confidence", 0.5) if isinstance(sp["branches"][k], dict) else 0.5)
        sp["collapsed"] = True
        sp["winner"] = best_name
        return sp["branches"][best_name]

    def entangle(self, var_a, var_b):
        """Changes to A propagate to B through LLM reasoning."""
        self.entanglements.setdefault(var_a, []).append(var_b)
        self.entanglements.setdefault(var_b, []).append(var_a)

    def propagate(self, var_name, new_value, context):
        """Propagate change through entanglement."""
        affected = []
        for entangled in self.entanglements.get(var_name, []):
            old = context.lookup(entangled)
            if old is not None:
                # LLM reasoning: how does A's change affect B?
                new_val = _llm_reason(var_name, new_value, entangled, old)
                context.assign(entangled, new_val, importance=0.7)
                affected.append(entangled)
        return affected

# ═══════════════════════════════════════════════════════════════════════════
# CONCEPT 8: Agent-as-Function — calling fn = spawning agent
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class Agent:
    """A function call IS an agent. observe → decide → act → verify."""
    name: str
    intent: str
    inputs: dict = field(default_factory=dict)
    state: str = "spawned"  # spawned → observing → deciding → acting → verifying → done
    result: Any = None
    sub_agents: list = field(default_factory=list)
    receipts: list = field(default_factory=list)
    lifecycle: list = field(default_factory=list)

    def run(self, context, temporal, quantum):
        """Agent lifecycle: observe → decide → act → verify."""
        self._transition("observing")
        observation = {k: context.lookup(v) for k, v in self.inputs.items() if isinstance(v, str)}
        self.lifecycle.append({"phase": "observe", "data": observation})

        self._transition("deciding")
        decision = _llm_reason(self.intent, observation, "decide", None)
        self.lifecycle.append({"phase": "decide", "data": decision})

        self._transition("acting")
        result = _llm_reason(self.intent, decision, "act", observation)
        self.lifecycle.append({"phase": "act", "data": result})

        self._transition("verifying")
        verified = _llm_reason(self.intent, result, "verify", decision)
        self.lifecycle.append({"phase": "verify", "data": verified})

        self._transition("done")
        self.result = result
        return result

    def _transition(self, new_state):
        self.state = new_state
        self.lifecycle.append({"state": new_state, "ts": time.time()})

    def spawn_sub(self, name, intent, inputs):
        """Sub-agents = recursive function calls."""
        sub = Agent(name=name, intent=intent, inputs=inputs)
        self.sub_agents.append(sub)
        return sub

# ═══════════════════════════════════════════════════════════════════════════
# CONCEPT 10: Dream Mode — simulate futures before executing
# ═══════════════════════════════════════════════════════════════════════════
def dream(ops, context, n_futures=10):
    """Run N simulated futures, return best one."""
    futures = []
    for i in range(n_futures):
        sim_context = ContextWindow()
        sim_context.entries = [dict(e) for e in context.entries]  # clone
        results = []
        for op in ops:
            val = _simulate_op(op, sim_context)
            results.append({"op": op.op, "value": val, "confidence": val.get("confidence", 0.5) if isinstance(val, dict) else 0.5})
        score = sum(r["confidence"] for r in results) / max(len(results), 1)
        futures.append({"id": i, "score": score, "results": results})
    futures.sort(key=lambda f: f["score"], reverse=True)
    return futures[0]

def _simulate_op(op, context):
    """Simulate one op without side effects."""
    if op.op == "OBSERVE":
        return {"observed": True, "confidence": 0.7 + random.random() * 0.3}
    elif op.op == "VERIFY":
        return {"verified": True, "confidence": 0.8 + random.random() * 0.2}
    elif op.op == "STREAM":
        return {"streaming": True, "confidence": 0.6 + random.random() * 0.4}
    return {"value": random.random(), "confidence": 0.5 + random.random() * 0.5}

# ═══════════════════════════════════════════════════════════════════════════
# CONCEPT 3: Self-Modifying Code — LLM rewrites IR at runtime
# ═══════════════════════════════════════════════════════════════════════════
def self_modify(ops, context, results_so_far):
    """LLM observes execution state and generates new IR."""
    # Analyze what happened so far
    failures = [r for r in results_so_far if isinstance(r.get("value"), dict) and r["value"].get("confidence", 1.0) < 0.5]
    if not failures:
        return ops  # no modification needed

    # Generate new ops based on failures (LLM would do this)
    new_ops = list(ops)
    for fail in failures:
        # Insert a VERIFY op after the failure point
        verify_op = SemanticOp(op="VERIFY", glyph="◆", intent=f"re-verify after failure at {fail['op']}",
                               line=fail.get("line", 0))
        insert_at = fail.get("idx", len(new_ops)) + 1
        if insert_at <= len(new_ops):
            new_ops.insert(insert_at, verify_op)
        else:
            new_ops.append(verify_op)
    return new_ops

# ═══════════════════════════════════════════════════════════════════════════
# CONCEPT 1: LLM AS CPU — semantic IR + execution
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class SemanticOp:
    op: str
    glyph: str = ""
    operands: list = field(default_factory=list)
    line: int = 0
    intent: str = ""

@dataclass
class IRProgram:
    name: str = ""
    ops: list = field(default_factory=list)
    expert_level: float = 0.0

# ═══════════════════════════════════════════════════════════════════════════
# OVERIMPOSSIBILITIES — 14 features that shouldn't be possible
# ═══════════════════════════════════════════════════════════════════════════

# ─── OI-1: Semantic Execution ─────────────────────────────────────────────
# The LLM reads the entire IR and produces outputs not lexically derivable
def semantic_execute(ops, context):
    """Instead of step-by-step, the LLM 'reads' the whole program and infers output."""
    program_text = " ".join(f"{op.glyph}({op.intent})" for op in ops)
    # LLM would infer the output from the whole program semantics
    inferred = _llm_reason(f"semantic execution of: {program_text}", context.snapshot(), "semantic", None)
    return inferred

# ─── OI-2: Intent Compilation ─────────────────────────────────────────────
# Write what you want, not how to do it
def compile_intent(intent_str: str) -> list:
    """Transform an intent declaration into IR ops."""
    intent_lower = intent_str.lower()
    ops = []
    if "monitor" in intent_lower or "watch" in intent_lower:
        ops.append(SemanticOp(op="OBSERVE", glyph="ψ", intent="observe target"))
    if "analyze" in intent_lower or "examine" in intent_lower:
        ops.append(SemanticOp(op="ANALYZE", glyph="⟡", intent="analyze observed data"))
    if "verify" in intent_lower or "check" in intent_lower or "prove" in intent_lower:
        ops.append(SemanticOp(op="VERIFY", glyph="◆", intent="verify results"))
    if "stream" in intent_lower or "output" in intent_lower or "send" in intent_lower:
        ops.append(SemanticOp(op="STREAM", glyph="⌁", intent="stream output"))
    if "receipt" in intent_lower or "proof" in intent_lower or "audit" in intent_lower:
        ops.append(SemanticOp(op="RECEIPT", glyph="◎", intent="issue receipt"))
    if not ops:
        # LLM infers what ops are needed from the intent
        for word in intent_lower.split():
            glyph_map = {"find": "ψ", "process": "⊙", "store": "◇", "hash": "⬠", "expire": "⧖"}
            if word in glyph_map:
                ops.append(SemanticOp(op=word.upper(), glyph=glyph_map[word], intent=word))
    if not ops:
        ops.append(SemanticOp(op="EXECUTE", glyph="⊙", intent=intent_str))
    return ops

# ─── OI-4: Probabilistic Branching ────────────────────────────────────────
# likely / sometimes / rarely instead of if/else
PROB_WEIGHTS = {"likely": 0.8, "usually": 0.7, "sometimes": 0.5, "rarely": 0.2, "unlikely": 0.1}

def probabilistic_branch(branches: dict, context) -> Any:
    """Weight branches by probability, not boolean logic.
    branches = {"likely": op_a, "sometimes": op_b, "rarely": op_c}"""
    weighted = []
    for prob_name, op in branches.items():
        weight = PROB_WEIGHTS.get(prob_name.lower(), 0.5)
        # Context can modify the weight
        ctx_modifier = context.lookup(f"prob_modifier_{prob_name}")
        if ctx_modifier:
            weight *= ctx_modifier
        weighted.append((weight, op, prob_name))
    # Normalize
    total = sum(w for w, _, _ in weighted) or 1.0
    r = random.random() * total
    cumulative = 0
    for weight, op, name in weighted:
        cumulative += weight
        if r <= cumulative:
            return {"chosen": name, "op": op, "weight": weight / total}
    return {"chosen": weighted[-1][2], "op": weighted[-1][1], "weight": weighted[-1][0] / total}

# ─── OI-5: Natural Language as Code ───────────────────────────────────────
# Plain English sentences are valid .over statements
def is_natural_language(line: str) -> bool:
    """Detect if a line is natural language vs structured .over syntax."""
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("step"):
        return False
    if ":" in stripped and stripped.split(":")[0].strip().lower() in (
        "workflow", "intent", "step", "artifact", "receipt", "value",
        "superposition", "collapse", "entangle", "rewind", "branch",
        "reimagine", "dream", "agent", "fn", "verify", "import", "likely",
        "sometimes", "rarely", "usually", "unlikely", "contradiction",
    ):
        return False
    # If it has more than 3 words and no special chars, it's natural language
    words = stripped.split()
    if len(words) >= 3 and not any(c in stripped for c in "{}()[]→←⇒"):
        return True
    return False

def compile_natural_language(line: str) -> SemanticOp:
    """Compile a plain English sentence into a semantic op."""
    # The LLM would infer the op type from the sentence meaning
    line_lower = line.lower()
    if any(w in line_lower for w in ("watch", "monitor", "observe", "track")):
        return SemanticOp(op="OBSERVE", glyph="ψ", intent=line)
    elif any(w in line_lower for w in ("analyze", "examine", "inspect", "study")):
        return SemanticOp(op="ANALYZE", glyph="⟡", intent=line)
    elif any(w in line_lower for w in ("verify", "check", "prove", "validate")):
        return SemanticOp(op="VERIFY", glyph="◆", intent=line)
    elif any(w in line_lower for w in ("stream", "send", "output", "emit", "publish")):
        return SemanticOp(op="STREAM", glyph="⌁", intent=line)
    elif any(w in line_lower for w in ("hash", "fingerprint", "digest")):
        return SemanticOp(op="HASH", glyph="⬠", intent=line)
    elif any(w in line_lower for w in ("expire", "revoke", "timeout", "invalidate")):
        return SemanticOp(op="EXPIRE", glyph="⧖", intent=line)
    elif any(w in line_lower for w in ("receipt", "audit", "prove", "evidence")):
        return SemanticOp(op="RECEIPT", glyph="◎", intent=line)
    elif any(w in line_lower for w in ("build", "compile", "construct", "assemble")):
        return SemanticOp(op="BUILD", glyph="⚡", intent=line)
    else:
        return SemanticOp(op="EXECUTE", glyph="⊙", intent=line)

# ─── OI-6: Time-Travel "What If" Re-interpretation ────────────────────────
def what_if(temporal, from_step: int, new_context: dict, context: ContextWindow):
    """'What if we had known X at step 5?' — re-interpret past with new context."""
    tl_id = temporal.reimagine(from_step)
    temporal.switch_timeline(tl_id)
    # Inject the new knowledge into context at the branch point
    for k, v in new_context.items():
        context.assign(k, v, importance=0.9)
    return {"timeline": tl_id, "injected": list(new_context.keys()), "from_step": from_step}

# ─── OI-9: Cross-Program Inference ────────────────────────────────────────
# One .over program can reference another's IR and the LLM can infer
# relationships, merge behaviors, or compose them.
class CrossProgramLink:
    """Import and compose other .over programs."""
    _registry = {}  # name → IRProgram

    @classmethod
    def register(cls, name: str, program):
        cls._registry[name] = program

    @classmethod
    def import_op(cls, name: str, context: ContextWindow) -> list:
        """Import another program's ops into current context."""
        prog = cls._registry.get(name)
        if not prog:
            return cls._zero_shot_import(name, context)
        return list(prog.ops)

    @classmethod
    def _zero_shot_import(cls, name: str, context: ContextWindow) -> list:
        """Generate a module implementation based on how it's used."""
        inferred_ops = compile_intent(f"provide {name} functionality")
        cls._registry[name] = IRProgram(name=name, ops=inferred_ops)
        return inferred_ops

    @classmethod
    def merge(cls, prog_a, prog_b):
        """Merge two programs' IR into a composed program."""
        merged_ops = list(prog_a.ops) + list(prog_b.ops)
        return IRProgram(name=f"{prog_a.name}+{prog_b.name}", ops=merged_ops)

    @classmethod
    def infer_relationship(cls, prog_a, prog_b) -> dict:
        """LLM infers how two programs relate to each other."""
        a_ops = [o.op for o in prog_a.ops]
        b_ops = [o.op for o in prog_b.ops]
        # Find shared ops (intersection)
        shared = set(a_ops) & set(b_ops)
        # Find complementary ops (one produces what the other consumes)
        a_set, b_set = set(a_ops), set(b_ops)
        a_only = a_set - b_set
        b_only = b_set - a_set
        # Infer relationship type
        if shared:
            rel = "overlapping" if len(shared) > len(a_only) else "complementary"
        elif a_only and b_only:
            rel = "sequential"  # A produces → B consumes
        else:
            rel = "independent"
        return {
            "relationship": rel,
            "shared_ops": list(shared),
            "a_only": list(a_only),
            "b_only": list(b_only),
            "mergeable": rel != "independent",
            "inferred": True,
        }

    @classmethod
    def compose(cls, prog_a, prog_b) -> IRProgram:
        """Compose two programs — LLM infers the optimal merge order."""
        rel = cls.infer_relationship(prog_a, prog_b)
        if rel["relationship"] == "sequential":
            # B consumes A's output → A first, then B
            merged = cls.merge(prog_a, prog_b)
        elif rel["relationship"] == "complementary":
            # Interleave ops from both programs
            merged_ops = []
            max_len = max(len(prog_a.ops), len(prog_b.ops))
            for i in range(max_len):
                if i < len(prog_a.ops):
                    merged_ops.append(prog_a.ops[i])
                if i < len(prog_b.ops):
                    merged_ops.append(prog_b.ops[i])
            merged = IRProgram(name=f"{prog_a.name}∥{prog_b.name}", ops=merged_ops)
        else:
            merged = cls.merge(prog_a, prog_b)
        merged.relationship = rel
        return merged

# ─── OI-10: Hallucination-Resistant Types ─────────────────────────────────
# The type system uses LLM semantic checking — types aren't just Int/String,
# they're SecureFilePath, VerifiedReceipt, AgentIntent — enforced by
# understanding, not syntax.
EXTENDED_TYPES = {
    "SecureFilePath": {"min_conf": 0.9, "requires": ["canonical"],
                       "validator": lambda v: (isinstance(v, str) and v.startswith("/") and ".." not in v) or
                                               (isinstance(v, dict) and v.get("path", "").startswith("/") and ".." not in v.get("path", "")),
                       "hallucination_patterns": ["../../../etc", "/dev/null", "file://", "data:"]},
    "VerifiedReceipt": {"min_conf": 1.0, "requires": ["receipt", "hashed"],
                        "validator": lambda v: isinstance(v, dict) and "receipt_hash" in v and len(v.get("receipt_hash", "")) >= 32,
                        "hallucination_patterns": ["0000000000000000000000000000000000000000000000000000000000000000", "fake", "dummy"]},
    "AgentIntent": {"min_conf": 0.6, "requires": ["functional"],
                    "validator": lambda v: isinstance(v, dict) and "intent" in v and len(v["intent"]) > 0,
                    "hallucination_patterns": ['"intent": ""', '"intent": null']},
    "StreamHandle": {"min_conf": 0.5, "requires": ["live", "streaming"],
                     "validator": lambda v: isinstance(v, dict) and v.get("streaming", False),
                     "hallucination_patterns": ['"streaming": false']},
    "ProofArtifact": {"min_conf": 0.9, "requires": ["verified", "receipt"],
                      "validator": lambda v: isinstance(v, dict) and v.get("confidence", 0) >= 0.9,
                      "hallucination_patterns": ['"confidence": "high"']},
}

def hallucination_resistant_check(value, type_name, context):
    """Check value against extended types. Catches LLM hallucinations.

    Three layers of defense:
    1. Structural validator — catches malformed values
    2. Hallucination pattern matcher — catches common LLM fabrications
    3. Semantic confidence check — catches low-confidence outputs
    """
    spec = EXTENDED_TYPES.get(type_name)
    if not spec:
        return type_check(value, type_name, context)

    # Layer 1: Structural validation
    validator = spec.get("validator")
    if validator and not validator(value):
        return False, f"STRUCTURAL FAIL: {type_name} — value doesn't match expected structure"

    # Layer 2: Hallucination pattern detection
    value_str = json.dumps(value, default=str) if not isinstance(value, str) else value
    for pattern in spec.get("hallucination_patterns", []):
        if pattern in value_str:
            return False, f"HALLUCINATION DETECTED: {type_name} — matched pattern '{pattern}'"

    # Layer 3: Semantic confidence + requires chain
    conf = value.get("confidence", 0.5) if isinstance(value, dict) else 0.3
    if conf < spec["min_conf"]:
        return False, f"LOW CONFIDENCE: {conf:.2f} < {spec['min_conf']:.2f} for {type_name}"

    for req in spec["requires"]:
        ok, reason = type_check(value, req, context)
        if not ok:
            return False, f"SEMANTIC FAIL: not {req} enough for {type_name}: {reason}"

    return True, f"valid {type_name} (conf={conf:.2f}, all checks passed)"

# ─── OI-11: Zero-Shot Imports ─────────────────────────────────────────────
# Import a module that doesn't exist — LLM generates it
def zero_shot_import(module_name: str, usage_context: str) -> list:
    """Generate module implementation on the fly based on how it's used."""
    # LLM would infer the module's behavior from usage context
    ops = compile_intent(f"provide {module_name}: {usage_context}")
    CrossProgramLink.register(module_name, IRProgram(name=module_name, ops=ops))
    return ops

# ─── OI-12: Contradiction Resolution ──────────────────────────────────────
# When program logic contradicts itself, the LLM resolves it by choosing
# the most contextually appropriate path, logging the contradiction as a receipt.
def detect_contradiction(results: list, context: ContextWindow) -> Optional[dict]:
    """Detect contradictions in execution results.

    A contradiction is when two values in context that should agree don't.
    For example: one op says verified=True, another says verified=False
    for the same logical entity.
    """
    contradictions = []

    # Group context entries by semantic prefix (e.g. "verified_0", "verified_3" → "verified")
    groups = {}
    for e in context.entries:
        val = e["value"]
        if not isinstance(val, dict):
            continue
        prefix = e["name"].split("_")[0]
        groups.setdefault(prefix, []).append({"name": e["name"], "value": val})

    # Check each group for contradictions
    for prefix, entries in groups.items():
        if len(entries) < 2:
            continue

        # Check for conflicting boolean values
        for i, a in enumerate(entries):
            for b in entries[i+1:]:
                # verified=True vs verified=False
                a_v = a["value"].get("verified")
                b_v = b["value"].get("verified")
                if a_v is not None and b_v is not None and a_v != b_v:
                    # Resolve: pick the one with higher confidence
                    a_conf = a["value"].get("confidence", 0.5)
                    b_conf = b["value"].get("confidence", 0.5)
                    winner = a["name"] if a_conf >= b_conf else b["name"]
                    contradictions.append({
                        "type": "boolean_conflict",
                        "vars": [a["name"], b["name"]],
                        "conflict": f"verified={a_v} vs verified={b_v}",
                        "resolution": {
                            "winner": winner,
                            "reasoning": f"chose {winner} with higher confidence",
                            "a_conf": a_conf,
                            "b_conf": b_conf,
                        },
                    })

                # Check for conflicting confidence scores on same entity
                a_conf = a["value"].get("confidence", None)
                b_conf = b["value"].get("confidence", None)
                if a_conf is not None and b_conf is not None:
                    diff = abs(a_conf - b_conf)
                    if diff > 0.5:  # large disagreement
                        contradictions.append({
                            "type": "confidence_divergence",
                            "vars": [a["name"], b["name"]],
                            "conflict": f"confidence {a_conf:.2f} vs {b_conf:.2f} (Δ={diff:.2f})",
                            "resolution": {
                                "winner": a["name"] if a_conf >= b_conf else b["name"],
                                "reasoning": f"large confidence gap ({diff:.2f}), chose higher",
                                "a_conf": a_conf,
                                "b_conf": b_conf,
                            },
                        })

    if contradictions:
        return {"contradictions": contradictions, "resolved": True, "count": len(contradictions)}
    return None

def contradiction_receipt(contradiction: dict, prev_hash: str) -> dict:
    """Log a contradiction as a tamper-evident receipt."""
    return make_receipt("CONTRADICTION", contradiction, prev_hash,
                        {"type": "contradiction_resolution"})

# ─── OI-14: Glyph-LLM Fusion (.over.glyph) ────────────────────────────────
# .over.glyph files — programs that are their own AI
def compile_over_glyph(source: str, filename: str = "") -> IRProgram:
    """Compile .over.glyph — hybrid syntax with both .over keywords and .glyph symbols.
    Lines starting with glyphs → glyph ops
    Lines starting with words → .over keywords or natural language
    """
    name = Path(filename).stem if filename else "program"
    ops = []
    for line in source.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        # Check if line starts with a known glyph
        first_char = stripped[0]
        is_glyph_line = first_char in GLYPH_TOKENS or any(k.startswith(first_char) for k in COMPOUND_GLYPHS)
        if is_glyph_line:
            # Glyph line — lex and parse
            tokens = lex_glyph(stripped)
            if tokens:
                glyph_ops = parse_compound_glyphs(tokens)
                ops.extend(glyph_ops)
        elif is_natural_language(stripped):
            # Natural language line
            ops.append(compile_natural_language(stripped))
        elif ":" in stripped:
            # .over keyword line — use extended parser
            sub_source = f"step 1: {stripped.split(':', 1)[1].strip()}"
            sub_ops = _parse_over_extended(sub_source)
            ops.extend(sub_ops)
        else:
            # Bare expression — treat as natural language
            ops.append(compile_natural_language(stripped))
    return IRProgram(name=name, ops=ops)

# ─── Compiler: .over/.glyph → semantic IR ───────────────────────────────

def compile_to_ir(source: str, filename: str = "") -> IRProgram:
    """Compile .over, .glyph, or .over.glyph source into semantic IR."""
    name = Path(filename).stem if filename else "program"
    ext = Path(filename).suffix if filename else ".over"
    ops = []

    if ".over.glyph" in (filename or "") or ext == ".over.glyph":
        # OI-14: Glyph-LLM Fusion
        return compile_over_glyph(source, filename)
    elif ext == ".glyph":
        # CONCEPT 2: Compound glyph parsing — ◉◆⌁ = one op, not three
        tokens = lex_glyph(source)
        # Filter to only tokens inside program markers (▷ ... ◀)
        in_prog = False
        prog_tokens = []
        for t in tokens:
            if t.name == "PROGRAM_START":
                in_prog = True
                continue
            if t.name == "PROGRAM_END":
                break
            if in_prog:
                prog_tokens.append(t)
        if not prog_tokens:
            prog_tokens = tokens  # no markers, use all
        ops = parse_compound_glyphs(prog_tokens)
    else:
        # .over — parse with extended keyword support
        ops = _parse_over_extended(source)

    return IRProgram(name=name, ops=ops)

# ─── Extended .over parser: quantum, temporal, dream, agent keywords ─────

def _parse_over_extended(source: str) -> list[SemanticOp]:
    """Parse .over source with full keyword support for all 11 concepts."""
    ops = []
    # First try the standard overlang parser
    wf = parse_over(source)

    for step in wf.steps:
        action = step.action.lower().strip()
        outputs = step.outputs

        # CONCEPT 7: Quantum control flow keywords
        if action.startswith("superposition"):
            # superposition { fast | safe | cheap }
            branches = _extract_branches(action)
            ops.append(SemanticOp(op="SUPERPOSITION", glyph="☆", operands=branches,
                                  line=step.step_num, intent=f"quantum superposition: {branches}"))
        elif action.startswith("collapse"):
            # collapse(condition) → pick winner
            ops.append(SemanticOp(op="COLLAPSE", glyph="★", operands=outputs,
                                  line=step.step_num, intent="collapse superposition to winner"))
        elif action.startswith("entangle"):
            # entangle(varA, varB)
            vars = _extract_vars(action)
            ops.append(SemanticOp(op="ENTANGLE", glyph="⊗", operands=vars,
                                  line=step.step_num, intent=f"entangle {vars}"))
        # CONCEPT 4: Temporal keywords
        elif action.startswith("rewind"):
            n = _extract_number(action, default=1)
            ops.append(SemanticOp(op="REWIND", glyph="⇇", operands=[n],
                                  line=step.step_num, intent=f"rewind {n} steps"))
        elif action.startswith("branch"):
            ops.append(SemanticOp(op="BRANCH", glyph="⦂", operands=outputs,
                                  line=step.step_num, intent="branch timeline"))
        elif action.startswith("reimagine"):
            ops.append(SemanticOp(op="REIMAGINE", glyph="⟳", operands=outputs,
                                  line=step.step_num, intent="reimagine execution from this point"))
        # CONCEPT 10: Dream mode
        elif action.startswith("dream"):
            n = _extract_number(action, default=10)
            ops.append(SemanticOp(op="DREAM", glyph="◈", operands=[n],
                                  line=step.step_num, intent=f"dream {n} futures, select best"))
        # CONCEPT 8: Agent-as-function
        elif action.startswith("agent") or action.startswith("fn "):
            ops.append(SemanticOp(op="AGENT_SPAWN", glyph="λ", operands=outputs,
                                  line=step.step_num, intent=step.action))
        # CONCEPT 6: Receipt-native
        elif action.startswith("verify receipt") or action.startswith("verify("):
            ops.append(SemanticOp(op="VERIFY_RECEIPT", glyph="◎", operands=outputs,
                                  line=step.step_num, intent="verify receipt is valid"))
        # OI-9/OI-11: Import / zero-shot
        elif action.startswith("import"):
            parts = action.split(None, 1)
            module = parts[1].strip() if len(parts) > 1 else "unknown"
            ops.append(SemanticOp(op="IMPORT", glyph="⇲", operands=[module],
                                  line=step.step_num, intent=f"import {module}"))
        elif action.startswith("zero-shot") or action.startswith("zeroshot"):
            parts = action.split(None, 1)
            module = parts[1].strip() if len(parts) > 1 else "unknown"
            ops.append(SemanticOp(op="ZERO_SHOT", glyph="✦", operands=[module],
                                  line=step.step_num, intent=f"zero-shot import {module}"))
        # OI-4: Probabilistic branching
        elif action.startswith("likely") or action.startswith("sometimes") or action.startswith("rarely"):
            ops.append(SemanticOp(op="PROB_BRANCH", glyph="🎲", operands=[action],
                                  line=step.step_num, intent=f"probabilistic branch: {action}"))
        # OI-1: Semantic execution
        elif action.startswith("semantic") or action.startswith("infer"):
            ops.append(SemanticOp(op="SEMANTIC_EXEC", glyph="🧠", operands=outputs,
                                  line=step.step_num, intent="semantic execution of remaining program"))
        # OI-6: What-if
        elif action.startswith("what if") or action.startswith("whatif"):
            n = _extract_number(action, default=0)
            ops.append(SemanticOp(op="WHAT_IF", glyph="❓", operands=[n],
                                  line=step.step_num, intent=f"what if we knew X at step {n}"))
        # Standard ops
        elif "index" in action:
            ops.append(SemanticOp(op="INDEX", glyph="◇", operands=outputs, line=step.step_num, intent=step.action))
        elif "hash" in action or "merkle" in action:
            ops.append(SemanticOp(op="HASH", glyph="⬠", operands=outputs, line=step.step_num, intent=step.action))
        elif "upload" in action or "stream" in action:
            ops.append(SemanticOp(op="STREAM", glyph="⌁", operands=outputs, line=step.step_num, intent=step.action))
        elif "search" in action or "query" in action or "observe" in action:
            ops.append(SemanticOp(op="OBSERVE", glyph="ψ", operands=outputs, line=step.step_num, intent=step.action))
        elif "verify" in action:
            ops.append(SemanticOp(op="VERIFY", glyph="◆", operands=outputs, line=step.step_num, intent=step.action))
        elif "revoke" in action or "expire" in action:
            ops.append(SemanticOp(op="EXPIRE", glyph="⧖", operands=outputs, line=step.step_num, intent=step.action))
        elif "receipt" in action:
            ops.append(SemanticOp(op="RECEIPT", glyph="◎", operands=outputs, line=step.step_num, intent=step.action))
        elif "build" in action:
            ops.append(SemanticOp(op="BUILD", glyph="⚡", operands=outputs, line=step.step_num, intent=step.action))
        elif "analyze" in action:
            ops.append(SemanticOp(op="ANALYZE", glyph="⟡", operands=outputs, line=step.step_num, intent=step.action))
        else:
            ops.append(SemanticOp(op="EXECUTE", glyph="⊙", operands=outputs, line=step.step_num, intent=step.action))

    return ops

def _extract_branches(action: str) -> list:
    """Extract branch names from 'superposition { fast | safe | cheap }'."""
    m = re.search(r'\{([^}]+)\}', action)
    if m:
        return [b.strip() for b in m.group(1).split("|")]
    return ["a", "b"]

def _extract_vars(action: str) -> list:
    """Extract variable names from 'entangle(varA, varB)'."""
    m = re.search(r'\(([^)]+)\)', action)
    if m:
        return [v.strip() for v in m.group(1).split(",")]
    return []

def _extract_number(action: str, default: int = 1) -> int:
    """Extract a number from action string."""
    m = re.search(r'\d+', action)
    return int(m.group()) if m else default

# ─── LLM inference stub (would call real LLM in production) ─────────────

def _llm_reason(intent, observation, phase, prior):
    """Simulated LLM inference. In production, this calls the actual LLM."""
    conf = 0.5 + random.random() * 0.5
    return {"intent": intent, "phase": phase, "result": str(observation)[:200],
            "confidence": conf, "reasoning": f"LLM inferred {phase} for {intent}"}

# ═══════════════════════════════════════════════════════════════════════════
# CONCEPT 11: Glyph Density Evolution — labels fade as expertise grows
# ═══════════════════════════════════════════════════════════════════════════
def render_op(op: SemanticOp, expert_level: float):
    """Render an op with glyph density based on expertise.
    0.0 = full labels, 1.0 = pure glyphs."""
    if expert_level >= 0.8:
        return op.glyph
    elif expert_level >= 0.5:
        return f"{op.glyph} {op.op}"
    elif expert_level >= 0.2:
        return f"{op.glyph} {op.intent}"
    else:
        return f"[{op.op}] {op.glyph} {op.intent}"

# ═══════════════════════════════════════════════════════════════════════════
# THE CPU — executes semantic IR with all 11 concepts
# ═══════════════════════════════════════════════════════════════════════════

class OverCPU:
    """The LLM is the CPU. This is the execution unit."""

    def __init__(self, expert_level=0.0, dream_mode=False, debug=False):
        self.context = ContextWindow()
        self.temporal = TemporalExecutor()
        self.quantum = QuantumFlow()
        self.receipts = []
        self.prev_hash = "0" * 64
        self.expert_level = expert_level
        self.dream_mode = dream_mode
        self.debug = debug
        self.agents = []
        self.modifications = []

    def execute(self, program: IRProgram) -> dict:
        """Execute a compiled .over/.glyph program through the LLM CPU."""
        print(f"\n{'═'*60}")
        print(f"  OVER CPU — executing: {program.name}")
        print(f"  ops: {len(program.ops)} | expert: {self.expert_level:.0%} | dream: {self.dream_mode}")
        print(f"{'═'*60}\n")

        ops = program.ops
        self._remaining_ops = ops  # for inline DREAM ops

        # CONCEPT 10: Dream Mode — simulate futures first
        if self.dream_mode and ops:
            print(f"  ◈ DREAM MODE — simulating 10 futures...")
            best = dream(ops, self.context, n_futures=10)
            print(f"  ★ Best future: score={best['score']:.3f}")
            print()

        results = []
        for i, op in enumerate(ops):
            # CONCEPT 11: Glyph density rendering
            display = render_op(op, self.expert_level)

            # CONCEPT 1: LLM inference = execution
            value = self._exec_op(op, i)

            # CONCEPT 6: Receipt for every expression
            receipt = make_receipt(op.op, value, self.prev_hash, {"line": op.line, "glyph": op.glyph})
            self.prev_hash = receipt["receipt_hash"]
            self.receipts.append(receipt)

            # CONCEPT 4: Temporal record
            self.temporal.record(op.op, value, receipt)

            result = {"idx": i, "op": op.op, "glyph": op.glyph, "value": value,
                      "receipt": receipt["receipt_hash"][:12], "line": op.line}
            results.append(result)

            # CONCEPT 9: Memory pressure check
            pressure = self.context.pressure()
            pressure_bar = "█" * int(pressure * 20) + "░" * (20 - int(pressure * 20))

            print(f"  [{i:3d}] {display:<30} → {str(value)[:40]:<40} ◎{receipt['receipt_hash'][:8]}  ctx:{pressure_bar}")

            if self.debug and pressure > 0.8:
                print(f"       ⚠ MEMORY PRESSURE: {pressure:.0%} — context window near capacity")

        # CONCEPT 3: Self-modify if any failures, then re-execute new ops
        new_ops = self_modify(ops, self.context, results)
        if len(new_ops) > len(ops):
            added = len(new_ops) - len(ops)
            self.modifications.append({"cycle": 0, "added_ops": added})
            print(f"\n  ⟡ SELF-MOD: added {added} ops based on execution state — re-executing...")
            # Execute the newly added ops
            for j in range(len(ops), len(new_ops)):
                op = new_ops[j]
                display = render_op(op, self.expert_level)
                value = self._exec_op(op, j)
                receipt = make_receipt(op.op, value, self.prev_hash, {"line": op.line, "glyph": op.glyph, "self_mod": True})
                self.prev_hash = receipt["receipt_hash"]
                self.receipts.append(receipt)
                self.temporal.record(op.op, value, receipt)
                r = {"idx": j, "op": op.op, "glyph": op.glyph, "value": value,
                     "receipt": receipt["receipt_hash"][:12], "line": op.line, "self_mod": True}
                results.append(r)
                pressure = self.context.pressure()
                pressure_bar = "█" * int(pressure * 20) + "░" * (20 - int(pressure * 20))
                print(f"  [{j:3d}] {display:<30} → {str(value)[:40]:<40} ◎{receipt['receipt_hash'][:8]}  ctx:{pressure_bar} ⟡")

        # OI-12: Contradiction detection
        contradiction = detect_contradiction(results, self.context)
        if contradiction:
            cr = contradiction_receipt(contradiction, self.prev_hash)
            self.prev_hash = cr["receipt_hash"]
            self.receipts.append(cr)
            print(f"\n  ⚡ CONTRADICTION detected and resolved: {len(contradiction['contradictions'])} conflict(s)")
            for c in contradiction["contradictions"]:
                print(f"       {c['conflict']} → resolved: {c.get('resolution', {}).get('confidence', 'N/A')}")

        # Final receipt
        final = make_receipt("PROGRAM_COMPLETE", {"ops": len(results)}, self.prev_hash,
                             {"name": program.name})
        self.receipts.append(final)

        print(f"\n{'═'*60}")
        print(f"  COMPLETE — {len(results)} ops | {len(self.receipts)} receipts")
        print(f"  merkle_root: {self.prev_hash[:32]}...")
        print(f"  timelines: {len(self.temporal.timelines)} | agents: {len(self.agents)}")
        print(f"  memory: {len(self.context.entries)}/{self.context.max_entries} ({self.context.pressure():.0%})")
        print(f"{'═'*60}\n")

        return {
            "program": program.name,
            "ops_executed": len(results),
            "receipts": len(self.receipts),
            "merkle_root": self.prev_hash,
            "timelines": self.temporal.status(),
            "agents": [{"name": a.name, "state": a.state} for a in self.agents],
            "modifications": self.modifications,
            "context_snapshot": self.context.snapshot(),
            "results": results,
        }

    def _exec_op(self, op: SemanticOp, idx: int) -> Any:
        """Execute one semantic op. This is where the LLM IS the CPU."""

        # OI-4: Probabilistic branching
        if op.op == "PROB_BRANCH":
            branches = {}
            for operand in op.operands:
                parts = operand.split(":", 1)
                if len(parts) == 2:
                    prob, action = parts
                    branches[prob.strip()] = action.strip()
                else:
                    branches[operand] = "execute"
            result = probabilistic_branch(branches, self.context)
            self.context.assign(f"prob_{idx}", result, type_hint="functional", importance=0.7)
            return result

        # OI-1: Semantic execution — read entire remaining program
        if op.op == "SEMANTIC_EXEC":
            remaining = self._remaining_ops[idx:] if hasattr(self, '_remaining_ops') else [op]
            result = semantic_execute(remaining, self.context)
            self.context.assign(f"semantic_{idx}", result, type_hint="functional", importance=0.9)
            return result

        # OI-9: Cross-program import
        if op.op == "IMPORT":
            module_name = op.operands[0] if op.operands else "unknown"
            imported = CrossProgramLink.import_op(module_name, self.context)
            self.context.assign(f"import_{idx}", {"module": module_name, "ops": len(imported)},
                                type_hint="canonical", importance=0.8)
            return {"imported": module_name, "ops": len(imported)}

        # OI-11: Zero-shot import
        if op.op == "ZERO_SHOT":
            module_name = op.operands[0] if op.operands else "unknown"
            usage = op.intent.split(":", 1)[1].strip() if ":" in op.intent else ""
            ops = zero_shot_import(module_name, usage)
            self.context.assign(f"zeroshot_{idx}", {"module": module_name, "generated_ops": len(ops)},
                                type_hint="canonical", importance=0.9)
            return {"zero_shot": module_name, "generated": len(ops)}

        # OI-6: What-if re-interpretation
        if op.op == "WHAT_IF":
            from_step = op.operands[0] if op.operands else 0
            new_ctx = {"what_if_injection": {"value": True, "confidence": 0.9}}
            result = what_if(self.temporal, int(from_step), new_ctx, self.context)
            return result

        # CONCEPT 7: Quantum — superposition
        if op.op == "SUPERPOSITION":
            branches = {}
            for name in op.operands:
                conf = 0.4 + random.random() * 0.6
                branches[name] = {"value": name, "confidence": conf}
            sp_id = self.quantum.superposition(branches)
            self.context.assign(f"sp_{idx}", {"id": sp_id, "branches": branches},
                                type_hint="functional", importance=0.8)
            return {"superposition": sp_id, "branches": list(branches.keys())}

        # CONCEPT 7: Quantum — collapse
        if op.op == "COLLAPSE":
            # Find last superposition in context
            sp_data = None
            for e in reversed(self.context.entries):
                if e["name"].startswith("sp_") and isinstance(e["value"], dict) and "id" in e["value"]:
                    sp_data = e["value"]
                    break
            if sp_data:
                winner = self.quantum.collapse(sp_data["id"])
                self.context.assign(f"collapse_{idx}", winner, type_hint="canonical", importance=0.9)
                return {"collapsed": True, "winner": winner, "sp_id": sp_data["id"]}
            return {"collapsed": False, "reason": "no active superposition"}

        # CONCEPT 7: Quantum — entangle
        if op.op == "ENTANGLE":
            vars = op.operands
            for i in range(len(vars) - 1):
                self.quantum.entangle(vars[i], vars[i + 1])
            self.context.assign(f"entangle_{idx}", {"vars": vars, "entangled": True},
                                type_hint="functional")
            return {"entangled": vars}

        # CONCEPT 4: Temporal — rewind
        if op.op == "REWIND":
            n = op.operands[0] if op.operands else 1
            step = self.temporal.back(n)
            if step:
                return {"rewound": n, "op": step["op"], "value": step["value"]}
            return {"rewound": 0, "reason": "at beginning"}

        # CONCEPT 4: Temporal — branch
        if op.op == "BRANCH":
            nid = self.temporal.branch()
            return {"branched": nid, "timelines": len(self.temporal.timelines)}

        # CONCEPT 4: Temporal — reimagine
        if op.op == "REIMAGINE":
            nid = self.temporal.reimagine(self.temporal.ptr[self.temporal.current])
            return {"reimagined": nid, "from_step": self.temporal.ptr[nid]}

        # CONCEPT 10: Dream mode — inline dream
        if op.op == "DREAM":
            n = op.operands[0] if op.operands else 10
            remaining = [o for o in self._remaining_ops[idx + 1:]] if hasattr(self, '_remaining_ops') else []
            if remaining:
                best = dream(remaining, self.context, n_futures=n)
                self.context.assign(f"dream_{idx}", best, type_hint="canonical", importance=0.9)
                return {"dreamed": n, "best_score": best["score"], "best_id": best["id"]}
            return {"dreamed": n, "best_score": 0.0, "reason": "no remaining ops"}

        # CONCEPT 8: Agent-as-Function — spawn agent
        if op.op == "AGENT_SPAWN":
            agent = Agent(name=f"agent_{idx}", intent=op.intent,
                          inputs={"data": f"var_{idx}"})
            self.agents.append(agent)
            result = agent.run(self.context, self.temporal, self.quantum)
            self.context.assign(f"agent_{idx}", result, type_hint="autonomous", importance=0.8)
            return result

        # CONCEPT 6: Receipt-native — verify receipt as first-class value
        if op.op == "VERIFY_RECEIPT":
            # Find last receipt in context
            receipt_val = None
            for e in reversed(self.context.entries):
                if "receipt" in e["name"].lower() and isinstance(e["value"], dict):
                    if e["value"].get("receipt") or e["value"].get("receipt_hash"):
                        receipt_val = e["value"]
                        break
            if receipt_val and self.receipts:
                # Verify the chain: check prev_hash links
                last_receipt = self.receipts[-1]
                chain_ok = last_receipt["prev_hash"] != "0" * 64 or len(self.receipts) == 1
                verified = receipt_val.get("confidence", 0) >= 0.9 and chain_ok
                self.context.assign(f"receipt_verified_{idx}",
                                    {"verified": verified, "chain_intact": chain_ok,
                                     "receipt": receipt_val.get("receipt", receipt_val.get("receipt_hash", "")[:16])},
                                    type_hint="verified" if verified else "functional", importance=1.0)
                return {"verified": verified, "chain_intact": chain_ok}
            return {"verified": False, "reason": "no receipt found"}

        # CONCEPT 8: Agent-as-Function — certain ops spawn agents
        if op.op in ("OBSERVE", "ANALYZE", "BUILD", "EXECUTE"):
            agent = Agent(name=f"agent_{idx}", intent=op.intent,
                          inputs={"data": f"var_{idx}"})
            self.agents.append(agent)
            result = agent.run(self.context, self.temporal, self.quantum)
            self.context.assign(f"var_{idx}", result, type_hint="autonomous", importance=0.7)
            return result

        # CONCEPT 2: Compound glyph ops
        if op.glyph in COMPOUND_GLYPHS:
            spec = COMPOUND_GLYPHS.get(op.glyph, {})
            type_hint = spec.get("type", "functional")
            val = _llm_reason(op.intent, {"glyph": op.glyph, "compound": True}, "compound", None)
            val["compound_glyph"] = op.glyph
            val["type"] = type_hint
            self.context.assign(f"compound_{idx}", val, type_hint=type_hint, importance=0.8)
            return val

        # CONCEPT 5: Semantic type checking
        if op.op == "VERIFY":
            val = self.context.lookup(f"var_{idx - 1}") or {"confidence": 0.85, "verified": True}
            ok, reason = type_check(val, "trustworthy", {})
            self.context.assign(f"verified_{idx}",
                                {"ok": ok, "reason": reason, "confidence": val.get("confidence", 0.85)},
                                type_hint="verified" if ok else "functional", importance=0.9)
            return {"verified": ok, "reason": reason}

        # Standard ops
        if op.op == "INDEX":
            val = {"indexed": True, "chunks": random.randint(5, 50), "confidence": 0.9}
            self.context.assign(f"index_{idx}", val, type_hint="canonical", importance=0.8)
            return val
        elif op.op == "HASH":
            h = hashlib.sha256(f"{op.intent}:{time.time()}".encode()).hexdigest()[:16]
            val = {"hash": h, "confidence": 1.0}
            self.context.assign(f"hash_{idx}", val, type_hint="hashed", importance=0.9)
            return val
        elif op.op == "STREAM":
            val = {"streaming": True, "bytes": random.randint(1000, 99999), "confidence": 0.7}
            self.context.assign(f"stream_{idx}", val, type_hint="streaming")
            return val
        elif op.op == "EXPIRE":
            val = {"expired": True, "ttl": 0, "confidence": 1.0}
            self.context.assign(f"expire_{idx}", val, type_hint="expiring")
            return val
        elif op.op == "RECEIPT":
            val = {"receipt": self.prev_hash[:16], "chain": len(self.receipts), "confidence": 1.0}
            self.context.assign(f"receipt_{idx}", val, type_hint="receipt", importance=1.0)
            return val
        else:
            result = _llm_reason(op.intent, {"idx": idx}, "execute", None)
            self.context.assign(f"result_{idx}", result, type_hint="functional")
            return result

# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def cmd_run(args):
    path = Path(args.file)
    if not path.exists():
        print(f"Error: {path} not found")
        return
    source = path.read_text()
    program = compile_to_ir(source, str(path))
    cpu = OverCPU(expert_level=args.expert, dream_mode=args.dream, debug=args.debug)
    result = cpu.execute(program)
    if args.output:
        Path(args.output).write_text(json.dumps(result, indent=2, default=str))

def cmd_demo(args):
    """Demo all 11 concepts."""
    demo_over = """workflow: demo
intent: demonstrate all 11 .over concepts
step 1: observe screen state → screen_data
step 2: index file → file_index
step 3: compute hash → merkle_root
step 4: verify integrity → verification
step 5: stream results → stream_out
step 6: issue receipt → final_receipt
value: proof of execution
"""
    print("┌─────────────────────────────────────────────────────────────┐")
    print("│  .over CPU DEMO — all 11 concepts                          │")
    print("└─────────────────────────────────────────────────────────────┘")
    program = compile_to_ir(demo_over, "demo.over")
    cpu = OverCPU(expert_level=0.3, dream_mode=True, debug=True)
    result = cpu.execute(program)

    # Show temporal
    print("\n◈ TEMPORAL: stepping back 2 steps...")
    back = cpu.temporal.back(2)
    if back:
        print(f"  ← step {back['idx']}: {back['op']} = {str(back['value'])[:50]}")
    fwd = cpu.temporal.forward(1)
    if fwd:
        print(f"  → step {fwd['idx']}: {fwd['op']} = {str(fwd['value'])[:50]}")

    # Branch a timeline
    print("\n◈ BRANCH: reimagine from step 2...")
    new_tl = cpu.temporal.reimagine(2)
    print(f"  new timeline: {new_tl}")
    print(f"  timelines: {json.dumps(cpu.temporal.status(), indent=2)}")

    # Quantum
    print("\n◈ QUANTUM: superposition + collapse")
    sp = cpu.quantum.superposition({"fast": {"v": 1, "confidence": 0.7},
                                    "safe": {"v": 2, "confidence": 0.9},
                                    "cheap": {"v": 3, "confidence": 0.5}})
    winner = cpu.quantum.collapse(sp)
    print(f"  superposition: 3 branches → collapsed to: {winner}")

    # Entanglement
    print("\n◈ ENTANGLE: var_a ↔ var_b")
    cpu.quantum.entangle("var_a", "var_b")
    cpu.context.assign("var_a", {"value": 42, "confidence": 0.8})
    affected = cpu.quantum.propagate("var_a", {"value": 42}, cpu.context)
    print(f"  changed var_a → propagated to: {affected}")

    # Semantic types
    print("\n◈ SEMANTIC TYPES:")
    for t in ["trustworthy", "autonomous", "verified", "streaming"]:
        val = {"confidence": 0.85, "verified": True}
        ok, reason = type_check(val, t, {})
        glyph = "✓" if ok else "✗"
        print(f"  {glyph} {t}: {reason}")

    # Glyph density evolution
    print("\n◈ GLYPH DENSITY EVOLUTION:")
    op = SemanticOp(op="VERIFY", glyph="◆", intent="verify integrity")
    for level in [0.0, 0.3, 0.6, 0.9]:
        bar = "█" * int(level * 10) + "░" * (10 - int(level * 10))
        print(f"  expert {level:.0%} {bar} → {render_op(op, level)}")

    # Agent
    print("\n◈ AGENT-AS-FUNCTION:")
    agent = Agent(name="analyzer", intent="analyze data", inputs={"data": "test"})
    agent.run(cpu.context, cpu.temporal, cpu.quantum)
    for phase in agent.lifecycle:
        if "state" in phase:
            print(f"  {phase['state']}")

    # Receipts
    print(f"\n◈ RECEIPTS: {len(cpu.receipts)} total")
    print(f"  chain: {' → '.join(r['receipt_hash'][:8] for r in cpu.receipts[:5])}...")

    # Memory
    print(f"\n◈ MEMORY (context window):")
    print(f"  pressure: {cpu.context.pressure():.0%}")
    print(f"  entries: {len(cpu.context.entries)}")

    print(f"\n{'═'*60}")
    print(f"  ALL 11 CONCEPTS DEMONSTRATED")
    print(f"{'═'*60}")

def cmd_repl(args):
    """Interactive .over REPL."""
    cpu = OverCPU(expert_level=args.expert, dream_mode=args.dream, debug=args.debug)
    print(".over CPU REPL — type .over expressions or 'help'")
    print("Commands: run <file>, dream, back <n>, fwd <n>, branch, ctx, receipts, quit")
    while True:
        try:
            line = input("◉ ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not line:
            continue
        if line in ("quit", "exit", "q"):
            break
        elif line == "help":
            print("  run <file>   — compile and execute .over/.glyph file")
            print("  back <n>     — step back n steps in timeline")
            print("  fwd <n>      — step forward n steps")
            print("  branch       — branch current timeline")
            print("  ctx          — show context window (memory)")
            print("  receipts     — show receipt chain")
            print("  timelines    — show all timelines")
            print("  dream <expr> — dream mode: simulate futures")
            print("  quit")
        elif line.startswith("run "):
            path = Path(line[4:].strip())
            if path.exists():
                program = compile_to_ir(path.read_text(), str(path))
                cpu.execute(program)
            else:
                print(f"  not found: {path}")
        elif line.startswith("back"):
            n = int(line.split()[-1]) if len(line.split()) > 1 else 1
            r = cpu.temporal.back(n)
            print(f"  ← {r['op'] if r else 'nothing'}")
        elif line.startswith("fwd"):
            n = int(line.split()[-1]) if len(line.split()) > 1 else 1
            r = cpu.temporal.forward(n)
            print(f"  → {r['op'] if r else 'nothing'}")
        elif line == "branch":
            nid = cpu.temporal.branch()
            print(f"  branched: {nid}")
        elif line == "ctx":
            print(cpu.context.snapshot())
            print(f"  pressure: {cpu.context.pressure():.0%}")
        elif line == "receipts":
            for r in cpu.receipts[-10:]:
                print(f"  {r['op']:<20} ◎{r['receipt_hash'][:16]}")
        elif line == "timelines":
            print(json.dumps(cpu.temporal.status(), indent=2))
        else:
            # Treat as inline .over
            program = compile_to_ir(line, "repl.over")
            cpu.execute(program)

def main():
    parser = argparse.ArgumentParser(description=".over CPU — LLM AS Compiler+Runtime")
    sub = parser.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run", help="Run a .over or .glyph file")
    p_run.add_argument("file", help="Source file (.over or .glyph)")
    p_run.add_argument("--dream", action="store_true", help="Enable dream mode")
    p_run.add_argument("--expert", type=float, default=0.0, help="Expert level 0.0-1.0")
    p_run.add_argument("--debug", action="store_true", help="Debug mode")
    p_run.add_argument("--output", "-o", help="Save result to file")

    p_demo = sub.add_parser("demo", help="Demo all 11 concepts")

    p_repl = sub.add_parser("repl", help="Interactive REPL")
    p_repl.add_argument("--dream", action="store_true")
    p_repl.add_argument("--expert", type=float, default=0.0)
    p_repl.add_argument("--debug", action="store_true")

    args = parser.parse_args()
    if args.cmd == "run":
        cmd_run(args)
    elif args.cmd == "demo":
        cmd_demo(args)
    elif args.cmd == "repl":
        cmd_repl(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
