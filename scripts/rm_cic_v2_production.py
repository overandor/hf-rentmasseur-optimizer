#!/usr/bin/env python3
"""
RM-CIC V2: Client Intent Classifier

Production-grade client intelligence classifier with:
- Updated phrase dictionaries with specified weights
- Two-score model (client_score and lead_value)
- Evidence hierarchy (body > title > username > city)
- Override rules for strong provider/client evidence
- conflict_manual_review bucket
- Evidence hits and decision ledger integration
"""
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "rm_cic.db"

# Updated phrase dictionaries with specified weights
CLIENT_PHRASES = {
    "looking for male massage": 90,
    "looking for massage therapist": 90,
    "looking for a massage therapist": 90,
    "looking for masseur": 85,
    "looking for massage": 80,
    "need a massage": 80,
    "need massage": 75,
    "in need of massage": 80,
    "seeking massage": 80,
    "seeking bodywork": 75,
    "massage wanted": 70,
    "want a massage": 70,
    "looking to book": 65,
    "can host": 35,
    "available today": 25
}

PROVIDER_PHRASES = {
    "male masseur": 120,
    "professional masseur": 120,
    "certified masseur": 110,
    "gay massage in": 110,
    "massage in new york": 100,
    "massage in manhattan": 100,
    "massage in brooklyn": 100,
    "massage in bronx": 100,
    "deep tissue massage": 90,
    "swedish massage": 90,
    "sports massage": 90,
    "therapeutic massage": 85,
    "bodywork by": 85,
    "i offer": 80,
    "my massage": 80,
    "book me": 80,
    "incall": 70,
    "outcall": 70,
    "rates": 70,
    "session": 60
}

CLIENT_USERNAME = {
    "inneed": 25,
    "need": 20,
    "looking": 20,
    "aching": 20,
    "sore": 20,
    "tired": 15,
    "luv": 15,
    "love": 15,
    "relax": 10
}

PROVIDER_USERNAME = {
    "masseur": 60,
    "massuer": 50,
    "massage": 45,
    "hands": 40,
    "touch": 40,
    "bodywork": 40,
    "therapist": 35,
    "therapy": 35,
    "spa": 35,
    "healing": 30,
    "deep": 30,
    "swedish": 30
}


def normalize(text: Optional[str]) -> str:
    """Normalize text for comparison."""
    if not text:
        return ""
    text = text.lower()
    return " ".join(text.split())


def assign_label(raw_score: float, client_score: float, provider_score: float, evidence_text: str) -> str:
    """Assign label based on scores and evidence."""
    # Check for strong evidence overrides
    strong_client = any(phrase in evidence_text for phrase in CLIENT_PHRASES.keys())
    strong_provider = any(phrase in evidence_text for phrase in PROVIDER_PHRASES.keys())

    if strong_client and strong_provider:
        return "conflict_manual_review"
    if strong_client and not strong_provider:
        return "client_confirmed"
    if strong_provider and not strong_client:
        return "provider_confirmed"

    # Score-based classification
    if raw_score >= 80:
        return "client_confirmed"
    elif raw_score >= 40:
        return "client_possible"
    elif raw_score >= -25:
        return "unknown"
    elif raw_score >= -90:
        return "provider_possible"
    else:
        return "provider_confirmed"


def calculate_lead_value(label: str, raw_score: float, city: str, has_body: bool, has_title: bool) -> float:
    """Calculate lead value score."""
    location_score = 0
    if "manhattan" in city.lower():
        location_score = 25
    elif "brooklyn" in city.lower():
        location_score = 15
    elif "bronx" in city.lower():
        location_score = 10
    elif "ny" in city.lower():
        location_score = 5

    recency_score = 0  # Would be calculated from visit timestamp
    intent_score = 0
    if label == "client_confirmed":
        intent_score = 50
    elif label == "client_possible":
        intent_score = 25

    contactability_score = 0  # Would be calculated from contact button presence

    ambiguity_penalty = 0
    if not has_title:
        ambiguity_penalty -= 20
    if not has_body:
        ambiguity_penalty -= 25

    provider_penalty = 0
    if label in ["provider_possible", "provider_confirmed"]:
        provider_penalty -= 150

    lead_value = raw_score + location_score + recency_score + intent_score + contactability_score + ambiguity_penalty + provider_penalty
    return max(0, lead_value)


def calculate_confidence(label: str, client_score: float, provider_score: float, has_body: bool, has_title: bool) -> int:
    """Calculate confidence score."""
    base_confidence = 50

    if has_body:
        base_confidence += 30
    if has_title:
        base_confidence += 20

    if label == "client_confirmed":
        base_confidence = min(95, base_confidence + 15)
    elif label == "provider_confirmed":
        base_confidence = min(95, base_confidence + 15)
    elif label == "conflict_manual_review":
        base_confidence = 40

    return min(100, base_confidence)


def classify_profile(username: str, city: str, title: str = "", h1: str = "", meta_description: str = "", body_text: str = "") -> Dict[str, Any]:
    """Classify a profile using RM-CIC V2 algorithm."""
    username_norm = normalize(username)
    city_norm = normalize(city)
    title_norm = normalize(title)
    h1_norm = normalize(h1)
    meta_norm = normalize(meta_description)
    body_norm = normalize(body_text)

    # Evidence hierarchy: body > title > username > city
    evidence_text = " ".join([body_norm, title_norm, h1_norm, meta_norm])

    client_score = 0
    provider_score = 0
    reasons = []
    evidence_hits = []

    # Strong client phrase detection
    for phrase, weight in CLIENT_PHRASES.items():
        if phrase in evidence_text:
            client_score += weight
            reasons.append(f"+{weight} client_phrase:{phrase}")
            evidence_hits.append({
                "phrase": phrase,
                "phrase_type": "client",
                "score_delta": weight,
                "field": "evidence_text"
            })

    # Weak username demand detection
    for phrase, weight in CLIENT_USERNAME.items():
        if phrase in username_norm:
            client_score += weight
            reasons.append(f"+{weight} client_username:{phrase}")
            evidence_hits.append({
                "phrase": phrase,
                "phrase_type": "client_username",
                "score_delta": weight,
                "field": "username"
            })

    # Strong provider phrase detection
    for phrase, weight in PROVIDER_PHRASES.items():
        if phrase in evidence_text:
            provider_score += weight
            reasons.append(f"-{weight} provider_phrase:{phrase}")
            evidence_hits.append({
                "phrase": phrase,
                "phrase_type": "provider",
                "score_delta": -weight,
                "field": "evidence_text"
            })

    # Provider username detection
    for phrase, weight in PROVIDER_USERNAME.items():
        if phrase in username_norm:
            provider_score += weight
            reasons.append(f"-{weight} provider_username:{phrase}")
            evidence_hits.append({
                "phrase": phrase,
                "phrase_type": "provider_username",
                "score_delta": -weight,
                "field": "username"
            })

    # Generic title bonus
    if not title_norm or title_norm == "rentmasseur.com" or "| rentmasseur" in title_norm:
        client_score += 10
        reasons.append("+10 generic_or_blank_title")

    raw_score = client_score - provider_score
    label = assign_label(raw_score, client_score, provider_score, evidence_text)
    lead_value = calculate_lead_value(label, raw_score, city_norm, bool(body_text), bool(title_norm))
    confidence = calculate_confidence(label, client_score, provider_score, bool(body_text), bool(title_norm))

    return {
        "username": username,
        "city": city,
        "label": label,
        "client_score": raw_score,
        "lead_value": lead_value,
        "confidence": confidence,
        "reasons": reasons,
        "evidence_hits": evidence_hits,
        "evidence_text": evidence_text
    }


def reclassify_all_profiles():
    """Reclassify all profiles in database with RM-CIC V2."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("=== RM-CIC V2: CLIENT INTENT CLASSIFIER ===")

    # Get all profiles with their visit data
    cursor.execute("""
        SELECT
            p.username,
            p.name,
            p.city,
            p.url,
            v.title,
            v.h1,
            v.meta_description,
            v.body_text
        FROM profiles p
        LEFT JOIN profile_visits v ON p.username = v.username
    """)

    profiles = cursor.fetchall()
    print(f"\n[1] Loaded {len(profiles)} profiles for reclassification")

    # Get old classifications for decision ledger
    cursor.execute("SELECT username, label, client_score FROM profile_classifications")
    old_classifications = {row[0]: {"label": row[1], "score": row[2]} for row in cursor.fetchall()}

    # Reclassify each profile
    reclassified = []
    for username, name, city, url, title, h1, meta_description, body_text in profiles:
        result = classify_profile(username, city or "", title or "", h1 or "", meta_description or "", body_text or "")
        reclassified.append(result)

        # Store old label and score for decision ledger
        old_data = old_classifications.get(username, {"label": None, "score": None})
        old_label = old_data["label"]
        old_score = old_data["score"]

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

        # Add to decision ledger if changed
        if old_label != result["label"] or old_score != result["client_score"]:
            cursor.execute("""
                INSERT INTO decision_ledger
                (username, old_label, new_label, old_score, new_score, reason, created_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                username,
                old_label,
                result["label"],
                old_score,
                result["client_score"],
                json.dumps(result["reasons"]),
                datetime.now(timezone.utc).isoformat()
            ))

        # Add evidence hits
        visit_id = cursor.execute("SELECT id FROM profile_visits WHERE username = ? ORDER BY visited_ts DESC LIMIT 1", (username,)).fetchone()
        visit_id = visit_id[0] if visit_id else None

        for hit in result["evidence_hits"]:
            cursor.execute("""
                INSERT INTO evidence_hits
                (username, visit_id, phrase, phrase_type, score_delta, field, created_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                username,
                visit_id,
                hit["phrase"],
                hit["phrase_type"],
                hit["score_delta"],
                hit["field"],
                datetime.now(timezone.utc).isoformat()
            ))

    print(f"[2] Reclassified {len(reclassified)} profiles")

    # Update client_candidates
    print("\n[3] Updating client_candidates...")
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
                AND (SELECT lead_value FROM profile_classifications WHERE username = client_candidates.username) >= 100
            THEN 'pending_manual_review'
            WHEN (SELECT label FROM profile_classifications WHERE username = client_candidates.username) = 'client_possible'
                AND (SELECT lead_value FROM profile_classifications WHERE username = client_candidates.username) >= 60
            THEN 'needs_manual_review'
            WHEN (SELECT label FROM profile_classifications WHERE username = client_candidates.username) = 'conflict_manual_review'
            THEN 'conflict_manual_review'
            WHEN (SELECT label FROM profile_classifications WHERE username = client_candidates.username) IN ('unknown', 'client_possible')
                AND (SELECT lead_value FROM profile_classifications WHERE username = client_candidates.username) >= 30
                AND (SELECT label FROM profile_classifications WHERE username = client_candidates.username) != 'provider_confirmed'
            THEN 'needs_profile_visit'
            ELSE 'do_not_contact'
        END,
        updated_ts = datetime('now')
    """)

    # Rebuild outreach_queue
    print("\n[4] Rebuilding outreach_queue...")
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
          AND c.lead_value >= 100
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
        WHERE c.label IN ('unknown', 'client_possible', 'conflict_manual_review')
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

    print("\n=== RM-CIC V2 SUMMARY ===")

    # Classification distribution
    print("\nClassification distribution:")
    cursor.execute("SELECT label, COUNT(*) FROM profile_classifications GROUP BY label ORDER BY COUNT(*) DESC")
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

    # Conflict manual review
    print("\nConflict manual review profiles:")
    cursor.execute("""
        SELECT c.username, p.city, c.client_score, c.lead_value
        FROM profile_classifications c
        JOIN profiles p ON c.username = p.username
        WHERE c.label = 'conflict_manual_review'
        ORDER BY c.lead_value DESC
        LIMIT 10
    """)
    for row in cursor.fetchall():
        print(f"  {row[0]}: {row[1]} (client_score: {row[2]}, lead_value: {row[3]})")

    # Evidence hits count
    evidence_count = cursor.execute("SELECT COUNT(*) FROM evidence_hits").fetchone()[0]
    print(f"\nEvidence hits stored: {evidence_count}")

    # Decision ledger count
    decision_count = cursor.execute("SELECT COUNT(*) FROM decision_ledger").fetchone()[0]
    print(f"Decision ledger entries: {decision_count}")

    conn.close()


if __name__ == "__main__":
    reclassify_all_profiles()
    print_summary()
