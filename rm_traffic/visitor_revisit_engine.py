"""
Visitor Revisit Engine — lawful review-and-reply recovery engine.

NOT a traffic bot. NOT a fake visitor generator. NOT a stealth scraper.

It reads live visitors/new visits from verified RM endpoints, joins against
mailbox/prior lead state, ranks who deserves review now, and drafts a safe
reply only when there is a prior message or platform-permitted contact path.

No fake visits. No scraping bypass. No auto-send. Every row requires approval.

Scoring:
  NOW   — visitor also messaged, asked about availability/today/tonight/rate/location/booking
  HOT   — visitor has prior thread or repeat signal but no fresh booking ask
  WARM  — visitor only, no message yet
  IGNORE — spam, boundary/adult-coded, opt-out, wrong number, unsafe, competitor, out-of-area

Output: visitor_revisit_queue.csv

Compliance:
  - CAN-SPAM: opt-out handling enforced
  - TCPA/robotext: no automated marketing texts — only approved replies to inbound/platform contacts
  - No cold outreach to view-only visitors
  - All drafts approval-gated
"""

import csv
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .intent_engine import classify, keyword_classify, IntentResult

log = logging.getLogger("visitor_revisit")

OUTPUT_DIR = Path(os.environ.get("RM_OUTPUT_DIR", Path(__file__).parent.parent / "output"))

# ─── Templates (canonical, local-only, no cloud) ─────────────────────

TEMPLATES = {
    "booking_now": (
        "Yes — I'm available today. Manhattan incall, deep tissue/sports recovery. "
        "60 min is $200. What time works best?"
    ),
    "price_question": (
        "Rate is $200 for 60 min, $280 for 90 min, $360 for 120 min. "
        "Manhattan incall. What duration and time work for you?"
    ),
    "location_question": (
        "I'm based in Manhattan with private incall. "
        "Outcall within Manhattan may be possible with travel fee. "
        "What area and time are you thinking?"
    ),
    "availability_question": (
        "I'm available today and this week. Manhattan incall, $200 for 60 min. "
        "What day and time work for you?"
    ),
    "repeat_client": (
        "Good to hear from you again. I have openings today. "
        "Do you want the same style as last time or more deep tissue?"
    ),
    "high_value_repeat": (
        "Great to hear from you again! I have openings today. "
        "Same location in Manhattan. Do you want the same style as last time?"
    ),
    "ghosted_lead": (
        "Hi — following up. I'm available this week if you'd like to book. "
        "Manhattan incall, $200 for 60 min. What time works for you?"
    ),
    "inquiry": (
        "Hi! Thanks for your interest. I offer deep tissue and sports recovery "
        "massage in Manhattan. Rate is $200 for 60 min. What questions can I answer?"
    ),
}

# Suppression keywords
OPT_OUT_KW = ["stop", "unsubscribe", "remove", "do not text", "don't text",
              "not interested", "wrong number", "stop texting", "opt out",
              "don't contact", "do not contact", "take me off", "no more"]
SPAM_KW = ["promo", "discount", "offer", "deal", "click here", "visit my",
           "check out my", "follow me", "subscribe", "free", "bonus"]
UNSAFE_KW = ["raw", "bb", "bareback", "unsafe", "no condom", "bare"]
BOUNDARY_KW = ["escort", "full service", "fs", "gfe", "happy ending", "extras", "menu"]


@dataclass
class VisitorContact:
    """One row in the revisit queue."""
    visitor_hash: str = ""
    username: str = ""
    last_seen_at: str = ""
    prior_message_exists: bool = False
    last_message_age_hours: float = 0.0
    urgency: str = "WARM_observe"  # NOW, HOT, WARM, IGNORE
    reason_code: str = ""
    recommended_action: str = ""
    draft_text: str = ""
    approval_required: bool = True
    campaign_eligible: bool = False
    receipt_hash: str = ""
    intent_class: str = ""
    confidence: float = 0.0
    risk_flags: List[str] = field(default_factory=list)


def _hash_visitor(username: str, visitor_id: str = "") -> str:
    """Hash visitor identity for privacy."""
    raw = f"{username}:{visitor_id}:{time.time() // 3600}"  # hour-bucketed hash
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _check_suppression(message: str) -> Optional[str]:
    """Check if message triggers suppression. Returns reason or None."""
    text = (message or "").lower().strip()
    if not text:
        return None
    if any(kw in text for kw in OPT_OUT_KW):
        return "opt_out_detected"
    if any(kw in text for kw in UNSAFE_KW):
        return "unsafe_content"
    if any(kw in text for kw in BOUNDARY_KW):
        return "boundary_adult_coded"
    if any(kw in text for kw in SPAM_KW):
        return "spam_content"
    return None


def _age_hours(timestamp: int) -> float:
    """Convert epoch timestamp to age in hours."""
    if not timestamp:
        return 0.0
    return max(0.0, (time.time() - float(timestamp)) / 3600.0)


def _get_template(intent_class: str) -> str:
    """Get canonical template for intent class."""
    return TEMPLATES.get(intent_class, TEMPLATES["inquiry"])


def _score_urgency(has_message: bool, has_outbound_reply: bool,
                   intent: IntentResult, age_hours: float,
                   is_repeat: bool, suppression: Optional[str]) -> Tuple[str, str, str]:
    """
    Score urgency level. Returns (urgency, reason_code, recommended_action).

    NOW    — messaged + booking intent + no reply = immediate recovery
    HOT    — prior thread or repeat signal, no fresh booking ask
    WARM   — viewed only, no message — observe, do not contact
    IGNORE — suppression triggered
    """
    if suppression:
        return ("IGNORE", suppression, "suppress_no_action")

    if not has_message:
        # View-only visitor — no platform-permitted contact path
        return ("WARM_observe", "view_only_no_message", "observe_wait_for_inbound")

    # Has a message
    if not has_outbound_reply:
        # Unresponded message — highest priority
        if intent.classification in ("booking_now", "high_value_repeat"):
            return ("P0_revisit_now", "unresponded_booking_intent",
                    "review_now_prepare_same_day_reply_draft")
        elif intent.classification in ("price_question", "location_question", "availability_question"):
            return ("P0_revisit_now", "unresponded_inquiry_with_intent",
                    "review_now_prepare_info_reply_draft")
        elif is_repeat:
            return ("P1_reengage_today", "unresponded_repeat_client",
                    "review_today_prepare_reengagement_draft")
        else:
            return ("P1_reengage_today", "unresponded_inquiry",
                    "review_today_prepare_reply_draft")

    # Has prior reply but new activity
    if is_repeat or intent.classification in ("repeat_client", "high_value_repeat"):
        return ("P1_reengage_today", "repeat_client_new_activity",
                "review_today_prepare_reengagement_draft")
    elif intent.classification in ("booking_now", "price_question", "location_question"):
        return ("P1_reengage_today", "returning_inquiry",
                "review_today_prepare_reply_draft")
    elif age_hours < 48:
        return ("P2_review_when_free", "recent_activity_no_urgent_intent",
                "review_when_free_assess_context")
    else:
        return ("P3_low_priority", "old_thread_no_fresh_intent",
                "archive_or_low_priority_review")


def build_revisit_queue(api, state=None, tenant_id: str = "") -> List[VisitorContact]:
    """
    Build the visitor revisit queue from live RM endpoints.

    Reads:
      - mailbox (verified endpoint) — for message threads
      - keeponline (verified endpoint) — for new visits/visitors
      - dashboard/ad-statistics — for traffic context

    Does NOT:
      - Create fake visits
      - Send messages
      - Contact view-only visitors
      - Use cloud LLM providers
    """
    queue: List[VisitorContact] = []

    # 1. Pull mailbox threads (verified endpoint)
    try:
        mailbox = api.get_mailbox(page=1, folder=1, sort=1)
        emails = mailbox.get("emails", [])
        log.info(f"  ◉ Mailbox: {len(emails)} conversations")
    except Exception as e:
        log.warning(f"  ⟁ mailbox error: {e}")
        emails = []

    # 2. Pull keeponline for new visit signals
    try:
        keep = api.get_keeponline()
        new_visits = int(keep.get("newVisits", 0))
        new_emails = int(keep.get("newEmails", 0))
        log.info(f"  ◉ KeepOnline: new_visits={new_visits} new_emails={new_emails}")
    except Exception as e:
        log.warning(f"  ⟁ keeponline error: {e}")
        new_visits = 0
        new_emails = 0

    # 3. Process mailbox threads — these are the recovery targets
    for email in emails:
        uc = email.get("userCard", {})
        username = uc.get("username", "")
        msg = email.get("lastMessage", "") or ""
        created_at = int(email.get("createdAt", 0) or 0)
        unread = bool(email.get("unread", 0))
        is_premium = bool(uc.get("isPremium", 0))

        # Check suppression first
        suppression = _check_suppression(msg)

        # Classify intent (keyword-based, local only — no cloud)
        intent = keyword_classify(msg)

        # Determine if we have prior outbound (heuristic: if unread=False, we likely replied)
        has_outbound_reply = not unread  # if not unread, we've seen and likely replied

        # Check for repeat signals
        is_repeat = intent.classification in ("repeat_client", "high_value_repeat")

        age_h = _age_hours(created_at)

        urgency, reason, action = _score_urgency(
            has_message=bool(msg.strip()),
            has_outbound_reply=has_outbound_reply,
            intent=intent,
            age_hours=age_h,
            is_repeat=is_repeat,
            suppression=suppression,
        )

        # Only draft for messaged contacts (not view-only)
        draft_text = ""
        if urgency != "IGNORE" and urgency != "WARM_observe":
            draft_text = _get_template(intent.classification)

        # All drafts require approval — no exceptions
        approval_required = True
        if urgency == "IGNORE":
            approval_required = False  # no draft to approve
            draft_text = ""

        visitor_hash = _hash_visitor(username)

        contact = VisitorContact(
            visitor_hash=visitor_hash,
            username=username,
            last_seen_at=datetime.fromtimestamp(created_at, tz=timezone.utc).isoformat() if created_at else "",
            prior_message_exists=bool(msg.strip()),
            last_message_age_hours=round(age_h, 1),
            urgency=urgency,
            reason_code=reason,
            recommended_action=action,
            draft_text=draft_text,
            approval_required=approval_required,
            campaign_eligible=False,  # always false until review decision
            receipt_hash=hashlib.sha256(
                f"{visitor_hash}:{urgency}:{reason}:{time.time() // 3600}".encode()
            ).hexdigest()[:12],
            intent_class=intent.classification,
            confidence=intent.confidence,
            risk_flags=intent.risk_flags if not suppression else [suppression],
        )
        queue.append(contact)

    # 4. Add WARM entries for new visits without messages (observe only)
    # We don't have visitor usernames from keeponline, so we log a summary entry
    if new_visits > 0 and not emails:
        log.info(f"  ◉ {new_visits} new visits with no mailbox threads — WARM observe only")

    # Sort by urgency priority
    urgency_order = {"P0_revisit_now": 0, "P1_reengage_today": 1,
                     "P2_review_when_free": 2, "P3_low_priority": 3,
                     "WARM_observe": 4, "IGNORE": 5}
    queue.sort(key=lambda c: urgency_order.get(c.urgency, 99))

    return queue


def write_revisit_queue(queue: List[VisitorContact], output_dir: Path = None) -> str:
    """Write visitor_revisit_queue.csv. Returns file path."""
    if output_dir is None:
        output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    filepath = output_dir / "visitor_revisit_queue.csv"
    fieldnames = [
        "visitor_hash", "username", "last_seen_at", "prior_message_exists",
        "last_message_age_hours", "urgency", "reason_code", "recommended_action",
        "draft_text", "approval_required", "campaign_eligible", "receipt_hash",
        "intent_class", "confidence", "risk_flags",
    ]

    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for c in queue:
            writer.writerow({
                "visitor_hash": c.visitor_hash,
                "username": c.username,
                "last_seen_at": c.last_seen_at,
                "prior_message_exists": c.prior_message_exists,
                "last_message_age_hours": c.last_message_age_hours,
                "urgency": c.urgency,
                "reason_code": c.reason_code,
                "recommended_action": c.recommended_action,
                "draft_text": c.draft_text,
                "approval_required": c.approval_required,
                "campaign_eligible": c.campaign_eligible,
                "receipt_hash": c.receipt_hash,
                "intent_class": c.intent_class,
                "confidence": c.confidence,
                "risk_flags": ";".join(c.risk_flags),
            })

    log.info(f"  ◉ Wrote {filepath} ({len(queue)} rows)")
    return str(filepath)


def format_queue_summary(queue: List[VisitorContact]) -> str:
    """Format queue for console display."""
    lines = [f"\n{'='*60}", f"  VISITOR REVISIT QUEUE — {len(queue)} contacts", f"{'='*60}\n"]

    counts = {}
    for c in queue:
        counts[c.urgency] = counts.get(c.urgency, 0) + 1

    for urgency in ["P0_revisit_now", "P1_reengage_today", "P2_review_when_free",
                    "P3_low_priority", "WARM_observe", "IGNORE"]:
        n = counts.get(urgency, 0)
        if n:
            lines.append(f"  {urgency}: {n}")

    lines.append("")

    for c in queue:
        if c.urgency == "IGNORE":
            lines.append(f"  🚫 {c.username or c.visitor_hash[:8]} [{c.urgency}] — {c.reason_code}")
            continue

        if c.urgency == "WARM_observe":
            lines.append(f"  ◌ {c.username or c.visitor_hash[:8]} [{c.urgency}] — {c.reason_code}")
            continue

        approval = "🔒 approval" if c.approval_required else "⚡ auto-ok"
        lines.append(f"  ◉ {c.username or c.visitor_hash[:8]} [{c.urgency}] {approval}")
        lines.append(f"    Intent: {c.intent_class} (conf={c.confidence:.2f})")
        lines.append(f"    Action: {c.recommended_action}")
        if c.draft_text:
            lines.append(f"    Draft: \"{c.draft_text[:120]}\"")
        lines.append("")

    return "\n".join(lines)
