#!/usr/bin/env python3
"""
RevenueIR — Canonical business state object for the RentMasseur revenue optimizer.

Every pass reads and writes this object. No more loose dictionaries.

Flow:
  raw_api → RevenueIR → scoring passes → action planner → policy gate → executor → after_snapshot → receipt
"""

import json
import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any


@dataclass
class FunnelMetrics:
    total_views: int = 0
    total_contacts: int = 0
    today_views: int = 0
    emails_count: int = 0
    unread_emails: int = 0
    premium_senders: int = 0
    booking_inquiries: int = 0
    general_inquiries: int = 0
    ctr: float = 0.0
    email_rate: float = 0.0
    avg_rate: float = 0.0

    def compute(self):
        if self.total_views > 0:
            self.ctr = round(self.total_contacts / self.total_views * 100, 2)
        if self.total_contacts > 0:
            self.email_rate = round(self.emails_count / self.total_contacts * 100, 2)


@dataclass
class ProfileState:
    headline: str = ""
    description_len: int = 0
    availability_option: int = 0
    availability_label: str = ""
    is_visible: bool = True
    search_rank: int = 0
    search_total: int = 0
    active_rates: List[Dict] = field(default_factory=list)


@dataclass
class VisitorRecord:
    username: str = ""
    source: str = "who_saw_me"
    location: str = ""
    is_ny: bool = False
    is_masseur: Optional[bool] = None
    visited_back: bool = False
    messaged: bool = False
    is_premium: bool = False
    email_classification: str = ""


@dataclass
class ActionItem:
    action: str = ""
    reason: str = ""
    priority: int = 0
    policy: str = "AUTO_OK"  # AUTO_OK, REVIEW_REQUIRED, BLOCKED
    executed: bool = False
    result: str = ""
    impact: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RevenueIR:
    """The canonical business state object. Every pass reads/writes this."""
    timestamp: str = ""
    cycle_num: int = 0
    login_ok: bool = False
    login_error: str = ""

    # Lane 1: Read-only scan results
    funnel: FunnelMetrics = field(default_factory=FunnelMetrics)
    profile: ProfileState = field(default_factory=ProfileState)
    visitors: List[VisitorRecord] = field(default_factory=list)
    mailbox_preview: List[Dict] = field(default_factory=list)

    # Lane 2: Safe actions executed
    actions_executed: List[ActionItem] = field(default_factory=list)

    # Lane 3: Risky actions queued for approval
    actions_queued: List[ActionItem] = field(default_factory=list)

    # Deltas vs last cycle
    deltas: Dict[str, float] = field(default_factory=dict)

    # Receipt
    receipt_hash: str = ""
    status: str = "GREEN"  # GREEN, YELLOW, RED

    # Raw API responses kept for debugging (not committed to repo)
    _raw: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

    def compute_receipt(self):
        """Tamper-evident receipt hash over the entire state."""
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
        lines = [
            f"RevenueIR — {self.timestamp}",
            f"Status: {self.status}",
            f"Login: {'OK' if self.login_ok else 'FAILED'}",
            f"",
            f"Funnel:",
            f"  Views: {self.funnel.total_views} (today: {self.funnel.today_views})",
            f"  Contacts: {self.funnel.total_contacts} (CTR: {self.funnel.ctr}%)",
            f"  Emails: {self.funnel.emails_count} (unread: {self.funnel.unread_emails}, premium: {self.funnel.premium_senders})",
            f"  Booking inquiries: {self.funnel.booking_inquiries}",
            f"  Avg rate: ${self.funnel.avg_rate}",
            f"",
            f"Profile:",
            f"  Headline: '{self.profile.headline}'",
            f"  Availability: {self.profile.availability_label} ({self.profile.availability_option})",
            f"  Visible: {self.profile.is_visible}",
            f"  Search rank: #{self.profile.search_rank} of {self.profile.search_total}",
            f"  Active rates: {len(self.profile.active_rates)}",
            f"",
            f"Visitors: {len(self.visitors)} total, {sum(1 for v in self.visitors if v.is_ny)} NYC",
            f"Actions executed: {len(self.actions_executed)}",
            f"Actions queued: {len(self.actions_queued)}",
            f"",
            f"Receipt: {self.receipt_hash}",
        ]
        return "\n".join(lines)
