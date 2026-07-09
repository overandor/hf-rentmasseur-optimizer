#!/usr/bin/env python3
"""
Visit all NY users using the working pattern from task1_visit_back.py:
1. API login (works)
2. Transfer cookies to Selenium
3. Visit profiles concurrently
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json, time, os
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from rm_traffic.api_client import RentMasseurAPI

BASE = "https://rentmasseur.com"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"

NY_CITIES = [
    "manhattan-ny", "brooklyn-ny", "queens-ny", "bronx-ny", "staten-island-ny",
    "long-island-ny", "yonkers-ny", "new-york-ny", "jersey-city-nj", "hoboken-nj",
]

# Major US metro areas for expanded search
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


def search_ny_users(api, max_pages=50):
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


def visit_profiles_concurrent(users, cookies, token, limit=500):
    """Visit profiles concurrently using HTTP requests (much faster than Selenium)."""
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
            if (i + 1) % 50 == 0 or i == len(targets) - 1:
                ok = sum(1 for x in results if x["status"] == 200)
                print(f"  [{i+1}/{len(targets)}] {r['username']}: {r['status']} (OK: {ok})")

    elapsed = time.time() - t0
    success = sum(1 for r in results if r["status"] == 200)
    print(f"Done: {len(results)} visited, {success} OK, {elapsed:.1f}s")
    return results


def main():
    print("=== RENTMASSEUR NY VISIT (API + CONCURRENT HTTP) ===")

    # API login
    print("[1] API login...")
    api = RentMasseurAPI()
    if not api.login("karpathianwolf", "os.environ.get("RM_PASSWORD", "")"):
        print("API login failed.")
        return

    print("  API login OK.")
    token = api.session.headers.get("Authorization", "").replace("Bearer ", "")

    # Search major US cities
    print("\n[2] Searching major US cities (47 cities, 50 pages each)...")
    users = search_ny_users(api, max_pages=50)
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

    # Visit profiles (concurrent HTTP)
    print("\n[3] Visiting profiles...")
    cookies = {c.name: c.value for c in api.session.cookies}
    results = visit_profiles_concurrent(users, cookies, token, limit=5000)

    # Write receipt
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    receipt = {
        "action": "ny_visit_api_concurrent",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "users_found": len(users),
        "visited": len(results),
        "success": sum(1 for r in results if r["status"] == 200),
        "results": results,
    }
    rpath = RECEIPTS_DIR / f"ny_visit_{ts}.json"
    rpath.write_text(json.dumps(receipt, indent=2))
    print(f"\nReceipt: {rpath}")
    print(f"Users found: {len(users)}")
    print(f"Visited: {len(results)}")
    print(f"Success: {sum(1 for r in results if r['status'] == 200)}")


if __name__ == "__main__":
    main()
