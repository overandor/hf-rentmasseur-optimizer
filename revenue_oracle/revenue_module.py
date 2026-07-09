"""
Revenue Module — legitimate revenue flows and receipt recording.

Allowed revenue flows:
- sell evidence report
- sell audit package
- sell software license
- sell API access
- paid waitlist
- consulting intake
- sponsorship checkout
- buyer request form
- manual invoice

Never sell speculative public tokens automatically.
Every payment event creates a RevenueReceipt.
"""

import hashlib
import json
import time
from dataclasses import dataclass, asdict
from enum import Enum
from typing import Optional

from .schema import OracleDB, RevenueReceipt


class ProductType(str, Enum):
    EVIDENCE_REPORT = "evidence_report"
    AUDIT_PACKAGE = "audit_package"
    SOFTWARE_LICENSE = "software_license"
    API_ACCESS = "api_access"
    PAID_WAITLIST = "paid_waitlist"
    CONSULTING_INTAKE = "consulting_intake"
    SPONSORSHIP = "sponsorship_checkout"
    BUYER_REQUEST = "buyer_request_form"
    MANUAL_INVOICE = "manual_invoice"


_ALLOWED_PRODUCT_TYPES = {pt.value for pt in ProductType}


@dataclass
class RevenueFlow:
    flow_id: str
    artifact_id: str
    packet_hash: str
    product_type: str
    amount: float
    currency: str
    buyer_reference: str
    payment_provider: str
    payment_status: str
    created_at: float

    def to_dict(self) -> dict:
        return asdict(self)


class RevenueModule:
    """Handles legitimate revenue flows and receipt recording."""

    def __init__(self, db: OracleDB, receipt_ledger=None):
        self.db = db
        self.receipt_ledger = receipt_ledger

    def create_checkout(self, artifact_id: str, packet_hash: str,
                        product_type: str, amount: float,
                        buyer_reference: str,
                        currency: str = "USD",
                        payment_provider: str = "stripe") -> RevenueFlow:
        """
        Create a checkout session for a legitimate revenue flow.

        Raises ValueError if product_type is not in the allowed list.
        """
        if product_type not in _ALLOWED_PRODUCT_TYPES:
            raise ValueError(
                f"Product type '{product_type}' is not allowed. "
                f"Allowed types: {sorted(_ALLOWED_PRODUCT_TYPES)}"
            )

        if amount <= 0:
            raise ValueError("Amount must be positive")

        flow_id = hashlib.sha256(
            f"revenue:{artifact_id}:{product_type}:{buyer_reference}:{time.time()}".encode()
        ).hexdigest()[:16]

        flow = RevenueFlow(
            flow_id=flow_id,
            artifact_id=artifact_id,
            packet_hash=packet_hash,
            product_type=product_type,
            amount=amount,
            currency=currency,
            buyer_reference=buyer_reference,
            payment_provider=payment_provider,
            payment_status="pending",
            created_at=time.time(),
        )

        if self.receipt_ledger:
            self.receipt_ledger.write(
                receipt_type="checkout_creation",
                artifact_id=artifact_id,
                data=flow.to_dict(),
                packet_hash=packet_hash,
            )

        return flow

    def confirm_payment(self, flow: RevenueFlow,
                        payment_provider: str = "",
                        external_confirmation: dict = None) -> RevenueReceipt:
        """
        Confirm a payment and create a RevenueReceipt.

        Only creates proof_of_revenue when there is external confirmation.
        Without external confirmation, labels as proof_of_financeable_structure_only.
        """
        external_confirmation = external_confirmation or {}
        has_external = bool(external_confirmation.get("verified", False))

        receipt_id = hashlib.sha256(
            f"rev_receipt:{flow.flow_id}:{flow.buyer_reference}:{time.time()}".encode()
        ).hexdigest()[:16]

        payment_status = "confirmed" if has_external else "pending_external_confirmation"

        rec = RevenueReceipt(
            receipt_id=receipt_id,
            buyer_reference=flow.buyer_reference,
            product_type=flow.product_type,
            amount=flow.amount,
            currency=flow.currency,
            payment_provider=payment_provider or flow.payment_provider,
            payment_status=payment_status,
            artifact_id=flow.artifact_id,
            packet_hash=flow.packet_hash,
            created_at=time.time(),
        )

        self.db.insert_revenue_receipt(rec)

        if self.receipt_ledger:
            self.receipt_ledger.write(
                receipt_type="payment_confirmation",
                artifact_id=flow.artifact_id,
                data={
                    "receipt_id": receipt_id,
                    "product_type": flow.product_type,
                    "amount": flow.amount,
                    "currency": flow.currency,
                    "payment_status": payment_status,
                    "has_external_confirmation": has_external,
                    "external_confirmation": external_confirmation,
                },
                packet_hash=flow.packet_hash,
            )

        return rec

    def list_revenue(self) -> list:
        """List all revenue receipts."""
        return self.db.list_revenue_receipts()

    def total_revenue(self) -> dict:
        """Compute total confirmed revenue."""
        receipts = self.db.list_revenue_receipts(limit=10000)
        confirmed = [r for r in receipts if r["payment_status"] == "confirmed"]
        total = sum(r["amount"] for r in confirmed)
        return {
            "total_confirmed_usd": total,
            "confirmed_count": len(confirmed),
            "pending_count": len(receipts) - len(confirmed),
            "currency": "USD",
        }
