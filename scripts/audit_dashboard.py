#!/usr/bin/env python3
"""
RM-CIC V2 Audit Dashboard

Shows counts, reasons, top leads, provider exclusions, and error pages.
Key metrics for monitoring the client intelligence classifier.
"""
import sqlite3
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "rm_cic.db"


def print_dashboard():
    """Print comprehensive audit dashboard."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=" * 60)
    print("RM-CIC V2 AUDIT DASHBOARD")
    print("=" * 60)

    # Total profiles
    total_profiles = cursor.execute("SELECT COUNT(*) FROM profiles").fetchone()[0]
    print(f"\nTotal profiles: {total_profiles}")

    # Visited vs unvisited
    visited_profiles = cursor.execute("SELECT COUNT(*) FROM profile_visits").fetchone()[0]
    unvisited_profiles = total_profiles - visited_profiles
    print(f"Visited profiles: {visited_profiles}")
    print(f"Unvisited profiles: {unvisited_profiles}")
    print(f"Visit rate: {visited_profiles/total_profiles*100:.1f}%")

    # Classification distribution
    print("\n" + "-" * 60)
    print("CLASSIFICATION DISTRIBUTION")
    print("-" * 60)
    cursor.execute("SELECT label, COUNT(*) FROM profile_classifications GROUP BY label ORDER BY COUNT(*) DESC")
    for label, count in cursor.fetchall():
        print(f"  {label}: {count}")

    # Client candidates by review status
    print("\n" + "-" * 60)
    print("CLIENT CANDIDATES BY REVIEW STATUS")
    print("-" * 60)
    cursor.execute("SELECT review_status, COUNT(*) FROM client_candidates GROUP BY review_status")
    for status, count in cursor.fetchall():
        print(f"  {status}: {count}")

    # Outreach queue
    print("\n" + "-" * 60)
    print("OUTREACH QUEUE")
    print("-" * 60)
    outreach_count = cursor.execute("SELECT COUNT(*) FROM outreach_queue").fetchone()[0]
    print(f"Total queued leads: {outreach_count}")

    cursor.execute("""
        SELECT oq.username, p.city, oq.label, oq.lead_value, c.confidence, oq.status
        FROM outreach_queue oq
        JOIN profiles p ON oq.username = p.username
        JOIN profile_classifications c ON oq.username = c.username
        ORDER BY oq.lead_value DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[2]} (lead_value: {row[3]}, confidence: {row[4]}, status: {row[5]})")

    # Verification queue
    print("\n" + "-" * 60)
    print("VERIFICATION QUEUE (NEEDS PROFILE VISIT)")
    print("-" * 60)
    verification_count = cursor.execute("SELECT COUNT(*) FROM verification_queue").fetchone()[0]
    print(f"Total verification candidates: {verification_count}")

    cursor.execute("""
        SELECT username, city, current_label, lead_value, priority, status
        FROM verification_queue
        ORDER BY lead_value DESC
        LIMIT 20
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[2]} (lead_value: {row[3]}, priority: {row[4]}, status: {row[5]})")

    # Top possible clients
    print("\n" + "-" * 60)
    print("TOP POSSIBLE CLIENTS")
    print("-" * 60)
    cursor.execute("""
        SELECT
            username,
            label,
            client_score,
            lead_value,
            confidence
        FROM profile_classifications
        WHERE label IN ('client_confirmed', 'client_possible', 'unknown')
        ORDER BY lead_value DESC
        LIMIT 20
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} (client_score: {row[2]}, lead_value: {row[3]}, confidence: {row[4]})")

    # Provider exclusions
    print("\n" + "-" * 60)
    print("PROVIDER EXCLUSIONS")
    print("-" * 60)
    cursor.execute("""
        SELECT
            username,
            label,
            client_score,
            reasons_json
        FROM profile_classifications
        WHERE label LIKE 'provider%'
        ORDER BY client_score ASC
        LIMIT 20
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} (client_score: {row[2]})")

    # Suppression list
    print("\n" + "-" * 60)
    print("SUPPRESSION LIST")
    print("-" * 60)
    suppression_count = cursor.execute("SELECT COUNT(*) FROM suppression_list").fetchone()[0]
    print(f"Total suppressed profiles: {suppression_count}")

    # Conflict manual review
    print("\n" + "-" * 60)
    print("CONFLICT MANUAL REVIEW")
    print("-" * 60)
    cursor.execute("""
        SELECT c.username, p.city, c.client_score, c.lead_value
        FROM profile_classifications c
        JOIN profiles p ON c.username = p.username
        WHERE c.label = 'conflict_manual_review'
        ORDER BY c.lead_value DESC
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} (client_score: {row[2]}, lead_value: {row[3]})")

    # Evidence audit
    print("\n" + "-" * 60)
    print("EVIDENCE AUDIT")
    print("-" * 60)
    evidence_count = cursor.execute("SELECT COUNT(*) FROM evidence_hits").fetchone()[0]
    print(f"Total evidence hits: {evidence_count}")

    cursor.execute("SELECT phrase_type, COUNT(*) FROM evidence_hits GROUP BY phrase_type")
    for phrase_type, count in cursor.fetchall():
        print(f"  {phrase_type}: {count}")

    # Decision ledger
    print("\n" + "-" * 60)
    print("DECISION LEDGER")
    print("-" * 60)
    decision_count = cursor.execute("SELECT COUNT(*) FROM decision_ledger").fetchone()[0]
    print(f"Total decision entries: {decision_count}")

    cursor.execute("""
        SELECT old_label, new_label, COUNT(*)
        FROM decision_ledger
        GROUP BY old_label, new_label
        ORDER BY COUNT(*) DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]} -> {row[1]}: {row[2]} changes")

    # Profiles needing visits
    print("\n" + "-" * 60)
    print("PROFILES NEEDING VISITS")
    print("-" * 60)
    cursor.execute("""
        SELECT
            p.username,
            p.city,
            p.url,
            c.label,
            c.client_score,
            c.lead_value
        FROM profiles p
        JOIN profile_classifications c ON p.username = c.username
        LEFT JOIN profile_visits v ON p.username = v.username
        WHERE v.username IS NULL
          AND c.label IN ('client_possible', 'unknown')
        ORDER BY c.lead_value DESC
        LIMIT 20
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[3]} (client_score: {row[4]}, lead_value: {row[5]})")

    # Key metrics summary
    print("\n" + "=" * 60)
    print("KEY METRICS SUMMARY")
    print("=" * 60)
    print(f"Total profiles: {total_profiles}")
    print(f"Visited profiles: {visited_profiles}")
    print(f"Unvisited profiles: {unvisited_profiles}")
    print(f"Client confirmed: {cursor.execute('SELECT COUNT(*) FROM profile_classifications WHERE label = \"client_confirmed\"').fetchone()[0]}")
    print(f"Client possible: {cursor.execute('SELECT COUNT(*) FROM profile_classifications WHERE label = \"client_possible\"').fetchone()[0]}")
    print(f"Unknown: {cursor.execute('SELECT COUNT(*) FROM profile_classifications WHERE label = \"unknown\"').fetchone()[0]}")
    print(f"Provider possible: {cursor.execute('SELECT COUNT(*) FROM profile_classifications WHERE label = \"provider_possible\"').fetchone()[0]}")
    print(f"Provider confirmed: {cursor.execute('SELECT COUNT(*) FROM profile_classifications WHERE label = \"provider_confirmed\"').fetchone()[0]}")
    print(f"Queued leads: {outreach_count}")
    print(f"Manual review rate: {outreach_count/total_profiles*100:.1f}%")
    print(f"Evidence hits: {evidence_count}")
    print(f"Decision entries: {decision_count}")

    conn.close()


if __name__ == "__main__":
    print_dashboard()
