#!/usr/bin/env python3
"""
Probe rentmasseur.com API for client-related endpoints.

Discovers:
  - Who Saw Me (client visitors)
  - Reviews (clients who left reviews)
  - Client profile pages
  - Any endpoint that returns client/user data

Usage:
    python3 scripts/probe_clients.py
"""
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

BASE = "https://rentmasseur.com"
API = f"{BASE}/api/v1"
USERNAME = os.getenv("RENTMASSEUR_USERNAME", "karpathianwolf")
PASSWORD = os.getenv("RENTMASSEUR_PASSWORD", os.environ.get("RM_PASSWORD", ""))

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": f"{BASE}/settings",
    "Origin": BASE,
})

# ── Login ──
print("=== LOGIN ===")
r = s.get(f"{BASE}/login")
m = re.search(r'csrf["\s:=]+([A-Za-z0-9+/=]{20,})', r.text)
csrf = m.group(1) if m else ""
r = s.post(f"{API}/login", json={
    "email": USERNAME, "password": PASSWORD, "csrf": csrf, "remember": True
})
if r.status_code != 200:
    print(f"Login failed: {r.status_code} {r.text[:300]}")
    sys.exit(1)
try:
    token = r.json().get("accessToken", "")
except Exception:
    print(f"Login response not JSON (CrowdSec?): {r.text[:200]}")
    sys.exit(1)
s.headers["Authorization"] = f"Bearer {token}"
print("Login OK\n")

# ── 1. Who Saw Me endpoints ──
print("=== WHO SAW ME ===")
for path in [
    "/api/v1/whosawme", "/api/v1/who-saw-me", "/api/v1/whosaw",
    "/api/v1/visitors", "/api/v1/visits", "/api/v1/settings/whosawme",
    "/api/v1/account/whosawme", "/api/v1/account/visitors",
    "/api/v1/account/visits", "/api/v1/dashboard/whosawme",
    "/api/v1/dashboard/visitors", "/api/v1/settings/visitors",
    "/api/v1/settings/visits", "/api/v1/who-saw",
    "/api/v1/account/who-saw-me", "/api/v1/recent-visitors",
    "/api/v1/profile-views", "/api/v1/account/profile-views",
    "/api/v1/settings/profile-views",
]:
    try:
        r = s.get(f"{BASE}{path}", timeout=5)
        if r.status_code != 404:
            body = r.text[:300].replace("\n", " ")
            print(f"  GET {r.status_code} {path}: {body}")
            # Try to extract usernames
            try:
                data = r.json()
                if isinstance(data, list) and data:
                    print(f"    -> {len(data)} items, keys: {list(data[0].keys()) if isinstance(data[0], dict) else 'not dict'}")
                elif isinstance(data, dict):
                    for k in data:
                        v = data[k]
                        if isinstance(v, list) and v:
                            print(f"    -> key '{k}': {len(v)} items")
                            if isinstance(v[0], dict):
                                print(f"       first item keys: {list(v[0].keys())}")
                                print(f"       first item: {json.dumps(v[0], default=str)[:300]}")
            except Exception:
                pass
    except Exception as e:
        print(f"  GET ERR {path}: {str(e)[:80]}")

# Also try with pagination params
print("\n  -- with pagination --")
for path in ["/api/v1/whosawme", "/api/v1/settings/whosawme", "/api/v1/visitors"]:
    for params in [{"page": 1}, {"page": 1, "limit": 50}, {"offset": 0, "limit": 50}]:
        try:
            r = s.get(f"{BASE}{path}", params=params, timeout=5)
            if r.status_code != 404:
                print(f"  GET {r.status_code} {path} params={params}: {r.text[:200]}")
        except Exception:
            pass

# ── 2. Reviews (clients who reviewed) ──
print("\n=== REVIEWS ===")
for path in [
    "/api/v1/account/reviews", "/api/v1/settings/reviews",
    "/api/v1/account/dashboard/reviews", "/api/v1/reviews",
    "/api/v1/account/reviews?page=1", "/api/v1/reviews?page=1",
]:
    try:
        r = s.get(f"{BASE}{path}", timeout=5)
        if r.status_code != 404:
            body = r.text[:400].replace("\n", " ")
            print(f"  GET {r.status_code} {path}: {body}")
            try:
                data = r.json()
                if isinstance(data, list) and data:
                    print(f"    -> {len(data)} reviews, keys: {list(data[0].keys())}")
                    print(f"    first: {json.dumps(data[0], default=str)[:400]}")
                elif isinstance(data, dict):
                    for k, v in data.items():
                        if isinstance(v, list) and v:
                            print(f"    key '{k}': {len(v)} items")
                            if isinstance(v[0], dict):
                                print(f"    first keys: {list(v[0].keys())}")
                                print(f"    first: {json.dumps(v[0], default=str)[:400]}")
            except Exception:
                pass
    except Exception as e:
        print(f"  GET ERR {path}: {str(e)[:80]}")

# ── 3. Mailbox (client usernames from messages) ──
print("\n=== MAILBOX (client senders) ===")
try:
    r = s.get(f"{API}/mailbox?page=1&folder=1&sort=1", timeout=10)
    data = r.json()
    emails = data.get("emails", [])
    print(f"  Mailbox: {len(emails)} emails")
    clients = set()
    for e in emails:
        uc = e.get("userCard", {})
        u = uc.get("username", "")
        if u:
            clients.add(u)
    print(f"  Unique client usernames from mailbox: {len(clients)}")
    for c in list(clients)[:10]:
        print(f"    {c}")
except Exception as e:
    print(f"  Mailbox error: {e}")

# ── 4. Search results — check if clients appear ──
print("\n=== SEARCH (check for client vs masseur) ===")
for city in ["manhattan-ny"]:
    try:
        r = s.post(f"{API}/search", json={"searchCity": city, "page": 1, "skipUsers": "0"}, timeout=10)
        data = r.json()
        users = data.get("users", data.get("results", []))
        print(f"  Search {city}: {len(users)} results")
        if users:
            print(f"  First result keys: {list(users[0].keys())}")
            print(f"  First result: {json.dumps(users[0], default=str)[:500]}")
            # Check if there's a user type field
            for u in users[:3]:
                utype = u.get("type", u.get("userType", u.get("role", "unknown")))
                print(f"    {u.get('username', '?')} type={utype} name={u.get('name', '?')}")
    except Exception as e:
        print(f"  Search error: {e}")

# ── 5. Probe individual profile endpoints ──
print("\n=== PROFILE ENDPOINTS (try a known username) ===")
test_user = "karpathianwolf"
for path in [
    f"/api/v1/user/{test_user}", f"/api/v1/users/{test_user}",
    f"/api/v1/profile/{test_user}", f"/api/v1/profiles/{test_user}",
    f"/api/v1/account/profile/{test_user}", f"/api/v1/u/{test_user}",
    f"/api/v1/member/{test_user}", f"/api/v1/members/{test_user}",
]:
    try:
        r = s.get(f"{BASE}{path}", timeout=5)
        if r.status_code != 404:
            print(f"  GET {r.status_code} {path}: {r.text[:300]}")
    except Exception:
        pass

# ── 6. Try whosawme with different folder/page params ──
print("\n=== WHO SAW ME (folder/page variations) ===")
for path in ["/api/v1/whosawme", "/api/v1/settings/whosawme"]:
    for folder in [1, 2, 3]:
        for page in [1, 2]:
            try:
                r = s.get(f"{BASE}{path}", params={"page": page, "folder": folder}, timeout=5)
                if r.status_code != 404:
                    body = r.text[:200]
                    print(f"  GET {r.status_code} {path}?page={page}&folder={folder}: {body}")
                    break
            except Exception:
                pass

# ── 7. Check dashboard for visitor stats ──
print("\n=== DASHBOARD (visitor data) ===")
for path in [
    "/api/v1/account/dashboard", "/api/v1/account/dashboard/visitors",
    "/api/v1/account/dashboard/whosawme", "/api/v1/account/dashboard/profile-views",
    "/api/v1/account/dashboard/ad-statistics",
]:
    try:
        r = s.get(f"{BASE}{path}", timeout=5)
        if r.status_code != 404:
            body = r.text[:400].replace("\n", " ")
            print(f"  GET {r.status_code} {path}: {body}")
    except Exception:
        pass

print("\n=== PROBE COMPLETE ===")
