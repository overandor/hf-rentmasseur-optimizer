"""
Rights Filter — License detection, source tracking, reuse status.

Critical rule: Do not download or reuse copyrighted footage without
explicit rights status. Do not insert clips automatically unless
rights status is safe.

Reuse statuses:
    safe          — public domain, Creative Commons, owned footage
    needs_review  — license unclear, requires manual verification
    blocked       — known copyright restriction, all rights reserved
    unknown       — no license information available

The rights filter is a hard gate: clips with "blocked" status are
never inserted into a timeline. Clips with "needs_review" or "unknown"
are flagged for manual approval.
"""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RightsStatus(Enum):
    """Reuse rights status for a video clip."""
    SAFE = "safe"
    NEEDS_REVIEW = "needs_review"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class LicenseType(Enum):
    """Detected license type."""
    PUBLIC_DOMAIN = "public_domain"
    CREATIVE_COMMONS = "creative_commons"
    CREATIVE_COMMONS_BY = "cc_by"
    CREATIVE_COMMONS_BY_SA = "cc_by_sa"
    CREATIVE_COMMONS_BY_NC = "cc_by_nc"
    CREATIVE_COMMONS_ZERO = "cc0"
    YOUTUBE_STANDARD = "youtube_standard"
    ALL_RIGHTS_RESERVED = "all_rights_reserved"
    OWNED = "owned"
    UNKNOWN = "unknown"


@dataclass
class RightsAssessment:
    """Rights assessment for a candidate video clip."""
    status: RightsStatus
    license_type: LicenseType
    source_url: str = ""
    source_platform: str = ""
    license_text: str = ""
    risk_flags: list[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "license_type": self.license_type.value,
            "source_url": self.source_url,
            "source_platform": self.source_platform,
            "license_text": self.license_text,
            "risk_flags": self.risk_flags,
            "notes": self.notes,
        }


# License detection patterns
_LICENSE_PATTERNS: dict[LicenseType, list[str]] = {
    LicenseType.CREATIVE_COMMONS_ZERO: ["cc0", "cc-0", "public domain dedication", "no copyright"],
    LicenseType.PUBLIC_DOMAIN: ["public domain", "pd", "government work", "nasa", "usgs", "noaa", "federal government"],
    LicenseType.CREATIVE_COMMONS_BY_SA: ["cc by-sa", "cc-by-sa", "creative commons attribution-sharealike"],
    LicenseType.CREATIVE_COMMONS_BY_NC: ["cc by-nc", "cc-by-nc", "creative commons attribution-noncommercial"],
    LicenseType.CREATIVE_COMMONS_BY: ["cc by", "cc-by", "creative commons attribution"],
    LicenseType.CREATIVE_COMMONS: ["creative commons", "cc license", "cc-licensed"],
    LicenseType.YOUTUBE_STANDARD: ["youtube standard license", "standard youtube license"],
    LicenseType.ALL_RIGHTS_RESERVED: ["all rights reserved", "(c)", "©", "copyright", "tm", "trademark"],
}

# Platform-specific license defaults
_PLATFORM_DEFAULTS: dict[str, RightsStatus] = {
    "youtube": RightsStatus.NEEDS_REVIEW,  # YouTube default is standard license unless CC
    "vimeo": RightsStatus.NEEDS_REVIEW,
    "pexels": RightsStatus.SAFE,  # Pexels license is free to use
    "pixabay": RightsStatus.SAFE,  # Pixabay license is free to use
    "wikimedia": RightsStatus.SAFE,  # Wikimedia Commons is CC or PD
    "archive.org": RightsStatus.NEEDS_REVIEW,  # Mixed licenses
    "local": RightsStatus.SAFE,  # Local/owned footage
    "stock": RightsStatus.NEEDS_REVIEW,  # Depends on specific stock license
}

# Risk indicators
_RISK_INDICATORS = {
    "music_video": "Contains music video content — likely copyrighted",
    "official_video": "Official channel video — may have distribution restrictions",
    "movie_clip": "Movie/TV clip — likely copyrighted",
    "trailer": "Trailer content — studio copyright likely",
    "news_broadcast": "News broadcast — network copyright likely",
    "sports_broadcast": "Sports broadcast — league copyright likely",
}


class RightsFilter:
    """
    License detector and rights risk assessor.

    Assesses the reuse rights status of candidate video clips.
    This is a hard gate: blocked clips are never inserted into timelines.

    Usage:
        filter = RightsFilter()
        assessment = filter.assess(
            title="Stonehenge Sunrise 4K Drone Footage",
            source="youtube",
            description="Creative Commons licensed footage",
            url="https://youtube.com/watch?v=...",
        )
        if assessment.status == RightsStatus.SAFE:
            # Can insert into timeline
        elif assessment.status == RightsStatus.BLOCKED:
            # Never insert
        else:
            # Flag for manual review
    """

    def __init__(self):
        self.license_patterns = dict(_LICENSE_PATTERNS)
        self.platform_defaults = dict(_PLATFORM_DEFAULTS)
        self.risk_indicators = dict(_RISK_INDICATORS)

    def detect_license(
        self,
        title: str = "",
        description: str = "",
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> LicenseType:
        """
        Detect license type from available text metadata.

        Checks title, description, tags, and metadata for license indicators.
        """
        combined = f"{title} {description}"
        if tags:
            combined += " " + " ".join(tags)
        if metadata:
            combined += " " + " ".join(str(v) for v in metadata.values())
        combined_lower = combined.lower()

        # Check each license pattern in priority order
        priority_order = [
            LicenseType.CREATIVE_COMMONS_ZERO,
            LicenseType.PUBLIC_DOMAIN,
            LicenseType.CREATIVE_COMMONS_BY_SA,
            LicenseType.CREATIVE_COMMONS_BY_NC,
            LicenseType.CREATIVE_COMMONS_BY,
            LicenseType.CREATIVE_COMMONS,
            LicenseType.YOUTUBE_STANDARD,
            LicenseType.ALL_RIGHTS_RESERVED,
        ]

        for license_type in priority_order:
            patterns = self.license_patterns.get(license_type, [])
            for pattern in patterns:
                if pattern in combined_lower:
                    return license_type

        # Check metadata for explicit license field
        if metadata:
            license_field = str(metadata.get("license", "")).lower()
            if "creative" in license_field or "cc" in license_field:
                return LicenseType.CREATIVE_COMMONS
            if "public domain" in license_field:
                return LicenseType.PUBLIC_DOMAIN

        return LicenseType.UNKNOWN

    def assess(
        self,
        title: str = "",
        source: str = "",
        description: str = "",
        url: str = "",
        tags: list[str] | None = None,
        metadata: dict | None = None,
    ) -> RightsAssessment:
        """
        Assess the rights status of a candidate video clip.

        Args:
            title: Video title
            source: Source platform (youtube, vimeo, pexels, local, etc.)
            description: Video description
            url: Source URL
            tags: Video tags
            metadata: Additional metadata (license field, channel info, etc.)

        Returns:
            RightsAssessment with status, license type, and risk flags
        """
        # Detect license
        license_type = self.detect_license(title, description, tags, metadata)

        # Detect risk indicators
        risk_flags: list[str] = []
        combined_lower = f"{title} {description}".lower()
        for indicator, warning in self.risk_indicators.items():
            if indicator in combined_lower:
                risk_flags.append(warning)

        # Determine rights status
        if license_type in (LicenseType.CREATIVE_COMMONS_ZERO, LicenseType.PUBLIC_DOMAIN):
            status = RightsStatus.SAFE
        elif license_type in (LicenseType.CREATIVE_COMMONS, LicenseType.CREATIVE_COMMONS_BY,
                              LicenseType.CREATIVE_COMMONS_BY_SA):
            status = RightsStatus.SAFE
        elif license_type == LicenseType.CREATIVE_COMMONS_BY_NC:
            status = RightsStatus.NEEDS_REVIEW  # NC has usage restrictions
        elif license_type == LicenseType.ALL_RIGHTS_RESERVED:
            status = RightsStatus.BLOCKED
        elif license_type == LicenseType.OWNED:
            status = RightsStatus.SAFE
        elif license_type == LicenseType.UNKNOWN:
            # Fall back to platform default
            platform_default = self.platform_defaults.get(source.lower(), RightsStatus.UNKNOWN)
            status = platform_default
        else:
            status = RightsStatus.NEEDS_REVIEW

        # Risk flags can upgrade status to more restrictive
        if risk_flags and status == RightsStatus.SAFE:
            status = RightsStatus.NEEDS_REVIEW

        # Local footage is always safe
        if source.lower() == "local":
            status = RightsStatus.SAFE
            license_type = LicenseType.OWNED

        # Build notes
        notes = ""
        if status == RightsStatus.SAFE:
            notes = f"License: {license_type.value}. Safe for reuse."
        elif status == RightsStatus.NEEDS_REVIEW:
            notes = f"License: {license_type.value}. Requires manual rights verification."
        elif status == RightsStatus.BLOCKED:
            notes = f"License: {license_type.value}. Do not reuse without explicit permission."
        else:
            notes = f"License: {license_type.value}. No license information available."

        return RightsAssessment(
            status=status,
            license_type=license_type,
            source_url=url,
            source_platform=source,
            license_text=license_type.value,
            risk_flags=risk_flags,
            notes=notes,
        )

    def filter_candidates(
        self,
        candidates: list[dict],
    ) -> dict[str, list[dict]]:
        """
        Filter a list of candidate videos by rights status.

        Returns a dict with keys: "safe", "needs_review", "blocked", "unknown".
        Each value is a list of candidates with added "rights_assessment" field.
        """
        result: dict[str, list[dict]] = {
            "safe": [],
            "needs_review": [],
            "blocked": [],
            "unknown": [],
        }

        for candidate in candidates:
            assessment = self.assess(
                title=candidate.get("title", ""),
                source=candidate.get("source", ""),
                description=candidate.get("description", ""),
                url=candidate.get("url", ""),
                tags=candidate.get("tags"),
                metadata=candidate.get("metadata"),
            )
            candidate["rights_assessment"] = assessment.to_dict()
            result[assessment.status.value].append(candidate)

        return result

    def can_insert(self, assessment: RightsAssessment) -> bool:
        """Hard gate: can this clip be inserted into a timeline?"""
        return assessment.status == RightsStatus.SAFE

    def needs_manual_review(self, assessment: RightsAssessment) -> bool:
        """Does this clip need manual rights review before insertion?"""
        return assessment.status in (RightsStatus.NEEDS_REVIEW, RightsStatus.UNKNOWN)
