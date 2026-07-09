#!/usr/bin/env python3
"""
RM-CIC: RentMasseur Client Intent Classifier

5-layer evidence classifier:
1. Title classifier (highest signal)
2. Username classifier (medium signal)
3. Profile-body classifier (high signal, requires crawl)
4. Negative evidence classifier (provider penalties)
5. Lead-value classifier (commercial targeting)

Buckets:
A — client_likely: explicit demand-side language
B — client_possible: weak but meaningful demand-side clues
C — unknown: generic page, ambiguous
D — provider_likely: provider/competitor

Rule: Never message provider_likely. Only contact client_likely.
"""
import json
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any

# Layer 1: Client title terms (strongest evidence)
CLIENT_TITLE_TERMS = {
    "looking for male massage": 80,
    "looking for massage": 75,
    "looking for therapist": 70,
    "looking for male massage ther": 80,
    "seeking massage": 65,
    "need massage": 60,
    "want massage": 60,
    "want a massage": 60,
    "need a massage": 60,
}

# Layer 2: Client username terms (medium evidence)
CLIENT_USERNAME_TERMS = {
    "inneed": 35,
    "looking": 30,
    "need": 25,
    "luv": 20,
    "love": 20,
    "wants": 20,
    "sore": 20,
    "aching": 20,
    "relax": 15,
    "body": 10,
}

# Layer 4: Provider title terms (negative evidence)
PROVIDER_TITLE_TERMS = {
    "male masseur": -90,
    "masseur": -80,
    "gay massage in": -75,
    "massage in": -65,
    "bodywork by": -60,
    "therapist in": -55,
    "deep tissue": -50,
    "swedish": -50,
    "sports massage": -50,
    "therapeutic massage": -50,
    "tantric": -45,
}

# Layer 4: Provider username terms (negative evidence)
PROVIDER_USERNAME_TERMS = {
    "masseur": -55,
    "massage": -45,
    "bodywork": -40,
    "hands": -35,
    "touch": -35,
    "healing": -35,
    "spa": -35,
    "therapist": -35,
    "deep": -30,
    "swedish": -30,
    "sportsmassage": -35,
}

# Layer 3: Client body terms (for profile-body scan)
CLIENT_BODY_TERMS = {
    "looking for a masseur": 100,
    "looking for massage therapist": 90,
    "looking for a massage therapist": 90,
    "seeking massage": 85,
    "need a massage": 80,
    "want a massage": 70,
    "can host": 35,
    "visiting nyc": 30,
    "available tonight": 30,
}

# Layer 3: Provider body terms (for profile-body scan)
PROVIDER_BODY_TERMS = {
    "i offer massage": -100,
    "book me": -90,
    "my rates": -85,
    "incall": -80,
    "outcall": -80,
    "deep tissue": -75,
    "swedish massage": -70,
    "sports massage": -70,
    "therapeutic massage": -65,
    "licensed massage therapist": -60,
    "my clients": -60,
    "services": -45,
    "session": -35,
    "availability": -25,
}


def normalize(text: str) -> str:
    """Normalize text for matching."""
    text = text or ""
    text = text.lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def apply_terms(text: str, terms: Dict[str, int], prefix: str) -> tuple[int, List[str]]:
    """Apply term scoring and return score + reasons."""
    score = 0
    reasons = []
    for term, weight in terms.items():
        if term in text:
            score += weight
            reasons.append(f"{prefix}:{term}:{weight}")
    return score, reasons


def classify_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a single profile using 5-layer evidence."""
    username = normalize(profile.get("username", ""))
    title = normalize(profile.get("title", ""))
    body = normalize(profile.get("body", ""))
    city = normalize(profile.get("city", ""))

    score = 0
    reasons: List[str] = []

    # Layer 1: Title classifier
    s, r = apply_terms(title, CLIENT_TITLE_TERMS, "client_title")
    score += s
    reasons.extend(r)

    # Layer 2: Username classifier
    s, r = apply_terms(username, CLIENT_USERNAME_TERMS, "client_username")
    score += s
    reasons.extend(r)

    # Layer 4: Provider title penalties
    s, r = apply_terms(title, PROVIDER_TITLE_TERMS, "provider_title")
    score += s
    reasons.extend(r)

    # Layer 4: Provider username penalties
    s, r = apply_terms(username, PROVIDER_USERNAME_TERMS, "provider_username")
    score += s
    reasons.extend(r)

    # Layer 3: Body classifier (if available)
    if body:
        s, r = apply_terms(body, CLIENT_BODY_TERMS, "client_body")
        score += s
        reasons.extend(r)
        s, r = apply_terms(body, PROVIDER_BODY_TERMS, "provider_body")
        score += s
        reasons.extend(r)

    # Generic title bonus
    if not title or title == "rentmasseur.com" or "| rentmasseur" in title:
        score += 10
        reasons.append("generic_or_blank_title:+10")

    # Classification
    if score >= 70:
        label = "client_likely"
        confidence = min(0.98, 0.70 + (score - 70) / 200)
        next_action = "export_to_A_clients_review"
    elif score >= 35:
        label = "client_possible"
        confidence = min(0.75, 0.45 + (score - 35) / 150)
        next_action = "crawl_profile_body_or_manual_review"
    elif score >= -25:
        label = "unknown"
        confidence = 0.40
        next_action = "low_priority_revisit"
    else:
        label = "provider_likely"
        confidence = min(0.98, 0.70 + abs(score) / 200)
        next_action = "exclude_from_client_outreach"

    return {
        "username": profile.get("username"),
        "url": profile.get("url"),
        "city": profile.get("city"),
        "title": profile.get("title"),
        "client_score": score,
        "label": label,
        "confidence": round(confidence, 2),
        "reasons": reasons,
        "next_action": next_action
    }


def main():
    DATA_DIR = Path(__file__).resolve().parent.parent / "data"
    RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"

    # Ensure directories exist
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

    print("=== RM-CIC: RentMasseur Client Intent Classifier ===")

    # Load 48 visited profiles (with titles)
    visited_file = DATA_DIR / "task1_visit_back.json"
    visited_profiles = []
    if visited_file.exists():
        with open(visited_file) as f:
            visited_data = json.load(f)
        visited_profiles = visited_data.get("visited", [])
        print(f"\n[1] Loaded {len(visited_profiles)} visited profiles with titles")
    else:
        print(f"\n[1] Visited file not found: {visited_file}")

    # Load 316 NY users (username only)
    ny_file = DATA_DIR / "ny_users.json"
    ny_users = []
    if ny_file.exists():
        with open(ny_file) as f:
            ny_data = json.load(f)
        ny_users = ny_data.get("users", [])
        print(f"[2] Loaded {len(ny_users)} NY users (username only)")
    else:
        print(f"[2] NY users file not found: {ny_file}")

    # Combine and deduplicate
    print("\n[3] Combining and deduplicating...")
    all_profiles = {}
    for p in visited_profiles:
        all_profiles[p["username"]] = {**p, "source": "visited"}
    for p in ny_users:
        if p["username"] not in all_profiles:
            all_profiles[p["username"]] = {**p, "source": "ny"}
    combined = list(all_profiles.values())
    print(f"  Total unique profiles: {len(combined)}")

    # Classify all profiles
    print("\n[4] Classifying profiles...")
    classified = []
    for p in combined:
        result = classify_profile(p)
        classified.append({**p, "classification": result})

    # Bucket into A, B, C, D
    print("\n[5] Bucketing profiles...")
    buckets = {
        "client_likely": [],
        "client_possible": [],
        "unknown": [],
        "provider_likely": []
    }
    for p in classified:
        label = p["classification"]["label"]
        buckets[label].append(p)

    # Print summary
    print(f"\n  A (client_likely): {len(buckets['client_likely'])}")
    print(f"  B (client_possible): {len(buckets['client_possible'])}")
    print(f"  C (unknown): {len(buckets['unknown'])}")
    print(f"  D (provider_likely): {len(buckets['provider_likely'])}")

    # Save individual bucket files
    print("\n[6] Saving bucket files...")
    for label, profiles in buckets.items():
        bucket_letter = {"client_likely": "A", "client_possible": "B", "unknown": "C", "provider_likely": "D"}[label]
        output_file = DATA_DIR / f"clients_{bucket_letter}_{label}.json"
        with open(output_file, "w") as f:
            json.dump({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "count": len(profiles),
                "profiles": profiles
            }, f, indent=2)
        print(f"  Saved: {output_file}")

    # Save classification audit
    audit_file = DATA_DIR / "classification_audit.json"
    with open(audit_file, "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_profiles": len(classified),
            "classified": classified
        }, f, indent=2)
    print(f"  Saved audit: {audit_file}")

    # Save client candidates (A + B only)
    client_candidates = buckets["client_likely"] + buckets["client_possible"]
    candidates_file = DATA_DIR / "client_candidates.json"
    with open(candidates_file, "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "count": len(client_candidates),
            "profiles": client_candidates
        }, f, indent=2)
    print(f"  Saved candidates: {candidates_file}")

    # Save summary
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_profiles": len(combined),
        "visited_profiles": len(visited_profiles),
        "ny_users": len(ny_users),
        "client_likely": len(buckets["client_likely"]),
        "client_possible": len(buckets["client_possible"]),
        "unknown": len(buckets["unknown"]),
        "provider_likely": len(buckets["provider_likely"]),
        "next_best_action": "crawl profile bodies for client_possible and unknown only"
    }
    summary_file = DATA_DIR / "client_detection_summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Saved summary: {summary_file}")

    # Save receipt
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    receipt_file = RECEIPTS_DIR / f"rm_cic_{ts}.json"
    with open(receipt_file, "w") as f:
        json.dump({
            "action": "rm_cic_classification",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "buckets": {k: len(v) for k, v in buckets.items()}
        }, f, indent=2)
    print(f"  Receipt: {receipt_file}")

    print("\n=== COMPLETE ===")
    print(f"Client candidates (A+B): {len(client_candidates)}")
    print(f"  - A (contact-ready): {len(buckets['client_likely'])}")
    print(f"  - B (needs verification): {len(buckets['client_possible'])}")
    print(f"Next action: Crawl profile bodies for B and C buckets")


if __name__ == "__main__":
    main()
