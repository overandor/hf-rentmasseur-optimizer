#!/usr/bin/env python3
"""
RentMasseur Visit Pipe — war-grade visitor roundtrip.

Two phases:
  1. WHO SAW ME — pull every username from /settings/whosawme via API
  2. NEW YORK SWEEP — search all NY cities, visit every masseur profile

Each visit = GET /username with auth cookies, logged with receipt.

Usage:
    python3 scripts/visit_pipe.py --dry-run
    python3 scripts/visit_pipe.py --limit 50
    python3 scripts/visit_pipe.py --ny-only
    python3 scripts/visit_pipe.py --whosaw-only
    python3 scripts/visit_pipe.py            # full pipe: whosaw + NY
"""
import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rm_traffic.api_client import RentMasseurAPI

BASE = "https://rentmasseur.com"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"

NY_CITIES = [
    "manhattan-ny",
    "brooklyn-ny",
    "queens-ny",
    "bronx-ny",
    "staten-island-ny",
    "long-island-ny",
    "yonkers-ny",
    "new-york-ny",
    "jersey-city-nj",
    "hoboken-nj",
]


def write_receipt(action: str, data: dict, success: bool = True) -> str:
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    receipt = {
        "action": action,
        "success": success,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **data,
    }
    rpath = RECEIPTS_DIR / f"{action}_{ts}.json"
    rpath.write_text(json.dumps(receipt, indent=2))
    return str(rpath)


def get_whosawme_usernames(api: RentMasseurAPI) -> list[dict]:
    """Pull usernames from mailbox contacts (proxy for whosawme via API)."""
    usernames = set()
    contacts = []
    for page in range(1, 6):
        try:
            mail = api.get_mailbox(page=page, folder=1)
            for email in mail.get("emails", []):
                uc = email.get("userCard", {})
                u = uc.get("username", "")
                if u and u not in usernames:
                    usernames.add(u)
                    contacts.append({"username": u, "source": "mailbox", "name": uc.get("name", u)})
        except Exception as e:
            print(f"  mailbox page {page}: {e}")
            break
    return contacts


def get_ny_usernames(api: RentMasseurAPI, max_pages: int = 10) -> list[dict]:
    """Search all NY cities and collect masseur usernames."""
    usernames = set()
    results = []
    for city in NY_CITIES:
        for page in range(1, max_pages + 1):
            try:
                data = api.search(city=city, available_only=False, page=page)
                users = data.get("users", data.get("results", []))
                if not users:
                    break
                for u in users:
                    username = u.get("username", "")
                    if username and username not in usernames:
                        usernames.add(username)
                        results.append({
                            "username": username,
                            "source": f"search:{city}",
                            "name": u.get("name", username),
                            "city": city,
                        })
                print(f"  {city} page {page}: +{len(users)} ({len(usernames)} total)")
            except Exception as e:
                print(f"  {city} page {page}: {e}")
                break
    return results


def visit_profiles(api: RentMasseurAPI, targets: list[dict], limit: int, dry_run: bool) -> list[dict]:
    """Visit each profile via authenticated GET request."""
    token = api.session.headers.get("Authorization", "")
    cookies = {c.name: c.value for c in api.session.cookies}
    headers = {
        "User-Agent": api.session.headers.get("User-Agent", "Mozilla/5.0"),
        "Accept": "text/html,application/xhtml+xml",
        "Referer": BASE,
    }
    if token:
        headers["Authorization"] = token

    import requests as req

    to_visit = targets[:limit]
    visited = []
    ok_count = 0

    def visit_one(target):
        u = target["username"]
        url = f"{BASE}/{u}"
        try:
            r = req.get(url, headers=headers, cookies=cookies, timeout=15, allow_redirects=True)
            status = r.status_code
            return {**target, "url": url, "status": status, "visited_at": datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            return {**target, "url": url, "status": "error", "error": str(e)[:80], "visited_at": datetime.now(timezone.utc).isoformat()}

    if dry_run:
        for t in to_visit:
            print(f"  [DRY] would visit {t['username']} (source: {t['source']})")
        return [{"username": t["username"], "source": t["source"], "status": "dry_run"} for t in to_visit]

    print(f"\n  Visiting {len(to_visit)} profiles with 33 workers...")
    with ThreadPoolExecutor(max_workers=33) as pool:
        futures = {pool.submit(visit_one, t): t for t in to_visit}
        for i, future in enumerate(as_completed(futures)):
            result = future.result()
            visited.append(result)
            if result.get("status") == 200:
                ok_count += 1
            if (i + 1) % 10 == 0 or i + 1 == len(to_visit):
                print(f"  [{i+1}/{len(to_visit)}] ok={ok_count} last={result['username']} status={result.get('status')}")

    print(f"\n  VISITED: {ok_count}/{len(to_visit)} OK")
    return visited


def main():
    parser = argparse.ArgumentParser(description="RentMasseur Visit Pipe — whosaw + NY sweep")
    parser.add_argument("--dry-run", action="store_true", help="List targets without visiting")
    parser.add_argument("--limit", type=int, default=100, help="Max profiles to visit per phase")
    parser.add_argument("--ny-only", action="store_true", help="Only NY city sweep")
    parser.add_argument("--whosaw-only", action="store_true", help="Only who-saw-me / mailbox contacts")
    parser.add_argument("--ny-pages", type=int, default=10, help="Max search pages per NY city")
    args = parser.parse_args()

    username = os.getenv("RENTMASSEUR_USERNAME", "karpathianwolf")
    password = os.getenv("RENTMASSEUR_PASSWORD", "os.environ.get("RM_PASSWORD", "")")

    print("=== RENTMASSEUR VISIT PIPE ===")
    print(f"  Mode: {'dry-run' if args.dry_run else 'LIVE'}")
    print(f"  Limit: {args.limit} per phase")

    api = RentMasseurAPI(min_request_interval=0.3)
    print("\n[1] Logging in...")
    if not api.login(username, password):
        print("  LOGIN FAILED")
        sys.exit(1)
    print(f"  OK: logged in as {username}")
    api.set_track_actions(True)

    all_visited = []
    all_targets = []

    if not args.ny_only:
        print("\n[2] Phase A: Who Saw Me / Mailbox contacts...")
        whosaw = get_whosawme_usernames(api)
        print(f"  Found {len(whosaw)} contacts from mailbox")
        all_targets.extend(whosaw)

    if not args.whosaw_only:
        print(f"\n[3] Phase B: New York city sweep ({len(NY_CITIES)} cities)...")
        ny_targets = get_ny_usernames(api, max_pages=args.ny_pages)
        print(f"  Found {len(ny_targets)} NY masseur profiles")
        all_targets.extend(ny_targets)

    # Deduplicate
    seen = set()
    deduped = []
    for t in all_targets:
        if t["username"] not in seen:
            seen.add(t["username"])
            deduped.append(t)
    all_targets = deduped
    print(f"\n[4] Total unique targets: {len(all_targets)}")

    if not all_targets:
        print("  No targets found. Exiting.")
        write_receipt("visit_pipe", {"targets": 0, "visited": 0}, success=False)
        return

    print(f"\n[5] Visiting up to {args.limit} profiles...")
    visited = visit_profiles(api, all_targets, args.limit, args.dry_run)
    all_visited = visited

    rpath = write_receipt("visit_pipe", {
        "targets_found": len(all_targets),
        "visited_count": len(all_visited),
        "ok_count": sum(1 for v in all_visited if v.get("status") == 200),
        "dry_run": args.dry_run,
        "phases": {
            "whosaw": not args.ny_only,
            "ny_sweep": not args.whosaw_only,
        },
        "ny_cities": NY_CITIES if not args.whosaw_only else [],
        "visited": all_visited,
    })

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    (DATA_DIR / "visit_pipe_latest.json").write_text(json.dumps({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "targets": len(all_targets),
        "visited": len(all_visited),
        "ok": sum(1 for v in all_visited if v.get("status") == 200),
        "results": all_visited,
    }, indent=2))

    ok = sum(1 for v in all_visited if v.get("status") == 200)
    print(f"\n=== PIPE COMPLETE ===")
    print(f"  Targets: {len(all_targets)}")
    print(f"  Visited: {len(all_visited)}")
    print(f"  OK (200): {ok}")
    print(f"  Receipt: {rpath}")
    print(f"  Data: {DATA_DIR / 'visit_pipe_latest.json'}")


if __name__ == "__main__":
    main()
