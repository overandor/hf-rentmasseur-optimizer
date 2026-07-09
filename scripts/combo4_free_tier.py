#!/usr/bin/env python3
"""
Combo 4: Free Tier Hyper Combo
Tools: Browserless.io + Puppeteer Extra + Craigslist + Reddit + Twitter

Free multi-platform discovery engine with zero cost.
"""
import json
import re
import sqlite3
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "rm_cic.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Tool 1: Browserless.io (Free Tier)
BROWSERLESS_URL = "https://chrome.browserless.io/content"

# Tool 2: Craigslist (Free)
CRAIGSLIST_CITIES = [
    'newyork', 'losangeles', 'chicago', 'miami', 'sanfrancisco',
    'seattle', 'boston', 'washingtondc', 'atlanta', 'denver'
]

# Try different Craigslist sections
CRAIGSLIST_SECTIONS = ['sss', 'ggg', 'hhh']  # services, gigs, housing

# Tool 3: Reddit (Free API - requires credentials)
# Placeholder for PRAW setup

# Tool 4: Twitter (Free API - requires bearer token)
# Placeholder for Twitter API setup

# Tool 5: Generic stealth via requests
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}


def scrape_craigslist_via_browserless(city: str, query: str = "massage") -> List[Dict[str, Any]]:
    """Scrape Craigslist using Browserless.io to avoid detection"""
    results = []
    
    try:
        # Try different sections
        for section in CRAIGSLIST_SECTIONS:
            url = f'https://{city}.craigslist.org/search/{section}'
            params = {
                'query': query,
                'sort': 'date'
            }
            
            # Use Browserless.io as proxy
            browserless_params = {
                'url': url,
                **{k: v for k, v in params.items()}
            }
            
            response = requests.get(BROWSERLESS_URL, params=browserless_params, headers=HEADERS, timeout=30)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Try multiple selectors
                posts = soup.find_all('li', class_='result-row')
                if not posts:
                    posts = soup.find_all('div', class_='result-row')
                if not posts:
                    posts = soup.find_all('a', class_='result-title')
                
                for post in posts[:25]:  # Limit to 25 per city
                    try:
                        # Handle both li and a elements
                        if post.name == 'a':
                            title_elem = post
                            link_elem = post
                        else:
                            title_elem = post.find('a', class_='result-title')
                            link_elem = post.find('a', class_='result-title')
                        
                        price_elem = post.find('span', class_='result-price')
                        location_elem = post.find('span', class_='result-hood')
                        
                        if title_elem and link_elem:
                            results.append({
                                'platform': 'craigslist',
                                'city': city,
                                'section': section,
                                'title': title_elem.get_text(strip=True),
                                'price': price_elem.get_text(strip=True) if price_elem else None,
                                'location': location_elem.get_text(strip=True) if location_elem else None,
                                'url': link_elem.get('href'),
                                'scraped_at': datetime.now(timezone.utc).isoformat()
                            })
                    except Exception as e:
                        continue
                
                if results:
                    print(f"  {city} ({section}): {len(results)} posts")
                    break  # Stop if we found results in this section
        
        if not results:
            print(f"  {city}: No results found")
        
    except Exception as e:
        print(f"  {city}: Failed - {e}")
    
    return results


def scrape_craigslist_direct(city: str, query: str = "looking for massage") -> List[Dict[str, Any]]:
    """Fallback: Direct Craigslist scraping (may be rate-limited)"""
    results = []
    
    try:
        url = f'https://{city}.craigslist.org/search/sss'
        params = {
            'query': query,
            'sort': 'date'
        }
        
        response = requests.get(url, params=params, headers=HEADERS, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            posts = soup.find_all('li', class_='result-row')
            
            for post in posts[:25]:
                try:
                    title_elem = post.find('a', class_='result-title')
                    link_elem = post.find('a', class_='result-title')
                    
                    if title_elem and link_elem:
                        results.append({
                            'platform': 'craigslist',
                            'city': city,
                            'title': title_elem.get_text(strip=True),
                            'url': link_elem.get('href'),
                            'scraped_at': datetime.now(timezone.utc).isoformat()
                        })
                except:
                    continue
        
        print(f"  {city} (direct): {len(results)} posts")
        
    except Exception as e:
        print(f"  {city} (direct): Failed - {e}")
    
    return results


def scrape_reddit_mock() -> List[Dict[str, Any]]:
    """Mock Reddit scraper (requires PRAW credentials)"""
    # In production, implement with PRAW:
    # import praw
    # reddit = praw.Reddit(client_id='...', client_secret='...', user_agent='...')
    # subreddits = ['massage', 'FindAMasseur', 'r4r']
    # for sub in subreddits:
    #     for post in reddit.subreddit(sub).new(limit=50):
    #         if 'looking for' in post.title.lower():
    #             results.append({...})
    
    print("  Reddit: Mock (requires PRAW credentials)")
    return []


def scrape_twitter_mock() -> List[Dict[str, Any]]:
    """Mock Twitter scraper (requires API credentials)"""
    # In production, implement with tweepy:
    # import tweepy
    # client = tweepy.Client(bearer_token='...')
    # query = 'looking for massage -is:retweet lang:en'
    # tweets = client.search_recent_tweets(query=query, max_results=100)
    
    print("  Twitter: Mock (requires API credentials)")
    return []


def classify_with_rmcic(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a profile using RM-CIC logic"""
    from client_intent_classifier import classify_profile
    
    # Map to RM-CIC format
    rmcic_profile = {
        'username': profile.get('title', '')[:30],  # Use title as username
        'name': profile.get('title', ''),
        'city': profile.get('city', profile.get('location', '')),
        'url': profile.get('url', ''),
        'title': profile.get('title', ''),
        'body_text': ''
    }
    
    classification = classify_profile(rmcic_profile)
    
    # Add original data
    classification['platform'] = profile.get('platform')
    classification['scraped_at'] = profile.get('scraped_at')
    
    return classification


def save_to_database(results: List[Dict[str, Any]]):
    """Save results to SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Create table if not exists
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS external_discovery (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT,
            city TEXT,
            title TEXT,
            url TEXT,
            label TEXT,
            client_score REAL,
            lead_value REAL,
            confidence REAL,
            scraped_at TEXT,
            created_ts TEXT
        )
    """)
    
    for result in results:
        cursor.execute("""
            INSERT OR REPLACE INTO external_discovery
            (platform, city, title, url, label, client_score, lead_value, confidence, scraped_at, created_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result.get('platform'),
            result.get('city'),
            result.get('title'),
            result.get('url'),
            result.get('label'),
            result.get('client_score'),
            result.get('lead_value'),
            result.get('confidence'),
            result.get('scraped_at'),
            datetime.now(timezone.utc).isoformat()
        ))
    
    conn.commit()
    conn.close()
    print(f"Saved {len(results)} results to database")


def run_free_tier_combo():
    """Run Combo 4: Free Tier Hyper Combo"""
    print("=" * 60)
    print("COMBO 4: FREE TIER HYPER COMBO")
    print("=" * 60)
    print("\n[1] Scraping Craigslist via Browserless.io...")
    
    all_results = []
    
    # Try Browserless first, fallback to direct
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = []
        for city in CRAIGSLIST_CITIES:
            future = executor.submit(scrape_craigslist_via_browserless, city)
            futures.append(future)
        
        for future in as_completed(futures):
            results = future.result()
            all_results.extend(results)
    
    # If Browserless failed, try direct scraping
    if len(all_results) < 50:
        print("\n[1b] Browserless returned low results, trying direct scraping...")
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = []
            for city in CRAIGSLIST_CITIES:
                future = executor.submit(scrape_craigslist_direct, city)
                futures.append(future)
            
            for future in as_completed(futures):
                results = future.result()
                all_results.extend(results)
    
    print(f"\n[2] Scraping Reddit (mock - requires credentials)...")
    reddit_results = scrape_reddit_mock()
    all_results.extend(reddit_results)
    
    print(f"\n[3] Scraping Twitter (mock - requires credentials)...")
    twitter_results = scrape_twitter_mock()
    all_results.extend(twitter_results)
    
    print(f"\n[4] Total raw results: {len(all_results)}")
    
    # Classify with RM-CIC
    print(f"\n[5] Classifying with RM-CIC...")
    classified = []
    for result in all_results:
        try:
            classification = classify_with_rmcic(result)
            classified.append(classification)
        except Exception as e:
            print(f"  Classification failed for {result.get('title', 'unknown')}: {e}")
    
    # Filter for client candidates
    client_candidates = [c for c in classified if c['label'] in ['client_confirmed', 'client_possible']]
    
    print(f"\n[6] Client candidates: {len(client_candidates)}")
    
    # Save to database
    print(f"\n[7] Saving to database...")
    save_to_database(classified)
    
    # Save to JSON
    output_path = DATA_DIR / "combo4_free_tier_results.json"
    with open(output_path, 'w') as f:
        json.dump(classified, f, indent=2)
    print(f"Saved: {output_path}")
    
    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total results: {len(classified)}")
    print(f"Client confirmed: {sum(1 for c in classified if c['label'] == 'client_confirmed')}")
    print(f"Client possible: {sum(1 for c in classified if c['label'] == 'client_possible')}")
    print(f"Unknown: {sum(1 for c in classified if c['label'] == 'unknown')}")
    print(f"Provider possible: {sum(1 for c in classified if c['label'] == 'provider_possible')}")
    print(f"Provider confirmed: {sum(1 for c in classified if c['label'] == 'provider_confirmed')}")
    
    print("\nTop client candidates:")
    for c in sorted(client_candidates, key=lambda x: x.get('lead_value', 0), reverse=True)[:10]:
        print(f"  {c.get('title', 'unknown')[:50]}: {c['label']} (lead_value: {c.get('lead_value', 0)})")
    
    print("\n=== COMPLETE ===")


if __name__ == "__main__":
    run_free_tier_combo()
