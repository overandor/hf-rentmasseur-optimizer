#!/usr/bin/env python3
"""
LLM Verifier Layer for Ambiguous Profiles

Uses LLM to verify profiles with conflicting or ambiguous evidence.
Only processes profiles where rule-based classification is uncertain.
"""
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Any, Optional
import requests

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DATA_DIR / "rm_cic.db"

# LLM configuration - using a free/accessible endpoint
LLM_API_URL = "https://api.openai.com/v1/chat/completions"
LLM_MODEL = "gpt-4o-mini"  # Cost-effective model for verification

# Alternative: use Groq for faster inference
# LLM_API_URL = "https://api.groq.com/openai/v1/chat/completions"
# LLM_MODEL = "llama3-70b-8192"


def get_ambiguous_profiles(limit: int = 20) -> List[Dict[str, Any]]:
    """Get profiles with ambiguous classification."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get profiles that are:
    # - client_possible (weak evidence)
    # - unknown with any lead_value (potential clients)
    # - Or have conflicting evidence (client_score and provider_score both > 0)
    cursor.execute("""
        SELECT
            p.username,
            p.name,
            p.city,
            p.url,
            v.title,
            v.body_text,
            c.label,
            c.client_score,
            c.provider_score,
            c.lead_value,
            c.confidence,
            c.reasons_json
        FROM profiles p
        JOIN profile_classifications c ON p.username = c.username
        LEFT JOIN profile_visits v ON p.username = v.username
        WHERE c.label IN ('client_possible', 'unknown')
          AND c.label != 'provider_confirmed'
        ORDER BY c.lead_value DESC
        LIMIT ?
    """, (limit,))

    profiles = []
    for row in cursor.fetchall():
        reasons_json = row[10]
        if isinstance(reasons_json, str) and reasons_json:
            reasons = json.loads(reasons_json)
        else:
            reasons = []

        profiles.append({
            "username": row[0],
            "name": row[1],
            "city": row[2],
            "url": row[3],
            "title": row[4] or "",
            "body_text": row[5] or "",
            "current_label": row[6],
            "client_score": row[7],
            "provider_score": row[8],
            "lead_value": row[9],
            "confidence": row[10],
            "reasons": reasons
        })

    conn.close()
    return profiles


def llm_verify_profile(profile: Dict[str, Any], api_key: Optional[str] = None) -> Dict[str, Any]:
    """Use LLM to verify a profile's classification."""
    prompt = f"""You classify public profile text into one of:
client_confirmed, client_possible, unknown, provider_possible, provider_confirmed, mixed.

A client is seeking massage/bodywork.
A provider is offering massage/bodywork.

Rules:
- Do not classify as client_confirmed unless the text explicitly says looking for, seeking, need, want, or trying to book massage/bodywork.
- Provider service language overrides weak username hints.
- Return JSON only.

Profile:
username: {profile['username']}
title: {profile['title']}
body: {profile['body_text'][:1000] if profile['body_text'] else 'No body text available'}

Return:
{{
  "label": "...",
  "confidence": 0.0-1.0,
  "client_evidence": [],
  "provider_evidence": [],
  "reason": "..."
}}"""

    headers = {
        "Content-Type": "application/json"
    }

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a strict classifier that returns only JSON."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.1,
        "max_tokens": 500
    }

    try:
        response = requests.post(LLM_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # Parse JSON from response
        llm_result = json.loads(content)
        return llm_result
    except Exception as e:
        return {
            "label": "unknown",
            "confidence": 0.0,
            "client_evidence": [],
            "provider_evidence": [],
            "reason": f"LLM error: {str(e)}"
        }


def update_profile_with_llm_result(username: str, llm_result: Dict[str, Any]):
    """Update profile classification with LLM verification result."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Store LLM verification in a new field or separate table
    # For now, we'll add it to reasons_json
    cursor.execute("SELECT reasons_json FROM profile_classifications WHERE username = ?", (username,))
    row = cursor.fetchone()
    if row:
        existing_reasons = json.loads(row[0]) if row[0] else []
        existing_reasons.append(f"llm_verification:{llm_result['label']}")
        existing_reasons.append(f"llm_confidence:{llm_result['confidence']}")
        existing_reasons.append(f"llm_reason:{llm_result['reason']}")

        cursor.execute("""
            UPDATE profile_classifications
            SET reasons_json = ?
            WHERE username = ?
        """, (json.dumps(existing_reasons), username))

    conn.commit()
    conn.close()


def verify_ambiguous_profiles(api_key: Optional[str] = None, limit: int = 20):
    """Verify ambiguous profiles using LLM."""
    print("=== LLM VERIFIER LAYER ===")
    print(f"Fetching {limit} ambiguous profiles...")

    profiles = get_ambiguous_profiles(limit)
    print(f"Found {len(profiles)} ambiguous profiles")

    if not profiles:
        print("No ambiguous profiles to verify.")
        return

    if not api_key:
        print("\nWARNING: No API key provided. LLM verification will fail.")
        print("Set OPENAI_API_KEY environment variable or pass api_key parameter.")
        print("Proceeding with mock verification for demonstration...")

    results = []
    for i, profile in enumerate(profiles, 1):
        print(f"\n[{i}/{len(profiles)}] Verifying: {profile['username']}")
        print(f"  Current label: {profile['current_label']}")
        print(f"  Client score: {profile['client_score']}")
        print(f"  Provider score: {profile['provider_score']}")
        print(f"  Title: {profile['title'][:80]}...")

        if api_key:
            llm_result = llm_verify_profile(profile, api_key)
        else:
            # Mock verification for demonstration
            llm_result = {
                "label": profile['current_label'],
                "confidence": 0.5,
                "client_evidence": [],
                "provider_evidence": [],
                "reason": "Mock verification (no API key)"
            }

        print(f"  LLM label: {llm_result['label']}")
        print(f"  LLM confidence: {llm_result['confidence']}")
        print(f"  LLM reason: {llm_result['reason']}")

        # Update database with LLM result
        update_profile_with_llm_result(profile['username'], llm_result)

        results.append({
            "username": profile['username'],
            "current_label": profile['current_label'],
            "llm_label": llm_result['label'],
            "llm_confidence": llm_result['confidence'],
            "llm_reason": llm_result['reason'],
            "agreement": profile['current_label'] == llm_result['label']
        })

    # Print summary
    print("\n" + "=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)

    agreement_count = sum(1 for r in results if r['agreement'])
    print(f"Total verified: {len(results)}")
    print(f"Agreement: {agreement_count}/{len(results)} ({agreement_count/len(results)*100:.1f}%)")

    print("\nDisagreements:")
    for r in results:
        if not r['agreement']:
            print(f"  {r['username']}: {r['current_label']} -> {r['llm_label']} (confidence: {r['llm_confidence']})")

    # Save results
    output_path = DATA_DIR / "llm_verification_results.json"
    with open(output_path, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved: {output_path}")


def main():
    import os

    # Get API key from environment or parameter
    api_key = os.environ.get("OPENAI_API_KEY")

    # Verify ambiguous profiles
    verify_ambiguous_profiles(api_key=api_key, limit=20)


if __name__ == "__main__":
    main()
