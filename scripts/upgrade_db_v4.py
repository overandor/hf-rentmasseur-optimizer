#!/usr/bin/env python3
"""
RM-CIC Database Upgrade V4

Upgrade the database with:
- profile_visits evidence table (populate with existing data)
- verification_queue table for uncertain but promising profiles
- classification_evidence table for audit trail
- Three-score system (client_probability, provider_probability, lead_value)
- conflict_review bucket for ambiguous profiles
- Rebuild outreach_queue with high-quality records only
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "rm_cic.db"

# Load existing data for migration
visited_file = DATA_DIR / "task1_visit_back.json"
classification_audit = DATA_DIR / "classification_audit_v3.json"


def upgrade_database():
    """Upgrade database schema and populate new tables."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=== RM-CIC DATABASE UPGRADE V4 ===")

    # 1. Add classification_evidence table
    print("\n[1] Adding classification_evidence table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS classification_evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            evidence_type TEXT,
            evidence_text TEXT,
            score_delta REAL,
            source_table TEXT,
            source_id INTEGER,
            created_ts TEXT
        )
    """)

    # 2. Add verification_queue table
    print("[2] Adding verification_queue table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS verification_queue (
            username TEXT PRIMARY KEY,
            url TEXT,
            city TEXT,
            current_label TEXT,
            client_score REAL,
            lead_value REAL,
            confidence REAL,
            priority TEXT,
            status TEXT,
            created_ts TEXT
        )
    """)

    # 3. Add exclusion_queue table
    print("[3] Adding exclusion_queue table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exclusion_queue (
            username TEXT PRIMARY KEY,
            url TEXT,
            city TEXT,
            label TEXT,
            reason TEXT,
            created_ts TEXT
        )
    """)

    # 4. Add audit_log table
    print("[4] Adding audit_log table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            action TEXT,
            old_label TEXT,
            new_label TEXT,
            old_score REAL,
            new_score REAL,
            reason TEXT,
            created_ts TEXT
        )
    """)

    # 5. Add columns for three-score system to profile_classifications
    print("[5] Adding three-score columns to profile_classifications...")
    try:
        cursor.execute("ALTER TABLE profile_classifications ADD COLUMN client_probability REAL")
    except:
        pass  # Column may already exist
    try:
        cursor.execute("ALTER TABLE profile_classifications ADD COLUMN provider_probability REAL")
    except:
        pass

    # 6. Populate profile_visits with existing data
    print("\n[6] Populating profile_visits with existing data...")
    if visited_file.exists():
        with open(visited_file) as f:
            visited_data = json.load(f)
        visited_profiles = visited_data.get("visited", [])

        for p in visited_profiles:
            username = p.get("username")
            title = p.get("title")
            status = p.get("status")
            bytes_len = p.get("bytes", 0)

            cursor.execute("""
                INSERT OR REPLACE INTO profile_visits
                (username, visited_ts, status, title, body_text, http_status, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                username,
                datetime.now(timezone.utc).isoformat(),
                "visited" if status == 200 else "error",
                title,
                "",  # No body text in current data
                status if isinstance(status, int) else 200,
                None if status == 200 else str(status)
            ))
        print(f"  Inserted {len(visited_profiles)} visit records")
    else:
        print("  No visited data file found")

    # 7. Populate classification_evidence from existing classifications
    print("\n[7] Populating classification_evidence from existing classifications...")
    cursor.execute("SELECT username, reasons_json FROM profile_classifications")
    classifications = cursor.fetchall()

    for username, reasons_json in classifications:
        if reasons_json:
            try:
                reasons = json.loads(reasons_json)
                for reason in reasons:
                    # Parse reason format: "+80 strong_client_text:looking for male massage"
                    parts = reason.split(":")
                    if len(parts) >= 2:
                        score_delta_str = parts[0]
                        evidence_text = ":".join(parts[1:])
                        evidence_type = "unknown"

                        if "client" in reason.lower():
                            evidence_type = "client_evidence"
                        elif "provider" in reason.lower():
                            evidence_type = "provider_evidence"
                        elif "confidence" in reason.lower():
                            evidence_type = "confidence"

                        try:
                            score_delta = float(score_delta_str)
                        except:
                            score_delta = 0

                        cursor.execute("""
                            INSERT INTO classification_evidence
                            (username, evidence_type, evidence_text, score_delta, source_table, created_ts)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            username,
                            evidence_type,
                            evidence_text,
                            score_delta,
                            "profile_classifications",
                            datetime.now(timezone.utc).isoformat()
                        ))
            except:
                pass

    print(f"  Inserted evidence records")

    # 8. Calculate client_probability and provider_probability
    print("\n[8] Calculating client_probability and provider_probability...")
    cursor.execute("SELECT username, client_score, reasons_json FROM profile_classifications")
    for username, client_score, reasons_json in cursor.fetchall():
        client_prob = 0
        provider_prob = 0

        if reasons_json:
            try:
                reasons = json.loads(reasons_json)
                for reason in reasons:
                    if "client" in reason.lower():
                        client_prob += abs(float(reason.split(":")[0])) if reason[0] in "+-" else 10
                    elif "provider" in reason.lower():
                        provider_prob += abs(float(reason.split(":")[0])) if reason[0] in "+-" else 10
            except:
                pass

        # Normalize to 0-100
        client_prob = min(100, max(0, client_prob))
        provider_prob = min(100, max(0, provider_prob))

        cursor.execute("""
            UPDATE profile_classifications
            SET client_probability = ?, provider_probability = ?
            WHERE username = ?
        """, (client_prob, provider_prob, username))

    # 9. Restore original V3 labels from classification_audit_v3.json
    print("\n[9] Restoring original V3 labels from classification_audit_v3.json...")
    audit_file = DATA_DIR / "classification_audit_v3.json"
    if audit_file.exists():
        with open(audit_file) as f:
            audit_data = json.load(f)
        profiles = audit_data.get("classified", [])

        for p in profiles:
            username = p.get("username")
            label = p.get("label")
            if username and label:
                cursor.execute("""
                    UPDATE profile_classifications
                    SET label = ?
                    WHERE username = ?
                """, (label, username))
        print(f"  Restored labels for {len(profiles)} profiles")
    else:
        print("  classification_audit_v3.json not found, trying final_classification.json...")
        final_class_file = DATA_DIR / "final_classification.json"
        if final_class_file.exists():
            with open(final_class_file) as f:
                final_data = json.load(f)
            profiles = final_data.get("profiles", [])

            for p in profiles:
                username = p.get("username")
                label = p.get("label")
                if username and label:
                    cursor.execute("""
                        UPDATE profile_classifications
                        SET label = ?
                        WHERE username = ?
                    """, (label, username))
            print(f"  Restored labels for {len(profiles)} profiles")

    # 10. Populate verification_queue with unknown profiles (lead_value >= 30)
    print("\n[10] Populating verification_queue...")
    cursor.execute("""
        INSERT OR REPLACE INTO verification_queue
        (username, url, city, current_label, client_score, lead_value, confidence, priority, status, created_ts)
        SELECT
            p.username,
            p.url,
            p.city,
            c.label,
            c.client_score,
            c.lead_value,
            c.confidence,
            CASE
                WHEN c.lead_value >= 60 THEN 'high'
                WHEN c.lead_value >= 40 THEN 'medium'
                ELSE 'low'
            END,
            'pending',
            datetime('now')
        FROM profile_classifications c
        JOIN profiles p USING(username)
        WHERE c.label IN ('unknown', 'conflict_review')
          AND c.lead_value >= 30
    """)

    verification_count = cursor.execute("SELECT COUNT(*) FROM verification_queue").fetchone()[0]
    print(f"  Added {verification_count} profiles to verification queue")

    # 11. Populate exclusion_queue with confirmed providers
    print("\n[11] Populating exclusion_queue...")
    cursor.execute("""
        INSERT OR REPLACE INTO exclusion_queue
        (username, url, city, label, reason, created_ts)
        SELECT
            p.username,
            p.url,
            p.city,
            c.label,
            'provider_confirmed or provider_possible',
            datetime('now')
        FROM profile_classifications c
        JOIN profiles p USING(username)
        WHERE c.label IN ('provider_confirmed', 'provider_possible')
    """)

    exclusion_count = cursor.execute("SELECT COUNT(*) FROM exclusion_queue").fetchone()[0]
    print(f"  Added {exclusion_count} profiles to exclusion queue")

    # 12. Rebuild outreach_queue with high-quality records only
    print("\n[12] Rebuilding outreach_queue with high-quality records...")
    cursor.execute("DELETE FROM outreach_queue")

    cursor.execute("""
        INSERT INTO outreach_queue
        (username, url, city, label, lead_value, status, created_ts)
        SELECT
            p.username,
            p.url,
            p.city,
            c.label,
            c.lead_value,
            'pending',
            datetime('now')
        FROM profile_classifications c
        JOIN profiles p USING(username)
        WHERE c.label IN ('client_confirmed', 'client_possible')
          AND c.lead_value >= 60
          AND c.confidence >= 60
        ORDER BY c.lead_value DESC
    """)

    outreach_count = cursor.execute("SELECT COUNT(*) FROM outreach_queue").fetchone()[0]
    print(f"  Rebuilt outreach queue with {outreach_count} high-quality records")

    conn.commit()
    conn.close()

    print("\n=== UPGRADE COMPLETE ===")
    print(f"Database: {DB_PATH}")
    print(f"Verification queue: {verification_count} profiles")
    print(f"Exclusion queue: {exclusion_count} profiles")
    print(f"Outreach queue: {outreach_count} profiles")


def print_summary():
    """Print current database summary."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n=== DATABASE SUMMARY ===")

    # Table counts
    tables = ["profiles", "profile_visits", "profile_classifications", "outreach_queue", "verification_queue", "exclusion_queue", "classification_evidence"]
    for table in tables:
        try:
            count = cursor.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            print(f"{table}: {count} rows")
        except:
            print(f"{table}: N/A")

    # Classification distribution
    print("\nClassification distribution:")
    cursor.execute("SELECT label, COUNT(*) FROM profile_classifications GROUP BY label")
    for label, count in cursor.fetchall():
        print(f"  {label}: {count}")

    # Top outreach candidates
    print("\nTop outreach candidates:")
    cursor.execute("""
        SELECT
            c.username,
            p.city,
            c.label,
            c.client_score,
            c.lead_value,
            c.confidence
        FROM profile_classifications c
        LEFT JOIN profiles p USING(username)
        ORDER BY c.lead_value DESC, c.confidence DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[2]} (score: {row[3]}, lead_value: {row[4]}, confidence: {row[5]})")

    # Top verification candidates
    print("\nTop verification candidates:")
    cursor.execute("""
        SELECT
            username,
            city,
            current_label,
            lead_value,
            priority
        FROM verification_queue
        ORDER BY lead_value DESC, priority DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[2]} (lead_value: {row[3]}, priority: {row[4]})")

    conn.close()


if __name__ == "__main__":
    upgrade_database()
    print_summary()
