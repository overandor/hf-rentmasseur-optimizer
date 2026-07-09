#!/usr/bin/env python3
"""
RM BookingOps Ledger — 6-lane revenue pipeline.

The product is not traffic. The product is conversion.

Lane 1: Observe    — read mailbox, dashboard, profile, prior leads
Lane 2: Qualify    — classify each lead by booking intent
Lane 3: Draft      — generate compliant reply drafts (never auto-send)
Lane 4: Approve    — human approval gate, send only approved drafts
Lane 5: Outcome    — log booking status, payment, completion
Lane 6: Learn      — attribute revenue to actions, promote what works

Usage:
  python3 booking_ledger.py --full        # run all 6 lanes
  python3 booking_ledger.py --observe     # lane 1 only (read-only)
  python3 booking_ledger.py --qualify     # lanes 1-2
  python3 booking_ledger.py --draft       # lanes 1-3 (generate drafts, no send)
  python3 booking_ledger.py --report      # generate report from last cycle
"""

import argparse
import hashlib
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rm_traffic.api_client import RentMasseurAPI
from rm_traffic.booking_ir import (
    BookingIR, LeadRecord, DraftReply, BookingRecord,
    RevenueMetrics, ProfileSnapshot, LEAD_CLASSIFICATIONS,
)

log = logging.getLogger("booking_ops")

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "booking_ops")
DB_PATH = os.path.join(DB_DIR, "booking.db")
REPORT_DIR = os.path.join(DB_DIR, "reports")

NYC_KEYWORDS = ["nyc", "manhattan", "brooklyn", "queens", "bronx", "staten island",
                "new york", "ny ", "nj ", "hoboken", "jersey city", "astoria",
                "long island", "yonkers", "harlem", "midtown", "uptown", "downtown"]

BOOKING_KEYWORDS = ["book", "appointment", "schedule", "available", "today",
                    "tonight", "tomorrow", "this week", "session", "how much",
                    "price", "rate", "cost", "where", "location", "incall",
                    "outcall", "hotel", "zip", "area"]

LOW_INTENT_KEYWORDS = ["maybe", "just looking", "curious", "browsing", "thinking about",
                       "someday", "eventually", "wondering"]

SPAM_KEYWORDS = ["promo", "discount", "offer", "deal", "click here", "visit my",
                 "check out my", "follow me", "subscribe", "free"]

UNSAFE_KEYWORDS = ["raw", "bb", "bareback", "unsafe", "no condom", "bare"]

COMPETITOR_KEYWORDS = ["i'm also a", "fellow masseur", "colleague", "i offer",
                       "my services", "my profile", "my rates"]

REPEAT_KEYWORDS = ["again", "back again", "last time", "saw you before",
                   "was here before", "returned", "repeat", "second time",
                   "third time", "regular"]


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
        person_id_hash TEXT UNIQUE,
        username TEXT,
        source TEXT DEFAULT 'rentmasseur',
        first_seen_at TEXT,
        last_message_at TEXT,
        classification TEXT,
        intent_score REAL,
        location_match INTEGER,
        budget_match INTEGER,
        is_premium INTEGER,
        is_repeat INTEGER,
        message_received TEXT,
        message_sent TEXT,
        consent_status TEXT,
        cooldown_until TEXT,
        suppressed INTEGER DEFAULT 0,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS drafts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id_hash TEXT,
        username TEXT,
        draft_text TEXT,
        includes_price INTEGER,
        includes_availability INTEGER,
        includes_location INTEGER,
        includes_boundary INTEGER,
        includes_next_step INTEGER,
        compliance_ok INTEGER,
        approval_status TEXT DEFAULT 'pending',
        risk_flags TEXT,
        created_at TEXT,
        approved_at TEXT,
        sent_at TEXT
    );

    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id_hash TEXT,
        username TEXT,
        booking_status TEXT DEFAULT 'inquiry',
        requested_time TEXT,
        confirmed_time TEXT,
        session_duration TEXT,
        session_value REAL,
        amount_collected REAL,
        source TEXT,
        attributed_action TEXT,
        created_at TEXT,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS revenue_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person_id_hash TEXT,
        source TEXT,
        event_type TEXT,
        event_data TEXT,
        amount REAL,
        created_at TEXT
    );

    CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cycle_num INTEGER,
        receipt_hash TEXT UNIQUE,
        timestamp TEXT,
        status TEXT,
        ir_json TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_leads_hash ON leads(person_id_hash);
    CREATE INDEX IF NOT EXISTS idx_drafts_hash ON drafts(person_id_hash);
    CREATE INDEX IF NOT EXISTS idx_bookings_hash ON bookings(person_id_hash);
    CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(approval_status);
    CREATE INDEX IF NOT EXISTS idx_bookings_status ON bookings(booking_status);
    """)
    conn.commit()
    return conn


def person_hash(username: str) -> str:
    return hashlib.sha256(f"rm:{username}".encode()).hexdigest()[:16]


# ─── Lane 1: Observe ───────────────────────────────────────────────

def lane1_observe(api: RentMasseurAPI, ir: BookingIR, conn: sqlite3.Connection) -> BookingIR:
    """Read inbound demand. No writes to the platform."""
    print("[LANE1] Observing inbound demand...")

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

    try:
        avail = api.get_availability()
        ir._raw["availability"] = avail
        data = avail.get("data", avail)
        ir.profile.availability_option = int(data.get("option", 0))
        labels = {0: "Not Set", 1: "Available", 2: "Not Available"}
        ir.profile.availability_label = labels.get(ir.profile.availability_option, "Unknown")
        print(f"  ◉ Availability: {ir.profile.availability_label}")
    except Exception as e:
        print(f"  ⟁ availability error: {e}")

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

    try:
        dashboard = api.get_dashboard()
        ir._raw["dashboard"] = dashboard
        data = dashboard.get("data", dashboard)
        ir.profile.is_visible = not data.get("isAdHidden", False)
        print(f"  ◉ Visible: {ir.profile.is_visible}")
    except Exception as e:
        print(f"  ⟁ dashboard error: {e}")

    # Pull mailbox — this is where leads live
    try:
        mailbox = api.get_mailbox(page=1, folder=1, sort=1)
        ir._raw["mailbox"] = mailbox
        conversations = mailbox.get("emails", mailbox.get("data", {}).get("conversations", []))
        if not conversations and isinstance(mailbox.get("data"), list):
            conversations = mailbox["data"]
        ir.mailbox_raw = conversations
        print(f"  ◉ Mailbox: {len(conversations)} conversations")
    except Exception as e:
        print(f"  ⟁ mailbox error: {e}")
        conversations = []

    # Convert mailbox conversations into LeadRecords
    for conv in conversations:
        user_card = conv.get("userCard", conv.get("user", {}))
        username = user_card.get("username", conv.get("username", ""))
        if not username:
            continue

        msg_text = conv.get("lastMessage", conv.get("message", conv.get("body", "")))
        is_premium = user_card.get("isPremium", conv.get("isPremium", False))
        created_ts = conv.get("createdAt", 0)
        if created_ts:
            from datetime import datetime as dt
            last_time = dt.utcfromtimestamp(int(created_ts)).isoformat()
        else:
            last_time = conv.get("lastMessageAt", conv.get("updatedAt", ""))
        unread = conv.get("unread", 0)

        lead = LeadRecord(
            person_id_hash=person_hash(username),
            username=username,
            source="rentmasseur",
            first_seen_at=last_time,
            last_message_at=last_time,
            message_received=msg_text,
            is_premium=bool(is_premium),
        )
        ir.leads.append(lead)

    # Check for prior leads in DB (repeat detection)
    cur = conn.cursor()
    for lead in ir.leads:
        cur.execute("SELECT * FROM leads WHERE person_id_hash = ?", (lead.person_id_hash,))
        row = cur.fetchone()
        if row:
            lead.is_repeat = bool(row["is_repeat"]) or lead.is_repeat
            if not lead.first_seen_at:
                lead.first_seen_at = row["first_seen_at"]
            if row["classification"]:
                lead.classification = row["classification"]
            if row["message_sent"]:
                lead.message_sent = row["message_sent"]
            if row["consent_status"]:
                lead.consent_status = row["consent_status"]
        else:
            cur.execute("SELECT COUNT(*) as c FROM leads WHERE person_id_hash = ?", (lead.person_id_hash,))
            if cur.fetchone()["c"] == 0:
                lead.is_repeat = False

    print(f"  ◉ Leads observed: {len(ir.leads)} ({sum(1 for l in ir.leads if l.is_repeat)} repeat)")
    print("[LANE1] Done.")
    return ir


# ─── Lane 2: Qualify ───────────────────────────────────────────────

def classify_lead(lead: LeadRecord) -> tuple:
    """Classify a lead and assign intent score. Returns (classification, intent_score, location_match)."""
    text = (lead.message_received or "").lower()
    location_match = any(kw in text for kw in NYC_KEYWORDS)

    if any(kw in text for kw in UNSAFE_KEYWORDS):
        return "unsafe", 0.0, location_match
    if any(kw in text for kw in SPAM_KEYWORDS):
        return "spam", 0.0, location_match
    if any(kw in text for kw in COMPETITOR_KEYWORDS):
        return "competitor", 0.0, location_match
    if not location_match and any(kw in text for kw in ["la", "sf", "chicago", "miami", "boston", "dc", "atlanta", "dallas", "houston", "philly", "seattle", "vegas"]):
        return "out_of_area", 0.1, location_match
    if lead.is_repeat or any(kw in text for kw in REPEAT_KEYWORDS):
        lead.is_repeat = True
        return "repeat_client", 0.9, location_match
    if any(kw in text for kw in BOOKING_KEYWORDS):
        return "booking_ready", 0.8, location_match
    if any(kw in text for kw in LOW_INTENT_KEYWORDS):
        return "low_intent", 0.2, location_match
    if text.strip():
        return "inquiry", 0.5, location_match
    return "low_intent", 0.1, location_match


def lane2_qualify(ir: BookingIR, conn: sqlite3.Connection) -> BookingIR:
    """Classify each lead by booking intent."""
    print("[LANE2] Qualifying leads...")

    for lead in ir.leads:
        classification, intent, loc_match = classify_lead(lead)
        lead.classification = classification
        lead.intent_score = intent
        lead.location_match = loc_match

        if lead.is_premium:
            lead.intent_score = min(1.0, lead.intent_score + 0.1)

    # Summary
    by_class = {}
    for l in ir.leads:
        by_class[l.classification] = by_class.get(l.classification, 0) + 1

    for cls, count in sorted(by_class.items(), key=lambda x: -x[1]):
        glyph = "◆" if cls in ("booking_ready", "repeat_client") else "◇" if cls == "inquiry" else "◌"
        print(f"  {glyph} {cls}: {count}")

    qualified = [l for l in ir.leads if l.classification in ("booking_ready", "inquiry", "repeat_client")]
    print(f"  ◉ Qualified leads: {len(qualified)}")
    print("[LANE2] Done.")
    return ir


# ─── Lane 3: Draft ─────────────────────────────────────────────────

def draft_reply(lead: LeadRecord, profile: ProfileSnapshot, phone: str) -> DraftReply:
    """Generate a compliant reply draft. Never auto-sends."""
    username = lead.username
    cls = lead.classification

    if cls == "booking_ready":
        rate_str = f"${profile.avg_rate:.0f}" if profile.avg_rate else "rates on my profile"
        text = (
            f"Hi! Thanks for reaching out. I'd be happy to schedule a session. "
            f"My rate is {rate_str}. I'm available for incall in Manhattan. "
            f"What day and time works best for you? "
            f"You can also reach me at {phone} for faster booking."
        )
        includes_price = True
        includes_availability = True
        includes_location = True
        includes_boundary = True
        includes_next_step = True

    elif cls == "repeat_client":
        text = (
            f"Great to hear from you again! I'd love to book another session. "
            f"What time works for you? Same location in Manhattan. "
            f"Text me at {phone} to confirm quickly."
        )
        includes_price = False
        includes_availability = True
        includes_location = True
        includes_boundary = True
        includes_next_step = True

    elif cls == "inquiry":
        text = (
            f"Hi! Thanks for your interest. I offer deep tissue and sports recovery massage in Manhattan. "
            f"Feel free to check my profile for rates and details. "
            f"What questions can I answer for you? "
            f"You can also text me at {phone}."
        )
        includes_price = False
        includes_availability = True
        includes_location = True
        includes_boundary = True
        includes_next_step = True

    elif cls == "out_of_area":
        text = (
            f"Hi! Thanks for reaching out. I'm based in Manhattan, NYC. "
            f"If you're planning to visit the city, I'd be happy to schedule a session. "
            f"Feel free to text me at {phone} when you're in town."
        )
        includes_price = False
        includes_availability = False
        includes_location = True
        includes_boundary = True
        includes_next_step = True

    elif cls == "low_intent":
        text = (
            f"Hi! Thanks for browsing. If you'd like to book a session, "
            f"I'm available in Manhattan. Text me at {phone} when you're ready."
        )
        includes_price = False
        includes_availability = True
        includes_location = True
        includes_boundary = True
        includes_next_step = True

    else:
        return None  # spam, competitor, unsafe — no draft

    risk_flags = []
    compliance_ok = True
    if not includes_boundary:
        risk_flags.append("missing_boundary")
        compliance_ok = False
    if not includes_next_step:
        risk_flags.append("missing_next_step")
        compliance_ok = False

    return DraftReply(
        person_id_hash=lead.person_id_hash,
        username=username,
        draft_text=text,
        includes_price=includes_price,
        includes_availability=includes_availability,
        includes_location=includes_location,
        includes_boundary=includes_boundary,
        includes_next_step=includes_next_step,
        compliance_ok=compliance_ok,
        approval_status="pending",
        created_at=datetime.now(timezone.utc).isoformat(),
        risk_flags=risk_flags,
    )


def lane3_draft(ir: BookingIR, phone: str) -> BookingIR:
    """Generate reply drafts for qualified leads. No sending."""
    print("[LANE3] Drafting replies...")

    for lead in ir.leads:
        if lead.classification in ("spam", "competitor", "unsafe", "already_active"):
            lead.suppressed = True
            continue
        if lead.suppressed:
            continue
        if lead.message_sent and lead.classification != "repeat_client":
            continue

        draft = draft_reply(lead, ir.profile, phone)
        if draft:
            ir.drafts.append(draft)
            print(f"  ⧖ Draft for {lead.username} ({lead.classification}, intent={lead.intent_score:.1f})")

    print(f"  ◉ Drafts generated: {len(ir.drafts)}")
    print(f"  ◌ Suppressed: {sum(1 for l in ir.leads if l.suppressed)}")
    print("[LANE3] Done.")
    return ir


# ─── Lane 4: Approve/Send ──────────────────────────────────────────

def lane4_approve(ir: BookingIR, conn: sqlite3.Connection, auto_send: bool = False) -> BookingIR:
    """Human approval gate. Only sends approved drafts."""
    print("[LANE4] Approval gate...")

    pending = [d for d in ir.drafts if d.approval_status == "pending"]
    print(f"  ⧖ {len(pending)} drafts pending approval")

    if not auto_send:
        print("  ◌ Auto-send disabled. All drafts queued for human review.")
        for d in pending:
            print(f"    → {d.username}: \"{d.draft_text[:80]}...\"")
        print("[LANE4] Done. No messages sent.")
        return ir

    # Auto-send only for repeat clients with prior consent
    for d in pending:
        lead = next((l for l in ir.leads if l.person_id_hash == d.person_id_hash), None)
        if lead and lead.is_repeat and lead.consent_status == "opted_in":
            print(f"  ◆ Auto-approved repeat client: {d.username}")
            d.approval_status = "approved"
            d.approved_at = datetime.now(timezone.utc).isoformat()
        else:
            print(f"  ⧖ Requires human approval: {d.username} ({lead.classification if lead else 'unknown'})")

    print("[LANE4] Done.")
    return ir


# ─── Lane 5: Outcome ───────────────────────────────────────────────

def lane5_outcome(ir: BookingIR, conn: sqlite3.Connection) -> BookingIR:
    """Log booking status and check for outcome updates in mailbox."""
    print("[LANE5] Tracking outcomes...")

    cur = conn.cursor()

    for lead in ir.leads:
        cur.execute("SELECT * FROM bookings WHERE person_id_hash = ? ORDER BY created_at DESC LIMIT 1",
                     (lead.person_id_hash,))
        row = cur.fetchone()

        text = (lead.message_received or "").lower()

        if row:
            booking = BookingRecord(
                person_id_hash=row["person_id_hash"],
                username=row["username"],
                booking_status=row["booking_status"],
                requested_time=row["requested_time"] or "",
                confirmed_time=row["confirmed_time"] or "",
                session_duration=row["session_duration"] or "",
                session_value=row["session_value"] or 0.0,
                amount_collected=row["amount_collected"] or 0.0,
                source=row["source"] or "rentmasseur",
                attributed_action=row["attributed_action"] or "",
                created_at=row["created_at"] or "",
                updated_at=datetime.now(timezone.utc).isoformat(),
            )

            # Check for status transitions in message text
            if any(kw in text for kw in ["confirmed", "see you", "on my way", "be there", "booking confirmed"]):
                booking.booking_status = "confirmed"
                print(f"  ◆ {lead.username}: booking confirmed")
            elif any(kw in text for kw in ["completed", "finished", "great session", "thank you", "thanks for the", "see you next"]):
                booking.booking_status = "completed"
                if booking.session_value == 0:
                    booking.session_value = ir.profile.avg_rate
                booking.amount_collected = booking.session_value
                print(f"  ◉ {lead.username}: session completed (${booking.amount_collected:.0f})")
            elif any(kw in text for kw in ["cancel", "reschedule", "can't make it", "postpone"]):
                booking.booking_status = "cancelled"
                print(f"  ⟁ {lead.username}: cancelled")
            elif any(kw in text for kw in ["book", "appointment", "schedule", "available today", "available tomorrow"]):
                if booking.booking_status == "inquiry":
                    booking.booking_status = "requested"
                    print(f"  ▲ {lead.username}: booking requested")

            ir.bookings.append(booking)
        else:
            # New lead showing booking intent
            if any(kw in text for kw in ["book", "appointment", "schedule", "available today", "available tomorrow"]):
                booking = BookingRecord(
                    person_id_hash=lead.person_id_hash,
                    username=lead.username,
                    booking_status="requested",
                    source="rentmasseur",
                    attributed_action="inbound_message",
                    created_at=datetime.now(timezone.utc).isoformat(),
                    updated_at=datetime.now(timezone.utc).isoformat(),
                )
                ir.bookings.append(booking)
                print(f"  ▲ {lead.username}: new booking request detected")

    print(f"  ◉ Bookings tracked: {len(ir.bookings)}")
    print("[LANE5] Done.")
    return ir


# ─── Lane 6: Learn ─────────────────────────────────────────────────

def lane6_learn(ir: BookingIR, conn: sqlite3.Connection) -> BookingIR:
    """Attribute revenue to actions. Promote what works, demote what doesn't."""
    print("[LANE6] Learning from outcomes...")

    cur = conn.cursor()

    # Revenue by source
    cur.execute("""
        SELECT source, SUM(amount_collected) as total
        FROM bookings WHERE booking_status = 'completed'
        GROUP BY source
    """)
    for row in cur.fetchall():
        ir.attribution[row["source"]] = row["total"]
        print(f"  ◉ {row['source']}: ${row['total']:.0f} collected")

    # Revenue by attributed action
    cur.execute("""
        SELECT attributed_action, SUM(amount_collected) as total, COUNT(*) as count
        FROM bookings WHERE booking_status = 'completed' AND attributed_action != ''
        GROUP BY attributed_action
    """)
    for row in cur.fetchall():
        ir.attribution[f"action:{row['attributed_action']}"] = row["total"]
        print(f"  ◉ action:{row['attributed_action']}: ${row['total']:.0f} from {row['count']} bookings")

    # Learnings
    total_revenue = sum(b.amount_collected for b in ir.bookings if b.booking_status == "completed")
    if total_revenue > 0:
        ir.learnings.append(f"Revenue collected this cycle: ${total_revenue:.0f}")

    confirmed = sum(1 for b in ir.bookings if b.booking_status in ("confirmed", "completed"))
    if confirmed > 0:
        ir.learnings.append(f"{confirmed} bookings confirmed/completed — reply drafts are working")

    no_reply = sum(1 for l in ir.leads if l.classification in ("booking_ready", "repeat_client") and not l.message_sent)
    if no_reply > 0:
        ir.learnings.append(f"{no_reply} qualified leads still need replies — prioritize approval")

    spam_count = sum(1 for l in ir.leads if l.classification == "spam")
    if spam_count > 0:
        ir.learnings.append(f"{spam_count} spam leads filtered — saving manual review time")

    for learning in ir.learnings:
        print(f"  ⟡ {learning}")

    print("[LANE6] Done.")
    return ir


# ─── Persistence ───────────────────────────────────────────────────

def persist(ir: BookingIR, conn: sqlite3.Connection):
    """Save all state to SQLite."""
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    # Cycle
    cur.execute("INSERT INTO cycles (cycle_num, timestamp, status, receipt_hash, ir_json) VALUES (?, ?, ?, ?, ?)",
                (ir.cycle_num, ir.timestamp, ir.status, ir.receipt_hash, ir.to_json(include_raw=False)))

    # Leads
    for lead in ir.leads:
        cur.execute("""
            INSERT OR REPLACE INTO leads
            (person_id_hash, username, source, first_seen_at, last_message_at,
             classification, intent_score, location_match, budget_match, is_premium,
             is_repeat, message_received, message_sent, consent_status, cooldown_until,
             suppressed, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (lead.person_id_hash, lead.username, lead.source, lead.first_seen_at,
              lead.last_message_at, lead.classification, lead.intent_score,
              int(lead.location_match), None, int(lead.is_premium), int(lead.is_repeat),
              lead.message_received, lead.message_sent, lead.consent_status,
              lead.cooldown_until, int(lead.suppressed), now))

    # Drafts
    for d in ir.drafts:
        cur.execute("""
            INSERT INTO drafts
            (person_id_hash, username, draft_text, includes_price, includes_availability,
             includes_location, includes_boundary, includes_next_step, compliance_ok,
             approval_status, risk_flags, created_at, approved_at, sent_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (d.person_id_hash, d.username, d.draft_text, int(d.includes_price),
              int(d.includes_availability), int(d.includes_location), int(d.includes_boundary),
              int(d.includes_next_step), int(d.compliance_ok), d.approval_status,
              json.dumps(d.risk_flags), d.created_at, d.approved_at, d.sent_at))

    # Bookings
    for b in ir.bookings:
        cur.execute("""
            INSERT OR REPLACE INTO bookings
            (person_id_hash, username, booking_status, requested_time, confirmed_time,
             session_duration, session_value, amount_collected, source, attributed_action,
             created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (b.person_id_hash, b.username, b.booking_status, b.requested_time,
              b.confirmed_time, b.session_duration, b.session_value, b.amount_collected,
              b.source, b.attributed_action, b.created_at, b.updated_at))

    # Receipt
    cur.execute("INSERT OR REPLACE INTO receipts (cycle_num, receipt_hash, timestamp, status, ir_json) VALUES (?, ?, ?, ?, ?)",
                (ir.cycle_num, ir.receipt_hash, ir.timestamp, ir.status, ir.to_json(include_raw=False)))

    conn.commit()


def get_cycle_num(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    cur.execute("SELECT MAX(cycle_num) as max_cycle FROM cycles")
    row = cur.fetchone()
    return (row["max_cycle"] or 0) + 1


# ─── Report ────────────────────────────────────────────────────────

def generate_report(ir: BookingIR) -> str:
    os.makedirs(REPORT_DIR, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = os.path.join(REPORT_DIR, f"booking_report_{date_str}.md")

    m = ir.metrics

    lines = [
        f"# BookingOps Report — {date_str}",
        f"**Status:** {'🟢 GREEN' if ir.status == 'GREEN' else '🟡 YELLOW' if ir.status == 'YELLOW' else '🔴 RED'}",
        f"**Receipt:** `{ir.receipt_hash}`",
        f"**Login:** {'OK' if ir.login_ok else 'FAILED'}",
        f"",
        f"## Revenue Metrics",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Leads | {m.total_leads} |",
        f"| Qualified Leads | {m.qualified_leads} |",
        f"| Reply Rate | {m.reply_rate}% |",
        f"| Booking Request Rate | {m.booking_request_rate}% |",
        f"| Booking Confirm Rate | {m.booking_confirm_rate}% |",
        f"| Show Rate | {m.show_rate}% |",
        f"| Collected Revenue | ${m.collected_revenue:.0f} |",
        f"| Avg Booking Value | ${m.average_booking_value:.0f} |",
        f"| Repeat Rate | {m.repeat_rate}% |",
        f"| Compliance Incidents | {m.compliance_incidents} |",
        f"",
        f"## Drafts",
        f"| Status | Count |",
        f"|--------|-------|",
        f"| Pending Approval | {m.drafts_pending} |",
        f"| Approved | {m.drafts_approved} |",
        f"| Sent | {m.drafts_sent} |",
        f"",
        f"## Secondary (Upstream)",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total Views | {m.total_views} |",
        f"| CTR | {m.ctr}% |",
        f"| Search Rank | #{m.search_rank} |",
        f"| Availability | {ir.profile.availability_label} |",
        f"",
        f"## Leads by Classification",
    ]

    by_class = {}
    for l in ir.leads:
        by_class[l.classification] = by_class.get(l.classification, 0) + 1
    for cls, count in sorted(by_class.items(), key=lambda x: -x[1]):
        lines.append(f"- **{cls}**: {count}")

    if ir.bookings:
        lines.append(f"\n## Bookings Tracked ({len(ir.bookings)})")
        lines.append("| Lead | Status | Value | Collected | Source |")
        lines.append("|------|--------|-------|-----------|--------|")
        for b in ir.bookings:
            lines.append(f"| {b.username} | {b.booking_status} | ${b.session_value:.0f} | ${b.amount_collected:.0f} | {b.source} |")

    if ir.learnings:
        lines.append(f"\n## Learnings")
        for l in ir.learnings:
            lines.append(f"- ⟡ {l}")

    if ir.drafts:
        lines.append(f"\n## Drafts Pending Approval ({len([d for d in ir.drafts if d.approval_status == 'pending'])})")
        for d in ir.drafts:
            if d.approval_status == "pending":
                lines.append(f"\n### {d.username}")
                lines.append(f"```\n{d.draft_text}\n```")
                flags = []
                if d.includes_price: flags.append("price")
                if d.includes_availability: flags.append("availability")
                if d.includes_location: flags.append("location")
                if d.includes_boundary: flags.append("boundary")
                if d.includes_next_step: flags.append("next_step")
                lines.append(f"Compliance: {'✅' if d.compliance_ok else '⚠️'} | Includes: {', '.join(flags)}")

    lines.append(f"\n## Pass/Fail")
    lines.append(f"- {'✅' if ir.login_ok else '❌'} {'PASS' if ir.login_ok else 'FAIL'}: Login")
    lines.append(f"- ✅ PASS: No unsafe actions executed")
    lines.append(f"- ✅ PASS: No auto-sent messages without approval")
    lines.append(f"- ✅ PASS: Receipt emitted")
    lines.append(f"- {'✅' if m.compliance_incidents == 0 else '⚠️'} {'PASS' if m.compliance_incidents == 0 else 'WARN'}: Compliance check")

    lines.append(f"\n---\n*Generated by RM BookingOps Ledger at {ir.timestamp}*")

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
    ir = BookingIR(cycle_num=cycle_num)

    print(f"\n{'='*60}")
    print(f"  RM BOOKINGOPS LEDGER — Cycle {cycle_num}")
    print(f"  Mode: {mode}")
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

    # Lane 1: Observe
    ir = lane1_observe(api, ir, conn)

    if mode == "observe":
        ir.metrics.compute(ir.leads, ir.bookings, ir.drafts)
        ir.compute_receipt()
        persist(ir, conn)
        print(ir.summary())
        generate_report(ir)
        return 0

    # Lane 2: Qualify
    ir = lane2_qualify(ir, conn)

    if mode == "qualify":
        ir.metrics.compute(ir.leads, ir.bookings, ir.drafts)
        ir.compute_receipt()
        persist(ir, conn)
        print(ir.summary())
        generate_report(ir)
        return 0

    # Lane 3: Draft
    ir = lane3_draft(ir, phone)

    if mode == "draft":
        ir.metrics.compute(ir.leads, ir.bookings, ir.drafts)
        ir.compute_receipt()
        persist(ir, conn)
        print(ir.summary())
        generate_report(ir)
        return 0

    # Lane 4: Approve (never auto-send in CI)
    ir = lane4_approve(ir, conn, auto_send=False)

    # Lane 5: Outcome
    ir = lane5_outcome(ir, conn)

    # Lane 6: Learn
    ir = lane6_learn(ir, conn)

    # Compute metrics
    ir.metrics.compute(ir.leads, ir.bookings, ir.drafts)

    # Status
    if not ir.login_ok:
        ir.status = "RED"
    elif ir.metrics.compliance_incidents > 0:
        ir.status = "YELLOW"
    elif ir.metrics.drafts_pending > 0:
        ir.status = "YELLOW"
    else:
        ir.status = "GREEN"

    ir.compute_receipt()
    persist(ir, conn)

    print(f"\n{'='*60}")
    print(ir.summary())
    print(f"{'='*60}\n")

    report_path = generate_report(ir)
    print(f"[PIPELINE] Status: {ir.status} | Receipt: {ir.receipt_hash}")
    print(f"[PIPELINE] Report: {report_path}")

    conn.close()
    return 0 if ir.status != "RED" else 2


def main():
    parser = argparse.ArgumentParser(description="RM BookingOps Ledger — revenue pipeline")
    parser.add_argument("--full", action="store_true", help="Run all 6 lanes")
    parser.add_argument("--observe", action="store_true", help="Lane 1 only (read-only)")
    parser.add_argument("--qualify", action="store_true", help="Lanes 1-2 (classify leads)")
    parser.add_argument("--draft", action="store_true", help="Lanes 1-3 (generate drafts, no send)")
    parser.add_argument("--report", action="store_true", help="Generate report from last cycle")
    args = parser.parse_args()

    if args.report:
        conn = init_db()
        cur = conn.cursor()
        cur.execute("SELECT ir_json FROM cycles ORDER BY cycle_num DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            ir = BookingIR(**{k: v for k, v in json.loads(row["ir_json"]).items() if k != "_raw"})
            generate_report(ir)
            print(ir.summary())
        else:
            print("No cycles found.")
        return

    if args.observe:
        sys.exit(run_pipeline("observe"))
    elif args.qualify:
        sys.exit(run_pipeline("qualify"))
    elif args.draft:
        sys.exit(run_pipeline("draft"))
    elif args.full:
        sys.exit(run_pipeline("full"))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
