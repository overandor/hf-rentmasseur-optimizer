"""
Deep token backend — unigrams, bigrams, trigrams, subword tokens, syllable tokens.
"""

import re
import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

from .bio_tokenizer import tokenize, _syllable_count


def extract_ngrams(tokens: List[str], n: int = 2) -> List[Tuple[str, ...]]:
    """Extract n-grams from token list."""
    return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]


def extract_subword_tokens(word: str, min_len: int = 3) -> List[str]:
    """Extract subword chunks: prefixes, suffixes, roots."""
    if len(word) <= min_len:
        return [word]
    chunks = []
    # Prefix 3, suffix 3, middle
    for i in range(0, len(word) - min_len + 1):
        chunks.append(word[i:i+min_len])
    return chunks


def extract_syllable_tokens(text: str) -> List[str]:
    """Extract syllable-count tokens per word."""
    words = tokenize(text)
    return [f"{w}:{_syllable_count(w)}" for w in words]


def extract_positional_tokens(text: str) -> List[str]:
    """Extract tokens with position: first, middle, last sentence."""
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    result = []
    for i, sent in enumerate(sentences):
        words = tokenize(sent)
        for j, w in enumerate(words):
            if i == 0 and j == 0:
                result.append(f"FIRST:{w}")
            elif i == len(sentences) - 1 and j == len(words) - 1:
                result.append(f"LAST:{w}")
            else:
                result.append(f"MID:{w}")
    return result


def extract_structural_tokens(text: str) -> List[str]:
    """Extract structure signals: paragraphs, sentence count, punctuation."""
    paragraphs = len([p for p in text.split("\n") if p.strip()])
    sentences = len(re.split(r'[.!?]+', text))
    questions = text.count("?")
    exclamations = text.count("!")
    return [
        f"PARA:{paragraphs}",
        f"SENTS:{min(sentences, 10)}",
        f"Q:{questions}",
        f"EX:{exclamations}",
    ]


def deep_tokenize(headline: str, description: str) -> Dict:
    """Full token extraction."""
    text = headline + " " + description
    tokens = tokenize(text)
    return {
        "unigrams": tokens,
        "bigrams": [" ".join(bg) for bg in extract_ngrams(tokens, 2)],
        "trigrams": [" ".join(tg) for tg in extract_ngrams(tokens, 3)],
        "subwords": [sw for w in tokens for sw in extract_subword_tokens(w)],
        "syllables": extract_syllable_tokens(text),
        "positional": extract_positional_tokens(text),
        "structural": extract_structural_tokens(text),
    }


def build_deep_vocab(bios: List[Dict], output_path: Path = None) -> Dict:
    """Build deep vocabulary across all token types."""
    counters = {
        "unigrams": Counter(),
        "bigrams": Counter(),
        "trigrams": Counter(),
        "subwords": Counter(),
        "syllables": Counter(),
        "positional": Counter(),
        "structural": Counter(),
    }
    for bio in bios:
        toks = deep_tokenize(bio["headline"], bio["description"])
        for k, v in toks.items():
            counters[k].update(v)

    vocab = {
        "total_bios": len(bios),
        "token_types": {
            k: {
                "unique": len(c),
                "total": sum(c.values()),
                "top_50": dict(c.most_common(50)),
            }
            for k, c in counters.items()
        },
    }
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(vocab, indent=2))
    return vocab
