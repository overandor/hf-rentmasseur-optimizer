#!/usr/bin/env python3
"""
Production-Grade Four-Pass System with Evidence Trail

Implements the full client-intelligence pipeline:
1. classify_from_username - Fast triage
2. visit_candidate_pages - Extract evidence
3. reclassify_from_body - Use full evidence
4. queue_only_confirmed_clients - Compliance gate
"""
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

from rm_cic_exact_spec import (
    classify_profile,
    DB_PATH,
    DATA_DIR
)

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Rate limiting
REQUEST_DELAY = 2.0


def pass1_classify_from_username(ny_users_file: str = "data/ny_users.json"):
    """Pass 1: Fast triage using username, city, and existing title evidence."""
    print("=" * 60)
    print("PASS 1: CLASSIFY FROM USERNAME (FAST TRIAGE)")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Load ny_users
    with open(ny_users_file) as f:
        data = json.load(f)
    
    users = data.get('users', [])
    print(f"Loaded {len(users)} profiles from ny_users.json")
    
    # Classify each user
    classified = 0
    for user in users:
        username = user.get('username')
        name = user.get('name')
        city = user.get('city')
        url = user.get('url')
        
        # Check if already classified
        cursor.execute("SELECT username FROM profile_classifications WHERE username = ?", (username,))
        if cursor.fetchone():
            continue
        
        # Classify
        result = classify_profile(username, title="", body_text="", city=city)
        
        # Save profile
        cursor.execute("""
            INSERT OR REPLACE INTO profiles (username, name, city, url, source, first_seen_ts, last_seen_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (username, name, city, url, 'ny_users', datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()))
        
        # Save classification
        cursor.execute("""
            INSERT OR REPLACE INTO profile_classifications
            (username, label, client_score, provider_score, net_client_score, lead_value, confidence, reasons_json, classified_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            username,
            result['label'],
            result['client_score'],
            result['provider_score'],
            result['net_client_score'],
            result['lead_value'],
            result['confidence'],
            json.dumps(result['reasons']),
            datetime.now(timezone.utc).isoformat()
        ))
        
        # Record decision in ledger
        cursor.execute("""
            INSERT INTO decision_ledger (username, old_label, new_label, old_score, new_score, reason, created_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (username, None, result['label'], 0, result['net_client_score'], 'Initial username classification', datetime.now(timezone.utc).isoformat()))
        
        classified += 1
    
    conn.commit()
    conn.close()
    
    print(f"Classified {classified} new profiles")
    
    # Print distribution
    print_classification_distribution()


def pass2_visit_candidate_pages():
    """Pass 2: Visit candidate profiles and extract full evidence."""
    print("\n" + "=" * 60)
    print("PASS 2: VISIT CANDIDATE PAGES (EVIDENCE EXTRACTION)")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get candidates worth visiting
    cursor.execute("""
        SELECT p.username, p.url, p.city, c.label, c.lead_value
        FROM profile_classifications c
        JOIN profiles p ON c.username = p.username
        WHERE c.label != 'provider_confirmed'
          AND c.lead_value >= 30
          AND p.username NOT IN (SELECT username FROM profile_visits)
        ORDER BY c.lead_value DESC
        LIMIT 30
    """)
    
    candidates = cursor.fetchall()
    print(f"Found {len(candidates)} candidates to visit")
    
    if not candidates:
        print("No candidates found")
        conn.close()
        return
    
    # Import evidence extraction
    from evidence_extraction import extract_evidence_from_visit
    
    visited = 0
    for i, (username, url, city, label, lead_value) in enumerate(candidates, 1):
        print(f"  [{i}/{len(candidates)}] Visiting {username}...")
        
        result = extract_evidence_from_visit(username)
        
        if result['success']:
            # Store visit
            cursor.execute("""
                INSERT OR REPLACE INTO profile_visits
                (username, visited_ts, status, title, h1, meta_description, 
                 body_text, extracted_json, evidence_hash, http_status, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result['username'],
                datetime.now(timezone.utc).isoformat(),
                'success',
                result['title'],
                result['h1'],
                result['meta_description'],
                result['body_text'],
                result['extracted_json'],
                result['evidence_hash'],
                result['http_status'],
                result['error']
            ))
            
            # Store evidence hits
            for hit in result['evidence_hits']:
                cursor.execute("""
                    INSERT INTO classification_evidence
                    (username, evidence_type, evidence_text, score_delta, source_table, created_ts)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    hit['username'],
                    hit['evidence_type'],
                    hit['evidence_text'],
                    hit['score_delta'],
                    hit['source_table'],
                    hit['created_ts']
                ))
            
            visited += 1
            print(f"    Evidence hits: {len(result['evidence_hits'])}")
        else:
            print(f"    Error: {result['error']}")
        
        # Rate limiting
        if i < len(candidates):
            time.sleep(REQUEST_DELAY)
    
    conn.commit()
    conn.close()
    
    print(f"Visited {visited}/{len(candidates)} profiles successfully")


def pass3_reclassify_from_body():
    """Pass 3: Reclassify profiles using full body evidence."""
    print("\n" + "=" * 60)
    print("PASS 3: RECLASSIFY FROM BODY (FULL EVIDENCE)")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get profiles with visit data
    cursor.execute("""
        SELECT p.username, p.city, v.title, v.body_text, c.label as old_label, c.net_client_score as old_score
        FROM profile_visits v
        JOIN profiles p ON v.username = p.username
        JOIN profile_classifications c ON p.username = c.username
        WHERE v.status = 'success'
    """)
    
    profiles = cursor.fetchall()
    print(f"Found {len(profiles)} profiles with visit data to reclassify")
    
    if not profiles:
        print("No profiles with visit data found")
        conn.close()
        return
    
    reclassified = 0
    for username, city, title, body_text, old_label, old_score in profiles:
        # Reclassify with full evidence
        result = classify_profile(username, title=title, body_text=body_text, city=city)
        
        # Update classification
        cursor.execute("""
            UPDATE profile_classifications
            SET label = ?, client_score = ?, provider_score = ?, net_client_score = ?,
                lead_value = ?, confidence = ?, reasons_json = ?, classified_ts = ?
            WHERE username = ?
        """, (
            result['label'],
            result['client_score'],
            result['provider_score'],
            result['net_client_score'],
            result['lead_value'],
            result['confidence'],
            json.dumps(result['reasons']),
            datetime.now(timezone.utc).isoformat(),
            username
        ))
        
        # Record decision in ledger
        cursor.execute("""
            INSERT INTO decision_ledger (username, old_label, new_label, old_score, new_score, reason, created_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (username, old_label, result['label'], old_score, result['net_client_score'], 'Reclassification with body evidence', datetime.now(timezone.utc).isoformat()))
        
        reclassified += 1
    
    conn.commit()
    conn.close()
    
    print(f"Reclassified {reclassified} profiles")
    print_classification_distribution()


def pass4_queue_only_confirmed_clients():
    """Pass 4: Queue only confirmed clients through compliance gate."""
    print("\n" + "=" * 60)
    print("PASS 4: QUEUE ONLY CONFIRMED CLIENTS (COMPLIANCE GATE)")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get client_confirmed profiles
    cursor.execute("""
        SELECT p.username, p.url, p.city, c.label, c.lead_value, c.confidence
        FROM profile_classifications c
        JOIN profiles p ON c.username = p.username
        WHERE c.label = 'client_confirmed'
          AND c.confidence >= 80
          AND c.lead_value >= 80
    """)
    
    confirmed_clients = cursor.fetchall()
    print(f"Found {len(confirmed_clients)} confirmed clients meeting criteria")
    
    if not confirmed_clients:
        print("No confirmed clients meet criteria")
        conn.close()
        return
    
    queued = 0
    for username, url, city, label, lead_value, confidence in confirmed_clients:
        # Check if in suppression list
        cursor.execute("SELECT username FROM suppression_list WHERE username = ?", (username,))
        if cursor.fetchone():
            print(f"  {username}: Suppressed, skipping")
            continue
        
        # Add to client_candidates
        cursor.execute("""
            INSERT OR REPLACE INTO client_candidates
            (username, url, city, label, client_score, provider_score, net_score,
             lead_value, confidence, evidence_title, evidence_excerpt, reasons_json,
             review_status, created_ts, updated_ts)
            SELECT 
                p.username, p.url, p.city, c.label, c.client_score, c.provider_score, c.net_client_score,
                c.lead_value, c.confidence, v.title, v.body_text, c.reasons_json,
                'pending_review', ?, ?
            FROM profiles p
            JOIN profile_classifications c ON p.username = c.username
            LEFT JOIN profile_visits v ON p.username = v.username
            WHERE p.username = ?
        """, (datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat(), username))
        
        # Add to outreach_queue
        cursor.execute("""
            INSERT OR REPLACE INTO outreach_queue
            (username, url, city, label, lead_value, confidence, status, created_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (username, url, city, label, lead_value, confidence, 'pending_review', datetime.now(timezone.utc).isoformat()))
        
        # Record compliance event
        cursor.execute("""
            INSERT INTO compliance_events (username, event_type, detail, created_ts)
            VALUES (?, ?, ?, ?)
        """, (username, 'queued_for_review', f'Client confirmed with confidence {confidence}', datetime.now(timezone.utc).isoformat()))
        
        queued += 1
        print(f"  Queued: {username} (lead_value: {lead_value}, confidence: {confidence})")
    
    conn.commit()
    conn.close()
    
    print(f"Queued {queued} confirmed clients for outreach")
    print_queue_status()


def print_classification_distribution():
    """Print current classification distribution."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT label, COUNT(*) as count
        FROM profile_classifications
        GROUP BY label
        ORDER BY count DESC
    """)
    
    distribution = cursor.fetchall()
    conn.close()
    
    print("\nClassification distribution:")
    for label, count in distribution:
        print(f"  {label}: {count}")


def print_queue_status():
    """Print current queue status."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM outreach_queue")
    outreach_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM verification_queue")
    verification_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM suppression_list")
    suppression_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM client_candidates")
    candidates_count = cursor.fetchone()[0]
    
    conn.close()
    
    print("\nQueue status:")
    print(f"  Outreach queue: {outreach_count}")
    print(f"  Verification queue: {verification_count}")
    print(f"  Suppression list: {suppression_count}")
    print(f"  Client candidates: {candidates_count}")


def run_production_system():
    """Run the full four-pass production system."""
    print("=" * 60)
    print("PRODUCTION-GRADE CLIENT-INTELLIGENCE SYSTEM")
    print("=" * 60)
    
    # Initialize database
    from rm_cic_exact_spec import init_database
    init_database()
    
    # Run passes
    pass1_classify_from_username()
    pass2_visit_candidate_pages()
    pass3_reclassify_from_body()
    pass4_queue_only_confirmed_clients()
    
    # Final summary
    print("\n" + "=" * 60)
    print("PRODUCTION SYSTEM COMPLETE")
    print("=" * 60)
    print_classification_distribution()
    print_queue_status()


if __name__ == "__main__":
    run_production_system()
