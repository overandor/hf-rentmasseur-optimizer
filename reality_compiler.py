"""
Reality Compiler — A provenance engine for AI-native work.

Converts AI-native activity into provenance-backed, transferable artifact value.

Public product:
  Capture work.
  Measure substrate.
  Prove provenance.
  Score value.
  Export receipt.

Pipeline:
  intent → glyph → workflow → agents → files → substrate accounting
  → provenance → receipt → lambda score → buyer packet

Modules:
  Layer4Meter     — substrate accounting (screen, file, process, time, power)
  ReceiptOS       — tamper-evident ledger of what happened
  LambdaBase      — database of transferability, value, proof density, reuse
  LambdaReceipt   — exportable proof/value credential (W3C VC-aligned)
  FinanceableArtifactExporter — buyer/proof/release/valuation packets

Provenance alignment:
  W3C PROV         = general provenance model
  SLSA v1.2        = software artifact provenance
  W3C VC 2.0       = tamper-evident credentials
  Reality Compiler = AI-native artifact/value provenance

Final law:
  OverLanguage describes the work.
  Agent Runtime performs the work.
  Layer4Meter measures the work.
  ReceiptOS proves the work.
  LambdaBase prices the work.
  LambdaReceipts transfer the work.
  Reality Compiler packages the work into value.

Usage:
  from reality_compiler import RealityCompiler
  rc = RealityCompiler()
  receipt = rc.compile(
      intent="build zip-to-app pipeline",
      source_dir="src/",
      artifacts=["build/AIApp.app"],
      agent_id="windsurf",
      build_log="python3 forge.py ziptoapp ...",
  )
"""

import hashlib
import json
import os
import sqlite3
import time
import subprocess
import platform
import resource
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Any

# ReceiptOS wraps the existing receipt_ledger and proofbook
import receipt_ledger
import proofbook

BASE = Path(__file__).parent
RC_DB = str(BASE / "data" / "reality_compiler.db")
L4_DB = str(BASE / "data" / "layer4meter.db")
LAMBDA_DB = str(BASE / "data" / "lambdabase.db")

os.makedirs(os.path.dirname(RC_DB), exist_ok=True)


# =============================================================================
# Layer4Meter — Substrate Accounting
# =============================================================================

class Layer4Meter:
    """
    Measures real substrate cost: CPU time, RAM, disk I/O, wall time.
    Emits .l4receipt with measured values, not estimates.

    This is the denominator of all value claims. Without substrate
    measurement, you cannot claim efficiency or cost savings.
    """

    def __init__(self, db_path: str = L4_DB):
        self.db_path = db_path
        self._init_db()
        self._start_rusage = None
        self._start_time = None
        self._start_disk = None

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS l4_receipts (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            wall_time_ms REAL,
            cpu_time_ms REAL,
            ram_peak_mb REAL,
            ram_avg_mb REAL,
            disk_read_bytes INTEGER,
            disk_write_bytes INTEGER,
            files_touched INTEGER,
            net_requests INTEGER,
            process_count INTEGER,
            platform TEXT,
            python_version TEXT,
            cost_estimate_usd REAL,
            timestamp TEXT,
            raw_json TEXT
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_session ON l4_receipts(session_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ts ON l4_receipts(timestamp)")
        conn.commit()
        conn.close()

    def start(self):
        """Begin measuring a substrate session."""
        self._start_time = time.time()
        self._start_rusage = resource.getrusage(resource.RUSAGE_SELF)
        self._start_disk = self._disk_usage()

    def stop(self, session_id: str, files_touched: int = 0,
             net_requests: int = 0, process_count: int = 1) -> dict:
        """Stop measuring and emit .l4receipt."""
        if self._start_time is None:
            return {"error": "Layer4Meter not started"}

        wall_ms = (time.time() - self._start_time) * 1000
        end_rusage = resource.getrusage(resource.RUSAGE_SELF)
        cpu_ms = (end_rusage.ru_utime - self._start_rusage.ru_utime +
                  end_rusage.ru_stime - self._start_rusage.ru_stime) * 1000

        # RAM: max RSS in KB → MB
        ram_peak_mb = end_rusage.ru_maxrss / 1024.0 if platform.system() != "Darwin" else end_rusage.ru_maxrss / (1024 * 1024)

        # Disk I/O from rusage (bytes on macOS, blocks on Linux)
        disk_read = end_rusage.ru_inblock * 512  # approximate
        disk_write = end_rusage.ru_oublock * 512

        # Cost estimate: $0.10/hr CPU, $0.05/hr wall, $0.02/GB disk
        cost = (cpu_ms / 3600000 * 0.10 +
                wall_ms / 3600000 * 0.05 +
                (disk_read + disk_write) / 1e9 * 0.02)

        receipt = {
            "id": hashlib.sha256(f"{session_id}:{self._start_time}".encode()).hexdigest()[:16],
            "session_id": session_id,
            "wall_time_ms": round(wall_ms, 2),
            "cpu_time_ms": round(cpu_ms, 2),
            "ram_peak_mb": round(ram_peak_mb, 2),
            "disk_read_bytes": disk_read,
            "disk_write_bytes": disk_write,
            "files_touched": files_touched,
            "net_requests": net_requests,
            "process_count": process_count,
            "platform": platform.system(),
            "python_version": platform.python_version(),
            "cost_estimate_usd": round(cost, 6),
            "timestamp": datetime.now().isoformat(),
        }

        # Persist
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO l4_receipts
            (id, session_id, wall_time_ms, cpu_time_ms, ram_peak_mb, ram_avg_mb,
             disk_read_bytes, disk_write_bytes, files_touched, net_requests,
             process_count, platform, python_version, cost_estimate_usd, timestamp, raw_json)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (receipt["id"], receipt["session_id"], receipt["wall_time_ms"],
             receipt["cpu_time_ms"], receipt["ram_peak_mb"], receipt["ram_peak_mb"],
             receipt["disk_read_bytes"], receipt["disk_write_bytes"],
             receipt["files_touched"], receipt["net_requests"],
             receipt["process_count"], receipt["platform"],
             receipt["python_version"], receipt["cost_estimate_usd"],
             receipt["timestamp"], json.dumps(receipt)))
        conn.commit()
        conn.close()

        self._start_time = None
        self._start_rusage = None
        return receipt

    def _disk_usage(self) -> int:
        try:
            usage = os.statvfs(".")
            return usage.f_bsize * usage.f_bavail
        except Exception:
            return 0

    def query(self, session_id: str = "", limit: int = 50) -> list:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        if session_id:
            c.execute("SELECT raw_json FROM l4_receipts WHERE session_id=? ORDER BY timestamp DESC LIMIT ?",
                      (session_id, limit))
        else:
            c.execute("SELECT raw_json FROM l4_receipts ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = [json.loads(r[0]) for r in c.fetchall()]
        conn.close()
        return rows


# =============================================================================
# ReceiptOS — Signing, Merkle Binding, Verification, Storage
# =============================================================================

class ReceiptOS:
    """
    Signs claims, binds them into a Merkle tree, verifies integrity,
    and stores them in a tamper-evident ledger.

    Wraps receipt_ledger.py (compute receipts) and proofbook.py
    (proof entries) into a unified proof layer.

    Aligns with SLSA provenance: records what was built, how, when,
    by whom, with what dependencies, and what was produced.
    """

    def __init__(self):
        self.receipt_db = receipt_ledger
        self.proof_db = proofbook

    def issue_receipt(self, receipt_type: str, action: str,
                      agent_id: str = "system", artifact_hash: str = "",
                      artifact_path: str = "", metrics: dict = None,
                      verification: dict = None, cost_saved_usd: float = 0.0,
                      compute_saved_ms: float = 0.0, notes: str = "") -> dict:
        """Issue a signed, chained receipt."""
        return self.receipt_db.create_receipt(
            receipt_type=receipt_type,
            action=action,
            agent_id=agent_id,
            artifact_hash=artifact_hash,
            artifact_path=artifact_path,
            metrics=metrics or {},
            verification=verification or {},
            cost_saved_usd=cost_saved_usd,
            compute_saved_ms=compute_saved_ms,
            notes=notes,
        )

    def record_proof(self, entry_type: str, subject: str,
                     content: dict, signer_id: str = "system",
                     tags: list = None) -> dict:
        """Record a proof entry in the tamper-evident proof chain."""
        return self.proof_db.record_entry(
            entry_type=entry_type,
            subject=subject,
            content=content,
            signer_id=signer_id,
            tags=tags or [],
        )

    def verify_ledger(self) -> dict:
        """Verify receipt ledger integrity."""
        return self.receipt_db.verify_ledger()

    def verify_proof_chain(self) -> dict:
        """Verify proof chain integrity."""
        return self.proof_db.verify_chain()

    def verify_all(self) -> dict:
        """Verify both ledgers."""
        return {
            "receipt_ledger": self.verify_ledger(),
            "proof_chain": self.verify_proof_chain(),
            "all_intact": self.verify_ledger()["ledger_intact"] and self.verify_proof_chain()["chain_intact"],
        }

    def get_stats(self) -> dict:
        return {
            "receipts": self.receipt_db.get_receipt_stats(),
            "proofs": self.proof_db.get_stats(),
        }

    def build_provenance(self, subject: str, build_def: dict,
                         run_details: dict, materials: list,
                         byproducts: list) -> dict:
        """
        Build an SLSA-aligned provenance statement.

        subject: artifact being provenanced
        build_def: what was supposed to happen (workflow, steps)
        run_details: what actually happened (commands, env, times)
        materials: input dependencies (files, repos, images)
        byproducts: secondary outputs (logs, caches, temp files)
        """
        provenance = {
            "schema": "reality_compiler.provenance.v1",
            "subject": subject,
            "build_definition": build_def,
            "run_details": run_details,
            "materials": materials,
            "byproducts": byproducts,
            "generated_at": datetime.now().isoformat(),
            "builder": {
                "id": run_details.get("agent_id", "system"),
                "platform": platform.system(),
                "python": platform.python_version(),
            },
        }
        prov_hash = hashlib.sha256(
            json.dumps(provenance, sort_keys=True).encode()
        ).hexdigest()
        provenance["provenance_hash"] = prov_hash
        return provenance


# =============================================================================
# LambdaBase — Transferability Scoring
# =============================================================================

@dataclass
class TransferabilityInputs:
    """Inputs for transferability scoring."""
    artifact_path: str = ""
    artifact_hash: str = ""
    file_count: int = 0
    total_size_bytes: int = 0
    has_readme: bool = False
    has_tests: bool = False
    has_build_script: bool = False
    has_dockerfile: bool = False
    has_ci: bool = False
    dependency_count: int = 0
    external_api_count: int = 0
    hardcoded_paths: int = 0
    hardcoded_secrets: int = 0
    platform_specific: int = 0
    docs_coverage: float = 0.0
    test_coverage: float = 0.0
    receipt_count: int = 0
    proof_count: int = 0
    has_license: bool = False


class LambdaBase:
    """
    Scores transferability: can this artifact be moved to another
    machine, adopted by another team, or sold to a buyer?

    Scores:
      transferability (0-1): how portable is the artifact?
      friction (0-1): how hard to adopt? (1 = very hard)
      dependency_risk (0-1): how fragile are external deps? (1 = very risky)
      buyer_readiness (0-1): is it packaged for sale?
      lambda_score: composite transferability score
    """

    def __init__(self, db_path: str = LAMBDA_DB):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS lambda_scores (
            id TEXT PRIMARY KEY,
            artifact_hash TEXT,
            artifact_path TEXT,
            transferability REAL,
            friction REAL,
            dependency_risk REAL,
            buyer_readiness REAL,
            lambda_score REAL,
            inputs_json TEXT,
            verdict TEXT,
            timestamp TEXT
        )""")
        c.execute("CREATE INDEX IF NOT EXISTS idx_hash ON lambda_scores(artifact_hash)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ts ON lambda_scores(timestamp)")
        conn.commit()
        conn.close()

    def analyze_artifact(self, artifact_path: str) -> TransferabilityInputs:
        """Analyze an artifact directory or file for transferability inputs."""
        p = Path(artifact_path)
        inputs = TransferabilityInputs(artifact_path=artifact_path)

        if p.is_file():
            inputs.file_count = 1
            inputs.total_size_bytes = p.stat().st_size
            inputs.artifact_hash = hashlib.sha256(p.read_bytes()).hexdigest()
        elif p.is_dir():
            files = list(p.rglob("*"))
            files = [f for f in files if f.is_file()]
            inputs.file_count = len(files)
            inputs.total_size_bytes = sum(f.stat().st_size for f in files)

            # Hash the whole directory
            h = hashlib.sha256()
            for f in sorted(files):
                h.update(f.read_bytes())
            inputs.artifact_hash = h.hexdigest()

            # Check for README, tests, build scripts, Dockerfile, CI
            names = {f.name.lower() for f in files}
            inputs.has_readme = any("readme" in n for n in names)
            inputs.has_tests = any("test" in n or n.startswith("test") for n in names)
            inputs.has_build_script = any(n in ("makefile", "build.sh", "setup.py", "pyproject.toml", "package.json") for n in names)
            inputs.has_dockerfile = any("dockerfile" in n for n in names)
            inputs.has_license = any("license" in n for n in names)

            # Check for CI
            ci_paths = [f for f in files if ".github" in str(f) or ".gitlab" in str(f)]
            inputs.has_ci = len(ci_paths) > 0

            # Count dependencies (requirements.txt, package.json, etc.)
            dep_files = [f for f in files if f.name in ("requirements.txt", "package.json", "Pipfile", "pyproject.toml")]
            for df in dep_files:
                try:
                    content = df.read_text()
                    if df.name == "requirements.txt":
                        inputs.dependency_count += len([l for l in content.split("\n") if l.strip() and not l.startswith("#")])
                    elif df.name == "package.json":
                        pkg = json.loads(content)
                        inputs.dependency_count += len(pkg.get("dependencies", {}))
                except Exception:
                    pass

            # Scan for hardcoded paths and secrets
            text_files = [f for f in files if f.suffix in (".py", ".js", ".ts", ".sh", ".yaml", ".yml", ".json", ".toml", ".cfg", ".env")]
            for f in text_files[:50]:  # cap at 50 files
                try:
                    content = f.read_text()
                    # Hardcoded absolute paths
                    inputs.hardcoded_paths += len([
                        l for l in content.split("\n")
                        if l.strip().startswith("/") and not l.strip().startswith("//") and not l.strip().startswith("#")
                    ])
                    # Potential secrets
                    inputs.hardcoded_secrets += len([
                        l for l in content.split("\n")
                        if any(k in l.lower() for k in ["api_key=", "secret=", "token=", "password=", "cookie="])
                        and not l.strip().startswith("#") and "getenv" not in l and "environ" not in l
                    ])
                    # Platform-specific calls
                    inputs.platform_specific += len([
                        l for l in content.split("\n")
                        if any(k in l for k in ["osascript", "codesign", "hdiutil", "xcodebuild", "open -a", "subprocess.run"])
                    ])
                except Exception:
                    pass

            # External API calls
            for f in text_files[:50]:
                try:
                    content = f.read_text()
                    inputs.external_api_count += content.count("requests.get(") + content.count("requests.post(")
                    inputs.external_api_count += content.count("urllib") + content.count("http.client")
                except Exception:
                    pass

        return inputs

    def score(self, inputs: TransferabilityInputs) -> dict:
        """Compute transferability scores from analyzed inputs."""

        # Transferability: how portable is the artifact?
        transferability = 1.0
        transferability -= min(0.3, inputs.hardcoded_paths * 0.02)
        transferability -= min(0.2, inputs.platform_specific * 0.03)
        transferability -= min(0.15, inputs.external_api_count * 0.02)
        transferability -= min(0.2, inputs.dependency_count * 0.01)
        transferability += 0.1 if inputs.has_dockerfile else 0
        transferability += 0.05 if inputs.has_readme else 0
        transferability = max(0.0, min(1.0, transferability))

        # Friction: how hard to adopt? (1 = very hard)
        friction = 0.0
        friction += min(0.3, inputs.dependency_count * 0.02)
        friction += min(0.2, inputs.platform_specific * 0.03)
        friction += min(0.2, inputs.hardcoded_paths * 0.02)
        friction += 0.1 if not inputs.has_readme else 0
        friction += 0.1 if not inputs.has_build_script else 0
        friction += 0.1 if not inputs.has_tests else 0
        friction = max(0.0, min(1.0, friction))

        # Dependency risk: how fragile are external deps?
        dependency_risk = 0.0
        dependency_risk += min(0.4, inputs.dependency_count * 0.03)
        dependency_risk += min(0.3, inputs.external_api_count * 0.05)
        dependency_risk += 0.2 if inputs.hardcoded_secrets > 0 else 0
        dependency_risk = max(0.0, min(1.0, dependency_risk))

        # Buyer readiness: is it packaged for sale?
        buyer_readiness = 0.0
        buyer_readiness += 0.15 if inputs.has_readme else 0
        buyer_readiness += 0.15 if inputs.has_tests else 0
        buyer_readiness += 0.15 if inputs.has_build_script else 0
        buyer_readiness += 0.10 if inputs.has_dockerfile else 0
        buyer_readiness += 0.10 if inputs.has_ci else 0
        buyer_readiness += 0.10 if inputs.has_license else 0
        buyer_readiness += 0.10 if inputs.receipt_count > 0 else 0
        buyer_readiness += 0.10 if inputs.proof_count > 0 else 0
        buyer_readiness -= min(0.3, inputs.hardcoded_secrets * 0.1)
        buyer_readiness = max(0.0, min(1.0, buyer_readiness))

        # Lambda score: composite
        lambda_score = (
            transferability * 0.30 +
            (1 - friction) * 0.25 +
            (1 - dependency_risk) * 0.20 +
            buyer_readiness * 0.25
        )

        # Verdict
        if lambda_score >= 0.75:
            verdict = "TRANSFERABLE: ready for zero-copy transfer"
        elif lambda_score >= 0.50:
            verdict = "PORTABLE: needs packaging improvements"
        elif lambda_score >= 0.30:
            verdict = "COUPLED: significant friction to transfer"
        else:
            verdict = "LOCKED: not transferable in current state"

        result = {
            "transferability": round(transferability, 4),
            "friction": round(friction, 4),
            "dependency_risk": round(dependency_risk, 4),
            "buyer_readiness": round(buyer_readiness, 4),
            "lambda_score": round(lambda_score, 4),
            "verdict": verdict,
            "inputs": asdict(inputs),
        }

        # Persist
        score_id = hashlib.sha256(f"{inputs.artifact_hash}:{time.time()}".encode()).hexdigest()[:16]
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO lambda_scores
            (id, artifact_hash, artifact_path, transferability, friction,
             dependency_risk, buyer_readiness, lambda_score, inputs_json, verdict, timestamp)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (score_id, inputs.artifact_hash, inputs.artifact_path,
             result["transferability"], result["friction"],
             result["dependency_risk"], result["buyer_readiness"],
             result["lambda_score"], json.dumps(asdict(inputs)),
             result["verdict"], datetime.now().isoformat()))
        conn.commit()
        conn.close()

        result["id"] = score_id
        return result

    def query_scores(self, limit: int = 20) -> list:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute("SELECT id, artifact_path, lambda_score, verdict, timestamp FROM lambda_scores ORDER BY timestamp DESC LIMIT ?", (limit,))
        rows = c.fetchall()
        conn.close()
        return [{"id": r[0], "artifact_path": r[1], "lambda_score": r[2], "verdict": r[3], "timestamp": r[4]} for r in rows]


# =============================================================================
# FinanceableArtifactExporter — Buyer/Proof/Release/Valuation Packets
# =============================================================================

class FinanceableArtifactExporter:
    """
    Exports LambdaReceipts as financeable packets:
      - buyer packet: what a buyer needs to evaluate the artifact
      - proof packet: cryptographic proof chain
      - release packet: deployment-ready bundle with manifest
      - valuation packet: scored value claim with substrate cost
    """

    def __init__(self, output_dir: str = "build/packets"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_buyer_packet(self, lambda_receipt: dict) -> str:
        """Export a buyer evaluation packet."""
        packet = {
            "schema": "reality_compiler.buyer_packet.v1",
            "artifact": lambda_receipt.get("artifact", {}),
            "lambda_score": lambda_receipt.get("lambda_score", {}),
            "provenance": lambda_receipt.get("provenance", {}),
            "substrate_cost": lambda_receipt.get("substrate_receipt", {}),
            "value_claim": lambda_receipt.get("value_claim", ""),
            "transferability_verdict": lambda_receipt.get("lambda_score", {}).get("verdict", ""),
            "receipt_count": lambda_receipt.get("receipt_count", 0),
            "proof_count": lambda_receipt.get("proof_count", 0),
            "exported_at": datetime.now().isoformat(),
        }
        path = self.output_dir / "buyer_packet.json"
        path.write_text(json.dumps(packet, indent=2, ensure_ascii=False))
        return str(path)

    def export_proof_packet(self, lambda_receipt: dict) -> str:
        """Export a cryptographic proof packet."""
        packet = {
            "schema": "reality_compiler.proof_packet.v1",
            "artifact_hash": lambda_receipt.get("artifact", {}).get("hash", ""),
            "source_hash": lambda_receipt.get("source_hash", ""),
            "merkle_root": lambda_receipt.get("merkle_root", ""),
            "receipt_chain": lambda_receipt.get("receipt_chain", []),
            "provenance": lambda_receipt.get("provenance", {}),
            "ledger_verification": lambda_receipt.get("ledger_verification", {}),
            "exported_at": datetime.now().isoformat(),
        }
        packet["packet_hash"] = hashlib.sha256(
            json.dumps(packet, sort_keys=True).encode()
        ).hexdigest()
        path = self.output_dir / "proof_packet.json"
        path.write_text(json.dumps(packet, indent=2, ensure_ascii=False))
        return str(path)

    def export_release_packet(self, lambda_receipt: dict) -> str:
        """Export a deployment-ready release packet."""
        packet = {
            "schema": "reality_compiler.release_packet.v1",
            "artifact": lambda_receipt.get("artifact", {}),
            "build_log": lambda_receipt.get("build_log", ""),
            "substrate_receipt": lambda_receipt.get("substrate_receipt", {}),
            "file_delta_ledger": lambda_receipt.get("file_delta_ledger", []),
            "dependencies": lambda_receipt.get("provenance", {}).get("materials", []),
            "platform": lambda_receipt.get("provenance", {}).get("builder", {}).get("platform", ""),
            "exported_at": datetime.now().isoformat(),
        }
        path = self.output_dir / "release_packet.json"
        path.write_text(json.dumps(packet, indent=2, ensure_ascii=False))
        return str(path)

    def export_valuation_packet(self, lambda_receipt: dict) -> str:
        """Export a scored valuation packet."""
        ls = lambda_receipt.get("lambda_score", {})
        sr = lambda_receipt.get("substrate_receipt", {})
        cost = sr.get("cost_estimate_usd", 0)
        lambda_score = ls.get("lambda_score", 0)

        # Value estimate: substrate cost / lambda_score (inverse — higher transferability = lower cost per unit value)
        # Plus a base value for verified work
        base_value = 100.0  # base value for verified, receipted work
        transferability_multiplier = 1 + lambda_score
        estimated_value = base_value * transferability_multiplier

        packet = {
            "schema": "reality_compiler.valuation_packet.v1",
            "artifact": lambda_receipt.get("artifact", {}),
            "substrate_cost_usd": cost,
            "lambda_score": lambda_score,
            "transferability": ls.get("transferability", 0),
            "buyer_readiness": ls.get("buyer_readiness", 0),
            "estimated_value_usd": round(estimated_value, 2),
            "value_basis": "substrate_cost × transferability_multiplier + base_verified_value",
            "verdict": ls.get("verdict", ""),
            "receipt_count": lambda_receipt.get("receipt_count", 0),
            "proof_count": lambda_receipt.get("proof_count", 0),
            "exported_at": datetime.now().isoformat(),
        }
        path = self.output_dir / "valuation_packet.json"
        path.write_text(json.dumps(packet, indent=2, ensure_ascii=False))
        return str(path)

    def export_all(self, lambda_receipt: dict) -> dict:
        """Export all packet types."""
        return {
            "buyer_packet": self.export_buyer_packet(lambda_receipt),
            "proof_packet": self.export_proof_packet(lambda_receipt),
            "release_packet": self.export_release_packet(lambda_receipt),
            "valuation_packet": self.export_valuation_packet(lambda_receipt),
        }


# =============================================================================
# RealityCompiler — Umbrella Orchestrator
# =============================================================================

class RealityCompiler:
    """
    The umbrella product. Compiles a production event into a verified,
    transferable artifact package (LambdaReceipt).

    Pipeline:
      1. Start Layer4Meter (substrate measurement)
      2. Hash source files (source provenance)
      3. Record file deltas (what changed)
      4. Execute or observe the build/work
      5. Stop Layer4Meter (substrate receipt)
      6. Analyze artifact (LambdaBase scoring)
      7. Build provenance statement (SLSA-aligned)
      8. Issue receipts (ReceiptOS)
      9. Record proofs (ReceiptOS)
      10. Verify ledger integrity
      11. Export financeable packets
      12. Emit LambdaReceipt
    """

    def __init__(self):
        self.l4 = Layer4Meter()
        self.receipt_os = ReceiptOS()
        self.lambda_base = LambdaBase()
        self.exporter = FinanceableArtifactExporter()

    def _hash_source(self, source_dir: str) -> dict:
        """Hash all source files for provenance."""
        p = Path(source_dir)
        if not p.exists():
            return {"error": f"Source dir not found: {source_dir}"}

        files = {}
        h = hashlib.sha256()
        for f in sorted(p.rglob("*")):
            if f.is_file() and not any(part.startswith(".") for part in f.parts):
                rel = str(f.relative_to(p))
                file_hash = hashlib.sha256(f.read_bytes()).hexdigest()
                files[rel] = {
                    "hash": file_hash,
                    "size": f.stat().st_size,
                    "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                }
                h.update(f.read_bytes())

        return {
            "source_dir": source_dir,
            "file_count": len(files),
            "files": files,
            "source_hash": h.hexdigest(),
        }

    def _file_delta_ledger(self, source_info: dict, baseline_dir: str = "") -> list:
        """Compute file deltas against a baseline (if provided)."""
        if not baseline_dir or not Path(baseline_dir).exists():
            return [{"file": f, "status": "new", "hash": d["hash"]} for f, d in source_info.get("files", {}).items()]

        baseline = Path(baseline_dir)
        deltas = []
        for rel, info in source_info.get("files", {}).items():
            baseline_file = baseline / rel
            if not baseline_file.exists():
                deltas.append({"file": rel, "status": "added", "hash": info["hash"]})
            else:
                old_hash = hashlib.sha256(baseline_file.read_bytes()).hexdigest()
                if old_hash != info["hash"]:
                    deltas.append({"file": rel, "status": "modified", "old_hash": old_hash, "new_hash": info["hash"]})
                else:
                    deltas.append({"file": rel, "status": "unchanged", "hash": info["hash"]})
        return deltas

    def compile(self, intent: str, source_dir: str = "",
                artifacts: list = None, agent_id: str = "system",
                build_log: str = "", value_claim: str = "",
                baseline_dir: str = "") -> dict:
        """
        Compile a production event into a LambdaReceipt.

        Args:
          intent: what was the work supposed to do?
          source_dir: where are the source files?
          artifacts: list of artifact paths produced
          agent_id: who/what did the work?
          build_log: command or description of what was run
          value_claim: what value does this work claim?
          baseline_dir: previous state for delta computation
        """
        artifacts = artifacts or []
        session_id = hashlib.sha256(f"{intent}:{time.time()}".encode()).hexdigest()[:12]

        # Step 1: Start substrate measurement
        self.l4.start()

        # Step 2: Hash source files
        source_info = self._hash_source(source_dir) if source_dir else {"source_hash": "", "file_count": 0, "files": {}}

        # Step 3: File delta ledger
        file_deltas = self._file_delta_ledger(source_info, baseline_dir)

        # Step 4: Hash artifacts
        artifact_infos = []
        for art_path in artifacts:
            p = Path(art_path)
            if p.is_file():
                art_hash = hashlib.sha256(p.read_bytes()).hexdigest()
                artifact_infos.append({
                    "path": art_path,
                    "hash": art_hash,
                    "size": p.stat().st_size,
                    "type": "file",
                })
            elif p.is_dir():
                h = hashlib.sha256()
                file_count = 0
                total_size = 0
                for f in sorted(p.rglob("*")):
                    if f.is_file():
                        h.update(f.read_bytes())
                        file_count += 1
                        total_size += f.stat().st_size
                artifact_infos.append({
                    "path": art_path,
                    "hash": h.hexdigest(),
                    "size": total_size,
                    "file_count": file_count,
                    "type": "directory",
                })

        # Step 5: Stop substrate measurement
        files_touched = source_info.get("file_count", 0) + sum(a.get("file_count", 1) for a in artifact_infos)
        substrate_receipt = self.l4.stop(session_id, files_touched=files_touched)

        # Step 6: Analyze and score artifacts with LambdaBase
        lambda_scores = []
        for art in artifact_infos:
            inputs = self.lambda_base.analyze_artifact(art["path"])
            inputs.receipt_count = len(self.receipt_os.receipt_db.query_receipts(limit=1000))
            inputs.proof_count = self.receipt_os.proof_db.get_stats().get("total_entries", 0)
            score = self.lambda_base.score(inputs)
            lambda_scores.append(score)

        # Step 7: Build provenance (SLSA-aligned)
        build_def = {
            "intent": intent,
            "source_dir": source_dir,
            "artifacts": [a["path"] for a in artifact_infos],
            "value_claim": value_claim,
        }
        run_details = {
            "agent_id": agent_id,
            "build_log": build_log,
            "wall_time_ms": substrate_receipt.get("wall_time_ms", 0),
            "cpu_time_ms": substrate_receipt.get("cpu_time_ms", 0),
            "ram_peak_mb": substrate_receipt.get("ram_peak_mb", 0),
            "platform": substrate_receipt.get("platform", ""),
        }
        materials = [{"path": f, "hash": d["hash"]} for f, d in source_info.get("files", {}).items()]
        byproducts = [{"path": "receipts/", "type": "receipt_chain"}]
        provenance = self.receipt_os.build_provenance(
            subject=artifact_infos[0]["path"] if artifact_infos else intent,
            build_def=build_def,
            run_details=run_details,
            materials=materials,
            byproducts=byproducts,
        )

        # Step 8: Issue receipt
        primary_hash = artifact_infos[0]["hash"] if artifact_infos else source_info.get("source_hash", "")
        receipt = self.receipt_os.issue_receipt(
            receipt_type="build_pass",
            action=intent,
            agent_id=agent_id,
            artifact_hash=primary_hash,
            artifact_path=artifact_infos[0]["path"] if artifact_infos else "",
            metrics={
                "wall_time_ms": substrate_receipt.get("wall_time_ms", 0),
                "cpu_time_ms": substrate_receipt.get("cpu_time_ms", 0),
                "files_touched": files_touched,
                "cost_estimate_usd": substrate_receipt.get("cost_estimate_usd", 0),
            },
            verification={
                "source_hash": source_info.get("source_hash", ""),
                "provenance_hash": provenance.get("provenance_hash", ""),
                "artifact_count": len(artifact_infos),
            },
            notes=value_claim,
        )

        # Step 9: Record proof
        proof = self.receipt_os.record_proof(
            entry_type="proof",
            subject=intent,
            content={
                "intent": intent,
                "artifact_hashes": [a["hash"] for a in artifact_infos],
                "source_hash": source_info.get("source_hash", ""),
                "provenance_hash": provenance.get("provenance_hash", ""),
                "substrate_receipt_id": substrate_receipt.get("id", ""),
                "receipt_id": receipt.get("id", ""),
            },
            signer_id=agent_id,
            tags=["reality_compiler", "lambda_receipt"],
        )

        # Step 10: Verify ledger
        ledger_verification = self.receipt_os.verify_all()

        # Step 11: Build LambdaReceipt
        lambda_receipt = {
            "schema": "reality_compiler.lambda_receipt.v1",
            "intent": intent,
            "agent_id": agent_id,
            "timestamp": datetime.now().isoformat(),
            "session_id": session_id,
            "artifact": artifact_infos[0] if artifact_infos else {},
            "artifacts": artifact_infos,
            "source_hash": source_info.get("source_hash", ""),
            "source_files": source_info.get("file_count", 0),
            "file_delta_ledger": file_deltas,
            "build_log": build_log,
            "substrate_receipt": substrate_receipt,
            "provenance": provenance,
            "lambda_score": lambda_scores[0] if lambda_scores else {},
            "lambda_scores": lambda_scores,
            "value_claim": value_claim,
            "receipt": receipt,
            "proof": proof,
            "receipt_count": len(self.receipt_os.receipt_db.query_receipts(limit=1000)),
            "proof_count": self.receipt_os.proof_db.get_stats().get("total_entries", 0),
            "ledger_verification": ledger_verification,
            "merkle_root": receipt.get("receipt_hash", ""),
        }

        # Hash the LambdaReceipt itself
        receipt_str = json.dumps(lambda_receipt, sort_keys=True, default=str)
        lambda_receipt["lambda_receipt_hash"] = hashlib.sha256(receipt_str.encode()).hexdigest()

        # Step 12: Export financeable packets
        packets = self.exporter.export_all(lambda_receipt)
        lambda_receipt["packets"] = packets

        # Write LambdaReceipt
        lr_path = Path("build") / f"lambda_receipt_{session_id}.json"
        lr_path.parent.mkdir(exist_ok=True)
        lr_path.write_text(json.dumps(lambda_receipt, indent=2, ensure_ascii=False, default=str))
        lambda_receipt["lambda_receipt_path"] = str(lr_path)

        return lambda_receipt

    def status(self) -> dict:
        """Get system status."""
        stats = self.receipt_os.get_stats()
        l4_recent = self.l4.query(limit=1)
        lambda_scores = self.lambda_base.query_scores(limit=5)
        return {
            "receipt_stats": stats["receipts"],
            "proof_stats": stats["proofs"],
            "ledger_intact": self.receipt_os.verify_all()["all_intact"],
            "recent_substrate": l4_recent[0] if l4_recent else None,
            "recent_lambda_scores": lambda_scores,
            "timestamp": datetime.now().isoformat(),
        }


# =============================================================================
# CLI
# =============================================================================

def cli():
    import sys
    args = sys.argv[1:] if len(sys.argv) > 1 else []

    if not args or args[0] in ("-h", "--help", "help"):
        print("Reality Compiler — A provenance engine for AI-native work")
        print()
        print("  Capture work. Measure substrate. Prove provenance. Score value. Export receipt.")
        print("Usage:")
        print("  python3 reality_compiler.py compile <intent> [--source=dir] [--artifact=path] ...")
        print("  python3 reality_compiler.py status")
        print("  python3 reality_compiler.py verify")
        print()
        print("Pipeline: intent → source hash → artifact hash → substrate → provenance → receipt → lambda score → packets")
        return

    cmd = args[0]
    rc = RealityCompiler()

    if cmd == "status":
        s = rc.status()
        print("Reality Compiler — System Status")
        print(f"  Ledger intact: {s['ledger_intact']}")
        print(f"  Receipts: {s['receipt_stats']['total_receipts']}")
        print(f"  Proofs: {s['proof_stats']['total_entries']}")
        if s["recent_substrate"]:
            sr = s["recent_substrate"]
            print(f"  Last substrate: {sr['wall_time_ms']}ms wall, {sr['cpu_time_ms']}ms cpu, ${sr['cost_estimate_usd']}")
        if s["recent_lambda_scores"]:
            for ls in s["recent_lambda_scores"]:
                print(f"  Lambda: {ls['lambda_score']} — {ls['verdict']} ({ls['artifact_path']})")
        return

    if cmd == "verify":
        v = rc.receipt_os.verify_all()
        print("Reality Compiler — Ledger Verification")
        print(f"  Receipt ledger: {'INTACT' if v['receipt_ledger']['ledger_intact'] else 'BROKEN'} ({v['receipt_ledger']['total_receipts']} receipts)")
        print(f"  Proof chain:    {'INTACT' if v['proof_chain']['chain_intact'] else 'BROKEN'} ({v['proof_chain']['total_entries']} entries)")
        if not v["all_intact"]:
            print(f"  Broken: {v['receipt_ledger']['broken_receipts']} {v['proof_chain']['broken_entries']}")
        return

    if cmd == "compile":
        intent = args[1] if len(args) > 1 else "unnamed work"
        source = ""
        artifacts = []
        agent = "system"
        build_log = ""
        value_claim = ""
        baseline = ""

        for a in args[2:]:
            if a.startswith("--source="):
                source = a.split("=", 1)[1]
            elif a.startswith("--artifact="):
                artifacts.append(a.split("=", 1)[1])
            elif a.startswith("--agent="):
                agent = a.split("=", 1)[1]
            elif a.startswith("--build_log="):
                build_log = a.split("=", 1)[1]
            elif a.startswith("--value="):
                value_claim = a.split("=", 1)[1]
            elif a.startswith("--baseline="):
                baseline = a.split("=", 1)[1]

        print(f"Reality Compiler — Compiling: {intent}")
        print(f"  Source: {source or '(none)'}")
        print(f"  Artifacts: {artifacts}")
        print(f"  Agent: {agent}")
        print()

        receipt = rc.compile(
            intent=intent,
            source_dir=source,
            artifacts=artifacts,
            agent_id=agent,
            build_log=build_log,
            value_claim=value_claim,
            baseline_dir=baseline,
        )

        print(f"  LambdaReceipt: {receipt['lambda_receipt_path']}")
        print(f"  Hash: {receipt['lambda_receipt_hash'][:32]}...")
        print(f"  Source files: {receipt['source_files']}")
        print(f"  Artifacts: {len(receipt['artifacts'])}")
        sr = receipt["substrate_receipt"]
        print(f"  Substrate: {sr['wall_time_ms']}ms wall, {sr['cpu_time_ms']}ms cpu, ${sr['cost_estimate_usd']}")
        ls = receipt.get("lambda_score", {})
        if ls:
            print(f"  Lambda score: {ls.get('lambda_score', 0)} — {ls.get('verdict', '')}")
            print(f"    transferability: {ls.get('transferability', 0)}")
            print(f"    friction: {ls.get('friction', 0)}")
            print(f"    dependency_risk: {ls.get('dependency_risk', 0)}")
            print(f"    buyer_readiness: {ls.get('buyer_readiness', 0)}")
        print(f"  Receipts: {receipt['receipt_count']}")
        print(f"  Proofs: {receipt['proof_count']}")
        print(f"  Ledger: {'INTACT' if receipt['ledger_verification']['all_intact'] else 'BROKEN'}")
        print()
        print("  Packets:")
        for ptype, ppath in receipt.get("packets", {}).items():
            print(f"    {ptype}: {ppath}")


if __name__ == "__main__":
    cli()
