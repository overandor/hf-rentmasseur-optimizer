"""
Bio feature extraction for ML/GA optimization.
"""

import re
from typing import Dict, List

from .bio_tokenizer import speech_features

LOCAL_AREAS = [
    "manhattan", "chelsea", "midtown", "hell's kitchen", "upper west side",
    "upper east side", "tribeca", "soho", "west village", "east village",
    "financial district", "flatiron", "gramercy", "murray hill", "nomad",
    "nyc", "new york"
]

SERVICE_WORDS = [
    "deep tissue", "sports", "recovery", "massage", "bodywork", "relief",
    "therapy", "knots", "tension", "pressure", "shoulder", "back", "hip",
    "neck", "glute", "stress", "desk", "travel", "athlete", "professional"
]

CTA_WORDS = [
    "message", "text", "email", "book", "call", "contact", "dm", "schedule",
    "reach out", "get in touch"
]

PROOF_WORDS = [
    "clients", "professional", "clean", "private", "experienced", "trained",
    "results", "years", "certified", "licensed"
]

TRUST_WORDS = [
    "professional", "clean", "private", "respect", "discreet", "boundaries",
    "communication", "confidential"
]

HUMOR_WORDS = [
    "wolf", "robot", "concrete", "phone cord", "group chat", "screaming",
    "dramatic", "hostile", "no fluff", "feather", "magic", "gps"
]


def extract_features(headline: str, description: str) -> Dict[str, float]:
    text = (headline + " " + description).lower()
    words = re.findall(r'\b[a-z]+\b', text)
    sentences = re.split(r'[.!?]+', description)
    sentences = [s.strip() for s in sentences if s.strip()]

    headline_len = len(headline)
    desc_len = len(description)
    word_count = len(words)
    avg_sentence_len = sum(len(s.split()) for s in sentences) / max(1, len(sentences))
    question_count = text.count("?")
    exclamation_count = text.count("!")
    paragraph_count = len([p for p in description.split("\n") if p.strip()])

    local_score = sum(1 for w in LOCAL_AREAS if w in text) / len(LOCAL_AREAS)
    service_score = sum(1 for w in SERVICE_WORDS if w in text) / len(SERVICE_WORDS)
    cta_score = sum(1 for w in CTA_WORDS if w in text) / len(CTA_WORDS)
    proof_score = sum(1 for w in PROOF_WORDS if w in text) / len(PROOF_WORDS)
    trust_score = sum(1 for w in TRUST_WORDS if w in text) / len(TRUST_WORDS)
    humor_score = min(1.0, sum(1 for w in HUMOR_WORDS if w in text) / 3.0)

    # Readability
    if 50 <= desc_len <= 300:
        readability = 1.0
    elif desc_len < 50:
        readability = 0.5
    else:
        readability = max(0.3, 1.0 - (desc_len - 300) / 500)

    speech = speech_features(text)
    return {
        "headline_len": headline_len / 100,
        "desc_len": desc_len / 500,
        "word_count": word_count / 100,
        "avg_sentence_len": min(avg_sentence_len / 30, 1.0),
        "paragraph_count": min(paragraph_count / 5, 1.0),
        "question_count": question_count / 2,
        "exclamation_count": exclamation_count / 2,
        "local_score": local_score,
        "service_score": service_score,
        "cta_score": cta_score,
        "proof_score": proof_score,
        "trust_score": trust_score,
        "humor_score": humor_score,
        "readability": readability,
        "speech_score": speech["speech_score"],
    }


def feature_vector(headline: str, description: str) -> List[float]:
    f = extract_features(headline, description)
    return [
        f["headline_len"],
        f["desc_len"],
        f["word_count"],
        f["avg_sentence_len"],
        f["paragraph_count"],
        f["question_count"],
        f["exclamation_count"],
        f["local_score"],
        f["service_score"],
        f["cta_score"],
        f["proof_score"],
        f["trust_score"],
        f["humor_score"],
        f["readability"],
        f["speech_score"],
    ]


FEATURE_NAMES = [
    "headline_len", "desc_len", "word_count", "avg_sentence_len", "paragraph_count",
    "question_count", "exclamation_count", "local_score", "service_score", "cta_score",
    "proof_score", "trust_score", "humor_score", "readability", "speech_score",
]
