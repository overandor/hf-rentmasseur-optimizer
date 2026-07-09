#!/usr/bin/env python3
"""
Exact Client-Intelligence Classifier Specification

Implements the strict rule: Never call someone a client unless there is demand-side evidence.

Production pipeline:
Discover profile → Visit profile → Extract evidence → Classify role → Score lead value → 
Apply compliance gate → Queue only confirmed or review-worthy client leads → Suppress providers
"""
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional
import hashlib

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "rm_cic.db"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Phrase dictionaries as specified
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
    "call or text",
    "text me",
    "call me",
    "phone:",
    "tel:",
    "contact:",
    "bio:",
    "about me",
    "my services",
    "my background",
    "certified in",
    "licensed",
    "years of experience",
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
    """
    Exact classifier function as specified.
    
    Returns classification with client_score, provider_score, net_client_score, lead_value, label, confidence, reasons.
    """
    u = (username or "").lower()
    t = (title or "").lower()
    b = (body_text or "").lower()
    c = (city or "").lower()
    text = f"{t} {b}"
    
    client_score = 0
    provider_score = 0
    reasons = []
    
    # Strong client phrases in title/body
    for term in CLIENT_STRONG:
        if term in text:
            client_score += 80
            reasons.append(f"+80 strong_client:{term}")
    
    # Weak client phrases in title/body
    for term in CLIENT_WEAK:
        if term in text:
            client_score += 25
            reasons.append(f"+25 weak_client:{term}")
    
    # Client-like username
    for term in CLIENT_USERNAME:
        if term in u:
            client_score += 20
            reasons.append(f"+20 client_username:{term}")
    
    # Generic or blank title
    if not t or t == "rentmasseur.com" or "| rentmasseur" in t:
        client_score += 15
        reasons.append("+15 generic_or_blank_title")
    
    # Strong provider phrases in title/body
    for term in PROVIDER_STRONG:
        if term in text:
            provider_score += 100
            reasons.append(f"-100 strong_provider:{term}")
    
    # Provider-like username
    for term in PROVIDER_USERNAME:
        if term in u:
            provider_score += 45
            reasons.append(f"-45 provider_username:{term}")
    
    net_score = client_score - provider_score
    
    # Location bonus (only after role classification)
    if "manhattan" in c:
        location_bonus = 20
    elif "brooklyn" in c:
        location_bonus = 15
    elif "bronx" in c:
        location_bonus = 10
    else:
        location_bonus = 0
    
    lead_value = net_score + location_bonus
    
    # Determine strong evidence flags
    strong_client = any(term in text for term in CLIENT_STRONG)
    strong_provider = any(term in text for term in PROVIDER_STRONG)
    
    # Classification logic as specified
    if strong_client and not strong_provider:
        label = "client_confirmed"
        confidence = 85
    elif strong_provider and not strong_client:
        label = "provider_confirmed"
        confidence = 90
    elif strong_client and strong_provider:
        label = "conflict_manual_review"
        confidence = 55
    elif net_score >= 80:
        label = "client_confirmed"
        confidence = min(95, net_score)
    elif net_score >= 40:
        label = "client_possible"
        confidence = 65
    elif net_score >= -20:
        label = "unknown"
        confidence = 40
    elif net_score >= -80:
        label = "provider_possible"
        confidence = 55
    else:
        label = "provider_confirmed"
        confidence = 85
    
    return {
        "username": username,
        "city": city,
        "label": label,
        "client_score": client_score,
        "provider_score": provider_score,
        "net_client_score": net_score,
        "lead_value": lead_value,
        "confidence": confidence,
        "reasons": reasons,
    }


def calculate_lead_value_advanced(profile: Dict[str, Any]) -> float:
    """
    Advanced lead value formula as specified.
    
    lead_value = net_client_score + location_bonus + recency_bonus + intent_bonus - ambiguity_penalty - compliance_penalty
    """
    net_score = profile.get("net_client_score", 0)
    city = (profile.get("city", "") or "").lower()
    
    # Location bonus
    if "manhattan" in city:
        location_bonus = 20
    elif "brooklyn" in city:
        location_bonus = 15
    elif "bronx" in city:
        location_bonus = 10
    else:
        location_bonus = 0
    
    # Intent bonus (based on reasons)
    reasons = profile.get("reasons", [])
    intent_bonus = 0
    for reason in reasons:
        if "strong_client" in reason:
            intent_bonus += 30
        elif "weak_client" in reason:
            intent_bonus += 25
        elif "client_username" in reason and "aching" in reason:
            intent_bonus += 10
    
    # Recency bonus (placeholder - requires visit timestamp)
    recency_bonus = 0
    
    # Ambiguity penalty
    ambiguity_penalty = 0
    title = (profile.get("title", "") or "").lower()
    if not title or title == "rentmasseur.com":
        ambiguity_penalty += 20
    if profile.get("label") == "conflict_manual_review":
        ambiguity_penalty += 30
    
    # Compliance penalty (placeholder - requires compliance checks)
    compliance_penalty = 0
    
    lead_value = net_score + location_bonus + recency_bonus + intent_bonus - ambiguity_penalty - compliance_penalty
    
    return lead_value


def should_queue_for_review(profile: Dict[str, Any]) -> bool:
    """
    Outreach queue rule as specified.
    
    Only profiles that are strong enough for human review before contact.
    """
    return (
        profile.get("label") == "client_confirmed"
        and profile.get("confidence", 0) >= 80
        and profile.get("lead_value", 0) >= 80
    )


def should_visit_next(profile: Dict[str, Any]) -> bool:
    """
    Verification queue rule as specified.
    
    Profiles that might be clients but need profile body text.
    """
    if profile.get("label") in ["provider_confirmed", "do_not_contact"]:
        return False
    if profile.get("lead_value", 0) >= 30:
        return True
    if profile.get("label") in ["unknown", "client_possible"]:
        return True
    return False


def should_suppress(profile: Dict[str, Any]) -> bool:
    """
    Suppression queue rule as specified.
    
    Profiles that should not be contacted as clients.
    """
    return profile.get("label") in [
        "provider_confirmed",
        "provider_possible",
        "bad_page",
        "do_not_contact"
    ]


def compliance_gate(profile: Dict[str, Any]) -> bool:
    """
    Compliance gate as specified.
    
    The classifier should not become an auto-spam system.
    """
    if profile.get("label") != "client_confirmed":
        return False
    if profile.get("confidence", 0) < 80:
        return False
    if profile.get("lead_value", 0) < 80:
        return False
    if profile.get("suppressed", False):
        return False
    if profile.get("provider_score", 0) >= 100:
        return False
    return True


def init_database():
    """Initialize database with exact schema as specified."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # profiles table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            username TEXT PRIMARY KEY,
            name TEXT,
            city TEXT,
            url TEXT NOT NULL,
            source TEXT,
            first_seen_ts TEXT,
            last_seen_ts TEXT,
            phone TEXT,
            email TEXT
        )
    """)
    
    # profile_visits table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profile_visits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL,
            visited_ts TEXT NOT NULL,
            status TEXT,
            title TEXT,
            h1 TEXT,
            meta_description TEXT,
            body_text TEXT,
            extracted_json TEXT,
            evidence_hash TEXT,
            http_status INTEGER,
            error TEXT
        )
    """)
    
    # profile_classifications table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS profile_classifications (
            username TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            client_score REAL,
            provider_score REAL,
            net_client_score REAL,
            lead_value REAL,
            confidence REAL,
            reasons_json TEXT,
            classified_ts TEXT
        )
    """)
    
    # client_candidates table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS client_candidates (
            username TEXT PRIMARY KEY,
            url TEXT,
            city TEXT,
            label TEXT,
            client_score REAL,
            provider_score REAL,
            lead_value REAL,
            confidence REAL,
            evidence_title TEXT,
            evidence_excerpt TEXT,
            reasons_json TEXT,
            review_status TEXT,
            created_ts TEXT,
            updated_ts TEXT
        )
    """)
    
    # outreach_queue table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS outreach_queue (
            username TEXT PRIMARY KEY,
            url TEXT,
            city TEXT,
            label TEXT,
            lead_value REAL,
            confidence REAL,
            status TEXT,
            created_ts TEXT
        )
    """)
    
    # verification_queue table - drop and recreate to ensure correct schema
    cursor.execute("DROP TABLE IF EXISTS verification_queue")
    cursor.execute("""
        CREATE TABLE verification_queue (
            username TEXT PRIMARY KEY,
            url TEXT,
            city TEXT,
            current_label TEXT,
            lead_value REAL,
            priority TEXT,
            reason TEXT,
            created_ts TEXT
        )
    """)
    
    # suppression_list table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS suppression_list (
            username TEXT PRIMARY KEY,
            reason TEXT,
            created_ts TEXT
        )
    """)
    
    # evidence_hits table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS evidence_hits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            evidence_type TEXT,
            term TEXT,
            weight REAL,
            source_field TEXT,
            created_ts TEXT
        )
    """)
    
    # decision_ledger table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decision_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            old_label TEXT,
            new_label TEXT,
            old_score REAL,
            new_score REAL,
            reason TEXT,
            created_ts TEXT
        )
    """)
    
    # compliance_events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS compliance_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            event_type TEXT,
            detail TEXT,
            created_ts TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    print(f"Database initialized: {DB_PATH}")


def save_profile(username: str, name: str, city: str, url: str, source: str = "ny_users"):
    """Save profile to profiles table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    
    cursor.execute("""
        INSERT OR REPLACE INTO profiles (username, name, city, url, source, first_seen_ts, last_seen_ts)
        VALUES (?, ?, ?, ?, ?, COALESCE((SELECT first_seen_ts FROM profiles WHERE username = ?), ?), ?)
    """, (username, name, city, url, source, username, now, now))
    
    conn.commit()
    conn.close()


def save_profile_visit(username: str, title: str, body_text: str = "", status: str = "visited"):
    """Save profile visit to profile_visits table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Calculate evidence hash
    evidence_str = f"{title}{body_text}"
    evidence_hash = hashlib.md5(evidence_str.encode()).hexdigest()
    
    cursor.execute("""
        INSERT INTO profile_visits 
        (username, visited_ts, status, title, body_text, evidence_hash, http_status)
        VALUES (?, ?, ?, ?, ?, ?, 200)
    """, (username, now, status, title, body_text, evidence_hash))
    
    conn.commit()
    conn.close()


def save_classification(classification: Dict[str, Any]):
    """Save classification to profile_classifications table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Check if exists for decision ledger
    cursor.execute("SELECT label, client_score FROM profile_classifications WHERE username = ?", 
                   (classification['username'],))
    old_row = cursor.fetchone()
    
    cursor.execute("""
        INSERT OR REPLACE INTO profile_classifications
        (username, label, client_score, provider_score, net_client_score, lead_value, confidence, reasons_json, classified_ts)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        classification['username'],
        classification['label'],
        classification['client_score'],
        classification['provider_score'],
        classification['net_client_score'],
        classification['lead_value'],
        classification['confidence'],
        json.dumps(classification['reasons']),
        now
    ))
    
    # Add to decision ledger if changed
    if old_row:
        old_label, old_score = old_row
        if old_label != classification['label'] or old_score != classification['client_score']:
            cursor.execute("""
                INSERT INTO decision_ledger (username, old_label, new_label, old_score, new_score, reason, created_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (classification['username'], old_label, classification['label'], old_score, 
                  classification['client_score'], "reclassification", now))
    
    conn.commit()
    conn.close()


def update_queues(classification: Dict[str, Any], url: str = ""):
    """Update outreach_queue, verification_queue, and suppression_list based on classification."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    username = classification['username']
    now = datetime.now(timezone.utc).isoformat()
    
    # Clear from all queues first
    cursor.execute("DELETE FROM outreach_queue WHERE username = ?", (username,))
    cursor.execute("DELETE FROM verification_queue WHERE username = ?", (username,))
    cursor.execute("DELETE FROM suppression_list WHERE username = ?", (username,))
    
    # Route to appropriate queue
    if should_queue_for_review(classification):
        cursor.execute("""
            INSERT INTO outreach_queue (username, url, city, label, lead_value, confidence, status, created_ts)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (username, url, classification.get('city', ''), classification['label'], 
              classification['lead_value'], classification['confidence'], 'pending', now))
    
    elif should_visit_next(classification):
        priority = "high" if classification['lead_value'] >= 50 else "medium"
        if classification['lead_value'] >= 30:
            cursor.execute("""
                INSERT INTO verification_queue (username, url, city, current_label, lead_value, priority, reason, created_ts)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (username, url, classification.get('city', ''), classification['label'],
                  classification['lead_value'], priority, "needs body text verification", now))
    
    elif should_suppress(classification):
        cursor.execute("""
            INSERT INTO suppression_list (username, reason, created_ts)
            VALUES (?, ?, ?)
        """, (username, classification['label'], now))
    
    conn.commit()
    conn.close()


def save_evidence_hits(username: str, classification: Dict[str, Any]):
    """Save evidence hits to evidence_hits table."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    now = datetime.now(timezone.utc).isoformat()
    
    for reason in classification['reasons']:
        # Parse reason to extract term and weight
        parts = reason.split(':')
        if len(parts) >= 2:
            weight_str = parts[0]
            term = ':'.join(parts[1:])
            
            try:
                weight = float(weight_str.replace('+', '').replace('-', ''))
                evidence_type = "client" if '+' in weight_str else "provider"
                source_field = "title/body" if "strong" in reason or "weak" in reason else "username"
                
                cursor.execute("""
                    INSERT INTO evidence_hits (username, evidence_type, term, weight, source_field, created_ts)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (username, evidence_type, term, weight, source_field, now))
            except ValueError:
                continue
    
    conn.commit()
    conn.close()


def test_classifier():
    """Test classifier with known examples."""
    print("=" * 60)
    print("TESTING EXACT CLASSIFIER")
    print("=" * 60)
    
    # Test DanitzHH (should be client_confirmed)
    danitzhh = classify_profile(
        username="DanitzHH",
        title="DanitzHH - Looking for Male Massage Ther",
        body_text="",
        city=""
    )
    print("\n[1] DanitzHH:")
    print(f"  Label: {danitzhh['label']}")
    print(f"  Client Score: {danitzhh['client_score']}")
    print(f"  Provider Score: {danitzhh['provider_score']}")
    print(f"  Net Score: {danitzhh['net_client_score']}")
    print(f"  Lead Value: {danitzhh['lead_value']}")
    print(f"  Confidence: {danitzhh['confidence']}")
    print(f"  Reasons: {danitzhh['reasons']}")
    print(f"  Should queue for review: {should_queue_for_review(danitzhh)}")
    
    # Test Inneedofmassage (should be client_possible or unknown)
    inneedofmassage = classify_profile(
        username="Inneedofmassage",
        title="Inneedofmassage | RentMasseur",
        body_text="",
        city=""
    )
    print("\n[2] Inneedofmassage:")
    print(f"  Label: {inneedofmassage['label']}")
    print(f"  Client Score: {inneedofmassage['client_score']}")
    print(f"  Provider Score: {inneedofmassage['provider_score']}")
    print(f"  Net Score: {inneedofmassage['net_client_score']}")
    print(f"  Lead Value: {inneedofmassage['lead_value']}")
    print(f"  Confidence: {inneedofmassage['confidence']}")
    print(f"  Reasons: {inneedofmassage['reasons']}")
    print(f"  Should visit next: {should_visit_next(inneedofmassage)}")
    print(f"  Should queue for review: {should_queue_for_review(inneedofmassage)}")
    
    # Test Achingbod (should be client_possible or unknown)
    achingbod = classify_profile(
        username="Achingbod",
        title="Achingbod | RentMasseur",
        body_text="",
        city=""
    )
    print("\n[3] Achingbod:")
    print(f"  Label: {achingbod['label']}")
    print(f"  Client Score: {achingbod['client_score']}")
    print(f"  Provider Score: {achingbod['provider_score']}")
    print(f"  Net Score: {achingbod['net_client_score']}")
    print(f"  Lead Value: {achingbod['lead_value']}")
    print(f"  Confidence: {achingbod['confidence']}")
    print(f"  Reasons: {achingbod['reasons']}")
    print(f"  Should visit next: {should_visit_next(achingbod)}")
    
    # Test Igor_Masseur (should be provider_confirmed)
    igor = classify_profile(
        username="Igor_Masseur",
        title="Igor_Masseur - Male Masseur, Gay massage",
        body_text="",
        city=""
    )
    print("\n[4] Igor_Masseur:")
    print(f"  Label: {igor['label']}")
    print(f"  Client Score: {igor['client_score']}")
    print(f"  Provider Score: {igor['provider_score']}")
    print(f"  Net Score: {igor['net_client_score']}")
    print(f"  Lead Value: {igor['lead_value']}")
    print(f"  Confidence: {igor['confidence']}")
    print(f"  Reasons: {igor['reasons']}")
    print(f"  Should suppress: {should_suppress(igor)}")
    
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    init_database()
    test_classifier()
