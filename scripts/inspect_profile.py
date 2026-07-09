#!/usr/bin/env python3
"""
Profile Page Inspector - Check HTML structure for reviews
"""
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# Load Manhattan profiles
ny_file = DATA_DIR / "ny_users.json"
with open(ny_file) as f:
    ny_data = json.load(f)
manhattan_profiles = [p for p in ny_data.get("users", []) if "manhattan" in p.get("city", "").lower()]

print(f"Found {len(manhattan_profiles)} Manhattan profiles")

# Pick a few to inspect
for p in manhattan_profiles[:5]:
    print(f"\nUsername: {p['username']}")
    print(f"URL: {p['url']}")

# Now let's fetch one profile and save the HTML for inspection
import requests

username = manhattan_profiles[0]["username"]
url = f"https://rentmasseur.com/{username}"

print(f"\nFetching {url}...")
headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

r = requests.get(url, headers=headers, timeout=15)
print(f"Status: {r.status_code}")

# Save HTML for inspection
html_file = DATA_DIR / f"profile_{username}_html.html"
html_file.write_text(r.text)
print(f"Saved HTML to: {html_file}")

# Search for review-related keywords
text = r.text.lower()
keywords = ["review", "testimonial", "comment", "rating", "star", "feedback"]
print("\nSearching for review-related keywords:")
for keyword in keywords:
    count = text.count(keyword)
    if count > 0:
        print(f"  {keyword}: {count} occurrences")

# Look for any divs with review-like classes
div_classes = re.findall(r'<div[^>]*class="([^"]*)"', r.text, re.IGNORECASE)
review_classes = [c for c in div_classes if any(k in c.lower() for k in ["review", "testimonial", "comment", "rating", "star"])]
if review_classes:
    print("\nFound divs with review-related classes:")
    for c in set(review_classes[:10]):
        print(f"  {c}")
