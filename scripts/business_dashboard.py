#!/usr/bin/env python3
"""
Business Outcome Dashboard

Focus on actual business metrics: contact rate, bookings, revenue.
No ego metrics. No "immortality" or "virality" language.
Just numbers that matter: did this change bring more booked clients?
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

DB_PATH = Path("data/profile_intelligence.db")


def get_business_summary(profile_id: str = None) -> Dict[str, Any]:
    """Get business outcome summary."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if profile_id:
        cursor.execute("SELECT profile_id FROM profile_metrics WHERE profile_id = ? LIMIT 1", (profile_id,))
        if not cursor.fetchone():
            conn.close()
            return {"error": "Profile not found"}
        
        cursor.execute("SELECT profile_id FROM profile_metrics WHERE profile_id = ?", (profile_id,))
    else:
        cursor.execute("SELECT DISTINCT profile_id FROM profile_metrics")
    
    profiles = [row[0] for row in cursor.fetchall()]
    
    summary = {
        "profiles_analyzed": len(profiles),
        "total_snapshots": 0,
        "total_views": 0,
        "total_contact_clicks": 0,
        "avg_contact_rate": 0,
        "total_revenue": 0,
        "experiments_run": 0,
        "decisions_made": 0,
        "profile_breakdown": []
    }
    
    for profile in profiles:
        cursor.execute("""
            SELECT 
                COUNT(*) as snapshots,
                SUM(views) as views,
                SUM(contact_clicks) as clicks,
                AVG(contact_rate) as rate
            FROM profile_metrics
            WHERE profile_id = ?
        """, (profile,))
        
        metrics = cursor.fetchone()
        snapshots, views, clicks, rate = metrics
        
        summary["total_snapshots"] += snapshots or 0
        summary["total_views"] += views or 0
        summary["total_contact_clicks"] += clicks or 0
        
        # Revenue for this profile
        cursor.execute("""
            SELECT COALESCE(SUM(amount), 0) 
            FROM revenue_events 
            WHERE profile_id = ?
        """, (profile,))
        revenue = cursor.fetchone()[0]
        summary["total_revenue"] += revenue
        
        summary["profile_breakdown"].append({
            "profile_id": profile,
            "snapshots": snapshots or 0,
            "views": views or 0,
            "clicks": clicks or 0,
            "contact_rate": rate or 0,
            "revenue": revenue
        })
    
    # Calculate overall contact rate
    if summary["total_views"] > 0:
        summary["avg_contact_rate"] = summary["total_contact_clicks"] / summary["total_views"]
    
    # Count experiments
    cursor.execute("SELECT COUNT(*) FROM experiments")
    summary["experiments_run"] = cursor.fetchone()[0]
    
    # Count decisions
    cursor.execute("SELECT COUNT(*) FROM decision_ledger")
    summary["decisions_made"] = cursor.fetchone()[0]
    
    conn.close()
    return summary


def get_experiment_outcomes() -> List[Dict[str, Any]]:
    """Get experiment outcomes."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            e.id,
            e.profile_id,
            e.experiment_name,
            e.hypothesis,
            e.status,
            e.start_ts,
            e.end_ts,
            COUNT(DISTINCT pm.id) as snapshots,
            AVG(pm.contact_rate) as avg_contact_rate,
            SUM(pm.contact_clicks) as total_clicks
        FROM experiments e
        LEFT JOIN profile_metrics pm ON pm.profile_id = e.profile_id
            AND pm.timestamp >= e.start_ts
            AND (pm.timestamp <= e.end_ts OR e.end_ts IS NULL)
        GROUP BY e.id
        ORDER BY e.id DESC
    """)
    
    experiments = []
    for row in cursor.fetchall():
        experiments.append({
            "id": row[0],
            "profile_id": row[1],
            "name": row[2],
            "hypothesis": row[3],
            "status": row[4],
            "start": row[5],
            "end": row[6],
            "snapshots": row[7],
            "contact_rate": row[8] or 0,
            "total_clicks": row[9] or 0
        })
    
    conn.close()
    return experiments


def get_recent_decisions(limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent decisions."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            profile_id,
            decision_type,
            old_value,
            new_value,
            reason,
            outcome,
            created_ts
        FROM decision_ledger
        ORDER BY id DESC
        LIMIT ?
    """, (limit,))
    
    decisions = []
    for row in cursor.fetchall():
        decisions.append({
            "profile_id": row[0],
            "type": row[1],
            "old": row[2],
            "new": row[3],
            "reason": row[4],
            "outcome": row[5],
            "timestamp": row[6]
        })
    
    conn.close()
    return decisions


def print_dashboard():
    """Print business outcome dashboard."""
    print("=" * 60)
    print("BUSINESS OUTCOME DASHBOARD")
    print("=" * 60)
    
    summary = get_business_summary()
    
    print(f"\nProfiles Analyzed: {summary['profiles_analyzed']}")
    print(f"Total Snapshots: {summary['total_snapshots']}")
    print(f"Total Views: {summary['total_views']}")
    print(f"Total Contact Clicks: {summary['total_contact_clicks']}")
    print(f"Average Contact Rate: {summary['avg_contact_rate']:.2%}")
    print(f"Total Revenue: ${summary['total_revenue']:.2f}")
    print(f"Experiments Run: {summary['experiments_run']}")
    print(f"Decisions Made: {summary['decisions_made']}")
    
    if summary['profile_breakdown']:
        print("\n--- Profile Breakdown ---")
        for profile in summary['profile_breakdown']:
            print(f"\n{profile['profile_id']}:")
            print(f"  Views: {profile['views']}")
            print(f"  Clicks: {profile['clicks']}")
            print(f"  Contact Rate: {profile['contact_rate']:.2%}")
            print(f"  Revenue: ${profile['revenue']:.2f}")
    
    experiments = get_experiment_outcomes()
    if experiments:
        print("\n--- Experiment Outcomes ---")
        for exp in experiments:
            print(f"\n{exp['name']} (ID: {exp['id']}):")
            print(f"  Hypothesis: {exp['hypothesis']}")
            print(f"  Status: {exp['status']}")
            print(f"  Contact Rate: {exp['contact_rate']:.2%}")
            print(f"  Total Clicks: {exp['total_clicks']}")
            print(f"  Snapshots: {exp['snapshots']}")
    
    decisions = get_recent_decisions()
    if decisions:
        print("\n--- Recent Decisions ---")
        for dec in decisions:
            print(f"\n{dec['timestamp']}:")
            print(f"  Profile: {dec['profile_id']}")
            print(f"  Type: {dec['type']}")
            print(f"  Reason: {dec['reason']}")
            print(f"  Outcome: {dec['outcome'] or 'Pending'}")
    
    print("\n" + "=" * 60)


if __name__ == "__main__":
    print_dashboard()
