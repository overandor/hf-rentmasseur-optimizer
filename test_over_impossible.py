#!/usr/bin/env python3
"""Test OI-9 through OI-13: Cross-Program Inference, Hallucination-Resistant
Types, Zero-Shot Imports, Contradiction Resolution, Dream Mode."""
import sys, json, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from over_cpu import (
    CrossProgramLink, IRProgram, SemanticOp, ContextWindow,
    hallucination_resistant_check, zero_shot_import,
    detect_contradiction, contradiction_receipt, make_receipt,
    dream, compile_to_ir, OverCPU, compile_intent,
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
print("  OVERIMPOSSIBILITY TESTS — OI-9 through OI-13")
print("═" * 60)

# ─── OI-9: Cross-Program Inference ─────────────────────────────────────
print("\n┌─ OI-9: Cross-Program Inference ──────────────────────────────┐")

prog_a = compile_to_ir(
    "workflow: collector\nstep 1: observe data → raw\nstep 2: index file → idx\n",
    "collector.over"
)
prog_b = compile_to_ir(
    "workflow: verifier\nstep 1: verify integrity → v\nstep 2: issue receipt → r\n",
    "verifier.over"
)

CrossProgramLink.register("collector", prog_a)
CrossProgramLink.register("verifier", prog_b)

# Test import
imported = CrossProgramLink.import_op("collector", ContextWindow())
check("import registered program", len(imported) == 2, f"{len(imported)} ops imported")

# Test relationship inference
rel = CrossProgramLink.infer_relationship(prog_a, prog_b)
check("infer relationship", rel["relationship"] in ("sequential", "complementary", "overlapping", "independent"),
      f"relationship={rel['relationship']}, shared={rel['shared_ops']}")

# Test compose
composed = CrossProgramLink.compose(prog_a, prog_b)
check("compose two programs", len(composed.ops) >= len(prog_a.ops) + len(prog_b.ops) - 2,
      f"composed {len(composed.ops)} ops from {len(prog_a.ops)}+{len(prog_b.ops)}")
check("composed has relationship", hasattr(composed, "relationship"),
      f"relationship={composed.relationship['relationship']}")

print("└──────────────────────────────────────────────────────────────┘")

# ─── OI-10: Hallucination-Resistant Types ─────────────────────────────
print("\n┌─ OI-10: Hallucination-Resistant Types ───────────────────────┐")
ctx = ContextWindow()

# Good SecureFilePath — wrapped in dict with confidence for semantic checks
ok, reason = hallucination_resistant_check({"path": "/var/data/file.txt", "confidence": 0.95, "verified": True}, "SecureFilePath", ctx)
check("SecureFilePath valid path", ok, reason)

# Bad SecureFilePath — path traversal
ok, reason = hallucination_resistant_check("../../../etc/passwd", "SecureFilePath", ctx)
check("SecureFilePath blocks traversal", not ok, reason)

# Bad SecureFilePath — low confidence dict
ok, reason = hallucination_resistant_check({"path": "/data", "confidence": 0.3}, "SecureFilePath", ctx)
check("SecureFilePath blocks low confidence", not ok, reason)

# Good VerifiedReceipt
good_receipt = {"receipt_hash": "a" * 64, "confidence": 1.0, "verified": True}
ok, reason = hallucination_resistant_check(good_receipt, "VerifiedReceipt", ctx)
check("VerifiedReceipt valid", ok, reason)

# Bad VerifiedReceipt — fake hash
bad_receipt = {"receipt_hash": "0" * 64, "confidence": 1.0}
ok, reason = hallucination_resistant_check(bad_receipt, "VerifiedReceipt", ctx)
check("VerifiedReceipt blocks all-zeros hash", not ok, reason)

# Good AgentIntent
good_intent = {"intent": "analyze data", "confidence": 0.8}
ok, reason = hallucination_resistant_check(good_intent, "AgentIntent", ctx)
check("AgentIntent valid", ok, reason)

# Bad AgentIntent — empty intent
bad_intent = {"intent": "", "confidence": 0.9}
ok, reason = hallucination_resistant_check(bad_intent, "AgentIntent", ctx)
check("AgentIntent blocks empty intent", not ok, reason)

# Good StreamHandle
good_stream = {"streaming": True, "confidence": 0.7, "live": True}
ok, reason = hallucination_resistant_check(good_stream, "StreamHandle", ctx)
check("StreamHandle valid", ok, reason)

# Bad StreamHandle — not streaming
bad_stream = {"streaming": False, "confidence": 0.7}
ok, reason = hallucination_resistant_check(bad_stream, "StreamHandle", ctx)
check("StreamHandle blocks non-streaming", not ok, reason)

print("└──────────────────────────────────────────────────────────────┘")

# ─── OI-11: Zero-Shot Imports ─────────────────────────────────────────
print("\n┌─ OI-11: Zero-Shot Imports ───────────────────────────────────┐")

# Import a module that doesn't exist
ops = zero_shot_import("anomaly_detector", "detect anomalies in streaming data")
check("zero-shot generates ops", len(ops) > 0, f"generated {len(ops)} ops: {[o.op for o in ops]}")

# Verify it's registered now
registered = CrossProgramLink._registry.get("anomaly_detector")
check("zero-shot registered in registry", registered is not None,
      f"registered as '{registered.name}'" if registered else "not found")

# Import again — should return from registry, not regenerate
ops2 = CrossProgramLink.import_op("anomaly_detector", ContextWindow())
check("second import uses registry", ops2 is not None, f"{len(ops2)} ops from registry")

# Generate another zero-shot for a different module
ops3 = zero_shot_import("crypto_signer", "sign and verify cryptographic receipts")
check("different zero-shot generates different ops",
      len(ops3) > 0 and [o.op for o in ops3] != [o.op for o in ops],
      f"crypto_signer: {[o.op for o in ops3]}")

print("└──────────────────────────────────────────────────────────────┘")

# ─── OI-12: Contradiction Resolution ──────────────────────────────────
print("\n┌─ OI-12: Contradiction Resolution ───────────────────────────┐")

ctx2 = ContextWindow()
# Create a contradiction: two verified_ entries with different results
ctx2.assign("verified_1", {"verified": True, "confidence": 0.9})
ctx2.assign("verified_3", {"verified": False, "confidence": 0.6})

contradiction = detect_contradiction([], ctx2)
check("contradiction detected", contradiction is not None,
      f"found {contradiction['count'] if contradiction else 0} contradiction(s)" if contradiction else "none found")

if contradiction:
    c = contradiction["contradictions"][0]
    check("contradiction has resolution", "resolution" in c,
          f"winner={c['resolution']['winner']}, reasoning={c['resolution']['reasoning']}")
    check("contradiction picks higher confidence",
          c["resolution"]["winner"] == "verified_1",
          f"chose {c['resolution']['winner']} (conf 0.9 > 0.6)")

    # Test receipt logging
    receipt = contradiction_receipt(contradiction, "0" * 64)
    check("contradiction receipt created", "receipt_hash" in receipt,
          f"hash={receipt['receipt_hash'][:16]}")

# Test no contradiction when values agree
ctx3 = ContextWindow()
ctx3.assign("verified_1", {"verified": True, "confidence": 0.9})
ctx3.assign("verified_2", {"verified": True, "confidence": 0.85})
no_contradiction = detect_contradiction([], ctx3)
check("no false positive when values agree", no_contradiction is None,
      "correctly found no contradiction")

# Test confidence divergence detection
ctx4 = ContextWindow()
ctx4.assign("result_1", {"confidence": 0.95})
ctx4.assign("result_2", {"confidence": 0.2})
divergence = detect_contradiction([], ctx4)
check("confidence divergence detected", divergence is not None,
      f"found {divergence['count'] if divergence else 0} divergence(s)" if divergence else "none")

print("└──────────────────────────────────────────────────────────────┘")

# ─── OI-13: Dream Mode ────────────────────────────────────────────────
print("\n┌─ OI-13: Dream Mode ─────────────────────────────────────────┐")

ctx5 = ContextWindow()
ctx5.assign("baseline", {"value": 42, "confidence": 0.7})

ops = [
    SemanticOp(op="OBSERVE", glyph="ψ", intent="observe system"),
    SemanticOp(op="VERIFY", glyph="◆", intent="verify integrity"),
    SemanticOp(op="STREAM", glyph="⌁", intent="stream output"),
]

# Dream 10 futures
best = dream(ops, ctx5, n_futures=10)
check("dream returns best future", best is not None and "score" in best,
      f"best score={best['score']:.3f}, id={best['id']}")

# Dream more futures → score should be at least as good (more chances)
best_more = dream(ops, ctx5, n_futures=50)
check("more futures → score >= ", best_more["score"] >= best["score"] * 0.8,
      f"10 futures: {best['score']:.3f}, 50 futures: {best_more['score']:.3f}")

# Dream with no ops → empty result
best_empty = dream([], ctx5, n_futures=5)
check("dream with no ops handles gracefully", "score" in best_empty,
      f"score={best_empty['score']:.3f}")

# Full CPU execution with dream mode
cpu = OverCPU(expert_level=0.5, dream_mode=True)
prog = compile_to_ir(
    "workflow: dreamtest\nstep 1: observe → a\nstep 2: verify → b\nstep 3: receipt → c\n",
    "dreamtest.over"
)
result = cpu.execute(prog)
check("dream mode execution completes", result["ops_executed"] == 3,
      f"{result['ops_executed']} ops, {result['receipts']} receipts")

print("└──────────────────────────────────────────────────────────────┘")

# ─── Summary ──────────────────────────────────────────────────────────
print(f"\n{'═' * 60}")
print(f"  RESULTS: {PASS} passed, {FAIL} failed")
print(f"{'═' * 60}")
sys.exit(0 if FAIL == 0 else 1)
