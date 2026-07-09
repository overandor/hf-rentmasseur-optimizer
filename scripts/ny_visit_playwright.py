#!/usr/bin/env python3
"""
Playwright-based auto-login and cookie extraction.
Playwright has better anti-detection than undetected-chromedriver.
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright
import requests

BASE = "https://rentmasseur.com"
USERNAME = "karpathianwolf"
PASSWORD = os.environ.get("RM_PASSWORD", "")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"
COOKIE_FILE = DATA_DIR / "rentmasseur_cookies.json"

NY_CITIES = [
    "manhattan-ny", "brooklyn-ny", "queens-ny", "bronx-ny", "staten-island-ny",
    "long-island-ny", "yonkers-ny", "new-york-ny", "jersey-city-nj", "hoboken-nj",
]


def extract_cookies_playwright():
    """Use Playwright to login and extract cookies."""
    print("=== PLAYWRIGHT AUTO LOGIN ===")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )
        page = context.new_page()

        try:
            page.goto(f"{BASE}/login", wait_until="networkidle", timeout=60000)
            print("Page loaded. Waiting for captcha bypass (30s)...")
            time.sleep(30)

            # Check if captcha is still present
            content = page.content()
            if "crowdsec" in content.lower() or "captcha" in content.lower():
                print("Captcha still present. Trying to click checkbox...")
                try:
                    checkbox = page.locator("input[type='checkbox']").first
                    if checkbox.is_visible():
                        checkbox.click()
                        time.sleep(15)
                except:
                    pass

            # Fill login form
            print("Filling login form...")
            try:
                page.fill("input[type='email'], input[type='text'], input[name='email']", USERNAME)
                page.fill("input[type='password'], input[name='password']", PASSWORD)
                time.sleep(1)
                page.click("button[type='submit'], button:has-text('Log'), button:has-text('Sign')")
            except Exception as e:
                print(f"Login form error: {e}")

            print("Waiting for login (15s)...")
            time.sleep(15)

            # Check if logged in
            if "login" in page.url.lower():
                print("Login failed. Still on login page.")
                browser.close()
                return None

            print("Login successful! Extracting cookies...")
            cookies = context.cookies()

            # Save cookies
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with open(COOKIE_FILE, "w") as f:
                json.dump(cookies, f, indent=2)

            print(f"Saved {len(cookies)} cookies to: {COOKIE_FILE}")
            return {c["name"]: c["value"] for c in cookies}

        finally:
            browser.close()


def search_ny_users(cookies, max_pages=10):
    """Search NY cities using cookies."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": BASE,
        "Origin": BASE,
    }

    all_users = []
    seen = set()

    for city in NY_CITIES:
        for page in range(1, max_pages + 1):
            try:
                r = requests.post(f"{BASE}/api/v1/search",
                    json={"searchCity": city, "page": page, "skipUsers": str(len(all_users))},
                    headers=headers, cookies=cookies, timeout=10)
                if r.status_code != 200:
                    print(f"  {city} page {page}: {r.status_code}")
                    break
                data = r.json()
                users = data.get("users", data.get("results", []))
                if not users:
                    break
                for u in users:
                    username = u.get("username", "")
                    if username and username not in seen:
                        seen.add(username)
                        all_users.append({
                            "username": username,
                            "name": u.get("name", username),
                            "city": city,
                            "url": f"{BASE}/{username}",
                        })
                print(f"  {city} page {page}: +{len(users)} (total: {len(all_users)})")
            except Exception as e:
                print(f"  {city} page {page}: {e}")
                break

    return all_users


def visit_profiles(users, cookies, limit=500):
    """Visit profiles concurrently."""
    targets = users[:limit]
    print(f"\nVisiting {len(targets)} profiles (33 threads)...")

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Referer": BASE,
    }

    results = []
    t0 = time.time()

    def visit_one(u):
        try:
            r = requests.get(u["url"], headers=headers, cookies=cookies, timeout=15, allow_redirects=True)
            return {**u, "status": r.status_code, "bytes": len(r.text)}
        except Exception as e:
            return {**u, "status": "error", "error": str(e)[:80]}

    with ThreadPoolExecutor(max_workers=33) as pool:
        futures = {pool.submit(visit_one, u): u for u in targets}
        for i, fut in enumerate(as_completed(futures)):
            r = fut.result()
            results.append(r)
            if (i + 1) % 50 == 0 or i == len(targets) - 1:
                ok = sum(1 for x in results if x["status"] == 200)
                print(f"  [{i+1}/{len(targets)}] {r['username']}: {r['status']} (OK: {ok})")

    elapsed = time.time() - t0
    success = sum(1 for r in results if r["status"] == 200)
    print(f"Done: {len(results)} visited, {success} OK, {elapsed:.1f}s")
    return results


def main():
    print("=== RENTMASSEUR NY VISIT (PLAYWRIGHT) ===")

    # Try loading existing cookies
    cookies = None
    if COOKIE_FILE.exists():
        with open(COOKIE_FILE) as f:
            cookie_list = json.load(f)
        cookies = {c["name"]: c["value"] for c in cookie_list}
        print(f"Loaded {len(cookies)} cookies from file")

        # Test if cookies are valid
        r = requests.get(BASE, cookies=cookies, timeout=10)
        if "crowdsec" in r.text.lower() or "captcha" in r.text.lower():
            print("Cookies expired. Need fresh login.")
            cookies = None

    if not cookies:
        cookies = extract_cookies_playwright()
        if not cookies:
            print("Failed to extract cookies.")
            return

    users = search_ny_users(cookies, max_pages=10)
    if not users:
        print("No users found.")
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "ny_users.json").write_text(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "count": len(users),
        "users": users,
    }, indent=2))
    print(f"Saved: {DATA_DIR / 'ny_users.json'}")

    results = visit_profiles(users, cookies, limit=500)

    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    receipt = {
        "action": "ny_visit_playwright",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "users_found": len(users),
        "visited": len(results),
        "success": sum(1 for r in results if r["status"] == 200),
        "results": results,
    }
    rpath = RECEIPTS_DIR / f"ny_visit_{ts}.json"
    rpath.write_text(json.dumps(receipt, indent=2))
    print(f"Receipt: {rpath}")


if __name__ == "__main__":
    main()
