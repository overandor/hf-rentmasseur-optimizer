"""
Layer 4: Action
Recommends hardening, blocks fake production claims, generates tasks.
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from layer_crawler_etl.layer3_scoring.scorer import ScoreResult, RiskLevel


class ActionType(Enum):
    HARDEN = "harden"
    BLOCK = "block"
    TASK = "task"
    WARN = "warn"
    APPROVE = "approve"


class Priority(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class Action:
    """Recommended action based on scoring."""
    action_type: ActionType
    priority: Priority
    title: str
    description: str
    source_id: str
    metadata: Dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict:
        return {
            "action_type": self.action_type.value,
            "priority": self.priority.value,
            "title": self.title,
            "description": self.description,
            "source_id": self.source_id,
            "metadata": self.metadata,
            "timestamp": self.timestamp
        }


@dataclass
class ActionResult:
    """Result of action execution."""
    actions_generated: List[Action] = field(default_factory=list)
    blocked_claims: List[str] = field(default_factory=list)
    hardening_recommendations: List[Dict] = field(default_factory=list)
    tasks_generated: List[Dict] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    
    def to_dict(self) -> Dict:
        return {
            "actions_generated": [a.to_dict() for a in self.actions_generated],
            "blocked_claims": self.blocked_claims,
            "hardening_recommendations": self.hardening_recommendations,
            "tasks_generated": self.tasks_generated,
            "timestamp": self.timestamp
        }


class ActionEngine:
    """Generates actions based on scoring results."""
    
    # Thresholds for different actions
    BLOCK_THRESHOLDS = {
        "secrets_exposed": 1,  # Block if any secrets exposed
        "ip_risk": 80,  # Block if IP risk > 80
        "runtime_risk": 80  # Block if runtime risk > 80
    }
    
    HARDEN_THRESHOLDS = {
        "prod_score": 50,  # Recommend hardening if prod score < 50
        "harden_rank": 40,  # Recommend hardening if HardenRank > 40
        "ip_risk": 50,  # Recommend hardening if IP risk > 50
        "runtime_risk": 50  # Recommend hardening if runtime risk > 50
    }
    
    def __init__(self):
        pass
    
    def generate_actions(self, score_result: ScoreResult, record_data: Dict) -> ActionResult:
        """Generate actions based on scoring result."""
        result = ActionResult()
        
        # Check for blocking conditions
        self._check_block_conditions(score_result, record_data, result)
        
        # Generate hardening recommendations
        self._generate_hardening_recommendations(score_result, record_data, result)
        
        # Generate tasks
        self._generate_tasks(score_result, record_data, result)
        
        # Generate warnings
        self._generate_warnings(score_result, record_data, result)
        
        return result
    
    def _check_block_conditions(self, score_result: ScoreResult, record_data: Dict, result: ActionResult):
        """Check if production claims should be blocked."""
        signals = score_result.signals
        
        # Block if secrets exposed
        if signals.get("secrets_exposed", 0) >= self.BLOCK_THRESHOLDS["secrets_exposed"]:
            result.blocked_claims.append(f"Source {score_result.source_id}: Secrets exposed")
            result.actions_generated.append(Action(
                action_type=ActionType.BLOCK,
                priority=Priority.CRITICAL,
                title="Block Production Claim",
                description=f"Secrets exposed in source {score_result.source_id}. Cannot verify production readiness.",
                source_id=score_result.source_id,
                metadata={"reason": "secrets_exposed", "count": signals.get("secrets_exposed", 0)}
            ))
        
        # Block if IP risk too high
        if score_result.ip_risk >= self.BLOCK_THRESHOLDS["ip_risk"]:
            result.blocked_claims.append(f"Source {score_result.source_id}: IP risk too high")
            result.actions_generated.append(Action(
                action_type=ActionType.BLOCK,
                priority=Priority.CRITICAL,
                title="Block Production Claim",
                description=f"IP risk ({score_result.ip_risk}) exceeds threshold. License conflicts detected.",
                source_id=score_result.source_id,
                metadata={"reason": "ip_risk", "score": score_result.ip_risk}
            ))
        
        # Block if runtime risk too high
        if score_result.runtime_risk >= self.BLOCK_THRESHOLDS["runtime_risk"]:
            result.blocked_claims.append(f"Source {score_result.source_id}: Runtime risk too high")
            result.actions_generated.append(Action(
                action_type=ActionType.BLOCK,
                priority=Priority.CRITICAL,
                title="Block Production Claim",
                description=f"Runtime risk ({score_result.runtime_risk}) exceeds threshold. Critical errors detected.",
                source_id=score_result.source_id,
                metadata={"reason": "runtime_risk", "score": score_result.runtime_risk}
            ))
    
    def _generate_hardening_recommendations(self, score_result: ScoreResult, record_data: Dict, result: ActionResult):
        """Generate hardening recommendations."""
        signals = score_result.signals
        data = record_data
        
        # Secrets exposed
        if signals.get("secrets_exposed", 0) > 0:
            result.hardening_recommendations.append({
                "source_id": score_result.source_id,
                "priority": "critical",
                "issue": "secrets_exposed",
                "recommendation": "Remove exposed secrets and use environment variables",
                "details": f"Found {signals.get('secrets_exposed')} potential secrets"
            })
            result.actions_generated.append(Action(
                action_type=ActionType.HARDEN,
                priority=Priority.CRITICAL,
                title="Remove Exposed Secrets",
                description="Remove exposed secrets and use environment variables",
                source_id=score_result.source_id,
                metadata={"issue": "secrets_exposed", "count": signals.get("secrets_exposed", 0)}
            ))
        
        # No tests
        if data.get("test_file_count", 0) == 0:
            result.hardening_recommendations.append({
                "source_id": score_result.source_id,
                "priority": "high",
                "issue": "no_tests",
                "recommendation": "Add test coverage to verify functionality",
                "details": "No test files found"
            })
            result.actions_generated.append(Action(
                action_type=ActionType.HARDEN,
                priority=Priority.HIGH,
                title="Add Test Coverage",
                description="Add test coverage to verify functionality",
                source_id=score_result.source_id,
                metadata={"issue": "no_tests"}
            ))
        
        # No CI/CD
        if not data.get("has_ci_cd"):
            result.hardening_recommendations.append({
                "source_id": score_result.source_id,
                "priority": "high",
                "issue": "no_ci_cd",
                "recommendation": "Configure CI/CD pipeline for automated testing and deployment",
                "details": "No CI/CD configuration found"
            })
            result.actions_generated.append(Action(
                action_type=ActionType.HARDEN,
                priority=Priority.HIGH,
                title="Configure CI/CD",
                description="Configure CI/CD pipeline for automated testing and deployment",
                source_id=score_result.source_id,
                metadata={"issue": "no_ci_cd"}
            ))
        
        # License conflicts
        if data.get("conflicts"):
            result.hardening_recommendations.append({
                "source_id": score_result.source_id,
                "priority": "high",
                "issue": "license_conflicts",
                "recommendation": "Review and resolve license conflicts",
                "details": f"Found {len(data.get('conflicts', []))} license conflicts"
            })
            result.actions_generated.append(Action(
                action_type=ActionType.HARDEN,
                priority=Priority.HIGH,
                title="Resolve License Conflicts",
                description="Review and resolve license conflicts",
                source_id=score_result.source_id,
                metadata={"issue": "license_conflicts", "count": len(data.get("conflicts", []))}
            ))
        
        # Console errors
        if signals.get("console_errors", 0) > 0:
            result.hardening_recommendations.append({
                "source_id": score_result.source_id,
                "priority": "medium",
                "issue": "console_errors",
                "recommendation": "Fix console errors in production",
                "details": f"Found {signals.get('console_errors')} console errors"
            })
            result.actions_generated.append(Action(
                action_type=ActionType.HARDEN,
                priority=Priority.MEDIUM,
                title="Fix Console Errors",
                description="Fix console errors in production",
                source_id=score_result.source_id,
                metadata={"issue": "console_errors", "count": signals.get("console_errors", 0)}
            ))
    
    def _generate_tasks(self, score_result: ScoreResult, record_data: Dict, result: ActionResult):
        """Generate actionable tasks."""
        tasks = []
        
        # Task: Remove secrets
        if score_result.signals.get("secrets_exposed", 0) > 0:
            tasks.append({
                "title": "Remove exposed secrets",
                "description": "Scan codebase for secrets and replace with environment variables",
                "priority": "critical",
                "estimated_effort": "2-4 hours",
                "source_id": score_result.source_id
            })
        
        # Task: Add tests
        if record_data.get("test_file_count", 0) == 0:
            tasks.append({
                "title": "Add test coverage",
                "description": "Write unit tests for critical functionality",
                "priority": "high",
                "estimated_effort": "1-2 days",
                "source_id": score_result.source_id
            })
        
        # Task: Setup CI/CD
        if not record_data.get("has_ci_cd"):
            tasks.append({
                "title": "Setup CI/CD pipeline",
                "description": "Configure GitHub Actions or similar for automated testing",
                "priority": "high",
                "estimated_effort": "4-8 hours",
                "source_id": score_result.source_id
            })
        
        # Task: Fix license issues
        if record_data.get("conflicts"):
            tasks.append({
                "title": "Resolve license conflicts",
                "description": "Review dependency licenses and replace conflicting ones",
                "priority": "high",
                "estimated_effort": "2-4 hours",
                "source_id": score_result.source_id
            })
        
        result.tasks_generated = tasks
        
        for task in tasks:
            result.actions_generated.append(Action(
                action_type=ActionType.TASK,
                priority=Priority[task["priority"].upper()],
                title=task["title"],
                description=task["description"],
                source_id=score_result.source_id,
                metadata=task
            ))
    
    def _generate_warnings(self, score_result: ScoreResult, record_data: Dict, result: ActionResult):
        """Generate warnings for non-critical issues."""
        if score_result.prod_score < 70:
            result.actions_generated.append(Action(
                action_type=ActionType.WARN,
                priority=Priority.MEDIUM,
                title="Low Production Score",
                description=f"Production score ({score_result.prod_score}) is below recommended threshold (70)",
                source_id=score_result.source_id,
                metadata={"prod_score": score_result.prod_score}
            ))
        
        if score_result.harden_rank > 30:
            result.actions_generated.append(Action(
                action_type=ActionType.WARN,
                priority=Priority.MEDIUM,
                title="Hardening Recommended",
                description=f"HardenRank ({score_result.harden_rank}) indicates significant hardening needed",
                source_id=score_result.source_id,
                metadata={"harden_rank": score_result.harden_rank}
            ))
    
    def batch_generate_actions(self, score_results: List[ScoreResult], records_data: List[Dict]) -> ActionResult:
        """Generate actions for multiple score results."""
        combined_result = ActionResult()
        
        for score_result, record_data in zip(score_results, records_data):
            result = self.generate_actions(score_result, record_data)
            combined_result.actions_generated.extend(result.actions_generated)
            combined_result.blocked_claims.extend(result.blocked_claims)
            combined_result.hardening_recommendations.extend(result.hardening_recommendations)
            combined_result.tasks_generated.extend(result.tasks_generated)
        
        return combined_result
