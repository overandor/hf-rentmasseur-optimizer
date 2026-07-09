"""
Layer 3: Scoring
Calculates evidence scores, reality penalties, production scores, 
HardenRank, IP risk, and runtime risk.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from layer_crawler_etl.layer2_etl.transformer import NormalizedRecord


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ScoreResult:
    """Scoring result for a normalized record."""
    source_id: str
    record_type: str
    evidence_score: float = 0.0
    reality_penalty: float = 0.0
    prod_score: float = 0.0
    harden_rank: float = 0.0
    ip_risk: float = 0.0
    runtime_risk: float = 0.0
    overall_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.MEDIUM
    signals: Dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict:
        return {
            "source_id": self.source_id,
            "record_type": self.record_type,
            "evidence_score": self.evidence_score,
            "reality_penalty": self.reality_penalty,
            "prod_score": self.prod_score,
            "harden_rank": self.harden_rank,
            "ip_risk": self.ip_risk,
            "runtime_risk": self.runtime_risk,
            "overall_score": self.overall_score,
            "risk_level": self.risk_level.value,
            "signals": self.signals,
            "timestamp": self.timestamp
        }


class Scorer:
    """Calculates various scores for normalized records."""
    
    # Weight configuration
    EVIDENCE_WEIGHTS = {
        "build_verified": 25,
        "tests_verified": 20,
        "runtime_verified": 25,
        "docs_exist": 10,
        "ci_configured": 10,
        "coverage_configured": 10
    }
    
    REALITY_PENALTY_FACTORS = {
        "console_errors": 10,
        "failed_requests": 5,
        "secrets_exposed": 50,
        "license_conflicts": 20,
        "no_tests": 15,
        "no_ci": 10
    }
    
    def __init__(self):
        pass
    
    def score(self, record: NormalizedRecord) -> ScoreResult:
        """Calculate all scores for a normalized record."""
        result = ScoreResult(
            source_id=record.source_id,
            record_type=record.record_type,
            signals=record.signals
        )
        
        # Calculate individual scores
        result.evidence_score = self._calculate_evidence_score(record)
        result.reality_penalty = self._calculate_reality_penalty(record)
        result.prod_score = self._calculate_prod_score(result)
        result.harden_rank = self._calculate_harden_rank(record)
        result.ip_risk = self._calculate_ip_risk(record)
        result.runtime_risk = self._calculate_runtime_risk(record)
        
        # Calculate overall score
        result.overall_score = self._calculate_overall_score(result)
        
        # Determine risk level
        result.risk_level = self._determine_risk_level(result)
        
        return result
    
    def _calculate_evidence_score(self, record: NormalizedRecord) -> float:
        """Calculate evidence score (0-100)."""
        score = 0.0
        signals = record.signals
        data = record.data
        
        # Build verification
        if signals.get("build_verified"):
            score += self.EVIDENCE_WEIGHTS["build_verified"]
        
        # Test verification
        if signals.get("tests_verified") or data.get("test_file_count", 0) > 0:
            score += self.EVIDENCE_WEIGHTS["tests_verified"]
        
        # Runtime verification
        if signals.get("runtime_verified"):
            score += self.EVIDENCE_WEIGHTS["runtime_verified"]
        
        # Documentation
        if data.get("has_docs"):
            score += self.EVIDENCE_WEIGHTS["docs_exist"]
        
        # CI/CD
        if data.get("has_ci_cd"):
            score += self.EVIDENCE_WEIGHTS["ci_configured"]
        
        # Coverage
        if data.get("coverage_configured"):
            score += self.EVIDENCE_WEIGHTS["coverage_configured"]
        
        return min(score, 100.0)
    
    def _calculate_reality_penalty(self, record: NormalizedRecord) -> float:
        """Calculate reality penalty (0-100, higher is worse)."""
        penalty = 0.0
        signals = record.signals
        data = record.data
        
        # Console errors
        penalty += signals.get("console_errors", 0) * self.REALITY_PENALTY_FACTORS["console_errors"]
        
        # Failed requests
        penalty += signals.get("failed_requests", 0) * self.REALITY_PENALTY_FACTORS["failed_requests"]
        
        # Secrets exposed
        penalty += signals.get("secrets_exposed", 0) * self.REALITY_PENALTY_FACTORS["secrets_exposed"]
        
        # License conflicts
        penalty += data.get("license_risks", len(data.get("license_risks", []))) * self.REALITY_PENALTY_FACTORS["license_conflicts"]
        
        # No tests
        if data.get("test_file_count", 0) == 0:
            penalty += self.REALITY_PENALTY_FACTORS["no_tests"]
        
        # No CI
        if not data.get("has_ci_cd"):
            penalty += self.REALITY_PENALTY_FACTORS["no_ci"]
        
        return min(penalty, 100.0)
    
    def _calculate_prod_score(self, result: ScoreResult) -> float:
        """Calculate production score (evidence - penalty)."""
        return max(0.0, result.evidence_score - result.reality_penalty)
    
    def _calculate_harden_rank(self, record: NormalizedRecord) -> float:
        """Calculate HardenRank (0-100, measures hardening needed)."""
        # HardenRank is inverse of production readiness
        # Higher HardenRank = more hardening needed
        rank = 0.0
        signals = record.signals
        data = record.data
        
        # Security issues
        if signals.get("secrets_exposed", 0) > 0:
            rank += 30
        
        # License issues
        if data.get("license_conflicts"):
            rank += 20
        
        # No tests
        if data.get("test_file_count", 0) == 0:
            rank += 20
        
        # No CI
        if not data.get("has_ci_cd"):
            rank += 15
        
        # Runtime errors
        if signals.get("console_errors", 0) > 0:
            rank += 15
        
        return min(rank, 100.0)
    
    def _calculate_ip_risk(self, record: NormalizedRecord) -> float:
        """Calculate IP risk score (0-100, higher is worse)."""
        risk = 0.0
        data = record.data
        
        # License type risk
        license_type = data.get("license_type", "unknown")
        if license_type == "copyleft":
            risk += 30
        elif license_type == "proprietary":
            risk += 50
        elif license_type == "unknown":
            risk += 20
        
        # License conflicts
        risk += len(data.get("conflicts", [])) * 15
        
        # Compatibility score inverse
        compatibility = data.get("compatibility_score", 100)
        risk += (100 - compatibility) * 0.5
        
        return min(risk, 100.0)
    
    def _calculate_runtime_risk(self, record: NormalizedRecord) -> float:
        """Calculate runtime risk score (0-100, higher is worse)."""
        risk = 0.0
        signals = record.signals
        data = record.data
        
        # Console errors
        risk += signals.get("console_errors", 0) * 15
        
        # Failed requests
        risk += signals.get("failed_requests", 0) * 10
        
        # Not runtime verified
        if not signals.get("runtime_verified"):
            risk += 25
        
        # Slow page load
        page_load = data.get("page_load_time_ms", 0)
        if page_load > 3000:
            risk += 20
        elif page_load > 1000:
            risk += 10
        
        return min(risk, 100.0)
    
    def _calculate_overall_score(self, result: ScoreResult) -> float:
        """Calculate overall score (0-100)."""
        # Weighted combination of scores
        weights = {
            "prod_score": 0.4,
            "harden_rank": -0.2,  # Negative because higher HardenRank is worse
            "ip_risk": -0.2,  # Negative because higher risk is worse
            "runtime_risk": -0.2  # Negative because higher risk is worse
        }
        
        overall = (
            weights["prod_score"] * result.prod_score +
            weights["harden_rank"] * (100 - result.harden_rank) +
            weights["ip_risk"] * (100 - result.ip_risk) +
            weights["runtime_risk"] * (100 - result.runtime_risk)
        )
        
        return max(0.0, min(100.0, overall))
    
    def _determine_risk_level(self, result: ScoreResult) -> RiskLevel:
        """Determine risk level from scores."""
        if result.ip_risk > 70 or result.runtime_risk > 70:
            return RiskLevel.CRITICAL
        elif result.ip_risk > 50 or result.runtime_risk > 50 or result.harden_rank > 50:
            return RiskLevel.HIGH
        elif result.overall_score < 50:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def batch_score(self, records: List[NormalizedRecord]) -> List[ScoreResult]:
        """Score multiple records."""
        return [self.score(r) for r in records]
