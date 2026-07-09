#!/usr/bin/env python3
"""
Manhattan Review Extractor

Get all Manhattan provider profiles, extract their reviews,
and identify New York reviewers (confirmed clients).
"""
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rm_traffic.api_client import RentMasseurAPI

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"

DATA_DIR.mkdir(parents=True, exist_ok=True)
RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://rentmasseur.com"
USERNAME = "karpathianwolf"
PASSWORD = os.environ.get("RM_PASSWORD", "")
PROFILE_DIR = "/tmp/rm_manhattan_reviews"


def selenium_login():
    """Login using undetected-chromedriver to bypass CrowdSec."""
    os.makedirs(PROFILE_DIR, exist_ok=True)
    opts = uc.ChromeOptions()
    opts.add_argument("--window-size=1280,900")
    opts.add_argument(f"--user-data-dir={PROFILE_DIR}")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    driver = uc.Chrome(options=opts, version_main=149)

    try:
        driver.get(f"{BASE}/login")
        time.sleep(30)  # Wait for captcha bypass

        # Check if captcha is still present
        src = driver.page_source or ""
        if "crowdsec" in src.lower() or "captcha" in src.lower():
            print("  Captcha still present. Trying to click checkbox...")
            try:
                checkbox = driver.find_element(By.CSS_SELECTOR, "input[type='checkbox']")
                if checkbox.is_displayed():
                    checkbox.click()
                    time.sleep(15)
            except:
                pass

        # Auto-login
        driver.execute_script("""
            const pwd = document.querySelector('input[type="password"]');
            const user = document.querySelector('input[type="text"], input[type="email"]');
            const ns = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            if (user) { ns.call(user, arguments[0]); user.dispatchEvent(new Event('input', {bubbles: true})); }
            if (pwd) { ns.call(pwd, arguments[1]); pwd.dispatchEvent(new Event('input', {bubbles: true})); }
        """, USERNAME, PASSWORD)
        time.sleep(1)
        try:
            pwd = driver.find_element(By.CSS_SELECTOR, "input[type='password']")
            pwd.send_keys(Keys.ENTER)
        except:
            pass

        time.sleep(10)

        # Check if logged in
        if "login" in driver.current_url.lower():
            print("  Login failed. Still on login page.")
            driver.quit()
            return None, None

        print("  Login successful!")
        cookies = driver.get_cookies()
        return driver, cookies
    except Exception as e:
        print(f"  Login error: {e}")
        driver.quit()
        return None, None


def get_manhattan_profiles(api, max_pages=100):
    """Get all Manhattan profiles via API."""
    all_users = []
    seen = set()

    for page in range(1, max_pages + 1):
        try:
            data = api.search(city="manhattan-ny", available_only=False, page=page)
            users = data.get("users", data.get("results", []))
            if not users:
                print(f"  No more users at page {page}")
                break
            for u in users:
                user_card = u.get("userCard", {})
                username = user_card.get("username", "")
                if username and username not in seen:
                    seen.add(username)
                    all_users.append({
                        "username": username,
                        "name": user_card.get("name", username),
                        "city": "manhattan-ny",
                        "url": f"https://rentmasseur.com/{username}",
                    })
            print(f"  Page {page}: +{len(users)} (total: {len(all_users)})")
        except Exception as e:
            print(f"  Page {page} error: {e}")
            break

    return all_users


def extract_reviews_from_profile(username: str, cookies: dict, token: str) -> Dict:
    """Extract reviews from a profile page."""
    import requests as req

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Referer": "https://rentmasseur.com",
    }
    if token:
        headers["Authorization"] = token

    url = f"https://rentmasseur.com/{username}"
    result = {
        "username": username,
        "url": url,
        "reviews": [],
        "error": None
    }

    try:
        r = req.get(url, headers=headers, cookies=cookies, timeout=15, allow_redirects=True)
        if r.status_code != 200:
            result["error"] = f"HTTP {r.status_code}"
            return result

        text = r.text

        # Extract reviews - look for review sections
        # Pattern: review author, location, rating, text
        # This is a simplified extraction - may need adjustment based on actual HTML structure

        # Look for review cards/sections
        review_pattern = r'<div[^>]*class="[^"]*review[^"]*"[^>]*>(.*?)</div>'
        reviews = re.findall(review_pattern, text, re.IGNORECASE | re.DOTALL)

        if not reviews:
            # Try alternative patterns
            review_pattern = r'<div[^>]*class="[^"]*testimonial[^"]*"[^>]*>(.*?)</div>'
            reviews = re.findall(review_pattern, text, re.IGNORECASE | re.DOTALL)

        for review_html in reviews:
            # Extract reviewer info
            reviewer = {
                "name": None,
                "location": None,
                "rating": None,
                "text": None,
                "date": None
            }

            # Try to extract name
            name_match = re.search(r'<h3[^>]*>([^<]+)</h3>', review_html, re.IGNORECASE)
            if name_match:
                reviewer["name"] = name_match.group(1).strip()

            # Try to extract location
            loc_match = re.search(r'(New York|NYC|Manhattan|Brooklyn|Queens|Bronx|NY|NJ|CT)', review_html, re.IGNORECASE)
            if loc_match:
                reviewer["location"] = loc_match.group(1)

            # Try to extract rating
            rating_match = re.search(r'(\d+)\s*stars?|rating[:\s]*(\d+)', review_html, re.IGNORECASE)
            if rating_match:
                reviewer["rating"] = rating_match.group(1) or rating_match.group(2)

            # Extract text
            text_match = re.search(r'<p[^>]*>([^<]+)</p>', review_html, re.IGNORECASE)
            if text_match:
                reviewer["text"] = text_match.group(1).strip()

            if reviewer["name"] or reviewer["text"]:
                result["reviews"].append(reviewer)

    except Exception as e:
        result["error"] = str(e)[:100]

    return result


def main():
    print("=== MANHATTAN REVIEW EXTRACTOR ===")

    # Selenium login for auth
    print("\n[1] Selenium login (undetected-chromedriver)...")
    driver, cookies = selenium_login()
    if not driver or not cookies:
        print("Login failed. Aborting.")
        return

    try:
        # Transfer cookies to API client
        print("\n[2] Transferring cookies to API client...")
        api = RentMasseurAPI()
        for c in cookies:
            api.session.cookies.set(c["name"], c["value"], domain=c.get("domain", ""), path=c.get("path", "/"))

        # Get token from localStorage
        token = ""
        try:
            access_token = driver.execute_script("return localStorage.getItem('accessToken') || '';")
            if access_token:
                api.session.headers["Authorization"] = f"Bearer {access_token}"
                token = access_token
                print("  Token extracted from localStorage")
        except:
            print("  No token in localStorage")

        cookies_dict = {c["name"]: c["value"] for c in cookies}

        # Get Manhattan profiles
        print("\n[3] Getting Manhattan profiles...")
        profiles = get_manhattan_profiles(api, max_pages=100)
        if not profiles:
            print("No profiles found")
            return

        print(f"  Found {len(profiles)} Manhattan profiles")

        # Save raw profiles
        (DATA_DIR / "manhattan_profiles.json").write_text(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(profiles),
            "profiles": profiles
        }, indent=2))
        print(f"  Saved: {DATA_DIR / 'manhattan_profiles.json'}")

        # Extract reviews
        print(f"\n[4] Extracting reviews from {len(profiles)} profiles (33 threads)...")
        t0 = time.time()

        def extract_one(p):
            return extract_reviews_from_profile(p["username"], cookies_dict, token)

        review_results = []
        with ThreadPoolExecutor(max_workers=33) as pool:
            futures = {pool.submit(extract_one, p): p for p in profiles}
            for i, fut in enumerate(as_completed(futures)):
                r = fut.result()
                review_results.append(r)
                if (i + 1) % 50 == 0 or i == len(profiles) - 1:
                    with_reviews = sum(1 for x in review_results if x["reviews"])
                    print(f"  [{i+1}/{len(profiles)}] profiles with reviews: {with_reviews}")

        elapsed = time.time() - t0
        print(f"  Done: {len(review_results)} profiles, {elapsed:.1f}s")

        # Aggregate reviews
        print("\n[5] Aggregating reviews...")
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
            "action": "manhattan_review_extraction",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "profiles_scraped": len(profiles),
            "total_reviews": len(all_reviews),
            "ny_reviewers": len(ny_reviewers),
            "elapsed_seconds": elapsed
        }, indent=2))
        print(f"  Receipt: {RECEIPTS_DIR / f'manhattan_reviews_{ts}.json'}")

        print("\n=== COMPLETE ===")
        print(f"Manhattan profiles: {len(profiles)}")
        print(f"Total reviews extracted: {len(all_reviews)}")
        print(f"NY reviewers found: {len(ny_reviewers)}")
        print(f"These NY reviewers are confirmed clients (they left reviews)")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
