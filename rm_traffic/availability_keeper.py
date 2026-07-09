"""
RM Availability Keeper — standalone 24/7 daemon.

Keeps the profile "Available" at all times. Re-authenticates automatically.
Refreshes availability before expiry. Handles session drops.

Usage:
    python3 -m rm_traffic.availability_keeper              # 24/7 daemon
    python3 -m rm_traffic.availability_keeper --once       # single check + refresh
    python3 -m rm_traffic.availability_keeper --status     # show current state
"""

import argparse
import json
import logging
import os
import signal
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

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

log = logging.getLogger("availability_keeper")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(str(Path(__file__).parent / "availability_keeper.log")),
    ],
)

KEEPER_DB = Path(__file__).parent / "availability_keeper.db"
SESSION_FILE = str(Path(__file__).parent / "session.json")

# Refresh when less than this many seconds remain
REFRESH_THRESHOLD_SEC = 30 * 60  # 30 min before expiry
# How often to check (when availability is far from expiring)
CHECK_INTERVAL_SEC = 5 * 60      # 5 min
# Max duration index (5 = 6 hours, the longest for "Available")
MAX_DURATION = 5


def _db():
    conn = sqlite3.connect(str(KEEPER_DB))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    conn = _db()
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS availability_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        action TEXT NOT NULL,
        option INTEGER,
        duration INTEGER,
        remaining_sec INTEGER,
        success INTEGER DEFAULT 1,
        detail TEXT
    );
    """)
    conn.commit()
    conn.close()


def _log(action: str, option: int = None, duration: int = None,
         remaining: int = None, success: bool = True, detail: str = ""):
    ts = datetime.now(timezone.utc).isoformat()
    conn = _db()
    conn.execute(
        "INSERT INTO availability_log (ts, action, option, duration, remaining_sec, success, detail) VALUES (?,?,?,?,?,?,?)",
        (ts, action, option, duration, remaining, int(success), detail[:200])
    )
    conn.commit()
    conn.close()


class AvailabilityKeeper:
    def __init__(self):
        self.api = RentMasseurAPI(min_request_interval=2.0)
        self.auth = AuthSession(self.api, session_file=SESSION_FILE)
        self.username = os.environ.get("RM_USER", "")
        self.password = os.environ.get("RM_PASS", "")
        self.running = True
        self.last_login = 0
        self.consecutive_failures = 0

    def login(self) -> bool:
        if not self.username or not self.password:
            log.error("RM_USER / RM_PASS not set")
            return False
        ok = self.auth.login(self.username, self.password)
        if ok:
            self.last_login = time.time()
            self.consecutive_failures = 0
            _log("login", success=True, detail=f"logged in as {self.username}")
            log.info("Login OK as %s", self.username)
        else:
            self.consecutive_failures += 1
            _log("login", success=False, detail=f"login failed (attempt {self.consecutive_failures})")
            log.error("Login failed (attempt %d)", self.consecutive_failures)
        return ok

    def ensure_session(self) -> bool:
        # Re-login if > 50 min since last login
        if time.time() - self.last_login > 3000:
            log.info("Session aging, re-logging in...")
            return self.login()
        # Test session with a lightweight call
        try:
            self.api.get_keeponline()
            return True
        except Exception as e:
            log.warning("Session check failed (%s), re-logging in...", str(e)[:60])
            return self.login()

    def get_remaining_sec(self, avail: dict) -> int:
        countdown = avail.get("countdown", 0)
        if not countdown:
            return 0
        remaining = int(countdown - time.time())
        return max(0, remaining)

    def check_and_refresh(self) -> dict:
        """Check availability. Refresh if not Available or near expiry."""
        result = {"action": "noop", "refreshed": False, "remaining": 0, "detail": ""}

        if not self.ensure_session():
            result["detail"] = "auth failed"
            return result

        try:
            avail = self.api.get_availability()
        except Exception as e:
            log.error("get_availability failed: %s", e)
            # Try re-login once
            if self.login():
                try:
                    avail = self.api.get_availability()
                except Exception as e2:
                    result["detail"] = f"get_availability failed after relogin: {e2}"
                    _log("check", success=False, detail=result["detail"])
                    return result
            else:
                result["detail"] = "relogin failed"
                _log("check", success=False, detail=result["detail"])
                return result

        option = avail.get("selected", "")
        remaining = self.get_remaining_sec(avail)

        log.info("Availability: %s, remaining=%ds (%.1fh)", option, remaining, remaining / 3600)

        needs_refresh = False
        reason = ""

        if option != "Available":
            needs_refresh = True
            reason = f"not Available (was: {option})"
        elif remaining < REFRESH_THRESHOLD_SEC:
            needs_refresh = True
            reason = f"expiring soon ({remaining}s left, threshold {REFRESH_THRESHOLD_SEC}s)"

        if not needs_refresh:
            result["remaining"] = remaining
            result["detail"] = f"OK: {option}, {remaining}s left"
            _log("check", option=1 if option == "Available" else 0, remaining=remaining, success=True, detail=result["detail"])
            return result

        # Refresh
        log.info("Refreshing availability: %s", reason)
        try:
            self.api.set_availability(option=1, duration=MAX_DURATION)
            result["action"] = "refresh"
            result["refreshed"] = True
            result["detail"] = f"set to Available for 6h ({reason})"
            _log("refresh", option=1, duration=MAX_DURATION, remaining=remaining, success=True, detail=result["detail"])
            log.info("◆ Refreshed: set to Available (6h)")

            # Verify
            time.sleep(2)
            try:
                after = self.api.get_availability()
                after_remaining = self.get_remaining_sec(after)
                result["remaining"] = after_remaining
                if after.get("selected") == "Available":
                    log.info("Verified: Available, %ds remaining", after_remaining)
                else:
                    log.warning("Verify mismatch: selected=%s", after.get("selected"))
            except Exception as e:
                log.warning("Verify check failed: %s", e)

        except Exception as e:
            result["detail"] = f"refresh failed: {e}"
            _log("refresh", option=1, duration=MAX_DURATION, remaining=remaining, success=False, detail=str(e)[:200])
            log.error("Refresh failed: %s", e)

            # Try re-login and one more attempt
            if self.consecutive_failures < 3:
                log.info("Retrying after relogin...")
                if self.login():
                    try:
                        self.api.set_availability(option=1, duration=MAX_DURATION)
                        result["refreshed"] = True
                        result["detail"] = f"set to Available on retry"
                        _log("refresh_retry", option=1, duration=MAX_DURATION, success=True, detail="retry success")
                        log.info("◆ Refreshed on retry")
                    except Exception as e2:
                        log.error("Retry also failed: %s", e2)
                        _log("refresh_retry", success=False, detail=str(e2)[:200])

        return result

    def run_forever(self):
        log.info("═══ AVAILABILITY KEEPER STARTING ═══")
        log.info("User: %s", self.username)
        log.info("Check interval: %ds", CHECK_INTERVAL_SEC)
        log.info("Refresh threshold: %ds before expiry", REFRESH_THRESHOLD_SEC)
        log.info("Max duration: 6h (index %d)", MAX_DURATION)

        if not self.login():
            log.error("Initial login failed. Exiting.")
            sys.exit(1)

        # Set up signal handler for clean shutdown
        def handle_sigterm(sig, frame):
            log.info("Received signal %d, shutting down...", sig)
            self.running = False
        signal.signal(signal.SIGINT, handle_sigterm)
        signal.signal(signal.SIGTERM, handle_sigterm)

        while self.running:
            try:
                self.check_and_refresh()
            except Exception as e:
                log.error("Cycle error: %s", e)
                _log("cycle_error", success=False, detail=str(e)[:200])
                # Backoff on repeated failures
                if self.consecutive_failures > 5:
                    log.error("Too many failures, backing off 10 min...")
                    time.sleep(600)
                    self.consecutive_failures = 0

            # Sleep in small increments so signal handler can interrupt
            slept = 0
            while slept < CHECK_INTERVAL_SEC and self.running:
                time.sleep(5)
                slept += 5

        log.info("Availability keeper stopped.")

    def run_once(self):
        log.info("═══ AVAILABILITY KEEPER (single run) ═══")
        if not self.login():
            sys.exit(1)
        result = self.check_and_refresh()
        print(json.dumps(result, indent=2))
        return result

    def show_status(self):
        log.info("═══ AVAILABILITY KEEPER STATUS ═══")
        if not self.login():
            sys.exit(1)
        try:
            avail = self.api.get_availability()
            remaining = self.get_remaining_sec(avail)
            keep = self.api.get_keeponline()

            print(f"\n  {'='*50}")
            print(f"  AVAILABILITY KEEPER STATUS")
            print(f"  {'='*50}")
            print(f"  User:         {self.username}")
            print(f"  Available:    {avail.get('selected', '?')}")
            print(f"  Remaining:    {remaining}s ({remaining/3600:.1f}h)")
            print(f"  Hidden:       {'YES' if keep.get('isAdHidden') else 'NO'}")
            print(f"  New visits:   {keep.get('newVisits', '?')}")
            print(f"  New emails:   {keep.get('newEmails', '?')}")
            print(f"  {'='*50}")

            # Show recent log
            conn = _db()
            rows = conn.execute(
                "SELECT * FROM availability_log ORDER BY id DESC LIMIT 10"
            ).fetchall()
            conn.close()
            if rows:
                print(f"\n  Recent actions:")
                for r in rows:
                    glyph = "◆" if r["success"] else "⟁"
                    print(f"    {glyph} {r['ts'][:19]}  {r['action']:12s}  {r['detail'][:50]}")
            print()
        except Exception as e:
            log.error("Status check failed: %s", e)
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="RM Availability Keeper — 24/7 availability daemon")
    parser.add_argument("--once", action="store_true", help="Single check + refresh")
    parser.add_argument("--status", action="store_true", help="Show current availability status")
    parser.add_argument("--check-interval", type=int, default=CHECK_INTERVAL_SEC, help="Seconds between checks (default: 300)")
    args = parser.parse_args()

    init_db()
    keeper = AvailabilityKeeper()
    keeper.check_interval = args.check_interval

    if args.status:
        keeper.show_status()
        return

    if args.once:
        keeper.run_once()
        return

    keeper.run_forever()


if __name__ == "__main__":
    main()
