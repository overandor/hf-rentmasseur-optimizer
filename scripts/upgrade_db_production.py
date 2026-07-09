#!/usr/bin/env python3
"""
Database Schema Upgrade to Production-Grade Client Intelligence System

Upgrades rm_cic.db with production tables for evidence tracking, 
review extraction, compliance gate, and decision ledger.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from rm_cic_exact_spec import DB_PATH, DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)


def upgrade_database_schema():
    """Upgrade database to production-grade schema."""
    print("=" * 60)
    print("DATABASE SCHEMA UPGRADE TO PRODUCTION-GRADE")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Upgrade profile_visits table with additional columns
    print("\n1. Upgrading profile_visits table...")
    try:
        cursor.execute("ALTER TABLE profile_visits ADD COLUMN h1 TEXT")
        print("   Added h1 column")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e):
            print("   h1 column already exists")
        else:
            print(f"   Error adding h1: {e}")
    
    try:
        cursor.execute("ALTER TABLE profile_visits ADD COLUMN meta_description TEXT")
        print("   Added meta_description column")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e):
            print("   meta_description column already exists")
        else:
            print(f"   Error adding meta_description: {e}")
    
    try:
        cursor.execute("ALTER TABLE profile_visits ADD COLUMN extracted_json TEXT")
        print("   Added extracted_json column")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e):
            print("   extracted_json column already exists")
        else:
            print(f"   Error adding extracted_json: {e}")
    
    try:
        cursor.execute("ALTER TABLE profile_visits ADD COLUMN evidence_hash TEXT")
        print("   Added evidence_hash column")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e):
            print("   evidence_hash column already exists")
        else:
            print(f"   Error adding evidence_hash: {e}")
    
    # 2. Create client_candidates table
    print("\n2. Creating client_candidates table...")
    cursor.execute("DROP TABLE IF EXISTS client_candidates")
    cursor.execute("""
        CREATE TABLE client_candidates (
            username TEXT PRIMARY KEY,
            url TEXT,
            city TEXT,
            label TEXT,
            client_score REAL,
            provider_score REAL,
            net_score REAL,
            lead_value REAL,
            confidence REAL,
            evidence_title TEXT,
            evidence_excerpt TEXT,
            reasons_json TEXT,
            review_status TEXT,
            created_ts TEXT,
            updated_ts TEXT
        )
    """)
    print("   Created client_candidates table")
    
    # 3. Create suppression_list table
    print("\n3. Creating suppression_list table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppression_list (
            username TEXT PRIMARY KEY,
            reason TEXT,
            created_ts TEXT
        )
    """)
    print("   Created suppression_list table")
    
    # 4. Create compliance_events table
    print("\n4. Creating compliance_events table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compliance_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            event_type TEXT,
            detail TEXT,
            created_ts TEXT
        )
    """)
    print("   Created compliance_events table")
    
    # 5. Create classification_evidence table
    print("\n5. Creating classification_evidence table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS classification_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            evidence_type TEXT,
            evidence_text TEXT,
            score_delta REAL,
            source_table TEXT,
            created_ts TEXT
        )
    """)
    print("   Created classification_evidence table")
    
    # 6. Create decision_ledger table
    print("\n6. Creating decision_ledger table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decision_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            old_label TEXT,
            new_label TEXT,
            old_score REAL,
            new_score REAL,
            reason TEXT,
            created_ts TEXT
        )
    """)
    print("   Created decision_ledger table")
    
    # 7. Create reviews table
    print("\n7. Creating reviews table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            provider_username TEXT,
            reviewer_name TEXT,
            reviewer_profile_url TEXT,
            reviewer_location TEXT,
            review_text TEXT,
            rating REAL,
            review_date TEXT,
            extracted_ts TEXT,
            evidence_hash TEXT
        )
    """)
    print("   Created reviews table")
    
    # 8. Create reviewer_clients table
    print("\n8. Creating reviewer_clients table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reviewer_clients (
            reviewer_key TEXT PRIMARY KEY,
            reviewer_name TEXT,
            reviewer_profile_url TEXT,
            inferred_city TEXT,
            review_count INTEGER,
            provider_count INTEGER,
            last_review_date TEXT,
            client_confidence REAL,
            lead_value REAL,
            status TEXT
        )
    """)
    print("   Created reviewer_clients table")
    
    # 9. Create indexes for performance
    print("\n9. Creating indexes...")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_profile_visits_username ON profile_visits(username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_provider ON reviews(provider_username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reviews_reviewer ON reviews(reviewer_name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_classification_evidence_username ON classification_evidence(username)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_decision_ledger_username ON decision_ledger(username)")
    print("   Created indexes")
    
    # 10. Populate suppression_list with existing provider_confirmed
    print("\n10. Populating suppression_list with provider_confirmed...")
    cursor.execute("""
        INSERT OR IGNORE INTO suppression_list (username, reason, created_ts)
        SELECT username, 'provider_confirmed from initial classification', ?
        FROM profile_classifications
        WHERE label = 'provider_confirmed'
    """, (datetime.now(timezone.utc).isoformat(),))
    suppressed = cursor.rowcount
    print(f"   Added {suppressed} providers to suppression_list")
    
    # 11. Populate client_candidates with existing client_confirmed
    print("\n11. Populating client_candidates with client_confirmed...")
    cursor.execute("""
        INSERT OR REPLACE INTO client_candidates 
        (username, url, city, label, client_score, provider_score, net_score, 
         lead_value, confidence, evidence_title, evidence_excerpt, reasons_json, 
         review_status, created_ts, updated_ts)
        SELECT 
            p.username, p.url, p.city, c.label, c.client_score, c.provider_score, 
            c.net_client_score, c.lead_value, c.confidence, 
            v.title as evidence_title, v.body_text as evidence_excerpt, 
            c.reasons_json, 'pending_review', ?, ?
        FROM profile_classifications c
        JOIN profiles p ON c.username = p.username
        LEFT JOIN profile_visits v ON c.username = v.username
        WHERE c.label = 'client_confirmed'
    """, (datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
    candidates = cursor.rowcount
    print(f"   Added {candidates} clients to client_candidates")
    
    conn.commit()
    conn.close()
    
    print("\n" + "=" * 60)
    print("DATABASE UPGRADE COMPLETE")
    print("=" * 60)
    print("\nNew tables created:")
    print("  - client_candidates")
    print("  - suppression_list")
    print("  - compliance_events")
    print("  - classification_evidence")
    print("  - decision_ledger")
    print("  - reviews")
    print("  - reviewer_clients")
    print("\nUpgraded tables:")
    print("  - profile_visits (added h1, meta_description, extracted_json, evidence_hash)")
    print("\nData migrated:")
    print(f"  - {suppressed} providers moved to suppression_list")
    print(f"  - {candidates} clients moved to client_candidates")
    print("\n=== COMPLETE ===")


if __name__ == "__main__":
    upgrade_database_schema()
