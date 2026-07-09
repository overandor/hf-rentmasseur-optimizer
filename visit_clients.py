"""Visit client profiles concurrently — reciprocal profile visits."""
import json, time, requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from rm_traffic.api_client import RentMasseurAPI

BASE = "https://rentmasseur.com"

def collect_clients(api, pages=4):
    """Collect client usernames from mailbox."""
    usernames = set()
    for page in range(1, pages + 1):
        mail = api.get_mailbox(page=page, folder=1)
        emails = mail.get("emails", [])
        if not emails:
            break
        for e in emails:
            u = e.get("userCard", {}).get("username", "")
            if u:
                usernames.add(u)
    return sorted(usernames)

def visit_profile(uname, token, cookies):
    """Visit a single client profile page."""
    url = f"{BASE}/{uname}"
    try:
        resp = requests.get(url, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            "Authorization": token,
        }, cookies=cookies, timeout=15, allow_redirects=True)
        return {"username": uname, "status": resp.status_code, "bytes": len(resp.text)}
    except Exception as e:
        return {"username": uname, "status": "error", "error": str(e)[:80]}

def main():
    api = RentMasseurAPI(min_request_interval=0.5)
    ok = api.login("karpathianwolf", "Lola369!")
    if not ok:
        print("LOGIN FAILED")
        return

    # Enable track-actions so our profile shows when visiting others
    api.set_track_actions(True)

    clients = collect_clients(api, pages=4)
    print(f"Clients from mailbox: {len(clients)}")
    print(f"Usernames: {clients}")

    token = api.session.headers.get("Authorization", "")
    cookies = {c.name: c.value for c in api.session.cookies}

    # Visit all profiles concurrently with 33 workers
    MAX_WORKERS = 33
    print(f"\nVisiting {len(clients)} profiles with {MAX_WORKERS} concurrent workers...")
    visited = []
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(visit_profile, u, token, cookies): u for u in clients}
        for fut in as_completed(futures):
            result = fut.result()
            visited.append(result)
            print(f"  {result['username']}: {result['status']}")

    elapsed = time.time() - t0
    success = sum(1 for v in visited if v["status"] == 200)

    receipt = {
        "action": "reciprocal_profile_visits",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_clients": len(clients),
        "visited": len(visited),
        "success_200": success,
        "elapsed_seconds": round(elapsed, 1),
        "concurrent_workers": MAX_WORKERS,
        "visited_details": visited,
    }

    with open("rm_traffic/data/profile_visits.json", "w") as f:
        json.dump(receipt, f, indent=2)

    print(f"\nDone: {len(visited)} visited, {success} OK, {elapsed:.1f}s elapsed")
    print(f"Receipt: rm_traffic/data/profile_visits.json")

if __name__ == "__main__":
    main()
