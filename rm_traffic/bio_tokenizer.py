"""
Bio tokenizer and vocabulary builder.

Tokenizes every word in generated bios and builds frequency statistics.
Used for speech-friendly optimization and vocabulary analysis.
"""

import re
import json
from collections import Counter
from pathlib import Path
from typing import List, Dict, Tuple


def tokenize(text: str) -> List[str]:
    """Simple word-level tokenizer. Lowercase, strip punctuation."""
    return re.findall(r'\b[a-zA-Z\']+\b', text.lower())


def build_vocab(bios: List[Dict], min_freq: int = 2) -> Dict:
    """Build vocabulary from a list of bios."""
    counter = Counter()
    for bio in bios:
        tokens = tokenize(bio["headline"] + " " + bio["description"])
        counter.update(tokens)
    return {
        "total_tokens": sum(counter.values()),
        "unique_tokens": len(counter),
        "token_freq": dict(counter.most_common()),
        "vocab": [t for t, c in counter.items() if c >= min_freq],
    }


def save_vocab(vocab: Dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(vocab, indent=2))


def load_vocab(path: Path) -> Dict:
    return json.loads(path.read_text())


def _is_simple_word(word: str) -> bool:
    """Simple words are short and phonetic."""
    return len(word) <= 6 and word.isalpha()


def _syllable_count(word: str) -> int:
    """Rough syllable count for speech rhythm."""
    word = word.lower()
    vowels = "aeiouy"
    count = 0
    prev_was_vowel = False
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not prev_was_vowel:
            count += 1
        prev_was_vowel = is_vowel
    if word.endswith("e"):
        count -= 1
    return max(1, count)


def speech_features(text: str) -> Dict:
    """Compute speech-friendliness features."""
    tokens = tokenize(text)
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not tokens:
        return {"speech_score": 0.0}

    avg_word_len = sum(len(t) for t in tokens) / len(tokens)
    avg_syllables = sum(_syllable_count(t) for t in tokens) / len(tokens)
    avg_sentence_len = len(tokens) / max(1, len(sentences))
    simple_word_ratio = sum(1 for t in tokens if _is_simple_word(t)) / len(tokens)

    # Speech score: shorter words, shorter sentences, fewer syllables = higher
    speech_score = (
        (1 - min(avg_word_len / 8, 1)) * 0.3
        + (1 - min(avg_syllables / 2.5, 1)) * 0.3
        + (1 - min(avg_sentence_len / 20, 1)) * 0.25
        + simple_word_ratio * 0.15
    )

    return {
        "avg_word_len": round(avg_word_len, 2),
        "avg_syllables": round(avg_syllables, 2),
        "avg_sentence_len": round(avg_sentence_len, 2),
        "simple_word_ratio": round(simple_word_ratio, 2),
        "speech_score": round(speech_score, 4),
    }
