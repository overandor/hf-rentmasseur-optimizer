#!/usr/bin/env python3
"""
Build Reviewer Clients Graph

Aggregates review data to create reviewer_clients records with client confidence scores.
"""
import sqlite3
from datetime import datetime, timezone

from rm_cic_exact_spec import DB_PATH, DATA_DIR


def build_reviewer_clients_graph():
    """Build reviewer_clients graph from reviews table."""
    print("=" * 60)
    print("BUILDING REVIEWER CLIENTS GRAPH")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all unique reviewers
    cursor.execute("""
        SELECT reviewer_name, COUNT(*) as review_count, 
               COUNT(DISTINCT provider_username) as provider_count,
               MAX(extracted_ts) as last_review_date
        FROM reviews
        GROUP BY reviewer_name
    """)
    
    reviewers = cursor.fetchall()
    print(f"Found {len(reviewers)} unique reviewers")
    
    if not reviewers:
        print("No reviewers found")
        conn.close()
        return
    
    now = datetime.now(timezone.utc).isoformat()
    
    for reviewer_name, review_count, provider_count, last_review_date in reviewers:
        # Calculate client confidence
        client_confidence = 0.0
        
        # Base score for being a reviewer
        client_confidence += 100
        
        # Bonus for multiple reviews
        if review_count > 1:
            client_confidence += 20
        
        # Bonus for reviewing multiple providers (indicates active client)
        if provider_count > 1:
            client_confidence += 20
        
        # Check if reviewer is also a provider
        cursor.execute("SELECT username FROM profiles WHERE username = ?", (reviewer_name,))
        is_provider = cursor.fetchone()
        
        if is_provider:
            # Check if they're classified as provider
            cursor.execute("""
                SELECT label FROM profile_classifications 
                WHERE username = ?
            """, (reviewer_name,))
            classification = cursor.fetchone()
            
            if classification and classification[0] in ['provider_confirmed', 'provider_possible']:
                client_confidence -= 50  # Penalize if they're also a provider
        
        # Calculate lead value
        lead_value = client_confidence
        
        # Determine status
        if client_confidence >= 100:
            status = 'pending_review'
        elif client_confidence >= 70:
            status = 'needs_verification'
        else:
            status = 'low_priority'
        
        # Insert into reviewer_clients
        cursor.execute("""
            INSERT OR REPLACE INTO reviewer_clients
            (reviewer_key, reviewer_name, reviewer_profile_url, inferred_city,
             review_count, provider_count, last_review_date, client_confidence,
             lead_value, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            reviewer_name,
            reviewer_name,
            f"https://rentmasseur.com/{reviewer_name}",
            'New York',  # Default to NYC for now
            review_count,
            provider_count,
            last_review_date,
            client_confidence,
            lead_value,
            status
        ))
    
    conn.commit()
    conn.close()
    
    print(f"Built reviewer_clients graph for {len(reviewers)} reviewers")
    
    # Print summary
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT reviewer_name, review_count, provider_count, 
               client_confidence, lead_value, status
        FROM reviewer_clients
        ORDER BY client_confidence DESC
        LIMIT 10
    """)
    
    top_reviewers = cursor.fetchall()
    conn.close()
    
    print("\nTop reviewer clients:")
    for reviewer, review_count, provider_count, confidence, lead_value, status in top_reviewers:
        print(f"  {reviewer}: {review_count} reviews, {provider_count} providers, confidence={confidence}, status={status}")
    
    print("\n=== COMPLETE ===")


if __name__ == "__main__":
    build_reviewer_clients_graph()
