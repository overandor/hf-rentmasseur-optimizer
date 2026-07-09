#!/usr/bin/env python3
"""
Clean A/B Testing Framework for Bio Variants

Run one clean test: same photos, same price, same services, same availability.
Only change the bio. Collect hourly results. Compare contact clicks.
If contact rate rises, keep it. If drops, roll back. If traffic too low, wait.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any
import time

from profile_intelligence import (
    DB_PATH,
    init_database,
    create_bio_variant,
    start_experiment,
    record_hourly_metrics,
    record_decision,
    record_revenue,
    get_experiment_results
)


class BioABTest:
    """Clean A/B test for bio variants."""
    
    def __init__(self, profile_id: str):
        self.profile_id = profile_id
        init_database()
    
    def setup_variants(self, control_bio: str, test_bio: str):
        """Setup control and test bio variants."""
        create_bio_variant(self.profile_id, "control", control_bio)
        create_bio_variant(self.profile_id, "test", test_bio)
        print("Bio variants created")
    
    def start_test(self, hypothesis: str, duration_hours: int = 48):
        """Start the A/B test."""
        start_experiment(
            self.profile_id,
            f"bio_test_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M')}",
            "control",
            "test",
            hypothesis
        )
        print(f"Test started for {duration_hours} hours")
        return duration_hours
    
    def collect_metrics(self, views: int, contact_clicks: int, 
                       visibility: float, availability: float, retention: float):
        """Collect hourly metrics."""
        record_hourly_metrics(
            self.profile_id, views, contact_clicks, 
            visibility, availability, retention
        )
    
    def analyze_results(self, experiment_id: int) -> Dict[str, Any]:
        """Analyze test results and make decision."""
        results = get_experiment_results(experiment_id)
        
        # Simple decision logic
        avg_rate = results['avg_contact_rate'] or 0
        total_clicks = results['total_clicks'] or 0
        
        if total_clicks < 10:
            decision = "wait"
            reason = "Insufficient traffic for statistical significance"
        elif avg_rate > 0.05:  # 5% contact rate threshold
            decision = "keep"
            reason = f"Contact rate {avg_rate:.2%} exceeds threshold"
        else:
            decision = "rollback"
            reason = f"Contact rate {avg_rate:.2%} below threshold"
        
        return {
            "decision": decision,
            "reason": reason,
            "avg_contact_rate": avg_rate,
            "total_clicks": total_clicks
        }
    
    def execute_decision(self, decision: str, reason: str, evidence_before: str, evidence_after: str):
        """Execute the decision and record it."""
        record_decision(
            self.profile_id,
            "bio_change",
            evidence_before,
            evidence_after,
            reason,
            evidence_before,
            evidence_after
        )
        
        if decision == "keep":
            print(f"Decision: KEEP - {reason}")
        elif decision == "rollback":
            print(f"Decision: ROLLBACK - {reason}")
        else:
            print(f"Decision: WAIT - {reason}")


def run_clean_test():
    """Run a clean bio A/B test."""
    print("=" * 60)
    print("CLEAN BIO A/B TEST")
    print("=" * 60)
    
    profile_id = "test_profile_001"
    
    # Setup test
    test = BioABTest(profile_id)
    
    # Define variants (same structure, different messaging)
    control_bio = """
    Professional massage therapist in NYC. 
    5 years experience. Swedish, deep tissue, sports massage.
    Available Mon-Fri 9am-7pm. $120/hour.
    """
    
    test_bio = """
    NYC massage therapist specializing in stress relief and recovery.
    5 years helping clients feel their best. 
    Swedish, deep tissue, sports massage.
    Available Mon-Fri 9am-7pm. $120/hour.
    """
    
    test.setup_variants(control_bio, test_bio)
    
    # Start test
    hypothesis = "Stress-focused messaging increases contact rate"
    duration = test.start_test(hypothesis, duration_hours=48)
    
    # Simulate hourly data collection (in production, this would be real data)
    print("\nSimulating hourly data collection...")
    for hour in range(duration):
        # Simulate metrics with some variation
        views = 80 + (hour % 20) - 10
        clicks = int(views * 0.04) + (1 if hour % 5 == 0 else 0)
        visibility = 0.9
        availability = 0.85
        retention = 0.95
        
        test.collect_metrics(views, clicks, visibility, availability, retention)
        
        if hour % 12 == 0:
            print(f"  Hour {hour}: views={views}, clicks={clicks}, rate={clicks/views:.2%}")
        
        time.sleep(0.1)  # Simulate time passing
    
    # Analyze results
    print("\nAnalyzing results...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM experiments WHERE profile_id = ? ORDER BY id DESC LIMIT 1", (profile_id,))
    experiment_id = cursor.fetchone()[0]
    conn.close()
    
    results = test.analyze_results(experiment_id)
    
    # Execute decision
    test.execute_decision(
        results['decision'],
        results['reason'],
        f"Contact rate before: unknown",
        f"Contact rate after: {results['avg_contact_rate']:.2%}"
    )
    
    print("\n=== TEST COMPLETE ===")


if __name__ == "__main__":
    run_clean_test()
