"""
Computational Capital Valuation
Values a machine as hardware + verified recoverable utility - future reconstruction cost
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass
from datetime import datetime

@dataclass
class MachineState:
    """State of a computational machine"""
    hardware_value_usd: float
    ram_gb: float
    cpu_cores: int
    storage_gb: float
    age_years: float
    
    # Recoverable state
    cache_hit_rate: float
    embeddings_count: int
    workflow_graphs: int
    execution_traces: int
    semantic_summaries: int
    checkpoints: int
    compiled_artifacts: int
    agent_memories: int
    code_indexes: int
    retrieval_structures: int
    model_outputs: int
    latent_representations: int
    reconstruction_recipes: int
    
    # Utility metrics
    jobs_completed: int
    restore_success_rate: float
    compute_saved_hours: float
    cloud_cost_avoided_usd: float
    uptime_percentage: float

@dataclass
class ValuationResult:
    """Valuation of computational capital"""
    hardware_value: float
    depreciation_rate: float
    recoverable_utility_value: float
    reconstruction_cost: float
    total_value: float
    value_per_gb_ram: float
    productivity_multiplier: float
    appraisal_memo: str
    timestamp: str

class ComputeCapitalValuation:
    """
    Values machines as: hardware + recoverable utility - reconstruction cost
    
    Thesis: A machine with accumulated productive state is worth more than
    resale value because it reduces future compute requirements.
    """
    
    def __init__(self):
        self.depreciation_schedule = {
            0: 1.0,    # New
            1: 0.85,   # 1 year
            2: 0.70,   # 2 years
            3: 0.55,   # 3 years
            4: 0.40,   # 4 years
            5: 0.25,   # 5+ years
        }
    
    def calculate_hardware_value(self, state: MachineState) -> float:
        """Calculate depreciated hardware value"""
        age_bucket = min(int(state.age_years), 5)
        multiplier = self.depreciation_schedule.get(age_bucket, 0.25)
        return state.hardware_value_usd * multiplier
    
    def calculate_recoverable_utility(self, state: MachineState) -> float:
        """
        Calculate value of recoverable computational state
        
        Each type of state has different utility value:
        - Caches: high utility for repeated work
        - Embeddings: high utility for semantic search
        - Workflows: high utility for automation
        - Traces: medium utility for debugging
        - Checkpoints: high utility for recovery
        """
        utility_score = 0
        
        # Cache utility (direct compute savings)
        utility_score += state.cache_hit_rate * 1000
        
        # Embeddings (semantic search capability)
        utility_score += state.embeddings_count * 10
        
        # Workflow graphs (automation value)
        utility_score += state.workflow_graphs * 500
        
        # Execution traces (debugging/reproducibility)
        utility_score += state.execution_traces * 5
        
        # Semantic summaries (knowledge compression)
        utility_score += state.semantic_summaries * 50
        
        # Checkpoints (recovery value)
        utility_score += state.checkpoints * 200
        
        # Compiled artifacts (ready-to-use)
        utility_score += state.compiled_artifacts * 100
        
        # Agent memories (continuity value)
        utility_score += state.agent_memories * 150
        
        # Code indexes (searchability)
        utility_score += state.code_indexes * 75
        
        # Retrieval structures (query efficiency)
        utility_score += state.retrieval_structures * 80
        
        # Model outputs (reusable generations)
        utility_score += state.model_outputs * 2
        
        # Latent representations (compressed knowledge)
        utility_score += state.latent_representations * 20
        
        # Reconstruction recipes (rebuild instructions)
        utility_score += state.reconstruction_recipes * 300
        
        # Apply restore success rate as quality multiplier
        utility_score *= state.restore_success_rate
        
        return utility_score
    
    def calculate_reconstruction_cost(self, state: MachineState) -> float:
        """
        Calculate cost to reconstruct state from scratch
        
        This is the "future cost" that reduces current value
        """
        # Compute cost to regenerate
        compute_hours = state.compute_saved_hours
        compute_cost_per_hour = 2.0  # $2/hour for cloud compute
        reconstruction_compute_cost = compute_hours * compute_cost_per_hour
        
        # Cloud cost that would be incurred without local state
        reconstruction_cloud_cost = state.cloud_cost_avoided_usd * 0.5
        
        # Time cost (opportunity cost)
        time_cost = compute_hours * 50  # $50/hour value of time
        
        return reconstruction_compute_cost + reconstruction_cloud_cost + time_cost
    
    def calculate_productivity_multiplier(self, state: MachineState) -> float:
        """
        Calculate how much more productive this machine is vs fresh hardware
        """
        base_multiplier = 1.0
        
        # Jobs completed indicates utilization
        if state.jobs_completed > 1000:
            base_multiplier += 0.3
        elif state.jobs_completed > 100:
            base_multiplier += 0.15
        
        # Uptime indicates reliability
        if state.uptime_percentage > 0.99:
            base_multiplier += 0.2
        elif state.uptime_percentage > 0.95:
            base_multiplier += 0.1
        
        # Restore success indicates state quality
        if state.restore_success_rate > 0.95:
            base_multiplier += 0.15
        elif state.restore_success_rate > 0.9:
            base_multiplier += 0.08
        
        return min(base_multiplier, 2.5)  # Cap at 2.5x
    
    def value(self, state: MachineState) -> ValuationResult:
        """Run full valuation"""
        hardware_value = self.calculate_hardware_value(state)
        recoverable_utility = self.calculate_recoverable_utility(state)
        reconstruction_cost = self.calculate_reconstruction_cost(state)
        productivity_multiplier = self.calculate_productivity_multiplier(state)
        
        # Total value = hardware + recoverable utility - reconstruction cost
        # Then apply productivity multiplier
        base_value = hardware_value + recoverable_utility - reconstruction_cost
        total_value = max(0, base_value * productivity_multiplier)
        
        # Value per GB of RAM (useful for comparison)
        value_per_gb = total_value / max(state.ram_gb, 1)
        
        # Generate appraisal memo
        memo = self.generate_memo(
            state, hardware_value, recoverable_utility,
            reconstruction_cost, total_value, productivity_multiplier
        )
        
        return ValuationResult(
            hardware_value=hardware_value,
            depreciation_rate=1 - self.depreciation_schedule.get(min(int(state.age_years), 5), 0.25),
            recoverable_utility_value=recoverable_utility,
            reconstruction_cost=reconstruction_cost,
            total_value=total_value,
            value_per_gb_ram=value_per_gb,
            productivity_multiplier=productivity_multiplier,
            appraisal_memo=memo,
            timestamp=datetime.now().isoformat()
        )
    
    def generate_memo(self, state: MachineState, hw_val: float, util_val: float,
                      recon_cost: float, total_val: float, mult: float) -> str:
        """Generate appraisal memo"""
        return f"""
COMPUTATIONAL CAPITAL APPRAISAL

Hardware Specification:
- Original Value: ${state.hardware_value_usd:,.2f}
- Current Value: ${hw_val:,.2f}
- RAM: {state.ram_gb} GB
- CPU Cores: {state.cpu_cores}
- Storage: {state.storage_gb} GB
- Age: {state.age_years} years

Recoverable State:
- Cache Hit Rate: {state.cache_hit_rate:.1%}
- Jobs Completed: {state.jobs_completed}
- Restore Success Rate: {state.restore_success_rate:.1%}
- Compute Saved: {state.compute_saved_hours:.1f} hours
- Cloud Cost Avoided: ${state.cloud_cost_avoided_usd:,.2f}
- Uptime: {state.uptime_percentage:.1%}

State Inventory:
- Embeddings: {state.embeddings_count}
- Workflow Graphs: {state.workflow_graphs}
- Execution Traces: {state.execution_traces}
- Checkpoints: {state.checkpoints}
- Agent Memories: {state.agent_memories}

Valuation:
- Hardware Value: ${hw_val:,.2f}
- Recoverable Utility Value: ${util_val:,.2f}
- Reconstruction Cost: ${recon_cost:,.2f}
- Productivity Multiplier: {mult:.2f}x
- TOTAL VALUE: ${total_val:,.2f}
- Value per GB RAM: ${total_val/state.ram_gb:,.2f}/GB

Thesis Application:
This machine is valued not merely as depreciating hardware but as computational
property with accumulated capital improvements. The recoverable state represents
verified reusable compute capacity that reduces future work requirements.

If recoverable utility rises faster than hardware depreciates, the economic value
of the machine can remain stable or increase even if resale value declines.

The financeable object is not raw RAM but deployable capacity: the amount of
productive work that can be performed using the machine and its accumulated state.
"""

# Example usage
if __name__ == "__main__":
    valuer = ComputeCapitalValuation()
    
    # Example: 3-year-old machine with significant state
    state = MachineState(
        hardware_value_usd=3000,
        ram_gb=64,
        cpu_cores=8,
        storage_gb=1000,
        age_years=3,
        cache_hit_rate=0.75,
        embeddings_count=5000,
        workflow_graphs=25,
        execution_traces=10000,
        semantic_summaries=200,
        checkpoints=50,
        compiled_artifacts=100,
        agent_memories=30,
        code_indexes=15,
        retrieval_structures=20,
        model_outputs=5000,
        latent_representations=1000,
        reconstruction_recipes=40,
        jobs_completed=2500,
        restore_success_rate=0.92,
        compute_saved_hours=500,
        cloud_cost_avoided_usd=2000,
        uptime_percentage=0.98
    )
    
    result = valuer.value(state)
    print(result.appraisal_memo)
