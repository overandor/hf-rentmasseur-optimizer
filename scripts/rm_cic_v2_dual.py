#!/usr/bin/env python3
"""
RM-CIC V2: Dual-Score Client Intent Classifier

Separate client_score and provider_score for accurate classification.
Negative targeting: exclude providers first, then identify clients.

Lead grades:
A = explicit seeker, contact-ready after compliance check
B = likely seeker, needs profile verification
C = unknown, revisit later
D = provider/competitor, exclude from client outreach
X = do-not-contact / compliance risk
"""
import csv
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List, Dict, Tuple

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RECEIPTS_DIR = Path(__file__).resolve().parent.parent / "receipts"

# Ensure directories exist
DATA_DIR.mkdir(parents=True, exist_ok=True)
RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

# Client title patterns (demand-side)
CLIENT_TITLE_PATTERNS = [
    (r"\blooking for\b.*\bmassage\b", 80),
    (r"\blooking for\b.*\btherapist\b", 75),
    (r"\blooking for\b.*\bmale\b", 70),
    (r"\bseeking\b.*\bmassage\b", 70),
    (r"\bneed\b.*\bmassage\b", 65),
    (r"\bwant\b.*\bmassage\b", 50),
    (r"\blooking to book\b", 60),
    (r"\blooking for\b.*\bprovider\b", 55),
]

# Client username patterns (demand-side)
CLIENT_USERNAME_PATTERNS = [
    (r"inneed", 35),
    (r"\bneed\b", 30),
    (r"looking", 30),
    (r"seeking", 30),
    (r"aching|sore|pain|relief", 25),
    (r"luv|love|relax", 20),
]

# Provider title patterns (supply-side)
PROVIDER_TITLE_PATTERNS = [
    (r"\bmale masseur\b", 90),
    (r"\bmasseur\b", 85),
    (r"\bgay massage in\b", 75),
    (r"\bmassage in\b", 70),
    (r"\bbodywork\b", 65),
    (r"\bdeep tissue\b", 60),
    (r"\bswedish\b", 55),
    (r"\bsports massage\b", 55),
    (r"\bincall\b|\boutcall\b|\brates\b", 50),
    (r"\bbook me\b|\bmy services\b", 65),
    (r"\btherapeutic massage\b", 55),
    (r"\btantric\b", 50),
]

# Provider username patterns (supply-side)
PROVIDER_USERNAME_PATTERNS = [
    (r"masseur", 50),
    (r"massage|massaging", 45),
    (r"hands|touch", 40),
    (r"bodywork", 40),
    (r"healing|therapist|therapy", 35),
    (r"deep|swedish|sportsmassage", 30),
]

# Generic title patterns
GENERIC_TITLE_PATTERNS = [
    r"^\s*$",
    r"^rentmasseur\.com$",
    r"\|\s*rentmasseur$",
]


@dataclass
class ProfileClassification:
    username: str
    title: str
    city: Optional[str]
    url: Optional[str]
    client_score: int
    provider_score: int
    confidence: int
    label: str
    lead_grade: str
    reasons: List[str]
    next_action: str


def clean_text(x: Optional[str]) -> str:
    return (x or "").strip().lower()


def apply_patterns(text: str, patterns: List[Tuple[str, int]], bucket: str) -> Tuple[int, List[str]]:
    score = 0
    reasons = []
    for pattern, points in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            score += points
            reasons.append(f"{bucket}:{pattern}:{points}")
    return score, reasons


def is_generic_title(title: str) -> bool:
    t = clean_text(title)
    return any(re.search(p, t, flags=re.IGNORECASE) for p in GENERIC_TITLE_PATTERNS)


def classify_profile(profile: Dict) -> ProfileClassification:
    """Dual-score classification."""
    username = profile.get("username") or ""
    title = profile.get("title") or ""
    city = profile.get("city")
    url = profile.get("url")

    u = clean_text(username)
    t = clean_text(title)

    client_score = 0
    provider_score = 0
    confidence = 20
    reasons = []

    # Client evidence
    s, r = apply_patterns(t, CLIENT_TITLE_PATTERNS, "client_title")
    client_score += s
    reasons.extend(r)

    s, r = apply_patterns(u, CLIENT_USERNAME_PATTERNS, "client_username")
    client_score += s
    reasons.extend(r)

    # Provider evidence
    s, r = apply_patterns(t, PROVIDER_TITLE_PATTERNS, "provider_title")
    provider_score += s
    reasons.extend(r)

    s, r = apply_patterns(u, PROVIDER_USERNAME_PATTERNS, "provider_username")
    provider_score += s
    reasons.extend(r)

    # Confidence calculation
    if title and not is_generic_title(title):
        confidence += 30
        reasons.append("confidence:descriptive_title:+30")
    else:
        confidence -= 20
        reasons.append("confidence:generic_or_blank_title:-20")

    if city:
        confidence += 10
        reasons.append("confidence:city_present:+10")

    if url:
        confidence += 10
        reasons.append("confidence:url_present:+10")

    # Classification logic
    if provider_score >= 70 and provider_score >= client_score + 30:
        label = "provider_likely"
    elif client_score >= 70 and client_score >= provider_score + 30:
        label = "client_likely"
    elif client_score >= 40 and provider_score < 50:
        label = "client_possible"
    elif provider_score >= 40 and client_score < 40:
        label = "provider_possible"
    else:
        label = "unknown"

    # Lead grade
    if label == "client_likely" and confidence >= 50:
        lead_grade = "A_contact_ready_after_compliance_check"
        next_action = "verify_contact_permissions"
    elif label == "client_possible" and confidence >= 30:
        lead_grade = "B_verify_profile_text"
        next_action = "revisit_profile_extract_bio"
    elif label == "unknown":
        lead_grade = "C_visit_or_recheck"
        next_action = "low_priority_revisit"
    else:
        lead_grade = "D_exclude_from_client_outreach"
        next_action = "exclude_or_competitor_intel"

    return ProfileClassification(
        username=username,
        title=title,
        city=city,
        url=url,
        client_score=client_score,
        provider_score=provider_score,
        confidence=max(0, min(confidence, 100)),
        label=label,
        lead_grade=lead_grade,
        reasons=reasons,
        next_action=next_action
    )


def main():
    print("=== RM-CIC V2: Dual-Score Classifier ===")

    # Load ny_users.json (profile universe)
    ny_file = DATA_DIR / "ny_users.json"
    if not ny_file.exists():
        print(f"NY users file not found: {ny_file}")
        return

    with open(ny_file) as f:
        ny_data = json.load(f)
    ny_users = ny_data.get("users", [])
    print(f"\n[1] Loaded {len(ny_users)} NY users (profile universe)")

    # Load task1_visit_back.json (evidence)
    visited_file = DATA_DIR / "task1_visit_back.json"
    if not visited_file.exists():
        print(f"Visited file not found: {visited_file}")
        return

    with open(visited_file) as f:
        visited_data = json.load(f)
    visited_profiles = visited_data.get("visited", [])
    print(f"[2] Loaded {len(visited_profiles)} visited profiles (evidence)")

    # Merge: attach titles from visited to universe
    print("\n[3] Merging evidence into profile universe...")
    title_map = {p["username"]: p.get("title") for p in visited_profiles}
    merged = []
    for p in ny_users:
        username = p["username"]
        title = title_map.get(username)
        merged.append({
            **p,
            "title": title,
            "visited": username in title_map,
            "source": "ny_users"
        })

    # Add visited-only profiles
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
                "source": "visited_only"
            })

    print(f"  Merged: {len(merged)} total profiles")

    # Classify all profiles
    print("\n[4] Running dual-score classification...")
    classified = []
    for p in merged:
        classification = classify_profile(p)
        classified.append({
            **p,
            "client_score": classification.client_score,
            "provider_score": classification.provider_score,
            "confidence": classification.confidence,
            "label": classification.label,
            "lead_grade": classification.lead_grade,
            "reasons": classification.reasons,
            "next_action": classification.next_action
        })

    # Bucket by lead grade
    print("\n[5] Bucketing by lead grade...")
    buckets = {
        "A": [],
        "B": [],
        "C": [],
        "D": [],
        "X": []
    }
    for p in classified:
        grade = p["lead_grade"][0]  # First character
        buckets[grade].append(p)

    print(f"  A (contact-ready): {len(buckets['A'])}")
    print(f"  B (verify needed): {len(buckets['B'])}")
    print(f"  C (unknown): {len(buckets['C'])}")
    print(f"  D (exclude): {len(buckets['D'])}")
    print(f"  X (compliance risk): {len(buckets['X'])}")

    # Save classification audit
    audit_file = DATA_DIR / "classification_audit_v2.json"
    with open(audit_file, "w") as f:
        json.dump({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_profiles": len(classified),
            "classified": classified
        }, f, indent=2)
    print(f"\n[6] Saved audit: {audit_file}")

    # Export clients_A_B.csv
    clients = buckets["A"] + buckets["B"]
    clients_csv = DATA_DIR / "clients_A_B.csv"
    with open(clients_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["username", "title", "city", "url", "client_score", "provider_score", "confidence", "label", "lead_grade", "next_action"])
        for p in clients:
            writer.writerow([
                p["username"],
                p["title"],
                p["city"],
                p["url"],
                p["client_score"],
                p["provider_score"],
                p["confidence"],
                p["label"],
                p["lead_grade"],
                p["next_action"]
            ])
    print(f"  Saved clients CSV: {clients_csv}")

    # Export providers_excluded.csv
    providers = buckets["D"] + buckets["X"]
    providers_csv = DATA_DIR / "providers_excluded.csv"
    with open(providers_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["username", "title", "city", "url", "client_score", "provider_score", "confidence", "label", "lead_grade", "next_action"])
        for p in providers:
            writer.writerow([
                p["username"],
                p["title"],
                p["city"],
                p["url"],
                p["client_score"],
                p["provider_score"],
                p["confidence"],
                p["label"],
                p["lead_grade"],
                p["next_action"]
            ])
    print(f"  Saved providers CSV: {providers_csv}")

    # Save summary
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total_profiles": len(classified),
        "ny_users": len(ny_users),
        "visited_profiles": len(visited_profiles),
        "merged_profiles": len(merged),
        "A_contact_ready": len(buckets["A"]),
        "B_verify_needed": len(buckets["B"]),
        "C_unknown": len(buckets["C"]),
        "D_exclude": len(buckets["D"]),
        "X_compliance_risk": len(buckets["X"]),
        "client_candidates": len(clients),
        "providers_excluded": len(providers),
        "next_action": "revisit B and C profiles for body evidence"
    }
    summary_file = DATA_DIR / "client_detection_summary_v2.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Saved summary: {summary_file}")

    # Save receipt
    ts = datetime.now(timezone.utc).isoformat().replace(":", "-")
    receipt_file = RECEIPTS_DIR / f"rm_cic_v2_{ts}.json"
    with open(receipt_file, "w") as f:
        json.dump({
            "action": "rm_cic_v2_dual_score",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "buckets": {k: len(v) for k, v in buckets.items()}
        }, f, indent=2)
    print(f"  Receipt: {receipt_file}")

    print("\n=== COMPLETE ===")
    print(f"Client candidates (A+B): {len(clients)}")
    print(f"  - A (contact-ready): {len(buckets['A'])}")
    print(f"  - B (verify needed): {len(buckets['B'])}")
    print(f"Providers excluded (D+X): {len(providers)}")
    print(f"Next action: Revisit B and C profiles for body evidence")


if __name__ == "__main__":
    main()
