#!/usr/bin/env python3
"""
Evidence Extraction from Profile Visits

Visits profiles, extracts full evidence (title, h1, meta, body text),
stores in profile_visits, and creates evidence hits in classification_evidence.
"""
import hashlib
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
import requests
from bs4 import BeautifulSoup

from rm_cic_exact_spec import DB_PATH, DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Rate limiting
REQUEST_DELAY = 2.0

# Evidence dictionaries
CLIENT_STRONG = [
    "looking for male massage",
    "looking for massage therapist",
    "looking for a massage therapist",
    "looking for masseur",
    "looking for massage",
    "need a massage",
    "need massage",
    "in need of massage",
    "seeking massage",
    "seeking bodywork",
    "massage wanted",
    "want a massage",
    "looking to book",
]

CLIENT_WEAK = [
    "looking for",
    "seeking",
    "need",
    "wanted",
    "can host",
    "available today",
    "prefer",
]

PROVIDER_STRONG = [
    "male masseur",
    "professional masseur",
    "certified masseur",
    "gay massage in",
    "massage in new york",
    "massage in manhattan",
    "massage in brooklyn",
    "massage in bronx",
    "deep tissue massage",
    "swedish massage",
    "sports massage",
    "therapeutic massage",
    "bodywork by",
    "i offer",
    "my massage",
    "book me",
    "incall",
    "outcall",
    "rates",
    "pricing",
    "session",
]

CLIENT_USERNAME = [
    "need",
    "inneed",
    "looking",
    "luv",
    "love",
    "aching",
    "sore",
    "tired",
    "relax",
    "body",
]

PROVIDER_USERNAME = [
    "masseur",
    "massuer",
    "massage",
    "hands",
    "touch",
    "bodywork",
    "spa",
    "therapy",
    "therapist",
    "healing",
    "deep",
    "swedish",
    "sportsmassage",
]


def extract_evidence_from_visit(username: str) -> Dict[str, Any]:
    """Visit a profile and extract all evidence."""
    result = {
        'username': username,
        'success': False,
        'http_status': None,
        'title': None,
        'h1': None,
        'meta_description': None,
        'body_text': None,
        'extracted_json': None,
        'evidence_hash': None,
        'error': None,
        'evidence_hits': []
    }
    
    try:
        url = f"https://rentmasseur.com/{username}"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        
        result['http_status'] = response.status_code
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract title
            title_tag = soup.find('title')
            result['title'] = title_tag.get_text(strip=True) if title_tag else None
            
            # Extract h1
            h1_tag = soup.find('h1')
            result['h1'] = h1_tag.get_text(strip=True) if h1_tag else None
            
            # Extract meta description
            meta_desc = soup.find('meta', attrs={'name': 'description'})
            result['meta_description'] = meta_desc.get('content', '') if meta_desc else None
            
            # Extract body text
            body = soup.get_text(separator=' ', strip=True)
            result['body_text'] = body[:10000] if body else None  # Limit to 10k chars
            
            # Extract JSON data
            next_data = soup.find('script', {'id': '__NEXT_DATA__'})
            if next_data and next_data.string:
                result['extracted_json'] = next_data.string[:5000]  # Limit to 5k chars
            
            # Generate evidence hash
            evidence_str = f"{result['title']}|{result['h1']}|{result['body_text'][:1000]}"
            result['evidence_hash'] = hashlib.md5(evidence_str.encode()).hexdigest()
            
            # Extract evidence hits
            result['evidence_hits'] = extract_evidence_hits(
                username, result['title'], result['body_text']
            )
            
            result['success'] = True
        else:
            result['error'] = f"HTTP {response.status_code}"
    
    except Exception as e:
        result['error'] = str(e)
    
    return result


def extract_evidence_hits(username: str, title: str, body_text: str) -> List[Dict[str, Any]]:
    """Extract evidence hits from profile content."""
    hits = []
    u = username.lower()
    t = (title or "").lower()
    b = (body_text or "").lower()
    text = f"{t} {b}"
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Client strong evidence
    for term in CLIENT_STRONG:
        if term in text:
            hits.append({
                'username': username,
                'evidence_type': 'client_strong',
                'evidence_text': term,
                'score_delta': 80,
                'source_table': 'profile_visits',
                'created_ts': now
            })
    
    # Client weak evidence
    for term in CLIENT_WEAK:
        if term in text:
            hits.append({
                'username': username,
                'evidence_type': 'client_weak',
                'evidence_text': term,
                'score_delta': 25,
                'source_table': 'profile_visits',
                'created_ts': now
            })
    
    # Client username evidence
    for term in CLIENT_USERNAME:
        if term in u:
            hits.append({
                'username': username,
                'evidence_type': 'client_username',
                'evidence_text': term,
                'score_delta': 20,
                'source_table': 'profiles',
                'created_ts': now
            })
    
    # Provider strong evidence
    for term in PROVIDER_STRONG:
        if term in text:
            hits.append({
                'username': username,
                'evidence_type': 'provider_strong',
                'evidence_text': term,
                'score_delta': -100,
                'source_table': 'profile_visits',
                'created_ts': now
            })
    
    # Provider username evidence
    for term in PROVIDER_USERNAME:
        if term in u:
            hits.append({
                'username': username,
                'evidence_type': 'provider_username',
                'evidence_text': term,
                'score_delta': -45,
                'source_table': 'profiles',
                'created_ts': now
            })
    
    return hits


def visit_and_extract_candidates():
    """Visit candidate profiles and extract evidence."""
    print("=" * 60)
    print("EVIDENCE EXTRACTION FROM CANDIDATE PROFILES")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get candidates worth visiting (increase limit for deeper intel)
    cursor.execute("""
        SELECT p.username, p.url, p.city, c.label, c.lead_value
        FROM profile_classifications c
        JOIN profiles p ON c.username = p.username
        WHERE c.label != 'provider_confirmed'
          AND p.username NOT IN (SELECT username FROM profile_visits)
        ORDER BY c.lead_value DESC
        LIMIT 100
    """)
    
    candidates = cursor.fetchall()
    conn.close()
    
    print(f"Found {len(candidates)} candidates to visit")
    
    if not candidates:
        print("No candidates found")
        return
    
    # Visit and extract
    results = []
    for i, (username, url, city, label, lead_value) in enumerate(candidates, 1):
        print(f"  [{i}/{len(candidates)}] Visiting {username}...")
        
        result = extract_evidence_from_visit(username)
        results.append(result)
        
        if result['success']:
            print(f"    Title: {result['title'][:60]}...")
            print(f"    Evidence hits: {len(result['evidence_hits'])}")
        else:
            print(f"    Error: {result['error']}")
        
        # Rate limiting
        if i < len(candidates):
            time.sleep(REQUEST_DELAY)
    
    # Store in database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    
    for result in results:
        if result['success']:
            # Store visit
            cursor.execute("""
                INSERT OR REPLACE INTO profile_visits
                (username, visited_ts, status, title, h1, meta_description, 
                 body_text, extracted_json, evidence_hash, http_status, error)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result['username'],
                now,
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
    
    conn.commit()
    conn.close()
    
    # Summary
    successful = sum(1 for r in results if r['success'])
    total_hits = sum(len(r['evidence_hits']) for r in results)
    
    print(f"\nExtraction complete:")
    print(f"  Successful visits: {successful}/{len(results)}")
    print(f"  Total evidence hits: {total_hits}")
    
    # Save results
    output_path = DATA_DIR / "evidence_extraction_results.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    visit_and_extract_candidates()
    print("\n=== COMPLETE ===")
