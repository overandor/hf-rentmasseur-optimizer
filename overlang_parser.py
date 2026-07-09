"""
OverLang Parser — Parse and compile .over source files.

parse_over: line-based parser for .over workflow specs.
compile_over: compile parsed workflow into JSON artifact with receipt chain.
"""

import json
import time
import hashlib

from overlang_types import OverStep, OverWorkflow


def parse_over(source: str) -> OverWorkflow:
    """Parse .over source into OverWorkflow.
    Format is line-based with → as the flow operator:
      intent: <description>
      step 1: <action> → <output>
      step 2: <action> → <output>
      artifact: <name>
      receipt: <description>
      value: <claim>
    """
    wf = OverWorkflow()
    step_counter = 0

    for line in source.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("intent:"):
            wf.intent = line[7:].strip()
        elif line.startswith("workflow:"):
            wf.name = line[9:].strip()
        elif line.startswith("step"):
            step_counter += 1
            rest = line.split(":", 1)[1].strip() if ":" in line else line
            parts = rest.split("→")
            action = parts[0].strip()
            outputs = [p.strip() for p in parts[1:]] if len(parts) > 1 else []
            wf.steps.append(OverStep(step_num=step_counter, action=action, outputs=outputs))
        elif line.startswith("artifact:"):
            wf.artifacts.append(line[9:].strip())
        elif line.startswith("receipt:"):
            wf.receipts.append(line[8:].strip())
        elif line.startswith("value:"):
            wf.value_claim = line[6:].strip()

    return wf


def compile_over(source: str, filename: str = "") -> dict:
    """Compile a .over source file into a workflow artifact."""
    start = time.time()
    wf = parse_over(source)

    # Generate receipt chain
    receipt_chain = []
    prev_hash = "0" * 64
    for step in wf.steps:
        entry = json.dumps({
            "step": step.step_num,
            "action": step.action,
            "outputs": step.outputs,
            "ts": time.time(),
        }, sort_keys=True)
        entry_hash = hashlib.sha256((prev_hash + entry).encode()).hexdigest()
        receipt_chain.append({
            "step": step.step_num,
            "action": step.action,
            "hash": entry_hash,
            "prev_hash": prev_hash,
        })
        prev_hash = entry_hash

    artifact = {
        "type": "over_compiled",
        "source_file": filename,
        "compiled_at": time.time(),
        "workflow_name": wf.name,
        "intent": wf.intent,
        "step_count": len(wf.steps),
        "steps": [
            {"step": s.step_num, "action": s.action, "outputs": s.outputs}
            for s in wf.steps
        ],
        "artifacts": wf.artifacts,
        "value_claim": wf.value_claim,
        "receipt_chain": receipt_chain,
        "merkle_root": prev_hash,
        "compile_time_ms": round((time.time() - start) * 1000, 2),
    }

    artifact_str = json.dumps(artifact, sort_keys=True)
    artifact["sha256"] = hashlib.sha256(artifact_str.encode()).hexdigest()

    return artifact
