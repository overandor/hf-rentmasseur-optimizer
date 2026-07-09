#!/usr/bin/env python3
"""
RM Revenue Pipeline — 3-lane CI/CD operator for RentMasseur.

Lane 1: Read-only scan (pull all business signals via API)
Lane 2: Safe auto-optimization (availability, visibility, bio experiments)
Lane 3: Risky action queue (messaging, rate changes — queued for approval)

Flow:
  raw_api → RevenueIR → scoring passes → action planner → policy gate → executor → after_snapshot → receipt

Usage:
    python3 rm_revenue_pipeline.py --scan          # Lane 1 only (read-only)
    python3 rm_revenue_pipeline.py --optimize       # Lanes 1+2 (safe auto-actions)
    python3 rm_revenue_pipeline.py --full           # All 3 lanes (queue risky actions)
    python3 rm_revenue_pipeline.py --report         # Print last report
"""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Load .env
ENV_PATH = Path(__file__).parent / ".env"
if ENV_PATH.exists():
    for line in open(ENV_PATH):
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent))

from rm_traffic.api_client import RentMasseurAPI
from rm_traffic.revenue_ir import RevenueIR, FunnelMetrics, ProfileState, VisitorRecord, ActionItem

USERNAME = os.environ.get("RENTMASSEUR_USER", os.environ.get("RM_USER", ""))
PASSWORD = os.environ.get("RENTMASSEUR_PASS", os.environ.get("RM_PASS", ""))
PHONE = os.environ.get("RM_PHONE", "6464103406")

DATA_DIR = Path(__file__).parent / "data" / "revenue_pipeline"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "revenue.db"
REPORT_DIR = DATA_DIR / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

# ── Policy definitions ──
AUTO_OK_ACTIONS = {"refresh_availability", "visibility_guard", "extend_availability"}
REVIEW_REQUIRED_ACTIONS = {"send_messages", "update_bio", "adjust_rates", "visit_profiles"}
BLOCKED_ACTIONS = {"mass_message", "spam", "scrape_private", "delete_content"}

NY_KEYWORDS = ["new york", "nyc", "manhattan", "brooklyn", "queens", "bronx", "staten island",
               "hudson", "dutchess", "westchester", "long island", "astoria", "harlem",
               "midtown", "uptown", "downtown", "soho", "village", "williamsburg"]


def is_ny_location(location: str) -> bool:
    loc = (location or "").lower()
    return any(kw in loc for kw in NY_KEYWORDS)


def classify_email(preview: str) -> str:
    p = (preview or "").lower()
    booking_words = ["book", "appointment", "session", "today", "tomorrow", "available", "schedule", "time", "hour"]
    inquiry_words = ["price", "rate", "how much", "where", "location", "incall", "outcall", "service", "what"]
    if any(w in p for w in booking_words):
        return "booking"
    if any(w in p for w in inquiry_words):
        return "inquiry"
    return "reply"


# ── SQLite persistence ──

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS cycles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, status TEXT, login_ok INTEGER,
        views INTEGER, contacts INTEGER, ctr REAL,
        emails INTEGER, unread INTEGER, premium INTEGER,
        booking_inquiries INTEGER, search_rank INTEGER,
        availability_option INTEGER, headline TEXT,
        actions_executed INTEGER, actions_queued INTEGER,
        receipt_hash TEXT, ir_json TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS visitors (
        username TEXT PRIMARY KEY,
        first_seen TEXT, last_seen TEXT,
        location TEXT, is_ny INTEGER, is_masseur INTEGER,
        visited_back INTEGER DEFAULT 0, messaged INTEGER DEFAULT 0,
        is_premium INTEGER DEFAULT 0, email_classification TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, action TEXT, target TEXT, success INTEGER,
        detail TEXT, receipt_hash TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS pending_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT, action TEXT, reason TEXT, priority INTEGER,
        status TEXT DEFAULT 'pending', ir_snapshot TEXT
    )""")
    conn.commit()
    conn.close()


def write_receipt(action: str, target: str, success: bool, detail: str, receipt_hash: str = ""):
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("INSERT INTO receipts (ts, action, target, success, detail, receipt_hash) VALUES (?,?,?,?,?,?)",
                 (datetime.now(timezone.utc).isoformat(), action, target, int(success), detail, receipt_hash))
    conn.commit()
    conn.close()


def get_last_cycle() -> Optional[Dict]:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM cycles ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return dict(row) if row else None


def upsert_visitor(username: str, location: str = "", is_ny: bool = False, is_masseur: Optional[bool] = None,
                   is_premium: bool = False, email_classification: str = ""):
    conn = sqlite3.connect(str(DB_PATH))
    now = datetime.now(timezone.utc).isoformat()
    conn.execute("""INSERT OR IGNORE INTO visitors (username, first_seen, last_seen, location, is_ny, is_masseur, visited_back, messaged, is_premium, email_classification)
                    VALUES (?,?,?,?,?,?,?,?,?,?)""",
                 (username, now, now, location, int(is_ny), int(is_masseur) if is_masseur is not None else -1, 0, 0, int(is_premium), email_classification))
    conn.execute("""UPDATE visitors SET last_seen=?, location=COALESCE(NULLIF(?, ''), location),
                    is_ny=COALESCE(?, is_ny), is_premium=COALESCE(?, is_premium),
                    email_classification=COALESCE(NULLIF(?, ''), email_classification)
                    WHERE username=?""",
                 (now, location, int(is_ny) if is_ny else None, int(is_premium) if is_premium else None, email_classification, username))
    conn.commit()
    conn.close()


# ── Lane 1: Read-only scan ──

def lane1_scan(api: RentMasseurAPI, ir: RevenueIR) -> RevenueIR:
    """Pull all business signals. No writes."""
    print("[LANE1] Scanning business state...")

    # Ad statistics — the funnel
    try:
        stats = api.get_ad_statistics()
        prof = stats.get("profileStatistics", {}) or {}
        ir.funnel.total_views = prof.get("totalPageViews", 0)
        ir.funnel.total_contacts = prof.get("totalContactClicks", 0)
        visits = prof.get("visits", []) or []
        daily = {v.get("day", ""): v.get("count", 0) for v in visits}
        ir.funnel.today_views = daily.get("Today", 0)
        ir._raw["ad_statistics"] = stats
        print(f"  ◉ Views={ir.funnel.total_views} Contacts={ir.funnel.total_contacts} Today={ir.funnel.today_views}")
    except Exception as e:
        print(f"  ⟁ ad_statistics failed: {e}")
        ir.status = "RED"

    # Mailbox
    try:
        mb = api.get_mailbox()
        emails = mb.get("emails", []) or []
        ir.funnel.emails_count = len(emails)
        ir.funnel.unread_emails = sum(1 for e in emails if e.get("unread"))
        ir.funnel.premium_senders = sum(1 for e in emails if e.get("userCard", {}).get("isGold") or e.get("userCard", {}).get("isPremium"))

        for e in emails:
            uname = e.get("userCard", {}).get("username", "")
            preview = (e.get("lastMessage", "") or "")[:200]
            cls = classify_email(preview)
            is_prem = bool(e.get("userCard", {}).get("isGold") or e.get("userCard", {}).get("isPremium"))
            if cls == "booking":
                ir.funnel.booking_inquiries += 1
            elif cls == "inquiry":
                ir.funnel.general_inquiries += 1
            if uname:
                upsert_visitor(uname, is_premium=is_prem, email_classification=cls)
                ir.mailbox_preview.append({"username": uname, "classification": cls, "premium": is_prem, "unread": bool(e.get("unread"))})
                # Check if visitor is NY from profile
                try:
                    prof_data = api.get_profile(uname)
                    loc = prof_data.get("location", "") or prof_data.get("city", "") or ""
                    is_mass = prof_data.get("isMasseur", None)
                    ny = is_ny_location(loc)
                    upsert_visitor(uname, location=loc, is_ny=ny, is_masseur=is_mass)
                    ir.visitors.append(VisitorRecord(username=uname, location=loc, is_ny=ny, is_masseur=is_mass, is_premium=is_prem, email_classification=cls))
                except Exception:
                    ir.visitors.append(VisitorRecord(username=uname, is_premium=is_prem, email_classification=cls))
        print(f"  ◉ Emails={ir.funnel.emails_count} Unread={ir.funnel.unread_emails} Premium={ir.funnel.premium_senders} Bookings={ir.funnel.booking_inquiries}")
    except Exception as e:
        print(f"  ⟁ mailbox failed: {e}")

    # Bio / about
    try:
        about = api.get_about()
        assets = about.get("userProps", {}).get("assets", {})
        ir.profile.headline = assets.get("headline", "")
        ir.profile.description_len = len(assets.get("description", ""))
        ir._raw["about"] = about
        print(f"  ◉ Headline: '{ir.profile.headline}'")
    except Exception as e:
        print(f"  ⟁ about failed: {e}")

    # Availability
    try:
        avail = api.get_availability()
        ir.profile.availability_option = avail.get("option", 0)
        labels = {0: "Not Set", 1: "Available", 2: "Not Available"}
        ir.profile.availability_label = labels.get(ir.profile.availability_option, "Unknown")
        print(f"  ◉ Availability: {ir.profile.availability_label}")
    except Exception as e:
        print(f"  ⟁ availability failed: {e}")

    # Dashboard — visibility + rates
    try:
        dash = api.get_dashboard()
        settings = dash.get("userSetting", {}) or {}
        ir.profile.is_visible = not settings.get("isAdHidden", False)
        services = dash.get("service", {}) or {}
        for key, svc in services.items():
            if isinstance(svc, dict) and svc.get("activated"):
                p = svc.get("price", {})
                incall = p.get("incall")
                outcall = p.get("outcall")
                if isinstance(incall, int) and isinstance(outcall, int):
                    ir.profile.active_rates.append({"service": key, "incall": incall, "outcall": outcall})
        ir.funnel.avg_rate = sum((r["incall"] + r["outcall"]) / 2 for r in ir.profile.active_rates) / len(ir.profile.active_rates) if ir.profile.active_rates else 199
        print(f"  ◉ Visible={ir.profile.is_visible} Rates={len(ir.profile.active_rates)} Avg=${ir.funnel.avg_rate}")
    except Exception as e:
        print(f"  ⟁ dashboard failed: {e}")

    # Search rank
    try:
        search = api.search(city="manhattan-ny", available_only=False, page=1)
        results = search.get("results", []) or search.get("data", []) or search.get("users", [])
        ir.profile.search_total = len(results)
        my_uname = USERNAME.split("@")[0] if "@" in USERNAME else USERNAME
        for i, r in enumerate(results):
            if isinstance(r, dict) and r.get("username", "").lower() == my_uname.lower():
                ir.profile.search_rank = i + 1
                break
        print(f"  ◉ Search rank: #{ir.profile.search_rank} of {ir.profile.search_total}")
    except Exception as e:
        print(f"  ⟁ search failed: {e}")

    # Compute funnel
    ir.funnel.compute()

    # Deltas vs last cycle
    last = get_last_cycle()
    if last:
        ir.deltas = {
            "views": ir.funnel.total_views - last.get("views", 0),
            "contacts": ir.funnel.total_contacts - last.get("contacts", 0),
            "ctr": round(ir.funnel.ctr - last.get("ctr", 0), 2),
            "emails": ir.funnel.emails_count - last.get("emails", 0),
        }
        print(f"  ◉ Deltas: views={ir.deltas['views']:+d} contacts={ir.deltas['contacts']:+d} ctr={ir.deltas['ctr']:+.2f}%")

    print("[LANE1] Scan complete.")
    return ir


# ── Lane 2: Safe auto-optimization ──

def lane2_optimize(api: RentMasseurAPI, ir: RevenueIR) -> RevenueIR:
    """Execute only AUTO_OK actions."""
    print("[LANE2] Running safe auto-optimization...")

    # 1. Refresh availability if not Available
    if ir.profile.availability_option != 1:
        try:
            api.set_availability(option=1, duration=5)
            action = ActionItem(action="refresh_availability", reason="was not Available", priority=1, policy="AUTO_OK", executed=True, result="set to Available")
            ir.actions_executed.append(action)
            write_receipt("refresh_availability", "self", True, "set to Available")
            print("  ◆ refresh_availability: set to Available")
        except Exception as e:
            print(f"  ⟁ refresh_availability failed: {e}")
    else:
        # Already available — extend to 6h
        try:
            api.set_availability(option=1, duration=5)
            action = ActionItem(action="extend_availability", reason="extend to 6h", priority=2, policy="AUTO_OK", executed=True, result="extended to 6h")
            ir.actions_executed.append(action)
            write_receipt("extend_availability", "self", True, "extended to 6h")
            print("  ◆ extend_availability: extended to 6h")
        except Exception as e:
            print(f"  ⟁ extend_availability failed: {e}")

    # 2. Visibility guard
    if not ir.profile.is_visible:
        try:
            api.set_visibility(True)
            action = ActionItem(action="visibility_guard", reason="was hidden", priority=1, policy="AUTO_OK", executed=True, result="set visible")
            ir.actions_executed.append(action)
            write_receipt("visibility_guard", "self", True, "set visible")
            print("  ◆ visibility_guard: set visible")
        except Exception as e:
            print(f"  ⟁ visibility_guard failed: {e}")
    else:
        print("  ◉ visibility_guard: already visible (OK)")

    # 3. Bio experiment — only if CTR is below benchmark and no recent change
    if ir.funnel.ctr < 5.0 and ir.funnel.total_views > 100:
        action = ActionItem(
            action="update_bio",
            reason=f"CTR {ir.funnel.ctr}% below 5% benchmark",
            priority=3,
            policy="REVIEW_REQUIRED",
            executed=False,
            result="queued for approval"
        )
        ir.actions_queued.append(action)
        print(f"  ⧖ update_bio: queued (CTR={ir.funnel.ctr}% below benchmark)")

    print(f"[LANE2] Done. {len(ir.actions_executed)} actions executed, {len(ir.actions_queued)} queued.")
    return ir


# ── Lane 3: Risky action queue ──

def lane3_queue(api: RentMasseurAPI, ir: RevenueIR) -> RevenueIR:
    """Queue risky actions for human approval. No execution."""
    print("[LANE3] Evaluating risky actions for queue...")

    # Queue messaging for NYC visitors
    ny_visitors = [v for v in ir.visitors if v.is_ny and not v.messaged]
    if ny_visitors:
        action = ActionItem(
            action="send_messages",
            reason=f"{len(ny_visitors)} NYC visitors not yet messaged",
            priority=1,
            policy="REVIEW_REQUIRED",
            executed=False,
            result=f"queued: {len(ny_visitors)} NYC visitors"
        )
        ir.actions_queued.append(action)
        print(f"  ⧖ send_messages: {len(ny_visitors)} NYC visitors queued")

    # Queue rate adjustment if booking rate is high
    if ir.funnel.booking_inquiries > 3 and ir.funnel.ctr > 5:
        action = ActionItem(
            action="adjust_rates",
            reason=f"{ir.funnel.booking_inquiries} booking inquiries with CTR {ir.funnel.ctr}% — demand may support rate increase",
            priority=2,
            policy="REVIEW_REQUIRED",
            executed=False,
            result="queued for review"
        )
        ir.actions_queued.append(action)
        print(f"  ⧖ adjust_rates: queued (high demand detected)")

    # Queue profile visits for reciprocity
    unvisited = [v for v in ir.visitors if not v.visited_back]
    if unvisited:
        action = ActionItem(
            action="visit_profiles",
            reason=f"{len(unvisited)} visitors not visited back",
            priority=3,
            policy="REVIEW_REQUIRED",
            executed=False,
            result=f"queued: {len(unvisited)} profiles"
        )
        ir.actions_queued.append(action)
        print(f"  ⧖ visit_profiles: {len(unvisited)} profiles queued")

    # Store pending actions in DB
    conn = sqlite3.connect(str(DB_PATH))
    for a in ir.actions_queued:
        conn.execute("INSERT INTO pending_actions (ts, action, reason, priority, status, ir_snapshot) VALUES (?,?,?,?,?,?)",
                     (datetime.now(timezone.utc).isoformat(), a.action, a.reason, a.priority, "pending", ir.to_json(include_raw=False)[:2000]))
    conn.commit()
    conn.close()

    print(f"[LANE3] Done. {len(ir.actions_queued)} actions queued for approval.")
    return ir


# ── Status determination ──

def determine_status(ir: RevenueIR) -> str:
    if not ir.login_ok:
        return "RED"
    if ir.actions_queued:
        return "YELLOW"
    return "GREEN"


# ── Report generation ──

def generate_report(ir: RevenueIR) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    report_path = REPORT_DIR / f"daily_report_{ts}.md"

    status_emoji = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}
    emoji = status_emoji.get(ir.status, "⚪")

    lines = [
        f"# RentMasseur Daily Report — {ts}",
        f"",
        f"**Status:** {emoji} {ir.status}",
        f"**Receipt:** `{ir.receipt_hash}`",
        f"**Login:** {'OK' if ir.login_ok else 'FAILED'}",
        f"",
        f"## Funnel",
        f"| Metric | Value | Delta |",
        f"|--------|-------|-------|",
        f"| Total Views | {ir.funnel.total_views} | {ir.deltas.get('views', 0):+d} |",
        f"| Today Views | {ir.funnel.today_views} | — |",
        f"| Contact Clicks | {ir.funnel.total_contacts} | {ir.deltas.get('contacts', 0):+d} |",
        f"| CTR | {ir.funnel.ctr}% | {ir.deltas.get('ctr', 0):+.2f}% |",
        f"| Emails | {ir.funnel.emails_count} | {ir.deltas.get('emails', 0):+d} |",
        f"| Unread | {ir.funnel.unread_emails} | — |",
        f"| Premium Senders | {ir.funnel.premium_senders} | — |",
        f"| Booking Inquiries | {ir.funnel.booking_inquiries} | — |",
        f"| Avg Rate | ${ir.funnel.avg_rate} | — |",
        f"",
        f"## Profile",
        f"- **Headline:** {ir.profile.headline}",
        f"- **Availability:** {ir.profile.availability_label}",
        f"- **Visible:** {ir.profile.is_visible}",
        f"- **Search Rank:** #{ir.profile.search_rank} of {ir.profile.search_total}",
        f"- **Active Rates:** {len(ir.profile.active_rates)}",
        f"",
        f"## Visitors",
        f"- Total: {len(ir.visitors)}",
        f"- NYC: {sum(1 for v in ir.visitors if v.is_ny)}",
        f"",
        f"## Actions Executed ({len(ir.actions_executed)})",
    ]
    for a in ir.actions_executed:
        lines.append(f"- ◆ **{a.action}** — {a.result}")
    if not ir.actions_executed:
        lines.append("- (none)")

    lines.append(f"")
    lines.append(f"## Actions Queued for Approval ({len(ir.actions_queued)})")
    for a in ir.actions_queued:
        lines.append(f"- ⧖ **{a.action}** (priority {a.priority}) — {a.reason}")
    if not ir.actions_queued:
        lines.append("- (none)")

    lines.extend([
        f"",
        f"## Pass/Fail",
        f"- {'✅ PASS' if ir.status != 'RED' else '❌ FAIL'}: Scan {'succeeded' if ir.login_ok else 'FAILED'}",
        f"- {'✅ PASS' if not any(a.policy == 'BLOCKED' for a in ir.actions_executed) else '❌ FAIL'}: No unsafe actions executed",
        f"- {'✅ PASS' if ir.receipt_hash else '❌ FAIL'}: Receipt emitted",
        f"",
        f"---",
        f"*Generated by RM Revenue Pipeline at {ir.timestamp}*",
    ])

    report_path.write_text("\n".join(lines))
    return report_path


# ── Main pipeline ──

def run_pipeline(mode: str = "scan") -> RevenueIR:
    ir = RevenueIR()
    ir.cycle_num = 1  # Will be set from DB

    # Get cycle number
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute("SELECT MAX(id) FROM cycles").fetchone()
    ir.cycle_num = (row[0] or 0) + 1
    conn.close()

    # Login
    print(f"[PIPELINE] Cycle {ir.cycle_num} — mode={mode}")
    api = RentMasseurAPI(min_request_interval=2.0)
    ir.login_ok = api.login(USERNAME, PASSWORD)
    if not ir.login_ok:
        ir.login_error = "Login failed"
        ir.status = "RED"
        ir.compute_receipt()
        print(f"[PIPELINE] LOGIN FAILED — aborting")
        return ir

    # Lane 1: Always scan
    ir = lane1_scan(api, ir)

    # Lane 2: Optimize if mode allows
    if mode in ("optimize", "full"):
        ir = lane2_optimize(api, ir)

    # Lane 3: Queue risky actions if full mode
    if mode == "full":
        ir = lane3_queue(api, ir)

    # Determine status
    ir.status = determine_status(ir)

    # Compute receipt
    ir.compute_receipt()

    # Persist cycle
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""INSERT INTO cycles (ts, status, login_ok, views, contacts, ctr, emails, unread, premium,
        booking_inquiries, search_rank, availability_option, headline, actions_executed, actions_queued, receipt_hash, ir_json)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (ir.timestamp, ir.status, int(ir.login_ok), ir.funnel.total_views, ir.funnel.total_contacts,
                  ir.funnel.ctr, ir.funnel.emails_count, ir.funnel.unread_emails, ir.funnel.premium_senders,
                  ir.funnel.booking_inquiries, ir.profile.search_rank, ir.profile.availability_option,
                  ir.profile.headline, len(ir.actions_executed), len(ir.actions_queued), ir.receipt_hash,
                  ir.to_json(include_raw=False)[:5000]))
    conn.commit()
    conn.close()

    # Generate report
    report = generate_report(ir)
    print(f"\n[PIPELINE] Report: {report}")
    print(f"[PIPELINE] Status: {ir.status} | Receipt: {ir.receipt_hash}")
    print(f"\n{ir.summary()}")

    return ir


def main():
    parser = argparse.ArgumentParser(description="RM Revenue Pipeline — 3-lane CI/CD operator")
    parser.add_argument("--scan", action="store_true", help="Lane 1 only: read-only scan")
    parser.add_argument("--optimize", action="store_true", help="Lanes 1+2: scan + safe auto-actions")
    parser.add_argument("--full", action="store_true", help="All 3 lanes: scan + optimize + queue risky actions")
    parser.add_argument("--report", action="store_true", help="Print last report")
    args = parser.parse_args()

    init_db()

    if args.report:
        reports = sorted(REPORT_DIR.glob("*.md"))
        if reports:
            print(reports[-1].read_text())
        else:
            print("No reports found")
        return

    if not USERNAME or not PASSWORD:
        print("ERROR: Set RENTMASSEUR_USER and RENTMASSEUR_PASS in .env or GitHub Secrets")
        sys.exit(1)

    mode = "full" if args.full else "optimize" if args.optimize else "scan" if args.scan else "scan"
    ir = run_pipeline(mode=mode)

    # Exit code: 0=GREEN, 1=YELLOW (review needed), 2=RED (failure)
    if ir.status == "RED":
        sys.exit(2)
    elif ir.status == "YELLOW":
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
