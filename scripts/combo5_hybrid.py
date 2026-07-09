#!/usr/bin/env python3
"""
Combo 5: Hybrid Multi-Strategy Combo
Tools: FlareSolverr + Residential Proxies + Craigslist + Reddit + Instagram

Requires:
- FlareSolverr running on localhost:8191 (Docker: docker run -p 8191:8191 glaurin/flaresolverr:latest)
- Residential proxy credentials
- Reddit API credentials (PRAW)
- Instagram credentials (instagrapi)
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

# Tool 1: FlareSolverr (Cloudflare bypass)
FLARESOLVERR_URL = "http://localhost:8191/v1"

# Tool 2: Residential Proxies (placeholder - requires credentials)
PROXY_CONFIG = {
    'enabled': False,
    'proxies': [
        # 'http://username:password@proxy1:port',
        # 'http://username:password@proxy2:port',
    ]
}

# Tool 3: Craigslist
CRAIGSLIST_CITIES = [
    'newyork', 'losangeles', 'chicago', 'miami', 'sanfrancisco',
    'seattle', 'boston', 'washingtondc', 'atlanta', 'denver'
]

# Tool 4: Reddit (requires PRAW credentials)
REDDIT_CONFIG = {
    'enabled': False,
    'client_id': '',
    'client_secret': '',
    'user_agent': ''
}

# Tool 5: Instagram (requires credentials)
INSTAGRAM_CONFIG = {
    'enabled': False,
    'username': '',
    'password': ''
}


def check_flaresolverr():
    """Check if FlareSolverr is running"""
    try:
        response = requests.get(FLARESOLVERR_URL, timeout=5)
        return response.status_code == 200
    except:
        return False


def scrape_via_flaresolverr(url: str) -> Optional[str]:
    """Scrape URL using FlareSolverr to bypass Cloudflare"""
    try:
        response = requests.post(FLARESOLVERR_URL, json={
            'cmd': 'request.get',
            'url': url,
            'maxTimeout': 60000
        }, timeout=90)
        
        if response.status_code == 200:
            result = response.json()
            if result.get('solution', {}).get('status') == 'success':
                return result['solution'].get('response')
            return result.get('solution', {}).get('response')
        
        return None
    except Exception as e:
        print(f"  FlareSolverr error: {e}")
        return None


def scrape_craigslist_with_flaresolverr(city: str) -> List[Dict[str, Any]]:
    """Scrape Craigslist using FlareSolverr"""
    results = []
    
    if not check_flaresolverr():
        print(f"  {city}: FlareSolverr not running. Start with: docker run -p 8191:8191 glaurin/flaresolverr:latest")
        return results
    
    try:
        url = f'https://{city}.craigslist.org/search/sss'
        params = {'query': 'massage', 'sort': 'date'}
        
        # Use FlareSolverr
        full_url = f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}"
        html = scrape_via_flaresolverr(full_url)
        
        if html:
            soup = BeautifulSoup(html, 'html.parser')
            posts = soup.find_all('li', class_='result-row')
            
            for post in posts[:25]:
                try:
                    title_elem = post.find('a', class_='result-title')
                    link_elem = post.find('a', class_='result-title')
                    price_elem = post.find('span', class_='result-price')
                    location_elem = post.find('span', class_='result-hood')
                    
                    if title_elem and link_elem:
                        results.append({
                            'platform': 'craigslist',
                            'city': city,
                            'title': title_elem.get_text(strip=True),
                            'price': price_elem.get_text(strip=True) if price_elem else None,
                            'location': location_elem.get_text(strip=True) if location_elem else None,
                            'url': link_elem.get('href'),
                            'scraped_at': datetime.now(timezone.utc).isoformat(),
                            'method': 'flaresolverr'
                        })
                except:
                    continue
            
            print(f"  {city}: {len(results)} posts (FlareSolverr)")
        else:
            print(f"  {city}: FlareSolverr returned no data")
    
    except Exception as e:
        print(f"  {city}: Failed - {e}")
    
    return results


def scrape_reddit_with_praw() -> List[Dict[str, Any]]:
    """Scrape Reddit using PRAW"""
    results = []
    
    if not REDDIT_CONFIG['enabled']:
        print("  Reddit: Not configured (requires PRAW credentials)")
        return results
    
    try:
        import praw
        reddit = praw.Reddit(
            client_id=REDDIT_CONFIG['client_id'],
            client_secret=REDDIT_CONFIG['client_secret'],
            user_agent=REDDIT_CONFIG['user_agent']
        )
        
        subreddits = ['massage', 'FindAMasseur', 'r4r', 'newyork', 'losangeles']
        
        for sub in subreddits:
            try:
                for post in reddit.subreddit(sub).new(limit=50):
                    if 'looking for' in post.title.lower() or 'need massage' in post.title.lower():
                        results.append({
                            'platform': 'reddit',
                            'subreddit': sub,
                            'title': post.title,
                            'body': post.selftext[:500],
                            'url': post.url,
                            'scraped_at': datetime.now(timezone.utc).isoformat(),
                            'method': 'praw'
                        })
            except Exception as e:
                print(f"  Reddit {sub}: Failed - {e}")
        
        print(f"  Reddit: {len(results)} posts")
    
    except ImportError:
        print("  Reddit: PRAW not installed (pip install praw)")
    except Exception as e:
        print(f"  Reddit: Failed - {e}")
    
    return results


def scrape_instagram_with_api() -> List[Dict[str, Any]]:
    """Scrape Instagram using instagrapi"""
    results = []
    
    if not INSTAGRAM_CONFIG['enabled']:
        print("  Instagram: Not configured (requires credentials)")
        return results
    
    try:
        from instagrapi import Client
        client = Client()
        client.login(INSTAGRAM_CONFIG['username'], INSTAGRAM_CONFIG['password'])
        
        hashtag = client.hashtag_info('massage')
        
        for post in client.hashtag_medias_top(hashtag, amount=50):
            try:
                results.append({
                    'platform': 'instagram',
                    'hashtag': 'massage',
                    'caption': post.caption_text[:500] if post.caption_text else '',
                    'location': post.location.name if post.location else None,
                    'url': f'https://instagram.com/p/{post.code}/',
                    'scraped_at': datetime.now(timezone.utc).isoformat(),
                    'method': 'instagrapi'
                })
            except:
                continue
        
        print(f"  Instagram: {len(results)} posts")
    
    except ImportError:
        print("  Instagram: instagrapi not installed (pip install instagrapi)")
    except Exception as e:
        print(f"  Instagram: Failed - {e}")
    
    return results


def classify_with_rmcic(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a profile using RM-CIC logic"""
    from client_intent_classifier import classify_profile
    
    rmcic_profile = {
        'username': profile.get('title', '')[:30],
        'name': profile.get('title', ''),
        'city': profile.get('city', profile.get('location', '')),
        'url': profile.get('url', ''),
        'title': profile.get('title', ''),
        'body_text': profile.get('body', '')
    }
    
    classification = classify_profile(rmcic_profile)
    classification['platform'] = profile.get('platform')
    classification['scraped_at'] = profile.get('scraped_at')
    classification['method'] = profile.get('method')
    
    return classification


def save_to_database(results: List[Dict[str, Any]]):
    """Save results to SQLite database"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
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
            method TEXT,
            created_ts TEXT
        )
    """)
    
    for result in results:
        cursor.execute("""
            INSERT OR REPLACE INTO external_discovery
            (platform, city, title, url, label, client_score, lead_value, confidence, scraped_at, method, created_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            result.get('method'),
            datetime.now(timezone.utc).isoformat()
        ))
    
    conn.commit()
    conn.close()
    print(f"Saved {len(results)} results to database")


def run_hybrid_combo():
    """Run Combo 5: Hybrid Multi-Strategy Combo"""
    print("=" * 60)
    print("COMBO 5: HYBRID MULTI-STRATEGY COMBO")
    print("=" * 60)
    
    # Check FlareSolverr
    print("\n[0] Checking FlareSolverr...")
    if check_flaresolverr():
        print("  FlareSolverr: Running ✓")
    else:
        print("  FlareSolverr: Not running ✗")
        print("  Start with: docker run -p 8191:8191 glaurin/flaresolverr:latest")
        print("  Continuing without FlareSolverr...")
    
    all_results = []
    
    # Scrape Craigslist with FlareSolverr
    print("\n[1] Scraping Craigslist with FlareSolverr...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(scrape_craigslist_with_flaresolverr, city) for city in CRAIGSLIST_CITIES]
        for future in as_completed(futures):
            results = future.result()
            all_results.extend(results)
    
    # Scrape Reddit
    print("\n[2] Scraping Reddit with PRAW...")
    reddit_results = scrape_reddit_with_praw()
    all_results.extend(reddit_results)
    
    # Scrape Instagram
    print("\n[3] Scraping Instagram with instagrapi...")
    instagram_results = scrape_instagram_with_api()
    all_results.extend(instagram_results)
    
    print(f"\n[4] Total raw results: {len(all_results)}")
    
    # Classify
    print(f"\n[5] Classifying with RM-CIC...")
    classified = []
    for result in all_results:
        try:
            classification = classify_with_rmcic(result)
            classified.append(classification)
        except Exception as e:
            print(f"  Classification failed: {e}")
    
    # Filter client candidates
    client_candidates = [c for c in classified if c['label'] in ['client_confirmed', 'client_possible']]
    
    print(f"\n[6] Client candidates: {len(client_candidates)}")
    
    # Save
    print(f"\n[7] Saving to database...")
    save_to_database(classified)
    
    # Save JSON
    output_path = DATA_DIR / "combo5_hybrid_results.json"
    with open(output_path, 'w') as f:
        json.dump(classified, f, indent=2)
    print(f"Saved: {output_path}")
    
    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total results: {len(classified)}")
    print(f"Client confirmed: {sum(1 for c in classified if c['label'] == 'client_confirmed')}")
    print(f"Client possible: {sum(1 for c in classified if c['label'] == 'client_possible')}")
    print(f"By method:")
    for method in set(c.get('method', 'unknown') for c in classified):
        count = sum(1 for c in classified if c.get('method') == method)
        print(f"  {method}: {count}")
    
    print("\nTop client candidates:")
    for c in sorted(client_candidates, key=lambda x: x.get('lead_value', 0), reverse=True)[:10]:
        print(f"  {c.get('title', 'unknown')[:50]}: {c['label']} (lead_value: {c.get('lead_value', 0)})")
    
    print("\n=== COMPLETE ===")


if __name__ == "__main__":
    run_hybrid_combo()
