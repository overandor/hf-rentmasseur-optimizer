"""Probe all possible blog/interview API paths — all methods simultaneously."""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from rm_traffic.api_client import RentMasseurAPI

import os
api = RentMasseurAPI(min_request_interval=0.1)
api.login(os.environ.get("RENTMASSEUR_USER", os.environ.get("RM_USER", "")),
          os.environ.get("RENTMASSEUR_PASS", os.environ.get("RM_PASS", "")))
token = api.session.headers.get("Authorization", "")
cookies = {c.name: c.value for c in api.session.cookies}

import requests as req
BASE = "https://rentmasseur.com"
API = f"{BASE}/api/v1"
H = {"User-Agent": "Mozilla/5.0", "Authorization": token, "Accept": "application/json",
     "Origin": BASE, "Referer": f"{BASE}/settings"}

# All paths x all methods = full grid
paths = [
    "/settings/blog", "/settings/blogs", "/account/blog", "/account/blogs",
    "/settings/interview", "/settings/interviews", "/account/interview", "/account/interviews",
    "/settings/blog/create", "/settings/blog/edit", "/settings/blog/save", "/settings/blog/post",
    "/settings/interview/create", "/settings/interview/edit", "/settings/interview/save", "/settings/interview/update",
    "/account/blog/create", "/account/blog/save", "/account/blog/post",
    "/account/interview/create", "/account/interview/save", "/account/interview/update",
    "/account/dashboard/blog", "/account/dashboard/interview",
    "/blogs", "/blogs/create", "/blogs/post", "/blogs/save",
    "/interview", "/interview/create", "/interview/save", "/interview/update",
    "/settings/about", "/settings/about/blog", "/settings/about/interview",
    "/account/keeponline", "/account/keeponline/blog",
    "/settings/visibility", "/settings/sms", "/settings/track-actions",
    "/account/dashboard", "/account/dashboard/availability", "/account/dashboard/ad-statistics",
    "/account/keeponline", "/mailbox", "/search",
]
methods = ["GET", "POST", "PUT", "DELETE"]

def probe(args):
    p, m = args
    url = f"{API}{p}"
    try:
        if m == "GET":
            r = req.get(url, headers=H, cookies=cookies, timeout=8)
        elif m == "POST":
            r = req.post(url, headers=H, cookies=cookies, json={"title":"t","description":"d","body":"b","answers":["a"]}, timeout=8)
        elif m == "PUT":
            r = req.put(url, headers=H, cookies=cookies, json={"title":"t","description":"d","body":"b","answers":["a"]}, timeout=8)
        elif m == "DELETE":
            r = req.delete(url, headers=H, cookies=cookies, timeout=8)
        s = r.status_code
        t = r.text[:100].replace("\n"," ") if s != 404 else ""
        return (p, m, s, t)
    except Exception as e:
        return (p, m, "ERR", str(e)[:50])

# Build full grid: paths x methods
jobs = [(p, m) for p in paths for m in methods]
print(f"Probing {len(jobs)} combinations ({len(paths)} paths x {len(methods)} methods) with 33 workers...")
t0 = time.time()

hits = []
with ThreadPoolExecutor(max_workers=33) as pool:
    futures = {pool.submit(probe, j): j for j in jobs}
    for fut in as_completed(futures):
        p, m, s, t = fut.result()
        if s != 404:
            hits.append((p, m, s, t))
            print(f"  HIT: {m:6s} {p}: {s} {t}")

elapsed = time.time() - t0
print(f"\n{len(hits)} hits out of {len(jobs)} probes in {elapsed:.1f}s")
print("\n=== ALL HITS ===")
for p, m, s, t in sorted(hits, key=lambda x: (x[0], x[1])):
    print(f"  {m:6s} {p:40s} {s} {t}")
