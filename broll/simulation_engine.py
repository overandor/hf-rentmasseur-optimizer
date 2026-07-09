"""
Simulation Engine — Generates animation descriptions for invisible systems.

Many claims refer to phenomena that cannot be directly filmed:
    - energy fields
    - money flows
    - supply chains
    - neural networks
    - distributed computing
    - planetary systems
    - electromagnetic fields
    - resonance patterns

The Simulation Engine generates structured animation descriptions that
can be rendered by a visualization tool or motion graphics system.

This is NOT actual rendering. It is the specification layer — the system
describes WHAT animation should be created, not how to render it.

Output format:
    {
        "simulation_id": "...",
        "concept": "planetary resonance",
        "animation_type": "wave_field",
        "description": "Animated wave pattern emanating from Earth's surface...",
        "visual_elements": [...],
        "duration_seconds": 5.0,
        "style": "scientific_documentary",
        "narration_sync": "show during claim about resonance",
    }
"""

import hashlib
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SimulationSpec:
    """Specification for a generated animation/visualization."""
    simulation_id: str
    concept: str
    animation_type: str
    description: str
    visual_elements: list[str] = field(default_factory=list)
    duration_seconds: float = 5.0
    style: str = "scientific_documentary"
    narration_sync: str = ""
    color_palette: list[str] = field(default_factory=list)
    motion_pattern: str = ""
    overlay_text: list[str] = field(default_factory=list)
    confidence: float = 0.5  # How well this simulation represents the concept

    def to_dict(self) -> dict:
        return {
            "simulation_id": self.simulation_id,
            "concept": self.concept,
            "animation_type": self.animation_type,
            "description": self.description,
            "visual_elements": self.visual_elements,
            "duration_seconds": self.duration_seconds,
            "style": self.style,
            "narration_sync": self.narration_sync,
            "color_palette": self.color_palette,
            "motion_pattern": self.motion_pattern,
            "overlay_text": self.overlay_text,
            "confidence": self.confidence,
        }


# Animation type templates for different concept domains
_SIMULATION_TEMPLATES: dict[str, dict] = {
    "resonance": {
        "animation_type": "standing_wave",
        "description": "Standing wave pattern on a circular surface, showing nodes and antinodes vibrating at resonant frequency",
        "visual_elements": ["circular membrane", "wave nodes", "frequency indicator", "amplitude bars"],
        "color_palette": ["deep blue", "cyan", "white"],
        "motion_pattern": "radial standing wave with pulsing amplitude",
        "overlay_text": ["frequency: 7.83 Hz", "resonance pattern"],
    },
    "frequency": {
        "animation_type": "waveform",
        "description": "Oscilloscope-style waveform showing frequency oscillation with labeled peaks",
        "visual_elements": ["waveform line", "frequency axis", "amplitude axis", "peak markers"],
        "color_palette": ["green", "black", "white"],
        "motion_pattern": "left-to-right scrolling waveform",
        "overlay_text": ["frequency spectrum", "Hz"],
    },
    "energy": {
        "animation_type": "field_visualization",
        "description": "Electromagnetic field lines emanating from a central source, with energy flow particles",
        "visual_elements": ["field lines", "energy particles", "source object", "field strength indicator"],
        "color_palette": ["purple", "blue", "white"],
        "motion_pattern": "pulsing field lines with flowing particles",
        "overlay_text": ["energy field", "field strength"],
    },
    "earth": {
        "animation_type": "globe_overlay",
        "description": "3D Earth globe with electromagnetic field lines wrapping around the surface",
        "visual_elements": ["Earth globe", "magnetic field lines", "atmosphere glow", "grid overlay"],
        "color_palette": ["blue", "green", "white", "orange"],
        "motion_pattern": "slowly rotating globe with pulsing field lines",
        "overlay_text": ["Earth electromagnetic field", "geomagnetic"],
    },
    "megalithic": {
        "animation_type": "alignment_diagram",
        "description": "Top-down diagram of stone circle with solar/lunar alignment lines showing astronomical positioning",
        "visual_elements": ["stone circle", "alignment lines", "sun/moon path", "cardinal directions"],
        "color_palette": ["stone gray", "golden yellow", "dark blue"],
        "motion_pattern": "animated sun arc with alignment highlights",
        "overlay_text": ["solar alignment", "astronomical positioning"],
    },
    "cave": {
        "animation_type": "cross_section",
        "description": "Cross-section animation of cave structure showing water flow, light penetration, and acoustic properties",
        "visual_elements": ["cave cross-section", "water flow", "light rays", "sound wave overlay"],
        "color_palette": ["brown", "blue", "yellow"],
        "motion_pattern": "flowing water with pulsing light and sound waves",
        "overlay_text": ["cave acoustics", "water flow"],
    },
    "solar": {
        "animation_type": "solar_arc",
        "description": "Animated sun arc over ancient structure showing alignment during solstice",
        "visual_elements": ["sun", "structure silhouette", "horizon line", "shadow projection"],
        "color_palette": ["golden", "orange", "dark blue", "gray"],
        "motion_pattern": "sun rising in arc with moving shadow",
        "overlay_text": ["solstice alignment", "solar position"],
    },
    "network": {
        "animation_type": "network_graph",
        "description": "Network graph showing nodes and connections with data flowing between them",
        "visual_elements": ["network nodes", "connection lines", "data packets", "node labels"],
        "color_palette": ["cyan", "blue", "white"],
        "motion_pattern": "pulsing nodes with flowing data packets",
        "overlay_text": ["network topology", "data flow"],
    },
    "money": {
        "animation_type": "flow_diagram",
        "description": "Sankey-style flow diagram showing money moving between entities",
        "visual_elements": ["flow arrows", "entity boxes", "amount labels", "time axis"],
        "color_palette": ["green", "red", "gray"],
        "motion_pattern": "flowing arrows with changing amounts",
        "overlay_text": ["capital flow", "transaction volume"],
    },
    "neural": {
        "animation_type": "neural_network",
        "description": "Neural network visualization with layers, neurons, and activation signals",
        "visual_elements": ["neuron nodes", "layer connections", "activation pulses", "layer labels"],
        "color_palette": ["purple", "blue", "white"],
        "motion_pattern": "forward propagation with pulsing activations",
        "overlay_text": ["neural network", "activation function"],
    },
    "climate": {
        "animation_type": "temperature_map",
        "description": "Global temperature anomaly map with time progression",
        "visual_elements": ["world map", "temperature gradient", "time slider", "anomaly scale"],
        "color_palette": ["blue", "white", "orange", "red"],
        "motion_pattern": "time-sequenced temperature changes",
        "overlay_text": ["temperature anomaly", "year"],
    },
    "supply_chain": {
        "animation_type": "logistics_flow",
        "description": "Supply chain flow showing materials moving from source to factory to distribution",
        "visual_elements": ["factory icons", "transport arrows", "inventory bars", "location map"],
        "color_palette": ["blue", "green", "orange"],
        "motion_pattern": "flowing materials with inventory changes",
        "overlay_text": ["supply chain", "inventory level"],
    },
}


class SimulationEngine:
    """
    Generates animation specifications for invisible systems.

    For concepts that cannot be directly filmed (energy fields, resonance,
    money flows, neural networks), this engine produces structured
    animation descriptions that a rendering system can use.

    Usage:
        engine = SimulationEngine()
        sim = engine.generate_for_concept("resonance", "planetary resonance at 7.83 Hz")
        print(sim.description)
    """

    def __init__(self):
        self.templates = dict(_SIMULATION_TEMPLATES)

    def generate_for_concept(
        self,
        concept: str,
        context: str = "",
        duration: float = 5.0,
        style: str = "scientific_documentary",
    ) -> SimulationSpec:
        """
        Generate a simulation specification for a concept.

        Args:
            concept: The concept to visualize (resonance, energy, etc.)
            context: Additional context from the narration
            duration: Animation duration in seconds
            style: Visual style (scientific_documentary, infographic, cinematic, etc.)

        Returns:
            SimulationSpec with animation description
        """
        concept_lower = concept.lower()

        # Find matching template
        template = None
        for key, tmpl in self.templates.items():
            if key in concept_lower:
                template = tmpl
                break

        if not template:
            # Generate a generic simulation
            return self._generate_generic(concept, context, duration, style)

        sim_id = hashlib.sha256(
            f"{concept}:{context}".encode()
        ).hexdigest()[:12]

        return SimulationSpec(
            simulation_id=sim_id,
            concept=concept,
            animation_type=template["animation_type"],
            description=template["description"],
            visual_elements=template["visual_elements"],
            duration_seconds=duration,
            style=style,
            narration_sync=f"show during discussion of {concept}",
            color_palette=template["color_palette"],
            motion_pattern=template["motion_pattern"],
            overlay_text=template["overlay_text"],
            confidence=0.7,
        )

    def _generate_generic(
        self,
        concept: str,
        context: str,
        duration: float,
        style: str,
    ) -> SimulationSpec:
        """Generate a generic simulation for concepts without templates."""
        sim_id = hashlib.sha256(
            f"{concept}:{context}".encode()
        ).hexdigest()[:12]

        return SimulationSpec(
            simulation_id=sim_id,
            concept=concept,
            animation_type="abstract_visualization",
            description=f"Abstract visualization representing {concept}, with flowing particles and labeled elements",
            visual_elements=["abstract particles", "concept label", "flowing lines"],
            duration_seconds=duration,
            style=style,
            narration_sync=f"show during discussion of {concept}",
            color_palette=["blue", "cyan", "white"],
            motion_pattern="flowing particles with pulsing intensity",
            overlay_text=[concept],
            confidence=0.3,
        )

    def generate_for_concepts(
        self,
        concepts: list[str],
        context: str = "",
        duration_per_concept: float = 5.0,
    ) -> list[SimulationSpec]:
        """Generate simulations for multiple concepts."""
        return [
            self.generate_for_concept(c, context, duration_per_concept)
            for c in concepts
        ]

    def add_template(self, concept: str, template: dict) -> None:
        """Add a custom simulation template."""
        self.templates[concept.lower()] = template

    @property
    def available_concepts(self) -> list[str]:
        """List of concepts with simulation templates."""
        return list(self.templates.keys())
