#!/usr/bin/env python3
"""Debug search API response structure."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rm_traffic.api_client import RentMasseurAPI
import json

api = RentMasseurAPI()
api.login("karpathianwolf", "os.environ.get("RM_PASSWORD", "")")

data = api.search(city="manhattan-ny", page=1)
print("Response keys:", list(data.keys()))
print("Users key:", "users" in data, "results" in data)

users = data.get("users", data.get("results", []))
print(f"Found {len(users)} users")
if users:
    print("First user keys:", list(users[0].keys()))
    print("First user sample:", json.dumps(users[0], indent=2)[:500])
