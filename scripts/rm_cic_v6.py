#!/usr/bin/env python3
"""
RM-CIC V6: Cleaned Client Algorithm with Four-Pass System

Updated term lists and scoring logic as specified.
Four-pass system:
1. classify_from_username (already done)
2. visit_candidate_pages (blocked by captcha)
3. reclassify_from_body
4. queue_only_confirmed_clients with compliance gate
"""
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "rm_cic.db"

# Updated term lists
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


def classify_profile(username: str, title: str = "", body_text: str = "", city: str = "") -> Dict[str, Any]:
    """Cleaned classification algorithm with updated term lists."""
    u = (username or "").lower()
    t = (title or "").lower()
    b = (body_text or "").lower()
    c = (city or "").lower()
    text = f"{t} {b}"

    score = 0
    reasons = []

    # Client strong signals
    for term in CLIENT_STRONG:
        if term in text:
            score += 80
            reasons.append(f"+80 strong_client:{term}")

    # Client weak signals
    for term in CLIENT_WEAK:
        if term in text:
            score += 25
            reasons.append(f"+25 weak_client:{term}")

    # Client username signals
    for term in CLIENT_USERNAME:
        if term in u:
            score += 20
            reasons.append(f"+20 client_username:{term}")

    # Generic title bonus
    if not t or t == "rentmasseur.com" or "| rentmasseur" in t:
        score += 15
        reasons.append("+15 generic_or_blank_title")

    # Provider strong signals
    for term in PROVIDER_STRONG:
        if term in text:
            score -= 100
            reasons.append(f"-100 strong_provider:{term}")

    # Provider username signals
    for term in PROVIDER_USERNAME:
        if term in u:
            score -= 45
            reasons.append(f"-45 provider_username:{term}")

    # Location bonus
    if "manhattan" in c:
        lead_bonus = 20
    elif "brooklyn" in c:
        lead_bonus = 15
    elif "bronx" in c:
        lead_bonus = 10
    else:
        lead_bonus = 0

    lead_value = score + lead_bonus

    # Override logic
    strong_provider = any(term in text for term in PROVIDER_STRONG)
    strong_client = any(term in text for term in CLIENT_STRONG)

    if strong_client and not strong_provider:
        label = "client_confirmed"
        confidence = 85
    elif strong_provider and not strong_client:
        label = "provider_confirmed"
        confidence = 90
    elif score >= 80:
        label = "client_confirmed"
        confidence = min(95, score)
    elif score >= 40:
        label = "client_possible"
        confidence = 65
    elif score >= -20:
        label = "unknown"
        confidence = 40
    elif score >= -80:
        label = "provider_possible"
        confidence = 55
    else:
        label = "provider_confirmed"
        confidence = 85

    return {
        "username": username,
        "city": city,
        "label": label,
        "client_score": score,
        "lead_value": lead_value,
        "confidence": confidence,
        "reasons": reasons,
    }


def should_visit_next(row: Dict[str, Any]) -> bool:
    """Determine if profile should be visited next."""
    if row.get("label") == "provider_confirmed":
        return False
    if row.get("lead_value", 0) >= 30:
        return True
    if row.get("label") in ["unknown", "client_possible"]:
        return True
    return False


def should_queue_for_review(row: Dict[str, Any]) -> bool:
    """Determine if profile should be queued for manual review."""
    return (
        row.get("label") == "client_confirmed"
        and row.get("confidence", 0) >= 80
        and row.get("lead_value", 0) >= 80
    )


def reclassify_database():
    """Reclassify all profiles in database with cleaned algorithm."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=== RM-CIC V6: CLEANED ALGORITHM RECLASSIFICATION ===")

    # Get all profiles with their current data
    cursor.execute("""
        SELECT
            p.username,
            p.name,
            p.city,
            p.url,
            v.title,
            v.body_text
        FROM profiles p
        LEFT JOIN profile_visits v ON p.username = v.username
    """)

    profiles = cursor.fetchall()
    print(f"\n[1] Loaded {len(profiles)} profiles for reclassification")

    # Reclassify each profile
    reclassified = []
    for username, name, city, url, title, body_text in profiles:
        result = classify_profile(username, title or "", body_text or "", city or "")
        reclassified.append(result)

        # Update profile_classifications
        cursor.execute("""
            UPDATE profile_classifications
            SET label = ?,
                client_score = ?,
                lead_value = ?,
                confidence = ?,
                reasons_json = ?
            WHERE username = ?
        """, (
            result["label"],
            result["client_score"],
            result["lead_value"],
            result["confidence"],
            json.dumps(result["reasons"]),
            username
        ))

    print(f"[2] Reclassified {len(reclassified)} profiles")

    # Update client_candidates with new review_status
    print("\n[3] Updating client_candidates review_status...")
    cursor.execute("""
        UPDATE client_candidates
        SET label = (
            SELECT label FROM profile_classifications WHERE username = client_candidates.username
        ),
        client_score = (
            SELECT client_score FROM profile_classifications WHERE username = client_candidates.username
        ),
        lead_value = (
            SELECT lead_value FROM profile_classifications WHERE username = client_candidates.username
        ),
        confidence = (
            SELECT confidence FROM profile_classifications WHERE username = client_candidates.username
        ),
        review_status = CASE
            WHEN (SELECT label FROM profile_classifications WHERE username = client_candidates.username) = 'client_confirmed'
                AND (SELECT confidence FROM profile_classifications WHERE username = client_candidates.username) >= 80
                AND (SELECT lead_value FROM profile_classifications WHERE username = client_candidates.username) >= 80
            THEN 'pending_manual_review'
            WHEN (SELECT label FROM profile_classifications WHERE username = client_candidates.username) IN ('unknown', 'client_possible')
                AND (SELECT lead_value FROM profile_classifications WHERE username = client_candidates.username) >= 30
                AND (SELECT label FROM profile_classifications WHERE username = client_candidates.username) != 'provider_confirmed'
            THEN 'needs_profile_visit'
            ELSE 'do_not_contact'
        END,
        updated_ts = datetime('now')
    """)

    # Rebuild outreach_queue with compliance gate
    print("\n[4] Rebuilding outreach_queue with compliance gate...")
    cursor.execute("DELETE FROM outreach_queue")

    cursor.execute("""
        INSERT INTO outreach_queue
        (username, url, city, label, lead_value, status, created_ts)
        SELECT
            p.username,
            p.url,
            p.city,
            c.label,
            c.lead_value,
            'pending',
            datetime('now')
        FROM profile_classifications c
        JOIN profiles p USING(username)
        WHERE c.label = 'client_confirmed'
          AND c.confidence >= 80
          AND c.lead_value >= 80
        ORDER BY c.lead_value DESC
    """)

    outreach_count = cursor.execute("SELECT COUNT(*) FROM outreach_queue").fetchone()[0]
    print(f"  Outreach queue: {outreach_count} profiles")

    # Update verification_queue
    print("\n[5] Updating verification_queue...")
    cursor.execute("DELETE FROM verification_queue")

    cursor.execute("""
        INSERT OR REPLACE INTO verification_queue
        (username, url, city, current_label, client_score, lead_value, confidence, priority, status, created_ts)
        SELECT
            p.username,
            p.url,
            p.city,
            c.label,
            c.client_score,
            c.lead_value,
            c.confidence,
            CASE
                WHEN c.lead_value >= 60 THEN 'high'
                WHEN c.lead_value >= 40 THEN 'medium'
                ELSE 'low'
            END,
            'pending',
            datetime('now')
        FROM profile_classifications c
        JOIN profiles p USING(username)
        WHERE c.label IN ('unknown', 'client_possible')
          AND c.lead_value >= 30
          AND c.label != 'provider_confirmed'
        ORDER BY c.lead_value DESC
    """)

    verification_count = cursor.execute("SELECT COUNT(*) FROM verification_queue").fetchone()[0]
    print(f"  Verification queue: {verification_count} profiles")

    conn.commit()
    conn.close()

    print("\n=== RECLASSIFICATION COMPLETE ===")


def print_summary():
    """Print summary of current state."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n=== CURRENT STATE SUMMARY ===")

    # Classification distribution
    print("\nClassification distribution:")
    cursor.execute("SELECT label, COUNT(*) FROM profile_classifications GROUP BY label")
    for label, count in cursor.fetchall():
        print(f"  {label}: {count}")

    # Client candidates by review status
    print("\nClient candidates by review status:")
    cursor.execute("SELECT review_status, COUNT(*) FROM client_candidates GROUP BY review_status")
    for status, count in cursor.fetchall():
        print(f"  {status}: {count}")

    # Top outreach candidates
    print("\nTop outreach candidates:")
    cursor.execute("""
        SELECT oq.username, p.city, oq.label, oq.lead_value, c.confidence
        FROM outreach_queue oq
        JOIN profiles p ON oq.username = p.username
        JOIN profile_classifications c ON oq.username = c.username
        ORDER BY oq.lead_value DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[2]} (lead_value: {row[3]}, confidence: {row[4]})")

    # Top verification candidates
    print("\nTop verification candidates:")
    cursor.execute("""
        SELECT username, city, current_label, lead_value, priority
        FROM verification_queue
        ORDER BY lead_value DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[2]} (lead_value: {row[3]}, priority: {row[4]})")

    conn.close()


if __name__ == "__main__":
    reclassify_database()
    print_summary()
