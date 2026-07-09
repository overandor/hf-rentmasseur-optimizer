#!/usr/bin/env python3
"""
Classify Reviewers as Review-Confirmed Clients

Reviewer evidence is stronger than username evidence because leaving a review
indicates the person actually booked or received a service.
"""
import sqlite3
from datetime import datetime, timezone

from rm_cic_exact_spec import DB_PATH


def classify_reviewers_as_clients():
    """Classify reviewers as review-confirmed clients and add to outreach queue."""
    print("=" * 60)
    print("CLASSIFYING REVIEWERS AS REVIEW-CONFIRMED CLIENTS")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all reviewer clients
    cursor.execute("""
        SELECT reviewer_key, reviewer_name, review_count, provider_count,
               last_review_date, client_confidence, lead_value, status
        FROM reviewer_clients
        ORDER BY client_confidence DESC
    """)
    
    reviewers = cursor.fetchall()
    print(f"Found {len(reviewers)} reviewer clients")
    
    if not reviewers:
        print("No reviewer clients found")
        conn.close()
        return
    
    now = datetime.now(timezone.utc).isoformat()
    
    classified = 0
    queued = 0
    
    for reviewer_key, reviewer_name, review_count, provider_count, last_review_date, client_confidence, lead_value, status in reviewers:
        # Determine if reviewer is review-confirmed
        if review_count >= 1 and client_confidence >= 100:
            label = "review_confirmed_client"
            confidence = min(95, client_confidence + 10)  # Boost confidence for review evidence
        elif review_count >= 1 and client_confidence >= 80:
            label = "review_possible_client"
            confidence = client_confidence
        else:
            label = "reviewer_unknown"
            confidence = client_confidence
        
        # Check if reviewer is also a provider
        cursor.execute("SELECT username FROM profiles WHERE username = ?", (reviewer_name,))
        is_profile = cursor.fetchone()
        
        if is_profile:
            # Check classification
            cursor.execute("""
                SELECT label FROM profile_classifications 
                WHERE username = ?
            """, (reviewer_name,))
            classification = cursor.fetchone()
            
            if classification and classification[0] in ['provider_confirmed', 'provider_possible']:
                # Downgrade if they're also a provider
                label = "conflict_manual_review"
                confidence = 50
        
        # Update reviewer_clients status
        cursor.execute("""
            UPDATE reviewer_clients
            SET status = ?
            WHERE reviewer_key = ?
        """, (label, reviewer_key))
        
        # Add to client_candidates if review-confirmed
        if label == "review_confirmed_client":
            # Check if already in client_candidates
            cursor.execute("SELECT username FROM client_candidates WHERE username = ?", (reviewer_name,))
            existing = cursor.fetchone()
            
            if not existing:
                cursor.execute("""
                    INSERT INTO client_candidates
                    (username, url, city, label, client_score, provider_score, net_score,
                     lead_value, confidence, evidence_title, evidence_excerpt, reasons_json,
                     review_status, created_ts, updated_ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    reviewer_name,
                    f"https://rentmasseur.com/{reviewer_name}",
                    'New York',  # Default to NYC for reviewers
                    label,
                    client_confidence,
                    0,  # No provider score for reviewers
                    client_confidence,
                    lead_value,
                    confidence,
                    f'Review-confirmed: {review_count} reviews across {provider_count} providers',
                    f'Left {review_count} reviews for NYC providers. Last review: {last_review_date}',
                    f'["review_count:{review_count}", "provider_count:{provider_count}", "confidence:{client_confidence}"]',
                    'review_confirmed',
                    now,
                    now
                ))
                
                # Add to outreach_queue
                cursor.execute("""
                    INSERT OR REPLACE INTO outreach_queue
                    (username, url, city, label, lead_value, confidence, status, created_ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (reviewer_name, f"https://rentmasseur.com/{reviewer_name}", 'New York', label, lead_value, confidence, 'pending_manual_review', now))
                
                # Record compliance event
                cursor.execute("""
                    INSERT INTO compliance_events (username, event_type, detail, created_ts)
                    VALUES (?, ?, ?, ?)
                """, (reviewer_name, 'queued_for_review', f'Review-confirmed client with {review_count} reviews', now))
                
                queued += 1
                print(f"  Queued: {reviewer_name} (reviews: {review_count}, confidence: {confidence})")
            else:
                print(f"  Already in candidates: {reviewer_name}")
        
        classified += 1
    
    conn.commit()
    conn.close()
    
    print(f"\nClassified {classified} reviewer clients")
    print(f"Queued {queued} review-confirmed clients for outreach")
    
    # Print summary
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM reviewer_clients
        GROUP BY status
        ORDER BY count DESC
    """)
    
    distribution = cursor.fetchall()
    conn.close()
    
    print("\nReviewer client distribution:")
    for label, count in distribution:
        print(f"  {label}: {count}")
    
    print("\n=== COMPLETE ===")


if __name__ == "__main__":
    classify_reviewers_as_clients()
