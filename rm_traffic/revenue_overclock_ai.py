"""
RM Revenue Overclock AI Layer — the proprietary AI control layer.

Sits above every RM module and decides what action is most likely to
increase real contact actions, calls, inquiries, and booked sessions.

Does NOT replace profileops.py, availability_keeper.py, service.py, or roi_algorithm.py.
It ORCHESTRATES them.

5 Engines:
  1. Traffic State Engine     — reads live RM metrics into TrafficState
  2. Revenue Pressure Engine  — scores how urgently the account needs action
  3. Action Selection Engine  — contextual bandit with ROA scoring
  4. Client Intent Engine     — local Ollama intent classifier
  5. Proof + ROI Engine       — tamper-evident receipts with metric deltas

CLI:
  python3 -m rm_traffic.revenue_overclock_ai --once --tenant <id>
  python3 -m rm_traffic.revenue_overclock_ai --daemon
  python3 -m rm_traffic.revenue_overclock_ai --report --tenant <id>
  python3 -m rm_traffic.revenue_overclock_ai --explain-last --tenant <id>
"""

import argparse
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

# .env loading
ENV_PATH = Path(__file__).parent.parent / ".env"
if ENV_PATH.exists():
    for line in open(ENV_PATH):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

from .api_client import RentMasseurAPI
from .state_engine import collect_state, TrafficState
from .action_bandit import select_action, record_outcome, ActionOutcome, explain_last_action, ACTIONS
from .intent_engine import classify_mailbox
from .reward_engine import compute_delta, compute_reward, delta_to_dict, is_measurement_valid
from .receipts import write_receipt, Receipt, get_recent_receipts, verify_chain

log = logging.getLogger("overclock_ai")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

# ─── Action executors ──────────────────────────────────────────────

def execute_action(action: str, api: RentMasseurAPI, state: TrafficState,
                   tenant_id: str = "") -> Dict:
    """Execute the selected action. Returns {error, result}."""
    result = {"error": "", "result": {}}

    try:
        if action == "refresh_availability":
            if state.available_status != "Available" or state.availability_seconds_left < 3600:
                api.set_availability(option=1, duration=5)
                api.invalidate_cache("availability")
                result["result"] = {"set_to": "Available", "duration": "6h"}
                log.info("  ◆ Set availability to Available (6h)")
            else:
                result["result"] = {"already_available": True}
                log.info("  ◉ Already available — no action needed")

        elif action == "ensure_visible":
            if state.profile_hidden:
                # Try to unhide via dashboard API
                try:
                    api._post("/account/dashboard/hide", {"hide": False})
                    result["result"] = {"unhid": True}
                    log.info("  ◆ Unhid profile")
                except Exception:
                    result["result"] = {"note": "visibility API not available — manual check needed"}
                    log.warning("  ⟁ Could not unhide profile via API")
            else:
                result["result"] = {"already_visible": True}

        elif action == "check_search_rank":
            results = api.search_masseurs(city="manhattan-ny", page=1)
            users = results.get("users", [])
            result["result"] = {"total_results": len(users), "rank": state.search_rank}

        elif action == "mailbox_intent_scan":
            mailbox = api.get_mailbox(page=1, folder=1, sort=1)
            emails = mailbox.get("emails", [])
            classified = classify_mailbox(emails)
            result["result"] = {
                "total": len(emails),
                "classified": len(classified),
                "booking_ready": sum(1 for c in classified if c["classification"] == "booking_now"),
                "high_value": sum(1 for c in classified if c["classification"] == "high_value_repeat"),
            }

        elif action == "reply_draft_queue":
            mailbox = api.get_mailbox(page=1, folder=1, sort=1)
            emails = mailbox.get("emails", [])
            from .reply_drafter import draft_mailbox_replies, format_drafts_summary
            phone = os.environ.get("RM_PHONE", "")
            ctx = {"rate": "$200", "phone": phone, "location": "Manhattan incall"}
            drafts = draft_mailbox_replies(emails, ctx)
            print(format_drafts_summary(drafts))
            result["result"] = {
                "drafts_queued": len([d for d in drafts if d.risk_level != "blocked"]),
                "blocked": len([d for d in drafts if d.risk_level == "blocked"]),
                "needs_approval": len([d for d in drafts if d.needs_human_approval]),
                "auto_ok": len([d for d in drafts if not d.needs_human_approval and d.risk_level != "blocked"]),
                "classifications": [d.intent_class for d in drafts if d.risk_level != "blocked"],
                "sample_draft": drafts[0].reply_text[:100] if drafts else "",
            }

        elif action == "visitor_revisit":
            from .visitor_revisit_engine import build_revisit_queue, write_revisit_queue, format_queue_summary
            queue = build_revisit_queue(api, state, tenant_id)
            filepath = write_revisit_queue(queue)
            print(format_queue_summary(queue))
            p0 = len([c for c in queue if c.urgency == "P0_revisit_now"])
            p1 = len([c for c in queue if c.urgency == "P1_reengage_today"])
            warm = len([c for c in queue if c.urgency == "WARM_observe"])
            ignored = len([c for c in queue if c.urgency == "IGNORE"])
            drafts_queued = len([c for c in queue if c.draft_text and c.approval_required])
            result["result"] = {
                "total_contacts": len(queue),
                "p0_revisit_now": p0,
                "p1_reengage_today": p1,
                "warm_observe": warm,
                "ignored": ignored,
                "drafts_queued": drafts_queued,
                "needs_approval": drafts_queued,
                "auto_ok": 0,  # all approval-gated
                "csv_path": filepath,
            }

        elif action == "city_rank_scan":
            results = api.search_masseurs(city="manhattan-ny", page=1)
            result["result"] = {"search_total": len(results.get("users", []))}

        elif action == "headline_variant_test":
            result["result"] = {"note": "headline test requires manual approval — draft only"}
            result["error"] = "manual_approval_required"

        elif action == "bio_variant_test":
            result["result"] = {"note": "bio test requires manual approval — draft only"}
            result["error"] = "manual_approval_required"

        elif action == "photo_order_test":
            result["result"] = {"note": "photo test requires manual approval — draft only"}
            result["error"] = "manual_approval_required"

        elif action == "rate_position_test":
            result["result"] = {"note": "rate test requires manual approval — draft only"}
            result["error"] = "manual_approval_required"

        elif action == "traffic_report":
            result["result"] = {"report_generated": True}

        elif action == "do_nothing":
            result["result"] = {"reason": "no high-value action available"}

        else:
            result["error"] = f"unknown action: {action}"

    except Exception as e:
        result["error"] = str(e)
        log.error(f"  ⟁ Action error: {e}")

    return result


# ─── Main cycle ────────────────────────────────────────────────────

def run_cycle(tenant_id: str = "", username: str = "", password: str = "") -> Dict:
    """Run one overclock cycle: state → pressure → bandit → execute → measure → receipt."""
    print(f"\n{'='*60}")
    print(f"  RM REVENUE OVERCLOCK AI — {tenant_id or 'default'}")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*60}\n")

    # Login
    api = RentMasseurAPI(min_request_interval=2.0)
    if not api.login(username, password):
        print("🔴 Login failed")
        return {"error": "login_failed", "tenant_id": tenant_id}

    print("[STATE] Collecting traffic state from verified endpoints...")

    # 1. Collect state BEFORE
    state_before = collect_state(api, tenant_id)
    print(f"  ◉ State hash: {state_before.state_hash}")
    print(f"  ◉ Revenue pressure: {state_before.revenue_pressure}")
    print(f"  ◉ Pressure components: {json.dumps(state_before.pressure_components)}")

    # 2. Select action via bandit
    print("\n[BANDIT] Selecting action via contextual bandit (ROA)...")
    action, roa_scores = select_action(state_before, tenant_id)

    # Show top 3 ROA scores
    sorted_roa = sorted(roa_scores.items(), key=lambda x: -x[1])[:5]
    for a, score in sorted_roa:
        marker = "◆" if a == action else " "
        print(f"  {marker} {a}: ROA={score:.3f}")

    print(f"\n  → Selected: {action}")

    # 3. Execute action
    print(f"\n[EXEC] Executing {action}...")
    exec_result = execute_action(action, api, state_before, tenant_id)
    error = exec_result.get("error", "")
    if error:
        print(f"  ⟁ Error: {error}")
    else:
        print(f"  ◉ Result: {json.dumps(exec_result.get('result', {}))}")

    # 4. Collect state AFTER
    print("\n[MEASURE] Collecting state after action...")
    time.sleep(2)  # brief pause for API to reflect changes
    api.invalidate_cache()  # clear all caches
    state_after = collect_state(api, tenant_id)
    print(f"  ◉ State hash: {state_after.state_hash}")
    if not state_after.measurement_valid:
        print(f"  ⟁ MEASUREMENT INVALID: {state_after.endpoint_error_count} endpoint errors")
        print(f"  ⟁ Errors: {state_after.endpoint_errors}")

    # 5. Compute reward
    print("\n[REWARD] Computing metric delta and reward...")
    measurement_valid = is_measurement_valid(state_before, state_after)
    delta = compute_delta(state_before, state_after)

    # For reply_draft_queue and visitor_revisit, pass action_result for draft-quality-based reward
    action_result = exec_result.get("result", {}) if action in ("reply_draft_queue", "visitor_revisit") else None
    reward = compute_reward(delta, action, error,
                             measurement_valid=measurement_valid,
                             action_result=action_result)
    print(f"  ◉ Delta: {json.dumps(delta_to_dict(delta))}")
    print(f"  ◉ Reward: {reward:.3f}")
    if not measurement_valid:
        print(f"  ⟁ MEASUREMENT INVALID — reward=0.0, bandit NOT updated")

    # 6. Record outcome for bandit learning (skip if measurement invalid)
    if measurement_valid:
        outcome = ActionOutcome(
            action=action,
            reward=reward,
            metric_delta=delta_to_dict(delta),
            state_before_hash=state_before.state_hash,
            state_after_hash=state_after.state_hash,
            error=error,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        record_outcome(outcome, tenant_id)
        print(f"  ◉ Recorded: {action} reward={reward:.3f}")
    else:
        print(f"  ⟁ SKIPPED bandit update — measurement invalid")

    # 7. Write tamper-evident receipt
    receipt_reason = f"ROA-selected: pressure={state_before.revenue_pressure:.3f}"
    if not measurement_valid:
        receipt_reason = f"measurement_invalid_after_snapshot_403: {state_after.endpoint_error_count} errors"

    receipt = Receipt(
        tenant_id=tenant_id,
        state_before_hash=state_before.state_hash,
        state_after_hash=state_after.state_hash,
        action=action,
        reason=receipt_reason,
        model_used="contextual_bandit_v1",
        metric_delta=delta_to_dict(delta),
        reward=reward,
        error=error if measurement_valid else "measurement_invalid",
        revenue_estimate=reward * 50.0,
    )
    receipt_hash = write_receipt(receipt)

    # Summary
    print(f"\n{'='*60}")
    print(f"  CYCLE COMPLETE")
    print(f"  Action: {action}")
    print(f"  Reward: {reward:.3f}")
    print(f"  Receipt: {receipt_hash}")
    print(f"  State: {state_before.state_hash} → {state_after.state_hash}")
    print(f"  Pressure: {state_before.revenue_pressure:.3f} → {state_after.revenue_pressure:.3f}")
    print(f"{'='*60}\n")

    return {
        "tenant_id": tenant_id,
        "action": action,
        "reward": reward,
        "receipt_hash": receipt_hash,
        "state_before": state_before.state_hash,
        "state_after": state_after.state_hash,
        "pressure_before": state_before.revenue_pressure,
        "pressure_after": state_after.revenue_pressure,
        "delta": delta_to_dict(delta),
        "error": error,
    }


def run_report(tenant_id: str = "") -> str:
    """Generate a text report of recent cycles."""
    receipts = get_recent_receipts(tenant_id, limit=20)
    chain_valid = verify_chain(tenant_id)

    lines = [
        f"RM Revenue Overclock AI — Report for {tenant_id or 'default'}",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        f"Receipt chain: {'✅ VALID' if chain_valid else '❌ TAMPERED'}",
        f"",
        f"Recent Actions ({len(receipts)}):",
        f"{'Time':<28} {'Action':<25} {'Reward':>8} {'Receipt':<10}",
        f"{'-'*28} {'-'*25} {'-'*8} {'-'*10}",
    ]

    for r in receipts:
        ts = r["timestamp"][:19]
        lines.append(f"{ts:<28} {r['action']:<25} {r['reward']:>8.3f} {r['receipt_hash']:<10}")

    # Action stats
    from .action_bandit import get_action_stats, _db as bandit_db
    stats = get_action_stats(bandit_db(), tenant_id)
    lines.append(f"\nAction Statistics:")
    lines.append(f"{'Action':<25} {'Runs':>5} {'Avg Reward':>10} {'Win Rate':>9} {'Confidence':>10}")
    lines.append(f"{'-'*25} {'-'*5} {'-'*10} {'-'*9} {'-'*10}")
    for action in ACTIONS:
        s = stats.get(action, {})
        if s.get("n", 0) > 0:
            lines.append(f"{action:<25} {s['n']:>5} {s['avg_reward']:>10.3f} {s['win_rate']:>9.1%} {s['confidence']:>10.3f}")

    report = "\n".join(lines)
    print(report)
    return report


# ─── CLI ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="RM Revenue Overclock AI Layer")
    parser.add_argument("--once", action="store_true", help="Run one cycle")
    parser.add_argument("--daemon", action="store_true", help="Run as daemon (continuous)")
    parser.add_argument("--report", action="store_true", help="Generate report")
    parser.add_argument("--explain-last", action="store_true", help="Explain last action")
    parser.add_argument("--tenant", default="", help="Tenant ID")
    parser.add_argument("--interval", type=int, default=300, help="Daemon interval (seconds)")
    args = parser.parse_args()

    username = os.environ.get("RENTMASSEUR_USER", os.environ.get("RM_USER", ""))
    password = os.environ.get("RENTMASSEUR_PASS", os.environ.get("RM_PASS", ""))

    tenant_id = args.tenant or hashlib.sha256(username.encode()).hexdigest()[:16]

    if args.report:
        run_report(tenant_id)
        return

    if args.explain_last:
        print(explain_last_action(tenant_id))
        return

    if args.once:
        result = run_cycle(tenant_id, username, password)
        if result.get("error") == "login_failed":
            sys.exit(2)
        sys.exit(0)

    if args.daemon:
        print(f"Starting daemon mode (interval={args.interval}s, tenant={tenant_id})")
        while True:
            try:
                run_cycle(tenant_id, username, password)
            except Exception as e:
                log.error(f"Cycle error: {e}")
            print(f"Sleeping {args.interval}s...")
            time.sleep(args.interval)

    parser.print_help()


if __name__ == "__main__":
    main()
