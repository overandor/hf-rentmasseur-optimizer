#!/usr/bin/env python3
"""
Four-Pass Production System for RM-CIC

Pass 1: classify_from_username - Fast scan all profiles from ny_users
Pass 2: visit_candidate_pages - Visit only profiles worth verifying
Pass 3: reclassify_from_body - Re-score using full evidence hierarchy
Pass 4: queue_only_confirmed_clients - Only insert into outreach_queue when confirmed
"""
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

from rm_cic_exact_spec import (
    classify_profile,
    save_profile,
    save_profile_visit,
    save_classification,
    update_queues,
    save_evidence_hits,
    should_visit_next,
    should_queue_for_review,
    should_suppress,
    init_database,
    DB_PATH,
    DATA_DIR
)

DATA_DIR.mkdir(parents=True, exist_ok=True)


def pass1_classify_from_username(ny_users_file: str = "data/ny_users.json", task1_file: str = "data/task1_visit_back.json"):
    """
    Pass 1: classify_from_username
    
    Fast scan all profiles from ny_users + visited-only profiles from task1.
    Purpose: create first-pass routing, not final outreach.
    """
    print("=" * 60)
    print("PASS 1: CLASSIFY FROM USERNAME")
    print("=" * 60)
    
    # Load ny_users
    with open(ny_users_file) as f:
        ny_data = json.load(f)
    users = ny_data.get("users", [])
    print(f"Loaded {len(users)} profiles from ny_users.json")
    
    # Load task1_visit_back for visited-only profiles
    with open(task1_file) as f:
        task1_data = json.load(f)
    visited = task1_data.get("visited", [])
    print(f"Loaded {len(visited)} visited profiles from task1_visit_back.json")
    
    # Create set of ny_users usernames
    ny_usernames = {u.get("username") for u in users}
    
    classified = []
    
    # Process ny_users
    for user in users:
        username = user.get("username")
        name = user.get("name")
        city = user.get("city")
        url = user.get("url")
        
        classification = classify_profile(username=username, title="", body_text="", city=city)
        save_profile(username, name, city, url, source="ny_users")
        save_classification(classification)
        update_queues(classification, url)
        classified.append(classification)
    
    # Process visited-only profiles (not in ny_users)
    for visit_record in visited:
        username = visit_record.get("username")
        if username not in ny_usernames:
            title = visit_record.get("title", "")
            url = f"https://rentmasseur.com/{username}"
            
            classification = classify_profile(username=username, title=title, body_text="", city="")
            save_profile(username, username, "", url, source="task1_visit_back")
            save_classification(classification)
            update_queues(classification, url)
            classified.append(classification)
    
    # Summary
    print(f"\nClassified {len(classified)} profiles total")
    print(f"  client_confirmed: {sum(1 for c in classified if c['label'] == 'client_confirmed')}")
    print(f"  client_possible: {sum(1 for c in classified if c['label'] == 'client_possible')}")
    print(f"  unknown: {sum(1 for c in classified if c['label'] == 'unknown')}")
    print(f"  provider_possible: {sum(1 for c in classified if c['label'] == 'provider_possible')}")
    print(f"  provider_confirmed: {sum(1 for c in classified if c['label'] == 'provider_confirmed')}")
    
    return classified


def pass2_visit_candidate_pages(task1_file: str = "data/task1_visit_back.json"):
    """
    Pass 2: visit_candidate_pages
    
    Visit only profiles worth verifying.
    Do not spend time on obvious providers.
    """
    print("\n" + "=" * 60)
    print("PASS 2: VISIT CANDIDATE PAGES")
    print("=" * 60)
    
    # Load visited data from task1_visit_back.json
    with open(task1_file) as f:
        data = json.load(f)
    
    visited = data.get("visited", [])
    print(f"Loaded {len(visited)} visited profiles from task1_visit_back.json")
    
    # Get profiles that need visits from database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT p.username, p.url, p.city, c.label, c.lead_value
        FROM profile_classifications c
        JOIN profiles p ON c.username = p.username
        WHERE c.label NOT IN ('provider_confirmed', 'do_not_contact')
          AND c.lead_value >= 30
    """)
    
    candidates = cursor.fetchall()
    conn.close()
    
    print(f"Found {len(candidates)} candidates worth visiting")
    
    # Process visited data (simulated - in production, this would be actual visits)
    visited_count = 0
    for visit_record in visited:
        username = visit_record.get("username")
        title = visit_record.get("title", "")
        status = visit_record.get("status", "visited")
        
        # Save visit record
        save_profile_visit(username, title, status=status)
        visited_count += 1
    
    print(f"Saved {visited_count} visit records to profile_visits")
    
    return visited_count


def pass3_reclassify_from_body():
    """
    Pass 3: reclassify_from_body
    
    Re-score using the full evidence hierarchy.
    Body text should override username.
    """
    print("\n" + "=" * 60)
    print("PASS 3: RECLASSIFY FROM BODY")
    print("=" * 60)
    
    # Get profiles with visit data
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT p.username, p.name, p.city, p.url, v.title, v.body_text
        FROM profiles p
        JOIN profile_visits v ON p.username = v.username
    """)
    
    profiles_with_visits = cursor.fetchall()
    conn.close()
    
    print(f"Found {len(profiles_with_visits)} profiles with visit data")
    
    reclassified = []
    for username, name, city, url, title, body_text in profiles_with_visits:
        # Reclassify with title and body text
        classification = classify_profile(username=username, title=title, body_text=body_text, city=city)
        
        # Save updated classification
        save_classification(classification)
        update_queues(classification, url)
        save_evidence_hits(username, classification)
        
        reclassified.append(classification)
    
    # Summary
    print(f"\nReclassified {len(reclassified)} profiles with body evidence")
    print(f"  client_confirmed: {sum(1 for c in reclassified if c['label'] == 'client_confirmed')}")
    print(f"  client_possible: {sum(1 for c in reclassified if c['label'] == 'client_possible')}")
    print(f"  unknown: {sum(1 for c in reclassified if c['label'] == 'unknown')}")
    print(f"  provider_possible: {sum(1 for c in reclassified if c['label'] == 'provider_possible')}")
    print(f"  provider_confirmed: {sum(1 for c in reclassified if c['label'] == 'provider_confirmed')}")
    
    return reclassified


def pass4_queue_only_confirmed_clients():
    """
    Pass 4: queue_only_confirmed_clients
    
    Only insert into outreach_queue when:
    - label == client_confirmed
    - confidence >= 80
    - lead_value >= 80
    - no strong provider evidence
    - not in suppression_list
    """
    print("\n" + "=" * 60)
    print("PASS 4: QUEUE ONLY CONFIRMED CLIENTS")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all client_confirmed profiles
    cursor.execute("""
        SELECT p.username, p.url, p.city, c.label, c.lead_value, c.confidence, c.provider_score
        FROM profile_classifications c
        JOIN profiles p ON c.username = p.username
        WHERE c.label = 'client_confirmed'
    """)
    
    client_confirmed = cursor.fetchall()
    print(f"Found {len(client_confirmed)} client_confirmed profiles")
    
    # Apply compliance gate
    queued = 0
    for username, url, city, label, lead_value, confidence, provider_score in client_confirmed:
        profile = {
            'username': username,
            'label': label,
            'lead_value': lead_value,
            'confidence': confidence,
            'provider_score': provider_score
        }
        
        if should_queue_for_review(profile):
            # Ensure in outreach_queue
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                INSERT OR REPLACE INTO outreach_queue (username, url, city, label, lead_value, confidence, status, created_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (username, url, city, label, lead_value, confidence, 'pending', now))
            queued += 1
            print(f"  Queued: {username} (lead_value: {lead_value}, confidence: {confidence})")
        else:
            print(f"  Skipped: {username} (lead_value: {lead_value}, confidence: {confidence})")
    
    conn.commit()
    conn.close()
    
    print(f"\nQueued {queued} profiles for outreach")
    
    return queued


def print_production_summary():
    """Print final production summary."""
    print("\n" + "=" * 60)
    print("PRODUCTION SUMMARY")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Profile counts
    cursor.execute("SELECT COUNT(*) FROM profiles")
    total_profiles = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM profile_visits")
    total_visits = cursor.fetchone()[0]
    
    # Classification distribution
    cursor.execute("""
        SELECT label, COUNT(*) 
        FROM profile_classifications 
        GROUP BY label
    """)
    classification_dist = dict(cursor.fetchall())
    
    # Queue counts
    cursor.execute("SELECT COUNT(*) FROM outreach_queue")
    outreach_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM verification_queue")
    verification_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM suppression_list")
    suppression_count = cursor.fetchone()[0]
    
    conn.close()
    
    print(f"\nTotal profiles: {total_profiles}")
    print(f"Total visits: {total_visits}")
    print(f"\nClassification distribution:")
    for label, count in classification_dist.items():
        print(f"  {label}: {count}")
    print(f"\nQueue status:")
    print(f"  Outreach queue: {outreach_count}")
    print(f"  Verification queue: {verification_count}")
    print(f"  Suppression list: {suppression_count}")
    
    # Top outreach candidates
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT username, lead_value, confidence 
        FROM outreach_queue 
        ORDER BY lead_value DESC 
        LIMIT 10
    """)
    top_outreach = cursor.fetchall()
    conn.close()
    
    if top_outreach:
        print(f"\nTop outreach candidates:")
        for username, lead_value, confidence in top_outreach:
            print(f"  {username}: lead_value={lead_value}, confidence={confidence}")
    
    print("\n" + "=" * 60)


def run_four_pass_system():
    """Run the complete four-pass production system."""
    print("=" * 60)
    print("FOUR-PASS PRODUCTION SYSTEM")
    print("=" * 60)
    
    # Initialize database
    init_database()
    
    # Pass 1: Classify from username
    pass1_results = pass1_classify_from_username()
    
    # Pass 2: Visit candidate pages
    pass2_count = pass2_visit_candidate_pages()
    
    # Pass 3: Reclassify from body
    pass3_results = pass3_reclassify_from_body()
    
    # Pass 4: Queue only confirmed clients
    pass4_count = pass4_queue_only_confirmed_clients()
    
    # Print summary
    print_production_summary()
    
    print("\n=== FOUR-PASS SYSTEM COMPLETE ===")


if __name__ == "__main__":
    run_four_pass_system()
