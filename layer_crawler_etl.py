"""
Layer Crawler ETL Engine
==========================

Adds a receipt-based evidence layer above the email crawler:

    Sources
    → Crawlers
    → Extractors
    → Normalizers
    → Classifiers
    → Evidence Scorers
    → Receipts
    → HardenRank / ProdScore

POptimizer hard rule: No receipt → no production claim.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import sqlite3
import subprocess
import time
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import requests


# ─── Config ─────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.resolve()
RECEIPTS_DIR = BASE_DIR / "receipts"
RECEIPTS_DIR.mkdir(exist_ok=True)
RAW_DIR = RECEIPTS_DIR / "raw"
RAW_DIR.mkdir(exist_ok=True)
DB_PATH = str(BASE_DIR / "data" / "emails10k.db")

SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|secret|password|token|private[_-]?key|aws[_-]?access|ghp_"
    r"|sk-)[\s]*[=:][\s]*['\"]?[a-z0-9\-_]{16,}['\"]?",
    re.MULTILINE,
)

# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class EvidenceReceipt:
    system: str
    subject: str
    source: str
    timestamp: str
    artifact: str
    signals: dict[str, Any] = field(default_factory=dict)
    scores: dict[str, float] = field(default_factory=dict)
    hardening: list[str] = field(default_factory=list)
    receipt_id: str = ""
    parent_id: str = ""

    def __post_init__(self):
        if not self.receipt_id:
            payload = f"{self.system}:{self.subject}:{self.source}:{self.timestamp}:{json.dumps(self.signals, sort_keys=True)}"
            self.receipt_id = hashlib.sha256(payload.encode()).hexdigest()[:32]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, receipts_dir: Path = RECEIPTS_DIR) -> Path:
        path = receipts_dir / f"{self.receipt_id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return path


@dataclass
class EtlRun:
    run_id: str
    timestamp: str
    receipts: list[EvidenceReceipt] = field(default_factory=list)
    aggregate_scores: dict[str, float] = field(default_factory=dict)
    hardening_actions: list[str] = field(default_factory=list)

    def save(self, receipts_dir: Path = RECEIPTS_DIR) -> Path:
        path = receipts_dir / f"run_{self.run_id}.json"
        data = {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "receipt_count": len(self.receipts),
            "receipt_ids": [r.receipt_id for r in self.receipts],
            "aggregate_scores": self.aggregate_scores,
            "hardening_actions": self.hardening_actions,
        }
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        return path


# ─── Layer 0: Source Registry ────────────────────────────────────────────────

class SourceRegistry:
    def __init__(self):
        self.sources: list[dict[str, Any]] = []

    def register(self, name: str, source_type: str, locator: str, meta: dict | None = None):
        self.sources.append({
            "name": name,
            "type": source_type,
            "locator": locator,
            "meta": meta or {},
        })

    def default_project_registry(self) -> "SourceRegistry":
        """Register the local email-crawler project as sources to verify."""
        self.register("email_crawler_webapp", "code", "crawler_webapp.py")
        self.register("project_requirements", "manifest", "requirements.txt")
        self.register("project_readme", "docs", "README.md")
        self.register("project_dockerfile", "build", "Dockerfile")
        self.register("crawler_database", "artifact", "data/emails10k.db")
        self.register("runtime_http", "runtime", "http://localhost:7860")
        return self


# ─── Layer 1: Subject Crawlers ──────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CodeCrawler:
    subject = "code"

    def crawl(self, file_path: str) -> dict[str, Any]:
        path = BASE_DIR / file_path
        if not path.exists():
            return {"found": False, "lines": 0, "functions": 0, "imports": []}
        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        functions = len(re.findall(r"^\s*def\s+\w+", text, re.MULTILINE))
        classes = len(re.findall(r"^\s*class\s+\w+", text, re.MULTILINE))
        imports = re.findall(r"^(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_.]*)", text, re.MULTILINE)
        return {
            "found": True,
            "lines": len(lines),
            "functions": functions,
            "classes": classes,
            "imports": sorted(set(imports)),
            "sha256": hashlib.sha256(text.encode()).hexdigest()[:16],
        }


class DependencyCrawler:
    subject = "dependency"

    def crawl(self, manifest_path: str = "requirements.txt") -> dict[str, Any]:
        path = BASE_DIR / manifest_path
        if not path.exists():
            return {"found": False, "packages": [], "unpinned": []}
        text = path.read_text(encoding="utf-8", errors="ignore")
        packages = [line.strip() for line in text.splitlines() if line.strip() and not line.startswith("#")]
        unpinned = [p for p in packages if "==" not in p and ">=" not in p]
        return {
            "found": True,
            "packages": packages,
            "unpinned": unpinned,
            "package_count": len(packages),
        }


class LicenseCrawler:
    subject = "license"

    def crawl(self, readme_path: str = "README.md") -> dict[str, Any]:
        path = BASE_DIR / readme_path
        license_line = None
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                if line.lower().startswith("license:"):
                    license_line = line.split(":", 1)[1].strip()
                    break
        return {
            "license_declared": license_line,
            "license_file_exists": (BASE_DIR / "LICENSE").exists(),
            "license_in_readme": license_line is not None,
        }


class TestBuildCrawler:
    subject = "test_build"

    def crawl(self) -> dict[str, Any]:
        has_dockerfile = (BASE_DIR / "Dockerfile").exists()
        has_tests = any(
            (BASE_DIR / name).exists() or (BASE_DIR / "tests" / name).exists()
            for name in ["test_crawler.py", "tests", "pytest.ini", "pyproject.toml"]
        )
        has_ci = (BASE_DIR / ".github" / "workflows").is_dir()
        return {
            "dockerfile_present": has_dockerfile,
            "tests_present": has_tests,
            "ci_present": has_ci,
        }


class BrowserRuntimeCrawler:
    subject = "runtime"

    def crawl(self, url: str = "http://localhost:7860", timeout: int = 5) -> dict[str, Any]:
        result = {
            "reachable": False,
            "status_code": 0,
            "latency_ms": 0,
            "api_ok": False,
            "console_errors": None,
            "failed_requests": None,
        }
        try:
            start = time.time()
            r = requests.get(url, timeout=timeout)
            result["latency_ms"] = round((time.time() - start) * 1000, 2)
            result["status_code"] = r.status_code
            result["reachable"] = r.status_code == 200
            try:
                api = requests.get(f"{url}/api/stats", timeout=timeout)
                result["api_ok"] = api.status_code == 200
            except Exception:
                result["api_ok"] = False
        except Exception as e:
            result["error"] = str(e)
        return result


class ArtifactCrawler:
    subject = "artifact"

    def crawl(self, db_path: str = DB_PATH) -> dict[str, Any]:
        exists = os.path.exists(db_path)
        stats = {"db_exists": exists, "email_count": 0, "category_counts": {}, "high_score_count": 0}
        if exists:
            try:
                conn = sqlite3.connect(db_path)
                c = conn.cursor()
                c.execute("SELECT COUNT(*) FROM emails")
                stats["email_count"] = c.fetchone()[0]
                c.execute("SELECT category, COUNT(*) FROM emails GROUP BY category")
                stats["category_counts"] = dict(c.fetchall())
                c.execute("SELECT COUNT(*) FROM emails WHERE response_likelihood >= 70")
                stats["high_score_count"] = c.fetchone()[0]
                conn.close()
            except Exception as e:
                stats["error"] = str(e)
        return stats


class SecuritySecretsCrawler:
    subject = "security"

    def crawl(self, glob: str = "*.py") -> dict[str, Any]:
        hits = []
        for path in BASE_DIR.glob(glob):
            if path.name == __file__:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for i, line in enumerate(text.splitlines(), 1):
                if SECRET_RE.search(line):
                    hits.append({"file": path.name, "line": i, "snippet": line.strip()[:80]})
        return {
            "files_scanned": len(list(BASE_DIR.glob(glob))),
            "secret_pattern_hits": len(hits),
            "hits": hits[:10],
            "secrets_exposed": 1 if hits else 0,
        }


class DocsClaimsCrawler:
    subject = "docs_claims"

    def crawl(self, readme_path: str = "README.md") -> dict[str, Any]:
        path = BASE_DIR / readme_path
        if not path.exists():
            return {"readme_exists": False, "claims": []}
        text = path.read_text(encoding="utf-8", errors="ignore")
        claims = []
        # Simple claim extraction: lines under "Features" or starting with "-"
        in_features = False
        for line in text.splitlines():
            low = line.lower()
            if "features" in low or "##" in low and "feature" in low:
                in_features = True
                continue
            if in_features and line.startswith("##"):
                in_features = False
            if in_features and line.strip().startswith("-"):
                claims.append(line.strip().lstrip("- ").strip())
        return {
            "readme_exists": True,
            "claims": claims,
            "claim_count": len(claims),
            "has_license_declaration": "license" in text.lower(),
        }


# ─── Layer 2: ETL Pipeline ────────────────────────────────────────────────────

class EtlPipeline:
    def __init__(self, system: str = "Email Crawler Dashboard"):
        self.system = system
        self.crawlers: dict[str, Callable[[], dict[str, Any]]] = {}
        self.receipts: list[EvidenceReceipt] = []
        self._register_default_crawlers()

    def _register_default_crawlers(self):
        cc = CodeCrawler()
        dc = DependencyCrawler()
        lc = LicenseCrawler()
        tbc = TestBuildCrawler()
        brc = BrowserRuntimeCrawler()
        ac = ArtifactCrawler()
        ssc = SecuritySecretsCrawler()
        dcc = DocsClaimsCrawler()

        self.crawlers["code"] = lambda: cc.crawl("crawler_webapp.py")
        self.crawlers["dependency"] = lambda: dc.crawl("requirements.txt")
        self.crawlers["license"] = lambda: lc.crawl("README.md")
        self.crawlers["test_build"] = lambda: tbc.crawl()
        self.crawlers["runtime"] = lambda: brc.crawl("http://localhost:7860")
        self.crawlers["artifact"] = lambda: ac.crawl(DB_PATH)
        self.crawlers["security"] = lambda: ssc.crawl("*.py")
        self.crawlers["docs_claims"] = lambda: dcc.crawl("README.md")

    def run(self, save: bool = True, runtime_url: str = "http://localhost:7860") -> EtlRun:
        self.receipts = []
        run_id = hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]
        timestamp = _now()

        for subject, crawler in self.crawlers.items():
            raw = crawler()
            receipt = self._build_receipt(subject, raw, timestamp, runtime_url)
            self.receipts.append(receipt)
            if save:
                receipt.save()

        aggregate = self._aggregate_scores(self.receipts)
        hardening = self._generate_hardening(self.receipts, aggregate)
        run = EtlRun(
            run_id=run_id,
            timestamp=timestamp,
            receipts=self.receipts,
            aggregate_scores=aggregate,
            hardening_actions=hardening,
        )
        if save:
            run.save()
        return run

    def _build_receipt(self, subject: str, raw: dict, timestamp: str, runtime_url: str) -> EvidenceReceipt:
        signals = self._normalize_signals(subject, raw, runtime_url)
        scores = self._score_signals(subject, signals)
        artifact = self._artifact_path(subject, raw)
        return EvidenceReceipt(
            system=self.system,
            subject=subject,
            source=self._source_name(subject),
            timestamp=timestamp,
            artifact=artifact,
            signals=signals,
            scores=scores,
            hardening=self._subject_hardening(subject, signals, scores),
        )

    def _normalize_signals(self, subject: str, raw: dict, runtime_url: str) -> dict:
        defaults = {
            "build_verified": False,
            "tests_verified": False,
            "runtime_verified": False,
            "console_errors": None,
            "failed_requests": None,
            "secrets_exposed": 0,
            "license_conflict": 0,
            "unpinned_dependencies": 0,
            "receipts_present": 0,
            "readme_claims": 0,
        }
        if subject == "code":
            defaults["build_verified"] = raw.get("found", False)
            defaults["lines_of_code"] = raw.get("lines", 0)
            defaults["function_count"] = raw.get("functions", 0)
        elif subject == "dependency":
            defaults["unpinned_dependencies"] = len(raw.get("unpinned", []))
            defaults["dependency_count"] = raw.get("package_count", 0)
        elif subject == "license":
            defaults["license_conflict"] = 0 if raw.get("license_declared") else 1
        elif subject == "test_build":
            defaults["build_verified"] = raw.get("dockerfile_present", False)
            defaults["tests_verified"] = raw.get("tests_present", False)
            defaults["ci_present"] = raw.get("ci_present", False)
        elif subject == "runtime":
            defaults["runtime_verified"] = raw.get("reachable", False)
            defaults["latency_ms"] = raw.get("latency_ms", 0)
            defaults["api_ok"] = raw.get("api_ok", False)
        elif subject == "artifact":
            defaults["receipts_present"] = raw.get("email_count", 0)
            defaults["db_exists"] = raw.get("db_exists", False)
        elif subject == "security":
            defaults["secrets_exposed"] = raw.get("secrets_exposed", 0)
            defaults["files_scanned"] = raw.get("files_scanned", 0)
        elif subject == "docs_claims":
            defaults["readme_claims"] = raw.get("claim_count", 0)
        return defaults

    def _source_name(self, subject: str) -> str:
        mapping = {
            "code": "local_file",
            "dependency": "requirements.txt",
            "license": "README.md",
            "test_build": "filesystem",
            "runtime": "http_probe",
            "artifact": "sqlite_db",
            "security": "static_scan",
            "docs_claims": "readme",
        }
        return mapping.get(subject, subject)

    def _artifact_path(self, subject: str, raw: dict) -> str:
        if subject == "runtime":
            return "receipts/runtime-proof.json"
        if subject == "code":
            return f"receipts/{raw.get('sha256', 'code')}-code.json"
        return f"receipts/{subject}-proof.json"

    def _score_signals(self, subject: str, signals: dict) -> dict[str, float]:
        evidence = 0
        reality_penalty = 0
        ip_risk = 0
        runtime_risk = 0

        if subject == "code":
            evidence = min(100, 20 + signals.get("lines_of_code", 0) / 10)
        elif subject == "dependency":
            evidence = 60 if signals.get("dependency_count", 0) > 0 else 0
            reality_penalty = signals.get("unpinned_dependencies", 0) * 8
        elif subject == "license":
            evidence = 100 if not signals.get("license_conflict") else 40
        elif subject == "test_build":
            evidence = (
                (20 if signals.get("build_verified") else 0)
                + (40 if signals.get("tests_verified") else 0)
                + (20 if signals.get("ci_present") else 0)
            )
            reality_penalty = 40 if not signals.get("tests_verified") else 0
        elif subject == "runtime":
            evidence = 80 if signals.get("runtime_verified") else 0
            reality_penalty = 30 if not signals.get("runtime_verified") else 0
            runtime_risk = 20 if not signals.get("api_ok") else 0
        elif subject == "artifact":
            evidence = min(100, 20 + signals.get("receipts_present", 0))
        elif subject == "security":
            evidence = 100 if signals.get("secrets_exposed") == 0 else 20
            ip_risk = 100 if signals.get("secrets_exposed") > 0 else 0
        elif subject == "docs_claims":
            evidence = min(100, 20 + signals.get("readme_claims", 0) * 10)

        prod_score = max(0, min(100, evidence - reality_penalty - runtime_risk))
        return {
            "evidence": round(evidence, 1),
            "reality_penalty": round(reality_penalty, 1),
            "prod_score": round(prod_score, 1),
            "ip_risk": round(ip_risk, 1),
            "runtime_risk": round(runtime_risk, 1),
            "harden_rank": round(100 - prod_score, 1),
        }

    def _subject_hardening(self, subject: str, signals: dict, scores: dict) -> list[str]:
        actions = []
        if subject == "test_build" and not signals.get("tests_verified"):
            actions.append("Add tests (pytest) and run them in CI.")
        if subject == "dependency" and signals.get("unpinned_dependencies"):
            actions.append("Pin dependency versions in requirements.txt.")
        if subject == "runtime" and not signals.get("runtime_verified"):
            actions.append("Start the web app before claiming runtime proof.")
        if subject == "security" and signals.get("secrets_exposed"):
            actions.append("Rotate exposed secrets and move them to environment variables.")
        if subject == "license" and signals.get("license_conflict"):
            actions.append("Add a license declaration to README.md or a LICENSE file.")
        if scores.get("prod_score", 0) < 50:
            actions.append(f"[{subject}] ProdScore below 50; harden before production claim.")
        return actions

    def _aggregate_scores(self, receipts: list[EvidenceReceipt]) -> dict[str, float]:
        if not receipts:
            return {}
        keys = ["evidence", "reality_penalty", "prod_score", "ip_risk", "runtime_risk", "harden_rank"]
        agg = {}
        for key in keys:
            values = [r.scores.get(key, 0) for r in receipts if key in r.scores]
            agg[key] = round(sum(values) / len(values), 1) if values else 0
        return agg

    def _generate_hardening(self, receipts: list[EvidenceReceipt], aggregate: dict) -> list[str]:
        actions = []
        for r in receipts:
            actions.extend(r.hardening)
        if aggregate.get("prod_score", 0) < 60:
            actions.append("Aggregate ProdScore below 60; do not claim production readiness.")
        if aggregate.get("ip_risk", 0) > 0:
            actions.append("IP risk detected; audit secrets before any external disclosure.")
        return sorted(set(actions))


# ─── Convenience API ──────────────────────────────────────────────────────────

def run_etl(system: str = "Email Crawler Dashboard", save: bool = True, runtime_url: str = "http://localhost:7860") -> dict[str, Any]:
    pipeline = EtlPipeline(system=system)
    run = pipeline.run(save=save, runtime_url=runtime_url)
    return {
        "run_id": run.run_id,
        "timestamp": run.timestamp,
        "receipt_count": len(run.receipts),
        "aggregate_scores": run.aggregate_scores,
        "hardening_actions": run.hardening_actions,
        "receipts": [r.to_dict() for r in run.receipts],
    }


def latest_run() -> dict[str, Any] | None:
    paths = sorted(RECEIPTS_DIR.glob("run_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not paths:
        return None
    return json.loads(paths[0].read_text(encoding="utf-8"))


def list_receipts() -> list[dict[str, Any]]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RECEIPTS_DIR.glob("*.json")) if not p.name.startswith("run_")]


if __name__ == "__main__":
    result = run_etl()
    print(json.dumps(result, indent=2))
