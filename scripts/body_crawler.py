#!/usr/bin/env python3
"""
Profile Body Crawler for RM-CIC

Extracts Layer 3 evidence (profile body) for unknown profiles.
Fields: title, headline, bio, services, rates, availability, location, contact button.
"""
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rm_traffic.api_client import RentMasseurAPI

BASE = "https://rentmasseur.com"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"


def extract_profile_body(username: str, cookies: dict, token: str) -> Dict:
    """Extract profile evidence via HTTP request."""
    import requests as req

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Referer": BASE,
    }
    if token:
        headers["Authorization"] = token

    url = f"{BASE}/{username}"
    evidence = {
        "username": username,
        "url": url,
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "title": None,
        "headline": None,
        "bio": None,
        "services": None,
        "rates": None,
        "availability": None,
        "location": None,
        "contact_button": None,
        "raw_length": 0,
        "error": None,
    }

    try:
        r = req.get(url, headers=headers, cookies=cookies, timeout=15, allow_redirects=True)
        if r.status_code != 200:
            evidence["error"] = f"HTTP {r.status_code}"
            return evidence

        text = r.text
        evidence["raw_length"] = len(text)

        # Extract title
        title_match = re.search(r'<title>([^<]+)</title>', r.text)
        if title_match:
            evidence["title"] = title_match.group(1).strip()

        # Extract headline (h1, h2)
        headline_match = re.search(r'<h1[^>]*>([^<]+)</h1>', r.text, re.IGNORECASE)
        if headline_match:
            evidence["headline"] = headline_match.group(1).strip()

        # Extract bio (about section)
        bio_match = re.search(r'<div[^>]*class="[^"]*about[^"]*"[^>]*>(.*?)</div>', r.text, re.IGNORECASE | re.DOTALL)
        if bio_match:
            evidence["bio"] = bio_match.group(1).strip()[:2000]

        # Extract services
        services_match = re.search(r'<div[^>]*class="[^"]*service[^"]*"[^>]*>(.*?)</div>', r.text, re.IGNORECASE | re.DOTALL)
        if services_match:
            evidence["services"] = services_match.group(1).strip()[:1000]

        # Extract rates/pricing
        rates_match = re.search(r'<div[^>]*class="[^"]*rate[^"]*"[^>]*>(.*?)</div>', r.text, re.IGNORECASE | re.DOTALL)
        if rates_match:
            evidence["rates"] = rates_match.group(1).strip()[:500]

        # Extract availability
        avail_match = re.search(r'<div[^>]*class="[^"]*avail[^"]*"[^>]*>(.*?)</div>', r.text, re.IGNORECASE | re.DOTALL)
        if avail_match:
            evidence["availability"] = avail_match.group(1).strip()[:500]

        # Extract location
        loc_match = re.search(r'<div[^>]*class="[^"]*location[^"]*"[^>]*>(.*?)</div>', r.text, re.IGNORECASE | re.DOTALL)
        if loc_match:
            evidence["location"] = loc_match.group(1).strip()[:500]

        # Extract contact button
        contact_match = re.search(r'<button[^>]*class="[^"]*contact[^"]*"[^>]*>([^<]+)</button>', r.text, re.IGNORECASE)
        if contact_match:
            evidence["contact_button"] = contact_match.group(1).strip()

        # If no structured fields, use raw text as bio sample
        if not evidence["bio"]:
            evidence["bio"] = text[:3000]

    except Exception as e:
        evidence["error"] = str(e)[:100]

    return evidence


def main():
    print("=== PROFILE BODY CRAWLER ===")

    # Load unknown profiles
    unknown_file = DATA_DIR / "clients_C_unknown.json"
    if not unknown_file.exists():
        print(f"Unknown file not found: {unknown_file}")
        return

    with open(unknown_file) as f:
        unknown_data = json.load(f)
    unknown_profiles = unknown_data.get("profiles", [])
    print(f"\n[1] Loaded {len(unknown_profiles)} unknown profiles")

    # Try API login for auth
    print("\n[2] Setting up auth...")
    token = ""
    cookies = {}

    api = RentMasseurAPI()
    if api.login("karpathianwolf", "os.environ.get("RM_PASSWORD", "")"):
        token = api.session.headers.get("Authorization", "").replace("Bearer ", "")
        cookies = {c.name: c.value for c in api.session.cookies}
        print("  API login OK")
    else:
        print("  API login blocked, proceeding without auth")

    # Extract body evidence
    print(f"\n[3] Extracting profile bodies (33 threads)...")
    evidence_results = []

    def extract_one(p):
        return extract_profile_body(p["username"], cookies, token)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=33) as pool:
        futures = {pool.submit(extract_one, p): p for p in unknown_profiles}
        for i, fut in enumerate(as_completed(futures)):
            r = fut.result()
            evidence_results.append(r)
            if (i + 1) % 50 == 0 or i == len(unknown_profiles) - 1:
                print(f"  [{i+1}/{len(unknown_profiles)}] extracted")

    elapsed = time.time() - t0
    print(f"  Done: {len(evidence_results)} extracted, {elapsed:.1f}s")

    # Map evidence to profiles
    evidence_map = {e["username"]: e for e in evidence_results}

    # Save body evidence
    body_file = DATA_DIR / "profile_bodies.json"
    with open(body_file, "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(evidence_results),
            "evidence": evidence_results
        }, f, indent=2)
    print(f"\n[4] Saved body evidence: {body_file}")

    # Save receipt
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    receipt_file = RECEIPTS_DIR / f"body_crawl_{ts}.json"
    with open(receipt_file, "w") as f:
        json.dump({
            "action": "profile_body_crawl",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "profiles_crawled": len(evidence_results),
            "elapsed_seconds": elapsed,
        }, f, indent=2)
    print(f"  Receipt: {receipt_file}")

    print("\n=== COMPLETE ===")
    print(f"Body evidence extracted for {len(evidence_results)} profiles")
    print("Next: Re-run RM-CIC with body evidence")


if __name__ == "__main__":
    main()
