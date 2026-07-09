"""
VideoRights OS — Compliant fractional media-rights platform.

Videos are treated as revenue-producing rights objects. Backers can fund
production, receive perks or regulated revenue participation, and machines
can inspect, price, license, route, and purchase rights-cleared video
segments through a receipt-bearing rights ledger.

Core primitives:
    FRVO  — Fractional Revenue Video Object
    VRRU  — Video Revenue Rights Unit
    RightsLedger — tamper-evident chain of rights assignments and transfers
    PayoutSimulator — project revenue scenarios and compute participant shares
    ProofPacket — machine-readable rights proof for external verification

Usage:
    from broll.rights_vault import RightsVault
    vault = RightsVault()
    frvo = vault.create_frvo(videolake_result, offering_mode="PERK_ONLY")
    vault.add_backer(frvo, "backer_001", amount_usd=100, units=1000)
    sim = vault.simulate_payout(frvo, total_revenue=50000)
    proof = vault.generate_proof_packet(frvo)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class OfferingMode(Enum):
    PERK_ONLY = "PERK_ONLY"
    RIGHTS_RESERVATION = "RIGHTS_RESERVATION"
    REGULATED_REVENUE_SHARE = "REGULATED_REVENUE_SHARE"
    MACHINE_RIGHTS_MARKET = "MACHINE_RIGHTS_MARKET"


class OfferingStatus(Enum):
    DRAFT = "DRAFT"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PAYOUT_ACTIVE = "PAYOUT_ACTIVE"
    COMPLETED = "COMPLETED"
    LEGAL_REVIEW = "LEGAL_REVIEW"


class BackerType(Enum):
    HUMAN_PERK = "HUMAN_PERK"
    HUMAN_REVENUE = "HUMAN_REVENUE"
    MACHINE_LICENSE = "MACHINE_LICENSE"
    MACHINE_REVENUE = "MACHINE_REVENUE"


@dataclass
class RevenueSource:
    """A defined revenue stream for a video project."""
    source_id: str
    source_type: str  # youtube_ads, licensing, education, api, sponsorship, syndication
    description: str
    gross_revenue_usd: float = 0.0
    platform_fee_pct: float = 0.0
    direct_cost_usd: float = 0.0

    @property
    def net_revenue_usd(self) -> float:
        gross_after_fee = self.gross_revenue_usd * (1 - self.platform_fee_pct / 100)
        return max(gross_after_fee - self.direct_cost_usd, 0)

    def to_dict(self) -> dict:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "description": self.description,
            "gross_revenue_usd": round(self.gross_revenue_usd, 2),
            "platform_fee_pct": self.platform_fee_pct,
            "direct_cost_usd": round(self.direct_cost_usd, 2),
            "net_revenue_usd": round(self.net_revenue_usd, 2),
        }


@dataclass
class PayoutWaterfallTier:
    """A tier in the payout waterfall — sequential distribution of net revenue."""
    tier: int
    name: str
    recipient: str  # creator, backers, platform, reserve
    share_pct: float
    cap_usd: Optional[float] = None
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "tier": self.tier,
            "name": self.name,
            "recipient": self.recipient,
            "share_pct": self.share_pct,
            "cap_usd": self.cap_usd,
            "description": self.description,
        }


@dataclass
class VRRU:
    """
    Video Revenue Rights Unit.

    Each unit represents a contractual right to a defined slice
    of a defined revenue pool, not vague ownership of "the video."
    """
    unit_id: str
    project: str
    revenue_pool: str
    share_bps: float  # basis points (1 bps = 0.01%)
    term_months: int
    territory: str
    platforms: list[str]
    exclusions: list[str]
    transferability: str  # restricted, locked, transferable
    offering_exemption: str  # Reg CF, Reg D, private_contract, perk_only, machine_license
    risk_status: str  # legal_review_required, cleared, pending
    receipt_hash: str = ""
    holder_id: str = ""
    issued_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "project": self.project,
            "revenue_pool": self.revenue_pool,
            "share_bps": self.share_bps,
            "term_months": self.term_months,
            "territory": self.territory,
            "platforms": self.platforms,
            "exclusions": self.exclusions,
            "transferability": self.transferability,
            "offering_exemption": self.offering_exemption,
            "risk_status": self.risk_status,
            "receipt_hash": self.receipt_hash,
            "holder_id": self.holder_id,
            "issued_at": self.issued_at,
        }


@dataclass
class Backer:
    """A participant in the rights vault."""
    backer_id: str
    backer_type: BackerType
    amount_usd: float
    units: int
    perks: list[str] = field(default_factory=list)
    registered_at: float = 0.0
    kyc_status: str = "not_required"  # not_required, pending, verified, rejected
    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "backer_id": self.backer_id,
            "backer_type": self.backer_type.value,
            "amount_usd": round(self.amount_usd, 2),
            "units": self.units,
            "perks": self.perks,
            "registered_at": self.registered_at,
            "kyc_status": self.kyc_status,
            "receipt_hash": self.receipt_hash,
        }


@dataclass
class RightsLedgerEntry:
    """A single entry in the tamper-evident rights ledger."""
    index: int
    action: str  # create, add_backer, issue_units, transfer, payout, close
    description: str
    data: dict
    timestamp: float
    prev_hash: str
    hash: str = ""

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "action": self.action,
            "description": self.description,
            "data": self.data,
            "timestamp": self.timestamp,
            "prev_hash": self.prev_hash,
            "hash": self.hash,
        }


@dataclass
class RiskDisclosure:
    """A disclosed risk for the offering."""
    disclosure_id: str
    category: str  # platform_risk, legal_risk, revenue_risk, liquidity_risk
    description: str
    severity: str  # low, medium, high
    mitigation: str = ""

    def to_dict(self) -> dict:
        return {
            "disclosure_id": self.disclosure_id,
            "category": self.category,
            "description": self.description,
            "severity": self.severity,
            "mitigation": self.mitigation,
        }


@dataclass
class FRVO:
    """
    Fractional Revenue Video Object.

    The top-level rights object that binds a video to its revenue sources,
    fractional units, participant registry, payout waterfall, and receipts.
    """
    frvo_id: str
    video_id: str
    project_name: str
    copyright_owner: str
    offering_mode: OfferingMode
    offering_status: OfferingStatus
    revenue_sources: list[RevenueSource] = field(default_factory=list)
    fractional_units: int = 1_000_000
    units_issued: int = 0
    units_available: int = 1_000_000
    unit_price_usd: float = 0.0
    backers: list[Backer] = field(default_factory=list)
    vrrus: list[VRRU] = field(default_factory=list)
    payout_waterfall: list[PayoutWaterfallTier] = field(default_factory=list)
    rights_metadata: list[dict] = field(default_factory=list)
    risk_disclosures: list[RiskDisclosure] = field(default_factory=list)
    ledger: list[RightsLedgerEntry] = field(default_factory=list)
    machine_bid_packet: dict = field(default_factory=dict)
    created_at: float = 0.0
    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "frvo_id": self.frvo_id,
            "video_id": self.video_id,
            "project_name": self.project_name,
            "copyright_owner": self.copyright_owner,
            "offering_mode": self.offering_mode.value,
            "offering_status": self.offering_status.value,
            "revenue_sources": [r.to_dict() for r in self.revenue_sources],
            "fractional_units": self.fractional_units,
            "units_issued": self.units_issued,
            "units_available": self.units_available,
            "unit_price_usd": round(self.unit_price_usd, 4),
            "backers": [b.to_dict() for b in self.backers],
            "vrrus": [v.to_dict() for v in self.vrrus],
            "payout_waterfall": [w.to_dict() for w in self.payout_waterfall],
            "rights_metadata": self.rights_metadata,
            "risk_disclosures": [d.to_dict() for d in self.risk_disclosures],
            "ledger": [e.to_dict() if hasattr(e, 'to_dict') else e for e in self.ledger],
            "machine_bid_packet": self.machine_bid_packet,
            "created_at": self.created_at,
            "receipt_hash": self.receipt_hash,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class PayoutResult:
    """Result of a payout simulation or actual payout."""
    total_gross: float
    total_net: float
    tier_distributions: list[dict]
    backer_payouts: list[dict]
    creator_payout: float
    platform_fee: float
    reserve: float
    timestamp: float = 0.0
    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "total_gross": round(self.total_gross, 2),
            "total_net": round(self.total_net, 2),
            "tier_distributions": self.tier_distributions,
            "backer_payouts": self.backer_payouts,
            "creator_payout": round(self.creator_payout, 2),
            "platform_fee": round(self.platform_fee, 2),
            "reserve": round(self.reserve, 2),
            "timestamp": self.timestamp,
            "receipt_hash": self.receipt_hash,
        }


class RightsLedger:
    """
    Tamper-evident ledger for rights operations.

    Each entry is SHA-256 chained: hash depends on previous hash,
    making any modification detectable.
    """

    def __init__(self):
        self.entries: list[RightsLedgerEntry] = []

    def add(self, action: str, description: str, data: dict) -> RightsLedgerEntry:
        prev_hash = self.entries[-1].hash if self.entries else "0" * 64
        ts = time.time()
        index = len(self.entries)

        h = hashlib.sha256(
            f"{index}{action}{description}{json.dumps(data, sort_keys=True)}{ts}{prev_hash}".encode()
        ).hexdigest()

        entry = RightsLedgerEntry(
            index=index,
            action=action,
            description=description,
            data=data,
            timestamp=ts,
            prev_hash=prev_hash,
            hash=h,
        )
        self.entries.append(entry)
        return entry

    def verify_chain(self) -> bool:
        """Verify the entire chain is intact."""
        prev_hash = "0" * 64
        for entry in self.entries:
            if entry.prev_hash != prev_hash:
                return False
            expected = hashlib.sha256(
                f"{entry.index}{entry.action}{entry.description}"
                f"{json.dumps(entry.data, sort_keys=True)}{entry.timestamp}{entry.prev_hash}".encode()
            ).hexdigest()
            if entry.hash != expected:
                return False
            prev_hash = entry.hash
        return True

    def to_list(self) -> list[dict]:
        return [e.to_dict() for e in self.entries]


class PayoutSimulator:
    """
    Simulate revenue scenarios and compute participant payouts.

    Uses the waterfall model: revenue flows through tiers sequentially,
    each tier taking its share before the next tier receives funds.
    """

    @staticmethod
    def simulate(
        frvo: FRVO,
        total_revenue: float,
        revenue_breakdown: Optional[dict] = None,
    ) -> PayoutResult:
        """
        Simulate a payout for a given total revenue amount.

        Args:
            frvo: The FRVO to simulate payouts for
            total_revenue: Total gross revenue to distribute
            revenue_breakdown: Optional dict mapping source_type -> amount
        """
        # Calculate net revenue from sources or flat total
        if revenue_breakdown:
            for source in frvo.revenue_sources:
                if source.source_type in revenue_breakdown:
                    source.gross_revenue_usd = revenue_breakdown[source.source_type]
            total_net = sum(s.net_revenue_usd for s in frvo.revenue_sources)
        else:
            # Flat distribution: assume 30% platform fee, 5% direct costs
            platform_fee = total_revenue * 0.30
            direct_costs = total_revenue * 0.05
            total_net = total_revenue - platform_fee - direct_costs

        # Apply waterfall tiers
        tier_distributions = []
        remaining = total_net

        for tier in frvo.payout_waterfall:
            tier_amount = remaining * (tier.share_pct / 100)
            if tier.cap_usd is not None:
                tier_amount = min(tier_amount, tier.cap_usd)

            tier_distributions.append({
                "tier": tier.tier,
                "name": tier.name,
                "recipient": tier.recipient,
                "amount": round(tier_amount, 2),
                "share_pct": tier.share_pct,
            })
            remaining -= tier_amount
            if remaining <= 0:
                break

        # Compute backer payouts (pro rata based on units held)
        backer_payouts = []
        backer_pool = 0.0
        for td in tier_distributions:
            if td["recipient"] == "backers":
                backer_pool = td["amount"]
                break

        if frvo.units_issued > 0 and backer_pool > 0:
            for backer in frvo.backers:
                if backer.units > 0:
                    share = (backer.units / frvo.units_issued) * backer_pool
                    backer_payouts.append({
                        "backer_id": backer.backer_id,
                        "units": backer.units,
                        "payout_usd": round(share, 2),
                        "share_pct": round((backer.units / frvo.units_issued) * 100, 4),
                    })

        # Extract creator and platform amounts
        creator_payout = 0.0
        platform_fee = 0.0
        reserve = 0.0
        for td in tier_distributions:
            if td["recipient"] == "creator":
                creator_payout = td["amount"]
            elif td["recipient"] == "platform":
                platform_fee = td["amount"]
            elif td["recipient"] == "reserve":
                reserve = td["amount"]

        ts = time.time()
        receipt_data = {
            "frvo_id": frvo.frvo_id,
            "total_revenue": total_revenue,
            "total_net": total_net,
            "backers_paid": len(backer_payouts),
            "timestamp": ts,
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        return PayoutResult(
            total_gross=total_revenue,
            total_net=total_net,
            tier_distributions=tier_distributions,
            backer_payouts=backer_payouts,
            creator_payout=creator_payout,
            platform_fee=platform_fee,
            reserve=reserve,
            timestamp=ts,
            receipt_hash=receipt_hash,
        )


class RightsVault:
    """
    The main interface for creating and managing FRVOs.

    Creates fractional revenue video objects, manages backers,
    issues VRRUs, simulates payouts, and generates proof packets.
    """

    DEFAULT_WATERFALL = [
        PayoutWaterfallTier(1, "Platform Fee", "platform", 10, None, "Platform operational fee"),
        PayoutWaterfallTier(2, "Direct Cost Recovery", "creator", 15, None, "Recover production costs"),
        PayoutWaterfallTier(3, "Creator Share", "creator", 40, None, "Creator's base revenue share"),
        PayoutWaterfallTier(4, "Backer Pool", "backers", 30, None, "Pro rata distribution to backers"),
        PayoutWaterfallTier(5, "Reserve", "reserve", 5, None, "Contingency reserve"),
    ]

    DEFAULT_REVENUE_SOURCES = [
        RevenueSource("src_youtube", "youtube_ads", "YouTube ad revenue", 0, 45, 0),
        RevenueSource("src_premium", "youtube_premium", "YouTube Premium allocation", 0, 0, 0),
        RevenueSource("src_licensing", "licensing", "Clip and video licensing", 0, 0, 0),
        RevenueSource("src_education", "education", "Course and education licensing", 0, 0, 0),
        RevenueSource("src_api", "api", "Dataset and API access", 0, 0, 0),
        RevenueSource("src_sponsorship", "sponsorship", "Sponsorship integrations", 0, 0, 0),
        RevenueSource("src_syndication", "syndication", "Platform syndication", 0, 0, 0),
    ]

    DEFAULT_RISK_DISCLOSURES = [
        RiskDisclosure("rd_001", "platform_risk",
            "YouTube may demonetize, remove monetization, or change revenue sharing terms at any time.",
            "high", "Diversify revenue sources beyond YouTube"),
        RiskDisclosure("rd_002", "revenue_risk",
            "Revenue is not guaranteed. Video may generate less than projected or zero revenue.",
            "high", "Backers should not invest more than they can afford to lose"),
        RiskDisclosure("rd_003", "liquidity_risk",
            "Units are restricted and may not be transferable for 12+ months under Reg CF.",
            "medium", "Clear transferability terms disclosed before purchase"),
        RiskDisclosure("rd_004", "legal_risk",
            "Revenue participation may constitute a security under Howey analysis.",
            "high", "Use Reg CF, Reg D, or private contract structures with legal review"),
        RiskDisclosure("rd_005", "content_risk",
            "Content may be flagged, age-restricted, or removed for policy violations.",
            "medium", "Comply with platform policies and maintain content review"),
    ]

    def __init__(self):
        self.ledger = RightsLedger()

    def create_frvo(
        self,
        videolake_result=None,
        project_name: str = "",
        copyright_owner: str = "Creator",
        offering_mode: OfferingMode = OfferingMode.PERK_ONLY,
        fractional_units: int = 1_000_000,
        unit_price_usd: float = 0.0,
    ) -> FRVO:
        """Create a new Fractional Revenue Video Object."""
        video_id = ""
        if videolake_result:
            if videolake_result.investigation:
                video_id = videolake_result.investigation.investigation_id
            if not project_name:
                project_name = videolake_result.question[:80]

        frvo_id = f"frvo_{hashlib.sha256(f'{video_id}{time.time()}'.encode()).hexdigest()[:12]}"

        frvo = FRVO(
            frvo_id=frvo_id,
            video_id=video_id,
            project_name=project_name,
            copyright_owner=copyright_owner,
            offering_mode=offering_mode,
            offering_status=OfferingStatus.DRAFT,
            revenue_sources=[RevenueSource(
                s.source_id, s.source_type, s.description, 0, s.platform_fee_pct, 0
            ) for s in self.DEFAULT_REVENUE_SOURCES],
            fractional_units=fractional_units,
            units_available=fractional_units,
            unit_price_usd=unit_price_usd,
            payout_waterfall=[PayoutWaterfallTier(
                t.tier, t.name, t.recipient, t.share_pct, t.cap_usd, t.description
            ) for t in self.DEFAULT_WATERFALL],
            risk_disclosures=[
                RiskDisclosure(d.disclosure_id, d.category, d.description, d.severity, d.mitigation)
                for d in self.DEFAULT_RISK_DISCLOSURES
            ],
            created_at=time.time(),
        )

        # Add rights metadata from MCRV sidecar if available
        if videolake_result and videolake_result.mcrv_sidecar:
            sidecar = videolake_result.mcrv_sidecar
            for right in sidecar.rights:
                frvo.rights_metadata.append({
                    "segment_id": right.get("segment_id", ""),
                    "rights_status": right.get("rights_status", "unknown"),
                    "source": "mcrv_sidecar",
                })
            # Machine bid packet from agent purchase surface
            aps = sidecar.agent_purchase_surface
            if aps:
                frvo.machine_bid_packet = {
                    "license_available": aps.license_available,
                    "allowed_uses": aps.allowed_uses,
                    "forbidden_uses": aps.forbidden_uses,
                    "price_per_segment": aps.price_per_segment,
                    "price_full_video": aps.price_full_video,
                    "buyable_segments": aps.segment_count_buyable,
                    "total_segments": aps.segment_count_total,
                    "rights_receipt": aps.rights_receipt,
                }

        # Ledger entry
        entry = self.ledger.add(
            action="create",
            description=f"Created FRVO {frvo_id} for '{project_name}'",
            data={"frvo_id": frvo_id, "offering_mode": offering_mode.value},
        )
        frvo.ledger = self.ledger.to_list()
        frvo.receipt_hash = entry.hash

        return frvo

    def open_offering(self, frvo: FRVO) -> None:
        """Open the offering for backers."""
        frvo.offering_status = OfferingStatus.OPEN
        entry = self.ledger.add(
            action="open_offering",
            description=f"Opened offering for {frvo.frvo_id}",
            data={"frvo_id": frvo.frvo_id, "mode": frvo.offering_mode.value},
        )
        frvo.ledger = self.ledger.to_list()

    def add_backer(
        self,
        frvo: FRVO,
        backer_id: str,
        amount_usd: float,
        units: int = 0,
        backer_type: BackerType = BackerType.HUMAN_PERK,
        perks: list[str] = None,
        kyc_status: str = "not_required",
    ) -> Backer:
        """Add a backer to the FRVO."""
        if frvo.offering_status != OfferingStatus.OPEN:
            raise ValueError(f"Offering is not open (status: {frvo.offering_status.value})")

        if units == 0 and frvo.unit_price_usd > 0:
            units = int(amount_usd / frvo.unit_price_usd)

        if units > frvo.units_available:
            raise ValueError(f"Only {frvo.units_available} units available")

        # Determine KYC requirement based on mode
        if frvo.offering_mode == OfferingMode.REGULATED_REVENUE_SHARE:
            kyc_status = kyc_status if kyc_status != "not_required" else "pending"
        elif frvo.offering_mode == OfferingMode.MACHINE_RIGHTS_MARKET:
            backer_type = BackerType.MACHINE_LICENSE if backer_type == BackerType.HUMAN_PERK else backer_type

        backer = Backer(
            backer_id=backer_id,
            backer_type=backer_type,
            amount_usd=amount_usd,
            units=units,
            perks=perks or [],
            registered_at=time.time(),
            kyc_status=kyc_status,
        )

        receipt_data = {
            "backer_id": backer_id,
            "amount_usd": amount_usd,
            "units": units,
            "frvo_id": frvo.frvo_id,
        }
        backer.receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        frvo.backers.append(backer)
        frvo.units_issued += units
        frvo.units_available -= units

        # Issue VRRUs if revenue share
        if frvo.offering_mode in (OfferingMode.REGULATED_REVENUE_SHARE, OfferingMode.MACHINE_RIGHTS_MARKET):
            vrru = self._issue_vrru(frvo, backer)
            frvo.vrrus.append(vrru)

        entry = self.ledger.add(
            action="add_backer",
            description=f"Added backer {backer_id} with {units} units",
            data={"backer_id": backer_id, "units": units, "amount": amount_usd},
        )
        frvo.ledger = self.ledger.to_list()

        return backer

    def _issue_vrru(self, frvo: FRVO, backer: Backer) -> VRRU:
        """Issue a VRRU for a backer."""
        share_bps = (backer.units / frvo.fractional_units) * 10000

        exemption = "private_contract"
        if frvo.offering_mode == OfferingMode.REGULATED_REVENUE_SHARE:
            exemption = "Reg CF pending"
        elif frvo.offering_mode == OfferingMode.MACHINE_RIGHTS_MARKET:
            exemption = "machine_license"

        vrru = VRRU(
            unit_id=f"VRRU-{backer.backer_id[-6:]}",
            project=frvo.project_name,
            revenue_pool="net_receipts_after_platform_fees_and_direct_costs",
            share_bps=round(share_bps, 4),
            term_months=36,
            territory="worldwide",
            platforms=["YouTube", "licensing", "education", "API"],
            exclusions=["future unrelated works", "creator personal brand"],
            transferability="restricted",
            offering_exemption=exemption,
            risk_status="legal_review_required" if frvo.offering_mode == OfferingMode.REGULATED_REVENUE_SHARE else "cleared",
            holder_id=backer.backer_id,
            issued_at=time.time(),
        )

        receipt_data = vrru.to_dict()
        vrru.receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        return vrru

    def close_offering(self, frvo: FRVO) -> None:
        """Close the offering to new backers."""
        frvo.offering_status = OfferingStatus.CLOSED
        entry = self.ledger.add(
            action="close_offering",
            description=f"Closed offering for {frvo.frvo_id}",
            data={"frvo_id": frvo.frvo_id, "total_backers": len(frvo.backers), "total_units": frvo.units_issued},
        )
        frvo.ledger = self.ledger.to_list()

    def simulate_payout(
        self,
        frvo: FRVO,
        total_revenue: float,
        revenue_breakdown: Optional[dict] = None,
    ) -> PayoutResult:
        """Simulate a payout for a given revenue amount."""
        return PayoutSimulator.simulate(frvo, total_revenue, revenue_breakdown)

    def record_payout(self, frvo: FRVO, payout: PayoutResult) -> None:
        """Record an actual payout in the ledger."""
        frvo.offering_status = OfferingStatus.PAYOUT_ACTIVE
        entry = self.ledger.add(
            action="payout",
            description=f"Payout of ${payout.total_net:.2f} net to {len(payout.backer_payouts)} backers",
            data={
                "total_gross": payout.total_gross,
                "total_net": payout.total_net,
                "backers_paid": len(payout.backer_payouts),
                "receipt_hash": payout.receipt_hash,
            },
        )
        frvo.ledger = self.ledger.to_list()

    def generate_proof_packet(self, frvo: FRVO) -> dict:
        """
        Generate a machine-readable proof packet for external verification.

        Contains: rights status, ownership chain, payout history,
        risk disclosures, and verification hashes.
        """
        ledger_valid = self.ledger.verify_chain()

        return {
            "schema": "videorights.proof.v1",
            "frvo_id": frvo.frvo_id,
            "video_id": frvo.video_id,
            "project": frvo.project_name,
            "copyright_owner": frvo.copyright_owner,
            "offering_mode": frvo.offering_mode.value,
            "offering_status": frvo.offering_status.value,
            "rights_summary": {
                "total_units": frvo.fractional_units,
                "units_issued": frvo.units_issued,
                "units_available": frvo.units_available,
                "backers": len(frvo.backers),
                "vrrus_issued": len(frvo.vrrus),
                "revenue_sources": len(frvo.revenue_sources),
            },
            "machine_bid_packet": frvo.machine_bid_packet,
            "rights_metadata": frvo.rights_metadata,
            "risk_disclosures": [d.to_dict() for d in frvo.risk_disclosures],
            "ledger_entries": len(frvo.ledger),
            "ledger_valid": ledger_valid,
            "ledger_root_hash": frvo.ledger[-1]["hash"] if frvo.ledger else "",
            "receipt_hash": frvo.receipt_hash,
            "timestamp": time.time(),
            "proof_hash": f"sha256:{hashlib.sha256(json.dumps({
                'frvo_id': frvo.frvo_id,
                'offering_mode': frvo.offering_mode.value,
                'units_issued': frvo.units_issued,
                'backers': len(frvo.backers),
                'ledger_valid': ledger_valid,
            }, sort_keys=True).encode()).hexdigest()[:16]}",
        }

    def machine_inspect(self, frvo: FRVO) -> dict:
        """
        Machine-readable inspection of rights status.

        Answers the questions a machine buyer needs:
        - What rights exist?
        - Who owns them?
        - What revenue pool do they attach to?
        - Is resale allowed?
        - Is copyright clean?
        - What payout history exists?
        - What license price clears?
        """
        return {
            "schema": "videorights.machine_inspect.v1",
            "frvo_id": frvo.frvo_id,
            "can_parse": True,
            "can_verify": self.ledger.verify_chain(),
            "can_cite": bool(frvo.rights_metadata),
            "can_reuse": frvo.offering_mode in (
                OfferingMode.MACHINE_RIGHTS_MARKET,
                OfferingMode.PERK_ONLY,
            ),
            "can_license": frvo.machine_bid_packet.get("license_available", False),
            "can_rank": True,
            "can_route": True,
            "can_buy": frvo.offering_mode == OfferingMode.MACHINE_RIGHTS_MARKET,
            "can_compare": True,
            "rights_exist": len(frvo.rights_metadata) > 0,
            "owners_known": all(b.backer_id for b in frvo.backers),
            "revenue_pool_defined": bool(any(
                t.recipient == "backers" for t in frvo.payout_waterfall
            )),
            "resale_allowed": any(
                v.transferability == "transferable" for v in frvo.vrrus
            ),
            "copyright_clean": len(frvo.rights_metadata) > 0,
            "monetized": any(
                s.gross_revenue_usd > 0 for s in frvo.revenue_sources
            ),
            "payout_history": [
                e.to_dict() for e in self.ledger.entries if e.action == "payout"
            ],
            "license_price": frvo.machine_bid_packet.get("price_full_video", 0),
            "segment_license_price": frvo.machine_bid_packet.get("price_per_segment", 0),
            "buyable_segments": frvo.machine_bid_packet.get("buyable_segments", 0),
            "total_segments": frvo.machine_bid_packet.get("total_segments", 0),
        }
