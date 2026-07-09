#!/usr/bin/env python3
"""
Final Classification: Merge NY + US results with RM-CIC V3
"""
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "rm_cic.db"

# Import classifier from V3
import sys
sys.path.insert(0, str(Path(__file__).parent))
from rm_cic_v3 import classify_profile, clean_text, contains_any


def main():
    print("=== FINAL CLASSIFICATION: NY + US ===")

    # Load US users
    us_file = DATA_DIR / "us_users_raw.json"
    with open(us_file) as f:
        us_data = json.load(f)
    us_users = us_data.get("users", [])
    print(f"\n[1] Loaded {len(us_users)} US profiles")

    # Load NY users
    ny_file = DATA_DIR / "ny_users.json"
    with open(ny_file) as f:
        ny_data = json.load(f)
    ny_users = ny_data.get("users", [])
    print(f"[2] Loaded {len(ny_users)} NY profiles")

    # Load visited for titles
    visited_file = DATA_DIR / "task1_visit_back.json"
    with open(visited_file) as f:
        visited_data = json.load(f)
    visited_profiles = visited_data.get("visited", [])
    title_map = {p["username"]: p.get("title") for p in visited_profiles}
    print(f"[3] Loaded {len(visited_profiles)} visited profiles for titles")

    # Merge all
    all_profiles = {}
    for p in ny_users:
        username = p["username"]
        all_profiles[username] = {
            **p,
            "title": title_map.get(username),
            "visited": username in title_map,
            "body_text": "",
            "source": "ny"
        }

    for p in us_users:
        username = p["username"]
        if username not in all_profiles:
            all_profiles[username] = {
                **p,
                "title": None,
                "visited": False,
                "body_text": "",
                "source": "us"
            }

    print(f"[4] Merged: {len(all_profiles)} unique profiles")

    # Classify
    print("\n[5] Classifying with RM-CIC V3...")
    classified = []
    for username, p in all_profiles.items():
        result = classify_profile(p)
        classified.append({**p, **result})

    # Bucket
    buckets = {"A": [], "B": [], "C": [], "D": [], "X": []}
    for p in classified:
        buckets[p["bucket"]].append(p)

    print(f"\n  A (contact-ready): {len(buckets['A'])}")
    print(f"  B (manual review): {len(buckets['B'])}")
    print(f"  C (keep in DB): {len(buckets['C'])}")
    print(f"  D (exclude): {len(buckets['D'])}")
    print(f"  X (error): {len(buckets['X'])}")

    # Save to database
    print("\n[6] Saving to SQLite database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for p in classified:
        cursor.execute("""
            INSERT OR REPLACE INTO profiles 
            (username, name, city, url, first_seen_ts, last_seen_ts, source)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            p["username"],
            p.get("name"),
            p.get("city"),
            p.get("url"),
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
            p.get("source", "merged")
        ))

        cursor.execute("""
            INSERT OR REPLACE INTO profile_classifications
            (username, label, client_score, lead_value, confidence, reasons_json, classified_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            p["username"],
            p["label"],
            p["client_score"],
            p["lead_value"],
            p["confidence"],
            json.dumps(p["reasons"]),
            datetime.now(timezone.utc).isoformat()
        ))

        if p["bucket"] in ["A", "B"]:
            cursor.execute("""
                INSERT OR REPLACE INTO outreach_queue
                (username, url, city, label, lead_value, status, created_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                p["username"],
                p.get("url"),
                p.get("city"),
                p["label"],
                p["lead_value"],
                "pending",
                datetime.now(timezone.utc).isoformat()
            ))

    conn.commit()
    conn.close()
    print(f"  Saved to: {DB_PATH}")

    # Save final JSON
    with open(DATA_DIR / "final_classification.json", "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_profiles": len(classified),
            "ny_profiles": len(ny_users),
            "us_profiles": len(us_users),
            "visited_profiles": len(visited_profiles),
            "summary": {
                "A_contact_ready": len(buckets["A"]),
                "B_manual_review": len(buckets["B"]),
                "C_keep_in_db": len(buckets["C"]),
                "D_exclude": len(buckets["D"]),
                "X_error": len(buckets["X"]),
                "client_candidates": len(buckets["A"]) + len(buckets["B"]),
                "providers_excluded": len(buckets["D"]) + len(buckets["X"])
            },
            "profiles": classified
        }, f, indent=2)
    print(f"  Saved: {DATA_DIR / 'final_classification.json'}")

    print("\n=== COMPLETE ===")
    print(f"Total profiles: {len(classified)}")
    print(f"Client candidates (A+B): {len(buckets['A']) + len(buckets['B'])}")
    print(f"Providers excluded (D+X): {len(buckets['D']) + len(buckets['X'])}")
    print(f"\nREALISTIC ASSESSMENT:")
    print(f"- RentMasseur is primarily a provider platform")
    print(f"- Client/seeker profiles are a minority")
    print(f"- 1000+ clients may not be achievable on this platform")
    print(f"- Current data: {len(ny_users)} NY + {len(us_users)} US = {len(classified)} total")
    print(f"- Confirmed clients: {len(buckets['A'])}")
    print(f"- Possible clients: {len(buckets['B'])}")


if __name__ == "__main__":
    main()
