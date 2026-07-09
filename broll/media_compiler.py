"""
Media Compiler — Compiles an InvestigationGraph into multiple output formats.

The Investigation Graph is the primary asset. From it, the Media Compiler
produces:
    - Video timeline (via OverVisualCompiler)
    - Blog post
    - Research paper / report
    - Slides
    - Podcast script
    - Dataset
    - Course outline
    - FAQ
    - Landing page
    - Knowledge base

Video is just one renderer among many. The investigation and evidence
graph are the source of truth, and every media format is compiled
from that source of truth.

Architecture:
    Investigation → Media Compiler → {Video, Blog, Paper, Slides, Podcast, ...}

The key insight: one investigation → many outputs, all from the same
evidence-backed source of truth.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional

from .investigation_graph import InvestigationGraph
from .scientific_claim import ScientificClaim, ScientificStatus


@dataclass
class MediaOutput:
    """A compiled media output from an investigation."""
    output_type: str  # video, blog, paper, slides, podcast, etc.
    title: str
    content: str = ""
    metadata: dict = field(default_factory=dict)
    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "output_type": self.output_type,
            "title": self.title,
            "content": self.content,
            "metadata": self.metadata,
            "receipt_hash": self.receipt_hash,
        }


class MediaCompiler:
    """
    Compiles an InvestigationGraph into multiple output formats.

    Usage:
        compiler = MediaCompiler()
        outputs = compiler.compile_all(investigation)
        for output in outputs:
            print(f"{output.output_type}: {output.title}")
    """

    def __init__(self):
        self.compilers = {
            "video_timeline": self.compile_video_timeline,
            "blog": self.compile_blog,
            "research_report": self.compile_research_report,
            "slides": self.compile_slides,
            "podcast_script": self.compile_podcast_script,
            "faq": self.compile_faq,
            "course_outline": self.compile_course_outline,
            "knowledge_base": self.compile_knowledge_base,
        }

    def compile_all(self, investigation: InvestigationGraph) -> list[MediaOutput]:
        """Compile all available output formats from an investigation."""
        outputs: list[MediaOutput] = []
        for output_type, compiler_fn in self.compilers.items():
            output = compiler_fn(investigation)
            if output:
                outputs.append(output)
        return outputs

    def compile_video_timeline(self, inv: InvestigationGraph) -> MediaOutput:
        """
        Compile a video timeline from the investigation.

        The video follows the investigation narrative:
            Question → Search → Discovery → Confusion → Contradiction
            → Verification → Experiment → Conclusion
        """
        sections: list[str] = []
        sections.append(f"# Video Timeline: {inv.question}")
        sections.append(f"\nDuration: ~5 minutes")
        sections.append(f"\n## Act 1: The Question (0:00-0:30)")
        sections.append(f"Narrator introduces: {inv.question}")

        sections.append(f"\n## Act 2: The Search (0:30-1:30)")
        for search in inv.searches:
            sections.append(f"  [{search.source}] {search.query} → {search.results_count} results")

        sections.append(f"\n## Act 3: Discovery (1:30-2:30)")
        for paper in inv.papers[:5]:
            sections.append(f"  {paper.title} ({paper.year}, {paper.citation_count} citations)")

        sections.append(f"\n## Act 4: Contradiction (2:30-3:15)")
        disputed = inv.get_disputed_claims()
        if disputed:
            for claim in disputed:
                sections.append(f"  DISPUTED: {claim.claim_text}")
                sections.append(f"    Counter: {len(claim.counter_papers)} papers")
        else:
            sections.append("  No significant contradictions found.")

        sections.append(f"\n## Act 5: Verification (3:15-4:00)")
        verified = inv.get_verified_claims()
        if verified:
            for claim in verified:
                sections.append(f"  VERIFIED: {claim.claim_text} (confidence: {claim.confidence:.2f})")
        else:
            sections.append("  No claims fully verified.")

        sections.append(f"\n## Act 6: Conclusion (4:00-5:00)")
        for c in inv.conclusions:
            sections.append(f"  {c}")

        content = "\n".join(sections)
        return MediaOutput(
            output_type="video_timeline",
            title=f"Investigation: {inv.question[:60]}",
            content=content,
            metadata={"duration_estimate": "5 minutes", "acts": 6},
            receipt_hash=inv.receipt_hash,
        )

    def compile_blog(self, inv: InvestigationGraph) -> MediaOutput:
        """Compile a blog post from the investigation."""
        sections: list[str] = []
        sections.append(f"# {inv.question}")
        sections.append(f"\n*An investigation compiled from {len(inv.papers)} papers across {len(inv.searches)} sources.*\n")

        sections.append("## What We Wanted to Know\n")
        sections.append(inv.question)

        sections.append("\n## What We Found\n")
        for claim in inv.claims:
            overlay = claim.to_overlay()
            sections.append(f"**{overlay['status'].upper()}**: {claim.claim_text}")
            sections.append(f"- Supporting evidence: {overlay['supporting_evidence']}")
            sections.append(f"- Counter evidence: {overlay['counter_evidence']}")
            sections.append(f"- Replication: {overlay['replication']}")
            sections.append(f"- Confidence: {overlay['confidence']}\n")

        sections.append("## Conclusions\n")
        for c in inv.conclusions:
            sections.append(f"- {c}")

        sections.append(f"\n---\n*Investigation ID: {inv.investigation_id}*")
        sections.append(f"*Receipt: {inv.receipt_hash}*")

        return MediaOutput(
            output_type="blog",
            title=inv.question,
            content="\n".join(sections),
            metadata={"word_count": len("\n".join(sections).split())},
        )

    def compile_research_report(self, inv: InvestigationGraph) -> MediaOutput:
        """Compile a formal research report."""
        sections: list[str] = []
        sections.append(f"# Research Report\n")
        sections.append(f"## Research Question\n{inv.question}\n")
        sections.append(f"## Methodology\n")
        sections.append(f"Searched {len(inv.searches)} sources: {', '.join(s.source for s in inv.searches)}")
        sections.append(f"Found {len(inv.papers)} papers.\n")

        sections.append("## Results\n")
        sections.append(f"### Claim Analysis\n")
        for claim in inv.claims:
            sections.append(f"#### {claim.claim_text}")
            sections.append(f"- Status: {claim.status.value}")
            sections.append(f"- Confidence: {claim.confidence:.3f}")
            sections.append(f"- Supporting papers: {len(claim.supporting_papers)}")
            sections.append(f"- Counter papers: {len(claim.counter_papers)}")
            sections.append(f"- Replications: {claim.replications} (failed: {claim.failed_replications})")
            sections.append(f"- Total citations: {claim.citation_count}\n")

        sections.append("## Conclusions\n")
        for c in inv.conclusions:
            sections.append(f"{c}")

        sections.append(f"\n## Provenance\n")
        sections.append(f"Investigation ID: {inv.investigation_id}")
        sections.append(f"Receipt hash: {inv.receipt_hash}")
        sections.append(f"Timestamp: {inv.timestamp}")

        return MediaOutput(
            output_type="research_report",
            title=f"Research Report: {inv.question[:60]}",
            content="\n".join(sections),
            metadata={
                "paper_count": len(inv.papers),
                "claim_count": len(inv.claims),
                "avg_confidence": inv.stats["avg_confidence"],
            },
        )

    def compile_slides(self, inv: InvestigationGraph) -> MediaOutput:
        """Compile a slide deck outline."""
        slides: list[str] = []
        slides.append("# Slide Deck\n")
        slides.append(f"## Slide 1: Title\n{inv.question}\n")
        slides.append(f"## Slide 2: Research Question\n{inv.question}\n")
        slides.append(f"## Slide 3: Methodology\nSearched {len(inv.searches)} sources\n")

        for i, claim in enumerate(inv.claims[:5], 4):
            slides.append(f"## Slide {i}: Finding {i-3}")
            slides.append(f"**{claim.status.value.upper()}**\n{claim.claim_text}")
            slides.append(f"Confidence: {claim.confidence:.2f}\n")

        slides.append(f"## Slide {len(inv.claims)+4}: Conclusions")
        for c in inv.conclusions:
            slides.append(f"- {c}")

        return MediaOutput(
            output_type="slides",
            title=f"Slides: {inv.question[:60]}",
            content="\n".join(slides),
            metadata={"slide_count": len(inv.claims) + 5},
        )

    def compile_podcast_script(self, inv: InvestigationGraph) -> MediaOutput:
        """Compile a podcast script."""
        script: list[str] = []
        script.append("# Podcast Script\n")
        script.append(f"[INTRO MUSIC]\n")
        script.append(f"Host: Today we're investigating: {inv.question}\n")
        script.append(f"Host: Let's start by searching the literature.\n")

        script.append(f"[SFX: typing]\n")
        for search in inv.searches[:3]:
            script.append(f"Host: Searching {search.source}... found {search.results_count} results.\n")

        script.append(f"\nHost: Here's what the research says.\n")
        for claim in inv.claims[:3]:
            script.append(f"Host: One claim is that {claim.claim_text.lower()}")
            script.append(f"Host: The status? {claim.status.value}. Confidence: {claim.confidence:.0%}.\n")

        script.append(f"\nHost: So what do we conclude?\n")
        for c in inv.conclusions:
            script.append(f"Host: {c}\n")

        script.append(f"\n[OUTRO MUSIC]\n")

        return MediaOutput(
            output_type="podcast_script",
            title=f"Podcast: {inv.question[:60]}",
            content="\n".join(script),
            metadata={"estimated_duration": "10-15 minutes"},
        )

    def compile_faq(self, inv: InvestigationGraph) -> MediaOutput:
        """Compile an FAQ from the investigation."""
        faqs: list[str] = []
        faqs.append("# FAQ\n")
        faqs.append(f"## Q: {inv.question}\n")
        faqs.append(f"A: {inv.conclusions[0] if inv.conclusions else 'Investigation ongoing.'}\n")

        for claim in inv.claims:
            faqs.append(f"## Q: Is it true that {claim.claim_text.lower()}?\n")
            faqs.append(f"A: Status: **{claim.status.value}**. Confidence: {claim.confidence:.0%}. ")
            if claim.counter_papers:
                faqs.append(f"Some researchers disagree ({len(claim.counter_papers)} counter-papers).")
            faqs.append("\n")

        return MediaOutput(
            output_type="faq",
            title=f"FAQ: {inv.question[:60]}",
            content="\n".join(faqs),
            metadata={"question_count": len(inv.claims) + 1},
        )

    def compile_course_outline(self, inv: InvestigationGraph) -> MediaOutput:
        """Compile a course outline from the investigation."""
        outline: list[str] = []
        outline.append("# Course Outline\n")
        outline.append(f"## Course: {inv.question[:80]}\n")
        outline.append("## Module 1: Introduction\n")
        outline.append(f"- Research question: {inv.question}\n")
        outline.append("## Module 2: Background\n")
        outline.append(f"- {len(inv.papers)} papers reviewed\n")
        outline.append("## Module 3: Key Claims\n")

        for i, claim in enumerate(inv.claims, 1):
            outline.append(f"### Claim {i}: {claim.claim_text}")
            outline.append(f"  - Status: {claim.status.value}")
            outline.append(f"  - Confidence: {claim.confidence:.2f}\n")

        outline.append("## Module 4: Evidence Analysis\n")
        outline.append("## Module 5: Conclusions\n")
        for c in inv.conclusions:
            outline.append(f"- {c}")

        return MediaOutput(
            output_type="course_outline",
            title=f"Course: {inv.question[:60]}",
            content="\n".join(outline),
            metadata={"module_count": 5},
        )

    def compile_knowledge_base(self, inv: InvestigationGraph) -> MediaOutput:
        """Compile a knowledge base entry."""
        kb: list[str] = []
        kb.append("# Knowledge Base Entry\n")
        kb.append(f"## Topic: {inv.question}\n")
        kb.append(f"## Investigation ID: {inv.investigation_id}\n")
        kb.append(f"## Verified Claims\n")
        for claim in inv.get_verified_claims():
            kb.append(f"- [{claim.status.value}] {claim.claim_text} (conf: {claim.confidence:.2f})")
        kb.append(f"\n## Disputed Claims\n")
        for claim in inv.get_disputed_claims():
            kb.append(f"- [{claim.status.value}] {claim.claim_text} (conf: {claim.confidence:.2f})")
        kb.append(f"\n## Key Papers\n")
        for paper in inv.papers[:10]:
            kb.append(f"- {paper.title} ({paper.year}, {paper.citation_count} citations)")
        kb.append(f"\n## Conclusions\n")
        for c in inv.conclusions:
            kb.append(f"- {c}")

        return MediaOutput(
            output_type="knowledge_base",
            title=f"KB: {inv.question[:60]}",
            content="\n".join(kb),
            metadata={
                "verified_claims": len(inv.get_verified_claims()),
                "disputed_claims": len(inv.get_disputed_claims()),
                "total_papers": len(inv.papers),
            },
        )

    def compile(self, inv: InvestigationGraph, output_type: str) -> MediaOutput | None:
        """Compile a specific output type."""
        compiler_fn = self.compilers.get(output_type)
        if compiler_fn:
            return compiler_fn(inv)
        return None

    @property
    def available_outputs(self) -> list[str]:
        """List of available output types."""
        return list(self.compilers.keys())
