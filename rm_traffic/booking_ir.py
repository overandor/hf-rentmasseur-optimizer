#!/usr/bin/env python3
"""
BookingIR — Canonical business state for the revenue pipeline.

The product is not traffic. The product is conversion.

Core object: RevenueEvent (a lead → booking → payment → repeat journey)
Secondary: LeadRecord, DraftReply, BookingRecord

Hard revenue metrics replace vanity metrics:
  qualified_leads, reply_rate, booking_request_rate, booking_confirm_rate,
  show_rate, collected_revenue, average_booking_value, repeat_rate,
  time_to_reply, source_roi, compliance_incidents
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any


# ─── Lead classification ───────────────────────────────────────────

LEAD_CLASSIFICATIONS = [
    "booking_ready",      # explicit request for session, time, location
    "inquiry",            # asking questions, price, availability
    "low_intent",         # vague, "maybe", "just looking"
    "spam",               # promotional, irrelevant
    "competitor",         # another masseur fishing
    "unsafe",             # suspicious, potentially harmful
    "out_of_area",        # too far, won't travel
    "repeat_client",      # has booked before
    "already_active",     # conversation already in progress
]


@dataclass
class LeadRecord:
    """One person who showed up in the mailbox or visitor list."""
    person_id_hash: str = ""          # SHA-256 of username (privacy)
    username: str = ""                # kept locally only, never committed
    source: str = "rentmasseur"       # rentmasseur / referral / direct
    first_seen_at: str = ""
    last_message_at: str = ""
    classification: str = "unclassified"
    intent_score: float = 0.0         # 0.0 to 1.0
    location_match: bool = False
    budget_match: Optional[bool] = None
    is_premium: bool = False
    is_repeat: bool = False
    message_received: str = ""        # last inbound message text
    message_sent: str = ""            # last outbound message text
    consent_status: str = "unknown"   # unknown / opted_in / opted_out
    cooldown_until: str = ""          # ISO timestamp, no contact before this
    suppressed: bool = False          # permanently suppressed


@dataclass
class DraftReply:
    """AI-drafted reply awaiting human approval."""
    person_id_hash: str = ""
    username: str = ""
    draft_text: str = ""
    includes_price: bool = False
    includes_availability: bool = False
    includes_location: bool = False
    includes_boundary: bool = False   # professional boundary statement
    includes_next_step: bool = False  # clear call to action
    compliance_ok: bool = True
    approval_status: str = "pending"  # pending / approved / rejected / sent
    created_at: str = ""
    approved_at: str = ""
    sent_at: str = ""
    risk_flags: List[str] = field(default_factory=list)


@dataclass
class BookingRecord:
    """The money table. One row per booking attempt."""
    person_id_hash: str = ""
    username: str = ""
    booking_status: str = "inquiry"   # inquiry / requested / confirmed / completed / cancelled / no_show
    requested_time: str = ""
    confirmed_time: str = ""
    session_duration: str = ""
    session_value: float = 0.0        # agreed price
    amount_collected: float = 0.0     # actually paid
    source: str = "rentmasseur"
    attributed_action: str = ""       # which pipeline action led to this
    created_at: str = ""
    updated_at: str = ""


@dataclass
class RevenueEvent:
    """The center of the system. Tracks a person from lead to revenue."""
    event_id: str = ""
    person_id_hash: str = ""
    source: str = "rentmasseur"
    first_seen_at: str = ""
    consent_status: str = "unknown"
    intent_score: float = 0.0
    location_match: bool = False
    budget_match: Optional[bool] = None
    requested_time: str = ""
    message_received: str = ""
    message_sent: str = ""
    booking_requested: bool = False
    booking_confirmed: bool = False
    session_completed: bool = False
    amount_collected: float = 0.0
    repeat_client: bool = False
    attribution_action_id: str = ""


@dataclass
class RevenueMetrics:
    """Hard revenue metrics. These are what matter."""
    qualified_leads: int = 0
    total_leads: int = 0
    reply_rate: float = 0.0           # % of leads we replied to
    booking_request_rate: float = 0.0  # % of qualified leads that requested booking
    booking_confirm_rate: float = 0.0  # % of requested that confirmed
    show_rate: float = 0.0            # % of confirmed that completed
    collected_revenue: float = 0.0
    average_booking_value: float = 0.0
    repeat_rate: float = 0.0
    time_to_reply_hours: float = 0.0
    source_roi: Dict[str, float] = field(default_factory=dict)
    compliance_incidents: int = 0
    drafts_pending: int = 0
    drafts_approved: int = 0
    drafts_sent: int = 0

    # Secondary (upstream, not revenue)
    total_views: int = 0
    total_contacts: int = 0
    ctr: float = 0.0
    search_rank: int = 0

    def compute(self, leads: List[LeadRecord], bookings: List[BookingRecord],
                drafts: List[DraftReply]):
        self.total_leads = len(leads)
        self.qualified_leads = sum(1 for l in leads if l.classification in ("booking_ready", "inquiry", "repeat_client"))
        replied = sum(1 for l in leads if l.message_sent)
        self.reply_rate = round(replied / self.total_leads * 100, 1) if self.total_leads else 0.0

        requested = sum(1 for b in bookings if b.booking_status in ("requested", "confirmed", "completed"))
        self.booking_request_rate = round(requested / self.qualified_leads * 100, 1) if self.qualified_leads else 0.0

        confirmed = sum(1 for b in bookings if b.booking_status in ("confirmed", "completed"))
        self.booking_confirm_rate = round(confirmed / requested * 100, 1) if requested else 0.0

        completed = sum(1 for b in bookings if b.booking_status == "completed")
        self.show_rate = round(completed / confirmed * 100, 1) if confirmed else 0.0

        self.collected_revenue = sum(b.amount_collected for b in bookings if b.booking_status == "completed")
        paid_bookings = [b for b in bookings if b.booking_status == "completed" and b.amount_collected > 0]
        self.average_booking_value = round(sum(b.amount_collected for b in paid_bookings) / len(paid_bookings), 2) if paid_bookings else 0.0

        repeat_clients = sum(1 for l in leads if l.is_repeat)
        self.repeat_rate = round(repeat_clients / self.total_leads * 100, 1) if self.total_leads else 0.0

        self.drafts_pending = sum(1 for d in drafts if d.approval_status == "pending")
        self.drafts_approved = sum(1 for d in drafts if d.approval_status == "approved")
        self.drafts_sent = sum(1 for d in drafts if d.approval_status == "sent")

        self.compliance_incidents = sum(1 for d in drafts if not d.compliance_ok)


@dataclass
class ProfileSnapshot:
    """Read-only profile state. Secondary signal, not revenue."""
    headline: str = ""
    availability_option: int = 0
    availability_label: str = ""
    is_visible: bool = True
    search_rank: int = 0
    search_total: int = 0
    active_rates: List[Dict] = field(default_factory=list)
    avg_rate: float = 0.0


@dataclass
class BookingIR:
    """The canonical business state object.

    Centered on revenue events, not activity counts.
    Every lane reads and writes this object.
    """
    timestamp: str = ""
    cycle_num: int = 0
    login_ok: bool = False
    login_error: str = ""

    # Lane 1: Observe — what we see
    profile: ProfileSnapshot = field(default_factory=ProfileSnapshot)
    leads: List[LeadRecord] = field(default_factory=list)
    mailbox_raw: List[Dict] = field(default_factory=list)

    # Lane 2: Qualify — classification results
    metrics: RevenueMetrics = field(default_factory=RevenueMetrics)

    # Lane 3: Draft — AI-drafted replies
    drafts: List[DraftReply] = field(default_factory=list)

    # Lane 4: Approve/Send — what was approved and sent
    drafts_sent: List[DraftReply] = field(default_factory=list)

    # Lane 5: Outcome — booking tracking
    bookings: List[BookingRecord] = field(default_factory=list)

    # Lane 6: Learn — what actions led to revenue
    attribution: Dict[str, float] = field(default_factory=dict)
    learnings: List[str] = field(default_factory=list)

    # Receipt
    receipt_hash: str = ""
    status: str = "GREEN"  # GREEN / YELLOW / RED

    # Raw API (never committed)
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
            f"BookingIR — {self.timestamp}",
            f"Status: {self.status}",
            f"Login: {'OK' if self.login_ok else 'FAILED'}",
            f"",
            f"Revenue Metrics:",
            f"  Qualified leads: {m.qualified_leads}/{m.total_leads}",
            f"  Reply rate: {m.reply_rate}%",
            f"  Booking request rate: {m.booking_request_rate}%",
            f"  Booking confirm rate: {m.booking_confirm_rate}%",
            f"  Show rate: {m.show_rate}%",
            f"  Collected revenue: ${m.collected_revenue}",
            f"  Avg booking value: ${m.average_booking_value}",
            f"  Repeat rate: {m.repeat_rate}%",
            f"  Compliance incidents: {m.compliance_incidents}",
            f"",
            f"Drafts: {m.drafts_pending} pending, {m.drafts_approved} approved, {m.drafts_sent} sent",
            f"",
            f"Secondary (upstream):",
            f"  Views: {m.total_views} (CTR: {m.ctr}%)",
            f"  Search rank: #{m.search_rank}",
            f"  Availability: {self.profile.availability_label}",
            f"",
            f"Leads: {len(self.leads)} total",
            f"Bookings tracked: {len(self.bookings)}",
            f"Learnings: {len(self.learnings)}",
            f"",
            f"Receipt: {self.receipt_hash}",
        ]
        return "\n".join(lines)
