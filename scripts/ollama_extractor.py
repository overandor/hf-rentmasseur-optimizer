#!/usr/bin/env python3
"""
Ollama-Based Intelligent Extraction Tool

Uses local LLM (via Ollama) to intelligently extract contact information
and classify profiles from RentMasseur.

Requires Ollama running locally: https://ollama.ai
Install: brew install ollama (Mac) or download from website
Run: ollama serve
Pull model: ollama pull llama3.2 or ollama pull mistral
"""
import json
import re
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
import requests

from rm_cic_exact_spec import DB_PATH, DATA_DIR

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Ollama configuration
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2"  # or "mistral", "llama2", etc.

# Rate limiting
REQUEST_DELAY = 3.0


def extract_with_ollama(html: str, username: str) -> Dict[str, Any]:
    """Use Ollama to extract contact information from profile HTML."""
    
    prompt = f"""You are analyzing a RentMasseur profile page for the user "{username}".

Extract the following information from the HTML content:
1. Phone number (if visible and legitimate)
2. Email address (if visible and legitimate)
3. Whether this is a client (seeking massage) or provider (offering massage)
4. Location/city
5. Any other contact information

Return ONLY a JSON object with this exact format:
{{
    "phone": "phone number or null",
    "email": "email address or null",
    "role": "client" or "provider" or "unknown",
    "city": "city name or null",
    "confidence": 0.0 to 1.0,
    "reasoning": "brief explanation"
}}

Rules:
- Only extract phone numbers that are clearly contact information, not random numbers
- Only extract emails that are clearly contact information
- A client is someone LOOKING FOR massage (e.g., "looking for", "need", "seeking")
- A provider is someone OFFERING massage (e.g., "masseur", "massage therapist", "rates", "book me")
- If unsure, return null for fields and set confidence low
- Return valid JSON only, no other text

HTML content:
{html[:10000]}"""

    try:
        response = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for consistent extraction
                "num_predict": 500
            }
        }, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            response_text = result.get('response', '')
            
            # Extract JSON from response
            json_match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)
            if json_match:
                try:
                    extracted = json.loads(json_match.group())
                    return {
                        'success': True,
                        'phone': extracted.get('phone'),
                        'email': extracted.get('email'),
                        'role': extracted.get('role'),
                        'city': extracted.get('city'),
                        'confidence': extracted.get('confidence'),
                        'reasoning': extracted.get('reasoning'),
                        'raw_response': response_text
                    }
                except json.JSONDecodeError:
                    return {
                        'success': False,
                        'error': 'Failed to parse JSON from LLM response',
                        'raw_response': response_text
                    }
            else:
                return {
                    'success': False,
                    'error': 'No JSON found in LLM response',
                    'raw_response': response_text
                }
        else:
            return {
                'success': False,
                'error': f'Ollama API error: {response.status_code}'
            }
    
    except requests.exceptions.ConnectionError:
        return {
            'success': False,
            'error': 'Cannot connect to Ollama. Is ollama serve running?'
        }
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def check_ollama():
    """Check if Ollama is running."""
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get('models', [])
            print(f"Ollama is running. Available models: {[m['name'] for m in models]}")
            return True
        return False
    except:
        print("Ollama is not running. Start with: ollama serve")
        return False


def extract_from_profile_with_ollama(username: str) -> Dict[str, Any]:
    """Extract information from a profile using Ollama."""
    result = {
        'username': username,
        'phone': None,
        'email': None,
        'role': None,
        'city': None,
        'confidence': 0,
        'success': False,
        'error': None
    }
    
    try:
        url = f"https://rentmasseur.com/{username}"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        
        if response.status_code == 200:
            html = response.text
            
            # Use Ollama to extract
            ollama_result = extract_with_ollama(html, username)
            
            if ollama_result['success']:
                result.update({
                    'phone': ollama_result['phone'],
                    'email': ollama_result['email'],
                    'role': ollama_result['role'],
                    'city': ollama_result['city'],
                    'confidence': ollama_result['confidence'],
                    'success': True
                })
            else:
                result['error'] = ollama_result['error']
        else:
            result['error'] = f"HTTP {response.status_code}"
    
    except Exception as e:
        result['error'] = str(e)
    
    return result


def extract_from_review_discovered_clients():
    """Extract information from review-discovered clients using Ollama."""
    print("=" * 60)
    print("OLLAMA-BASED EXTRACTION FROM REVIEW-DISCOVERED CLIENTS")
    print("=" * 60)
    
    # Check Ollama
    if not check_ollama():
        print("Cannot proceed without Ollama running")
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get review-discovered clients
    cursor.execute("""
        SELECT reviewer_name, provider_username, review_text
        FROM review_discovered_clients
        WHERE label = 'client_possible'
    """)
    
    reviewers = cursor.fetchall()
    conn.close()
    
    print(f"Found {len(reviewers)} review-discovered client candidates")
    
    if not reviewers:
        print("No review-discovered clients found")
        return
    
    # Extract using Ollama
    results = []
    for i, (reviewer_name, provider_username, review_text) in enumerate(reviewers, 1):
        print(f"  [{i}/{len(reviewers)}] Processing {reviewer_name}...")
        
        result = extract_from_profile_with_ollama(reviewer_name)
        results.append(result)
        
        if result['success']:
            print(f"    Phone: {result['phone']}")
            print(f"    Email: {result['email']}")
            print(f"    Role: {result['role']} (confidence: {result['confidence']})")
            print(f"    City: {result['city']}")
        else:
            print(f"    Error: {result['error']}")
        
        # Rate limiting
        if i < len(reviewers):
            time.sleep(REQUEST_DELAY)
    
    # Update database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    
    for result in results:
        if result['success']:
            cursor.execute("""
                UPDATE profiles
                SET phone = ?, email = ?, last_seen_ts = ?
                WHERE username = ?
            """, (result['phone'], result['email'], now, result['username']))
    
    conn.commit()
    conn.close()
    
    # Summary
    phones_found = sum(1 for r in results if r['success'] and r['phone'])
    emails_found = sum(1 for r in results if r['success'] and r['email'])
    
    print(f"\nExtraction complete:")
    print(f"  Phone numbers: {phones_found}")
    print(f"  Email addresses: {emails_found}")
    print(f"  Roles identified: {sum(1 for r in results if r['success'] and r['role'])}")
    
    # Save results
    output_path = DATA_DIR / "ollama_review_clients_extraction.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Saved: {output_path}")


def classify_with_ollama(username: str, title: str = "", body_text: str = "") -> Dict[str, Any]:
    """Use Ollama to classify a profile as client/provider."""
    
    prompt = f"""Classify this RentMasseur profile as either a "client" (seeking massage) or "provider" (offering massage).

Username: {username}
Title: {title}
Body: {body_text[:2000] if body_text else "N/A"}

Return ONLY a JSON object:
{{
    "label": "client_confirmed" or "provider_confirmed" or "unknown",
    "confidence": 0.0 to 1.0,
    "reasoning": "brief explanation"
}}

Rules:
- "client" = someone LOOKING FOR massage (e.g., "looking for", "need", "seeking", "want to book")
- "provider" = someone OFFERING massage (e.g., "masseur", "massage therapist", "rates", "book me", "I offer")
- If evidence is weak or mixed, return "unknown" with low confidence
- Return valid JSON only"""

    try:
        response = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "num_predict": 300
            }
        }, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            response_text = result.get('response', '')
            
            json_match = re.search(r'\{[^}]+\}', response_text, re.DOTALL)
            if json_match:
                try:
                    extracted = json.loads(json_match.group())
                    return {
                        'success': True,
                        'label': extracted.get('label'),
                        'confidence': extracted.get('confidence'),
                        'reasoning': extracted.get('reasoning')
                    }
                except json.JSONDecodeError:
                    pass
        
        return {'success': False, 'error': 'Failed to parse response'}
    
    except Exception as e:
        return {'success': False, 'error': str(e)}


if __name__ == "__main__":
    print("=" * 60)
    print("OLLAMA-BASED INTELLIGENT EXTRACTION TOOL")
    print("=" * 60)
    print("\nPrerequisites:")
    print("1. Install Ollama: https://ollama.ai")
    print("2. Run: ollama serve")
    print("3. Pull model: ollama pull llama3.2")
    print("\n" + "=" * 60)
    
    # Run extraction on review-discovered clients (real clients from reviews)
    extract_from_review_discovered_clients()
    
    print("\n=== COMPLETE ===")
