#!/usr/bin/env python3
"""
Try to use existing Chrome profile cookies to bypass captcha.
If cookies exist from previous login, use them directly.
"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import requests
import undetected_chromedriver as uc

BASE = "https://rentmasseur.com"
PROFILE_DIR = "/tmp/rm_auto_visit"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"

NY_CITIES = [
    "manhattan-ny", "brooklyn-ny", "queens-ny", "bronx-ny", "staten-island-ny",
    "long-island-ny", "yonkers-ny", "new-york-ny", "jersey-city-nj", "hoboken-nj",
]


def get_cookies_from_profile():
    """Extract cookies from existing Chrome profile if available."""
    # Try multiple profiles
    profiles = ["/tmp/rm_visit_pipe", "/tmp/rm_auto_visit", "/tmp/rm_task1", "/tmp/rm_task2", "/tmp/rm_task3"]

    for profile_dir in profiles:
        print(f"  Checking profile: {profile_dir}")
        if not os.path.exists(profile_dir):
            continue

        try:
            opts = uc.ChromeOptions()
            opts.add_argument("--window-size=1280,900")
            opts.add_argument(f"--user-data-dir={profile_dir}")
            driver = uc.Chrome(options=opts, version_main=149)

            driver.get(BASE)
            time.sleep(5)

            # Check if already logged in
            body = driver.find_element("tag name", "body").text.lower()
            if "log out" in body or "logout" in body or "my account" in body or "settings" in body:
                print(f"  Already logged in via {profile_dir}!")
                cookies = {}
                for c in driver.get_cookies():
                    cookies[c["name"]] = c["value"]
                driver.quit()
                return cookies
            else:
                print(f"  Not logged in in {profile_dir}.")
                driver.quit()
        except Exception as e:
            print(f"  Error checking {profile_dir}: {e}")
            try:
                driver.quit()
            except:
                pass

    return None


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
    print("=== RENTMASSEUR NY VISIT (PROFILE COOKIES) ===")

    cookies = get_cookies_from_profile()
    if not cookies:
        print("No valid cookies found. Need to login first.")
        print("Run: python3 scripts/extract_cookies.py")
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
        "action": "ny_visit",
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
