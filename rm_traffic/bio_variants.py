"""
Bio variant library — conservative, tested headline + bio copy.

These are not random mutations. Each variant has a hypothesis and is tracked.
"""

BIO_VARIANTS = {
    "direct_recovery": {
        "headline": "Deep Recovery Massage — Manhattan",
        "description": (
            "I work with men who train hard, sit long hours, or carry stress in their shoulders and lower back. "
            "My sessions are pressure-forward, slow, and deliberate — built around what your body actually needs "
            "that day. Incall in Manhattan. Outcall available. Same-day when my schedule allows."
        ),
        "hypothesis": "Recovery-focused copy increases contact clicks from serious clients.",
    },
    "professional_discretion": {
        "headline": "Discreet Therapeutic Massage — Manhattan",
        "description": (
            "Private, professional massage in a clean Manhattan space. I focus on therapeutic work first — "
            "neck, shoulders, back, and hips — with a calm, confident presence. No rushed sessions. "
            "Respectful clients only. Available for incall and selective outcall."
        ),
        "hypothesis": "Professional/discretion framing increases trust and booking quality.",
    },
    "luxury_manhattan": {
        "headline": "Premium Bodywork — Manhattan, NYC",
        "description": (
            "Athletic, intuitive bodywork for men who want more than a standard massage. "
            "I combine deep tissue, pressure-point work, and full-body flow in a private Manhattan studio. "
            "Clean, quiet, and comfortable. Incall preferred. Outcall considered for established clients."
        ),
        "hypothesis": "Premium positioning attracts higher-value bookings.",
    },
    "sports_deep_tissue": {
        "headline": "Sports & Deep Tissue — Manhattan",
        "description": (
            "Built for lifters, runners, and guys who beat up their bodies. My sessions target the muscle groups "
            "that actually hurt: hips, hamstrings, shoulders, lats. Strong pressure. No fluff. "
            "Manhattan incall. Book when available."
        ),
        "hypothesis": "Sports positioning captures fitness-focused traffic.",
    },
    "last_minute": {
        "headline": "Same-Day Massage — Manhattan",
        "description": (
            "When you need real bodywork today, not next week. I keep blocks open for same-day bookings in Manhattan "
            "when I am available. Clean private space, strong hands, no attitude. Text or email. "
            "Respectful clients only."
        ),
        "hypothesis": "Last-minute availability angle converts urgent search traffic.",
    },
}


def get_variant(variant_id: str) -> dict:
    v = BIO_VARIANTS.get(variant_id)
    if not v:
        return None
    return {
        "variant_id": variant_id,
        "headline": v["headline"],
        "description": v["description"],
        "hypothesis": v["hypothesis"],
    }


def list_variant_ids() -> list:
    return list(BIO_VARIANTS.keys())


def all_variants() -> list:
    return [get_variant(vid) for vid in list_variant_ids()]
