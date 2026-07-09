"""
Large-scale bio generator — combinatorial + hilarious + sentiment prediction.

Generates many variants, scores them for sentiment, risk, and conversion,
stores only the best ones.

Never auto-publishes. All drafts are approval-gated.
"""

import logging
import random
import time
from typing import Dict, List

from .db import upsert_content_variant, write_receipt
from .content_policy import check_bio_risk, check_headline_risk
from .bio_variants_library import list_all as list_all_library_variants

log = logging.getLogger("profileops.bio_generator")

# Headline templates
HEADLINE_TEMPLATES = [
    "Deep Tissue & {thing} — Manhattan",
    "{adjective} Bodywork in Manhattan",
    "{name} Does {thing} — Manhattan",
    "The Wolf's {thing} — Manhattan",
    "{thing} for {person} — Manhattan",
    "Manhattan's {adjective} {thing}",
    "Not Your Average {thing} — Manhattan",
    "Real {thing} for {person}",
    "{thing}: No Fluff, Just Pressure",
    "Bring the {body_part}, Bring the Wolf — Manhattan",
    "{adjective} {thing} in Manhattan, NYC",
    "The {person}'s {thing} — Manhattan",
    "Wolf-Level {thing} — Manhattan",
    "{body_part} Rescue in Manhattan",
    "From {city} Stress to {thing}",
]

# Bio paragraph templates
BIO_TEMPLATES = [
    "{hook}\n\n{specialty}\n\n{client}\n\n{style}\n\n{cta}",
    "{hook}\n\n{style}\n\n{specialty}\n\n{proof}\n\n{cta}",
    "{specialty}\n\n{client}\n\n{hook}\n\n{style}\n\n{cta}",
    "{hook}\n\n{proof}\n\n{specialty}\n\n{cta}",
]

# Component banks
HOOKS = [
    "Your shoulders called. They want out of this meeting.",
    "I don't do feathers. I do fixes.",
    "You bring the stress, I bring the Wolf.",
    "If your body were a group chat, your hips would be the one screaming.",
    "Some people meditate. I prefer pressure.",
    "Desk life: 1. Your posture: 0. I can fix that.",
    "Your back is not a storage unit for stress.",
    "I work on humans, not mannequins.",
    "The gym builds muscle. I build recovery.",
    "Tight neck? Tight shoulders? Tight everything? Same.",
    "Wolf knows where the knots hide.",
    "You can't out-train bad recovery, but you can out-massage it.",
    "Manhattan is stressful. Your body doesn't have to be.",
    "My hands are GPS for tension.",
    "If your muscles wrote a Yelp review, it would not be five stars.",
    "I find the thing that hurts and make it stop hurting.",
    "Your body is a resume. Let's edit it.",
    "Squats gave you glutes. I give them back their range of motion.",
    "The only thing I ghost is tension.",
    "I've got strong hands and zero patience for bad posture.",
]

SPECIALTIES = [
    "I specialize in deep tissue, sports recovery, and targeted relief for shoulders, neck, back, and hips.",
    "My focus is pressure-forward work: slow, deliberate, and built around the muscle groups that actually need it.",
    "I do deep tissue, recovery bodywork, and the kind of pressure that actually changes how you move.",
    "Sports recovery, deep tissue, and hip/glute work are my main zones.",
    "I work on the tension that builds from training, travel, and ten-hour desk days.",
]

CLIENTS = [
    "Best for lifters, runners, desk workers, and anyone who treats their body like a rental.",
    "Great if you sit all day, train hard, or fly too much.",
    "If your neck feels like a phone cord from 1997, you're my people.",
    "For clients who want real pressure, clear communication, and a clean space.",
    "You don't need to be an athlete. You need to be tight.",
]

STYLES = [
    "My style is direct. I find the tension, apply pressure, and stay there until it releases.",
    "No spa music required. No fluffy rituals. Just focused work.",
    "I adjust pressure to your body, not a script.",
    "Strong hands, calm presence, zero attitude.",
    "I work with intention. Every minute has a target.",
]

PROOFS = [
    "Clients usually leave looser, taller, and less hostile toward their desk.",
    "The feedback I get most: 'I should have done this months ago.'",
    "One session won't fix ten years of bad posture, but it's a solid opening argument.",
    "I don't promise magic. I promise real pressure in the right places.",
]

CTAS = [
    "Message me with your focus areas and we'll get you sorted.",
    "Manhattan incall. Text or email to book.",
    "Clean private space in Manhattan. DM me to set something up.",
    "If your body is ready, so am I. Message for availability.",
    "Book a session and let's make your muscles less dramatic.",
]

THINGS = [
    "Sports Recovery", "Deep Tissue", "Bodywork", "Knot Removal", "Recovery",
    "Shoulder Rescue", "Hip Relief", "Back Therapy", "Desk Detox", "Stress Reset",
]

ADJECTIVES = [
    "Serious", "Pressure-Forward", "Wolf-Approved", "No-Nonsense", "Focused",
    "Real", "Direct", "Professional", "High-Octane", "Tension-Finding",
]

PERSONS = [
    "Desk Workers", "Athletes", "Gym Rats", "Frequent Flyers", "Tired Humans",
    "Shoulders", "Hips", "Runners", "Lifters", "Stressed New Yorkers",
]

BODY_PARTS = [
    "Shoulders", "Back", "Hips", "Neck", "Glutes",
]

CITIES = [
    "Manhattan", "Midtown", "Chelsea", "Hell's Kitchen", "NYC",
]

NAMES = [
    "The Wolf", "Karpathian Wolf", "Wolf", "This Guy",
]


def _generate_headline() -> str:
    template = random.choice(HEADLINE_TEMPLATES)
    return template.format(
        thing=random.choice(THINGS),
        adjective=random.choice(ADJECTIVES),
        name=random.choice(NAMES),
        person=random.choice(PERSONS),
        body_part=random.choice(BODY_PARTS),
        city=random.choice(CITIES),
    )


def _generate_description() -> str:
    template = random.choice(BIO_TEMPLATES)
    return template.format(
        hook=random.choice(HOOKS),
        specialty=random.choice(SPECIALTIES),
        client=random.choice(CLIENTS),
        style=random.choice(STYLES),
        proof=random.choice(PROOFS),
        cta=random.choice(CTAS),
    )


def _sentiment_score(text: str) -> Dict:
    """Simple sentiment prediction based on positive/negative word counts."""
    positive = [
        "better", "relief", "recover", "strong", "calm", "clean", "professional",
        "great", "real", "focus", "help", "sorted", "looser", "improve", "fix",
        "good", "best", "solid", "ready", "direct", "target",
    ]
    negative = [
        "hurt", "pain", "stress", "tight", "bad", "dramatic", "hostile", "screaming",
        "knot", "tension", "stiff", "stressed", "tired",
    ]
    text_lower = text.lower()
    pos = sum(1 for w in positive if w in text_lower)
    neg = sum(1 for w in negative if w in text_lower)
    total = pos + neg
    if total == 0:
        return {"sentiment": "neutral", "score": 0.5, "pos": 0, "neg": 0}
    ratio = pos / total
    if ratio > 0.65:
        return {"sentiment": "positive", "score": ratio, "pos": pos, "neg": neg}
    elif ratio < 0.45:
        return {"sentiment": "negative", "score": ratio, "pos": pos, "neg": neg}
    else:
        return {"sentiment": "neutral", "score": ratio, "pos": pos, "neg": neg}


def _score_variant(headline: str, description: str) -> Dict:
    headline_risk = check_headline_risk(headline)
    bio_risk = check_bio_risk(description)
    sentiment = _sentiment_score(headline + " " + description)
    word_count = len(description.split())
    # Conversion score: clarity, length, CTA presence
    cta = any(w in description.lower() for w in ["message", "text", "email", "book", "dm"])
    local = any(c.lower() in description.lower() for c in CITIES)
    clarity = 1.0 if 50 < word_count < 250 else 0.7
    composite = (
        (1 - max(headline_risk, bio_risk)) * 0.35
        + sentiment["score"] * 0.25
        + (1.0 if cta else 0.0) * 0.15
        + (1.0 if local else 0.0) * 0.15
        + clarity * 0.1
    )
    return {
        "headline_risk": headline_risk,
        "bio_risk": bio_risk,
        "sentiment": sentiment,
        "word_count": word_count,
        "has_cta": cta,
        "has_local": local,
        "composite": round(composite, 4),
    }


def generate_bios(count: int = 1000, top_n: int = 100, min_score: float = 0.5) -> List[Dict]:
    """Generate many bios and keep only the top N by composite score."""
    log.info("Generating %d bio variants...", count)
    scored = []
    for i in range(count):
        headline = _generate_headline()
        description = _generate_description()
        scores = _score_variant(headline, description)
        if scores["composite"] >= min_score:
            scored.append({
                "headline": headline,
                "description": description,
                "scores": scores,
            })
    scored.sort(key=lambda x: x["scores"]["composite"], reverse=True)
    top = scored[:top_n]
    log.info("Generated %d, kept top %d", len(scored), len(top))
    return top


def save_bios_to_db(bios: List[Dict], batch_id: str = None) -> List[str]:
    """Save generated bios to the database as drafts."""
    batch_id = batch_id or f"batch_{int(time.time())}"
    saved_ids = []
    for i, bio in enumerate(bios):
        variant_id = f"gen_{batch_id}_{i:04d}"
        upsert_content_variant(
            variant_id, "bio",
            headline=bio["headline"],
            description=bio["description"],
            hypothesis=f"Generated bio. Sentiment: {bio['scores']['sentiment']['sentiment']}. Score: {bio['scores']['composite']}",
            status="draft"
        )
        saved_ids.append(variant_id)
    write_receipt(
        "bio_generation_batch_v1",
        "generate_bios",
        {"requested_count": len(bios), "batch_id": batch_id},
        {"saved_count": len(saved_ids)},
        verified=True,
    )
    return saved_ids


def run_generation(count: int = 1000, top_n: int = 100) -> List[str]:
    """Generate and save top bios."""
    bios = generate_bios(count=count, top_n=top_n)
    return save_bios_to_db(bios)
