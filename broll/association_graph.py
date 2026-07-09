"""
Visual Association Graph — Concept → Visual Archetype → Candidate Search Terms

This is the core invention: the concept bridge.
Text meaning → visual meaning → available footage.

The graph learns associations like:
    "planetary resonance" ≈ Stonehenge, ancient monuments, Earth frequency diagrams,
                            megalithic architecture, underground caverns

It is closer to a recommendation engine than a search engine.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict


@dataclass
class VisualArchetype:
    """
    A visual archetype is a category of footage that human editors associate
    with certain spoken concepts.

    Example: "ancient energy" archetype maps to:
      - Stonehenge at sunrise
      - Pyramid with light beam
      - Cave with glowing crystals
      - Ancient temple with sun rays
    """
    archetype_id: str
    label: str
    search_terms: list[str] = field(default_factory=list)
    example_descriptions: list[str] = field(default_factory=list)
    associated_concepts: list[str] = field(default_factory=list)
    weight: float = 1.0  # how strongly this archetype matches

    def to_dict(self) -> dict:
        return {
            "archetype_id": self.archetype_id,
            "label": self.label,
            "search_terms": self.search_terms,
            "example_descriptions": self.example_descriptions,
            "associated_concepts": self.associated_concepts,
            "weight": self.weight,
        }


@dataclass
class AssociationEdge:
    """An edge in the association graph: concept → archetype."""
    concept_label: str
    archetype_label: str
    strength: float  # 0.0 to 1.0
    co_occurrence_count: int = 1
    last_reinforced: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "concept_label": self.concept_label,
            "archetype_label": self.archetype_label,
            "strength": self.strength,
            "co_occurrence_count": self.co_occurrence_count,
            "last_reinforced": self.last_reinforced,
        }


# Pre-seeded associations — the "human editor's brain"
# These map semantic concepts to visual archetypes that editors actually use
_SEED_ASSOCIATIONS: dict[str, dict[str, list[str]]] = {
    "ancient_megalithic": {
        "archetypes": [
            "Stonehenge solar alignment",
            "ancient stone circle",
            "megalithic ruins",
            "standing stones at dawn",
            "ancient temple ruins",
            "pyramid structure",
        ],
        "search_terms": [
            "Stonehenge sunrise",
            "ancient stone circle",
            "megalithic site",
            "standing stones",
            "ancient ruins drone",
            "pyramid aerial",
            "ancient temple",
        ],
    },
    "earth_resonance_frequency": {
        "archetypes": [
            "Earth from space with energy lines",
            "Schumann resonance visualization",
            "geomagnetic field animation",
            "frequency wave over globe",
            "vibration in natural structure",
        ],
        "search_terms": [
            "Earth frequency visualization",
            "Schumann resonance",
            "geomagnetic field",
            "Earth energy",
            "planetary resonance animation",
            "Earth magnetic field",
        ],
    },
    "cave_underground": {
        "archetypes": [
            "cave with light beam",
            "underground crystal cavern",
            "subterranean water passage",
            "ancient underground chamber",
            "cave with glowing minerals",
        ],
        "search_terms": [
            "cave interior light",
            "crystal cave",
            "underground cavern",
            "cave water passage",
            "ancient underground chamber",
            "glowing cave minerals",
            "subterranean tunnel",
        ],
    },
    "solar_alignment": {
        "archetypes": [
            "sunrise through stone monument",
            "sun rays entering temple",
            "solar alignment at ancient site",
            "sunlight through ancient doorway",
            "dawn at megalithic site",
        ],
        "search_terms": [
            "sunrise ancient monument",
            "solar alignment Stonehenge",
            "sun rays temple",
            "dawn ancient site",
            "solstice sunrise",
            "sunlight ancient doorway",
        ],
    },
    "sacred_geometry": {
        "archetypes": [
            "geometric pattern overlay",
            "mandala animation",
            "flower of life pattern",
            "symmetrical ancient design",
            "geometric crop circle",
        ],
        "search_terms": [
            "sacred geometry animation",
            "flower of life",
            "ancient geometric pattern",
            "mandala",
            "geometric design overlay",
        ],
    },
    "ancient_technology": {
        "archetypes": [
            "ancient mechanism close-up",
            "Antikythera device",
            "ancient tool or artifact",
            "lost technology reconstruction",
            "ancient engineering marvel",
        ],
        "search_terms": [
            "ancient technology",
            "Antikythera mechanism",
            "ancient artifact",
            "lost technology",
            "ancient engineering",
        ],
    },
    "energy_field": {
        "archetypes": [
            "glowing energy field",
            "aurora borealis",
            "electromagnetic visualization",
            "light field around object",
            "energy waves animation",
        ],
        "search_terms": [
            "energy field visualization",
            "aurora borealis",
            "electromagnetic field animation",
            "light energy waves",
            "glowing field",
        ],
    },
    "mystery_hidden": {
        "archetypes": [
            "fog over ancient site",
            "hidden passage discovery",
            "mysterious ancient structure",
            "enigmatic ruins in mist",
            "secret chamber entrance",
        ],
        "search_terms": [
            "ancient ruins fog",
            "hidden passage",
            "mysterious ancient structure",
            "ancient site mist",
            "secret chamber",
        ],
    },
    "water_natural": {
        "archetypes": [
            "underground river",
            "waterfall in cave",
            "stream through ancient site",
            "water reflecting stone",
            "natural spring",
        ],
        "search_terms": [
            "underground river cave",
            "waterfall cave",
            "stream ancient site",
            "water stone reflection",
            "natural spring",
        ],
    },
    "cosmic_celestial": {
        "archetypes": [
            "night sky over ancient site",
            "stars above monument",
            "celestial alignment",
            "constellation over landscape",
            "milky way ancient ruins",
        ],
        "search_terms": [
            "night sky ancient ruins",
            "stars monument",
            "milky way ancient site",
            "celestial alignment",
            "constellation landscape",
        ],
    },
}

# Concept family detection — maps visual concepts to archetype families
_CONCEPT_TO_FAMILY: dict[str, str] = {
    # ancient_megalithic
    "ancient ruins": "ancient_megalithic",
    "megalithic stones": "ancient_megalithic",
    "stone circle": "ancient_megalithic",
    "Stonehenge": "ancient_megalithic",
    "megalith": "ancient_megalithic",
    "standing stones": "ancient_megalithic",
    "ancient monument": "ancient_megalithic",
    "ancient temple": "ancient_megalithic",
    "pyramid": "ancient_megalithic",
    "ancient structure": "ancient_megalithic",
    "megalithic architecture": "ancient_megalithic",
    "ancient city": "ancient_megalithic",
    "ruins": "ancient_megalithic",
    "archaeological site": "ancient_megalithic",
    "archaeological ruins": "ancient_megalithic",
    "temple complex": "ancient_megalithic",

    # earth_resonance_frequency
    "Earth frequency": "earth_resonance_frequency",
    "Schumann resonance": "earth_resonance_frequency",
    "planetary resonance": "earth_resonance_frequency",
    "geomagnetic field": "earth_resonance_frequency",
    "Earth magnetic field": "earth_resonance_frequency",
    "magnetosphere": "earth_resonance_frequency",
    "planetary field": "earth_resonance_frequency",
    "Earth from space": "earth_resonance_frequency",
    "globe": "earth_resonance_frequency",
    "planet Earth": "earth_resonance_frequency",
    "Earth surface": "earth_resonance_frequency",

    # cave_underground
    "cave interior": "cave_underground",
    "underground cavern": "cave_underground",
    "cave with light": "cave_underground",
    "crystal cave": "cave_underground",
    "underground cave": "cave_underground",
    "subterranean chamber": "cave_underground",
    "tunnel": "cave_underground",
    "cavern": "cave_underground",
    "underground tunnel": "cave_underground",
    "cave system": "cave_underground",
    "subterranean": "cave_underground",
    "hidden chamber": "cave_underground",
    "underground room": "cave_underground",
    "cave acoustics": "cave_underground",
    "resonant chamber": "cave_underground",
    "sacred chamber": "cave_underground",

    # solar_alignment
    "eastern horizon": "solar_alignment",
    "sunrise": "solar_alignment",
    "dawn": "solar_alignment",
    "solar alignment": "solar_alignment",
    "sun rays": "solar_alignment",
    "solstice": "solar_alignment",
    "sunlight through stones": "solar_alignment",
    "sun": "solar_alignment",
    "sunlight": "solar_alignment",
    "solar disk": "solar_alignment",
    "sun rays through clouds": "solar_alignment",
    "sunlight entering cave": "solar_alignment",
    "beam of light": "solar_alignment",
    "light in darkness": "solar_alignment",
    "glowing entrance": "solar_alignment",

    # sacred_geometry
    "sacred geometry": "sacred_geometry",
    "geometric pattern": "sacred_geometry",
    "mandala": "sacred_geometry",
    "symmetrical design": "sacred_geometry",

    # ancient_technology
    "ancient mechanism": "ancient_technology",
    "Antikythera": "ancient_technology",
    "ancient tool": "ancient_technology",
    "lost technology": "ancient_technology",

    # energy_field
    "energy field": "energy_field",
    "glowing light": "energy_field",
    "aurora": "energy_field",
    "electromagnetic visualization": "energy_field",
    "electromagnetic field": "energy_field",
    "magnetic field lines": "energy_field",
    "energy waves": "energy_field",
    "vibration field": "energy_field",
    "resonance pattern": "energy_field",
    "frequency wave": "energy_field",
    "oscilloscope": "energy_field",
    "sound wave": "energy_field",
    "vibration pattern": "energy_field",
    "vibrating surface": "energy_field",
    "wave animation": "energy_field",
    "standing wave": "energy_field",
    "light wave": "energy_field",
    "electromagnetic spectrum": "energy_field",
    "frequency diagram": "energy_field",
    "vibration": "energy_field",
    "frequency": "energy_field",
    "resonance": "energy_field",
    "energy": "energy_field",

    # mystery_hidden
    "mysterious fog": "mystery_hidden",
    "ancient fog": "mystery_hidden",
    "enigmatic ruins": "mystery_hidden",
    "hidden passage": "mystery_hidden",
    "secret passage": "mystery_hidden",
    "concealed entrance": "mystery_hidden",
    "secret chamber": "mystery_hidden",
    "hidden door": "mystery_hidden",
    "concealed passage": "mystery_hidden",
    "unexplored cave": "mystery_hidden",
    "mysterious structure": "mystery_hidden",
    "lost civilization": "mystery_hidden",
    "ruins in jungle": "mystery_hidden",
    "abandoned temple": "mystery_hidden",
    "forgotten city": "mystery_hidden",
    "ancient unknown": "mystery_hidden",

    # water_natural
    "water in cave": "water_natural",
    "underground river": "water_natural",
    "stream": "water_natural",
    "waterfall": "water_natural",
    "river": "water_natural",
    "stream through cave": "water_natural",
    "waterfall in cave": "water_natural",
    "natural formation": "water_natural",
    "cave formation": "water_natural",
    "geological feature": "water_natural",
    "mineral deposit": "water_natural",
    "crystal formation": "water_natural",
    "rock vein": "water_natural",
    "geode": "water_natural",
    "mineral": "water_natural",
    "rock structure": "water_natural",
    "artifact": "water_natural",
    "ancient stone": "water_natural",
    "rock formation": "water_natural",
    "ancient masonry": "water_natural",
    "stone structure": "water_natural",
    "stone building": "water_natural",
    "sarsen stones": "water_natural",
    "trilithon": "water_natural",

    # cosmic_celestial
    "night sky": "cosmic_celestial",
    "stars": "cosmic_celestial",
    "celestial sphere": "cosmic_celestial",
    "constellation": "cosmic_celestial",
    "star chart": "cosmic_celestial",
    "zodiac": "cosmic_celestial",
    "ancient cosmology": "cosmic_celestial",
    "celestial map": "cosmic_celestial",

    # sacred / ritual
    "sacred site": "sacred_geometry",
    "temple": "ancient_megalithic",
    "ritual space": "sacred_geometry",
    "holy place": "sacred_geometry",
    "ritual ceremony": "sacred_geometry",
    "ancient ceremony": "sacred_geometry",
    "sacred fire": "sacred_geometry",
    "sacred ritual": "sacred_geometry",
    "meditation": "sacred_geometry",
    "zen": "sacred_geometry",
    "contemplative space": "sacred_geometry",
    "sacred calm": "sacred_geometry",
    "energy vortex": "energy_field",

    # solar / horizon
    "horizon": "solar_alignment",
    "skyline": "solar_alignment",
    "distant view": "solar_alignment",
    "panoramic landscape": "solar_alignment",
    "eastern sky": "solar_alignment",
    "sun on horizon": "solar_alignment",

    # geological
    "geological formation": "cave_underground",
    "rock strata": "cave_underground",
    "earth crust": "cave_underground",
    "tectonic": "cave_underground",
    "tectonic plates": "cave_underground",
    "earthquake": "cave_underground",
    "geological fault": "cave_underground",

    # celestial
    "celestial body": "cosmic_celestial",
    "planetary body": "cosmic_celestial",
    "globe animation": "earth_resonance_frequency",
}


class VisualAssociationGraph:
    """
    The concept bridge: text meaning → visual meaning → available footage.

    Learns and stores associations between semantic concepts and visual archetypes.
    This is the component that knows "planetary resonance" ≈ Stonehenge.

    Usage:
        graph = VisualAssociationGraph()
        archetypes = graph.resolve(visual_concepts=["Earth frequency", "ancient ruins"])
        # Returns ranked visual archetypes with search terms
    """

    def __init__(self, seed: bool = True):
        self.archetypes: dict[str, VisualArchetype] = {}
        self.edges: list[AssociationEdge] = []
        self._edge_index: dict[str, list[AssociationEdge]] = defaultdict(list)
        self._concept_to_family = dict(_CONCEPT_TO_FAMILY)

        if seed:
            self._seed()

    def _seed(self) -> None:
        """Load pre-seeded associations."""
        for family_id, data in _SEED_ASSOCIATIONS.items():
            for i, arch_label in enumerate(data["archetypes"]):
                arch_id = hashlib.sha256(
                    f"{family_id}:{arch_label}".encode()
                ).hexdigest()[:12]
                search_terms = data["search_terms"]

                arch = VisualArchetype(
                    archetype_id=arch_id,
                    label=arch_label,
                    search_terms=search_terms,
                    example_descriptions=[arch_label],
                    associated_concepts=[family_id],
                    weight=1.0 - (i * 0.1),  # first archetype is strongest
                )
                self.archetypes[arch_id] = arch

                # Create edge from family to archetype
                edge = AssociationEdge(
                    concept_label=family_id,
                    archetype_label=arch_label,
                    strength=1.0 - (i * 0.1),
                )
                self.edges.append(edge)
                self._edge_index[family_id].append(edge)

    def resolve(self, visual_concepts: list[str]) -> list[VisualArchetype]:
        """
        Resolve a list of visual concepts into ranked visual archetypes.

        This is the core operation: given concepts extracted from narration,
        return the visual archetypes that a human editor would choose.

        Args:
            visual_concepts: e.g. ["Earth frequency", "ancient ruins", "cave interior"]

        Returns:
            Ranked list of VisualArchetype objects with search terms
        """
        # Map visual concepts to families
        families: dict[str, float] = defaultdict(float)
        for vc in visual_concepts:
            family = self._concept_to_family.get(vc)
            if family:
                families[family] += 1.0
            else:
                # Try partial match
                vc_lower = vc.lower()
                for known_concept, fam in self._concept_to_family.items():
                    if known_concept.lower() in vc_lower or vc_lower in known_concept.lower():
                        families[fam] += 0.5
                        break

        if not families:
            return []

        # Get archetypes for each family, weighted by family frequency
        scored_archetypes: list[tuple[float, VisualArchetype]] = []

        for family_id, family_weight in families.items():
            edges = self._edge_index.get(family_id, [])
            for edge in edges:
                # Find the archetype
                for arch in self.archetypes.values():
                    if arch.label == edge.archetype_label:
                        score = edge.strength * family_weight
                        scored_archetypes.append((score, arch))
                        break

        # Sort by score descending
        scored_archetypes.sort(key=lambda x: -x[0])

        # Deduplicate by archetype label, keeping highest score
        seen: set[str] = set()
        result: list[VisualArchetype] = []
        for score, arch in scored_archetypes:
            if arch.label not in seen:
                seen.add(arch.label)
                # Create a copy with updated weight
                ranked = VisualArchetype(
                    archetype_id=arch.archetype_id,
                    label=arch.label,
                    search_terms=arch.search_terms,
                    example_descriptions=arch.example_descriptions,
                    associated_concepts=arch.associated_concepts,
                    weight=score,
                )
                result.append(ranked)

        return result

    def get_search_terms(self, visual_concepts: list[str]) -> list[str]:
        """
        Get deduplicated search terms for a set of visual concepts.
        These are the actual queries to send to video search.
        """
        archetypes = self.resolve(visual_concepts)
        terms: list[str] = []
        seen: set[str] = set()
        for arch in archetypes:
            for term in arch.search_terms:
                if term not in seen:
                    seen.add(term)
                    terms.append(term)
        return terms

    def learn_association(
        self,
        concept_label: str,
        archetype_label: str,
        strength: float = 0.8,
    ) -> None:
        """
        Learn a new association or reinforce an existing one.

        This is how the graph improves over time — when an editor
        confirms that a concept → archetype mapping was correct.
        """
        # Check if edge exists
        for edge in self.edges:
            if edge.concept_label == concept_label and edge.archetype_label == archetype_label:
                edge.co_occurrence_count += 1
                edge.strength = min(1.0, edge.strength + 0.05)
                edge.last_reinforced = time.time()
                return

        # Create new edge
        new_edge = AssociationEdge(
            concept_label=concept_label,
            archetype_label=archetype_label,
            strength=strength,
        )
        self.edges.append(new_edge)
        self._edge_index[concept_label].append(new_edge)

        # Create archetype if it doesn't exist
        arch_id = hashlib.sha256(
            f"{concept_label}:{archetype_label}".encode()
        ).hexdigest()[:12]
        if arch_id not in self.archetypes:
            self.archetypes[arch_id] = VisualArchetype(
                archetype_id=arch_id,
                label=archetype_label,
                search_terms=[archetype_label],
                associated_concepts=[concept_label],
                weight=strength,
            )

    def add_concept_family_mapping(self, visual_concept: str, family: str) -> None:
        """Add or update a visual concept → family mapping at runtime."""
        self._concept_to_family[visual_concept] = family

    def to_dict(self) -> dict:
        return {
            "archetype_count": len(self.archetypes),
            "edge_count": len(self.edges),
            "families": list(set(e.concept_label for e in self.edges)),
            "concept_mappings": len(self._concept_to_family),
        }

    def save(self, path: str) -> None:
        """Save graph state to JSON."""
        data = {
            "archetypes": {k: v.to_dict() for k, v in self.archetypes.items()},
            "edges": [e.to_dict() for e in self.edges],
            "concept_to_family": dict(self._concept_to_family),
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load(self, path: str) -> None:
        """Load graph state from JSON."""
        with open(path) as f:
            data = json.load(f)

        self.archetypes = {}
        for arch_id, arch_data in data.get("archetypes", {}).items():
            self.archetypes[arch_id] = VisualArchetype(
                archetype_id=arch_data["archetype_id"],
                label=arch_data["label"],
                search_terms=arch_data["search_terms"],
                example_descriptions=arch_data.get("example_descriptions", []),
                associated_concepts=arch_data.get("associated_concepts", []),
                weight=arch_data.get("weight", 1.0),
            )

        self.edges = []
        self._edge_index = defaultdict(list)
        for edge_data in data.get("edges", []):
            edge = AssociationEdge(
                concept_label=edge_data["concept_label"],
                archetype_label=edge_data["archetype_label"],
                strength=edge_data["strength"],
                co_occurrence_count=edge_data.get("co_occurrence_count", 1),
                last_reinforced=edge_data.get("last_reinforced", time.time()),
            )
            self.edges.append(edge)
            self._edge_index[edge.concept_label].append(edge)

        self._concept_to_family = data.get("concept_to_family", dict(_CONCEPT_TO_FAMILY))
