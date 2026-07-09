"""
RM ProfileOps Daemon — safe, bounded, receipt-bearing account ops engine.

Modes:
    audit   — read only, change nothing
    guard   — fix visibility + availability only
    draft   — generate content drafts, do not publish
    daemon  — run safe loop continuously

The daemon never:
- fakes reviews
- fakes visits
- auto-sends messages
- auto-publishes blogs
- auto-changes interview
- makes destructive changes without backup
"""

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

from .db import init_db, write_receipt, get_latest_traffic_snapshot
from .api_client import RentMasseurAPI
from .auth import AuthSession
from .state import snapshot_state, save_snapshot
from .visibility_guard import ensure_visible
from .availability_guard import check_availability, refresh_availability
from .stats_collector import collect_snapshot
from .content_optimizer import run_daily_draft_cycle
from .blog_agent import generate_blog_drafts, save_blog_drafts_to_disk, get_blog_status
from .interview_agent import monitor_interview, generate_interview_drafts

log = logging.getLogger("profileops.daemon")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

CHECK_INTERVAL = 5 * 60           # 5 minutes
AVAILABILITY_CHECK_INTERVAL = 30 * 60  # 30 minutes
DAILY_DRAFT_INTERVAL = 24 * 60 * 60      # 24 hours


class ProfileOpsDaemon:
    def __init__(self, mode: str = "daemon", city: str = "manhattan-ny",
                 session_file: str = "rm_traffic/session.json"):
        self.mode = mode
        self.city = city
        self.api = RentMasseurAPI(min_request_interval=2.0)
        self.auth = AuthSession(self.api, session_file=session_file)
        self.running = True
        self.last_check = 0
        self.last_availability_check = 0
        self.last_daily_draft = 0

    def login(self) -> bool:
        ok = self.auth.login()
        if not ok:
            log.error("Login failed")
        return ok

    def audit(self) -> dict:
        """Read everything. Change nothing."""
        state = snapshot_state(self.api)
        save_snapshot(state)
        keep = state.get("keeponline", {})
        avail = state.get("availability", {})
        about = state.get("about", {})
        assets = about.get("userProps", {}).get("assets", {})
        stats = state.get("stats", {}).get("profileStatistics", {})
        dashboard = state.get("dashboard", {})

        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "visible": not bool(keep.get("isAdHidden", 0)),
            "available": avail.get("selected", "unknown"),
            "availability_countdown": avail.get("countdown", 0),
            "views": stats.get("totalPageViews"),
            "contact_clicks": stats.get("totalContactClicks"),
            "new_visits": keep.get("newVisits"),
            "new_emails": keep.get("newEmails"),
            "online_bookmarks": dashboard.get("onlineBookmarks"),
            "headline": assets.get("headline"),
            "description_len": len(assets.get("description", "")),
            "review_url": dashboard.get("reviewUrl"),
            "is_frozen": keep.get("isFrozen"),
            "is_ad_hidden": keep.get("isAdHidden"),
        }
        write_receipt("audit_v1", "audit", {}, report, verified=True)
        return report

    def guard(self) -> dict:
        """Fix low-risk operational issues only."""
        state = snapshot_state(self.api)
        save_snapshot(state)

        # Visibility guard
        visible_ok = ensure_visible(self.api)

        # Availability guard
        avail_status = check_availability(self.api)
        if avail_status["needs_refresh"]:
            refresh_availability(self.api)
            avail_status = check_availability(self.api)

        # Stats snapshot
        collect_snapshot(self.api)

        write_receipt("guard_cycle_v1", "guard", {}, {
            "visible_ok": visible_ok,
            "availability": avail_status,
        }, verified=True)

        return {
            "visible_ok": visible_ok,
            "availability": avail_status,
        }

    def draft(self) -> dict:
        """Generate content drafts. Do not publish."""
        return run_daily_draft_cycle(self.api)

    def run_cycle(self):
        """One daemon cycle."""
        now = time.time()
        if not self.auth.is_authenticated():
            log.info("Session not authenticated. Re-logging in...")
            if not self.login():
                log.error("Could not re-authenticate. Sleeping.")
                return

        # Always guard
        result = self.guard()
        self.last_check = now

        # Availability check every 30 min
        if now - self.last_availability_check >= AVAILABILITY_CHECK_INTERVAL:
            self.last_availability_check = now

        # Daily draft
        if now - self.last_daily_draft >= DAILY_DRAFT_INTERVAL:
            if self.mode != "guard":
                bio_drafts = run_daily_draft_cycle(self.api)
                blog_drafts = generate_blog_drafts(count=1)
                save_blog_drafts_to_disk(blog_drafts)
                interview_drafts = generate_interview_drafts()
                monitor_interview(self.api)
                log.info("Daily drafts: bio=%s blog=%s interview=%s",
                         bio_drafts.get("bio_draft")["variant_id"] if bio_drafts.get("bio_draft") else None,
                         [d["variant_id"] for d in blog_drafts],
                         [d["variant_id"] for d in interview_drafts])
            self.last_daily_draft = now

    def run(self):
        log.info("=== RM ProfileOps Daemon starting in %s mode ===", self.mode)
        if not self.login():
            log.error("Initial login failed")
            return

        if self.mode == "audit":
            print(json.dumps(self.audit(), indent=2, default=str))
            return

        if self.mode == "guard":
            print(json.dumps(self.guard(), indent=2, default=str))
            return

        if self.mode == "draft":
            print(json.dumps(self.draft(), indent=2, default=str))
            return

        while self.running:
            try:
                self.run_cycle()
            except KeyboardInterrupt:
                log.info("Shutdown requested")
                self.running = False
                break
            except Exception as e:
                log.error("Cycle error: %s", e)
                write_receipt("daemon_error_v1", "error", {}, {"error": str(e)}, verified=False)
            time.sleep(CHECK_INTERVAL)

        log.info("Daemon stopped")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    parser = argparse.ArgumentParser(description="RM ProfileOps Daemon")
    parser.add_argument("mode", choices=["audit", "guard", "draft", "daemon"], default="audit", nargs="?")
    parser.add_argument("--city", default="manhattan-ny")
    parser.add_argument("--session", default="rm_traffic/session.json")
    args = parser.parse_args()

    init_db()
    daemon = ProfileOpsDaemon(mode=args.mode, city=args.city, session_file=args.session)
    daemon.run()
