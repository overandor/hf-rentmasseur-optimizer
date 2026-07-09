"""
Asteroid Belt Prospector — The system at 2.8 AU that didn't exist before.

At 2.8 astronomical units from the Sun, between the inner planets (Mars at 1.5 AU)
and the gas giants (Jupiter at 5.2 AU), lies the asteroid belt — a zone of raw
fragments that never coalesced into a planet.

In this architecture:
    1.5 AU (Mars)   = Raw measurements (AstroMeasurementRegistry)
    2.8 AU (Belt)   = THIS SYSTEM — prospecting, fragment detection, tension mining
    5.2 AU (Jupiter)= Compiled video (VideoToRevenuePipeline)

The Belt Prospector scans the measurement registry for:
    - **Tensions** — same quantity measured differently by different methods
      (e.g., Hubble constant: 73.04 vs 67.36 km/s/Mpc)
    - **Anomalies** — measurements with surprising precision, unexpected values,
      or high citation-to-age ratios
    - **Discovery windows** — recent measurements (last 5 years) with low
      citation counts, indicating fresh findings not yet widely covered
    - **Controversies** — domains with counter-evidence, indicating active
      scientific disputes (high engagement potential)
    - **Cross-domain bridges** — measurements from different domains that
      constrain the same physical quantity (e.g., CMB + H0 + redshift all
      constrain cosmological models)

Each prospect is scored by:
    - Revenue potential (audience interest × controversy × freshness)
    - Evidence density (measurements per domain × citation weight)
    - Visual potential (can this be shown, not just told?)
    - Compilation speed (how fast can this become a video?)

The prospector then generates optimized questions and feeds them directly
into the VideoToRevenuePipeline, creating an autonomous loop:

    Belt → Prospect → Question → Video → Revenue → Belt (feedback)

Usage:
    from broll.belt_prospector import BeltProspector
    prospector = BeltProspector()
    prospects = prospector.prospect()
    for p in prospects:
        print(f"  [{p.prospect_type}] {p.suggested_question}")
        print(f"    Revenue score: {p.revenue_potential_score:.3f}")
        print(f"    Evidence: {p.evidence_density_score:.3f}")

    # Auto-compile the best prospect
    best = prospects[0]
    result = prospector.compile_prospect(best, compile_video=True)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from .astro_measurements import AstroMeasurement, AstroMeasurementRegistry


@dataclass
class BeltProspect:
    """
    A single prospect mined from the asteroid belt.

    A prospect is a content opportunity — a tension, anomaly, discovery,
    or controversy detected in the measurement registry that has high
    potential for video compilation and revenue generation.
    """
    prospect_id: str = ""
    prospect_type: str = ""  # tension, anomaly, discovery, controversy, bridge
    domain: str = ""
    title: str = ""
    suggested_question: str = ""
    measurements: list[AstroMeasurement] = field(default_factory=list)
    counter_measurements: list[AstroMeasurement] = field(default_factory=list)
    related_domains: list[str] = field(default_factory=list)

    # Scoring (0.0 - 1.0)
    revenue_potential_score: float = 0.0
    evidence_density_score: float = 0.0
    visual_potential_score: float = 0.0
    controversy_score: float = 0.0
    freshness_score: float = 0.0
    compilation_speed_score: float = 0.0
    overall_score: float = 0.0

    # Metadata
    detection_reason: str = ""
    estimated_revenue_usd: float = 0.0
    estimated_compile_time_sec: float = 0.0
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.prospect_id:
            data = f"{self.prospect_type}:{self.domain}:{self.title}:{time.time()}"
            self.prospect_id = f"belt_{hashlib.sha256(data.encode()).hexdigest()[:12]}"
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "prospect_id": self.prospect_id,
            "prospect_type": self.prospect_type,
            "domain": self.domain,
            "title": self.title,
            "suggested_question": self.suggested_question,
            "measurement_count": len(self.measurements),
            "counter_measurement_count": len(self.counter_measurements),
            "related_domains": self.related_domains,
            "scores": {
                "revenue_potential": round(self.revenue_potential_score, 3),
                "evidence_density": round(self.evidence_density_score, 3),
                "visual_potential": round(self.visual_potential_score, 3),
                "controversy": round(self.controversy_score, 3),
                "freshness": round(self.freshness_score, 3),
                "compilation_speed": round(self.compilation_speed_score, 3),
                "overall": round(self.overall_score, 3),
            },
            "detection_reason": self.detection_reason,
            "estimated_revenue_usd": round(self.estimated_revenue_usd, 2),
            "estimated_compile_time_sec": round(self.estimated_compile_time_sec, 2),
            "timestamp": self.timestamp,
        }


@dataclass
class BeltSurvey:
    """
    A complete survey of the asteroid belt — all prospects found in one pass.
    """
    survey_id: str = ""
    timestamp: float = 0.0
    prospects: list[BeltProspect] = field(default_factory=list)
    total_measurements_scanned: int = 0
    domains_scanned: int = 0
    tensions_found: int = 0
    anomalies_found: int = 0
    discoveries_found: int = 0
    controversies_found: int = 0
    bridges_found: int = 0
    best_prospect_id: str = ""
    best_overall_score: float = 0.0
    survey_duration_sec: float = 0.0

    def __post_init__(self):
        if not self.survey_id:
            self.survey_id = f"survey_{hashlib.sha256(str(time.time()).encode()).hexdigest()[:12]}"
        if not self.timestamp:
            self.timestamp = time.time()

    def to_dict(self) -> dict:
        return {
            "survey_id": self.survey_id,
            "timestamp": self.timestamp,
            "total_measurements_scanned": self.total_measurements_scanned,
            "domains_scanned": self.domains_scanned,
            "tensions_found": self.tensions_found,
            "anomalies_found": self.anomalies_found,
            "discoveries_found": self.discoveries_found,
            "controversies_found": self.controversies_found,
            "bridges_found": self.bridges_found,
            "best_prospect_id": self.best_prospect_id,
            "best_overall_score": round(self.best_overall_score, 3),
            "survey_duration_sec": round(self.survey_duration_sec, 4),
            "prospect_count": len(self.prospects),
            "prospects": [p.to_dict() for p in self.prospects],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def ranked_prospects(self) -> list[BeltProspect]:
        """Return prospects sorted by overall score (descending)."""
        return sorted(self.prospects, key=lambda p: p.overall_score, reverse=True)


class BeltProspector:
    """
    The Asteroid Belt Prospector — scans measurement data at 2.8 AU.

    This is the system that sits between raw astronomical measurements
    and the video-to-revenue pipeline. It prospectively mines the
    measurement registry for high-value content opportunities.

    Detection modes:
        - **Tension detection**: Same physical quantity, different methods,
          statistically significant discrepancy
        - **Anomaly detection**: Surprising precision, unexpected values,
          high citation density
        - **Discovery detection**: Recent measurements (≤5 years) with
          low citation counts (fresh, not yet widely covered)
        - **Controversy detection**: Domains with active counter-evidence
        - **Cross-domain bridge detection**: Measurements from different
          domains that constrain the same physics

    Scoring weights:
        revenue_potential:    0.25
        evidence_density:     0.20
        visual_potential:     0.15
        controversy:          0.15
        freshness:            0.10
        compilation_speed:    0.15

    Usage:
        prospector = BeltProspector()
        survey = prospector.prospect()
        print(f"Found {len(survey.prospects)} prospects")
        best = survey.ranked_prospects()[0]
        print(f"Best: {best.title} (score: {best.overall_score:.3f})")

        # Auto-compile the best prospect into a video
        result = prospector.compile_prospect(best)
        print(f"Revenue estimate: ${result.revenue.estimated_total_month_1_usd:.2f}")
    """

    # Scoring weights
    W_REVENUE = 0.25
    W_EVIDENCE = 0.20
    W_VISUAL = 0.15
    W_CONTROVERSY = 0.15
    W_FRESHNESS = 0.10
    W_COMPILE_SPEED = 0.15

    # Discovery window: measurements from last N years are "fresh"
    FRESH_YEARS = 5

    # Tension threshold: measurements must differ by >3σ to be a tension
    TENSION_SIGMA = 3.0

    def __init__(self, registry: AstroMeasurementRegistry | None = None):
        self.registry = registry or AstroMeasurementRegistry()
        self._current_year = 2026

    def prospect(self) -> BeltSurvey:
        """
        Run a full prospecting survey of the asteroid belt.

        Scans all measurement domains, detects tensions, anomalies,
        discoveries, controversies, and cross-domain bridges.

        Returns:
            BeltSurvey with all prospects ranked by overall score.
        """
        t_start = time.time()
        survey = BeltSurvey()
        survey.total_measurements_scanned = self.registry.total_measurements()
        survey.domains_scanned = len(self.registry.all_domains())

        # Run all detectors
        tensions = self._detect_tensions()
        anomalies = self._detect_anomalies()
        discoveries = self._detect_discoveries()
        controversies = self._detect_controversies()
        bridges = self._detect_bridges()

        survey.tensions_found = len(tensions)
        survey.anomalies_found = len(anomalies)
        survey.discoveries_found = len(discoveries)
        survey.controversies_found = len(controversies)
        survey.bridges_found = len(bridges)

        # Combine all prospects
        all_prospects = tensions + anomalies + discoveries + controversies + bridges

        # Score each prospect
        for p in all_prospects:
            self._score_prospect(p)

        # Sort by overall score
        all_prospects.sort(key=lambda p: p.overall_score, reverse=True)
        survey.prospects = all_prospects

        if all_prospects:
            survey.best_prospect_id = all_prospects[0].prospect_id
            survey.best_overall_score = all_prospects[0].overall_score

        survey.survey_duration_sec = time.time() - t_start
        return survey

    def _detect_tensions(self) -> list[BeltProspect]:
        """
        Detect measurement tensions — same quantity, different methods,
        statistically significant discrepancy.

        The Hubble tension is the canonical example:
            SH0ES: 73.04 ± 1.04 km/s/Mpc
            Planck: 67.36 ± 0.54 km/s/Mpc
            Difference: 5.68 km/s/Mpc (~5σ)
        """
        prospects = []

        for domain, measurements in self.registry.measurements.items():
            if len(measurements) < 2:
                continue

            # Check all pairs for tension
            for i, m1 in enumerate(measurements):
                for m2 in measurements[i + 1:]:
                    if m1.unit != m2.unit:
                        continue
                    if m1.value == 0 or m2.value == 0:
                        continue

                    diff = abs(m1.value - m2.value)
                    combined_unc = (m1.uncertainty**2 + m2.uncertainty**2) ** 0.5
                    if combined_unc == 0:
                        continue

                    sigma = diff / combined_unc

                    if sigma >= self.TENSION_SIGMA:
                        # This is a tension!
                        title = f"{domain.title()} tension: {m1.instrument} vs {m2.instrument}"
                        question = (
                            f"Why do {m1.instrument} and {m2.instrument} measure "
                            f"the {domain} differently ({m1.value} vs {m2.value} {m1.unit}), "
                            f"and what does this {sigma:.1f}σ discrepancy mean for physics?"
                        )

                        prospects.append(BeltProspect(
                            prospect_type="tension",
                            domain=domain,
                            title=title,
                            suggested_question=question,
                            measurements=[m1, m2],
                            detection_reason=(
                                f"{sigma:.1f}σ discrepancy between {m1.instrument} "
                                f"({m1.value} ± {m1.uncertainty}) and {m2.instrument} "
                                f"({m2.value} ± {m2.uncertainty})"
                            ),
                        ))

        return prospects

    def _detect_anomalies(self) -> list[BeltProspect]:
        """
        Detect measurement anomalies — surprising precision, unexpected values,
        or high citation density relative to age.
        """
        prospects = []

        for domain, measurements in self.registry.measurements.items():
            for m in measurements:
                reasons = []

                # High precision anomaly
                if m.value != 0 and m.uncertainty > 0:
                    precision_ratio = m.uncertainty / abs(m.value)
                    if precision_ratio < 1e-6:
                        reasons.append(
                            f"Extreme precision: uncertainty/value = {precision_ratio:.2e}"
                        )

                # High citation density (citations per year since publication)
                years_since = self._current_year - m.year
                if years_since > 0:
                    cite_rate = m.citation_count / years_since
                    if cite_rate > 500:
                        reasons.append(
                            f"High citation rate: {cite_rate:.0f} citations/year"
                        )

                # Very large or very small values (visually striking)
                if m.value > 1e9 or (m.value > 0 and m.value < 1e-10):
                    reasons.append(
                        f"Extreme value: {m.value} {m.unit} (visually striking)"
                    )

                if reasons:
                    question = (
                        f"What makes the {m.name} measurement from {m.instrument} "
                        f"so remarkable, and why has it been cited {m.citation_count} times?"
                    )

                    prospects.append(BeltProspect(
                        prospect_type="anomaly",
                        domain=domain,
                        title=f"Anomaly: {m.name} ({m.instrument})",
                        suggested_question=question,
                        measurements=[m],
                        detection_reason="; ".join(reasons),
                    ))

        return prospects

    def _detect_discoveries(self) -> list[BeltProspect]:
        """
        Detect fresh discoveries — measurements from the last FRESH_YEARS years
        with relatively low citation counts, indicating findings not yet
        widely covered in YouTube content.
        """
        prospects = []

        for domain, measurements in self.registry.measurements.items():
            for m in measurements:
                years_since = self._current_year - m.year

                if years_since <= self.FRESH_YEARS and years_since >= 0:
                    # Fresh measurement
                    # Low citations relative to age = undiscovered by content creators
                    expected_citations = years_since * 200  # rough benchmark
                    if m.citation_count < expected_citations:
                        freshness_factor = 1.0 - (years_since / self.FRESH_YEARS)

                        question = (
                            f"What is the significance of the {m.name} measurement "
                            f"from {m.mission} ({m.year}), and why is it important?"
                        )

                        prospects.append(BeltProspect(
                            prospect_type="discovery",
                            domain=domain,
                            title=f"Fresh discovery: {m.name} ({m.mission}, {m.year})",
                            suggested_question=question,
                            measurements=[m],
                            detection_reason=(
                                f"Published {years_since} years ago with {m.citation_count} citations "
                                f"(expected ~{expected_citations}). Freshness factor: {freshness_factor:.2f}"
                            ),
                        ))

        return prospects

    def _detect_controversies(self) -> list[BeltProspect]:
        """
        Detect active controversies — domains with counter-evidence,
        indicating ongoing scientific disputes.
        """
        prospects = []

        for domain, counter_measurements in self.registry.counter_measurements.items():
            main_measurements = self.registry.get_measurements(domain)
            if not main_measurements or not counter_measurements:
                continue

            question = (
                f"What is the controversy around {domain} measurements, "
                f"and what does the counter-evidence reveal?"
            )

            prospects.append(BeltProspect(
                prospect_type="controversy",
                domain=domain,
                title=f"Controversy: {domain} — {len(main_measurements)} measurements vs {len(counter_measurements)} counter-evidence",
                suggested_question=question,
                measurements=main_measurements,
                counter_measurements=counter_measurements,
                detection_reason=(
                    f"Active dispute: {len(main_measurements)} supporting measurements "
                    f"vs {len(counter_measurements)} counter-evidence measurements"
                ),
            ))

        return prospects

    def _detect_bridges(self) -> list[BeltProspect]:
        """
        Detect cross-domain bridges — measurements from different domains
        that constrain the same physical theory.

        Example: CMB + Hubble constant + redshift all constrain
        cosmological models (ΛCDM).
        """
        prospects = []

        # Define known bridges
        bridges = [
            {
                "name": "Cosmological model constraints",
                "domains": ["cosmic microwave background", "hubble constant", "redshift"],
                "question": (
                    "How do CMB measurements, the Hubble constant, and distant galaxy "
                    "redshifts together constrain our model of the universe?"
                ),
                "reason": "CMB + H0 + redshift all constrain ΛCDM cosmological parameters",
            },
            {
                "name": "Compact object mass scale",
                "domains": ["black hole", "gravitational wave", "pulsar"],
                "question": (
                    "What do black hole shadows, gravitational wave mergers, and pulsar "
                    "timing tell us about the mass spectrum of compact objects?"
                ),
                "reason": "BH shadows + GW mergers + pulsar timing all measure compact object masses",
            },
            {
                "name": "Distance ladder cross-checks",
                "domains": ["hubble constant", "stellar parallax", "redshift"],
                "question": (
                    "How do stellar parallax, redshift, and the Hubble constant "
                    "measurements form the cosmic distance ladder?"
                ),
                "reason": "Parallax (nearby) + H0 (intermediate) + redshift (far) = distance ladder",
            },
        ]

        for bridge in bridges:
            bridge_measurements = []
            bridge_domains = []
            for domain in bridge["domains"]:
                if domain in self.registry.measurements:
                    bridge_measurements.extend(self.registry.measurements[domain])
                    bridge_domains.append(domain)

            if len(bridge_domains) >= 2:
                prospects.append(BeltProspect(
                    prospect_type="bridge",
                    domain="cross-domain",
                    title=f"Bridge: {bridge['name']}",
                    suggested_question=bridge["question"],
                    measurements=bridge_measurements,
                    related_domains=bridge_domains,
                    detection_reason=bridge["reason"],
                ))

        return prospects

    def _score_prospect(self, p: BeltProspect):
        """Score a prospect across all dimensions."""

        # Evidence density: measurements × citations
        total_citations = sum(m.citation_count for m in p.measurements)
        p.evidence_density_score = min(1.0, len(p.measurements) / 10.0 + total_citations / 20000.0)

        # Controversy: counter-evidence + tension significance
        p.controversy_score = min(1.0, len(p.counter_measurements) * 0.3)
        if p.prospect_type == "tension":
            # Boost tension controversy
            p.controversy_score = min(1.0, p.controversy_score + 0.5)
        elif p.prospect_type == "controversy":
            p.controversy_score = min(1.0, p.controversy_score + 0.3)

        # Freshness: how recent are the measurements
        if p.measurements:
            avg_year = sum(m.year for m in p.measurements) / len(p.measurements)
            years_old = self._current_year - avg_year
            p.freshness_score = max(0.0, 1.0 - years_old / 20.0)  # 20-year half-life
        else:
            p.freshness_score = 0.0

        # Visual potential: can this be shown?
        visual_domains = ["cosmic microwave background", "black hole", "gravitational wave", "exoplanet", "redshift"]
        p.visual_potential_score = 0.3  # base
        for vd in visual_domains:
            if vd in p.domain or vd in p.related_domains:
                p.visual_potential_score = min(1.0, p.visual_potential_score + 0.3)
        if p.prospect_type == "bridge":
            p.visual_potential_score = min(1.0, p.visual_potential_score + 0.2)

        # Revenue potential: controversy × freshness × visual
        p.revenue_potential_score = (
            0.35 * p.controversy_score
            + 0.25 * p.freshness_score
            + 0.20 * p.visual_potential_score
            + 0.20 * p.evidence_density_score
        )

        # Compilation speed: simpler prospects compile faster
        if p.prospect_type == "tension":
            p.compilation_speed_score = 0.9  # clear narrative: two sides
        elif p.prospect_type == "discovery":
            p.compilation_speed_score = 0.8  # clear narrative: new finding
        elif p.prospect_type == "anomaly":
            p.compilation_speed_score = 0.7
        elif p.prospect_type == "controversy":
            p.compilation_speed_score = 0.6  # more complex
        elif p.prospect_type == "bridge":
            p.compilation_speed_score = 0.5  # most complex
        else:
            p.compilation_speed_score = 0.5

        # Overall score
        p.overall_score = (
            self.W_REVENUE * p.revenue_potential_score
            + self.W_EVIDENCE * p.evidence_density_score
            + self.W_VISUAL * p.visual_potential_score
            + self.W_CONTROVERSY * p.controversy_score
            + self.W_FRESHNESS * p.freshness_score
            + self.W_COMPILE_SPEED * p.compilation_speed_score
        )

        # Estimated revenue (rough)
        p.estimated_revenue_usd = p.revenue_potential_score * 2000.0

        # Estimated compile time (rough)
        p.estimated_compile_time_sec = (1.0 - p.compilation_speed_score) * 5.0 + 0.5

    def compile_prospect(
        self,
        prospect: BeltProspect,
        output_dir: str | None = None,
        compile_video: bool = True,
    ):
        """
        Compile a prospect into a video using the VideoToRevenuePipeline.

        Takes the prospect's suggested question and runs it through the
        full video-to-revenue pipeline.

        Returns:
            VideoToRevenueResult
        """
        from .revenue_pipeline import VideoToRevenuePipeline

        pipeline = VideoToRevenuePipeline()
        result = pipeline.run(
            question=prospect.suggested_question,
            output_dir=output_dir,
            compile_video=compile_video,
        )

        # Attach prospect metadata to the bundle
        result.bundle["belt_prospect.json"] = json.dumps(prospect.to_dict(), indent=2)

        return result

    def auto_prospect_and_compile(
        self,
        output_dir: str | None = None,
        compile_video: bool = True,
        top_n: int = 1,
    ) -> list:
        """
        Run a full survey and auto-compile the top N prospects.

        This is the autonomous loop: Belt → Prospect → Question → Video → Revenue.

        Returns:
            List of (prospect, VideoToRevenueResult) tuples for the top N.
        """
        survey = self.prospect()
        ranked = survey.ranked_prospects()[:top_n]

        results = []
        for prospect in ranked:
            result = self.compile_prospect(
                prospect,
                output_dir=output_dir,
                compile_video=compile_video,
            )
            results.append((prospect, result))

        return results
