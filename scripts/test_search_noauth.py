#!/usr/bin/env python3
"""Test if search API works without auth."""
import requests
import json

BASE = "https://rentmasseur.com"
API = f"{BASE}/api/v1"

# Try search without auth
r = requests.post(f"{API}/search", json={"searchCity": "manhattan-ny", "page": 1, "skipUsers": "0"}, timeout=10)
print(f"Search without auth: {r.status_code}")
print(r.text[:500])

if r.status_code == 200:
    data = r.json()
    users = data.get("users", data.get("results", []))
    print(f"Users found: {len(users)}")
    if users:
        print(json.dumps(users[0], indent=2)[:500])
