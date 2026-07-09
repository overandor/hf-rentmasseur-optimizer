"""
Action Bandit — contextual bandit for action selection.

Each action is an arm. The bandit chooses based on measured outcomes,
not LLM freestyle. The LLM can explain, but the bandit chooses.

ROA = Revenue Overclock Advantage
ROA_t = expected_revenue_lift(action | state) × confidence × attribution_weight × repeatability_score
        − compliance_risk − mutation_cost − platform_error_risk

best_action = argmax_a ROA(a, current_state)

Reward only counts when real metrics move:
  reward = 5.0 * booking_intent_delta
         + 3.0 * contact_click_delta
         + 2.0 * email_delta
         + 1.0 * view_delta
         - 2.0 * error_penalty
         - 3.0 * compliance_risk
         - 1.0 * excessive_mutation_penalty
"""

import json
import logging
import math
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

log = logging.getLogger("action_bandit")

BANDIT_DB = Path(__file__).parent / "overclock_bandit.db"

# All action arms
ACTIONS = [
    "refresh_availability",
    "ensure_visible",
    "check_search_rank",
    "mailbox_intent_scan",
    "reply_draft_queue",
    "visitor_revisit",
    "headline_variant_test",
    "bio_variant_test",
    "photo_order_test",
    "rate_position_test",
    "city_rank_scan",
    "traffic_report",
    "do_nothing",
]

# Actions that mutate the profile (need mutation cost)
MUTATION_ACTIONS = {
    "headline_variant_test",
    "bio_variant_test",
    "photo_order_test",
    "rate_position_test",
}

# Actions that are always safe (no platform risk)
SAFE_ACTIONS = {
    "refresh_availability",
    "ensure_visible",
    "check_search_rank",
    "mailbox_intent_scan",
    "reply_draft_queue",
    "visitor_revisit",
    "city_rank_scan",
    "traffic_report",
    "do_nothing",
}


@dataclass
class ActionOutcome:
    action: str
    reward: float
    metric_delta: Dict[str, float] = field(default_factory=dict)
    timestamp: str = ""
    state_before_hash: str = ""
    state_after_hash: str = ""
    error: str = ""


def _db():
    conn = sqlite3.connect(str(BANDIT_DB))
    conn.row_factory = sqlite3.Row
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS action_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tenant_id TEXT,
        action TEXT,
        reward REAL,
        metric_delta TEXT,
        state_before_hash TEXT,
        state_after_hash TEXT,
        error TEXT,
        timestamp TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_action ON action_history(action);
    CREATE INDEX IF NOT EXISTS idx_tenant ON action_history(tenant_id);
    """)
    conn.commit()
    return conn


def get_action_stats(conn: sqlite3.Connection, tenant_id: str = "") -> Dict[str, Dict]:
    """Get per-action stats: count, avg_reward, confidence."""
    cur = conn.cursor()
    stats = {}
    for action in ACTIONS:
        cur.execute(
            "SELECT COUNT(*) as n, AVG(reward) as avg_r, "
            "SUM(CASE WHEN reward > 0 THEN 1 ELSE 0 END) as wins "
            f"FROM action_history WHERE action = ? AND tenant_id = ?",
            (action, tenant_id)
        )
        row = cur.fetchone()
        n = row["n"] or 0
        avg_r = row["avg_r"] or 0.0
        wins = row["wins"] or 0
        # Wilson score interval lower bound as confidence
        if n > 0:
            z = 1.96
            p = wins / n
            denominator = 1 + z * z / n
            center = (p + z * z / (2 * n)) / denominator
            margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n) / denominator
            confidence = max(0, center - margin)
        else:
            confidence = 0.0
        stats[action] = {
            "n": n,
            "avg_reward": round(avg_r, 3),
            "win_rate": round(wins / n, 3) if n > 0 else 0.0,
            "confidence": round(confidence, 3),
        }
    return stats


def compute_roa(action: str, state, stats: Dict) -> float:
    """
    ROA = Revenue Overclock Advantage

    ROA = expected_revenue_lift × confidence × attribution_weight × repeatability
          − compliance_risk − mutation_cost − platform_error_risk
    """
    s = stats.get(action, {"avg_reward": 0, "confidence": 0, "n": 0})

    # Expected revenue lift: use avg reward as base, adjust for current state
    expected_lift = s["avg_reward"]

    # State-based adjustments
    pressure = state.revenue_pressure

    if action == "refresh_availability":
        if state.available_status != "Available":
            expected_lift = 2.0  # high value when not available
        elif state.availability_seconds_left < 3600:
            expected_lift = 1.0  # medium value when expiring
        else:
            expected_lift = 0.1  # low value when already available

    elif action == "ensure_visible":
        expected_lift = 2.0 if state.profile_hidden else 0.1

    elif action == "mailbox_intent_scan":
        expected_lift = 0.5 + (state.mailbox_intent_score * 2.0)

    elif action == "reply_draft_queue":
        expected_lift = 1.0 + (state.mailbox_intent_score * 3.0)

    elif action == "check_search_rank":
        expected_lift = 0.3

    elif action == "city_rank_scan":
        expected_lift = 0.3

    elif action == "headline_variant_test":
        # Only valuable when contact rate is low
        expected_lift = max(0, (5.0 - state.contact_rate) / 5.0) * 1.5

    elif action == "bio_variant_test":
        expected_lift = max(0, (5.0 - state.contact_rate) / 5.0) * 1.0

    elif action == "rate_position_test":
        expected_lift = 0.2  # risky, low default

    elif action == "photo_order_test":
        expected_lift = 0.3

    elif action == "traffic_report":
        expected_lift = 0.2

    elif action == "do_nothing":
        expected_lift = 0.0

    # Confidence from bandit history
    confidence = s["confidence"] if s["n"] >= 3 else 0.3  # default low confidence

    # Attribution weight: safe actions have higher attribution reliability
    attribution_weight = 0.9 if action in SAFE_ACTIONS else 0.6

    # Repeatability: can we do this again and again?
    repeatability = 0.8 if action in SAFE_ACTIONS else 0.4

    # Compliance risk
    compliance_risk = 0.0 if action in SAFE_ACTIONS else 0.3

    # Mutation cost: penalize frequent profile changes
    mutation_cost = 0.5 if action in MUTATION_ACTIONS else 0.0

    # Platform error risk
    platform_error_risk = 0.1 if action in SAFE_ACTIONS else 0.2

    roa = (
        expected_lift * confidence * attribution_weight * repeatability
        - compliance_risk
        - mutation_cost
        - platform_error_risk
    )

    return round(roa, 3)


def select_action(state, tenant_id: str = "") -> Tuple[str, Dict[str, float]]:
    """
    Select best action using contextual bandit.

    Returns (action_name, roa_scores).
    """
    conn = _db()
    stats = get_action_stats(conn, tenant_id)

    roa_scores = {}
    for action in ACTIONS:
        roa_scores[action] = compute_roa(action, state, stats)

    conn.close()

    # argmax ROA
    best = max(roa_scores, key=roa_scores.get)
    return best, roa_scores


def record_outcome(outcome: ActionOutcome, tenant_id: str = ""):
    """Record action outcome for bandit learning."""
    conn = _db()
    conn.execute(
        "INSERT INTO action_history (tenant_id, action, reward, metric_delta, state_before_hash, state_after_hash, error, timestamp) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (tenant_id, outcome.action, outcome.reward,
         json.dumps(outcome.metric_delta),
         outcome.state_before_hash, outcome.state_after_hash,
         outcome.error, outcome.timestamp or datetime.now(timezone.utc).isoformat())
    )
    conn.commit()
    conn.close()
    log.info(f"  ◉ Recorded: {outcome.action} reward={outcome.reward:.3f}")


def explain_last_action(tenant_id: str = "") -> str:
    """Explain the last action taken and why."""
    conn = _db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM action_history WHERE tenant_id = ? ORDER BY id DESC LIMIT 1",
        (tenant_id,)
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return "No actions recorded yet."

    stats = get_action_stats(_db(), tenant_id)
    action = row["action"]
    s = stats.get(action, {})

    return (
        f"Last action: {action}\n"
        f"  Reward: {row['reward']:.3f}\n"
        f"  Metric delta: {row['metric_delta']}\n"
        f"  Error: {row['error'] or 'none'}\n"
        f"  Timestamp: {row['timestamp']}\n"
        f"  History: {s['n']} runs, avg_reward={s['avg_reward']:.3f}, win_rate={s['win_rate']:.1%}\n"
        f"  Confidence: {s['confidence']:.3f}"
    )
