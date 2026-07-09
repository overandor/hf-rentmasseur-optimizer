#!/usr/bin/env python3
"""
ClientPulse OS — Genetic Pane Scheduler
Autonomously optimizes pane layout, schedules program lifecycles,
and spawns/retires panes based on throughput fitness.

Each program has a lifecycle: dormant → wake → execute → retire.
The GA evolves pane sizing and scheduling for maximum work density.
"""

import json
import math
import random
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

ROOT = Path(__file__).resolve().parent
SCHEDULE_DIR = ROOT / "content" / "schedule"
SCHEDULE_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class PaneGene:
    """A single pane's genetic representation."""
    module: str
    flex: float          # 0.1 to 3.0 — relative size weight
    wake_hour: int       # 0-23 — when this pane activates
    wake_minute: int     # 0-59
    active_duration: int # minutes — how long it stays alive
    priority: int        # 1-10 — execution priority
    co_operates_with: List[str] = field(default_factory=list)


@dataclass
class Genome:
    """A complete pane layout genome."""
    genes: List[PaneGene]
    fitness: float = 0.0
    generation: int = 0


@dataclass
class ScheduledProgram:
    """A program scheduled to wake at a specific time."""
    id: str
    module: str
    name: str
    wake_time: str       # ISO timestamp
    retire_time: str     # ISO timestamp
    priority: int
    flex: float
    status: str = "dormant"  # dormant → waking → executing → retiring → dormant
    co_operates_with: List[str] = field(default_factory=list)
    work_done: int = 0
    receipts_written: int = 0


# ---------------------------------------------------------------------------
# Genetic Algorithm — Pane Layout Optimizer
# ---------------------------------------------------------------------------

MODULES = [
    "immortality", "virality", "conversion", "trust",
    "velocity", "return", "bios", "decision", "receipts", "risk"
]


def random_gene(module: str = None) -> PaneGene:
    """Generate a random pane gene."""
    return PaneGene(
        module=module or random.choice(MODULES),
        flex=random.uniform(0.5, 2.0),
        wake_hour=random.randint(0, 23),
        wake_minute=random.choice([0, 15, 30, 45]),
        active_duration=random.choice([15, 30, 45, 60, 90, 120]),
        priority=random.randint(1, 10),
        co_operates_with=[],
    )


def random_genome(num_panes: int = 4) -> Genome:
    """Generate a random genome with N panes."""
    modules = random.sample(MODULES, min(num_panes, len(MODULES)))
    genes = [random_gene(m) for m in modules]
    # Wire cooperation — panes that wake near each other cooperate
    for i, g in enumerate(genes):
        for j, other in enumerate(genes):
            if i != j:
                wake_diff = abs(g.wake_hour * 60 + g.wake_minute - other.wake_hour * 60 - other.wake_minute)
                if wake_diff <= 30:
                    g.co_operates_with.append(other.module)
    return Genome(genes=genes)


def fitness_function(genome: Genome) -> float:
    """
    Fitness = work density × cooperation × coverage × efficiency.

    - Work density: how many panes are active simultaneously
    - Cooperation: how many panes share wake windows
    - Coverage: how many distinct modules are covered across 24h
    - Efficiency: active_duration / total_time (don't waste cycles)
    """
    genes = genome.genes
    if not genes:
        return 0.0

    # Coverage: distinct modules
    coverage = len(set(g.module for g in genes)) / len(MODULES)

    # Time coverage: how many hours have at least one active pane
    hourly_active = [0] * 24
    for g in genes:
        start = g.wake_hour
        duration_hours = g.active_duration / 60
        for h in range(int(duration_hours) + 1):
            hourly_active[(start + h) % 24] += 1
    time_coverage = sum(1 for a in hourly_active if a > 0) / 24

    # Cooperation: panes that co-activate
    cooperation_score = sum(len(g.co_operates_with) for g in genes) / max(len(genes), 1)

    # Simultaneity: peak concurrent panes
    peak_concurrent = max(hourly_active) if hourly_active else 1
    simultaneity = peak_concurrent / max(len(genes), 1)

    # Efficiency: average active duration relative to a 1-hour window
    avg_duration = sum(g.active_duration for g in genes) / len(genes)
    efficiency = min(1.0, avg_duration / 60)

    # Priority weighting
    avg_priority = sum(g.priority for g in genes) / len(genes)
    priority_score = avg_priority / 10

    # Flex balance — prefer varied sizes, not all equal
    flexes = [g.flex for g in genes]
    flex_variance = sum((f - sum(flexes) / len(flexes)) ** 2 for f in flexes) / len(flexes)
    flex_balance = min(1.0, flex_variance / 0.5)

    fitness = (
        coverage * 0.20 +
        time_coverage * 0.20 +
        cooperation_score * 0.15 +
        simultaneity * 0.15 +
        efficiency * 0.10 +
        priority_score * 0.10 +
        flex_balance * 0.10
    )

    return max(0.0, min(1.0, fitness))


def crossover(parent1: Genome, parent2: Genome) -> Genome:
    """Single-point crossover of two genomes."""
    if not parent1.genes or not parent2.genes:
        return parent1

    split = random.randint(1, max(len(parent1.genes) - 1, 1))
    child_genes = parent1.genes[:split] + parent2.genes[split:]
    return Genome(genes=child_genes, generation=max(parent1.generation, parent2.generation) + 1)


def mutate(genome: Genome, rate: float = 0.15) -> Genome:
    """Random mutation of genome."""
    for g in genome.genes:
        if random.random() < rate:
            g.flex = max(0.3, min(3.0, g.flex + random.gauss(0, 0.3)))
        if random.random() < rate:
            g.wake_hour = random.randint(0, 23)
        if random.random() < rate:
            g.wake_minute = random.choice([0, 15, 30, 45])
        if random.random() < rate:
            g.active_duration = random.choice([15, 30, 45, 60, 90, 120])
        if random.random() < rate * 0.5:
            g.priority = max(1, min(10, g.priority + random.choice([-1, 1])))
        if random.random() < rate * 0.3:
            g.module = random.choice(MODULES)
    # Rewire cooperation
    for i, g in enumerate(genome.genes):
        g.co_operates_with = []
        for j, other in enumerate(genome.genes):
            if i != j:
                wake_diff = abs(g.wake_hour * 60 + g.wake_minute - other.wake_hour * 60 - other.wake_minute)
                if wake_diff <= 30:
                    g.co_operates_with.append(other.module)
    return genome


def evolve(population: List[Genome], generations: int = 50, population_size: int = 20) -> Genome:
    """Run the genetic algorithm."""
    # Evaluate fitness
    for g in population:
        g.fitness = fitness_function(g)

    for gen in range(generations):
        # Sort by fitness
        population.sort(key=lambda g: g.fitness, reverse=True)

        # Elitism: keep top 20%
        elite_count = max(2, population_size // 5)
        new_pop = population[:elite_count]

        # Crossover and mutate to fill rest
        while len(new_pop) < population_size:
            p1 = tournament_select(population)
            p2 = tournament_select(population)
            child = crossover(p1, p2)
            child = mutate(child)
            child.fitness = fitness_function(child)
            new_pop.append(child)

        population = new_pop

    # Return best
    population.sort(key=lambda g: g.fitness, reverse=True)
    return population[0]


def tournament_select(population: List[Genome], k: int = 3) -> Genome:
    """Tournament selection."""
    contestants = random.sample(population, min(k, len(population)))
    return max(contestants, key=lambda g: g.fitness)


# ---------------------------------------------------------------------------
# Scheduler — Program Lifecycle
# ---------------------------------------------------------------------------

def genome_to_schedule(genome: Genome, base_date: datetime = None) -> List[ScheduledProgram]:
    """Convert a genome into a concrete schedule for a given day."""
    if base_date is None:
        base_date = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

    programs = []
    for g in genome.genes:
        wake = base_date + timedelta(hours=g.wake_hour, minutes=g.wake_minute)
        retire = wake + timedelta(minutes=g.active_duration)
        prog = ScheduledProgram(
            id=hashlib.sha256(f"{g.module}_{wake.isoformat()}".encode()).hexdigest()[:8],
            module=g.module,
            name=f"{g.module}_{wake.strftime('%H%M')}",
            wake_time=wake.isoformat(),
            retire_time=retire.isoformat(),
            priority=g.priority,
            flex=g.flex,
            co_operates_with=g.co_operates_with,
        )
        programs.append(prog)

    return sorted(programs, key=lambda p: p.wake_time)


def get_active_programs(schedule: List[ScheduledProgram], now: datetime = None) -> List[ScheduledProgram]:
    """Return programs that should be active right now."""
    if now is None:
        now = datetime.now(timezone.utc)

    active = []
    for prog in schedule:
        wake = datetime.fromisoformat(prog.wake_time)
        retire = datetime.fromisoformat(prog.retire_time)
        if wake <= now < retire:
            prog.status = "executing"
            active.append(prog)
        elif now < wake:
            prog.status = "dormant"
        else:
            prog.status = "retired"

    return active


def get_next_wakeups(schedule: List[ScheduledProgram], now: datetime = None, limit: int = 5) -> List[ScheduledProgram]:
    """Return the next N programs to wake up."""
    if now is None:
        now = datetime.now(timezone.utc)

    upcoming = []
    for prog in schedule:
        wake = datetime.fromisoformat(prog.wake_time)
        if wake > now and prog.status != "retired":
            upcoming.append(prog)

    upcoming.sort(key=lambda p: p.wake_time)
    return upcoming[:limit]


def save_schedule(schedule: List[ScheduledProgram]) -> None:
    """Save schedule to file."""
    data = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "programs": [
            {
                "id": p.id,
                "module": p.module,
                "name": p.name,
                "wake_time": p.wake_time,
                "retire_time": p.retire_time,
                "priority": p.priority,
                "flex": p.flex,
                "status": p.status,
                "co_operates_with": p.co_operates_with,
            }
            for p in schedule
        ],
    }
    with open(SCHEDULE_DIR / "today_schedule.json", "w") as f:
        json.dump(data, f, indent=2)


def save_genome(genome: Genome) -> None:
    """Save the evolved genome."""
    data = {
        "generation": genome.generation,
        "fitness": genome.fitness,
        "genes": [
            {
                "module": g.module,
                "flex": g.flex,
                "wake_hour": g.wake_hour,
                "wake_minute": g.wake_minute,
                "active_duration": g.active_duration,
                "priority": g.priority,
                "co_operates_with": g.co_operates_with,
            }
            for g in genome.genes
        ],
    }
    with open(SCHEDULE_DIR / "evolved_genome.json", "w") as f:
        json.dump(data, f, indent=2)


# ---------------------------------------------------------------------------
# Main — Evolve and Schedule
# ---------------------------------------------------------------------------

def run():
    """Evolve optimal pane layout and generate today's schedule."""
    print("=" * 60)
    print("GENETIC PANE SCHEDULER")
    print("=" * 60)

    # Initialize population
    print("\nInitializing population of 20 genomes...")
    population = [random_genome(num_panes=random.randint(3, 6)) for _ in range(20)]

    # Evolve
    print("Evolving for 50 generations...")
    best = evolve(population, generations=50, population_size=20)

    print(f"\nBest genome fitness: {best.fitness:.4f}")
    print(f"Generation: {best.generation}")
    print(f"Panes: {len(best.genes)}")

    for g in best.genes:
        print(f"  {g.module:15s} flex={g.flex:.2f} wake={g.wake_hour:02d}:{g.wake_minute:02d} "
              f"duration={g.active_duration}min priority={g.priority} "
              f"cooperates={g.co_operates_with}")

    # Generate schedule
    schedule = genome_to_schedule(best)
    save_schedule(schedule)
    save_genome(best)

    now = datetime.now(timezone.utc)
    active = get_active_programs(schedule, now)
    upcoming = get_next_wakeups(schedule, now)

    print(f"\n--- SCHEDULE FOR {now.strftime('%Y-%m-%d')} ---")
    print(f"Total programs: {len(schedule)}")
    print(f"Currently active: {len(active)}")
    for p in active:
        print(f"  ◉ EXECUTING: {p.name} (flex={p.flex:.2f}, priority={p.priority})")

    print(f"\nNext wakeups:")
    for p in upcoming:
        wake = datetime.fromisoformat(p.wake_time)
        delta = wake - now
        print(f"  ⧖ {p.name} wakes in {delta} (flex={p.flex:.2f})")

    # Hourly throughput estimate
    hourly = {}
    for p in schedule:
        wake = datetime.fromisoformat(p.wake_time)
        h = wake.hour
        hourly[h] = hourly.get(h, 0) + 1

    print(f"\nHourly spawn density:")
    for h in range(24):
        count = hourly.get(h, 0)
        bar = "◉" * count
        print(f"  {h:02d}:00 [{count}] {bar}")

    print("\n" + "=" * 60)
    print("Programs autonomously wake at their scheduled time,")
    print("execute their module function, write receipts,")
    print("then self-retire. The GA optimizes when each pane")
    print("should be active for maximum work density.")
    print("=" * 60)


if __name__ == "__main__":
    run()
