#!/usr/bin/env python3
"""
Client-Intent Classifier V1.0

Production-grade client intelligence classifier with:
- Two-score model (client_score and provider_score)
- Evidence hierarchy (body > title > username > city)
- Updated phrase dictionaries with specified weights
- Lead value scoring with location/intent/recency/ambiguity/compliance
- SQLite database integration
- Output file generation
- Visit priority algorithm
"""
import csv
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"
DB_PATH = DATA_DIR / "rm_cic.db"

DATA_DIR.mkdir(parents=True, exist_ok=True)
RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

# Updated phrase dictionaries as specified
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
    "looking for deep tissue",
]

CLIENT_CONTEXT = [
    "looking for",
    "seeking",
    "need",
    "wanted",
    "want",
    "can host",
    "available today",
    "visiting",
    "hotel",
    "prefer",
]

CLIENT_PROBLEM = [
    "aching",
    "sore",
    "stiff",
    "tired",
    "recovery",
    "back pain",
    "neck pain",
    "shoulder pain",
    "after gym",
    "post workout",
    "travel stiffness",
]

CLIENT_USERNAME = [
    "inneed",
    "need",
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
    "licensed massage therapist",
    "gay massage in",
    "massage in new york",
    "massage in manhattan",
    "massage in brooklyn",
    "massage in bronx",
    "bodywork by",
    "i offer",
    "my massage",
    "book me",
    "book your session",
    "incall",
    "outcall",
    "rates",
    "pricing",
    "appointment",
    "appointments",
]

PROVIDER_SERVICES = [
    "deep tissue massage",
    "swedish massage",
    "sports massage",
    "therapeutic massage",
    "tantric massage",
    "relaxing massage",
    "bodywork",
    "60 minutes",
    "90 minutes",
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


def clean(value: Optional[str]) -> str:
    """Normalize text for comparison."""
    value = value or ""
    value = value.lower()
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def hits(text: str, terms: List[str]) -> List[str]:
    """Find which terms appear in text."""
    return [term for term in terms if term in text]


def classify_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Classify a profile using the two-score model."""
    username = clean(profile.get("username"))
    title = clean(profile.get("title"))
    body = clean(profile.get("body_text"))
    city = clean(profile.get("city"))
    url = profile.get("url")

    combined = f"{title} {body}".strip()

    client_score = 0
    provider_score = 0
    reasons = []

    # Strong client signals
    for term in hits(combined, CLIENT_STRONG):
        client_score += 90
        reasons.append(f"client_strong:{term}")

    # Client context near bodywork
    for term in hits(combined, CLIENT_CONTEXT):
        if "massage" in combined or "bodywork" in combined or "therapist" in combined:
            client_score += 50
            reasons.append(f"client_context_near_bodywork:{term}")

    # Client problem language
    for term in hits(combined, CLIENT_PROBLEM):
        client_score += 25
        reasons.append(f"client_problem:{term}")

    # Client username hints
    for term in hits(username, CLIENT_USERNAME):
        client_score += 20
        reasons.append(f"client_username:{term}")

    # Generic title bonus
    if not title or title == "rentmasseur.com" or "| rentmasseur" in title:
        client_score += 15
        reasons.append("generic_or_blank_title")

    # Strong provider signals
    for term in hits(combined, PROVIDER_STRONG):
        provider_score += 100
        reasons.append(f"provider_strong:{term}")

    # Provider services
    for term in hits(combined, PROVIDER_SERVICES):
        provider_score += 70
        reasons.append(f"provider_service:{term}")

    # Provider username hints
    for term in hits(username, PROVIDER_USERNAME):
        provider_score += 45
        reasons.append(f"provider_username:{term}")

    net = client_score - provider_score

    # Classification with overrides
    if provider_score >= 100 and client_score < 80:
        label = "provider_confirmed"
        confidence = min(100, 80 + provider_score // 10)
    elif client_score >= 90 and provider_score < 70:
        label = "client_confirmed"
        confidence = min(100, 80 + client_score // 10)
    elif client_score >= 90 and provider_score >= 70:
        label = "manual_review"
        confidence = 60
    elif net >= 80:
        label = "client_confirmed"
        confidence = min(100, 70 + net // 5)
    elif net >= 40:
        label = "client_possible"
        confidence = min(85, 50 + net // 5)
    elif net >= -30:
        label = "unknown"
        confidence = 40
    elif net >= -100:
        label = "provider_possible"
        confidence = min(85, 50 + abs(net) // 5)
    else:
        label = "provider_confirmed"
        confidence = min(100, 70 + abs(net) // 10)

    return {
        "username": profile.get("username"),
        "name": profile.get("name"),
        "city": profile.get("city"),
        "url": url,
        "title": profile.get("title"),
        "client_score": client_score,
        "provider_score": provider_score,
        "net_client_score": net,
        "label": label,
        "confidence": confidence,
        "reasons": reasons,
        "classified_at": datetime.now(timezone.utc).isoformat()
    }


def calculate_lead_value(profile: Dict[str, Any]) -> float:
    """Calculate lead value score."""
    label = profile.get("label", "unknown")
    city = clean(profile.get("city", ""))
    title = clean(profile.get("title", ""))
    body = clean(profile.get("body_text", ""))

    # Role score
    role_scores = {
        "client_confirmed": 60,
        "client_possible": 35,
        "unknown": 0,
        "provider_possible": -60,
        "provider_confirmed": -100,
        "manual_review": 0,
        "bad_page": -100
    }
    role_score = role_scores.get(label, 0)

    # Location score
    if "manhattan" in city:
        location_score = 25
    elif "brooklyn" in city:
        location_score = 15
    elif "bronx" in city:
        location_score = 10
    elif "ny" in city:
        location_score = 10
    else:
        location_score = 0

    # Intent score
    intent_score = 0
    if "looking for" in title or "looking for" in body:
        intent_score += 30
    if "need massage" in title or "need massage" in body:
        intent_score += 30
    if any(term in title or term in body for term in CLIENT_PROBLEM):
        intent_score += 15
    if not title or title == "rentmasseur.com":
        intent_score -= 10

    # Recency score (simplified - would use visit timestamp)
    recency_score = 0

    # Ambiguity penalty
    ambiguity_penalty = 0
    if not title:
        ambiguity_penalty -= 20
    if not body:
        ambiguity_penalty -= 10
    if label == "manual_review":
        ambiguity_penalty -= 30

    # Compliance penalty (simplified)
    compliance_penalty = 0

    lead_value = role_score + location_score + intent_score + recency_score + ambiguity_penalty + compliance_penalty
    return max(0, lead_value)


def determine_action(profile: Dict[str, Any]) -> str:
    """Determine action based on classification and lead value."""
    label = profile.get("label")
    lead_value = profile.get("lead_value", 0)

    if label == "provider_confirmed" or label == "provider_possible":
        return "exclude_provider"
    elif label == "client_confirmed" and lead_value >= 60:
        return "contact_ready_platform_allowed"
    elif label == "client_possible":
        return "manual_review_client_possible"
    elif label == "manual_review":
        return "manual_review_client_possible"
    elif label == "unknown" and lead_value >= 30:
        return "revisit_later"
    else:
        return "do_not_contact"


def init_database():
    """Initialize SQLite database with schema."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            username TEXT PRIMARY KEY,
            name TEXT,
            city TEXT,
            url TEXT NOT NULL,
            source TEXT,
            first_seen_ts TEXT,
            last_seen_ts TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profile_visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            visited_ts TEXT NOT NULL,
            status TEXT,
            title TEXT,
            body_text TEXT,
            http_status INTEGER,
            error TEXT,
            FOREIGN KEY(username) REFERENCES profiles(username)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profile_classifications (
            username TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            client_score REAL NOT NULL,
            provider_score REAL NOT NULL,
            net_client_score REAL NOT NULL,
            confidence REAL NOT NULL,
            reasons_json TEXT,
            classified_ts TEXT NOT NULL,
            FOREIGN KEY(username) REFERENCES profiles(username)
        )
    """)

    # Add missing columns if table exists
    try:
        cursor.execute("ALTER TABLE profile_classifications ADD COLUMN provider_score REAL")
    except:
        pass
    try:
        cursor.execute("ALTER TABLE profile_classifications ADD COLUMN net_client_score REAL")
    except:
        pass

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lead_queue (
            username TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            city TEXT,
            label TEXT,
            lead_value REAL,
            action TEXT,
            status TEXT DEFAULT 'pending_review',
            created_ts TEXT,
            reviewed_ts TEXT,
            notes TEXT,
            FOREIGN KEY(username) REFERENCES profiles(username)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppression_list (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identifier TEXT NOT NULL,
            identifier_type TEXT,
            reason TEXT,
            created_ts TEXT
        )
    """)

    conn.commit()
    conn.close()
    print(f"Database initialized: {DB_PATH}")


def load_and_merge_data():
    """Load and merge ny_users.json with task1_visit_back.json."""
    ny_file = DATA_DIR / "ny_users.json"
    with open(ny_file) as f:
        ny_data = json.load(f)
    base_profiles = ny_data.get("users", [])

    visited_file = DATA_DIR / "task1_visit_back.json"
    with open(visited_file) as f:
        visited_data = json.load(f)
    visited = visited_data.get("visited", [])

    visited_by_username = {row["username"].lower(): row for row in visited}
    base_usernames = {p["username"].lower() for p in base_profiles}

    merged = []
    visited_count = 0

    # First, merge base profiles with visited data
    for profile in base_profiles:
        key = profile["username"].lower()
        evidence = visited_by_username.get(key, {})
        is_visited = bool(evidence)
        if is_visited:
            visited_count += 1
        merged.append({
            "username": profile.get("username"),
            "name": profile.get("name"),
            "city": profile.get("city"),
            "url": profile.get("url"),
            "visited": is_visited,
            "title": evidence.get("title", ""),
            "visit_status": evidence.get("status", "not_visited"),
            "body_text": ""
        })

    # Second, add visited-only profiles (not in base)
    for visit_record in visited:
        username = visit_record["username"]
        if username.lower() not in base_usernames:
            merged.append({
                "username": username,
                "name": username,
                "city": None,
                "url": f"https://rentmasseur.com/{username}",
                "visited": True,
                "title": visit_record.get("title", ""),
                "visit_status": visit_record.get("status", "visited"),
                "body_text": ""
            })

    print(f"Loaded {len(base_profiles)} base profiles")
    print(f"Merged with {len(visited)} visited profiles")
    print(f"Successfully matched {visited_count} base profiles with visited data")
    print(f"Added {len(visited) - visited_count} visited-only profiles")
    print(f"Total merged: {len(merged)}")

    return merged


def save_to_database(profiles: List[Dict[str, Any]]):
    """Save profiles and classifications to database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for profile in profiles:
        username = profile.get("username")

        # Insert/update profile
        cursor.execute("""
            INSERT OR REPLACE INTO profiles
            (username, name, city, url, source, first_seen_ts, last_seen_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            username,
            profile.get("name"),
            profile.get("city"),
            profile.get("url"),
            "ny_users",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat()
        ))

        # Insert visit if visited
        if profile.get("visited"):
            cursor.execute("""
                INSERT OR REPLACE INTO profile_visits
                (username, visited_ts, status, title, body_text, http_status, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                username,
                datetime.now(timezone.utc).isoformat(),
                profile.get("visit_status", "visited"),
                profile.get("title"),
                profile.get("body_text"),
                200,
                None
            ))

    conn.commit()
    conn.close()
    print(f"Saved {len(profiles)} profiles to database")


def classify_and_save(profiles: List[Dict[str, Any]]):
    """Classify profiles and save to database."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    classified = []
    for profile in profiles:
        result = classify_profile(profile)
        result["lead_value"] = calculate_lead_value(result)
        result["action"] = determine_action(result)
        classified.append(result)

        # Save classification
        cursor.execute("""
            INSERT OR REPLACE INTO profile_classifications
            (username, label, client_score, provider_score, net_client_score, confidence, reasons_json, classified_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            result["username"],
            result["label"],
            result["client_score"],
            result["provider_score"],
            result["net_client_score"],
            result["confidence"],
            json.dumps(result["reasons"]),
            result["classified_at"]
        ))

        # Save to lead queue if not excluded
        if result["action"] != "exclude_provider":
            cursor.execute("""
                INSERT OR REPLACE INTO lead_queue
                (username, url, city, label, lead_value, action, status, created_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result["username"],
                result["url"],
                result["city"],
                result["label"],
                result["lead_value"],
                result["action"],
                "pending_review",
                datetime.now(timezone.utc).isoformat()
            ))

    conn.commit()
    conn.close()
    print(f"Classified {len(classified)} profiles")

    return classified


def generate_output_files(classified: List[Dict[str, Any]]):
    """Generate output files."""
    # classified_profiles.json
    with open(DATA_DIR / "classified_profiles.json", "w") as f:
        json.dump(classified, f, indent=2)
    print(f"Saved: {DATA_DIR / 'classified_profiles.json'}")

    # client_candidates.csv
    client_candidates = [p for p in classified if p["label"] in ["client_confirmed", "client_possible"]]
    with open(DATA_DIR / "client_candidates.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["username", "name", "city", "url", "label", "client_score", "provider_score", "net_client_score", "confidence", "lead_value", "action"])
        for p in client_candidates:
            writer.writerow([p["username"], p["name"], p["city"], p["url"], p["label"], p["client_score"], p["provider_score"], p["net_client_score"], p["confidence"], p["lead_value"], p["action"]])
    print(f"Saved: {DATA_DIR / 'client_candidates.csv'} ({len(client_candidates)} records)")

    # provider_exclusions.csv
    provider_exclusions = [p for p in classified if p["label"] in ["provider_confirmed", "provider_possible"]]
    with open(DATA_DIR / "provider_exclusions.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["username", "name", "city", "url", "label", "client_score", "provider_score", "net_client_score", "confidence", "action"])
        for p in provider_exclusions:
            writer.writerow([p["username"], p["name"], p["city"], p["url"], p["label"], p["client_score"], p["provider_score"], p["net_client_score"], p["confidence"], p["action"]])
    print(f"Saved: {DATA_DIR / 'provider_exclusions.csv'} ({len(provider_exclusions)} records)")

    # manual_review_queue.csv
    manual_review = [p for p in classified if p["action"] in ["manual_review_client_possible", "revisit_later"]]
    with open(DATA_DIR / "manual_review_queue.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["username", "name", "city", "url", "label", "client_score", "provider_score", "net_client_score", "confidence", "lead_value", "action"])
        for p in manual_review:
            writer.writerow([p["username"], p["name"], p["city"], p["url"], p["label"], p["client_score"], p["provider_score"], p["net_client_score"], p["confidence"], p["lead_value"], p["action"]])
    print(f"Saved: {DATA_DIR / 'manual_review_queue.csv'} ({len(manual_review)} records)")

    # classification_receipt.json
    receipt = {
        "run_id": f"rm-client-classifier-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "input_profiles": len(classified),
        "visited_profiles": sum(1 for p in classified if p.get("visited")),
        "client_confirmed": sum(1 for p in classified if p["label"] == "client_confirmed"),
        "client_possible": sum(1 for p in classified if p["label"] == "client_possible"),
        "unknown": sum(1 for p in classified if p["label"] == "unknown"),
        "provider_possible": sum(1 for p in classified if p["label"] == "provider_possible"),
        "provider_confirmed": sum(1 for p in classified if p["label"] == "provider_confirmed"),
        "manual_review": sum(1 for p in classified if p["label"] == "manual_review"),
        "bad_page": 0,
        "classifier_version": "client-intent-v1.0",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    with open(RECEIPTS_DIR / f"classification_receipt_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json", "w") as f:
        json.dump(receipt, f, indent=2)
    print(f"Saved: {RECEIPTS_DIR / f'classification_receipt_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json'}")

    return receipt


def calculate_visit_priority(profile: Dict[str, Any]) -> int:
    """Calculate visit priority score for next crawl."""
    username = clean(profile.get("username", ""))
    city = clean(profile.get("city", ""))

    score = 0

    # Positive signals
    for term in CLIENT_USERNAME:
        if term in username:
            score += 50

    if "manhattan" in city:
        score += 30
    elif "brooklyn" in city:
        score += 20
    elif "bronx" in city:
        score += 10

    # Negative signals
    for term in PROVIDER_USERNAME:
        if term in username:
            score -= 80

    # Provider brand patterns
    provider_brands = ["sportsmassagenyc", "healinghandsnyc", "deeptouchman", "gentletouchnyc"]
    if any(brand in username for brand in provider_brands):
        score -= 40

    return score


def main():
    print("=" * 60)
    print("CLIENT-INTENT CLASSIFIER V1.0")
    print("=" * 60)

    # Initialize database
    print("\n[1] Initializing database...")
    init_database()

    # Load and merge data
    print("\n[2] Loading and merging data...")
    profiles = load_and_merge_data()

    # Save to database
    print("\n[3] Saving to database...")
    save_to_database(profiles)

    # Classify
    print("\n[4] Classifying profiles...")
    classified = classify_and_save(profiles)

    # Generate output files
    print("\n[5] Generating output files...")
    receipt = generate_output_files(classified)

    # Print summary
    print("\n" + "=" * 60)
    print("CLASSIFICATION SUMMARY")
    print("=" * 60)
    for key, value in receipt.items():
        if key != "created_at":
            print(f"{key}: {value}")

    # Top client candidates
    print("\nTop client candidates:")
    client_candidates = sorted([p for p in classified if p["label"] in ["client_confirmed", "client_possible"]], key=lambda x: x["lead_value"], reverse=True)[:10]
    for p in client_candidates:
        print(f"  {p['username']}: {p['label']} (lead_value: {p['lead_value']}, confidence: {p['confidence']})")

    print("\n=== COMPLETE ===")


if __name__ == "__main__":
    main()
