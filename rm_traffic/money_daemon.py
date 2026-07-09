"""
Money-Making 24/7 Daemon — continuous revenue optimization loop.

Combines:
  1. Profile visibility guard (unhide if hidden → clients find you)
  2. Availability auto-refresh (stay "Available" → appear in search)
  3. Stats collection (views, contacts, emails → track conversion)
  4. Search rank monitoring (know your position in Manhattan)
  5. ML training loop (retrain money model every 6h → better bio predictions)
  6. Bio A/B testing (rotate bio every 24h → higher CTR → more bookings)
  7. Selenium verification (verify search visibility every 30min)
  8. Live dashboard (print revenue metrics to terminal)

The loop never stops. It handles crashes, re-auths, and writes receipts.

Usage:
    python3 -m rm_traffic.money_daemon

Credentials read from .env file or environment variables.
"""

import json
import logging
import os
import signal
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import numpy as np

CYCLE_TIMEOUT = 120  # max seconds per cycle before watchdog kills it

# Load .env
ENV_PATH = Path(__file__).parent.parent / ".env"
if ENV_PATH.exists():
    for line in open(ENV_PATH):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

os.environ.setdefault("RM_USER", os.environ.get("RENTMASSEUR_USER", ""))
os.environ.setdefault("RM_PASS", os.environ.get("RENTMASSEUR_PASS", ""))

from .api_client import RentMasseurAPI
from .auth import AuthSession
from .db import init_db, write_receipt, write_traffic_snapshot, get_latest_traffic_snapshot
from .visibility_guard import ensure_visible
from .availability_guard import check_availability, refresh_availability
from .stats_collector import collect_snapshot
from .search_rank import check_search_rank
from .content_optimizer import run_daily_draft_cycle
from .bio_ml_trainer import MLP
from .bio_appraiser import load_bios
from .money_training_selenium import build_money_dataset, predict_top_bios, selenium_verify_search

log = logging.getLogger("money.daemon")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Path(__file__).parent / "data" / "money_daemon.log"),
    ],
)

# Intervals (seconds)
CYCLE_INTERVAL = 5 * 60           # 5 min — main loop
AVAIL_REFRESH_THRESHOLD = 45 * 60 # refresh if < 45 min left
STATS_INTERVAL = 15 * 60          # 15 min
SEARCH_RANK_INTERVAL = 60 * 60    # 60 min
ML_RETRAIN_INTERVAL = 6 * 60 * 60 # 6 hours
BIO_TEST_INTERVAL = 24 * 60 * 60  # 24 hours
SELENIUM_INTERVAL = 30 * 60       # 30 min

BIOS_PATH = Path(__file__).parent / "data" / "real_bios_with_views.jsonl"
MODEL_PATH = Path(__file__).parent / "data" / "models" / "money_mlp.pkl"
DASHBOARD_PATH = Path(__file__).parent / "data" / "money_dashboard.json"


class MoneyDaemon:
    def __init__(self):
        self.api = RentMasseurAPI(min_request_interval=2.0)
        self.auth = AuthSession(self.api, session_file="rm_traffic/session.json")
        self.running = True
        self.cycle_count = 0
        self.start_time = time.time()

        # Timers
        self.last_stats = 0
        self.last_search_rank = 0
        self.last_ml_retrain = 0
        self.last_bio_test = 0
        self.last_selenium = 0
        self.last_avail_check = 0

        # State
        self.current_stats = {}
        self.search_position = None
        self.ml_model = None
        self.ml_summary = {}
        self.top_bios = []
        self.selenium_status = "pending"
        self.total_revenue_signals = 0
        self.total_actions = 0
        self.total_receipts = 0
        self.errors = 0
        self.last_error = ""

        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        log.info("Shutdown signal %d received. Finishing cycle...", signum)
        self.running = False

    def login(self) -> bool:
        try:
            ok = self.auth.login()
            if ok:
                log.info("Authenticated as %s", self.auth.username or "karpathianwolf")
            else:
                log.warning("Auth failed — running in offline mode (ML + Selenium only)")
            return ok
        except Exception as e:
            log.warning("Auth error: %s — offline mode", e)
            return False

    def run(self):
        log.info("=" * 60)
        log.info("MONEY-MAKING DAEMON — 24/7 REVENUE OPTIMIZATION")
        log.info("=" * 60)

        init_db()
        self.login()

        # Initial ML training
        self._retrain_ml()

        while self.running:
            cycle_done = threading.Event()
            cycle_error = [None]

            def _run_cycle():
                try:
                    self._cycle()
                except Exception as e:
                    cycle_error[0] = e
                finally:
                    cycle_done.set()

            t = threading.Thread(target=_run_cycle, daemon=True)
            t.start()
            t.join(timeout=CYCLE_TIMEOUT)

            if not cycle_done.is_set():
                log.error("⚠ Cycle %d TIMED OUT after %ds — killing thread", self.cycle_count, CYCLE_TIMEOUT)
                self.errors += 1
                self.last_error = f"cycle_timeout_{CYCLE_TIMEOUT}s"
                # Thread is daemon, will be abandoned. Continue.
            elif cycle_error[0]:
                self.errors += 1
                self.last_error = str(cycle_error[0])
                log.error("Cycle %d error: %s", self.cycle_count, cycle_error[0])
                traceback.print_exc()
                write_receipt("daemon_error_v1", "cycle_error", {},
                              {"error": str(cycle_error[0]), "cycle": self.cycle_count}, verified=False)

            # Sleep between cycles — flush stdout so logs appear in nohup file
            for _ in range(CYCLE_INTERVAL):
                if not self.running:
                    break
                time.sleep(1)
            sys.stdout.flush()
            sys.stderr.flush()

        self._print_final_report()
        log.info("Daemon stopped after %d cycles, %d actions, %d receipts",
                 self.cycle_count, self.total_actions, self.total_receipts)

    def _cycle(self):
        self.cycle_count += 1
        now = time.time()
        log.info("")
        log.info("━" * 50)
        log.info("Cycle %d | Uptime: %s | Actions: %d | Receipts: %d",
                 self.cycle_count, self._uptime(), self.total_actions, self.total_receipts)
        log.info("━" * 50)

        # Re-auth if needed (with timeout)
        try:
            authed = self.auth.is_authenticated()
        except Exception:
            authed = False
        if not authed:
            log.info("Session expired. Re-authenticating...")
            self.login()

        # 1. Visibility guard (every cycle)
        if self.auth.api.logged_in:
            try:
                visible_ok = ensure_visible(self.api)
                self.total_actions += 1
                self.total_receipts += 1
                if visible_ok:
                    log.info("◉ Visibility: OK")
                else:
                    log.warning("⟁ Visibility: REPAIRING")
            except Exception as e:
                log.warning("Visibility check failed: %s", e)

        # 2. Availability guard (every cycle)
        if self.auth.api.logged_in and (now - self.last_avail_check >= 5 * 60):
            self.last_avail_check = now
            try:
                avail = check_availability(self.api)
                self.total_receipts += 1
                if avail.get("needs_refresh"):
                    log.info("⌁ Refreshing availability...")
                    refresh_availability(self.api)
                    self.total_actions += 1
                    self.total_receipts += 1
                    log.info("◆ Availability refreshed")
                else:
                    remaining = avail.get("remaining_seconds", 0)
                    log.info("◉ Availability: %s (%d min left)",
                             avail.get("selected"), remaining // 60)
            except Exception as e:
                log.warning("Availability check failed: %s", e)

        # 3. Stats collection (every 15 min)
        if self.auth.api.logged_in and (now - self.last_stats >= STATS_INTERVAL):
            self.last_stats = now
            try:
                snapshot = collect_snapshot(self.api)
                self.current_stats = snapshot
                self.total_receipts += 1
                views = snapshot.get("profile_views", 0)
                clicks = snapshot.get("contact_clicks", 0)
                visits = snapshot.get("new_visits", 0)
                emails = snapshot.get("new_emails", 0)
                ctr = (clicks / views * 100) if views else 0
                log.info("◍ Stats: views=%s contacts=%s visits=%s emails=%s ctr=%.2f%%",
                         views, clicks, visits, emails, ctr)
                if visits or emails:
                    self.total_revenue_signals += visits + emails
                    log.info("▲ Revenue signals: +%d (total: %d)",
                             visits + emails, self.total_revenue_signals)
            except Exception as e:
                log.warning("Stats collection failed: %s", e)

        # 4. Search rank (every 60 min)
        if self.auth.api.logged_in and (now - self.last_search_rank >= SEARCH_RANK_INTERVAL):
            self.last_search_rank = now
            try:
                rank = check_search_rank(self.api, "karpathianwolf", city="manhattan-ny")
                self.search_position = rank.get("position")
                self.total_receipts += 1
                if rank.get("found"):
                    log.info("◆ Search rank: #%d/%d in Manhattan",
                             rank["position"], rank.get("total", 0))
                else:
                    log.warning("⟁ Not found in search results")
            except Exception as e:
                log.warning("Search rank check failed: %s", e)

        # 5. ML retraining (every 6 hours)
        if now - self.last_ml_retrain >= ML_RETRAIN_INTERVAL:
            self._retrain_ml()

        # 6. Bio A/B test (every 24 hours)
        if self.auth.api.logged_in and (now - self.last_bio_test >= BIO_TEST_INTERVAL):
            self.last_bio_test = now
            try:
                log.info("⌁ Running daily bio A/B test cycle...")
                result = run_daily_draft_cycle(self.api)
                self.total_actions += 1
                self.total_receipts += 1
                draft = result.get("bio_draft")
                if draft:
                    log.info("◆ Bio draft created: %s (score: %s)",
                             draft.get("variant_id"),
                             draft.get("hypothesis", "")[:60])
                else:
                    log.info("No bio change needed (too soon or no better variant)")
            except Exception as e:
                log.warning("Bio A/B test failed: %s", e)

        # 7. Selenium verification (every 30 min)
        if now - self.last_selenium >= SELENIUM_INTERVAL:
            self.last_selenium = now
            try:
                log.info("◉ Selenium verification...")
                sel = selenium_verify_search()
                self.selenium_status = sel.get("selenium_status", "unknown")
                cards = sel.get("total_found", 0)
                links = sel.get("total_profile_links", 0)
                log.info("◆ Selenium: %s (%d cards, %d links, %.1fs)",
                         self.selenium_status, cards, links,
                         sel.get("page_load_time", 0))
            except Exception as e:
                log.warning("Selenium verification failed: %s", e)
                self.selenium_status = "fail"

        # 8. Update dashboard
        self._update_dashboard()

        # Print mini dashboard
        self._print_mini_dashboard()

    def _retrain_ml(self):
        self.last_ml_retrain = time.time()
        try:
            log.info("⟡ ML retraining: 30 epochs on bio dataset...")
            from .money_training_selenium import train_money_model
            bios = load_bios(BIOS_PATH, limit=5000)
            if bios:
                model, summary = train_money_model(bios, epochs=30)
                self.ml_model = model
                self.ml_summary = summary
                self.top_bios = predict_top_bios(model, bios, top_n=10)
                self.total_receipts += 1
                log.info("◆ ML retrained: R²=%.4f MAE=%.6f reward=%.2f",
                         summary["final_r2"], summary["final_mae"],
                         summary["money_reward_final"])
                if self.top_bios:
                    log.info("  Top bio: %s (ctr=%.4f score=%.2f)",
                             self.top_bios[0]["username"],
                             self.top_bios[0]["predicted_ctr"],
                             self.top_bios[0]["money_score"])
        except Exception as e:
            log.warning("ML retraining failed: %s", e)

    def _uptime(self) -> str:
        secs = int(time.time() - self.start_time)
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        return f"{h}h{m}m{s}s"

    def _update_dashboard(self):
        dashboard = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": int(time.time() - self.start_time),
            "cycle_count": self.cycle_count,
            "authenticated": self.auth.api.logged_in,
            "current_stats": self.current_stats,
            "search_position": self.search_position,
            "selenium_status": self.selenium_status,
            "ml_summary": {
                "r2": self.ml_summary.get("final_r2"),
                "mae": self.ml_summary.get("final_mae"),
                "money_reward": self.ml_summary.get("money_reward_final"),
            } if self.ml_summary else None,
            "top_bios": self.top_bios[:3],
            "total_revenue_signals": self.total_revenue_signals,
            "total_actions": self.total_actions,
            "total_receipts": self.total_receipts,
            "errors": self.errors,
            "last_error": self.last_error,
        }
        DASHBOARD_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DASHBOARD_PATH, "w") as f:
            json.dump(dashboard, f, indent=2, default=str)

    def _print_mini_dashboard(self):
        views = self.current_stats.get("profile_views", "—")
        clicks = self.current_stats.get("contact_clicks", "—")
        visits = self.current_stats.get("new_visits", "—")
        emails = self.current_stats.get("new_emails", "—")
        pos = self.search_position or "—"
        r2 = self.ml_summary.get("final_r2", "—") if self.ml_summary else "—"

        log.info("")
        log.info("┌─────────────────────────────────────────────┐")
        log.info("│  ◉◆⌁  MONEY DASHBOARD — Cycle %d  │", self.cycle_count)
        log.info("├─────────────────────────────────────────────┤")
        log.info("│  Uptime:     %s", self._uptime())
        log.info("│  Auth:       %s", "◉ logged in" if self.auth.api.logged_in else "◌ offline")
        log.info("│  Views:      %s", views)
        log.info("│  Contacts:   %s", clicks)
        log.info("│  New visits: %s", visits)
        log.info("│  New emails: %s", emails)
        log.info("│  Search pos: #%s in Manhattan", pos)
        log.info("│  Selenium:   %s", self.selenium_status)
        log.info("│  ML R²:      %s", f"{r2:.4f}" if isinstance(r2, float) else r2)
        log.info("│  Rev signals: %d", self.total_revenue_signals)
        log.info("│  Actions:    %d | Receipts: %d | Errors: %d",
                 self.total_actions, self.total_receipts, self.errors)
        log.info("└─────────────────────────────────────────────┘")

    def _print_final_report(self):
        log.info("")
        log.info("=" * 60)
        log.info("FINAL REPORT")
        log.info("=" * 60)
        log.info("Uptime:          %s", self._uptime())
        log.info("Cycles:          %d", self.cycle_count)
        log.info("Total actions:   %d", self.total_actions)
        log.info("Total receipts:  %d", self.total_receipts)
        log.info("Revenue signals: %d", self.total_revenue_signals)
        log.info("Errors:          %d", self.errors)
        log.info("ML R²:           %s", self.ml_summary.get("final_r2", "—"))
        log.info("Dashboard:       %s", DASHBOARD_PATH)
        log.info("=" * 60)


def main():
    daemon = MoneyDaemon()
    daemon.run()


if __name__ == "__main__":
    main()
