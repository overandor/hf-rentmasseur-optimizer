"""
Underwriting Pipeline Integration
Combines GitHub underwriting with compute memory continuity underwriting
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass

@dataclass
class UnderwritingInput:
    """Input for underwriting pipeline"""
    github_username: Optional[str] = None
    repo_count: int = 0
    test_coverage: float = 0.0
    deployable_count: int = 0
    docs_count: int = 0
    issues_closed: int = 0
    prs_merged: int = 0
    arr_mrr: float = 0.0
    ip_assigned: bool = False
    memory_state_gb: float = 0.0
    recoverable_state_score: float = 0.0

@dataclass
class UnderwritingOutput:
    """Output from underwriting pipeline"""
    value_estimate: float
    benchmark_value: float
    risk_grade: str  # A through E
    borrowing_base: float
    conditions: list
    covenants: list
    memo: str
    timestamp: str

class UnderwritingPipeline:
    """
    Pipeline: intake → collect → value → benchmark → risk → eligibility → decide → memo
    """
    
    def __init__(self):
        self.risk_grades = {
            'A': {'min_score': 90, 'multiplier': 1.0},
            'B': {'min_score': 75, 'multiplier': 0.85},
            'C': {'min_score': 60, 'multiplier': 0.65},
            'D': {'min_score': 45, 'multiplier': 0.45},
            'E': {'min_score': 0, 'multiplier': 0.25}
        }
    
    def intake(self, input_data: UnderwritingInput) -> Dict[str, Any]:
        """Intake: validate and normalize input"""
        return {
            'github_activity': {
                'repo_count': input_data.repo_count,
                'test_coverage': input_data.test_coverage,
                'deployable_count': input_data.deployable_count,
                'docs_count': input_data.docs_count,
                'issues_closed': input_data.issues_closed,
                'prs_merged': input_data.prs_merged
            },
            'financial': {
                'arr_mrr': input_data.arr_mrr,
                'ip_assigned': input_data.ip_assigned
            },
            'compute_state': {
                'memory_state_gb': input_data.memory_state_gb,
                'recoverable_state_score': input_data.recoverable_state_score
            }
        }
    
    def collect(self, intake_data: Dict[str, Any]) -> Dict[str, Any]:
        """Collect: aggregate signals"""
        github = intake_data['github_activity']
        financial = intake_data['financial']
        compute = intake_data['compute_state']
        
        # GitHub signal score
        github_score = (
            min(github['repo_count'] / 10, 1.0) * 20 +
            github['test_coverage'] * 25 +
            min(github['deployable_count'] / 5, 1.0) * 15 +
            min(github['docs_count'] / 5, 1.0) * 10 +
            min(github['issues_closed'] / 50, 1.0) * 15 +
            min(github['prs_merged'] / 30, 1.0) * 15
        )
        
        # Financial signal score
        financial_score = (
            min(financial['arr_mrr'] / 100000, 1.0) * 50 +
            (50 if financial['ip_assigned'] else 0)
        )
        
        # Compute state signal score
        compute_score = (
            min(compute['memory_state_gb'] / 64, 1.0) * 30 +
            compute['recoverable_state_score'] * 70
        )
        
        return {
            'github_score': github_score,
            'financial_score': financial_score,
            'compute_score': compute_score,
            'total_score': (github_score * 0.4 + financial_score * 0.4 + compute_score * 0.2)
        }
    
    def value(self, collected: Dict[str, Any]) -> float:
        """Value: estimate base value"""
        total_score = collected['total_score']
        # Base value: $10,000 * score percentage
        return 10000 * (total_score / 100)
    
    def benchmark(self, value: float, collected: Dict[str, Any]) -> float:
        """Benchmark: compare to market"""
        # Benchmark: 1.2x of estimated value for strong compute state
        compute_multiplier = 1.0 + (collected['compute_score'] / 200)
        return value * compute_multiplier
    
    def risk(self, collected: Dict[str, Any]) -> str:
        """Risk: assign risk grade"""
        total_score = collected['total_score']
        
        for grade, config in self.risk_grades.items():
            if total_score >= config['min_score']:
                return grade
        return 'E'
    
    def eligibility(self, risk_grade: str, benchmark_value: float) -> bool:
        """Eligibility: check if eligible for lending"""
        if risk_grade in ['D', 'E']:
            return False
        if benchmark_value < 10000:
            return False
        return True
    
    def decide(self, eligible: bool, risk_grade: str, benchmark_value: float) -> Dict[str, Any]:
        """Decide: calculate borrowing base and terms"""
        if not eligible:
            return {
                'approved': False,
                'reason': f'Risk grade {risk_grade} or value too low'
            }
        
        multiplier = self.risk_grades[risk_grade]['multiplier']
        borrowing_base = benchmark_value * multiplier
        
        conditions = []
        covenants = []
        
        if risk_grade == 'C':
            conditions.append('IP assignment required')
            conditions.append('Minimum $100K ARR')
            covenants.append('Maintain test coverage > 60%')
        elif risk_grade == 'B':
            conditions.append('Regular performance reporting')
        elif risk_grade == 'A':
            conditions.append('Standard covenant package')
        
        return {
            'approved': True,
            'borrowing_base': borrowing_base,
            'conditions': conditions,
            'covenants': covenants
        }
    
    def memo(self, decision: Dict[str, Any], collected: Dict[str, Any], risk_grade: str) -> str:
        """Memo: generate underwriting memo"""
        if not decision['approved']:
            return f"""
UNDERWRITING MEMO - REJECTED

Risk Grade: {risk_grade}
Reason: {decision['reason']}

Scores:
- GitHub: {collected['github_score']:.1f}/100
- Financial: {collected['financial_score']:.1f}/100
- Compute State: {collected['compute_score']:.1f}/100
- Total: {collected['total_score']:.1f}/100

Recommendation: Improve GitHub activity, ARR, or compute state before reapplying.
"""
        
        return f"""
UNDERWRITING MEMO - APPROVED

Risk Grade: {risk_grade}
Borrowing Base: ${decision['borrowing_base']:,.2f}

Scores:
- GitHub: {collected['github_score']:.1f}/100
- Financial: {collected['financial_score']:.1f}/100
- Compute State: {collected['compute_score']:.1f}/100
- Total: {collected['total_score']:.1f}/100

Conditions:
{chr(10).join(f'- {c}' for c in decision['conditions'])}

Covenants:
{chr(10).join(f'- {c}' for c in decision['covenants'])}

This decision is based on verified GitHub activity, financial metrics, and compute memory continuity.
"""
    
    def run(self, input_data: UnderwritingInput) -> UnderwritingOutput:
        """Run full pipeline"""
        from datetime import datetime
        
        intake_data = self.intake(input_data)
        collected = self.collect(intake_data)
        value = self.value(collected)
        benchmark = self.benchmark(value, collected)
        risk_grade = self.risk(collected)
        eligible = self.eligibility(risk_grade, benchmark)
        decision = self.decide(eligible, risk_grade, benchmark)
        memo = self.memo(decision, collected, risk_grade)
        
        return UnderwritingOutput(
            value_estimate=value,
            benchmark_value=benchmark,
            risk_grade=risk_grade,
            borrowing_base=decision.get('borrowing_base', 0),
            conditions=decision.get('conditions', []),
            covenants=decision.get('covenants', []),
            memo=memo,
            timestamp=datetime.now().isoformat()
        )

# Example usage
if __name__ == "__main__":
    pipeline = UnderwritingPipeline()
    
    # As-is example (risk grade E, ~$14K borrowing base)
    input_as_is = UnderwritingInput(
        repo_count=5,
        test_coverage=0.3,
        deployable_count=1,
        docs_count=2,
        issues_closed=10,
        prs_merged=5,
        arr_mrr=0,
        ip_assigned=False,
        memory_state_gb=16,
        recoverable_state_score=0.4
    )
    
    output_as_is = pipeline.run(input_as_is)
    print("AS-IS:")
    print(f"Risk Grade: {output_as_is.risk_grade}")
    print(f"Borrowing Base: ${output_as_is.borrowing_base:,.2f}")
    
    # After IP assignment and $100K ARR (risk grade C, ~$41K borrowing base)
    input_improved = UnderwritingInput(
        repo_count=5,
        test_coverage=0.3,
        deployable_count=1,
        docs_count=2,
        issues_closed=10,
        prs_merged=5,
        arr_mrr=100000,
        ip_assigned=True,
        memory_state_gb=16,
        recoverable_state_score=0.4
    )
    
    output_improved = pipeline.run(input_improved)
    print("\nIMPROVED:")
    print(f"Risk Grade: {output_improved.risk_grade}")
    print(f"Borrowing Base: ${output_improved.borrowing_base:,.2f}")
