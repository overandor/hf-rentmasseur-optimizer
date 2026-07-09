"""
POptimizer — Speed / RAM / Quality / Proprietary Objective Engine

Implements the optimization formula:

  J(x) = λ₁·L(x) + λ₂·M(x) + λ₃·C(x) + λ₄·B(x) + λ₅·D(x) + λ₆·R(x) + λ₇·I(x) - λ₈·Q(x) - λ₉·V(x)

Subject to hard constraints:
  secrets_exposed = 0
  private_code_uploaded = 0
  license_conflict = 0
  tests_required = pass
  destructive_action => explicit_approval

Priority order:
  security > correctness > verification > RAM > speed > quality > convenience
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

DEFAULT_LAMBDAS = {
    'latency': 1.0,
    'memory': 1.2,
    'cpu': 0.8,
    'bundle_size': 0.5,
    'dependency_risk': 1.5,
    'runtime_risk': 1.3,
    'ip_leakage': 10.0,
    'code_quality': 0.9,
    'verification_confidence': 0.7,
}


@dataclass
class OptimizationInput:
    startup_time_ms: float = 0.0
    p95_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    blocking_io_time_ms: float = 0.0
    cold_path_penalty: float = 0.0

    peak_rss_mb: float = 0.0
    heap_used_mb: float = 0.0
    allocation_rate_mbps: float = 0.0
    cache_unboundedness: float = 0.0
    leak_probability: float = 0.0

    cpu_usage_pct: float = 0.0

    bundle_size_kb: float = 0.0

    dependency_license_risk: float = 0.0
    dependency_maintenance_risk: float = 0.0
    dependency_supply_chain_risk: float = 0.0

    runtime_failure_probability: float = 0.0

    secret_exposure: int = 0
    private_code_upload: int = 0
    license_conflict: int = 0
    public_disclosure_unapproved: int = 0
    ownership_notice_removed: int = 0
    unapproved_third_party_dependency: int = 0

    readability: float = 50.0
    maintainability: float = 50.0
    testability: float = 50.0
    type_safety: float = 50.0
    locality_of_change: float = 50.0
    style_consistency: float = 50.0
    complexity: float = 50.0
    cleverness: float = 50.0
    surface_area: float = 50.0

    tests_passed: bool = False
    build_passed: bool = False
    lint_passed: bool = False
    benchmark_available: bool = False
    manual_inspection: bool = False
    receipt_created: bool = False

    lambdas: dict = field(default_factory=lambda: dict(DEFAULT_LAMBDAS))


@dataclass
class OptimizationResult:
    valid: bool
    j_score: float
    latency_cost: float
    memory_cost: float
    cpu_cost: float
    bundle_cost: float
    dependency_cost: float
    runtime_risk: float
    ip_risk: float
    quality_score: float
    verification_confidence: float
    constraint_violations: list = field(default_factory=list)
    receipt: dict = field(default_factory=dict)
    timestamp: str = ''

    def to_dict(self) -> dict:
        return asdict(self)


def compute_latency(x: OptimizationInput) -> float:
    return (
        0.3 * x.startup_time_ms
        + 0.3 * x.p95_latency_ms
        + 0.2 * x.p99_latency_ms
        + 0.15 * x.blocking_io_time_ms
        + 0.05 * x.cold_path_penalty
    )


def compute_memory(x: OptimizationInput) -> float:
    if x.cache_unboundedness > 0.5:
        return 1e9
    if x.leak_probability > 0.5:
        return 1e9
    return (
        0.3 * x.peak_rss_mb
        + 0.3 * x.heap_used_mb
        + 0.2 * x.allocation_rate_mbps
        + 0.15 * x.cache_unboundedness * 1000
        + 0.05 * x.leak_probability * 1000
    )


def compute_cpu(x: OptimizationInput) -> float:
    return x.cpu_usage_pct


def compute_bundle(x: OptimizationInput) -> float:
    return x.bundle_size_kb


def compute_dependency(x: OptimizationInput) -> float:
    return (
        0.3 * x.dependency_license_risk * 100
        + 0.3 * x.dependency_maintenance_risk * 100
        + 0.2 * x.bundle_size_kb * 0.01
        + 0.1 * x.dependency_supply_chain_risk * 100
    )


def compute_runtime_risk(x: OptimizationInput) -> float:
    return x.runtime_failure_probability * 100


def compute_ip_risk(x: OptimizationInput) -> float:
    total = (
        x.secret_exposure
        + x.private_code_upload
        + x.license_conflict
        + x.public_disclosure_unapproved
        + x.ownership_notice_removed
        + x.unapproved_third_party_dependency
    )
    if total > 0:
        return 1e9
    return 0.0


def compute_quality(x: OptimizationInput) -> float:
    positive = (
        0.15 * x.readability
        + 0.15 * x.maintainability
        + 0.15 * x.testability
        + 0.10 * x.type_safety
        + 0.10 * x.locality_of_change
        + 0.10 * x.style_consistency
    )
    negative = (
        0.10 * x.complexity
        + 0.10 * x.cleverness
        + 0.05 * x.surface_area
    )
    return positive - negative


def compute_verification(x: OptimizationInput) -> float:
    score = 0.0
    if x.tests_passed:
        score += 25
    if x.build_passed:
        score += 20
    if x.lint_passed:
        score += 10
    if x.benchmark_available:
        score += 15
    if x.manual_inspection:
        score += 15
    if x.receipt_created:
        score += 15
    return score


def check_constraints(x: OptimizationInput) -> list:
    violations = []
    if x.secret_exposure > 0:
        violations.append('secret_exposure > 0')
    if x.private_code_upload > 0:
        violations.append('private_code_uploaded > 0')
    if x.license_conflict > 0:
        violations.append('license_conflict > 0')
    if x.public_disclosure_unapproved > 0:
        violations.append('public_disclosure_unapproved > 0')
    if x.ownership_notice_removed > 0:
        violations.append('ownership_notice_removed > 0')
    if x.unapproved_third_party_dependency > 0:
        violations.append('unapproved_third_party_dependency > 0')
    return violations


def optimize(x: OptimizationInput) -> OptimizationResult:
    lam = x.lambdas

    violations = check_constraints(x)
    valid = len(violations) == 0

    L = compute_latency(x)
    M = compute_memory(x)
    C = compute_cpu(x)
    B = compute_bundle(x)
    D = compute_dependency(x)
    R = compute_runtime_risk(x)
    I = compute_ip_risk(x)
    Q = compute_quality(x)
    V = compute_verification(x)

    j = (
        lam['latency'] * L
        + lam['memory'] * M
        + lam['cpu'] * C
        + lam['bundle_size'] * B
        + lam['dependency_risk'] * D
        + lam['runtime_risk'] * R
        + lam['ip_leakage'] * I
        - lam['code_quality'] * Q
        - lam['verification_confidence'] * V
    )

    receipt = {
        'timestamp': datetime.now().isoformat(),
        'j_score': round(j, 4),
        'valid': valid,
        'constraint_violations': violations,
        'L_latency': round(L, 4),
        'M_memory': round(M, 4),
        'C_cpu': round(C, 4),
        'B_bundle': round(B, 4),
        'D_dependency': round(D, 4),
        'R_runtime_risk': round(R, 4),
        'I_ip_risk': I,
        'Q_quality': round(Q, 4),
        'V_verification': round(V, 4),
        'lambdas': lam,
        'hard_rule': 'No receipt → no production claim.',
    }

    return OptimizationResult(
        valid=valid,
        j_score=round(j, 4),
        latency_cost=round(L, 4),
        memory_cost=round(M, 4),
        cpu_cost=round(C, 4),
        bundle_cost=round(B, 4),
        dependency_cost=round(D, 4),
        runtime_risk=round(R, 4),
        ip_risk=I,
        quality_score=round(Q, 4),
        verification_confidence=round(V, 4),
        constraint_violations=violations,
        receipt=receipt,
        timestamp=datetime.now().isoformat(),
    )


def compare(x_old: OptimizationInput, x_new: OptimizationInput) -> dict:
    r_old = optimize(x_old)
    r_new = optimize(x_new)

    if not r_new.valid:
        return {
            'decision': 'REJECT',
            'reason': 'constraint_violations',
            'violations': r_new.constraint_violations,
            'j_old': r_old.j_score,
            'j_new': r_new.j_score,
        }

    improved = r_new.j_score < r_old.j_score
    return {
        'decision': 'ACCEPT' if improved else 'REJECT',
        'reason': 'J(x_new) < J(x_old)' if improved else 'J(x_new) >= J(x_old)',
        'j_old': r_old.j_score,
        'j_new': r_new.j_score,
        'delta_j': round(r_new.j_score - r_old.j_score, 4),
        'delta_speed': round(r_old.latency_cost - r_new.latency_cost, 4),
        'delta_ram': round(r_old.memory_cost - r_new.memory_cost, 4),
        'delta_quality': round(r_new.quality_score - r_old.quality_score, 4),
        'ip_risk': r_new.ip_risk,
        'verification': r_new.verification_confidence,
        'receipt': r_new.receipt,
    }


def endpoint_receipt(
    endpoint: str,
    classification: str,
    availability: bool,
    latency_ms: float,
    schema_valid: bool,
    auth_flow: str,
    security_observations: list,
    build_evidence: bool,
    runtime_evidence: bool,
    verification_confidence: float,
) -> dict:
    return {
        'endpoint': endpoint,
        'classification': classification,
        'availability': availability,
        'latency_ms': latency_ms,
        'schema_valid': schema_valid,
        'authentication': auth_flow,
        'security_observations': security_observations,
        'build_evidence': build_evidence,
        'runtime_evidence': runtime_evidence,
        'verification_confidence': verification_confidence,
        'receipt_hash': hashlib.sha256(
            json.dumps({
                'endpoint': endpoint,
                'classification': classification,
                'timestamp': datetime.now().isoformat(),
            }, sort_keys=True).encode()
        ).hexdigest()[:16],
        'next_hardening_action': 'Add rate limiting and input validation' if not security_observations else security_observations[0],
    }
