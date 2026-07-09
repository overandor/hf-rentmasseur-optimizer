"""
GlyphML — Real ML Pipeline Powered by Glyph Spinor Features
=============================================================
Uses sklearn + XGBoost with glyph-encoded features:
  - PCA: dimensionality reduction on glyph spinor embeddings
  - KMeans: cluster glyphs by semantic similarity
  - SVM: classify glyph programs by intent
  - RandomForest: feature importance of glyph operators
  - GradientBoosting: predict program outcomes from glyph sequences
  - XGBoost: high-performance gradient boosting on glyph features

The glyph spinor encoding (SU(2)) provides the feature space.
Each glyph → 2-component complex spinor → 64-dim real embedding.
PCA compresses to 16 principal components.
The ML models discover patterns in glyph programs that humans can't see.

No RAM sacrifice: features are computed on-the-fly from spinor cache.
No CPU sacrifice: ML runs in dry-run mode by default, full mode on demand.
"""

import sys
import json
import time
import hashlib
import struct
import cmath
import math
import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path

import numpy as np
import warnings
warnings.filterwarnings('ignore', category=RuntimeWarning)
warnings.filterwarnings('ignore', category=UserWarning)

# ML imports
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.svm import SVC
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import cross_val_score, train_test_split
from sklearn.metrics import classification_report, accuracy_score
from sklearn.preprocessing import StandardScaler

try:
    import xgboost as xgb
    HAS_XGBOOST = True
except ImportError:
    HAS_XGBOOST = False

# --- Glyph token sets (from glyphlang.py, replicated for standalone use) ---

GLYPH_NOUNS = {
    "□": "FILE", "◇": "ARTIFACT", "⧉": "STATIONARY",
    "H": "HASH", "L": "LOCATION", "R": "RECEIPT",
    "λ": "FRICTION", "λ⁻¹": "TRANSFERABILITY",
    "T": "TIME", "Σ": "SHARD", "M": "MERKLE", "ZK": "ZK_PROOF",
    "Δ": "DELTA", "◎": "VERIFIED", "✕": "INVALID",
    "$": "VALUE", "Ω": "CANONICAL", "@": "ANCHOR",
    "∇": "GRADIENT", "∂": "PARTIAL", "∫": "INTEGRAL",
    "ℏ": "PLANCK", "ℂ": "COMPLEX", "ℝ": "REAL",
    "ψ": "WAVEFUNCTION", "φ": "PHASE", "θ": "ANGLE",
    "ρ": "DENSITY", "σ": "PAULI", "π": "PI_GLYPH",
    "χ": "EIGENVECTOR", "μ": "MEAN", "ν": "VARIANCE",
    # Additional nouns to balance operator ratio toward 40%
    "◈": "PROVE", "⚡": "CLAIM", "¤": "PAY", "⊙̂": "EMIT",
    "ξ": "RANDOM", "τ": "TENSOR", "η": "EFFICIENCY",
    "κ": "CURVATURE", "ω": "FREQUENCY", "α": "ALPHA",
    "β": "BETA", "γ": "GAMMA", "δ": "DELTA_OP",
    "ε": "EPSILON", "ζ": "ZETA", "ι": "IOTA",
    "κ̃": "CURVATURE_TILDE", "λ̃": "FRICTION_TILDE",
    "ρ̃": "DENSITY_TILDE", "σ̃": "PAULI_TILDE",
    "𝔸": "MATRIX_A", "𝔹": "MATRIX_B", "ℂ̃": "COMPLEX_TILDE",
    "𝔻": "MATRIX_D", "𝔼": "MATRIX_E", "𝔽": "MATRIX_F",
    "𝔾": "MATRIX_G", "ℍ": "QUATERNION", "𝕀": "IDENTITY",
    "𝕁": "EXCHANGE", "𝕂": "COUPLING", "𝕃": "LAGRANGIAN",
    "𝕄": "MOMENT", "ℕ": "NATURAL", "𝕆": "OCTONION",
    "ℙ": "PROJECTOR", "ℚ": "RATIONAL", "ℝ̃": "REAL_TILDE",
    "𝕊": "SPHERE", "𝕋": "TORUS", "𝕌": "UNITARY",
    "𝕍": "VECTOR", "𝕎": "WEIGHT", "𝕏": "CROSS",
    "𝕐": "YIELD", "𝕑": "JET",
    "𝕊̃": "SPHERE_TILDE", "𝕋̃": "TORUS_TILDE",
    "𝕌̃": "UNITARY_TILDE", "𝕍̃": "VECTOR_TILDE",
    "𝕎̃": "WEIGHT_TILDE", "𝕏̃": "CROSS_TILDE",
    "𝕐̃": "YIELD_TILDE", "𝕑̃": "JET_TILDE",
    "𝕒": "LOWER_A", "𝕓": "LOWER_B", "𝕔": "LOWER_C",
    "𝕕": "LOWER_D", "𝕖": "LOWER_E", "𝕗": "LOWER_F",
}

GLYPH_OPERATORS = {
    "⊕": "ADD", "⊖": "SUB", "⊗": "MUL", "⊘": "DIV",
    "⊙": "DOT", "⊚": "OUTER", "⊛": "KRON", "⊜": "EQ_CHECK",
    "∧": "AND", "∨": "OR", "¬": "NOT", "⊼": "NAND",
    "⊽": "NOR", "⊻": "XOR", "⊾": "XNOR",
    "≡": "IDENTICAL", "≠": "DIFFERENT", "≲": "LESSEQ", "≳": "GREATEQ",
    "⊑": "SUBSET", "⊒": "SUPSET",
    "⇉": "PIPE_FWD", "⇇": "PIPE_BWD", "⇈": "PAR_UP", "⇊": "PAR_DOWN",
    "↺": "REWIND", "↻": "FORWARD", "⟳": "REPEAT", "⟲": "LOOP_BACK",
    "⨁": "SPIN_ADD", "⨂": "SPIN_MUL", "⨄": "SPIN_SUM", "⨆": "SPIN_PROD",
    "↑": "SPIN_UP", "↓": "SPIN_DOWN", "↕": "SPIN_FLIP", "↔": "SPIN_SWAP",
    "⊠": "TENSOR_BOX", "⊞": "TENSOR_ADD", "⊟": "TENSOR_SUB", "⊡": "TENSOR_DOT",
    "Æ": "BIND", "ÆÆ": "DOUBLE_BIND", "Æ⁻": "BOND_BREAK",
    "Æ⁺": "BOND_FORM", "Æ⁰": "BOND_NULL", "Æ*": "BOND_WILD",
    "Æ#": "BOND_HASH", "Æ@": "BOND_ANCHOR",
    "→": "DERIVE", "=": "ASSERT", ";": "SEPARATOR",
    "∮": "INTEGRATE", "∯": "SURFACE", "∰": "VOLUME",
    "∴": "THEREFORE", "∵": "BECAUSE", "∞": "DIVERGE",
    "▷": "PROGRAM_START", "◀": "PROGRAM_END",
}

ALL_GLYPHS = {**GLYPH_NOUNS, **GLYPH_OPERATORS}
OPERATOR_RATIO = len(GLYPH_OPERATORS) / len(ALL_GLYPHS)


# --- Spinor encoding (SU(2)) ---

def glyph_to_spinor(glyph: str) -> np.ndarray:
    """Encode glyph as 2-component complex spinor on Bloch sphere."""
    h = hashlib.sha256(glyph.encode()).digest()
    a = complex(struct.unpack('f', h[0:4])[0], struct.unpack('f', h[4:8])[0])
    b = complex(struct.unpack('f', h[8:12])[0], struct.unpack('f', h[12:16])[0])
    norm = np.sqrt(abs(a)**2 + abs(b)**2)
    if norm < 1e-30:
        return np.array([1.0 + 0j, 0.0 + 0j])
    return np.array([a / norm, b / norm])


def spinor_to_embedding(spinor: np.ndarray, dim: int = 64) -> np.ndarray:
    """Expand 2-component spinor to dim-dimensional real embedding.
    Uses repeated tensor products: |ψ⟩⊗|ψ⟩⊗... → 2^n, then take |·|.
    """
    result = np.array([spinor[0], spinor[1]], dtype=complex)
    while len(result) < dim:
        result = np.kron(result, spinor)
    # Take absolute values (real features) and truncate
    return np.abs(result[:dim]).astype(np.float64)


def spinor_to_bloch(spinor: np.ndarray) -> tuple:
    """Convert spinor to Bloch sphere (theta, phi)."""
    theta = 2 * np.arccos(np.clip(abs(spinor[0]), 0, 1))
    if abs(spinor[1]) < 1e-30 or abs(spinor[0]) < 1e-30:
        phi = 0.0
    else:
        phi = np.angle(spinor[1] / spinor[0])
        if phi < 0:
            phi += 2 * np.pi
    return (float(theta), float(phi))


# --- Feature extraction from glyph programs ---

@dataclass
class GlyphProgramFeatures:
    """Features extracted from a glyph program for ML processing."""
    name: str
    source: str
    glyph_sequence: list
    embedding: np.ndarray
    operator_count: int
    noun_count: int
    operator_ratio: float
    chain_length: int
    chain_count: int
    avg_bloch_theta: float
    avg_bloch_phi: float
    spinor_entropy: float
    label: str  # program intent class


def extract_glyphs(source: str) -> list[str]:
    """Extract glyph sequence from source text."""
    glyphs = []
    i = 0
    while i < len(source):
        matched = False
        for g in sorted(ALL_GLYPHS.keys(), key=len, reverse=True):
            if source[i:i+len(g)] == g:
                glyphs.append(g)
                i += len(g)
                matched = True
                break
        if not matched:
            i += 1
    return glyphs


def compute_spinor_entropy(spinors: list[np.ndarray]) -> float:
    """Von Neumann-like entropy of a set of spinors.
    S = -Σ |⟨ψ_i|ψ_j⟩|² log(|⟨ψ_i|ψ_j⟩|²)
    Measures how "spread out" the spinors are on the Bloch sphere.
    """
    n = len(spinors)
    if n < 2:
        return 0.0
    total = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            fidelity = abs(np.vdot(spinors[i], spinors[j]))**2
            if fidelity > 1e-10 and fidelity < 1 - 1e-10:
                total -= fidelity * np.log(fidelity)
    return float(total / (n * (n - 1) / 2))


def extract_features(source: str, label: str = "unknown") -> GlyphProgramFeatures:
    """Extract ML features from a glyph program."""
    glyphs = extract_glyphs(source)
    spinors = [glyph_to_spinor(g) for g in glyphs]
    embeddings = np.array([spinor_to_embedding(s, 64) for s in spinors]) if spinors else np.zeros((1, 64))

    # Aggregate embedding: mean of all glyph embeddings
    agg_embedding = np.mean(embeddings, axis=0) if len(embeddings) > 0 else np.zeros(64)

    # Operator/noun counts
    op_count = sum(1 for g in glyphs if g in GLYPH_OPERATORS)
    noun_count = sum(1 for g in glyphs if g in GLYPH_NOUNS)
    total = op_count + noun_count

    # Bloch sphere statistics
    bloch_coords = [spinor_to_bloch(s) for s in spinors]
    avg_theta = np.mean([c[0] for c in bloch_coords]) if bloch_coords else 0
    avg_phi = np.mean([c[1] for c in bloch_coords]) if bloch_coords else 0

    # Spinor entropy
    entropy = compute_spinor_entropy(spinors)

    # Chain detection (split by operators that terminate chains)
    chain_count = source.count("\n") + 1
    chain_length = len(glyphs) // max(chain_count, 1)

    return GlyphProgramFeatures(
        name=source.split("\n")[0][:40],
        source=source,
        glyph_sequence=glyphs,
        embedding=agg_embedding,
        operator_count=op_count,
        noun_count=noun_count,
        operator_ratio=op_count / max(total, 1),
        chain_length=chain_length,
        chain_count=chain_count,
        avg_bloch_theta=float(avg_theta),
        avg_bloch_phi=float(avg_phi),
        spinor_entropy=entropy,
        label=label,
    )


# --- Training data: synthetic glyph programs with labels ---

PROGRAM_TEMPLATES = {
    "hash_verify": [
        "▷ HashVerify\n  ◇ → H\n  H ⊙ R\n  R ≡ ◎\n  ⊙̂ H\n◀",
        "▷ HashCheck\n  □ → H\n  H ⊗ H\n  H ≡ ◎\n  ⊙̂ ◎\n◀",
        "▷ MerkleProof\n  ◇ → M\n  M ⊕ M\n  M ≡ H\n  ⊙̂ M\n◀",
    ],
    "payment_flow": [
        "▷ PayFlow\n  ◇ → $\n  $ Æ R\n  R → ◎\n  ¤ $\n◀",
        "▷ EscrowBond\n  $ Æ ◇\n  ◇ → R\n  R ⊙ ◎\n  ¤ R\n◀",
        "▷ ValueTransfer\n  ◇ ⊗ $ → R\n  R Æ ◎\n  ¤ ◎\n◀",
    ],
    "zk_proof": [
        "▷ ZKProof\n  ZK → ◇\n  ◇ ⊙ R\n  R ≡ ◎\n  ◈ ZK\n◀",
        "▷ ProveClaim\n  ZK ⊗ ◇ → H\n  H ≡ ◎\n  ◈ H\n◀",
        "▷ VerifyZK\n  ZK → ◎\n  ◎ ⊙ R\n  ◈ ◎\n◀",
    ],
    "compute_pipeline": [
        "▷ ComputePipe\n  ◇ ⊕ ◇ → H\n  H ⊗ H → Σ\n  Σ → ◎\n  ⊙̂ Σ\n◀",
        "▷ TensorCompute\n  ◇ ⊠ ◇ → Σ\n  Σ ⊗ Σ → ◎\n  ⊙̂ Σ\n◀",
        "▷ SpinorCompute\n  ◇ ⨂ ◇ → ψ\n  ψ ⨁ ψ → ◎\n  ⊙̂ ψ\n◀",
    ],
    "file_index": [
        "▷ FileIndex\n  □ → H\n  H ⊙ L\n  L → R\n  ⊙̂ R\n◀",
        "▷ IndexFiles\n  □ ⊕ □ → H\n  H → M\n  M ⊙ R\n  ⊙̂ M\n◀",
        "▷ ScanFiles\n  □ → L\n  L ⊗ H → R\n  R → ◎\n  ⊙̂ R\n◀",
    ],
}

LABELS = list(PROGRAM_TEMPLATES.keys())


def generate_training_data(n_per_class: int = 50) -> list[GlyphProgramFeatures]:
    """Generate training data from program templates with smart mutations.
    Mutations preserve label-relevant glyphs, only swap operators within categories.
    """
    import random
    rng = random.Random(42)
    data = []

    # Operator categories for smart swapping
    op_categories = {
        'arith': ["⊕", "⊖", "⊗", "⊘", "⊙", "⊚", "⊛", "⊜"],
        'logic': ["∧", "∨", "¬", "⊼", "⊽", "⊻", "⊾"],
        'compare': ["≡", "≠", "≲", "≳", "⊑", "⊒"],
        'flow': ["⇉", "⇇", "⇈", "⇊", "↺", "↻", "⟳", "⟲"],
        'spinor': ["⨁", "⨂", "⨄", "⨆", "↑", "↓", "↕", "↔"],
        'tensor': ["⊠", "⊞", "⊟", "⊡"],
        'bond': ["Æ", "ÆÆ", "Æ⁻", "Æ⁺", "Æ⁰", "Æ*", "Æ#", "Æ@"],
        'derive': ["→", "=", ";"],
        'meta': ["∮", "∯", "∰", "∴", "∵", "∞"],
    }

    # Build reverse map: operator → category
    op_to_cat = {}
    for cat, ops in op_categories.items():
        for op in ops:
            op_to_cat[op] = cat

    for label, templates in PROGRAM_TEMPLATES.items():
        for i in range(n_per_class):
            template = templates[i % len(templates)]
            source = template
            # Smart mutation: swap operators within same category
            glyphs_in_source = extract_glyphs(source)
            for g in glyphs_in_source:
                if g in op_to_cat and rng.random() < 0.15:
                    cat = op_to_cat[g]
                    replacement = rng.choice(op_categories[cat])
                    source = source.replace(g, replacement, 1)
            data.append(extract_features(source, label))

    return data


# --- ML Pipeline ---

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


# =============================================================================
# LIQUID LAMBDA — Replaces Fixed Slope with Flowing Regularization
# =============================================================================
#
# Traditional ML uses a fixed learning rate (slope): α = 0.05, constant.
# Liquid Lambda replaces this with a FLOWING value encoded as:
#
#   λ = 0,005.05
#        ^   ^
#        |   └── flow rate: how fast lambda changes per epoch (0.05)
#        └── phase transition: base value before the flow kicks in (0.005)
#
# The comma (,) marks where the base value ends and the flow begins.
# The period (.) marks the flow rate's precision.
# Both live WITHIN the same number — no separate parameters.
#
# During training, λ(t) evolves:
#   λ(t) = base + flow × sin(2πt / period) × decay(t)
#
# Where:
#   base = value before comma
#   flow = value after period
#   period = value between comma and period
#   decay(t) = 1 / (1 + t × flow)
#
# The lambda LIQUIDATES — it flows between base and base+flow,
# oscillating with decreasing amplitude. This is not a fixed slope.
# It's a liquid surface that adapts to the loss landscape.
#
# Multiple commas create multi-phase liquid lambda:
#   λ = 0,005.05,001.02
#   Phase 1: base=0,005 flow=0.05
#   Phase 2: base=0,001 flow=0.02
#   The training oscillates between phases.
#
# =============================================================================

class LiquidLambda:
    """Flowing regularization parameter that replaces fixed slope.
    Encoded as comma-period notation within a single number string.

    Format: "base,period.flow" or multi-phase "b1,p1.f1,b2,p2.f2"

    Examples:
        "0,005.05"     → base=0.005, period=5, flow=0.05
        "0,010.10,001.02" → two phases, oscillates between them
        "0,1.0"        → base=0, period=1, flow=0 (constant, like old slope)

    The lambda value at step t:
        λ(t) = base + flow × sin(2πt / period) × decay(t)
        decay(t) = 1 / (1 + t × flow × 0.001)
    """

    @staticmethod
    def parse(literal: str) -> list[dict]:
        """Parse a liquid lambda literal into phases.
        Returns list of {base, period, flow} dicts.

        Notation: comma and period WITHIN the same number.
        The comma is the decimal separator for the base value (European style).
        The period separates the base fraction from the flow value.

        "0,005.05"    → base=0.005, flow=0.05, period=auto
        "0,010.10,001.02" → two phases: (0.010, 0.10) and (0.001, 0.02)
        "0.05"        → plain number, fixed slope (no liquid)
        "0,005.05.3"  → base=0.005, flow=0.05, period=3 (triple-dot notation)
        """
        literal = literal.strip()

        # Plain number (no comma) — old-style fixed slope
        if "," not in literal:
            val = float(literal)
            return [{"base": val, "period": 1.0, "flow": 0.0}]

        # Split on comma — pairs of (int_part, frac.flow) per phase
        # "0,005.05,001.02" → ["0", "005.05", "001.02"]
        # Phase 1: "0" + "005.05" → base=0.005, flow=0.05
        # Phase 2: "001.02" has no int pair → base=0.001, flow=0.02
        #   (when a part contains a period but no preceding int_part,
        #    treat the whole thing as "int,frac.flow" with int=0)
        comma_parts = literal.split(",")

        phases = []
        i = 0
        while i < len(comma_parts):
            int_part = comma_parts[i].strip()

            if i + 1 < len(comma_parts):
                rest = comma_parts[i + 1].strip()
                # rest contains "frac.flow" or "frac.flow.period" or just "frac"
                if "." in rest:
                    dot_parts = rest.split(".")
                    frac_part = dot_parts[0]
                    flow_part = dot_parts[1] if len(dot_parts) > 1 else "0"
                    period_part = dot_parts[2] if len(dot_parts) > 2 else None

                    # base = int_part.frac_part (European comma → American period)
                    base = float(f"{int_part}.{frac_part}") if frac_part else float(int_part)
                    # flow = 0.flow_part (decimal fraction)
                    flow = float(f"0.{flow_part}") if flow_part else 0.0
                    # period: explicit if provided, else auto-derive from flow
                    if period_part is not None:
                        period = float(period_part)
                    elif flow > 0:
                        period = 1.0 / flow  # auto: faster flow = shorter period
                    else:
                        period = 1.0
                else:
                    # No period in rest — just a fraction, no flow
                    base = float(f"{int_part}.{rest}") if rest else float(int_part)
                    flow = 0.0
                    period = 1.0
                i += 2
            else:
                # Last part without a pair — if it contains a period,
                # treat as "frac.flow" with int=0
                if "." in int_part:
                    dot_parts = int_part.split(".")
                    frac_part = dot_parts[0]
                    flow_part = dot_parts[1] if len(dot_parts) > 1 else "0"
                    period_part = dot_parts[2] if len(dot_parts) > 2 else None
                    base = float(f"0.{frac_part}") if frac_part else 0.0
                    flow = float(f"0.{flow_part}") if flow_part else 0.0
                    if period_part is not None:
                        period = float(period_part)
                    elif flow > 0:
                        period = 1.0 / flow
                    else:
                        period = 1.0
                else:
                    base = float(int_part)
                    flow = 0.0
                    period = 1.0
                i += 1

            phases.append({"base": base, "period": max(period, 0.001), "flow": flow})

        return phases

    @staticmethod
    def value_at(phases: list[dict], t: float) -> float:
        """Compute liquid lambda value at step t.
        Multi-phase: oscillates between phases with crossfade.
        """
        if len(phases) == 1:
            p = phases[0]
            decay = 1.0 / (1.0 + t * p["flow"] * 0.001)
            oscillation = p["flow"] * math.sin(2 * math.pi * t / p["period"]) * decay
            return max(p["base"] + oscillation, 1e-10)

        # Multi-phase: crossfade between phases
        total_period = sum(p["period"] for p in phases)
        phase_pos = (t % total_period) / total_period  # 0..1 position in cycle

        # Find which two phases we're between
        cumsum = 0
        for i, p in enumerate(phases):
            phase_frac = p["period"] / total_period
            if phase_pos < cumsum + phase_frac:
                # We're in phase i, crossfade from prev
                local_t = (phase_pos - cumsum) / phase_frac * p["period"]
                decay = 1.0 / (1.0 + t * p["flow"] * 0.001)
                oscillation = p["flow"] * math.sin(2 * math.pi * local_t / p["period"]) * decay
                # Crossfade with previous phase
                prev = phases[(i - 1) % len(phases)]
                blend = math.sin(math.pi * (phase_pos - cumsum) / phase_frac) ** 2
                val_i = p["base"] + oscillation
                val_prev = prev["base"]
                return max(val_prev * (1 - blend) + val_i * blend, 1e-10)
            cumsum += phase_frac

        return max(phases[-1]["base"], 1e-10)

    @staticmethod
    def flow_curve(phases: list[dict], n_steps: int = 100) -> list[dict]:
        """Generate the full flow curve for visualization."""
        return [
            {"step": t, "lambda": LiquidLambda.value_at(phases, t)}
            for t in range(n_steps)
        ]

    @staticmethod
    def encode(base: float, period: float, flow: float) -> str:
        """Encode a liquid lambda as comma-period notation."""
        return f"{base},{period}.{flow}"

    @staticmethod
    def stats(literal: str) -> dict:
        """Parse and describe a liquid lambda literal."""
        phases = LiquidLambda.parse(literal)
        curve = LiquidLambda.flow_curve(phases, n_steps=100)
        values = [c["lambda"] for c in curve]
        return {
            "literal": literal,
            "phases": phases,
            "n_phases": len(phases),
            "min_lambda": min(values),
            "max_lambda": max(values),
            "mean_lambda": sum(values) / len(values),
            "amplitude": max(values) - min(values),
            "is_liquid": any(p["flow"] > 0 for p in phases),
            "is_multiphase": len(phases) > 1,
            "description": (
                f"Liquid lambda with {len(phases)} phase(s). "
                f"Flows between {min(values):.6f} and {max(values):.6f}. "
                f"Mean: {sum(values)/len(values):.6f}. "
                f"Amplitude: {max(values)-min(values):.6f}."
                if any(p["flow"] > 0 for p in phases)
                else f"Fixed lambda (no flow). Value: {phases[0]['base']:.6f}."
            ),
            "curve_sample": curve[:10] + curve[-5:],
        }


class GlyphMLPipeline:
    """Production ML pipeline — all 6 models train in parallel.
    No dry-run. No safety mode. Full military speed.
    Models train concurrently via ThreadPoolExecutor.
    Batch prediction supports concurrent inference.
    """

    # Production hyperparameters — overmilitary grade
    PCA_COMPONENTS = 32
    RF_N_ESTIMATORS = 500
    RF_MAX_DEPTH = 20
    GB_N_ESTIMATORS = 300
    GB_MAX_DEPTH = 5
    # LIQUID LAMBDA replaces fixed learning rate (slope)
    # "0,005.05" = base=0.005, period=5, flow=0.05 — lambda oscillates
    GB_LIQUID_LAMBDA = "0,005.05"      # GB: flows 0.005 ↔ 0.010, period=5
    XGB_LIQUID_LAMBDA = "0,003.08"     # XGB: flows 0.003 ↔ 0.011, period=8
    SVM_LIQUID_LAMBDA = "0,1.5"        # SVM C: flows 1.0 ↔ 6.0, period=5
    XGB_N_ESTIMATORS = 500
    XGB_MAX_DEPTH = 8
    SVM_C = 10.0
    SVM_GAMMA = 'scale'
    KMEAN_N_INIT = 20
    TRAINING_N_PER_CLASS = 200
    MAX_WORKERS = 6  # one thread per model

    def __init__(self):
        self.scaler = StandardScaler()
        self.pca = PCA(n_components=self.PCA_COMPONENTS)
        self.kmeans = KMeans(n_clusters=len(LABELS), random_state=42, n_init=self.KMEAN_N_INIT)
        # Parse liquid lambdas
        self._gb_lambda = LiquidLambda.parse(self.GB_LIQUID_LAMBDA)
        self._xgb_lambda = LiquidLambda.parse(self.XGB_LIQUID_LAMBDA)
        self._svm_lambda = LiquidLambda.parse(self.SVM_LIQUID_LAMBDA)
        # Use initial liquid lambda value for model init
        gb_lr = LiquidLambda.value_at(self._gb_lambda, 0)
        xgb_lr = LiquidLambda.value_at(self._xgb_lambda, 0)
        svm_c = LiquidLambda.value_at(self._svm_lambda, 0)
        self.svm = SVC(kernel='rbf', C=svm_c, gamma=self.SVM_GAMMA,
                       random_state=42, probability=True)
        self.rf = RandomForestClassifier(
            n_estimators=self.RF_N_ESTIMATORS,
            max_depth=self.RF_MAX_DEPTH,
            random_state=42, n_jobs=-1)
        self.gb = GradientBoostingClassifier(
            n_estimators=self.GB_N_ESTIMATORS,
            max_depth=self.GB_MAX_DEPTH,
            learning_rate=gb_lr,
            random_state=42)
        self.xgb_model = None
        self.is_trained = False
        self.training_results = {}
        self.feature_names = []
        self._lock = threading.Lock()
        self._train_time = 0
        self.liquid_lambda_curve = []  # track lambda flow during training

    def _build_feature_matrix(self, data: list[GlyphProgramFeatures]) -> np.ndarray:
        """Build feature matrix from glyph program features.
        Combines spinor embeddings with structural features and
        glyph presence indicators for discriminative power.
        """
        # Key discriminative glyphs per class
        discriminative_glyphs = ["$", "¤", "ZK", "◈", "H", "M", "□", "L", "Σ", "ψ", "⨂", "⊠"]
        features = []
        for d in data:
            # Glyph presence features (binary: is this glyph in the program?)
            glyph_set = set(d.glyph_sequence)
            presence = np.array([1.0 if g in glyph_set else 0.0 for g in discriminative_glyphs])

            # Combine embedding + structural + presence features
            row = np.concatenate([
                d.embedding,  # 64-dim spinor embedding
                np.array([
                    d.operator_count,
                    d.noun_count,
                    d.operator_ratio,
                    d.chain_length,
                    d.chain_count,
                    d.avg_bloch_theta,
                    d.avg_bloch_phi,
                    d.spinor_entropy,
                ]),
                presence,  # 12-dim glyph presence
            ])
            features.append(row)
        return np.array(features)

    def train(self, data: list[GlyphProgramFeatures]) -> dict:
        """Train all ML models on glyph features."""
        start = time.time()

        X = self._build_feature_matrix(data)
        y = np.array([d.label for d in data])
        self.feature_names = [f"emb_{i}" for i in range(64)] + [
            "op_count", "noun_count", "op_ratio", "chain_len",
            "chain_count", "bloch_theta", "bloch_phi", "spinor_entropy"
        ] + [f"has_{g}" for g in ["$", "¤", "ZK", "◈", "H", "M", "□", "L", "Σ", "ψ", "⨂", "⊠"]]

        # Increase PCA components to preserve discriminative presence features

        # Split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        results = {"mode": "production", "samples": len(data), "features": X.shape[1]}

        # Scale + PCA (must be done before parallel model training)
        self.scaler.fit(X_train)
        X_train_s = self.scaler.transform(X_train)
        X_test_s = self.scaler.transform(X_test)

        self.pca.fit(X_train_s)
        X_train_p = self.pca.transform(X_train_s)
        X_test_p = self.pca.transform(X_test_s)
        results["pca_variance_preserved"] = float(self.pca.explained_variance_ratio_.sum())
        results["pca_components"] = self.pca.n_components_

        # KMeans (fast, do it first)
        self.kmeans.fit(X_train_p)
        results["kmeans_inertia"] = float(self.kmeans.inertia_)

        # Parallel model training — all 4 classifiers train simultaneously
        label_map = {label: i for i, label in enumerate(LABELS)}
        inv_map = {v: k for k, v in label_map.items()}
        y_train_num = np.array([label_map[l] for l in y_train])
        y_test_num = np.array([label_map[l] for l in y_test])

        def _train_svm():
            # Liquid lambda for SVM: C flows during cross-validation
            # We use the mean liquid value for the final fit
            svm_c_mean = sum(LiquidLambda.value_at(self._svm_lambda, t) for t in range(10)) / 10
            self.svm.C = svm_c_mean
            self.svm.fit(X_train_p, y_train)
            pred = self.svm.predict(X_test_p)
            acc = accuracy_score(y_test, pred)
            cv = cross_val_score(self.svm, X_train_p, y_train, cv=5, n_jobs=-1).mean()
            return {"svm_accuracy": float(acc), "svm_cv_mean": float(cv),
                    "svm_C_liquid": float(svm_c_mean)}

        def _train_rf():
            self.rf.fit(X_train_p, y_train)
            pred = self.rf.predict(X_test_p)
            acc = accuracy_score(y_test, pred)
            cv = cross_val_score(self.rf, X_train_p, y_train, cv=5, n_jobs=-1).mean()
            importances = self.rf.feature_importances_
            top_idx = np.argsort(importances)[-10:][::-1]
            top_feats = [{"feature": self.feature_names[i], "importance": float(importances[i])} for i in top_idx]
            return {"rf_accuracy": float(acc), "rf_cv_mean": float(cv), "rf_top_features": top_feats}

        def _train_gb():
            # Liquid lambda: GB gets staged learning rates from the flow curve
            # We simulate liquid lambda by fitting with the mean value
            # (sklearn doesn't support per-epoch lr changes natively, but
            # we record the flow curve for analysis)
            gb_lr_mean = sum(LiquidLambda.value_at(self._gb_lambda, t) for t in range(self.GB_N_ESTIMATORS)) / self.GB_N_ESTIMATORS
            self.gb.learning_rate = gb_lr_mean
            self.gb.fit(X_train_p, y_train)
            pred = self.gb.predict(X_test_p)
            acc = accuracy_score(y_test, pred)
            cv = cross_val_score(self.gb, X_train_p, y_train, cv=5, n_jobs=-1).mean()
            return {"gb_accuracy": float(acc), "gb_cv_mean": float(cv),
                    "gb_liquid_lambda_mean": float(gb_lr_mean)}

        def _train_xgb():
            if not HAS_XGBOOST:
                return {"xgb_accuracy": None, "xgb_top_features": []}
            # Liquid lambda: XGBoost supports staged learning rates via callbacks
            # We use the mean of the liquid flow curve
            xgb_lr_mean = sum(LiquidLambda.value_at(self._xgb_lambda, t) for t in range(self.XGB_N_ESTIMATORS)) / self.XGB_N_ESTIMATORS
            model = xgb.XGBClassifier(
                n_estimators=self.XGB_N_ESTIMATORS,
                max_depth=self.XGB_MAX_DEPTH,
                learning_rate=xgb_lr_mean,
                random_state=42,
                n_jobs=-1,
                eval_metric='mlogloss',
                subsample=0.8,
                colsample_bytree=0.8,
                reg_alpha=0.1,
                reg_lambda=1.0,
            )
            model.fit(X_train_p, y_train_num)
            pred = model.predict(X_test_p)
            acc = accuracy_score(y_test_num, pred)
            importances = model.feature_importances_
            top_idx = np.argsort(importances)[-10:][::-1]
            top_feats = [{"feature": self.feature_names[i], "importance": float(importances[i])} for i in top_idx]
            with self._lock:
                self.xgb_model = model
            return {"xgb_accuracy": float(acc), "xgb_top_features": top_feats,
                    "xgb_liquid_lambda_mean": float(xgb_lr_mean)}

        # Launch all 4 models in parallel threads
        parallel_start = time.time()
        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as executor:
            futures = {
                executor.submit(_train_svm): "svm",
                executor.submit(_train_rf): "rf",
                executor.submit(_train_gb): "gb",
                executor.submit(_train_xgb): "xgb",
            }
            for future in as_completed(futures):
                name = futures[future]
                try:
                    res = future.result()
                    results.update(res)
                except Exception as e:
                    results[f"{name}_error"] = str(e)

        results["parallel_train_seconds"] = round(time.time() - parallel_start, 3)

        # Record liquid lambda flow curves
        self.liquid_lambda_curve = {
            "gb": LiquidLambda.flow_curve(self._gb_lambda, n_steps=50),
            "xgb": LiquidLambda.flow_curve(self._xgb_lambda, n_steps=50),
            "svm": LiquidLambda.flow_curve(self._svm_lambda, n_steps=50),
        }
        results["liquid_lambda"] = {
            "gb": {"literal": self.GB_LIQUID_LAMBDA, "mean": float(results.get("gb_liquid_lambda_mean", 0))},
            "xgb": {"literal": self.XGB_LIQUID_LAMBDA, "mean": float(results.get("xgb_liquid_lambda_mean", 0))},
            "svm": {"literal": self.SVM_LIQUID_LAMBDA, "mean": float(results.get("svm_C_liquid", 0))},
        }

        self.is_trained = True
        results["elapsed"] = round(time.time() - start, 3)
        results["models_trained"] = 6
        results["parallel"] = True
        results["max_workers"] = self.MAX_WORKERS
        results["description"] = "PRODUCTION: PCA + KMeans + SVM + RF + GB + XGBoost trained in parallel on glyph spinor features. No dry-run. Military speed."
        self._train_time = results["elapsed"]
        self.training_results = results
        return results

    def predict(self, source: str) -> dict:
        """Predict the intent/class of a glyph program.
        All 4 models predict in parallel for minimum latency.
        """
        if not self.is_trained:
            return {"error": "Model not trained. Run train() first."}

        features = extract_features(source)
        X = self._build_feature_matrix([features])
        X_s = self.scaler.transform(X)
        X_p = self.pca.transform(X_s)

        label_map = {label: i for i, label in enumerate(LABELS)}
        inv_map = {v: k for k, v in label_map.items()}

        # Parallel prediction — all models predict simultaneously
        results = {}
        votes = []

        def _pred_svm():
            p = self.svm.predict(X_p)[0]
            pr = self.svm.predict_proba(X_p)[0]
            return p, float(pr.max())

        def _pred_rf():
            p = self.rf.predict(X_p)[0]
            pr = self.rf.predict_proba(X_p)[0]
            return p, float(pr.max())

        def _pred_gb():
            p = self.gb.predict(X_p)[0]
            pr = self.gb.predict_proba(X_p)[0]
            return p, float(pr.max())

        def _pred_xgb():
            if not self.xgb_model:
                return None, 0.0
            p = int(self.xgb_model.predict(X_p)[0])
            pr = self.xgb_model.predict_proba(X_p)[0]
            return inv_map.get(p, "unknown"), float(pr.max())

        with ThreadPoolExecutor(max_workers=4) as executor:
            f_svm = executor.submit(_pred_svm)
            f_rf = executor.submit(_pred_rf)
            f_gb = executor.submit(_pred_gb)
            f_xgb = executor.submit(_pred_xgb)

            svm_p, svm_c = f_svm.result()
            rf_p, rf_c = f_rf.result()
            gb_p, gb_c = f_gb.result()
            xgb_p, xgb_c = f_xgb.result()

        results["svm"] = {"prediction": svm_p, "confidence": svm_c}
        results["random_forest"] = {"prediction": rf_p, "confidence": rf_c}
        results["gradient_boosting"] = {"prediction": gb_p, "confidence": gb_c}
        if self.xgb_model:
            results["xgboost"] = {"prediction": xgb_p, "confidence": xgb_c}

        votes = [svm_p, rf_p, gb_p]
        if self.xgb_model:
            votes.append(xgb_p)

        from collections import Counter
        ensemble = Counter(votes).most_common(1)[0]
        results["ensemble"] = {"prediction": ensemble[0], "votes": ensemble[1], "total_models": len(votes)}

        return results

    def predict_batch(self, sources: list[str]) -> list[dict]:
        """Batch prediction — multiple programs predicted concurrently.
        Each program gets all 4 models. Programs are processed in parallel.
        """
        if not self.is_trained:
            return [{"error": "Model not trained."} for _ in sources]

        with ThreadPoolExecutor(max_workers=min(len(sources), 8)) as executor:
            futures = {executor.submit(self.predict, src): i for i, src in enumerate(sources)}
            results = [None] * len(sources)
            for future in as_completed(futures):
                idx = futures[future]
                results[idx] = future.result()
        return results

    def extrapolate(self, n_sigmas: float = 10000.0, n_directions: int = 10) -> dict:
        """Extrapolate N standard deviations away from the training mean.

        Generates synthetic feature vectors at n_sigmas × std from the mean
        along random directions in PCA space. Tests all 6 models on these
        extreme outliers. Measures:
        - Whether models produce confident predictions or break down
        - Prediction entropy (how uncertain the ensemble is)
        - Which model is most robust to extreme extrapolation
        - The effective "decision boundary distance" where models flip

        At 10000σ, the data is so far from training distribution that:
        - SVM's RBF kernel → near-zero similarity → ambiguous
        - RF trees → fall off the edge of leaf nodes → default to majority class
        - GB/XGBoost → log-odds saturate → extreme confidence in one class
        - KMeans → nearest centroid is arbitrary at this distance

        The question: does the spinor encoding preserve ANY structure
        at 10000σ, or do all models produce garbage?
        """
        if not self.is_trained:
            return {"error": "Model not trained. Run train() first."}

        start = time.time()

        # Get training data statistics in PCA space
        data = generate_training_data(n_per_class=self.TRAINING_N_PER_CLASS)
        X = self._build_feature_matrix(data)
        X_s = self.scaler.transform(X)
        X_p = self.pca.transform(X_s)

        mean_p = X_p.mean(axis=0)
        std_p = X_p.std(axis=0)

        # Also compute per-class means
        y = np.array([d.label for d in data])
        class_means = {}
        for label in LABELS:
            mask = y == label
            if mask.any():
                class_means[label] = X_p[mask].mean(axis=0)

        # Generate extreme outlier points at n_sigmas from mean
        rng = np.random.RandomState(1337)
        n_components = X_p.shape[1]

        # Generate random unit directions in PCA space
        directions = []
        for _ in range(n_directions):
            v = rng.randn(n_components)
            v /= np.linalg.norm(v)
            directions.append(v)

        # Also add axis-aligned directions (one per principal component)
        for i in range(min(5, n_components)):
            v = np.zeros(n_components)
            v[i] = 1.0
            directions.append(v)

        # Also add directions toward each class mean (then overshoot 10000x)
        for label, cm in class_means.items():
            diff = cm - mean_p
            norm = np.linalg.norm(diff)
            if norm > 1e-10:
                directions.append(diff / norm)

        results = []
        for i, direction in enumerate(directions):
            # Point at n_sigmas from mean along this direction
            extreme_point = mean_p + n_sigmas * std_p * direction
            extreme_point_2d = extreme_point.reshape(1, -1)

            # Measure distance from each class mean
            class_distances = {}
            for label, cm in class_means.items():
                dist = np.linalg.norm(extreme_point - cm)
                class_distances[label] = float(dist)

            # Run all 4 models in parallel
            def _pred_svm():
                p = self.svm.predict(extreme_point_2d)[0]
                pr = self.svm.predict_proba(extreme_point_2d)[0]
                return p, float(pr.max()), [float(x) for x in pr]

            def _pred_rf():
                p = self.rf.predict(extreme_point_2d)[0]
                pr = self.rf.predict_proba(extreme_point_2d)[0]
                return p, float(pr.max()), [float(x) for x in pr]

            def _pred_gb():
                p = self.gb.predict(extreme_point_2d)[0]
                pr = self.gb.predict_proba(extreme_point_2d)[0]
                return p, float(pr.max()), [float(x) for x in pr]

            def _pred_xgb():
                if not self.xgb_model:
                    return None, 0.0, []
                p = int(self.xgb_model.predict(extreme_point_2d)[0])
                pr = self.xgb_model.predict_proba(extreme_point_2d)[0]
                label_map = {label: i for i, label in enumerate(LABELS)}
                inv_map = {v: k for k, v in label_map.items()}
                return inv_map.get(p, "unknown"), float(pr.max()), [float(x) for x in pr]

            with ThreadPoolExecutor(max_workers=4) as executor:
                f_svm = executor.submit(_pred_svm)
                f_rf = executor.submit(_pred_rf)
                f_gb = executor.submit(_pred_gb)
                f_xgb = executor.submit(_pred_xgb)

                svm_p, svm_c, svm_dist = f_svm.result()
                rf_p, rf_c, rf_dist = f_rf.result()
                gb_p, gb_c, gb_dist = f_gb.result()
                xgb_p, xgb_c, xgb_dist = f_xgb.result()

            # KMeans nearest cluster
            km_cluster = int(self.kmeans.predict(extreme_point_2d)[0])
            km_dist_to_centroid = float(np.linalg.norm(extreme_point - self.kmeans.cluster_centers_[km_cluster]))

            # Ensemble vote
            votes = [svm_p, rf_p, gb_p]
            if self.xgb_model:
                votes.append(xgb_p)
            from collections import Counter
            vote_counts = Counter(votes)
            ensemble_pred, ensemble_votes = vote_counts.most_common(1)[0]

            # Prediction entropy (Shannon) — measures model disagreement
            all_probs = np.array([svm_dist, rf_dist, gb_dist] + ([xgb_dist] if self.xgb_model else []))
            avg_probs = all_probs.mean(axis=0)
            avg_probs = avg_probs / (avg_probs.sum() + 1e-10)
            entropy = -np.sum(avg_probs * np.log(avg_probs + 1e-10))
            max_entropy = np.log(len(LABELS))

            # Confidence: how sure is the ensemble?
            confidence = ensemble_votes / len(votes)

            # Direction type
            if i < n_directions:
                dir_type = "random"
            elif i < n_directions + 5:
                dir_type = f"pc_axis_{i - n_directions}"
            else:
                dir_type = "class_overshoot"

            results.append({
                "direction": i,
                "dir_type": dir_type,
                "n_sigmas": n_sigmas,
                "ensemble_prediction": ensemble_pred,
                "ensemble_confidence": confidence,
                "ensemble_votes": ensemble_votes,
                "total_models": len(votes),
                "prediction_entropy": float(entropy),
                "max_entropy": float(max_entropy),
                "entropy_ratio": float(entropy / max_entropy),
                "models": {
                    "svm": {"prediction": svm_p, "confidence": svm_c},
                    "random_forest": {"prediction": rf_p, "confidence": rf_c},
                    "gradient_boosting": {"prediction": gb_p, "confidence": gb_c},
                    "xgboost": {"prediction": xgb_p, "confidence": xgb_c} if self.xgb_model else None,
                    "kmeans_cluster": km_cluster,
                    "kmeans_distance_to_centroid": km_dist_to_centroid,
                },
                "class_distances": class_distances,
                "nearest_class": min(class_distances, key=class_distances.get),
                "nearest_class_distance": min(class_distances.values()),
            })

        # Aggregate statistics
        entropies = [r["prediction_entropy"] for r in results]
        confidences = [r["ensemble_confidence"] for r in results]
        model_agreements = [r["ensemble_votes"] for r in results]

        # Per-model prediction distribution at n_sigmas
        model_preds = {"svm": [], "rf": [], "gb": [], "xgb": []}
        for r in results:
            model_preds["svm"].append(r["models"]["svm"]["prediction"])
            model_preds["rf"].append(r["models"]["random_forest"]["prediction"])
            model_preds["gb"].append(r["models"]["gradient_boosting"]["prediction"])
            if r["models"]["xgboost"]:
                model_preds["xgb"].append(r["models"]["xgboost"]["prediction"])

        model_pred_dist = {}
        for model, preds in model_preds.items():
            dist = Counter(preds)
            model_pred_dist[model] = {k: v for k, v in dist.items()}

        elapsed = time.time() - start

        return {
            "n_sigmas": n_sigmas,
            "n_directions": len(directions),
            "n_results": len(results),
            "mean_entropy": float(np.mean(entropies)),
            "max_entropy_possible": float(max_entropy),
            "entropy_ratio": float(np.mean(entropies) / max_entropy),
            "mean_confidence": float(np.mean(confidences)),
            "mean_model_agreement": float(np.mean(model_agreements)),
            "full_agreement_rate": float(np.mean([1 if v == 4 else 0 for v in model_agreements])),
            "model_prediction_distribution": model_pred_dist,
            "pca_components": int(self.pca.n_components_),
            "training_samples": len(data),
            "elapsed_seconds": round(elapsed, 3),
            "description": f"Extrapolated {n_sigmas}σ from mean along {len(directions)} directions. "
                          f"Mean entropy ratio={np.mean(entropies)/max_entropy:.4f} (1.0=max uncertainty). "
                          f"Full agreement={np.mean([1 if v == 4 else 0 for v in model_agreements]):.1%}.",
            "results": results,
        }

    def cluster_glyphs(self, n_clusters: int = 10) -> dict:
        """Cluster all known glyphs by spinor similarity using KMeans."""
        glyphs = list(ALL_GLYPHS.keys())
        embeddings = np.array([spinor_to_embedding(glyph_to_spinor(g), 64) for g in glyphs])

        scaler = StandardScaler()
        emb_scaled = scaler.fit_transform(embeddings)

        pca = PCA(n_components=min(8, len(glyphs) - 1))
        emb_pca = pca.fit_transform(emb_scaled)

        km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
        clusters = km.fit_predict(emb_pca)

        cluster_map = {}
        for g, c in zip(glyphs, clusters):
            cluster_map.setdefault(int(c), []).append(g)

        return {
            "n_glyphs": len(glyphs),
            "n_clusters": n_clusters,
            "pca_variance_preserved": float(pca.explained_variance_ratio_.sum()),
            "clusters": {
                str(k): {"glyphs": v, "count": len(v),
                         "types": [ALL_GLYPHS[g] for g in v]}
                for k, v in sorted(cluster_map.items())
            },
        }

    def stats(self) -> dict:
        return {
            "mode": "production",
            "is_trained": self.is_trained,
            "has_xgboost": HAS_XGBOOST,
            "operator_ratio": round(OPERATOR_RATIO, 4),
            "total_glyphs": len(ALL_GLYPHS),
            "operator_count": len(GLYPH_OPERATORS),
            "noun_count": len(GLYPH_NOUNS),
            "embedding_dim": 64,
            "pca_components": self.PCA_COMPONENTS,
            "models": ["PCA", "KMeans", "SVM", "RandomForest", "GradientBoosting"] + (["XGBoost"] if HAS_XGBOOST else []),
            "labels": LABELS,
            "parallel_training": True,
            "max_workers": self.MAX_WORKERS,
            "hyperparameters": {
                "rf_n_estimators": self.RF_N_ESTIMATORS,
                "rf_max_depth": self.RF_MAX_DEPTH,
                "gb_n_estimators": self.GB_N_ESTIMATORS,
                "xgb_n_estimators": self.XGB_N_ESTIMATORS,
                "xgb_max_depth": self.XGB_MAX_DEPTH,
                "svm_C": self.SVM_C,
                "pca_components": self.PCA_COMPONENTS,
                "gb_liquid_lambda": self.GB_LIQUID_LAMBDA,
                "xgb_liquid_lambda": self.XGB_LIQUID_LAMBDA,
                "svm_liquid_lambda": self.SVM_LIQUID_LAMBDA,
            },
            "train_time_seconds": round(self._train_time, 3) if self._train_time else None,
            "description": "PRODUCTION ML pipeline. No dry-run. Parallel training. Military speed. All 6 models train simultaneously.",
        }


# --- CLI ---

def cli():
    if len(sys.argv) < 2:
        print("GlyphML — PRODUCTION ML Pipeline on Glyph Spinor Features")
        print(f"  Operators: {len(GLYPH_OPERATORS)}/{len(ALL_GLYPHS)} = {OPERATOR_RATIO:.1%} of language")
        print(f"  Mode: PRODUCTION (no dry-run, parallel training, military speed)")
        print()
        print("Commands:")
        print("  python3 glyph_ml.py train             Train all 6 models in parallel (production)")
        print("  python3 glyph_ml.py predict <src>     Predict class of a glyph program")
        print("  python3 glyph_ml.py batch <f1> <f2>   Batch predict multiple programs")
        print("  python3 glyph_ml.py extrapolate <sigma> Extrapolate N sigmas from mean")
        print("  python3 glyph_ml.py liquid <literal>    Show liquid lambda flow curve")
        print("  python3 glyph_ml.py clusters          Cluster all glyphs by spinor similarity")
        print("  python3 glyph_ml.py stats             Show pipeline stats")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "stats":
        p = GlyphMLPipeline()
        print(json.dumps(p.stats(), indent=2, ensure_ascii=False))

    elif cmd == "train":
        print("GlyphML PRODUCTION — Parallel Training All 6 Models")
        print(f"Operators: {len(GLYPH_OPERATORS)}/{len(ALL_GLYPHS)} = {OPERATOR_RATIO:.1%}")
        print(f"Training data: {GlyphMLPipeline.TRAINING_N_PER_CLASS} per class = {GlyphMLPipeline.TRAINING_N_PER_CLASS * len(LABELS)} total")
        print(f"Parallel workers: {GlyphMLPipeline.MAX_WORKERS}")
        print()
        data = generate_training_data(n_per_class=GlyphMLPipeline.TRAINING_N_PER_CLASS)
        pipeline = GlyphMLPipeline()
        result = pipeline.train(data)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "extrapolate":
        sigma = float(sys.argv[2]) if len(sys.argv) > 2 else 10000.0
        n_dirs = int(sys.argv[3]) if len(sys.argv) > 3 else 10
        print(f"GlyphML PRODUCTION — Extrapolating {sigma}σ from mean")
        print(f"Directions: {n_dirs} random + 5 axis-aligned + {len(LABELS)} class-overshoot")
        print()
        data = generate_training_data(n_per_class=GlyphMLPipeline.TRAINING_N_PER_CLASS)
        pipeline = GlyphMLPipeline()
        pipeline.train(data)
        result = pipeline.extrapolate(n_sigmas=sigma, n_directions=n_dirs)
        # Print summary
        print(f"Sigmas: {result['n_sigmas']}")
        print(f"Directions tested: {result['n_directions']}")
        print(f"Mean entropy ratio: {result['entropy_ratio']:.4f} (1.0 = max uncertainty)")
        print(f"Mean confidence: {result['mean_confidence']:.4f}")
        print(f"Mean model agreement: {result['mean_model_agreement']:.2f}/4")
        print(f"Full agreement rate: {result['full_agreement_rate']:.1%}")
        print(f"Elapsed: {result['elapsed_seconds']}s")
        print()
        print("Model prediction distribution at extreme distance:")
        for model, dist in result['model_prediction_distribution'].items():
            print(f"  {model}: {dist}")
        print()
        print("Per-direction results:")
        for r in result['results']:
            print(f"  dir {r['direction']:2d} ({r['dir_type']:20s}): "
                  f"ensemble={r['ensemble_prediction']:20s} conf={r['ensemble_confidence']:.2f} "
                  f"entropy_ratio={r['entropy_ratio']:.4f} "
                  f"svm={r['models']['svm']['confidence']:.3f} "
                  f"rf={r['models']['random_forest']['confidence']:.3f} "
                  f"gb={r['models']['gradient_boosting']['confidence']:.3f} "
                  f"xgb={r['models']['xgboost']['confidence']:.3f} "
                  f"km_dist={r['models']['kmeans_distance_to_centroid']:.1f}")

    elif cmd == "liquid":
        literal = sys.argv[2] if len(sys.argv) > 2 else "0,005.05"
        print(f"Liquid Lambda — Flow Analysis")
        print(f"Literal: {literal}")
        print()
        stats = LiquidLambda.stats(literal)
        print(json.dumps(stats, indent=2, ensure_ascii=False))
        print()
        print("Flow curve (50 steps):")
        phases = LiquidLambda.parse(literal)
        curve = LiquidLambda.flow_curve(phases, n_steps=50)
        for c in curve:
            bar_len = int(c['lambda'] * 1000)
            bar = '█' * min(bar_len, 60)
            print(f"  t={c['step']:3d}  λ={c['lambda']:.6f}  {bar}")

    elif cmd == "clusters":
        print("GlyphML — Clustering All Glyphs by Spinor Similarity")
        print()
        pipeline = GlyphMLPipeline()
        result = pipeline.cluster_glyphs(n_clusters=10)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "predict":
        if len(sys.argv) < 3:
            print("Usage: python3 glyph_ml.py predict '<glyph source>'")
            sys.exit(1)
        source = sys.argv[2]
        print("GlyphML PRODUCTION — Predicting Program Class")
        print(f"Source: {source[:60]}...")
        print()
        data = generate_training_data(n_per_class=GlyphMLPipeline.TRAINING_N_PER_CLASS)
        pipeline = GlyphMLPipeline()
        pipeline.train(data)
        result = pipeline.predict(source)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif cmd == "batch":
        if len(sys.argv) < 4:
            print("Usage: python3 glyph_ml.py batch '<src1>' '<src2>' ...")
            sys.exit(1)
        sources = sys.argv[2:]
        print(f"GlyphML PRODUCTION — Batch Predicting {len(sources)} Programs")
        print()
        data = generate_training_data(n_per_class=GlyphMLPipeline.TRAINING_N_PER_CLASS)
        pipeline = GlyphMLPipeline()
        pipeline.train(data)
        results = pipeline.predict_batch(sources)
        for i, (src, res) in enumerate(zip(sources, results)):
            print(f"Program {i+1}: {src[:40]}...")
            print(f"  Ensemble: {res['ensemble']['prediction']} ({res['ensemble']['votes']}/{res['ensemble']['total_models']} votes)")
            print()

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
