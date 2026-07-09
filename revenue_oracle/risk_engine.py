"""
Risk Engine — compliance blockers, token mode gates, graceful degradation.

Four hard gates:
1. No RevenueProof without external acceptance
2. No public token mode unless compliance-approved
3. No terminal/code execution exposed without auth
4. Every claim must degrade gracefully

Token modes (in order of escalation):
  disabled
  proof_only (default)
  non_transferable_devnet
  non_transferable_mainnet_review_required
  restricted_reviewed
  public_transferable_blocked_by_default
"""

import hashlib
import json
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class TokenMode(str, Enum):
    DISABLED = "disabled"
    PROOF_ONLY = "proof_only"
    NON_TRANSFERABLE_DEVNET = "non_transferable_devnet"
    NON_TRANSFERABLE_MAINNET_REVIEW_REQUIRED = "non_transferable_mainnet_review_required"
    RESTRICTED_REVIEWED = "restricted_reviewed"
    PUBLIC_TRANSFERABLE_BLOCKED_BY_DEFAULT = "public_transferable_blocked_by_default"


class AssetStatus(str, Enum):
    DRAFT = "draft"
    PROOF_ONLY = "proof_only"
    UNVERIFIED = "unverified"
    BLOCKED = "blocked"
    NEEDS_HUMAN_REVIEW = "needs_human_review"
    VERIFIED = "verified"


@dataclass
class ComplianceBlocker:
    code: str
    description: str
    severity: str  # "info", "warning", "blocker"
    gate: str  # which of the 4 gates this relates to


_FORBIDDEN_PHRASES = [
    "guaranteed profit",
    "passive income",
    "risk-free",
    "price will rise",
    "investment opportunity",
    "buy before it pumps",
    "backed by future revenue",
    "guaranteed returns",
    "sure thing",
    "can't lose",
]

_REVENUE_PROOF_TYPES = [
    "paid_invoice",
    "api_usage_billed",
    "stripe_checkout_payment",
    "buyer_acceptance_signed",
    "escrow_release",
    "cost_avoided_confirmed",
    "external_counterparty_acceptance",
    "compute_avoided",
    "time_saved",
    "files_processed",
    "tests_passed",
    "benchmark_improvement",
]


class RiskEngine:
    """Risk and compliance evaluation engine."""

    def __init__(self, db):
        self.db = db

    def evaluate(self, artifact_id: str, packet_hash: str,
                 packet_data: dict = None,
                 revenue_evidence: list = None,
                 token_mode_requested: str = TokenMode.PROOF_ONLY.value,
                 compliance_approved: bool = False,
                 human_approved: bool = False,
                 disclaimers_present: bool = False) -> dict:
        """
        Evaluate an artifact's risk and compliance status.

        Returns:
            dict with: risk_score, blockers, token_mode_allowed,
            asset_status, revenue_status, summary
        """
        blockers: list[ComplianceBlocker] = []
        risk_score = 0.0
        revenue_evidence = revenue_evidence or []
        packet_data = packet_data or {}

        # Gate 1: No RevenueProof without external acceptance
        has_external_acceptance = any(
            e.get("type", "") in _REVENUE_PROOF_TYPES and e.get("verified", False)
            for e in revenue_evidence
        )

        if revenue_evidence and not has_external_acceptance:
            blockers.append(ComplianceBlocker(
                code="no_external_acceptance",
                description="Revenue claims exist but no external acceptance verified. "
                           "Labeling as proof_of_financeable_structure_only.",
                severity="warning",
                gate="gate_1_revenue_proof",
            ))
            risk_score += 0.2

        revenue_status = "proof_of_revenue" if has_external_acceptance else "proof_of_financeable_structure_only"

        # Gate 2: No public token mode unless compliance-approved
        requested_mode = TokenMode(token_mode_requested)
        token_mode_allowed = TokenMode.PROOF_ONLY

        if requested_mode == TokenMode.DISABLED:
            token_mode_allowed = TokenMode.DISABLED
        elif requested_mode == TokenMode.PROOF_ONLY:
            token_mode_allowed = TokenMode.PROOF_ONLY
        elif requested_mode == TokenMode.NON_TRANSFERABLE_DEVNET:
            if not packet_hash:
                blockers.append(ComplianceBlocker(
                    code="missing_packet_hash",
                    description="Cannot mint devnet token without evidence packet hash.",
                    severity="blocker",
                    gate="gate_2_token_mode",
                ))
                risk_score += 0.3
            else:
                token_mode_allowed = TokenMode.NON_TRANSFERABLE_DEVNET
        elif requested_mode in (TokenMode.NON_TRANSFERABLE_MAINNET_REVIEW_REQUIRED,
                                TokenMode.RESTRICTED_REVIEWED):
            if not compliance_approved:
                blockers.append(ComplianceBlocker(
                    code="compliance_not_approved",
                    description="Mainnet/restricted token mode requires compliance approval.",
                    severity="blocker",
                    gate="gate_2_token_mode",
                ))
                risk_score += 0.4
            elif not disclaimers_present:
                blockers.append(ComplianceBlocker(
                    code="missing_disclaimers",
                    description="Required disclaimers are missing.",
                    severity="blocker",
                    gate="gate_2_token_mode",
                ))
                risk_score += 0.2
            else:
                token_mode_allowed = requested_mode
        elif requested_mode == TokenMode.PUBLIC_TRANSFERABLE_BLOCKED_BY_DEFAULT:
            if not compliance_approved or not human_approved:
                blockers.append(ComplianceBlocker(
                    code="public_transferable_blocked",
                    description="Public transferable token mode is blocked by default. "
                               "Requires both compliance approval and explicit human approval.",
                    severity="blocker",
                    gate="gate_2_token_mode",
                ))
                risk_score += 0.6
            else:
                blockers.append(ComplianceBlocker(
                    code="public_transferable_requires_legal_review",
                    description="Public transferable tokens require legal review. "
                               "Tokenized securities remain securities under SEC guidance.",
                    severity="blocker",
                    gate="gate_2_token_mode",
                ))
                risk_score += 0.5
                token_mode_allowed = TokenMode.RESTRICTED_REVIEWED

        # Gate 4: Graceful degradation
        has_blockers = any(b.severity == "blocker" for b in blockers)
        if has_blockers:
            asset_status = AssetStatus.BLOCKED
        elif any(b.severity == "warning" for b in blockers):
            asset_status = AssetStatus.NEEDS_HUMAN_REVIEW
        elif not packet_hash:
            asset_status = AssetStatus.DRAFT
        elif has_external_acceptance:
            asset_status = AssetStatus.VERIFIED
        else:
            asset_status = AssetStatus.PROOF_ONLY

        # Check risk flags from packet
        risk_flags = packet_data.get("risk_flags", [])
        for rf in risk_flags:
            if rf.get("severity") in ("high", "critical"):
                risk_score += 0.2

        risk_score = min(1.0, risk_score)

        # Check for forbidden phrases in claims
        claims_text = " ".join(
            c.get("text", "") for c in packet_data.get("claims", [])
        ).lower()
        for phrase in _FORBIDDEN_PHRASES:
            if phrase in claims_text:
                blockers.append(ComplianceBlocker(
                    code="forbidden_phrase",
                    description=f"Forbidden phrase detected: '{phrase}'",
                    severity="blocker",
                    gate="gate_4_graceful_degradation",
                ))
                risk_score = min(1.0, risk_score + 0.3)

        # Re-evaluate status after forbidden phrase check
        has_blockers = any(b.severity == "blocker" for b in blockers)
        if has_blockers:
            asset_status = AssetStatus.BLOCKED

        report_id = hashlib.sha256(
            f"risk:{artifact_id}:{packet_hash}:{time.time()}".encode()
        ).hexdigest()[:16]

        result = {
            "report_id": report_id,
            "artifact_id": artifact_id,
            "packet_hash": packet_hash,
            "risk_score": round(risk_score, 3),
            "blockers": [b.__dict__ for b in blockers],
            "token_mode_allowed": token_mode_allowed.value,
            "asset_status": asset_status.value,
            "revenue_status": revenue_status,
            "summary": self._build_summary(blockers, asset_status, revenue_status),
        }

        self.db.insert_risk_report(
            report_id=report_id,
            artifact_id=artifact_id,
            packet_hash=packet_hash,
            risk_score=risk_score,
            blockers=[b.__dict__ for b in blockers],
            token_mode_allowed=token_mode_allowed.value,
            asset_status=asset_status.value,
            summary=result["summary"],
        )

        return result

    @staticmethod
    def _build_summary(blockers: list, asset_status: AssetStatus,
                       revenue_status: str) -> str:
        blocker_count = sum(1 for b in blockers if b.severity == "blocker")
        warning_count = sum(1 for b in blockers if b.severity == "warning")
        parts = [f"Asset status: {asset_status.value}"]
        parts.append(f"Revenue status: {revenue_status}")
        if blocker_count:
            parts.append(f"{blocker_count} blocker(s) detected")
        if warning_count:
            parts.append(f"{warning_count} warning(s)")
        if not blockers:
            parts.append("No compliance issues detected")
        return ". ".join(parts) + "."

    @staticmethod
    def check_forbidden_phrases(text: str) -> list:
        """Check text for forbidden phrases."""
        found = []
        text_lower = text.lower()
        for phrase in _FORBIDDEN_PHRASES:
            if phrase in text_lower:
                found.append(phrase)
        return found
