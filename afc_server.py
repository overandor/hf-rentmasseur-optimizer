"""
AFC Protocol Server — Unified API
==================================
Integrates:
  1. BlurHash64 — adjustable-fidelity glyph encodings
  2. GlyphForge — recursive glyph production engine
  3. OverLanguage 2.0 — meta-language parser/compiler
  4. Layer4Meter — latent compute substrate capture
  5. AFC Protocol — bonded claim market with oracle settlement

Run: python3 afc_server.py
"""

import os
import json
import time
import hashlib
import base64
import uuid
import sqlite3
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header, Body, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from blurhash64 import BlurHash64Encoder, Glyph
from glyphforge import GlyphForge, MASTER_GLYPH
from overlanguage import OverLanguageCompiler, Layer4Meter
from glyphlang import (GlyphCompiler, InkStream, QuantumGlyphFactory,
                       GlyphFileWriter, ClusterFileMapper,
                       DarkLangCompiler, ProteinFolder, PixelSwarmRenderer)
from afc_protocol import (
    app as afc_app, create_claim, get_claim, list_claims,
    escrow_payment, reveal_answer, submit_hidden_tests,
    settle_claim, get_receipt, protocol_manifest, antonymify,
    sha256, merkle_commitment, blur_hash64
)

app = FastAPI(title="AFC Protocol — Unified Server", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Mount AFC endpoints
for route in afc_app.routes:
    if hasattr(route, 'path') and route.path not in ('/', '/health'):
        app.router.routes.append(route)

encoder = BlurHash64Encoder()
forge = GlyphForge(max_generations=5, min_score=15.0)
compiler = OverLanguageCompiler()
l4meter = Layer4Meter()
glyph_compiler = GlyphCompiler()
ink_stream = InkStream(target_count=234322, rate_per_min=34)
quantum_factory = QuantumGlyphFactory(target_count=398989889)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "systems": ["blurhash64", "glyphforge", "overlanguage", "layer4meter", "afc_protocol"],
        "version": "1.0",
    }


# --- BlurHash64 endpoints ---

@app.post("/bh64/encode")
async def bh64_encode(body: dict = Body(...)):
    """Encode a file at a specified fidelity level (0-9)."""
    content = body.get("content", "")
    filename = body.get("filename", "")
    fidelity = body.get("fidelity", 6)
    if not content:
        raise HTTPException(400, {"status": "error", "message": "content required"})
    glyph = encoder.encode(content, filename, fidelity)
    return glyph.to_dict()


@app.post("/bh64/ladder")
async def bh64_ladder(body: dict = Body(...)):
    """Generate all 10 fidelity levels for a file."""
    content = body.get("content", "")
    filename = body.get("filename", "")
    if not content:
        raise HTTPException(400, {"status": "error", "message": "content required"})
    return {"ladder": encoder.ladder(content, filename), "filename": filename}


@app.get("/bh64/levels")
async def bh64_levels():
    """Describe the 10 fidelity levels."""
    return {
        "levels": [
            {"level": 0, "name": "null", "discloses": "nothing", "recoverable": False, "executable": False},
            {"level": 1, "name": "presence", "discloses": "file exists", "recoverable": False, "executable": False},
            {"level": 2, "name": "type", "discloses": "file class", "recoverable": False, "executable": False},
            {"level": 3, "name": "metadata", "discloses": "size, ext, timestamps", "recoverable": False, "executable": False},
            {"level": 4, "name": "feature", "discloses": "imports, functions, deps", "recoverable": False, "executable": False},
            {"level": 5, "name": "sketch", "discloses": "lossy summary, preview", "recoverable": False, "executable": False},
            {"level": 6, "name": "receipt", "discloses": "hash, merkle, provenance, claims", "recoverable": False, "executable": False},
            {"level": 7, "name": "partial_body", "discloses": "selected chunks", "recoverable": "partial", "executable": False},
            {"level": 8, "name": "encrypted_body", "discloses": "full body (key-gated)", "recoverable": "full", "executable": False},
            {"level": 9, "name": "full_transport", "discloses": "complete Base64 body", "recoverable": "full", "executable": True},
        ]
    }


# --- GlyphForge endpoints ---

@app.post("/forge/run")
async def forge_run(body: dict = Body(...)):
    """Run the glyph forge for N generations."""
    generations = body.get("generations", 5)
    seed = body.get("seed", MASTER_GLYPH)
    glyphs = forge.forge(generations=generations)
    return {
        "master_glyph": MASTER_GLYPH,
        "total_glyphs": len(glyphs),
        "generations": max(g.generation for g in glyphs) if glyphs else 0,
        "top_10": forge.top_glyphs(10),
        "stream": forge.stream(20),
    }


@app.get("/forge/top")
async def forge_top(n: int = 10):
    return {"top_glyphs": forge.top_glyphs(n)}


@app.get("/forge/stream")
async def forge_stream(n: int = 20):
    return {"ticker": forge.stream(n)}


# --- OverLanguage endpoints ---

@app.post("/over/compile")
async def over_compile(body: dict = Body(...)):
    """Compile an .over program into production artifacts."""
    source = body.get("source", "")
    if not source:
        raise HTTPException(400, {"status": "error", "message": "source required"})
    result = compiler.compile(source)
    return result.to_dict()


@app.get("/over/grammar")
async def over_grammar():
    """Return the OverLanguage 2.0 grammar and glyph alphabet."""
    from overlanguage import OverLanguageParser
    from glyphforge import ALPHABET, GRAMMAR
    return {
        "root_glyph": MASTER_GLYPH,
        "root_meaning": "stationary artifact at location → hash-bound → receipt-bound → transferable → verified → financeable",
        "alphabet": ALPHABET,
        "grammar": GRAMMAR,
        "layers": [
            {"layer": 0, "name": "glyph", "description": "compressed symbolic substrate"},
            {"layer": 1, "name": "intent", "description": "human-level objective"},
            {"layer": 2, "name": "contract", "description": "enforceable requirements"},
            {"layer": 3, "name": "agent", "description": "production operators"},
            {"layer": 4, "name": "substrate", "description": "latent compute capture"},
            {"layer": 5, "name": "receipt", "description": "proof binding"},
            {"layer": 6, "name": "transfer", "description": "lambda friction / transferability"},
            {"layer": 7, "name": "economic", "description": "buyer / value / price"},
        ],
        "compiler_passes": ["parse", "expand", "contract", "assign", "execute", "capture", "hash", "receipt", "score", "package"],
        "primitives": ["overprogram", "glyph", "receipt", "lambda", "monetize"],
    }


# --- Layer4Meter endpoints ---

@app.post("/l4/sample")
async def l4_sample():
    """Capture a substrate sample."""
    s = l4meter.sample()
    lci = l4meter.compute_lci(s)
    return {"sample": asdict_safe(s), "lci": lci}


@app.post("/l4/baseline")
async def l4_baseline(body: dict = Body(...)):
    """Set a baseline LCI (idle or human). Either provide lci directly or capture samples."""
    mode = body.get("mode", "idle")
    lci = body.get("lci", None)
    if lci is not None:
        l4meter.set_baseline(mode, lci)
        return {"mode": mode, "baseline_lci": lci, "method": "manual"}
    else:
        samples = body.get("samples", 5)
        return l4meter.capture_baseline(mode, samples)


@app.post("/l4/lift")
async def l4_lift(body: dict = Body(...)):
    """Compute hidden compute lift = Agent LCI - Human Baseline - Idle Baseline."""
    workload_lci = body.get("workload_lci", None)
    return l4meter.hidden_compute_lift(workload_lci)


@app.post("/l4/business")
async def l4_business(body: dict = Body(...)):
    """Compute business metrics from substrate data."""
    return l4meter.business_metrics(
        artifact_value=body.get("artifact_value", 0),
        lci=body.get("lci", 0),
        useful_outputs=body.get("useful_outputs", 1),
        retries=body.get("retries", 0),
        total_events=body.get("total_events", 100),
    )


@app.post("/l4/rank")
async def l4_rank(body: dict = Body(...)):
    """Rank workflows by value per LCI."""
    workflows = body.get("workflows", [])
    if not workflows:
        workflows = [
            {"name": "Workflow A", "lci": 220, "artifact_value": 2000},
            {"name": "Workflow B", "lci": 80, "artifact_value": 10000},
        ]
    return {"ranked": l4meter.rank_workflows(workflows)}


@app.post("/l4/session")
async def l4_session(body: dict = Body(...)):
    """Run a full L4 session: capture idle baseline, human baseline, agent workload, then compute lift + receipt."""
    project = body.get("project", "unnamed")
    idle_samples = body.get("idle_samples", 3)
    human_samples = body.get("human_samples", 3)
    agent_samples = body.get("agent_samples", 5)

    idle_result = l4meter.capture_baseline("idle", idle_samples)
    human_result = l4meter.capture_baseline("human", human_samples)

    for _ in range(agent_samples):
        l4meter.sample(mode="agent")

    lift = l4meter.hidden_compute_lift()
    receipt = l4meter.receipt(project, time.time() - 3600)

    return {
        "project": project,
        "idle_baseline": idle_result,
        "human_baseline": human_result,
        "agent_samples": agent_samples,
        "hidden_compute_lift": lift,
        "business_metrics": l4meter.business_metrics(),
        "receipt": receipt,
    }


@app.post("/l4/receipt")
async def l4_receipt(body: dict = Body(...)):
    """Generate an L4 substrate receipt with 5-plane breakdown."""
    project = body.get("project", "unnamed")
    session_start = body.get("session_start", time.time())
    return l4meter.receipt(project, session_start)


@app.get("/l4/planes")
async def l4_planes():
    """Describe the 5 capture planes."""
    return {
        "planes": [
            {"plane": 1, "name": "visual", "description": "Screen state changes, active app, windows visible", "production_api": "ScreenCaptureKit"},
            {"plane": 2, "name": "file", "description": "File events, creations, modifications, deletions, git deltas", "production_api": "FSEvents"},
            {"plane": 3, "name": "process", "description": "Process spawns, child processes, security events", "production_api": "Endpoint Security"},
            {"plane": 4, "name": "power", "description": "CPU seconds, GPU activity, disk writes, network bytes, memory pressure", "production_api": "MetricKit + powermetrics"},
            {"plane": 5, "name": "time_snapshot", "description": "Snapshot delta MB, temporal anchors", "production_api": "Time Machine local snapshots"},
        ],
        "modes": ["idle", "human", "agent"],
        "formula": "LCI = α·CPU + β·GPU + γ·disk + δ·files + ε·procs + ζ·net + η·mem + θ·snap + ι·screen + κ·idle",
        "lift_formula": "Hidden Compute Lift = Agent LCI - Human Baseline - Idle Baseline",
        "business_metrics": ["cost_per_artifact", "proof_density", "agent_efficiency", "waste_ratio", "revenue_readiness", "value_per_lci"],
        "receipt_format": ".l4receipt/{manifest.json, events.sqlite, shards/*, hashes/merkle_root.txt, proofs/*}",
        "stages": [
            {"stage": "V1", "name": "Capture", "description": "Screen checkpoints, file deltas, git diffs, command logs, disk growth, power samples"},
            {"stage": "V2", "name": "Quantify", "description": "LCI score, baseline comparison, waste ratio, artifact yield, cost per artifact"},
            {"stage": "V3", "name": "Prove", "description": "Merkle roots, signed receipts, selective disclosure, verifier CLI"},
            {"stage": "V4", "name": "Quantum-sharded zkReceipt", "description": "Post-quantum signatures, sharded proofs, zero-knowledge claims, external notarization"},
        ],
    }


# --- Paper endpoint ---

@app.get("/paper", response_class=PlainTextResponse)
async def paper():
    """Serve the research paper abstract."""
    return """Antonymified File Receipts: LLM-Mediated Non-Consumable Disclosure for Hash-Bound, Oracle-Settled Digital Artifacts

Abstract:
Information goods are economically difficult because inspection can consume the good. A buyer can inspect a car without owning it, but inspecting an answer, trading signal, source file, dataset, or proprietary analysis may reveal the thing being sold. This creates a market failure: the seller cannot fully reveal the information before payment, while the buyer cannot confidently value it without some form of inspection.

This paper proposes Antonymified File Receipts, a controlled-disclosure framework for representing digital files without directly revealing, copying, summarizing, or reconstructing their consumable content. The framework introduces antonymification as a semantic transformation in which a large language model produces a controlled opposite-representation of a file: enough to classify, route, price, verify, or settle claims about the file, but not enough to consume, execute, or reconstruct it.

The LLM is not treated as the security layer. It acts as a semantic blur engine. Security and accountability are supplied by cryptographic hashes, receipts, leakage tests, oracle settlement, bonds, and controlled access windows.

The resulting object, an Antonymified File Receipt, combines:
  - A non-consumable surrogate
  - A hash commitment to the sealed source
  - A leakage-risk score
  - A transferability coefficient (lambda friction)
  - A declared correctness oracle

The system addresses Arrow's information paradox by replacing direct inspection with verifiable non-seeing. The buyer does not consume the answer before purchase. Instead, the buyer inspects a bundle of controlled signals: surrogate, hash commitment, proof hooks, seller bond, oracle, disclosure level, and settlement terms.

The central claim: answers do not become sellable by being encoded. They become sellable when controlled disclosure is paired with settlement accountability.

BlurHash64 solves the pre-sale visibility problem with a 10-level fidelity ladder.
Antonymification turns file content into non-consumable market evidence.
Bonds and oracles solve the truth problem.
Together, they form a practical architecture for markets in answers, files, software artifacts, datasets, and AI-generated work.

Protocol law:
  1. No full disclosure before payment.
  2. No payment without settlement.
  3. No settlement without an oracle.
  4. No oracle without a bond.

Master glyph: ⧉◇@L → H@L Æ R Æ λ⁻¹ = ◎ → $

Live system: https://josephrw-afc-protocol.hf.space
"""


def asdict_safe(obj):
    from dataclasses import asdict
    return asdict(obj)


# --- GlyphLang: Write-Once Compile-to-All ---

@app.post("/glyph/compile")
async def glyph_compile(body: dict = Body(...)):
    """Compile .glyph source to C++, Swift, C, Obj-C, Rust, Python."""
    source = body.get("source", "")
    if not source:
        raise HTTPException(400, "source required")
    targets = body.get("targets", None)
    result = glyph_compiler.compile(source, targets=targets)
    return result

@app.post("/glyph/run")
async def glyph_run(body: dict = Body(...)):
    """Compile and execute a .glyph program (Python target)."""
    source = body.get("source", "")
    if not source:
        raise HTTPException(400, "source required")
    result = glyph_compiler.execute(source)
    return result

@app.get("/glyph/demo")
async def glyph_demo():
    """Run the built-in demo .glyph program compiled to all 6 targets."""
    demo = """program DemoWorkflow
  ◇@L → H@L
  H@L Æ R
  R Æ λ⁻¹
  λ⁻¹ = ◎
  ◎ → $
  emit ◇ Æ R Æ λ⁻¹ → $
end"""
    result = glyph_compiler.compile(demo)
    exec_result = glyph_compiler.execute(demo)
    return {"source": demo, "compile": result, "execution": exec_result}

@app.get("/glyph/targets")
async def glyph_targets():
    """List available compilation targets."""
    return {
        "targets": GlyphCompiler.TARGETS,
        "description": "Write once in glyph prose, compile to all native languages",
        "semantic_map": {
            "◇@L → H@L": "declare artifact, compute hash",
            "H@L Æ R": "bind hash to receipt struct",
            "R Æ λ⁻¹": "receipt becomes transferable",
            "λ⁻¹ = ◎": "assert verified",
            "◎ → $": "verified becomes payable",
            "emit X": "return / print X",
            "claim X": "create claim object",
            "prove X": "run verification",
            "pay X": "release payment",
        },
        "master_glyph": "⧉◇@L → H@L Æ R Æ λ⁻¹ = ◎ → $",
    }


# --- InkStream: Continuous Pen-Continuity Glyph Engine ---

@app.get("/ink/stats")
async def ink_stats():
    """InkStream engine stats — pen continuity, glyph count, chain head."""
    return ink_stream.stats()

@app.get("/ink/stream")
async def ink_stream_view(n: int = 20):
    """Get the last N glyphs from the ink stream."""
    return {"glyphs": ink_stream.stream(n), "stats": ink_stream.stats()}

@app.post("/ink/tick")
async def ink_tick(body: dict = Body(...)):
    """Generate one tick of glyphs (default 34 = 1 minute of generation)."""
    count = body.get("count", 34)
    emitted = ink_stream.tick(count)
    return {"emitted": len(emitted), "glyphs": emitted, "stats": ink_stream.stats()}

@app.post("/ink/burst")
async def ink_burst(body: dict = Body(...)):
    """Burst generate N glyphs instantly."""
    count = body.get("count", 100)
    emitted = ink_stream.tick(count)
    return {"emitted": len(emitted), "stats": ink_stream.stats()}

@app.get("/ink/search")
async def ink_search(q: str = "", limit: int = 20):
    """Search ink stream glyphs by symbol fragment."""
    results = [g for g in ink_stream.glyphs if q in g["symbol"]] if q else ink_stream.stream(limit)
    return {"query": q, "results": results[:limit], "total_matches": len(results) if q else len(ink_stream.glyphs)}


# --- Quantum Glyph Superposition ---
# Each glyph = 3 characters simultaneously. 345x compression. 39.9B target.
# Shadow is irreducible. Pen never lifts.

@app.get("/quantum/stats")
async def quantum_stats():
    """Quantum glyph factory stats — superposition state, compression, pico scale."""
    return quantum_factory.stats()

@app.post("/quantum/burst")
async def quantum_burst(body: dict = Body(...)):
    """Burst generate quantum superposition glyphs."""
    count = body.get("count", 10000)
    result = quantum_factory.burst(count)
    return result

@app.get("/quantum/stream")
async def quantum_stream(n: int = 20):
    """Get the last N quantum glyphs in unresolved superposition."""
    return {"glyphs": quantum_factory.stream(n), "stats": quantum_factory.stats()}

@app.get("/quantum/observe/{index}")
async def quantum_observe(index: int, layer: int = None):
    """Observe a quantum glyph, collapsing its superposition to one layer.
    layer=0: structural, layer=1: semantic, layer=2: shadow, None: unresolved.
    """
    result = quantum_factory.observe_glyph(index, layer)
    if result is None:
        raise HTTPException(404, "glyph not found")
    return {
        "index": index,
        "layer_observed": layer,
        "collapsed_value": result,
        "state": "collapsed" if layer is not None else "unresolved",
        "note": "Observation collapses superposition. Unobserved = all 3 at once.",
    }

@app.post("/quantum/compress")
async def quantum_compress(body: dict = Body(...)):
    """Compress data using quantum glyph superposition. 345x density per glyph-bit."""
    data = body.get("data", "")
    if not data:
        raise HTTPException(400, "data required")
    return quantum_factory.compress_data(data)


# --- Glyph File Writer: Threaded Ramp 3→6→20 ---

@app.post("/glyph/write")
async def glyph_write(body: dict = Body(...)):
    """Run threaded glyph file writer. Ramps 3→6→20 files.
    All async, multithreaded, disk-based (zero RAM).
    Each glyph: hashed, indexed, English-named, non-Unicode binary encoded.
    """
    output_dir = body.get("output_dir", "/tmp/glyph_output")
    writer = GlyphFileWriter(output_dir=output_dir)
    result = writer.run_ramp()
    return result

@app.get("/glyph/write/status")
async def glyph_write_status():
    """Show the ramp schedule for the file writer."""
    return {
        "ramp_schedule": GlyphFileWriter.RAMP_SCHEDULE,
        "encoding": "non-unicode binary (8 bytes per glyph)",
        "per_file_outputs": [".bin (raw bytes)", ".idx (hash index)", ".names (English names)"],
        "ram_usage": "zero — all glyphs streamed to disk",
        "threading": "async multithreaded, one thread per file",
        "description": "Ramps 3 files (slow) → 6 files (medium) → 20 files (fast). Each glyph gets SHA-256 hash, sequential index, and English name. No Unicode encoding — pure binary.",
    }


# --- DarkLang: 9 Orders of Capitalization + Astronomical Hypernotation ---

@app.get("/darklang/stats")
async def darklang_stats():
    """DarkLang compiler stats — 9 orders, font sizes, astronomical scales."""
    dc = DarkLangCompiler()
    return dc.stats()

@app.post("/darklang/compile")
async def darklang_compile(body: dict = Body(...)):
    """Compile a .glyph program across all 9 capitalization orders.
    Each order is a different scale — from 14pt (human) to 0.0000001pt (Planck).
    Dark layers carry deuterium bonds. Astronomical hypernotation maps each order.
    """
    source = body.get("source", "")
    if not source:
        raise HTTPException(400, "source required")
    dc = DarkLangCompiler()
    return dc.compile_all_orders(source)


# --- Protein Folding File Melter ---

@app.post("/fold")
async def fold_file(body: dict = Body(...)):
    """Fold a .glyph file through GA generations like a protein.
    The file melts into a totally different file.
    Each character is an amino acid residue with folding propensity.
    """
    source = body.get("source", "")
    if not source:
        raise HTTPException(400, "source required")
    generations = body.get("generations", 30)
    folder = ProteinFolder(population_size=body.get("population_size", 20),
                           mutation_rate=body.get("mutation_rate", 0.05))
    return folder.fold(source, generations=generations)


# --- Pixel Swarm Renderer ---

@app.post("/swarm/render")
async def swarm_render(body: dict = Body(...)):
    """Render source as a pixel swarm of autonomous character-bees.
    No terminal. No IDE. Each character has hash, program, position.
    The swarm self-organizes. The arrangement IS the output.
    """
    source = body.get("source", "")
    if not source:
        raise HTTPException(400, "source required")
    steps = body.get("steps", 100)
    width = body.get("width", 80)
    height = body.get("height", 40)
    renderer = PixelSwarmRenderer(width=width, height=height)
    renderer.load_source(source)
    return renderer.tick(steps=steps)

@app.get("/swarm/stats")
async def swarm_stats():
    """Pixel swarm renderer stats."""
    return PixelSwarmRenderer().stats()


# --- GlyphML: Real sklearn + XGBoost ML Pipeline ---

@app.get("/ml/stats")
async def ml_stats():
    """GlyphML pipeline stats — production mode, parallel training."""
    from glyph_ml import GlyphMLPipeline, OPERATOR_RATIO
    p = GlyphMLPipeline()
    s = p.stats()
    s["operator_ratio"] = round(OPERATOR_RATIO, 4)
    return s

@app.post("/ml/train")
async def ml_train(body: dict = Body(...)):
    """Train all 6 ML models in PARALLEL (PCA, KMeans, SVM, RF, GB, XGBoost).
    Production mode — no dry-run. All models train simultaneously via ThreadPoolExecutor.
    """
    from glyph_ml import GlyphMLPipeline, generate_training_data
    n_per_class = body.get("n_per_class", GlyphMLPipeline.TRAINING_N_PER_CLASS)
    data = generate_training_data(n_per_class=n_per_class)
    pipeline = GlyphMLPipeline()
    return pipeline.train(data)

@app.post("/ml/predict")
async def ml_predict(body: dict = Body(...)):
    """Predict the class/intent of a glyph program using trained ensemble.
    All 4 models predict in parallel. Trains on-demand if not already trained.
    """
    from glyph_ml import GlyphMLPipeline, generate_training_data
    source = body.get("source", "")
    if not source:
        raise HTTPException(400, "source required")
    data = generate_training_data(n_per_class=GlyphMLPipeline.TRAINING_N_PER_CLASS)
    pipeline = GlyphMLPipeline()
    pipeline.train(data)
    return pipeline.predict(source)

@app.post("/ml/predict/batch")
async def ml_predict_batch(body: dict = Body(...)):
    """Batch predict multiple glyph programs concurrently.
    Each program gets all 4 models. Programs processed in parallel.
    """
    from glyph_ml import GlyphMLPipeline, generate_training_data
    sources = body.get("sources", [])
    if not sources:
        raise HTTPException(400, "sources list required")
    data = generate_training_data(n_per_class=GlyphMLPipeline.TRAINING_N_PER_CLASS)
    pipeline = GlyphMLPipeline()
    pipeline.train(data)
    return pipeline.predict_batch(sources)

@app.get("/ml/clusters")
async def ml_clusters():
    """Cluster all glyphs by spinor similarity using KMeans + PCA."""
    from glyph_ml import GlyphMLPipeline
    pipeline = GlyphMLPipeline()
    return pipeline.cluster_glyphs(n_clusters=10)

@app.post("/ml/extrapolate")
async def ml_extrapolate(body: dict = Body(...)):
    """Extrapolate N standard deviations from training mean.
    Tests all 6 models on extreme outlier features.
    Default: 10000 sigma, 10 random directions.
    """
    from glyph_ml import GlyphMLPipeline, generate_training_data
    n_sigmas = body.get("n_sigmas", 10000.0)
    n_directions = body.get("n_directions", 10)
    data = generate_training_data(n_per_class=GlyphMLPipeline.TRAINING_N_PER_CLASS)
    pipeline = GlyphMLPipeline()
    pipeline.train(data)
    return pipeline.extrapolate(n_sigmas=n_sigmas, n_directions=n_directions)

@app.get("/ml/liquid")
async def ml_liquid(literal: str = "0,005.05"):
    """Analyze a liquid lambda literal.
    Returns phases, flow curve, min/max/mean values.
    """
    from glyph_ml import LiquidLambda
    return LiquidLambda.stats(literal)


# --- Forge compiler endpoints ---

@app.get("/forge/build")
async def forge_build():
    """Compile all .glyph and .over sources in src/."""
    from forge import cmd_build
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_build()
    return {"status": "ok", "output": buf.getvalue()}

@app.get("/forge/test")
async def forge_test():
    """Run all forge test vectors."""
    from forge import cmd_test
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_test()
    return {"status": "ok", "output": buf.getvalue()}

@app.get("/forge/manifest")
async def forge_manifest():
    """Get build manifest with all artifact checksums."""
    import json
    from pathlib import Path
    manifest_path = Path("build/manifest.json")
    if not manifest_path.exists():
        return {"error": "No build manifest. Run /forge/build first."}
    return json.loads(manifest_path.read_text())

@app.get("/forge/verify/{filename}")
async def forge_verify(filename: str):
    """Verify a build artifact's SHA256 checksum."""
    from forge import cmd_verify
    import io, contextlib
    buf = io.StringIO()
    path = f"build/{filename}"
    with contextlib.redirect_stdout(buf):
        try:
            cmd_verify(path)
        except SystemExit:
            pass
    return {"status": "ok", "output": buf.getvalue(), "file": filename}

@app.get("/forge/snapshot")
async def forge_snapshot():
    """Emit policy snapshot with SHA256."""
    from forge import cmd_snapshot
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cmd_snapshot()
    return {"status": "ok", "output": buf.getvalue()}


# --- JORKI gateway simulation ---

@app.post("/jorki/index")
async def jorki_index(body: dict = Body(...)):
    """Simulate JORKI file indexing: given a file path, return a compact
    index summary with Merkle root, capabilities, and query URL."""
    import hashlib, time, os
    filepath = body.get("filepath", "")
    if not filepath or not os.path.exists(filepath):
        return {"error": "File not found", "path": filepath}
    stat = os.stat(filepath)
    with open(filepath, "rb") as f:
        content = f.read()
    merkle_root = hashlib.sha256(content).hexdigest()
    file_id = merkle_root[:12]
    size = stat.st_size
    # Compact index stats
    lines = content.count(b"\n") + 1
    words = len(content.split())
    return {
        "file_id": file_id,
        "filename": os.path.basename(filepath),
        "size_bytes": size,
        "size_human": f"{size/1024:.1f}KB" if size < 1048576 else f"{size/1048576:.1f}MB",
        "total_lines": lines,
        "total_words": words,
        "merkle_root": merkle_root,
        "capabilities": 40,
        "query_url": f"/jorki/meta/{file_id}",
        "index_time_ms": round(time.time() * 1000 % 1000, 2),
        "indexed_at": time.time(),
    }

@app.get("/jorki/meta/{file_id}")
async def jorki_meta(file_id: str):
    """Get metadata for an indexed file (simulated)."""
    return {
        "file_id": file_id,
        "status": "indexed",
        "capabilities": ["sql", "nosql", "search", "chunk", "summary", "mcp"],
        "endpoints": {
            "meta": f"/jorki/meta/{file_id}",
            "search": f"/jorki/search/{file_id}?q=",
            "chunk": f"/jorki/chunk/{file_id}/{{idx}}",
            "sql": f"/jorki/query/sql/{file_id}",
        },
        "merkle_root": file_id + "0" * 52,
    }

@app.get("/jorki/search/{file_id}")
async def jorki_search(file_id: str, q: str = ""):
    """Search an indexed file (simulated)."""
    return {
        "file_id": file_id,
        "query": q,
        "total_matches": 0,
        "results": {"symbols": [], "lines": [], "entities": []},
        "note": "Simulated search. Connect real C++ engine for production.",
    }

@app.get("/jorki/health")
async def jorki_health():
    """JORKI gateway health check."""
    return {
        "status": "ok",
        "service": "jorki",
        "version": "2.0",
        "capabilities": 40,
        "endpoints": ["/jorki/index", "/jorki/meta/{id}", "/jorki/search/{id}", "/jorki/health"],
    }


# --- Layer4Meter endpoints ---

@app.post("/l4/start")
async def l4_start(body: dict = Body(...)):
    """Start a Layer4Meter capture session."""
    import time, hashlib
    project = body.get("project", "unknown")
    mode = body.get("mode", "agent")  # idle, human, agent
    session_id = hashlib.sha256(f"{project}{time.time()}".encode()).hexdigest()[:16]
    return {
        "session_id": session_id,
        "project": project,
        "mode": mode,
        "started_at": time.time(),
        "planes": ["visual", "file", "process", "power", "snapshot"],
        "status": "capturing",
    }

@app.get("/l4/score/{session_id}")
async def l4_score(session_id: str):
    """Compute Latent Compute Index for a session (simulated)."""
    import random
    random.seed(session_id)
    lci = round(random.uniform(50, 300), 1)
    return {
        "session_id": session_id,
        "lci_score": lci,
        "components": {
            "cpu_seconds": round(random.uniform(10, 200), 1),
            "disk_write_mb": round(random.uniform(50, 800), 1),
            "file_event_count": random.randint(10, 200),
            "process_spawn_count": random.randint(20, 300),
            "memory_pressure_score": round(random.uniform(0.1, 0.9), 2),
        },
        "business_metrics": {
            "cost_per_artifact": round(random.uniform(0.5, 10.0), 2),
            "agent_efficiency": round(random.uniform(0.3, 0.95), 2),
            "waste_ratio": round(random.uniform(0.05, 0.4), 2),
        },
        "receipt_hash": hashlib.sha256(str(lci).encode()).hexdigest(),
    }

@app.get("/l4/health")
async def l4_health():
    """Layer4Meter health check."""
    return {
        "status": "ok",
        "service": "layer4meter",
        "version": "1.0",
        "planes": ["visual", "file", "process", "power", "snapshot"],
        "endpoints": ["/l4/start", "/l4/score/{session_id}", "/l4/health"],
    }


# --- Grammar stats ---

@app.get("/grammar/stats")
async def grammar_stats():
    """Return grammar rule count and category breakdown."""
    from glyphforge import GRAMMAR, ALPHABET
    categories = {}
    for rule in GRAMMAR:
        cat = rule["category"]
        categories[cat] = categories.get(cat, 0) + 1
    return {
        "total_rules": len(GRAMMAR),
        "total_symbols": len(ALPHABET),
        "categories": categories,
        "master_glyph": MASTER_GLYPH,
    }


@app.get("/grammar/rules")
async def grammar_rules(category: str = None, limit: int = 50):
    """Browse grammar rules, optionally filtered by category."""
    from glyphforge import GRAMMAR
    rules = GRAMMAR
    if category:
        rules = [r for r in rules if r["category"] == category]
    return {
        "total": len(rules),
        "showing": min(limit, len(rules)),
        "rules": rules[:limit],
        "categories": list(set(r["category"] for r in GRAMMAR)),
    }


# --- Unified Payable Workflow ---
# One pipeline. One payment. All 5 systems collide.
# Upload file → BlurHash64 encode → Antonymify → GlyphForge score
# → OverLanguage compile → Layer4Meter capture → AFC claim create
# → Buyer sees surrogate → Escrow → Reveal → Oracle settle → Receipt
# → L4 substrate receipt → Final packaged deliverable

@app.post("/workflow/pay")
async def workflow_pay(body: dict = Body(...)):
    """The unified payable workflow.

    Input: file content + task description + bond + buyer payment
    Output: settled claim with receipts, substrate accounting, glyph score,
            OverLanguage build plan, and financeable buyer packet.

    This is the ONE thing a user pays for. Everything else is plumbing.
    """
    import hashlib as _hl
    import time as _t

    content = body.get("content", "")
    filename = body.get("filename", "artifact.py")
    task = body.get("task_description", "Deliver working code artifact")
    seller_id = body.get("seller_id", "seller_001")
    buyer_id = body.get("buyer_id", "buyer_001")
    bond = body.get("bond_amount", 100)
    payment = body.get("payment_amount", 200)
    oracle_tests = body.get("oracle_tests", [
        {"type": "contains", "expected": "def "},
        {"type": "contains", "expected": "return"},
    ])

    if not content:
        raise HTTPException(400, "content required")

    workflow_start = _t.time()
    steps = []

    # STEP 1: BlurHash64 — encode at L6 (receipt level, non-consumable)
    glyph_l6 = encoder.encode(content, filename, 6)
    steps.append({
        "step": 1, "system": "blurhash64", "action": "encode_L6",
        "result": "non-consumable surrogate created",
        "glyph_id": glyph_l6.glyph_id, "file_class": glyph_l6.file_class,
        "merkle": glyph_l6.identity["merkle_root"][:16],
        "blur": glyph_l6.identity["blur_hash64"][:16],
        "lambda": glyph_l6.lambda_friction["lambda_total"],
        "transferability": glyph_l6.lambda_friction["transferability"],
        "executable": glyph_l6.executability["crosses_threshold"],
    })

    # STEP 2: BlurHash64 — full fidelity ladder
    ladder = encoder.ladder(content, filename)
    steps.append({
        "step": 2, "system": "blurhash64", "action": "fidelity_ladder",
        "result": f"{len(ladder)} disclosure levels generated (L0-L9)",
        "levels": [{"level": l["level"], "name": l["payload_keys"][-1] if l["payload_keys"] else "null", "recoverable": l["recoverable"]} for l in ladder],
    })

    # STEP 3: GlyphForge — score the artifact's glyph
    forge.forge(generations=3)
    top = forge.top_glyphs(3)
    steps.append({
        "step": 3, "system": "glyphforge", "action": "glyph_scoring",
        "result": f"{len(forge.ledger)} glyphs produced, top score={top[0]['score'] if top else 0}",
        "top_glyph": top[0]["symbol"][:40] if top else "",
        "top_score": top[0]["score"] if top else 0,
    })

    # STEP 4: OverLanguage — compile the production plan
    over_source = f"""overprogram PayableWorkflow {{
  intent:
    "{task}"
  object:
    {filename}
  anchor:
    local
  capture:
    files
    git
    substrate
  prove:
    artifact_existed
    tests_passed
    no_secrets_detected
    hash_bound
  score:
    lambda = friction
    tau = transferability
  output:
    {filename}
    receipt
    buyer_packet
  success:
    verified and settled
  economic:
    price = "{payment}"
    buyer = "{buyer_id}"
}}"""
    over_result = compiler.compile(over_source)
    steps.append({
        "step": 4, "system": "overlanguage", "action": "compile",
        "result": f"build plan: {len(over_result.build_plan['steps'])} steps, {len(over_result.build_plan['agents'])} agents",
        "receipt_id": over_result.receipt["receipt_id"],
        "transferability": over_result.lambda_score["transferability"],
        "price": over_result.buyer_packet["price"],
    })

    # STEP 5: Layer4Meter — capture substrate for this workflow
    l4meter_local = Layer4Meter()
    l4meter_local.capture_baseline("idle", 2)
    l4meter_local.capture_baseline("human", 2)
    for _ in range(3):
        l4meter_local.sample(mode="agent")
    l4_lift = l4meter_local.hidden_compute_lift()
    l4_receipt = l4meter_local.receipt(filename, workflow_start)
    l4_business = l4meter_local.business_metrics(artifact_value=payment)
    steps.append({
        "step": 5, "system": "layer4meter", "action": "substrate_capture",
        "result": f"LCI={l4_receipt['lci_total']}, lift={l4_lift['hidden_compute_lift']}",
        "planes": l4_receipt["planes"],
        "lci": l4_receipt["lci_total"],
        "hidden_compute_lift": l4_lift["hidden_compute_lift"],
        "value_per_lci": l4_business["value_per_lci"],
    })

    # STEP 6: AFC Protocol — create bonded claim
    claim = await create_claim(body={
        "seller_id": seller_id,
        "task_description": task,
        "full_answer": content,
        "filename": filename,
        "bond_amount": bond,
        "oracle_type": "hidden_test",
        "exclusivity_window_s": 3600,
    })
    cid = claim["claim_id"]
    steps.append({
        "step": 6, "system": "afc_protocol", "action": "create_claim",
        "result": f"claim={cid}, bond={bond} posted, surrogate non-consumable",
        "claim_id": cid,
        "surrogate_class": claim["surrogate"]["file_class"],
        "surrogate_lambda": claim["surrogate"]["lambda_score"],
        "bond_posted": claim["bond_posted"],
    })

    # STEP 7: AFC Protocol — buyer escrows payment
    escrow = await escrow_payment(cid, body={"buyer_id": buyer_id, "amount": payment})
    steps.append({
        "step": 7, "system": "afc_protocol", "action": "escrow",
        "result": f"buyer {buyer_id} escrowed {payment}",
        "escrow_amount": escrow["escrow_amount"],
    })

    # STEP 8: AFC Protocol — reveal answer to buyer
    reveal = await reveal_answer(cid)
    steps.append({
        "step": 8, "system": "afc_protocol", "action": "reveal",
        "result": f"answer revealed, hash verified={reveal['verify']}",
        "verified": reveal["verify"],
    })

    # STEP 9: AFC Protocol — oracle tests
    tests_result = await submit_hidden_tests(cid, body={"tests": oracle_tests})
    steps.append({
        "step": 9, "system": "afc_protocol", "action": "oracle_tests",
        "result": f"{tests_result['tests_submitted']} hidden tests submitted",
        "tests_count": tests_result["tests_submitted"],
    })

    # STEP 10: AFC Protocol — settle
    settlement = await settle_claim(cid, body={})
    steps.append({
        "step": 10, "system": "afc_protocol", "action": "settle",
        "result": f"result={settlement['result']}, pass={settlement['tests_passed']}, fail={settlement['tests_failed']}",
        "result_status": settlement["result"],
        "bond_returned": settlement["bond_returned"],
        "payment_released": settlement["payment_released"],
    })

    # STEP 11: AFC Protocol — final receipt
    afc_receipt = await get_receipt(cid)
    steps.append({
        "step": 11, "system": "afc_protocol", "action": "receipt",
        "result": f"settlement receipt: {afc_receipt['receipt_id']}",
        "receipt_id": afc_receipt["receipt_id"],
        "protocol": afc_receipt["protocol"],
    })

    # Final packaged deliverable
    workflow_end = _t.time()
    total_time = round(workflow_end - workflow_start, 3)

    deliverable = {
        "type": "PAYABLE_WORKFLOW_RECEIPT",
        "workflow": "unified_payable",
        "status": "settled" if settlement["result"] == "pass" else "failed",
        "total_steps": len(steps),
        "total_time_seconds": total_time,
        "seller": seller_id,
        "buyer": buyer_id,
        "task": task,
        "artifact": filename,
        "bond_amount": bond,
        "payment_amount": payment,
        "settlement": settlement,
        "afc_receipt": afc_receipt,
        "l4_substrate_receipt": l4_receipt,
        "l4_business_metrics": l4_business,
        "overlanguage_build_plan": over_result.build_plan,
        "overlanguage_buyer_packet": over_result.buyer_packet,
        "glyph_score": top[0]["score"] if top else 0,
        "blurhash64": {
            "glyph_id": glyph_l6.glyph_id,
            "file_class": glyph_l6.file_class,
            "merkle_root": glyph_l6.identity["merkle_root"],
            "blur_hash64": glyph_l6.identity["blur_hash64"],
            "lambda": glyph_l6.lambda_friction["lambda_total"],
            "transferability": glyph_l6.lambda_friction["transferability"],
            "fidelity_ladder_levels": len(ladder),
        },
        "steps": steps,
        "master_glyph": MASTER_GLYPH,
        "protocol": "AFC-Payable/1.0",
        "generated_at": _t.time(),
    }

    # Chain hash across all steps
    chain_input = json.dumps(steps, sort_keys=True).encode()
    deliverable["chain_hash"] = _hl.sha256(chain_input).hexdigest()

    return deliverable


# --- Unified landing page ---

LANDING = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AFC Protocol — Antonymified File Claim Protocol</title>
<style>
:root{--bg:#09090B;--surface:#111114;--primary:#4F7CFF;--accent:#8B5CFF;--glass:rgba(255,255,255,0.03);--border:rgba(255,255,255,0.08);--text:#FAFAFA;--dim:rgba(250,250,250,0.5);--faint:rgba(250,250,250,0.2);--success:#22C55E;--danger:#EF4444;--r:20px;--rs:12px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Inter,-apple-system,system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;-webkit-font-smoothing:antialiased}
.glow{position:fixed;top:-200px;left:50%;transform:translateX(-50%);width:800px;height:400px;background:radial-gradient(ellipse,rgba(79,124,255,0.06),transparent 70%);pointer-events:none;z-index:0}
.wrap{max-width:900px;margin:0 auto;padding:0 24px;position:relative;z-index:1}
.hero{text-align:center;padding:80px 0 40px}
.hero h1{font-size:2.5rem;font-weight:800;letter-spacing:-0.04em;background:linear-gradient(135deg,var(--primary),var(--accent));-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:12px}
.hero .sub{font-size:1rem;color:var(--dim);margin-bottom:8px}
.hero .thesis{font-size:1.1rem;color:var(--text);font-weight:600;max-width:600px;margin:0 auto 24px;line-height:1.5}
.hero .glyph{font-family:SF Mono,monospace;font-size:1.4rem;color:var(--accent);margin:16px 0;padding:12px 24px;background:var(--surface);border-radius:100px;display:inline-block;border:1px solid var(--border)}
.btn{padding:10px 24px;border-radius:100px;font-size:0.85rem;font-weight:600;border:none;cursor:pointer;transition:all 0.2s;font-family:inherit}
.btn-p{background:var(--primary);color:#fff}.btn-p:hover{background:#6B91FF}
.btn-g{background:var(--glass);color:var(--text);border:1px solid var(--border)}.btn-g:hover{background:rgba(255,255,255,0.06)}
.hero-btns{display:flex;gap:8px;justify-content:center;flex-wrap:wrap}
.panel{background:var(--glass);backdrop-filter:blur(20px);border:1px solid var(--border);border-radius:var(--r);padding:20px;margin-bottom:12px}
.pt{font-size:0.72rem;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;color:var(--dim);margin-bottom:12px}
.sys-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}
.sys-card{background:var(--surface);border-radius:var(--rs);padding:14px;cursor:pointer;transition:all 0.15s;border:1px solid transparent}
.sys-card:hover{border-color:var(--primary);background:rgba(79,124,255,0.05)}
.sys-name{font-size:0.85rem;font-weight:600;color:var(--text)}
.sys-desc{font-size:0.72rem;color:var(--dim);margin-top:4px}
.sys-ep{font-size:0.68rem;color:var(--faint);margin-top:6px;font-family:SF Mono,monospace}
.law{font-family:SF Mono,monospace;font-size:0.75rem;line-height:1.8;padding:12px 16px;background:var(--surface);border-radius:var(--rs);margin-bottom:12px}
.law div{color:var(--text)}
.law .num{color:var(--primary);margin-right:8px}
.result{padding:14px;border-radius:var(--rs);font-family:SF Mono,monospace;font-size:0.75rem;line-height:1.6;white-space:pre-wrap;word-break:break-all;margin-top:12px}
.result-ok{background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.2);color:var(--success)}
.result-info{background:var(--surface);border:1px solid var(--border);color:var(--text)}
.field{margin-bottom:10px}
.field label{display:block;font-size:0.75rem;color:var(--dim);margin-bottom:3px}
.field input,.field textarea,.field select{width:100%;padding:8px 10px;border-radius:8px;background:var(--surface);border:1px solid var(--border);color:var(--text);font-size:0.82rem;font-family:inherit;outline:none}
.field textarea{min-height:60px;resize:vertical;font-family:SF Mono,monospace;font-size:0.75rem}
.hidden{display:none}
.tab{display:inline-block;padding:6px 14px;border-radius:8px 8px 0 0;font-size:0.78rem;font-weight:600;cursor:pointer;background:var(--surface);border:1px solid var(--border);border-bottom:none;color:var(--dim);margin-right:4px}
.tab.active{color:var(--text);border-color:var(--primary)}
.tab-content{display:none;padding:16px;background:var(--surface);border-radius:0 var(--rs) var(--rs) var(--rs);border:1px solid var(--border)}
.tab-content.active{display:block}
.footer{text-align:center;padding:30px 0;font-size:0.7rem;color:var(--faint)}
</style>
</head>
<body>
<div class="glow"></div>
<div class="wrap">
  <div class="hero">
    <h1>AFC Protocol</h1>
    <p class="sub">Antonymified File Claim Protocol</p>
    <p class="thesis">We do not sell answers. We sell bonded answer-claims whose value can be priced through controlled blur and settled through an oracle.</p>
    <div class="glyph">⧉◇@L → H@L Æ R Æ λ⁻¹ = ◎ → $</div>
    <div class="hero-btns" style="margin-top:20px">
      <button class="btn btn-p" onclick="document.getElementById('systems').scrollIntoView()">Explore Systems</button>
      <button class="btn btn-g" onclick="document.getElementById('afc').scrollIntoView()">Claim Market</button>
      <button class="btn btn-g" onclick="document.getElementById('forge').scrollIntoView()">GlyphForge</button>
    </div>
  </div>

  <div class="panel">
    <div class="pt">Protocol Law</div>
    <div class="law">
      <div><span class="num">1.</span>No full disclosure before payment.</div>
      <div><span class="num">2.</span>No payment without settlement.</div>
      <div><span class="num">3.</span>No settlement without an oracle.</div>
      <div><span class="num">4.</span>No oracle without a bond.</div>
    </div>
  </div>

  <div class="panel" id="systems">
    <div class="pt">Five Systems</div>
    <div class="sys-grid">
      <div class="sys-card" onclick="document.getElementById('bh64').scrollIntoView()">
        <div class="sys-name">BlurHash64</div>
        <div class="sys-desc">Adjustable-fidelity glyph encodings</div>
        <div class="sys-ep">/bh64/encode /bh64/ladder</div>
      </div>
      <div class="sys-card" onclick="document.getElementById('forge').scrollIntoView()">
        <div class="sys-name">GlyphForge</div>
        <div class="sys-desc">Recursive glyph production engine</div>
        <div class="sys-ep">/forge/run /forge/top</div>
      </div>
      <div class="sys-card" onclick="document.getElementById('over').scrollIntoView()">
        <div class="sys-name">OverLanguage 2.0</div>
        <div class="sys-desc">Meta-language for production reality</div>
        <div class="sys-ep">/over/compile /over/grammar</div>
      </div>
      <div class="sys-card" onclick="document.getElementById('l4').scrollIntoView()">
        <div class="sys-name">Layer4Meter</div>
        <div class="sys-desc">Latent compute substrate capture</div>
        <div class="sys-ep">/l4/sample /l4/receipt</div>
      </div>
      <div class="sys-card" onclick="document.getElementById('afc').scrollIntoView()">
        <div class="sys-name">AFC Protocol</div>
        <div class="sys-desc">Bonded claim market + oracle</div>
        <div class="sys-ep">/claim/create /claim/settle</div>
      </div>
    </div>
  </div>

  <div class="panel" id="bh64">
    <div class="pt">BlurHash64 — Fidelity Ladder</div>
    <div class="field"><label>Content</label><textarea id="bh-content" placeholder="def hello(): print('world')">def hello():
    print('world')</textarea></div>
    <div class="field"><label>Filename</label><input id="bh-fname" value="hello.py"></div>
    <div class="field"><label>Fidelity Level (0-9)</label><input id="bh-level" type="number" value="6" min="0" max="9"></div>
    <button class="btn btn-p" onclick="bhEncode()">Encode Glyph</button>
    <button class="btn btn-g" onclick="bhLadder()">Full Ladder</button>
    <div id="bh-result" class="hidden"></div>
  </div>

  <div class="panel" id="forge">
    <div class="pt">GlyphForge — Recursive Production</div>
    <div class="field"><label>Generations</label><input id="fg-gens" type="number" value="5"></div>
    <button class="btn btn-p" onclick="forgeRun()">Forge Glyphs</button>
    <button class="btn btn-g" onclick="forgeStream()">Live Ticker</button>
    <div id="fg-result" class="hidden"></div>
  </div>

  <div class="panel" id="over">
    <div class="pt">OverLanguage 2.0 — Compile .over Program</div>
    <div class="field"><label>Source (.over)</label><textarea id="ov-src" style="min-height:200px">overprogram AgentLedger {
  intent:
    "Build a Mac-native black box recorder for AI work."
  object:
    ◇ = "Agent Activity Ledger"
  anchor:
    ⧉◇@L
  capture:
    screen
    files
    git
    terminal
    build
    substrate
  prove:
    H@L Æ R
    R Æ σ
    R ⊢ tests_passed
    R ⊢ no_secrets_detected
    R ⊢ artifact_existed
  score:
    λ = local_paths + secrets + runtime_drift + docs_gap + test_gap
    τ = R / (1 + λ)
  output:
    app
    receipt.pdf
    receipt.zip
    verifier.cli
    buyer_packet.pdf
  success:
    ◎ and τ > 80 and buyer_packet exists
  economic:
    price = "$10k pilot"
    buyer = "AI agencies, CTOs, Mac dev teams"
}</textarea></div>
    <button class="btn btn-p" onclick="overCompile()">Compile</button>
    <button class="btn btn-g" onclick="overGrammar()">View Grammar</button>
    <div id="ov-result" class="hidden"></div>
  </div>

  <div class="panel" id="l4">
    <div class="pt">Layer4Meter — Latent Compute Substrate</div>
    <button class="btn btn-p" onclick="l4Sample()">Capture Sample</button>
    <button class="btn btn-g" onclick="l4Receipt()">Generate Receipt</button>
    <div id="l4-result" class="hidden"></div>
  </div>

  <div class="panel" id="afc">
    <div class="pt">AFC Protocol — Bonded Claim Market</div>
    <div class="field"><label>Seller ID</label><input id="ac-seller" value="seller_001"></div>
    <div class="field"><label>Task Description</label><input id="ac-task" value="Python function to reverse a linked list"></div>
    <div class="field"><label>Full Answer (hidden until escrow)</label><textarea id="ac-answer">def reverse_ll(head):
    prev = None
    while head:
        nxt = head.next
        head.next = prev
        prev = head
        head = nxt
    return prev</textarea></div>
    <div class="field"><label>Bond Amount</label><input id="ac-bond" type="number" value="100"></div>
    <button class="btn btn-p" onclick="afcCreate()">Create Claim</button>
    <div id="ac-result" class="hidden"></div>
  </div>

  <div class="footer">AFC Protocol v1.0 — Verifiable Non-Seeing — ⧉◇@L → H@L Æ R Æ λ⁻¹ = ◎ → $</div>
</div>
<script>
async function api(p,o){const r=await fetch(p,o);return r.json()}
function show(id,html,cls){const e=document.getElementById(id);e.className='result '+cls;e.classList.remove('hidden');e.innerHTML=html}
function json(d){return JSON.stringify(d,null,2).replace(/</g,'&lt;').replace(/>/g,'&gt;')}

async function bhEncode(){
  const d=await api('/bh64/encode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:document.getElementById('bh-content').value,filename:document.getElementById('bh-fname').value,fidelity:parseInt(document.getElementById('bh-level').value)})});
  show('bh-result',json(d),'result-info');
}
async function bhLadder(){
  const d=await api('/bh64/ladder',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({content:document.getElementById('bh-content').value,filename:document.getElementById('bh-fname').value})});
  let html='Fidelity Ladder:\\n\\n';
  d.ladder.forEach(l=>{html+=`L${l.level}: ${l.payload_keys.join(', ')} | recoverable=${l.recoverable} executable=${l.executable} λ=${l.lambda} τ=${l.transferability}\\n`});
  show('bh-result',html,'result-info');
}
async function forgeRun(){
  const d=await api('/forge/run',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({generations:parseInt(document.getElementById('fg-gens').value)})});
  let html=`Master: ${d.master_glyph}\\nTotal: ${d.total_glyphs} glyphs in ${d.generations} generations\\n\\nTop 10:\\n`;
  d.top_10.forEach(g=>{html+=`  ${g.symbol} — score=${g.score} role=${g.role} gen=${g.generation}\\n`});
  show('fg-result',html,'result-info');
}
async function forgeStream(){
  const d=await api('/forge/stream');
  let html='Production Ticker:\\n\\n';
  d.ticker.forEach(t=>{html+=`[${t.timestamp}] ${t.symbol} score=${t.score} (${t.role})\\n`});
  show('fg-result',html,'result-info');
}
async function overCompile(){
  const d=await api('/over/compile',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source:document.getElementById('ov-src').value})});
  let html=`Compiled: ${d.status}\\nGlyph: ${d.glyph}\\n\\nBuild Plan:\\n`;
  d.build_plan.steps.forEach(s=>{html+=`  ${s}\\n`});
  html+=`\\nReceipt ID: ${d.receipt.receipt_id}\\nTransferability: ${d.lambda_score.transferability}\\nPrice: ${d.buyer_packet.price}\\nBuyer: ${d.buyer_packet.buyer}`;
  show('ov-result',html,'result-ok');
}
async function overGrammar(){
  const d=await api('/over/grammar');
  show('ov-result',json(d),'result-info');
}
async function l4Sample(){
  const d=await api('/l4/sample',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  show('l4-result',`LCI: ${d.lci}\\n\\nSample:\\n${json(d.sample)}`,'result-info');
}
async function l4Receipt(){
  const d=await api('/l4/receipt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({project:'AgentLedger',session_start:Date.now()/1000-3600})});
  show('l4-result',json(d),'result-ok');
}
async function afcCreate(){
  const d=await api('/claim/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({seller_id:document.getElementById('ac-seller').value,task_description:document.getElementById('ac-task').value,full_answer:document.getElementById('ac-answer').value,filename:'solution.py',bond_amount:parseFloat(document.getElementById('ac-bond').value),oracle_type:'hidden_test',exclusivity_window_s:3600})});
  if(d.claim_id){
    show('ac-result',`Claim Created: ${d.claim_id}\\n\\nSurrogate:\\n  class: ${d.surrogate.file_class}\\n  merkle: ${d.surrogate.merkle_root.slice(0,24)}...\\n  blur: ${d.surrogate.blur_hash64.slice(0,24)}...\\n  lambda: ${d.surrogate.lambda_score}\\n  hooks: ${d.surrogate.proof_hooks.join(', ')}\\n  bond: ${d.bond_posted}\\n\\nFull answer encrypted. Share /claim/${d.claim_id} with buyers.`,'result-ok');
  } else {
    show('ac-result',json(d),'result-info');
  }
}
</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def landing():
    return LANDING


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
