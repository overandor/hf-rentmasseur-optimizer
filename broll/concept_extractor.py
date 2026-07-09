"""
Concept Extractor — Transcript → Semantic Concepts → Meaning Atoms

Decomposes spoken narration into meaning atoms, not keywords.
A meaning atom is a semantic unit that maps to visual concepts.

Example:
    "The material could have been derived from eastern energy wavelengths,
     a unit calibrated to the planet's natural resonance."

    NOT searched as: material, eastern, wavelength, unit, calibrated
    Decomposed into atoms:
      - ancient material / stone / crystal
      - eastern energy / solar alignment / sunrise
      - wavelengths / frequency / vibration
      - planetary resonance / Earth frequency / Schumann resonance
"""

import re
import hashlib
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class MeaningAtom:
    """A single semantic unit extracted from narration."""
    atom_id: str
    text: str
    start_char: int
    end_char: int
    timestamp_start: float
    timestamp_end: float
    visual_concepts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "atom_id": self.atom_id,
            "text": self.text,
            "start_char": self.start_char,
            "end_char": self.end_char,
            "timestamp_start": self.timestamp_start,
            "timestamp_end": self.timestamp_end,
            "visual_concepts": self.visual_concepts,
        }


@dataclass
class Concept:
    """A semantic concept extracted from narration, carrying visual associations."""
    concept_id: str
    label: str
    source_text: str
    atoms: list[MeaningAtom] = field(default_factory=list)
    visual_archetypes: list[str] = field(default_factory=list)
    emotional_tone: str = "neutral"
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "concept_id": self.concept_id,
            "label": self.label,
            "source_text": self.source_text,
            "atoms": [a.to_dict() for a in self.atoms],
            "visual_archetypes": self.visual_archetypes,
            "emotional_tone": self.emotional_tone,
            "confidence": self.confidence,
        }


# Words that are visually useless — they carry no visual signal
_VISUALLY_USELESS = {
    # articles
    "the", "a", "an",
    # prepositions
    "of", "to", "in", "on", "at", "by", "for", "with", "from", "into", "onto",
    "upon", "over", "under", "between", "through", "during", "before", "after",
    # conjunctions
    "and", "or", "but", "nor", "yet", "so", "because", "although", "while",
    "if", "unless", "since", "as",
    # pronouns
    "he", "she", "it", "they", "we", "you", "i", "his", "her", "its", "their",
    "our", "your", "my", "this", "that", "these", "those", "which", "who",
    "whom", "whose",
    # auxiliary verbs
    "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
    "do", "does", "did", "will", "would", "could", "should", "may", "might",
    "must", "can", "shall",
    # filler
    "very", "quite", "rather", "somewhat", "perhaps", "maybe", "just", "also",
    "even", "still", "already", "always", "never", "now", "then", "here",
    "there", "where", "when", "how", "why",
    # generic descriptors with no visual content
    "could", "have", "been", "derived", "unit", "calibrated",
}

# Concept → visual concept mappings (the semantic bridge)
# This is the core knowledge base that a human editor uses implicitly
_CONCEPT_VISUAL_MAP: dict[str, list[str]] = {
    # ancient / megalithic
    "ancient": ["ancient ruins", "megalithic stones", "archaeological site", "old temple"],
    "stone": ["stone circle", "megalith", "rock formation", "ancient masonry"],
    "crystal": ["crystal cave", "crystal formation", "mineral deposit", "geode"],
    "material": ["ancient stone", "mineral", "rock structure", "artifact"],
    "megalithic": ["Stonehenge", "megalith", "standing stones", "ancient monument"],
    "monument": ["ancient monument", "stone structure", "megalithic site"],
    "civilization": ["ancient city", "ruins", "archaeological ruins", "temple complex"],
    "temple": ["ancient temple", "sacred site", "stone temple", "ritual chamber"],
    "chamber": ["hidden chamber", "underground room", "cave interior", "sacred chamber"],
    "structure": ["ancient structure", "megalithic architecture", "stone building"],
    "sacred": ["sacred site", "temple", "ritual space", "holy place"],
    "geometry": ["sacred geometry", "geometric pattern", "mandala", "symmetrical design"],
    "pyramid": ["pyramid", "Giza", "ancient pyramid", "pyramid interior"],
    "stonehenge": ["Stonehenge", "stone circle", "trilithon", "sarsen stones"],

    # energy / frequency / resonance
    "energy": ["energy field", "glowing light", "aurora", "electromagnetic visualization"],
    "resonance": ["vibration", "standing wave", "frequency pattern", "resonant chamber", "Earth frequency", "Schumann resonance", "planetary resonance"],
    "frequency": ["frequency wave", "oscilloscope", "sound wave", "vibration pattern"],
    "vibration": ["vibrating surface", "resonance pattern", "wave animation"],
    "wavelength": ["light wave", "electromagnetic spectrum", "wave animation", "frequency diagram"],
    "wave": ["ocean wave", "sound wave", "light wave", "standing wave"],
    "sound": ["acoustic chamber", "sound wave", "echo", "cave acoustics"],
    "acoustics": ["cave acoustics", "resonant chamber", "sound reflection"],
    "electromagnetic": ["electromagnetic field", "magnetic field lines", "aurora"],
    "magnetic": ["magnetic field", "geomagnetic field", "magnetosphere"],
    "schumann": ["Schumann resonance", "Earth frequency", "planetary resonance"],
    "vibration_field": ["vibration field", "resonance pattern", "energy waves"],

    # earth / planetary
    "earth": ["Earth from space", "globe", "planet Earth", "Earth surface"],
    "planet": ["planet", "planetary body", "globe", "celestial body"],
    "planetary": ["planetary scale", "Earth", "globe animation", "planetary field"],
    "geological": ["geological formation", "rock strata", "earth crust", "tectonic"],
    "underground": ["underground cave", "subterranean chamber", "tunnel", "cavern"],
    "cave": ["cave interior", "underground cavern", "cave with light", "crystal cave"],
    "subterranean": ["underground tunnel", "cave system", "subterranean chamber"],
    "geomagnetic": ["geomagnetic field", "Earth magnetic field", "magnetosphere"],
    "tectonic": ["tectonic plates", "earthquake", "geological fault", "earth crust"],

    # eastern / solar / alignment
    "eastern": ["eastern horizon", "sunrise", "solar alignment", "dawn"],
    "sunrise": ["sunrise", "dawn", "eastern sky", "sun on horizon"],
    "solar": ["solar alignment", "sun rays", "solstice", "sunlight through stones"],
    "sun": ["sun", "sunlight", "solar disk", "sun rays through clouds"],
    "horizon": ["horizon", "skyline", "distant view", "panoramic landscape"],
    "alignment": ["solar alignment", "astronomical alignment", "stone alignment"],
    "cosmology": ["ancient cosmology", "celestial map", "star chart", "zodiac"],
    "celestial": ["night sky", "stars", "celestial sphere", "constellation"],

    # mystery / hidden / unknown
    "mystery": ["mysterious fog", "ancient fog", "enigmatic ruins", "hidden passage"],
    "hidden": ["hidden chamber", "secret passage", "concealed entrance", "underground room"],
    "unknown": ["unexplored cave", "mysterious structure", "ancient unknown"],
    "secret": ["secret chamber", "hidden door", "concealed passage"],
    "ancient_technology": ["ancient mechanism", "Antikythera", "ancient tool", "lost technology"],
    "lost": ["lost civilization", "ruins in jungle", "abandoned temple", "forgotten city"],

    # water / natural
    "water": ["water in cave", "underground river", "stream", "waterfall"],
    "river": ["river", "underground river", "stream through cave"],
    "light": ["light in darkness", "sunlight entering cave", "glowing entrance", "beam of light"],
    "natural": ["natural formation", "cave formation", "geological feature"],
    "mineral": ["mineral deposit", "crystal formation", "rock vein", "geode"],

    # ritual / spiritual
    "ritual": ["ritual ceremony", "ancient ceremony", "sacred ritual"],
    "spiritual": ["sacred site", "meditation space", "temple", "energy vortex"],
    "ceremony": ["ancient ceremony", "ritual gathering", "sacred fire"],
    "meditation": ["meditation", "zen", "contemplative space", "sacred calm"],
}

# Emotional tone detection from context words
_TONE_INDICATORS: dict[str, set[str]] = {
    "mysterious": {"mystery", "hidden", "unknown", "secret", "lost", "ancient", "enigmatic"},
    "awe": {"ancient", "megalithic", "monument", "pyramid", "cosmic", "celestial", "planetary"},
    "energetic": {"energy", "frequency", "vibration", "resonance", "wave", "power"},
    "contemplative": {"sacred", "meditation", "spiritual", "ritual", "geometry", "alignment"},
    "dark": {"underground", "subterranean", "cave", "hidden", "chamber", "dark"},
}


class ConceptExtractor:
    """
    Extracts semantic concepts and meaning atoms from narration text.

    This is NOT keyword matching. It decomposes spoken meaning into
    visual-concept-bearing atoms that a human editor would associate
    with footage.
    """

    def __init(self):
        self.visual_map = dict(_CONCEPT_VISUAL_MAP)
        self.useless_words = set(_VISUALLY_USELESS)

    def __init__(self, custom_map: dict[str, list[str]] | None = None):
        self.visual_map = dict(_CONCEPT_VISUAL_MAP)
        if custom_map:
            self.visual_map.update(custom_map)
        self.useless_words = set(_VISUALLY_USELESS)

    def extract_atoms(
        self,
        text: str,
        timestamp_start: float = 0.0,
        timestamp_end: float | None = None,
    ) -> list[MeaningAtom]:
        """
        Split text into meaning atoms — phrases that carry visual signal.

        Strategy:
        1. Tokenize into words with positions
        2. Filter out visually useless words
        3. Group remaining words into contiguous phrases (atoms)
        4. Expand each atom with visual concepts from the map
        """
        if timestamp_end is None:
            timestamp_end = timestamp_start + 5.0

        words = []
        for m in re.finditer(r"[a-zA-Z]+", text):
            word = m.group(0).lower()
            words.append((word, m.start(), m.end()))

        # Group non-useless words into contiguous atoms
        atoms: list[MeaningAtom] = []
        current_group: list[tuple[str, int, int]] = []

        for word, start, end in words:
            if word in self.useless_words:
                if current_group:
                    atoms.append(self._make_atom(current_group, text, timestamp_start, timestamp_end))
                    current_group = []
            else:
                current_group.append((word, start, end))

        if current_group:
            atoms.append(self._make_atom(current_group, text, timestamp_start, timestamp_end))

        return atoms

    def _make_atom(
        self,
        group: list[tuple[str, int, int]],
        full_text: str,
        ts_start: float,
        ts_end: float,
    ) -> MeaningAtom:
        """Create a MeaningAtom from a group of words."""
        words = [g[0] for g in group]
        start_char = group[0][1]
        end_char = group[-1][2]
        atom_text = full_text[start_char:end_char]

        # Generate stable ID
        atom_id = hashlib.sha256(
            f"{atom_text}:{start_char}:{end_char}".encode()
        ).hexdigest()[:12]

        # Expand into visual concepts
        visual_concepts: list[str] = []
        for word in words:
            if word in self.visual_map:
                for vc in self.visual_map[word]:
                    if vc not in visual_concepts:
                        visual_concepts.append(vc)

        # Also check multi-word phrases
        for i in range(len(words)):
            for j in range(i + 2, len(words) + 1):
                phrase = " ".join(words[i:j])
                if phrase in self.visual_map:
                    for vc in self.visual_map[phrase]:
                        if vc not in visual_concepts:
                            visual_concepts.append(vc)

        # Interpolate timestamp within the segment
        span = end_char - start_char if (end_char - start_char) > 0 else 1
        text_len = len(full_text) if len(full_text) > 0 else 1
        rel_start = start_char / text_len
        rel_end = end_char / text_len
        duration = ts_end - ts_start
        atom_ts_start = ts_start + rel_start * duration
        atom_ts_end = ts_start + rel_end * duration

        return MeaningAtom(
            atom_id=atom_id,
            text=atom_text,
            start_char=start_char,
            end_char=end_char,
            timestamp_start=atom_ts_start,
            timestamp_end=atom_ts_end,
            visual_concepts=visual_concepts,
        )

    def detect_tone(self, text: str) -> str:
        """Detect emotional tone from text content."""
        words = set(re.findall(r"[a-zA-Z]+", text.lower()))
        best_tone = "neutral"
        best_score = 0
        for tone, indicators in _TONE_INDICATORS.items():
            score = len(words & indicators)
            if score > best_score:
                best_score = score
                best_tone = tone
        return best_tone

    def extract(
        self,
        text: str,
        timestamp_start: float = 0.0,
        timestamp_end: float | None = None,
    ) -> list[Concept]:
        """
        Full extraction: text → list of Concepts with atoms and visual archetypes.

        Groups atoms into higher-level concepts based on visual concept overlap.
        """
        atoms = self.extract_atoms(text, timestamp_start, timestamp_end)

        # Only keep atoms that have visual concepts
        visual_atoms = [a for a in atoms if a.visual_concepts]

        if not visual_atoms:
            return []

        # Group atoms by visual concept families
        # Two atoms belong to the same concept if they share visual concepts
        concepts: list[Concept] = []
        used_atoms: set[str] = set()

        for i, atom in enumerate(visual_atoms):
            if atom.atom_id in used_atoms:
                continue

            # Start a new concept group
            group_atoms = [atom]
            group_visuals = set(atom.visual_concepts)
            used_atoms.add(atom.atom_id)

            for j, other in enumerate(visual_atoms[i + 1:], i + 1):
                if other.atom_id in used_atoms:
                    continue
                if set(other.visual_concepts) & group_visuals:
                    group_atoms.append(other)
                    group_visuals.update(other.visual_concepts)
                    used_atoms.add(other.atom_id)

            # Create concept
            label = group_atoms[0].text
            all_visuals = sorted(group_visuals)

            concept_id = hashlib.sha256(
                f"{label}:{':'.join(all_visuals)}".encode()
            ).hexdigest()[:12]

            tone = self.detect_tone(text)

            # Confidence based on number of visual concepts and atoms
            confidence = min(1.0, len(all_visuals) / 8.0 + len(group_atoms) * 0.1)

            concepts.append(Concept(
                concept_id=concept_id,
                label=label,
                source_text=text,
                atoms=group_atoms,
                visual_archetypes=all_visuals,
                emotional_tone=tone,
                confidence=confidence,
            ))

        return concepts

    def add_custom_mapping(self, key: str, visuals: list[str]) -> None:
        """Add a custom concept → visual mapping at runtime."""
        key_lower = key.lower()
        if key_lower in self.visual_map:
            for v in visuals:
                if v not in self.visual_map[key_lower]:
                    self.visual_map[key_lower].append(v)
        else:
            self.visual_map[key_lower] = list(visuals)

        # Also register individual words for multi-word keys
        # so that tokenized text can still match
        words = key_lower.replace("_", " ").split()
        if len(words) > 1:
            for word in words:
                if word not in self.useless_words and word not in self.visual_map:
                    self.visual_map[word] = list(visuals)
                elif word in self.visual_map:
                    for v in visuals:
                        if v not in self.visual_map[word]:
                            self.visual_map[word].append(v)
