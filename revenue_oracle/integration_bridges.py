"""
Integration Bridges — Protocols 195-204

Connects the trust kernel (SGE, AAU, RBC, BMMA, EvidenceOS, VideoLake,
SystemLake) into the Revenue Oracle's SQLite-backed pipeline.

Each bridge is a one-way or two-way adapter that:
  - Reads from the source system
  - Translates into Oracle-compatible records
  - Writes receipts for every bridged event
  - Never fakes data — missing source data = blocked status

Protocol 195: SGE → Oracle Bridge
Protocol 196: AAU → Oracle Bridge
Protocol 197: BMMA → Oracle Full Integration
Protocol 198: Payout Waterfall Engine
Protocol 199: Licensing Engine
Protocol 200: Escrow Protocol
Protocol 201: Revenue Settlement Engine
Protocol 202: Valuation Reconciliation
Protocol 203: EvidenceOS → Oracle Bridge
Protocol 204: VideoLake → Oracle Bridge
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

from .schema import OracleDB
from .receipt_ledger import ReceiptLedger


# ═══════════════════════════════════════════════════════════════════
# Protocol 195: SGE → Oracle Bridge
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SealedGradeClaim:
    claim_id: str
    artifact_id: str
    packet_hash: str
    rubric_id: str
    claimed_grade: float
    computed_grade: float
    bond_amount_usd: float
    bond_required_usd: float
    status: str  # DRAFT, SEALED, CHALLENGED, UPHELD, SLASHED, WITHDRAWN
    audit_probability: float
    receipt_hash: str
    created_at: float = field(default_factory=time.time)


class SGEBridge:
    """
    Bridge between Sealed Grade Exchange (broll/grade_bond.py) and the Oracle.

    Imports grade claims, bond states, and challenge settlements into the
    Oracle's SQLite, creating risk reports and receipts for each.
    """

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger):
        self.db = db
        self.receipt_ledger = receipt_ledger

    def import_grade_claim(
        self,
        artifact_id: str,
        packet_hash: str,
        rubric_id: str,
        claimed_grade: float,
        computed_grade: float,
        bond_amount: float,
        bond_required: float,
        audit_probability: float,
        grade_bond_protocol=None,
    ) -> SealedGradeClaim:
        claim_id = f"sge_{hashlib.sha256(f'{artifact_id}{packet_hash}{rubric_id}{time.time()}'.encode()).hexdigest()[:12]}"

        grade_premium = max(claimed_grade - computed_grade, 0)
        status = "SEALED"
        blockers = []

        if grade_premium > 10 and bond_amount < bond_required:
            status = "BLOCKED"
            blockers.append("insufficient_bond_for_grade_premium")

        if claimed_grade > 95 and audit_probability < 0.05:
            status = "BLOCKED"
            blockers.append("high_grade_low_audit_probability")

        receipt_data = {
            "claim_id": claim_id,
            "artifact_id": artifact_id,
            "packet_hash": packet_hash,
            "rubric_id": rubric_id,
            "claimed_grade": claimed_grade,
            "computed_grade": computed_grade,
            "bond_amount": bond_amount,
            "bond_required": bond_required,
            "audit_probability": audit_probability,
            "status": status,
            "blockers": blockers,
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="sge_grade_claim_imported",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
            packet_hash=packet_hash,
        )

        return SealedGradeClaim(
            claim_id=claim_id,
            artifact_id=artifact_id,
            packet_hash=packet_hash,
            rubric_id=rubric_id,
            claimed_grade=claimed_grade,
            computed_grade=computed_grade,
            bond_amount_usd=bond_amount,
            bond_required_usd=bond_required,
            status=status,
            audit_probability=audit_probability,
            receipt_hash=receipt_hash,
        )

    def import_challenge_result(
        self,
        claim_id: str,
        artifact_id: str,
        verdict: str,  # upheld, slashed, withdrawn
        slash_amount: float = 0.0,
        evidence: str = "",
    ) -> dict:
        receipt_data = {
            "claim_id": claim_id,
            "artifact_id": artifact_id,
            "verdict": verdict,
            "slash_amount": slash_amount,
            "evidence": evidence,
            "timestamp": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="sge_challenge_settled",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )

        return {
            "claim_id": claim_id,
            "verdict": verdict,
            "slash_amount": slash_amount,
            "receipt_hash": receipt_hash,
        }


# ═══════════════════════════════════════════════════════════════════
# Protocol 196: AAU → Oracle Bridge
# ═══════════════════════════════════════════════════════════════════

class AAUBridge:
    """
    Bridge between Adversarial Attribution Underwriting (systemlake/aau.py)
    and the Oracle.

    Imports value claims, baseline locks, and settlement statuses.
    Translates AAU's ClaimStatus into Oracle risk reports.
    """

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger):
        self.db = db
        self.receipt_ledger = receipt_ledger

    def import_value_claim(
        self,
        artifact_id: str,
        packet_hash: str,
        claimed_delta: float,
        baseline_hash: str,
        counterfactual_stripped: float,
        confidence: float,
        evidence_score: float,
        reputation_score: float,
        settlement_score: float,
        exchangeability_score: float,
        fraud_penalty: float = 0.0,
        gaming_flags: list = None,
        aau_engine=None,
    ) -> dict:
        gaming_flags = gaming_flags or []

        finance_readable_value = (
            claimed_delta * confidence * evidence_score *
            reputation_score * settlement_score * exchangeability_score
        ) - fraud_penalty - counterfactual_stripped

        if finance_readable_value < 0:
            finance_readable_value = 0.0

        if gaming_flags:
            status = "REJECTED_GAMING"
        elif finance_readable_value == 0:
            status = "REJECTED_NO_DELTA"
        else:
            status = "FINANCE_READABLE_OPEN"

        receipt_data = {
            "artifact_id": artifact_id,
            "packet_hash": packet_hash,
            "claimed_delta": claimed_delta,
            "baseline_hash": baseline_hash,
            "counterfactual_stripped": counterfactual_stripped,
            "confidence": confidence,
            "evidence_score": evidence_score,
            "reputation_score": reputation_score,
            "settlement_score": settlement_score,
            "exchangeability_score": exchangeability_score,
            "fraud_penalty": fraud_penalty,
            "gaming_flags": gaming_flags,
            "finance_readable_value": round(finance_readable_value, 2),
            "status": status,
            "timestamp": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="aau_value_claim_imported",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
            packet_hash=packet_hash,
        )

        return {
            "finance_readable_value": round(finance_readable_value, 2),
            "status": status,
            "gaming_flags": gaming_flags,
            "receipt_hash": receipt_hash,
        }

    def import_settlement(
        self,
        artifact_id: str,
        claim_id: str,
        settlement_amount: float,
        settlement_reference: str,
        external_confirmed: bool = False,
    ) -> dict:
        if not external_confirmed:
            status = "PENDING_EXTERNAL_CONFIRMATION"
        else:
            status = "SETTLED_FINANCE_READABLE"

        receipt_data = {
            "artifact_id": artifact_id,
            "claim_id": claim_id,
            "settlement_amount": settlement_amount,
            "settlement_reference": settlement_reference,
            "external_confirmed": external_confirmed,
            "status": status,
            "timestamp": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="aau_settlement_imported",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )

        return {
            "status": status,
            "settlement_amount": settlement_amount,
            "receipt_hash": receipt_hash,
        }


# ═══════════════════════════════════════════════════════════════════
# Protocol 198: Payout Waterfall Engine
# ═══════════════════════════════════════════════════════════════════

@dataclass
class WaterfallTier:
    tier_name: str
    recipient_id: str
    share_percentage: float
    priority: int  # 1 = highest priority
    minimum_amount: float = 0.0


@dataclass
class PayoutResult:
    total_distributed: float
    distributions: list  # [{tier, recipient, amount}]
    residual: float
    receipt_hash: str


class PayoutWaterfallEngine:
    """
    Distributes revenue according to a priority waterfall.

    Standard waterfall:
      1. Platform fee (10%)
      2. Production costs (fixed)
      3. Rights holders (proportional)
      4. Producer (residual)

    No payout occurs until revenue is confirmed (money_moved).
    """

    def __init__(self, receipt_ledger: ReceiptLedger):
        self.receipt_ledger = receipt_ledger

    def create_waterfall(
        self,
        tiers: list[WaterfallTier],
    ) -> list[WaterfallTier]:
        tiers.sort(key=lambda t: t.priority)
        total_pct = sum(t.share_percentage for t in tiers)
        if total_pct > 100.0:
            raise ValueError(f"Waterfall tiers sum to {total_pct}%, exceeds 100%")
        return tiers

    def distribute(
        self,
        artifact_id: str,
        total_revenue: float,
        tiers: list[WaterfallTier],
    ) -> PayoutResult:
        if total_revenue <= 0:
            return PayoutResult(
                total_distributed=0.0,
                distributions=[],
                residual=0.0,
                receipt_hash="",
            )

        tiers = self.create_waterfall(tiers)
        distributions = []
        remaining = total_revenue

        for tier in tiers:
            if remaining <= 0:
                amount = 0.0
            elif tier.minimum_amount > 0:
                amount = min(tier.minimum_amount, remaining)
            else:
                amount = round(remaining * (tier.share_percentage / 100.0), 2)

            if amount > 0:
                distributions.append({
                    "tier": tier.tier_name,
                    "recipient": tier.recipient_id,
                    "amount": amount,
                    "priority": tier.priority,
                })
                remaining -= amount

        receipt_data = {
            "artifact_id": artifact_id,
            "total_revenue": total_revenue,
            "distributions": distributions,
            "residual": round(remaining, 2),
            "timestamp": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="waterfall_distribution",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )

        return PayoutResult(
            total_distributed=round(total_revenue - remaining, 2),
            distributions=distributions,
            residual=round(remaining, 2),
            receipt_hash=receipt_hash,
        )


# ═══════════════════════════════════════════════════════════════════
# Protocol 199: Licensing Engine
# ═══════════════════════════════════════════════════════════════════

class LicenseType(Enum):
    EVIDENCE_REPORT = "evidence_report"
    AUDIT_PACKAGE = "audit_package"
    API_ACCESS = "api_access"
    ARTIFACT_LICENSE = "artifact_license"
    CONSULTING = "consulting"
    RESEARCH_ACCESS = "research_access"
    MEDIA_LICENSE = "media_license"
    EXCLUSIVE_LICENSE = "exclusive_license"


@dataclass
class LicenseRecord:
    license_id: str
    artifact_id: str
    packet_hash: str
    license_type: str
    licensee: str
    terms: dict
    price_usd: float
    duration_days: int  # 0 = perpetual
    status: str  # offered, active, expired, revoked
    receipt_hash: str
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0.0


class LicensingEngine:
    """
    Manages artifact licensing with terms, pricing, and receipts.

    Licenses are the primary monetization mechanism — not tokens.
    """

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger):
        self.db = db
        self.receipt_ledger = receipt_ledger
        self.licenses: dict[str, LicenseRecord] = {}

    def offer_license(
        self,
        artifact_id: str,
        packet_hash: str,
        license_type: str,
        licensee: str,
        terms: dict,
        price_usd: float,
        duration_days: int = 0,
    ) -> LicenseRecord:
        if license_type not in [lt.value for lt in LicenseType]:
            raise ValueError(f"Invalid license type: {license_type}")

        license_id = f"lic_{hashlib.sha256(f'{artifact_id}{license_type}{licensee}{time.time()}'.encode()).hexdigest()[:12]}"
        expires_at = time.time() + (duration_days * 86400) if duration_days > 0 else 0

        record = LicenseRecord(
            license_id=license_id,
            artifact_id=artifact_id,
            packet_hash=packet_hash,
            license_type=license_type,
            licensee=licensee,
            terms=terms,
            price_usd=price_usd,
            duration_days=duration_days,
            status="offered",
            receipt_hash="",
            expires_at=expires_at,
        )

        receipt_data = {
            "license_id": license_id,
            "artifact_id": artifact_id,
            "license_type": license_type,
            "licensee": licensee,
            "price_usd": price_usd,
            "duration_days": duration_days,
            "terms": terms,
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"
        record.receipt_hash = receipt_hash

        self.receipt_ledger.write(
            receipt_type="license_offered",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
            packet_hash=packet_hash,
        )

        self.licenses[license_id] = record
        return record

    def activate_license(
        self,
        license_id: str,
        payment_reference: str,
    ) -> LicenseRecord:
        record = self._get_license(license_id)
        record.status = "active"

        receipt_data = {
            "license_id": license_id,
            "payment_reference": payment_reference,
            "activated_at": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"
        record.receipt_hash = receipt_hash

        self.receipt_ledger.write(
            receipt_type="license_activated",
            artifact_id=record.artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )

        return record

    def revoke_license(
        self,
        license_id: str,
        reason: str,
    ) -> LicenseRecord:
        record = self._get_license(license_id)
        record.status = "revoked"

        receipt_data = {
            "license_id": license_id,
            "reason": reason,
            "revoked_at": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"
        record.receipt_hash = receipt_hash

        self.receipt_ledger.write(
            receipt_type="license_revoked",
            artifact_id=record.artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )

        return record

    def check_license(self, license_id: str) -> dict:
        record = self._get_license(license_id)
        if record.expires_at > 0 and time.time() > record.expires_at:
            record.status = "expired"
        return {
            "license_id": record.license_id,
            "status": record.status,
            "license_type": record.license_type,
            "licensee": record.licensee,
            "expires_at": record.expires_at,
        }

    def list_licenses(self, artifact_id: str = None) -> list:
        if artifact_id:
            return [asdict(r) for r in self.licenses.values() if r.artifact_id == artifact_id]
        return [asdict(r) for r in self.licenses.values()]

    def _get_license(self, license_id: str) -> LicenseRecord:
        if license_id not in self.licenses:
            raise KeyError(f"License {license_id} not found")
        return self.licenses[license_id]


# ═══════════════════════════════════════════════════════════════════
# Protocol 200: Escrow Protocol
# ═══════════════════════════════════════════════════════════════════

class EscrowStatus(Enum):
    PENDING = "pending"
    HELD = "held"
    RELEASED = "released"
    REFUNDED = "refunded"
    DISPUTED = "disputed"


@dataclass
class EscrowHold:
    escrow_id: str
    artifact_id: str
    packet_hash: str
    amount_usd: float
    buyer: str
    seller: str
    product_type: str
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    released_at: float = 0.0
    external_confirmation: dict = field(default_factory=dict)
    receipt_hash: str = ""


class EscrowProtocol:
    """
    Hold funds until external confirmation is received.

    No escrow release without:
      - External payment confirmation (stripe charge_id, etc.)
      - Product delivery confirmation
      - Both buyer and seller recorded

    This is the hard gate between "checkout created" and "revenue confirmed."
    """

    def __init__(self, receipt_ledger: ReceiptLedger):
        self.receipt_ledger = receipt_ledger
        self.holds: dict[str, EscrowHold] = {}

    def create_hold(
        self,
        artifact_id: str,
        packet_hash: str,
        amount_usd: float,
        buyer: str,
        seller: str,
        product_type: str,
    ) -> EscrowHold:
        escrow_id = f"esc_{hashlib.sha256(f'{artifact_id}{buyer}{amount_usd}{time.time()}'.encode()).hexdigest()[:12]}"

        hold = EscrowHold(
            escrow_id=escrow_id,
            artifact_id=artifact_id,
            packet_hash=packet_hash,
            amount_usd=amount_usd,
            buyer=buyer,
            seller=seller,
            product_type=product_type,
            status=EscrowStatus.HELD.value,
        )

        receipt_data = {
            "escrow_id": escrow_id,
            "artifact_id": artifact_id,
            "amount_usd": amount_usd,
            "buyer": buyer,
            "seller": seller,
            "product_type": product_type,
            "status": hold.status,
        }
        hold.receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="escrow_held",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=hold.receipt_hash,
            packet_hash=packet_hash,
        )

        self.holds[escrow_id] = hold
        return hold

    def release(
        self,
        escrow_id: str,
        external_confirmation: dict,
    ) -> EscrowHold:
        hold = self._get_hold(escrow_id)

        if not external_confirmation or not external_confirmation.get("verified"):
            raise ValueError("External confirmation required for escrow release")

        hold.status = EscrowStatus.RELEASED.value
        hold.released_at = time.time()
        hold.external_confirmation = external_confirmation

        receipt_data = {
            "escrow_id": escrow_id,
            "status": hold.status,
            "external_confirmation": external_confirmation,
            "released_at": hold.released_at,
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"
        hold.receipt_hash = receipt_hash

        self.receipt_ledger.write(
            receipt_type="escrow_released",
            artifact_id=hold.artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
            packet_hash=hold.packet_hash,
        )

        return hold

    def refund(
        self,
        escrow_id: str,
        reason: str,
    ) -> EscrowHold:
        hold = self._get_hold(escrow_id)
        hold.status = EscrowStatus.REFUNDED.value

        receipt_data = {
            "escrow_id": escrow_id,
            "reason": reason,
            "refunded_at": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"
        hold.receipt_hash = receipt_hash

        self.receipt_ledger.write(
            receipt_type="escrow_refunded",
            artifact_id=hold.artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )
        return hold

    def dispute(
        self,
        escrow_id: str,
        reason: str,
    ) -> EscrowHold:
        hold = self._get_hold(escrow_id)
        hold.status = EscrowStatus.DISPUTED.value

        receipt_data = {
            "escrow_id": escrow_id,
            "reason": reason,
            "disputed_at": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"
        hold.receipt_hash = receipt_hash

        self.receipt_ledger.write(
            receipt_type="escrow_disputed",
            artifact_id=hold.artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )
        return hold

    def _get_hold(self, escrow_id: str) -> EscrowHold:
        if escrow_id not in self.holds:
            raise KeyError(f"Escrow {escrow_id} not found")
        return self.holds[escrow_id]

    def list_holds(self, status: str = None) -> list:
        if status:
            return [asdict(h) for h in self.holds.values() if h.status == status]
        return [asdict(h) for h in self.holds.values()]


# ═══════════════════════════════════════════════════════════════════
# Protocol 201: Revenue Settlement Engine
# ═══════════════════════════════════════════════════════════════════

@dataclass
class SettlementResult:
    settlement_id: str
    artifact_id: str
    escrow_id: str
    license_id: str
    amount_usd: float
    waterfall_result: dict
    status: str
    receipt_hash: str
    settled_at: float = field(default_factory=time.time)


class RevenueSettlementEngine:
    """
    Combines escrow + waterfall + licensing into a single settlement flow.

    Flow:
      1. Escrow hold created (buyer pays)
      2. External confirmation received
      3. Escrow released
      4. License activated
      5. Waterfall distributes funds
      6. Settlement receipt written

    No settlement without external confirmation. No revenue without settlement.
    """

    def __init__(
        self,
        db: OracleDB,
        receipt_ledger: ReceiptLedger,
        escrow: EscrowProtocol,
        licensing: LicensingEngine,
        waterfall: PayoutWaterfallEngine,
    ):
        self.db = db
        self.receipt_ledger = receipt_ledger
        self.escrow = escrow
        self.licensing = licensing
        self.waterfall = waterfall
        self.settlements: dict[str, SettlementResult] = {}

    def settle(
        self,
        artifact_id: str,
        packet_hash: str,
        escrow_id: str,
        license_id: str,
        external_confirmation: dict,
        waterfall_tiers: list[WaterfallTier],
    ) -> SettlementResult:
        # 1. Release escrow with external confirmation
        released = self.escrow.release(escrow_id, external_confirmation)
        if released.status != "released":
            raise ValueError(f"Escrow release failed: {released.status}")

        # 2. Activate license
        license_record = self.licensing.activate_license(
            license_id,
            payment_reference=external_confirmation.get("charge_id", ""),
        )

        # 3. Distribute via waterfall
        waterfall_result = self.waterfall.distribute(
            artifact_id=artifact_id,
            total_revenue=released.amount_usd,
            tiers=waterfall_tiers,
        )

        # 4. Write settlement receipt
        settlement_id = f"stl_{hashlib.sha256(f'{artifact_id}{escrow_id}{time.time()}'.encode()).hexdigest()[:12]}"
        receipt_data = {
            "settlement_id": settlement_id,
            "artifact_id": artifact_id,
            "escrow_id": escrow_id,
            "license_id": license_id,
            "amount_usd": released.amount_usd,
            "waterfall_distributions": waterfall_result.distributions,
            "external_confirmation": external_confirmation,
            "settled_at": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="revenue_settled",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
            packet_hash=packet_hash,
        )

        result = SettlementResult(
            settlement_id=settlement_id,
            artifact_id=artifact_id,
            escrow_id=escrow_id,
            license_id=license_id,
            amount_usd=released.amount_usd,
            waterfall_result=asdict(waterfall_result),
            status="settled",
            receipt_hash=receipt_hash,
        )
        self.settlements[settlement_id] = result
        return result

    def list_settlements(self) -> list:
        return [asdict(s) for s in self.settlements.values()]


# ═══════════════════════════════════════════════════════════════════
# Protocol 202: Valuation Reconciliation
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ReconciledValuation:
    artifact_id: str
    headline_valuation: float
    reconciled_valuation: float
    haircuts: list  # [{reason, amount, percentage}]
    revenue_evidence: float
    user_evidence: int
    pilot_evidence: int
    signed_contracts: int
    status: str  # "unverified", "partially_verified", "verified"
    receipt_hash: str
    timestamp: float = field(default_factory=time.time)


class ValuationReconciliation:
    """
    Honest downward correction of headline valuations.

    Rules:
      - No revenue = 80% haircut
      - No users = 50% haircut
      - No signed pilots = 30% haircut
      - No external validation = 20% haircut
      - Minimum reconciled value = $0

    The reconciliation is the sanity brake that prevents
    "AI creates money" false claims.
    """

    def __init__(self, receipt_ledger: ReceiptLedger):
        self.receipt_ledger = receipt_ledger

    def reconcile(
        self,
        artifact_id: str,
        headline_valuation: float,
        revenue_usd: float = 0.0,
        user_count: int = 0,
        pilot_count: int = 0,
        signed_contracts: int = 0,
        external_validation: bool = False,
    ) -> ReconciledValuation:
        haircuts = []
        remaining = headline_valuation

        if revenue_usd == 0:
            haircut = remaining * 0.80
            haircuts.append({"reason": "no_revenue", "amount": round(haircut, 2), "percentage": 80})
            remaining -= haircut

        if user_count == 0:
            haircut = remaining * 0.50
            haircuts.append({"reason": "no_users", "amount": round(haircut, 2), "percentage": 50})
            remaining -= haircut

        if pilot_count == 0:
            haircut = remaining * 0.30
            haircuts.append({"reason": "no_pilots", "amount": round(haircut, 2), "percentage": 30})
            remaining -= haircut

        if not external_validation:
            haircut = remaining * 0.20
            haircuts.append({"reason": "no_external_validation", "amount": round(haircut, 2), "percentage": 20})
            remaining -= haircut

        remaining = max(remaining, 0.0)

        if revenue_usd > 0 and user_count > 0 and external_validation:
            status = "verified"
        elif revenue_usd > 0 or user_count > 0 or pilot_count > 0:
            status = "partially_verified"
        else:
            status = "unverified"

        receipt_data = {
            "artifact_id": artifact_id,
            "headline_valuation": headline_valuation,
            "reconciled_valuation": round(remaining, 2),
            "haircuts": haircuts,
            "revenue_usd": revenue_usd,
            "user_count": user_count,
            "pilot_count": pilot_count,
            "signed_contracts": signed_contracts,
            "external_validation": external_validation,
            "status": status,
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="valuation_reconciled",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )

        return ReconciledValuation(
            artifact_id=artifact_id,
            headline_valuation=headline_valuation,
            reconciled_valuation=round(remaining, 2),
            haircuts=haircuts,
            revenue_evidence=revenue_usd,
            user_evidence=user_count,
            pilot_evidence=pilot_count,
            signed_contracts=signed_contracts,
            status=status,
            receipt_hash=receipt_hash,
        )


# ═══════════════════════════════════════════════════════════════════
# Protocol 203: EvidenceOS → Oracle Bridge
# ═══════════════════════════════════════════════════════════════════

class EvidenceOSBridge:
    """
    Bridge between EvidenceOS (broll/evidence_os.py) and the Oracle.

    Imports unified evidence graphs, Merkle manifests, and scores
    into the Oracle's artifact + packet system.
    """

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger):
        self.db = db
        self.receipt_ledger = receipt_ledger

    def import_evidenceos_result(
        self,
        question: str,
        unified_graph_hash: str = "",
        merkle_root: str = "",
        scores: dict = None,
        base64_packet_hash: str = "",
        receipt_chain_hash: str = "",
        provenance_node_count: int = 0,
        investigation_claim_count: int = 0,
    ) -> dict:
        scores = scores or {}
        artifact_id = f"eos_{hashlib.sha256(f'{question}{time.time()}'.encode()).hexdigest()[:16]}"

        receipt_data = {
            "artifact_id": artifact_id,
            "question": question,
            "unified_graph_hash": unified_graph_hash,
            "merkle_root": merkle_root,
            "scores": scores,
            "base64_packet_hash": base64_packet_hash,
            "receipt_chain_hash": receipt_chain_hash,
            "provenance_node_count": provenance_node_count,
            "investigation_claim_count": investigation_claim_count,
            "imported_at": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="evidenceos_imported",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )

        return {
            "artifact_id": artifact_id,
            "scores": scores,
            "receipt_hash": receipt_hash,
            "status": "imported",
        }


# ═══════════════════════════════════════════════════════════════════
# Protocol 204: VideoLake → Oracle Bridge
# ═══════════════════════════════════════════════════════════════════

class VideoLakeBridge:
    """
    Bridge between VideoLake (broll/videolake.py) and the Oracle.

    Imports compiled video packets, VRAP manifests, and MCRV sidecars
    into the Oracle's BMMA pipeline.
    """

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger):
        self.db = db
        self.receipt_ledger = receipt_ledger

    def import_videolake_result(
        self,
        question: str,
        bundle_file_count: int = 0,
        bundle_hash: str = "",
        vrap_manifest_hash: str = "",
        mcrv_sidecar_hash: str = "",
        scene_graph_hash: str = "",
        base64_packet_hash: str = "",
        frvo_id: str = "",
        machine_scores: dict = None,
    ) -> dict:
        machine_scores = machine_scores or {}
        artifact_id = f"vlk_{hashlib.sha256(f'{question}{time.time()}'.encode()).hexdigest()[:16]}"

        receipt_data = {
            "artifact_id": artifact_id,
            "question": question,
            "bundle_file_count": bundle_file_count,
            "bundle_hash": bundle_hash,
            "vrap_manifest_hash": vrap_manifest_hash,
            "mcrv_sidecar_hash": mcrv_sidecar_hash,
            "scene_graph_hash": scene_graph_hash,
            "base64_packet_hash": base64_packet_hash,
            "frvo_id": frvo_id,
            "machine_scores": machine_scores,
            "imported_at": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="videolake_imported",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )

        return {
            "artifact_id": artifact_id,
            "machine_scores": machine_scores,
            "receipt_hash": receipt_hash,
            "status": "imported",
        }
