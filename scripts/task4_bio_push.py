#!/usr/bin/env python3
"""Task 4: Bio push via direct API. Independent tiny Chrome window not needed — uses API.
Pushes a selected bio variant to the live profile via PUT /settings/about."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json, time, os, sys

def main():
    from rm_traffic.api_client import RentMasseurAPI
    api = RentMasseurAPI()
    assert api.login(os.environ.get("RM_USER", ""), os.environ.get("RM_PASS", "")), "Login failed"

    bio_id = os.getenv("BIO_ID", "controlled_wolf_v1")
    bio_dir = os.path.join(os.path.dirname(__file__), "..", "content", "bios")
    # Try extension repo bios too
    ext_bio_dir = os.path.expanduser("~/Downloads/MEMBRA::SURFACE=BUILD@LIVE/02_AI_Agents/rentmasseur-extension/content/bios")
    opt_bio_dir = os.path.expanduser("~/Downloads/rentmasseur-optimizer/content/bios")

    bio_path = None
    for d in [bio_dir, ext_bio_dir, opt_bio_dir]:
        p = os.path.join(d, f"{bio_id}.md")
        if os.path.exists(p):
            bio_path = p
            break

    if not bio_path:
        # Use inline default
        headline = "You bring the Smile, i bring the Wolf..."
        description = """KARPATHIAN WOLF — targeted recovery in Manhattan.

75,000+ profile views.

I do not do generic relaxation. I do focused deep tissue, sports recovery, Swedish flow, stretching, and pressure-forward bodywork for men carrying stress in their neck, shoulders, back, hips, and legs.

If your shoulders live near your ears, you are my kind of client.

My approach is simple: find the knot, negotiate with the knot, defeat the knot.

Book a session. Your body will thank you."""
        print(f"[task4] Using inline bio (bio_id={bio_id} not found)")
    else:
        text = open(bio_path).read().strip()
        lines = text.split("\n", 1)
        headline = lines[0].lstrip("# ").strip()
        description = lines[1].strip() if len(lines) > 1 else text
        print(f"[task4] Loaded bio from {bio_path}")

    # Get current bio for before snapshot
    before = api.get_about()
    before_headline = before.get("userProps", {}).get("assets", {}).get("headline", "")

    # Push new bio
    resp = api.set_about(headline, description)
    print(f"[task4] Bio pushed: {headline[:50]}")
    print(f"[task4] Response: {str(resp)[:200]}")

    # Verify
    after = api.get_about()
    after_headline = after.get("userProps", {}).get("assets", {}).get("headline", "")

    result = {
        "status": "GREEN_REAL" if after_headline == headline else "RED_FAILED",
        "bio_id": bio_id,
        "before_headline": before_headline,
        "after_headline": after_headline,
        "headline": headline,
        "description_len": len(description),
        "response": str(resp)[:500],
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open("data/task4_bio_push.json", "w") as f:
        json.dump(result, f, indent=2)
    print(f"[task4] Done: {result['status']}")

if __name__ == "__main__":
    main()
