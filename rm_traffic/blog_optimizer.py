"""
Blog Optimizer — GA-style optimization for blog topics, titles, and content.

Scores each blog candidate for:
- local SEO (Manhattan area terms)
- marketing angle (problem → solution → CTA)
- readability (sentence length, structure)
- uniqueness (avoid repetition)
- engagement (funny/quirky hook)

Then selects the best candidate.
"""

import re
import random
from typing import Dict, List

from .content_policy import check_blog_risk

LOCAL_AREAS = [
    "Manhattan", "Chelsea", "Midtown", "Hell's Kitchen", "Upper West Side",
    "Upper East Side", "Tribeca", "SoHo", "West Village", "East Village",
    "Financial District", "Flatiron", "Gramercy", "Murray Hill", "NoMad",
]

KEYWORDS = [
    "deep tissue", "sports recovery", "massage", "bodywork", "shoulder tension",
    "neck pain", "back pain", "hip relief", "stress relief", "desk worker",
    "travel stiffness", "recovery massage", "professional massage", "Manhattan massage",
]


def _local_seo_score(title: str, body: str) -> float:
    text = (title + " " + body).lower()
    matches = sum(1 for a in LOCAL_AREAS if a.lower() in text)
    keyword_matches = sum(1 for k in KEYWORDS if k.lower() in text)
    return min(1.0, (matches * 0.15 + keyword_matches * 0.08))


def _marketing_score(title: str, body: str) -> float:
    score = 0.0
    text = (title + " " + body).lower()
    # Problem-solution structure
    if any(w in text for w in ["tension", "pain", "stress", "stiff", "tight"]):
        score += 0.3
    if any(w in text for w in ["relief", "recover", "release", "better", "help"]):
        score += 0.3
    if any(w in text for w in ["book", "message", "contact", "session", "schedule"]):
        score += 0.2
    if re.search(r"\bManhattan\b", text, re.I):
        score += 0.2
    return min(1.0, score)


def _readability_score(title: str, body: str) -> float:
    sentences = re.split(r'[.!?]+', body)
    if not sentences:
        return 0.0
    avg_len = sum(len(s.split()) for s in sentences if s.strip()) / max(1, len([s for s in sentences if s.strip()]))
    # Ideal average sentence length: 15-20 words
    if avg_len <= 10:
        return 0.6
    if avg_len <= 25:
        return 1.0
    return max(0.4, 1.0 - (avg_len - 25) / 50)


def _engagement_score(title: str, body: str) -> float:
    score = 0.0
    text = title + " " + body
    # Funny/quirky elements
    if "wolf" in text.lower() or "smile" in text.lower() or "howl" in text.lower():
        score += 0.4
    if any(w in text.lower() for w in ["secret", "truth", "myth", "why", "how to"]):
        score += 0.3
    if len(title) <= 80 and len(title) >= 20:
        score += 0.3
    return min(1.0, score)


def _risk_score(title: str, body: str) -> float:
    return check_blog_risk(title, body)


def score_blog(title: str, body: str) -> Dict:
    """Return composite score for a blog candidate."""
    local = _local_seo_score(title, body)
    marketing = _marketing_score(title, body)
    readability = _readability_score(title, body)
    engagement = _engagement_score(title, body)
    risk = _risk_score(title, body)
    composite = (local * 0.25 + marketing * 0.25 + readability * 0.2 + engagement * 0.2) * (1 - risk)
    return {
        "local_seo": round(local, 2),
        "marketing": round(marketing, 2),
        "readability": round(readability, 2),
        "engagement": round(engagement, 2),
        "risk": round(risk, 2),
        "composite": round(composite, 3),
    }


def select_best(candidates: List[Dict]) -> Dict:
    """Select the highest-scoring blog candidate."""
    if not candidates:
        return None
    scored = []
    for c in candidates:
        s = score_blog(c["title"], c["body"])
        scored.append({**c, **s})
    scored.sort(key=lambda x: x["composite"], reverse=True)
    return scored[0]


def mutate_title(title: str) -> str:
    """Generate title variations for GA testing."""
    prefixes = ["Why", "How", "The Truth About", "What", "Manhattan Guide to", "Real Talk:"]
    suffixes = ["— Manhattan", "in NYC", "for Manhattan Clients", "(No Fluff)"]
    variations = [title]
    for p in prefixes:
        if not title.lower().startswith(p.lower()):
            variations.append(f"{p} {title}")
    for s in suffixes:
        if s not in title:
            variations.append(f"{title} {s}")
    return random.choice(variations)


def generate_optimized_blog(topic: Dict) -> Dict:
    """Generate a blog with optimized title and scoring."""
    title = mutate_title(topic["title"])
    body = topic["body"]
    scores = score_blog(title, body)
    return {
        "title": title,
        "body": body,
        "hypothesis": topic["hypothesis"],
        "scores": scores,
    }
