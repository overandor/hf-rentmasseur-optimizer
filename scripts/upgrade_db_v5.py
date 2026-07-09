#!/usr/bin/env python3
"""
RM-CIC Database Upgrade V5 - Production Tables

Add client_candidates, suppression_list, compliance_events tables.
Implement four-pass system logic.
"""
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "rm_cic.db"


def upgrade_database_v5():
    """Upgrade database with production tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=== RM-CIC DATABASE UPGRADE V5 ===")

    # 1. Add client_candidates table
    print("\n[1] Adding client_candidates table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS client_candidates (
            username TEXT PRIMARY KEY,
            url TEXT,
            city TEXT,
            label TEXT,
            client_score REAL,
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

    # 2. Add suppression_list table
    print("[2] Adding suppression_list table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppression_list (
            username TEXT PRIMARY KEY,
            reason TEXT,
            created_ts TEXT
        )
    """)

    # 3. Add compliance_events table
    print("[3] Adding compliance_events table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compliance_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            event_type TEXT,
            detail TEXT,
            created_ts TEXT
        )
    """)

    # 4. Populate client_candidates from current classifications
    print("\n[4] Populating client_candidates from current classifications...")
    cursor.execute("""
        INSERT OR REPLACE INTO client_candidates
        (username, url, city, label, client_score, lead_value, confidence, evidence_title, reasons_json, review_status, created_ts, updated_ts)
        SELECT
            p.username,
            p.url,
            p.city,
            c.label,
            c.client_score,
            c.lead_value,
            c.confidence,
            v.title,
            c.reasons_json,
            CASE
                WHEN c.label = 'client_confirmed' AND c.confidence >= 80 AND c.lead_value >= 80 THEN 'pending_manual_review'
                WHEN c.label IN ('unknown', 'client_possible') AND c.lead_value >= 30 AND c.label != 'provider_confirmed' THEN 'needs_profile_visit'
                ELSE 'do_not_contact'
            END,
            datetime('now'),
            datetime('now')
        FROM profile_classifications c
        LEFT JOIN profiles p USING(username)
        LEFT JOIN profile_visits v ON c.username = v.username
    """)

    candidate_count = cursor.execute("SELECT COUNT(*) FROM client_candidates").fetchone()[0]
    print(f"  Added {candidate_count} candidates")

    # 5. Populate suppression_list with confirmed providers
    print("\n[5] Populating suppression_list with confirmed providers...")
    cursor.execute("""
        INSERT OR REPLACE INTO suppression_list
        (username, reason, created_ts)
        SELECT
            p.username,
            'provider_confirmed or provider_possible',
            datetime('now')
        FROM profile_classifications c
        JOIN profiles p USING(username)
        WHERE c.label IN ('provider_confirmed', 'provider_possible')
    """)

    suppression_count = cursor.execute("SELECT COUNT(*) FROM suppression_list").fetchone()[0]
    print(f"  Added {suppression_count} profiles to suppression list")

    conn.commit()
    conn.close()

    print("\n=== UPGRADE COMPLETE ===")
    print(f"Database: {DB_PATH}")
    print(f"Client candidates: {candidate_count}")
    print(f"Suppression list: {suppression_count}")


def print_production_summary():
    """Print production-ready summary."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n=== PRODUCTION SUMMARY ===")

    # Client candidates by review status
    print("\nClient candidates by review status:")
    cursor.execute("SELECT review_status, COUNT(*) FROM client_candidates GROUP BY review_status")
    for status, count in cursor.fetchall():
        print(f"  {status}: {count}")

    # Top candidates for manual review
    print("\nTop candidates for manual review:")
    cursor.execute("""
        SELECT username, city, label, lead_value, confidence
        FROM client_candidates
        WHERE review_status = 'pending_manual_review'
        ORDER BY lead_value DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[2]} (lead_value: {row[3]}, confidence: {row[4]})")

    # Profiles needing visit
    print("\nProfiles needing profile visit:")
    cursor.execute("""
        SELECT username, city, label, lead_value
        FROM client_candidates
        WHERE review_status = 'needs_profile_visit'
        ORDER BY lead_value DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[2]} (lead_value: {row[3]})")

    # Suppression list
    print(f"\nSuppression list: {cursor.execute('SELECT COUNT(*) FROM suppression_list').fetchone()[0]} profiles")

    conn.close()


if __name__ == "__main__":
    upgrade_database_v5()
    print_production_summary()
