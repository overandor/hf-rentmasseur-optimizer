"""
Segment Marketplace — query, price, license, and purchase individual evidence segments.

The machine market layer of the Bonded Machine Media Asset stack.

A normal video asks people to watch. A machine-consumable research video asks
machines to parse, cite, license, reuse, and verify. The segment marketplace
is where that machine consumption happens: agents can query for segments
matching their needs, inspect rights and evidence backing, purchase licenses,
and receive cryptographic receipts.

Architecture:

    Segment Listing → Query/Filter → Price Quote → License Purchase → Receipt

Each listing wraps a VisualEvidenceSegment with:
    - Pricing (base price, tier discounts, bulk rates)
    - License terms (allowed/forbidden uses, duration, territory)
    - Evidence backing score (claims, sources, confidence)
    - Rights safety classification
    - Machine buyability score
    - BMMA binding (if the segment belongs to a bonded asset)

Usage:
    from broll.segment_marketplace import SegmentMarketplace
    market = SegmentMarketplace()

    # Register segments from a VideoLake compilation
    market.register_segments(segments, media_packet_id="mcrv_abc",
                             frvo_id="frvo_xyz", bmma_id="bmma_001")

    # Query for segments
    results = market.query(
        min_evidence_score=0.7,
        rights_status="safe",
        claim_type="verified",
        max_price=50.0,
    )

    # Get a price quote
    quote = market.get_quote(segment_id="seg_001", buyer_id="agent_7",
                             use_case="citation")

    # Execute a license purchase
    purchase = market.purchase(quote, buyer_id="agent_7")

    # Verify the purchase receipt
    assert market.verify_purchase(purchase.purchase_id)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class LicenseTier(Enum):
    """License tier for a segment purchase."""
    CITE = "cite"              # citation/reference only
    REUSE = "reuse"            # reuse in derivative works
    EXCLUSIVE = "exclusive"    # exclusive license (no other buyers)
    COMMERCIAL = "commercial"  # commercial use license
    RESEARCH = "research"      # academic/research use only


class PurchaseStatus(Enum):
    """Status of a segment purchase."""
    PENDING = "pending"
    COMPLETED = "completed"
    REFUNDED = "refunded"
    DISPUTED = "disputed"
    REVOKED = "revoked"


@dataclass
class SegmentListing:
    """
    A marketplace listing for a single evidence segment.

    Wraps a VisualEvidenceSegment with pricing and license metadata.
    """
    listing_id: str
    segment_id: str
    media_packet_id: str = ""
    frvo_id: str = ""
    bmma_id: str = ""
    # Segment data
    claim: str = ""
    claim_type: str = "unknown"
    transcript_text: str = ""
    start_sec: float = 0.0
    end_sec: float = 0.0
    visual_concepts: list[str] = field(default_factory=list)
    # Scores
    evidence_relevance_score: float = 0.0
    truth_safety_score: float = 0.0
    semantic_match_score: float = 0.0
    machine_buyability: float = 0.0
    # Rights
    rights_status: str = "unknown"
    rights_assessment: dict | None = None
    # Pricing
    base_price_usd: float = 5.0
    currency: str = "USD"
    # License
    license_available: bool = True
    allowed_uses: list[str] = field(default_factory=lambda: ["cite", "research"])
    forbidden_uses: list[str] = field(default_factory=lambda: ["exclusive_resale"])
    # Metadata
    registered_at: float = 0.0
    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "listing_id": self.listing_id,
            "segment_id": self.segment_id,
            "media_packet_id": self.media_packet_id,
            "frvo_id": self.frvo_id,
            "bmma_id": self.bmma_id,
            "claim": self.claim,
            "claim_type": self.claim_type,
            "transcript_text": self.transcript_text[:500],
            "start_sec": self.start_sec,
            "end_sec": self.end_sec,
            "visual_concepts": self.visual_concepts,
            "evidence_relevance_score": round(self.evidence_relevance_score, 3),
            "truth_safety_score": round(self.truth_safety_score, 3),
            "semantic_match_score": round(self.semantic_match_score, 3),
            "machine_buyability": round(self.machine_buyability, 3),
            "rights_status": self.rights_status,
            "base_price_usd": round(self.base_price_usd, 2),
            "currency": self.currency,
            "license_available": self.license_available,
            "allowed_uses": self.allowed_uses,
            "forbidden_uses": self.forbidden_uses,
            "registered_at": self.registered_at,
            "receipt_hash": self.receipt_hash,
        }

    def to_compact_dict(self) -> dict:
        return {
            "listing_id": self.listing_id,
            "segment_id": self.segment_id,
            "claim": self.claim[:80],
            "claim_type": self.claim_type,
            "rights_status": self.rights_status,
            "base_price_usd": round(self.base_price_usd, 2),
            "evidence_score": round(self.evidence_relevance_score, 3),
            "license_available": self.license_available,
        }


@dataclass
class PriceQuote:
    """A price quote for a segment license."""
    quote_id: str
    listing_id: str
    segment_id: str
    buyer_id: str
    license_tier: LicenseTier
    use_case: str = ""
    price_usd: float = 0.0
    currency: str = "USD"
    valid_until: float = 0.0
    terms: dict = field(default_factory=dict)
    created_at: float = 0.0
    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "quote_id": self.quote_id,
            "listing_id": self.listing_id,
            "segment_id": self.segment_id,
            "buyer_id": self.buyer_id,
            "license_tier": self.license_tier.value,
            "use_case": self.use_case,
            "price_usd": round(self.price_usd, 2),
            "currency": self.currency,
            "valid_until": self.valid_until,
            "terms": self.terms,
            "created_at": self.created_at,
            "receipt_hash": self.receipt_hash,
        }


@dataclass
class Purchase:
    """A completed segment license purchase."""
    purchase_id: str
    quote_id: str
    listing_id: str
    segment_id: str
    buyer_id: str
    license_tier: LicenseTier
    price_paid_usd: float = 0.0
    currency: str = "USD"
    status: PurchaseStatus = PurchaseStatus.COMPLETED
    license_key: str = ""
    license_terms: dict = field(default_factory=dict)
    purchased_at: float = 0.0
    receipt_hash: str = ""
    prev_receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "purchase_id": self.purchase_id,
            "quote_id": self.quote_id,
            "listing_id": self.listing_id,
            "segment_id": self.segment_id,
            "buyer_id": self.buyer_id,
            "license_tier": self.license_tier.value,
            "price_paid_usd": round(self.price_paid_usd, 2),
            "currency": self.currency,
            "status": self.status.value,
            "license_key": self.license_key,
            "license_terms": self.license_terms,
            "purchased_at": self.purchased_at,
            "receipt_hash": self.receipt_hash,
            "prev_receipt_hash": self.prev_receipt_hash,
        }


class SegmentMarketplace:
    """
    The segment-level licensing marketplace.

    Enables machines to:
    1. Query for segments matching specific criteria
    2. Inspect evidence backing, rights status, and pricing
    3. Get price quotes for specific use cases
    4. Purchase licenses with cryptographic receipts
    5. Verify purchase history and license validity

    Pricing model:
    - CITE: 10% of base price (citation/reference)
    - RESEARCH: 25% of base price (academic use)
    - REUSE: 50% of base price (derivative works)
    - COMMERCIAL: 100% of base price (commercial use)
    - EXCLUSIVE: 300% of base price (exclusive license)

    Evidence premium: segments with higher evidence scores cost more.
    Rights discount: segments with "safe" rights get a 10% discount.
    BMMA discount: segments from bonded assets get a 5% discount (trust premium).
    """

    TIER_MULTIPLIERS = {
        LicenseTier.CITE: 0.10,
        LicenseTier.RESEARCH: 0.25,
        LicenseTier.REUSE: 0.50,
        LicenseTier.COMMERCIAL: 1.00,
        LicenseTier.EXCLUSIVE: 3.00,
    }

    def __init__(self):
        self.listings: dict[str, SegmentListing] = {}
        self.quotes: dict[str, PriceQuote] = {}
        self.purchases: dict[str, Purchase] = {}
        self._receipt_chain: list[dict] = []

    def register_segment(
        self,
        segment: dict,
        media_packet_id: str = "",
        frvo_id: str = "",
        bmma_id: str = "",
        base_price_usd: float = 5.0,
    ) -> SegmentListing:
        """Register a single segment as a marketplace listing."""
        segment_id = segment.get("segment_id", f"seg_{hashlib.sha256(json.dumps(segment, sort_keys=True).encode()).hexdigest()[:8]}")
        listing_id = f"lst_{hashlib.sha256(f'{segment_id}{time.time()}'.encode()).hexdigest()[:12]}"

        listing = SegmentListing(
            listing_id=listing_id,
            segment_id=segment_id,
            media_packet_id=media_packet_id,
            frvo_id=frvo_id,
            bmma_id=bmma_id,
            claim=segment.get("claim", ""),
            claim_type=segment.get("claim_type", "unknown"),
            transcript_text=segment.get("transcript_text", ""),
            start_sec=segment.get("start_sec", 0.0),
            end_sec=segment.get("end_sec", 0.0),
            visual_concepts=segment.get("visual_concepts", []),
            evidence_relevance_score=segment.get("evidence_relevance_score", 0.0),
            truth_safety_score=segment.get("truth_safety_score", 0.0),
            semantic_match_score=segment.get("semantic_match_score", 0.0),
            machine_buyability=segment.get("machine_buyability", 0.0),
            rights_status=segment.get("rights_status", "unknown"),
            rights_assessment=segment.get("rights_assessment"),
            base_price_usd=base_price_usd,
            license_available=segment.get("rights_status", "unknown") in ("safe", "fair_use"),
            allowed_uses=self._default_allowed_uses(segment.get("rights_status", "unknown")),
            forbidden_uses=self._default_forbidden_uses(segment.get("rights_status", "unknown")),
            registered_at=time.time(),
        )

        receipt_data = {
            "listing_id": listing_id,
            "segment_id": segment_id,
            "claim": listing.claim[:100],
            "rights_status": listing.rights_status,
        }
        listing.receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.listings[listing_id] = listing
        self._add_receipt("register_segment", f"Registered segment {segment_id}", receipt_data)
        return listing

    def register_segments(
        self,
        segments: list[dict],
        media_packet_id: str = "",
        frvo_id: str = "",
        bmma_id: str = "",
        base_price_usd: float = 5.0,
    ) -> list[SegmentListing]:
        """Register multiple segments at once."""
        return [
            self.register_segment(seg, media_packet_id, frvo_id, bmma_id, base_price_usd)
            for seg in segments
        ]

    def query(
        self,
        min_evidence_score: float = 0.0,
        max_evidence_score: float = 1.0,
        rights_status: str | None = None,
        claim_type: str | None = None,
        min_price: float = 0.0,
        max_price: float = float("inf"),
        license_available_only: bool = False,
        media_packet_id: str | None = None,
        bmma_id: str | None = None,
        visual_concept: str | None = None,
        limit: int = 50,
    ) -> list[SegmentListing]:
        """
        Query segments by criteria.

        Returns matching listings sorted by evidence score (descending).
        """
        results = []
        for listing in self.listings.values():
            if listing.evidence_relevance_score < min_evidence_score:
                continue
            if listing.evidence_relevance_score > max_evidence_score:
                continue
            if rights_status and listing.rights_status != rights_status:
                continue
            if claim_type and listing.claim_type != claim_type:
                continue
            if listing.base_price_usd < min_price:
                continue
            if listing.base_price_usd > max_price:
                continue
            if license_available_only and not listing.license_available:
                continue
            if media_packet_id and listing.media_packet_id != media_packet_id:
                continue
            if bmma_id and listing.bmma_id != bmma_id:
                continue
            if visual_concept and visual_concept not in listing.visual_concepts:
                continue
            results.append(listing)

        results.sort(key=lambda l: l.evidence_relevance_score, reverse=True)
        return results[:limit]

    def get_quote(
        self,
        listing_id: str,
        buyer_id: str,
        use_case: str = "research",
        license_tier: LicenseTier | None = None,
    ) -> PriceQuote:
        """
        Generate a price quote for a segment license.

        Pricing factors:
        - Base price × tier multiplier
        - Evidence premium: +2% per 0.1 evidence score above 0.5
        - Rights discount: -10% if rights_status == "safe"
        - BMMA trust discount: -5% if segment belongs to a bonded asset
        """
        listing = self.listings.get(listing_id)
        if not listing:
            raise ValueError(f"Listing {listing_id} not found")
        if not listing.license_available:
            raise ValueError(f"Listing {listing_id} is not available for licensing")

        # Infer tier from use case if not specified
        if license_tier is None:
            license_tier = self._infer_tier(use_case)

        # Base price
        price = listing.base_price_usd * self.TIER_MULTIPLIERS[license_tier]

        # Evidence premium
        if listing.evidence_relevance_score > 0.5:
            premium = (listing.evidence_relevance_score - 0.5) * 0.2
            price *= (1 + premium)

        # Rights discount
        if listing.rights_status == "safe":
            price *= 0.90

        # BMMA trust discount
        if listing.bmma_id:
            price *= 0.95

        price = round(max(price, 0.01), 2)

        quote_id = f"qt_{hashlib.sha256(f'{listing_id}{buyer_id}{time.time()}'.encode()).hexdigest()[:12]}"
        quote = PriceQuote(
            quote_id=quote_id,
            listing_id=listing_id,
            segment_id=listing.segment_id,
            buyer_id=buyer_id,
            license_tier=license_tier,
            use_case=use_case,
            price_usd=price,
            terms={
                "allowed_uses": listing.allowed_uses,
                "forbidden_uses": listing.forbidden_uses,
                "rights_status": listing.rights_status,
                "media_packet_id": listing.media_packet_id,
                "bmma_id": listing.bmma_id,
            },
            valid_until=time.time() + 3600,  # 1 hour
            created_at=time.time(),
        )

        receipt_data = {
            "quote_id": quote_id,
            "listing_id": listing_id,
            "price": price,
            "tier": license_tier.value,
        }
        quote.receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.quotes[quote_id] = quote
        self._add_receipt("get_quote", f"Quote {quote_id} for {buyer_id}: ${price}", receipt_data)
        return quote

    def purchase(self, quote: PriceQuote, buyer_id: str) -> Purchase:
        """Execute a segment license purchase."""
        if quote.buyer_id != buyer_id:
            raise ValueError(f"Quote {quote.quote_id} was not for buyer {buyer_id}")
        if time.time() > quote.valid_until:
            raise ValueError(f"Quote {quote.quote_id} has expired")
        if quote.quote_id not in self.quotes:
            raise ValueError(f"Quote {quote.quote_id} not found")

        listing = self.listings.get(quote.listing_id)
        if not listing:
            raise ValueError(f"Listing {quote.listing_id} not found")
        if not listing.license_available:
            raise ValueError(f"Listing {quote.listing_id} is no longer available")

        purchase_id = f"pur_{hashlib.sha256(f'{quote.quote_id}{buyer_id}{time.time()}'.encode()).hexdigest()[:12]}"
        license_key = f"lic_{hashlib.sha256(f'{purchase_id}{listing.segment_id}'.encode()).hexdigest()[:16]}"

        prev_hash = self._receipt_chain[-1]["hash"] if self._receipt_chain else "0" * 64

        purchase = Purchase(
            purchase_id=purchase_id,
            quote_id=quote.quote_id,
            listing_id=quote.listing_id,
            segment_id=quote.segment_id,
            buyer_id=buyer_id,
            license_tier=quote.license_tier,
            price_paid_usd=quote.price_usd,
            license_key=license_key,
            license_terms=quote.terms,
            purchased_at=time.time(),
            prev_receipt_hash=prev_hash,
        )

        receipt_data = {
            "purchase_id": purchase_id,
            "segment_id": quote.segment_id,
            "buyer_id": buyer_id,
            "price": quote.price_usd,
            "tier": quote.license_tier.value,
            "license_key": license_key,
        }
        purchase.receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        # If exclusive, mark listing as no longer available
        if quote.license_tier == LicenseTier.EXCLUSIVE:
            listing.license_available = False

        self.purchases[purchase_id] = purchase
        self._add_receipt("purchase", f"Purchase {purchase_id}: {buyer_id} licensed segment {quote.segment_id} for ${quote.price_usd}", receipt_data)
        return purchase

    def verify_purchase(self, purchase_id: str) -> bool:
        """Verify a purchase receipt against the chain."""
        purchase = self.purchases.get(purchase_id)
        if not purchase:
            return False

        receipt_data = {
            "purchase_id": purchase_id,
            "segment_id": purchase.segment_id,
            "buyer_id": purchase.buyer_id,
            "price": purchase.price_paid_usd,
            "tier": purchase.license_tier.value,
            "license_key": purchase.license_key,
        }
        expected_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"
        return purchase.receipt_hash == expected_hash

    def get_license(self, purchase_id: str) -> dict | None:
        """Retrieve license details for a purchase."""
        purchase = self.purchases.get(purchase_id)
        if not purchase:
            return None
        listing = self.listings.get(purchase.listing_id)
        return {
            "license_key": purchase.license_key,
            "segment_id": purchase.segment_id,
            "buyer_id": purchase.buyer_id,
            "license_tier": purchase.license_tier.value,
            "price_paid": purchase.price_paid_usd,
            "status": purchase.status.value,
            "terms": purchase.license_terms,
            "claim": listing.claim if listing else "",
            "transcript_excerpt": listing.transcript_text[:200] if listing else "",
            "purchased_at": purchase.purchased_at,
            "receipt_hash": purchase.receipt_hash,
        }

    def buyer_history(self, buyer_id: str) -> list[dict]:
        """Get purchase history for a buyer."""
        return [
            p.to_dict() for p in self.purchases.values()
            if p.buyer_id == buyer_id
        ]

    def market_summary(self) -> dict:
        """Generate a summary of the marketplace state."""
        total_listings = len(self.listings)
        available = sum(1 for l in self.listings.values() if l.license_available)
        by_rights = {}
        by_claim_type = {}
        for l in self.listings.values():
            by_rights[l.rights_status] = by_rights.get(l.rights_status, 0) + 1
            by_claim_type[l.claim_type] = by_claim_type.get(l.claim_type, 0) + 1

        total_revenue = sum(p.price_paid_usd for p in self.purchases.values() if p.status == PurchaseStatus.COMPLETED)
        total_purchases = len(self.purchases)

        return {
            "schema": "segment_marketplace_summary_v1",
            "timestamp": time.time(),
            "total_listings": total_listings,
            "available_listings": available,
            "total_purchases": total_purchases,
            "total_revenue_usd": round(total_revenue, 2),
            "by_rights_status": by_rights,
            "by_claim_type": by_claim_type,
            "avg_evidence_score": round(
                sum(l.evidence_relevance_score for l in self.listings.values()) / max(total_listings, 1), 3
            ),
            "avg_price": round(
                sum(l.base_price_usd for l in self.listings.values()) / max(total_listings, 1), 2
            ),
            "receipt_chain_valid": self._verify_chain(),
            "receipt_chain_length": len(self._receipt_chain),
        }

    def _infer_tier(self, use_case: str) -> LicenseTier:
        """Infer license tier from use case."""
        uc = use_case.lower()
        if "cite" in uc or "citation" in uc or "reference" in uc:
            return LicenseTier.CITE
        if "research" in uc or "academic" in uc or "education" in uc:
            return LicenseTier.RESEARCH
        if "commercial" in uc or "monetize" in uc:
            return LicenseTier.COMMERCIAL
        if "exclusive" in uc:
            return LicenseTier.EXCLUSIVE
        if "reuse" in uc or "derivative" in uc or "remix" in uc:
            return LicenseTier.REUSE
        return LicenseTier.RESEARCH

    def _default_allowed_uses(self, rights_status: str) -> list[str]:
        if rights_status == "safe":
            return ["cite", "research", "reuse", "commercial"]
        if rights_status == "fair_use":
            return ["cite", "research"]
        return ["cite"]

    def _default_forbidden_uses(self, rights_status: str) -> list[str]:
        if rights_status == "safe":
            return ["exclusive_resale_without_license"]
        if rights_status == "fair_use":
            return ["commercial", "exclusive_resale", "derivative_without_attribution"]
        return ["commercial", "reuse", "exclusive_resale", "derivative"]

    def _add_receipt(self, action: str, description: str, data: dict) -> dict:
        """Add a tamper-evident receipt entry."""
        prev_hash = self._receipt_chain[-1]["hash"] if self._receipt_chain else "0" * 64
        ts = time.time()
        index = len(self._receipt_chain)
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
        self._receipt_chain.append(entry)
        return entry

    def _verify_chain(self) -> bool:
        """Verify the receipt chain integrity."""
        prev_hash = "0" * 64
        for entry in self._receipt_chain:
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

    def export_receipts(self) -> list[dict]:
        """Export the full receipt chain."""
        return list(self._receipt_chain)
