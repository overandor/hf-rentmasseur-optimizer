"""
RentMasseur AGI — Python orchestrator layer.
Handles authenticated account operations, dashboard stats, experiments, receipts.
C++ engine handles generation, scoring, training, GA.
"""

import json
import hashlib
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

DATA_DIR = Path("rm_agi/data")
EXPERIMENTS_DIR = DATA_DIR / "experiments"
CANDIDATES_DIR = DATA_DIR / "candidates"
MODELS_DIR = DATA_DIR / "models"
RECEIPTS_DIR = DATA_DIR / "receipts"

for d in [EXPERIMENTS_DIR, CANDIDATES_DIR, MODELS_DIR, RECEIPTS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

CPP_BINARY = "rm_agi/rm_agi"


# ─── Receipt Ledger ───

class ReceiptLedger:
    """Tamper-evident SHA-256 chained receipt ledger."""

    def __init__(self, path: Path = RECEIPTS_DIR / "ledger.jsonl"):
        self.path = path
        self.entries: List[dict] = []
        self._load()

    def _load(self):
        if self.path.exists():
            for line in self.path.open():
                if line.strip():
                    self.entries.append(json.loads(line))

    def add(self, action: str, description: str, data: dict) -> dict:
        prev_hash = self.entries[-1]["hash"] if self.entries else "0" * 64
        ts = datetime.now(timezone.utc).isoformat()
        entry = {
            "index": len(self.entries),
            "timestamp": ts,
            "action": action,
            "description": description,
            "data": data,
            "prev_hash": prev_hash,
        }
        entry_str = json.dumps(entry, sort_keys=True)
        entry["hash"] = hashlib.sha256(entry_str.encode()).hexdigest()
        self.entries.append(entry)
        with self.path.open("a") as f:
            f.write(json.dumps(entry) + "\n")
        return entry

    def verify(self) -> bool:
        for i, entry in enumerate(self.entries):
            prev = self.entries[i - 1]["hash"] if i > 0 else "0" * 64
            if entry["prev_hash"] != prev:
                return False
            check = {k: v for k, v in entry.items() if k != "hash"}
            check_str = json.dumps(check, sort_keys=True)
            expected = hashlib.sha256(check_str.encode()).hexdigest()
            if entry["hash"] != expected:
                return False
        return True

    def summary(self) -> dict:
        return {
            "total_receipts": len(self.entries),
            "chain_valid": self.verify(),
            "last_action": self.entries[-1]["action"] if self.entries else None,
            "last_timestamp": self.entries[-1]["timestamp"] if self.entries else None,
        }


# ─── Profile Observer ───

class ProfileObserver:
    """Reads your account state: visibility, availability, headline, bio, stats."""

    def __init__(self, api):
        self.api = api

    def snapshot(self) -> dict:
        """Take a full snapshot of current profile state."""
        state = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        try:
            about = self.api.get_about()
            state["headline"] = about.get("headline", "")
            state["description"] = about.get("description", "")
            state["description_len"] = len(about.get("description", ""))
            state["visible"] = about.get("isVisible", True)
            state["is_gold"] = about.get("isGold", False)
            state["is_available"] = about.get("isAvailable", False)
            state["is_certified"] = about.get("isCertified", False)
            state["rating"] = about.get("ratingAverage", 0)
            state["reviews"] = about.get("reviewsCount", 0)
            state["username"] = about.get("username", "")
            state["city"] = about.get("city", "")
        except Exception as e:
            state["error"] = str(e)

        try:
            stats = self.api.get_dashboard_stats()
            state["profile_views"] = stats.get("views", 0)
            state["contact_clicks"] = stats.get("contactClicks", 0)
            state["new_visits"] = stats.get("newVisits", 0)
            state["new_emails"] = stats.get("newEmails", 0)
            state["online_bookmarks"] = stats.get("onlineBookmarks", 0)
            pv = state.get("profile_views", 0)
            state["contact_click_rate"] = state["contact_clicks"] / pv if pv > 0 else 0
            state["email_rate"] = state["new_emails"] / pv if pv > 0 else 0
        except Exception as e:
            state["stats_error"] = str(e)

        return state

    def save_snapshot(self, state: dict, label: str = "snapshot") -> Path:
        """Save snapshot to file."""
        path = EXPERIMENTS_DIR / f"snapshot_{label}_{int(time.time())}.json"
        with path.open("w") as f:
            json.dump(state, f, indent=2)
        return path


# ─── Experiment Runner ───

class ExperimentRunner:
    """Manages A/B profile experiments: before/after snapshots, lift calculation."""

    def __init__(self, ledger: ReceiptLedger):
        self.ledger = ledger
        self.experiments_path = EXPERIMENTS_DIR / "experiment_results.jsonl"

    def start_experiment(self, variant_id: str, before_state: dict) -> dict:
        """Record experiment start with before-snapshot."""
        exp = {
            "experiment_id": f"exp_{int(time.time())}",
            "variant_id": variant_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "before": before_state,
            "status": "running",
        }
        self.ledger.add("experiment_start", f"Started experiment {exp['experiment_id']}", exp)
        return exp

    def end_experiment(self, exp: dict, after_state: dict) -> dict:
        """Compute lift and record result."""
        exp["ended_at"] = datetime.now(timezone.utc).isoformat()
        exp["after"] = after_state
        exp["status"] = "completed"

        before = exp["before"]
        after = exp["after"]

        exp["lift_views"] = after.get("profile_views", 0) - before.get("profile_views", 0)
        exp["lift_contact_clicks"] = after.get("contact_clicks", 0) - before.get("contact_clicks", 0)
        exp["lift_emails"] = after.get("new_emails", 0) - before.get("new_emails", 0)
        exp["lift_bookmarks"] = after.get("online_bookmarks", 0) - before.get("online_bookmarks", 0)

        bv = before.get("profile_views", 0)
        av = after.get("profile_views", 0)
        bc = before.get("contact_clicks", 0)
        ac = after.get("contact_clicks", 0)

        before_ctr = bc / bv if bv > 0 else 0
        after_ctr = ac / av if av > 0 else 0
        exp["before_ctr"] = before_ctr
        exp["after_ctr"] = after_ctr
        exp["ctr_lift"] = after_ctr - before_ctr
        exp["result_label"] = "winner" if exp["ctr_lift"] > 0 else "loser"

        with self.experiments_path.open("a") as f:
            f.write(json.dumps(exp, default=str) + "\n")

        self.ledger.add("experiment_end", f"Ended {exp['experiment_id']}: {exp['result_label']}", exp)
        return exp

    def list_experiments(self) -> List[dict]:
        if not self.experiments_path.exists():
            return []
        return [json.loads(l) for l in self.experiments_path.open() if l.strip()]


# ─── Approval Queue ───

class ApprovalQueue:
    """Manages draft candidates awaiting human approval."""

    def __init__(self):
        self.queue_path = CANDIDATES_DIR / "approval_queue.jsonl"
        self.approved_path = CANDIDATES_DIR / "approved.jsonl"

    def import_candidates(self, candidates_path: Path) -> int:
        """Import top candidates from C++ select output into approval queue."""
        count = 0
        with self.queue_path.open("a") as out:
            for line in candidates_path.open():
                if not line.strip():
                    continue
                c = json.loads(line)
                c["status"] = "pending"
                c["imported_at"] = datetime.now(timezone.utc).isoformat()
                out.write(json.dumps(c, ensure_ascii=False) + "\n")
                count += 1
        return count

    def list_pending(self) -> List[dict]:
        if not self.queue_path.exists():
            return []
        return [json.loads(l) for l in self.queue_path.open() if l.strip()]

    def approve(self, variant_id: str) -> Optional[dict]:
        """Approve a candidate by rank or headline match."""
        pending = self.list_pending()
        for c in pending:
            if str(c.get("rank", "")) == variant_id or c.get("headline", "").startswith(variant_id):
                c["status"] = "approved"
                c["approved_at"] = datetime.now(timezone.utc).isoformat()
                with self.approved_path.open("a") as f:
                    f.write(json.dumps(c, ensure_ascii=False) + "\n")
                return c
        return None

    def list_approved(self) -> List[dict]:
        if not self.approved_path.exists():
            return []
        return [json.loads(l) for l in self.approved_path.open() if l.strip()]


# ─── C++ Engine Bridge ───

class CPPEngine:
    """Wraps the C++ rm_agi binary for Python orchestration."""

    def __init__(self, binary: str = CPP_BINARY):
        self.binary = binary

    def inspect(self, bios_path: str) -> str:
        r = subprocess.run([self.binary, "inspect", bios_path], capture_output=True, text=True)
        return r.stdout

    def train(self, bios_path: str, label: str = "reviews", cv: int = 5,
              walk_forward: bool = False, epochs: int = 100, lr: float = 0.001,
              hidden: int = 64) -> str:
        cmd = [self.binary, "train", bios_path, "--label", label, "--cv", str(cv),
               "--epochs", str(epochs), "--lr", str(lr), "--hidden", str(hidden)]
        if walk_forward:
            cmd.append("--walk-forward")
        r = subprocess.run(cmd, capture_output=True, text=True)
        return r.stdout

    def generate(self, count: int = 100000, mode: str = "speech",
                 out: str = None) -> str:
        out = out or str(CANDIDATES_DIR / "candidates.jsonl")
        r = subprocess.run([self.binary, "generate", "--count", str(count),
                            "--mode", mode, "--out", out], capture_output=True, text=True)
        return r.stdout

    def score(self, candidates_path: str, model_path: str = None,
              out: str = None) -> str:
        model_path = model_path or str(MODELS_DIR / "bio_model.bin")
        out = out or str(CANDIDATES_DIR / "scored.jsonl")
        r = subprocess.run([self.binary, "score", candidates_path,
                            "--model", model_path, "--out", out],
                           capture_output=True, text=True)
        return r.stdout

    def evolve(self, scored_path: str, population: int = 5000,
               generations: int = 200, elites: int = 50) -> str:
        r = subprocess.run([self.binary, "evolve", scored_path,
                            "--population", str(population),
                            "--generations", str(generations),
                            "--elites", str(elites)],
                           capture_output=True, text=True)
        return r.stdout

    def select(self, evolved_path: str, top: int = 25,
               diversity: float = 0.5, max_risk: float = 0.15) -> str:
        r = subprocess.run([self.binary, "select", evolved_path,
                            "--top", str(top), "--diversity", str(diversity),
                            "--max-risk", str(max_risk)],
                           capture_output=True, text=True)
        return r.stdout

    def full_pipeline(self, bios_path: str, count: int = 100000,
                      label: str = "reviews", generations: int = 100,
                      top: int = 25) -> dict:
        """Run the complete AGI pipeline: train → generate → score → evolve → select."""
        results = {}
        print("=== RM-AGI Pipeline ===")
        print(f"Corpus: {bios_path}")
        print(f"Generate: {count} candidates")
        print(f"Label: {label}")
        print()

        print("[1/5] Training model on real data...")
        results["train"] = self.train(bios_path, label=label, cv=5, walk_forward=True)

        print("[2/5] Generating candidates...")
        results["generate"] = self.generate(count=count)

        print("[3/5] Scoring candidates...")
        results["score"] = self.score(str(CANDIDATES_DIR / "candidates.jsonl"))

        print("[4/5] Evolving with GA...")
        results["evolve"] = self.evolve(str(CANDIDATES_DIR / "scored.jsonl"),
                                         generations=generations)

        print("[5/5] Selecting top diverse candidates...")
        results["select"] = self.select(str(CANDIDATES_DIR / "ga_elites.jsonl"),
                                         top=top)

        print("\n=== Pipeline Complete ===")
        print(f"Top candidates saved to: {CANDIDATES_DIR}/top_{top}.jsonl")
        return results


# ─── AGI Orchestrator ───

class RMAGIOrchestrator:
    """Top-level orchestrator that ties everything together."""

    def __init__(self, api=None):
        self.api = api
        self.ledger = ReceiptLedger()
        self.engine = CPPEngine()
        self.queue = ApprovalQueue()
        self.experiments = ExperimentRunner(self.ledger)
        self.observer = ProfileObserver(api) if api else None

    def corpus_summary(self, bios_path: str = "rm_traffic/data/real_bios.jsonl") -> str:
        """Show real corpus stats."""
        return self.engine.inspect(bios_path)

    def run_pipeline(self, bios_path: str = "rm_traffic/data/real_bios.jsonl",
                     count: int = 100000, label: str = "reviews",
                     generations: int = 100, top: int = 25) -> dict:
        """Run full C++ pipeline and log receipt."""
        results = self.engine.full_pipeline(bios_path, count, label, generations, top)
        self.ledger.add("pipeline_run", f"Full pipeline: {count} candidates, label={label}", {
            "bios_path": bios_path, "count": count, "label": label,
        })
        return results

    def import_winners(self, path: Path = None) -> int:
        """Import top candidates into approval queue."""
        path = path or CANDIDATES_DIR / "top_25.jsonl"
        count = self.queue.import_candidates(path)
        self.ledger.add("import_winners", f"Imported {count} candidates", {"path": str(path), "count": count})
        return count

    def approve(self, variant_id: str) -> Optional[dict]:
        """Approve a candidate."""
        result = self.queue.approve(variant_id)
        if result:
            self.ledger.add("approve", f"Approved variant: {variant_id}", result)
        return result

    def snapshot(self) -> dict:
        """Take dashboard snapshot."""
        if not self.observer:
            return {"error": "No API connection"}
        state = self.observer.snapshot()
        self.observer.save_snapshot(state)
        self.ledger.add("snapshot", "Profile snapshot taken", state)
        return state

    def start_experiment(self, variant_id: str) -> Optional[dict]:
        """Start a live A/B experiment with before-snapshot."""
        if not self.observer:
            return None
        before = self.observer.snapshot()
        exp = self.experiments.start_experiment(variant_id, before)
        self.ledger.add("experiment_start", f"Started experiment for {variant_id}", exp)
        return exp

    def end_experiment(self, exp: dict) -> dict:
        """End experiment with after-snapshot and lift calculation."""
        if not self.observer:
            return {"error": "No API connection"}
        after = self.observer.snapshot()
        result = self.experiments.end_experiment(exp, after)
        self.ledger.add("experiment_end", f"Experiment {exp['experiment_id']}: {result['result_label']}", result)
        return result

    def dashboard_data(self) -> dict:
        """Collect all data for dashboard display."""
        data = {
            "receipts": self.ledger.summary(),
            "experiments": self.experiments.list_experiments()[-5:],
            "pending_count": len(self.queue.list_pending()),
            "approved_count": len(self.queue.list_approved()),
        }
        if self.observer:
            try:
                data["account"] = self.observer.snapshot()
            except:
                data["account"] = {"error": "Cannot reach API"}
        return data

    def receipt_report(self) -> str:
        """Print receipt ledger summary."""
        s = self.ledger.summary()
        lines = [
            "RECEIPT LEDGER",
            f"  Total receipts: {s['total_receipts']}",
            f"  Chain valid:   {s['chain_valid']}",
            f"  Last action:   {s['last_action']}",
            f"  Last timestamp:{s['last_timestamp']}",
        ]
        return "\n".join(lines)
