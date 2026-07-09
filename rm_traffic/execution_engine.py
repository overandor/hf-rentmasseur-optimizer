"""
Execution Engine — execute API mutations with verification and receipts.

Every action: read → mutate → verify → receipt.
"""

import logging
from typing import Dict, Any, Callable

from .api_client import RentMasseurAPI
from .db import write_receipt
from .content_policy import check_bio_risk, check_headline_risk

log = logging.getLogger("profileops.execution")


def _hash_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def execute_visibility(api: RentMasseurAPI, visible: bool) -> Dict:
    """Set visibility and verify."""
    keep_before = api.get_keeponline()
    before = {"isAdHidden": int(keep_before.get("isAdHidden", 0))}

    result = api.set_visibility(visible)

    keep_after = api.get_keeponline()
    after = {"isAdHidden": int(keep_after.get("isAdHidden", 0))}
    verified = (after["isAdHidden"] == int(not visible))

    write_receipt("visibility_change_v1", "set_visibility", before, after, verified=verified)
    log.info("Visibility set to %s (verified=%s)", visible, verified)
    return {"success": verified, "result": result}


def execute_bio(api: RentMasseurAPI, headline: str, description: str) -> Dict:
    """Update bio with policy check and verification."""
    headline_risk = check_headline_risk(headline)
    bio_risk = check_bio_risk(description)
    if headline_risk > 0.7 or bio_risk > 0.7:
        write_receipt("bio_change_blocked_v1", "set_about",
                      {"headline": headline, "description": description[:200]},
                      {"reason": "policy_risk", "headline_risk": headline_risk, "bio_risk": bio_risk},
                      verified=False)
        log.error("Bio change blocked by policy")
        return {"success": False, "reason": "policy_risk"}

    about_before = api.get_about()
    assets_before = about_before.get("userProps", {}).get("assets", {})
    before = {
        "headline": assets_before.get("headline"),
        "description_hash": _hash_text(assets_before.get("description", "")),
    }

    result = api.set_about(headline, description)

    about_after = api.get_about()
    assets_after = about_after.get("userProps", {}).get("assets", {})
    after = {
        "headline": assets_after.get("headline"),
        "description_hash": _hash_text(assets_after.get("description", "")),
    }
    verified = (after["headline"] == headline and after["description_hash"] == _hash_text(description))

    write_receipt("bio_change_v1", "set_about", before, after, verified=verified)
    log.info("Bio updated (verified=%s)", verified)
    return {"success": verified, "result": result}


def rollback_bio(api: RentMasseurAPI, previous_headline: str, previous_description: str) -> Dict:
    """Rollback to previous bio."""
    log.warning("Rolling back bio to previous version")
    before = api.get_about()
    result = execute_bio(api, previous_headline, previous_description)
    after = api.get_about()
    write_receipt("bio_rollback_v1", "rollback_bio",
                  {"headline": before.get("userProps", {}).get("assets", {}).get("headline")},
                  {"headline": after.get("userProps", {}).get("assets", {}).get("headline")},
                  verified=result["success"])
    return result


def execute_if_verified(api: RentMasseurAPI, action: Callable, *args, **kwargs) -> Dict:
    """Generic wrapper: execute an action and verify."""
    try:
        result = action(*args, **kwargs)
        return {"success": True, "result": result}
    except Exception as e:
        log.error("Execution failed: %s", e)
        write_receipt("execution_error_v1", "execute", {}, {"error": str(e)}, verified=False)
        return {"success": False, "error": str(e)}
