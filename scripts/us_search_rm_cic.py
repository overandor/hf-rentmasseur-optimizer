#!/usr/bin/env python3
"""
US City Search with RM-CIC Classification

1. Selenium login (undetected-chromedriver bypasses CrowdSec)
2. Transfer cookies to API client
3. Search 47 major US cities
4. Visit profiles concurrently
5. Run RM-CIC classification
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

BASE = "https://rentmasseur.com"
USERNAME = "karpathianwolf"
PASSWORD = os.environ.get("RM_PASSWORD", "")
PROFILE_DIR = "/tmp/rm_us_search"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"

MAJOR_CITIES = [
    # NY area
    "manhattan-ny", "brooklyn-ny", "queens-ny", "bronx-ny", "staten-island-ny",
    "long-island-ny", "yonkers-ny", "new-york-ny", "jersey-city-nj", "hoboken-nj",
    # LA area
    "los-angeles-ca", "west-hollywood-ca", "hollywood-ca", "beverly-hills-ca",
    "santa-monica-ca", "culver-city-ca", "pasadena-ca", "glendale-ca",
    # Chicago
    "chicago-il", "lincoln-park-il", "lakeview-il", "wicker-park-il",
    # Miami
    "miami-fl", "miami-beach-fl", "fort-lauderdale-fl", "hialeah-fl",
    # San Francisco
    "san-francisco-ca", "castro-ca", "mission-district-ca", "soma-ca",
    # Boston
    "boston-ma", "cambridge-ma", "brookline-ma", "somerville-ma",
    # DC
    "washington-dc", "arlington-va", "alexandria-va",
    # Other major metros
    "atlanta-ga", "dallas-tx", "houston-tx", "seattle-wa", "portland-or",
    "denver-co", "phoenix-az", "san-diego-ca", "austin-tx", "nashville-tn",
]

# RM-CIC terms
CLIENT_TITLE_TERMS = {
    "looking for male massage": 80,
    "looking for massage": 75,
    "looking for therapist": 70,
    "looking for male massage ther": 80,
    "seeking massage": 65,
    "need massage": 60,
    "want massage": 60,
    "want a massage": 60,
    "need a massage": 60,
}

CLIENT_USERNAME_TERMS = {
    "inneed": 35,
    "looking": 30,
    "need": 25,
    "luv": 20,
    "love": 20,
    "wants": 20,
    "sore": 20,
    "aching": 20,
    "relax": 15,
    "body": 10,
}

PROVIDER_TITLE_TERMS = {
    "male masseur": -90,
    "masseur": -80,
    "gay massage in": -75,
    "massage in": -65,
    "bodywork by": -60,
    "therapist in": -55,
    "deep tissue": -50,
    "swedish": -50,
    "sports massage": -50,
    "therapeutic massage": -50,
    "tantric": -45,
}

PROVIDER_USERNAME_TERMS = {
    "masseur": -55,
    "massage": -45,
    "bodywork": -40,
    "hands": -35,
    "touch": -35,
    "healing": -35,
    "spa": -35,
    "therapist": -35,
    "deep": -30,
    "swedish": -30,
    "sportsmassage": -35,
}


def normalize(text: str) -> str:
    text = text or ""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def apply_terms(text: str, terms: Dict[str, int], prefix: str) -> tuple[int, List[str]]:
    score = 0
    reasons = []
    for term, weight in terms.items():
        if term in text:
            score += weight
            reasons.append(f"{prefix}:{term}:{weight}")
    return score, reasons


def classify_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """RM-CIC classification (without body evidence for speed)."""
    username = normalize(profile.get("username", ""))
    title = normalize(profile.get("title", ""))

    score = 0
    reasons: List[str] = []

    s, r = apply_terms(title, CLIENT_TITLE_TERMS, "client_title")
    score += s
    reasons.extend(r)

    s, r = apply_terms(username, CLIENT_USERNAME_TERMS, "client_username")
    score += s
    reasons.extend(r)

    s, r = apply_terms(title, PROVIDER_TITLE_TERMS, "provider_title")
    score += s
    reasons.extend(r)

    s, r = apply_terms(username, PROVIDER_USERNAME_TERMS, "provider_username")
    score += s
    reasons.extend(r)

    if not title or title == "rentmasseur.com" or "| rentmasseur" in title:
        score += 10
        reasons.append("generic_or_blank_title:+10")

    if score >= 70:
        label = "client_likely"
        confidence = min(0.98, 0.70 + (score - 70) / 200)
        next_action = "export_to_A_clients_review"
    elif score >= 35:
        label = "client_possible"
        confidence = min(0.75, 0.45 + (score - 35) / 150)
        next_action = "crawl_profile_body_or_manual_review"
    elif score >= -25:
        label = "unknown"
        confidence = 0.40
        next_action = "low_priority_revisit"
    else:
        label = "provider_likely"
        confidence = min(0.98, 0.70 + abs(score) / 200)
        next_action = "exclude_from_client_outreach"

    return {
        "username": profile.get("username"),
        "url": profile.get("url"),
        "city": profile.get("city"),
        "title": profile.get("title"),
        "client_score": score,
        "label": label,
        "confidence": round(confidence, 2),
        "reasons": reasons,
        "next_action": next_action
    }


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


def search_us_cities(api, max_pages=50):
    """Search all major US cities via API."""
    all_users = []
    seen = set()

    for city in MAJOR_CITIES:
        for page in range(1, max_pages + 1):
            try:
                data = api.search(city=city, available_only=False, page=page)
                users = data.get("users", data.get("results", []))
                if not users:
                    break
                for u in users:
                    user_card = u.get("userCard", {})
                    username = user_card.get("username", "")
                    if username and username not in seen:
                        seen.add(username)
                        all_users.append({
                            "username": username,
                            "name": user_card.get("name", username),
                            "city": city,
                            "url": f"{BASE}/{username}",
                        })
                print(f"  {city} page {page}: +{len(users)} (total: {len(all_users)})")
            except Exception as e:
                print(f"  {city} page {page}: {e}")
                break

    return all_users


def visit_profiles_concurrent(users, cookies, token, limit=10000):
    """Visit profiles concurrently using HTTP requests."""
    targets = users[:limit]
    print(f"\nVisiting {len(targets)} profiles (33 threads)...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Referer": BASE,
    }
    if token:
        headers["Authorization"] = token

    import requests as req

    results = []
    t0 = time.time()

    def visit_one(u):
        try:
            r = req.get(u["url"], headers=headers, cookies=cookies, timeout=15, allow_redirects=True)
            title_match = re.search(r'<title>([^<]+)</title>', r.text)
            title = title_match.group(1).strip() if title_match else None
            return {**u, "status": r.status_code, "title": title, "bytes": len(r.text)}
        except Exception as e:
            return {**u, "status": "error", "error": str(e)[:80], "title": None}

    with ThreadPoolExecutor(max_workers=33) as pool:
        futures = {pool.submit(visit_one, u): u for u in targets}
        for i, fut in enumerate(as_completed(futures)):
            r = fut.result()
            results.append(r)
            if (i + 1) % 100 == 0 or i == len(targets) - 1:
                ok = sum(1 for x in results if x["status"] == 200)
                print(f"  [{i+1}/{len(targets)}] OK: {ok}")

    elapsed = time.time() - t0
    success = sum(1 for r in results if r["status"] == 200)
    print(f"Done: {len(results)} visited, {success} OK, {elapsed:.1f}s")
    return results


def main():
    print("=== US CITY SEARCH + RM-CIC CLASSIFICATION ===")

    # Selenium login
    print("[1] Selenium login (undetected-chromedriver)...")
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
        try:
            access_token = driver.execute_script("return localStorage.getItem('accessToken') || '';")
            if access_token:
                api.session.headers["Authorization"] = f"Bearer {access_token}"
                print("  Token extracted from localStorage")
        except:
            print("  No token in localStorage")

        # Search major US cities
        print("\n[3] Searching major US cities (47 cities, 50 pages each)...")
        users = search_us_cities(api, max_pages=50)
        if not users:
            print("No users found.")
            return

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "us_users_raw.json").write_text(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(users),
            "users": users,
        }, indent=2))
        print(f"  Saved: {DATA_DIR / 'us_users_raw.json'}")

        # Visit profiles
        print("\n[4] Visiting profiles...")
        cookies_dict = {c["name"]: c["value"] for c in cookies}
        token = api.session.headers.get("Authorization", "").replace("Bearer ", "")
        results = visit_profiles_concurrent(users, cookies_dict, token, limit=10000)

        # Classify with RM-CIC
        print("\n[5] Classifying with RM-CIC...")
        classified = []
        for r in results:
            classification = classify_profile(r)
            classified.append({
                **r,
                "classification": classification
            })

        # Bucket
        print("\n[6] Bucketing...")
        buckets = {
            "client_likely": [],
            "client_possible": [],
            "unknown": [],
            "provider_likely": []
        }
        for p in classified:
            label = p["classification"]["label"]
            buckets[label].append(p)

        print(f"  A (client_likely): {len(buckets['client_likely'])}")
        print(f"  B (client_possible): {len(buckets['client_possible'])}")
        print(f"  C (unknown): {len(buckets['unknown'])}")
        print(f"  D (provider_likely): {len(buckets['provider_likely'])}")

        # Save results
        client_candidates = buckets["client_likely"] + buckets["client_possible"]
        (DATA_DIR / "us_client_candidates.json").write_text(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(client_candidates),
            "profiles": client_candidates
        }, indent=2))
        print(f"\n  Saved: {DATA_DIR / 'us_client_candidates.json'}")

        # Save receipt
        RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
        receipt_file = RECEIPTS_DIR / f"us_search_rm_cic_{ts}.json"
        with open(receipt_file, "w") as f:
            json.dump({
                "action": "us_search_rm_cic",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "summary": {
                    "users_found": len(users),
                    "visited": len(results),
                    "success": sum(1 for r in results if r["status"] == 200),
                    "client_likely": len(buckets["client_likely"]),
                    "client_possible": len(buckets["client_possible"]),
                    "client_candidates": len(client_candidates),
                },
                "buckets": {k: len(v) for k, v in buckets.items()}
            }, f, indent=2)
        print(f"  Receipt: {receipt_file}")

        print("\n=== COMPLETE ===")
        print(f"Client candidates (A+B): {len(client_candidates)}")
        print(f"  - A (contact-ready): {len(buckets['client_likely'])}")
        print(f"  - B (needs verification): {len(buckets['client_possible'])}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
