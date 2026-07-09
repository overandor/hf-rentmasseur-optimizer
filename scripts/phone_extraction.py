#!/usr/bin/env python3
"""
Phone Number Extraction from RentMasseur Profiles

Extracts phone numbers from profile pages for client outreach.
Internal use by RentMasseur staff.

Rate-limited to avoid detection and server load.
"""
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

# Rate limiting: delay between requests (seconds)
REQUEST_DELAY = 2.0


def extract_phone_from_html(html: str) -> Optional[str]:
    """Extract phone number from HTML content."""
    # Try to extract from JSON data first (more reliable)
    json_patterns = [
        r'"phone":"([^"]+)"',
        r'"phoneNumber":"([^"]+)"',
        r'"contactPhone":"([^"]+)"',
    ]
    
    for pattern in json_patterns:
        matches = re.findall(pattern, html)
        if matches:
            for match in matches:
                # Clean up the phone number
                phone = re.sub(r'[^\d+]', '', match)
                
                # Validate
                if len(phone) == 10 or (len(phone) == 11 and phone.startswith('1')):
                    if len(phone) == 11:
                        phone = phone[1:]
                    
                    # Valid area code
                    area_code = phone[:3]
                    if not area_code.startswith(('2', '3', '4', '5', '6', '7', '8', '9')):
                        continue
                    
                    # Valid exchange code
                    exchange = phone[3:6]
                    if not exchange.startswith(('2', '3', '4', '5', '6', '7', '8', '9')):
                        continue
                    
                    # Reject obviously fake patterns
                    if len(set(phone[-4:])) == 1:
                        continue
                    
                    if len(set(phone)) < 5:
                        continue
                    
                    return phone
    
    # If no JSON phone found, return None (HTML extraction too unreliable)
    return None


def extract_phone_from_profile(username: str) -> Dict[str, Any]:
    """Extract phone number from a profile page."""
    result = {
        'username': username,
        'phone': None,
        'email': None,
        'success': False,
        'error': None
    }
    
    try:
        url = f"https://rentmasseur.com/{username}"
        response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        
        if response.status_code == 200:
            html = response.text
            
            # Extract phone from HTML
            phone = extract_phone_from_html(html)
            
            # Extract email
            email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
            emails = re.findall(email_pattern, html)
            email = emails[0] if emails else None
            
            result['phone'] = phone
            result['email'] = email
            result['success'] = True
        else:
            result['error'] = f"HTTP {response.status_code}"
    
    except Exception as e:
        result['error'] = str(e)
    
    return result


def extract_phones_from_client_confirmed():
    """Extract phone numbers from client_confirmed profiles."""
    print("=" * 60)
    print("PHONE EXTRACTION FROM CLIENT CONFIRMED PROFILES")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get client_confirmed profiles
    cursor.execute("""
        SELECT p.username, p.url, p.city
        FROM profile_classifications c
        JOIN profiles p ON c.username = p.username
        WHERE c.label = 'client_confirmed'
    """)
    
    profiles = cursor.fetchall()
    conn.close()
    
    print(f"Found {len(profiles)} client_confirmed profiles")
    
    if not profiles:
        print("No client_confirmed profiles found")
        return
    
    # Extract phones sequentially with rate limiting
    results = []
    for i, (username, url, city) in enumerate(profiles, 1):
        print(f"  [{i}/{len(profiles)}] Processing {username}...")
        
        result = extract_phone_from_profile(username)
        results.append(result)
        
        if result['success']:
            if result['phone']:
                print(f"    Phone: {result['phone']}")
            else:
                print(f"    No phone found")
        else:
            print(f"    Error: {result['error']}")
        
        # Rate limiting delay
        if i < len(profiles):
            time.sleep(REQUEST_DELAY)
    
    # Update database with phone numbers
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    
    for result in results:
        if result['success'] and result['phone']:
            cursor.execute("""
                UPDATE profiles
                SET phone = ?, email = ?, last_seen_ts = ?
                WHERE username = ?
            """, (result['phone'], result['email'], now, result['username']))
    
    conn.commit()
    conn.close()
    
    # Summary
    phones_found = sum(1 for r in results if r['success'] and r['phone'])
    print(f"\nPhone numbers extracted: {phones_found}/{len(profiles)}")
    
    # Save results
    output_path = DATA_DIR / "phone_extraction_results.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Saved: {output_path}")


def extract_phones_from_verification_queue():
    """Extract phone numbers from verification queue (review-discovered clients)."""
    print("\n" + "=" * 60)
    print("PHONE EXTRACTION FROM VERIFICATION QUEUE")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get profiles from verification queue
    cursor.execute("""
        SELECT v.username, p.url, p.city
        FROM verification_queue v
        JOIN profiles p ON v.username = p.username
        WHERE v.priority = 'high'
    """)
    
    profiles = cursor.fetchall()
    conn.close()
    
    print(f"Found {len(profiles)} high-priority profiles in verification queue")
    
    if not profiles:
        print("No profiles found in verification queue")
        return
    
    # Extract phones sequentially with rate limiting
    results = []
    seen_phones = set()  # Track seen phone numbers to detect duplicates
    
    for i, (username, url, city) in enumerate(profiles, 1):
        print(f"  [{i}/{len(profiles)}] Processing {username}...")
        
        result = extract_phone_from_profile(username)
        
        if result['success'] and result['phone']:
            # Check if this phone number was already seen
            if result['phone'] in seen_phones:
                print(f"    Duplicate phone number detected: {result['phone']}")
                result['phone'] = None  # Mark as invalid
            else:
                seen_phones.add(result['phone'])
                print(f"    Phone: {result['phone']}")
        elif result['success']:
            print(f"    No phone found")
        else:
            print(f"    Error: {result['error']}")
        
        results.append(result)
        
        # Rate limiting delay
        if i < len(profiles):
            time.sleep(REQUEST_DELAY)
    
    # Update database with phone numbers
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    
    for result in results:
        if result['success'] and result['phone']:
            cursor.execute("""
                UPDATE profiles
                SET phone = ?, email = ?, last_seen_ts = ?
                WHERE username = ?
            """, (result['phone'], result['email'], now, result['username']))
    
    conn.commit()
    conn.close()
    
    # Summary
    phones_found = sum(1 for r in results if r['success'] and r['phone'])
    print(f"\nPhone numbers extracted: {phones_found}/{len(profiles)}")
    
    # Save results
    output_path = DATA_DIR / "phone_extraction_verification_queue.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Saved: {output_path}")


def extract_phones_from_all_profiles(limit: int = 50):
    """Extract phone numbers from all profiles (internal use)."""
    print("\n" + "=" * 60)
    print("PHONE EXTRACTION FROM ALL PROFILES")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get all profiles
    cursor.execute("""
        SELECT username, url, city
        FROM profiles
        WHERE phone IS NULL OR phone = ''
        LIMIT ?
    """, (limit,))
    
    profiles = cursor.fetchall()
    conn.close()
    
    print(f"Found {len(profiles)} profiles without phone numbers")
    
    if not profiles:
        print("No profiles found")
        return
    
    # Extract phones
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(extract_phone_from_profile, username): username for username, url, city in profiles}
        
        for future in as_completed(futures):
            username = futures[future]
            try:
                result = future.result()
                results.append(result)
                
                if result['success']:
                    if result['phone']:
                        print(f"  {username}: {result['phone']}")
                    else:
                        print(f"  {username}: No phone found")
                else:
                    print(f"  {username}: Error - {result['error']}")
            except Exception as e:
                print(f"  {username}: Exception - {e}")
    
    # Update database with phone numbers
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
    print(f"\nPhone numbers extracted: {phones_found}/{len(profiles)}")
    
    # Save results
    output_path = DATA_DIR / "phone_extraction_all_profiles.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"Saved: {output_path}")


def print_phone_summary():
    """Print summary of phone numbers in database."""
    print("\n" + "=" * 60)
    print("PHONE NUMBER SUMMARY")
    print("=" * 60)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Count profiles with phones
    cursor.execute("SELECT COUNT(*) FROM profiles WHERE phone IS NOT NULL AND phone != ''")
    phone_count = cursor.fetchone()[0]
    
    # Count total profiles
    cursor.execute("SELECT COUNT(*) FROM profiles")
    total_count = cursor.fetchone()[0]
    
    # Get client_confirmed with phones
    cursor.execute("""
        SELECT p.username, p.phone, p.email, c.label, c.lead_value
        FROM profiles p
        JOIN profile_classifications c ON p.username = c.username
        WHERE p.phone IS NOT NULL AND p.phone != ''
        ORDER BY c.lead_value DESC
    """)
    
    profiles_with_phones = cursor.fetchall()
    conn.close()
    
    print(f"\nTotal profiles: {total_count}")
    print(f"Profiles with phone numbers: {phone_count}")
    print(f"Coverage: {phone_count/total_count*100:.1f}%")
    
    if profiles_with_phones:
        print(f"\nProfiles with phone numbers:")
        for username, phone, email, label, lead_value in profiles_with_phones:
            print(f"  {username}: {phone} ({label}, lead_value: {lead_value})")
            if email:
                print(f"    Email: {email}")


if __name__ == "__main__":
    # Extract phones from client_confirmed
    extract_phones_from_client_confirmed()
    
    # Extract phones from verification queue
    extract_phones_from_verification_queue()
    
    # Extract phones from all profiles (optional)
    # extract_phones_from_all_profiles(limit=50)
    
    # Print summary
    print_phone_summary()
    
    print("\n=== PHONE EXTRACTION COMPLETE ===")
