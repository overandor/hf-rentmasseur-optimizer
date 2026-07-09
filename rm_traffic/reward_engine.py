"""
Reward Engine — measures metric deltas after actions and computes reward.

reward = 5.0 * booking_intent_delta
       + 3.0 * contact_click_delta
       + 2.0 * email_delta
       + 1.0 * view_delta
       - 2.0 * error_penalty
       - 3.0 * compliance_risk
       - 1.0 * excessive_mutation_penalty

Also computes attribution: which action produced which metric movement.
"""

import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

log = logging.getLogger("reward_engine")

REWARD_DB = Path(__file__).parent / "overclock_bandit.db"


@dataclass
class MetricDelta:
    views_delta: int = 0
    contact_clicks_delta: int = 0
    emails_delta: int = 0
    booking_intent_delta: float = 0.0
    rank_delta: int = 0
    availability_changed: bool = False
    visibility_changed: bool = False


def is_measurement_valid(state_before, state_after) -> bool:
    """Check if both snapshots have valid measurements.
    A failed measurement is not a negative outcome — it is no outcome."""
    if not state_before.measurement_valid:
        return False
    if not state_after.measurement_valid:
        return False
    return True


def compute_delta(state_before, state_after) -> MetricDelta:
    """Compute metric delta between two TrafficState snapshots.
    Returns all-zero delta if measurement is invalid."""
    if not is_measurement_valid(state_before, state_after):
        log.warning("  ⟁ MEASUREMENT INVALID — returning zero delta, no bandit update")
        return MetricDelta()
    return MetricDelta(
        views_delta=state_after.views - state_before.views,
        contact_clicks_delta=state_after.contact_clicks - state_before.contact_clicks,
        emails_delta=state_after.mailbox_count - state_before.mailbox_count,
        booking_intent_delta=round(
            state_after.mailbox_intent_score - state_before.mailbox_intent_score, 3
        ),
        rank_delta=state_after.search_rank - state_before.search_rank if state_after.search_rank and state_before.search_rank else 0,
        availability_changed=state_after.available_status != state_before.available_status,
        visibility_changed=state_after.profile_hidden != state_before.profile_hidden,
    )


def compute_reward(delta: MetricDelta, action: str, error: str = "",
                     measurement_valid: bool = True,
                     action_result: Dict = None) -> float:
    """
    Compute reward from metric delta.

    If measurement is invalid (403/timeout/auth failure on after-snapshot),
    return 0.0 — a failed measurement is not a negative outcome.

    For reply_draft_queue, reward by draft quality and workflow outputs,
    not by same-cycle traffic deltas.
    """
    if not measurement_valid:
        log.warning("  ⟁ MEASUREMENT INVALID — reward=0.0, no bandit update")
        return 0.0

    # ─── reply_draft_queue: reward by draft quality, not traffic deltas ───
    if action == "reply_draft_queue" and action_result:
        drafts_created = action_result.get("drafts_queued", 0)
        blocked = action_result.get("blocked", 0)
        needs_approval = action_result.get("needs_approval", 0)
        auto_ok = action_result.get("auto_ok", 0)
        cloud_leaked = action_result.get("cloud_fallback_attempted", False)
        bad_llm = action_result.get("bad_llm_output", False)

        reward = 0.0
        reward += 0.5 * drafts_created       # small positive per valid draft
        reward += 0.3 * blocked               # small positive for catching unsafe/DNC
        reward += 0.2 * auto_ok               # small positive for safe auto-ok
        if cloud_leaked:
            reward -= 2.0                     # penalty: cloud fallback on private data
        if bad_llm:
            reward -= 1.0                     # penalty: bad LLM output
        return round(reward, 3)

    # ─── visitor_revisit: drafts are inventory, not revenue ───
    # Reward only by downstream outcomes, not drafts generated.
    # Small provisional positive for queue building + suppression catches.
    # Real reward comes later when reviewed/approved/sent/replied/booked.
    if action == "visitor_revisit" and action_result:
        drafts_queued = action_result.get("drafts_queued", 0)
        ignored = action_result.get("ignored", 0)  # suppression catches
        p0 = action_result.get("p0_revisit_now", 0)
        cloud_leaked = action_result.get("cloud_fallback_attempted", False)

        # Downstream outcomes (these come later, not same-cycle)
        reply_sent = action_result.get("reply_sent_after_approval", 0)
        client_replied = action_result.get("client_replied", 0)
        call_received = action_result.get("call_received", 0)
        booking_confirmed = action_result.get("booking_confirmed", 0)
        session_completed = action_result.get("session_completed", 0)

        reward = 0.0
        # Small provisional positive for building the queue
        reward += 0.2 * drafts_queued          # drafts are inventory, small credit
        reward += 0.3 * ignored                 # catching suppressions is valuable
        reward += 0.1 * p0                      # identifying urgent recovery targets

        # Real reward from downstream outcomes
        reward += 2.0 * reply_sent              # approved reply actually sent
        reward += 5.0 * client_replied          # client responded to our reply
        reward += 10.0 * call_received          # real call
        reward += 20.0 * booking_confirmed      # booking confirmed
        reward += 50.0 * session_completed      # session completed = revenue

        if cloud_leaked:
            reward -= 2.0                       # penalty: cloud on private data

        return round(reward, 3)

    # ─── Standard traffic-delta reward for other actions ───
    reward = (
        5.0 * max(0, delta.booking_intent_delta)
        + 3.0 * max(0, delta.contact_clicks_delta)
        + 2.0 * max(0, delta.emails_delta)
        + 1.0 * max(0, delta.views_delta) * 0.01
    )

    # Penalty for negative deltas (only if measurement is valid)
    if delta.booking_intent_delta < 0:
        reward += 3.0 * delta.booking_intent_delta
    if delta.contact_clicks_delta < 0:
        reward += 2.0 * delta.contact_clicks_delta

    # Rank improvement is good (lower rank number = better)
    if delta.rank_delta < 0:
        reward += 1.0 * abs(delta.rank_delta) * 0.5

    # Error penalty
    if error:
        reward -= 2.0

    # Compliance risk
    risky_actions = {"rate_position_test", "photo_order_test"}
    if action in risky_actions:
        reward -= 0.5

    # Excessive mutation penalty
    mutation_actions = {"headline_variant_test", "bio_variant_test", "photo_order_test", "rate_position_test"}
    if action in mutation_actions:
        if delta.contact_clicks_delta == 0 and delta.booking_intent_delta == 0:
            reward -= 1.0

    # Availability fix reward
    if action == "refresh_availability" and delta.availability_changed:
        reward += 2.0

    # Visibility fix reward
    if action == "ensure_visible" and delta.visibility_changed:
        reward += 2.0

    return round(reward, 3)


def delta_to_dict(delta: MetricDelta) -> Dict:
    return {
        "views_delta": delta.views_delta,
        "contact_clicks_delta": delta.contact_clicks_delta,
        "emails_delta": delta.emails_delta,
        "booking_intent_delta": delta.booking_intent_delta,
        "rank_delta": delta.rank_delta,
        "availability_changed": delta.availability_changed,
        "visibility_changed": delta.visibility_changed,
    }
