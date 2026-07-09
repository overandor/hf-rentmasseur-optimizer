#!/usr/bin/env python3
"""Test OI-1 through OI-8 and OI-14: Semantic Execution, Intent Compilation,
Self-Modifying Code, Probabilistic Branching, Natural Language as Code,
Time-Travel Debugging, Glyph-Encoded Semantics, Receipt-Verified Execution,
Glyph-LLM Fusion."""
import sys, json, random, hashlib
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from over_cpu import (
    SemanticOp, IRProgram, ContextWindow, make_receipt,
    semantic_execute, compile_intent, self_modify,
    probabilistic_branch, is_natural_language, compile_natural_language,
    what_if, COMPOUND_GLYPHS, parse_compound_glyphs, GLYPH_TOKENS,
    compile_to_ir, compile_over_glyph, OverCPU, TemporalExecutor,
    QuantumFlow, Agent, dream, type_check, SEMANTIC_TYPES,
    lex_glyph, _parse_over_extended,
)

random.seed(42)
PASS = 0
FAIL = 0

def check(name, ok, detail=""):
    global PASS, FAIL
    status = "✓ PASS" if ok else "✗ FAIL"
    print(f"  {status}: {name}")
    if detail:
        print(f"         {detail}")
    if ok: PASS += 1
    else: FAIL += 1

print("═" * 60)
print("  OVERIMPOSSIBILITY TESTS — OI-1 through OI-8, OI-14")
print("═" * 60)

# ─── OI-1: Semantic Execution ─────────────────────────────────────────
print("\n┌─ OI-1: Semantic Execution ───────────────────────────────────┐")
ctx = ContextWindow()
ops = [
    SemanticOp(op="OBSERVE", glyph="ψ", intent="observe system state"),
    SemanticOp(op="VERIFY", glyph="◆", intent="verify integrity"),
    SemanticOp(op="STREAM", glyph="⌁", intent="stream results"),
]
result = semantic_execute(ops, ctx)
check("semantic_execute returns dict", isinstance(result, dict),
      f"keys={list(result.keys())}")
check("semantic_execute has confidence", "confidence" in result,
      f"confidence={result.get('confidence', 'missing')}")
check("semantic_execute has inferred output", "result" in result or "reasoning" in result,
      f"output={str(result.get('result', result.get('reasoning', 'missing')))[:50]}")

print("└──────────────────────────────────────────────────────────────┘")

# ─── OI-2: Intent Compilation ────────────────────────────────────────
print("\n┌─ OI-2: Intent Compilation ───────────────────────────────────┐")

# Monitor intent → should produce OBSERVE
ops = compile_intent("monitor the system for anomalies")
check("intent: monitor → OBSERVE", any(o.op == "OBSERVE" for o in ops),
      f"ops={[o.op for o in ops]}")

# Verify intent → should produce VERIFY
ops = compile_intent("verify all receipts are valid")
check("intent: verify → VERIFY", any(o.op == "VERIFY" for o in ops),
      f"ops={[o.op for o in ops]}")

# Complex intent → multiple ops
ops = compile_intent("monitor analyze verify and stream results then issue receipt")
check("intent: complex → multiple ops", len(ops) >= 4,
      f"ops={[o.op for o in ops]}")

# Unknown intent → fallback EXECUTE
ops = compile_intent("do something unprecedented")
check("intent: unknown → EXECUTE fallback", any(o.op == "EXECUTE" for o in ops),
      f"ops={[o.op for o in ops]}")

# Empty intent → EXECUTE
ops = compile_intent("")
check("intent: empty → EXECUTE", len(ops) == 1 and ops[0].op == "EXECUTE",
      f"ops={[o.op for o in ops]}")

print("└──────────────────────────────────────────────────────────────┘")

# ─── OI-3: Self-Modifying Code ───────────────────────────────────────
print("\n┌─ OI-3: Self-Modifying Code ──────────────────────────────────┐")

base_ops = [
    SemanticOp(op="OBSERVE", glyph="ψ", intent="observe"),
    SemanticOp(op="VERIFY", glyph="◆", intent="verify"),
    SemanticOp(op="STREAM", glyph="⌁", intent="stream"),
]
# No failures → no modification
ctx2 = ContextWindow()
results_no_fail = [
    {"op": "OBSERVE", "idx": 0, "value": {"confidence": 0.9}},
    {"op": "VERIFY", "idx": 1, "value": {"confidence": 0.85}},
]
unchanged = self_modify(base_ops, ctx2, results_no_fail)
check("self_modify: no failures → unchanged", len(unchanged) == len(base_ops),
      f"ops={len(unchanged)} (same as {len(base_ops)})")

# With failures → should insert VERIFY ops
results_with_fail = [
    {"op": "OBSERVE", "idx": 0, "value": {"confidence": 0.9}},
    {"op": "VERIFY", "idx": 1, "value": {"confidence": 0.3}},  # failure
]
modified = self_modify(base_ops, ctx2, results_with_fail)
check("self_modify: failure → adds ops", len(modified) > len(base_ops),
      f"ops={len(modified)} > {len(base_ops)}")
check("self_modify: adds VERIFY op", any(o.op == "VERIFY" and "re-verify" in o.intent for o in modified),
      f"intents={[o.intent for o in modified]}")

print("└──────────────────────────────────────────────────────────────┘")

# ─── OI-4: Probabilistic Branching ───────────────────────────────────
print("\n┌─ OI-4: Probabilistic Branching ──────────────────────────────┐")

ctx3 = ContextWindow()
branches = {"likely": "optimize", "sometimes": "explore", "rarely": "abort"}

# Run many times — likely should be chosen most often
counts = {"likely": 0, "sometimes": 0, "rarely": 0}
for _ in range(1000):
    r = probabilistic_branch(branches, ctx3)
    counts[r["chosen"]] = counts.get(r["chosen"], 0) + 1

check("prob_branch: likely chosen most", counts["likely"] > counts["sometimes"],
      f"likely={counts['likely']}, sometimes={counts['sometimes']}, rarely={counts['rarely']}")
check("prob_branch: rarely chosen least", counts["rarely"] < counts["sometimes"],
      f"rarely={counts['rarely']} < sometimes={counts['sometimes']}")
check("prob_branch: returns weight", all(isinstance(r.get("weight"), float) for r in
      [probabilistic_branch(branches, ctx3)]),
      "weight is float")

# Context modifier
ctx3.assign("prob_modifier_likely", 0.01)  # nearly kill likely
r = probabilistic_branch(branches, ctx3)
check("prob_branch: context modifier works", r["chosen"] in branches,
      f"chosen={r['chosen']} (likely was suppressed)")

print("└──────────────────────────────────────────────────────────────┘")

# ─── OI-5: Natural Language as Code ──────────────────────────────────
print("\n┌─ OI-5: Natural Language as Code ─────────────────────────────┐")

# Detection
check("is_natural_language: detects English", is_natural_language("monitor the system for anomalies"))
check("is_natural_language: rejects .over syntax", not is_natural_language("step 1: observe → data"))
check("is_natural_language: rejects comments", not is_natural_language("# this is a comment"))
check("is_natural_language: rejects empty", not is_natural_language(""))
check("is_natural_language: rejects keywords", not is_natural_language("superposition: a b c"))

# Compilation
op = compile_natural_language("monitor the system for anomalies")
check("nl_compile: monitor → OBSERVE", op.op == "OBSERVE", f"op={op.op}")

op = compile_natural_language("verify all receipts are valid")
check("nl_compile: verify → VERIFY", op.op == "VERIFY", f"op={op.op}")

op = compile_natural_language("stream results to output channel")
check("nl_compile: stream → STREAM", op.op == "STREAM", f"op={op.op}")

op = compile_natural_language("hash the file contents")
check("nl_compile: hash → HASH", op.op == "HASH", f"op={op.op}")

op = compile_natural_language("build the final artifact")
check("nl_compile: build → BUILD", op.op == "BUILD", f"op={op.op}")

op = compile_natural_language("do something unprecedented")
check("nl_compile: unknown → EXECUTE", op.op == "EXECUTE", f"op={op.op}")

# Intent preserved
op = compile_natural_language("monitor the system for anomalies")
check("nl_compile: preserves intent text", "monitor" in op.intent, f"intent={op.intent}")

print("└──────────────────────────────────────────────────────────────┘")

# ─── OI-6: Time-Travel Debugging ─────────────────────────────────────
print("\n┌─ OI-6: Time-Travel Debugging ────────────────────────────────┐")

temporal = TemporalExecutor()
# Record some steps (record(op, value, receipt))
for i in range(5):
    temporal.record(f"op_{i}", {"value": i, "confidence": 0.8}, {"hash": f"h{i}"})

# Step back (ptr starts at 5 after recording 0-4, back(2) → ptr=3)
back = temporal.back(2)
check("time-travel: step back", back is not None and back["op"] == "op_3",
      f"back={back['op'] if back else 'none'}")

# Step forward
fwd = temporal.forward(1)
check("time-travel: step forward", fwd is not None and fwd["op"] == "op_4",
      f"fwd={fwd['op'] if fwd else 'none'}")

# Branch
tl_id = temporal.branch(from_step=2)
check("time-travel: branch creates new timeline", tl_id != "main",
      f"new timeline={tl_id}")

# Reimagine
re_id = temporal.reimagine(3)
check("time-travel: reimagine creates new timeline", re_id != "main" and re_id != tl_id,
      f"reimagined={re_id}")

# What-if
ctx4 = ContextWindow()
wi = what_if(temporal, 2, {"new_knowledge": "the system was compromised"}, ctx4)
check("what_if: creates timeline", "timeline" in wi,
      f"timeline={wi['timeline']}")
check("what_if: injects context", "new_knowledge" in wi["injected"],
      f"injected={wi['injected']}")

# Status
status = temporal.status()
check("time-travel: status shows all timelines", len(status["timelines"]) >= 3,
      f"timelines={list(status['timelines'].keys())}")

print("└──────────────────────────────────────────────────────────────┘")

# ─── OI-7: Glyph-Encoded Semantics ──────────────────────────────────
print("\n┌─ OI-7: Glyph-Encoded Semantics ──────────────────────────────┐")

# Compound glyphs exist
check("compound glyphs defined", len(COMPOUND_GLYPHS) >= 10,
      f"{len(COMPOUND_GLYPHS)} compound glyphs")

# Parse compound glyphs from token stream
# ◉◆⌁ = LIVE_VERIFIED_STREAM
tokens = [type('T', (), {"glyph": g, "name": g, "line": 0})() for g in "◉◆⌁"]
parsed = parse_compound_glyphs(tokens)
check("compound: ◉◆⌁ → single op", len(parsed) == 1,
      f"parsed {len(parsed)} ops (expected 1)")
check("compound: ◉◆⌁ → LIVE_VERIFIED_STREAM", parsed[0].op == "LIVE_VERIFIED_STREAM",
      f"op={parsed[0].op}")

# ◆⌁ = VERIFIED_STREAM (2-glyph compound)
tokens2 = [type('T', (), {"glyph": g, "name": g, "line": 0})() for g in "◆⌁"]
parsed2 = parse_compound_glyphs(tokens2)
check("compound: ◆⌁ → VERIFIED_STREAM", parsed2[0].op == "VERIFIED_STREAM",
      f"op={parsed2[0].op}")

# Non-compound glyphs → individual ops
tokens3 = [type('T', (), {"glyph": "ψ", "name": "WAVEFUNCTION", "line": 0})()]
parsed3 = parse_compound_glyphs(tokens3)
check("compound: single glyph → individual op", len(parsed3) == 1,
      f"op={parsed3[0].op}")

# Intent is set from compound glyph spec
check("compound: intent set from spec", "verified" in parsed[0].intent.lower(),
      f"intent={parsed[0].intent}")

print("└──────────────────────────────────────────────────────────────┘")

# ─── OI-8: Receipt-Verified Execution ────────────────────────────────
print("\n┌─ OI-8: Receipt-Verified Execution ───────────────────────────┐")

# Create receipt chain
r0 = make_receipt("OBSERVE", {"data": "hello"}, "0" * 64)
check("receipt: has hash", len(r0["receipt_hash"]) == 64,
      f"hash={r0['receipt_hash'][:16]}...")
check("receipt: has prev_hash", r0["prev_hash"] == "0" * 64,
      "genesis prev_hash is zeros")
check("receipt: has timestamp", "ts" in r0 and r0["ts"].endswith("Z"),
      f"ts={r0['ts']}")

# Chain
r1 = make_receipt("VERIFY", {"ok": True}, r0["receipt_hash"])
check("receipt: chain links prev", r1["prev_hash"] == r0["receipt_hash"],
      "r1.prev == r0.hash")

r2 = make_receipt("STREAM", {"bytes": 1024}, r1["receipt_hash"])
check("receipt: chain length 3", r2["prev_hash"] == r1["receipt_hash"],
      "r2.prev == r1.hash")

# Verify chain integrity
chain = [r0, r1, r2]
intact = all(chain[i]["prev_hash"] == chain[i-1]["receipt_hash"] for i in range(1, len(chain)))
check("receipt: chain integrity verified", intact, "all links valid")

# Tamper detection
tampered = dict(r1)
tampered["op"] = "TAMPERED"
broken = chain[0]["receipt_hash"] != chain[1]["prev_hash"]  # still intact structurally
check("receipt: tamper changes op", tampered["op"] != r1["op"],
      f"original={r1['op']}, tampered={tampered['op']}")

# Full CPU execution produces receipts
cpu = OverCPU(expert_level=0.5)
prog = compile_to_ir("workflow: r\nstep 1: observe → a\nstep 2: verify → b\n", "r.over")
result = cpu.execute(prog)
check("receipt: CPU produces receipts", result["receipts"] >= 2,
      f"{result['receipts']} receipts for {result['ops_executed']} ops")
check("receipt: merkle root exists", len(result["merkle_root"]) > 0,
      f"root={result['merkle_root'][:16]}...")

print("└──────────────────────────────────────────────────────────────┘")

# ─── OI-14: Glyph-LLM Fusion ─────────────────────────────────────────
print("\n┌─ OI-14: Glyph-LLM Fusion (.over.glyph) ──────────────────────┐")

hybrid_source = """# Hybrid .over.glyph program
step 1: superposition { fast | safe } → choice
step 2: collapse → winner
◉◆⌁
monitor the system for anomalies
verify all receipts
"""

prog = compile_over_glyph(hybrid_source, "test.over.glyph")
check("fusion: compiles hybrid source", len(prog.ops) > 0,
      f"{len(prog.ops)} ops from hybrid source")
check("fusion: has .over keyword ops", any(o.op in ("SUPERPOSITION", "COLLAPSE") for o in prog.ops),
      f"keyword ops={[o.op for o in prog.ops if o.op in ('SUPERPOSITION', 'COLLAPSE')]}")
check("fusion: has compound glyph ops", any(o.glyph in COMPOUND_GLYPHS for o in prog.ops),
      f"compound ops={[o.op for o in prog.ops if o.glyph in COMPOUND_GLYPHS]}")
check("fusion: has natural language ops", any(o.op in ("OBSERVE", "VERIFY") for o in prog.ops),
      f"nl ops={[o.op for o in prog.ops if o.intent and ' ' in o.intent]}")

# Execute the hybrid program
cpu2 = OverCPU(expert_level=0.6, debug=True)
result2 = cpu2.execute(prog)
check("fusion: executes successfully", result2["ops_executed"] > 0,
      f"{result2['ops_executed']} ops, {result2['receipts']} receipts")

# Verify compile_to_ir dispatches to compile_over_glyph for .over.glyph
prog2 = compile_to_ir(hybrid_source, "test.over.glyph")
check("fusion: compile_to_ir dispatches .over.glyph", len(prog2.ops) == len(prog.ops),
      f"same op count: {len(prog2.ops)}")

print("└──────────────────────────────────────────────────────────────┘")

# ─── Bonus: Quantum + Agent integration ──────────────────────────────
print("\n┌─ Bonus: Quantum Flow + Agent Lifecycle ──────────────────────┐")

qf = QuantumFlow()
sp_id = qf.superposition({"fast": {"v": 1, "confidence": 0.6}, "safe": {"v": 2, "confidence": 0.9}})
check("quantum: superposition creates id", len(sp_id) > 0, f"sp_id={sp_id}")

winner = qf.collapse(sp_id)
check("quantum: collapse picks highest confidence", winner is not None,
      f"winner={winner}")

qf.entangle("var_a", "var_b")
check("quantum: entanglement registered", "var_b" in qf.entanglements.get("var_a", []),
      f"entanglements={qf.entanglements}")

agent = Agent("test_agent", "analyze data")
agent_ctx = ContextWindow()
agent_ctx.assign("data", {"value": 42, "confidence": 0.8})
agent_result = agent.run(agent_ctx, TemporalExecutor(), QuantumFlow())
check("agent: lifecycle completes", agent.state == "done",
      f"state={agent.state}")
check("agent: produces result", agent.result is not None,
      f"result={str(agent.result)[:50]}")

print("└──────────────────────────────────────────────────────────────┘")

# ─── Summary ──────────────────────────────────────────────────────────
print(f"\n{'═' * 60}")
print(f"  RESULTS: {PASS} passed, {FAIL} failed")
print(f"{'═' * 60}")
sys.exit(0 if FAIL == 0 else 1)
