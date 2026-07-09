"""LatentOS EDU — Academic Performance Liquidity vertical.

Applies the LatentOS doctrine to verified academic performance with
privacy-preserving credential boundaries.

Core primitive:
    student work / grade event / credential / proof-of-scholarship profile
    -> value leak -> scored academic liquidity endpoint
    -> scholarship, credit, staking, prediction, or opportunity settlement

Doctrine: liquidify academic progress, not academic privacy.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from .models import (
    MarketPurpose,
    DisclosureMode,
    Provenance,
    PrivacyConfig,
)


def _receipt_hash(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def _now() -> str:
    return datetime.now().isoformat()


class CredentialVerifier:
    """Verifies academic credentials using the W3C VC issuer-holder-verifier model."""

    REQUIRED_FIELDS = {"issuer", "credential_subject", "issuance_date", "type"}

    def verify(self, credential: Dict[str, Any], issuer_did: Optional[str] = None) -> Dict[str, Any]:
        issues: List[str] = []
        verified_fields: List[str] = []

        missing = self.REQUIRED_FIELDS - set(credential.keys())
        if missing:
            issues.extend(f"missing_field:{f}" for f in missing)

        if issuer_did and credential.get("issuer", {}).get("id", "") != issuer_did:
            issues.append("issuer_did_mismatch")

        if credential.get("credential_status", {}).get("type") == "RevocationList2020":
            if credential.get("credential_status", {}).get("revoked"):
                issues.append("credential_revoked")
            else:
                verified_fields.append("credential_status_active")

        if credential.get("proof", {}).get("type"):
            verified_fields.append("issuer_signature_present")
        else:
            issues.append("missing_issuer_signature")

        if credential.get("evidence"):
            verified_fields.append("evidence_linked")
        else:
            issues.append("no_evidence_linked")

        if credential.get("expiration_date"):
            exp = credential["expiration_date"]
            if exp < datetime.now().isoformat():
                issues.append("credential_expired")

        is_valid = len(issues) == 0 or all("missing_field" not in i and "revoked" not in i and "expired" not in i and "missing_issuer" not in i for i in issues)

        return {
            "valid": is_valid,
            "issues": issues,
            "verified_fields": verified_fields,
            "credential_type": credential.get("type", "unknown"),
            "issuer": credential.get("issuer", {}).get("id", "unknown"),
            "has_evidence": bool(credential.get("evidence")),
            "has_proof": bool(credential.get("proof")),
        }


class ProofOfScholarshipScorer:
    """Computes the Proof-of-Scholarship score — the collateral object for EDU.

    Weights:
        0.20 Verified Academic Claims
        0.16 Issuer Trust
        0.14 Credential Status
        0.12 Completion Trajectory
        0.10 Skill Scarcity
        0.10 Evidence Quality
        0.08 Prediction Settlement History
        0.06 Counterparty Acceptance
        0.04 Privacy Minimization
    """

    WEIGHTS = {
        "verified_academic_claims": 0.20,
        "issuer_trust": 0.16,
        "credential_status": 0.14,
        "completion_trajectory": 0.12,
        "skill_scarcity": 0.10,
        "evidence_quality": 0.10,
        "prediction_settlement_history": 0.08,
        "counterparty_acceptance": 0.06,
        "privacy_minimization": 0.04,
    }

    def score(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        components = {}

        claims = profile.get("verified_claims", [])
        verified = [c for c in claims if c.get("verified")]
        components["verified_academic_claims"] = min(100, len(verified) * 20) if claims else 0

        issuer_trust = profile.get("issuer_trust_score", 0)
        components["issuer_trust"] = min(100, issuer_trust)

        active_creds = sum(1 for c in profile.get("credentials", []) if c.get("status") == "active")
        total_creds = max(1, len(profile.get("credentials", [])))
        components["credential_status"] = (active_creds / total_creds) * 100 if total_creds > 0 else 0

        trajectory = profile.get("improvement_trajectory", [])
        if len(trajectory) >= 2:
            deltas = [trajectory[i+1] - trajectory[i] for i in range(len(trajectory)-1)]
            avg_delta = sum(deltas) / len(deltas)
            components["completion_trajectory"] = min(100, max(0, 50 + avg_delta * 10))
        else:
            components["completion_trajectory"] = 30 if trajectory else 0

        components["skill_scarcity"] = min(100, profile.get("skill_scarcity_score", 20))

        evidence = profile.get("evidence_links", [])
        components["evidence_quality"] = min(100, len(evidence) * 25) if evidence else 0

        settlements = profile.get("prediction_settlement_history", [])
        settled = sum(1 for s in settlements if s.get("status") == "settled")
        components["prediction_settlement_history"] = min(100, settled * 25) if settlements else 0

        components["counterparty_acceptance"] = min(100, profile.get("counterparty_acceptance_score", 10))

        privacy_perms = profile.get("privacy_permissions", {})
        if privacy_perms.get("disclosure_mode") == "minimal":
            components["privacy_minimization"] = 100
        elif privacy_perms.get("disclosure_mode") == "threshold_only":
            components["privacy_minimization"] = 75
        elif privacy_perms.get("disclosure_mode") == "settlement_only":
            components["privacy_minimization"] = 50
        else:
            components["privacy_minimization"] = 25

        total = sum(components[k] * self.WEIGHTS[k] for k in self.WEIGHTS)

        return {
            "proof_of_scholarship_score": round(total, 1),
            "components": {k: round(v, 1) for k, v in components.items()},
            "weights": self.WEIGHTS,
        }


class AcademicLiquidityScorer:
    """Computes the Academic Liquidity Score.

    SACV = Verified Performance × Completion Probability × Skill Scarcity
          × Counterparty Acceptance × Institution Trust × Improvement Trajectory
          × Time-to-Outcome Discount
          - Privacy Risk - Fraud Risk - Dropout Risk - Compliance Risk
    """

    def score(self, profile: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        verified_performance = profile.get("verified_performance_score", 50)
        completion_probability = profile.get("completion_probability", 0.7)
        skill_scarcity = profile.get("skill_scarcity_score", 30) / 100
        counterparty_acceptance = profile.get("counterparty_acceptance_score", 20) / 100
        institution_trust = profile.get("issuer_trust_score", 50) / 100
        improvement_trajectory = profile.get("improvement_trajectory_score", 0.5)
        time_to_outcome_discount = profile.get("time_to_outcome_discount", 0.8)

        gross = (
            verified_performance
            * completion_probability
            * skill_scarcity
            * counterparty_acceptance
            * institution_trust
            * improvement_trajectory
            * time_to_outcome_discount
        )

        privacy_risk = self._privacy_risk(profile, context)
        fraud_risk = self._fraud_risk(profile)
        dropout_risk = self._dropout_risk(profile)
        compliance_risk = self._compliance_risk(profile, context)

        net = max(0, gross * 100 - privacy_risk - fraud_risk - dropout_risk - compliance_risk)

        return {
            "academic_liquidity_score": round(net, 1),
            "gross_score": round(gross * 100, 1),
            "verified_performance": verified_performance,
            "completion_probability": completion_probability,
            "skill_scarcity": skill_scarcity * 100,
            "counterparty_acceptance": counterparty_acceptance * 100,
            "institution_trust": institution_trust * 100,
            "improvement_trajectory": improvement_trajectory * 100,
            "time_to_outcome_discount": time_to_outcome_discount,
            "privacy_risk": round(privacy_risk, 1),
            "fraud_risk": round(fraud_risk, 1),
            "dropout_risk": round(dropout_risk, 1),
            "compliance_risk": round(compliance_risk, 1),
        }

    def _privacy_risk(self, profile: Dict[str, Any], context: Dict[str, Any]) -> float:
        risk = 0.0
        perms = profile.get("privacy_permissions", {})
        if perms.get("reveal_raw_grade"):
            risk += 30
        if perms.get("reveal_transcript"):
            risk += 25
        if perms.get("reveal_identity") == "full":
            risk += 20
        if not perms.get("student_consent"):
            risk += 35
        if context.get("jurisdiction") == "US" and not perms.get("ferpa_compliant"):
            risk += 20
        return min(100, risk)

    def _fraud_risk(self, profile: Dict[str, Any]) -> float:
        risk = 0.0
        creds = profile.get("credentials", [])
        if not creds:
            risk += 30
        if any(c.get("status") == "revoked" for c in creds):
            risk += 40
        if profile.get("self_claimed_only"):
            risk += 25
        if profile.get("coerced_consent"):
            risk += 35
        return min(100, risk)

    def _dropout_risk(self, profile: Dict[str, Any]) -> float:
        risk = 0.0
        completion = profile.get("completion_probability", 0.7)
        risk += (1 - completion) * 60
        if not profile.get("improvement_trajectory"):
            risk += 20
        if profile.get("attendance_signal", 0.8) < 0.5:
            risk += 20
        return min(100, risk)

    def _compliance_risk(self, profile: Dict[str, Any], context: Dict[str, Any]) -> float:
        risk = 0.0
        if profile.get("minor_record") and not profile.get("parental_consent"):
            risk += 40
        use_case = context.get("use_case", "")
        if use_case in ("prediction", "credit") and not profile.get("consent_for_market_use"):
            risk += 25
        if context.get("jurisdiction") == "US" and not profile.get("ferpa_compliant"):
            risk += 20
        return min(100, risk)


class EduMintCapCalculator:
    """Calculates the EDU mint capacity from verified evidence.

    EDU Mint Cap = f(
        verified credits, grade band, course difficulty,
        institution trust, improvement trajectory,
        attendance/completion signal, credential freshness,
        counterparty demand, risk haircut
    )
    """

    BASE_MINT_PER_CREDIT = 100

    def calculate(self, pos_score: float, credential_count: int, issuer_trust: float) -> Dict[str, Any]:
        base = credential_count * self.BASE_MINT_PER_CREDIT
        trust_multiplier = 0.5 + issuer_trust
        pos_multiplier = pos_score / 100.0

        risk_haircut = 0.0
        if pos_score < 30:
            risk_haircut = 0.5
        elif pos_score < 50:
            risk_haircut = 0.3
        elif pos_score < 70:
            risk_haircut = 0.15

        mint_cap = base * trust_multiplier * pos_multiplier * (1 - risk_haircut)

        return {
            "edu_mint_cap": round(mint_cap, 2),
            "base_credits": credential_count,
            "base_mint": base,
            "trust_multiplier": round(trust_multiplier, 2),
            "pos_multiplier": round(pos_multiplier, 2),
            "risk_haircut": round(risk_haircut, 2),
            "formula": "base * trust_multiplier * pos_multiplier * (1 - risk_haircut)",
        }


class AcademicPredictionEngine:
    """Manages academic prediction quotes and settlement."""

    def __init__(self):
        self._predictions: Dict[str, Dict[str, Any]] = {}

    def quote(
        self,
        credential: Dict[str, Any],
        outcome: str,
        stake_amount: float,
        pos_score: float,
    ) -> Dict[str, Any]:
        prediction_id = str(uuid.uuid4())

        confidence = pos_score / 100.0
        risk_adjusted_stake = stake_amount * confidence
        potential_payout = stake_amount * (1 + (1 - confidence) * 2)

        prediction = {
            "prediction_id": prediction_id,
            "outcome": outcome,
            "stake_amount": stake_amount,
            "confidence": round(confidence, 2),
            "risk_adjusted_stake": round(risk_adjusted_stake, 2),
            "potential_payout": round(potential_payout, 2),
            "pos_score": pos_score,
            "status": "open",
            "created_at": _now(),
        }
        self._predictions[prediction_id] = prediction

        return prediction

    def settle(self, prediction_id: str, outcome_achieved: bool, evidence: Dict[str, Any]) -> Dict[str, Any]:
        pred = self._predictions.get(prediction_id)
        if not pred:
            return {"error": "prediction_not_found", "prediction_id": prediction_id}

        pred["status"] = "settled"
        pred["outcome_achieved"] = outcome_achieved
        pred["settled_at"] = _now()
        pred["settlement_evidence"] = evidence

        if outcome_achieved:
            pred["settlement_amount"] = pred["potential_payout"]
        else:
            pred["settlement_amount"] = 0.0
            pred["forfeit_amount"] = pred["stake_amount"]

        pred["receipt_hash"] = _receipt_hash(pred)

        return pred


class AntiZKArrow:
    """AntiZK/ARROW — reveal the minimum receipt needed to settle value
    without exposing the full private source record.

    For software: do not expose all private chats, repo secrets, or internal reasoning.
    For academic: do not expose raw grades, transcripts, or protected student records.
    """

    BLOCKED_FIELDS_ACADEMIC = {
        "raw_grade", "transcript", "student_name", "student_ssn",
        "student_email", "student_phone", "parent_name", "home_address",
    }

    BLOCKED_FIELDS_SOFTWARE = {
        "source_code", "secrets", "api_keys", "internal_reasoning",
        "private_chat", "env_vars", "credentials",
    }

    def minimize_disclosure(
        self,
        credential: Dict[str, Any],
        purpose: MarketPurpose,
        disclosure_mode: DisclosureMode,
    ) -> Dict[str, Any]:
        allowed: Dict[str, Any] = {}
        blocked: List[str] = []

        all_blocked = self.BLOCKED_FIELDS_ACADEMIC | self.BLOCKED_FIELDS_SOFTWARE

        for key, value in credential.items():
            if key in all_blocked:
                blocked.append(key)
                continue

            if disclosure_mode == DisclosureMode.minimal:
                if key in ("grade_band", "credential_type", "issuer_id", "completion_status", "skill_tag"):
                    allowed[key] = value
                else:
                    blocked.append(key)
            elif disclosure_mode == DisclosureMode.threshold_only:
                if key in ("grade_band", "credential_type", "issuer_id", "completion_status",
                          "skill_tag", "course_difficulty", "institution_name"):
                    allowed[key] = value
                else:
                    blocked.append(key)
            elif disclosure_mode == DisclosureMode.settlement_only:
                if key in ("grade_band", "credential_type", "issuer_id", "completion_status",
                          "settlement_amount", "liquidity_score"):
                    allowed[key] = value
                else:
                    blocked.append(key)
            elif disclosure_mode == DisclosureMode.full_with_consent:
                if credential.get("student_consent") or credential.get("owner_consent"):
                    allowed[key] = value
                else:
                    blocked.append(key)

        return {
            "allowed_disclosure": allowed,
            "blocked_disclosure": blocked,
            "disclosure_mode": disclosure_mode.value,
            "purpose": purpose.value,
            "fields_revealed": len(allowed),
            "fields_blocked": len(blocked),
            "doctrine": "Reveal the minimum receipt needed to settle value.",
        }

    def privacy_grade(self, profile: Dict[str, Any]) -> Dict[str, Any]:
        perms = profile.get("privacy_permissions", {})
        score = 100

        if perms.get("reveal_raw_grade"):
            score -= 35
        if perms.get("reveal_transcript"):
            score -= 30
        if perms.get("reveal_identity") == "full":
            score -= 25
        if not perms.get("student_consent"):
            score -= 40
        if profile.get("minor_record") and not perms.get("parental_consent"):
            score -= 50

        score = max(0, score)

        grade = "A" if score >= 80 else "B" if score >= 60 else "C" if score >= 40 else "D" if score >= 20 else "F"

        return {
            "privacy_grade": grade,
            "privacy_score": score,
            "violations": [k for k, v in perms.items() if v is True and k.startswith("reveal_") and k != "reveal_grade_band"],
            "doctrine": "A grade is private. A credential is permissioned.",
        }


class AcademicLiquidityEngine:
    """Unified academic liquidity engine — combines all EDU components."""

    def __init__(self):
        self.credential_verifier = CredentialVerifier()
        self.pos_scorer = ProofOfScholarshipScorer()
        self.liquidity_scorer = AcademicLiquidityScorer()
        self.mint_calculator = EduMintCapCalculator()
        self.prediction_engine = AcademicPredictionEngine()
        self.arrow = AntiZKArrow()

    def liquidify(
        self,
        credential: Dict[str, Any],
        student_permissions: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        verification = self.credential_verifier.verify(credential)

        profile = {
            "credentials": [credential],
            "verified_claims": credential.get("verified_claims", []),
            "evidence_links": credential.get("evidence", []),
            "improvement_trajectory": credential.get("improvement_trajectory", []),
            "prediction_settlement_history": credential.get("prediction_settlement_history", []),
            "privacy_permissions": student_permissions,
            "issuer_trust_score": credential.get("issuer_trust_score", 50),
            "skill_scarcity_score": credential.get("skill_scarcity_score", 30),
            "counterparty_acceptance_score": credential.get("counterparty_acceptance_score", 20),
            "verified_performance_score": credential.get("verified_performance_score", 50),
            "completion_probability": credential.get("completion_probability", 0.7),
            "improvement_trajectory_score": credential.get("improvement_trajectory_score", 0.5),
            "time_to_outcome_discount": credential.get("time_to_outcome_discount", 0.8),
            "attendance_signal": credential.get("attendance_signal", 0.8),
            "minor_record": credential.get("minor_record", False),
            "parental_consent": credential.get("parental_consent", False),
            "ferpa_compliant": student_permissions.get("ferpa_compliant", False),
            "consent_for_market_use": student_permissions.get("consent_for_market_use", False),
            "self_claimed_only": not verification.get("has_proof"),
            "coerced_consent": student_permissions.get("coerced", False),
        }

        pos_result = self.pos_scorer.score(profile)
        liquidity_result = self.liquidity_scorer.score(profile, context)
        mint_result = self.mint_calculator.calculate(
            pos_result["proof_of_scholarship_score"],
            len(profile["credentials"]),
            profile["issuer_trust_score"] / 100,
        )
        privacy_result = self.arrow.privacy_grade(profile)

        routes: List[str] = ["scholarship_pool"]
        if liquidity_result["academic_liquidity_score"] >= 40:
            routes.extend(["conditional_advance", "employer_bounty"])
        if liquidity_result["academic_liquidity_score"] >= 60:
            routes.extend(["peer_backed_education_funding", "prediction_settled_academic_pool"])
        if liquidity_result["academic_liquidity_score"] >= 80:
            routes.append("credit_line")

        required_proofs: List[str] = []
        if not verification.get("has_proof"):
            required_proofs.append("issuer_signature")
        if not verification.get("has_evidence"):
            required_proofs.append("evidence_link")
        if not student_permissions.get("student_consent"):
            required_proofs.append("student_consent")
        if not credential.get("grade_band") and not credential.get("verified_claims"):
            required_proofs.append("grade_band_claim")
        if not credential.get("completion_status"):
            required_proofs.append("course_completion_claim")

        receipt = {
            "schema": "membra.latentos.edu.liquidify_receipt.v1",
            "receipt_id": str(uuid.uuid4()),
            "timestamp": _now(),
            "credential_type": credential.get("type", "unknown"),
            "issuer": credential.get("issuer", {}).get("id", "unknown"),
            "credential_verified": verification["valid"],
            "proof_of_scholarship_score": pos_result["proof_of_scholarship_score"],
            "academic_liquidity_score": liquidity_result["academic_liquidity_score"],
            "edu_mint_cap": mint_result["edu_mint_cap"],
            "privacy_grade": privacy_result["privacy_grade"],
            "routes": routes,
        }
        receipt["receipt_hash"] = _receipt_hash(receipt)

        return {
            "academic_liquidity_score": liquidity_result["academic_liquidity_score"],
            "proof_of_scholarship_score": pos_result["proof_of_scholarship_score"],
            "issuer_trust_score": profile["issuer_trust_score"],
            "privacy_risk_score": liquidity_result["privacy_risk"],
            "fraud_risk_score": liquidity_result["fraud_risk"],
            "dropout_risk_score": liquidity_result["dropout_risk"],
            "compliance_risk_score": liquidity_result["compliance_risk"],
            "edu_mint_cap": mint_result["edu_mint_cap"],
            "recommended_routes": routes,
            "required_proofs": required_proofs,
            "privacy_grade": privacy_result["privacy_grade"],
            "credential_verification": verification,
            "pos_components": pos_result["components"],
            "receipt": receipt,
        }
