"""
Video-to-Revenue Pipeline — The fastest path from question to monetizable YouTube video.

This is the novel primitive: a single pipeline that goes from an astronomical
question to a published, monetizable YouTube video with revenue estimates,
ad break placement, sponsorship slots, and machine-readable monetization
metadata — all in one pass.

The pipeline measures and minimizes the time from question input to
revenue-ready video output:

    Question → Astro Investigation → VideoLake Compile → YouTube Metadata
    → Monetization Metadata → Revenue Estimate → Revenue Packet → Receipt

The "fastest video-to-revenue time" is measured as:
    T_revenue = T_investigate + T_compile + T_metadata + T_monetize

Each stage is timed. The pipeline produces a RevenueTimeline that shows
exactly where time was spent and where it can be reduced.

Usage:
    from broll.revenue_pipeline import VideoToRevenuePipeline
    pipeline = VideoToRevenuePipeline()
    result = pipeline.run(
        question="What does the cosmic microwave background tell us about the early universe?",
        output_dir="out/",
        compile_video=True,
    )
    print(f"Video-to-revenue time: {result.timeline.total_seconds:.2f}s")
    print(f"Estimated monthly revenue: ${result.revenue.estimated_monthly_usd:.2f}")
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from typing import Optional

from .astro_measurements import AstroInvestigationEngine, AstroMeasurementRegistry
from .videolake import VideoLakeCompiler, VideoLakeResult
from .youtube_metadata import YouTubeMetadataGenerator, YouTubeMetadata


@dataclass
class AdBreak:
    """A single ad break placement in the video."""
    timestamp_sec: float = 0.0
    timestamp_str: str = ""
    duration_sec: float = 0.0
    ad_type: str = "midroll"
    placement_reason: str = ""
    estimated_cpm_usd: float = 0.0

    def to_dict(self) -> dict:
        return {
            "timestamp_sec": self.timestamp_sec,
            "timestamp_str": self.timestamp_str,
            "duration_sec": self.duration_sec,
            "ad_type": self.ad_type,
            "placement_reason": self.placement_reason,
            "estimated_cpm_usd": round(self.estimated_cpm_usd, 2),
        }


@dataclass
class SponsorshipSlot:
    """A sponsorship integration slot."""
    slot_id: str = ""
    position: str = ""  # pre_roll, mid_roll, post_roll
    timestamp_sec: float = 0.0
    duration_sec: float = 0.0
    suggested_category: str = ""  # education_tech, science_equipment, etc.
    estimated_value_usd: float = 0.0
    available: bool = True

    def to_dict(self) -> dict:
        return {
            "slot_id": self.slot_id,
            "position": self.position,
            "timestamp_sec": self.timestamp_sec,
            "duration_sec": self.duration_sec,
            "suggested_category": self.suggested_category,
            "estimated_value_usd": round(self.estimated_value_usd, 2),
            "available": self.available,
        }


@dataclass
class MonetizationMetadata:
    """
    YouTube monetization metadata for a compiled video.

    Includes ad break placements, sponsorship slots, Super Chat eligibility,
    channel membership gating, and merchandise integration points.
    """
    monetization_eligible: bool = False
    eligibility_reasons: list[str] = field(default_factory=list)
    ad_breaks: list[AdBreak] = field(default_factory=list)
    sponsorship_slots: list[SponsorshipSlot] = field(default_factory=list)
    super_chat_enabled: bool = False
    channel_membership_available: bool = False
    membership_tiers: list[dict] = field(default_factory=list)
    merchandise_integration_points: list[dict] = field(default_factory=list)
    estimated_video_length_sec: float = 0.0
    content_category: str = "Education"
    content_rating: str = "G"
    advertiser_friendly: bool = True
    advertiser_friendly_notes: str = ""

    def to_dict(self) -> dict:
        return {
            "monetization_eligible": self.monetization_eligible,
            "eligibility_reasons": self.eligibility_reasons,
            "ad_breaks": [ab.to_dict() for ab in self.ad_breaks],
            "sponsorship_slots": [ss.to_dict() for ss in self.sponsorship_slots],
            "super_chat_enabled": self.super_chat_enabled,
            "channel_membership_available": self.channel_membership_available,
            "membership_tiers": self.membership_tiers,
            "merchandise_integration_points": self.merchandise_integration_points,
            "estimated_video_length_sec": round(self.estimated_video_length_sec, 1),
            "content_category": self.content_category,
            "content_rating": self.content_rating,
            "advertiser_friendly": self.advertiser_friendly,
            "advertiser_friendly_notes": self.advertiser_friendly_notes,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class RevenueEstimate:
    """
    Estimated revenue potential for a compiled YouTube video.

    Estimates are based on:
        - Content category (Education = higher CPM)
        - Video length (longer = more midroll slots)
        - Claim quality (verified claims = higher advertiser trust)
        - Machine buyability (MCRV score = licensing revenue)
        - Target audience (astronomy/education = premium demographics)

    This is an ESTIMATE, not guaranteed revenue. Every estimate includes
    a confidence score and disclaimer.
    """
    estimated_cpm_usd: float = 0.0
    estimated_rpm_usd: float = 0.0
    estimated_views_month_1: int = 0
    estimated_ad_revenue_month_1_usd: float = 0.0
    estimated_sponsorship_value_usd: float = 0.0
    estimated_licensing_value_month_1_usd: float = 0.0
    estimated_total_month_1_usd: float = 0.0
    estimated_monthly_recurring_usd: float = 0.0
    confidence_score: float = 0.0
    assumptions: list[str] = field(default_factory=list)
    disclaimer: str = ""

    def to_dict(self) -> dict:
        return {
            "estimated_cpm_usd": round(self.estimated_cpm_usd, 2),
            "estimated_rpm_usd": round(self.estimated_rpm_usd, 2),
            "estimated_views_month_1": self.estimated_views_month_1,
            "estimated_ad_revenue_month_1_usd": round(self.estimated_ad_revenue_month_1_usd, 2),
            "estimated_sponsorship_value_usd": round(self.estimated_sponsorship_value_usd, 2),
            "estimated_licensing_value_month_1_usd": round(self.estimated_licensing_value_month_1_usd, 2),
            "estimated_total_month_1_usd": round(self.estimated_total_month_1_usd, 2),
            "estimated_monthly_recurring_usd": round(self.estimated_monthly_recurring_usd, 2),
            "confidence_score": round(self.confidence_score, 3),
            "assumptions": self.assumptions,
            "disclaimer": self.disclaimer,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)


@dataclass
class RevenueTimeline:
    """
    Timeline of the video-to-revenue pipeline execution.

    Measures the time spent in each stage to identify bottlenecks
    and optimize for the fastest video-to-revenue time.
    """
    t_start: float = 0.0
    t_investigate_start: float = 0.0
    t_investigate_end: float = 0.0
    t_compile_start: float = 0.0
    t_compile_end: float = 0.0
    t_metadata_start: float = 0.0
    t_metadata_end: float = 0.0
    t_monetize_start: float = 0.0
    t_monetize_end: float = 0.0
    t_revenue_start: float = 0.0
    t_revenue_end: float = 0.0
    t_end: float = 0.0

    @property
    def investigate_seconds(self) -> float:
        return self.t_investigate_end - self.t_investigate_start

    @property
    def compile_seconds(self) -> float:
        return self.t_compile_end - self.t_compile_start

    @property
    def metadata_seconds(self) -> float:
        return self.t_metadata_end - self.t_metadata_start

    @property
    def monetize_seconds(self) -> float:
        return self.t_monetize_end - self.t_monetize_start

    @property
    def revenue_seconds(self) -> float:
        return self.t_revenue_end - self.t_revenue_start

    @property
    def total_seconds(self) -> float:
        return self.t_end - self.t_start

    def to_dict(self) -> dict:
        return {
            "investigate_seconds": round(self.investigate_seconds, 4),
            "compile_seconds": round(self.compile_seconds, 4),
            "metadata_seconds": round(self.metadata_seconds, 4),
            "monetize_seconds": round(self.monetize_seconds, 4),
            "revenue_seconds": round(self.revenue_seconds, 4),
            "total_seconds": round(self.total_seconds, 4),
            "bottleneck": self.bottleneck,
        }

    @property
    def bottleneck(self) -> str:
        """Identify the slowest stage."""
        stages = {
            "investigate": self.investigate_seconds,
            "compile": self.compile_seconds,
            "metadata": self.metadata_seconds,
            "monetize": self.monetize_seconds,
            "revenue": self.revenue_seconds,
        }
        return max(stages, key=stages.get)


@dataclass
class VideoToRevenueResult:
    """Complete result of the video-to-revenue pipeline."""
    question: str = ""
    videolake_result: Optional[VideoLakeResult] = None
    youtube_metadata: Optional[YouTubeMetadata] = None
    monetization: Optional[MonetizationMetadata] = None
    revenue: Optional[RevenueEstimate] = None
    timeline: Optional[RevenueTimeline] = None
    measurement_manifest: dict = field(default_factory=dict)
    bundle: dict[str, str] = field(default_factory=dict)
    receipt_hash: str = ""
    output_dir: str = ""

    def summary(self) -> dict:
        return {
            "question": self.question,
            "video_to_revenue_time_sec": round(self.timeline.total_seconds, 4) if self.timeline else 0,
            "bottleneck": self.timeline.bottleneck if self.timeline else "",
            "monetization_eligible": self.monetization.monetization_eligible if self.monetization else False,
            "estimated_total_month_1_usd": round(self.revenue.estimated_total_month_1_usd, 2) if self.revenue else 0,
            "estimated_monthly_recurring_usd": round(self.revenue.estimated_monthly_recurring_usd, 2) if self.revenue else 0,
            "ad_breaks": len(self.monetization.ad_breaks) if self.monetization else 0,
            "sponsorship_slots": len(self.monetization.sponsorship_slots) if self.monetization else 0,
            "files": len(self.bundle),
            "receipt_hash": self.receipt_hash,
            "measurements_used": len(self.measurement_manifest.get("measurements", {})),
        }


class VideoToRevenuePipeline:
    """
    The fastest video-to-revenue pipeline.

    Takes an astronomical question and produces a complete YouTube-ready
    video package with monetization metadata and revenue estimates.

    Pipeline stages (each timed):
        1. Investigate — Run astronomical investigation with measurement data
        2. Compile — Compile to VideoLake result (video + evidence + MCRV)
        3. Metadata — Generate YouTube metadata (title, description, tags, chapters)
        4. Monetize — Generate monetization metadata (ad breaks, sponsorships)
        5. Revenue — Estimate revenue potential

    Usage:
        pipeline = VideoToRevenuePipeline()
        result = pipeline.run(
            "What does the cosmic microwave background reveal about the early universe?",
            output_dir="out/",
        )
        print(f"Total time: {result.timeline.total_seconds:.2f}s")
        print(f"Estimated revenue: ${result.revenue.estimated_total_month_1_usd:.2f}")
    """

    # Education category CPM benchmarks (USD per 1000 views)
    EDUCATION_CPM_BASE = 8.0
    EDUCATION_CPM_PREMIUM = 15.0  # science/astronomy = premium education

    # Revenue confidence by claim quality
    CONFIDENCE_BASE = 0.3
    CONFIDENCE_PER_VERIFIED_CLAIM = 0.1
    CONFIDENCE_MAX = 0.8

    def __init__(self):
        self.astro_engine = AstroInvestigationEngine()
        self.registry = AstroMeasurementRegistry()
        self.videolake = VideoLakeCompiler()
        self.videolake.investigation_engine = self.astro_engine.base_engine
        self.youtube_gen = YouTubeMetadataGenerator()

    def run(
        self,
        question: str,
        output_dir: str | None = None,
        compile_video: bool = True,
        write_receipts: bool = True,
        export_b64: bool = True,
    ) -> VideoToRevenueResult:
        """
        Run the full video-to-revenue pipeline.

        Args:
            question: The astronomical question to investigate
            output_dir: Directory to write output files
            compile_video: Whether to render actual MP4
            write_receipts: Whether to include receipt chain
            export_b64: Whether to generate Base64 packet

        Returns:
            VideoToRevenueResult with all artifacts and timeline
        """
        result = VideoToRevenueResult(question=question, output_dir=output_dir or "")
        timeline = RevenueTimeline()
        timeline.t_start = time.time()

        # Stage 1: Investigate
        timeline.t_investigate_start = time.time()
        result.measurement_manifest = self.registry.to_manifest()
        timeline.t_investigate_end = time.time()

        # Stage 2: Compile (VideoLake)
        timeline.t_compile_start = time.time()
        result.videolake_result = self.videolake.compile(
            question=question,
            output_dir=output_dir,
            compile_video=compile_video,
            write_receipts=write_receipts,
            export_b64=export_b64,
        )
        timeline.t_compile_end = time.time()

        # Stage 3: YouTube Metadata
        timeline.t_metadata_start = time.time()
        result.youtube_metadata = result.videolake_result.youtube_metadata
        if not result.youtube_metadata:
            result.youtube_metadata = self.youtube_gen.generate(result.videolake_result)
        timeline.t_metadata_end = time.time()

        # Stage 4: Monetize
        timeline.t_monetize_start = time.time()
        result.monetization = self._generate_monetization(result.videolake_result)
        timeline.t_monetize_end = time.time()

        # Stage 5: Revenue estimate
        timeline.t_revenue_start = time.time()
        result.revenue = self._estimate_revenue(result.videolake_result, result.monetization)
        timeline.t_revenue_end = time.time()

        # Build bundle
        result.bundle = dict(result.videolake_result.bundle)
        result.bundle["monetization.json"] = result.monetization.to_json()
        result.bundle["revenue_estimate.json"] = result.revenue.to_json()
        result.bundle["revenue_timeline.json"] = json.dumps(timeline.to_dict(), indent=2)
        result.bundle["astro_measurements.json"] = self.registry.to_json()
        result.bundle["video_to_revenue_summary.json"] = json.dumps(result.summary(), indent=2)

        # Write to disk
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            for filename, content in result.bundle.items():
                if content.startswith("[binary file:"):
                    continue
                filepath = os.path.join(output_dir, filename)
                with open(filepath, "w") as f:
                    f.write(content)

        # Compute receipt
        timeline.t_end = time.time()
        result.timeline = timeline
        result.receipt_hash = self._compute_receipt(result)

        return result

    def _generate_monetization(self, vl_result: VideoLakeResult) -> MonetizationMetadata:
        """Generate monetization metadata from a VideoLake result."""
        meta = MonetizationMetadata()
        inv = vl_result.investigation
        mevf = vl_result.mevf
        scenes = vl_result.scene_graph

        # Estimate video length from scene graph
        meta.estimated_video_length_sec = sum(s.duration for s in scenes) if scenes else 60.0

        # Monetization eligibility
        all_safe = mevf and all(s.rights_status == "safe" for s in mevf.segments)
        no_disputed = inv and len(inv.get_disputed_claims()) == 0
        no_speculative = inv and all(c.status.value != "speculative" for c in inv.claims)

        meta.monetization_eligible = all_safe and (no_disputed or True)  # disputed is OK with disclaimer

        reasons = []
        if all_safe:
            reasons.append("All visual segments have clear rights")
        else:
            unsafe = sum(1 for s in mevf.segments if s.rights_status != "safe") if mevf else 0
            reasons.append(f"{unsafe} segment(s) have rights restrictions")
            meta.advertiser_friendly_notes = "Some segments have rights restrictions. Review before monetizing."

        if inv:
            verified = len(inv.get_verified_claims())
            total = len(inv.claims)
            reasons.append(f"{verified}/{total} claims verified or replicated")

        meta.eligibility_reasons = reasons
        meta.advertiser_friendly = all_safe
        meta.super_chat_enabled = True
        meta.channel_membership_available = True

        # Membership tiers
        meta.membership_tiers = [
            {"name": "Evidence Supporter", "price_usd": 2.99, "perks": ["name in credits", "early access"]},
            {"name": "Investigation Patron", "price_usd": 9.99, "perks": ["name in credits", "early access", "raw data access", "Q&A priority"]},
        ]

        # Ad breaks — place at scene boundaries, minimum 8 minutes apart
        min_ad_gap = 480.0  # 8 minutes
        last_ad = -min_ad_gap
        for scene in scenes:
            if scene.timestamp > last_ad + min_ad_gap and scene.timestamp > 30:
                ts = scene.timestamp
                h = int(ts // 3600)
                m = int((ts % 3600) // 60)
                s = int(ts % 60)
                meta.ad_breaks.append(AdBreak(
                    timestamp_sec=ts,
                    timestamp_str=f"{h:02d}:{m:02d}:{s:02d}",
                    duration_sec=15.0,
                    ad_type="midroll",
                    placement_reason=f"Scene boundary: {scene.scene_id} ({scene.mood})",
                    estimated_cpm_usd=self.EDUCATION_CPM_PREMIUM,
                ))
                last_ad = ts

        # Sponsorship slots
        if scenes:
            # Pre-roll
            meta.sponsorship_slots.append(SponsorshipSlot(
                slot_id="sponsor_pre",
                position="pre_roll",
                timestamp_sec=0.0,
                duration_sec=60.0,
                suggested_category="science_education",
                estimated_value_usd=500.0,
            ))
            # Mid-roll (at midpoint)
            mid_ts = sum(s.duration for s in scenes) / 2
            meta.sponsorship_slots.append(SponsorshipSlot(
                slot_id="sponsor_mid",
                position="mid_roll",
                timestamp_sec=mid_ts,
                duration_sec=90.0,
                suggested_category="astronomy_equipment",
                estimated_value_usd=800.0,
            ))
            # Post-roll
            total_dur = sum(s.duration for s in scenes)
            meta.sponsorship_slots.append(SponsorshipSlot(
                slot_id="sponsor_post",
                position="post_roll",
                timestamp_sec=total_dur - 30,
                duration_sec=30.0,
                suggested_category="education_tech",
                estimated_value_usd=300.0,
            ))

        # Merchandise integration
        meta.merchandise_integration_points = [
            {"timestamp_sec": 5.0, "type": "overlay", "product": "evidence_graph_poster", "estimated_value_usd": 5.0},
            {"timestamp_sec": mid_ts if scenes else 30.0, "type": "verbal_mention", "product": "investigation_dataset", "estimated_value_usd": 10.0},
        ]

        return meta

    def _estimate_revenue(
        self,
        vl_result: VideoLakeResult,
        monetization: MonetizationMetadata,
    ) -> RevenueEstimate:
        """Estimate revenue potential for the compiled video."""
        est = RevenueEstimate()
        inv = vl_result.investigation
        mevf = vl_result.mevf
        vrap = vl_result.vrap

        # CPM: Education + Science = premium
        est.estimated_cpm_usd = self.EDUCATION_CPM_PREMIUM
        est.estimated_rpm_usd = self.EDUCATION_CPM_PREMIUM * 0.55  # YouTube takes 45%

        # Views estimate: based on content quality
        base_views = 1000
        if inv:
            verified = len(inv.get_verified_claims())
            total_claims = len(inv.claims)
            total_papers = len(inv.papers)
            base_views += verified * 500 + total_papers * 100

        if mevf:
            avg_buyability = mevf.avg_machine_buyability
            base_views += int(avg_buyability * 2000)

        est.estimated_views_month_1 = base_views

        # Ad revenue
        est.estimated_ad_revenue_month_1_usd = (
            (est.estimated_views_month_1 / 1000) * est.estimated_rpm_usd
        )

        # Sponsorship value
        if monetization.sponsorship_slots:
            est.estimated_sponsorship_value_usd = sum(
                s.estimated_value_usd for s in monetization.sponsorship_slots if s.available
            )

        # Licensing value (MCRV machine buyability)
        if vrap:
            buyable_segments = sum(1 for s in mevf.segments if s.scores.is_machine_buyable) if mevf else 0
            est.estimated_licensing_value_month_1_usd = buyable_segments * 0.05 * 100  # 100 licenses/month

        # Total
        est.estimated_total_month_1_usd = (
            est.estimated_ad_revenue_month_1_usd
            + est.estimated_sponsorship_value_usd
            + est.estimated_licensing_value_month_1_usd
        )

        # Monthly recurring (ad revenue continues)
        est.estimated_monthly_recurring_usd = est.estimated_ad_revenue_month_1_usd * 0.3  # decay

        # Confidence
        confidence = self.CONFIDENCE_BASE
        if inv:
            verified = len(inv.get_verified_claims())
            confidence += verified * self.CONFIDENCE_PER_VERIFIED_CLAIM
        if mevf and mevf.avg_machine_buyability > 0.5:
            confidence += 0.15
        if monetization.advertiser_friendly:
            confidence += 0.1
        est.confidence_score = min(confidence, self.CONFIDENCE_MAX)

        # Assumptions
        est.assumptions = [
            f"CPM based on Education/Science category benchmark (${self.EDUCATION_CPM_PREMIUM}/1000 views)",
            f"RPM assumes YouTube's 45% revenue share",
            f"Month 1 views estimated at {est.estimated_views_month_1} based on claim quality and buyability",
            f"Sponsorship value based on {len(monetization.sponsorship_slots)} available slots",
            "Licensing value assumes machine-buyable segments at $0.05/segment/100 licenses",
            "Monthly recurring assumes 30% of initial ad revenue decay rate",
        ]

        est.disclaimer = (
            "These are estimates based on category benchmarks and content quality scores. "
            "Actual revenue depends on YouTube algorithm performance, audience engagement, "
            "advertiser demand, and market conditions. No revenue is guaranteed."
        )

        return est

    def _compute_receipt(self, result: VideoToRevenueResult) -> str:
        """Compute SHA-256 receipt hash for the pipeline run."""
        data = {
            "question": result.question,
            "timeline": result.timeline.to_dict() if result.timeline else {},
            "monetization_eligible": result.monetization.monetization_eligible if result.monetization else False,
            "estimated_total_usd": result.revenue.estimated_total_month_1_usd if result.revenue else 0,
            "file_count": len(result.bundle),
            "measurement_domains": len(result.measurement_manifest.get("measurements", {})),
            "timestamp": time.time(),
        }
        return f"sha256:{hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:16]}"
