"""
Traffic Analyzer — compare snapshots, detect drops, compute conversion rates.
"""

import logging
from typing import List, Dict

from .db import get_latest_traffic_snapshot

log = logging.getLogger("profileops.analyzer")


def conversion_rate(views: int, clicks: int) -> float:
    if not views:
        return 0.0
    return round(clicks / views, 4)


def compare_snapshots(current: Dict, previous: Dict) -> Dict:
    """Compare two snapshots and return deltas."""
    delta_views = (current.get("profile_views") or 0) - (previous.get("profile_views") or 0)
    delta_clicks = (current.get("contact_clicks") or 0) - (previous.get("contact_clicks") or 0)
    current_rate = conversion_rate(current.get("profile_views") or 0, current.get("contact_clicks") or 0)
    previous_rate = conversion_rate(previous.get("profile_views") or 0, previous.get("contact_clicks") or 0)
    return {
        "delta_views": delta_views,
        "delta_clicks": delta_clicks,
        "previous_rate": previous_rate,
        "current_rate": current_rate,
        "rate_delta": round(current_rate - previous_rate, 4),
    }


def analyze_trend(hours: int = 24) -> Dict:
    """Analyze traffic trend over last N hours."""
    rows = get_latest_traffic_snapshot(limit=100)
    if len(rows) < 2:
        return {"status": "insufficient_data"}
    current = rows[0]
    # Find snapshot closest to N hours ago
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    baseline = rows[-1]
    for row in rows[1:]:
        ts = datetime.fromisoformat(row["created_at"])
        if (now - ts).total_seconds() <= hours * 3600:
            baseline = row
            break

    comparison = compare_snapshots(current, baseline)
    return {
        "status": "ok",
        "hours": hours,
        "current": {
            "views": current.get("profile_views"),
            "contacts": current.get("contact_clicks"),
            "rate": conversion_rate(current.get("profile_views") or 0, current.get("contact_clicks") or 0),
        },
        "baseline": {
            "views": baseline.get("profile_views"),
            "contacts": baseline.get("contact_clicks"),
            "rate": conversion_rate(baseline.get("profile_views") or 0, baseline.get("contact_clicks") or 0),
        },
        "comparison": comparison,
        "alert": comparison["delta_views"] < 0 or comparison["rate_delta"] < -0.01,
    }


def detect_drop() -> Dict:
    """Detect if views or contact rate dropped significantly."""
    trend = analyze_trend(hours=24)
    if trend["status"] != "ok":
        return trend
    if trend["alert"]:
        log.warning("Traffic drop detected: %s", trend["comparison"])
    return trend
