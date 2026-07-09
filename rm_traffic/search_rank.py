"""
Search Rank Monitor — track profile position in search results.

Confirmed endpoint:
    POST /api/v1/search
    body: {"searchCity": "manhattan-ny", "available": 1, "page": 1, "skipUsers": "0"}

Rules:
- Run only once per hour max.
- Search for own username only.
- Record position, total results, and available results.
- Do not scrape other profiles aggressively.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict

from .db import write_receipt
from .api_client import RentMasseurAPI

log = logging.getLogger("profileops.search")


def find_position(results: Dict, username: str) -> Optional[int]:
    """Find the position of the user's profile in search results."""
    username_lower = username.lower()
    masseurs = results.get("masseurs") if isinstance(results.get("masseurs"), list) else []
    if not masseurs:
        masseurs = results.get("data", {}).get("masseurs", []) if isinstance(results.get("data"), dict) else []
    if not masseurs:
        masseurs = results.get("list", []) if isinstance(results.get("list"), list) else []
    if not masseurs:
        # Try generic list keys
        for key in ["users", "items", "results"]:
            if isinstance(results.get(key), list):
                masseurs = results[key]
                break

    for i, m in enumerate(masseurs):
        if not isinstance(m, dict):
            continue
        uname = (m.get("username") or m.get("userCard", {}).get("username") or "").lower()
        if uname == username_lower:
            return i + 1
    return None


def total_count(results: Dict) -> int:
    """Estimate total search results."""
    return (
        results.get("total") or
        results.get("count") or
        results.get("totalCount") or
        len(results.get("masseurs", [])) or
        0
    )


def check_search_rank(api: RentMasseurAPI, username: str, city: str = "manhattan-ny",
                      available_only: bool = True) -> Dict:
    """Check search position for the user's profile."""
    results = api.search(city, available_only=available_only)
    position = find_position(results, username)
    total = total_count(results)
    available_total = total if available_only else None

    rank = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "city": city,
        "available_only": available_only,
        "position": position,
        "total": total,
        "available_total": available_total,
        "found": position is not None,
    }

    write_receipt("search_rank_check_v1", "check_search_rank", {}, rank, verified=True)
    if position:
        log.info("Search rank: #%d/%d in %s", position, total, city)
    else:
        log.warning("Profile not found in search results for %s", city)
    return rank


def check_available_now_rank(api: RentMasseurAPI, username: str, city: str = "manhattan-ny") -> Dict:
    """Check Available Now search rank."""
    return check_search_rank(api, username, city, available_only=True)


def check_all_search_ranks(api: RentMasseurAPI, username: str) -> Dict:
    """Check both general and available-only search ranks."""
    return {
        "all": check_search_rank(api, username, available_only=False),
        "available_now": check_search_rank(api, username, available_only=True),
    }
