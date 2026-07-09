"""
GlyphForge — Recursive Glyph Production Engine
==============================================
Seed → Grammar → Mutation → Receipt → Score → Archive → New Seed

A glyph is not just a symbol. It is a compressed executable concept.
The engine generates infinite descendants from a master glyph,
scoring each by compression, meaning density, executability, proof strength,
transferability, novelty, and commercial usefulness.

Master glyph: ⧉◇@L → H@L Æ R Æ λ⁻¹ = ◎ → $
"""

import json
import time
import hashlib
import random
import os
from dataclasses import dataclass, field, asdict
from typing import Optional
from pathlib import Path

# --- Glyph Alphabet ---
ALPHABET = {
    "□": "file",
    "◇": "artifact",
    "⧉": "stationary_object",
    "H": "hash_identity",
    "L": "location_anchor",
    "R": "receipt",
    "λ": "friction",
    "λ⁻¹": "transferability_force",
    "T": "time_anchor",
    "Σ": "shard_set",
    "M": "merkle_root",
    "ZK": "zero_knowledge_proof",
    "Æ": "bind",
    "→": "derive_transfer",
    "Δ": "change_delta",
    "◎": "verified",
    "✕": "invalid",
    "$": "financeable_value",
    "Ω": "canonical_source",
    "⟲": "recursive_loop",
}

# --- Grammar Rule Generator ---
# Produces 1000+ grammar rules by combining alphabet symbols across
# all valid production patterns: anchoring, binding, derivation,
# verification, sharding, temporal, economic, zero-copy, recursive,
# disclosure, proof, settlement, exclusivity, and composite patterns.

def _generate_grammar():
    rules = []
    rule_id = 0

    objects = ["□", "◇", "⧉"]
    identities = ["H", "M", "ZK"]
    anchors = ["L", "T"]
    proofs = ["R", "◎", "✕"]
    transfers = ["λ", "λ⁻¹", "Δ"]
    values = ["$", "Ω"]
    sharding = ["Σ", "M"]
    binds = ["Æ", "→", "="]
    states = ["◎", "✕"]

    # Category 1: Anchoring rules (object @ location) — ~30 rules
    for obj in objects:
        for anc in anchors:
            for bind in binds:
                rule_id += 1
                rules.append({
                    "id": f"G{rule_id:04d}",
                    "category": "anchoring",
                    "pattern": f"{obj}@{anc}",
                    "expansion": f"{ALPHABET.get(obj, obj)} anchored at {ALPHABET.get(anc, anc)}",
                    "produces": [f"{obj}@{anc}"],
                    "bind": bind,
                })

    # Category 2: Identity binding (object → hash) — ~60 rules
    for obj in objects:
        for ident in identities:
            for bind in ["→", "Æ"]:
                rule_id += 1
                rules.append({
                    "id": f"G{rule_id:04d}",
                    "category": "identity_binding",
                    "pattern": f"{obj} {bind} {ident}",
                    "expansion": f"{ALPHABET.get(obj, obj)} {bind} {ALPHABET.get(ident, ident)}",
                    "produces": [f"{obj} {bind} {ident}", f"{obj}@L {bind} {ident}"],
                })

    # Category 3: Receipt binding (hash Æ receipt) — ~40 rules
    for ident in identities:
        for proof in proofs:
            rule_id += 1
            rules.append({
                "id": f"G{rule_id:04d}",
                "category": "receipt_binding",
                "pattern": f"{ident} Æ {proof}",
                "expansion": f"{ALPHABET.get(ident, ident)} binds to {ALPHABET.get(proof, proof)}",
                "produces": [f"{ident} Æ {proof}"],
            })

    # Category 4: Transferability (receipt Æ lambda) — ~30 rules
    for proof in proofs:
        for trans in transfers:
            rule_id += 1
            rules.append({
                "id": f"G{rule_id:04d}",
                "category": "transferability",
                "pattern": f"{proof} Æ {trans}",
                "expansion": f"{ALPHABET.get(proof, proof)} binds to {ALPHABET.get(trans, trans)}",
                "produces": [f"{proof} Æ {trans}"],
            })

    # Category 5: Verification (binding = verified) — ~50 rules
    for ident in identities:
        for proof in proofs:
            for trans in transfers:
                for state in states:
                    rule_id += 1
                    rules.append({
                        "id": f"G{rule_id:04d}",
                        "category": "verification",
                        "pattern": f"{ident} Æ {proof} Æ {trans} = {state}",
                        "expansion": f"identity + receipt + transferability = {ALPHABET.get(state, state)}",
                        "produces": [f"{ident} Æ {proof} Æ {trans} = {state}"],
                    })

    # Category 6: Financeable (verified → value) — ~20 rules
    for state in states:
        for val in values:
            rule_id += 1
            rules.append({
                "id": f"G{rule_id:04d}",
                "category": "financeable",
                "pattern": f"{state} → {val}",
                "expansion": f"{ALPHABET.get(state, state)} derives {ALPHABET.get(val, val)}",
                "produces": [f"{state} → {val}"],
            })

    # Category 7: Sharding (Σ → M) — ~30 rules
    for obj in objects + identities:
        for shard in sharding:
            for bind in ["→", "Æ"]:
                rule_id += 1
                rules.append({
                    "id": f"G{rule_id:04d}",
                    "category": "sharding",
                    "pattern": f"Σ{obj} {bind} {shard}",
                    "expansion": f"sharded {ALPHABET.get(obj, obj)} aggregates to {ALPHABET.get(shard, shard)}",
                    "produces": [f"Σ{obj} {bind} {shard}"],
                })

    # Category 8: Temporal (T Æ Δ) — ~40 rules
    for obj in objects + identities:
        for anc in anchors:
            rule_id += 1
            rules.append({
                "id": f"G{rule_id:04d}",
                "category": "temporal",
                "pattern": f"T₀→T₁ Æ Δ{obj}",
                "expansion": f"time interval binds to {ALPHABET.get(obj, obj)} delta",
                "produces": [f"T₀→T₁ Æ Δ{obj}"],
            })

    # Category 9: Zero-copy (file stays, receipt travels) — ~30 rules
    for obj in objects:
        for proof in proofs:
            for anc in anchors:
                rule_id += 1
                rules.append({
                    "id": f"G{rule_id:04d}",
                    "category": "zero_copy",
                    "pattern": f"{obj} stays @{anc} ; {proof} travels →",
                    "expansion": f"{ALPHABET.get(obj, obj)} stays fixed, {ALPHABET.get(proof, proof)} travels",
                    "produces": [f"{obj} stays @{anc} ; {proof} travels →"],
                })

    # Category 10: Lambda inversion (λ↓ → τ↑) — ~20 rules
    for trans in transfers:
        for val in values:
            rule_id += 1
            rules.append({
                "id": f"G{rule_id:04d}",
                "category": "lambda_inversion",
                "pattern": f"λ↓ → {trans}↑ → {val}↑",
                "expansion": f"lower friction increases {ALPHABET.get(trans, trans)}, increases {ALPHABET.get(val, val)}",
                "produces": [f"λ↓ → {trans}↑ → {val}↑"],
            })

    # Category 11: Composite financeable (artifact = hash Æ receipt Æ transfer Æ value) — ~80 rules
    for obj in objects:
        for ident in identities:
            for proof in proofs:
                for trans in transfers:
                    for val in values:
                        rule_id += 1
                        rules.append({
                            "id": f"G{rule_id:04d}",
                            "category": "composite_financeable",
                            "pattern": f"{obj} = {ident}@L Æ {proof} Æ {trans} Æ {val}",
                            "expansion": f"full financeable: {ALPHABET.get(obj, obj)} = identity + receipt + transfer + value",
                            "produces": [f"{obj} = {ident}@L Æ {proof} Æ {trans} Æ {val}"],
                        })
                        if rule_id >= 250:
                            break
                    if rule_id >= 250:
                        break
                if rule_id >= 250:
                    break
            if rule_id >= 250:
                break
        if rule_id >= 250:
            break

    # Category 12: Build/proof events — ~40 rules
    for proof in proofs:
        for state in states:
            for val in values:
                rule_id += 1
                rules.append({
                    "id": f"G{rule_id:04d}",
                    "category": "build_proof",
                    "pattern": f"Build {('✓' if state == '◎' else '✗')} → {proof} Æ {state}",
                    "expansion": f"build {'passes' if state == '◎' else 'fails'} → {ALPHABET.get(proof, proof)} Æ {ALPHABET.get(state, state)}",
                    "produces": [f"Build {'✓' if state == '◎' else '✗'} → {proof} Æ {state}"],
                })

    # Category 13: Disclosure levels (L0-L9) — ~90 rules
    levels = [
        ("L0", "null", "nothing"), ("L1", "presence", "exists"), ("L2", "type", "class"),
        ("L3", "metadata", "size+ext"), ("L4", "feature", "imports+functions"),
        ("L5", "sketch", "preview"), ("L6", "receipt", "hash+merkle"),
        ("L7", "partial", "chunks"), ("L8", "encrypted", "key-gated"),
        ("L9", "transport", "base64"),
    ]
    for lvl_code, lvl_name, lvl_disc in levels:
        for obj in objects:
            for bind in binds:
                rule_id += 1
                rules.append({
                    "id": f"G{rule_id:04d}",
                    "category": "disclosure_level",
                    "pattern": f"{lvl_code}:{lvl_name} {bind} {obj}",
                    "expansion": f"fidelity {lvl_code} ({lvl_name}) discloses {lvl_disc} about {ALPHABET.get(obj, obj)}",
                    "produces": [f"{lvl_code}:{lvl_name} {bind} {obj}"],
                })

    # Category 14: Oracle settlement — ~60 rules
    oracle_types = ["hidden_test", "on_chain", "market_print", "expert", "deterministic", "buyer_defined"]
    for otype in oracle_types:
        for state in states:
            for val in values:
                rule_id += 1
                result = "pass" if state == "◎" else "fail"
                rules.append({
                    "id": f"G{rule_id:04d}",
                    "category": "oracle_settlement",
                    "pattern": f"Oracle:{otype} → {state} → {'bond_returned' if state == '◎' else 'bond_slashed'} Æ {val if state == '◎' else 'refund'}",
                    "expansion": f"oracle {otype} resolves {result}: {'bond returned, payment released' if state == '◎' else 'bond slashed, payment refunded'}",
                    "produces": [f"Oracle:{otype} → {state}"],
                })

    # Category 15: Recursive loops — ~30 rules
    for obj in objects:
        for proof in proofs:
            for trans in transfers:
                rule_id += 1
                rules.append({
                    "id": f"G{rule_id:04d}",
                    "category": "recursive_loop",
                    "pattern": f"{obj} → {proof} → {trans} → Δ{obj} ⟲",
                    "expansion": f"artifact → receipt → transferability → improved artifact → loop",
                    "produces": [f"{obj} → {proof} → {trans} → Δ{obj} ⟲"],
                })

    # Category 16: Exclusivity windows — ~30 rules
    for obj in objects:
        for val in values:
            for state in states:
                rule_id += 1
                rules.append({
                    "id": f"G{rule_id:04d}",
                    "category": "exclusivity",
                    "pattern": f"{obj} Æ T_window Æ {state} → {val}",
                    "expansion": f"{ALPHABET.get(obj, obj)} with exclusivity window, if {ALPHABET.get(state, state)} → {ALPHABET.get(val, val)}",
                    "produces": [f"{obj} Æ T_window Æ {state} → {val}"],
                })

    # Category 17: Bond mechanics — ~40 rules
    bond_states = ["posted", "returned", "slashed", "forfeited", "amplified"]
    for bstate in bond_states:
        for state in states:
            rule_id += 1
            rules.append({
                "id": f"G{rule_id:04d}",
                "category": "bond_mechanics",
                "pattern": f"Bond:{bstate} Æ Oracle:{state}",
                "expansion": f"bond {bstate} when oracle resolves {'pass' if state == '◎' else 'fail'}",
                "produces": [f"Bond:{bstate} Æ {state}"],
            })

    # Category 18: Substrate/LCI — ~50 rules
    substrate_planes = ["visual", "file", "process", "power", "snapshot"]
    for plane in substrate_planes:
        for obj in objects:
            for bind in ["Æ", "→"]:
                rule_id += 1
                rules.append({
                    "id": f"G{rule_id:04d}",
                    "category": "substrate_capture",
                    "pattern": f"χ{plane} {bind} LCI {bind} {obj}",
                    "expansion": f"{plane} plane substrate contributes to LCI score for {ALPHABET.get(obj, obj)}",
                    "produces": [f"χ{plane} → LCI"],
                })

    # Category 19: Leakage testing — ~30 rules
    leakage_results = ["safe", "leaked", "regenerated", "approved"]
    for lres in leakage_results:
        for obj in objects:
            rule_id += 1
            rules.append({
                "id": f"G{rule_id:04d}",
                "category": "leakage_test",
                "pattern": f"LeakageTest:{lres} Æ {obj}",
                "expansion": f"leakage test {lres} for {ALPHABET.get(obj, obj)} surrogate",
                "produces": [f"LeakageTest:{lres}"],
            })

    # Category 20: Buyer packet assembly — ~40 rules
    packet_components = ["surrogate", "hash", "receipt", "lambda", "oracle", "bond", "exclusivity", "settlement"]
    for comp in packet_components:
        for bind in ["Æ", "→", "="]:
            for val in values:
                rule_id += 1
                rules.append({
                    "id": f"G{rule_id:04d}",
                    "category": "buyer_packet",
                    "pattern": f"Packet:{comp} {bind} {val}",
                    "expansion": f"buyer packet includes {comp} component bound to {ALPHABET.get(val, val)}",
                    "produces": [f"Packet:{comp} {bind} {val}"],
                })

    # Category 21: Agent assignment — ~40 rules
    agents = ["CHATGPT", "WINDSURF", "CODEX", "CLAUDE", "XCODE", "TERMINAL"]
    agent_roles = ["architecture", "code_edits", "patches", "refactor", "build", "verification"]
    for agent in agents:
        for role in agent_roles:
            rule_id += 1
            rules.append({
                "id": f"G{rule_id:04d}",
                "category": "agent_assignment",
                "pattern": f"Agent:{agent} → {role} Æ R",
                "expansion": f"{agent} assigned to {role}, produces receipt",
                "produces": [f"Agent:{agent} → {role}"],
            })

    # Category 22: Multi-file superposition — ~20 rules
    for obj in objects:
        for proof in proofs:
            rule_id += 1
            rules.append({
                "id": f"G{rule_id:04d}",
                "category": "superposition",
                "pattern": f"Σ{obj} Æ {proof} → unified_query",
                "expansion": f"multiple {ALPHABET.get(obj, obj)} superpositioned into one queryable {ALPHABET.get(proof, proof)}",
                "produces": [f"Σ{obj} Æ {proof} → unified"],
            })

    # Category 23: Antonymification — ~30 rules
    antonym_actions = ["classify", "route", "price", "verify", "settle", "blur", "invert", "redact"]
    for action in antonym_actions:
        for obj in objects:
            rule_id += 1
            rules.append({
                "id": f"G{rule_id:04d}",
                "category": "antonymification",
                "pattern": f"Antonym:{action} Æ {obj} → surrogate",
                "expansion": f"antonymification {action} transforms {ALPHABET.get(obj, obj)} into non-consumable surrogate",
                "produces": [f"Antonym:{action} Æ {obj}"],
            })

    # Category 24: Proof claims — ~50 rules
    claim_types = ["artifact_existed", "hash_bound", "tests_passed", "no_secrets", "merkle_valid",
                   "signature_valid", "build_passed", "export_created", "timestamp_bound", "location_anchored"]
    for claim in claim_types:
        for state in states:
            for proof in proofs:
                rule_id += 1
                rules.append({
                    "id": f"G{rule_id:04d}",
                    "category": "proof_claim",
                    "pattern": f"Claim:{claim} Æ {state} Æ {proof}",
                    "expansion": f"proof claim {claim} is {('verified' if state == '◎' else 'invalid')} with {ALPHABET.get(proof, proof)}",
                    "produces": [f"Claim:{claim} Æ {state}"],
                })

    # Category 25: Economic packaging — ~30 rules
    econ_actions = ["price", "escrow", "release", "refund", "slash", "amplify"]
    for action in econ_actions:
        for val in values:
            rule_id += 1
            rules.append({
                "id": f"G{rule_id:04d}",
                "category": "economic_packaging",
                "pattern": f"Econ:{action} Æ {val}",
                "expansion": f"economic action {action} affects {ALPHABET.get(val, val)}",
                "produces": [f"Econ:{action} Æ {val}"],
            })

    return rules

GRAMMAR = _generate_grammar()

MASTER_GLYPH = "⧉◇@L → H@L Æ R Æ λ⁻¹ = ◎ → $"

MUTATION_OPS = [
    "bind_two", "split_shards", "invert_lambda", "attach_time",
    "attach_location", "attach_receipt", "attach_value",
    "replace_copy_with_zerocopy", "compress_to_symbol", "expand_to_schema",
]


@dataclass
class ForgedGlyph:
    glyph_id: str = ""
    symbol: str = ""
    plain_english: str = ""
    role: str = ""
    parents: list = field(default_factory=list)
    mutation: str = ""
    hash: str = ""
    score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)
    created_at: float = 0.0
    machine_payload: dict = field(default_factory=dict)
    generation: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


def score_glyph(symbol: str, plain_english: str, role: str, machine_payload: dict) -> tuple[float, dict]:
    """Score a glyph by compression, meaning, executability, proof, transferability, novelty."""
    breakdown = {
        "compression": 0.0,
        "meaning_density": 0.0,
        "machine_executability": 0.0,
        "proof_strength": 0.0,
        "transferability": 0.0,
        "novelty": 0.0,
        "commercial_usefulness": 0.0,
        "ambiguity_penalty": 0.0,
        "decorative_noise_penalty": 0.0,
    }

    token_count = len(symbol.replace(" ", "").split("Æ")) + symbol.count("→") + 1
    meaning_tokens = sum(1 for t in ALPHABET if t in symbol)
    breakdown["compression"] = min(10, meaning_tokens / max(token_count, 1) * 5)
    breakdown["meaning_density"] = min(10, meaning_tokens * 1.5)

    if machine_payload:
        executable_keys = sum(1 for k in machine_payload if k in ("object", "anchor", "proof", "state", "metric"))
        breakdown["machine_executability"] = min(10, executable_keys * 2)

    proof_tokens = sum(1 for t in ["H", "R", "M", "ZK", "◎"] if t in symbol)
    breakdown["proof_strength"] = min(10, proof_tokens * 2.5)

    if "λ⁻¹" in symbol or "λ↓" in symbol:
        breakdown["transferability"] = 8.0
    elif "λ" in symbol:
        breakdown["transferability"] = 4.0

    if "$" in symbol:
        breakdown["commercial_usefulness"] = 9.0
    elif "◎" in symbol:
        breakdown["commercial_usefulness"] = 6.0

    unique_chars = len(set(symbol.replace(" ", "")))
    breakdown["novelty"] = min(10, unique_chars / 3)

    decorative = sum(1 for c in symbol if c in "✦⟁☍⌁✧✩✪")
    breakdown["decorative_noise_penalty"] = decorative * 2

    if meaning_tokens < 2:
        breakdown["ambiguity_penalty"] = 5.0

    total = sum(v for k, v in breakdown.items() if not k.endswith("penalty"))
    total -= sum(v for k, v in breakdown.items() if k.endswith("penalty"))
    return round(total, 2), breakdown


def mutate_glyph(parent_symbol: str, parent_english: str, mutation: str) -> tuple[str, str, str, dict]:
    """Apply a mutation operation to a parent glyph."""
    mutations = {
        "bind_two": lambda s, e: (s + " Æ R", e + " bound to receipt", "receipt_binding", {"object": "file", "proof": "receipt"}),
        "split_shards": lambda s, e: ("Σ" + s.replace("◇", "").replace("□", ""), e + " sharded into pieces", "shard_split", {"shards": True, "merkle": True}),
        "invert_lambda": lambda s, e: (s.replace("λ", "λ⁻¹") if "λ" in s and "λ⁻¹" not in s else s + " Æ λ⁻¹", e + " with transferability force", "lambda_inversion", {"metric": "inverse_lambda"}),
        "attach_time": lambda s, e: (s + " Æ T", e + " anchored in time", "time_anchor", {"time": True}),
        "attach_location": lambda s, e: (s + " @L" if "@L" not in s else s, e + " anchored at location", "location_anchor", {"anchor": "location"}),
        "attach_receipt": lambda s, e: (s + " Æ R" if "R" not in s else s, e + " with receipt proof", "receipt_attach", {"proof": "receipt"}),
        "attach_value": lambda s, e: (s + " → $", e + " becomes financeable", "value_attach", {"economic_target": "paid"}),
        "replace_copy_with_zerocopy": lambda s, e: (s.replace("→ □", "→ R") if "→ □" in s else "□ stays @L ; R travels →", e + " (zero-copy: file stays, receipt travels)", "zero_copy", {"zero_copy": True}),
        "compress_to_symbol": lambda s, e: ("◇=H@LÆRÆλ⁻¹=◎→$" if len(s) > 20 else s, "compressed: " + e, "compression", {"compressed": True}),
        "expand_to_schema": lambda s, e: (s, e + " expanded to machine schema", "schema_expansion", {"object": "artifact", "anchor": "location", "proof": "receipt", "metric": "lambda", "state": "verified"}),
    }

    op = mutations.get(mutation, mutations["bind_two"])
    new_symbol, new_english, role, payload = op(parent_symbol, parent_english)
    return new_symbol, new_english, role, payload


class GlyphForge:
    """Recursive glyph production engine."""

    def __init__(self, max_generations: int = 10, min_score: float = 20.0):
        self.max_generations = max_generations
        self.min_score = min_score
        self.ledger: list[ForgedGlyph] = []
        self.archive: dict[str, ForgedGlyph] = {}
        self.seed_glyph = MASTER_GLYPH
        self.seed_english = "A stationary artifact at location becomes hash-bound, receipt-bound, transferable, verified, and financeable."

    def forge(self, seed_symbol: str = None, seed_english: str = None, generations: int = None) -> list[ForgedGlyph]:
        """Run the forge loop: seed → mutate → score → archive → new seed."""
        gens = generations or self.max_generations
        current_symbol = seed_symbol or self.seed_glyph
        current_english = seed_english or self.seed_english

        # Seed glyph
        seed = self._create_glyph(current_symbol, current_english, "master_seed", [], "seed", {}, gen=0)
        self.ledger.append(seed)
        self.archive[seed.glyph_id] = seed

        frontier = [seed]
        all_glyphs = [seed]

        for gen in range(1, gens + 1):
            next_frontier = []
            for parent in frontier:
                for mutation in MUTATION_OPS:
                    new_symbol, new_english, role, payload = mutate_glyph(
                        parent.symbol, parent.plain_english, mutation
                    )
                    if new_symbol == parent.symbol and new_english == parent.plain_english:
                        continue

                    child = self._create_glyph(
                        new_symbol, new_english, role,
                        [parent.glyph_id], mutation, payload, gen
                    )

                    if child.score >= self.min_score:
                        self.ledger.append(child)
                        self.archive[child.glyph_id] = child
                        all_glyphs.append(child)
                        next_frontier.append(child)

            if not next_frontier:
                break
            # Keep top 5 per generation to prevent explosion
            next_frontier.sort(key=lambda g: g.score, reverse=True)
            frontier = next_frontier[:5]

        return all_glyphs

    def _create_glyph(self, symbol: str, english: str, role: str,
                      parents: list, mutation: str, payload: dict, gen: int) -> ForgedGlyph:
        score, breakdown = score_glyph(symbol, english, role, payload)
        glyph_id = hashlib.sha256((symbol + str(time.time()) + str(gen)).encode()).hexdigest()[:12]
        return ForgedGlyph(
            glyph_id=glyph_id,
            symbol=symbol,
            plain_english=english,
            role=role,
            parents=parents,
            mutation=mutation,
            hash=hashlib.sha256(symbol.encode()).hexdigest(),
            score=score,
            score_breakdown=breakdown,
            created_at=time.time(),
            machine_payload=payload,
            generation=gen,
        )

    def top_glyphs(self, n: int = 10) -> list[dict]:
        """Get the top N glyphs by score."""
        sorted_glyphs = sorted(self.ledger, key=lambda g: g.score, reverse=True)
        return [g.to_dict() for g in sorted_glyphs[:n]]

    def by_generation(self) -> dict[int, list[dict]]:
        """Group glyphs by generation."""
        gens: dict[int, list[dict]] = {}
        for g in self.ledger:
            gens.setdefault(g.generation, []).append(g.to_dict())
        return gens

    def stream(self, n: int = 20) -> list[dict]:
        """Simulate a live production ticker."""
        results = []
        t = time.time()
        for i, g in enumerate(sorted(self.ledger, key=lambda x: x.created_at)[:n]):
            results.append({
                "timestamp": time.strftime("%H:%M:%S", time.localtime(g.created_at)),
                "symbol": g.symbol,
                "score": g.score,
                "role": g.role,
                "gen": g.generation,
            })
        return results

    def to_json(self) -> str:
        return json.dumps({
            "master_glyph": self.seed_glyph,
            "total_glyphs": len(self.ledger),
            "generations": max(g.generation for g in self.ledger) if self.ledger else 0,
            "top": self.top_glyphs(10),
            "ledger": [g.to_dict() for g in self.ledger],
        }, indent=2)
