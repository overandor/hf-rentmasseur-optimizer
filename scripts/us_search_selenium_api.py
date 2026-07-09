#!/usr/bin/env python3
"""
Expanded US Search using Selenium for auth, then API for search + concurrent visits.

Pattern from task1_visit_back.py which worked:
1. Selenium login (bypasses captcha with undetected-chromedriver)
2. Transfer cookies to API client
3. Search major US cities via API
4. Visit profiles concurrently
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json, time, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import undetected_chromedriver as uc
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


def get_driver_and_login():
    """Get undetected-chromedriver and login."""
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
                checkbox = driver.find_element("css selector", "input[type='checkbox']")
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
            pwd = driver.find_element("css selector", "input[type='password']")
            pwd.send_keys("\n")
        except:
            pass

        time.sleep(10)

        # Check if logged in
        if "login" in driver.current_url.lower():
            print("  Login failed. Still on login page.")
            driver.quit()
            return None, None

        print("  Login successful!")
        return driver, driver.get_cookies()
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


def visit_profiles_concurrent(users, cookies, token, limit=5000):
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
            return {**u, "status": r.status_code, "bytes": len(r.text)}
        except Exception as e:
            return {**u, "status": "error", "error": str(e)[:80]}

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
    print("=== RENTMASSEUR US SEARCH (SELENIUM AUTH + API SEARCH) ===")

    # Selenium login
    print("[1] Selenium login (undetected-chromedriver)...")
    driver, cookies = get_driver_and_login()
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
        (DATA_DIR / "us_users.json").write_text(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(users),
            "users": users,
        }, indent=2))
        print(f"  Saved: {DATA_DIR / 'us_users.json'}")

        # Visit profiles
        print("\n[4] Visiting profiles...")
        cookies_dict = {c["name"]: c["value"] for c in cookies}
        token = api.session.headers.get("Authorization", "").replace("Bearer ", "")
        results = visit_profiles_concurrent(users, cookies_dict, token, limit=5000)

        # Write receipt
        RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
        receipt = {
            "action": "us_search_selenium_api",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "users_found": len(users),
            "visited": len(results),
            "success": sum(1 for r in results if r["status"] == 200),
            "results": results,
        }
        rpath = RECEIPTS_DIR / f"us_search_{ts}.json"
        rpath.write_text(json.dumps(receipt, indent=2))
        print(f"\nReceipt: {rpath}")
        print(f"Users found: {len(users)}")
        print(f"Visited: {len(results)}")
        print(f"Success: {sum(1 for r in results if r['status'] == 200)}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
