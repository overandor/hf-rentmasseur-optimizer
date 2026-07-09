#!/usr/bin/env python3
"""
Manhattan Review Extractor - HTTP Only

Extract reviews from Manhattan profiles using HTTP requests (no login required for public profiles).
"""
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"

DATA_DIR.mkdir(parents=True, exist_ok=True)
RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)


def extract_reviews_from_profile(username: str) -> Dict:
    """Extract reviews from a profile page using HTTP."""
    import requests as req

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Referer": "https://rentmasseur.com",
    }

    url = f"https://rentmasseur.com/{username}"
    result = {
        "username": username,
        "url": url,
        "reviews": [],
        "error": None
    }

    try:
        r = req.get(url, headers=headers, timeout=15, allow_redirects=True)
        if r.status_code != 200:
            result["error"] = f"HTTP {r.status_code}"
            return result

        text = r.text

        # Look for review sections - try multiple patterns
        # Pattern 1: Review cards with class
        review_patterns = [
            r'<div[^>]*class="[^"]*review[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*testimonial[^"]*"[^>]*>(.*?)</div>',
            r'<div[^>]*class="[^"]*comment[^"]*"[^>]*>(.*?)</div>',
        ]

        for pattern in review_patterns:
            reviews = re.findall(pattern, text, re.IGNORECASE | re.DOTALL)
            if reviews:
                for review_html in reviews:
                    reviewer = extract_reviewer_info(review_html)
                    if reviewer:
                        result["reviews"].append(reviewer)
                break

        # If no reviews found with div patterns, try looking for review text directly
        if not result["reviews"]:
            # Look for patterns like "Great massage" or "Excellent service" in text
            text_patterns = [
                r'(Great|Excellent|Amazing|Wonderful|Fantastic|Professional|Best|Good|Amazing).{0,100}(massage|session|experience|service)',
            ]
            for pattern in text_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                if matches:
                    for match in matches:
                        result["reviews"].append({
                            "text": match[0] + " " + match[1],
                            "extracted_from": "text_pattern"
                        })

    except Exception as e:
        result["error"] = str(e)[:100]

    return result


def extract_reviewer_info(review_html: str) -> Dict:
    """Extract reviewer info from review HTML."""
    reviewer = {
        "name": None,
        "location": None,
        "rating": None,
        "text": None,
        "date": None
    }

    # Try to extract name
    name_patterns = [
        r'<h3[^>]*>([^<]+)</h3>',
        r'<h4[^>]*>([^<]+)</h4>',
        r'<span[^>]*class="[^"]*name[^"]*"[^>]*>([^<]+)</span>',
        r'<strong[^>]*>([^<]+)</strong>',
    ]
    for pattern in name_patterns:
        match = re.search(pattern, review_html, re.IGNORECASE)
        if match:
            reviewer["name"] = match.group(1).strip()
            break

    # Try to extract location
    loc_patterns = [
        r'(New York|NYC|Manhattan|Brooklyn|Queens|Bronx|Staten Island|NY|NJ|CT|Los Angeles|LA|Chicago|Miami|San Francisco|Boston|DC|Atlanta|Dallas|Houston|Seattle|Portland|Denver|Phoenix|San Diego|Austin|Nashville)',
    ]
    for pattern in loc_patterns:
        match = re.search(pattern, review_html, re.IGNORECASE)
        if match:
            reviewer["location"] = match.group(1)
            break

    # Try to extract text
    text_patterns = [
        r'<p[^>]*>([^<]+)</p>',
        r'<div[^>]*class="[^"]*text[^"]*"[^>]*>([^<]+)</div>',
    ]
    for pattern in text_patterns:
        match = re.search(pattern, review_html, re.IGNORECASE)
        if match:
            reviewer["text"] = match.group(1).strip()
            break

    # Only return if we have some useful info
    if reviewer["name"] or reviewer["text"] or reviewer["location"]:
        return reviewer
    return None


def main():
    print("=== MANHATTAN REVIEW EXTRACTOR (HTTP ONLY) ===")

    # Load NY users (includes Manhattan)
    ny_file = DATA_DIR / "ny_users.json"
    with open(ny_file) as f:
        ny_data = json.load(f)
    ny_users = ny_data.get("users", [])

    # Filter Manhattan profiles
    manhattan_profiles = [p for p in ny_users if "manhattan" in p.get("city", "").lower()]
    print(f"\n[1] Loaded {len(manhattan_profiles)} Manhattan profiles from ny_users.json")

    if not manhattan_profiles:
        print("No Manhattan profiles found")
        return

    # Extract reviews
    print(f"\n[2] Extracting reviews from {len(manhattan_profiles)} profiles (33 threads)...")
    t0 = time.time()

    def extract_one(p):
        return extract_reviews_from_profile(p["username"])

    review_results = []
    with ThreadPoolExecutor(max_workers=33) as pool:
        futures = {pool.submit(extract_one, p): p for p in manhattan_profiles}
        for i, fut in enumerate(as_completed(futures)):
            r = fut.result()
            review_results.append(r)
            if (i + 1) % 20 == 0 or i == len(manhattan_profiles) - 1:
                with_reviews = sum(1 for x in review_results if x["reviews"])
                print(f"  [{i+1}/{len(manhattan_profiles)}] profiles with reviews: {with_reviews}")

    elapsed = time.time() - t0
    print(f"  Done: {len(review_results)} profiles, {elapsed:.1f}s")

    # Aggregate reviews
    print("\n[3] Aggregating reviews...")
    all_reviews = []
    ny_reviewers = {}

    for result in review_results:
        if result["reviews"]:
            for review in result["reviews"]:
                review["provider_username"] = result["username"]
                all_reviews.append(review)

                # Track NY reviewers
                if review.get("location") and any(loc in review["location"].lower() for loc in ["new york", "nyc", "manhattan", "brooklyn", "queens", "bronx", "ny"]):
                    reviewer_name = review.get("name") or "anonymous"
                    if reviewer_name not in ny_reviewers:
                        ny_reviewers[reviewer_name] = {
                            "name": reviewer_name,
                            "location": review.get("location"),
                            "reviews": [],
                            "providers_seen": []
                        }
                    ny_reviewers[reviewer_name]["reviews"].append(review)
                    ny_reviewers[reviewer_name]["providers_seen"].append(result["username"])

    print(f"  Total reviews: {len(all_reviews)}")
    print(f"  NY reviewers: {len(ny_reviewers)}")

    # Save results
    (DATA_DIR / "manhattan_reviews.json").write_text(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_reviews": len(all_reviews),
        "ny_reviewers_count": len(ny_reviewers),
        "all_reviews": all_reviews,
        "ny_reviewers": ny_reviewers
    }, indent=2))
    print(f"  Saved: {DATA_DIR / 'manhattan_reviews.json'}")

    # Save receipt
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    (RECEIPTS_DIR / f"manhattan_reviews_{ts}.json").write_text(json.dumps({
        "action": "manhattan_review_extraction_http",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "profiles_scraped": len(manhattan_profiles),
        "total_reviews": len(all_reviews),
        "ny_reviewers": len(ny_reviewers),
        "elapsed_seconds": elapsed
    }, indent=2))
    print(f"  Receipt: {RECEIPTS_DIR / f'manhattan_reviews_{ts}.json'}")

    print("\n=== COMPLETE ===")
    print(f"Manhattan profiles: {len(manhattan_profiles)}")
    print(f"Total reviews extracted: {len(all_reviews)}")
    print(f"NY reviewers found: {len(ny_reviewers)}")
    print(f"These NY reviewers are confirmed clients (they left reviews)")


if __name__ == "__main__":
    main()
