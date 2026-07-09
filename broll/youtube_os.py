"""
Investigation YouTube Operating System

Turns the VideoLake compiler into a channel-grade operating system for
evidence-backed research media.

    QRC turns questions into executable software capsules.
    SystemLake turns files into collateral evidence.
    VideoLake turns investigations into machine-readable research media.
    YouTubeOS turns VideoLake into a channel-grade publishing platform.

Architecture:

    Channel
    ├── Episodes (compiled investigations)
    │   ├── Draft       — question registered, not yet compiled
    │   ├── Compiled    — VideoLake compilation complete
    │   ├── Published   — visible to subscribers and machine agents
    │   └── Archived    — retained for provenance, not in active feed
    ├── Playlists (curated episode collections)
    ├── Feed (published episodes, machine-readable)
    ├── Analytics (aggregate trust, buyability, coverage)
    ├── Subscriptions (topic-based follow system)
    └── Receipt Ledger (SHA-256 chained across all episodes)

Machine API (FastAPI):

    GET  /channel                    — channel manifest
    GET  /channel/episodes           — list episodes (filter by status, topic, grade)
    GET  /channel/episodes/{id}      — episode detail with MEVF manifest
    GET  /channel/episodes/{id}/bundle — full VRAP bundle
    GET  /channel/feed               — RSS-like JSON feed
    GET  /channel/playlists          — list playlists
    GET  /channel/playlists/{id}     — playlist with episodes
    GET  /channel/analytics          — aggregate analytics
    GET  /channel/search?q=...       — search episodes by topic/claim/status
    GET  /channel/subscriptions      — list topic subscriptions
    POST /channel/subscriptions      — subscribe to a topic
    GET  /channel/receipts           — receipt ledger
    GET  /channel/receipts/verify    — verify receipt chain
    POST /channel/episodes           — create + compile a new episode
    POST /channel/episodes/{id}/publish — publish an episode
    POST /channel/episodes/{id}/archive — archive an episode
    POST /channel/playlists          — create a playlist
    POST /channel/playlists/{id}/add — add episode to playlist

Core principle: The channel is not a video feed. It is an evidence feed.
"""

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .videolake import VideoLakeCompiler, VideoLakeResult
from .investigation_graph import InvestigationGraph
from .mevf import MEVFObject, MEVFBuilder, query_segments
from .vrap import VRAPBuilder, VRAPManifest
from .machine_scores import MachineScoreSet


class EpisodeStatus(Enum):
    DRAFT = "draft"
    COMPILED = "compiled"
    PUBLISHED = "published"
    ARCHIVED = "archived"


@dataclass
class Episode:
    """A single investigation episode in the channel."""
    episode_id: str = ""
    title: str = ""
    question: str = ""
    status: EpisodeStatus = EpisodeStatus.DRAFT
    topic_tags: list[str] = field(default_factory=list)
    created_at: float = 0.0
    compiled_at: float = 0.0
    published_at: float = 0.0
    duration_seconds: float = 0.0
    trust_grade: str = ""
    avg_buyability: float = 0.0
    claim_count: int = 0
    segment_count: int = 0
    paper_count: int = 0
    total_price_usd: float = 0.0
    receipt_hash: str = ""
    investigation: Optional[InvestigationGraph] = None
    mevf: Optional[MEVFObject] = None
    vrap: Optional[VRAPManifest] = None
    bundle: dict[str, str] = field(default_factory=dict)
    scene_count: int = 0
    base64_packet: str = ""
    description: str = ""
    view_count: int = 0
    machine_queries: int = 0

    def to_public_dict(self) -> dict:
        """Public-facing metadata (no bundle content)."""
        return {
            "episode_id": self.episode_id,
            "title": self.title,
            "question": self.question,
            "status": self.status.value,
            "topic_tags": self.topic_tags,
            "created_at": self.created_at,
            "compiled_at": self.compiled_at,
            "published_at": self.published_at,
            "duration_seconds": self.duration_seconds,
            "trust_grade": self.trust_grade,
            "avg_buyability": round(self.avg_buyability, 3),
            "claim_count": self.claim_count,
            "segment_count": self.segment_count,
            "paper_count": self.paper_count,
            "total_price_usd": round(self.total_price_usd, 2),
            "receipt_hash": self.receipt_hash,
            "scene_count": self.scene_count,
            "description": self.description,
            "view_count": self.view_count,
            "machine_queries": self.machine_queries,
        }

    def to_compact_dict(self) -> dict:
        """Compact metadata for feed/list views."""
        return {
            "id": self.episode_id,
            "title": self.title,
            "question": self.question[:80],
            "status": self.status.value,
            "grade": self.trust_grade,
            "buyability": round(self.avg_buyability, 2),
            "claims": self.claim_count,
            "price": round(self.total_price_usd, 2),
            "tags": self.topic_tags[:5],
            "duration": round(self.duration_seconds, 1),
        }


@dataclass
class Playlist:
    """A curated collection of episodes."""
    playlist_id: str = ""
    title: str = ""
    description: str = ""
    episode_ids: list[str] = field(default_factory=list)
    created_at: float = 0.0
    curator: str = ""

    def to_dict(self) -> dict:
        return {
            "playlist_id": self.playlist_id,
            "title": self.title,
            "description": self.description,
            "episode_ids": self.episode_ids,
            "episode_count": len(self.episode_ids),
            "created_at": self.created_at,
            "curator": self.curator,
        }


@dataclass
class Subscription:
    """A topic-based subscription."""
    subscription_id: str = ""
    topic: str = ""
    subscriber_id: str = ""
    created_at: float = 0.0
    notify_on_publish: bool = True
    min_trust_grade: str = "F"

    def to_dict(self) -> dict:
        return {
            "subscription_id": self.subscription_id,
            "topic": self.topic,
            "subscriber_id": self.subscriber_id,
            "created_at": self.created_at,
            "notify_on_publish": self.notify_on_publish,
            "min_trust_grade": self.min_trust_grade,
        }


@dataclass
class ChannelAnalytics:
    """Aggregate analytics across all episodes."""
    total_episodes: int = 0
    published_episodes: int = 0
    draft_episodes: int = 0
    compiled_episodes: int = 0
    archived_episodes: int = 0
    total_claims: int = 0
    total_papers: int = 0
    total_segments: int = 0
    total_duration_seconds: float = 0.0
    total_price_usd: float = 0.0
    avg_buyability: float = 0.0
    grade_distribution: dict[str, int] = field(default_factory=dict)
    status_distribution: dict[str, int] = field(default_factory=dict)
    topic_distribution: dict[str, int] = field(default_factory=dict)
    total_views: int = 0
    total_machine_queries: int = 0
    total_playlists: int = 0
    total_subscriptions: int = 0
    receipt_chain_verified: bool = False

    def to_dict(self) -> dict:
        return {
            "total_episodes": self.total_episodes,
            "published_episodes": self.published_episodes,
            "draft_episodes": self.draft_episodes,
            "compiled_episodes": self.compiled_episodes,
            "archived_episodes": self.archived_episodes,
            "total_claims": self.total_claims,
            "total_papers": self.total_papers,
            "total_segments": self.total_segments,
            "total_duration_seconds": round(self.total_duration_seconds, 1),
            "total_price_usd": round(self.total_price_usd, 2),
            "avg_buyability": round(self.avg_buyability, 3),
            "grade_distribution": self.grade_distribution,
            "status_distribution": self.status_distribution,
            "topic_distribution": self.topic_distribution,
            "total_views": self.total_views,
            "total_machine_queries": self.total_machine_queries,
            "total_playlists": self.total_playlists,
            "total_subscriptions": self.total_subscriptions,
            "receipt_chain_verified": self.receipt_chain_verified,
        }


class InvestigationYouTubeOS:
    """
    Channel-grade operating system for evidence-backed research media.

    Manages a YouTube-like channel where each "video" is a fully compiled
    investigation with MEVF segments, VRAP bundles, machine scores, and
    tamper-evident receipts.

    Usage:
        os = InvestigationYouTubeOS(channel_name="Resonance Research")
        ep = os.create_episode("Can ancient stone structures exhibit resonance?")
        os.compile_episode(ep.episode_id)
        os.publish_episode(ep.episode_id)
        analytics = os.analytics()
        feed = os.feed()
    """

    def __init__(self, channel_name: str = "Investigation Channel", channel_id: str = ""):
        self.channel_name = channel_name
        self.channel_id = channel_id or f"chan_{uuid.uuid4().hex[:12]}"
        self.created_at = time.time()
        self._episodes: dict[str, Episode] = {}
        self._playlists: dict[str, Playlist] = {}
        self._subscriptions: dict[str, Subscription] = {}
        self._receipt_chain: list[dict] = []
        self._compiler = VideoLakeCompiler()

    # ── Episode Lifecycle ──────────────────────────────────────────

    def create_episode(
        self,
        question: str,
        title: str = "",
        topic_tags: list[str] | None = None,
        description: str = "",
    ) -> Episode:
        """Register a new investigation question as a draft episode."""
        ep_id = f"ep_{uuid.uuid4().hex[:12]}"
        ep = Episode(
            episode_id=ep_id,
            title=title or question[:80],
            question=question,
            topic_tags=topic_tags or [],
            description=description,
            created_at=time.time(),
        )
        self._episodes[ep_id] = ep
        self._add_receipt("create_episode", ep_id, {"question": question})
        return ep

    def compile_episode(self, episode_id: str) -> Episode:
        """Compile a draft episode into a full VideoLake result."""
        ep = self._episodes.get(episode_id)
        if not ep:
            raise KeyError(f"Episode not found: {episode_id}")
        if ep.status not in (EpisodeStatus.DRAFT, EpisodeStatus.COMPILED):
            raise ValueError(f"Cannot compile episode in status: {ep.status.value}")

        result = self._compiler.compile(
            question=ep.question,
            compile_video=True,
            write_receipts=True,
            export_b64=True,
        )

        ep.investigation = result.investigation
        ep.mevf = result.mevf
        ep.vrap = result.vrap
        ep.bundle = result.bundle
        ep.base64_packet = result.base64_packet
        ep.receipt_hash = result.receipt_hash
        ep.compiled_at = time.time()
        ep.status = EpisodeStatus.COMPILED

        if result.investigation:
            ep.claim_count = len(result.investigation.claims)
            ep.paper_count = len(result.investigation.papers)
        if result.mevf:
            ep.segment_count = len(result.mevf.segments)
            ep.duration_seconds = sum(s.duration_seconds for s in result.mevf.segments)
            ep.avg_buyability = result.mevf.avg_machine_buyability
            ep.trust_grade = result.mevf.trust_grade
        if result.vrap:
            ep.total_price_usd = result.vrap.total_price_usd
        ep.scene_count = len(result.scene_graph)

        # Auto-extract topic tags from investigation if not provided
        if not ep.topic_tags and result.investigation:
            ep.topic_tags = self._extract_topics(result.investigation)

        self._add_receipt("compile_episode", episode_id, {
            "claims": ep.claim_count,
            "segments": ep.segment_count,
            "grade": ep.trust_grade,
            "buyability": ep.avg_buyability,
        })

        return ep

    def publish_episode(self, episode_id: str) -> Episode:
        """Publish a compiled episode to the feed."""
        ep = self._episodes.get(episode_id)
        if not ep:
            raise KeyError(f"Episode not found: {episode_id}")
        if ep.status != EpisodeStatus.COMPILED:
            raise ValueError(f"Episode must be compiled first (current: {ep.status.value})")

        ep.status = EpisodeStatus.PUBLISHED
        ep.published_at = time.time()
        self._add_receipt("publish_episode", episode_id, {"published_at": ep.published_at})
        return ep

    def archive_episode(self, episode_id: str) -> Episode:
        """Archive a published episode (retained for provenance)."""
        ep = self._episodes.get(episode_id)
        if not ep:
            raise KeyError(f"Episode not found: {episode_id}")

        ep.status = EpisodeStatus.ARCHIVED
        self._add_receipt("archive_episode", episode_id, {})
        return ep

    def get_episode(self, episode_id: str) -> Optional[Episode]:
        return self._episodes.get(episode_id)

    def list_episodes(
        self,
        status: EpisodeStatus | None = None,
        topic: str | None = None,
        min_grade: str | None = None,
        min_buyability: float | None = None,
        limit: int = 50,
    ) -> list[Episode]:
        """List episodes with optional filters."""
        episodes = list(self._episodes.values())

        if status:
            episodes = [e for e in episodes if e.status == status]
        if topic:
            episodes = [e for e in episodes if topic.lower() in [t.lower() for t in e.topic_tags]]
        if min_grade:
            grade_order = ["F", "D", "C", "B", "A"]
            min_idx = grade_order.index(min_grade) if min_grade in grade_order else 0
            episodes = [
                e for e in episodes
                if e.trust_grade and grade_order.index(e.trust_grade) >= min_idx
                if e.trust_grade in grade_order
            ]
        if min_buyability is not None:
            episodes = [e for e in episodes if e.avg_buyability >= min_buyability]

        episodes.sort(key=lambda e: e.created_at, reverse=True)
        return episodes[:limit]

    def record_view(self, episode_id: str) -> None:
        """Record a human view on an episode."""
        ep = self._episodes.get(episode_id)
        if ep:
            ep.view_count += 1

    def record_machine_query(self, episode_id: str) -> None:
        """Record a machine agent query on an episode."""
        ep = self._episodes.get(episode_id)
        if ep:
            ep.machine_queries += 1

    # ── Playlists ──────────────────────────────────────────────────

    def create_playlist(
        self,
        title: str,
        description: str = "",
        episode_ids: list[str] | None = None,
        curator: str = "channel_owner",
    ) -> Playlist:
        """Create a curated playlist of episodes."""
        pl_id = f"pl_{uuid.uuid4().hex[:12]}"
        pl = Playlist(
            playlist_id=pl_id,
            title=title,
            description=description,
            episode_ids=episode_ids or [],
            created_at=time.time(),
            curator=curator,
        )
        self._playlists[pl_id] = pl
        self._add_receipt("create_playlist", pl_id, {"title": title})
        return pl

    def add_to_playlist(self, playlist_id: str, episode_id: str) -> Playlist:
        """Add an episode to a playlist."""
        pl = self._playlists.get(playlist_id)
        if not pl:
            raise KeyError(f"Playlist not found: {playlist_id}")
        if episode_id not in self._episodes:
            raise KeyError(f"Episode not found: {episode_id}")
        if episode_id not in pl.episode_ids:
            pl.episode_ids.append(episode_id)
        return pl

    def remove_from_playlist(self, playlist_id: str, episode_id: str) -> Playlist:
        """Remove an episode from a playlist."""
        pl = self._playlists.get(playlist_id)
        if not pl:
            raise KeyError(f"Playlist not found: {playlist_id}")
        if episode_id in pl.episode_ids:
            pl.episode_ids.remove(episode_id)
        return pl

    def get_playlist(self, playlist_id: str) -> Optional[Playlist]:
        return self._playlists.get(playlist_id)

    def list_playlists(self) -> list[Playlist]:
        return list(self._playlists.values())

    # ── Subscriptions ──────────────────────────────────────────────

    def subscribe(
        self,
        topic: str,
        subscriber_id: str = "anonymous",
        min_trust_grade: str = "F",
        notify_on_publish: bool = True,
    ) -> Subscription:
        """Subscribe to a topic. Notified when new episodes match."""
        sub_id = f"sub_{uuid.uuid4().hex[:12]}"
        sub = Subscription(
            subscription_id=sub_id,
            topic=topic.lower(),
            subscriber_id=subscriber_id,
            created_at=time.time(),
            notify_on_publish=notify_on_publish,
            min_trust_grade=min_trust_grade,
        )
        self._subscriptions[sub_id] = sub
        self._add_receipt("subscribe", sub_id, {"topic": topic.lower(), "subscriber_id": subscriber_id})
        return sub

    def unsubscribe(self, subscription_id: str) -> bool:
        if subscription_id in self._subscriptions:
            del self._subscriptions[subscription_id]
            return True
        return False

    def list_subscriptions(self) -> list[Subscription]:
        return list(self._subscriptions.values())

    def check_notifications(self) -> list[dict]:
        """Check for published episodes matching subscriptions."""
        notifications = []
        for sub in self._subscriptions.values():
            matching = self.list_episodes(
                status=EpisodeStatus.PUBLISHED,
                topic=sub.topic,
            )
            grade_order = ["F", "D", "C", "B", "A"]
            min_idx = grade_order.index(sub.min_trust_grade) if sub.min_trust_grade in grade_order else 0
            matching = [
                e for e in matching
                if e.trust_grade in grade_order
                and grade_order.index(e.trust_grade) >= min_idx
                and e.published_at > sub.created_at
            ]
            for ep in matching:
                notifications.append({
                    "subscription_id": sub.subscription_id,
                    "topic": sub.topic,
                    "subscriber_id": sub.subscriber_id,
                    "episode_id": ep.episode_id,
                    "episode_title": ep.title,
                    "trust_grade": ep.trust_grade,
                })
        return notifications

    # ── Feed ───────────────────────────────────────────────────────

    def feed(self, limit: int = 20) -> dict:
        """Generate a JSON feed of published episodes (RSS-like)."""
        published = self.list_episodes(status=EpisodeStatus.PUBLISHED, limit=limit)
        return {
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "feed_type": "investigation_evidence_feed_v1",
            "generated_at": time.time(),
            "episode_count": len(published),
            "episodes": [e.to_compact_dict() for e in published],
        }

    # ── Search ─────────────────────────────────────────────────────

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Search episodes by question, title, topic tags, or claim text."""
        query_lower = query.lower()
        results = []
        for ep in self._episodes.values():
            score = 0
            if query_lower in ep.title.lower():
                score += 3
            if query_lower in ep.question.lower():
                score += 3
            for tag in ep.topic_tags:
                if query_lower in tag.lower():
                    score += 2
            if ep.investigation:
                for claim in ep.investigation.claims:
                    if query_lower in claim.claim_text.lower():
                        score += 1
            if score > 0:
                results.append({
                    "episode": ep.to_compact_dict(),
                    "relevance_score": score,
                })
        results.sort(key=lambda x: x["relevance_score"], reverse=True)
        return results[:limit]

    # ── Analytics ──────────────────────────────────────────────────

    def analytics(self) -> ChannelAnalytics:
        """Compute aggregate analytics across all episodes."""
        episodes = list(self._episodes.values())
        published = [e for e in episodes if e.status == EpisodeStatus.PUBLISHED]
        drafts = [e for e in episodes if e.status == EpisodeStatus.DRAFT]
        compiled = [e for e in episodes if e.status == EpisodeStatus.COMPILED]
        archived = [e for e in episodes if e.status == EpisodeStatus.ARCHIVED]

        grade_dist: dict[str, int] = {}
        status_dist: dict[str, int] = {}
        topic_dist: dict[str, int] = {}

        total_claims = 0
        total_papers = 0
        total_segments = 0
        total_duration = 0.0
        total_price = 0.0
        buyability_sum = 0.0
        buyability_count = 0
        total_views = 0
        total_mq = 0

        for ep in episodes:
            status_dist[ep.status.value] = status_dist.get(ep.status.value, 0) + 1
            if ep.trust_grade:
                grade_dist[ep.trust_grade] = grade_dist.get(ep.trust_grade, 0) + 1
            for tag in ep.topic_tags:
                topic_dist[tag] = topic_dist.get(tag, 0) + 1
            total_claims += ep.claim_count
            total_papers += ep.paper_count
            total_segments += ep.segment_count
            total_duration += ep.duration_seconds
            total_price += ep.total_price_usd
            if ep.avg_buyability > 0:
                buyability_sum += ep.avg_buyability
                buyability_count += 1
            total_views += ep.view_count
            total_mq += ep.machine_queries

        return ChannelAnalytics(
            total_episodes=len(episodes),
            published_episodes=len(published),
            draft_episodes=len(drafts),
            compiled_episodes=len(compiled),
            archived_episodes=len(archived),
            total_claims=total_claims,
            total_papers=total_papers,
            total_segments=total_segments,
            total_duration_seconds=total_duration,
            total_price_usd=total_price,
            avg_buyability=buyability_sum / buyability_count if buyability_count else 0.0,
            grade_distribution=grade_dist,
            status_distribution=status_dist,
            topic_distribution=topic_dist,
            total_views=total_views,
            total_machine_queries=total_mq,
            total_playlists=len(self._playlists),
            total_subscriptions=len(self._subscriptions),
            receipt_chain_verified=self.verify_receipts(),
        )

    # ── Machine Query ──────────────────────────────────────────────

    def machine_query(
        self,
        topic: str | None = None,
        min_buyability: float = 0.0,
        min_trust_grade: str = "F",
        rights_status: str | None = None,
        for_sale_only: bool = False,
        limit: int = 20,
    ) -> list[dict]:
        """Machine-agent query across all published episodes.

        Returns segments matching criteria across all episodes.
        """
        results = []
        grade_order = ["F", "D", "C", "B", "A"]
        min_idx = grade_order.index(min_trust_grade) if min_trust_grade in grade_order else 0

        for ep in self._episodes.values():
            if ep.status != EpisodeStatus.PUBLISHED:
                continue
            if ep.trust_grade not in grade_order:
                continue
            if grade_order.index(ep.trust_grade) < min_idx:
                continue
            if topic and topic.lower() not in [t.lower() for t in ep.topic_tags]:
                continue

            if ep.mevf:
                segments = query_segments(
                    ep.mevf,
                    min_buyability=min_buyability,
                    rights_status=rights_status,
                    for_sale_only=for_sale_only,
                )
                for seg in segments:
                    results.append({
                        "episode_id": ep.episode_id,
                        "episode_title": ep.title,
                        "segment_id": seg.segment_id,
                        "claim": seg.claim[:80],
                        "status": seg.claim_status,
                        "buyability": seg.scores.machine_buyability_score,
                        "trust_grade": seg.scores.trust_grade,
                        "rights": seg.rights_status,
                        "price": seg.price_per_render,
                        "for_sale": seg.is_for_sale,
                    })
                    ep.machine_queries += 1

        results.sort(key=lambda x: x["buyability"], reverse=True)
        return results[:limit]

    # ── Receipt Ledger ─────────────────────────────────────────────

    def _add_receipt(self, action: str, entity_id: str, data: dict) -> None:
        """Add a receipt entry to the channel ledger."""
        prev_hash = self._receipt_chain[-1]["hash"] if self._receipt_chain else ""
        entry = {
            "receipt_id": f"rct_{uuid.uuid4().hex[:8]}",
            "action": action,
            "entity_id": entity_id,
            "timestamp": time.time(),
            "data": data,
            "prev_hash": prev_hash,
        }
        entry_str = json.dumps({
            "action": action,
            "entity_id": entity_id,
            "timestamp": entry["timestamp"],
            "data": data,
            "prev_hash": prev_hash,
        }, sort_keys=True)
        entry["hash"] = f"sha256:{hashlib.sha256(entry_str.encode()).hexdigest()[:16]}"
        self._receipt_chain.append(entry)

    def get_receipts(self) -> list[dict]:
        return list(self._receipt_chain)

    def verify_receipts(self) -> bool:
        """Verify the integrity of the receipt chain."""
        for i, entry in enumerate(self._receipt_chain):
            prev_hash = self._receipt_chain[i - 1]["hash"] if i > 0 else ""
            if entry["prev_hash"] != prev_hash:
                return False
            entry_str = json.dumps({
                "action": entry["action"],
                "entity_id": entry["entity_id"],
                "timestamp": entry["timestamp"],
                "data": entry["data"],
                "prev_hash": prev_hash,
            }, sort_keys=True)
            computed = f"sha256:{hashlib.sha256(entry_str.encode()).hexdigest()[:16]}"
            if entry["hash"] != computed:
                return False
        return True

    # ── Channel Manifest ───────────────────────────────────────────

    def channel_manifest(self) -> dict:
        """Top-level channel manifest."""
        analytics = self.analytics()
        return {
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "created_at": self.created_at,
            "platform": "investigation_youtube_os_v1",
            "description": "Evidence-backed research media channel",
            "total_episodes": analytics.total_episodes,
            "published_episodes": analytics.published_episodes,
            "total_claims": analytics.total_claims,
            "total_papers": analytics.total_papers,
            "avg_buyability": round(analytics.avg_buyability, 3),
            "grade_distribution": analytics.grade_distribution,
            "receipt_chain_verified": analytics.receipt_chain_verified,
            "receipt_count": len(self._receipt_chain),
            "total_playlists": analytics.total_playlists,
            "total_subscriptions": analytics.total_subscriptions,
        }

    # ── Export / Import ────────────────────────────────────────────

    def export_channel(self) -> dict:
        """Export the full channel state (metadata only, no bundles)."""
        return {
            "manifest": self.channel_manifest(),
            "episodes": [e.to_public_dict() for e in self._episodes.values()],
            "playlists": [pl.to_dict() for pl in self._playlists.values()],
            "subscriptions": [s.to_dict() for s in self._subscriptions.values()],
            "receipts": self._receipt_chain,
            "analytics": self.analytics().to_dict(),
        }

    def export_episode_bundle(self, episode_id: str) -> dict[str, str]:
        """Export the full VRAP bundle for a specific episode."""
        ep = self._episodes.get(episode_id)
        if not ep:
            raise KeyError(f"Episode not found: {episode_id}")
        return dict(ep.bundle)

    # ── Helpers ────────────────────────────────────────────────────

    def _extract_topics(self, investigation: InvestigationGraph) -> list[str]:
        """Auto-extract topic tags from an investigation."""
        text = investigation.question.lower()
        topics = []
        topic_keywords = {
            "resonance": ["resonance", "frequency", "vibration", "oscillation"],
            "ancient structures": ["ancient", "megalithic", "stone", "archaeological"],
            "energy": ["energy", "field", "electromagnetic", "power"],
            "geology": ["earth", "geology", "seismic", "tectonic"],
            "physics": ["physics", "quantum", "particle", "wave"],
            "biology": ["biological", "cell", "organism", "dna"],
            "climate": ["climate", "temperature", "atmosphere", "carbon"],
            "astronomy": ["space", "star", "planet", "cosmic", "nasa"],
            "medicine": ["health", "medical", "disease", "treatment"],
            "technology": ["technology", "algorithm", "computer", "ai"],
        }
        for topic, keywords in topic_keywords.items():
            if any(kw in text for kw in keywords):
                topics.append(topic)
        return topics[:5] if topics else ["general"]


def create_youtube_os_api(os: InvestigationYouTubeOS):
    """Create a FastAPI application for the Investigation YouTube OS.

    Returns a FastAPI app with all channel endpoints.
    Requires fastapi to be installed.
    """
    from fastapi import FastAPI, HTTPException, Query
    from pydantic import BaseModel

    app = FastAPI(
        title=f"{os.channel_name} — Investigation YouTube OS",
        description="Evidence-backed research media channel API",
        version="1.0.0",
    )

    # ── Request Models ──────────────────────────────────────

    class CreateEpisodeRequest(BaseModel):
        question: str
        title: str = ""
        topic_tags: list[str] = []
        description: str = ""
        compile: bool = True
        publish: bool = False

    class CreatePlaylistRequest(BaseModel):
        title: str
        description: str = ""
        episode_ids: list[str] = []
        curator: str = "api_user"

    class AddToPlaylistRequest(BaseModel):
        episode_id: str

    class SubscribeRequest(BaseModel):
        topic: str
        subscriber_id: str = "api_user"
        min_trust_grade: str = "F"
        notify_on_publish: bool = True

    # ── Channel Endpoints ───────────────────────────────────

    @app.get("/channel")
    def channel_manifest():
        return os.channel_manifest()

    @app.get("/channel/episodes")
    def list_episodes(
        status: str | None = None,
        topic: str | None = None,
        min_grade: str | None = None,
        min_buyability: float | None = None,
        limit: int = 50,
    ):
        ep_status = None
        if status:
            try:
                ep_status = EpisodeStatus(status)
            except ValueError:
                raise HTTPException(400, f"Invalid status: {status}")
        episodes = os.list_episodes(
            status=ep_status, topic=topic, min_grade=min_grade,
            min_buyability=min_buyability, limit=limit,
        )
        return {"episodes": [e.to_compact_dict() for e in episodes], "count": len(episodes)}

    @app.get("/channel/episodes/{episode_id}")
    def get_episode(episode_id: str):
        ep = os.get_episode(episode_id)
        if not ep:
            raise HTTPException(404, "Episode not found")
        os.record_view(episode_id)
        return ep.to_public_dict()

    @app.get("/channel/episodes/{episode_id}/bundle")
    def get_episode_bundle(episode_id: str):
        ep = os.get_episode(episode_id)
        if not ep:
            raise HTTPException(404, "Episode not found")
        if not ep.bundle:
            raise HTTPException(400, "Episode not compiled")
        return {"episode_id": episode_id, "files": list(ep.bundle.keys()), "bundle": ep.bundle}

    @app.get("/channel/episodes/{episode_id}/segments")
    def get_episode_segments(
        episode_id: str,
        min_buyability: float = 0.0,
        rights_status: str | None = None,
        for_sale_only: bool = False,
    ):
        ep = os.get_episode(episode_id)
        if not ep or not ep.mevf:
            raise HTTPException(404, "Episode not found or not compiled")
        segments = query_segments(
            ep.mevf, min_buyability=min_buyability,
            rights_status=rights_status, for_sale_only=for_sale_only,
        )
        return {
            "episode_id": episode_id,
            "segment_count": len(segments),
            "segments": [s.to_dict() for s in segments],
        }

    @app.post("/channel/episodes")
    def create_episode(req: CreateEpisodeRequest):
        ep = os.create_episode(
            question=req.question, title=req.title,
            topic_tags=req.topic_tags, description=req.description,
        )
        if req.compile:
            ep = os.compile_episode(ep.episode_id)
        if req.publish and ep.status == EpisodeStatus.COMPILED:
            ep = os.publish_episode(ep.episode_id)
        return ep.to_public_dict()

    @app.post("/channel/episodes/{episode_id}/publish")
    def publish_episode(episode_id: str):
        try:
            ep = os.publish_episode(episode_id)
            return ep.to_public_dict()
        except KeyError:
            raise HTTPException(404, "Episode not found")
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/channel/episodes/{episode_id}/archive")
    def archive_episode(episode_id: str):
        try:
            ep = os.archive_episode(episode_id)
            return ep.to_public_dict()
        except KeyError:
            raise HTTPException(404, "Episode not found")

    # ── Feed ─────────────────────────────────────────────────

    @app.get("/channel/feed")
    def feed(limit: int = 20):
        return os.feed(limit=limit)

    # ── Search ───────────────────────────────────────────────

    @app.get("/channel/search")
    def search(q: str = Query(...), limit: int = 20):
        results = os.search(q, limit=limit)
        return {"query": q, "results": results, "count": len(results)}

    # ── Playlists ────────────────────────────────────────────

    @app.get("/channel/playlists")
    def list_playlists():
        return {"playlists": [pl.to_dict() for pl in os.list_playlists()]}

    @app.get("/channel/playlists/{playlist_id}")
    def get_playlist(playlist_id: str):
        pl = os.get_playlist(playlist_id)
        if not pl:
            raise HTTPException(404, "Playlist not found")
        episodes = [os.get_episode(eid) for eid in pl.episode_ids]
        return {
            **pl.to_dict(),
            "episodes": [e.to_compact_dict() for e in episodes if e],
        }

    @app.post("/channel/playlists")
    def create_playlist(req: CreatePlaylistRequest):
        pl = os.create_playlist(
            title=req.title, description=req.description,
            episode_ids=req.episode_ids, curator=req.curator,
        )
        return pl.to_dict()

    @app.post("/channel/playlists/{playlist_id}/add")
    def add_to_playlist(playlist_id: str, req: AddToPlaylistRequest):
        try:
            pl = os.add_to_playlist(playlist_id, req.episode_id)
            return pl.to_dict()
        except KeyError as e:
            raise HTTPException(404, str(e))

    # ── Subscriptions ────────────────────────────────────────

    @app.get("/channel/subscriptions")
    def list_subscriptions():
        return {"subscriptions": [s.to_dict() for s in os.list_subscriptions()]}

    @app.post("/channel/subscriptions")
    def subscribe(req: SubscribeRequest):
        sub = os.subscribe(
            topic=req.topic, subscriber_id=req.subscriber_id,
            min_trust_grade=req.min_trust_grade, notify_on_publish=req.notify_on_publish,
        )
        return sub.to_dict()

    @app.get("/channel/notifications")
    def notifications():
        return {"notifications": os.check_notifications()}

    # ── Analytics ────────────────────────────────────────────

    @app.get("/channel/analytics")
    def analytics():
        return os.analytics().to_dict()

    # ── Machine Query ────────────────────────────────────────

    @app.get("/channel/machine-query")
    def machine_query(
        topic: str | None = None,
        min_buyability: float = 0.0,
        min_trust_grade: str = "F",
        rights_status: str | None = None,
        for_sale_only: bool = False,
        limit: int = 20,
    ):
        results = os.machine_query(
            topic=topic, min_buyability=min_buyability,
            min_trust_grade=min_trust_grade, rights_status=rights_status,
            for_sale_only=for_sale_only, limit=limit,
        )
        return {"results": results, "count": len(results)}

    # ── Receipts ─────────────────────────────────────────────

    @app.get("/channel/receipts")
    def receipts():
        return {"receipts": os.get_receipts(), "count": len(os.get_receipts())}

    @app.get("/channel/receipts/verify")
    def verify_receipts():
        verified = os.verify_receipts()
        return {"verified": verified, "receipt_count": len(os.get_receipts())}

    # ── Export ───────────────────────────────────────────────

    @app.get("/channel/export")
    def export_channel():
        return os.export_channel()

    return app
