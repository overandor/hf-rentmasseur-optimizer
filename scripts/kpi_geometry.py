#!/usr/bin/env python3
"""
Complex Geometrical KPI Formulas

Models profile health as a point in N-dimensional space.
Uses vector geometry, not arbitrary weights.

Immortality = magnitude of the durability vector in survival space.
Virality = directional derivative of the attention vector over time.
Conversion = ratio of contact events to view events (probability density).
Proof = Hausdorff distance between claimed state and evidenced state.
"""

import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple, Dict
from dataclasses import dataclass

DB_PATH = Path("data/profile_intelligence.db")


@dataclass
class ProfileSnapshot:
    """Single point in time snapshot of profile state."""
    timestamp: str
    views: int
    contact_clicks: int
    visibility: float       # 0..1 (profile is publicly accessible)
    availability: float     # 0..1 (marked available on platform)
    retention: float        # 0..1 (account age normalized)
    account_age_days: int
    avg_views_per_day: float


# ---------------------------------------------------------------------------
# IMMORTALITY: Magnitude of durability vector in survival space
# ---------------------------------------------------------------------------

def immortality_vector(s: ProfileSnapshot) -> Tuple[float, float, float, float, float]:
    """
    Project profile into 5-dimensional survival space.

    Dimensions (each normalized 0..1):
      d1 = visibility       — is the profile publicly reachable?
      d2 = availability     — is the profile marked active?
      d3 = retention        — account age relative to platform median
      d4 = view_consistency — daily view rate relative to historical baseline
      d5 = contact_density  — contact clicks per day relative to views

    Returns the vector (d1, d2, d3, d4, d5).
    """
    d1 = max(0.0, min(1.0, s.visibility))

    d2 = max(0.0, min(1.0, s.availability))

    # Retention: sigmoid curve centered at 365 days
    # Accounts < 30 days are fragile. Accounts > 2 years are durable.
    d3 = 1.0 / (1.0 + math.exp(-(s.account_age_days - 365) / 180))

    # View consistency: how close current daily views are to a healthy baseline
    # Baseline assumption: 50 views/day is healthy for an established profile
    baseline = 50.0
    if s.avg_views_per_day <= 0:
        d4 = 0.0
    else:
        # Log-normal style: diminishing returns above baseline
        ratio = s.avg_views_per_day / baseline
        d4 = max(0.0, min(1.0, math.log(1 + ratio) / math.log(1 + 3)))

    # Contact density: fraction of views that become contacts
    if s.views <= 0:
        d5 = 0.0
    else:
        raw = s.contact_clicks / s.views
        # Sigmoid: 5% contact rate is good, 10% is excellent
        d5 = 1.0 / (1.0 + math.exp(-(raw - 0.05) / 0.02))

    return (d1, d2, d3, d4, d5)


def immortality_score(s: ProfileSnapshot) -> float:
    """
    Immortality = L2 norm (Euclidean magnitude) of the durability vector,
    normalized to 0..1 by dividing by sqrt(5).

    A profile with all dimensions at 1.0 has immortality = 1.0.
    A profile with all dimensions at 0.0 has immortality = 0.0.

    The geometric interpretation: the profile is a point in survival space.
    The further from the origin, the more durable.
    """
    v = immortality_vector(s)
    magnitude = math.sqrt(sum(d ** 2 for d in v))
    max_magnitude = math.sqrt(5)  # all dimensions = 1
    return magnitude / max_magnitude


def immortality_label(score: float) -> str:
    """Classify immortality score."""
    if score >= 0.85:
        return "IMMORTAL"
    elif score >= 0.65:
        return "DURABLE"
    elif score >= 0.40:
        return "STABLE"
    elif score >= 0.20:
        return "FRAGILE"
    else:
        return "CRITICAL"


# ---------------------------------------------------------------------------
# VIRALITY: Directional derivative of attention vector over time
# ---------------------------------------------------------------------------

def virality_vector(snapshots: List[ProfileSnapshot]) -> Tuple[float, float, float, float]:
    """
    Compute the velocity of attention across 4 dimensions.

    Requires at least 2 snapshots. More snapshots = better estimate.

    Dimensions (each represents rate of change):
      v1 = view_velocity      — change in daily views over time
      v2 = click_velocity     — change in daily contact clicks over time
      v3 = conversion_trend   — change in contact rate over time
      v4 = momentum_persistence — fraction of intervals showing growth

    Returns the velocity vector (v1, v2, v3, v4), each in -1..1.
    """
    if len(snapshots) < 2:
        return (0.0, 0.0, 0.0, 0.0)

    # Sort by timestamp (oldest first)
    snaps = sorted(snapshots, key=lambda s: s.timestamp)

    # Compute per-interval deltas
    view_deltas = []
    click_deltas = []
    conversion_deltas = []
    growth_intervals = 0
    total_intervals = 0

    for i in range(1, len(snaps)):
        prev = snaps[i - 1]
        curr = snaps[i]

        # View velocity: normalized change
        if prev.views > 0:
            vd = (curr.views - prev.views) / max(prev.views, 1)
            view_deltas.append(vd)
        else:
            view_deltas.append(0.0)

        # Click velocity
        if prev.contact_clicks > 0:
            cd = (curr.contact_clicks - prev.contact_clicks) / max(prev.contact_clicks, 1)
            click_deltas.append(cd)
        else:
            click_deltas.append(0.0)

        # Conversion trend
        prev_rate = prev.contact_clicks / prev.views if prev.views > 0 else 0
        curr_rate = curr.contact_clicks / curr.views if curr.views > 0 else 0
        conversion_deltas.append(curr_rate - prev_rate)

        # Growth check: did total attention increase?
        if (curr.views + curr.contact_clicks) > (prev.views + prev.contact_clicks):
            growth_intervals += 1
        total_intervals += 1

    # Average velocities, clamped to -1..1
    v1 = max(-1.0, min(1.0, sum(view_deltas) / len(view_deltas)))
    v2 = max(-1.0, min(1.0, sum(click_deltas) / len(click_deltas)))
    v3 = max(-1.0, min(1.0, sum(conversion_deltas) / len(conversion_deltas)))
    v4 = growth_intervals / total_intervals if total_intervals > 0 else 0.0

    return (v1, v2, v3, v4)


def virality_score(snapshots: List[ProfileSnapshot]) -> float:
    """
    Virality = projected magnitude of the velocity vector onto the growth direction.

    Geometric interpretation:
    - The velocity vector points in the direction of change.
    - The growth direction is (1, 1, 1, 1) / sqrt(4) — uniform growth.
    - We project the velocity vector onto this direction.
    - Positive projection = growing. Negative = declining.

    Normalized to 0..1 where 0.5 = stagnant, 1.0 = rapid growth, 0.0 = rapid decline.
    """
    if len(snapshots) < 2:
        return 0.1  # Single snapshot cannot prove motion

    v = virality_vector(snapshots)

    # Growth direction unit vector
    growth = (1.0, 1.0, 1.0, 1.0)
    growth_mag = math.sqrt(sum(g ** 2 for g in growth))
    growth_unit = tuple(g / growth_mag for g in growth)

    # Dot product = projection onto growth direction
    dot = sum(vi * gi for vi, gi in zip(v, growth_unit))

    # Normalize: dot product ranges from -sqrt(4) to +sqrt(4)
    # Map to 0..1: 0.5 = stagnant, 1.0 = max growth, 0.0 = max decline
    normalized = (dot / growth_mag + 1.0) / 2.0

    return max(0.0, min(1.0, normalized))


def virality_label(score: float) -> str:
    """Classify virality score."""
    if score >= 0.75:
        return "ACCELERATING"
    elif score >= 0.55:
        return "GROWING"
    elif score >= 0.45:
        return "STAGNANT"
    elif score >= 0.25:
        return "DECLINING"
    else:
        return "COLLAPSING"


# ---------------------------------------------------------------------------
# CONVERSION: Probability density of contact given view
# ---------------------------------------------------------------------------

def conversion_score(snapshots: List[ProfileSnapshot]) -> float:
    """
    Conversion = Bayesian estimate of P(contact | view).

    Uses Beta distribution prior with alpha=2, beta=38 (prior mean = 5%).
    This is a conservative prior: we assume 5% contact rate until data says otherwise.

    Posterior mean = (alpha + total_clicks) / (alpha + beta + total_views)

    This is more honest than raw rate because it handles small sample sizes.
    """
    total_views = sum(s.views for s in snapshots)
    total_clicks = sum(s.contact_clicks for s in snapshots)

    alpha_prior = 2    # pseudo-count of contacts
    beta_prior = 38    # pseudo-count of non-contacts

    posterior_mean = (alpha_prior + total_clicks) / (alpha_prior + beta_prior + total_views)
    return posterior_mean


# ---------------------------------------------------------------------------
# PROOF: Hausdorff distance between claimed and evidenced state
# ---------------------------------------------------------------------------

def proof_score(claimed: ProfileSnapshot, evidenced: ProfileSnapshot) -> float:
    """
    Proof = 1 - normalized Hausdorff distance between claimed and evidenced state.

    Each profile makes implicit claims (e.g., "75,000 views", "available 24/7").
    Evidence is what the measurement system actually observes.

    Hausdorff distance measures the maximum discrepancy between claim and evidence.
    Small distance = high proof. Large distance = low proof.

    We compute it as the Chebyshev (L-inf) distance across normalized dimensions,
    then invert: proof = 1 - distance.
    """
    dims_claimed = [
        claimed.visibility,
        claimed.availability,
        min(1.0, claimed.avg_views_per_day / 100),
        min(1.0, claimed.views / 10000),
        min(1.0, claimed.contact_clicks / 500),
    ]
    dims_evidenced = [
        evidenced.visibility,
        evidenced.availability,
        min(1.0, evidenced.avg_views_per_day / 100),
        min(1.0, evidenced.views / 10000),
        min(1.0, evidenced.contact_clicks / 500),
    ]

    # Chebyshev distance: max dimension-wise difference
    distance = max(abs(c - e) for c, e in zip(dims_claimed, dims_evidenced))

    return max(0.0, min(1.0, 1.0 - distance))


# ---------------------------------------------------------------------------
# Composite: Full KPI calculation
# ---------------------------------------------------------------------------

def calculate_kpis(snapshots: List[ProfileSnapshot],
                   claimed: ProfileSnapshot = None) -> Dict:
    """
    Calculate all four KPIs from snapshot history.

    Returns dict with scores, vectors, labels, and raw components.
    """
    if not snapshots:
        return {"error": "No snapshots provided"}

    latest = snapshots[-1]

    # Immortality from latest snapshot
    imm_vec = immortality_vector(latest)
    imm = immortality_score(latest)

    # Virality from full history
    vir_vec = virality_vector(snapshots)
    vir = virality_score(snapshots)

    # Conversion from all snapshots
    conv = conversion_score(snapshots)

    # Proof: compare claimed vs evidenced
    if claimed:
        prf = proof_score(claimed, latest)
    else:
        prf = 1.0  # No claims to verify against

    return {
        "immortality": {
            "score": round(imm, 4),
            "label": immortality_label(imm),
            "vector": [round(d, 4) for d in imm_vec],
            "dimensions": ["visibility", "availability", "retention", "view_consistency", "contact_density"],
        },
        "virality": {
            "score": round(vir, 4),
            "label": virality_label(vir),
            "vector": [round(d, 4) for d in vir_vec],
            "dimensions": ["view_velocity", "click_velocity", "conversion_trend", "momentum_persistence"],
        },
        "conversion": {
            "score": round(conv, 4),
            "label": "HEALTHY" if conv >= 0.05 else "LOW" if conv >= 0.02 else "CRITICAL",
            "bayesian_prior": "Beta(2, 38) — conservative 5% prior",
        },
        "proof": {
            "score": round(prf, 4),
            "label": "VERIFIED" if prf >= 0.8 else "PARTIAL" if prf >= 0.5 else "UNVERIFIED",
        },
        "snapshots_used": len(snapshots),
        "timestamp": latest.timestamp,
    }


# ---------------------------------------------------------------------------
# Demo with real data from DB
# ---------------------------------------------------------------------------

def demo():
    """Run KPI calculation on real data from profile_intelligence.db."""
    print("=" * 60)
    print("GEOMETRICAL KPI CALCULATION")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT timestamp, views, contact_clicks, visibility_score,
               availability_score, retention_score
        FROM profile_metrics
        ORDER BY timestamp ASC
    """)

    rows = cursor.fetchall()
    conn.close()

    if not rows:
        print("No snapshots in DB. Running synthetic demo...")

        # Synthetic data: 5 snapshots showing growth
        snapshots = []
        for i in range(5):
            views = 70 + i * 15
            clicks = int(views * (0.03 + i * 0.005))
            snapshots.append(ProfileSnapshot(
                timestamp=f"2026-01-0{i+1}T00:00:00Z",
                views=views,
                contact_clicks=clicks,
                visibility=0.9,
                availability=0.85,
                retention=0.95,
                account_age_days=964,
                avg_views_per_day=81,
            ))
    else:
        snapshots = []
        for row in rows:
            snapshots.append(ProfileSnapshot(
                timestamp=row[0],
                views=row[1] or 0,
                contact_clicks=row[2] or 0,
                visibility=row[3] or 0,
                availability=row[4] or 0,
                retention=row[5] or 0,
                account_age_days=964,
                avg_views_per_day=81,
            ))

    kpis = calculate_kpis(snapshots)

    print(f"\nSnapshots analyzed: {kpis['snapshots_used']}")
    print(f"Timestamp: {kpis['timestamp']}")

    print(f"\n--- IMMORTALITY ---")
    imm = kpis["immortality"]
    print(f"  Score: {imm['score']:.4f}")
    print(f"  Label: {imm['label']}")
    print(f"  Vector: {imm['vector']}")
    print(f"  Dimensions: {imm['dimensions']}")
    print(f"  Formula: ||v|| / sqrt(5) where v = (d1, d2, d3, d4, d5)")

    print(f"\n--- VIRALITY ---")
    vir = kpis["virality"]
    print(f"  Score: {vir['score']:.4f}")
    print(f"  Label: {vir['label']}")
    print(f"  Vector: {vir['vector']}")
    print(f"  Dimensions: {vir['dimensions']}")
    print(f"  Formula: (v . g_hat + 1) / 2 where g_hat = (1,1,1,1)/sqrt(4)")

    print(f"\n--- CONVERSION ---")
    conv = kpis["conversion"]
    print(f"  Score: {conv['score']:.4f}")
    print(f"  Label: {conv['label']}")
    print(f"  Formula: (alpha + clicks) / (alpha + beta + views)")
    print(f"  Prior: {conv['bayesian_prior']}")

    print(f"\n--- PROOF ---")
    prf = kpis["proof"]
    print(f"  Score: {prf['score']:.4f}")
    print(f"  Label: {prf['label']}")
    print(f"  Formula: 1 - Chebyshev(claimed, evidenced)")

    print("\n" + "=" * 60)
    print("GEOMETRIC INTERPRETATION:")
    print(f"  Immortality = distance from origin in survival space")
    print(f"  Virality = projection of velocity onto growth direction")
    print(f"  Conversion = Bayesian posterior of P(contact|view)")
    print(f"  Proof = 1 - max discrepancy between claim and evidence")
    print("=" * 60)


if __name__ == "__main__":
    demo()
