"""
Sealed Grade Bond (AGB) Protocol — Bonded Machine Media Assets.

The trust and recourse layer that turns evidence-backed media from
"interesting content" into an underwritable, slashable, auditable instrument.

A normal video says: "Watch me."
A Machine-Consumable Research Video says: "Here are my claims, sources, rights, provenance, receipts."
A Fractional Revenue Video Object says: "Here is the revenue ledger, participant registry, payout waterfall."
A Sealed Grade Bond says: "The claimed quality of this packet is bonded, slashable, and auditable."

BMMA = MCRV + FRVO + AGB

Architecture:

    Rubrics → Grade Claim → Bond → Audit → Challenge → Slash/Settle → Receipt

Rubrics define how to score a media packet across dimensions.
Grade claims assert a score under a rubric.
Bonds stake capital behind the claim.
Audits randomly verify claims.
Challenges dispute claims.
Slash schedules define penalties for false claims.
Settlements resolve challenges and distribute slashed bonds.

Usage:
    from broll.grade_bond import GradeBondProtocol
    protocol = GradeBondProtocol()
    claim = protocol.create_grade_claim(
        media_packet_id="mcrv_abc123",
        frvo_id="frvo_def456",
        rubric_id="video_evidence_quality_v1",
        claimed_grade=92,
        bond_amount_usd=5000,
        machine_scores={"evidence_strength": 0.86, "rights_safety": 0.91},
    )
    challenge = protocol.challenge_claim(claim, challenger="auditor_001", evidence="grade_inflated")
    settlement = protocol.settle_challenge(challenge, verdict="upheld")
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ClaimStatus(Enum):
    DRAFT = "DRAFT"
    SEALED = "SEALED"
    CHALLENGED = "CHALLENGED"
    UPHELD = "UPHELD"
    SLASHED = "SLASHED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"


class ChallengeVerdict(Enum):
    PENDING = "PENDING"
    UPHELD = "UPHELD"          # Claim is accurate, challenger loses
    OVERTURNED = "OVERTURNED"  # Claim is false, bond is slashed
    PARTIAL = "PARTIAL"        # Claim is partially false, partial slash
    DISMISSED = "DISMISSED"    # Challenge invalid


class SlashTier(Enum):
    NONE = "NONE"
    MINOR = "MINOR"        # <= tolerance breach, 10% slash
    MODERATE = "MODERATE"  # 1-2x tolerance breach, 25% slash
    MAJOR = "MAJOR"        # 2-3x tolerance breach, 50% slash
    SEVERE = "SEVERE"      # >3x tolerance breach, 100% slash


# ---------------------------------------------------------------------------
# Rubrics
# ---------------------------------------------------------------------------

@dataclass
class RubricDimension:
    """A single scoring dimension within a rubric."""
    name: str
    weight: float  # 0.0 to 1.0, sum of all weights = 1.0
    description: str
    source_field: str  # which machine_score field to read

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "weight": self.weight,
            "description": self.description,
            "source_field": self.source_field,
        }


@dataclass
class Rubric:
    """A scoring rubric that defines how to grade a media packet."""
    rubric_id: str
    name: str
    description: str
    dimensions: list[RubricDimension] = field(default_factory=list)
    max_grade: float = 100.0
    tolerance: float = 3.0  # allowed deviation before slash

    def to_dict(self) -> dict:
        return {
            "rubric_id": self.rubric_id,
            "name": self.name,
            "description": self.description,
            "dimensions": [d.to_dict() for d in self.dimensions],
            "max_grade": self.max_grade,
            "tolerance": self.tolerance,
        }

    def compute_grade(self, machine_scores: dict) -> float:
        """Compute a grade from machine scores using the rubric dimensions."""
        total = 0.0
        for dim in self.dimensions:
            raw = machine_scores.get(dim.source_field, 0.0)
            total += raw * dim.weight * self.max_grade
        return round(min(total, self.max_grade), 1)


# ---------------------------------------------------------------------------
# Bond and Slash
# ---------------------------------------------------------------------------

@dataclass
class SlashSchedule:
    """Defines how much of the bond is slashed per severity tier."""
    schedule_id: str
    minor_pct: float = 10.0
    moderate_pct: float = 25.0
    major_pct: float = 50.0
    severe_pct: float = 100.0

    def to_dict(self) -> dict:
        return {
            "schedule_id": self.schedule_id,
            "minor_pct": self.minor_pct,
            "moderate_pct": self.moderate_pct,
            "major_pct": self.major_pct,
            "severe_pct": self.severe_pct,
        }

    def slash_amount(self, tier: SlashTier, bond_amount: float) -> float:
        pct = {
            SlashTier.NONE: 0.0,
            SlashTier.MINOR: self.minor_pct,
            SlashTier.MODERATE: self.moderate_pct,
            SlashTier.MAJOR: self.major_pct,
            SlashTier.SEVERE: self.severe_pct,
        }[tier]
        return round(bond_amount * pct / 100.0, 2)

    @staticmethod
    def determine_tier(deviation: float, tolerance: float) -> SlashTier:
        """Determine slash tier from grade deviation and tolerance."""
        if deviation <= tolerance:
            return SlashTier.NONE
        ratio = deviation / tolerance if tolerance > 0 else deviation
        if ratio <= 2:
            return SlashTier.MINOR
        if ratio <= 3:
            return SlashTier.MODERATE
        if ratio <= 4:
            return SlashTier.MAJOR
        return SlashTier.SEVERE


@dataclass
class Bond:
    """A capital bond staked behind a grade claim."""
    bond_id: str
    claim_id: str
    amount_usd: float
    currency: str = "USD"
    posted_at: float = 0.0
    poster_id: str = ""
    status: str = "ACTIVE"  # ACTIVE, SLASHED, RELEASED, FORFEITED
    slashed_amount: float = 0.0
    released_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "bond_id": self.bond_id,
            "claim_id": self.claim_id,
            "amount_usd": round(self.amount_usd, 2),
            "currency": self.currency,
            "posted_at": self.posted_at,
            "poster_id": self.poster_id,
            "status": self.status,
            "slashed_amount": round(self.slashed_amount, 2),
            "released_at": self.released_at,
        }


# ---------------------------------------------------------------------------
# Grade Claim
# ---------------------------------------------------------------------------

@dataclass
class GradeClaim:
    """
    A sealed grade claim over a media packet.

    Asserts that the packet achieves a specific grade under a rubric,
    with a bond staked behind the claim.
    """
    claim_id: str
    media_packet_id: str
    frvo_id: str
    rubric_id: str
    claimed_grade: float
    computed_grade: float = 0.0
    bond_id: str = ""
    bond_amount_usd: float = 0.0
    audit_probability: float = 0.0
    tolerance: float = 3.0
    status: ClaimStatus = ClaimStatus.DRAFT
    machine_scores: dict = field(default_factory=dict)
    slash_schedule_id: str = ""
    sealed_at: float = 0.0
    expires_at: float = 0.0
    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "claim_id": self.claim_id,
            "media_packet_id": self.media_packet_id,
            "frvo_id": self.frvo_id,
            "rubric_id": self.rubric_id,
            "claimed_grade": self.claimed_grade,
            "computed_grade": self.computed_grade,
            "bond_id": self.bond_id,
            "bond_amount_usd": round(self.bond_amount_usd, 2),
            "audit_probability": self.audit_probability,
            "tolerance": self.tolerance,
            "status": self.status.value,
            "machine_scores": self.machine_scores,
            "slash_schedule_id": self.slash_schedule_id,
            "sealed_at": self.sealed_at,
            "expires_at": self.expires_at,
            "receipt_hash": self.receipt_hash,
        }


# ---------------------------------------------------------------------------
# Challenge and Settlement
# ---------------------------------------------------------------------------

@dataclass
class Challenge:
    """A challenge against a grade claim."""
    challenge_id: str
    claim_id: str
    challenger_id: str
    reason: str
    evidence: str
    proposed_grade: Optional[float] = None
    status: ChallengeVerdict = ChallengeVerdict.PENDING
    created_at: float = 0.0
    resolved_at: float = 0.0
    slash_tier: str = "NONE"
    slash_amount: float = 0.0
    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "challenge_id": self.challenge_id,
            "claim_id": self.claim_id,
            "challenger_id": self.challenger_id,
            "reason": self.reason,
            "evidence": self.evidence,
            "proposed_grade": self.proposed_grade,
            "status": self.status.value,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "slash_tier": self.slash_tier,
            "slash_amount": round(self.slash_amount, 2),
            "receipt_hash": self.receipt_hash,
        }


@dataclass
class Settlement:
    """The resolution of a challenge."""
    settlement_id: str
    challenge_id: str
    claim_id: str
    verdict: ChallengeVerdict
    slash_tier: SlashTier
    slash_amount: float
    bond_remaining: float
    challenger_reward: float
    creator_penalty: float
    timestamp: float = 0.0
    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "settlement_id": self.settlement_id,
            "challenge_id": self.challenge_id,
            "claim_id": self.claim_id,
            "verdict": self.verdict.value,
            "slash_tier": self.slash_tier.value,
            "slash_amount": round(self.slash_amount, 2),
            "bond_remaining": round(self.bond_remaining, 2),
            "challenger_reward": round(self.challenger_reward, 2),
            "creator_penalty": round(self.creator_penalty, 2),
            "timestamp": self.timestamp,
            "receipt_hash": self.receipt_hash,
        }


# ---------------------------------------------------------------------------
# BMMA — Bonded Machine Media Asset
# ---------------------------------------------------------------------------

@dataclass
class BMMA:
    """
    Bonded Machine Media Asset — the unified financeable instrument.

    BMMA = MCRV + FRVO + SGB + BEA + Standards + Marketplace

    This is the top-level object that binds all five layers:
        1. EvidenceOS substrate (provenance, receipts, graph)
        2. VideoLake / OverVisual (evidence-backed media packet)
        3. MCRV / VRAP (machine-consumable media packet)
        4. Fractional Video Rights Vault (revenue + rights ledger)
        5. Sealed Grade Exchange (bonded grade + audit + slash)

    A human can watch it. A machine can parse it. A buyer can license it.
    A backer can underwrite it. An auditor can challenge it.
    """
    instrument_type: str = "bonded_machine_media_asset_v1"
    bmma_id: str = ""
    media_packet_id: str = ""
    video_asset_id: str = ""  # frvo_id
    grade_bond_id: str = ""  # claim_id
    bea_id: str = ""  # Bonded Evidence Asset reference
    question: str = ""
    media_packet: dict = field(default_factory=dict)
    fractional_revenue_object: dict = field(default_factory=dict)
    bonded_grade: dict = field(default_factory=dict)
    machine_scores: dict = field(default_factory=dict)
    # Standards exports
    schema_org_object: dict = field(default_factory=dict)
    c2pa_manifest: dict = field(default_factory=dict)
    # Segment marketplace
    segment_listings: list[dict] = field(default_factory=list)
    marketplace_summary: dict = field(default_factory=dict)
    # Provenance
    provenance_hash: str = ""
    receipt_hash: str = ""
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "instrument_type": self.instrument_type,
            "bmma_id": self.bmma_id,
            "media_packet_id": self.media_packet_id,
            "video_asset_id": self.video_asset_id,
            "grade_bond_id": self.grade_bond_id,
            "bea_id": self.bea_id,
            "question": self.question,
            "media_packet": self.media_packet,
            "fractional_revenue_object": self.fractional_revenue_object,
            "bonded_grade": self.bonded_grade,
            "machine_scores": self.machine_scores,
            "schema_org_object": self.schema_org_object,
            "c2pa_manifest": self.c2pa_manifest,
            "segment_listings": self.segment_listings,
            "marketplace_summary": self.marketplace_summary,
            "provenance_hash": self.provenance_hash,
            "receipt_hash": self.receipt_hash,
            "created_at": self.created_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def compute_hash(self) -> str:
        data = json.dumps({
            "instrument_type": self.instrument_type,
            "bmma_id": self.bmma_id,
            "media_packet_id": self.media_packet_id,
            "video_asset_id": self.video_asset_id,
            "grade_bond_id": self.grade_bond_id,
            "bea_id": self.bea_id,
        }, sort_keys=True)
        self.receipt_hash = f"sha256:{hashlib.sha256(data.encode()).hexdigest()[:16]}"
        return self.receipt_hash

    def underwriter_view(self) -> dict:
        """
        Public underwriter view — what a backer, auditor, or licensing
        market sees.

        Exposes:
            - Asset type and hash (not content)
            - Claimed and computed grade
            - Rubric used
            - Bond amount and required bond
            - Audit probability and slash schedule
            - Producer tier and track record summary
            - Receipt chain validity
            - Rights safety and revenue ledger status
            - Segment marketplace availability
            - Standards compliance (Schema.org, C2PA)

        Does NOT expose:
            - Raw video content
            - Raw claims text
            - Raw revenue amounts (only ledger validity)
            - Producer identity beyond tier
        """
        bg = self.bonded_grade
        fr = self.fractional_revenue_object
        return {
            "schema": "bmma_underwriter_view_v1",
            "bmma_id": self.bmma_id,
            "instrument_type": self.instrument_type,
            "question": self.question,
            "asset_hash": self.provenance_hash,
            "grade": {
                "claimed": bg.get("claimed_grade", 0),
                "computed": bg.get("computed_grade", 0),
                "rubric_id": bg.get("rubric_id", ""),
                "tolerance": bg.get("tolerance", 0),
                "status": bg.get("status", ""),
            },
            "bond": {
                "amount_usd": bg.get("bond_amount", 0),
                "audit_probability": bg.get("audit_probability", 0),
                "slash_schedule_id": bg.get("slash_schedule_id", ""),
                "required_bond": bg.get("required_bond", 0),
            },
            "producer": {
                "tier": bg.get("producer_tier", "unproven"),
                "slash_rate": bg.get("producer_slash_rate", 0),
                "total_claims": bg.get("producer_total_claims", 0),
            },
            "rights": {
                "offering_mode": fr.get("offering_mode", ""),
                "ledger_valid": fr.get("ledger_valid", False),
                "revenue_sources_count": len(fr.get("revenue_sources", [])),
                "participants_count": len(fr.get("participant_registry", [])),
            },
            "marketplace": {
                "segments_listed": len(self.segment_listings),
                "segments_available": sum(
                    1 for s in self.segment_listings if s.get("license_available", False)
                ),
                "avg_evidence_score": self.marketplace_summary.get("avg_evidence_score", 0),
                "avg_price_usd": self.marketplace_summary.get("avg_price", 0),
            },
            "standards": {
                "schema_org": bool(self.schema_org_object),
                "c2pa_manifest": bool(self.c2pa_manifest),
            },
            "receipt_hash": self.receipt_hash,
            "ledger_valid": bg.get("ledger_valid", True),
        }

    def public_view(self) -> dict:
        """
        Minimal public view — what anyone can see without commitment.

        Even more restricted than underwriter_view. No bond amounts,
        no producer details, no revenue info. Just existence, grade,
        and availability.
        """
        bg = self.bonded_grade
        return {
            "schema": "bmma_public_view_v1",
            "bmma_id": self.bmma_id,
            "question": self.question,
            "asset_type": self.instrument_type,
            "claimed_grade": bg.get("claimed_grade", 0),
            "rubric_id": bg.get("rubric_id", ""),
            "grade_status": bg.get("status", ""),
            "segments_available": sum(
                1 for s in self.segment_listings if s.get("license_available", False)
            ),
            "standards_compliant": bool(self.schema_org_object) or bool(self.c2pa_manifest),
            "receipt_hash": self.receipt_hash,
        }


# ---------------------------------------------------------------------------
# Receipt Ledger
# ---------------------------------------------------------------------------

class GradeBondLedger:
    """Tamper-evident ledger for all grade bond operations."""

    def __init__(self):
        self.entries: list[dict] = []

    def add(self, action: str, description: str, data: dict) -> dict:
        prev_hash = self.entries[-1]["hash"] if self.entries else "0" * 64
        ts = time.time()
        index = len(self.entries)
        h = hashlib.sha256(
            f"{index}{action}{description}{json.dumps(data, sort_keys=True)}{ts}{prev_hash}".encode()
        ).hexdigest()
        entry = {
            "index": index,
            "action": action,
            "description": description,
            "data": data,
            "timestamp": ts,
            "prev_hash": prev_hash,
            "hash": h,
        }
        self.entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        prev_hash = "0" * 64
        for entry in self.entries:
            if entry["prev_hash"] != prev_hash:
                return False
            expected = hashlib.sha256(
                f"{entry['index']}{entry['action']}{entry['description']}"
                f"{json.dumps(entry['data'], sort_keys=True)}{entry['timestamp']}{entry['prev_hash']}".encode()
            ).hexdigest()
            if entry["hash"] != expected:
                return False
            prev_hash = entry["hash"]
        return True

    def to_list(self) -> list[dict]:
        return list(self.entries)


# ---------------------------------------------------------------------------
# Audit Draw — stochastic audit selection (defined early, used by Protocol)
# ---------------------------------------------------------------------------

@dataclass
class AuditDraw:
    """
    A stochastic audit draw against a sealed grade claim.

    Uses audit_probability to determine whether to audit.
    If drawn, an auditor evaluates the claim and produces a grade.
    """
    draw_id: str
    claim_id: str
    drawn: bool
    auditor_id: str = ""
    auditor_grade: float = 0.0
    deviation: float = 0.0
    slash_tier: str = "NONE"
    timestamp: float = 0.0
    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "draw_id": self.draw_id,
            "claim_id": self.claim_id,
            "drawn": self.drawn,
            "auditor_id": self.auditor_id,
            "auditor_grade": self.auditor_grade,
            "deviation": self.deviation,
            "slash_tier": self.slash_tier,
            "timestamp": self.timestamp,
            "receipt_hash": self.receipt_hash,
        }


# ---------------------------------------------------------------------------
# Bonded Evidence Asset (BEA) — defined early, used by Protocol
# ---------------------------------------------------------------------------

@dataclass
class BondedEvidenceAsset:
    """
    Bonded Evidence Asset — the generalized financeable primitive.

    BEA = sealed artifact + claimed grade + rubric + locked bond
          + audit probability + slash rule + receipt chain + producer track record

    Works for: answers, videos, repo appraisals, investigations,
    revenue packets, and method graphs.
    """
    bea_id: str
    asset_type: str  # mcrv, frvo, answer, repo_method, prospect, revenue_ledger
    asset_hash: str  # sha256 of the sealed artifact
    asset_uri: str = ""
    claimed_grade: float = 0.0
    computed_grade: float = 0.0
    rubric_id: str = ""
    grade_dimensions: dict = field(default_factory=dict)
    bond_amount: float = 0.0
    required_bond: float = 0.0
    audit_probability: float = 0.0
    slash_schedule_id: str = ""
    producer_id: str = ""
    producer_tier: str = "unproven"
    claim_id: str = ""
    receipt_hash: str = ""
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "bea_id": self.bea_id,
            "asset_type": self.asset_type,
            "asset_hash": self.asset_hash,
            "asset_uri": self.asset_uri,
            "claimed_grade": self.claimed_grade,
            "computed_grade": self.computed_grade,
            "rubric_id": self.rubric_id,
            "grade_dimensions": self.grade_dimensions,
            "bond_amount": round(self.bond_amount, 2),
            "required_bond": round(self.required_bond, 2),
            "audit_probability": self.audit_probability,
            "slash_schedule_id": self.slash_schedule_id,
            "producer_id": self.producer_id,
            "producer_tier": self.producer_tier,
            "claim_id": self.claim_id,
            "receipt_hash": self.receipt_hash,
            "created_at": self.created_at,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------

class GradeBondProtocol:
    """
    The Sealed Grade Bond protocol.

    Manages rubrics, grade claims, bonds, challenges, and settlements.
    Produces BMMA instruments that bind MCRV + FRVO + AGB.
    """

    DEFAULT_SLASH_SCHEDULE = SlashSchedule(
        schedule_id="media_grade_slash_v1",
        minor_pct=10.0,
        moderate_pct=25.0,
        major_pct=50.0,
        severe_pct=100.0,
    )

    def __init__(self):
        self.rubrics: dict[str, Rubric] = {}
        self.claims: list[GradeClaim] = []
        self.bonds: list[Bond] = []
        self.challenges: list[Challenge] = []
        self.settlements: list[Settlement] = []
        self.producers: dict[str, ProducerTrackRecord] = {}
        self.ledger = GradeBondLedger()
        self._register_default_rubrics()

    def _register_default_rubrics(self):
        """Register the five default rubrics."""
        self.register_rubric(Rubric(
            rubric_id="video_evidence_quality_v1",
            name="Video Evidence Quality",
            description="Scores the strength of evidence backing in a video packet",
            dimensions=[
                RubricDimension("evidence_strength", 0.30, "How well-supported are the claims", "evidence_strength"),
                RubricDimension("source_quality", 0.20, "Quality of cited sources", "source_quality"),
                RubricDimension("claim_coverage", 0.20, "Fraction of claims with visual evidence", "claim_coverage"),
                RubricDimension("counter_evidence", 0.15, "Counter-evidence acknowledged", "counter_evidence"),
                RubricDimension("provenance_integrity", 0.15, "Provenance chain completeness", "provenance_integrity"),
            ],
            tolerance=3.0,
        ))

        self.register_rubric(Rubric(
            rubric_id="rights_safety_v1",
            name="Rights Safety",
            description="Scores the clarity and safety of rights/licenses in the packet",
            dimensions=[
                RubricDimension("rights_safety", 0.40, "Fraction of segments with safe rights", "rights_safety"),
                RubricDimension("license_clarity", 0.30, "License status is clear and documented", "license_clarity"),
                RubricDimension("copyright_clean", 0.30, "No copyright conflicts detected", "copyright_clean"),
            ],
            tolerance=2.0,
        ))

        self.register_rubric(Rubric(
            rubric_id="revenue_receipt_quality_v1",
            name="Revenue Receipt Quality",
            description="Scores the quality of revenue tracking and receipts",
            dimensions=[
                RubricDimension("revenue_receipt_quality", 0.40, "Quality of revenue receipts", "revenue_receipt_quality"),
                RubricDimension("ledger_integrity", 0.30, "Ledger chain is valid and complete", "ledger_integrity"),
                RubricDimension("payout_traceability", 0.30, "Payouts are traceable to sources", "payout_traceability"),
            ],
            tolerance=2.0,
        ))

        self.register_rubric(Rubric(
            rubric_id="machine_buyability_v1",
            name="Machine Buyability",
            description="Scores how safely a machine can query, cite, license, or buy the packet",
            dimensions=[
                RubricDimension("machine_buyability", 0.35, "Machine can parse and verify", "machine_buyability"),
                RubricDimension("license_available", 0.25, "License is available for purchase", "license_available"),
                RubricDimension("segment_granularity", 0.20, "Buyable at segment granularity", "segment_granularity"),
                RubricDimension("receipt_completeness", 0.20, "Receipts are complete and verifiable", "receipt_completeness"),
            ],
            tolerance=3.0,
        ))

        self.register_rubric(Rubric(
            rubric_id="scientific_claim_quality_v1",
            name="Scientific Claim Quality",
            description="Scores the scientific rigor of claims in the packet",
            dimensions=[
                RubricDimension("evidence_strength", 0.25, "Evidence supports claims", "evidence_strength"),
                RubricDimension("peer_review", 0.25, "Sources are peer-reviewed", "peer_review"),
                RubricDimension("reproducibility", 0.20, "Claims are reproducible", "reproducibility"),
                RubricDimension("counter_evidence", 0.15, "Counter-evidence is acknowledged", "counter_evidence"),
                RubricDimension("confidence_calibration", 0.15, "Confidence is calibrated to evidence", "confidence_calibration"),
            ],
            tolerance=3.0,
        ))

        self.register_rubric(_mcrv_rubric_v1())
        self.register_rubric(_method_provenance_safety_v1())
        self.register_rubric(_forecast_quality_v1())

    def register_rubric(self, rubric: Rubric):
        self.rubrics[rubric.rubric_id] = rubric
        self.ledger.add(
            "register_rubric",
            f"Registered rubric {rubric.rubric_id}",
            {"rubric_id": rubric.rubric_id, "dimensions": len(rubric.dimensions)},
        )

    def compute_grade(
        self,
        rubric_id: str,
        machine_scores: dict,
    ) -> float:
        """Compute a grade from machine scores using a rubric."""
        rubric = self.rubrics.get(rubric_id)
        if not rubric:
            raise ValueError(f"Unknown rubric: {rubric_id}")
        return rubric.compute_grade(machine_scores)

    def create_grade_claim(
        self,
        media_packet_id: str,
        frvo_id: str,
        rubric_id: str,
        claimed_grade: float,
        bond_amount_usd: float,
        machine_scores: dict,
        poster_id: str = "creator",
        audit_probability: float = 0.04,
        term_months: int = 12,
    ) -> GradeClaim:
        """
        Create and seal a grade claim with a bond.

        The claimed grade is asserted by the creator. The computed grade
        is calculated from machine scores. If the claimed grade exceeds
        the computed grade beyond the tolerance, the bond is at risk.
        """
        rubric = self.rubrics.get(rubric_id)
        if not rubric:
            raise ValueError(f"Unknown rubric: {rubric_id}")

        computed = rubric.compute_grade(machine_scores)
        claim_id = f"agb_{hashlib.sha256(f'{media_packet_id}{rubric_id}{time.time()}'.encode()).hexdigest()[:12]}"
        bond_id = f"bond_{hashlib.sha256(f'{claim_id}{bond_amount_usd}'.encode()).hexdigest()[:12]}"

        claim = GradeClaim(
            claim_id=claim_id,
            media_packet_id=media_packet_id,
            frvo_id=frvo_id,
            rubric_id=rubric_id,
            claimed_grade=claimed_grade,
            computed_grade=computed,
            bond_id=bond_id,
            bond_amount_usd=bond_amount_usd,
            audit_probability=audit_probability,
            tolerance=rubric.tolerance,
            status=ClaimStatus.SEALED,
            machine_scores=machine_scores,
            slash_schedule_id=self.DEFAULT_SLASH_SCHEDULE.schedule_id,
            sealed_at=time.time(),
            expires_at=time.time() + term_months * 30 * 24 * 3600,
        )

        bond = Bond(
            bond_id=bond_id,
            claim_id=claim_id,
            amount_usd=bond_amount_usd,
            posted_at=time.time(),
            poster_id=poster_id,
        )
        self.bonds.append(bond)
        claim.bond_id = bond_id

        # Record in producer track record
        if poster_id not in self.producers:
            self.producers[poster_id] = ProducerTrackRecord(producer_id=poster_id)
        self.producers[poster_id].record_claim(claim)

        receipt_data = {
            "claim_id": claim_id,
            "claimed_grade": claimed_grade,
            "computed_grade": computed,
            "bond_amount": bond_amount_usd,
            "rubric_id": rubric_id,
            "producer_tier": self.producers[poster_id].reputation_tier,
            "producer_bond_multiplier": self.producers[poster_id].bond_multiplier,
        }
        claim.receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.claims.append(claim)
        self.ledger.add(
            "seal_claim",
            f"Sealed grade claim {claim_id}: claimed={claimed_grade}, computed={computed}, bond=${bond_amount_usd}",
            receipt_data,
        )

        return claim

    def challenge_claim(
        self,
        claim: GradeClaim,
        challenger_id: str,
        reason: str,
        evidence: str,
        proposed_grade: Optional[float] = None,
    ) -> Challenge:
        """Challenge a grade claim."""
        if claim.status != ClaimStatus.SEALED:
            raise ValueError(f"Can only challenge SEALED claims, status={claim.status.value}")

        challenge_id = f"ch_{hashlib.sha256(f'{claim.claim_id}{challenger_id}{time.time()}'.encode()).hexdigest()[:12]}"

        challenge = Challenge(
            challenge_id=challenge_id,
            claim_id=claim.claim_id,
            challenger_id=challenger_id,
            reason=reason,
            evidence=evidence,
            proposed_grade=proposed_grade,
            created_at=time.time(),
        )

        claim.status = ClaimStatus.CHALLENGED
        self.challenges.append(challenge)

        self.ledger.add(
            "challenge",
            f"Challenge {challenge_id} against claim {claim.claim_id}: {reason}",
            {"challenge_id": challenge_id, "challenger": challenger_id, "reason": reason},
        )

        return challenge

    def settle_challenge(
        self,
        challenge: Challenge,
        verdict: str,
        auditor_grade: Optional[float] = None,
    ) -> Settlement:
        """
        Settle a challenge with a verdict.

        Args:
            challenge: The challenge to settle
            verdict: "UPHELD" (claim accurate), "OVERTURNED" (claim false),
                     "PARTIAL" (partially false), "DISMISSED" (challenge invalid)
            auditor_grade: The grade determined by the audit. If None, uses
                          the challenge's proposed_grade or the claim's computed_grade.
        """
        claim = next((c for c in self.claims if c.claim_id == challenge.claim_id), None)
        if not claim:
            raise ValueError(f"Claim {challenge.claim_id} not found")

        v = ChallengeVerdict(verdict)
        settlement_id = f"stl_{hashlib.sha256(f'{challenge.challenge_id}{verdict}{time.time()}'.encode()).hexdigest()[:12]}"

        # Determine the authoritative grade
        if auditor_grade is not None:
            authoritative_grade = auditor_grade
        elif challenge.proposed_grade is not None:
            authoritative_grade = challenge.proposed_grade
        else:
            authoritative_grade = claim.computed_grade

        # Calculate deviation and slash tier
        deviation = abs(claim.claimed_grade - authoritative_grade)
        slash_tier = SlashSchedule.determine_tier(deviation, claim.tolerance)

        # Determine slash based on verdict
        if v == ChallengeVerdict.UPHELD:
            slash_tier = SlashTier.NONE
            slash_amount = 0.0
            claim.status = ClaimStatus.UPHELD
        elif v == ChallengeVerdict.DISMISSED:
            slash_tier = SlashTier.NONE
            slash_amount = 0.0
            claim.status = ClaimStatus.SEALED  # Restore to sealed
        elif v == ChallengeVerdict.OVERTURNED:
            slash_amount = self.DEFAULT_SLASH_SCHEDULE.slash_amount(slash_tier, claim.bond_amount_usd)
            claim.status = ClaimStatus.SLASHED
        elif v == ChallengeVerdict.PARTIAL:
            # Partial slash: use the tier but halve it
            full_slash = self.DEFAULT_SLASH_SCHEDULE.slash_amount(slash_tier, claim.bond_amount_usd)
            slash_amount = round(full_slash / 2, 2)
            claim.status = ClaimStatus.SLASHED
        else:
            slash_amount = 0.0

        # Update bond
        bond = next((b for b in self.bonds if b.bond_id == claim.bond_id), None)
        bond_remaining = claim.bond_amount_usd
        if bond and slash_amount > 0:
            bond.slashed_amount = slash_amount
            bond.status = "SLASHED"
            bond_remaining = claim.bond_amount_usd - slash_amount

        # Challenger reward = 50% of slash
        challenger_reward = round(slash_amount * 0.5, 2)
        creator_penalty = slash_amount

        # Update challenge
        challenge.status = v
        challenge.resolved_at = time.time()
        challenge.slash_tier = slash_tier.value
        challenge.slash_amount = slash_amount

        settlement = Settlement(
            settlement_id=settlement_id,
            challenge_id=challenge.challenge_id,
            claim_id=claim.claim_id,
            verdict=v,
            slash_tier=slash_tier,
            slash_amount=slash_amount,
            bond_remaining=bond_remaining,
            challenger_reward=challenger_reward,
            creator_penalty=creator_penalty,
            timestamp=time.time(),
        )

        receipt_data = {
            "settlement_id": settlement_id,
            "verdict": v.value,
            "slash_tier": slash_tier.value,
            "slash_amount": slash_amount,
            "challenger_reward": challenger_reward,
        }
        settlement.receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.settlements.append(settlement)

        # Record settlement in producer track record
        producer = next((p for p in self.producers.values() if any(h.get("claim_id") == claim.claim_id for h in p.history)), None)
        if producer:
            producer.record_settlement(settlement)

        self.ledger.add(
            "settle",
            f"Settled challenge {challenge.challenge_id}: verdict={v.value}, slash=${slash_amount}",
            receipt_data,
        )

        return settlement

    def release_bond(self, claim: GradeClaim) -> dict:
        """Release a bond back to the poster after the claim expires unchallenged."""
        if claim.status not in (ClaimStatus.SEALED, ClaimStatus.UPHELD):
            raise ValueError(f"Can only release bonds for SEALED or UPHELD claims, status={claim.status.value}")

        bond = next((b for b in self.bonds if b.bond_id == claim.bond_id), None)
        if not bond:
            raise ValueError(f"Bond {claim.bond_id} not found")

        bond.status = "RELEASED"
        bond.released_at = time.time()

        self.ledger.add(
            "release_bond",
            f"Released bond {bond.bond_id} for claim {claim.claim_id}",
            {"bond_id": bond.bond_id, "amount": bond.amount_usd},
        )

        return {
            "bond_id": bond.bond_id,
            "released_amount": bond.amount_usd - bond.slashed_amount,
            "released_to": bond.poster_id,
            "timestamp": bond.released_at,
        }

    def create_bmma(
        self,
        claim: GradeClaim,
        media_packet: dict,
        fractional_revenue: dict,
        question: str = "",
        bea: Optional[BondedEvidenceAsset] = None,
        schema_org_object: Optional[dict] = None,
        c2pa_manifest: Optional[dict] = None,
        segment_listings: Optional[list[dict]] = None,
        marketplace_summary: Optional[dict] = None,
        provenance_hash: str = "",
    ) -> BMMA:
        """
        Create a Bonded Machine Media Asset (BMMA).

        Binds all five layers into a single financeable instrument:
            - MCRV media packet (VideoLake)
            - FRVO fractional revenue (Rights Vault)
            - SGB sealed grade bond (GradeBondProtocol)
            - BEA bonded evidence asset (generalized primitive)
            - Standards exports (Schema.org, C2PA)
            - Segment marketplace listings
        """
        bg = {
            "claimed_grade": claim.claimed_grade,
            "computed_grade": claim.computed_grade,
            "rubric_id": claim.rubric_id,
            "bond_amount": claim.bond_amount_usd,
            "audit_probability": claim.audit_probability,
            "tolerance": claim.tolerance,
            "slash_schedule_id": claim.slash_schedule_id,
            "status": claim.status.value,
            "receipt_hash": claim.receipt_hash,
            "ledger_valid": self.ledger.verify_chain(),
        }

        if bea:
            bg["required_bond"] = bea.required_bond
            bg["producer_tier"] = bea.producer_tier
            producer = self.producers.get(bea.producer_id)
            if producer:
                bg["producer_slash_rate"] = round(producer.slash_rate, 4)
                bg["producer_total_claims"] = producer.total_claims

        fr_enriched = dict(fractional_revenue)
        if result_frvo_proof := fractional_revenue.get("ledger_valid"):
            fr_enriched["ledger_valid"] = result_frvo_proof
        else:
            fr_enriched.setdefault("ledger_valid", True)

        bmma = BMMA(
            bmma_id=f"bmma_{hashlib.sha256(f'{claim.claim_id}{claim.frvo_id}{time.time()}'.encode()).hexdigest()[:12]}",
            media_packet_id=claim.media_packet_id,
            video_asset_id=claim.frvo_id,
            grade_bond_id=claim.claim_id,
            bea_id=bea.bea_id if bea else "",
            question=question,
            media_packet=media_packet,
            fractional_revenue_object=fr_enriched,
            bonded_grade=bg,
            machine_scores=claim.machine_scores,
            schema_org_object=schema_org_object or {},
            c2pa_manifest=c2pa_manifest or {},
            segment_listings=segment_listings or [],
            marketplace_summary=marketplace_summary or {},
            provenance_hash=provenance_hash,
            created_at=time.time(),
        )
        bmma.compute_hash()

        self.ledger.add(
            "create_bmma",
            f"Created BMMA {bmma.bmma_id}: bea={bmma.bea_id or 'none'}, "
            f"standards={'yes' if schema_org_object else 'no'}, "
            f"segments={len(bmma.segment_listings)}",
            {
                "bmma_id": bmma.bmma_id,
                "media_packet_id": bmma.media_packet_id,
                "video_asset_id": bmma.video_asset_id,
                "grade_bond_id": bmma.grade_bond_id,
                "bea_id": bmma.bea_id,
            },
        )

        return bmma

    def draw_audit(
        self,
        claim: GradeClaim,
        auditor_id: str = "auditor_001",
        auditor_grade: Optional[float] = None,
        force_draw: bool = False,
    ) -> AuditDraw:
        """
        Stochastically draw an audit against a sealed grade claim.

        If drawn and auditor_grade is provided, computes deviation and slash tier.
        If force_draw is True, always draws (for testing).
        """
        import random

        drawn = force_draw or random.random() < claim.audit_probability
        draw_id = f"aud_{hashlib.sha256(f'{claim.claim_id}{time.time()}'.encode()).hexdigest()[:12]}"

        audit = AuditDraw(
            draw_id=draw_id,
            claim_id=claim.claim_id,
            drawn=drawn,
            auditor_id=auditor_id if drawn else "",
            timestamp=time.time(),
        )

        if drawn and auditor_grade is not None:
            audit.auditor_grade = auditor_grade
            audit.deviation = round(abs(claim.claimed_grade - auditor_grade), 1)
            audit.slash_tier = SlashSchedule.determine_tier(audit.deviation, claim.tolerance).value

            receipt_data = {
                "draw_id": draw_id,
                "claim_id": claim.claim_id,
                "auditor_grade": auditor_grade,
                "deviation": audit.deviation,
                "slash_tier": audit.slash_tier,
            }
            audit.receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

            self.ledger.add(
                "audit_draw",
                f"Audit drawn for {claim.claim_id}: auditor_grade={auditor_grade}, deviation={audit.deviation}, tier={audit.slash_tier}",
                receipt_data,
            )

            if audit.deviation > claim.tolerance:
                challenge = self.challenge_claim(
                    claim, challenger_id=auditor_id,
                    reason=f"audit_deviation_{audit.deviation}",
                    evidence=f"auditor_grade={auditor_grade}",
                    proposed_grade=auditor_grade,
                )
                self.settle_challenge(challenge, verdict="OVERTURNED", auditor_grade=auditor_grade)

        elif drawn:
            self.ledger.add(
                "audit_draw",
                f"Audit drawn for {claim.claim_id}: no grade submitted",
                {"draw_id": draw_id, "claim_id": claim.claim_id},
            )

        return audit

    def create_bea(
        self,
        asset_type: str,
        artifact_data: bytes,
        rubric_id: str,
        claimed_grade: float,
        bond_amount_usd: float,
        machine_scores: dict,
        producer_id: str = "creator",
        audit_probability: float = 0.05,
        grade_premium: float = 0.0,
        asset_uri: str = "",
        media_packet_id: str = "",
        frvo_id: str = "",
    ) -> BondedEvidenceAsset:
        """
        Create a Bonded Evidence Asset (BEA).

        Seals the artifact hash, creates a grade claim with bond, and wraps
        everything into a BEA — the generalized financeable primitive.
        """
        artifact_hash = f"sha256:{hashlib.sha256(artifact_data).hexdigest()}"

        claim = self.create_grade_claim(
            media_packet_id=media_packet_id or f"{asset_type}_{artifact_hash[:16]}",
            frvo_id=frvo_id,
            rubric_id=rubric_id,
            claimed_grade=claimed_grade,
            bond_amount_usd=bond_amount_usd,
            machine_scores=machine_scores,
            poster_id=producer_id,
            audit_probability=audit_probability,
        )

        rubric = self.rubrics.get(rubric_id)
        grade_dims = {}
        if rubric:
            for dim in rubric.dimensions:
                raw = machine_scores.get(dim.source_field, 0.0)
                grade_dims[dim.name] = round(raw, 4)

        required = compute_required_bond(
            grade_premium=grade_premium,
            audit_probability=audit_probability,
        )

        bea = BondedEvidenceAsset(
            bea_id=f"bea_{hashlib.sha256(f'{artifact_hash}{rubric_id}{time.time()}'.encode()).hexdigest()[:12]}",
            asset_type=asset_type,
            asset_hash=artifact_hash,
            asset_uri=asset_uri,
            claimed_grade=claimed_grade,
            computed_grade=claim.computed_grade,
            rubric_id=rubric_id,
            grade_dimensions=grade_dims,
            bond_amount=bond_amount_usd,
            required_bond=required,
            audit_probability=audit_probability,
            slash_schedule_id=claim.slash_schedule_id,
            producer_id=producer_id,
            producer_tier="unproven",
            claim_id=claim.claim_id,
            receipt_hash=claim.receipt_hash,
            created_at=time.time(),
        )

        self.ledger.add(
            "create_bea",
            f"Created BEA {bea.bea_id}: type={asset_type}, grade={claimed_grade}, bond=${bond_amount_usd}",
            {
                "bea_id": bea.bea_id,
                "asset_type": asset_type,
                "asset_hash": artifact_hash[:22] + "...",
                "claim_id": claim.claim_id,
            },
        )

        return bea

    def audit_report(self) -> dict:
        """Generate an audit report of the grade bond protocol."""
        return {
            "schema": "grade_bond_audit.v1",
            "timestamp": time.time(),
            "total_rubrics": len(self.rubrics),
            "rubric_ids": list(self.rubrics.keys()),
            "total_claims": len(self.claims),
            "sealed_claims": sum(1 for c in self.claims if c.status == ClaimStatus.SEALED),
            "challenged_claims": sum(1 for c in self.claims if c.status == ClaimStatus.CHALLENGED),
            "upheld_claims": sum(1 for c in self.claims if c.status == ClaimStatus.UPHELD),
            "slashed_claims": sum(1 for c in self.claims if c.status == ClaimStatus.SLASHED),
            "total_bonded_usd": sum(c.bond_amount_usd for c in self.claims),
            "total_slashed_usd": sum(
                s.slash_amount for s in self.settlements
            ),
            "total_challenges": len(self.challenges),
            "total_settlements": len(self.settlements),
            "ledger_valid": self.ledger.verify_chain(),
            "ledger_entries": len(self.ledger.entries),
            "total_producers": len(self.producers),
            "producer_tiers": {
                pid: p.reputation_tier for pid, p in self.producers.items()
            },
        }

    def receipt(self) -> dict:
        """Generate a receipt for the protocol state."""
        data = json.dumps({
            "total_claims": len(self.claims),
            "total_bonded": sum(c.bond_amount_usd for c in self.claims),
            "ledger_valid": self.ledger.verify_chain(),
        }, sort_keys=True)

        return {
            "action": "grade_bond_protocol_state",
            "timestamp": time.time(),
            "total_claims": len(self.claims),
            "total_bonded_usd": sum(c.bond_amount_usd for c in self.claims),
            "total_slashed_usd": sum(s.slash_amount for s in self.settlements),
            "ledger_valid": self.ledger.verify_chain(),
            "receipt_hash": f"sha256:{hashlib.sha256(data.encode()).hexdigest()[:16]}",
            "ip_risk": 0,
            "secrets_exposed": 0,
        }


# ---------------------------------------------------------------------------
# Producer Track Record
# ---------------------------------------------------------------------------

@dataclass
class ProducerTrackRecord:
    """
    Tracks a producer's history of grade claims, audits, and slashes.

    Producers with high slash rates face higher required bonds.
    Producers with clean records earn lower bond requirements.
    """
    producer_id: str
    total_claims: int = 0
    total_challenged: int = 0
    total_upheld: int = 0
    total_slashed: int = 0
    total_slash_amount_usd: float = 0.0
    total_bond_posted_usd: float = 0.0
    history: list[dict] = field(default_factory=list)

    @property
    def slash_rate(self) -> float:
        if self.total_claims == 0:
            return 0.0
        return self.total_slashed / self.total_claims

    @property
    def upheld_rate(self) -> float:
        if self.total_challenged == 0:
            return 1.0
        return self.total_upheld / self.total_challenged

    @property
    def reputation_tier(self) -> str:
        sr = self.slash_rate
        if self.total_claims < 3:
            return "unproven"
        if sr == 0.0 and self.total_claims >= 10:
            return "gold"
        if sr <= 0.05:
            return "silver"
        if sr <= 0.15:
            return "bronze"
        return "penalized"

    @property
    def bond_multiplier(self) -> float:
        tier = self.reputation_tier
        if tier == "gold":
            return 0.75
        if tier == "silver":
            return 0.90
        if tier == "bronze":
            return 1.00
        if tier == "penalized":
            return 2.00
        return 1.50  # unproven

    def record_claim(self, claim: GradeClaim):
        self.total_claims += 1
        self.total_bond_posted_usd += claim.bond_amount_usd
        self.history.append({
            "claim_id": claim.claim_id,
            "status": claim.status.value,
            "bond": claim.bond_amount_usd,
            "timestamp": time.time(),
        })

    def record_settlement(self, settlement: Settlement):
        if settlement.verdict == ChallengeVerdict.UPHELD:
            self.total_upheld += 1
        elif settlement.verdict in (ChallengeVerdict.OVERTURNED, ChallengeVerdict.PARTIAL):
            self.total_slashed += 1
            self.total_slash_amount_usd += settlement.slash_amount
        self.total_challenged += 1
        self.history.append({
            "settlement_id": settlement.settlement_id,
            "verdict": settlement.verdict.value,
            "slash": settlement.slash_amount,
            "timestamp": settlement.timestamp,
        })

    def to_dict(self) -> dict:
        return {
            "producer_id": self.producer_id,
            "total_claims": self.total_claims,
            "total_challenged": self.total_challenged,
            "total_upheld": self.total_upheld,
            "total_slashed": self.total_slashed,
            "total_slash_amount_usd": round(self.total_slash_amount_usd, 2),
            "total_bond_posted_usd": round(self.total_bond_posted_usd, 2),
            "slash_rate": round(self.slash_rate, 4),
            "upheld_rate": round(self.upheld_rate, 4),
            "reputation_tier": self.reputation_tier,
            "bond_multiplier": self.bond_multiplier,
            "history": self.history,
        }


# ---------------------------------------------------------------------------
# Extension methods on GradeBondProtocol
# ---------------------------------------------------------------------------

def _method_provenance_safety_v1() -> Rubric:
    """Method Provenance Safety v1 — scores the safety of the method supply chain."""
    return Rubric(
        rubric_id="method_provenance_safety_v1",
        name="Method Provenance Safety",
        description="Scores the license safety, security, and adapter eligibility of the method supply chain",
        dimensions=[
            RubricDimension("license_safety", 0.30, "Fraction of methods with safe licenses", "license_safety"),
            RubricDimension("security_cleanliness", 0.25, "Methods are free of known security issues", "security_cleanliness"),
            RubricDimension("adapter_coverage", 0.20, "Fraction of methods with safe adapters", "adapter_coverage"),
            RubricDimension("incorporation_safety", 0.15, "No unsafe code incorporation", "incorporation_safety"),
            RubricDimension("supply_chain_traceability", 0.10, "Method lineage is traceable", "supply_chain_traceability"),
        ],
        tolerance=2.0,
    )


def _forecast_quality_v1() -> Rubric:
    """Forecast Quality v1 — scores the quality of revenue/audience forecasts."""
    return Rubric(
        rubric_id="forecast_quality_v1",
        name="Forecast Quality",
        description="Scores the rigor and calibration of revenue and audience forecasts",
        dimensions=[
            RubricDimension("forecast_basis", 0.25, "Forecast is grounded in data, not aspiration", "forecast_basis"),
            RubricDimension("calibration_history", 0.25, "Past forecasts were calibrated to outcomes", "calibration_history"),
            RubricDimension("assumption_disclosure", 0.20, "Assumptions are explicitly disclosed", "assumption_disclosure"),
            RubricDimension("scenario_coverage", 0.15, "Multiple scenarios (base/bull/bear) provided", "scenario_coverage"),
            RubricDimension("downside_disclosure", 0.15, "Downside risks are disclosed", "downside_disclosure"),
        ],
        tolerance=3.0,
    )


def _mcrv_rubric_v1() -> Rubric:
    """MCRV Grade Rubric v1 — 10 dimensions for machine-consumable research video."""
    return Rubric(
        rubric_id="mcrv_rubric_v1",
        name="MCRV Grade Rubric v1",
        description="10-dimension rubric for machine-consumable research video quality",
        dimensions=[
            RubricDimension("claim_accuracy", 0.15, "Claims are factually accurate", "claim_accuracy"),
            RubricDimension("citation_precision", 0.10, "Citations are precise and verifiable", "citation_precision"),
            RubricDimension("counterevidence_coverage", 0.10, "Counter-evidence is acknowledged", "counterevidence_coverage"),
            RubricDimension("rights_clarity", 0.10, "Rights and licenses are clear", "rights_clarity"),
            RubricDimension("provenance_completeness", 0.10, "Provenance chain is complete", "provenance_completeness"),
            RubricDimension("reproduction_strength", 0.10, "Claims are reproducible", "reproduction_strength"),
            RubricDimension("machine_parseability", 0.10, "Machine can parse and verify", "machine_parseability"),
            RubricDimension("segment_buyability", 0.10, "Segments are buyable at granularity", "segment_buyability"),
            RubricDimension("revenue_ledger_quality", 0.08, "Revenue ledger is accurate and traceable", "revenue_ledger_quality"),
            RubricDimension("method_supply_chain_safety", 0.07, "Method supply chain is license-safe", "method_supply_chain_safety"),
        ],
        tolerance=3.0,
    )


def compute_required_bond(
    grade_premium: float,
    audit_probability: float,
    producer_multiplier: float = 1.0,
) -> float:
    """
    Required Bond >= Grade Premium / Audit Probability

    grade_premium: the economic advantage of claiming a higher grade
                   (e.g. license price difference, sponsorship uplift)
    audit_probability: probability of being audited (0.0 to 1.0)
    producer_multiplier: adjustment based on producer track record

    Returns the minimum bond required to make the claim credible.
    """
    if audit_probability <= 0:
        return float("inf")
    return round((grade_premium / audit_probability) * producer_multiplier, 2)


def verify_artifact_hash(artifact_data: bytes, claimed_hash: str) -> bool:
    """Verify that an artifact's SHA-256 hash matches the claimed hash."""
    actual = f"sha256:{hashlib.sha256(artifact_data).hexdigest()}"
    return actual == claimed_hash
