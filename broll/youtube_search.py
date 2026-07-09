"""
YouTube Data API integration — real video search + caption retrieval.

Uses YouTube Data API v3 to:
1. Search videos by semantic search terms
2. Retrieve video metadata (duration, channel, tags)
3. List and download caption tracks when available
4. Match captions against speaker transcript

Reference: https://developers.google.com/youtube/v3/docs/search/list

Requires a YouTube Data API key. When no key is provided, falls back
to the local corpus search in VideoSearch.
"""

import hashlib
import json
import re
import time
import urllib.request
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional
from collections import Counter


@dataclass
class YouTubeVideo:
    """A video result from YouTube Data API."""
    video_id: str
    title: str
    channel: str
    channel_id: str = ""
    description: str = ""
    published_at: str = ""
    duration_seconds: float = 0.0
    view_count: int = 0
    like_count: int = 0
    tags: list[str] = field(default_factory=list)
    thumbnail_url: str = ""
    caption_available: bool = False
    caption_text: str = ""
    url: str = ""

    def to_dict(self) -> dict:
        return {
            "video_id": self.video_id,
            "title": self.title,
            "channel": self.channel,
            "channel_id": self.channel_id,
            "description": self.description,
            "published_at": self.published_at,
            "duration_seconds": self.duration_seconds,
            "view_count": self.view_count,
            "like_count": self.like_count,
            "tags": self.tags,
            "thumbnail_url": self.thumbnail_url,
            "caption_available": self.caption_available,
            "caption_text": self.caption_text[:500] if self.caption_text else "",
            "url": self.url or f"https://www.youtube.com/watch?v={self.video_id}",
        }


@dataclass
class CaptionTrack:
    """A caption track for a YouTube video."""
    track_id: str
    language: str
    name: str
    is_auto: bool = False
    segments: list[dict] = field(default_factory=list)  # {"start": float, "end": float, "text": str}

    def to_dict(self) -> dict:
        return {
            "track_id": self.track_id,
            "language": self.language,
            "name": self.name,
            "is_auto": self.is_auto,
            "segment_count": len(self.segments),
            "segments": self.segments[:20],  # first 20 for preview
        }


class YouTubeSearch:
    """
    YouTube Data API v3 integration.

    Requires an API key obtained from Google Cloud Console.
    When no key is provided, methods raise or return empty results.

    Usage:
        search = YouTubeSearch(api_key="YOUR_KEY")
        results = search.search_videos("Stonehenge sunrise documentary", max_results=10)
        captions = search.get_captions(results[0].video_id)
    """

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key: str = "", max_quota_per_day: int = 10000):
        self.api_key = api_key
        self.max_quota = max_quota_per_day
        self._quota_used = 0
        self._has_key = bool(api_key)

    @property
    def has_api_key(self) -> bool:
        return self._has_key

    @property
    def quota_remaining(self) -> int:
        return max(0, self.max_quota - self._quota_used)

    def search_videos(
        self,
        query: str,
        max_results: int = 10,
        order: str = "relevance",
        video_duration: str = "",  # "short" (<4min), "medium" (4-20min), "long" (>20min)
        video_license: str = "",  # "creativeCommon" or "youtube"
        region_code: str = "",
    ) -> list[YouTubeVideo]:
        """
        Search YouTube videos using Data API v3.

        Args:
            query: Search query string
            max_results: Maximum number of results (1-50)
            order: "relevance", "date", "rating", "viewCount"
            video_duration: Filter by duration category
            video_license: Filter by license type
            region_code: ISO 3166-1 alpha-2 country code

        Returns:
            List of YouTubeVideo objects

        Quota cost: 100 units per search request
        """
        if not self._has_key:
            return []

        params: dict[str, str] = {
            "part": "snippet",
            "q": query,
            "type": "video",
            "maxResults": str(min(max_results, 50)),
            "order": order,
            "key": self.api_key,
        }

        if video_duration:
            params["videoDuration"] = video_duration
        if video_license:
            params["videoLicense"] = video_license
        if region_code:
            params["regionCode"] = region_code

        url = f"{self.BASE_URL}/search?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "VideoLake/1.0"})

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            self._quota_used += 100

            videos: list[YouTubeVideo] = []
            for item in data.get("items", []):
                vid = item.get("id", {}).get("videoId", "")
                if not vid:
                    continue
                snippet = item.get("snippet", {})
                videos.append(YouTubeVideo(
                    video_id=vid,
                    title=snippet.get("title", ""),
                    channel=snippet.get("channelTitle", ""),
                    channel_id=snippet.get("channelId", ""),
                    description=snippet.get("description", ""),
                    published_at=snippet.get("publishedAt", ""),
                    thumbnail_url=snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
                    url=f"https://www.youtube.com/watch?v={vid}",
                ))
            return videos
        except Exception:
            return []

    def get_video_details(self, video_id: str) -> YouTubeVideo | None:
        """
        Get detailed metadata for a single video.

        Quota cost: 1 unit per video
        """
        if not self._has_key:
            return None

        params = {
            "part": "snippet,statistics,contentDetails",
            "id": video_id,
            "key": self.api_key,
        }
        url = f"{self.BASE_URL}/videos?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "VideoLake/1.0"})

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            self._quota_used += 1

            items = data.get("items", [])
            if not items:
                return None

            item = items[0]
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            content = item.get("contentDetails", {})

            duration_str = content.get("duration", "PT0S")
            duration_sec = self._parse_iso8601_duration(duration_str)

            return YouTubeVideo(
                video_id=video_id,
                title=snippet.get("title", ""),
                channel=snippet.get("channelTitle", ""),
                channel_id=snippet.get("channelId", ""),
                description=snippet.get("description", ""),
                published_at=snippet.get("publishedAt", ""),
                duration_seconds=duration_sec,
                view_count=int(stats.get("viewCount", 0)),
                like_count=int(stats.get("likeCount", 0)),
                tags=snippet.get("tags", []),
                thumbnail_url=snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
                url=f"https://www.youtube.com/watch?v={video_id}",
            )
        except Exception:
            return None

    def get_captions(self, video_id: str) -> list[CaptionTrack]:
        """
        List and download caption tracks for a video.

        Note: YouTube's captions API requires OAuth2 authentication,
        not just an API key. The caption download endpoint requires
        the video owner's permission or specific OAuth scopes.

        For third-party videos, captions can be accessed via:
        1. YouTube's timedtext API (when captions are publicly available)
        2. youtube-transcript-api library (third-party)

        Quota cost: 50 units per caption list request
        """
        if not self._has_key:
            return []

        params = {"part": "snippet", "videoId": video_id, "key": self.api_key}
        url = f"{self.BASE_URL}/captions?{urllib.parse.urlencode(params)}"
        req = urllib.request.Request(url, headers={"User-Agent": "VideoLake/1.0"})

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
            self._quota_used += 50

            tracks: list[CaptionTrack] = []
            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                tracks.append(CaptionTrack(
                    track_id=item.get("id", ""),
                    language=snippet.get("language", ""),
                    name=snippet.get("name", ""),
                    is_cc=snippet.get("trackKind", "") == "standard",
                    is_asr=snippet.get("trackKind", "") == "ASR",
                ))
            return tracks
        except Exception:
            return []

    @staticmethod
    def _parse_iso8601_duration(duration: str) -> float:
        """Parse ISO 8601 duration (e.g. PT1M30S) to seconds."""
        import re
        pattern = r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
        match = re.match(pattern, duration)
        if not match:
            return 0.0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    def get_transcript(self, video_id: str) -> str:
        """
        Get the full transcript text for a video.

        Uses youtube-transcript-api if available, otherwise returns empty.
        """
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            transcript = YouTubeTranscriptApi.get_transcript(video_id)
            return " ".join(seg["text"] for seg in transcript)
        except Exception:
            return ""

    def match_transcript(
        self,
        speaker_transcript: str,
        video_transcript: str,
    ) -> float:
        """
        Match a speaker's transcript against a video's caption transcript.

        Returns a similarity score 0.0 to 1.0 based on semantic overlap.
        """
        if not speaker_transcript or not video_transcript:
            return 0.0

        # Tokenize
        speaker_tokens = set(re.findall(r"[a-zA-Z]+", speaker_transcript.lower()))
        video_tokens = set(re.findall(r"[a-zA-Z]+", video_transcript.lower()))

        if not speaker_tokens or not video_tokens:
            return 0.0

        # Filter common words
        common = {"the", "a", "an", "is", "are", "was", "were", "be", "and", "or",
                  "but", "in", "on", "at", "to", "of", "for", "with", "from", "by",
                  "this", "that", "it", "as", "we", "you", "they", "he", "she"}
        speaker_tokens -= common
        video_tokens -= common

        if not speaker_tokens:
            return 0.0

        # Overlap score
        overlap = len(speaker_tokens & video_tokens)
        coverage = overlap / len(speaker_tokens)

        # Phrase matching
        speaker_phrases = self._extract_phrases(speaker_transcript)
        video_phrases = self._extract_phrases(video_transcript)
        phrase_matches = sum(1 for p in speaker_phrases if p in video_transcript.lower())
        phrase_score = phrase_matches / max(len(speaker_phrases), 1)

        return min(1.0, coverage * 0.6 + phrase_score * 0.4)

    def _extract_phrases(self, text: str) -> list[str]:
        """Extract 2-3 word phrases from text."""
        words = re.findall(r"[a-zA-Z]+", text.lower())
        phrases: list[str] = []
        for i in range(len(words) - 1):
            phrases.append(f"{words[i]} {words[i+1]}")
        return phrases

    def search_with_transcript_match(
        self,
        search_terms: list[str],
        speaker_transcript: str,
        max_results: int = 10,
    ) -> list[dict]:
        """
        Search YouTube and match results against speaker transcript.

        Combines keyword search with transcript-level semantic matching.

        Returns list of dicts with video info + transcript_match_score.
        """
        if not self._has_key:
            return []

        all_results: list[dict] = []

        for term in search_terms:
            videos = self.search_videos(term, max_results=max_results)
            for video in videos:
                # Get transcript
                transcript = self.get_transcript(video.video_id)
                match_score = self.match_transcript(speaker_transcript, transcript) if transcript else 0.0

                all_results.append({
                    "video": video.to_dict(),
                    "search_term": term,
                    "transcript_match_score": match_score,
                    "has_transcript": bool(transcript),
                })

        # Sort by transcript match score (videos with transcripts rank higher)
        all_results.sort(key=lambda x: -x["transcript_match_score"])
        return all_results[:max_results]
