"""
Blog Draft Engine — high-quality blog drafts, never auto-published.

Confirmed: GET /api/v1/blogs?page=1
Not confirmed: create/edit endpoints (use CDP discovery first)

Policy: 1-2 posts per week, useful content, no fake claims.
"""

import logging
import time
from pathlib import Path
from typing import Dict, List

from .db import write_receipt, upsert_content_variant
from .content_policy import check_blog_risk
from .api_client import RentMasseurAPI
from .blog_optimizer import select_best, generate_optimized_blog

log = logging.getLogger("profileops.blog")

BLOG_TOPICS = [
    {
        "title": "Why Manhattan Clients Book Deep Tissue After Long Desk Days",
        "body": """Desk work in Manhattan builds tension in shoulders, neck, and lower back. Deep tissue massage targets those overworked areas with sustained pressure and slow, deliberate work. It is not about relaxation — it is about restoring movement and reducing the tightness that accumulates from hours in front of a screen. The best sessions start with clear communication: where you feel it, how long it has been there, and what kind of pressure you respond to.""",
        "hypothesis": "Professional, local content attracts long-tail search traffic.",
    },
    {
        "title": "Sports Recovery Massage in Manhattan: What to Expect",
        "body": """After heavy training, the body needs more than rest. It needs targeted work on the muscle groups that took the load. A sports recovery session focuses on hips, hamstrings, glutes, shoulders, and back — the areas that tighten from lifting, running, and repetitive motion. The pressure is firm, the pace is intentional, and the goal is simple: help you move better tomorrow than you did today.""",
        "hypothesis": "Sports/recovery angle captures fitness-focused readers.",
    },
    {
        "title": "Neck and Shoulder Tension: How It Builds and How to Release It",
        "body": """Most neck and shoulder tension does not come from one bad night of sleep. It comes from weeks of forward head posture, shallow breathing, and stress held in the upper back. Targeted massage works through the levator scapulae, upper traps, and rhomboids to restore range of motion and reduce the dull ache that follows you through the day.""",
        "hypothesis": "Pain-specific content increases relevance and trust.",
    },
    {
        "title": "What to Expect From Your First Professional Massage Session",
        "body": """A professional session starts with clear boundaries and a clear plan. We discuss focus areas, pressure preferences, and any injuries or sensitivities. The room is clean, the temperature is comfortable, and the work is focused on your goals. You can communicate at any time if the pressure is too much or too little. The point is not to endure — it is to get real relief.""",
        "hypothesis": "Trust-building content reduces friction for first-time clients.",
    },
    {
        "title": "Incall vs Outcall Massage in Manhattan: How to Choose",
        "body": """Incall means you come to a private, prepared space. Outcall means the session comes to you. Incall is usually better for controlled environment, equipment, and focus. Outcall works for clients who prefer their own space. In Manhattan, both have a place — the right choice depends on your schedule, privacy preference, and how much you want to travel after the session.""",
        "hypothesis": "Comparison content captures high-intent searches.",
    },
    {
        "title": "Travel Stiffness Relief for Frequent Flyers",
        "body": """Long flights compress the spine, tighten hips, and leave the neck locked in one position. Travel stiffness is real, and it does not go away with a hot shower. A focused session on the lower back, hip flexors, and neck can reset the body after a trip and make the next flight easier.""",
        "hypothesis": "Travel-specific content reaches transient Manhattan visitors.",
    },
    {
        "title": "The Truth About Deep Tissue Massage in Manhattan",
        "body": """Deep tissue massage is not a magic cure. It is focused, sustained pressure on muscle groups that have tightened from training, posture, or stress. The real results come from consistency, clear communication, and a therapist who knows how deep is too deep. In Manhattan, the difference is usually the therapist, not the room.""",
        "hypothesis": "Truth-based content builds authority and trust.",
    },
    {
        "title": "Why Your Shoulders Feel Like Concrete by Wednesday",
        "body": """By midweek, most Manhattan desk workers have shoulders up to their ears. The cause is not one bad email. It is hours of forward head posture, shallow breathing, and a laptop that is too low. The fix is targeted work on the upper back, neck, and shoulders — plus the occasional reminder to breathe.""",
        "hypothesis": "Relatable midweek content increases engagement.",
    },
    {
        "title": "Karpathian Wolf's Guide to Not Walking Like a Robot",
        "body": """If you sit in meetings all day and then hit the gym, your body is confused. It is stiff from the chair and then hammered by the weights. The result is a human who moves like a robot. Deep tissue work helps reconnect the muscles that the desk disconnected. The wolf is here to help.""",
        "hypothesis": "Funny, branded content increases shareability and memorability.",
    },
    {
        "title": "Why Do My Hips Hurt After Squats? A Manhattan Guide",
        "body": """Squats do not hurt your hips. Bad recovery hurts your hips. If you train legs and then sit at a desk for ten hours, the hip flexors tighten and the glutes check out. The fix is targeted work on the front of the hips and the sides of the glutes. Your squat will thank you.""",
        "hypothesis": "Fitness-specific pain points drive high-intent searches.",
    },
    {
        "title": "The Real Difference Between a Spa Massage and Recovery Work",
        "body": """A spa massage is about atmosphere. Recovery work is about results. One uses light oil and quiet music. The other uses pressure, communication, and a plan for the muscle groups that are actually limiting you. Both have value, but if you are training hard or sitting long hours, you probably need the second one.""",
        "hypothesis": "Comparison content educates clients and improves lead quality.",
    },
]


def generate_blog_drafts(count: int = 1) -> List[Dict]:
    """Generate optimized blog drafts without publishing."""
    candidates = [generate_optimized_blog(t) for t in BLOG_TOPICS]
    selected = []
    for i in range(min(count, len(candidates))):
        if not candidates:
            break
        best_idx = max(range(len(candidates)), key=lambda j: candidates[j]["scores"]["composite"])
        best = candidates.pop(best_idx)
        if best["scores"]["risk"] > 0.7:
            log.error("Blog draft rejected by policy: %s", best["title"])
            continue
        variant_id = f"blog_{int(time.time())}_{i}"
        upsert_content_variant(
            variant_id, "blog",
            headline=best["title"], description=best["body"],
            title=best["title"], body=best["body"],
            hypothesis=best["hypothesis"],
            status="draft"
        )
        write_receipt(
            "blog_draft_created_v1",
            "generate_blog_draft",
            {},
            {"variant_id": variant_id, "title": best["title"], "scores": best["scores"]},
            verified=True,
        )
        selected.append({
            "variant_id": variant_id,
            "title": best["title"],
            "body": best["body"],
            "hypothesis": best["hypothesis"],
            "scores": best["scores"],
        })
        log.info("Blog draft created: %s (score=%.3f)", best["title"], best["scores"]["composite"])
    return selected


def get_blog_drafts_dir() -> Path:
    d = Path(__file__).parent / "data" / "drafts" / "blog"
    d.mkdir(parents=True, exist_ok=True)
    return d


def save_blog_drafts_to_disk(drafts: List[Dict]):
    """Save blog drafts to markdown files for review."""
    d = get_blog_drafts_dir()
    for draft in drafts:
        path = d / f"{draft['variant_id']}.md"
        path.write_text(f"# {draft['title']}\n\n{draft['body']}\n\n**Hypothesis:** {draft['hypothesis']}\n")


def get_blog_status(api: RentMasseurAPI) -> Dict:
    """Get current blog list."""
    return api.get_blogs(page=1)
