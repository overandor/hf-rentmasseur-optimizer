"""LatentOS Core — Pre-revenue software value liquidity engine.

Scores messy artifacts, failed deployments, memory conflicts, product gaps,
safety gaps, long-context failures, and monetization workflows as pre-revenue
software value.

Pipeline:
    unstructured progress -> truth-graded claim -> evidence/provenance
    -> risk score -> liquidity cap -> endpoint opportunity -> settlement route
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    SignalType,
    ProvenanceSource,
    DisclosureMode,
    MarketPurpose,
    Provenance,
    PrivacyConfig,
    MarketContext,
)


def _receipt_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def _now() -> str:
    return datetime.now().isoformat()


class LatentSignalScorer:
    """Scores any latent signal (software or academic) into a liquidity verdict.

    The scoring formula is generalized:

        liquidity = proof_strength - privacy_risk - fraud_risk - compliance_risk

    For software:
        proof_strength = f(artifact_hash, deployment_evidence, test_pass, receipt, usage_log)
        privacy_risk = f(secret_exposure, source_code_leaked, internal_reasoning_exposed)
        fraud_risk = f(self_declared_only, no_delta, phantom_usage, circular_ref)

    For academic:
        proof_strength = f(issuer_sig, credential_status, verified_claims, evidence_links)
        privacy_risk = f(raw_grade_exposed, transcript_leaked, identity_doxxed)
        fraud_risk = f(self_claimed, stale_credential, revoked, coerced)
    """

    PROVENANCE_WEIGHTS: Dict[str, float] = {
        ProvenanceSource.user_declared.value: 0.1,
        ProvenanceSource.observed_behavior.value: 0.3,
        ProvenanceSource.uploaded_file.value: 0.3,
        ProvenanceSource.issuer_signed.value: 0.9,
        ProvenanceSource.tool_verified.value: 0.7,
        ProvenanceSource.external_verified.value: 0.8,
    }

    def score_provenance(self, provenance: Provenance) -> float:
        base = self.PROVENANCE_WEIGHTS.get(provenance.source.value, 0.1)
        return base * provenance.confidence * 100

    def score_proof_strength(
        self,
        signal_type: SignalType,
        payload: Dict[str, Any],
        provenance: Provenance,
    ) -> Tuple[float, List[str]]:
        """Returns (score 0-100, list of proof gaps)."""
        score = 0.0
        gaps: List[str] = []

        if signal_type == SignalType.software_artifact:
            if payload.get("artifact_hash"):
                score += 15
            else:
                gaps.append("artifact_hash")
            if payload.get("deployment_evidence"):
                score += 20
            else:
                gaps.append("deployment_evidence")
            if payload.get("test_pass"):
                score += 20
            else:
                gaps.append("test_pass")
            if payload.get("receipt"):
                score += 15
            else:
                gaps.append("receipt")
            if payload.get("usage_log"):
                score += 10
            else:
                gaps.append("usage_log")
            if payload.get("endpoint_response"):
                score += 10
            else:
                gaps.append("endpoint_response")
            score += self.score_provenance(provenance) * 0.1

        elif signal_type == SignalType.deployment_failure:
            if payload.get("failure_log"):
                score += 25
            else:
                gaps.append("failure_log")
            if payload.get("root_cause"):
                score += 20
            else:
                gaps.append("root_cause_analysis")
            if payload.get("remediation_path"):
                score += 15
            else:
                gaps.append("remediation_path")
            if payload.get("repro_steps"):
                score += 15
            else:
                gaps.append("repro_steps")
            score += self.score_provenance(provenance) * 0.25

        elif signal_type == SignalType.memory_claim:
            if payload.get("corroborating_evidence"):
                score += 30
            else:
                gaps.append("corroborating_evidence")
            if payload.get("receipt"):
                score += 25
            else:
                gaps.append("receipt")
            if payload.get("delta_proof"):
                score += 20
            else:
                gaps.append("delta_proof")
            score += self.score_provenance(provenance) * 0.25

        elif signal_type == SignalType.verification_gap:
            if payload.get("gap_description"):
                score += 20
            else:
                gaps.append("gap_description")
            if payload.get("attempted_verification"):
                score += 25
            else:
                gaps.append("attempted_verification")
            if payload.get("blocking_issue"):
                score += 15
            else:
                gaps.append("blocking_issue")
            score += self.score_provenance(provenance) * 0.4

        else:
            score += self.score_provenance(provenance) * 0.5

        return min(100.0, score), gaps

    def score_privacy_risk(
        self,
        signal_type: SignalType,
        payload: Dict[str, Any],
        privacy: PrivacyConfig,
    ) -> Tuple[float, List[str]]:
        """Returns (risk 0-100, list of blocked fields that would be exposed)."""
        risk = 0.0
        blocked_exposed: List[str] = []

        blocked_set = set(privacy.blocked_fields)

        for field in blocked_set:
            if field in payload:
                blocked_exposed.append(field)
                risk += 25

        if signal_type == SignalType.software_artifact:
            if payload.get("source_code_included"):
                risk += 30
            if payload.get("secrets_included"):
                risk += 40
            if payload.get("internal_reasoning_exposed"):
                risk += 20

        elif signal_type == SignalType.academic_credential:
            if payload.get("raw_grade_exposed"):
                risk += 35
            if payload.get("transcript_exposed"):
                risk += 30
            if payload.get("identity_doxxed"):
                risk += 25
            if payload.get("ferpa_data_without_consent"):
                risk += 40

        elif signal_type == SignalType.memory_claim:
            if payload.get("private_chat_exposed"):
                risk += 30

        if privacy.disclosure_mode == DisclosureMode.full_with_consent:
            risk *= 0.5
        elif privacy.disclosure_mode == DisclosureMode.settlement_only:
            risk *= 0.3
        elif privacy.disclosure_mode == DisclosureMode.threshold_only:
            risk *= 0.2
        elif privacy.disclosure_mode == DisclosureMode.minimal:
            risk *= 0.1

        return min(100.0, risk), blocked_exposed

    def score_fraud_risk(
        self,
        signal_type: SignalType,
        payload: Dict[str, Any],
        provenance: Provenance,
    ) -> float:
        risk = 0.0

        if provenance.source == ProvenanceSource.user_declared and provenance.confidence < 0.3:
            risk += 30

        if signal_type == SignalType.software_artifact:
            if not payload.get("artifact_hash"):
                risk += 15
            if payload.get("phantom_usage"):
                risk += 25
            if payload.get("circular_reference"):
                risk += 20
            if not payload.get("delta_proof"):
                risk += 10

        elif signal_type == SignalType.academic_credential:
            if not payload.get("issuer_signature"):
                risk += 30
            if payload.get("credential_revoked"):
                risk += 40
            if payload.get("stale_credential"):
                risk += 15
            if payload.get("self_claimed_grade"):
                risk += 25
            if payload.get("coerced_consent"):
                risk += 35

        elif signal_type == SignalType.memory_claim:
            if not payload.get("corroborating_evidence"):
                risk += 20

        return min(100.0, risk)

    def score_compliance_risk(
        self,
        signal_type: SignalType,
        payload: Dict[str, Any],
        market_context: MarketContext,
    ) -> float:
        risk = 0.0

        if signal_type == SignalType.academic_credential:
            if not payload.get("student_consent"):
                risk += 30
            if payload.get("minor_record") and not payload.get("parental_consent"):
                risk += 40
            if market_context.purpose in (MarketPurpose.prediction, MarketPurpose.credit):
                if not payload.get("consent_for_market_use"):
                    risk += 25
            if payload.get("jurisdiction") == "US" and not payload.get("ferpa_compliant"):
                risk += 20

        if signal_type == SignalType.software_artifact:
            if payload.get("license_conflict"):
                risk += 25
            if payload.get("unapproved_dependency"):
                risk += 15

        return min(100.0, risk)

    def estimate_value_range(
        self,
        liquidity_score: float,
        signal_type: SignalType,
        market_context: MarketContext,
    ) -> Dict[str, float]:
        base = liquidity_score

        if signal_type == SignalType.software_artifact:
            multiplier = {"low": 200, "mid": 1000, "high": 5000}
        elif signal_type == SignalType.academic_credential:
            multiplier = {"low": 50, "mid": 300, "high": 1200}
        elif signal_type == SignalType.deployment_failure:
            multiplier = {"low": 100, "mid": 500, "high": 2000}
        else:
            multiplier = {"low": 50, "mid": 250, "high": 1000}

        if market_context.purpose == MarketPurpose.scholarship:
            multiplier = {"low": 100, "mid": 500, "high": 2000}
        elif market_context.purpose == MarketPurpose.saas_opportunity:
            multiplier = {"low": 500, "mid": 5000, "high": 50000}

        return {
            "low": round(base * multiplier["low"] / 100, 2),
            "mid": round(base * multiplier["mid"] / 100, 2),
            "high": round(base * multiplier["high"] / 100, 2),
        }

    def compute_liquidity_routes(
        self,
        signal_type: SignalType,
        liquidity_score: float,
        market_context: MarketContext,
    ) -> List[str]:
        routes: List[str] = []

        if liquidity_score < 20:
            return ["insufficient_proof"]

        if signal_type == SignalType.software_artifact:
            routes = ["valuation", "licensing", "SaaS_opportunity"]
            if liquidity_score >= 50:
                routes.append("acquisition_target")
            if liquidity_score >= 70:
                routes.append("revenue_share")

        elif signal_type == SignalType.academic_credential:
            routes = ["scholarship_pool"]
            if liquidity_score >= 40:
                routes.append("conditional_advance")
                routes.append("employer_bounty")
            if liquidity_score >= 60:
                routes.append("peer_backed_education_funding")
                routes.append("prediction_settled_academic_pool")
            if liquidity_score >= 80:
                routes.append("credit_line")

        elif signal_type == SignalType.deployment_failure:
            routes = ["breakage_report", "remediation_bounty"]
            if liquidity_score >= 50:
                routes.append("eval_dataset")

        elif signal_type == SignalType.memory_claim:
            routes = ["eval_signal"]
            if liquidity_score >= 50:
                routes.append("training_data_contribution")

        elif signal_type == SignalType.verification_gap:
            routes = ["gap_bounty"]
            if liquidity_score >= 50:
                routes.append("safety_improvement_grant")

        return routes

    def settle_signal(
        self,
        signal_type: SignalType,
        payload: Dict[str, Any],
        provenance: Provenance,
        privacy: PrivacyConfig,
        market_context: MarketContext,
    ) -> Dict[str, Any]:
        proof_strength, proof_gaps = self.score_proof_strength(signal_type, payload, provenance)
        privacy_risk, blocked_exposed = self.score_privacy_risk(signal_type, payload, privacy)
        fraud_risk = self.score_fraud_risk(signal_type, payload, provenance)
        compliance_risk = self.score_compliance_risk(signal_type, payload, market_context)

        liquidity_score = max(
            0.0,
            proof_strength - privacy_risk * 0.3 - fraud_risk * 0.3 - compliance_risk * 0.2,
        )

        readiness = max(0.0, proof_strength - privacy_risk - fraud_risk - compliance_risk)

        value_range = self.estimate_value_range(liquidity_score, signal_type, market_context)
        routes = self.compute_liquidity_routes(signal_type, liquidity_score, market_context)

        allowed_disclosure: List[str] = []
        blocked_disclosure: List[str] = list(privacy.blocked_fields)

        if privacy.disclosure_mode == DisclosureMode.minimal:
            allowed_disclosure = ["liquidity_score", "proof_strength", "grade_band"]
            blocked_disclosure.extend(["raw_grade", "transcript", "source_code", "secrets"])
        elif privacy.disclosure_mode == DisclosureMode.threshold_only:
            allowed_disclosure = ["liquidity_score", "proof_strength", "grade_band", "credential_status"]
            blocked_disclosure.extend(["raw_grade", "transcript"])
        elif privacy.disclosure_mode == DisclosureMode.settlement_only:
            allowed_disclosure = ["liquidity_score", "proof_strength", "settlement_amount", "route"]
            blocked_disclosure.extend(["raw_grade", "transcript", "source_code"])
        elif privacy.disclosure_mode == DisclosureMode.full_with_consent:
            allowed_disclosure = ["all_with_documented_consent"]

        receipt = {
            "schema": "membra.latentos.settlement_receipt.v1",
            "receipt_id": str(uuid.uuid4()),
            "timestamp": _now(),
            "signal_type": signal_type.value,
            "provenance_source": provenance.source.value,
            "provenance_confidence": provenance.confidence,
            "proof_strength": round(proof_strength, 1),
            "privacy_risk": round(privacy_risk, 1),
            "fraud_risk": round(fraud_risk, 1),
            "compliance_risk": round(compliance_risk, 1),
            "liquidity_score": round(liquidity_score, 1),
            "readiness": round(readiness, 1),
            "value_range_usd": value_range,
            "routes": routes,
            "blocked_exposed": blocked_exposed,
            "disclosure_mode": privacy.disclosure_mode.value,
            "market_purpose": market_context.purpose.value,
        }
        receipt["receipt_hash"] = _receipt_hash(receipt)

        return {
            "signal_liquidity_score": round(liquidity_score, 1),
            "proof_strength": round(proof_strength, 1),
            "privacy_risk": round(privacy_risk, 1),
            "fraud_risk": round(fraud_risk, 1),
            "deployment_or_settlement_readiness": round(readiness, 1),
            "estimated_value_range_usd": value_range,
            "allowed_disclosure": allowed_disclosure,
            "blocked_disclosure": list(set(blocked_disclosure)),
            "liquidification_routes": routes,
            "required_next_proofs": proof_gaps,
            "receipt": receipt,
        }


class BreakageMapper:
    """Maps breakage signals (failed deployments, memory conflicts, product gaps) into value leaks."""

    def map(self, payload: Dict[str, Any], provenance: Provenance) -> Dict[str, Any]:
        breakage_type = payload.get("breakage_type", "unknown")
        severity = payload.get("severity", "medium")
        root_cause = payload.get("root_cause", "unidentified")
        remediation = payload.get("remediation_path", "not_defined")
        reproducible = payload.get("reproducible", False)

        severity_scores = {"low": 20, "medium": 40, "high": 60, "critical": 80}
        sev_score = severity_scores.get(severity, 40)

        value_leak = sev_score * (1.5 if reproducible else 1.0)

        opportunities: List[str] = []
        if breakage_type == "deployment_failure":
            opportunities = ["remediation_bounty", "eval_dataset", "safety_improvement"]
        elif breakage_type == "memory_conflict":
            opportunities = ["memory_repair_grant", "eval_signal", "context_window_optimization"]
        elif breakage_type == "product_gap":
            opportunities = ["gap_bounty", "SaaS_opportunity", "feature_funding"]
        elif breakage_type == "long_context_failure":
            opportunities = ["context_optimization_grant", "eval_dataset"]
        elif breakage_type == "safety_gap":
            opportunities = ["safety_improvement_grant", "red_team_bounty"]

        return {
            "breakage_type": breakage_type,
            "severity": severity,
            "root_cause": root_cause,
            "remediation_path": remediation,
            "reproducible": reproducible,
            "estimated_value_leak_usd": round(value_leak * 10, 2),
            "liquidity_opportunities": opportunities,
            "provenance_confidence": provenance.confidence,
        }


class GapDetector:
    """Detects product gaps, safety gaps, and verification gaps from signals."""

    def detect(self, payload: Dict[str, Any], provenance: Provenance) -> Dict[str, Any]:
        gaps: List[Dict[str, Any]] = []

        if not payload.get("has_tests"):
            gaps.append({"gap_type": "verification_gap", "description": "No test coverage", "severity": "medium"})
        if not payload.get("has_receipts"):
            gaps.append({"gap_type": "verification_gap", "description": "No execution receipts", "severity": "medium"})
        if not payload.get("has_deployment"):
            gaps.append({"gap_type": "product_gap", "description": "No deployment evidence", "severity": "high"})
        if payload.get("secret_exposure"):
            gaps.append({"gap_type": "safety_gap", "description": "Secret exposure detected", "severity": "critical"})
        if not payload.get("has_license"):
            gaps.append({"gap_type": "product_gap", "description": "No license file", "severity": "low"})
        if payload.get("long_context_failure"):
            gaps.append({"gap_type": "product_gap", "description": "Long-context collapse detected", "severity": "high"})

        custom_gaps = payload.get("detected_gaps", [])
        for cg in custom_gaps:
            gaps.append(cg)

        total_gaps = len(gaps)
        critical = sum(1 for g in gaps if g.get("severity") == "critical")
        high = sum(1 for g in gaps if g.get("severity") == "high")

        gap_liquidity = min(100, total_gaps * 15 + critical * 20 + high * 10)

        return {
            "total_gaps": total_gaps,
            "critical_gaps": critical,
            "high_gaps": high,
            "gaps": gaps,
            "gap_liquidity_score": gap_liquidity,
            "opportunities": ["gap_bounty"] if gap_liquidity >= 30 else [],
        }


class MemoryGrader:
    """Grades memory claims — memory is not truth, claims are not proof."""

    def grade(self, claims: List[Dict[str, Any]], provenance: Provenance) -> Dict[str, Any]:
        graded: List[Dict[str, Any]] = []
        for claim in claims:
            has_evidence = bool(claim.get("evidence"))
            has_receipt = bool(claim.get("receipt"))
            has_delta = bool(claim.get("delta_proof"))
            corroborated = bool(claim.get("corroborating_evidence"))

            if has_receipt and has_delta:
                grade = "verified"
            elif has_evidence and corroborated:
                grade = "supported"
            elif has_evidence:
                grade = "plausible"
            else:
                grade = "unverified"

            truth_score = 0.0
            if has_receipt:
                truth_score += 40
            if has_delta:
                truth_score += 30
            if has_evidence:
                truth_score += 20
            if corroborated:
                truth_score += 10

            graded.append({
                "claim_id": claim.get("claim_id", str(uuid.uuid4())),
                "claim_summary": claim.get("summary", ""),
                "grade": grade,
                "truth_score": truth_score,
                "has_evidence": has_evidence,
                "has_receipt": has_receipt,
                "has_delta": has_delta,
            })

        verified_count = sum(1 for g in graded if g["grade"] == "verified")
        supported_count = sum(1 for g in graded if g["grade"] == "supported")
        unverified_count = sum(1 for g in graded if g["grade"] == "unverified")

        return {
            "total_claims": len(claims),
            "verified": verified_count,
            "supported": supported_count,
            "plausible": sum(1 for g in graded if g["grade"] == "plausible"),
            "unverified": unverified_count,
            "graded_claims": graded,
            "doctrine": "Memory is not truth. A claim is not proof.",
        }


class PreRevenueValuator:
    """Estimates pre-revenue valuation from latent signals."""

    def value(self, payload: Dict[str, Any], market_context: MarketContext) -> Dict[str, Any]:
        proof_score = payload.get("proof_strength", 0)
        deployment_readiness = payload.get("deployment_readiness", 0)
        market_demand = payload.get("market_demand_signal", 0)
        gap_liquidity = payload.get("gap_liquidity_score", 0)
        breakage_value = payload.get("breakage_value_leak", 0)

        composite = (
            proof_score * 0.30
            + deployment_readiness * 0.25
            + market_demand * 0.20
            + gap_liquidity * 0.15
            + min(100, breakage_value / 10) * 0.10
        )

        if market_context.purpose == MarketPurpose.saas_opportunity:
            multipliers = {"low": 1000, "mid": 10000, "high": 100000}
        elif market_context.purpose == MarketPurpose.eval_dataset:
            multipliers = {"low": 100, "mid": 1000, "high": 10000}
        elif market_context.purpose == MarketPurpose.grant:
            multipliers = {"low": 500, "mid": 5000, "high": 50000}
        else:
            multipliers = {"low": 200, "mid": 2000, "high": 20000}

        return {
            "pre_revenue_composite_score": round(composite, 1),
            "estimated_valuation_usd": {
                "low": round(composite * multipliers["low"] / 100, 2),
                "mid": round(composite * multipliers["mid"] / 100, 2),
                "high": round(composite * multipliers["high"] / 100, 2),
            },
            "components": {
                "proof_strength": proof_score,
                "deployment_readiness": deployment_readiness,
                "market_demand": market_demand,
                "gap_liquidity": gap_liquidity,
                "breakage_value": breakage_value,
            },
            "market_purpose": market_context.purpose.value,
        }


class MonetizationRouter:
    """Routes latent value signals to monetization pathways."""

    def route(self, payload: Dict[str, Any], market_context: MarketContext) -> Dict[str, Any]:
        liquidity = payload.get("liquidity_score", 0)
        signal_type = payload.get("signal_type", "software_artifact")

        routes: List[Dict[str, Any]] = []

        if liquidity >= 20:
            routes.append({"route": "valuation", "fit": "low", "description": "Baseline asset valuation"})
        if liquidity >= 40:
            routes.append({"route": "licensing", "fit": "medium", "description": "License the artifact or protocol"})
            routes.append({"route": "advisory", "fit": "medium", "description": "Advisory or consulting engagement"})
        if liquidity >= 60:
            routes.append({"route": "SaaS_opportunity", "fit": "high", "description": "Productize as SaaS"})
            routes.append({"route": "grant", "fit": "high", "description": "Research or development grant"})
        if liquidity >= 80:
            routes.append({"route": "acquisition_target", "fit": "high", "description": "Position for acquisition"})
            routes.append({"route": "revenue_share", "fit": "high", "description": "Revenue-sharing partnership"})

        if signal_type == "academic_credential":
            routes = [r for r in routes if r["route"] not in ("SaaS_opportunity", "acquisition_target")]
            if liquidity >= 40:
                routes.append({"route": "scholarship_pool", "fit": "high", "description": "Scholarship matching"})
            if liquidity >= 60:
                routes.append({"route": "prediction_settled_pool", "fit": "high", "description": "Peer-backed academic prediction"})

        return {
            "liquidity_score": liquidity,
            "routes": routes,
            "market_purpose": market_context.purpose.value,
            "best_route": routes[-1]["route"] if routes else "none",
        }
