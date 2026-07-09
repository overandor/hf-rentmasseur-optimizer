"""
Content Optimizer — conservative bio A/B testing.

Rules:
- One bio change per 24 hours max.
- Only rotate through known, hypothesis-driven variants.
- Store before/after metrics and receipt.
- Never auto-generate random spam.
"""

import logging
import random
import time
from datetime import datetime, timezone

from .db import (
    write_receipt,
    upsert_content_variant,
    set_variant_status,
    get_active_variant,
    get_variant_history,
    start_experiment,
    end_experiment,
    get_open_experiments,
    get_latest_traffic_snapshot,
)
from .api_client import RentMasseurAPI
from .bio_variants import get_variant, list_variant_ids
from .bio_variants_library import get_variant as get_library_variant, list_all as list_all_library_variants, count as library_count
from .llm_bio_writer import generate_bio_with_llm
from .content_policy import check_bio_risk

log = logging.getLogger("profileops.content")

MIN_SECONDS_BETWEEN_BIO_CHANGES = 24 * 60 * 60


def _last_bio_change_time() -> float:
    """Return timestamp of last applied bio variant, or 0."""
    history = get_variant_history("bio", limit=1)
    if not history:
        return 0
    row = history[0]
    if row.get("status") == "active" and row.get("applied_at"):
        dt = datetime.fromisoformat(row["applied_at"])
        return dt.timestamp()
    return 0


def _can_change_bio() -> bool:
    last = _last_bio_change_time()
    if not last:
        return True
    return (time.time() - last) >= MIN_SECONDS_BETWEEN_BIO_CHANGES


def _pick_next_variant(current_id: str) -> dict:
    """Pick a different variant than the current one."""
    candidates = [vid for vid in list_variant_ids() if vid != current_id]
    if not candidates:
        return None
    return get_variant(random.choice(candidates))


def draft_bio_variant(api: RentMasseurAPI, use_llm: bool = True) -> dict:
    """
    Draft a new bio variant. Uses LLM if configured, otherwise library.
    Does NOT apply it.
    """
    about = api.get_about()
    assets = about.get("userProps", {}).get("assets", {})
    current_headline = assets.get("headline", "")
    current_description = assets.get("description", "")

    raw_history = get_latest_traffic_snapshot(7)
    history = [
        {"ts": r["created_at"], "views": r["profile_views"], "contact_clicks": r["contact_clicks"], "visits": r["new_visits"]}
        for r in raw_history
    ]
    suggestion = None
    if use_llm:
        import os
        suggestion = generate_bio_with_llm(
            {"about": about, "stats": {}}, history,
            current_headline, current_description,
            city="Manhattan, NYC", provider=os.environ.get("LLM_PROVIDER"),
            model=os.environ.get("LLM_MODEL")
        )

    if suggestion:
        variant_id = f"llm_{int(time.time())}"
        variant = {
            "variant_id": variant_id,
            "headline": suggestion["headline"],
            "description": suggestion["bio"],
            "hypothesis": "LLM-generated variant based on profile and recent traffic.",
        }
    else:
        active = get_active_variant("bio")
        current_idx = -1
        if active:
            try:
                current_idx = int(active["variant_id"].replace("module_", ""))
            except Exception:
                pass
        # Pick next from 30-module library
        next_idx = (current_idx + 1) % library_count()
        variant = get_library_variant(next_idx)
        if not variant:
            log.warning("No alternative variant found")
            return None

    # Policy check
    risk = check_bio_risk(variant["headline"] + " " + variant["description"])
    variant["risk_score"] = risk
    if risk > 0.7:
        log.error("Draft rejected by policy: risk=%.2f", risk)
        return None

    upsert_content_variant(
        variant["variant_id"], "bio",
        variant["headline"], variant["description"],
        hypothesis=variant["hypothesis"],
        status="draft"
    )
    write_receipt(
        "bio_draft_created_v1",
        "draft_bio_variant",
        {"current_headline": current_headline},
        variant,
        verified=True,
    )
    log.info("Bio draft created: %s", variant["variant_id"])
    return variant


def apply_bio_variant(api: RentMasseurAPI, variant_id: str) -> bool:
    """
    Apply a drafted bio variant. Enforces 24-hour cooldown and policy.
    """
    if not _can_change_bio():
        log.warning("Bio change blocked: within 24-hour cooldown")
        return False

    from .db import get_conn
    conn = get_conn()
    row = conn.execute("SELECT * FROM content_variants WHERE variant_id=?", (variant_id,)).fetchone()
    conn.close()
    if not row:
        log.error("Variant not found: %s", variant_id)
        return False

    variant = dict(row)

    about = api.get_about()
    assets = about.get("userProps", {}).get("assets", {})
    before = {
        "headline": assets.get("headline"),
        "description": assets.get("description"),
    }

    api.set_about(variant["headline"], variant["description"])

    # Verify
    about = api.get_about()
    assets = about.get("userProps", {}).get("assets", {})
    after = {
        "headline": assets.get("headline"),
        "description": assets.get("description"),
    }
    verified = (after["headline"] == variant["headline"] and after["description"] == variant["description"])

    # Mark old active as removed
    old = get_active_variant("bio")
    if old:
        set_variant_status(old["variant_id"], "archived", "removed_at")
    set_variant_status(variant_id, "active", "applied_at")

    # Start experiment
    baseline = get_latest_traffic_snapshot(1)
    baseline_views = baseline[0]["profile_views"] if baseline else 0
    baseline_clicks = baseline[0]["contact_clicks"] if baseline else 0
    start_experiment(f"exp_{variant_id}_{int(time.time())}", variant_id, baseline_views, baseline_clicks)

    write_receipt(
        "bio_applied_v1",
        "apply_bio_variant",
        before,
        after,
        verified=verified,
    )

    if verified:
        log.info("Bio applied: %s", variant_id)
    else:
        log.error("Bio apply verification failed: %s", variant_id)
    return verified


def evaluate_open_experiments(api: RentMasseurAPI) -> list:
    """End any open experiments that have run for 24+ hours."""
    results = []
    open_exps = get_open_experiments()
    now = time.time()
    for exp in open_exps:
        started = datetime.fromisoformat(exp["started_at"]).timestamp()
        if now - started < 24 * 60 * 60:
            continue
        current = get_latest_traffic_snapshot(1)
        final_views = current[0]["profile_views"] if current else 0
        final_clicks = current[0]["contact_clicks"] if current else 0
        delta_views = final_views - (exp["baseline_views"] or 0)
        delta_clicks = final_clicks - (exp["baseline_clicks"] or 0)
        result = {
            "experiment_id": exp["experiment_id"],
            "variant_id": exp["variant_id"],
            "delta_views": delta_views,
            "delta_clicks": delta_clicks,
            "baseline_views": exp["baseline_views"],
            "baseline_clicks": exp["baseline_clicks"],
            "final_views": final_views,
            "final_clicks": final_clicks,
        }
        end_experiment(exp["experiment_id"], final_views, final_clicks, result)
        results.append(result)
        log.info("Experiment ended: %s", result)
    return results


def run_daily_draft_cycle(api: RentMasseurAPI) -> dict:
    """Generate bio and headline drafts. Do not apply."""
    bio = draft_bio_variant(api)
    return {
        "bio_draft": bio,
        "experiments_evaluated": evaluate_open_experiments(api),
    }
