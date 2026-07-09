"""
Compute Capital — Computational Capital Valuation Kernel

Formalizes the "memory-as-collateralizable-continuity" thesis:

  Machine Value = Hardware Value + Recoverable Utility Value

Where:
  Hardware Value may decline through depreciation
  Recoverable Utility Value may rise through accumulated productive state

  If recoverable utility rises faster than hardware depreciates,
  the economic value of the machine can remain stable or increase
  even if its resale value declines.

Recoverable computational state includes:
  - Key-value caches
  - Embeddings
  - Workflow graphs
  - Execution traces
  - Semantic summaries
  - Checkpoints
  - Compiled artifacts
  - Agent memories
  - Code indexes
  - Retrieval structures
  - Model outputs
  - Latent representations
  - Reconstruction recipes

The real asset is not raw RAM. The real asset is deployable capacity.
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional


@dataclass
class HardwareSpec:
    purchase_price_usd: float = 3000.0
    purchase_date: str = ''
    ram_gb: float = 16.0
    cpu_cores: int = 8
    gpu_vram_gb: float = 0.0
    storage_gb: float = 512.0
    depreciation_years: float = 4.0
    current_age_years: float = 1.0


@dataclass
class RecoverableState:
    """Accumulated computational state that reduces future compute cost."""
    kv_cache_entries: int = 0
    kv_cache_size_mb: float = 0.0
    embeddings_count: int = 0
    embeddings_size_mb: float = 0.0
    workflow_graphs: int = 0
    execution_traces: int = 0
    semantic_summaries: int = 0
    checkpoints: int = 0
    compiled_artifacts: int = 0
    agent_memories: int = 0
    code_indexes: int = 0
    retrieval_structures: int = 0
    model_outputs: int = 0
    latent_representations: int = 0
    reconstruction_recipes: int = 0
    total_state_size_mb: float = 0.0


@dataclass
class VerifiedHistory:
    """Receipts and verified metrics from repeated execution."""
    agent_runs_total: int = 0
    agent_runs_successful: int = 0
    tasks_completed: int = 0
    releases_shipped: int = 0
    documents_generated: int = 0
    bugs_fixed: int = 0
    uptime_hours: float = 0.0
    cache_hit_rate: float = 0.0
    restore_success_rate: float = 0.0
    compute_saved_ms: float = 0.0
    latency_saved_ms: float = 0.0
    cloud_cost_avoided_usd: float = 0.0
    revenue_earned_usd: float = 0.0
    compression_ratio: float = 0.0
    reconstruction_cost_ms: float = 0.0


def compute_hardware_value(hw: HardwareSpec) -> dict:
    """Compute depreciated hardware value using straight-line depreciation."""
    annual_depreciation = hw.purchase_price_usd / hw.depreciation_years
    depreciated_value = max(
        hw.purchase_price_usd * 0.1,
        hw.purchase_price_usd - (annual_depreciation * hw.current_age_years)
    )
    return {
        'purchase_price_usd': hw.purchase_price_usd,
        'annual_depreciation_usd': round(annual_depreciation, 2),
        'current_age_years': hw.current_age_years,
        'depreciated_value_usd': round(depreciated_value, 2),
        'resale_value_usd': round(depreciated_value * 0.6, 2),
    }


def compute_recoverable_utility(state: RecoverableState, history: VerifiedHistory) -> dict:
    """
    Compute the value of accumulated computational state.

    The value comes from:
    1. Verified reuse (cache hits, restore success) — reduces future compute cost
    2. Productive output (tasks, releases, revenue) — demonstrates utility
    3. State inventory (embeddings, indexes, memories) — reconstruction cost avoided
    """
    if history.agent_runs_total == 0:
        return {
            'reuse_value_usd': 0.0,
            'productivity_value_usd': 0.0,
            'state_inventory_value_usd': 0.0,
            'total_utility_value_usd': 0.0,
            'confidence': 'NONE: no execution history',
        }

    success_rate = history.agent_runs_successful / max(1, history.agent_runs_total)

    reuse_value = (
        history.compute_saved_ms / 1000 / 3600 * 0.10
        + history.cloud_cost_avoided_usd
        + history.cache_hit_rate * history.agent_runs_total * 0.05
    )

    productivity_value = (
        history.tasks_completed * 2.0
        + history.releases_shipped * 50.0
        + history.documents_generated * 5.0
        + history.bugs_fixed * 10.0
        + history.revenue_earned_usd * 0.5
    )

    state_inventory_value = (
        state.kv_cache_entries * 0.01
        + state.embeddings_count * 0.005
        + state.workflow_graphs * 2.0
        + state.execution_traces * 0.10
        + state.checkpoints * 5.0
        + state.compiled_artifacts * 3.0
        + state.agent_memories * 1.0
        + state.code_indexes * 5.0
        + state.retrieval_structures * 2.0
        + state.reconstruction_recipes * 10.0
    )

    state_inventory_value *= success_rate

    total = reuse_value + productivity_value + state_inventory_value

    if history.restore_success_rate > 0.8 and success_rate > 0.7:
        confidence = 'HIGH: verified restore and high success rate'
    elif history.restore_success_rate > 0.5:
        confidence = 'MEDIUM: partial restore verification'
    elif success_rate > 0.5:
        confidence = 'LOW: execution history but no restore verification'
    else:
        confidence = 'NONE: insufficient verified history'

    return {
        'reuse_value_usd': round(reuse_value, 2),
        'productivity_value_usd': round(productivity_value, 2),
        'state_inventory_value_usd': round(state_inventory_value, 2),
        'total_utility_value_usd': round(total, 2),
        'success_rate': round(success_rate, 4),
        'restore_success_rate': history.restore_success_rate,
        'confidence': confidence,
    }


def compute_machine_value(hw: HardwareSpec, state: RecoverableState, history: VerifiedHistory) -> dict:
    """
    Full machine appraisal:

      Machine Value = Hardware Value + Recoverable Utility Value

    Also computes:
      - Reconstruction cost (future cost of rebuilding compressed state)
      - Net computational capital (machine value minus reconstruction liability)
      - Depreciation vs appreciation trajectory
    """
    hw_val = compute_hardware_value(hw)
    util_val = compute_recoverable_utility(state, history)

    machine_value = hw_val['depreciated_value_usd'] + util_val['total_utility_value_usd']

    reconstruction_cost = _compute_reconstruction_cost(state, history)

    net_computational_capital = machine_value - reconstruction_cost

    hw_depreciation_delta = hw_val['annual_depreciation_usd']
    utility_appreciation = util_val['total_utility_value_usd']

    trajectory = 'APPRECIATING' if utility_appreciation > hw_depreciation_delta else 'DEPRECIATING'

    return {
        'hardware_value': hw_val,
        'recoverable_utility': util_val,
        'reconstruction_cost_usd': round(reconstruction_cost, 2),
        'machine_value_usd': round(machine_value, 2),
        'net_computational_capital_usd': round(net_computational_capital, 2),
        'hw_depreciation_annual_usd': hw_depreciation_delta,
        'utility_appreciation_usd': utility_appreciation,
        'trajectory': trajectory,
        'trajectory_note': (
            f'Recoverable utility (${utility_appreciation:.2f}) exceeds '
            f'hardware depreciation (${hw_depreciation_delta:.2f}) — '
            f'machine value is {trajectory.lower()}'
        ),
        'timestamp': datetime.now().isoformat(),
    }


def _compute_reconstruction_cost(state: RecoverableState, history: VerifiedHistory) -> float:
    """
    Future cost of reconstructing compressed state.

    If state is compressed (compression_ratio > 0), reconstruction requires:
    - Compute time to regenerate
    - Fidelity risk (reconstruction may not be perfect)
    """
    if history.compression_ratio <= 0:
        return 0.0

    state_units = (
        state.kv_cache_entries + state.embeddings_count + state.workflow_graphs
        + state.execution_traces + state.checkpoints + state.compiled_artifacts
        + state.agent_memories + state.code_indexes + state.retrieval_structures
        + state.reconstruction_recipes
    )

    base_reconstruction_cost = state_units * 0.02
    fidelity_risk_penalty = base_reconstruction_cost * (1 - history.restore_success_rate) * 2

    return base_reconstruction_cost + fidelity_risk_penalty


def compute_node_appraisal(
    node_id: str,
    hw: HardwareSpec,
    state: RecoverableState,
    history: VerifiedHistory,
) -> dict:
    """
    Full node appraisal for underwriting.

    Appraises a computational node based on:
    - Hardware value (land + structure)
    - State inventory (capital improvements)
    - Utility history (income potential)
    - Allocation capacity (rentable capacity)
    - Agent demand (market demand)
    """
    machine_val = compute_machine_value(hw, state, history)

    allocation_capacity = {
        'ram_gb': hw.ram_gb,
        'cpu_cores': hw.cpu_cores,
        'gpu_vram_gb': hw.gpu_vram_gb,
        'storage_gb': hw.storage_gb,
        'allocatable_state_mb': state.total_state_size_mb,
    }

    demand_indicators = {
        'agent_runs': history.agent_runs_total,
        'success_rate': round(history.agent_runs_successful / max(1, history.agent_runs_total), 4),
        'uptime_hours': history.uptime_hours,
        'revenue_earned_usd': history.revenue_earned_usd,
    }

    return {
        'node_id': node_id,
        'appraisal_timestamp': datetime.now().isoformat(),
        'machine_value': machine_val,
        'allocation_capacity': allocation_capacity,
        'demand_indicators': demand_indicators,
        'appraisal_summary': {
            'machine_value_usd': machine_val['machine_value_usd'],
            'net_computational_capital_usd': machine_val['net_computational_capital_usd'],
            'trajectory': machine_val['trajectory'],
            'confidence': machine_val['recoverable_utility']['confidence'],
            'verdict': _node_verdict(machine_val),
        },
    }


def _node_verdict(machine_val: dict) -> str:
    net = machine_val['net_computational_capital_usd']
    traj = machine_val['trajectory']
    conf = machine_val['recoverable_utility']['confidence']

    if 'NONE' in conf:
        return 'UNVERIFIED: no execution history — cannot appraise recoverable utility'
    if net < 0:
        return 'UNDERWATER: reconstruction cost exceeds machine value'
    if traj == 'APPRECIATING' and 'HIGH' in conf:
        return 'FINANCEABLE: machine is appreciating with verified state'
    if traj == 'APPRECIATING':
        return 'POTENTIAL: machine is appreciating but verification is incomplete'
    return 'DEPRECIATING: hardware depreciation exceeds state accumulation'
