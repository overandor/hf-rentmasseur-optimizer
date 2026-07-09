"""
ClientPulse OS — Hourly evidence engine for profile conversion.

Turns profile traffic, visitors, bios, first-party metrics, and
experiments into an hourly decision machine.

Primitive:
  visitor signal → metric packet → KPI vector → experiment decision → receipt

KPIs:
  Immortality  — durable platform life
  Virality     — attention acceleration
  Conversion   — monetization rate
  Trust        — safety / clean test
  Decision     — action state

Decision logic:
  snapshots < 2          → INSUFFICIENT_DATA
  profile_visible == false → EMERGENCY_RESTORE
  contact_click_rate drops > 25% → ROLLBACK
  views rise but CTR falls → ATTENTION_WITHOUT_INTENT
  CTR rises and views hold → WINNER_FOUND
  immortality high, virality low → NEEDS_HOOK_TEST

Boundary:
  No CAPTCHA bypass. No session files. No scraping harder when blocked.
  First-party metrics in. Tiny candidate pool. Decision ledger out.
"""

import hashlib
import json
import sqlite3
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any

BASE = Path(__file__).parent
CP_DB = str(BASE / "data" / "clientpulse.db")
METRICS_DIR = BASE / "content" / "metrics"
BIOS_DIR = BASE / "content" / "bios"
DECISIONS_DIR = BASE / "content" / "decisions"
EXPERIMENTS_DIR = BASE / "content" / "experiments"
RECEIPTS_DIR = BASE / "receipts"

for d in [METRICS_DIR, BIOS_DIR, DECISIONS_DIR, EXPERIMENTS_DIR, RECEIPTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

os.makedirs(os.path.dirname(CP_DB), exist_ok=True)


# =============================================================================
# Schema
# =============================================================================

def _init_db(db_path: str = CP_DB):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS metrics (
        id TEXT PRIMARY KEY,
        snapshot_time TEXT NOT NULL,
        profile_visible INTEGER,
        days_online INTEGER,
        lifetime_views INTEGER,
        daily_views INTEGER,
        new_visitors INTEGER,
        contact_clicks INTEGER,
        bookmarks INTEGER,
        ctr REAL,
        views_per_day REAL,
        source TEXT,
        raw_json TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS experiments (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        hypothesis TEXT,
        bio_id TEXT,
        start_time TEXT,
        end_time TEXT,
        status TEXT DEFAULT 'running',
        verdict TEXT,
        baseline_ctr REAL,
        peak_ctr REAL,
        snapshots INTEGER DEFAULT 0,
        notes TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS decisions (
        id TEXT PRIMARY KEY,
        decision_time TEXT NOT NULL,
        state TEXT NOT NULL,
        immortality REAL,
        virality REAL,
        conversion REAL,
        trust REAL,
        reasoning TEXT,
        action TEXT,
        receipt_hash TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS bios (
        id TEXT PRIMARY KEY,
        name TEXT,
        content TEXT,
        status TEXT DEFAULT 'approved',
        created_at TEXT,
        tested INTEGER DEFAULT 0,
        winner INTEGER DEFAULT 0
    )""")

    c.execute("CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(snapshot_time)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_exp_status ON experiments(status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_dec_ts ON decisions(decision_time)")

    conn.commit()
    conn.close()


_init_db()


# =============================================================================
# HourlyMetricsCollector
# =============================================================================

class HourlyMetricsCollector:
    """
    Ingests first-party metrics and stores hourly snapshots.
    No scraping. No automation. Manual or API-fed metrics only.
    """

    def __init__(self, db_path: str = CP_DB):
        self.db_path = db_path

    def ingest(self, metrics: dict) -> dict:
        """
        Ingest a metric snapshot.

        Required: profile_visible, daily_views, contact_clicks
        Optional: days_online, lifetime_views, new_visitors, bookmarks, source
        """
        ts = datetime.now().isoformat()
        snapshot_id = hashlib.sha256(f"{ts}:{json.dumps(metrics, sort_keys=True)}".encode()).hexdigest()[:16]

        daily_views = metrics.get("daily_views", 0)
        contact_clicks = metrics.get("contact_clicks", 0)
        ctr = (contact_clicks / daily_views * 100) if daily_views > 0 else 0.0
        days_online = metrics.get("days_online", 0)
        lifetime_views = metrics.get("lifetime_views", 0)
        views_per_day = (lifetime_views / days_online) if days_online > 0 else 0.0

        record = {
            "id": snapshot_id,
            "snapshot_time": ts,
            "profile_visible": 1 if metrics.get("profile_visible", True) else 0,
            "days_online": days_online,
            "lifetime_views": lifetime_views,
            "daily_views": daily_views,
            "new_visitors": metrics.get("new_visitors", 0),
            "contact_clicks": contact_clicks,
            "bookmarks": metrics.get("bookmarks", 0),
            "ctr": round(ctr, 4),
            "views_per_day": round(views_per_day, 2),
            "source": metrics.get("source", "manual"),
            "raw_json": json.dumps(metrics),
        }

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO metrics
            (id, snapshot_time, profile_visible, days_online, lifetime_views,
             daily_views, new_visitors, contact_clicks, bookmarks, ctr,
             views_per_day, source, raw_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (record["id"], record["snapshot_time"], record["profile_visible"],
             record["days_online"], record["lifetime_views"], record["daily_views"],
             record["new_visitors"], record["contact_clicks"], record["bookmarks"],
             record["ctr"], record["views_per_day"], record["source"], record["raw_json"]))
        conn.commit()
        conn.close()

        # Also write to daily file
        day_str = datetime.now().strftime("%Y%m%d")
        daily_file = METRICS_DIR / f"daily_metrics_{day_str}.jsonl"
        with open(daily_file, "a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

        return record

    def get_snapshots(self, limit: int = 50) -> list:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""SELECT id, snapshot_time, profile_visible, days_online,
                     lifetime_views, daily_views, new_visitors, contact_clicks,
                     bookmarks, ctr, views_per_day, source
                     FROM metrics ORDER BY snapshot_time DESC LIMIT ?""", (limit,))
        rows = c.fetchall()
        conn.close()
        return [{
            "id": r[0], "snapshot_time": r[1], "profile_visible": r[2],
            "days_online": r[3], "lifetime_views": r[4], "daily_views": r[5],
            "new_visitors": r[6], "contact_clicks": r[7], "bookmarks": r[8],
            "ctr": r[9], "views_per_day": r[10], "source": r[11],
        } for r in rows]


# =============================================================================
# KPIs — Immortality, Virality, Conversion, Trust
# =============================================================================

@dataclass
class KPIVector:
    immortality: float = 0.0
    virality: float = 0.0
    conversion: float = 0.0
    trust: float = 0.0
    decision: str = "INSUFFICIENT_DATA"
    reasoning: str = ""
    action: str = ""


class KPIEngine:
    """
    Computes KPI vectors from metric snapshots.

    Immortality = durability (days online, views/day, visibility, availability)
    Virality = acceleration (velocity, acceleration, return rate)
    Conversion = monetization (CTR, contact clicks)
    Trust = safety (clean test, no contamination)
    """

    def compute(self, snapshots: list, experiment: dict = None) -> KPIVector:
        if not snapshots:
            return KPIVector(decision="INSUFFICIENT_DATA", reasoning="no snapshots")

        latest = snapshots[0]  # most recent first
        snap_count = len(snapshots)

        # --- Immortality ---
        imm = 0.0
        if latest.get("profile_visible"):
            imm += 0.2
        days = latest.get("days_online", 0)
        if days > 0:
            imm += min(0.3, days / 1000)  # 1000 days = full 0.3
        vpd = latest.get("views_per_day", 0)
        if vpd > 0:
            imm += min(0.2, vpd / 100)  # 100 views/day = full 0.2
        lifetime = latest.get("lifetime_views", 0)
        if lifetime > 0:
            imm += min(0.15, lifetime / 5000)  # 5000 lifetime = full 0.15
        if latest.get("bookmarks", 0) > 0:
            imm += min(0.15, latest["bookmarks"] / 20)  # 20 bookmarks = full 0.15
        immortality = max(0.0, min(1.0, imm))

        # --- Virality ---
        vir = 0.0
        if snap_count < 2:
            vir = 0.0
        else:
            prev = snapshots[1]
            # Velocity: daily_views change
            curr_views = latest.get("daily_views", 0)
            prev_views = prev.get("daily_views", 0)
            if prev_views > 0:
                velocity = (curr_views - prev_views) / prev_views
                vir += max(0, min(0.3, velocity * 0.3))
            # Acceleration: CTR change
            curr_ctr = latest.get("ctr", 0)
            prev_ctr = prev.get("ctr", 0)
            if prev_ctr > 0:
                ctr_accel = (curr_ctr - prev_ctr) / prev_ctr
                vir += max(0, min(0.2, ctr_accel * 0.2))
            # New visitors
            new_vis = latest.get("new_visitors", 0)
            if new_vis > 0:
                vir += min(0.2, new_vis / 50)
            # Contact clicks growth
            curr_clicks = latest.get("contact_clicks", 0)
            prev_clicks = prev.get("contact_clicks", 0)
            if prev_clicks > 0 and curr_clicks > prev_clicks:
                vir += min(0.15, (curr_clicks - prev_clicks) / prev_clicks * 0.15)
            # Bookmarks
            if latest.get("bookmarks", 0) > prev.get("bookmarks", 0):
                vir += 0.15
        virality = max(0.0, min(1.0, vir))

        # --- Conversion ---
        conv = 0.0
        ctr = latest.get("ctr", 0)
        if ctr > 0:
            conv += min(0.4, ctr / 10)  # 10% CTR = full 0.4
        clicks = latest.get("contact_clicks", 0)
        if clicks > 0:
            conv += min(0.3, clicks / 20)  # 20 clicks = full 0.3
        if latest.get("bookmarks", 0) > 0:
            conv += min(0.3, latest["bookmarks"] / 15)
        conversion = max(0.0, min(1.0, conv))

        # --- Trust ---
        trust = 1.0  # start clean
        if experiment:
            contamination = experiment.get("contamination", {})
            if contamination.get("contaminated"):
                trust -= 0.5
            if not experiment.get("controlled", True):
                trust -= 0.3
        trust = max(0.0, min(1.0, trust))

        # --- Decision ---
        decision, reasoning, action = self._decide(
            immortality, virality, conversion, trust,
            latest, snapshots, experiment
        )

        return KPIVector(
            immortality=round(immortality, 4),
            virality=round(virality, 4),
            conversion=round(conversion, 4),
            trust=round(trust, 4),
            decision=decision,
            reasoning=reasoning,
            action=action,
        )

    def _decide(self, imm, vir, conv, trust, latest, snapshots, experiment) -> tuple:
        snap_count = len(snapshots)

        if snap_count < 2:
            return ("INSUFFICIENT_DATA",
                    f"only {snap_count} snapshot(s) — need ≥2 for velocity",
                    "collect more hourly snapshots")

        if not latest.get("profile_visible"):
            return ("EMERGENCY_RESTORE",
                    "profile is not visible — traffic will stop",
                    "restore profile visibility immediately")

        # Check CTR drop
        if snap_count >= 2:
            prev = snapshots[1]
            curr_ctr = latest.get("ctr", 0)
            prev_ctr = prev.get("ctr", 0)
            if prev_ctr > 0 and curr_ctr < prev_ctr * 0.75:
                drop_pct = ((prev_ctr - curr_ctr) / prev_ctr) * 100
                return ("ROLLBACK",
                        f"CTR dropped {drop_pct:.1f}% ({prev_ctr:.2f}% → {curr_ctr:.2f}%)",
                        "revert to previous bio/content")

            # Views rising but CTR falling
            curr_views = latest.get("daily_views", 0)
            prev_views = prev.get("daily_views", 0)
            if curr_views > prev_views and curr_ctr < prev_ctr:
                return ("ATTENTION_WITHOUT_INTENT",
                        "views rising but CTR falling — attention without buyer intent",
                        "test bio that filters for intent, not traffic")

            # CTR rising and views holding
            if curr_ctr > prev_ctr and curr_views >= prev_views * 0.9:
                return ("WINNER_FOUND",
                        f"CTR improved ({prev_ctr:.2f}% → {curr_ctr:.2f}%) with stable views",
                        "lock in current bio, scale exposure")

        # High immortality, low virality
        if imm >= 0.6 and vir < 0.2:
            return ("NEEDS_HOOK_TEST",
                    f"profile is durable (immortality={imm:.2f}) but stagnant (virality={vir:.2f})",
                    "run controlled bio experiment with stronger hook")

        # Trust broken
        if trust < 0.5:
            return ("DIRTY_TEST",
                    f"trust={trust:.2f} — experiment contaminated",
                    "halt experiment, clean test conditions, restart")

        if conv > 0.5 and vir > 0.3:
            return ("SCALE",
                    f"strong conversion ({conv:.2f}) and acceleration ({vir:.2f})",
                    "increase exposure, maintain current bio")

        return ("HOLD",
                f"immortality={imm:.2f}, virality={vir:.2f}, conversion={conv:.2f} — no action threshold met",
                "continue monitoring")


# =============================================================================
# DecisionGate
# =============================================================================

class DecisionGate:
    """
    Records decisions in a tamper-evident ledger with KPI snapshots.
    Each decision is receipted and stored for audit.
    """

    def __init__(self, db_path: str = CP_DB):
        self.db_path = db_path

    def record(self, kpi: KPIVector) -> dict:
        ts = datetime.now().isoformat()
        decision_id = hashlib.sha256(f"{ts}:{kpi.decision}".encode()).hexdigest()[:16]

        # Build receipt hash
        receipt_data = json.dumps({
            "decision": kpi.decision,
            "immortality": kpi.immortality,
            "virality": kpi.virality,
            "conversion": kpi.conversion,
            "trust": kpi.trust,
            "ts": ts,
        }, sort_keys=True)
        receipt_hash = hashlib.sha256(receipt_data.encode()).hexdigest()

        record = {
            "id": decision_id,
            "decision_time": ts,
            "state": kpi.decision,
            "immortality": kpi.immortality,
            "virality": kpi.virality,
            "conversion": kpi.conversion,
            "trust": kpi.trust,
            "reasoning": kpi.reasoning,
            "action": kpi.action,
            "receipt_hash": receipt_hash,
        }

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO decisions
            (id, decision_time, state, immortality, virality, conversion,
             trust, reasoning, action, receipt_hash)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (record["id"], record["decision_time"], record["state"],
             record["immortality"], record["virality"], record["conversion"],
             record["trust"], record["reasoning"], record["action"],
             record["receipt_hash"]))
        conn.commit()
        conn.close()

        # Write to decisions dir
        (DECISIONS_DIR / "latest_decision.json").write_text(
            json.dumps(record, indent=2, ensure_ascii=False))

        return record

    def get_latest(self) -> Optional[dict]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""SELECT id, decision_time, state, immortality, virality,
                     conversion, trust, reasoning, action, receipt_hash
                     FROM decisions ORDER BY decision_time DESC LIMIT 1""")
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {
            "id": row[0], "decision_time": row[1], "state": row[2],
            "immortality": row[3], "virality": row[4], "conversion": row[5],
            "trust": row[6], "reasoning": row[7], "action": row[8],
            "receipt_hash": row[9],
        }

    def history(self, limit: int = 20) -> list:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""SELECT id, decision_time, state, immortality, virality,
                     conversion, trust, reasoning, action
                     FROM decisions ORDER BY decision_time DESC LIMIT ?""", (limit,))
        rows = c.fetchall()
        conn.close()
        return [{
            "id": r[0], "decision_time": r[1], "state": r[2],
            "immortality": r[3], "virality": r[4], "conversion": r[5],
            "trust": r[6], "reasoning": r[7], "action": r[8],
        } for r in rows]


# =============================================================================
# ExperimentGovernance
# =============================================================================

class ExperimentGovernance:
    """
    Tracks bio/content experiments with hypothesis, duration, and verdict.
    Maintains a tiny approved candidate pool (max 4 bios).
    """

    MAX_BIOS = 4

    def __init__(self, db_path: str = CP_DB):
        self.db_path = db_path

    def approve_bio(self, name: str, content: str) -> dict:
        """Add a bio to the approved candidate pool."""
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM bios WHERE status='approved'")
        count = c.fetchone()[0]
        if count >= self.MAX_BIOS:
            conn.close()
            return {"error": f"Pool full ({self.MAX_BIOS} bios max). Revoke one first."}

        bio_id = hashlib.sha256(f"{name}:{time.time()}".encode()).hexdigest()[:12]
        ts = datetime.now().isoformat()
        c.execute("""INSERT INTO bios (id, name, content, status, created_at, tested, winner)
            VALUES (?,?,?,?,?,?,?)""",
            (bio_id, name, content, "approved", ts, 0, 0))
        conn.commit()
        conn.close()
        return {"id": bio_id, "name": name, "status": "approved", "created_at": ts}

    def revoke_bio(self, bio_id: str) -> dict:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("UPDATE bios SET status='revoked' WHERE id=?", (bio_id,))
        conn.commit()
        conn.close()
        return {"id": bio_id, "status": "revoked"}

    def list_bios(self) -> list:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT id, name, status, tested, winner, created_at FROM bios ORDER BY created_at DESC")
        rows = c.fetchall()
        conn.close()
        return [{"id": r[0], "name": r[1], "status": r[2], "tested": r[3], "winner": r[4], "created_at": r[5]} for r in rows]

    def start_experiment(self, name: str, hypothesis: str, bio_id: str) -> dict:
        """Start a controlled experiment."""
        exp_id = hashlib.sha256(f"{name}:{time.time()}".encode()).hexdigest()[:12]
        ts = datetime.now().isoformat()

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""INSERT INTO experiments (id, name, hypothesis, bio_id, start_time, status, snapshots)
            VALUES (?,?,?,?,?,?,?)""",
            (exp_id, name, hypothesis, bio_id, ts, "running", 0))
        c.execute("UPDATE bios SET tested=1 WHERE id=?", (bio_id,))
        conn.commit()
        conn.close()

        # Write experiment file
        exp = {
            "id": exp_id, "name": name, "hypothesis": hypothesis,
            "bio_id": bio_id, "start_time": ts, "status": "running",
            "snapshots": 0,
        }
        (EXPERIMENTS_DIR / f"exp_{exp_id}.json").write_text(
            json.dumps(exp, indent=2, ensure_ascii=False))

        return exp

    def record_verdict(self, exp_id: str, verdict: str, notes: str = "") -> dict:
        """Record experiment verdict: keep, rollback, or iterate."""
        ts = datetime.now().isoformat()
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""UPDATE experiments SET end_time=?, status='completed', verdict=?, notes=? WHERE id=?""",
            (ts, verdict, notes, exp_id))
        if verdict == "keep":
            c.execute("""UPDATE experiments SET peak_ctr=(
                SELECT MAX(ctr) FROM metrics WHERE snapshot_time >=
                (SELECT start_time FROM experiments WHERE id=?)
            ) WHERE id=?""", (exp_id, exp_id))
        conn.commit()
        conn.close()
        return {"id": exp_id, "verdict": verdict, "end_time": ts, "notes": notes}

    def list_experiments(self, status: str = "") -> list:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if status:
            c.execute("""SELECT id, name, hypothesis, bio_id, start_time, end_time,
                         status, verdict, snapshots FROM experiments WHERE status=? ORDER BY start_time DESC""",
                (status,))
        else:
            c.execute("""SELECT id, name, hypothesis, bio_id, start_time, end_time,
                         status, verdict, snapshots FROM experiments ORDER BY start_time DESC""")
        rows = c.fetchall()
        conn.close()
        return [{
            "id": r[0], "name": r[1], "hypothesis": r[2], "bio_id": r[3],
            "start_time": r[4], "end_time": r[5], "status": r[6],
            "verdict": r[7], "snapshots": r[8],
        } for r in rows]


# =============================================================================
# DirtyTestDetector
# =============================================================================

class DirtyTestDetector:
    """
    Detects experiment contamination: if photos, price, availability,
    service list, or external links change during a bio test, the test
    is contaminated and results are invalid.
    """

    CONTAMINATION_FIELDS = [
        "photos", "price", "availability", "services", "external_links",
        "location", "phone", "rates",
    ]

    def __init__(self, db_path: str = CP_DB):
        self.db_path = db_path

    def snapshot_baseline(self, experiment_id: str, profile_state: dict) -> dict:
        """Record the profile state at experiment start."""
        baseline = {
            "experiment_id": experiment_id,
            "fields": {k: profile_state.get(k) for k in self.CONTAMINATION_FIELDS},
            "timestamp": datetime.now().isoformat(),
        }
        path = EXPERIMENTS_DIR / f"baseline_{experiment_id}.json"
        path.write_text(json.dumps(baseline, indent=2, ensure_ascii=False))
        return baseline

    def check(self, experiment_id: str, current_state: dict) -> dict:
        """Check if profile state changed during experiment."""
        path = EXPERIMENTS_DIR / f"baseline_{experiment_id}.json"
        if not path.exists():
            return {"contaminated": False, "reason": "no baseline recorded"}

        baseline = json.loads(path.read_text())
        changes = []
        for field in self.CONTAMINATION_FIELDS:
            old = baseline["fields"].get(field)
            new = current_state.get(field)
            if old != new:
                changes.append({"field": field, "old": old, "new": new})

        contaminated = len(changes) > 0
        return {
            "contaminated": contaminated,
            "changes": changes,
            "experiment_id": experiment_id,
            "checked_at": datetime.now().isoformat(),
        }


# =============================================================================
# ClientPulseOS — Umbrella
# =============================================================================

class ClientPulseOS:
    """
    The full client intelligence operating system.

    Flow:
      ingest metrics → compute KPIs → decision gate → receipt
      + experiment governance + dirty-test detection
    """

    def __init__(self):
        self.collector = HourlyMetricsCollector()
        self.kpis = KPIEngine()
        self.decisions = DecisionGate()
        self.experiments = ExperimentGovernance()
        self.dirty_detector = DirtyTestDetector()

    def run_hourly(self, metrics: dict) -> dict:
        """
        Run the hourly cycle: ingest → KPIs → decision → receipt.
        """
        # Ingest
        snapshot = self.collector.ingest(metrics)

        # Get all snapshots for KPI computation
        all_snaps = self.collector.get_snapshots(limit=50)

        # Get current experiment (if any)
        running = self.experiments.list_experiments(status="running")
        experiment = running[0] if running else None

        # Compute KPIs
        kpi = self.kpis.compute(all_snaps, experiment)

        # Record decision
        decision = self.decisions.record(kpi)

        return {
            "snapshot": snapshot,
            "kpi": asdict(kpi),
            "decision": decision,
            "snapshot_count": len(all_snaps),
            "experiment": experiment,
        }

    def dashboard(self) -> dict:
        """Get the current dashboard state."""
        snaps = self.collector.get_snapshots(limit=50)
        running = self.experiments.list_experiments(status="running")
        experiment = running[0] if running else None
        kpi = self.kpis.compute(snaps, experiment)
        latest_decision = self.decisions.get_latest()
        bios = self.experiments.list_bios()

        return {
            "immortality": kpi.immortality,
            "virality": kpi.virality,
            "conversion": kpi.conversion,
            "trust": kpi.trust,
            "decision": kpi.decision,
            "reasoning": kpi.reasoning,
            "action": kpi.action,
            "ctr": snaps[0]["ctr"] if snaps else 0,
            "snapshot_count": len(snaps),
            "bios": bios,
            "experiment": experiment,
            "latest_decision": latest_decision,
            "timestamp": datetime.now().isoformat(),
        }


# =============================================================================
# CLI
# =============================================================================

def cli():
    import sys
    args = sys.argv[1:] if len(sys.argv) > 1 else []

    if not args or args[0] in ("-h", "--help", "help"):
        print("ClientPulse OS — Hourly evidence engine for profile conversion")
        print()
        print("Usage:")
        print("  python3 clientpulse.py ingest --daily_views=81 --contact_clicks=4 --days_online=964 ...")
        print("  python3 clientpulse.py dashboard")
        print("  python3 clientpulse.py decisions")
        print("  python3 clientpulse.py approve-bio --name=wolf_v1 --content='...'")
        print("  python3 clientpulse.py start-exp --name=wolf_test --hypothesis='...' --bio_id=...")
        print("  python3 clientpulse.py bios")
        print()
        print("KPIs: Immortality, Virality, Conversion, Trust, Decision")
        return

    cmd = args[0]
    cp = ClientPulseOS()

    if cmd == "ingest":
        metrics = {}
        for a in args[1:]:
            if a.startswith("--"):
                k, v = a.lstrip("--").split("=", 1)
                if k in ("daily_views", "contact_clicks", "days_online", "lifetime_views",
                         "new_visitors", "bookmarks"):
                    metrics[k] = int(v)
                elif k == "profile_visible":
                    metrics[k] = v.lower() in ("true", "1", "yes")
                else:
                    metrics[k] = v
        result = cp.run_hourly(metrics)
        k = result["kpi"]
        print(f"ClientPulse — Metric Ingested")
        print(f"  Snapshot: {result['snapshot']['id']}")
        print(f"  CTR: {result['snapshot']['ctr']}%")
        print(f"  Snapshots: {result['snapshot_count']}")
        print()
        print(f"  IMMORTALITY: {k['immortality']}")
        print(f"  VIRALITY:    {k['virality']}")
        print(f"  CONVERSION:  {k['conversion']}")
        print(f"  TRUST:       {k['trust']}")
        print(f"  DECISION:    {k['decision']}")
        print(f"  Reasoning:   {k['reasoning']}")
        print(f"  Action:      {k['action']}")
        print(f"  Receipt:     {result['decision']['receipt_hash'][:32]}...")
        return

    if cmd == "dashboard":
        d = cp.dashboard()
        print("ClientPulse OS — Dashboard")
        print(f"  IMMORTALITY: {d['immortality']:.4f}")
        print(f"  VIRALITY:    {d['virality']:.4f}")
        print(f"  CONVERSION:  {d['conversion']:.4f}")
        print(f"  TRUST:       {d['trust']:.4f}")
        print(f"  CTR:         {d['ctr']:.2f}%")
        print(f"  DECISION:    {d['decision']}")
        print(f"  Reasoning:   {d['reasoning']}")
        print(f"  Action:      {d['action']}")
        print(f"  Snapshots:   {d['snapshot_count']}")
        print(f"  Bios:        {len(d['bios'])} approved")
        if d.get("experiment"):
            print(f"  Experiment:  {d['experiment']['name']} (running)")
        return

    if cmd == "decisions":
        history = cp.decisions.history(limit=20)
        print(f"ClientPulse — Decision History ({len(history)})")
        for d in history:
            print(f"  {d['decision_time'][:19]}  {d['state']:25s}  imm={d['immortality']:.2f} vir={d['virality']:.2f} conv={d['conversion']:.2f}")
        return

    if cmd == "approve-bio":
        name = ""
        content = ""
        for a in args[1:]:
            if a.startswith("--name="):
                name = a.split("=", 1)[1]
            elif a.startswith("--content="):
                content = a.split("=", 1)[1]
        result = cp.experiments.approve_bio(name, content)
        print(f"Bio approved: {result.get('id', 'error')} — {result.get('name', result.get('error', ''))}")
        return

    if cmd == "bios":
        bios = cp.experiments.list_bios()
        print(f"ClientPulse — Bio Pool ({len(bios)})")
        for b in bios:
            print(f"  {b['id']}  {b['name']:20s}  status={b['status']}  tested={b['tested']}  winner={b['winner']}")
        return

    if cmd == "start-exp":
        name = ""
        hypothesis = ""
        bio_id = ""
        for a in args[1:]:
            if a.startswith("--name="):
                name = a.split("=", 1)[1]
            elif a.startswith("--hypothesis="):
                hypothesis = a.split("=", 1)[1]
            elif a.startswith("--bio_id="):
                bio_id = a.split("=", 1)[1]
        result = cp.experiments.start_experiment(name, hypothesis, bio_id)
        print(f"Experiment started: {result['id']} — {result['name']}")
        print(f"  Hypothesis: {result['hypothesis']}")
        print(f"  Bio: {result['bio_id']}")
        return


if __name__ == "__main__":
    cli()
