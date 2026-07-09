"""
Bio Appraiser — measure novelty and quality of generated bios.
"""

import json
import random
from collections import Counter
from pathlib import Path
from typing import Dict, List

from .bio_features import extract_features
from .bio_generator import _score_variant
from .bio_tokenizer import tokenize, build_vocab


def load_bios(path: Path, limit: int = None) -> List[Dict]:
    bios = []
    with open(path, "r") as f:
        for line in f:
            if not line.strip():
                continue
            bio = json.loads(line)
            bios.append(bio)
            if limit and len(bios) >= limit:
                break
    return bios


def appraise_novelty(bios: List[Dict]) -> Dict:
    """Measure how unique the bios are."""
    headlines = [b["headline"] for b in bios]
    descriptions = [b["description"] for b in bios]
    unique_headlines = len(set(headlines))
    unique_descriptions = len(set(descriptions))
    unique_pairs = len(set((h, d) for h, d in zip(headlines, descriptions)))
    return {
        "total": len(bios),
        "unique_headlines": unique_headlines,
        "unique_descriptions": unique_descriptions,
        "unique_pairs": unique_pairs,
        "headline_novelty": round(unique_headlines / len(bios), 4),
        "description_novelty": round(unique_descriptions / len(bios), 4),
        "pair_novelty": round(unique_pairs / len(bios), 4),
    }


def appraise_quality(bios: List[Dict], sample_size: int = 500) -> Dict:
    """Sample and score quality."""
    sample = random.sample(bios, min(sample_size, len(bios)))
    scores = []
    for bio in sample:
        s = _score_variant(bio["headline"], bio["description"])
        scores.append(s)
    avg_composite = sum(s["composite"] for s in scores) / len(scores)
    avg_risk = sum(max(s["headline_risk"], s["bio_risk"]) for s in scores) / len(scores)
    avg_sentiment = sum(s["sentiment"]["score"] for s in scores) / len(scores)
    return {
        "sample_size": len(sample),
        "avg_composite_score": round(avg_composite, 4),
        "avg_risk": round(avg_risk, 4),
        "avg_sentiment": round(avg_sentiment, 4),
        "top_10_percent": round(sorted([s["composite"] for s in scores], reverse=True)[int(len(scores)*0.1)], 4),
        "bottom_10_percent": round(sorted([s["composite"] for s in scores])[int(len(scores)*0.1)], 4),
    }


def appraise_vocabulary(bios: List[Dict]) -> Dict:
    """Build vocabulary and report richness."""
    vocab = build_vocab(bios, min_freq=1)
    return {
        "unique_tokens": vocab["unique_tokens"],
        "total_tokens": vocab["total_tokens"],
        "top_20": list(vocab["token_freq"].items())[:20],
    }


def full_appraisal(path: Path, sample_size: int = 500) -> Dict:
    bios = load_bios(path)
    return {
        "file": str(path),
        "novelty": appraise_novelty(bios),
        "quality": appraise_quality(bios, sample_size),
        "vocabulary": appraise_vocabulary(bios),
    }
