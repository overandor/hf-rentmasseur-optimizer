"""
Verification & Audit Protocols — 217-220

Protocol 217: Revenue Attestation Engine
Protocol 218: Audit Trail Exporter
Protocol 219: SLSA Build Provenance
Protocol 220: FAIR Risk Scoring
"""

import hashlib
import json
import time
import base64
import zlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

from .schema import OracleDB
from .receipt_ledger import ReceiptLedger


# ═══════════════════════════════════════════════════════════════════
# Protocol 217: Revenue Attestation Engine
# ═══════════════════════════════════════════════════════════════════

class AttestationStatus(Enum):
    ATTESTED = "attested"
    REJECTED = "rejected"
    PENDING = "pending"
    EXPIRED = "expired"


@dataclass
class RevenueAttestation:
    attestation_id: str
    artifact_id: str
    revenue_amount_usd: float
    payment_reference: str
    payment_provider: str
    external_confirmation_hash: str
    attester: str
    status: str
    attested_at: float
    expires_at: float
    receipt_hash: str
    metadata: dict = field(default_factory=dict)


class RevenueAttestationEngine:
    """
    Attests that a revenue claim is backed by verifiable external evidence.

    Hard rules:
      - No attestation without external_confirmation (payment provider receipt, escrow release, etc.)
      - No attestation without payment_reference
      - Attestations expire after 90 days unless renewed
      - Every attestation writes a receipt

    Attestation is NOT a guarantee of payment. It is a cryptographic statement
    that "at time T, evidence E was present showing payment P from provider PR."
    """

    ATTESTATION_TTL_SECONDS = 90 * 24 * 60 * 60  # 90 days

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger):
        self.db = db
        self.receipt_ledger = receipt_ledger
        self.attestations: dict[str, RevenueAttestation] = {}

    def attest(
        self,
        artifact_id: str,
        revenue_amount_usd: float,
        payment_reference: str,
        payment_provider: str,
        external_confirmation: dict,
        attester: str = "system",
    ) -> RevenueAttestation:
        # Hard gate: no external confirmation = reject
        if not external_confirmation or not external_confirmation.get("verified"):
            return self._reject(artifact_id, revenue_amount_usd, "no_external_confirmation")

        # Hard gate: no payment reference = reject
        if not payment_reference:
            return self._reject(artifact_id, revenue_amount_usd, "no_payment_reference")

        # Hard gate: zero revenue = reject
        if revenue_amount_usd <= 0:
            return self._reject(artifact_id, revenue_amount_usd, "zero_or_negative_revenue")

        confirmation_hash = f"sha256:{hashlib.sha256(json.dumps(external_confirmation, sort_keys=True).encode()).hexdigest()[:16]}"
        attestation_id = f"att_{hashlib.sha256(f'{artifact_id}{payment_reference}{time.time()}'.encode()).hexdigest()[:12]}"
        now = time.time()

        receipt_data = {
            "attestation_id": attestation_id,
            "artifact_id": artifact_id,
            "revenue_amount_usd": revenue_amount_usd,
            "payment_reference": payment_reference,
            "payment_provider": payment_provider,
            "external_confirmation_hash": confirmation_hash,
            "attester": attester,
            "attested_at": now,
            "expires_at": now + self.ATTESTATION_TTL_SECONDS,
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="revenue_attested",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )

        attestation = RevenueAttestation(
            attestation_id=attestation_id,
            artifact_id=artifact_id,
            revenue_amount_usd=revenue_amount_usd,
            payment_reference=payment_reference,
            payment_provider=payment_provider,
            external_confirmation_hash=confirmation_hash,
            attester=attester,
            status=AttestationStatus.ATTESTED.value,
            attested_at=now,
            expires_at=now + self.ATTESTATION_TTL_SECONDS,
            receipt_hash=receipt_hash,
            metadata=external_confirmation,
        )
        self.attestations[attestation_id] = attestation
        return attestation

    def _reject(self, artifact_id: str, amount: float, reason: str) -> RevenueAttestation:
        attestation_id = f"rej_{hashlib.sha256(f'{artifact_id}{reason}{time.time()}'.encode()).hexdigest()[:12]}"
        receipt_data = {
            "attestation_id": attestation_id,
            "artifact_id": artifact_id,
            "revenue_amount_usd": amount,
            "rejection_reason": reason,
            "rejected_at": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="revenue_attestation_rejected",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )

        result = RevenueAttestation(
            attestation_id=attestation_id,
            artifact_id=artifact_id,
            revenue_amount_usd=amount,
            payment_reference="",
            payment_provider="",
            external_confirmation_hash="",
            attester="system",
            status=AttestationStatus.REJECTED.value,
            attested_at=time.time(),
            expires_at=0,
            receipt_hash=receipt_hash,
            metadata={"rejection_reason": reason},
        )
        self.attestations[attestation_id] = result
        return result

    def verify(self, attestation_id: str) -> dict:
        att = self.attestations.get(attestation_id)
        if not att:
            return {"valid": False, "error": "attestation_not_found"}

        now = time.time()
        if now > att.expires_at:
            att.status = AttestationStatus.EXPIRED.value
            return {"valid": False, "error": "attestation_expired", "expired_at": att.expires_at}

        return {
            "valid": True,
            "attestation_id": att.attestation_id,
            "artifact_id": att.artifact_id,
            "revenue_amount_usd": att.revenue_amount_usd,
            "payment_reference": att.payment_reference,
            "payment_provider": att.payment_provider,
            "status": att.status,
            "attested_at": att.attested_at,
            "expires_at": att.expires_at,
        }

    def list_attestations(self, artifact_id: str = None) -> list:
        if artifact_id:
            return [asdict(a) for a in self.attestations.values() if a.artifact_id == artifact_id]
        return [asdict(a) for a in self.attestations.values()]


# ═══════════════════════════════════════════════════════════════════
# Protocol 218: Audit Trail Exporter
# ═══════════════════════════════════════════════════════════════════

@dataclass
class AuditTrail:
    trail_id: str
    artifact_id: str
    events: list  # [{timestamp, event_type, description, receipt_hash}]
    total_events: int
    chain_valid: bool
    export_hash: str
    exported_at: float = field(default_factory=time.time)


class AuditTrailExporter:
    """
    Exports a complete audit trail for an artifact.

    Pulls all receipts, evidence packets, risk reports, deployments,
    revenue events, attestations, and compliance checks into a single
    chronological trail with chain verification.

    Output formats: JSON, CSV, Base64 compressed.
    """

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger):
        self.db = db
        self.receipt_ledger = receipt_ledger

    def export_trail(
        self,
        artifact_id: str,
        format: str = "json",  # json, csv, base64
    ) -> AuditTrail:
        events = []

        # Gather all receipts for this artifact
        all_receipts = self.receipt_ledger.list_all()
        for r in all_receipts:
            r_dict = r.to_dict() if hasattr(r, 'to_dict') else r
            if isinstance(r_dict, dict) and r_dict.get("artifact_id") == artifact_id:
                events.append({
                    "timestamp": r_dict.get("timestamp", 0),
                    "event_type": r_dict.get("receipt_type", "unknown"),
                    "description": f"{r_dict.get('receipt_type', 'unknown')} for {artifact_id}",
                    "receipt_hash": r_dict.get("receipt_hash", ""),
                    "receipt_id": r_dict.get("receipt_id", ""),
                })

        # Sort chronologically
        events.sort(key=lambda e: e["timestamp"])

        # Verify chain
        chain_valid = self.receipt_ledger.verify_chain()

        trail_id = f"aud_{hashlib.sha256(f'{artifact_id}{time.time()}'.encode()).hexdigest()[:12]}"

        trail_data = {
            "trail_id": trail_id,
            "artifact_id": artifact_id,
            "events": events,
            "total_events": len(events),
            "chain_valid": chain_valid,
        }
        export_hash = f"sha256:{hashlib.sha256(json.dumps(trail_data, sort_keys=True).encode()).hexdigest()[:16]}"

        # Write receipt for the export itself
        self.receipt_ledger.write(
            receipt_type="audit_trail_exported",
            artifact_id=artifact_id,
            data={
                "trail_id": trail_id,
                "total_events": len(events),
                "chain_valid": chain_valid,
                "export_hash": export_hash,
                "format": format,
            },
            output_hash=export_hash,
        )

        return AuditTrail(
            trail_id=trail_id,
            artifact_id=artifact_id,
            events=events,
            total_events=len(events),
            chain_valid=chain_valid,
            export_hash=export_hash,
        )

    def export_base64(self, artifact_id: str) -> str:
        trail = self.export_trail(artifact_id, format="base64")
        data = json.dumps({
            "trail_id": trail.trail_id,
            "artifact_id": trail.artifact_id,
            "events": trail.events,
            "total_events": trail.total_events,
            "chain_valid": trail.chain_valid,
            "export_hash": trail.export_hash,
        }, sort_keys=True).encode()
        compressed = zlib.compress(data)
        return base64.b64encode(compressed).decode()

    def export_csv(self, artifact_id: str) -> str:
        trail = self.export_trail(artifact_id, format="csv")
        lines = ["timestamp,event_type,description,receipt_hash"]
        for e in trail.events:
            lines.append(f"{e['timestamp']},{e['event_type']},{e['description']},{e['receipt_hash']}")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Protocol 219: SLSA Build Provenance
# ═══════════════════════════════════════════════════════════════════

class SLSALevel(Enum):
    NONE = 0
    UNTRUSTED_BUILD = 1
    TRUSTED_BUILD = 2
    ISOLATED_BUILD = 3
    REPRODUCIBLE_BUILD = 4


@dataclass
class SLSAProvenance:
    provenance_id: str
    artifact_id: str
    slsa_level: int
    builder_id: str
    build_type: str
    source_uri: str
    source_hash: str
    build_hash: str
    materials: list  # [{uri, hash}]
    build_command: str
    build_started_at: float
    build_finished_at: float
    environment: dict
    receipt_hash: str
    reproducible: bool = False


class SLSABuildProvenance:
    """
    Generates SLSA (Supply-chain Levels for Software Artifacts) provenance records.

    SLSA levels:
      1: Untrusted build — provenance exists but build not trusted
      2: Trusted build — build service is trusted
      3: Isolated build — build runs in isolated environment
      4: Reproducible build — two builds produce identical output

    This implementation generates provenance metadata. It does NOT
    verify the trust of the build service — that requires external
    infrastructure (e.g., Sigstore, Tekton Chains).
    """

    def __init__(self, receipt_ledger: ReceiptLedger):
        self.receipt_ledger = receipt_ledger

    def generate(
        self,
        artifact_id: str,
        builder_id: str,
        build_type: str,
        source_uri: str,
        source_hash: str,
        build_hash: str,
        materials: list = None,
        build_command: str = "",
        build_started_at: float = 0,
        build_finished_at: float = 0,
        environment: dict = None,
        reproducible: bool = False,
    ) -> SLSAProvenance:
        materials = materials or []
        environment = environment or {}

        # Determine SLSA level
        if reproducible:
            level = SLSALevel.REPRODUCIBLE_BUILD.value
        elif environment.get("isolated"):
            level = SLSALevel.ISOLATED_BUILD.value
        elif builder_id and builder_id != "unknown":
            level = SLSALevel.TRUSTED_BUILD.value
        else:
            level = SLSALevel.UNTRUSTED_BUILD.value

        provenance_id = f"slsa_{hashlib.sha256(f'{artifact_id}{build_hash}{time.time()}'.encode()).hexdigest()[:12]}"

        provenance_data = {
            "provenance_id": provenance_id,
            "artifact_id": artifact_id,
            "slsa_level": level,
            "builder_id": builder_id,
            "build_type": build_type,
            "source_uri": source_uri,
            "source_hash": source_hash,
            "build_hash": build_hash,
            "materials": materials,
            "build_command": build_command,
            "build_started_at": build_started_at,
            "build_finished_at": build_finished_at,
            "environment": environment,
            "reproducible": reproducible,
            "generated_at": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(provenance_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="slsa_provenance_generated",
            artifact_id=artifact_id,
            data=provenance_data,
            output_hash=receipt_hash,
        )

        return SLSAProvenance(
            provenance_id=provenance_id,
            artifact_id=artifact_id,
            slsa_level=level,
            builder_id=builder_id,
            build_type=build_type,
            source_uri=source_uri,
            source_hash=source_hash,
            build_hash=build_hash,
            materials=materials,
            build_command=build_command,
            build_started_at=build_started_at,
            build_finished_at=build_finished_at,
            environment=environment,
            receipt_hash=receipt_hash,
            reproducible=reproducible,
        )

    def verify_provenance(self, provenance: SLSAProvenance) -> dict:
        """Verify that provenance data is internally consistent."""
        issues = []

        if not provenance.source_hash:
            issues.append("missing_source_hash")
        if not provenance.build_hash:
            issues.append("missing_build_hash")
        if provenance.build_finished_at < provenance.build_started_at:
            issues.append("build_finished_before_started")
        if provenance.slsa_level >= 3 and not provenance.environment.get("isolated"):
            issues.append("level_3_requires_isolated_env")
        if provenance.slsa_level >= 4 and not provenance.reproducible:
            issues.append("level_4_requires_reproducible")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "slsa_level": provenance.slsa_level,
        }


# ═══════════════════════════════════════════════════════════════════
# Protocol 220: FAIR Risk Scoring
# ═══════════════════════════════════════════════════════════════════

class FAIRLossMagnitude(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class FAIRRiskScore:
    score_id: str
    artifact_id: str
    threat_event_frequency: float  # events per year
    vulnerability: float  # 0.0 to 1.0
    loss_magnitude_usd: float  # average loss per event
    ale: float  # Annualized Loss Expectancy = TEF × Vuln × LM
    risk_level: str
    factors: list  # [{factor, value, weight}]
    receipt_hash: str
    timestamp: float = field(default_factory=time.time)


class FAIRRiskScoring:
    """
    FAIR (Factor Analysis of Information Risk) scoring for artifacts.

    ALE = Threat Event Frequency × Vulnerability × Loss Magnitude

    Risk levels:
      low: ALE < $1,000/year
      medium: $1,000 ≤ ALE < $10,000
      high: $10,000 ≤ ALE < $100,000
      critical: ALE ≥ $100,000

    Factors that influence scoring:
      - Secret exposure risk
      - Dependency vulnerability count
      - License conflict risk
      - Deployment exposure (public vs private)
      - Data sensitivity
      - Compliance gap count
    """

    def __init__(self, receipt_ledger: ReceiptLedger):
        self.receipt_ledger = receipt_ledger

    def score(
        self,
        artifact_id: str,
        secret_exposure_count: int = 0,
        dependency_vuln_count: int = 0,
        has_license_conflict: bool = False,
        is_publicly_deployed: bool = False,
        data_sensitivity: str = "low",  # low, medium, high, critical
        compliance_gap_count: int = 0,
        custom_tef: float = 0,
        custom_loss_magnitude: float = 0,
    ) -> FAIRRiskScore:
        factors = []

        # Threat Event Frequency (events per year)
        tef = custom_tef if custom_tef > 0 else 0.1  # baseline
        if secret_exposure_count > 0:
            tef += secret_exposure_count * 0.5
            factors.append({"factor": "secret_exposure", "value": secret_exposure_count, "weight": 0.5})
        if dependency_vuln_count > 0:
            tef += dependency_vuln_count * 0.1
            factors.append({"factor": "dependency_vulns", "value": dependency_vuln_count, "weight": 0.1})
        if is_publicly_deployed:
            tef += 0.3
            factors.append({"factor": "public_deployment", "value": True, "weight": 0.3})

        # Vulnerability (0.0 to 1.0)
        vuln = 0.1  # baseline
        if has_license_conflict:
            vuln += 0.2
            factors.append({"factor": "license_conflict", "value": True, "weight": 0.2})
        if compliance_gap_count > 0:
            vuln += min(compliance_gap_count * 0.1, 0.5)
            factors.append({"factor": "compliance_gaps", "value": compliance_gap_count, "weight": 0.1})
        vuln = min(vuln, 1.0)

        # Loss Magnitude (USD per event)
        sensitivity_multipliers = {
            "low": 500,
            "medium": 5000,
            "high": 50000,
            "critical": 500000,
        }
        loss_magnitude = custom_loss_magnitude if custom_loss_magnitude > 0 else sensitivity_multipliers.get(data_sensitivity, 500)
        factors.append({"factor": "data_sensitivity", "value": data_sensitivity, "weight": 1.0})

        # ALE = TEF × Vuln × LM
        ale = tef * vuln * loss_magnitude

        # Risk level
        if ale < 1000:
            risk_level = FAIRLossMagnitude.LOW.value
        elif ale < 10000:
            risk_level = FAIRLossMagnitude.MEDIUM.value
        elif ale < 100000:
            risk_level = FAIRLossMagnitude.HIGH.value
        else:
            risk_level = FAIRLossMagnitude.CRITICAL.value

        score_id = f"fair_{hashlib.sha256(f'{artifact_id}{ale}{time.time()}'.encode()).hexdigest()[:12]}"

        score_data = {
            "score_id": score_id,
            "artifact_id": artifact_id,
            "tef": round(tef, 3),
            "vulnerability": round(vuln, 3),
            "loss_magnitude": loss_magnitude,
            "ale": round(ale, 2),
            "risk_level": risk_level,
            "factors": factors,
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(score_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="fair_risk_scored",
            artifact_id=artifact_id,
            data=score_data,
            output_hash=receipt_hash,
        )

        return FAIRRiskScore(
            score_id=score_id,
            artifact_id=artifact_id,
            threat_event_frequency=round(tef, 3),
            vulnerability=round(vuln, 3),
            loss_magnitude_usd=loss_magnitude,
            ale=round(ale, 2),
            risk_level=risk_level,
            factors=factors,
            receipt_hash=receipt_hash,
        )
