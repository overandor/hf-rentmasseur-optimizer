#!/usr/bin/env python3
"""
RM-CIC V3: Evidence Hierarchy + Override Logic + SQLite Database

Evidence hierarchy:
Tier 1: Body/profile text (most important)
Tier 2: Page title
Tier 3: Username
Tier 4: City (routing only)

Labels:
client_confirmed - explicit demand-side language
client_possible - weak demand-side clues
unknown - no useful evidence
provider_possible - some provider-like branding
provider_confirmed - clear service advertising

Override logic:
- Strong provider language → provider_confirmed (even if username looks client-like)
- Strong seeker language → client_confirmed (unless body advertises services)

Lead value scoring for commercial targeting.
"""
import csv
import json
import re
import sqlite3
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"
DB_PATH = DATA_DIR / "rm_cic.db"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

# Evidence terms
CLIENT_STRONG = [
    "looking for male massage",
    "looking for massage therapist",
    "looking for a massage therapist",
    "looking for masseur",
    "looking for massage",
    "need a massage",
    "need massage",
    "in need of massage",
    "seeking massage",
    "seeking bodywork",
    "massage wanted",
    "want a massage",
    "looking to book",
    "looking for therapeutic massage",
]

CLIENT_WEAK = [
    "looking for",
    "seeking",
    "need",
    "wanted",
    "can host",
    "available today",
    "prefer",
]

CLIENT_USERNAME = [
    "need",
    "inneed",
    "looking",
    "luv",
    "love",
    "aching",
    "sore",
    "tired",
    "relax",
    "body",
]

PROVIDER_STRONG = [
    "male masseur",
    "professional masseur",
    "certified masseur",
    "gay massage in",
    "massage in new york",
    "massage in manhattan",
    "massage in brooklyn",
    "massage in bronx",
    "deep tissue massage",
    "swedish massage",
    "sports massage",
    "therapeutic massage",
    "bodywork by",
    "i offer",
    "my massage",
    "book me",
    "incall",
    "outcall",
    "rates",
    "pricing",
    "session",
]

PROVIDER_USERNAME = [
    "masseur",
    "massuer",
    "massage",
    "hands",
    "touch",
    "bodywork",
    "spa",
    "therapy",
    "therapist",
    "healing",
    "deep",
    "swedish",
    "sportsmassage",
]


def clean_text(value: Optional[str]) -> str:
    value = value or ""
    value = value.lower()
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def contains_any(text: str, terms: List[str]) -> List[str]:
    return [term for term in terms if term in text]


def init_database():
    """Initialize SQLite database with schema."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            username TEXT PRIMARY KEY,
            name TEXT,
            city TEXT,
            url TEXT,
            first_seen_ts TEXT,
            last_seen_ts TEXT,
            source TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profile_visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            visited_ts TEXT,
            status TEXT,
            title TEXT,
            body_text TEXT,
            http_status INTEGER,
            error TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profile_classifications (
            username TEXT PRIMARY KEY,
            label TEXT,
            client_score REAL,
            lead_value REAL,
            confidence REAL,
            reasons_json TEXT,
            classified_ts TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS outreach_queue (
            username TEXT PRIMARY KEY,
            url TEXT,
            city TEXT,
            label TEXT,
            lead_value REAL,
            status TEXT,
            created_ts TEXT
        )
    """)

    conn.commit()
    conn.close()
    print(f"Database initialized: {DB_PATH}")


def classify_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """V3 classification with evidence hierarchy and override logic."""
    username = clean_text(profile.get("username"))
    title = clean_text(profile.get("title"))
    body = clean_text(profile.get("body_text", ""))
    city = clean_text(profile.get("city"))

    # Evidence hierarchy: body + title combined
    combined_text = f"{title} {body}".strip()

    score = 0
    reasons = []

    # Tier 1+2: Body + Title (strong evidence)
    strong_client_hits = contains_any(combined_text, CLIENT_STRONG)
    weak_client_hits = contains_any(combined_text, CLIENT_WEAK)

    # Tier 3: Username (weak evidence)
    client_username_hits = contains_any(username, CLIENT_USERNAME)

    # Provider evidence
    strong_provider_hits = contains_any(combined_text, PROVIDER_STRONG)
    provider_username_hits = contains_any(username, PROVIDER_USERNAME)

    # Scoring
    for hit in strong_client_hits:
        score += 80
        reasons.append(f"+80 strong_client_text:{hit}")

    for hit in weak_client_hits:
        score += 25
        reasons.append(f"+25 weak_client_text:{hit}")

    for hit in client_username_hits:
        score += 20
        reasons.append(f"+20 client_username:{hit}")

    if not title or title == "rentmasseur.com" or "| rentmasseur" in title:
        score += 15
        reasons.append("+15 generic_or_blank_title")

    for hit in strong_provider_hits:
        score -= 100
        reasons.append(f"-100 strong_provider_text:{hit}")

    for hit in provider_username_hits:
        score -= 45
        reasons.append(f"-45 provider_username:{hit}")

    # Override logic
    if strong_provider_hits and not strong_client_hits:
        label = "provider_confirmed"
        confidence = min(100, 80 + 5 * len(strong_provider_hits))
    elif strong_client_hits and not strong_provider_hits:
        label = "client_confirmed"
        confidence = min(100, 80 + 5 * len(strong_client_hits))
    else:
        if score >= 80:
            label = "client_confirmed"
            confidence = min(100, score)
        elif score >= 40:
            label = "client_possible"
            confidence = min(79, score + 20)
        elif score >= -20:
            label = "unknown"
            confidence = 40
        elif score >= -80:
            label = "provider_possible"
            confidence = min(79, abs(score) + 20)
        else:
            label = "provider_confirmed"
            confidence = min(100, abs(score))

    # Lead value scoring
    location_score = 0
    if "manhattan" in city:
        location_score = 20
    elif "brooklyn" in city:
        location_score = 15
    elif "bronx" in city:
        location_score = 10

    recency_score = 20 if profile.get("visited") else 0

    intent_score = 30 if strong_client_hits else (15 if weak_client_hits else 0)

    ambiguity_penalty = -20 if (not title or title == "rentmasseur.com") else 0

    provider_penalty = -100 if strong_provider_hits else 0

    lead_value = score + location_score + recency_score + intent_score + ambiguity_penalty + provider_penalty

    # Outreach bucket
    if label == "client_confirmed" and confidence >= 70:
        action = "queue_for_manual_review_or_allowed_platform_contact"
        bucket = "A"
    elif label == "client_possible" and confidence >= 50:
        action = "needs_manual_review"
        bucket = "B"
    elif label == "unknown":
        action = "keep_in_database_no_action"
        bucket = "C"
    elif label in ["provider_possible", "provider_confirmed"]:
        action = "exclude"
        bucket = "D"
    else:
        action = "bad_blank_error_page"
        bucket = "X"

    return {
        "username": profile.get("username"),
        "city": profile.get("city"),
        "url": profile.get("url"),
        "title": profile.get("title"),
        "client_score": score,
        "lead_value": lead_value,
        "label": label,
        "confidence": confidence,
        "reasons": reasons,
        "action": action,
        "bucket": bucket
    }


def main():
    print("=== RM-CIC V3: Evidence Hierarchy + SQLite ===")

    # Initialize database
    init_database()

    # Load data
    ny_file = DATA_DIR / "ny_users.json"
    with open(ny_file) as f:
        ny_data = json.load(f)
    ny_users = ny_data.get("users", [])
    print(f"\n[1] Loaded {len(ny_users)} NY users")

    visited_file = DATA_DIR / "task1_visit_back.json"
    with open(visited_file) as f:
        visited_data = json.load(f)
    visited_profiles = visited_data.get("visited", [])
    print(f"[2] Loaded {len(visited_profiles)} visited profiles")

    # Merge
    title_map = {p["username"]: p.get("title") for p in visited_profiles}
    merged = []
    for p in ny_users:
        username = p["username"]
        title = title_map.get(username)
        merged.append({
            **p,
            "title": title,
            "visited": username in title_map,
            "body_text": ""  # No body evidence yet
        })

    # Add visited-only
    for p in visited_profiles:
        username = p["username"]
        if username not in {u["username"] for u in ny_users}:
            merged.append({
                "username": username,
                "name": username,
                "city": None,
                "url": f"https://rentmasseur.com/{username}",
                "title": p.get("title"),
                "visited": True,
                "body_text": ""
            })

    print(f"[3] Merged: {len(merged)} profiles")

    # Classify
    print("\n[4] Classifying with V3 algorithm...")
    classified = []
    for p in merged:
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
    print("\n[5] Saving to SQLite database...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for p in classified:
        # Insert/update profile
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
            "ny_users"
        ))

        # Insert classification
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

        # Insert into outreach queue if A or B
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

    # Export CSVs
    print("\n[6] Exporting CSVs...")
    clients = buckets["A"] + buckets["B"]
    with open(DATA_DIR / "clients_A_B_v3.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["username", "title", "city", "url", "label", "client_score", "lead_value", "confidence", "action"])
        for p in clients:
            writer.writerow([p["username"], p["title"], p["city"], p["url"], p["label"], p["client_score"], p["lead_value"], p["confidence"], p["action"]])
    print(f"  Saved: {DATA_DIR / 'clients_A_B_v3.csv'}")

    providers = buckets["D"] + buckets["X"]
    with open(DATA_DIR / "providers_excluded_v3.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["username", "title", "city", "url", "label", "client_score", "lead_value", "confidence", "action"])
        for p in providers:
            writer.writerow([p["username"], p["title"], p["city"], p["url"], p["label"], p["client_score"], p["lead_value"], p["confidence"], p["action"]])
    print(f"  Saved: {DATA_DIR / 'providers_excluded_v3.csv'}")

    # Save JSON audit
    with open(DATA_DIR / "classification_audit_v3.json", "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total": len(classified),
            "classified": classified
        }, f, indent=2)
    print(f"  Saved: {DATA_DIR / 'classification_audit_v3.json'}")

    # Receipt
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    with open(RECEIPTS_DIR / f"rm_cic_v3_{ts}.json", "w") as f:
        json.dump({
            "action": "rm_cic_v3",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total": len(classified),
                "A": len(buckets["A"]),
                "B": len(buckets["B"]),
                "C": len(buckets["C"]),
                "D": len(buckets["D"]),
                "X": len(buckets["X"]),
                "clients": len(clients),
                "providers": len(providers)
            }
        }, f, indent=2)
    print(f"  Receipt: {RECEIPTS_DIR / f'rm_cic_v3_{ts}.json'}")

    print("\n=== COMPLETE ===")
    print(f"Client candidates (A+B): {len(clients)}")
    print(f"Providers excluded (D+X): {len(providers)}")
    print(f"Database: {DB_PATH}")


if __name__ == "__main__":
    main()
