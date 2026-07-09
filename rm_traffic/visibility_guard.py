"""
Visibility Guard — ensure profile is shown in search.

Confirmed endpoint:
    GET /api/v1/account/keeponline
    PUT /api/v1/settings/visibility
"""

import logging

from .db import write_receipt
from .api_client import RentMasseurAPI

log = logging.getLogger("profileops.visibility")


def ensure_visible(api: RentMasseurAPI) -> bool:
    """Check if profile is hidden and unhide it if needed."""
    keep = api.get_keeponline()
    is_hidden = bool(keep.get("isAdHidden", 0))

    before = {"isAdHidden": int(is_hidden)}

    if is_hidden:
        log.warning("Profile is hidden. Repairing visibility...")
        result = api.set_visibility(True)
        # Verify
        keep = api.get_keeponline()
        after_hidden = bool(keep.get("isAdHidden", 0))
        after = {"isAdHidden": int(after_hidden)}
        verified = not after_hidden
        write_receipt(
            "profile_visibility_repair_v1",
            "ensure_visible",
            before,
            after,
            verified=verified,
        )
        if verified:
            log.info("Visibility repaired successfully")
        else:
            log.error("Visibility repair failed")
        return verified
    else:
        log.info("Profile visibility OK")
        write_receipt(
            "profile_visibility_check_v1",
            "check_visible",
            before,
            before,
            verified=True,
        )
        return True
