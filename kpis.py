#!/usr/bin/env python3
"""
ClientPulse OS — KPI Engine
Turns first-party metrics into immortality, virality, conversion, trust, and decision state.
"""

import json
import math
import hashlib
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, asdict

ROOT = Path(__file__).resolve().parent
CONTENT_DIR = ROOT / "content"
RECEIPTS_DIR = ROOT / "receipts"
DECISIONS_DIR = CONTENT_DIR / "decisions"
METRICS_DIR = CONTENT_DIR / "metrics"


@dataclass
class MetricSnapshot:
    timestamp: str
    views: int
    contact_clicks: int
    profile_visible: bool
    availability_truthful: bool
    days_online: int
    views_per_day: float
    bookmarks: int
    returning_visitors: int
    new_visitors: int
    photos_changed: bool = False
    price_changed: bool = False
    services_changed: bool = False
    availability_changed: bool = False
    external_link_changed: bool = False


def load_snapshots() -> List[MetricSnapshot]:
    """Load all metric snapshots from JSONL file."""
    ingest_file = CONTENT_DIR / "metrics_ingest.jsonl"
    if not ingest_file.exists():
        return []
    snapshots = []
    with open(ingest_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            snapshots.append(MetricSnapshot(**data))
    return snapshots


def immortality_score(s: MetricSnapshot) -> Tuple[float, str, Dict]:
    """
    Immortality = durability of profile life.
    5D vector: visibility, availability, retention, view_consistency, return_rate.
    Score = L2 norm / sqrt(5).
    """
    d1 = 1.0 if s.profile_visible else 0.0
    d2 = 1.0 if s.availability_truthful else 0.0
    d3 = 1.0 / (1.0 + math.exp(-(s.days_online - 365) / 180))
    baseline = 50.0
    if s.views_per_day <= 0:
        d4 = 0.0
    else:
        ratio = s.views_per_day / baseline
        d4 = max(0.0, min(1.0, math.log(1 + ratio) / math.log(1 + 3)))
    total_visitors = s.new_visitors + s.returning_visitors
    if total_visitors <= 0:
        d5 = 0.0
    else:
        d5 = max(0.0, min(1.0, s.returning_visitors / total_visitors))

    vec = (d1, d2, d3, d4, d5)
    magnitude = math.sqrt(sum(d ** 2 for d in vec))
    score = magnitude / math.sqrt(5)

    if score >= 0.85:
        label = "IMMORTAL"
    elif score >= 0.65:
        label = "DURABLE"
    elif score >= 0.40:
        label = "STABLE"
    elif score >= 0.20:
        label = "FRAGILE"
    else:
        label = "CRITICAL"

    return score, label, {
        "vector": [round(d, 4) for d in vec],
        "dimensions": ["visibility", "availability", "retention", "view_consistency", "return_rate"],
    }


def virality_score(snapshots: List[MetricSnapshot]) -> Tuple[float, str, Dict]:
    """
    Virality = acceleration of attention.
    4D velocity vector projected onto growth direction.
    Requires 2+ snapshots.
    """
    if len(snapshots) < 2:
        return 0.11, "INSUFFICIENT_DATA", {
            "reason": "Need 2+ snapshots for velocity",
            "snapshots": len(snapshots),
        }

    snaps = sorted(snapshots, key=lambda s: s.timestamp)

    view_deltas = []
    click_deltas = []
    return_deltas = []
    growth_intervals = 0
    total_intervals = 0

    for i in range(1, len(snaps)):
        prev, curr = snaps[i - 1], snaps[i]
        if prev.views > 0:
            view_deltas.append((curr.views - prev.views) / max(prev.views, 1))
        else:
            view_deltas.append(0.0)
        if prev.contact_clicks > 0:
            click_deltas.append((curr.contact_clicks - prev.contact_clicks) / max(prev.contact_clicks, 1))
        else:
            click_deltas.append(0.0)
        prev_ret = prev.returning_visitors / max(prev.new_visitors + prev.returning_visitors, 1)
        curr_ret = curr.returning_visitors / max(curr.new_visitors + curr.returning_visitors, 1)
        return_deltas.append(curr_ret - prev_ret)
        if (curr.views + curr.contact_clicks) > (prev.views + prev.contact_clicks):
            growth_intervals += 1
        total_intervals += 1

    v1 = max(-1.0, min(1.0, sum(view_deltas) / len(view_deltas)))
    v2 = max(-1.0, min(1.0, sum(click_deltas) / len(click_deltas)))
    v3 = max(-1.0, min(1.0, sum(return_deltas) / len(return_deltas)))
    v4 = growth_intervals / total_intervals if total_intervals > 0 else 0.0

    growth = (1.0, 1.0, 1.0, 1.0)
    growth_mag = math.sqrt(4)
    dot = sum(vi * gi for vi, gi in zip((v1, v2, v3, v4), growth))
    score = max(0.0, min(1.0, (dot / growth_mag + 1.0) / 2.0))

    if score >= 0.75:
        label = "ACCELERATING"
    elif score >= 0.55:
        label = "GROWING"
    elif score >= 0.45:
        label = "STAGNANT"
    elif score >= 0.25:
        label = "DECLINING"
    else:
        label = "COLLAPSING"

    return score, label, {
        "vector": [round(v1, 4), round(v2, 4), round(v3, 4), round(v4, 4)],
        "dimensions": ["view_velocity", "click_velocity", "return_trend", "momentum_persistence"],
    }


def conversion_score(snapshots: List[MetricSnapshot]) -> Tuple[float, str, Dict]:
    """
    Conversion = Bayesian P(contact | view).
    Beta(2, 38) prior — conservative 5% assumption.
    """
    total_views = sum(s.views for s in snapshots)
    total_clicks = sum(s.contact_clicks for s in snapshots)
    alpha, beta_prior = 2, 38
    score = (alpha + total_clicks) / (alpha + beta_prior + total_views)

    if score >= 0.08:
        label = "HEALTHY"
    elif score >= 0.05:
        label = "OK"
    elif score >= 0.02:
        label = "LOW"
    else:
        label = "CRITICAL"

    return score, label, {
        "total_views": total_views,
        "total_clicks": total_clicks,
        "raw_rate": round(total_clicks / max(total_views, 1), 4),
        "prior": "Beta(2, 38)",
    }


def trust_score(s: MetricSnapshot) -> Tuple[float, str, Dict]:
    """
    Trust = safety of current state.
    Checks for dirty-test contamination.
    """
    dirty_flags = []
    if s.photos_changed:
        dirty_flags.append("photos_changed")
    if s.price_changed:
        dirty_flags.append("price_changed")
    if s.services_changed:
        dirty_flags.append("services_changed")
    if s.availability_changed:
        dirty_flags.append("availability_changed")
    if s.external_link_changed:
        dirty_flags.append("external_link_changed")

    if not s.profile_visible:
        dirty_flags.append("profile_not_visible")

    if not s.availability_truthful:
        dirty_flags.append("availability_not_truthful")

    clean_count = 7 - len(dirty_flags)
    score = clean_count / 7

    if score >= 0.9:
        label = "GREEN"
    elif score >= 0.6:
        label = "YELLOW"
    else:
        label = "RED"

    return score, label, {
        "dirty_flags": dirty_flags,
        "is_clean": len(dirty_flags) == 0,
    }


def decision_gate(snapshots: List[MetricSnapshot], imm: float, imm_label: str,
                   vir: float, vir_label: str, conv: float, conv_label: str,
                   trust: float, trust_label: str) -> Tuple[str, str]:
    """
    Decision logic — the action the operator should take.
    """
    if not snapshots:
        return "NO_DATA", "Capture first metric snapshot"

    latest = snapshots[-1]

    if trust_label == "RED":
        return "EMERGENCY_RESTORE", "Profile contaminated or offline — fix immediately"

    if not latest.profile_visible:
        return "EMERGENCY_RESTORE", "Profile not visible — restore immediately"

    if len(snapshots) < 2:
        return "INSUFFICIENT_DATA", "Need 2+ hourly snapshots for velocity"

    # Check for rollback condition
    if len(snapshots) >= 2:
        prev = snapshots[-2]
        if prev.contact_clicks > 0:
            drop = (prev.contact_clicks - latest.contact_clicks) / prev.contact_clicks
            if drop > 0.25:
                return "ROLLBACK", f"Contact clicks dropped {drop:.0%} — rollback bio change"

    # Attention without intent
    if len(snapshots) >= 2:
        prev = snapshots[-2]
        views_rising = latest.views > prev.views
        ctr_prev = prev.contact_clicks / max(prev.views, 1)
        ctr_curr = latest.contact_clicks / max(latest.views, 1)
        if views_rising and ctr_curr < ctr_prev:
            return "ATTENTION_WITHOUT_INTENT", "Views rising but CTR falling — bio attracts wrong audience"

    # Winner found
    if len(snapshots) >= 2:
        prev = snapshots[-2]
        ctr_prev = prev.contact_clicks / max(prev.views, 1)
        ctr_curr = latest.contact_clicks / max(latest.views, 1)
        if ctr_curr > ctr_prev and latest.views >= prev.views:
            return "WINNER_FOUND", "CTR rising with views holding — keep this variant"

    # High durability, low acceleration
    if imm >= 0.65 and vir < 0.45:
        return "NEEDS_HOOK_TEST", "Profile durable but stagnant — test new bio hook"

    if conv < 0.02:
        return "CRITICAL_CONVERSION", "Contact rate critically low — overhaul bio"

    return "HOLD", "Metrics stable — continue collecting snapshots"


def write_receipt(kpi_data: Dict) -> str:
    """Write tamper-evident receipt to JSONL ledger."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    receipt_file = RECEIPTS_DIR / "hourly_kpi_receipts.jsonl"

    receipt = {
        "id": hashlib.sha256(json.dumps(kpi_data, sort_keys=True).encode()).hexdigest()[:16],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": kpi_data,
    }

    with open(receipt_file, "a") as f:
        f.write(json.dumps(receipt) + "\n")

    return receipt["id"]


def write_decision(decision: str, reason: str, kpi_data: Dict) -> None:
    """Write latest decision to file."""
    DECISIONS_DIR.mkdir(parents=True, exist_ok=True)
    decision_file = DECISIONS_DIR / "latest_decision.json"
    with open(decision_file, "w") as f:
        json.dump({
            "decision": decision,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "kpi_snapshot": kpi_data,
        }, f, indent=2)


def calculate_all() -> Dict:
    """Full KPI calculation pipeline."""
    snapshots = load_snapshots()

    if not snapshots:
        return {
            "error": "No snapshots found",
            "snapshots": 0,
        }

    latest = snapshots[-1]

    imm_score, imm_label, imm_data = immortality_score(latest)
    vir_score, vir_label, vir_data = virality_score(snapshots)
    conv_score, conv_label, conv_data = conversion_score(snapshots)
    trust_val, trust_label, trust_data = trust_score(latest)
    decision, reason = decision_gate(
        snapshots, imm_score, imm_label, vir_score, vir_label,
        conv_score, conv_label, trust_val, trust_label
    )

    kpi_data = {
        "immortality": {"score": round(imm_score, 4), "label": imm_label, **imm_data},
        "virality": {"score": round(vir_score, 4), "label": vir_label, **vir_data},
        "conversion": {"score": round(conv_score, 4), "label": conv_label, **conv_data},
        "trust": {"score": round(trust_val, 4), "label": trust_label, **trust_data},
        "decision": {"state": decision, "reason": reason},
        "snapshots": len(snapshots),
        "latest_timestamp": latest.timestamp,
        "latest_metrics": {
            "views": latest.views,
            "contact_clicks": latest.contact_clicks,
            "views_per_day": latest.views_per_day,
            "days_online": latest.days_online,
            "new_visitors": latest.new_visitors,
            "returning_visitors": latest.returning_visitors,
            "bookmarks": latest.bookmarks,
        },
    }

    receipt_id = write_receipt(kpi_data)
    write_decision(decision, reason, kpi_data)
    kpi_data["receipt_id"] = receipt_id

    return kpi_data


if __name__ == "__main__":
    result = calculate_all()
    print(json.dumps(result, indent=2))
