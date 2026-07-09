"""
YouTube Metadata Generator — Produces YouTube-ready metadata from a VideoLakeResult.

Generates:
    - youtube_metadata.json (title, description, tags, chapters, claims, citations, rights note)
    - youtube_chapters.txt (chapter markers for description)
    - youtube_thumbnail_spec.json (thumbnail specification)

This is NOT automated upload. It produces the metadata package for manual upload
until OAuth + rights gates are production-safe.

Usage:
    metadata = YouTubeMetadataGenerator().generate(videolake_result)
    print(metadata["title"])
    print(metadata["chapters"])
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class YouTubeMetadata:
    """YouTube-ready metadata for a compiled investigation."""
    schema: str = "videolake.youtube_metadata.v1"
    video_id_local: str = ""
    title: str = ""
    description: str = ""
    short_description: str = ""
    chapters: list[dict] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)
    category: str = "Education"
    category_id: str = "27"  # Education
    made_for_kids: bool = False
    language: str = "en"
    visibility_recommendation: str = "private_until_review"
    claims_summary: dict = field(default_factory=dict)
    claims_detail: list[dict] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    rights_note: str = ""
    reuse_note: str = ""
    risk_note: str = ""
    packet_refs: dict = field(default_factory=dict)
    upload_gate: dict = field(default_factory=dict)
    privacy_status: str = "private"
    recording_date: str = ""
    license_type: str = "youtube"
    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "schema": self.schema,
            "video_id_local": self.video_id_local,
            "title": self.title,
            "description": self.description,
            "short_description": self.short_description,
            "chapters": self.chapters,
            "tags": self.tags,
            "hashtags": self.hashtags,
            "category": self.category,
            "category_id": self.category_id,
            "made_for_kids": self.made_for_kids,
            "language": self.language,
            "visibility_recommendation": self.visibility_recommendation,
            "claims_summary": self.claims_summary,
            "claims_detail": self.claims_detail,
            "citations": self.citations,
            "rights_note": self.rights_note,
            "reuse_note": self.reuse_note,
            "risk_note": self.risk_note,
            "packet_refs": self.packet_refs,
            "upload_gate": self.upload_gate,
            "privacy_status": self.privacy_status,
            "recording_date": self.recording_date,
            "license": self.license_type,
            "receipt_hash": self.receipt_hash,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_chapters_text(self) -> str:
        """Format chapters for YouTube description."""
        lines = []
        for ch in self.chapters:
            lines.append(f"{ch['timestamp']} {ch['title']}")
        return "\n".join(lines)

    def to_machine_dict(self) -> dict:
        """Machine-readable subset for API consumption."""
        return {
            "schema": self.schema,
            "video_id_local": self.video_id_local,
            "title": self.title,
            "short_description": self.short_description,
            "claims_summary": self.claims_summary,
            "rights_note": self.rights_note,
            "risk_note": self.risk_note,
            "upload_gate": self.upload_gate,
            "visibility_recommendation": self.visibility_recommendation,
            "receipt_hash": self.receipt_hash,
        }


class YouTubeMetadataGenerator:
    """
    Generates YouTube metadata from a VideoLakeResult.

    The metadata includes:
        - Title: derived from the investigation question
        - Description: structured with summary, chapters, claims, citations, rights
        - Tags: from investigation topics and claim keywords
        - Chapters: from scene graph timestamps
        - Claims summary: each claim with status and confidence
        - Citations: all supporting and counter papers
        - Rights note: rights status summary
    """

    # YouTube category IDs
    CATEGORY_SCIENCE = "28"
    CATEGORY_EDUCATION = "27"

    # Max lengths per YouTube spec
    MAX_TITLE = 100
    MAX_SHORT_DESC = 200
    MAX_DESCRIPTION = 5000
    MAX_TAGS = 500
    MAX_TAGS_COUNT = 15
    MAX_HASHTAGS = 10

    def generate(self, videolake_result) -> YouTubeMetadata:
        """Generate YouTube metadata from a VideoLakeResult."""
        inv = videolake_result.investigation
        mevf = videolake_result.mevf
        vrap = videolake_result.vrap
        scenes = videolake_result.scene_graph

        metadata = YouTubeMetadata()
        metadata.receipt_hash = videolake_result.receipt_hash

        # 0. Video ID local (SHA-256 of question + timestamp)
        vid_id_data = f"{videolake_result.question}:{time.time()}"
        metadata.video_id_local = f"sha256:{hashlib.sha256(vid_id_data.encode()).hexdigest()[:16]}"

        # 1. Claims summary (counts by status)
        metadata.claims_summary = self._generate_claims_summary_counts(inv)
        metadata.claims_detail = self._generate_claims_detail(inv)

        # 2. Title (follows claim-status rules)
        metadata.title = self._generate_title(inv, mevf, metadata.claims_summary)

        # 3. Short description
        metadata.short_description = self._generate_short_description(inv, mevf, metadata.claims_summary)

        # 4. Tags and hashtags
        metadata.tags = self._generate_tags(inv, mevf)
        metadata.hashtags = self._generate_hashtags(metadata.tags)

        # 5. Chapters from scene graph (with claim/segment refs)
        metadata.chapters = self._generate_chapters(scenes, mevf)

        # 6. Citations
        metadata.citations = self._generate_citations(inv)

        # 7. Rights note
        metadata.rights_note = self._generate_rights_note(mevf, vrap)

        # 8. Reuse note
        metadata.reuse_note = self._generate_reuse_note(mevf, vrap)

        # 9. Risk note
        metadata.risk_note = self._generate_risk_note(metadata.claims_summary, mevf)

        # 10. Packet refs
        metadata.packet_refs = {
            "vrap_manifest": "manifest.json",
            "claims": "claims.jsonl",
            "evidence": "evidence.jsonld",
            "rights": "rights.json",
            "receipts": "receipts.jsonl",
            "base64_packet": "asset_packet.b64",
        }

        # 11. Upload gate (conservative by default)
        all_safe = mevf and all(s.rights_status == "safe" for s in mevf.segments)
        metadata.upload_gate = {
            "manual_review_required": True,
            "rights_review_required": not all_safe,
            "oauth_upload_allowed": False,
            "auto_publish_allowed": False,
        }

        # 12. Visibility recommendation
        if not all_safe:
            metadata.visibility_recommendation = "private_until_review"
        elif metadata.claims_summary.get("speculative", 0) > 0 or metadata.claims_summary.get("disputed", 0) > 0:
            metadata.visibility_recommendation = "private_until_review"
        else:
            metadata.visibility_recommendation = "unlisted_until_review"

        # 13. Recording date
        metadata.recording_date = time.strftime("%Y-%m-%d", time.gmtime())

        # 14. License based on rights status
        if all_safe:
            metadata.license_type = "creativeCommon"
        else:
            metadata.license_type = "youtube"

        # 15. Description (assembled from all parts)
        metadata.description = self._generate_description(
            inv, mevf, vrap, metadata
        )

        return metadata

    def _generate_title(self, inv, mevf, claims_summary: dict) -> str:
        """Generate a YouTube-optimized title following claim-status rules.

        Rules:
            verified claim → direct title allowed
            speculative claim → question/framing title only
            pseudoscientific/disputed claim → debunking/investigation title only
        """
        if not inv:
            return "VideoLake Investigation"

        question = inv.question
        verified = claims_summary.get("verified", 0)
        speculative = claims_summary.get("speculative", 0)
        disputed = claims_summary.get("disputed", 0)
        unverified = claims_summary.get("unverified", 0)

        # Determine title framing based on claim status distribution
        if verified > 0 and speculative == 0 and disputed == 0:
            # All verified — direct title allowed
            if question.startswith(("Does ", "Can ", "Is ", "Are ", "Do ", "What ", "How ")):
                title = question
            else:
                title = f"Evidence: {question}"
        elif disputed > 0:
            # Disputed claims — debunking/investigation title only
            if question.startswith(("Does ", "Can ", "Is ", "Are ", "Do ", "What ", "How ")):
                title = f"Investigating: {question}"
            else:
                title = f"Investigation: {question}"
        elif speculative > 0:
            # Speculative claims — question/framing title only
            if not question.endswith("?"):
                title = f"Can {question}?"
            else:
                title = question
        else:
            # Default: investigation framing
            if question.startswith(("Does ", "Can ", "Is ", "Are ", "Do ", "What ", "How ")):
                title = question
            else:
                title = f"Investigation: {question}"

        # Add trust grade if available
        if mevf and mevf.trust_grade:
            title += f" [Grade {mevf.trust_grade}]"

        # Truncate to YouTube limit
        if len(title) > self.MAX_TITLE:
            title = title[:self.MAX_TITLE - 3] + "..."

        return title

    def _generate_claims_summary_counts(self, inv) -> dict:
        """Generate claims summary as a count dict by status."""
        if not inv:
            return {"verified": 0, "speculative": 0, "disputed": 0, "unsupported": 0}

        counts: dict[str, int] = {
            "verified": 0,
            "speculative": 0,
            "disputed": 0,
            "unsupported": 0,
        }
        for claim in inv.claims:
            status = claim.status.value
            if status in ("verified", "replicated"):
                counts["verified"] += 1
            elif status == "speculative":
                counts["speculative"] += 1
            elif status in ("disputed", "partially_replicated"):
                counts["disputed"] += 1
            elif status in ("unverified", "retracted"):
                counts["unsupported"] += 1
        return counts

    def _generate_claims_detail(self, inv) -> list[dict]:
        """Generate per-claim detail for machine consumption."""
        if not inv:
            return []

        detail = []
        for i, claim in enumerate(inv.claims):
            detail.append({
                "claim_id": f"claim_{i+1}",
                "text": claim.claim_text[:100],
                "status": claim.status.value,
                "confidence": round(claim.confidence, 3),
                "supporting_papers": len(claim.supporting_papers),
                "counter_papers": len(claim.counter_papers),
                "replications": claim.replications,
                "failed_replications": claim.failed_replications,
            })
        return detail

    def _generate_short_description(self, inv, mevf, claims_summary: dict) -> str:
        """Generate a short description for YouTube (max 200 chars)."""
        if not inv:
            return "An evidence-tracked investigation compiled by VideoLake."

        verified = claims_summary.get("verified", 0)
        speculative = claims_summary.get("speculative", 0)
        disputed = claims_summary.get("disputed", 0)
        total = verified + speculative + disputed + claims_summary.get("unsupported", 0)

        if disputed > 0:
            desc = f"An evidence-tracked investigation into {inv.question.lower()[:80]}, examining what sources actually support."
        elif speculative > 0:
            desc = f"An evidence-tracked investigation into {inv.question.lower()[:80]}, examining what available sources support."
        else:
            desc = f"An evidence-tracked investigation into {inv.question.lower()[:80]}."

        if len(desc) > self.MAX_SHORT_DESC:
            desc = desc[:self.MAX_SHORT_DESC - 3] + "..."
        return desc

    def _generate_hashtags(self, tags: list[str]) -> list[str]:
        """Generate hashtags from tags."""
        hashtags = []
        for tag in tags:
            clean = tag.replace(" ", "").replace("-", "")
            if clean and len(hashtags) < self.MAX_HASHTAGS:
                hashtags.append(f"#{clean}")
        return hashtags

    def _generate_reuse_note(self, mevf, vrap) -> str:
        """Generate a reuse note for the description."""
        if not mevf or not mevf.segments:
            return "No visual segments available for reuse."

        buyable = sum(1 for s in mevf.segments if s.is_for_sale)
        total = len(mevf.segments)
        reusable = sum(1 for s in mevf.segments if s.license_terms and "reuse" in s.license_terms.lower())

        note = f"{reusable}/{total} segments allow machine reuse. "
        if buyable > 0:
            note += f"{buyable} segments available for purchase. "
        note += "See market_terms.json for pricing and license details."
        return note

    def _generate_risk_note(self, claims_summary: dict, mevf) -> str:
        """Generate a risk note based on claim statuses."""
        speculative = claims_summary.get("speculative", 0)
        disputed = claims_summary.get("disputed", 0)
        unverified = claims_summary.get("unsupported", 0)

        risks = []
        if speculative > 0:
            risks.append(f"{speculative} speculative claim(s) are labeled as speculative and should not be presented as verified science")
        if disputed > 0:
            risks.append(f"{disputed} disputed claim(s) have significant counter-evidence")
        if unverified > 0:
            risks.append(f"{unverified} claim(s) lack sufficient evidence")

        if not risks:
            return "No significant risk factors identified. All claims have supporting evidence."
        return ". ".join(risks) + "."

    def _generate_tags(self, inv, mevf) -> list[str]:
        """Generate YouTube tags from investigation."""
        tags = []

        if inv:
            # Extract keywords from question
            question_words = inv.question.lower().split()
            meaningful_words = [
                w for w in question_words
                if len(w) > 3 and w not in ("does", "have", "been", "with", "that", "this", "from", "they", "were", "their")
            ]
            tags.extend(meaningful_words[:5])

            # Add claim keywords
            for claim in inv.claims[:3]:
                words = claim.claim_text.lower().split()
                for w in words:
                    if len(w) > 4 and w not in tags:
                        tags.append(w)
                        if len(tags) >= self.MAX_TAGS_COUNT:
                            break
                if len(tags) >= self.MAX_TAGS_COUNT:
                    break

        # Standard tags
        tags.extend(["research", "evidence", "investigation", "science"])
        tags.extend(["videolake", "algorithmic legibility"])

        # Deduplicate and limit
        seen = set()
        unique_tags = []
        for tag in tags:
            tag_lower = tag.lower()
            if tag_lower not in seen:
                seen.add(tag_lower)
                unique_tags.append(tag)
        return unique_tags[:self.MAX_TAGS_COUNT]

    def _generate_chapters(self, scenes, mevf) -> list[dict]:
        """Generate YouTube chapters from scene graph with claim/segment refs."""
        chapters = []
        for scene in scenes:
            ts = scene.timestamp
            hours = int(ts // 3600)
            minutes = int((ts % 3600) // 60)
            seconds = int(ts % 60)
            timestamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

            # Chapter title from scene description
            title = scene.description[:60]
            if scene.mood:
                title += f" ({scene.mood})"

            # Find matching claim and segment IDs
            claim_ids = []
            visual_segment_ids = []
            if scene.claim_ref:
                claim_ids.append(scene.claim_ref)
                visual_segment_ids.append(scene.claim_ref)
            elif mevf:
                # Match by timestamp proximity
                for seg in mevf.segments:
                    if abs(seg.timestamp_in_video + 5.0 - ts) < 0.1:
                        claim_ids.append(seg.segment_id)
                        visual_segment_ids.append(seg.segment_id)
                        break

            chapters.append({
                "start_sec": ts,
                "timestamp": timestamp,
                "title": title,
                "claim_ids": claim_ids,
                "visual_segment_ids": visual_segment_ids,
                "scene_id": scene.scene_id,
                "scene_type": scene.scene_type,
            })
        return chapters

    def _generate_citations(self, inv) -> list[dict]:
        """Generate citations from all papers."""
        if not inv:
            return []

        citations = []
        for paper in inv.papers:
            citation = {
                "title": paper.title,
                "authors": paper.authors,
                "year": paper.year,
                "source": paper.source,
                "citations": paper.citation_count,
                "peer_reviewed": paper.is_peer_reviewed,
                "doi": paper.doi,
            }
            citations.append(citation)
        return citations

    def _generate_rights_note(self, mevf, vrap) -> str:
        """Generate rights status note for description."""
        if not mevf:
            return ""

        safe_count = sum(1 for s in mevf.segments if s.rights_status == "safe")
        total = len(mevf.segments)
        unsafe = total - safe_count

        note = f"Rights Status: {safe_count}/{total} segments have clear rights for visual use."
        if unsafe > 0:
            note += f" {unsafe} segment(s) have rights restrictions — visual evidence is described but not shown."
        note += " All claims include provenance and truth-status labels."

        if vrap:
            note += f" Trust Grade: {vrap.trust_grade}. Machine Buyability: {vrap.avg_machine_buyability:.3f}."

        return note

    def _generate_description(self, inv, mevf, vrap, metadata: YouTubeMetadata) -> str:
        """Generate the full YouTube description."""
        lines = []

        # Header
        if inv:
            lines.append(f"Question: {inv.question}")
            lines.append("")

        # Summary
        if inv:
            verified = len(inv.get_verified_claims())
            disputed = len(inv.get_disputed_claims())
            total = len(inv.claims)
            lines.append(f"SUMMARY: {total} claims investigated | {verified} verified | {disputed} disputed | {len(inv.papers)} papers reviewed")
            lines.append("")

        # Chapters
        if metadata.chapters:
            lines.append("CHAPTERS:")
            for ch in metadata.chapters:
                lines.append(f"  {ch['timestamp']} {ch['title']}")
            lines.append("")

        # Claims detail
        if metadata.claims_detail:
            lines.append("CLAIMS:")
            for c in metadata.claims_detail:
                status_icon = {
                    "verified": "[VERIFIED]",
                    "disputed": "[DISPUTED]",
                    "speculative": "[SPECULATIVE]",
                    "unverified": "[UNVERIFIED]",
                    "retracted": "[RETRACTED]",
                    "replicated": "[REPLICATED]",
                }.get(c["status"], f"[{c['status'].upper()}]")
                lines.append(f"  {status_icon} {c['text']} (confidence: {c['confidence']})")
            lines.append("")

        # Risk note
        if metadata.risk_note:
            lines.append("RISK ASSESSMENT:")
            lines.append(f"  {metadata.risk_note}")
            lines.append("")

        # Reuse note
        if metadata.reuse_note:
            lines.append("REUSE & LICENSING:")
            lines.append(f"  {metadata.reuse_note}")
            lines.append("")

        # Citations
        if metadata.citations:
            lines.append("CITATIONS:")
            for i, cite in enumerate(metadata.citations[:10]):
                peer = "[peer-reviewed]" if cite["peer_reviewed"] else "[non-peer-reviewed]"
                lines.append(f"  [{i+1}] {cite['title']} ({cite['year']}) {peer} — {cite['source']}")
            if len(metadata.citations) > 10:
                lines.append(f"  ... and {len(metadata.citations) - 10} more")
            lines.append("")

        # Rights note
        if metadata.rights_note:
            lines.append("RIGHTS & PROVENANCE:")
            lines.append(f"  {metadata.rights_note}")
            lines.append("")

        # Machine-readable section
        lines.append("MACHINE-READABLE METADATA:")
        lines.append(f"  Receipt: {metadata.receipt_hash}")
        if vrap:
            lines.append(f"  VRAP ID: {vrap.vrap_id}")
            lines.append(f"  Asset Type: {vrap.asset_type}")
            lines.append(f"  Total Price: ${vrap.total_price_usd:.2f}")
        lines.append("  Full asset packet available as Base64 in companion files.")
        lines.append("")

        # Footer
        lines.append("---")
        lines.append("Generated by VideoLake Compiler — Research-to-Asset Compiler")
        lines.append("The video is the human surface. The evidence graph is the asset.")

        description = "\n".join(lines)

        # Truncate to YouTube limit
        if len(description) > self.MAX_DESCRIPTION:
            description = description[:self.MAX_DESCRIPTION - 3] + "..."

        return description

    def generate_thumbnail_spec(self, videolake_result) -> dict:
        """Generate a thumbnail specification (not the actual image)."""
        inv = videolake_result.investigation
        mevf = videolake_result.mevf
        scenes = videolake_result.scene_graph

        # Pick the most dramatic scene for thumbnail
        dramatic_scene = None
        for scene in scenes:
            if scene.mood in ("revelatory", "tense", "conclusive"):
                dramatic_scene = scene
                break
        if not dramatic_scene and scenes:
            dramatic_scene = scenes[0]

        return {
            "spec_version": "1.0",
            "resolution": "1280x720",
            "format": "jpg",
            "background_color": "#0a0a2a",
            "title_text": inv.question[:60] if inv else "",
            "subtitle_text": f"Grade {mevf.trust_grade}" if mevf else "",
            "scene_ref": dramatic_scene.scene_id if dramatic_scene else "",
            "visual_elements": dramatic_scene.visual_elements if dramatic_scene else [],
            "mood": dramatic_scene.mood if dramatic_scene else "investigative",
            "text_overlay": True,
            "status_badge": True,
        }
