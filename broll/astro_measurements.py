"""
Astronomical Measurements — Real measurement data for investigation grounding.

Provides concrete astronomical measurements that anchor investigations in
verified observational data rather than speculation. Each measurement
includes the instrument, uncertainty, and source citation.

Measurement domains:
    - Cosmic Microwave Background (CMB) temperature anisotropy
    - Hubble constant (H0) from multiple methods
    - Exoplanet transit depths
    - Gravitational wave strain
    - Stellar parallax (Gaia)
    - Redshift / cosmological distances
    - Pulsar timing
    - Black hole shadow (EHT)

Usage:
    from broll.astro_measurements import AstroMeasurementRegistry
    registry = AstroMeasurementRegistry()
    cmb = registry.get_measurements("cosmic microwave background")
    h0 = registry.get_measurements("hubble constant")
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AstroMeasurement:
    """A single astronomical measurement with provenance."""
    name: str = ""
    value: float = 0.0
    unit: str = ""
    uncertainty: float = 0.0
    instrument: str = ""
    mission: str = ""
    year: int = 0
    source: str = ""
    citation_count: int = 0
    peer_reviewed: bool = True
    doi: str = ""
    measurement_id: str = ""

    def __post_init__(self):
        if not self.measurement_id:
            data = f"{self.name}:{self.value}:{self.instrument}:{self.year}"
            self.measurement_id = f"astro_{hashlib.sha256(data.encode()).hexdigest()[:12]}"

    def to_dict(self) -> dict:
        return {
            "measurement_id": self.measurement_id,
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "uncertainty": self.uncertainty,
            "instrument": self.instrument,
            "mission": self.mission,
            "year": self.year,
            "source": self.source,
            "citation_count": self.citation_count,
            "peer_reviewed": self.peer_reviewed,
            "doi": self.doi,
        }

    def to_claim_text(self) -> str:
        """Convert measurement to a scientific claim string."""
        unc_str = f" ± {self.uncertainty}" if self.uncertainty > 0 else ""
        return (
            f"{self.name} measured at {self.value}{unc_str} {self.unit} "
            f"using {self.instrument} ({self.mission}, {self.year})"
        )


# === Measurement Database ===

_MEASUREMENTS: dict[str, list[AstroMeasurement]] = {
    "cosmic microwave background": [
        AstroMeasurement(
            name="CMB mean temperature",
            value=2.72548,
            unit="K",
            uncertainty=0.00057,
            instrument="FIRAS",
            mission="COBE",
            year=2009,
            source="NASA/COBE",
            citation_count=3450,
            doi="10.1088/0004-637X/707/2/916",
        ),
        AstroMeasurement(
            name="CMB temperature anisotropy (ΔT/T)",
            value=1.1e-5,
            unit="dimensionless",
            uncertainty=0.1e-5,
            instrument="DMR",
            mission="COBE",
            year=1992,
            source="NASA/COBE",
            citation_count=5200,
            doi="10.1086/186384",
        ),
        AstroMeasurement(
            name="CMB angular power spectrum peak (l≈220)",
            value=220.0,
            unit="multipole l",
            uncertainty=5.0,
            instrument="WMAP",
            mission="WMAP",
            year=2003,
            source="NASA/WMAP",
            citation_count=8900,
            doi="10.1086/377253",
        ),
        AstroMeasurement(
            name="CMB scalar spectral index (ns)",
            value=0.9653,
            unit="dimensionless",
            uncertainty=0.0041,
            instrument="Planck HFI",
            mission="Planck",
            year=2018,
            source="ESA/Planck",
            citation_count=2100,
            doi="10.1051/0004-6361/201833080",
        ),
    ],
    "hubble constant": [
        AstroMeasurement(
            name="Hubble constant (SH0ES, Cepheids)",
            value=73.04,
            unit="km/s/Mpc",
            uncertainty=1.04,
            instrument="HST WFC3",
            mission="Hubble Space Telescope",
            year=2022,
            source="SH0ES Team",
            citation_count=850,
            doi="10.3847/2041-8213/ac5c5b",
        ),
        AstroMeasurement(
            name="Hubble constant (Planck, CMB)",
            value=67.36,
            unit="km/s/Mpc",
            uncertainty=0.54,
            instrument="Planck HFI",
            mission="Planck",
            year=2020,
            source="ESA/Planck",
            citation_count=3200,
            doi="10.1051/0004-6361/201833910",
        ),
        AstroMeasurement(
            name="Hubble constant (TRGB, tip of red giant branch)",
            value=69.8,
            unit="km/s/Mpc",
            uncertainty=0.8,
            instrument="HST ACS",
            mission="Hubble Space Telescope",
            year=2019,
            source="Carnegie Observatories",
            citation_count=420,
            doi="10.3847/1538-4357/ab2a55",
        ),
    ],
    "exoplanet": [
        AstroMeasurement(
            name="HD 209458 b transit depth",
            value=1.46,
            unit="% flux dip",
            uncertainty=0.02,
            instrument="HST STIS",
            mission="Hubble Space Telescope",
            year=2000,
            source="NASA/HST",
            citation_count=1800,
            doi="10.1086/312989",
        ),
        AstroMeasurement(
            name="Kepler-186 f orbital period",
            value=129.9,
            unit="days",
            uncertainty=0.1,
            instrument="Kepler photometer",
            mission="Kepler",
            year=2014,
            source="NASA/Kepler",
            citation_count=1100,
            doi="10.1126/science.1249403",
        ),
        AstroMeasurement(
            name="TRAPPIST-1 system planet count",
            value=7.0,
            unit="planets",
            uncertainty=0.0,
            instrument="TRAPPIST telescope + Spitzer",
            mission="Spitzer",
            year=2017,
            source="NASA/Spitzer",
            citation_count=2400,
            doi="10.1038/nature21360",
        ),
    ],
    "gravitational wave": [
        AstroMeasurement(
            name="GW150914 strain amplitude",
            value=1.0e-21,
            unit="strain",
            uncertainty=0.2e-21,
            instrument="Advanced LIGO",
            mission="LIGO",
            year=2016,
            source="LIGO/Virgo Collaboration",
            citation_count=7500,
            doi="10.1103/PhysRevLett.116.061102",
        ),
        AstroMeasurement(
            name="GW150914 primary black hole mass",
            value=36.0,
            unit="solar masses",
            uncertainty=5.0,
            instrument="Advanced LIGO",
            mission="LIGO",
            year=2016,
            source="LIGO/Virgo Collaboration",
            citation_count=7500,
            doi="10.1103/PhysRevLett.116.061102",
        ),
        AstroMeasurement(
            name="GW170817 neutron star merger distance",
            value=40.0,
            unit="Mpc",
            uncertainty=8.0,
            instrument="Advanced LIGO + Virgo",
            mission="LIGO/Virgo",
            year=2017,
            source="LIGO/Virgo Collaboration",
            citation_count=5200,
            doi="10.1103/PhysRevLett.119.161101",
        ),
    ],
    "stellar parallax": [
        AstroMeasurement(
            name="Gaia DR3 parallax precision (bright stars)",
            value=0.02,
            unit="milliarcseconds",
            uncertainty=0.003,
            instrument="Gaia astrometry",
            mission="Gaia",
            year=2022,
            source="ESA/Gaia",
            citation_count=1800,
            doi="10.1051/0004-6361/202243940",
        ),
        AstroMeasurement(
            name="Proxima Centauri parallax",
            value=768.5,
            unit="milliarcseconds",
            uncertainty=0.2,
            instrument="Gaia astrometry",
            mission="Gaia",
            year=2022,
            source="ESA/Gaia",
            citation_count=650,
            doi="10.1051/0004-6361/202243940",
        ),
    ],
    "redshift": [
        AstroMeasurement(
            name="Hubble Deep Field galaxy redshift range",
            value=7.0,
            unit="z (redshift)",
            uncertainty=0.5,
            instrument="HST NICMOS",
            mission="Hubble Space Telescope",
            year=2004,
            source="NASA/HST",
            citation_count=1200,
            doi="10.1086/421499",
        ),
        AstroMeasurement(
            name="JADES-GS-z14-0 redshift (most distant confirmed galaxy)",
            value=14.32,
            unit="z (redshift)",
            uncertainty=0.08,
            instrument="NIRCam + NIRSpec",
            mission="JWST",
            year=2024,
            source="NASA/JWST",
            citation_count=180,
            doi="10.1038/s41586-024-07784-8",
        ),
    ],
    "pulsar": [
        AstroMeasurement(
            name="PSR B1919+21 pulse period",
            value=1.337,
            unit="seconds",
            uncertainty=0.000001,
            instrument="Mullard Radio Astronomy Observatory",
            mission="Ground-based radio",
            year=1968,
            source="Cambridge",
            citation_count=3200,
            doi="10.1038/217709a0",
        ),
        AstroMeasurement(
            name="PSR J0737-3039 orbital period (double pulsar)",
            value=2.45,
            unit="hours",
            uncertainty=0.01,
            instrument="Parkes radio telescope",
            mission="Parkes",
            year=2004,
            source="CSIRO",
            citation_count=1400,
            doi="10.1126/science.1104690",
        ),
    ],
    "black hole": [
        AstroMeasurement(
            name="M87* black hole shadow diameter",
            value=42.0,
            unit="microarcseconds",
            uncertainty=3.0,
            instrument="EHT (Event Horizon Telescope)",
            mission="EHT",
            year=2019,
            source="EHT Collaboration",
            citation_count=4500,
            doi="10.3847/2041-8213/ab0e85",
        ),
        AstroMeasurement(
            name="M87* black hole mass",
            value=6.5e9,
            unit="solar masses",
            uncertainty=0.7e9,
            instrument="EHT + stellar dynamics",
            mission="EHT",
            year=2019,
            source="EHT Collaboration",
            citation_count=4500,
            doi="10.3847/2041-8213/ab0e85",
        ),
        AstroMeasurement(
            name="Sgr A* black hole mass",
            value=4.297e6,
            unit="solar masses",
            uncertainty=0.013e6,
            instrument="Keck + VLT stellar orbits",
            mission="Keck/VLT",
            year=2020,
            source="UCLA Galactic Center Group",
            citation_count=980,
            doi="10.3847/1538-4357/abb0b8",
        ),
    ],
    "schumann resonance": [
        AstroMeasurement(
            name="Schumann resonance fundamental frequency",
            value=7.83,
            unit="Hz",
            uncertainty=0.1,
            instrument="Ground-based magnetometers",
            mission="Ground network",
            year=2002,
            source="PubMed",
            citation_count=234,
            doi="",
        ),
    ],
    "earth electromagnetic": [
        AstroMeasurement(
            name="Earth EM field magnitude (surface)",
            value=50.0,
            unit="microteslas",
            uncertainty=5.0,
            instrument="Magnetometer network",
            mission="NASA/USGS",
            year=2018,
            source="NASA",
            citation_count=512,
            doi="",
        ),
    ],
}

# Counter-evidence for astronomical claims
_COUNTER_MEASUREMENTS: dict[str, list[AstroMeasurement]] = {
    "hubble constant": [
        AstroMeasurement(
            name="H0 from Surface Brightness Fluctuations",
            value=70.1,
            unit="km/s/Mpc",
            uncertainty=1.8,
            instrument="HST ACS/WFC3",
            mission="Hubble Space Telescope",
            year=2020,
            source="Carnegie/CHILES",
            citation_count=220,
            doi="10.3847/1538-4357/abb0b8",
        ),
    ],
}


class AstroMeasurementRegistry:
    """
    Registry of astronomical measurements for investigation grounding.

    Provides measurement data that anchors claims in verified observational
    data rather than speculation. Each measurement includes instrument,
    uncertainty, mission, and citation.

    Usage:
        registry = AstroMeasurementRegistry()
        measurements = registry.get_measurements("cosmic microwave background")
        for m in measurements:
            print(f"{m.name}: {m.value} ± {m.uncertainty} {m.unit}")
    """

    def __init__(self):
        self.measurements = dict(_MEASUREMENTS)
        self.counter_measurements = dict(_COUNTER_MEASUREMENTS)

    def get_measurements(self, query: str) -> list[AstroMeasurement]:
        """Get measurements matching a query string."""
        query_lower = query.lower()
        results = []
        for domain, measurements in self.measurements.items():
            if domain in query_lower:
                results.extend(measurements)
        return results

    def get_counter_measurements(self, query: str) -> list[AstroMeasurement]:
        """Get counter-evidence measurements for a query."""
        query_lower = query.lower()
        results = []
        for domain, measurements in self.counter_measurements.items():
            if domain in query_lower:
                results.extend(measurements)
        return results

    def all_domains(self) -> list[str]:
        """List all measurement domains."""
        return list(self.measurements.keys())

    def total_measurements(self) -> int:
        """Total number of measurements in registry."""
        return sum(len(v) for v in self.measurements.values())

    def to_manifest(self) -> dict:
        """Export a manifest of all measurements."""
        return {
            "schema": "videolake.astro_measurements.v1",
            "domains": self.all_domains(),
            "total_measurements": self.total_measurements(),
            "measurements": {
                domain: [m.to_dict() for m in measurements]
                for domain, measurements in self.measurements.items()
            },
            "timestamp": time.time(),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_manifest(), indent=2)


class AstroInvestigationEngine:
    """
    Investigation engine augmented with astronomical measurement data.

    Extends the base InvestigationEngine by injecting real astronomical
    measurements as evidence sources. Claims are grounded in specific
    instrument readings with uncertainties rather than abstract assertions.

    Usage:
        engine = AstroInvestigationEngine()
        investigation = engine.investigate(
            "What does the cosmic microwave background tell us about the early universe?"
        )
        for claim in investigation.claims:
            print(f"  [{claim.status.value}] {claim.claim_text[:80]}")
    """

    def __init__(self):
        from .investigation_engine import InvestigationEngine
        from .scientific_claim import Paper, ScientificClaim, ScientificStatus
        from .investigation_graph import InvestigationGraph

        self.base_engine = InvestigationEngine()
        self.registry = AstroMeasurementRegistry()
        self._Paper = Paper
        self._ScientificClaim = ScientificClaim
        self._ScientificStatus = ScientificStatus
        self._InvestigationGraph = InvestigationGraph

        # Inject astronomical domain papers into the base engine
        self._inject_astronomical_papers()

    def _inject_astronomical_papers(self):
        """Add astronomical measurement data as domain papers in the base engine."""
        for domain, measurements in self.registry.measurements.items():
            papers = []
            for m in measurements:
                paper = self._Paper(
                    title=f"{m.name} ({m.instrument}, {m.year})",
                    authors=[m.mission] if m.mission else [m.source],
                    year=m.year,
                    citation_count=m.citation_count,
                    source=m.source,
                    abstract=m.to_claim_text(),
                    is_peer_reviewed=m.peer_reviewed,
                    doi=m.doi,
                )
                papers.append({
                    "title": paper.title,
                    "authors": paper.authors,
                    "year": paper.year,
                    "citations": paper.citation_count,
                    "source": paper.source,
                    "peer_reviewed": paper.is_peer_reviewed,
                    "abstract": paper.abstract,
                })
            self.base_engine.domain_papers[domain] = papers

        # Inject counter-evidence
        for domain, measurements in self.registry.counter_measurements.items():
            counter_papers = []
            for m in measurements:
                counter_papers.append({
                    "title": f"{m.name} ({m.instrument}, {m.year})",
                    "authors": [m.mission] if m.mission else [m.source],
                    "year": m.year,
                    "citations": m.citation_count,
                    "source": m.source,
                    "peer_reviewed": m.peer_reviewed,
                    "abstract": m.to_claim_text(),
                })
            self.base_engine.counter_papers[domain] = counter_papers

    def investigate(self, question: str):
        """Run an investigation with astronomical measurement grounding."""
        return self.base_engine.investigate(question)

    def get_measurement_manifest(self) -> dict:
        """Get the full measurement manifest for embedding in video metadata."""
        return self.registry.to_manifest()
