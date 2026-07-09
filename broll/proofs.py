"""
Proofs — Hash chain for every stage of the OverVisual pipeline.

Each stage produces a SHA-256 hash that chains to the previous stage:

    transcript_hash → claim_hash → query_hash → candidate_hash
    → selected_clip_hash → timeline_hash → receipt_hash

This creates a tamper-evident proof chain showing that:
    1. A specific transcript was processed
    2. Specific claims were extracted from it
    3. Specific search queries were generated
    4. Specific candidates were found
    5. Specific clips were selected
    6. A specific timeline was assembled
    7. A receipt was generated for the whole compilation

No step can be altered without breaking the chain.
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional


def sha256(data: str) -> str:
    """Compute SHA-256 hash of a string, return hex digest."""
    return hashlib.sha256(data.encode()).hexdigest()


@dataclass
class ProofChain:
    """
    Hash chain proving the integrity of an OverVisual compilation.

    Each hash chains to the previous: hash(prev_hash + current_data)
    """
    transcript_hash: str = ""
    claim_hash: str = ""
    query_hash: str = ""
    candidate_hash: str = ""
    selected_clip_hash: str = ""
    timeline_hash: str = ""
    receipt_hash: str = ""
    chain: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "transcript_hash": self.transcript_hash,
            "claim_hash": self.claim_hash,
            "query_hash": self.query_hash,
            "candidate_hash": self.candidate_hash,
            "selected_clip_hash": self.selected_clip_hash,
            "timeline_hash": self.timeline_hash,
            "receipt_hash": self.receipt_hash,
            "chain": self.chain,
        }

    def verify(self) -> bool:
        """Verify the chain is intact by recomputing each hash."""
        if not self.chain:
            return False

        prev = ""
        for link in self.chain:
            expected = sha256(prev + link["data"])
            if link["hash"] != expected:
                return False
            prev = link["hash"]

        return True


class ProofGenerator:
    """
    Generates and manages the proof hash chain for OverVisual compilations.

    Usage:
        gen = ProofGenerator()
        gen.add_transcript("The material could have been derived...")
        gen.add_claims([{"text": "...", "truth_status": "speculative"}])
        gen.add_queries(["ancient megalithic site sunrise", ...])
        gen.add_candidates([{"title": "...", "url": "..."}, ...])
        gen.add_selected_clips([{"title": "...", "timestamp": 5.0}, ...])
        gen.add_timeline({"segments": [...], "average_score": 0.85})
        chain = gen.finalize()
    """

    def __init__(self):
        self._chain = ProofChain()
        self._prev_hash = ""

    def _add_link(self, stage: str, data: str) -> str:
        """Add a link to the chain and return its hash."""
        h = sha256(self._prev_hash + data)
        self._chain.chain.append({
            "stage": stage,
            "data": data,
            "hash": h,
            "timestamp": time.time(),
        })
        self._prev_hash = h
        return h

    def add_transcript(self, transcript: str) -> str:
        """Hash the input transcript."""
        self._chain.transcript_hash = self._add_link("transcript", transcript)
        return self._chain.transcript_hash

    def add_claims(self, claims: list[dict]) -> str:
        """Hash the extracted claims."""
        data = json.dumps(claims, sort_keys=True)
        self._chain.claim_hash = self._add_link("claims", data)
        return self._chain.claim_hash

    def add_queries(self, queries: list[str]) -> str:
        """Hash the generated search queries."""
        data = json.dumps(queries, sort_keys=True)
        self._chain.query_hash = self._add_link("queries", data)
        return self._chain.query_hash

    def add_candidates(self, candidates: list[dict]) -> str:
        """Hash the candidate video results."""
        # Only hash essential fields to keep it stable
        essential = [
            {"title": c.get("title", ""), "url": c.get("url", ""), "source": c.get("source", "")}
            for c in candidates
        ]
        data = json.dumps(essential, sort_keys=True)
        self._chain.candidate_hash = self._add_link("candidates", data)
        return self._chain.candidate_hash

    def add_selected_clips(self, clips: list[dict]) -> str:
        """Hash the selected clips for the timeline."""
        essential = [
            {"title": c.get("title", ""), "timestamp": c.get("timestamp", 0.0),
             "score": c.get("score", 0.0)}
            for c in clips
        ]
        data = json.dumps(essential, sort_keys=True)
        self._chain.selected_clip_hash = self._add_link("selected_clips", data)
        return self._chain.selected_clip_hash

    def add_timeline(self, timeline: dict) -> str:
        """Hash the assembled timeline."""
        data = json.dumps(timeline, sort_keys=True)
        self._chain.timeline_hash = self._add_link("timeline", data)
        return self._chain.timeline_hash

    def finalize(self) -> ProofChain:
        """Finalize the chain with a receipt hash."""
        # Receipt hash = hash of all previous hashes
        all_hashes = json.dumps([
            self._chain.transcript_hash,
            self._chain.claim_hash,
            self._chain.query_hash,
            self._chain.candidate_hash,
            self._chain.selected_clip_hash,
            self._chain.timeline_hash,
        ], sort_keys=True)
        self._chain.receipt_hash = self._add_link("receipt", all_hashes)
        return self._chain

    def get_chain(self) -> ProofChain:
        """Get the current proof chain without finalizing."""
        return self._chain
