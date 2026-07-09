#!/usr/bin/env python3
"""
ONEFILE ML TOKEN LAUNCHER
=========================
A single-file, runnable, safe MVP that combines ML scoring, token-launch
readiness, proof receipts, API endpoints, and a local web UI.

Doctrine:
  Do not launch hype. Launch proof.
  A token is not value by itself.
  A token becomes defensible only when attached to evidence, receipts,
  utility, risk controls, and transparent launch constraints.

Safety:
  - Never prints environment secrets.
  - Never requests private keys.
  - Never generates instructions for market manipulation.
  - Never claims token value will rise.
  - Never says "guaranteed profitable."
  - Never recommends real investment.
  - Defaults to SIMULATION mode.
  - Blocks mainnet unless ALLOW_MAINNET=YES_I_UNDERSTAND_RISK is set,
    and even then only generates instructions, never signs transactions.

Usage:
  python onefile_ml_token_launcher.py --demo
  python onefile_ml_token_launcher.py --serve [--port 7860]
  python onefile_ml_token_launcher.py --score token.json

Requires Python 3.11+. Optional deps: fastapi, uvicorn, pydantic, numpy, scikit-learn.
If optional deps are missing, pure-Python fallbacks are used.

License: MIT
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import sys
import time
import traceback
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Optional imports with fallbacks
# ---------------------------------------------------------------------------

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
    HAS_FASTAPI = True
except ImportError:
    HAS_FASTAPI = False

try:
    from pydantic import BaseModel
    HAS_PYDANTIC = True
except ImportError:
    HAS_PYDANTIC = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    from sklearn.linear_model import LogisticRegression
    from sklearn.metrics import accuracy_score, balanced_accuracy_score
    HAS_SKLEARN = True
except ImportError:
    HAS_SKLEARN = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERSION = "1.0.0"
DEFAULT_PORT = 7860
DISCLAIMER = (
    "This is not legal, financial, or investment advice. "
    "This tool produces proof and launch-readiness artifacts, not investment guarantees."
)
MAINNET_ENV_VALUE = "YES_I_UNDERSTAND_RISK"

FORBIDDEN_HYPE_TERMS = [
    "pump", "guaranteed profit", "moon", "presale urgency",
    "hidden team", "no utility", "no proof", "fake apy",
    "risk-free", "insider allocation", "passive income",
    "price will rise", "buy before", "investment opportunity",
]

WEAK_UTILITY_TERMS = ["community", "moon", "meme", "profit", "pump", "hype"]

STRONG_UTILITY_TERMS = [
    "access", "receipts", "governance", "api credits",
    "staking for service quality", "academic", "proof settlement",
    "data licensing", "settlement", "verification", "audit",
]

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class ChainTarget(str, Enum):
    SIMULATION = "simulation"
    EVM_TESTNET = "evm_testnet"
    SOLANA_DEVNET = "solana_devnet"

class ProofGrade(str, Enum):
    NONE = "NONE"
    CLAIM_ONLY = "CLAIM_ONLY"
    METADATA_PRESENT = "METADATA_PRESENT"
    CODE_OR_REPO_PRESENT = "CODE_OR_REPO_PRESENT"
    METRICS_PRESENT = "METRICS_PRESENT"
    TESTNET_READY = "TESTNET_READY"
    EXTERNALLY_VERIFIED = "EXTERNALLY_VERIFIED"

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

if HAS_PYDANTIC:
    class MLModelMetrics(BaseModel):
        accuracy: Optional[float] = None
        balanced_accuracy: Optional[float] = None
        precision: Optional[float] = None
        recall: Optional[float] = None
        f1: Optional[float] = None
        auc: Optional[float] = None
        sample_size: Optional[int] = None
        validation_type: Optional[str] = None
        leakage_checked: bool = False
        out_of_sample: bool = False

    class TokenLaunchRequest(BaseModel):
        name: str = ""
        symbol: str = ""
        description: str = ""
        utility: str = ""
        chain_target: str = "simulation"
        supply: float = 1_000_000.0
        decimals: int = 18
        creator_wallet: Optional[str] = None
        project_url: Optional[str] = None
        github_url: Optional[str] = None
        evidence_text: Optional[str] = None
        model_metrics: Optional[MLModelMetrics] = None
        allow_public_launch_claim: bool = False
else:
    @dataclass
    class MLModelMetrics:
        accuracy: Optional[float] = None
        balanced_accuracy: Optional[float] = None
        precision: Optional[float] = None
        recall: Optional[float] = None
        f1: Optional[float] = None
        auc: Optional[float] = None
        sample_size: Optional[int] = None
        validation_type: Optional[str] = None
        leakage_checked: bool = False
        out_of_sample: bool = False

    @dataclass
    class TokenLaunchRequest:
        name: str = ""
        symbol: str = ""
        description: str = ""
        utility: str = ""
        chain_target: str = "simulation"
        supply: float = 1_000_000.0
        decimals: int = 18
        creator_wallet: Optional[str] = None
        project_url: Optional[str] = None
        github_url: Optional[str] = None
        evidence_text: Optional[str] = None
        model_metrics: Optional[MLModelMetrics] = None
        allow_public_launch_claim: bool = False

def req_to_dict(req: TokenLaunchRequest) -> dict:
    """Serialize a request to a plain dict regardless of pydantic/dataclass."""
    if HAS_PYDANTIC:
        return req.model_dump()
    d = asdict(req)
    if d.get("model_metrics") and isinstance(d["model_metrics"], dict):
        pass
    return d

def dict_to_req(d: dict) -> TokenLaunchRequest:
    """Build a TokenLaunchRequest from a plain dict."""
    mm = d.pop("model_metrics", None)
    if mm and isinstance(mm, dict):
        mm = MLModelMetrics(**mm)
    return TokenLaunchRequest(**d, model_metrics=mm) if mm else TokenLaunchRequest(**d)

# ---------------------------------------------------------------------------
# Receipt Store (SQLite preferred, JSONL fallback)
# ---------------------------------------------------------------------------

class ReceiptStore:
    """SHA-256 chained receipt persistence with SQLite or JSONL fallback."""

    def __init__(self, db_path: str = "receipts.db"):
        self.db_path = db_path
        self.jsonl_path = "receipts.jsonl"
        self._use_sqlite = False
        try:
            self._conn = sqlite3.connect(db_path)
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS receipts (
                    receipt_id TEXT PRIMARY KEY,
                    timestamp REAL,
                    input_hash TEXT,
                    output_hash TEXT,
                    risk_summary TEXT,
                    proof_grade TEXT,
                    launch_status TEXT,
                    chain_target TEXT,
                    blocked_actions TEXT,
                    prev_hash TEXT,
                    receipt_hash TEXT,
                    data TEXT
                )
            """)
            self._conn.commit()
            self._use_sqlite = True
        except Exception:
            self._conn = None

    def _last_hash(self) -> str:
        if self._use_sqlite:
            row = self._conn.execute(
                "SELECT receipt_hash FROM receipts ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
            return row[0] if row else "genesis"
        if Path(self.jsonl_path).exists():
            with open(self.jsonl_path, "r") as f:
                lines = [l.strip() for l in f if l.strip()]
            if lines:
                return json.loads(lines[-1])["receipt_hash"]
        return "genesis"

    def write(self, receipt: dict) -> str:
        prev = self._last_hash()
        receipt["prev_hash"] = prev
        canonical = json.dumps(receipt, sort_keys=True, default=str)
        receipt_hash = "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()
        receipt["receipt_hash"] = receipt_hash
        if self._use_sqlite:
            self._conn.execute(
                "INSERT OR REPLACE INTO receipts VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    receipt["receipt_id"], receipt["timestamp"],
                    receipt["input_hash"], receipt["output_hash"],
                    receipt.get("risk_summary", ""), receipt.get("proof_grade", ""),
                    receipt.get("launch_status", ""), receipt.get("chain_target", ""),
                    json.dumps(receipt.get("blocked_actions", [])),
                    receipt["prev_hash"], receipt["receipt_hash"],
                    json.dumps(receipt, default=str),
                ),
            )
            self._conn.commit()
        else:
            with open(self.jsonl_path, "a") as f:
                f.write(json.dumps(receipt, default=str) + "\n")
        return receipt_hash

    def all_receipts(self) -> list[dict]:
        if self._use_sqlite:
            rows = self._conn.execute(
                "SELECT data FROM receipts ORDER BY timestamp ASC"
            ).fetchall()
            return [json.loads(r[0]) for r in rows]
        if not Path(self.jsonl_path).exists():
            return []
        with open(self.jsonl_path, "r") as f:
            return [json.loads(l) for l in f if l.strip()]

    def verify_chain(self) -> bool:
        receipts = self.all_receipts()
        prev = "genesis"
        for r in receipts:
            if r.get("prev_hash") != prev:
                return False
            prev = r["receipt_hash"]
        return True

# ---------------------------------------------------------------------------
# Scoring Engine
# ---------------------------------------------------------------------------

class ScoringEngine:
    """Computes proof density, ML, utility, fraud risk, compliance risk, readiness."""

    def __init__(self, store: Optional[ReceiptStore] = None):
        self.store = store or ReceiptStore()

    @staticmethod
    def _hash(data: dict) -> str:
        canonical = json.dumps(data, sort_keys=True, default=str)
        return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()

    def score(self, req: TokenLaunchRequest) -> dict:
        """Full scoring pipeline returning all scores, grades, routes, and receipt."""
        input_data = req_to_dict(req)
        input_hash = self._hash(input_data)

        proof_density = self._proof_density(req)
        ml = self._ml_score(req)
        utility = self._utility_score(req)
        fraud = self._fraud_risk(req)
        compliance = self._compliance_risk(req)
        readiness = self._readiness(proof_density, ml, utility, fraud, compliance)
        grade = self._proof_grade(req, proof_density, ml)
        mainnet_blocked = self._mainnet_blocked()
        safe_testnet = fraud < 0.4 and compliance < 0.4
        routes = self._routes(readiness, fraud, compliance)
        blocked = self._blocked(fraud, compliance, mainnet_blocked)

        output: dict = {
            "token_name": req.name,
            "symbol": req.symbol,
            "chain_target": req.chain_target,
            "scores": {
                "proof_density_score": round(proof_density, 3),
                "ml_score": round(ml, 3),
                "utility_score": round(utility, 3),
                "launch_readiness_score": round(readiness, 3),
                "fraud_risk_score": round(fraud, 3),
                "compliance_risk_score": round(compliance, 3),
            },
            "proof_grade": grade.value,
            "mainnet_blocked": mainnet_blocked,
            "safe_to_generate_testnet_plan": safe_testnet,
            "recommended_routes": routes,
            "blocked_actions": blocked,
            "disclaimer": DISCLAIMER,
        }
        output_hash = self._hash(output)
        receipt_id = "rcpt_" + hashlib.sha256(
            f"{input_hash}{output_hash}{time.time()}".encode()
        ).hexdigest()[:16]
        receipt = {
            "receipt_id": receipt_id,
            "timestamp": time.time(),
            "input_hash": input_hash,
            "output_hash": output_hash,
            "risk_summary": f"fraud={fraud:.2f} compliance={compliance:.2f} readiness={readiness:.2f}",
            "proof_grade": grade.value,
            "launch_status": "blocked" if mainnet_blocked else ("ready_testnet" if safe_testnet else "needs_review"),
            "chain_target": req.chain_target,
            "blocked_actions": blocked,
            "output": output,
        }
        self.store.write(receipt)
        output["receipt_id"] = receipt_id
        output["receipt_hash"] = receipt["receipt_hash"]
        return output

    def _proof_density(self, req: TokenLaunchRequest) -> float:
        s = 0.0
        ev = req.evidence_text or ""
        if len(ev) > 50: s += 0.15
        if len(ev) > 200: s += 0.10
        if len(ev) > 500: s += 0.10
        if req.github_url: s += 0.20
        if req.project_url: s += 0.10
        if req.model_metrics: s += 0.15
        if req.model_metrics and req.model_metrics.validation_type: s += 0.10
        if req.creator_wallet: s += 0.05
        if req.utility and len(req.utility) > 20: s += 0.05
        return min(s, 1.0)

    def _ml_score(self, req: TokenLaunchRequest) -> float:
        m = req.model_metrics
        if m is None: return 0.0
        s = 0.0
        ba = m.balanced_accuracy if m.balanced_accuracy is not None else m.accuracy
        if ba is not None: s += min(ba, 1.0) * 0.30
        if m.accuracy is not None and m.balanced_accuracy is None:
            s += min(m.accuracy, 1.0) * 0.15
        if m.out_of_sample: s += 0.15
        if m.leakage_checked: s += 0.15
        if m.f1 is not None: s += min(m.f1, 1.0) * 0.10
        if m.auc is not None: s += min(m.auc, 1.0) * 0.05
        if m.sample_size is not None:
            if m.sample_size < 50: s -= 0.15
            elif m.sample_size < 200: s -= 0.05
            else: s += 0.05
        if m.validation_type is None: s -= 0.10
        return max(s, 0.0)

    def _utility_score(self, req: TokenLaunchRequest) -> float:
        text = (req.utility + " " + req.description).lower()
        s = 0.0
        for t in STRONG_UTILITY_TERMS:
            if t in text: s += 0.20
        for t in WEAK_UTILITY_TERMS:
            if t in text: s -= 0.15
        if not req.utility or len(req.utility) < 10: s -= 0.20
        return max(min(s, 1.0), 0.0)

    def _fraud_risk(self, req: TokenLaunchRequest) -> float:
        text = (req.description + " " + req.utility + " " + (req.evidence_text or "")).lower()
        r = 0.0
        for t in FORBIDDEN_HYPE_TERMS:
            if t in text: r += 0.15
        if not req.evidence_text: r += 0.10
        if not req.github_url: r += 0.05
        if req.allow_public_launch_claim and not req.evidence_text: r += 0.20
        if req.supply > 1_000_000_000: r += 0.10
        if not req.creator_wallet: r += 0.05
        return min(r, 1.0)

    def _compliance_risk(self, req: TokenLaunchRequest) -> float:
        text = (req.description + " " + req.utility).lower()
        r = 0.0
        for t in ["investment", "security", "dividend", "profit share",
                   "passive income", "yield", "apy", "return on investment",
                   "financial", "education records", "medical", "minors"]:
            if t in text: r += 0.15
        if req.chain_target == "simulation": r -= 0.10
        if req.allow_public_launch_claim: r += 0.15
        return max(min(r, 1.0), 0.0)

    def _readiness(self, p: float, m: float, u: float, f: float, c: float) -> float:
        return max((p * 0.25 + m * 0.20 + u * 0.30) - (f * 0.15 + c * 0.10), 0.0)

    def _proof_grade(self, req: TokenLaunchRequest, proof: float, ml: float) -> ProofGrade:
        if proof >= 0.7 and ml >= 0.5 and req.github_url:
            return ProofGrade.EXTERNALLY_VERIFIED
        if proof >= 0.5 and ml >= 0.3:
            return ProofGrade.TESTNET_READY
        if req.model_metrics and ml > 0:
            return ProofGrade.METRICS_PRESENT
        if req.github_url:
            return ProofGrade.CODE_OR_REPO_PRESENT
        if req.project_url or req.creator_wallet:
            return ProofGrade.METADATA_PRESENT
        if req.evidence_text:
            return ProofGrade.CLAIM_ONLY
        return ProofGrade.NONE

    def _mainnet_blocked(self) -> bool:
        return os.environ.get("ALLOW_MAINNET", "") != MAINNET_ENV_VALUE

    def _routes(self, readiness: float, fraud: float, compliance: float) -> list[str]:
        if readiness >= 0.5 and fraud < 0.3 and compliance < 0.3:
            return ["simulation_packet", "evm_testnet_contract_spec",
                    "solana_devnet_mint_plan", "proof_token_access_credit",
                    "receipt_backed_utility_token"]
        return ["private_proof_ledger_first", "non_transferable_receipt_token",
                "wait_for_legal_review"]

    def _blocked(self, fraud: float, compliance: float, mb: bool) -> list[str]:
        b = []
        if mb: b.append("mainnet_deployment")
        if fraud > 0.3: b.append("public_launch_claim")
        if compliance > 0.3: b.extend(["transferable_token", "public_sale"])
        if fraud > 0.5: b.append("any_launch")
        return b

# ---------------------------------------------------------------------------
# Token Spec Generators
# ---------------------------------------------------------------------------

def generate_evm_spec(req: TokenLaunchRequest, scores: dict) -> str:
    """Generate ERC-20 style Solidity contract text (spec only, not deployed)."""
    return f"""// SPDX-License-Identifier: MIT
// ============================================================================
// ONEFILE ML TOKEN LAUNCHER — EVM TESTNET CONTRACT SPEC
// ============================================================================
// WARNING: This is a SPEC ONLY. Do not deploy to mainnet.
// This contract has not been audited. Use only on testnet.
// {DISCLAIMER}
// ============================================================================

pragma solidity ^0.8.20;

// NOTE: In production, use OpenZeppelin ERC-20 implementation:
// import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
// import "@openzeppelin/contracts/access/Ownable.sol";

contract {req.symbol}Token {{
    string public name = "{req.name}";
    string public symbol = "{req.symbol}";
    uint8 public decimals = {req.decimals};
    uint256 public totalSupply = {int(req.supply)};

    address public owner;
    // WARNING: Owner/minter has mint control. Use multisig in production.
    // Creator wallet (public address only): {req.creator_wallet or "NOT_SET"}

    mapping(address => uint256) public balanceOf;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Mint(address indexed to, uint256 value);

    // Proof grade: {scores.get("proof_grade", "NONE")}
    // Receipt hash: {scores.get("receipt_hash", "N/A")}
    // Launch readiness: {scores.get("scores", {}).get("launch_readiness_score", 0)}

    constructor() {{
        owner = msg.sender;
        balanceOf[owner] = totalSupply;
        emit Transfer(address(0), owner, totalSupply);
    }}

    // === TESTNET ONLY NOTICE ===
    // Mainnet deployment requires:
    //   1. Professional security audit
    //   2. Legal/compliance review
    //   3. Multisig ownership
    //   4. Timelock on critical functions
    //   5. Proof of utility and revenue
}}
"""


def generate_solana_plan(req: TokenLaunchRequest, scores: dict) -> dict:
    """Generate Solana devnet mint plan as structured JSON (spec only)."""
    return {
        "plan_type": "solana_devnet_mint_plan",
        "status": "SPEC_ONLY",
        "warning": "This is a plan only. Do not execute on mainnet.",
        "disclaimer": DISCLAIMER,
        "token": {"name": req.name, "symbol": req.symbol,
                  "decimals": req.decimals, "supply": req.supply},
        "mint_account": {
            "description": "Solana mint account representing the token",
            "mint_authority": req.creator_wallet or "SET_AFTER_KEYPAIR_GENERATION",
            "decimals": req.decimals, "supply": req.supply,
            "is_initialized": True, "freeze_authority": None,
        },
        "token_account": {
            "description": "Associated token account for the creator",
            "owner": req.creator_wallet or "SET_AFTER_KEYPAIR_GENERATION",
            "amount": req.supply,
        },
        "metadata": {"uri": req.project_url or "", "name": req.name, "symbol": req.symbol},
        "devnet_checklist": [
            "1. Generate keypair OUTSIDE this tool (never enter private keys here)",
            "2. Configure Solana CLI to devnet: solana config set --url https://api.devnet.solana.com",
            "3. Airdrop test SOL: solana airdrop 2",
            "4. Create mint account: spl-token create-token",
            "5. Create token account: spl-token create-account <MINT_ADDRESS>",
            "6. Mint tokens: spl-token mint <MINT_ADDRESS> <AMOUNT>",
            "7. Verify on devnet explorer: https://explorer.solana.com?cluster=devnet",
        ],
        "proof_metadata": {
            "proof_grade": scores.get("proof_grade", "NONE"),
            "receipt_hash": scores.get("receipt_hash", "N/A"),
        },
    }


def generate_launch_packet(req: TokenLaunchRequest, scores: dict) -> dict:
    """Generate a complete launch packet with specs, checklist, and receipt."""
    return {
        "packet_type": "launch_packet_v1",
        "timestamp": time.time(),
        "token": req_to_dict(req),
        "scores": scores,
        "evm_spec": generate_evm_spec(req, scores) if req.chain_target in ("simulation", "evm_testnet") else None,
        "solana_plan": generate_solana_plan(req, scores) if req.chain_target in ("simulation", "solana_devnet") else None,
        "testnet_checklist": [
            "1. Review all scores and risk assessments",
            "2. Ensure proof grade is at least METRICS_PRESENT",
            "3. Generate keypair outside this tool (never enter private keys)",
            "4. Deploy to testnet only (Sepolia, Goerli, or Solana devnet)",
            "5. Verify contract/mint on testnet explorer",
            "6. Run test transactions",
            "7. Get external code audit before any mainnet consideration",
            "8. Obtain legal/compliance review for any public launch",
        ],
        "disclaimer": DISCLAIMER,
        "receipt_id": scores.get("receipt_id"),
        "receipt_hash": scores.get("receipt_hash"),
    }


# ---------------------------------------------------------------------------
# Embedded HTML Dashboard
# ---------------------------------------------------------------------------

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ONEFILE ML Token Launcher</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#c9d1d9;font-family:system-ui,sans-serif;padding:20px}
h1{color:#58a6ff;margin-bottom:8px;font-size:1.5rem}
.subtitle{color:#8b949e;margin-bottom:20px;font-size:.9rem}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px;max-width:1200px}
.card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:16px}
.card h2{color:#58a6ff;font-size:1rem;margin-bottom:10px}
.form-group{margin-bottom:10px}
.form-group label{display:block;color:#8b949e;font-size:.8rem;margin-bottom:4px}
.form-group input,.form-group select,.form-group textarea{
  width:100%;background:#0d1117;border:1px solid #30363d;border-radius:6px;
  color:#c9d1d9;padding:8px;font-size:.85rem}
.form-group textarea{min-height:60px;resize:vertical}
.btn-row{display:flex;gap:8px;flex-wrap:wrap;margin-top:12px}
button{background:#238636;border:1px solid #2ea043;color:#fff;border-radius:6px;
  padding:8px 16px;cursor:pointer;font-size:.85rem}
button:hover{background:#2ea043}
button.secondary{background:#21262d;border-color:#30363d}
button.secondary:hover{background:#30363d}
.score-card{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:14px}
.score-value{font-size:1.8rem;font-weight:bold}
.score-good{color:#3fb950}
.score-warn{color:#d29922}
.score-bad{color:#f85149}
.score-label{color:#8b949e;font-size:.8rem;margin-top:4px}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:.75rem;margin:2px}
.badge-green{background:#1a3a2e;color#3fb950}
.badge-red{background#3d1419;color:#f85149}
.badge-yellow{background#3d2e00;color:#d29922}
#results{margin-top:20px}
pre{background#0d1117;border:1px solid #30363d;border-radius:6px;padding:12px;
  overflow-x:auto;font-size:.8rem;color:#c9d1d9;max-height:400px;overflow-y:auto}
.disclaimer{color#f85149;font-size:.75rem;margin-top:16px;padding:8px;
  background:#3d1419;border-radius:6px;border:1px solid #f8514933}
</style>
</head>
<body>
<h1>ONEFILE ML Token Launcher</h1>
<p class="subtitle">Do not launch hype. Launch proof. Simulation/testnet first.</p>
<div class="grid">
  <div class="card" id="form-card">
    <h2>Token Configuration</h2>
    <div class="form-group"><label>Token Name</label><input id="name" value="LatentOS Proof Token"></div>
    <div class="form-group"><label>Symbol</label><input id="symbol" value="LPT"></div>
    <div class="form-group"><label>Description</label><textarea id="description">Proof-backed access token for evidence verification services</textarea></div>
    <div class="form-group"><label>Utility</label><textarea id="utility">Access to proof verification API, receipt-based settlement, audit credits</textarea></div>
    <div class="form-group"><label>Chain Target</label>
      <select id="chain_target"><option value="simulation">simulation</option>
      <option value="evm_testnet">evm_testnet</option>
      <option value="solana_devnet">solana_devnet</option></select></div>
    <div class="form-group"><label>Supply</label><input id="supply" type="number" value="1000000"></div>
    <div class="form-group"><label>Decimals</label><input id="decimals" type="number" value="18"></div>
    <div class="form-group"><label>Creator Wallet (public only)</label><input id="creator_wallet" placeholder="0x... (public address)"></div>
    <div class="form-group"><label>Project URL</label><input id="project_url" placeholder="https://..."></div>
    <div class="form-group"><label>GitHub URL</label><input id="github_url" placeholder="https://github.com/..."></div>
    <div class="form-group"><label>Evidence Text</label><textarea id="evidence_text" placeholder="Describe your proof, datasets, benchmarks..."></textarea></div>
    <div class="form-group"><label>ML Metrics (JSON)</label><textarea id="model_metrics" placeholder='{"balanced_accuracy":0.85,"sample_size":1000,"validation_type":"k_fold","leakage_checked":true,"out_of_sample":true}'></textarea></div>
    <div class="btn-row">
      <button onclick="callAPI('score')">Score</button>
      <button onclick="callAPI('launch/simulate')" class="secondary">Simulate Launch</button>
      <button onclick="callAPI('token/spec')" class="secondary">Token Spec</button>
      <button onclick="callAPI('launch/packet')" class="secondary">Launch Packet</button>
      <button onclick="loadReceipts()" class="secondary">View Receipts</button>
    </div>
  </div>
  <div id="results"></div>
</div>
<div class="disclaimer">This is not legal, financial, or investment advice. This tool produces proof and launch-readiness artifacts, not investment guarantees.</div>
<script>
function buildReq(){
  let mm=null;
  let mmText=document.getElementById('model_metrics').value.trim();
  if(mmText){try{mm=JSON.parse(mmText)}catch(e){}}
  return{
    name:document.getElementById('name').value,
    symbol:document.getElementById('symbol').value,
    description:document.getElementById('description').value,
    utility:document.getElementById('utility').value,
    chain_target:document.getElementById('chain_target').value,
    supply:parseFloat(document.getElementById('supply').value),
    decimals:parseInt(document.getElementById('decimals').value),
    creator_wallet:document.getElementById('creator_wallet').value||null,
    project_url:document.getElementById('project_url').value||null,
    github_url:document.getElementById('github_url').value||null,
    evidence_text:document.getElementById('evidence_text').value||null,
    model_metrics:mm,
    allow_public_launch_claim:false
  };
}
function scoreCard(label,val,max,goodThresh,warnThresh,invert){
  let cls='score-good';let pct=Math.round((val/max)*100);
  if(invert){if(pct>warnThresh)cls='score-warn';if(pct>goodThresh)cls='score-bad'}
  else{if(pct<warnThresh)cls='score-warn';if(pct<goodThresh)cls='score-bad'}
  return`<div class="score-card"><div class="score-value ${cls}">${val.toFixed(3)}</div><div class="score-label">${label}</div></div>`;
}
function renderScores(d){
  let s=d.scores||{};
  let html='<h2>Results</h2>';
  html+='<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-bottom:12px">';
  html+=scoreCard('Launch Readiness',s.launch_readiness_score||0,1,40,70,false);
  html+=scoreCard('Proof Density',s.proof_density_score||0,1,40,70,false);
  html+=scoreCard('ML Score',s.ml_score||0,1,40,70,false);
  html+=scoreCard('Fraud Risk',s.fraud_risk_score||0,1,30,60,true);
  html+=scoreCard('Compliance Risk',s.compliance_risk_score||0,1,30,60,true);
  html+=scoreCard('Utility',s.utility_score||0,1,40,70,false);
  html+='</div>';
  html+=`<div style="margin-bottom:8px"><span class="badge badge-${d.proof_grade==='NONE'?'red':'green'}">${d.proof_grade}</span>`;
  if(d.mainnet_blocked)html+='<span class="badge badge-red">mainnet blocked</span>';
  if(d.safe_to_generate_testnet_plan)html+='<span class="badge badge-green">testnet safe</span>';
  html+='</div>';
  if(d.recommended_routes&&d.recommended_routes.length){
    html+='<div style="margin-bottom:8px"><b>Routes:</b> '+d.recommended_routes.join(', ')+'</div>'}
  if(d.blocked_actions&&d.blocked_actions.length){
    html+='<div style="margin-bottom:8px"><b>Blocked:</b> '+d.blocked_actions.join(', ')+'</div>'}
  html+=`<div style="margin-bottom:8px;font-size:.75rem;color:#8b949e">Receipt: ${d.receipt_id||'N/A'}<br>Hash: ${(d.receipt_hash||'N/A').substring(0,30)}...</div>`;
  return html;
}
async function callAPI(endpoint){
  let req=buildReq();
  try{
    let resp=await fetch('/v1/'+endpoint,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(req)});
    let d=await resp.json();
    let html=renderScores(d);
    if(d.evm_spec)html+=`<details><summary>EVM Spec</summary><pre>${d.evm_spec}</pre></details>`;
    if(d.solana_plan)html+=`<details><summary>Solana Plan</summary><pre>${JSON.stringify(d.solana_plan,null,2)}</pre></details>`;
    if(d.testnet_checklist)html+=`<details><summary>Testnet Checklist</summary><pre>${d.testnet_checklist.join('\\n')}</pre></details>`;
    html+=`<details><summary>Full JSON</summary><pre>${JSON.stringify(d,null,2)}</pre></details>`;
    document.getElementById('results').innerHTML=html;
  }catch(e){document.getElementById('results').innerHTML='<p style="color:#f85149">Error: '+e.message+'</p>'}
}
async function loadReceipts(){
  try{
    let resp=await fetch('/v1/receipts');
    let d=await resp.json();
    let html='<h2>Receipts</h2>';
    if(d.receipts&&d.receipts.length){
      html+=`<p>Chain valid: ${d.chain_valid}</p>`;
      d.receipts.forEach(r=>{
        html+=`<details><summary>${r.receipt_id} — ${r.proof_grade} — ${r.launch_status}</summary><pre>${JSON.stringify(r,null,2)}</pre></details>`;
      });
    }else{html+='<p>No receipts yet.</p>'}
    document.getElementById('results').innerHTML=html;
  }catch(e){document.getElementById('results').innerHTML='<p style="color:#f85149">Error: '+e.message+'</p>'}
}
</script>
</body>
</html>"""

# ---------------------------------------------------------------------------
# HF Export Files
# ---------------------------------------------------------------------------

def hf_dockerfile() -> str:
    return """FROM python:3.11-slim
WORKDIR /app
COPY onefile_ml_token_launcher.py .
RUN pip install --no-cache-dir fastapi uvicorn pydantic
EXPOSE 7860
CMD ["python", "onefile_ml_token_launcher.py", "--serve", "--port", "7860"]
"""

def hf_requirements() -> str:
    return "fastapi\nuvicorn\npydantic\n"

def hf_readme() -> str:
    return f"""---
title: OneFile ML Token Launcher
emoji:rocket
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
---

# OneFile ML Token Launcher

Simulation/testnet-first token launch readiness scorer with ML metrics,
proof receipts, and risk assessment.

## Endpoints
- GET /health
- GET /
- POST /v1/score
- POST /v1/launch/simulate
- POST /v1/token/spec
- POST /v1/ml/evaluate
- POST /v1/proof/receipt
- POST /v1/risk/check
- POST /v1/launch/packet
- GET /v1/receipts
- GET /api/help
- GET /v1/export/hf-files

## Environment Variables
- ALLOW_MAINNET: set to YES_I_UNDERSTAND_RISK to generate mainnet instructions (never signs)
- No private keys are ever requested or stored.

## Disk Persistence
Hugging Face Spaces non-persistent disk is lost on restart.
For persistent receipts, attach a storage volume or use an external database.
The tool uses SQLite by default, falling back to JSONL.

{DISCLAIMER}
"""

# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

def create_app() -> "FastAPI":
    """Create the FastAPI application with all endpoints."""
    if not HAS_FASTAPI:
        raise RuntimeError("FastAPI not available. Install fastapi and uvicorn.")
    app = FastAPI(title="ONEFILE ML Token Launcher", version=VERSION)
    engine = ScoringEngine()

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": VERSION, "mainnet_blocked": engine._mainnet_blocked()}

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        return DASHBOARD_HTML

    @app.post("/v1/score")
    async def score(req: dict):
        r = dict_to_req(req.copy())
        return engine.score(r)

    @app.post("/v1/launch/simulate")
    async def launch_simulate(req: dict):
        r = dict_to_req(req.copy())
        s = engine.score(r)
        return {"simulation": True, "scores": s, "disclaimer": DISCLAIMER}

    @app.post("/v1/token/spec")
    async def token_spec(req: dict):
        r = dict_to_req(req.copy())
        s = engine.score(r)
        return {
            "evm_spec": generate_evm_spec(r, s),
            "solana_plan": generate_solana_plan(r, s),
            "scores": s,
            "disclaimer": DISCLAIMER,
        }

    @app.post("/v1/ml/evaluate")
    async def ml_evaluate(req: dict):
        r = dict_to_req(req.copy())
        s = engine.score(r)
        return {"ml_score": s["scores"]["ml_score"], "scores": s, "disclaimer": DISCLAIMER}

    @app.post("/v1/proof/receipt")
    async def proof_receipt(req: dict):
        r = dict_to_req(req.copy())
        s = engine.score(r)
        return {"receipt_id": s["receipt_id"], "receipt_hash": s["receipt_hash"],
                "proof_grade": s["proof_grade"], "disclaimer": DISCLAIMER}

    @app.post("/v1/risk/check")
    async def risk_check(req: dict):
        r = dict_to_req(req.copy())
        s = engine.score(r)
        return {"fraud_risk": s["scores"]["fraud_risk_score"],
                "compliance_risk": s["scores"]["compliance_risk_score"],
                "mainnet_blocked": s["mainnet_blocked"],
                "blocked_actions": s["blocked_actions"],
                "disclaimer": DISCLAIMER}

    @app.post("/v1/launch/packet")
    async def launch_packet(req: dict):
        r = dict_to_req(req.copy())
        s = engine.score(r)
        return generate_launch_packet(r, s)

    @app.get("/v1/receipts")
    async def receipts():
        rs = engine.store.all_receipts()
        return {"receipts": rs, "chain_valid": engine.store.verify_chain(), "count": len(rs)}

    @app.get("/api/help")
    async def api_help():
        return {
            "endpoints": [
                "GET /health", "GET /", "GET /openapi.json",
                "POST /v1/score", "POST /v1/launch/simulate",
                "POST /v1/token/spec", "POST /v1/ml/evaluate",
                "POST /v1/proof/receipt", "POST /v1/risk/check",
                "POST /v1/launch/packet", "GET /v1/receipts",
                "GET /api/help", "GET /v1/export/hf-files",
            ],
            "version": VERSION, "disclaimer": DISCLAIMER,
        }

    @app.get("/v1/export/hf-files")
    async def export_hf():
        return {
            "Dockerfile": hf_dockerfile(),
            "requirements.txt": hf_requirements(),
            "README.md": hf_readme(),
        }

    return app

# ---------------------------------------------------------------------------
# Fallback HTTP Server (no FastAPI)
# ---------------------------------------------------------------------------

def run_fallback_server(port: int):
    """Minimal HTTP server using stdlib when FastAPI is unavailable."""
    from http.server import HTTPServer, BaseHTTPRequestHandler
    engine = ScoringEngine()

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()
            if isinstance(body, str):
                body = body.encode()
            self.wfile.write(body)

        def do_OPTIONS(self):
            self._send(200, b"")

        def do_GET(self):
            if self.path == "/health":
                self._send(200, json.dumps({"status": "ok", "version": VERSION}))
            elif self.path == "/":
                self._send(200, DASHBOARD_HTML, "text/html")
            elif self.path == "/v1/receipts":
                rs = engine.store.all_receipts()
                self._send(200, json.dumps({"receipts": rs, "chain_valid": engine.store.verify_chain(), "count": len(rs)}, default=str))
            elif self.path == "/api/help":
                self._send(200, json.dumps({"endpoints": ["GET /health", "GET /", "POST /v1/score", "POST /v1/launch/simulate", "POST /v1/token/spec", "POST /v1/ml/evaluate", "POST /v1/proof/receipt", "POST /v1/risk/check", "POST /v1/launch/packet", "GET /v1/receipts", "GET /api/help"], "version": VERSION, "disclaimer": DISCLAIMER}))
            elif self.path == "/v1/export/hf-files":
                self._send(200, json.dumps({"Dockerfile": hf_dockerfile(), "requirements.txt": hf_requirements(), "README.md": hf_readme()}))
            else:
                self._send(404, json.dumps({"error": "not found"}))

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._send(400, json.dumps({"error": "invalid JSON"}))
                return
            path = self.path
            try:
                r = dict_to_req(data.copy())
                if path == "/v1/score":
                    self._send(200, json.dumps(engine.score(r), default=str))
                elif path == "/v1/launch/simulate":
                    s = engine.score(r)
                    self._send(200, json.dumps({"simulation": True, "scores": s, "disclaimer": DISCLAIMER}, default=str))
                elif path == "/v1/token/spec":
                    s = engine.score(r)
                    self._send(200, json.dumps({"evm_spec": generate_evm_spec(r, s), "solana_plan": generate_solana_plan(r, s), "scores": s, "disclaimer": DISCLAIMER}, default=str))
                elif path == "/v1/ml/evaluate":
                    s = engine.score(r)
                    self._send(200, json.dumps({"ml_score": s["scores"]["ml_score"], "scores": s, "disclaimer": DISCLAIMER}, default=str))
                elif path == "/v1/proof/receipt":
                    s = engine.score(r)
                    self._send(200, json.dumps({"receipt_id": s["receipt_id"], "receipt_hash": s["receipt_hash"], "proof_grade": s["proof_grade"], "disclaimer": DISCLAIMER}, default=str))
                elif path == "/v1/risk/check":
                    s = engine.score(r)
                    self._send(200, json.dumps({"fraud_risk": s["scores"]["fraud_risk_score"], "compliance_risk": s["scores"]["compliance_risk_score"], "mainnet_blocked": s["mainnet_blocked"], "blocked_actions": s["blocked_actions"], "disclaimer": DISCLAIMER}, default=str))
                elif path == "/v1/launch/packet":
                    s = engine.score(r)
                    self._send(200, json.dumps(generate_launch_packet(r, s), default=str))
                else:
                    self._send(404, json.dumps({"error": "not found"}))
            except Exception as e:
                self._send(500, json.dumps({"error": str(e), "traceback": traceback.format_exc()}))

    server = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Fallback HTTP server on port {port} (FastAPI not available)")
    server.serve_forever()

# ---------------------------------------------------------------------------
# Demo Mode
# ---------------------------------------------------------------------------

def run_demo():
    """Run a demo token scoring and write output files."""
    print("=" * 60)
    print("ONEFILE ML TOKEN LAUNCHER — DEMO MODE")
    print("=" * 60)
    engine = ScoringEngine()
    req = TokenLaunchRequest(
        name="LatentOS Proof Token",
        symbol="LPT",
        description="Proof-backed access token for evidence verification services",
        utility="Access to proof verification API, receipt-based settlement, audit credits, academic proof settlement",
        chain_target="simulation",
        supply=1_000_000.0,
        decimals=18,
        creator_wallet="0x0000000000000000000000000000000000000001",
        project_url="https://example.com/latentos",
        github_url="https://github.com/example/latentos",
        evidence_text="Evidence packet contains: ML model with balanced_accuracy=0.85 on 1000 samples, k-fold cross-validation, leakage checked, out-of-sample tested. Receipt chain verified. Proof grade: TESTNET_READY.",
        model_metrics=MLModelMetrics(
            balanced_accuracy=0.85, accuracy=0.87, f1=0.83, auc=0.89,
            sample_size=1000, validation_type="k_fold",
            leakage_checked=True, out_of_sample=True,
        ),
    )
    scores = engine.score(req)
    print(f"\nToken: {req.name} ({req.symbol})")
    print(f"Chain: {req.chain_target}")
    print(f"Proof Grade: {scores['proof_grade']}")
    print(f"Launch Readiness: {scores['scores']['launch_readiness_score']}")
    print(f"ML Score: {scores['scores']['ml_score']}")
    print(f"Proof Density: {scores['scores']['proof_density_score']}")
    print(f"Utility: {scores['scores']['utility_score']}")
    print(f"Fraud Risk: {scores['scores']['fraud_risk_score']}")
    print(f"Compliance Risk: {scores['scores']['compliance_risk_score']}")
    print(f"Mainnet Blocked: {scores['mainnet_blocked']}")
    print(f"Safe for Testnet: {scores['safe_to_generate_testnet_plan']}")
    print(f"Routes: {scores['recommended_routes']}")
    print(f"Blocked: {scores['blocked_actions']}")
    print(f"Receipt: {scores['receipt_id']}")
    print(f"Receipt Hash: {scores['receipt_hash']}")
    print(f"\n{DISCLAIMER}")

    # Write files
    packet = generate_launch_packet(req, scores)
    with open("launch_packet.json", "w") as f:
        json.dump(packet, f, indent=2, default=str)
    print(f"\nWrote: launch_packet.json")

    with open("token_spec_evm.sol.txt", "w") as f:
        f.write(generate_evm_spec(req, scores))
    print(f"Wrote: token_spec_evm.sol.txt")

    with open("token_plan_solana_devnet.json", "w") as f:
        json.dump(generate_solana_plan(req, scores), f, indent=2, default=str)
    print(f"Wrote: token_plan_solana_devnet.json")

    rs = engine.store.all_receipts()
    with open("receipts.jsonl", "w") as f:
        for r in rs:
            f.write(json.dumps(r, default=str) + "\n")
    print(f"Wrote: receipts.jsonl ({len(rs)} receipts)")

    readme = f"""# ONEFILE ML Token Launcher

## What This Is
A single-file, runnable MVP that combines ML scoring, token-launch readiness,
proof receipts, API endpoints, and a local web UI.

## How to Run
```bash
python onefile_ml_token_launcher.py --demo          # Demo mode
python onefile_ml_token_launcher.py --serve          # API server on port 7860
python onefile_ml_token_launcher.py --serve --port 8080  # Custom port
python onefile_ml_token_launcher.py --score token.json   # Score a JSON file
```

## Endpoints
- GET /health
- GET /
- GET /openapi.json (FastAPI only)
- POST /v1/score
- POST /v1/launch/simulate
- POST /v1/token/spec
- POST /v1/ml/evaluate
- POST /v1/proof/receipt
- POST /v1/risk/check
- POST /v1/launch/packet
- GET /v1/receipts
- GET /api/help
- GET /v1/export/hf-files

## Safety Model
- Defaults to SIMULATION mode
- Blocks mainnet unless ALLOW_MAINNET=YES_I_UNDERSTAND_RISK env var is set
- Never requests private keys
- Never signs transactions
- Never promises profit
- All generated contracts/plans are specs, not execution
- Every output includes risk warnings and proof status

## Environment Variables
- ALLOW_MAINNET: Set to YES_I_UNDERSTAND_RISK to allow mainnet instruction generation (never signs)
- No private keys are ever requested or stored

## Hugging Face Spaces Deployment
1. Create a new Docker Space on Hugging Face
2. Copy onefile_ml_token_launcher.py into the Space
3. GET /v1/export/hf-files returns Dockerfile, requirements.txt, and README.md
4. Copy those files into the Space repo
5. The app will start on port 7860

### Disk Persistence on HF Spaces
Non-persistent disk is lost on restart. For persistent receipts:
- Attach a persistent storage volume
- Or use an external database (Supabase, PlanetScale, etc.)
- The tool uses SQLite by default, falling back to JSONL

## What Is Still Simulation-Only
- All token contract specs are text only, not deployed
- All Solana mint plans are JSON specs, not executed
- No chain transactions are performed
- No private keys are handled
- Mainnet is blocked by default

{DISCLAIMER}
"""
    with open("README_ONEFILE_LAUNCHER.md", "w") as f:
        f.write(readme)
    print(f"Wrote: README_ONEFILE_LAUNCHER.md")
    print(f"\n{'=' * 60}")
    print("Demo complete. Files created in current directory.")
    print(f"{'=' * 60}")

# ---------------------------------------------------------------------------
# Score File Mode
# ---------------------------------------------------------------------------

def run_score_file(filepath: str):
    """Score a token request from a JSON file."""
    with open(filepath, "r") as f:
        data = json.load(f)
    engine = ScoringEngine()
    req = dict_to_req(data.copy())
    scores = engine.score(req)
    print(json.dumps(scores, indent=2, default=str))

# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="ONEFILE ML Token Launcher — Simulation/testnet-first MVP"
    )
    parser.add_argument("--demo", action="store_true", help="Run demo token scoring")
    parser.add_argument("--serve", action="store_true", help="Start API server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Server port (default {DEFAULT_PORT})")
    parser.add_argument("--score", type=str, help="Score a JSON token request file")
    args = parser.parse_args()

    if args.demo:
        run_demo()
    elif args.serve:
        if HAS_FASTAPI:
            app = create_app()
            print(f"Starting ONEFILE ML Token Launcher on port {args.port}")
            print(f"FastAPI: {HAS_FASTAPI}, Pydantic: {HAS_PYDANTIC}, NumPy: {HAS_NUMPY}, sklearn: {HAS_SKLEARN}")
            print(f"Mainnet blocked: {os.environ.get('ALLOW_MAINNET', '') != MAINNET_ENV_VALUE}")
            uvicorn.run(app, host="0.0.0.0", port=args.port)
        else:
            run_fallback_server(args.port)
    elif args.score:
        run_score_file(args.score)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
