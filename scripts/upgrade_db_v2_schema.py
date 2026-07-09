#!/usr/bin/env python3
"""
RM-CIC V2 Database Schema Upgrade

Add evidence_hits and decision_ledger tables.
Add h1, meta_description, extracted_json, evidence_hash to profile_visits.
"""
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "rm_cic.db"


def upgrade_database_v2():
    """Upgrade database schema for RM-CIC V2."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=== RM-CIC V2 DATABASE SCHEMA UPGRADE ===")

    # 1. Add columns to profile_visits
    print("\n[1] Adding columns to profile_visits...")
    try:
        cursor.execute("ALTER TABLE profile_visits ADD COLUMN h1 TEXT")
        print("  Added h1 column")
    except:
        print("  h1 column already exists")

    try:
        cursor.execute("ALTER TABLE profile_visits ADD COLUMN meta_description TEXT")
        print("  Added meta_description column")
    except:
        print("  meta_description column already exists")

    try:
        cursor.execute("ALTER TABLE profile_visits ADD COLUMN extracted_json TEXT")
        print("  Added extracted_json column")
    except:
        print("  extracted_json column already exists")

    try:
        cursor.execute("ALTER TABLE profile_visits ADD COLUMN evidence_hash TEXT")
        print("  Added evidence_hash column")
    except:
        print("  evidence_hash column already exists")

    # 2. Add evidence_hits table
    print("\n[2] Adding evidence_hits table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evidence_hits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            visit_id INTEGER,
            phrase TEXT,
            phrase_type TEXT,
            score_delta REAL,
            field TEXT,
            created_ts TEXT
        )
    """)
    print("  Created evidence_hits table")

    # 3. Add decision_ledger table
    print("\n[3] Adding decision_ledger table...")
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
    print("  Created decision_ledger table")

    # 4. Add conflict_manual_review bucket to classification
    print("\n[4] Note: conflict_manual_review will be handled in classification logic")

    conn.commit()
    conn.close()

    print("\n=== SCHEMA UPGRADE COMPLETE ===")
    print(f"Database: {DB_PATH}")


if __name__ == "__main__":
    upgrade_database_v2()
