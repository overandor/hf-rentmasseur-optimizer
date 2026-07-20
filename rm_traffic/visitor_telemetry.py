#!/usr/bin/env python3
"""
RentMasseur visitor telemetry and reciprocal-visit pipeline.

This module uses only information exposed to the authenticated account or on
the visitor's visible profile. It does not bypass challenges, infer hidden
location, store message bodies, or send messages.

Capabilities:
- discover profiles listed on the authenticated "Who Saw Me" page
- record when each profile appeared and how often it was observed
- perform bounded reciprocal profile visits with a configurable cooldown
- detect visible contact and message controls
- record profile-stated location and New York membership
- observe online/last-online indicators
- infer session lengths and typical online hours from repeated observations
- render a local HTML dashboard and JSON export
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import os
import re
import sqlite3
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from zoneinfo import ZoneInfo

from rm_traffic.api_client import RentMasseurAPI

try:
    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException, WebDriverException
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
except ImportError:  # pragma: no cover
    webdriver = None
    TimeoutException = WebDriverException = Exception
    Options = By = EC = WebDriverWait = None

LOG = logging.getLogger("rm_visitor_telemetry")
BASE_URL = "https://rentmasseur.com"
NY_TZ = ZoneInfo("America/New_York")
DEFAULT_DB = Path(os.environ.get("RM_VISITOR_DB", Path(__file__).resolve().parent.parent / "data" / "rm_visitor_telemetry.sqlite3"))
DEFAULT_OUTPUT = Path(os.environ.get("RM_VISITOR_OUTPUT", Path(__file__).resolve().parent.parent / "output"))
DEFAULT_PROFILE_DIR = Path(os.environ.get("RM_VISITOR_CHROME_PROFILE", "/tmp/rm_visitor_telemetry_chrome"))
PROFILE_PATH_EXCLUSIONS = {"", "settings", "login", "logout", "about", "contact", "privacy", "terms", "help", "blog", "blogs", "topics", "stream", "advertise", "api", "gay-massage", "masseurcams", "sitemap", "robots", "build-stream"}
NYC_TOKENS = {"new york", "new york city", "nyc", "manhattan", "brooklyn", "queens", "bronx", "staten island", "harlem", "chelsea", "midtown", "soho", "tribeca", "upper east side", "upper west side", "hell's kitchen", "williamsburg", "astoria", "long island city", "flushing", "jamaica", "forest hills", "washington heights", "greenpoint", "bushwick"}
NY_STATE_TOKENS = NYC_TOKENS | {"new york state", "long island", "nassau", "suffolk", "westchester", "yonkers", "white plains", "new rochelle", "mount vernon", "buffalo", "rochester", "albany", "syracuse", "utica", "troy", "poughkeepsie"}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def normalize_space(value: Any) -> str:
    return " ".join(str(value or "").split())


def stable_hash(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def normalize_location(location: str) -> Tuple[str, str, bool, bool]:
    text = normalize_space(location)
    lower = re.sub(r"[^a-z0-9\s,'-]", " ", text.casefold())
    parts = [p.strip() for p in re.split(r"[,|/]", lower) if p.strip()]
    city = parts[0].title() if parts else ""
    state = "NY" if re.search(r"\bny\b", lower) or "new york" in lower else ""
    in_nyc = any(token in lower for token in NYC_TOKENS)
    in_new_york = in_nyc or state == "NY" or any(token in lower for token in NY_STATE_TOKENS)
    return city, state, in_nyc, in_new_york


def parse_datetime_hint(text: str, datetime_attr: str = "") -> Optional[datetime]:
    explicit = parse_iso(datetime_attr)
    if explicit:
        return explicit
    value = normalize_space(text).casefold()
    if not value:
        return None
    now = utc_now()
    for pattern, unit in [(r"(\d+)\s*min", "minutes"), (r"(\d+)\s*hour", "hours"), (r"(\d+)\s*day", "days"), (r"(\d+)\s*week", "weeks")]:
        match = re.search(pattern, value)
        if match and ("ago" in value or "last" in value):
            return now - timedelta(**{unit: int(match.group(1))})
    if "just now" in value or "online now" in value or value == "online" or "today" in value:
        return now
    if "yesterday" in value:
        return now - timedelta(days=1)
    return None


def flatten_payload(payload: Any, prefix: str = "") -> Iterable[Tuple[str, Any]]:
    if isinstance(payload, dict):
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path, value
            yield from flatten_payload(value, path)
    elif isinstance(payload, list):
        for index, value in enumerate(payload[:20]):
            path = f"{prefix}[{index}]"
            yield path, value
            yield from flatten_payload(value, path)


def first_matching_value(payload: Dict[str, Any], keys: Sequence[str]) -> Any:
    wanted = tuple(k.casefold() for k in keys)
    for path, value in flatten_payload(payload):
        leaf = path.rsplit(".", 1)[-1].casefold()
        if any(token == leaf or token in leaf for token in wanted) and value not in (None, "", [], {}):
            return value
    return None


def bool_from_value(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = normalize_space(value).casefold()
    if text in {"true", "yes", "1", "online", "active", "available"}:
        return True
    if text in {"false", "no", "0", "offline", "inactive", "unavailable"}:
        return False
    return None


@dataclass
class VisitorSeed:
    username: str
    profile_url: str
    visitor_text: str = ""
    visitor_datetime: str = ""
    source_last_visit_at: Optional[str] = None


@dataclass
class ProfileObservation:
    username: str
    profile_url: str
    observed_at: str
    source_last_visit_at: Optional[str] = None
    source_visit_text: str = ""
    location_text: str = ""
    city: str = ""
    state: str = ""
    in_nyc: bool = False
    in_new_york: bool = False
    is_online: Optional[bool] = None
    online_text: str = ""
    last_online_at: Optional[str] = None
    has_contact_link: bool = False
    contact_kinds: List[str] = field(default_factory=list)
    has_message_control: bool = False
    prior_contact: bool = False
    can_message: bool = False
    reciprocal_visit_performed: bool = False
    reported_visit_count: Optional[int] = None
    page_title: str = ""
    profile_hash: str = ""
    raw_summary: Dict[str, Any] = field(default_factory=dict)
    error: str = ""


class TelemetryStore:
    def __init__(self, path: Path = DEFAULT_DB):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    def close(self) -> None:
        self.conn.close()

    def _init_schema(self) -> None:
        self.conn.executescript("""
        CREATE TABLE IF NOT EXISTS scan_runs (id INTEGER PRIMARY KEY AUTOINCREMENT, started_at TEXT NOT NULL, ended_at TEXT, status TEXT NOT NULL, discovered_count INTEGER NOT NULL DEFAULT 0, scanned_count INTEGER NOT NULL DEFAULT 0, ny_count INTEGER NOT NULL DEFAULT 0, online_count INTEGER NOT NULL DEFAULT 0, contactable_count INTEGER NOT NULL DEFAULT 0, reciprocal_visits INTEGER NOT NULL DEFAULT 0, errors_json TEXT NOT NULL DEFAULT '[]', receipt_hash TEXT);
        CREATE TABLE IF NOT EXISTS profiles (username TEXT PRIMARY KEY, profile_url TEXT NOT NULL, first_seen_at TEXT NOT NULL, last_seen_at TEXT NOT NULL, source_last_visit_at TEXT, source_visit_text TEXT NOT NULL DEFAULT '', observed_visitor_runs INTEGER NOT NULL DEFAULT 0, reported_visit_count INTEGER, reciprocal_visits INTEGER NOT NULL DEFAULT 0, last_reciprocal_visit_at TEXT, location_text TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '', in_nyc INTEGER NOT NULL DEFAULT 0, in_new_york INTEGER NOT NULL DEFAULT 0, is_online INTEGER, online_text TEXT NOT NULL DEFAULT '', last_online_at TEXT, average_online_seconds REAL, median_online_seconds REAL, usual_online_hours_json TEXT NOT NULL DEFAULT '[]', has_contact_link INTEGER NOT NULL DEFAULT 0, contact_kinds_json TEXT NOT NULL DEFAULT '[]', has_message_control INTEGER NOT NULL DEFAULT 0, prior_contact INTEGER NOT NULL DEFAULT 0, can_message INTEGER NOT NULL DEFAULT 0, page_title TEXT NOT NULL DEFAULT '', profile_hash TEXT NOT NULL DEFAULT '', last_error TEXT NOT NULL DEFAULT '');
        CREATE TABLE IF NOT EXISTS observations (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, username TEXT NOT NULL, observed_at TEXT NOT NULL, source_last_visit_at TEXT, source_visit_text TEXT NOT NULL DEFAULT '', location_text TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT '', in_nyc INTEGER NOT NULL DEFAULT 0, in_new_york INTEGER NOT NULL DEFAULT 0, is_online INTEGER, online_text TEXT NOT NULL DEFAULT '', last_online_at TEXT, has_contact_link INTEGER NOT NULL DEFAULT 0, contact_kinds_json TEXT NOT NULL DEFAULT '[]', has_message_control INTEGER NOT NULL DEFAULT 0, prior_contact INTEGER NOT NULL DEFAULT 0, can_message INTEGER NOT NULL DEFAULT 0, reciprocal_visit_performed INTEGER NOT NULL DEFAULT 0, reported_visit_count INTEGER, page_title TEXT NOT NULL DEFAULT '', profile_hash TEXT NOT NULL DEFAULT '', raw_summary_json TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '', FOREIGN KEY(run_id) REFERENCES scan_runs(id), FOREIGN KEY(username) REFERENCES profiles(username));
        CREATE INDEX IF NOT EXISTS idx_observations_username_time ON observations(username, observed_at DESC);
        CREATE TABLE IF NOT EXISTS online_sessions (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL, started_at TEXT NOT NULL, last_observed_online_at TEXT NOT NULL, ended_at TEXT, duration_seconds REAL, is_open INTEGER NOT NULL DEFAULT 1, FOREIGN KEY(username) REFERENCES profiles(username));
        CREATE INDEX IF NOT EXISTS idx_sessions_username ON online_sessions(username, started_at DESC);
        """)
        self.conn.commit()

    def begin_run(self) -> int:
        cur = self.conn.execute("INSERT INTO scan_runs (started_at, status) VALUES (?, ?)", (iso(utc_now()), "running"))
        self.conn.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, status: str, metrics: Dict[str, int], errors: List[str]) -> str:
        receipt = {"run_id": run_id, "ended_at": iso(utc_now()), "status": status, **metrics, "errors": errors}
        receipt_hash = stable_hash(receipt)
        self.conn.execute("UPDATE scan_runs SET ended_at=?, status=?, discovered_count=?, scanned_count=?, ny_count=?, online_count=?, contactable_count=?, reciprocal_visits=?, errors_json=?, receipt_hash=? WHERE id=?", (receipt["ended_at"], status, metrics.get("discovered_count", 0), metrics.get("scanned_count", 0), metrics.get("ny_count", 0), metrics.get("online_count", 0), metrics.get("contactable_count", 0), metrics.get("reciprocal_visits", 0), json.dumps(errors), receipt_hash, run_id))
        self.conn.commit()
        return receipt_hash

    def last_reciprocal_visit(self, username: str) -> Optional[datetime]:
        row = self.conn.execute("SELECT last_reciprocal_visit_at FROM profiles WHERE username=?", (username,)).fetchone()
        return parse_iso(row["last_reciprocal_visit_at"]) if row else None

    def record(self, run_id: int, obs: ProfileObservation) -> None:
        prior = self.conn.execute("SELECT * FROM profiles WHERE username=?", (obs.username,)).fetchone()
        observed_runs = (prior["observed_visitor_runs"] if prior else 0) + 1
        reciprocal_visits = (prior["reciprocal_visits"] if prior else 0) + int(obs.reciprocal_visit_performed)
        last_reciprocal = obs.observed_at if obs.reciprocal_visit_performed else (prior["last_reciprocal_visit_at"] if prior else None)
        first_seen = prior["first_seen_at"] if prior else obs.observed_at
        self.conn.execute("""
        INSERT INTO profiles (username, profile_url, first_seen_at, last_seen_at, source_last_visit_at, source_visit_text, observed_visitor_runs, reported_visit_count, reciprocal_visits, last_reciprocal_visit_at, location_text, city, state, in_nyc, in_new_york, is_online, online_text, last_online_at, has_contact_link, contact_kinds_json, has_message_control, prior_contact, can_message, page_title, profile_hash, last_error)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(username) DO UPDATE SET profile_url=excluded.profile_url, last_seen_at=excluded.last_seen_at, source_last_visit_at=COALESCE(excluded.source_last_visit_at, profiles.source_last_visit_at), source_visit_text=CASE WHEN excluded.source_visit_text!='' THEN excluded.source_visit_text ELSE profiles.source_visit_text END, observed_visitor_runs=excluded.observed_visitor_runs, reported_visit_count=COALESCE(excluded.reported_visit_count, profiles.reported_visit_count), reciprocal_visits=excluded.reciprocal_visits, last_reciprocal_visit_at=COALESCE(excluded.last_reciprocal_visit_at, profiles.last_reciprocal_visit_at), location_text=CASE WHEN excluded.location_text!='' THEN excluded.location_text ELSE profiles.location_text END, city=CASE WHEN excluded.city!='' THEN excluded.city ELSE profiles.city END, state=CASE WHEN excluded.state!='' THEN excluded.state ELSE profiles.state END, in_nyc=CASE WHEN excluded.location_text!='' THEN excluded.in_nyc ELSE profiles.in_nyc END, in_new_york=CASE WHEN excluded.location_text!='' THEN excluded.in_new_york ELSE profiles.in_new_york END, is_online=COALESCE(excluded.is_online, profiles.is_online), online_text=CASE WHEN excluded.online_text!='' THEN excluded.online_text ELSE profiles.online_text END, last_online_at=COALESCE(excluded.last_online_at, profiles.last_online_at), has_contact_link=MAX(profiles.has_contact_link, excluded.has_contact_link), contact_kinds_json=CASE WHEN excluded.contact_kinds_json!='[]' THEN excluded.contact_kinds_json ELSE profiles.contact_kinds_json END, has_message_control=MAX(profiles.has_message_control, excluded.has_message_control), prior_contact=MAX(profiles.prior_contact, excluded.prior_contact), can_message=MAX(profiles.can_message, excluded.can_message), page_title=CASE WHEN excluded.page_title!='' THEN excluded.page_title ELSE profiles.page_title END, profile_hash=CASE WHEN excluded.profile_hash!='' THEN excluded.profile_hash ELSE profiles.profile_hash END, last_error=excluded.last_error
        """, (obs.username, obs.profile_url, first_seen, obs.observed_at, obs.source_last_visit_at, obs.source_visit_text, observed_runs, obs.reported_visit_count, reciprocal_visits, last_reciprocal, obs.location_text, obs.city, obs.state, int(obs.in_nyc), int(obs.in_new_york), None if obs.is_online is None else int(obs.is_online), obs.online_text, obs.last_online_at, int(obs.has_contact_link), json.dumps(obs.contact_kinds), int(obs.has_message_control), int(obs.prior_contact), int(obs.can_message), obs.page_title, obs.profile_hash, obs.error))
        self.conn.execute("INSERT INTO observations (run_id, username, observed_at, source_last_visit_at, source_visit_text, location_text, city, state, in_nyc, in_new_york, is_online, online_text, last_online_at, has_contact_link, contact_kinds_json, has_message_control, prior_contact, can_message, reciprocal_visit_performed, reported_visit_count, page_title, profile_hash, raw_summary_json, error) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (run_id, obs.username, obs.observed_at, obs.source_last_visit_at, obs.source_visit_text, obs.location_text, obs.city, obs.state, int(obs.in_nyc), int(obs.in_new_york), None if obs.is_online is None else int(obs.is_online), obs.online_text, obs.last_online_at, int(obs.has_contact_link), json.dumps(obs.contact_kinds), int(obs.has_message_control), int(obs.prior_contact), int(obs.can_message), int(obs.reciprocal_visit_performed), obs.reported_visit_count, obs.page_title, obs.profile_hash, json.dumps(obs.raw_summary, default=str), obs.error))
        self._update_session(obs)
        self._refresh_profile_session_stats(obs.username)
        self.conn.commit()

    def _update_session(self, obs: ProfileObservation) -> None:
        if obs.is_online is None:
            return
        current = self.conn.execute("SELECT * FROM online_sessions WHERE username=? AND is_open=1 ORDER BY id DESC LIMIT 1", (obs.username,)).fetchone()
        if obs.is_online:
            if current:
                self.conn.execute("UPDATE online_sessions SET last_observed_online_at=? WHERE id=?", (obs.observed_at, current["id"]))
            else:
                self.conn.execute("INSERT INTO online_sessions (username, started_at, last_observed_online_at, is_open) VALUES (?,?,?,1)", (obs.username, obs.observed_at, obs.observed_at))
            self.conn.execute("UPDATE profiles SET last_online_at=? WHERE username=?", (obs.observed_at, obs.username))
        elif current:
            start = parse_iso(current["started_at"])
            end = parse_iso(current["last_observed_online_at"]) or parse_iso(obs.observed_at)
            duration = max(0.0, (end - start).total_seconds()) if start and end else 0.0
            self.conn.execute("UPDATE online_sessions SET ended_at=?, duration_seconds=?, is_open=0 WHERE id=?", (iso(end), duration, current["id"]))

    def _refresh_profile_session_stats(self, username: str) -> None:
        durations = [float(r["duration_seconds"]) for r in self.conn.execute("SELECT duration_seconds FROM online_sessions WHERE username=? AND is_open=0 AND duration_seconds IS NOT NULL ORDER BY id DESC LIMIT 100", (username,)).fetchall()]
        average = statistics.fmean(durations) if durations else None
        median = statistics.median(durations) if durations else None
        counts: Dict[int, int] = {}
        for row in self.conn.execute("SELECT observed_at FROM observations WHERE username=? AND is_online=1 ORDER BY observed_at DESC LIMIT 1000", (username,)).fetchall():
            dt = parse_iso(row["observed_at"])
            if dt:
                hour = dt.astimezone(NY_TZ).hour
                counts[hour] = counts.get(hour, 0) + 1
        usual = [{"hour": hour, "label": datetime(2000, 1, 1, hour).strftime("%-I %p"), "observations": count} for hour, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:6]]
        self.conn.execute("UPDATE profiles SET average_online_seconds=?, median_online_seconds=?, usual_online_hours_json=? WHERE username=?", (average, median, json.dumps(usual), username))

    def summary(self, area: str = "new-york") -> Dict[str, Any]:
        clause = "in_new_york=1" if area == "new-york" else "in_nyc=1"
        totals = self.conn.execute(f"SELECT COUNT(*) AS profiles, SUM(CASE WHEN is_online=1 THEN 1 ELSE 0 END) AS online_now, SUM(CASE WHEN has_contact_link=1 THEN 1 ELSE 0 END) AS contact_links, SUM(CASE WHEN can_message=1 THEN 1 ELSE 0 END) AS can_message, SUM(reciprocal_visits) AS reciprocal_visits FROM profiles WHERE {clause}").fetchone()
        last_run = self.conn.execute("SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1").fetchone()
        return {"area": area, "profiles": int(totals["profiles"] or 0), "online_now": int(totals["online_now"] or 0), "contact_links": int(totals["contact_links"] or 0), "can_message": int(totals["can_message"] or 0), "reciprocal_visits": int(totals["reciprocal_visits"] or 0), "last_run": dict(last_run) if last_run else None}

    def profile_rows(self, area: str = "new-york", limit: int = 1000) -> List[Dict[str, Any]]:
        clause = "in_new_york=1" if area == "new-york" else "in_nyc=1"
        rows = self.conn.execute(f"SELECT * FROM profiles WHERE {clause} ORDER BY is_online DESC, can_message DESC, COALESCE(source_last_visit_at, last_seen_at) DESC LIMIT ?", (limit,)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["contact_kinds"] = json.loads(item.pop("contact_kinds_json") or "[]")
            item["usual_online_hours"] = json.loads(item.pop("usual_online_hours_json") or "[]")
            result.append(item)
        return result


class VisitorTelemetryScanner:
    def __init__(self, store: TelemetryStore, headless: bool = True, cooldown_hours: float = 24.0, max_profiles: int = 0, page_limit: int = 25, request_delay: float = 2.0):
        if webdriver is None:
            raise RuntimeError("selenium is required: pip install selenium")
        self.store = store
        self.headless = headless
        self.cooldown = timedelta(hours=max(0.0, cooldown_hours))
        self.max_profiles = max_profiles
        self.page_limit = max(1, page_limit)
        self.request_delay = max(1.0, request_delay)
        self.api = RentMasseurAPI(min_request_interval=self.request_delay)
        self.driver = None

    def authenticate_api(self) -> str:
        token = os.environ.get("RM_TOKEN", "").strip()
        if token:
            self.api.session.headers["Authorization"] = f"Bearer {token}"
            self.api.logged_in = True
            return token
        username = (os.environ.get("RENTMASSEUR_USERNAME") or os.environ.get("RENTMASSEUR_USER") or os.environ.get("RM_USER") or "").strip()
        password = os.environ.get("RENTMASSEUR_PASSWORD") or os.environ.get("RENTMASSEUR_PASS") or os.environ.get("RM_PASS") or os.environ.get("RM_PASSWORD") or ""
        if not username or not password:
            raise RuntimeError("Set RM_TOKEN or RentMasseur username/password environment variables")
        if not self.api.login(username, password):
            raise RuntimeError("RentMasseur API login failed")
        return self.api.session.headers.get("Authorization", "").replace("Bearer ", "")

    def _new_driver(self):
        options = Options()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1440,1100")
        options.add_argument(f"--user-data-dir={DEFAULT_PROFILE_DIR}")
        if self.headless:
            options.add_argument("--headless=new")
        if os.environ.get("CHROME_BINARY"):
            options.binary_location = os.environ["CHROME_BINARY"]
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(40)
        return driver

    def authenticate_browser(self, token: str) -> None:
        self.driver = self._new_driver()
        self.driver.get(BASE_URL)
        self._raise_on_challenge()
        if token:
            self.driver.execute_script("window.localStorage.setItem('accessToken', arguments[0]);", token)
            try:
                self.driver.add_cookie({"name": "accessToken", "value": token, "domain": ".rentmasseur.com", "path": "/", "secure": True})
            except WebDriverException:
                pass
            self.driver.get(f"{BASE_URL}/settings/whosawme")
            self._raise_on_challenge()
            if "login" not in self.driver.current_url.casefold():
                return
        username = os.environ.get("RENTMASSEUR_USERNAME") or os.environ.get("RENTMASSEUR_USER") or os.environ.get("RM_USER") or ""
        password = os.environ.get("RENTMASSEUR_PASSWORD") or os.environ.get("RENTMASSEUR_PASS") or os.environ.get("RM_PASS") or os.environ.get("RM_PASSWORD") or ""
        self.driver.get(f"{BASE_URL}/login")
        self._raise_on_challenge()
        wait = WebDriverWait(self.driver, 20)
        user_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="email"], input[type="text"]')))
        password_input = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type="password"]')))
        user_input.clear(); user_input.send_keys(username)
        password_input.clear(); password_input.send_keys(password); password_input.submit()
        wait.until(lambda d: "login" not in d.current_url.casefold())
        self._raise_on_challenge()

    def _raise_on_challenge(self) -> None:
        if not self.driver:
            return
        title = (self.driver.title or "").casefold()
        source = (self.driver.page_source or "")[:250000].casefold()
        if any(marker in title or marker in source for marker in ("captcha", "crowdsec", "verify you are human", "challenge-platform")):
            raise RuntimeError("Access challenge detected; stopping without bypass")

    def prior_contacts(self, max_pages: int = 10) -> set[str]:
        users: set[str] = set()
        for page in range(1, max_pages + 1):
            try:
                data = self.api.get_mailbox(page=page, folder=1, sort=1)
            except Exception as exc:
                LOG.warning("Mailbox page %s failed: %s", page, exc)
                break
            emails = data.get("emails", [])
            if not emails:
                break
            for email in emails:
                username = normalize_space(email.get("userCard", {}).get("username", ""))
                if username:
                    users.add(username.casefold())
        return users

    def discover_visitors(self) -> List[VisitorSeed]:
        if not self.driver:
            raise RuntimeError("Browser is not authenticated")
        discovered: Dict[str, VisitorSeed] = {}
        for page_number in range(1, self.page_limit + 1):
            self.driver.get(f"{BASE_URL}/settings/whosawme?page={page_number}")
            self._raise_on_challenge()
            WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
            raw = self.driver.execute_script("""
            const excluded = new Set(arguments[0]); const currentUser = (arguments[1] || '').toLowerCase(); const rows = [];
            for (const link of [...document.querySelectorAll('a[href]')]) { let url; try { url = new URL(link.href); } catch (_) { continue; } if (url.origin !== location.origin) continue; const parts = url.pathname.split('/').filter(Boolean); if (parts.length !== 1) continue; const username = decodeURIComponent(parts[0]); if (!username || excluded.has(username.toLowerCase()) || username.toLowerCase() === currentUser || /^\d+$/.test(username)) continue; const card = link.closest('article, li, tr, [class*="card"], [class*="item"], [class*="row"]') || link.parentElement; const timeEl = card ? card.querySelector('time') : null; rows.push({username, profile_url: url.origin + '/' + username, visitor_text: (card?.innerText || link.innerText || '').trim().slice(0, 1000), visitor_datetime: timeEl?.getAttribute('datetime') || ''}); }
            return rows;
            """, list(PROFILE_PATH_EXCLUSIONS), (self.api.username or os.environ.get("RENTMASSEUR_USERNAME", "")))
            page_new = 0
            for item in raw or []:
                username = normalize_space(item.get("username"))
                if username and username.casefold() not in discovered:
                    visit_at = parse_datetime_hint(item.get("visitor_text", ""), item.get("visitor_datetime", ""))
                    discovered[username.casefold()] = VisitorSeed(username=username, profile_url=item.get("profile_url") or f"{BASE_URL}/{username}", visitor_text=normalize_space(item.get("visitor_text", "")), visitor_datetime=normalize_space(item.get("visitor_datetime", "")), source_last_visit_at=iso(visit_at))
                    page_new += 1
            if page_number > 1 and page_new == 0:
                break
        values = list(discovered.values())
        return values[:self.max_profiles] if self.max_profiles > 0 else values

    def _profile_api_data(self, username: str) -> Dict[str, Any]:
        try:
            data = self.api.get_profile(username)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            LOG.info("Profile API unavailable for %s: %s", username, exc)
            return {}

    def _extract_api_fields(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        location = first_matching_value(payload, ("location", "city", "cityName", "addressLocality", "region"))
        online_raw = first_matching_value(payload, ("isOnline", "online", "onlineNow", "currentlyOnline", "activeNow"))
        last_online = first_matching_value(payload, ("lastOnline", "lastSeen", "lastActive", "onlineAt"))
        visit_count = first_matching_value(payload, ("visitCount", "visits", "viewCount", "profileViews"))
        can_message = first_matching_value(payload, ("canMessage", "messageAllowed", "allowMessages"))
        result = {"location_text": normalize_space(location), "is_online": bool_from_value(online_raw), "last_online_at": iso(parse_datetime_hint(normalize_space(last_online), normalize_space(last_online))), "api_can_message": bool_from_value(can_message)}
        try:
            result["reported_visit_count"] = int(visit_count) if visit_count is not None else None
        except (ValueError, TypeError):
            result["reported_visit_count"] = None
        return result

    def _extract_dom_fields(self) -> Dict[str, Any]:
        return self.driver.execute_script("""
        const bodyText = (document.body?.innerText || '').replace(/\s+/g, ' ').trim(); const contactKinds = new Set(); let hasContact = false;
        for (const a of [...document.querySelectorAll('a[href]')]) { const href = (a.getAttribute('href') || '').toLowerCase(); const text = (a.innerText || a.getAttribute('aria-label') || '').toLowerCase(); if (href.startsWith('tel:')) { contactKinds.add('phone'); hasContact = true; } if (href.startsWith('mailto:')) { contactKinds.add('email'); hasContact = true; } if (/contact|call|phone|email/.test(text) && a.offsetParent !== null) { contactKinds.add('visible_contact'); hasContact = true; } }
        let hasMessage = false; for (const el of [...document.querySelectorAll('a,button')]) { const text = (el.innerText || el.getAttribute('aria-label') || '').toLowerCase().trim(); const href = (el.getAttribute('href') || '').toLowerCase(); if ((/^(message|send message|email me|contact)$/.test(text) || href.includes('message') || href.includes('mailbox')) && el.offsetParent !== null) { hasMessage = true; break; } }
        const locationCandidates = []; for (const selector of ['[class*="location"]','[data-testid*="location"]','[class*="city"]','[itemprop="addressLocality"]','[itemprop="addressRegion"]']) for (const el of [...document.querySelectorAll(selector)]) { const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim(); if (text && text.length < 200) locationCandidates.push(text); }
        const onlineCandidates = []; for (const selector of ['[class*="online"]','[data-testid*="online"]','[class*="last-seen"]','[class*="lastSeen"]','time']) for (const el of [...document.querySelectorAll(selector)]) { const text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim(); const dt = el.getAttribute?.('datetime') || ''; if ((text || dt) && (text + ' ' + dt).length < 250) onlineCandidates.push({text, datetime: dt}); }
        return {body_text: bodyText.slice(0,10000), title: document.title || '', has_contact_link: hasContact, contact_kinds: [...contactKinds], has_message_control: hasMessage, location_candidates: [...new Set(locationCandidates)].slice(0,20), online_candidates: onlineCandidates.slice(0,30), ld_json: [...document.querySelectorAll('script[type="application/ld+json"]')].map(s => s.textContent || '').slice(0,10)};
        """) or {}

    def _choose_location(self, api_fields: Dict[str, Any], dom: Dict[str, Any]) -> str:
        if api_fields.get("location_text"):
            return normalize_space(api_fields["location_text"])
        for raw in dom.get("ld_json", []):
            try:
                value = first_matching_value(json.loads(raw), ("addressLocality", "addressRegion", "location", "city"))
                if value:
                    return normalize_space(value)
            except Exception:
                pass
        candidates = [normalize_space(x) for x in dom.get("location_candidates", []) if x]
        ny_candidates = [x for x in candidates if normalize_location(x)[3]]
        return min(ny_candidates, key=len) if ny_candidates else (min(candidates, key=len) if candidates else "")

    def _choose_online(self, api_fields: Dict[str, Any], dom: Dict[str, Any]) -> Tuple[Optional[bool], str, Optional[str]]:
        if api_fields.get("is_online") is not None:
            return api_fields["is_online"], "API online indicator", api_fields.get("last_online_at")
        joined = []; last_online_at = api_fields.get("last_online_at")
        for item in dom.get("online_candidates", []):
            text = normalize_space(item.get("text", "")); dt_attr = normalize_space(item.get("datetime", "")); combined = normalize_space(f"{text} {dt_attr}")
            if combined: joined.append(combined)
            parsed = parse_datetime_hint(text, dt_attr)
            if parsed and not last_online_at: last_online_at = iso(parsed)
        signal = " | ".join(joined[:8]); searchable = f"{signal} {normalize_space(dom.get('body_text',''))[:5000]}".casefold()
        if re.search(r"\bonline now\b|\bcurrently online\b|\bactive now\b", searchable): return True, signal or "Online now", iso(utc_now())
        if re.search(r"\boffline\b|\blast online\b|\blast seen\b", searchable): return False, signal, last_online_at
        return None, signal, last_online_at

    def observe_profile(self, seed: VisitorSeed, prior_contacts: set[str]) -> ProfileObservation:
        observed_at = iso(utc_now()); api_payload = self._profile_api_data(seed.username); api_fields = self._extract_api_fields(api_payload); reciprocal_due = not self.store.last_reciprocal_visit(seed.username) or utc_now() - self.store.last_reciprocal_visit(seed.username) >= self.cooldown
        dom = {}; error = ""
        if reciprocal_due or not api_payload:
            try:
                self.driver.get(seed.profile_url); self._raise_on_challenge(); WebDriverWait(self.driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body"))); dom = self._extract_dom_fields()
            except Exception as exc:
                error = f"profile_visit_failed: {exc}"
        location = self._choose_location(api_fields, dom); city, state, in_nyc, in_new_york = normalize_location(location); is_online, online_text, last_online_at = self._choose_online(api_fields, dom)
        contact_kinds = sorted(set(dom.get("contact_kinds", []))); has_contact = bool(dom.get("has_contact_link")); has_message = bool(dom.get("has_message_control")); prior_contact = seed.username.casefold() in prior_contacts; can_message = bool(has_message or prior_contact or api_fields.get("api_can_message") is True)
        hash_payload = {"username": seed.username.casefold(), "location": location.casefold(), "is_online": is_online, "has_contact": has_contact, "has_message": has_message, "page_title": normalize_space(dom.get("title", ""))}
        return ProfileObservation(username=seed.username, profile_url=seed.profile_url, observed_at=observed_at, source_last_visit_at=seed.source_last_visit_at, source_visit_text=seed.visitor_text, location_text=location, city=city, state=state, in_nyc=in_nyc, in_new_york=in_new_york, is_online=is_online, online_text=online_text, last_online_at=last_online_at, has_contact_link=has_contact, contact_kinds=contact_kinds, has_message_control=has_message, prior_contact=prior_contact, can_message=can_message, reciprocal_visit_performed=reciprocal_due and not error, reported_visit_count=api_fields.get("reported_visit_count"), page_title=normalize_space(dom.get("title", "")), profile_hash=stable_hash(hash_payload), raw_summary={"api_keys": sorted(api_payload.keys())[:100] if isinstance(api_payload, dict) else [], "dom": {"location_candidates": dom.get("location_candidates", []), "online_candidates": dom.get("online_candidates", []), "contact_kinds": contact_kinds}}, error=error)

    def run_once(self) -> Dict[str, Any]:
        run_id = self.store.begin_run(); errors: List[str] = []; metrics = {"discovered_count": 0, "scanned_count": 0, "ny_count": 0, "online_count": 0, "contactable_count": 0, "reciprocal_visits": 0}; status = "success"
        try:
            token = self.authenticate_api(); self.authenticate_browser(token); contacts = self.prior_contacts(); visitors = self.discover_visitors(); metrics["discovered_count"] = len(visitors)
            for seed in visitors:
                try:
                    obs = self.observe_profile(seed, contacts); self.store.record(run_id, obs); metrics["scanned_count"] += 1; metrics["ny_count"] += int(obs.in_new_york); metrics["online_count"] += int(obs.is_online is True); metrics["contactable_count"] += int(obs.can_message); metrics["reciprocal_visits"] += int(obs.reciprocal_visit_performed)
                    if obs.error: errors.append(f"{obs.username}: {obs.error}")
                except Exception as exc:
                    errors.append(f"{seed.username}: {exc}")
                time.sleep(self.request_delay)
            status = "failure" if errors and metrics["scanned_count"] == 0 else ("partial" if errors else "success")
        except Exception as exc:
            status = "failure"; errors.append(str(exc))
        finally:
            if self.driver:
                self.driver.quit(); self.driver = None
        receipt_hash = self.store.finish_run(run_id, status, metrics, errors)
        return {"run_id": run_id, "status": status, **metrics, "errors": errors, "receipt_hash": receipt_hash, "db": str(self.store.path)}


def duration_label(seconds: Any) -> str:
    if seconds is None: return "Unknown"
    value = float(seconds)
    return f"{value:.0f}s" if value < 60 else (f"{value / 60:.0f}m" if value < 3600 else f"{value / 3600:.1f}h")


def local_time_label(value: Optional[str]) -> str:
    dt = parse_iso(value)
    return dt.astimezone(NY_TZ).strftime("%b %-d, %Y %-I:%M %p") if dt else "Unknown"


def render_dashboard(store: TelemetryStore, output: Path, area: str = "new-york") -> Path:
    output = Path(output); output.mkdir(parents=True, exist_ok=True); summary = store.summary(area); rows = store.profile_rows(area); generated = datetime.now(NY_TZ).strftime("%b %-d, %Y %-I:%M %p")
    table_rows = []
    for row in rows:
        online = '<span class="pill green">ONLINE</span>' if row["is_online"] == 1 else '<span class="pill muted">Offline</span>'; message = '<span class="pill blue">Message path</span>' if row["can_message"] else '<span class="pill muted">No message path</span>'; contact = ", ".join(row["contact_kinds"]) or ("Yes" if row["has_contact_link"] else "No"); usual = ", ".join(item.get("label", "") for item in row["usual_online_hours"][:4]) or "Learning"
        table_rows.append(f'<tr><td><a href="{html.escape(row["profile_url"])}" target="_blank">{html.escape(row["username"])}</a></td><td>{online}</td><td>{html.escape(row["location_text"] or "Unknown")}</td><td>{local_time_label(row["source_last_visit_at"])}</td><td>{int(row["observed_visitor_runs"] or 0)}</td><td>{int(row["reported_visit_count"]) if row["reported_visit_count"] is not None else "—"}</td><td>{int(row["reciprocal_visits"] or 0)}</td><td>{html.escape(contact)}</td><td>{message}</td><td>{local_time_label(row["last_online_at"])}</td><td>{duration_label(row["average_online_seconds"])}</td><td>{html.escape(usual)}</td><td>{html.escape(row["last_error"] or "")}</td></tr>')
    last_run = summary.get("last_run") or {}
    doc = f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="refresh" content="120"><title>RentMasseur Visitor Telemetry</title><style>:root{{color-scheme:dark;--bg:#0c0d0f;--panel:#15171b;--line:#2a2e35;--text:#f3f4f6;--muted:#9ca3af}}*{{box-sizing:border-box}}body{{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:var(--bg);color:var(--text)}}main{{max-width:1800px;margin:0 auto;padding:24px}}.sub,.note{{color:var(--muted)}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin:20px 0}}.card{{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}}.card strong{{display:block;font-size:28px;margin-top:6px}}.table-wrap{{overflow:auto;border:1px solid var(--line);border-radius:14px;background:var(--panel)}}table{{border-collapse:collapse;min-width:1650px;width:100%}}th,td{{padding:11px 10px;border-bottom:1px solid var(--line);text-align:left;font-size:13px}}th{{position:sticky;top:0;background:#1d2026}}a{{color:#8ab4ff}}.pill{{display:inline-block;padding:3px 7px;border-radius:999px;border:1px solid var(--line)}}.green{{background:#123b2a}}.blue{{background:#172f52}}.muted{{color:var(--muted)}}</style></head><body><main><h1>RentMasseur Visitor Telemetry</h1><div class="sub">Generated {html.escape(generated)} · Area: {html.escape(area)} · Last run: {html.escape(str(last_run.get("status","never")))}</div><section class="cards"><div class="card">New York profiles<strong>{summary["profiles"]}</strong></div><div class="card">Online now<strong>{summary["online_now"]}</strong></div><div class="card">Visible contact links<strong>{summary["contact_links"]}</strong></div><div class="card">Message-capable<strong>{summary["can_message"]}</strong></div><div class="card">Reciprocal visits<strong>{summary["reciprocal_visits"]}</strong></div></section><div class="table-wrap"><table><thead><tr><th>Profile</th><th>Status</th><th>Location</th><th>Visited you</th><th>Observed runs</th><th>Reported visits</th><th>Visited back</th><th>Contact</th><th>Messaging</th><th>Last online</th><th>Average session</th><th>Usual online hours</th><th>Error</th></tr></thead><tbody>{''.join(table_rows) if table_rows else '<tr><td colspan="13">No New York profiles recorded yet.</td></tr>'}</tbody></table></div><p class="note">Observed runs are not claimed as true visits. Reported visits appear only when the platform supplies a count. Online duration and common hours are estimates from repeated observations. This pipeline never sends messages.</p></main></body></html>'''
    target = output / "rm_visitor_dashboard.html"; target.write_text(doc, encoding="utf-8"); (output / "rm_visitor_telemetry.json").write_text(json.dumps({"summary": summary, "profiles": rows}, indent=2, default=str), encoding="utf-8"); return target


def serve_dashboard(store: TelemetryStore, area: str, host: str, port: int) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/api/telemetry"):
                body = json.dumps({"summary": store.summary(area), "profiles": store.profile_rows(area)}, default=str).encode(); content_type = "application/json"
            else:
                body = render_dashboard(store, DEFAULT_OUTPUT, area).read_bytes(); content_type = "text/html; charset=utf-8"
            self.send_response(200); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self, fmt, *args): LOG.info("dashboard: " + fmt, *args)
    server = ThreadingHTTPServer((host, port), Handler); LOG.info("Dashboard: http://%s:%s", host, port)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="RentMasseur visitor telemetry pipeline"); parser.add_argument("--db", type=Path, default=DEFAULT_DB); parser.add_argument("--verbose", action="store_true"); sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan"); scan.add_argument("--headed", action="store_true"); scan.add_argument("--cooldown-hours", type=float, default=24.0); scan.add_argument("--max-profiles", type=int, default=0); scan.add_argument("--page-limit", type=int, default=25); scan.add_argument("--delay", type=float, default=2.0); scan.add_argument("--area", choices=("nyc", "new-york"), default="new-york")
    dashboard = sub.add_parser("dashboard"); dashboard.add_argument("--output", type=Path, default=DEFAULT_OUTPUT); dashboard.add_argument("--area", choices=("nyc", "new-york"), default="new-york")
    summary = sub.add_parser("summary"); summary.add_argument("--area", choices=("nyc", "new-york"), default="new-york")
    serve = sub.add_parser("serve"); serve.add_argument("--host", default="127.0.0.1"); serve.add_argument("--port", type=int, default=8787); serve.add_argument("--area", choices=("nyc", "new-york"), default="new-york")
    return parser


def main() -> int:
    args = build_parser().parse_args(); logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"); store = TelemetryStore(args.db)
    try:
        if args.command == "scan":
            scanner = VisitorTelemetryScanner(store, not args.headed, args.cooldown_hours, args.max_profiles, args.page_limit, args.delay); result = scanner.run_once(); result["dashboard"] = str(render_dashboard(store, DEFAULT_OUTPUT, args.area)); print(json.dumps(result, indent=2)); return 0 if result["status"] in {"success", "partial"} else 1
        if args.command == "dashboard": print(render_dashboard(store, args.output, args.area)); return 0
        if args.command == "summary": print(json.dumps(store.summary(args.area), indent=2, default=str)); return 0
        if args.command == "serve": serve_dashboard(store, args.area, args.host, args.port); return 0
    finally:
        store.close()
    return 1


if __name__ == "__main__":
    sys.exit(main())
