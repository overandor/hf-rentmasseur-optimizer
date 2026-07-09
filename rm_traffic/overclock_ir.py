#!/usr/bin/env python3
"""
TrafficOverclockIR — Canonical state for RM Traffic Overclock.

The product is not traffic. The product is conversion.

Optimize: time-to-booking and qualified-client yield.
Not: more scripts, more cron jobs, more visits, more scraping.

Client Quantity = HighIntentSources × CaptureRate × QualificationRate
Conversion Speed = DetectionLatency + DraftLatency + ApprovalLatency + ReplyLatency
Revenue = ConfirmedBookings × AverageSessionValue × ShowRate × RepeatRate
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any


# ─── Urgency tiers ─────────────────────────────────────────────────

URGENCY_NOW = "NOW"          # booking language + today/tomorrow + NYC + direct question
URGENCY_HOT = "HOT"          # profile visitor + prior message + location match
URGENCY_WARM = "WARM"        # profile visitor only
URGENCY_COLD = "COLD"        # social mention / search discovery
URGENCY_IGNORE = "IGNORE"    # spam, competitor, unsafe, out-of-area

URGENCY_ORDER = [URGENCY_NOW, URGENCY_HOT, URGENCY_WARM, URGENCY_COLD, URGENCY_IGNORE]

# ─── Reply classes ─────────────────────────────────────────────────

REPLY_BOOKING_NOW = "booking_now_reply"
REPLY_PRICE_QUESTION = "price_question_reply"
REPLY_LOCATION_QUESTION = "location_question_reply"
REPLY_REPEAT_CLIENT = "repeat_client_reply"
REPLY_INQUIRY = "inquiry_reply"
REPLY_FOLLOW_UP = "follow_up_reply"
REPLY_CLOSE_LOOP = "close_loop_reply"


@dataclass
class LeadState:
    """One person in the funnel. Sorted by urgency, not by arrival time."""
    lead_id: str = ""               # person_id_hash
    username: str = ""
    source: str = "rentmasseur"
    first_seen_at: str = ""
    last_touch_at: str = ""
    intent_score: float = 0.0
    urgency: str = URGENCY_COLD
    location_match: bool = False
    budget_match: Optional[bool] = None
    time_urgency: bool = False      # "today", "tonight", "tomorrow"
    repeat_client: bool = False
    risk_flag: str = ""             # spam, competitor, unsafe, out_of_area, ""
    classification: str = "unclassified"
    recommended_reply_class: str = ""
    recommended_reply_text: str = ""
    approval_status: str = "pending"  # pending / approved / rejected / sent
    booking_status: str = "inquiry"   # inquiry / requested / confirmed / completed / cancelled / no_show
    collected_amount: float = 0.0
    message_received: str = ""
    message_sent: str = ""
    consent_status: str = "unknown"
    cooldown_until: str = ""
    suppressed: bool = False
    follow_up_due_at: str = ""      # when to send follow-up if no reply
    close_loop_due_at: str = ""     # when to send close-loop if still no reply
    first_reply_seconds: float = 0.0  # time from first_seen to first reply
    is_premium: bool = False


@dataclass
class BookingEvent:
    """The attribution table. One row per booking journey."""
    booking_id: str = ""
    lead_id: str = ""
    source: str = "rentmasseur"
    first_action: str = ""           # what triggered the lead
    first_reply_seconds: float = 0.0
    booking_requested_at: str = ""
    booking_confirmed_at: str = ""
    session_completed_at: str = ""
    amount_collected: float = 0.0
    repeat_booking: bool = False
    attributed_action_id: str = ""


@dataclass
class RevenueMetrics:
    """Hard revenue metrics. This is what the dashboard shows."""
    # Lead funnel
    total_leads: int = 0
    qualified_leads: int = 0
    booking_ready_leads: int = 0

    # Conversion
    reply_rate: float = 0.0
    booking_request_rate: float = 0.0
    booking_confirm_rate: float = 0.0
    show_rate: float = 0.0

    # Revenue
    collected_revenue: float = 0.0
    expected_revenue: float = 0.0
    average_booking_value: float = 0.0
    repeat_rate: float = 0.0

    # Speed
    median_reply_time_seconds: float = 0.0
    median_time_to_booking_hours: float = 0.0

    # Attribution
    best_source: str = ""
    worst_source: str = ""
    source_roi: Dict[str, float] = field(default_factory=dict)

    # Compliance
    compliance_incidents: int = 0
    suppressed_count: int = 0

    # Drafts
    drafts_pending: int = 0
    drafts_approved: int = 0
    drafts_sent: int = 0

    # Secondary (upstream, not revenue)
    total_views: int = 0
    total_contacts: int = 0
    ctr: float = 0.0
    search_rank: int = 0

    def compute(self, leads: List[LeadState], bookings: List[BookingEvent]):
        self.total_leads = len(leads)
        self.qualified_leads = sum(1 for l in leads if l.urgency in (URGENCY_NOW, URGENCY_HOT, URGENCY_WARM))
        self.booking_ready_leads = sum(1 for l in leads if l.urgency == URGENCY_NOW)

        replied = sum(1 for l in leads if l.message_sent)
        self.reply_rate = round(replied / self.total_leads * 100, 1) if self.total_leads else 0.0

        requested = [b for b in bookings if b.booking_requested_at]
        confirmed = [b for b in bookings if b.booking_confirmed_at]
        completed = [b for b in bookings if b.session_completed_at]

        self.booking_request_rate = round(len(requested) / self.qualified_leads * 100, 1) if self.qualified_leads else 0.0
        self.booking_confirm_rate = round(len(confirmed) / len(requested) * 100, 1) if requested else 0.0
        self.show_rate = round(len(completed) / len(confirmed) * 100, 1) if confirmed else 0.0

        self.collected_revenue = sum(b.amount_collected for b in completed)
        self.expected_revenue = sum(b.amount_collected for b in confirmed if not b.session_completed_at)
        paid = [b for b in completed if b.amount_collected > 0]
        self.average_booking_value = round(sum(b.amount_collected for b in paid) / len(paid), 2) if paid else 0.0

        repeat = sum(1 for l in leads if l.repeat_client)
        self.repeat_rate = round(repeat / self.total_leads * 100, 1) if self.total_leads else 0.0

        reply_times = [l.first_reply_seconds for l in leads if l.first_reply_seconds > 0]
        self.median_reply_time_seconds = sorted(reply_times)[len(reply_times)//2] if reply_times else 0.0

        self.suppressed_count = sum(1 for l in leads if l.suppressed)
        self.drafts_pending = sum(1 for l in leads if l.approval_status == "pending")
        self.drafts_approved = sum(1 for l in leads if l.approval_status == "approved")
        self.drafts_sent = sum(1 for l in leads if l.approval_status == "sent")

        # Source attribution
        by_source: Dict[str, float] = {}
        for b in completed:
            by_source[b.source] = by_source.get(b.source, 0) + b.amount_collected
        self.source_roi = by_source
        if by_source:
            self.best_source = max(by_source, key=by_source.get)
            self.worst_source = min(by_source, key=by_source.get)


@dataclass
class ProfileSnapshot:
    """Read-only profile state. Secondary signal."""
    headline: str = ""
    availability_option: int = 0
    availability_label: str = ""
    is_visible: bool = True
    search_rank: int = 0
    search_total: int = 0
    active_rates: List[Dict] = field(default_factory=list)
    avg_rate: float = 0.0


@dataclass
class TrafficOverclockIR:
    """The canonical state object.

    Client Quantity = HighIntentSources × CaptureRate × QualificationRate
    Conversion Speed = DetectionLatency + DraftLatency + ApprovalLatency + ReplyLatency
    Revenue = ConfirmedBookings × AverageSessionValue × ShowRate × RepeatRate
    """
    timestamp: str = ""
    cycle_num: int = 0
    login_ok: bool = False
    login_error: str = ""

    # Lane 1: Observe
    profile: ProfileSnapshot = field(default_factory=ProfileSnapshot)
    leads: List[LeadState] = field(default_factory=list)
    mailbox_raw: List[Dict] = field(default_factory=list)

    # Lane 2: Qualify + urgency sort
    metrics: RevenueMetrics = field(default_factory=RevenueMetrics)

    # Lane 3: Draft (fast reply templates, not LLM freestyle)
    drafts_generated: int = 0

    # Lane 4: Approve/Send
    drafts_sent_count: int = 0

    # Lane 5: Outcome
    bookings: List[BookingEvent] = field(default_factory=list)

    # Lane 6: Learn
    attribution: Dict[str, float] = field(default_factory=dict)
    learnings: List[str] = field(default_factory=list)

    # Receipt
    receipt_hash: str = ""
    status: str = "GREEN"

    _raw: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def compute_receipt(self) -> str:
        data = self.to_json(include_raw=False)
        self.receipt_hash = hashlib.sha256(data.encode()).hexdigest()[:16]
        return self.receipt_hash

    def to_json(self, include_raw: bool = False) -> str:
        d = asdict(self)
        if not include_raw:
            d.pop("_raw", None)
        return json.dumps(d, indent=2, default=str, sort_keys=True)

    def to_dict(self, include_raw: bool = False) -> Dict:
        d = asdict(self)
        if not include_raw:
            d.pop("_raw", None)
        return d

    def summary(self) -> str:
        m = self.metrics
        lines = [
            f"TrafficOverclockIR — {self.timestamp}",
            f"Status: {self.status}",
            f"Login: {'OK' if self.login_ok else 'FAILED'}",
            f"",
            f"Today:",
            f"  {m.total_leads} leads detected",
            f"  {m.qualified_leads} qualified",
            f"  {m.booking_ready_leads} booking-ready",
            f"  {len([b for b in self.bookings if b.booking_confirmed_at])} confirmed",
            f"  ${m.expected_revenue:.0f} expected",
            f"  ${m.collected_revenue:.0f} collected",
            f"  median reply time: {m.median_reply_time_seconds:.0f}s",
            f"  best source: {m.best_source or '—'}",
            f"  worst source: {m.worst_source or '—'}",
            f"",
            f"Revenue Metrics:",
            f"  Reply rate: {m.reply_rate}%",
            f"  Booking request rate: {m.booking_request_rate}%",
            f"  Booking confirm rate: {m.booking_confirm_rate}%",
            f"  Show rate: {m.show_rate}%",
            f"  Avg booking value: ${m.average_booking_value:.0f}",
            f"  Repeat rate: {m.repeat_rate}%",
            f"  Compliance incidents: {m.compliance_incidents}",
            f"  Suppressed: {m.suppressed_count}",
            f"",
            f"Drafts: {m.drafts_pending} pending, {m.drafts_approved} approved, {m.drafts_sent} sent",
            f"",
            f"Secondary (upstream):",
            f"  Views: {m.total_views} (CTR: {m.ctr}%)",
            f"  Search rank: #{m.search_rank}",
            f"  Availability: {self.profile.availability_label}",
            f"",
            f"Leads by urgency:",
        ]
        for tier in URGENCY_ORDER:
            count = sum(1 for l in self.leads if l.urgency == tier)
            if count:
                lines.append(f"  {tier}: {count}")

        lines.append(f"\nBookings tracked: {len(self.bookings)}")
        lines.append(f"Learnings: {len(self.learnings)}")
        lines.append(f"\nReceipt: {self.receipt_hash}")
        return "\n".join(lines)
