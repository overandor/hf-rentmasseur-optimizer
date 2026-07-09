"""
Availability Guard — refresh availability only when near expiry.

Confirmed endpoints:
    GET /api/v1/account/dashboard/availability
    PUT /api/v1/settings/availability (pending confirmation)

For now this module reports status and alerts when refresh is needed.
"""

import logging
import time

from .db import write_receipt
from .api_client import RentMasseurAPI

log = logging.getLogger("profileops.availability")

REFRESH_THRESHOLD_SECONDS = 45 * 60


def get_availability_seconds_remaining(availability: dict) -> int:
    """Return seconds remaining, or 0 if not available."""
    selected = availability.get("selected", "")
    countdown = availability.get("countdown", 0)
    if selected != "Available" or not countdown:
        return 0
    remaining = int(countdown - time.time())
    return max(0, remaining)


def check_availability(api: RentMasseurAPI) -> dict:
    """Check availability status and alert if refresh is needed."""
    avail = api.get_availability()
    remaining = get_availability_seconds_remaining(avail)
    selected = avail.get("selected", "")

    status = {
        "selected": selected,
        "remaining_seconds": remaining,
        "needs_refresh": remaining < REFRESH_THRESHOLD_SECONDS,
    }

    if status["needs_refresh"]:
        log.warning("Availability needs refresh: %s (%s minutes remaining)", selected, remaining // 60)
        write_receipt(
            "availability_refresh_needed_v1",
            "check_availability",
            status,
            status,
            verified=False,
        )
    else:
        log.info("Availability OK: %s (%s minutes remaining)", selected, remaining // 60)
        write_receipt(
            "availability_check_v1",
            "check_availability",
            status,
            status,
            verified=True,
        )

    return status


def refresh_availability(api: RentMasseurAPI, hours: int = 6) -> bool:
    """
    Refresh availability using verified endpoint.
    hours: 1, 2, 3, 4, 5, 6 maps to duration index 0-5.
    """
    duration_map = {1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5}
    duration = duration_map.get(hours, 5)
    log.info("Refreshing availability for %s hours...", hours)
    before = api.get_availability()
    result = api.set_availability(option=1, duration=duration)
    after = api.get_availability()
    verified = after.get("selected") == "Available" and after.get("countdown", 0) > before.get("countdown", 0)
    write_receipt(
        "availability_refresh_v1",
        "refresh_availability",
        {"selected": before.get("selected"), "countdown": before.get("countdown")},
        {"selected": after.get("selected"), "countdown": after.get("countdown"), "api_result": result},
        verified=verified,
    )
    if verified:
        log.info("Availability refreshed successfully")
    else:
        log.error("Availability refresh verification failed")
    return verified
