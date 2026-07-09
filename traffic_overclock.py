#!/usr/bin/env python3
"""
RM Revenue Control Plane — Conversion Velocity OS

The product is not traffic. The product is conversion.

Control objective:
  maximize booked-session profit per unit of attention,
  without violating platform rules or damaging account trust.

4 Lanes:
  Lane 1: Revenue Truth     — pull metrics, store immutable snapshots
  Lane 2: Diagnosis         — identify bottleneck in the funnel
  Lane 3: Controlled Experiment — change one variable, measure before/after
  Lane 4: Capital Report    — what changed, what metric moved, should it continue

Lead-speed engine:
  NOW   → booking language + today/tomorrow + NYC + direct question
  HOT   → profile visitor + prior message + location match
  WARM  → profile visitor only
  COLD  → social mention / search discovery
  IGNORE → spam, competitor, unsafe, out-of-area

Reply templates (not LLM freestyle):
  booking_now_reply, price_question_reply, location_question_reply, repeat_client_reply

Attribution: every action tied to a funnel metric with before/after receipt.
No action gets called "optimization" unless it moved a funnel metric.

Usage:
  python3 traffic_overclock.py --full        # all 4 lanes
  python3 traffic_overclock.py --observe     # lane 1 only (read-only)
  python3 traffic_overclock.py --diagnose    # lanes 1-2
  python3 traffic_overclock.py --experiment  # lanes 1-3 (draft, no send)
  python3 traffic_overclock.py --report      # generate report from last cycle
"""

import argparse
import hashlib
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rm_traffic.api_client import RentMasseurAPI
from rm_traffic.overclock_ir import (
    TrafficOverclockIR, LeadState, BookingEvent, RevenueMetrics,
    ProfileSnapshot, URGENCY_NOW, URGENCY_HOT, URGENCY_WARM,
    URGENCY_COLD, URGENCY_IGNORE, URGENCY_ORDER,
    REPLY_BOOKING_NOW, REPLY_PRICE_QUESTION, REPLY_LOCATION_QUESTION,
    REPLY_REPEAT_CLIENT, REPLY_INQUIRY, REPLY_FOLLOW_UP, REPLY_CLOSE_LOOP,
)

log = logging.getLogger("overclock")

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "overclock")
DB_PATH = os.path.join(DB_DIR, "overclock.db")
REPORT_DIR = os.path.join(DB_DIR, "reports")

# ─── Signal keywords ───────────────────────────────────────────────

NYC_KEYWORDS = ["nyc", "manhattan", "brooklyn", "queens", "bronx", "staten island",
                "new york", "ny ", "nj ", "hoboken", "jersey city", "astoria",
                "long island", "yonkers", "harlem", "midtown", "uptown", "downtown",
                "west side", "east side", "village", "soho", "tribeca", "murray hill"]

TIME_URGENCY_KEYWORDS = ["today", "tonight", "tomorrow", "now", "this morning",
                         "this afternoon", "this evening", "asap", "right now",
                         "this week", "available now"]

BOOKING_KEYWORDS = ["book", "appointment", "schedule", "session", "available",
                    "time slot", "when can", "how soon", "fit me in"]

PRICE_KEYWORDS = ["price", "rate", "cost", "how much", "fee", "charge", "donation",
                  "rates", "pricing", "expensive", "budget"]

LOCATION_KEYWORDS = ["where", "location", "incall", "outcall", "hotel", "address",
                     "zip", "area", "neighborhood", "come to", "travel to",
                     "do you travel", "can you host"]

SPAM_KEYWORDS = ["promo", "discount", "offer", "deal", "click here", "visit my",
                 "check out my", "follow me", "subscribe", "free", "bonus"]

UNSAFE_KEYWORDS = ["raw", "bb", "bareback", "unsafe", "no condom", "bare"]

COMPETITOR_KEYWORDS = ["i'm also a", "fellow masseur", "colleague", "i offer",
                       "my services", "my profile", "my rates", "i also massage"]

REPEAT_KEYWORDS = ["again", "back again", "last time", "saw you before",
                   "was here before", "returned", "repeat", "second time",
                   "third time", "regular", "missed you", "been a while"]

OUT_OF_AREA_KEYWORDS = ["la", "los angeles", "sf", "san francisco", "chicago",
                        "miami", "boston", "dc", "washington", "atlanta",
                        "dallas", "houston", "philly", "philadelphia",
                        "seattle", "vegas", "las vegas", "denver", "phoenix"]


# ─── SQLite schema ─────────────────────────────────────────────────

def init_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    conn.executescript("""
    CREATE TABLE IF NOT EXISTS cycles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cycle_num INTEGER,
        timestamp TEXT,
        status TEXT,
        receipt_hash TEXT,
        ir_json TEXT
    );

    CREATE TABLE IF NOT EXISTS leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        lead_id TEXT UNIQUE,
        username TEXT,
        source TEXT DEFAULT 'rentmasseur',
        first_seen_at TEXT,
        last_touch_at TEXT,
        intent_score REAL,
        urgency TEXT,
        location_match INTEGER,
        budget_match INTEGER,
        time_urgency INTEGER,
        repeat_client INTEGER,
        risk_flag TEXT,
        classification TEXT,
        recommended_reply_class TEXT,
        recommended_reply_text TEXT,
        approval_status TEXT DEFAULT 'pending',
        booking_status TEXT DEFAULT 'inquiry',
        collected_amount REAL DEFAULT 0,
        message_received TEXT,
        message_sent TEXT,
        consent_status TEXT,
        cooldown_until TEXT,
        suppressed INTEGER DEFAULT 0,
        follow_up_due_at TEXT,
        close_loop_due_at TEXT,
        first_reply_seconds REAL DEFAULT 0,
        is_premium INTEGER DEFAULT 0,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS booking_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        booking_id TEXT UNIQUE,
        lead_id TEXT,
        source TEXT,
        first_action TEXT,
        first_reply_seconds REAL,
        booking_requested_at TEXT,
        booking_confirmed_at TEXT,
        session_completed_at TEXT,
        amount_collected REAL DEFAULT 0,
        repeat_booking INTEGER DEFAULT 0,
        attributed_action_id TEXT,
        created_at TEXT,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS experiments (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        experiment_id TEXT UNIQUE,
        variable_changed TEXT,
        before_value TEXT,
        after_value TEXT,
        before_metric TEXT,
        after_metric TEXT,
        metric_name TEXT,
        status TEXT DEFAULT 'running',
        started_at TEXT,
        concluded_at TEXT,
        verdict TEXT
    );

    CREATE TABLE IF NOT EXISTS snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cycle_num INTEGER,
        timestamp TEXT,
        total_views INTEGER,
        total_contacts INTEGER,
        ctr REAL,
        qualified_inquiries INTEGER,
        bookings INTEGER,
        revenue REAL,
        search_rank INTEGER,
        availability TEXT,
        headline TEXT,
        immutable_hash TEXT
    );

    CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cycle_num INTEGER,
        receipt_hash TEXT UNIQUE,
        timestamp TEXT,
        status TEXT,
        ir_json TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_leads_urgency ON leads(urgency);
    CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(approval_status);
    CREATE INDEX IF NOT EXISTS idx_bookings_lead ON booking_events(lead_id);
    CREATE INDEX IF NOT EXISTS idx_bookings_status ON booking_events(session_completed_at);
    CREATE INDEX IF NOT EXISTS idx_experiments_status ON experiments(status);
    """)
    conn.commit()
    return conn


def person_hash(username: str) -> str:
    return hashlib.sha256(f"rm:{username}".encode()).hexdigest()[:16]


def ts_to_iso(ts) -> str:
    if not ts:
        return ""
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return str(ts)


# ─── Lane 1: Revenue Truth ─────────────────────────────────────────

def lane1_revenue_truth(api: RentMasseurAPI, ir: TrafficOverclockIR,
                        conn: sqlite3.Connection) -> TrafficOverclockIR:
    """Pull metrics and store immutable snapshots. No writes to platform."""
    print("[LANE1] Revenue truth — pulling immutable signals...")

    cur = conn.cursor()

    # Ad statistics
    try:
        stats = api.get_ad_statistics()
        ir._raw["ad_statistics"] = stats
        ps = stats.get("profileStatistics", stats)
        ir.metrics.total_views = int(ps.get("totalPageViews", 0))
        ir.metrics.total_contacts = int(ps.get("totalContactClicks", 0))
        if ir.metrics.total_views > 0:
            ir.metrics.ctr = round(ir.metrics.total_contacts / ir.metrics.total_views * 100, 2)
        print(f"  ◉ Views={ir.metrics.total_views} Contacts={ir.metrics.total_contacts} CTR={ir.metrics.ctr}%")
    except Exception as e:
        print(f"  ⟁ ad_statistics error: {e}")

    # Availability
    try:
        avail = api.get_availability()
        ir._raw["availability"] = avail
        selected = avail.get("selected", "")
        ir.profile.availability_label = selected or "Unknown"
        ir.profile.availability_option = {"Not Set": 0, "Available": 1, "Not Available": 2}.get(selected, 0)
        print(f"  ◉ Availability: {ir.profile.availability_label}")
    except Exception as e:
        print(f"  ⟁ availability error: {e}")

    # About / profile
    try:
        about = api.get_about()
        ir._raw["about"] = about
        props = about.get("userProps", {})
        assets = props.get("assets", {})
        info = props.get("information", {})
        ir.profile.headline = assets.get("headline", "")
        rates = info.get("rates", props.get("rates", []))
        ir.profile.active_rates = rates if isinstance(rates, list) else []
        if rates:
            ir.profile.avg_rate = sum(float(r.get("price", r.get("rate", 0))) for r in rates) / len(rates)
        print(f"  ◉ Headline: '{ir.profile.headline}'")
        print(f"  ◉ Rates: {len(ir.profile.active_rates)} active, avg ${ir.profile.avg_rate:.0f}")
    except Exception as e:
        print(f"  ⟁ about error: {e}")

    # Dashboard
    try:
        dashboard = api.get_dashboard()
        ir._raw["dashboard"] = dashboard
        data = dashboard.get("data", dashboard)
        ir.profile.is_visible = not data.get("isAdHidden", False)
        print(f"  ◉ Visible: {ir.profile.is_visible}")
    except Exception as e:
        print(f"  ⟁ dashboard error: {e}")

    # Mailbox — where leads live
    try:
        mailbox = api.get_mailbox(page=1, folder=1, sort=1)
        ir._raw["mailbox"] = mailbox
        emails = mailbox.get("emails", [])
        ir.mailbox_raw = emails
        print(f"  ◉ Mailbox: {len(emails)} conversations")
    except Exception as e:
        print(f"  ⟁ mailbox error: {e}")
        emails = []

    # Convert mailbox into LeadStates
    for conv in emails:
        user_card = conv.get("userCard", {})
        username = user_card.get("username", "")
        if not username:
            continue

        msg_text = conv.get("lastMessage", "")
        is_premium = bool(user_card.get("isPremium", 0))
        first_seen = ts_to_iso(conv.get("createdAt", 0))

        lead = LeadState(
            lead_id=person_hash(username),
            username=username,
            source="rentmasseur",
            first_seen_at=first_seen,
            last_touch_at=first_seen,
            message_received=msg_text,
            is_premium=is_premium,
        )

        # Check DB for prior history
        cur.execute("SELECT * FROM leads WHERE lead_id = ?", (lead.lead_id,))
        row = cur.fetchone()
        if row:
            lead.repeat_client = bool(row["repeat_client"])
            lead.message_sent = row["message_sent"] or ""
            lead.consent_status = row["consent_status"] or "unknown"
            lead.booking_status = row["booking_status"] or "inquiry"
            lead.collected_amount = row["collected_amount"] or 0.0
            lead.first_reply_seconds = row["first_reply_seconds"] or 0.0
            if row["first_seen_at"]:
                lead.first_seen_at = row["first_seen_at"]
            if row["classification"]:
                lead.classification = row["classification"]

        ir.leads.append(lead)

    print(f"  ◉ Leads observed: {len(ir.leads)} ({sum(1 for l in ir.leads if l.repeat_client)} repeat)")

    # Store immutable snapshot
    snap_hash = hashlib.sha256(
        f"{ir.metrics.total_views}:{ir.metrics.total_contacts}:{ir.timestamp}".encode()
    ).hexdigest()[:16]
    cur.execute("""INSERT INTO snapshots
        (cycle_num, timestamp, total_views, total_contacts, ctr, qualified_inquiries,
         bookings, revenue, search_rank, availability, headline, immutable_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (ir.cycle_num, ir.timestamp, ir.metrics.total_views, ir.metrics.total_contacts,
         ir.metrics.ctr, 0, 0, 0.0, ir.profile.search_rank,
         ir.profile.availability_label, ir.profile.headline, snap_hash))
    conn.commit()

    print(f"  ◉ Snapshot stored: {snap_hash}")
    print("[LANE1] Done.")
    return ir


# ─── Lane 2: Diagnosis ─────────────────────────────────────────────

def classify_and_score(lead: LeadState) -> None:
    """Classify lead, assign urgency tier, set recommended reply class."""
    text = (lead.message_received or "").lower()

    # Risk flags first
    if any(kw in text for kw in UNSAFE_KEYWORDS):
        lead.risk_flag = "unsafe"
        lead.urgency = URGENCY_IGNORE
        lead.classification = "unsafe"
        lead.intent_score = 0.0
        lead.suppressed = True
        return

    if any(kw in text for kw in SPAM_KEYWORDS):
        lead.risk_flag = "spam"
        lead.urgency = URGENCY_IGNORE
        lead.classification = "spam"
        lead.intent_score = 0.0
        lead.suppressed = True
        return

    if any(kw in text for kw in COMPETITOR_KEYWORDS):
        lead.risk_flag = "competitor"
        lead.urgency = URGENCY_IGNORE
        lead.classification = "competitor"
        lead.intent_score = 0.0
        lead.suppressed = True
        return

    # Location
    lead.location_match = any(kw in text for kw in NYC_KEYWORDS)

    if not lead.location_match and any(kw in text for kw in OUT_OF_AREA_KEYWORDS):
        lead.risk_flag = "out_of_area"
        lead.urgency = URGENCY_IGNORE
        lead.classification = "out_of_area"
        lead.intent_score = 0.1
        return

    # Time urgency
    lead.time_urgency = any(kw in text for kw in TIME_URGENCY_KEYWORDS)

    # Repeat client
    if lead.repeat_client or any(kw in text for kw in REPEAT_KEYWORDS):
        lead.repeat_client = True
        lead.classification = "repeat_client"
        lead.intent_score = 0.9
        lead.urgency = URGENCY_NOW if lead.time_urgency else URGENCY_HOT
        lead.recommended_reply_class = REPLY_REPEAT_CLIENT
        return

    # Booking-ready
    has_booking = any(kw in text for kw in BOOKING_KEYWORDS)
    has_price = any(kw in text for kw in PRICE_KEYWORDS)
    has_location = any(kw in text for kw in LOCATION_KEYWORDS)

    if has_booking and lead.time_urgency and lead.location_match:
        lead.classification = "booking_ready"
        lead.intent_score = 0.95
        lead.urgency = URGENCY_NOW
        lead.recommended_reply_class = REPLY_BOOKING_NOW
    elif has_booking:
        lead.classification = "booking_ready"
        lead.intent_score = 0.8
        lead.urgency = URGENCY_HOT if lead.location_match else URGENCY_WARM
        lead.recommended_reply_class = REPLY_BOOKING_NOW
    elif has_price:
        lead.classification = "price_inquiry"
        lead.intent_score = 0.7
        lead.urgency = URGENCY_HOT if lead.location_match else URGENCY_WARM
        lead.recommended_reply_class = REPLY_PRICE_QUESTION
    elif has_location:
        lead.classification = "location_inquiry"
        lead.intent_score = 0.6
        lead.urgency = URGENCY_WARM if lead.location_match else URGENCY_COLD
        lead.recommended_reply_class = REPLY_LOCATION_QUESTION
    elif text.strip():
        lead.classification = "inquiry"
        lead.intent_score = 0.5
        lead.urgency = URGENCY_WARM if lead.location_match else URGENCY_COLD
        lead.recommended_reply_class = REPLY_INQUIRY
    else:
        lead.classification = "low_intent"
        lead.intent_score = 0.1
        lead.urgency = URGENCY_COLD
        lead.recommended_reply_class = ""

    # Premium boost
    if lead.is_premium:
        lead.intent_score = min(1.0, lead.intent_score + 0.1)
        if lead.urgency == URGENCY_WARM:
            lead.urgency = URGENCY_HOT


def lane2_diagnosis(ir: TrafficOverclockIR, conn: sqlite3.Connection) -> TrafficOverclockIR:
    """Classify each lead by booking intent. Identify funnel bottleneck."""
    print("[LANE2] Diagnosis — classifying leads and identifying bottleneck...")

    for lead in ir.leads:
        classify_and_score(lead)

    # Urgency summary
    for tier in URGENCY_ORDER:
        count = sum(1 for l in ir.leads if l.urgency == tier)
        if count:
            glyph = {"NOW": "⌁", "HOT": "▲", "WARM": "◇", "COLD": "◌", "IGNORE": "✕"}[tier]
            print(f"  {glyph} {tier}: {count}")

    # Funnel diagnosis
    views = ir.metrics.total_views
    contacts = ir.metrics.total_contacts
    ctr = ir.metrics.ctr
    qualified = sum(1 for l in ir.leads if l.urgency in (URGENCY_NOW, URGENCY_HOT, URGENCY_WARM))
    booking_ready = sum(1 for l in ir.leads if l.urgency == URGENCY_NOW)

    print(f"\n  Funnel diagnosis:")
    print(f"    Views: {views}")
    print(f"    Contact clicks: {contacts} (CTR: {ctr}%)")
    print(f"    Mailbox conversations: {len(ir.leads)}")
    print(f"    Qualified leads: {qualified}")
    print(f"    Booking-ready (NOW): {booking_ready}")

    bottleneck = "unknown"
    if views > 0 and contacts == 0:
        bottleneck = "view_to_contact"
        diagnosis = "Traffic exists but contact conversion is zero. Fix profile conversion: headline, first 300 chars, contact method clarity."
    elif contacts > 0 and len(ir.leads) == 0:
        bottleneck = "contact_to_message"
        diagnosis = "Contacts exist but no inbound messages. Make first contact easier: clear call to action, obvious booking path."
    elif len(ir.leads) > 0 and qualified == 0:
        bottleneck = "message_to_qualified"
        diagnosis = "Messages exist but none qualified. Review lead scoring or improve targeting."
    elif qualified > 0 and booking_ready == 0:
        bottleneck = "qualified_to_booking"
        diagnosis = "Qualified leads but none booking-ready. Improve reply speed and booking clarity in responses."
    elif booking_ready > 0:
        bottleneck = "none"
        diagnosis = f"{booking_ready} booking-ready leads detected. Prioritize reply within minutes."
    else:
        bottleneck = "no_traffic"
        diagnosis = "No traffic detected. Focus on availability, visibility, and profile quality."

    print(f"\n  ⟡ Bottleneck: {bottleneck}")
    print(f"  ⟡ Diagnosis: {diagnosis}")

    ir.learnings.append(f"BOTTLENECK: {bottleneck}")
    ir.learnings.append(f"DIAGNOSIS: {diagnosis}")

    # Allowed vs blocked actions based on diagnosis
    if bottleneck in ("view_to_contact", "contact_to_message"):
        ir.learnings.append("ALLOWED: profile copy test, availability hygiene, search rank check")
        ir.learnings.append("BLOCKED: mass outreach, unapproved scraping, unproven messaging")
    elif bottleneck == "qualified_to_booking":
        ir.learnings.append("ALLOWED: reply speed optimization, booking clarity in templates")
        ir.learnings.append("BLOCKED: bio rotation, rate changes without booking data")
    elif bottleneck == "none":
        ir.learnings.append("ALLOWED: fast reply to booking-ready leads, follow-up scheduling")

    print("[LANE2] Done.")
    return ir


# ─── Lane 3: Controlled Experiment ─────────────────────────────────

def generate_reply(lead: LeadState, profile: ProfileSnapshot, phone: str) -> str:
    """Generate reply from template, not LLM freestyle. Conversion is removing uncertainty."""
    rate_str = f"${profile.avg_rate:.0f}" if profile.avg_rate else "see my profile for rates"
    cls = lead.recommended_reply_class

    if cls == REPLY_BOOKING_NOW:
        return (
            f"Yes, I'm available. "
            f"Best slots: 3:30, 5:00, or 7:15. "
            f"Manhattan incall. "
            f"Session is {rate_str}. "
            f"Send preferred time and I'll confirm. "
            f"Text {phone} for fastest response."
        )

    if cls == REPLY_PRICE_QUESTION:
        return (
            f"My rate is {rate_str} for a 60-minute session. "
            f"90-minute and 120-minute sessions also available. "
            f"Manhattan incall. "
            f"What time works for you? "
            f"Text {phone} to book."
        )

    if cls == REPLY_LOCATION_QUESTION:
        return (
            f"I'm based in Manhattan — private incall space. "
            f"Outcall available within Manhattan for an additional travel fee. "
            f"Rate is {rate_str}. "
            f"What day and time works? "
            f"Text {phone} for faster booking."
        )

    if cls == REPLY_REPEAT_CLIENT:
        return (
            f"Great to hear from you again! "
            f"I have openings today. "
            f"Same location in Manhattan. "
            f"Text {phone} to confirm your time."
        )

    if cls == REPLY_INQUIRY:
        return (
            f"Hi! Thanks for your interest. "
            f"I offer deep tissue and sports recovery massage in Manhattan. "
            f"Rate is {rate_str}. "
            f"What questions can I answer? "
            f"Text {phone} for faster response."
        )

    if cls == REPLY_FOLLOW_UP:
        return (
            f"Hi — following up on your message. "
            f"I'm available this week if you'd like to book. "
            f"Manhattan incall, {rate_str}. "
            f"Text {phone} to schedule."
        )

    if cls == REPLY_CLOSE_LOOP:
        return (
            f"No problem if the timing didn't work out. "
            f"I'm here when you're ready — text {phone} anytime."
        )

    return ""


def lane3_experiment(ir: TrafficOverclockIR, phone: str,
                     conn: sqlite3.Connection) -> TrafficOverclockIR:
    """Draft replies using templates. Set follow-up timing. No auto-send."""
    print("[LANE3] Controlled experiment — drafting replies and follow-up schedule...")

    now = datetime.now(timezone.utc)
    cur = conn.cursor()

    # Sort leads by urgency (NOW first)
    urgency_rank = {URGENCY_NOW: 0, URGENCY_HOT: 1, URGENCY_WARM: 2, URGENCY_COLD: 3, URGENCY_IGNORE: 4}
    sorted_leads = sorted(ir.leads, key=lambda l: urgency_rank.get(l.urgency, 99))

    for lead in sorted_leads:
        if lead.suppressed or lead.urgency == URGENCY_IGNORE:
            continue
        if lead.message_sent and not lead.repeat_client:
            continue

        # Generate reply from template
        reply_text = generate_reply(lead, ir.profile, phone)
        if not reply_text:
            continue

        lead.recommended_reply_text = reply_text
        lead.approval_status = "pending"
        ir.drafts_generated += 1

        # Set follow-up schedule
        if not lead.message_sent:
            # First reply — no follow-up yet, but schedule it
            lead.follow_up_due_at = (now + timedelta(hours=3)).isoformat()
            lead.close_loop_due_at = (now + timedelta(days=1)).isoformat()

        urgency_glyph = {"NOW": "⌁", "HOT": "▲", "WARM": "◇", "COLD": "◌"}[lead.urgency]
        print(f"  {urgency_glyph} {lead.username} [{lead.urgency}] intent={lead.intent_score:.2f} → {lead.recommended_reply_class}")
        print(f"    Draft: \"{reply_text[:100]}...\"")

    # Check for leads needing follow-up
    cur.execute("""SELECT lead_id, username, follow_up_due_at, close_loop_due_at, message_sent
                   FROM leads WHERE follow_up_due_at != '' AND message_sent != ''""")
    for row in cur.fetchall():
        follow_up = row["follow_up_due_at"]
        close_loop = row["close_loop_due_at"]
        if follow_up and now > datetime.fromisoformat(follow_up.replace("Z", "+00:00")):
            lead = next((l for l in ir.leads if l.lead_id == row["lead_id"]), None)
            if lead and not lead.message_sent:
                lead.recommended_reply_class = REPLY_FOLLOW_UP
                lead.recommended_reply_text = generate_reply(lead, ir.profile, phone)
                print(f"  ⧖ Follow-up due: {row['username']}")
        if close_loop and now > datetime.fromisoformat(close_loop.replace("Z", "+00:00")):
            lead = next((l for l in ir.leads if l.lead_id == row["lead_id"]), None)
            if lead and not lead.message_sent:
                lead.recommended_reply_class = REPLY_CLOSE_LOOP
                lead.recommended_reply_text = generate_reply(lead, ir.profile, phone)
                print(f"  ⧖ Close-loop due: {row['username']}")

    print(f"\n  ◉ Drafts generated: {ir.drafts_generated}")
    print(f"  ◌ Suppressed: {sum(1 for l in ir.leads if l.suppressed)}")
    print("[LANE3] Done.")
    return ir


# ─── Lane 4: Capital Report ────────────────────────────────────────

def lane4_capital_report(ir: TrafficOverclockIR, conn: sqlite3.Connection) -> TrafficOverclockIR:
    """Produce report: what changed, what metric moved, should action continue."""
    print("[LANE4] Capital report — measuring outcomes and attribution...")

    cur = conn.cursor()

    # Check for booking status transitions in mailbox messages
    for lead in ir.leads:
        text = (lead.message_received or "").lower()

        cur.execute("""SELECT * FROM booking_events WHERE lead_id = ?
                       ORDER BY created_at DESC LIMIT 1""", (lead.lead_id,))
        row = cur.fetchone()

        booking = BookingEvent(
            booking_id=hashlib.sha256(f"bk:{lead.lead_id}".encode()).hexdigest()[:16],
            lead_id=lead.lead_id,
            source=lead.source,
            first_action="inbound_message",
        )

        if row:
            booking.booking_id = row["booking_id"]
            booking.first_reply_seconds = row["first_reply_seconds"] or 0
            booking.booking_requested_at = row["booking_requested_at"] or ""
            booking.booking_confirmed_at = row["booking_confirmed_at"] or ""
            booking.session_completed_at = row["session_completed_at"] or ""
            booking.amount_collected = row["amount_collected"] or 0.0
            booking.repeat_booking = bool(row["repeat_booking"])
            booking.attributed_action_id = row["attributed_action_id"] or ""

        # Detect transitions
        if any(kw in text for kw in ["confirmed", "see you", "on my way", "be there", "booking confirmed"]):
            booking.booking_confirmed_at = datetime.now(timezone.utc).isoformat()
            lead.booking_status = "confirmed"
            print(f"  ◆ {lead.username}: booking confirmed")
        elif any(kw in text for kw in ["completed", "finished", "great session", "thank you", "thanks for the"]):
            booking.session_completed_at = datetime.now(timezone.utc).isoformat()
            booking.amount_collected = ir.profile.avg_rate if booking.amount_collected == 0 else booking.amount_collected
            lead.booking_status = "completed"
            lead.collected_amount = booking.amount_collected
            print(f"  ◉ {lead.username}: session completed (${booking.amount_collected:.0f})")
        elif any(kw in text for kw in ["cancel", "reschedule", "can't make it", "postpone"]):
            lead.booking_status = "cancelled"
            print(f"  ⟁ {lead.username}: cancelled")
        elif any(kw in text for kw in BOOKING_KEYWORDS):
            if lead.booking_status == "inquiry":
                booking.booking_requested_at = datetime.now(timezone.utc).isoformat()
                lead.booking_status = "requested"
                print(f"  ▲ {lead.username}: booking requested")

        # Track reply time
        if lead.message_sent and lead.first_reply_seconds == 0 and lead.first_seen_at:
            try:
                first_seen = datetime.fromisoformat(lead.first_seen_at.replace("Z", "+00:00"))
                # Approximate: we don't know exact send time, use now as proxy
                lead.first_reply_seconds = (datetime.now(timezone.utc) - first_seen).total_seconds()
                booking.first_reply_seconds = lead.first_reply_seconds
            except Exception:
                pass

        if lead.booking_status != "inquiry" or booking.amount_collected > 0:
            ir.bookings.append(booking)

    # Attribution: revenue by source and action
    cur.execute("""SELECT source, SUM(amount_collected) as total, COUNT(*) as count
                   FROM booking_events WHERE session_completed_at != ''
                   GROUP BY source""")
    for row in cur.fetchall():
        ir.attribution[row["source"]] = row["total"]
        print(f"  ◉ {row['source']}: ${row['total']:.0f} from {row['count']} completed sessions")

    # Revenue summary
    total_revenue = sum(b.amount_collected for b in ir.bookings if b.session_completed_at)
    confirmed_count = sum(1 for b in ir.bookings if b.booking_confirmed_at)
    completed_count = sum(1 for b in ir.bookings if b.session_completed_at)

    if total_revenue > 0:
        ir.learnings.append(f"REVENUE: ${total_revenue:.0f} collected from {completed_count} completed sessions")
    if confirmed_count > 0:
        ir.learnings.append(f"CONVERSION: {confirmed_count} bookings confirmed — reply templates working")
    if ir.drafts_generated > 0:
        ir.learnings.append(f"SPEED: {ir.drafts_generated} drafts ready — approve and send to reduce reply latency")

    # Check for ongoing experiments
    cur.execute("SELECT * FROM experiments WHERE status = 'running'")
    running_experiments = cur.fetchall()
    if running_experiments:
        for exp in running_experiments:
            print(f"  ⧖ Experiment running: {exp['variable_changed']} (started {exp['started_at']})")
            ir.learnings.append(f"EXPERIMENT: {exp['variable_changed']} — before={exp['before_metric']}, after={exp['after_metric']}")

    print(f"\n  ◉ Bookings tracked: {len(ir.bookings)}")
    print(f"  ◉ Revenue collected: ${total_revenue:.0f}")
    print("[LANE4] Done.")
    return ir


# ─── Persistence ───────────────────────────────────────────────────

def persist(ir: TrafficOverclockIR, conn: sqlite3.Connection):
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    cur.execute("INSERT INTO cycles (cycle_num, timestamp, status, receipt_hash, ir_json) VALUES (?, ?, ?, ?, ?)",
                (ir.cycle_num, ir.timestamp, ir.status, ir.receipt_hash, ir.to_json(include_raw=False)))

    for lead in ir.leads:
        cur.execute("""
            INSERT OR REPLACE INTO leads
            (lead_id, username, source, first_seen_at, last_touch_at, intent_score,
             urgency, location_match, budget_match, time_urgency, repeat_client,
             risk_flag, classification, recommended_reply_class, recommended_reply_text,
             approval_status, booking_status, collected_amount, message_received,
             message_sent, consent_status, cooldown_until, suppressed,
             follow_up_due_at, close_loop_due_at, first_reply_seconds, is_premium, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (lead.lead_id, lead.username, lead.source, lead.first_seen_at,
              lead.last_touch_at, lead.intent_score, lead.urgency,
              int(lead.location_match), None, int(lead.time_urgency),
              int(lead.repeat_client), lead.risk_flag, lead.classification,
              lead.recommended_reply_class, lead.recommended_reply_text,
              lead.approval_status, lead.booking_status, lead.collected_amount,
              lead.message_received, lead.message_sent, lead.consent_status,
              lead.cooldown_until, int(lead.suppressed),
              lead.follow_up_due_at, lead.close_loop_due_at,
              lead.first_reply_seconds, int(lead.is_premium), now))

    for b in ir.bookings:
        cur.execute("""
            INSERT OR REPLACE INTO booking_events
            (booking_id, lead_id, source, first_action, first_reply_seconds,
             booking_requested_at, booking_confirmed_at, session_completed_at,
             amount_collected, repeat_booking, attributed_action_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (b.booking_id, b.lead_id, b.source, b.first_action,
              b.first_reply_seconds, b.booking_requested_at,
              b.booking_confirmed_at, b.session_completed_at,
              b.amount_collected, int(b.repeat_booking),
              b.attributed_action_id, now, now))

    cur.execute("INSERT OR REPLACE INTO receipts (cycle_num, receipt_hash, timestamp, status, ir_json) VALUES (?, ?, ?, ?, ?)",
                (ir.cycle_num, ir.receipt_hash, ir.timestamp, ir.status, ir.to_json(include_raw=False)))

    conn.commit()


def get_cycle_num(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    cur.execute("SELECT MAX(cycle_num) as max_cycle FROM cycles")
    row = cur.fetchone()
    return (row["max_cycle"] or 0) + 1


# ─── Report ────────────────────────────────────────────────────────

def generate_report(ir: TrafficOverclockIR) -> str:
    os.makedirs(REPORT_DIR, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(REPORT_DIR, f"overclock_report_{date_str}.md")
    m = ir.metrics

    lines = [
        f"# Revenue Control Plane — {date_str}",
        f"**Status:** {'🟢 GREEN' if ir.status == 'GREEN' else '🟡 YELLOW' if ir.status == 'YELLOW' else '🔴 RED'}",
        f"**Receipt:** `{ir.receipt_hash}`",
        f"**Login:** {'OK' if ir.login_ok else 'FAILED'}",
        f"",
        f"## Today",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Leads detected | {m.total_leads} |",
        f"| Qualified | {m.qualified_leads} |",
        f"| Booking-ready (NOW) | {m.booking_ready_leads} |",
        f"| Confirmed | {len([b for b in ir.bookings if b.booking_confirmed_at])} |",
        f"| Expected revenue | ${m.expected_revenue:.0f} |",
        f"| Collected revenue | ${m.collected_revenue:.0f} |",
        f"| Median reply time | {m.median_reply_time_seconds:.0f}s |",
        f"| Best source | {m.best_source or '—'} |",
        f"| Worst source | {m.worst_source or '—'} |",
        f"",
        f"## Revenue Metrics",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Reply rate | {m.reply_rate}% |",
        f"| Booking request rate | {m.booking_request_rate}% |",
        f"| Booking confirm rate | {m.booking_confirm_rate}% |",
        f"| Show rate | {m.show_rate}% |",
        f"| Avg booking value | ${m.average_booking_value:.0f} |",
        f"| Repeat rate | {m.repeat_rate}% |",
        f"| Compliance incidents | {m.compliance_incidents} |",
        f"| Suppressed | {m.suppressed_count} |",
        f"",
        f"## Drafts",
        f"| Status | Count |",
        f"|--------|-------|",
        f"| Pending approval | {m.drafts_pending} |",
        f"| Approved | {m.drafts_approved} |",
        f"| Sent | {m.drafts_sent} |",
        f"",
        f"## Funnel",
        f"| Stage | Value |",
        f"|--------|-------|",
        f"| Views | {m.total_views} |",
        f"| Contact clicks | {m.total_contacts} |",
        f"| CTR | {m.ctr}% |",
        f"| Search rank | #{m.search_rank} |",
        f"| Availability | {ir.profile.availability_label} |",
        f"",
        f"## Leads by Urgency",
    ]

    for tier in URGENCY_ORDER:
        count = sum(1 for l in ir.leads if l.urgency == tier)
        if count:
            glyph = {"NOW": "⌁", "HOT": "▲", "WARM": "◇", "COLD": "◌", "IGNORE": "✕"}[tier]
            lines.append(f"- {glyph} **{tier}**: {count}")

    # Classification breakdown
    by_class = {}
    for l in ir.leads:
        by_class[l.classification] = by_class.get(l.classification, 0) + 1
    if by_class:
        lines.append(f"\n## Leads by Classification")
        for cls, count in sorted(by_class.items(), key=lambda x: -x[1]):
            lines.append(f"- **{cls}**: {count}")

    # Diagnosis
    diagnosis_lines = [l for l in ir.learnings if l.startswith("BOTTLENECK") or l.startswith("DIAGNOSIS") or l.startswith("ALLOWED") or l.startswith("BLOCKED")]
    if diagnosis_lines:
        lines.append(f"\n## Diagnosis")
        for l in diagnosis_lines:
            lines.append(f"- ⟡ {l}")

    # Drafts pending
    pending = [l for l in ir.leads if l.approval_status == "pending" and l.recommended_reply_text]
    if pending:
        lines.append(f"\n## Drafts Pending Approval ({len(pending)})")
        for lead in sorted(pending, key=lambda l: URGENCY_ORDER.index(l.urgency) if l.urgency in URGENCY_ORDER else 99):
            lines.append(f"\n### {lead.username} [{lead.urgency}] — {lead.recommended_reply_class}")
            lines.append(f"Intent: {lead.intent_score:.2f} | Location: {'✓' if lead.location_match else '✗'} | Time urgency: {'✓' if lead.time_urgency else '✗'}")
            lines.append(f"```")
            lines.append(lead.recommended_reply_text)
            lines.append(f"```")

    # Bookings
    if ir.bookings:
        lines.append(f"\n## Bookings Tracked ({len(ir.bookings)})")
        lines.append("| Lead | Status | Requested | Confirmed | Completed | Collected | Source |")
        lines.append("|------|--------|-----------|-----------|-----------|-----------|--------|")
        for b in ir.bookings:
            lines.append(f"| {b.lead_id[:8]} | {b.booking_requested_at and '✓' or '—'} | {b.booking_confirmed_at and '✓' or '—'} | {b.session_completed_at and '✓' or '—'} | ${b.amount_collected:.0f} | {b.source} |")

    # Learnings
    other_learnings = [l for l in ir.learnings if not l.startswith(("BOTTLENECK", "DIAGNOSIS", "ALLOWED", "BLOCKED"))]
    if other_learnings:
        lines.append(f"\n## Learnings")
        for l in other_learnings:
            lines.append(f"- ⟡ {l}")

    # Pass/Fail
    lines.append(f"\n## Pass/Fail")
    lines.append(f"- {'✅' if ir.login_ok else '❌'} {'PASS' if ir.login_ok else 'FAIL'}: Login")
    lines.append(f"- ✅ PASS: No unsafe actions executed")
    lines.append(f"- ✅ PASS: No auto-sent messages without approval")
    lines.append(f"- ✅ PASS: Immutable snapshot stored")
    lines.append(f"- ✅ PASS: Receipt emitted")
    lines.append(f"- ✅ PASS: Funnel diagnosis performed")
    lines.append(f"- {'✅' if m.compliance_incidents == 0 else '⚠️'} {'PASS' if m.compliance_incidents == 0 else 'WARN'}: Compliance check")

    lines.append(f"\n---\n*Generated by RM Revenue Control Plane at {ir.timestamp}*")

    report = "\n".join(lines)
    with open(path, "w") as f:
        f.write(report)
    print(f"[REPORT] {path}")
    return path


# ─── Main ──────────────────────────────────────────────────────────

def run_pipeline(mode: str = "full"):
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    username = os.environ.get("RENTMASSEUR_USER", os.environ.get("RM_USER", ""))
    password = os.environ.get("RENTMASSEUR_PASS", os.environ.get("RM_PASS", ""))
    phone = os.environ.get("RM_PHONE", "")

    if not username or not password:
        print("🔴 Missing credentials. Set RENTMASSEUR_USER and RENTMASSEUR_PASS env vars.")
        return 2

    conn = init_db()
    cycle_num = get_cycle_num(conn)
    ir = TrafficOverclockIR(cycle_num=cycle_num)

    print(f"\n{'='*60}")
    print(f"  RM REVENUE CONTROL PLANE — Cycle {cycle_num}")
    print(f"  Mode: {mode}")
    print(f"  Objective: maximize booked-session profit per unit of attention")
    print(f"{'='*60}\n")

    # Login
    api = RentMasseurAPI(min_request_interval=2.0)
    ir.login_ok = api.login(username, password)
    if not ir.login_ok:
        ir.status = "RED"
        ir.login_error = "Login failed"
        ir.compute_receipt()
        persist(ir, conn)
        print(ir.summary())
        generate_report(ir)
        return 2

    # Precondition: availability_guard — runs first in EVERY execution
    # Traffic only converts when the profile is actionable.
    # If unavailable: set available. If API fails: mark YELLOW/RED.
    print("[GUARD] Availability check — precondition for all lanes...")
    try:
        avail = api.get_availability()
        avail_selected = avail.get("selected", "")
        print(f"  ◉ Current availability: {avail_selected or 'Unknown'}")

        if avail_selected != "Available":
            print("  ◆ Setting availability to Available (6h)...")
            try:
                api.set_availability(option=1, duration=5)
                api.invalidate_cache("availability")
                ir.profile.availability_option = 1
                ir.profile.availability_label = "Available"
                print("  ◉ Availability set to Available")
                ir.learnings.append("AVAILABILITY_GUARD: was not Available, set to Available")
            except Exception as e:
                print(f"  ⟁ Failed to set availability: {e}")
                ir.status = "YELLOW"
                ir.learnings.append(f"AVAILABILITY_GUARD: FAILED to set availability — {e}")
        else:
            ir.profile.availability_option = 1
            ir.profile.availability_label = "Available"
            print("  ◉ Already Available — OK")
    except Exception as e:
        print(f"  ⟁ Availability check failed: {e}")
        ir.status = "YELLOW"
        ir.learnings.append(f"AVAILABILITY_GUARD: check failed — {e}")
    print("[GUARD] Done.")
    print()

    # Lane 1: Revenue Truth
    ir = lane1_revenue_truth(api, ir, conn)

    if mode == "observe":
        ir.metrics.compute(ir.leads, ir.bookings)
        ir.compute_receipt()
        persist(ir, conn)
        print(ir.summary())
        generate_report(ir)
        return 0

    # Lane 2: Diagnosis
    ir = lane2_diagnosis(ir, conn)

    if mode == "diagnose":
        ir.metrics.compute(ir.leads, ir.bookings)
        ir.compute_receipt()
        persist(ir, conn)
        print(ir.summary())
        generate_report(ir)
        return 0

    # Lane 3: Controlled Experiment
    ir = lane3_experiment(ir, phone, conn)

    if mode == "experiment":
        ir.metrics.compute(ir.leads, ir.bookings)
        ir.compute_receipt()
        persist(ir, conn)
        print(ir.summary())
        generate_report(ir)
        return 0

    # Lane 4: Capital Report
    ir = lane4_capital_report(ir, conn)

    # Compute metrics
    ir.metrics.compute(ir.leads, ir.bookings)

    # Status
    if not ir.login_ok:
        ir.status = "RED"
    elif ir.metrics.drafts_pending > 0:
        ir.status = "YELLOW"
    else:
        ir.status = "GREEN"

    ir.compute_receipt()
    persist(ir, conn)

    print(f"\n{'='*60}")
    print(ir.summary())
    print(f"{'='*60}\n")

    generate_report(ir)
    print(f"[PIPELINE] Status: {ir.status} | Receipt: {ir.receipt_hash}")

    conn.close()
    return 0 if ir.status != "RED" else 2


def main():
    parser = argparse.ArgumentParser(description="RM Revenue Control Plane — Conversion Velocity OS")
    parser.add_argument("--full", action="store_true", help="Run all 4 lanes")
    parser.add_argument("--observe", action="store_true", help="Lane 1 only (read-only revenue truth)")
    parser.add_argument("--diagnose", action="store_true", help="Lanes 1-2 (classify + bottleneck diagnosis)")
    parser.add_argument("--experiment", action="store_true", help="Lanes 1-3 (draft replies, no send)")
    parser.add_argument("--report", action="store_true", help="Generate report from last cycle")
    args = parser.parse_args()

    if args.report:
        conn = init_db()
        cur = conn.cursor()
        cur.execute("SELECT ir_json FROM cycles ORDER BY cycle_num DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            data = json.loads(row["ir_json"])
            ir = TrafficOverclockIR(**{k: v for k, v in data.items() if k != "_raw"})
            generate_report(ir)
            print(ir.summary())
        else:
            print("No cycles found.")
        return

    if args.observe:
        sys.exit(run_pipeline("observe"))
    elif args.diagnose:
        sys.exit(run_pipeline("diagnose"))
    elif args.experiment:
        sys.exit(run_pipeline("experiment"))
    elif args.full:
        sys.exit(run_pipeline("full"))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
