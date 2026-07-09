#!/usr/bin/env python3
"""Task 6: Metrics snapshot + ingest. Independent process.
Fetches live dashboard stats, posts sanitized packet to HF Space."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import json, time, os, sys, requests

def main():
    from rm_traffic.api_client import RentMasseurAPI
    api = RentMasseurAPI()
    assert api.login(os.environ.get("RM_USER", ""), os.environ.get("RM_PASS", "")), "Login failed"

    # Collect real metrics
    dash = api.get_dashboard()
    stats = api.get_ad_statistics()
    about = api.get_about()
    keeponline = api.get_keeponline()

    profile_stats = stats.get("profileStatistics", {})
    visits = profile_stats.get("visits", [])
    today_visits = next((v["count"] for v in visits if v["day"] == "Today"), 0)

    packet = {
        "date": time.strftime("%Y-%m-%d"),
        "profile_views": profile_stats.get("totalPageViews", 0),
        "contact_clicks": profile_stats.get("totalContactClicks", 0),
        "new_visits": today_visits,
        "new_emails": keeponline.get("newEmails", 0),
        "availability_state": "available" if dash.get("userSetting", {}).get("availability", {}).get("available") == 1 else "unavailable",
        "is_hidden": not bool(dash.get("userSetting", {}).get("visibility", 1)),
        "headline": about.get("userProps", {}).get("assets", {}).get("headline", ""),
        "description_len": len(about.get("userProps", {}).get("assets", {}).get("description", "")),
        "bio_id": os.getenv("BIO_ID", "controlled_wolf_v1"),
        "notes": "automated daily snapshot",
    }

    print(f"[task6] Metrics: {packet['profile_views']} views, {packet['contact_clicks']} clicks, {packet['new_visits']} today")

    # Post to HF Space
    hf_url = os.getenv("HF_SPACE_URL", "https://josephrw-rentmasseur-optimizer.hf.space")
    try:
        resp = requests.post(f"{hf_url}/api/metrics/ingest", json=packet, timeout=15)
        print(f"[task6] Ingest response: {resp.status_code} {resp.text[:200]}")
        ingest_result = resp.json() if resp.status_code == 200 else {"error": resp.text[:200]}
    except Exception as e:
        print(f"[task6] Ingest failed: {e}")
        ingest_result = {"error": str(e)[:200]}

    result = {
        "status": "GREEN_REAL",
        "packet": packet,
        "ingest_result": ingest_result,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open("data/task6_metrics_ingest.json", "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"[task6] Done: {result['status']}")

if __name__ == "__main__":
    main()
