#!/usr/bin/env python3
"""
Review Mining for Client Discovery

Extracts reviewer usernames from provider profile reviews and classifies them as potential clients.
Client-side language in reviews indicates demand-side intent.
"""
import hashlib
import json
import sqlite3
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
import requests
from bs4 import BeautifulSoup

from rm_cic_exact_spec import (
    classify_profile,
    save_profile,
    save_classification,
    update_queues,
    init_database,
    DB_PATH,
    DATA_DIR
)

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Client-side language patterns in reviews
CLIENT_REVIEW_PATTERNS = [
    "great massage",
    "excellent massage",
    "amazing massage",
    "best massage",
    "loved the massage",
    "really needed this",
    "was looking for",
    "found exactly what",
    "highly recommend",
    "will definitely",
    "going back",
    "thank you for",
    "much needed",
    "felt great",
    "very relaxing",
    "perfect massage",
    "experienced",
    "professional",
]

# Provider-side language patterns (reviewer is also a provider)
PROVIDER_REVIEW_PATTERNS = [
    "also a masseur",
    "i offer",
    "my clients",
    "my practice",
    "in the industry",
    "fellow masseur",
    "colleague",
]


def extract_reviews_from_profile(username: str) -> List[Dict[str, Any]]:
    """
    Extract reviews from a provider profile.
    Returns list of reviews with reviewer info and text.
    """
    reviews = []
    
    try:
        url = f"https://rentmasseur.com/{username}"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        
        if response.status_code == 200:
            html = response.text
            
            # Simple pattern to extract reviewer usernames
            reviewer_pattern = r'"reviewedBy":"([^"]+)"'
            reviewers = re.findall(reviewer_pattern, html)
            
            # Extract review text pattern
            text_pattern = r'"text":"([^"]*(?:\\.[^"]*)*)"'
            texts = re.findall(text_pattern, html)
            
            # Extract rating pattern
            rating_pattern = r'"rating":(\d+)'
            ratings = re.findall(rating_pattern, html)
            
            # Pair up the data
            for i in range(min(len(reviewers), len(texts), len(ratings))):
                reviewer = reviewers[i]
                text = texts[i]
                rating = int(ratings[i])
                
                # Decode HTML entities and escape sequences
                text = text.replace('\\u2019', "'").replace('\\u2018', "'").replace('\\u201c', '"').replace('\\u201d', '"')
                text = text.replace('\\n', ' ').replace('\\r', '')
                
                if text and len(text) > 20:
                    reviews.append({
                        'reviewer': reviewer,
                        'text': text,
                        'rating': rating,
                        'date': '',
                        'provider_username': username,
                        'source_url': url
                    })
        
    except Exception as e:
        print(f"  Error extracting reviews from {username}: {e}")
    
    return reviews


def classify_reviewer(review: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classify a reviewer as potential client based on review text.
    """
    text = review['text'].lower()
    reviewer = review['reviewer']
    
    # Check for client-side language
    client_signals = sum(1 for pattern in CLIENT_REVIEW_PATTERNS if pattern in text)
    
    # Check for provider-side language
    provider_signals = sum(1 for pattern in PROVIDER_REVIEW_PATTERNS if pattern in text)
    
    # Determine classification
    if client_signals >= 2 and provider_signals == 0:
        label = "client_possible"
        confidence = 70
    elif client_signals >= 1 and provider_signals == 0:
        label = "client_possible"
        confidence = 55
    elif provider_signals >= 1:
        label = "provider_possible"
        confidence = 65
    else:
        label = "unknown"
        confidence = 40
    
    return {
        'reviewer': reviewer,
        'text': review['text'],
        'provider_username': review['provider_username'],
        'label': label,
        'confidence': confidence,
        'client_signals': client_signals,
        'provider_signals': provider_signals
    }


def mine_reviews_from_providers(limit: int = 200):
    """
    Mine reviews from provider profiles in the database.
    """
    print("=" * 60)
    print("REVIEW MINING FOR CLIENT DISCOVERY")
    print("=" * 60)
    
    # Get provider_confirmed profiles (all NYC providers for deeper intel)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT p.username, p.url, p.city
        FROM profile_classifications c
        JOIN profiles p ON c.username = p.username
        WHERE c.label = 'provider_confirmed'
          AND (p.city LIKE '%Manhattan%' OR p.city LIKE '%New York%' OR p.city LIKE '%Brooklyn%' OR p.city LIKE '%Bronx%' OR p.city = '')
        LIMIT ?
    """, (limit,))
    
    providers = cursor.fetchall()
    conn.close()
    
    print(f"Found {len(providers)} provider profiles to mine")
    
    all_reviews = []
    all_reviewers = []
    
    # Extract reviews from each provider
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {}
        for username, url, city in providers:
            future = executor.submit(extract_reviews_from_profile, username)
            futures[future] = username
        
        for future in as_completed(futures):
            username = futures[future]
            try:
                reviews = future.result()
                if reviews:
                    print(f"  {username}: {len(reviews)} reviews")
                    all_reviews.extend(reviews)
                    
                    # Classify each reviewer
                    for review in reviews:
                        classification = classify_reviewer(review)
                        all_reviewers.append(classification)
                else:
                    print(f"  {username}: No reviews found")
            except Exception as e:
                print(f"  {username}: Error - {e}")
    
    print(f"\nTotal reviews extracted: {len(all_reviews)}")
    print(f"Total reviewers classified: {len(all_reviewers)}")
    
    # Save reviews to file
    reviews_file = DATA_DIR / "extracted_reviews.json"
    with open(reviews_file, 'w') as f:
        json.dump(all_reviews, f, indent=2)
    print(f"Saved: {reviews_file}")
    
    # Save reviewers to file
    reviewers_file = DATA_DIR / "classified_reviewers.json"
    with open(reviewers_file, 'w') as f:
        json.dump(all_reviewers, f, indent=2)
    print(f"Saved: {reviewers_file}")
    
    # Save client_possible reviewers to database
    client_reviewers = [r for r in all_reviewers if r['label'] == 'client_possible']
    print(f"\nClient-possible reviewers: {len(client_reviewers)}")
    
    if client_reviewers:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create table for review-discovered clients
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS review_discovered_clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reviewer_name TEXT,
                provider_username TEXT,
                review_text TEXT,
                label TEXT,
                confidence REAL,
                client_signals INTEGER,
                provider_signals INTEGER,
                created_ts TEXT
            )
        """)
        
        now = datetime.now(timezone.utc).isoformat()
        
        for reviewer in client_reviewers:
            cursor.execute("""
                INSERT INTO review_discovered_clients
                (reviewer_name, provider_username, review_text, label, confidence, client_signals, provider_signals, created_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                reviewer['reviewer'],
                reviewer['provider_username'],
                reviewer['text'],
                reviewer['label'],
                reviewer['confidence'],
                reviewer['client_signals'],
                reviewer['provider_signals'],
                now
            ))
        
        conn.commit()
        conn.close()
        print(f"Saved {len(client_reviewers)} client-possible reviewers to database")
        
        # Also save to new reviews table
        print(f"\nSaving reviews to reviews table...")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        for review in all_reviews:
            cursor.execute("""
                INSERT OR REPLACE INTO reviews
                (provider_username, reviewer_name, review_text, rating, extracted_ts, evidence_hash)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                review['provider_username'],
                review['reviewer'],
                review['text'],
                review.get('rating', 0),
                now,
                hashlib.md5(review['text'].encode()).hexdigest()
            ))
        
        conn.commit()
        conn.close()
        print(f"Saved {len(all_reviews)} reviews to reviews table")
        
        # Add to verification queue
        print(f"\nAdding {len(client_reviewers)} reviewers to verification queue...")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        for reviewer in client_reviewers:
            # Check if already in profiles table
            cursor.execute("SELECT username FROM profiles WHERE username = ?", (reviewer['reviewer'],))
            exists = cursor.fetchone()
            
            if not exists:
                # Add to profiles table
                cursor.execute("""
                    INSERT INTO profiles (username, name, city, url, source, first_seen_ts, last_seen_ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    reviewer['reviewer'],
                    reviewer['reviewer'],
                    '',
                    f"https://rentmasseur.com/{reviewer['reviewer']}",
                    'review_mining',
                    now,
                    now
                ))
                
                # Add to verification queue
                cursor.execute("""
                    INSERT INTO verification_queue (username, url, city, current_label, lead_value, priority, reason, created_ts)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    reviewer['reviewer'],
                    f"https://rentmasseur.com/{reviewer['reviewer']}",
                    '',
                    'client_possible',
                    reviewer['confidence'] * 1.5,  # Lead value based on confidence
                    'high',
                    'Review-discovered client candidate',
                    now
                ))
                print(f"  Added {reviewer['reviewer']} to verification queue")
            else:
                print(f"  {reviewer['reviewer']} already in database")
        
        conn.commit()
        conn.close()
        print(f"Added reviewers to verification queue")
    
    # Print summary
    print("\n" + "=" * 60)
    print("REVIEW MINING SUMMARY")
    print("=" * 60)
    print(f"Total providers mined: {len(providers)}")
    print(f"Total reviews extracted: {len(all_reviews)}")
    print(f"Total reviewers: {len(all_reviewers)}")
    print(f"Client-possible reviewers: {len(client_reviewers)}")
    
    if client_reviewers:
        print("\nTop client-possible reviewers:")
        for reviewer in sorted(client_reviewers, key=lambda x: x['confidence'], reverse=True)[:10]:
            print(f"  {reviewer['reviewer']}: confidence={reviewer['confidence']}, signals={reviewer['client_signals']}")
            print(f"    Review: {reviewer['text'][:100]}...")
    
    print("\n=== COMPLETE ===")


def load_and_classify_existing_reviews():
    """
    Load existing review data if available and classify reviewers.
    """
    print("=" * 60)
    print("LOADING EXISTING REVIEW DATA")
    print("=" * 60)
    
    # Check for existing review files
    review_files = [
        DATA_DIR / "manhattan_reviews.json",
        DATA_DIR / "extracted_reviews.json",
        DATA_DIR / "classified_reviewers.json"
    ]
    
    for review_file in review_files:
        if review_file.exists():
            print(f"\nFound: {review_file.name}")
            with open(review_file) as f:
                data = json.load(f)
            
            if isinstance(data, dict) and 'all_reviews' in data:
                reviews = data['all_reviews']
                print(f"  Reviews: {len(reviews)}")
            elif isinstance(data, list):
                reviews = data
                print(f"  Reviews: {len(reviews)}")
            else:
                reviews = []
                print(f"  No reviews found")
            
            if reviews:
                # Classify reviewers
                all_reviewers = []
                for review in reviews:
                    if isinstance(review, dict):
                        classification = classify_reviewer(review)
                        all_reviewers.append(classification)
                
                print(f"  Classified reviewers: {len(all_reviewers)}")
                
                # Save to database
                client_reviewers = [r for r in all_reviewers if r['label'] == 'client_possible']
                if client_reviewers:
                    conn = sqlite3.connect(DB_PATH)
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS review_discovered_clients (
                            id INTEGER PRIMARY KEY AUTOINCREMENT,
                            reviewer_name TEXT,
                            provider_username TEXT,
                            review_text TEXT,
                            label TEXT,
                            confidence REAL,
                            client_signals INTEGER,
                            provider_signals INTEGER,
                            created_ts TEXT
                        )
                    """)
                    
                    now = datetime.now(timezone.utc).isoformat()
                    
                    for reviewer in client_reviewers:
                        cursor.execute("""
                            INSERT OR REPLACE INTO review_discovered_clients
                            (reviewer_name, provider_username, review_text, label, confidence, client_signals, provider_signals, created_ts)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            reviewer['reviewer'],
                            reviewer.get('provider_username', ''),
                            reviewer['text'],
                            reviewer['label'],
                            reviewer['confidence'],
                            reviewer['client_signals'],
                            reviewer['provider_signals'],
                            now
                        ))
                    
                    conn.commit()
                    conn.close()
                    print(f"  Saved {len(client_reviewers)} client-possible reviewers to database")


if __name__ == "__main__":
    init_database()
    
    # First, try to load existing review data
    load_and_classify_existing_reviews()
    
    # Then, mine new reviews from providers (expanded for deeper intel)
    print("\n")
    mine_reviews_from_providers(limit=200)
