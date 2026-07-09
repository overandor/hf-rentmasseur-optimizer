#!/usr/bin/env python3
"""
Profile Intelligence System

Hourly profile intelligence that proves which presentation changes increase client intent.
Focus on business outcomes: contact clicks, bookings, revenue - not ego metrics.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any
import json

DB_PATH = Path("data/profile_intelligence.db")
DATA_DIR = Path("data")
DATA_DIR.mkdir(parents=True, exist_ok=True)


def init_database():
    """Initialize profile intelligence database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Profile metrics (hourly snapshots)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profile_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            views INTEGER,
            contact_clicks INTEGER,
            contact_rate REAL,
            visibility_score REAL,
            availability_score REAL,
            retention_score REAL,
            immortality_score REAL,
            virality_score REAL,
            evidence_hash TEXT
        )
    """)
    
    # Bio variants (A/B testing)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS bio_variants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL,
            variant_name TEXT NOT NULL,
            bio_text TEXT NOT NULL,
            created_ts TEXT NOT NULL,
            is_active BOOLEAN DEFAULT 0,
            evidence_hash TEXT
        )
    """)
    
    # Experiments (clean A/B tests)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL,
            experiment_name TEXT NOT NULL,
            control_variant_id INTEGER,
            test_variant_id INTEGER,
            start_ts TEXT NOT NULL,
            end_ts TEXT,
            status TEXT,
            hypothesis TEXT,
            created_ts TEXT
        )
    """)
    
    # Decision ledger (profile optimization decisions)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decision_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL,
            decision_type TEXT NOT NULL,
            old_value TEXT,
            new_value TEXT,
            reason TEXT,
            evidence_before TEXT,
            evidence_after TEXT,
            outcome TEXT,
            created_ts TEXT
        )
    """)
    
    # Revenue tracking (business outcomes)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS revenue_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            amount REAL,
            source TEXT,
            variant_id INTEGER,
            experiment_id INTEGER,
            created_ts TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    print("Database initialized")


def record_hourly_metrics(profile_id: str, views: int, contact_clicks: int, 
                         visibility: float, availability: float, retention: float):
    """Record hourly profile metrics."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    contact_rate = contact_clicks / views if views > 0 else 0
    
    # Calculate immortality score (profile durability)
    immortality = (visibility * 0.3 + availability * 0.3 + retention * 0.4)
    
    # Calculate virality score (attention acceleration - needs trend data)
    virality = 0.1  # Base score, will be calculated from trends
    
    evidence_hash = f"{profile_id}_{now}_{views}_{contact_clicks}"
    
    cursor.execute("""
        INSERT INTO profile_metrics
        (profile_id, timestamp, views, contact_clicks, contact_rate, 
         visibility_score, availability_score, retention_score, 
         immortality_score, virality_score, evidence_hash)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (profile_id, now, views, contact_clicks, contact_rate,
          visibility, availability, retention, immortality, virality, evidence_hash))
    
    conn.commit()
    conn.close()
    print(f"Recorded metrics for {profile_id}: views={views}, clicks={contact_clicks}, rate={contact_rate:.2%}")


def create_bio_variant(profile_id: str, variant_name: str, bio_text: str):
    """Create a bio variant for A/B testing."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    evidence_hash = f"{profile_id}_{variant_name}_{hash(bio_text)}"
    
    cursor.execute("""
        INSERT INTO bio_variants
        (profile_id, variant_name, bio_text, created_ts, is_active, evidence_hash)
        VALUES (?, ?, ?, ?, 0, ?)
    """, (profile_id, variant_name, bio_text, now, evidence_hash))
    
    conn.commit()
    conn.close()
    print(f"Created bio variant: {variant_name}")


def start_experiment(profile_id: str, experiment_name: str, control_variant: str, 
                    test_variant: str, hypothesis: str):
    """Start a clean A/B experiment."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Get variant IDs
    cursor.execute("SELECT id FROM bio_variants WHERE variant_name = ?", (control_variant,))
    control_id = cursor.fetchone()[0]
    
    cursor.execute("SELECT id FROM bio_variants WHERE variant_name = ?", (test_variant,))
    test_id = cursor.fetchone()[0]
    
    cursor.execute("""
        INSERT INTO experiments
        (profile_id, experiment_name, control_variant_id, test_variant_id, 
         start_ts, status, hypothesis, created_ts)
        VALUES (?, ?, ?, ?, ?, 'running', ?, ?)
    """, (profile_id, experiment_name, control_id, test_id, now, hypothesis, now))
    
    conn.commit()
    conn.close()
    print(f"Started experiment: {experiment_name}")


def record_decision(profile_id: str, decision_type: str, old_value: str, new_value: str,
                  reason: str, evidence_before: str, evidence_after: str):
    """Record a profile optimization decision."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    
    cursor.execute("""
        INSERT INTO decision_ledger
        (profile_id, decision_type, old_value, new_value, reason, 
         evidence_before, evidence_after, created_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (profile_id, decision_type, old_value, new_value, reason, 
          evidence_before, evidence_after, now))
    
    conn.commit()
    conn.close()
    print(f"Recorded decision: {decision_type}")


def record_revenue(profile_id: str, event_type: str, amount: float, source: str,
                  variant_id: int = None, experiment_id: int = None):
    """Record a revenue event."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    
    cursor.execute("""
        INSERT INTO revenue_events
        (profile_id, event_type, amount, source, variant_id, experiment_id, created_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (profile_id, event_type, amount, source, variant_id, experiment_id, now))
    
    conn.commit()
    conn.close()
    print(f"Recorded revenue: {event_type} ${amount}")


def get_experiment_results(experiment_id: int) -> Dict[str, Any]:
    """Get results for an experiment."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get experiment info
    cursor.execute("SELECT * FROM experiments WHERE id = ?", (experiment_id,))
    experiment = cursor.fetchone()
    
    # Get metrics during experiment period
    cursor.execute("""
        SELECT AVG(contact_rate) as avg_rate, 
               SUM(contact_clicks) as total_clicks,
               COUNT(*) as snapshots
        FROM profile_metrics
        WHERE timestamp >= ? AND timestamp <= ?
    """, (experiment[5], experiment[6] or datetime.now(timezone.utc).isoformat()))
    
    results = cursor.fetchone()
    conn.close()
    
    return {
        "experiment": experiment,
        "avg_contact_rate": results[0],
        "total_clicks": results[1],
        "snapshots": results[2]
    }


if __name__ == "__main__":
    init_database()
    print("Profile Intelligence System initialized")
    print("Focus: business outcomes, not ego metrics")
