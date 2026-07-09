"""
Content Policy — block risky marketing claims and spam patterns.

Reference: FTC Consumer Reviews and Testimonials Rule; Google spam policies.
"""

import re

# Risky patterns that should not appear in public profile copy
RISKY_PATTERNS = [
    (r"\b(cure|heal|healing|treat|treatment|medical|diagnose|therapy|therapeutic)\b", "medical_claim", 0.4),
    (r"\b(guaranteed|guarantee|100%|money back|promise)\b", "guarantee", 0.5),
    (r"\b(fake|buy reviews|fake testimonials|fake clients)\b", "fake_engagement", 1.0),
    (r"\b(best|top|number one|#1|award winning)\b", "superlative", 0.3),
    (r"\b(cheap|discount|free|sale|limited time)\b", "discount_spam", 0.3),
    (r"\b(click here|call now|book now|hurry)\b", "urgency_spam", 0.2),
    (r"\b(sex|escort|happy ending|full service|nude|naked)\b", "explicit", 1.0),
    (r"\b(bot|automated|ai-generated|auto-post|spam)\b", "spam_signal", 0.6),
]

# Cap maximum risk score
MAX_RISK = 1.0


def check_bio_risk(text: str) -> float:
    """Return risk score 0.0-1.0. Higher is riskier."""
    if not text:
        return 0.0
    text_lower = text.lower()
    risk = 0.0
    reasons = []
    for pattern, reason, weight in RISKY_PATTERNS:
        if re.search(pattern, text_lower):
            risk += weight
            reasons.append(reason)
    # Keyword stuffing penalty
    word_count = len(text.split())
    if word_count > 400:
        risk += 0.1
    # Normalize
    return min(risk, MAX_RISK)


def check_headline_risk(text: str) -> float:
    """Headlines are more visible; stricter."""
    if not text:
        return 0.5
    risk = check_bio_risk(text)
    if len(text) > 120:
        risk += 0.2
    return min(risk, MAX_RISK)


def check_blog_risk(title: str, body: str) -> float:
    """Blog posts are public content."""
    return max(check_bio_risk(title), check_bio_risk(body))


def explain_risk(text: str) -> dict:
    """Return risk score and matching reasons."""
    text_lower = text.lower()
    reasons = []
    risk = 0.0
    for pattern, reason, weight in RISKY_PATTERNS:
        if re.search(pattern, text_lower):
            risk += weight
            reasons.append(reason)
    return {"score": min(risk, MAX_RISK), "reasons": reasons}
