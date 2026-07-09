#!/usr/bin/env python3
"""
Final Client List Generation

Uses the 48 visited profiles with REAL titles (strong evidence) + NY username-based clients (weak evidence).
CrowdSec blocked profile page extraction, so we work with available data.
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


def main():
    DATA_DIR = Path(__file__).resolve().parent.parent / "data"
    RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"

    print("=== FINAL CLIENT LIST GENERATION ===")

    # Load 48 visited profiles (with REAL titles - strong evidence)
    visited_file = DATA_DIR / "task1_visit_back.json"
    with open(visited_file) as f:
        visited_data = json.load(f)
    visited_profiles = visited_data.get("visited", [])
    print(f"\n[1] Loaded {len(visited_profiles)} visited profiles with real titles")

    # Classify visited profiles
    print("\n[2] Classifying visited profiles...")
    classified_visited = []
    for p in visited_profiles:
        result = classify_profile(p["username"], p.get("title"))
        classified_visited.append({
            **p,
            "classification": result,
            "source": "visited_with_title"
        })

    # Load NY users (username only - weak evidence)
    ny_file = DATA_DIR / "ny_users.json"
    with open(ny_file) as f:
        ny_data = json.load(f)
    ny_users = ny_data.get("users", [])
    print(f"\n[3] Loaded {len(ny_users)} NY users (username only)")

    # Classify NY users
    print("\n[4] Classifying NY users...")
    classified_ny = []
    for p in ny_users:
        result = classify_profile(p["username"], None)  # No title
        classified_ny.append({
            **p,
            "classification": result,
            "source": "ny_username_only"
        })

    # Combine and deduplicate
    print("\n[5] Combining and deduplicating...")
    all_profiles = {}
    for p in classified_visited:
        all_profiles[p["username"]] = p
    for p in classified_ny:
        if p["username"] not in all_profiles:
            all_profiles[p["username"]] = p
        else:
            # Keep the visited version (has real title)
            pass

    combined = list(all_profiles.values())
    print(f"  Total unique profiles: {len(combined)}")

    # Filter to clients only (client_likely + client_possible)
    clients = [p for p in combined if p["classification"]["label"] in ["client_likely", "client_possible"]]
    print(f"  Clients (likely + possible): {len(clients)}")

    # Bucket by source
    visited_clients = [p for p in clients if p["source"] == "visited_with_title"]
    ny_clients = [p for p in clients if p["source"] == "ny_username_only"]
    print(f"  From visited (strong evidence): {len(visited_clients)}")
    print(f"  From NY (weak evidence): {len(ny_clients)}")

    # Detailed breakdown
    print("\n[6] Client breakdown:")
    for p in clients:
        label = p["classification"]["label"]
        username = p["username"]
        title = p.get("title", "N/A")
        score = p["classification"]["score"]
        source = p["source"]
        print(f"  [{label}] {username} ({source}) score={score} title='{title[:50]}'")

    # Save final client list
    final_clients = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_clients": len(clients),
        "visited_clients": len(visited_clients),
        "ny_clients": len(ny_clients),
        "clients": clients
    }

    clients_file = DATA_DIR / "final_clients_accurate.json"
    with open(clients_file, "w") as f:
        json.dump(final_clients, f, indent=2)
    print(f"\n[7] Saved final clients: {clients_file}")

    # Save receipt
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    receipt_file = RECEIPTS_DIR / f"final_clients_receipt_{ts}.json"
    with open(receipt_file, "w") as f:
        json.dump({
            "action": "final_client_list_generation",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_profiles": len(combined),
                "total_clients": len(clients),
                "visited_clients": len(visited_clients),
                "ny_clients": len(ny_clients),
            },
            "clients": clients
        }, f, indent=2)
    print(f"  Receipt: {receipt_file}")

    print("\n=== COMPLETE ===")
    print(f"Ready for outreach: {len(clients)} clients")
    print(f"  - {len(visited_clients)} with strong evidence (visited with real titles)")
    print(f"  - {len(ny_clients)} with weak evidence (username only)")


if __name__ == "__main__":
    main()
