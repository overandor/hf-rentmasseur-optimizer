"""
Genetic Algorithm for bio optimization.

Evolution target: maximize CTR + email + phone-call predictions.
Genetic operators: crossover, mutation, tournament selection.
Population: generated bios or from library.
Result: top elite individuals for A/B testing.
"""

import logging
import random
import time
from typing import Dict, List, Tuple

from .bio_generator import (
    _generate_headline, _generate_description, _score_variant, _sentiment_score,
    HEADLINE_TEMPLATES, HOOKS, SPECIALTIES, CLIENTS, STYLES, PROOFS, CTAS,
)
from .bio_features import feature_vector
from .bio_predictor import predict_performance, train_predictor, MLP
from .db import upsert_content_variant, write_receipt

log = logging.getLogger("profileops.evolver")


def _crossover(parent1: Dict, parent2: Dict) -> Dict:
    """Create child by combining headline from one parent and desc from another."""
    return {
        "headline": parent1["headline"],
        "description": parent2["description"],
    }


def _mutate_headline(headline: str) -> str:
    """Mutate a headline."""
    return _generate_headline()


def _mutate_description(description: str) -> str:
    """Mutate a description by swapping a random paragraph."""
    parts = {
        "hook": random.choice(HOOKS),
        "specialty": random.choice(SPECIALTIES),
        "client": random.choice(CLIENTS),
        "style": random.choice(STYLES),
        "proof": random.choice(PROOFS),
        "cta": random.choice(CTAS),
    }
    return random.choice([
        f"{parts['hook']}\n\n{parts['specialty']}\n\n{parts['client']}\n\n{parts['style']}\n\n{parts['cta']}",
        f"{parts['hook']}\n\n{parts['style']}\n\n{parts['specialty']}\n\n{parts['proof']}\n\n{parts['cta']}",
    ])


def _mutate(bio: Dict, mutation_rate: float = 0.3) -> Dict:
    headline = bio["headline"]
    description = bio["description"]
    if random.random() < mutation_rate:
        headline = _mutate_headline(headline)
    if random.random() < mutation_rate:
        description = _mutate_description(description)
    return {"headline": headline, "description": description}


def _fitness(bio: Dict, model: MLP = None, speech_weight: float = 0.5) -> float:
    """Fitness = weighted sum of predicted CTR, email, phone, sentiment, speech, minus risk."""
    from .bio_features import extract_features
    scores = _score_variant(bio["headline"], bio["description"])
    pred = predict_performance(bio["headline"], bio["description"], model)
    features = extract_features(bio["headline"], bio["description"])
    risk_penalty = max(0, scores["headline_risk"], scores["bio_risk"]) * 0.5
    # Weighted: CTR, email, phone, sentiment, speech-friendliness
    fitness = (
        pred["ctr"] * 3.0
        + pred["email"] * 2.0
        + pred["phone"] * 1.5
        + scores["sentiment"]["score"] * 0.5
        + features["speech_score"] * speech_weight
        - risk_penalty
    )
    return fitness


def _tournament_select(population: List[Dict], fitnesses: List[float], k: int = 3) -> Dict:
    selected = random.sample(list(zip(population, fitnesses)), min(k, len(population)))
    selected.sort(key=lambda x: x[1], reverse=True)
    return selected[0][0]


def evolve(population: List[Dict], generations: int = 50, population_size: int = 100,
           elite_size: int = 10, mutation_rate: float = 0.3,
           model: MLP = None) -> List[Dict]:
    """Run genetic algorithm to optimize bios."""
    log.info("Starting GA: %d generations, pop=%d", generations, population_size)

    # If population is too small, seed with more random
    while len(population) < population_size:
        population.append({"headline": _generate_headline(), "description": _generate_description()})

    for gen in range(generations):
        # Evaluate fitness
        fitnesses = [_fitness(bio, model) for bio in population]

        # Sort by fitness
        ranked = sorted(zip(population, fitnesses), key=lambda x: x[1], reverse=True)
        log.info("Gen %d: best fitness=%.4f", gen, ranked[0][1])

        # Elites
        elites = [bio for bio, _ in ranked[:elite_size]]

        # Create next generation
        next_pop = elites[:]
        while len(next_pop) < population_size:
            parent1 = _tournament_select(population, fitnesses)
            parent2 = _tournament_select(population, fitnesses)
            child = _crossover(parent1, parent2)
            child = _mutate(child, mutation_rate)
            next_pop.append(child)

        population = next_pop

    # Final evaluation
    fitnesses = [_fitness(bio, model) for bio in population]
    ranked = sorted(zip(population, fitnesses), key=lambda x: x[1], reverse=True)
    return [bio for bio, _ in ranked[:elite_size]]


def run_evolution(initial_bios: List[Dict] = None, generations: int = 50,
                  population_size: int = 100, elite_size: int = 10,
                  top_n: int = 10) -> List[Dict]:
    """Full GA pipeline: train predictor, evolve, save top elites."""
    if initial_bios is None:
        from .bio_generator import generate_bios
        initial_bios = generate_bios(count=population_size, top_n=population_size)

    # Train predictor on initial population
    model = train_predictor(initial_bios, epochs=300)

    # Run GA
    elites = evolve(initial_bios, generations=generations, population_size=population_size,
                    elite_size=elite_size, model=model)

    # Save elites
    batch_id = f"ga_{int(time.time())}"
    saved_ids = []
    for i, bio in enumerate(elites):
        variant_id = f"{batch_id}_{i:03d}"
        pred = predict_performance(bio["headline"], bio["description"], model)
        scores = _score_variant(bio["headline"], bio["description"])
        upsert_content_variant(
            variant_id, "bio",
            headline=bio["headline"],
            description=bio["description"],
            hypothesis=f"GA elite. CTR={pred['ctr']}, email={pred['email']}, phone={pred['phone']}, fitness={_fitness(bio, model):.4f}",
            status="draft"
        )
        saved_ids.append(variant_id)

    write_receipt(
        "ga_evolution_v1",
        "run_evolution",
        {"generations": generations, "population_size": population_size},
        {"elites_saved": len(saved_ids), "top_fitness": _fitness(elites[0], model) if elites else 0},
        verified=True,
    )
    log.info("GA evolution complete. Saved %d elites.", len(saved_ids))
    return saved_ids
