"""
Stats Collector — traffic snapshots every cycle.

Confirmed endpoints:
    GET /api/v1/account/dashboard
    GET /api/v1/account/dashboard/ad-statistics
    GET /api/v1/account/keeponline
    GET /api/v1/settings/about
"""

import logging

from .db import write_receipt, write_traffic_snapshot
from .api_client import RentMasseurAPI

log = logging.getLogger("profileops.stats")


def collect_snapshot(api: RentMasseurAPI) -> dict:
    """Collect a single traffic snapshot and store it."""
    dashboard = api.get_dashboard()
    stats = api.get_ad_statistics()
    keep = api.get_keeponline()
    about = api.get_about()

    prof_stats = stats.get("profileStatistics", {}) or {}
    assets = about.get("userProps", {}).get("assets", {})
    availability = dashboard.get("userSetting", {}).get("availability", {})

    snapshot = {
        "profile_views": prof_stats.get("totalPageViews"),
        "contact_clicks": prof_stats.get("totalContactClicks"),
        "new_visits": keep.get("newVisits"),
        "new_emails": keep.get("newEmails"),
        "is_hidden": int(bool(keep.get("isAdHidden", 0))),
        "is_available": int(availability.get("available", 0)),
        "availability_valid_to": availability.get("validTo"),
        "headline": assets.get("headline"),
        "description_len": len(assets.get("description", "")),
    }

    write_traffic_snapshot(snapshot)
    write_receipt(
        "traffic_snapshot_v1",
        "collect_snapshot",
        {},
        snapshot,
        verified=True,
    )

    log.info("Snapshot: views=%s contacts=%s visits=%s emails=%s hidden=%s",
             snapshot["profile_views"], snapshot["contact_clicks"],
             snapshot["new_visits"], snapshot["new_emails"], snapshot["is_hidden"])
    return snapshot


def calculate_conversion_rate(views: int, clicks: int) -> float:
    if not views:
        return 0.0
    return round(clicks / views, 4)


def compare_to_baseline(current: dict, baseline: dict) -> dict:
    """Compare current snapshot to baseline and return deltas."""
    if not baseline:
        return {"delta_views": 0, "delta_clicks": 0, "delta_rate": 0.0}
    return {
        "delta_views": (current.get("profile_views") or 0) - (baseline.get("profile_views") or 0),
        "delta_clicks": (current.get("contact_clicks") or 0) - (baseline.get("contact_clicks") or 0),
        "baseline_rate": calculate_conversion_rate(
            baseline.get("profile_views") or 0, baseline.get("contact_clicks") or 0
        ),
        "current_rate": calculate_conversion_rate(
            current.get("profile_views") or 0, current.get("contact_clicks") or 0
        ),
    }
