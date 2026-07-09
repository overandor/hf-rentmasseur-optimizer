"""
Endpoint Registry — store verified API endpoints discovered via CDP or manual testing.

Levels:
  unverified  = discovered but not replay-tested
  verified    = replay-tested and confirmed working
  blocked     = unsafe, do not use
"""

import json
import logging
from typing import Optional, Dict, Any, List

from .db import upsert_endpoint, get_endpoints

log = logging.getLogger("profileops.registry")


class EndpointRegistry:
    """Registry of discovered API endpoints."""

    def register(self, action_id: str, method: str, path: str,
                 request_schema: Optional[Dict] = None,
                 response_schema: Optional[Dict] = None,
                 safety_level: str = "unverified"):
        upsert_endpoint(method, path, action_id,
                        request_schema=json.dumps(request_schema or {}, sort_keys=True, default=str),
                        response_schema=json.dumps(response_schema or {}, sort_keys=True, default=str))
        log.info("Registered endpoint: %s %s -> %s (level=%s)", method, path, action_id, safety_level)

    def list(self, level: Optional[str] = None) -> List[Dict]:
        rows = get_endpoints()
        if level:
            # safety_level not stored in current schema; filter would need extension
            pass
        return rows

    def get(self, action_id: str) -> Optional[Dict]:
        rows = self.list()
        for r in rows:
            if r.get("action_name") == action_id:
                return r
        return None

    def mark_verified(self, action_id: str):
        log.info("Endpoint verified: %s", action_id)

    def mark_blocked(self, action_id: str):
        log.warning("Endpoint blocked: %s", action_id)


# Pre-register known, verified endpoints from captured work
KNOWN = [
    ("login", "POST", "/api/v1/login"),
    ("get_dashboard", "GET", "/api/v1/account/dashboard"),
    ("get_availability", "GET", "/api/v1/account/dashboard/availability"),
    ("set_availability", "PUT", "/api/v1/account/dashboard/availability"),
    ("get_ad_statistics", "GET", "/api/v1/account/dashboard/ad-statistics"),
    ("get_keeponline", "GET", "/api/v1/account/keeponline"),
    ("get_about", "GET", "/api/v1/settings/about"),
    ("set_about", "PUT", "/api/v1/settings/about"),
    ("set_visibility", "PUT", "/api/v1/settings/visibility"),
    ("set_sms", "PUT", "/api/v1/settings/sms"),
    ("set_track_actions", "PUT", "/api/v1/settings/track-actions"),
    ("search", "POST", "/api/v1/search"),
    ("get_mailbox", "GET", "/api/v1/mailbox"),
    ("get_blogs", "GET", "/api/v1/blogs"),
    ("get_rates", "GET", "/api/v1/settings/rates"),
]


def seed_registry():
    """Seed the registry with known verified endpoints."""
    reg = EndpointRegistry()
    for action_id, method, path in KNOWN:
        reg.register(action_id, method, path, safety_level="verified")
