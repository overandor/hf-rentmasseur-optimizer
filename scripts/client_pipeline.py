#!/usr/bin/env python3
"""
Client-Focused Pipeline V1

Pipeline:
1. Load classified profiles
2. Stage 2: Extract profile evidence for ambiguous profiles (client_possible + unknown)
3. Re-classify with deeper evidence (headline, bio, services, looking-for)
4. Calculate lead_value_score for commercial targeting
5. Generate final client list for outreach

Lead Value Score = client_probability + recency + location_quality + intent_strength - ambiguity_penalty
"""
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from rm_traffic.api_client import RentMasseurAPI

BASE = "https://rentmasseur.com"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"

# Stage 2: Provider signals (exclude)
PROVIDER_SIGNALS = [
    "prices", "rates", "hour", "incall", "outcall", "book me", "book now",
    "i offer", "my massage", "my services", "certified", "therapeutic",
    "deep tissue", "swedish", "sports massage", "book session",
    "appointment", "schedule", "booking", "payment", "cash", "credit"
]

# Stage 2: Client signals (include)
CLIENT_SIGNALS = [
    "looking for", "need", "seeking", "want a massage", "prefer",
    "can host", "available today", "looking for therapist", "need relief",
    "looking for male", "seeking male", "need someone", "find a"
]


def extract_profile_evidence(username: str, cookies: dict, token: str) -> Dict:
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
        "looking_for": None,
        "has_prices": False,
        "has_booking": False,
        "raw_length": 0,
    }

    try:
        r = req.get(url, headers=headers, cookies=cookies, timeout=15, allow_redirects=True)
        if r.status_code != 200:
            return {**evidence, "error": f"HTTP {r.status_code}"}

        text = r.text.lower()
        evidence["raw_length"] = len(text)

        # Extract title from title tag
        title_match = re.search(r'<title>([^<]+)</title>', r.text)
        if title_match:
            evidence["title"] = title_match.group(1).strip()

        # Simple text extraction (can be improved with proper parsing)
        evidence["bio"] = text[:2000]  # First 2KB as sample

        # Detect signals
        for signal in PROVIDER_SIGNALS:
            if signal in text:
                if "price" in signal or "rate" in signal or "hour" in signal:
                    evidence["has_prices"] = True
                if "book" in signal:
                    evidence["has_booking"] = True

        # Count client signals
        client_signal_count = sum(1 for s in CLIENT_SIGNALS if s in text)
        evidence["client_signal_count"] = client_signal_count

    except Exception as e:
        evidence["error"] = str(e)[:100]

    return evidence


def calculate_lead_value_score(profile: Dict, evidence: Optional[Dict] = None) -> Dict:
    """Calculate lead_value_score for commercial targeting."""
    username = profile.get("username", "")
    city = profile.get("city", "")
    label = profile.get("label", "unknown")
    score = profile.get("score", 0)

    # Base client probability (0-100)
    client_probability = max(0, min(100, score + 50))  # Normalize to 0-100

    # Recency (visited recently = higher)
    recency = 50 if profile.get("visited_status") == "visited" else 30

    # Location quality (Manhattan/Brooklyn/Bronx = higher)
    location_quality = 50
    if city in ["manhattan-ny", "brooklyn-ny", "bronx-ny"]:
        location_quality = 80
    elif city in ["queens-ny", "new-york-ny"]:
        location_quality = 60

    # Intent strength (from evidence)
    intent_strength = 30
    if evidence:
        client_signal_count = evidence.get("client_signal_count", 0)
        intent_strength = 30 + (client_signal_count * 10)
        if evidence.get("has_prices"):
            intent_strength -= 20  # Provider signal
        if evidence.get("has_booking"):
            intent_strength -= 20  # Provider signal

    # Ambiguity penalty
    ambiguity_penalty = 0
    if label == "unknown":
        ambiguity_penalty = 20
    if label == "provider_likely":
        ambiguity_penalty = 50

    # Calculate lead value score
    lead_value_score = (
        client_probability * 0.4 +
        recency * 0.2 +
        location_quality * 0.2 +
        intent_strength * 0.2 -
        ambiguity_penalty
    )

    # Bucket
    if lead_value_score >= 70:
        bucket = "A"  # Confirmed seeker, contact-ready
    elif lead_value_score >= 50:
        bucket = "B"  # Likely seeker, needs profile read
    elif lead_value_score >= 30:
        bucket = "C"  # Unknown, low priority
    else:
        bucket = "D"  # Provider/competitor, exclude

    return {
        "username": username,
        "lead_value_score": round(lead_value_score, 1),
        "bucket": bucket,
        "components": {
            "client_probability": client_probability,
            "recency": recency,
            "location_quality": location_quality,
            "intent_strength": intent_strength,
            "ambiguity_penalty": ambiguity_penalty,
        }
    }


def main():
    print("=== CLIENT-FOCUSED PIPELINE V1 ===")

    # Load classified profiles
    verification_file = DATA_DIR / "profiles_for_verification.json"
    if not verification_file.exists():
        print(f"Verification file not found: {verification_file}")
        return

    with open(verification_file) as f:
        verification_data = json.load(f)

    profiles = verification_data.get("profiles", [])
    print(f"\n[1] Loaded {len(profiles)} profiles for stage 2 verification")

    # Try to use existing cookies from ny_visit if available
    print("\n[2] Setting up auth...")
    token = ""
    cookies = {}

    # Try API login (may be blocked by captcha)
    api = RentMasseurAPI()
    if api.login("karpathianwolf", "os.environ.get("RM_PASSWORD", "")"):
        token = api.session.headers.get("Authorization", "").replace("Bearer ", "")
        cookies = {c.name: c.value for c in api.session.cookies}
        print("  API login OK")
    else:
        print("  API login blocked, proceeding without auth (public profiles)")
        # Profile pages may be accessible without auth

    # Stage 2: Extract profile evidence
    print(f"\n[3] Extracting profile evidence (33 threads)...")
    evidence_results = []

    def extract_one(p):
        return extract_profile_evidence(p["username"], cookies, token)

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=33) as pool:
        futures = {pool.submit(extract_one, p): p for p in profiles}
        for i, fut in enumerate(as_completed(futures)):
            r = fut.result()
            evidence_results.append(r)
            if (i + 1) % 50 == 0 or i == len(profiles) - 1:
                print(f"  [{i+1}/{len(profiles)}] extracted")

    elapsed = time.time() - t0
    print(f"  Done: {len(evidence_results)} extracted, {elapsed:.1f}s")

    # Map evidence to profiles
    evidence_map = {e["username"]: e for e in evidence_results}

    # Re-classify with deeper evidence
    print("\n[4] Re-classifying with deeper evidence...")
    enriched_profiles = []
    for p in profiles:
        username = p["username"]
        evidence = evidence_map.get(username, {})
        lead_value = calculate_lead_value_score(p, evidence)
        enriched_profiles.append({
            **p,
            "evidence": evidence,
            "lead_value": lead_value
        })

    # Generate final client list (A + B buckets)
    print("\n[5] Generating final client list...")
    final_clients = [p for p in enriched_profiles if p["lead_value"]["bucket"] in ["A", "B"]]

    # Bucket summary
    bucket_counts = {}
    for p in enriched_profiles:
        bucket = p["lead_value"]["bucket"]
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

    print(f"  Bucket A (contact-ready): {bucket_counts.get('A', 0)}")
    print(f"  Bucket B (likely seeker): {bucket_counts.get('B', 0)}")
    print(f"  Bucket C (low priority): {bucket_counts.get('C', 0)}")
    print(f"  Bucket D (exclude): {bucket_counts.get('D', 0)}")
    print(f"  Final clients (A+B): {len(final_clients)}")

    # Save results
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")

    # Full enriched data
    enriched_file = RECEIPTS_DIR / f"client_pipeline_enriched_{ts}.json"
    with open(enriched_file, "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": len(enriched_profiles),
            "bucket_counts": bucket_counts,
            "final_clients_count": len(final_clients),
            "profiles": enriched_profiles
        }, f, indent=2)
    print(f"\n  Saved enriched data: {enriched_file}")

    # Final client list (A+B only)
    clients_file = DATA_DIR / "final_clients.json"
    with open(clients_file, "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(final_clients),
            "clients": final_clients
        }, f, indent=2)
    print(f"  Saved final clients: {clients_file}")

    print("\n=== COMPLETE ===")
    print(f"Ready for outreach: {len(final_clients)} clients in A+B buckets")


if __name__ == "__main__":
    main()
