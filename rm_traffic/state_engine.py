"""
Traffic State Engine — reads live RM metrics from verified endpoints and
turns raw API responses into a canonical TrafficState object.

Verified endpoints (2026-07-09):
  GET /account/dashboard              → profileStatistics, userSetting, isAdHidden
  GET /account/dashboard/availability → selected, list, countdown
  GET /account/dashboard/ad-statistics→ profileStatistics.totalPageViews, totalContactClicks, visits
  GET /account/keeponline             → newEmails, newVisits, isAdHidden, issues
  GET /settings/about                 → userProps.assets.headline, userProps.information
  GET /mailbox                        → emails[] with userCard.username, lastMessage, createdAt
  POST /search                        → users[], pagination, search rank

Dead endpoints (removed):
  GET /settings/interview → 404
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

log = logging.getLogger("state_engine")


@dataclass
class TrafficState:
    """Canonical state object — what the account looks like right now."""
    # Identity
    tenant_id: str = ""
    timestamp: str = ""

    # Traffic metrics
    views: int = 0
    contact_clicks: int = 0
    contact_rate: float = 0.0  # contact_clicks / views * 100
    emails: int = 0
    new_visits: int = 0
    new_emails: int = 0

    # Availability
    available_status: str = ""  # "Available", "Not Set", "Not Available"
    availability_countdown: int = 0  # epoch seconds when availability expires
    availability_seconds_left: float = 0.0

    # Profile
    profile_hidden: bool = False
    headline: str = ""
    search_rank: int = 0
    search_total: int = 0

    # Mailbox
    mailbox_count: int = 0
    mailbox_intent_score: float = 0.0  # 0-1, how booking-ready are the messages
    mailbox_leads: List[Dict] = field(default_factory=list)

    # Derived pressure
    revenue_pressure: float = 0.0
    pressure_components: Dict[str, float] = field(default_factory=dict)

    # Endpoint health (for measurement validity)
    endpoint_errors: List[str] = field(default_factory=list)
    endpoint_error_count: int = 0
    measurement_valid: bool = True

    # State hash (for receipt comparison)
    state_hash: str = ""

    # Raw (for debugging, not persisted in receipts)
    _raw: Dict[str, Any] = field(default_factory=dict)

    def compute_hash(self) -> str:
        d = {k: v for k, v in asdict(self).items() if k not in ("_raw", "mailbox_leads", "pressure_components", "endpoint_errors")}
        self.state_hash = hashlib.sha256(
            json.dumps(d, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        return self.state_hash

    def to_dict(self) -> Dict:
        return asdict(self)


def collect_state(api, tenant_id: str = "") -> TrafficState:
    """Read all verified endpoints and build a TrafficState."""
    state = TrafficState(tenant_id=tenant_id, timestamp=datetime.now(timezone.utc).isoformat())

    # 1. Dashboard — visibility + profile stats
    try:
        dash = api.get_dashboard()
        state._raw["dashboard"] = dash
        ps = dash.get("profileStatistics") or {}
        state.views = int(ps.get("totalPageViews", 0))
        state.contact_clicks = int(ps.get("totalContactClicks", 0))
        if state.views > 0:
            state.contact_rate = round(state.contact_clicks / state.views * 100, 2)
        state.profile_hidden = dash.get("isAdHidden", False)
        log.info(f"  ◉ Dashboard: views={state.views} contacts={state.contact_clicks} CTR={state.contact_rate}%")
    except Exception as e:
        err = str(e)
        state.endpoint_errors.append(f"dashboard:{err[:60]}")
        log.warning(f"  ⟁ dashboard error: {e}")

    # 2. Ad statistics — same profileStatistics but with visits breakdown
    try:
        stats = api.get_ad_statistics()
        state._raw["ad_statistics"] = stats
        ps = stats.get("profileStatistics", {})
        if not state.views:
            state.views = int(ps.get("totalPageViews", 0))
        if not state.contact_clicks:
            state.contact_clicks = int(ps.get("totalContactClicks", 0))
            if state.views > 0:
                state.contact_rate = round(state.contact_clicks / state.views * 100, 2)
    except Exception as e:
        err = str(e)
        state.endpoint_errors.append(f"ad_statistics:{err[:60]}")
        log.warning(f"  ⟁ ad_statistics error: {e}")

    # 3. KeepOnline — new emails, new visits, frozen status
    try:
        keep = api.get_keeponline()
        state._raw["keeponline"] = keep
        state.new_emails = int(keep.get("newEmails", 0))
        state.new_visits = int(keep.get("newVisits", 0))
        state.profile_hidden = state.profile_hidden or keep.get("isAdHidden", False)
        log.info(f"  ◉ KeepOnline: new_emails={state.new_emails} new_visits={state.new_visits}")
    except Exception as e:
        err = str(e)
        state.endpoint_errors.append(f"keeponline:{err[:60]}")
        log.warning(f"  ⟁ keeponline error: {e}")

    # 4. Availability — selected label + countdown
    try:
        avail = api.get_availability()
        state._raw["availability"] = avail
        state.available_status = avail.get("selected", "Unknown")
        countdown = avail.get("countdown", 0)
        state.availability_countdown = int(countdown) if countdown else 0
        if state.availability_countdown:
            state.availability_seconds_left = max(0, state.availability_countdown - time.time())
        log.info(f"  ◉ Availability: {state.available_status} ({state.availability_seconds_left:.0f}s left)")
    except Exception as e:
        err = str(e)
        state.endpoint_errors.append(f"availability:{err[:60]}")
        log.warning(f"  ⟁ availability error: {e}")

    # 5. About — headline
    try:
        about = api.get_about()
        state._raw["about"] = about
        props = about.get("userProps", {})
        assets = props.get("assets", {})
        state.headline = assets.get("headline", "")
        log.info(f"  ◉ Headline: '{state.headline}'")
    except Exception as e:
        err = str(e)
        state.endpoint_errors.append(f"about:{err[:60]}")
        log.warning(f"  ⟁ about error: {e}")

    # 6. Mailbox — leads
    try:
        mailbox = api.get_mailbox(page=1, folder=1, sort=1)
        state._raw["mailbox"] = mailbox
        emails = mailbox.get("emails", [])
        state.mailbox_count = len(emails)
        state.emails = state.mailbox_count

        # Score mailbox intent
        booking_kw = ["book", "available", "today", "tonight", "tomorrow", "session", "time", "schedule"]
        price_kw = ["price", "rate", "cost", "how much"]
        intent_scores = []
        for email in emails:
            msg = (email.get("lastMessage", "") or "").lower()
            score = 0.0
            if any(kw in msg for kw in booking_kw):
                score += 0.5
            if any(kw in msg for kw in price_kw):
                score += 0.3
            if msg.strip():
                score += 0.2
            intent_scores.append(min(1.0, score))

        state.mailbox_intent_score = round(
            sum(intent_scores) / len(intent_scores), 2
        ) if intent_scores else 0.0

        # Store lead summaries (no raw PII in state)
        for email in emails:
            uc = email.get("userCard", {})
            state.mailbox_leads.append({
                "username": uc.get("username", ""),
                "is_premium": bool(uc.get("isPremium", 0)),
                "unread": bool(email.get("unread", 0)),
                "created_at": email.get("createdAt", 0),
                "intent_score": min(1.0, (
                    0.5 if any(kw in (email.get("lastMessage", "") or "").lower() for kw in booking_kw) else 0.0
                ) + (0.3 if any(kw in (email.get("lastMessage", "") or "").lower() for kw in price_kw) else 0.0)
                + (0.2 if (email.get("lastMessage", "") or "").strip() else 0.0)),
            })

        log.info(f"  ◉ Mailbox: {state.mailbox_count} conversations, intent={state.mailbox_intent_score}")
    except Exception as e:
        err = str(e)
        state.endpoint_errors.append(f"mailbox:{err[:60]}")
        log.warning(f"  ⟁ mailbox error: {e}")

    # 7. Search rank (optional — can be slow)
    try:
        results = api.search_masseurs(city="manhattan-ny", page=1)
        users = results.get("users", [])
        state.search_total = len(users)
        # Find our position
        my_username = ""
        try:
            my_username = api.session.headers.get("X-RM-Username", "")
        except Exception:
            pass
        for i, user in enumerate(users):
            if user.get("username") == my_username:
                state.search_rank = i + 1
                break
        log.info(f"  ◉ Search: rank=#{state.search_rank} of {state.search_total}")
    except Exception as e:
        err = str(e)
        state.endpoint_errors.append(f"search:{err[:60]}")
        log.warning(f"  ⟁ search error: {e}")

    # Determine measurement validity — 3+ endpoint errors = invalid
    state.endpoint_error_count = len(state.endpoint_errors)
    critical_endpoints = {"dashboard", "ad_statistics", "keeponline", "availability", "mailbox"}
    critical_failures = sum(1 for e in state.endpoint_errors if any(c in e for c in critical_endpoints))
    if critical_failures >= 3:
        state.measurement_valid = False
        log.warning(f"  ⟁ MEASUREMENT INVALID: {critical_failures} critical endpoint failures")

    # Compute revenue pressure
    compute_revenue_pressure(state)

    # Compute state hash
    state.compute_hash()

    return state


def compute_revenue_pressure(state: TrafficState) -> None:
    """
    Revenue Pressure Engine — scores how urgently the account needs action.

    revenue_pressure =
      0.30 * contact_rate_gap      (low CTR = high pressure to fix profile)
    + 0.20 * availability_risk     (not available = high pressure)
    + 0.20 * rank_decay            (low rank = high pressure)
    + 0.15 * unanswered_intent     (mailbox with intent but no replies)
    + 0.10 * profile_fatigue       (hidden or stale)
    + 0.05 * traffic_drop          (low views)
    """
    # Contact rate gap: target 5%, below that = pressure
    contact_rate_gap = max(0, (5.0 - state.contact_rate) / 5.0) if state.views > 0 else 0.5

    # Availability risk: not available = 1.0, available with <1h left = 0.5
    if state.available_status != "Available":
        availability_risk = 1.0
    elif state.availability_seconds_left < 3600:
        availability_risk = 0.5
    else:
        availability_risk = 0.0

    # Rank decay: rank > 20 = high pressure, rank 1-5 = low
    if state.search_rank == 0:
        rank_decay = 0.3  # unknown
    elif state.search_rank > 20:
        rank_decay = 0.8
    elif state.search_rank > 10:
        rank_decay = 0.5
    else:
        rank_decay = 0.1

    # Unanswered intent: mailbox with high intent but no recent replies
    unanswered = state.mailbox_intent_score if state.mailbox_count > 0 else 0.0

    # Profile fatigue: hidden or no headline
    profile_fatigue = 0.0
    if state.profile_hidden:
        profile_fatigue += 0.5
    if not state.headline:
        profile_fatigue += 0.3

    # Traffic drop: very low views
    traffic_drop = 0.3 if state.views < 100 else 0.0

    state.pressure_components = {
        "contact_rate_gap": round(contact_rate_gap, 3),
        "availability_risk": round(availability_risk, 3),
        "rank_decay": round(rank_decay, 3),
        "unanswered_intent": round(unanswered, 3),
        "profile_fatigue": round(profile_fatigue, 3),
        "traffic_drop": round(traffic_drop, 3),
    }

    state.revenue_pressure = round(
        0.30 * contact_rate_gap
        + 0.20 * availability_risk
        + 0.20 * rank_decay
        + 0.15 * unanswered
        + 0.10 * profile_fatigue
        + 0.05 * traffic_drop,
        3
    )
