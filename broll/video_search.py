"""
Video Search — Visual Archetypes → Candidate Videos → Best Match

Searches YouTube and local video corpus for footage matching visual archetypes.
Ranks candidates by 5-dimensional score:

    Clip Score = semantic_similarity + visual_clarity + timing_fit
                 + copyright_safety + emotional_tone_match

This is closer to a recommendation engine than a search engine.
"""

import hashlib
import re
import time
import json
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict


@dataclass
class VideoCandidate:
    """A candidate video clip that might match a visual archetype."""
    candidate_id: str
    title: str
    url: str = ""
    source: str = "unknown"  # youtube, local, stock
    duration_seconds: float = 0.0
    thumbnail_url: str = ""
    channel: str = ""
    # Scoring dimensions (0.0 to 1.0 each)
    semantic_similarity: float = 0.0
    visual_clarity: float = 0.0
    timing_fit: float = 0.0
    copyright_safety: float = 0.0
    emotional_tone_match: float = 0.0
    # Composite
    composite_score: float = 0.0
    # What archetype this was matched against
    matched_archetype: str = ""
    matched_search_term: str = ""

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "duration_seconds": self.duration_seconds,
            "thumbnail_url": self.thumbnail_url,
            "channel": self.channel,
            "semantic_similarity": self.semantic_similarity,
            "visual_clarity": self.visual_clarity,
            "timing_fit": self.timing_fit,
            "copyright_safety": self.copyright_safety,
            "emotional_tone_match": self.emotional_tone_match,
            "composite_score": self.composite_score,
            "matched_archetype": self.matched_archetype,
            "matched_search_term": self.matched_search_term,
        }


@dataclass
class ClipScore:
    """5-dimensional clip scoring as specified in the architecture."""
    semantic_similarity: float = 0.0
    visual_clarity: float = 0.0
    timing_fit: float = 0.0
    copyright_safety: float = 0.0
    emotional_tone_match: float = 0.0

    # Weights for each dimension
    WEIGHTS = {
        "semantic_similarity": 0.35,
        "visual_clarity": 0.20,
        "timing_fit": 0.15,
        "copyright_safety": 0.15,
        "emotional_tone_match": 0.15,
    }

    @property
    def composite(self) -> float:
        return (
            self.semantic_similarity * self.WEIGHTS["semantic_similarity"]
            + self.visual_clarity * self.WEIGHTS["visual_clarity"]
            + self.timing_fit * self.WEIGHTS["timing_fit"]
            + self.copyright_safety * self.WEIGHTS["copyright_safety"]
            + self.emotional_tone_match * self.WEIGHTS["emotional_tone_match"]
        )

    def to_dict(self) -> dict:
        return {
            "semantic_similarity": self.semantic_similarity,
            "visual_clarity": self.visual_clarity,
            "timing_fit": self.timing_fit,
            "copyright_safety": self.copyright_safety,
            "emotional_tone_match": self.emotional_tone_match,
            "composite": self.composite,
        }


# Keywords that indicate copyright-safe content
_COPYRIGHT_SAFE_INDICATORS = {
    "creative commons", "cc0", "public domain", "royalty free",
    "stock footage", "free footage", "no copyright", "nc-free",
    "archive", "nasa", "government", "wikimedia", "pexels", "pixabay",
}

# Keywords that suggest copyright risk
_COPYRIGHT_RISK_INDICATORS = {
    "official video", "music video", "movie clip", "trailer",
    "netflix", "hbo", "disney", "warner", "universal", "copyrighted",
    "all rights reserved", "tm", "(c)",
}

# Visual clarity indicators in titles
_CLARITY_INDICATORS = {
    "4k": 0.95, "8k": 1.0, "hd": 0.7, "high quality": 0.8,
    "drone": 0.9, "aerial": 0.85, "cinematic": 0.9,
    "documentary": 0.85, "footage": 0.75, "close-up": 0.8,
    "timelapse": 0.85, "slow motion": 0.85,
}

# Emotional tone keywords in titles/descriptions
_TONE_KEYWORDS: dict[str, set[str]] = {
    "mysterious": {"mystery", "hidden", "secret", "unknown", "enigmatic", "unexplained"},
    "awe": {"ancient", "magnificent", "incredible", "amazing", "spectacular", "breathtaking"},
    "energetic": {"energy", "power", "frequency", "vibration", "resonance", "active"},
    "contemplative": {"sacred", "spiritual", "meditation", "calm", "peaceful", "zen"},
    "dark": {"underground", "cave", "dark", "hidden", "subterranean", "deep"},
}


class VideoSearch:
    """
    Searches for video clips matching visual archetypes.

    In production, this would query YouTube Data API, local video corpus,
    and stock footage APIs. For now, it simulates search results and
    scores them using the 5-dimensional ClipScore.

    The scoring is the valuable part — it encodes editorial judgment.
    """

    def __init__(self, use_youtube_api: bool = False, youtube_api_key: str = ""):
        self.use_youtube_api = use_youtube_api
        self.youtube_api_key = youtube_api_key
        self._local_corpus: list[dict] = []
        self._search_cache: dict[str, list[VideoCandidate]] = {}

    def add_local_video(
        self,
        title: str,
        path: str,
        duration: float = 0.0,
        description: str = "",
        tags: list[str] | None = None,
    ) -> None:
        """Add a local video to the searchable corpus."""
        self._local_corpus.append({
            "title": title,
            "path": path,
            "duration": duration,
            "description": description,
            "tags": tags or [],
            "source": "local",
        })

    def search(
        self,
        search_terms: list[str],
        archetype_label: str = "",
        emotional_tone: str = "neutral",
        max_results: int = 10,
    ) -> list[VideoCandidate]:
        """
        Search for videos matching the given search terms.

        Returns ranked VideoCandidate list scored by the 5-dimensional ClipScore.
        """
        candidates: list[VideoCandidate] = []

        for term in search_terms:
            # Search local corpus
            local_results = self._search_local(term, archetype_label, emotional_tone)
            candidates.extend(local_results)

            # If YouTube API is configured, search there
            if self.use_youtube_api and self.youtube_api_key:
                yt_results = self._search_youtube(term, archetype_label, emotional_tone)
                candidates.extend(yt_results)
            else:
                # Generate deterministic candidates from local corpus
                sim_results = self._simulate_search(term, archetype_label, emotional_tone)
                candidates.extend(sim_results)

        # Sort by composite score
        candidates.sort(key=lambda c: -c.composite_score)

        # Deduplicate by title
        seen: set[str] = set()
        unique: list[VideoCandidate] = []
        for c in candidates:
            key = c.title.lower().strip()
            if key not in seen:
                seen.add(key)
                unique.append(c)

        return unique[:max_results]

    def _search_local(
        self,
        term: str,
        archetype_label: str,
        emotional_tone: str,
    ) -> list[VideoCandidate]:
        """Search local video corpus."""
        results: list[VideoCandidate] = []
        term_lower = term.lower()

        for video in self._local_corpus:
            searchable = f"{video['title']} {video['description']} {' '.join(video['tags'])}".lower()
            if term_lower in searchable:
                score = self._score_candidate(
                    title=video["title"],
                    description=video["description"],
                    search_term=term,
                    archetype_label=archetype_label,
                    emotional_tone=emotional_tone,
                    duration=video["duration"],
                    source="local",
                )

                candidate = VideoCandidate(
                    candidate_id=hashlib.sha256(
                        f"local:{video['title']}".encode()
                    ).hexdigest()[:12],
                    title=video["title"],
                    url=video["path"],
                    source="local",
                    duration_seconds=video["duration"],
                    semantic_similarity=score.semantic_similarity,
                    visual_clarity=score.visual_clarity,
                    timing_fit=score.timing_fit,
                    copyright_safety=score.copyright_safety,
                    emotional_tone_match=score.emotional_tone_match,
                    composite_score=score.composite,
                    matched_archetype=archetype_label,
                    matched_search_term=term,
                )
                results.append(candidate)

        return results

    def _search_youtube(
        self,
        term: str,
        archetype_label: str,
        emotional_tone: str,
    ) -> list[VideoCandidate]:
        """Search YouTube via Data API v3 using the YouTubeSearchClient."""
        from .youtube_search import YouTubeSearchClient
        client = YouTubeSearchClient(api_key=self.youtube_api_key)
        videos = client.search_videos(query=term, max_results=5)

        candidates: list[VideoCandidate] = []
        for v in videos:
            score = self._score_candidate(
                title=v.title,
                description=v.description,
                search_term=term,
                archetype_label=archetype_label,
                emotional_tone=emotional_tone,
                duration=v.duration_seconds,
                source="youtube",
            )
            candidate = VideoCandidate(
                candidate_id=hashlib.sha256(
                    f"yt:{v.video_id}:{term}".encode()
                ).hexdigest()[:12],
                title=v.title,
                url=v.url,
                source="youtube",
                duration_seconds=v.duration_seconds,
                thumbnail_url=v.thumbnail_url,
                channel=v.channel,
                semantic_similarity=score.semantic_similarity,
                visual_clarity=score.visual_clarity,
                timing_fit=score.timing_fit,
                copyright_safety=score.copyright_safety,
                emotional_tone_match=score.emotional_tone_match,
                composite_score=score.composite,
                matched_archetype=archetype_label,
                matched_search_term=term,
            )
            candidates.append(candidate)

        return candidates

    def _simulate_search(
        self,
        term: str,
        archetype_label: str,
        emotional_tone: str,
    ) -> list[VideoCandidate]:
        """
        Generate deterministic candidates from local corpus when no YouTube API key is available.

        Produces realistic candidates that demonstrate the scoring and ranking mechanism.
        """
        candidates: list[VideoCandidate] = []

        variations = [
            f"{term} documentary 4K",
            f"{term} drone footage",
            f"{term} close-up HD",
        ]

        for i, title in enumerate(variations[:3]):
            score = self._score_candidate(
                title=title,
                description=f"Footage of {term}",
                search_term=term,
                archetype_label=archetype_label,
                emotional_tone=emotional_tone,
                duration=30.0 + i * 15,
                source="youtube_simulated",
            )

            candidate = VideoCandidate(
                candidate_id=hashlib.sha256(
                    f"sim:{title}:{time.time()}".encode()
                ).hexdigest()[:12],
                title=title,
                url=f"https://www.youtube.com/results?search_query={term.replace(' ', '+')}",
                source="youtube_simulated",
                duration_seconds=30.0 + i * 15,
                thumbnail_url="",
                channel="NatureDocumentary" if i == 0 else "AerialVisions" if i == 1 else "CloseUpWorld",
                semantic_similarity=score.semantic_similarity,
                visual_clarity=score.visual_clarity,
                timing_fit=score.timing_fit,
                copyright_safety=score.copyright_safety,
                emotional_tone_match=score.emotional_tone_match,
                composite_score=score.composite,
                matched_archetype=archetype_label,
                matched_search_term=term,
            )
            candidates.append(candidate)

        return candidates

    def _score_candidate(
        self,
        title: str,
        description: str,
        search_term: str,
        archetype_label: str,
        emotional_tone: str,
        duration: float,
        source: str,
    ) -> ClipScore:
        """
        Score a candidate on 5 dimensions.

        1. semantic_similarity: how well the title/description matches the search term
        2. visual_clarity: production quality indicators (4K, drone, cinematic)
        3. timing_fit: duration appropriateness for B-roll (5-30s ideal)
        4. copyright_safety: presence of CC/public domain indicators
        5. emotional_tone_match: tone alignment with narration
        """
        combined = f"{title} {description}".lower()

        # 1. Semantic similarity — token overlap between search term and title
        search_tokens = set(search_term.lower().split())
        title_tokens = set(title.lower().split())
        if search_tokens:
            overlap = len(search_tokens & title_tokens) / len(search_tokens)
        else:
            overlap = 0.0
        # Boost for exact phrase match
        if search_term.lower() in title.lower():
            overlap = min(1.0, overlap + 0.3)
        semantic_similarity = overlap

        # 2. Visual clarity — production quality indicators
        visual_clarity = 0.5  # baseline
        for indicator, boost in _CLARITY_INDICATORS.items():
            if indicator in combined:
                visual_clarity = max(visual_clarity, boost)

        # 3. Timing fit — ideal B-roll is 5-30 seconds
        if 5 <= duration <= 30:
            timing_fit = 1.0
        elif 3 <= duration <= 60:
            timing_fit = 0.7
        elif duration > 0:
            timing_fit = 0.4
        else:
            timing_fit = 0.5  # unknown duration

        # 4. Copyright safety
        copyright_safety = 0.5  # baseline
        for indicator in _COPYRIGHT_SAFE_INDICATORS:
            if indicator in combined:
                copyright_safety = 0.95
                break
        for indicator in _COPYRIGHT_RISK_INDICATORS:
            if indicator in combined:
                copyright_safety = min(copyright_safety, 0.2)
                break
        # Local files are always copyright-safe (they're yours)
        if source == "local":
            copyright_safety = 1.0

        # 5. Emotional tone match
        emotional_tone_match = 0.5  # neutral baseline
        if emotional_tone != "neutral":
            for tone, keywords in _TONE_KEYWORDS.items():
                if tone == emotional_tone:
                    matches = sum(1 for kw in keywords if kw in combined)
                    if matches > 0:
                        emotional_tone_match = min(1.0, 0.5 + matches * 0.2)
                elif any(kw in combined for kw in keywords):
                    emotional_tone_match = max(0.0, emotional_tone_match - 0.1)

        return ClipScore(
            semantic_similarity=semantic_similarity,
            visual_clarity=visual_clarity,
            timing_fit=timing_fit,
            copyright_safety=copyright_safety,
            emotional_tone_match=emotional_tone_match,
        )

    def rank_candidates(
        self,
        candidates: list[VideoCandidate],
        max_results: int = 5,
    ) -> list[VideoCandidate]:
        """Re-rank candidates by composite score."""
        ranked = sorted(candidates, key=lambda c: -c.composite_score)
        return ranked[:max_results]
