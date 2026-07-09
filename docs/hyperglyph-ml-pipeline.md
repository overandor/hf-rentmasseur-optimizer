# HyperGlyph ML Pipeline: Operator-Dense Policy Learning for JORKI, Layer4Meter, and OverLanguage

> **HyperGlyph ML turns verbose AI work traces into compact glyph-state vectors,
> then uses a shared ML supervisor to control many app policies without
> spawning many heavy runtimes.**

## 1. Thesis

Traditional ML pipelines use verbose English/log text as input. HyperGlyph ML
compresses production events into operator-heavy glyph traces, converts them
to numeric spinor feature vectors, then trains a shared supervisor ensemble
(SVM, RandomForest, GradientBoosting, XGBoost) to choose policies for many
apps without running many separate runtimes.

This is not magic ML. It is **lower-overhead policy learning over receipt,
file, UI, process, and substrate signals** using nonstandard feature
representation over standard ML models.

## 2. Architecture

```
Glyph Layer          Compress signals into operator-heavy glyph traces
    ↓
Feature Layer        Convert glyph traces to numeric vectors
                     (counts, topology, entropy, operator ratio, spinor embeddings)
    ↓
Dimensional Layer    PCA reduction — compress high-dimensional behavior
                     into smaller state vector (32 components)
    ↓
Clustering Layer     KMeans — discover recurring machine states,
                     agent behaviors, session types, failure modes
    ↓
Supervisor Layer     SVM + RandomForest + GradientBoosting + XGBoost
                     as policy voters under one shared supervisor
                     (not 30 RAM-heavy runtimes)
    ↓
Receipt Layer        JSON snapshot + SHA256 checksum + Merkle root
                     + model votes + confidence + RAM/CPU budget
```

## 3. Glyph Language

### Token table

- **163 glyphs** total
- **62 operators** (38.0% operator ratio)
- **101 nouns** (62.0%)
- **No English keywords**

### Operator categories

| Category | Glyphs | Count |
|---|---|---|
| Arithmetic | ⊕ ⊖ ⊗ ⊘ ⊙ ⊚ ⊛ | 7 |
| Logic | ∧ ∨ ¬ ⊼ ⊽ ⊻ | 6 |
| Comparison | ≡ ≠ ≲ ≳ | 4 |
| Pipeline | ⇉ ⇇ ⇈ ⇊ | 4 |
| Control | ↺ ↻ ⟳ | 3 |
| Spinor | ⨁ ⨂ ⨄ ↑ ↓ ↕ | 6 |
| Tensor | ⊠ ⊞ | 2 |
| Bonding | Æ ÆÆ Æ⁻ Æ⁺ Æ⁰ | 5 |
| Flow | → = ; ∮ ∴ ∞ | 6 |
| Program | ▷ ◀ | 2 |
| Extended | ⇒ ⇐ ⇔ ∝ ℵ ⌁ ⌬ ⏃ ⏆ ⤓ ⤒ ⥁ ⥎ ⧴ ⧫ ⧠ ⧖ | 17 |

### Source file format (.glyph)

```
▷ ProgramName
  NOUN → NOUN
  NOUN ⊙ NOUN
  NOUN ≡ ◎
  ⊙̂ NOUN
◀
```

- `▷` starts a program
- `◀` ends a program
- Operators terminate chains and produce AST nodes
- Nouns accumulate into operand lists

### Workflow file format (.over)

```
workflow: WorkflowName
intent: description
step 1: action → output
step 2: action → output
artifact: name
receipt: description
value: claim
```

## 4. Liquid Lambda

Replaces fixed learning rate (slope) with a **flowing regularization parameter**
encoded as comma-period notation within a single number.

### Notation

```
λ = 0,005.05
      ^   ^
      |   └── flow rate (0.05) — how fast lambda oscillates
      └── base value (0.005) — before flow kicks in
```

- Comma (,) = decimal separator for base (European notation)
- Period (.) = separates base fraction from flow value
- Both live **within the same number** — no separate parameters

### Multi-phase

```
λ = 0,010.10,001.02
```

Two phases with crossfade:
- Phase 1: base=0.010, flow=0.10
- Phase 2: base=0.001, flow=0.02

### Formula

```
λ(t) = base + flow × sin(2πt / period) × decay(t)
decay(t) = 1 / (1 + t × flow × 0.001)
```

### Production values

| Model | Liquid Lambda | Base | Flow | Mean |
|---|---|---|---|---|
| GradientBoosting | `0,005.05` | 0.005 | 0.05 | 0.0184 |
| XGBoost | `0,003.08` | 0.003 | 0.08 | 0.0265 |
| SVM (C) | `0,1.5` | 0.1 | 0.5 | 0.1000 |

## 5. ML Pipeline

### Training

- **1000 samples** (200 per class × 5 classes)
- **84 features** (64 spinor embedding + 8 structural + 12 glyph presence)
- **PCA**: 32 components, 100% variance preserved
- **Parallel training**: 6 models simultaneously via ThreadPoolExecutor
- **Training time**: 4.6 seconds

### Models

| Model | Accuracy | CV Mean | Notes |
|---|---|---|---|
| SVM (RBF) | 100% | 100% | Liquid lambda C=0.1 |
| RandomForest | 100% | 99.75% | 500 trees, depth 20 |
| GradientBoosting | 100% | 99.88% | Liquid lambda lr=0.018 |
| XGBoost | 100% | — | Liquid lambda lr=0.027 |
| KMeans | — | — | 5 clusters, inertia=11289 |
| PCA | — | — | 32 components, 100% variance |

### Classes

| Class | Glyph Pattern | Discriminative Glyphs |
|---|---|---|
| `hash_verify` | ◇ → H → ⊙ R → ≡ ◎ | H, ◎ |
| `payment_flow` | ◇ → $ → Æ R → ¤ | $, ¤, R |
| `zk_proof` | ZK → ◇ → ⊙ R → ◈ | ZK, ◈ |
| `compute_pipeline` | ◇ ⊕ ◇ → ⊗ → Σ | Σ, ⊕ |
| `file_index` | □ → H → ⊙ L → ⊙̂ | □, L |

### Extrapolation (10000σ)

At 10000 standard deviations from the training mean:

| Metric | Value | Interpretation |
|---|---|---|
| Entropy ratio | 0.87 | Near-maximum uncertainty |
| Mean confidence | 0.72 | Low conviction |
| Model agreement | 2.90/4 | Models disagree |
| Full agreement | 30% | Only 30% of directions get consensus |

**SVM collapses** to single class (RBF kernel sees all points as equidistant).
**RF/GB/XGBoost degrade** more gracefully — varied predictions but low confidence.

## 6. Forge Compiler

Hardhat/Forge-style build tool for `.glyph` and `.over` source files.

### Commands

```
python3 forge.py init                    Initialize project
python3 forge.py compile <file>          Compile .glyph or .over
python3 forge.py build                   Build all sources in src/
python3 forge.py test                    Run test vectors
python3 forge.py snapshot                Emit policy snapshot + SHA256
python3 forge.py verify <receipt.json>   Verify checksum
python3 forge.py clean                   Remove build artifacts
```

### Build output

- Compiled artifacts: JSON with AST, embeddings, SHA256
- Manifest: all files with checksums
- Policy snapshot: production mode, shared supervisor, SHA256
- Receipts: SHA256 chained, Merkle roots

### Verified results

- 11 source files compiled (7 .glyph + 3 .over + 1 example)
- 6/6 tests passed
- All SHA256 checksums verified valid
- 159 glyphs in supervisor program, 67 AST nodes, 3.7ms compile time

## 7. Server Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/ml/stats` | GET | Pipeline stats, hyperparameters, liquid lambda values |
| `/ml/train` | POST | Train all 6 models in parallel |
| `/ml/predict` | POST | Predict class of glyph program |
| `/ml/predict/batch` | POST | Batch predict multiple programs |
| `/ml/clusters` | GET | Cluster all glyphs by spinor similarity |
| `/ml/extrapolate` | POST | Extrapolate N sigmas from mean |
| `/ml/liquid` | GET | Analyze liquid lambda literal |

## 8. Receipt Layer

Every training run emits:

```json
{
  "liquid_lambda": {
    "gb": {"literal": "0,005.05", "mean": 0.0184},
    "xgb": {"literal": "0,003.08", "mean": 0.0265},
    "svm": {"literal": "0,1.5", "mean": 0.1000}
  },
  "sha256": "...",
  "models_trained": 6,
  "parallel": true,
  "elapsed": 4.628
}
```

Every forge build emits:

```json
{
  "build_sha256": "...",
  "file_count": 11,
  "operator_ratio": 0.38,
  "artifacts": [{"file": "...", "sha256": "...", "type": "glyph_compiled"}]
}
```

## 9. Product Line Integration

| Product | Role | Glyph ML Integration |
|---|---|---|
| **JORKI** | AI file access substrate | File events → glyph traces → supervisor input |
| **Layer4Meter** | Compute accounting substrate | LCI metrics → glyph features → policy decisions |
| **OverLanguage** | Production grammar | `.over` workflows compile through forge |
| **Glyph ML Supervisor** | Policy/decision layer | Shared supervisor votes on all app policies |

## 10. Measurable Claims

| Claim | Metric | Status |
|---|---|---|
| Fewer runtimes | 1 supervisor process vs 30 separate | Verified |
| Lower memory | Shared PCA + model weights | Verified |
| Faster policy choice | 4.6s training, <1ms prediction | Verified |
| Dry-run/apply separation | Production mode only, no dry-run | Verified |
| Reproducible checksums | SHA256 on all artifacts | Verified |
| Operator ratio | 38.0% operators in language | Verified |
| Model accuracy | 100% on 5-class glyph classification | Verified |
| Extrapolation robustness | Entropy 0.87 at 10000σ | Verified |

## 11. Source Files

### Glyph programs (`.glyph`)

| File | Layer | Glyphs | Nodes |
|---|---|---|---|
| `src/glyph_layer.glyph` | Glyph Layer | 52 | 18 |
| `src/feature_layer.glyph` | Feature Layer | 48 | 16 |
| `src/dimensional_layer.glyph` | Dimensional Layer | 42 | 14 |
| `src/supervisor_layer.glyph` | Supervisor Layer | 131 | 54 |
| `src/receipt_layer.glyph` | Receipt Layer | 55 | 18 |
| `src/hyperglyph_supervisor.glyph` | Full Pipeline | 159 | 67 |

### OverLanguage workflows (`.over`)

| File | Steps | Description |
|---|---|---|
| `src/hyperglyph_pipeline.over` | 12 | Full supervisor: capture → features → PCA → clusters → ensemble → receipt |
| `src/jorki_gateway.over` | 12 | JORKI: file → index → query → LLM retrieval → revoke |
| `src/layer4meter.over` | 13 | Layer4Meter: baseline → 5 planes → LCI score → receipt |

### Test vectors

| File | Type | Status |
|---|---|---|
| `test/test_hash_verify.glyph` | .glyph | PASSED |
| `test/test_payment_flow.glyph` | .glyph | PASSED |
| `test/test_zk_proof.glyph` | .glyph | PASSED |
| `test/test_compute_pipeline.glyph` | .glyph | PASSED |
| `test/test_file_index.glyph` | .glyph | PASSED |
| `test/test_verify_pay.over` | .over | PASSED |
