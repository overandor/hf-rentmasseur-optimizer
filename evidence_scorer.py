"""
Evidence Scorer — Scoring engine for the Layer Crawler ETL pipeline.

Scores:
  EvidenceScore   — how much verifiable evidence exists (0-100)
  RealityPenalty  — penalty for unverified or fake production claims (0-100)
  ProdScore       — EvidenceScore - RealityPenalty (0-100)
  HardenRank      — ranking of how much hardening is needed (0-100, lower = better)
  IPRisk          — proprietary / IP leakage risk (0-100, 0 = clean)
  RuntimeRisk     — runtime failure risk (0-100, 0 = safe)

Canonical record format:
  {
    "system": "...",
    "subject": "...",
    "source": "...",
    "timestamp": "...",
    "artifact": "...",
    "signals": { build_verified, tests_verified, runtime_verified, ... },
    "scores": { evidence, reality_penalty, prod_score, ip_risk }
  }
"""

import hashlib
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class EvidenceSignals:
    build_verified: bool = False
    tests_verified: bool = False
    runtime_verified: bool = False
    browser_verified: bool = False
    console_errors: int = -1
    failed_requests: int = -1
    secrets_exposed: int = 0
    license_conflict: int = 0
    docs_verified: bool = False
    ci_verified: bool = False
    deploy_verified: bool = False
    has_screenshots: bool = False
    has_command_logs: bool = False
    has_receipts: bool = False
    claims_without_evidence: int = 0
    unverified_production_claims: int = 0
    test_count: int = 0
    test_pass_count: int = 0
    lint_passed: bool = False
    dependency_audit_passed: bool = False
    security_scan_passed: bool = False


def compute_evidence_score(s: EvidenceSignals) -> float:
    """How much verifiable evidence exists. 0-100."""
    score = 0.0
    if s.build_verified: score += 15
    if s.tests_verified: score += 15
    if s.runtime_verified: score += 15
    if s.browser_verified: score += 10
    if s.docs_verified: score += 5
    if s.ci_verified: score += 10
    if s.deploy_verified: score += 10
    if s.has_screenshots: score += 5
    if s.has_command_logs: score += 5
    if s.has_receipts: score += 10
    if s.lint_passed: score += 5
    if s.dependency_audit_passed: score += 5
    if s.security_scan_passed: score += 5
    if s.test_count > 0 and s.test_pass_count == s.test_count: score += 5
    if s.console_errors == 0: score += 5
    if s.failed_requests == 0: score += 5
    return min(100.0, score)


def compute_reality_penalty(s: EvidenceSignals) -> float:
    """Penalty for unverified or fake production claims. 0-100."""
    penalty = 0.0
    penalty += s.claims_without_evidence * 10
    penalty += s.unverified_production_claims * 15
    if s.console_errors > 0: penalty += min(20, s.console_errors * 2)
    if s.failed_requests > 0: penalty += min(20, s.failed_requests * 2)
    if not s.build_verified: penalty += 10
    if not s.tests_verified and s.test_count > 0: penalty += 10
    if not s.runtime_verified: penalty += 10
    if not s.deploy_verified: penalty += 5
    return min(100.0, penalty)


def compute_prod_score(evidence: float, reality: float) -> float:
    """ProdScore = EvidenceScore - RealityPenalty, clamped 0-100."""
    return max(0.0, min(100.0, evidence - reality))


def compute_harden_rank(s: EvidenceSignals, prod_score: float) -> float:
    """How much hardening is needed. 0 = production-ready, 100 = needs everything."""
    gaps = 0.0
    if not s.build_verified: gaps += 15
    if not s.tests_verified: gaps += 15
    if not s.runtime_verified: gaps += 15
    if not s.browser_verified: gaps += 10
    if not s.ci_verified: gaps += 10
    if not s.deploy_verified: gaps += 10
    if not s.lint_passed: gaps += 5
    if not s.dependency_audit_passed: gaps += 10
    if not s.security_scan_passed: gaps += 10
    if s.secrets_exposed > 0: gaps += 20
    if s.license_conflict > 0: gaps += 10
    return min(100.0, gaps)


def compute_ip_risk(s: EvidenceSignals) -> float:
    """IP leakage risk. 0 = clean, 100 = severe."""
    risk = 0.0
    risk += s.secrets_exposed * 30
    risk += s.license_conflict * 20
    return min(100.0, risk)


def compute_runtime_risk(s: EvidenceSignals) -> float:
    """Runtime failure risk. 0 = safe, 100 = likely to fail."""
    risk = 0.0
    if not s.build_verified: risk += 25
    if not s.tests_verified: risk += 20
    if not s.runtime_verified: risk += 25
    if s.console_errors > 0: risk += min(15, s.console_errors * 3)
    if s.failed_requests > 0: risk += min(15, s.failed_requests * 3)
    if not s.deploy_verified: risk += 10
    return min(100.0, risk)


def score_signals(signals: EvidenceSignals) -> dict:
    """Full scoring of evidence signals."""
    evidence = compute_evidence_score(signals)
    reality = compute_reality_penalty(signals)
    prod = compute_prod_score(evidence, reality)
    harden = compute_harden_rank(signals, prod)
    ip = compute_ip_risk(signals)
    runtime = compute_runtime_risk(signals)

    return {
        'evidence': round(evidence, 1),
        'reality_penalty': round(reality, 1),
        'prod_score': round(prod, 1),
        'harden_rank': round(harden, 1),
        'ip_risk': round(ip, 1),
        'runtime_risk': round(runtime, 1),
        'verdict': _verdict(prod, harden, ip),
    }


def _verdict(prod_score: float, harden_rank: float, ip_risk: float) -> str:
    if ip_risk > 0:
        return 'BLOCKED: IP risk detected'
    if prod_score >= 80 and harden_rank <= 10:
        return 'PRODUCTION READY'
    if prod_score >= 60 and harden_rank <= 30:
        return 'NEAR READY: minor hardening needed'
    if prod_score >= 40:
        return 'DEVELOPMENT: significant hardening needed'
    if prod_score >= 20:
        return 'EARLY: major gaps in evidence'
    return 'UNVERIFIED: no production claim allowed'


def create_canonical_record(
    system: str,
    subject: str,
    source: str,
    artifact: str,
    signals: EvidenceSignals,
    extra_signals: dict = None,
) -> dict:
    """Create a canonical evidence record."""
    scores = score_signals(signals)
    signal_dict = asdict(signals)
    if extra_signals:
        signal_dict.update(extra_signals)

    record = {
        'system': system,
        'subject': subject,
        'source': source,
        'timestamp': datetime.now().isoformat(),
        'artifact': artifact,
        'signals': signal_dict,
        'scores': scores,
    }
    record['record_hash'] = hashlib.sha256(
        json.dumps(record, sort_keys=True, default=str).encode()
    ).hexdigest()[:16]
    return record
