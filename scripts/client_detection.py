#!/usr/bin/env python3
"""
Client Detection Algorithm V1

Classifies RentMasseur profiles into:
- client_likely: Strong demand-side evidence
- client_possible: Some seeker intent
- unknown: Ambiguous
- provider_likely: Supply-side evidence

Scoring:
+50: Client title terms
+25: Client username terms
+15: Generic/uninformative title
-60: Provider title terms
-35: Provider username terms
"""
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional

CLIENT_TITLE_TERMS = [
    "looking for male massage",
    "looking for massage",
    "looking for male massage ther",
    "need massage",
    "seeking massage",
    "looking for therapist",
    "massage therapist",
]

CLIENT_USERNAME_TERMS = [
    "need", "inneed", "looking", "luv", "love",
    "aching", "sore", "relax", "massage", "body"
]

PROVIDER_TITLE_TERMS = [
    "male masseur",
    "masseur",
    "gay massage in",
    "massage in",
    "bodywork by",
    "therapist in",
]

PROVIDER_USERNAME_TERMS = [
    "masseur", "massage", "hands", "touch", "bodywork",
    "spa", "therapy", "therapist", "healing", "deep", "swedish"
]


def classify_profile(username: str, title: Optional[str] = None) -> Dict:
    """Classify a single profile using the scoring system."""
    u = (username or "").lower()
    t = (title or "").lower()

    score = 0
    reasons = []

    # Client evidence
    for term in CLIENT_TITLE_TERMS:
        if term in t:
            score += 50
            reasons.append(f"client_title:{term}")

    for term in CLIENT_USERNAME_TERMS:
        if term in u:
            score += 25
            reasons.append(f"client_username:{term}")

    if not t or t.strip() == "rentmasseur.com" or "| rentmasseur" in t:
        score += 15
        reasons.append("generic_or_uninformative_title")

    # Provider evidence
    for term in PROVIDER_TITLE_TERMS:
        if term in t:
            score -= 60
            reasons.append(f"provider_title:{term}")

    for term in PROVIDER_USERNAME_TERMS:
        if term in u:
            score -= 35
            reasons.append(f"provider_username:{term}")

    # Classification
    if score >= 50:
        label = "client_likely"
    elif score >= 20:
        label = "client_possible"
    elif score >= -20:
        label = "unknown"
    else:
        label = "provider_likely"

    return {
        "username": username,
        "title": title,
        "score": score,
        "label": label,
        "reasons": reasons
    }


def classify_batch(profiles: List[Dict]) -> List[Dict]:
    """Classify a batch of profiles."""
    results = []
    for p in profiles:
        username = p.get("username", "")
        title = p.get("title")  # May be None for ny_users.json
        result = classify_profile(username, title)
        results.append({**p, **result})
    return results


def generate_report(classified: List[Dict]) -> Dict:
    """Generate classification report with buckets."""
    buckets = {
        "client_likely": [],
        "client_possible": [],
        "unknown": [],
        "provider_likely": []
    }

    for p in classified:
        label = p.get("label", "unknown")
        buckets[label].append(p)

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": len(classified),
        "buckets": {
            k: {
                "count": len(v),
                "percentage": round(len(v) / len(classified) * 100, 1) if classified else 0,
                "users": [p["username"] for p in v]
            }
            for k, v in buckets.items()
        },
        "summary": {
            "client_likely": len(buckets["client_likely"]),
            "client_possible": len(buckets["client_possible"]),
            "unknown": len(buckets["unknown"]),
            "provider_likely": len(buckets["provider_likely"]),
        }
    }

    return report


def main():
    DATA_DIR = Path(__file__).resolve().parent.parent / "data"
    RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"

    print("=== CLIENT DETECTION CLASSIFIER ===")

    # Load 48 visited profiles (with titles)
    visited_file = DATA_DIR / "task1_visit_back.json"
    if visited_file.exists():
        print(f"\n[1] Loading visited profiles: {visited_file}")
        with open(visited_file) as f:
            visited_data = json.load(f)
        visited_profiles = visited_data.get("visited", [])
        print(f"  Found {len(visited_profiles)} visited profiles")

        # Classify
        print("\n[2] Classifying visited profiles...")
        classified_visited = classify_batch(visited_profiles)

        # Generate report
        visited_report = generate_report(classified_visited)
        print(f"\n  Client Likely: {visited_report['summary']['client_likely']}")
        print(f"  Client Possible: {visited_report['summary']['client_possible']}")
        print(f"  Unknown: {visited_report['summary']['unknown']}")
        print(f"  Provider Likely: {visited_report['summary']['provider_likely']}")

        # Save
        RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
        visited_output = RECEIPTS_DIR / f"client_detection_visited_{ts}.json"
        with open(visited_output, "w") as f:
            json.dump({
                "report": visited_report,
                "classified": classified_visited
            }, f, indent=2)
        print(f"  Saved: {visited_output}")
    else:
        print(f"  Visited file not found: {visited_file}")

    # Load 316 NY users (without titles)
    ny_file = DATA_DIR / "ny_users.json"
    if ny_file.exists():
        print(f"\n[3] Loading NY users: {ny_file}")
        with open(ny_file) as f:
            ny_data = json.load(f)
        ny_users = ny_data.get("users", [])
        print(f"  Found {len(ny_users)} NY users")

        # Classify (no titles = generic/uninformative)
        print("\n[4] Classifying NY users (no titles)...")
        classified_ny = classify_batch(ny_users)

        # Generate report
        ny_report = generate_report(classified_ny)
        print(f"\n  Client Likely: {ny_report['summary']['client_likely']}")
        print(f"  Client Possible: {ny_report['summary']['client_possible']}")
        print(f"  Unknown: {ny_report['summary']['unknown']}")
        print(f"  Provider Likely: {ny_report['summary']['provider_likely']}")

        # Save
        ny_output = RECEIPTS_DIR / f"client_detection_ny_{ts}.json"
        with open(ny_output, "w") as f:
            json.dump({
                "report": ny_report,
                "classified": classified_ny
            }, f, indent=2)
        print(f"  Saved: {ny_output}")
    else:
        print(f"  NY users file not found: {ny_file}")

    # Identify profiles for stage 2 verification
    print("\n[5] Profiles for stage 2 verification (client_possible + unknown):")
    for_verification = [
        p for p in classified_ny
        if p.get("label") in ["client_possible", "unknown"]
    ]
    print(f"  Total: {len(for_verification)}")

    verification_file = DATA_DIR / "profiles_for_verification.json"
    with open(verification_file, "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(for_verification),
            "profiles": for_verification
        }, f, indent=2)
    print(f"  Saved: {verification_file}")

    print("\n=== COMPLETE ===")


if __name__ == "__main__":
    main()
