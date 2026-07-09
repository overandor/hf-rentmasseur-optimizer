"""
RM ProfileOps CLI — run modes and manage approved drafts.
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .db import init_db, get_variant_history, get_conn
from .api_client import RentMasseurAPI
from .auth import AuthSession, get_credential
from .content_optimizer import apply_bio_variant, draft_bio_variant
from .daemon import ProfileOpsDaemon
from .execution_engine import execute_visibility
from .state import snapshot_state, save_snapshot
from .approval_queue import approve_draft, list_pending, list_approved
from .endpoint_registry import seed_registry
from .cdp_discovery import run_discovery
from .search_rank import check_all_search_ranks
from .reports import generate_report, save_report, print_report
from .blog_agent import generate_blog_drafts, save_blog_drafts_to_disk
from .interview_agent import generate_interview_drafts, monitor_interview
from .bio_generator import run_generation
from .bio_evolver import run_evolution
from .stats_dashboard import generate_dashboard
from .bio_tokenizer import build_vocab, save_vocab, load_vocab, tokenize
from .bio_appraiser import full_appraisal
from .bio_ml_trainer import full_training_pipeline, k_fold_cv, walk_forward_validation

# AGI orchestrator
from rm_agi.orchestrator import RMAGIOrchestrator, CPPEngine, ReceiptLedger

# RM-PRI (Profile Revenue Intelligence)
from rm_agi.rm_pri import (
    validate_corpus as pri_validate_corpus,
    validate_enriched as pri_validate_enriched,
    enrich_bios as pri_enrich_bios,
    rank_by_views_per_day as pri_rank_views,
    atomize_bios as pri_atomize_bios,
    compute_lift as pri_compute_lift,
    ReceiptLedger as PRIReceiptLedger,
    RAW_PATH, ENRICHED_PATH, RANKED_PATH,
)

REQUIRED_FIELDS_CLI = ["id", "username", "city", "headline", "description",
                       "ratingAverage", "reviewsCount", "isGold", "isAvailable", "isCertified"]


def _api_login(args):
    api = RentMasseurAPI()
    auth = AuthSession(api, session_file=args.session)
    if not auth.login():
        print("Login failed")
        sys.exit(1)
    return api


def cmd_status(args):
    init_db()
    api = _api_login(args)
    state = snapshot_state(api)
    save_snapshot(state)
    keep = state.get("keeponline", {})
    avail = state.get("availability", {})
    about = state.get("about", {})
    assets = about.get("userProps", {}).get("assets", {})
    stats = state.get("stats", {}).get("profileStatistics", {})
    dashboard = state.get("dashboard", {})
    print(json.dumps({
        "timestamp": state["timestamp"],
        "visible": not bool(keep.get("isAdHidden", 0)),
        "available": avail.get("selected", "unknown"),
        "availability_minutes_left": max(0, int(avail.get("countdown", 0) - __import__('time').time()) // 60),
        "views": stats.get("totalPageViews"),
        "contact_clicks": stats.get("totalContactClicks"),
        "new_visits": keep.get("newVisits"),
        "new_emails": keep.get("newEmails"),
        "online_bookmarks": dashboard.get("onlineBookmarks"),
        "headline": assets.get("headline"),
        "description_len": len(assets.get("description", "")),
    }, indent=2, default=str))


def cmd_snapshot(args):
    init_db()
    api = _api_login(args)
    state = snapshot_state(api)
    path = save_snapshot(state)
    print(f"Snapshot saved: {path}")


def cmd_unhide(args):
    init_db()
    api = _api_login(args)
    result = execute_visibility(api, True)
    print(json.dumps(result, indent=2, default=str))


def cmd_draft_bio(args):
    init_db()
    api = _api_login(args)
    variant = draft_bio_variant(api)
    print(json.dumps(variant, indent=2, default=str))


def cmd_draft_blog(args):
    init_db()
    drafts = generate_blog_drafts(count=args.count)
    save_blog_drafts_to_disk(drafts)
    print(json.dumps(drafts, indent=2, default=str))


def cmd_draft_interview(args):
    init_db()
    api = _api_login(args)
    status = monitor_interview(api)
    drafts = generate_interview_drafts()
    print(json.dumps({"status": status, "drafts": drafts}, indent=2, default=str))


def cmd_generate_bios(args):
    init_db()
    ids = run_generation(count=args.count, top_n=args.top_n)
    print(f"Generated {len(ids)} bio variants")
    print("Top 3:")
    for vid in ids[:3]:
        print(f"  {vid}")


def cmd_evolve_bios(args):
    init_db()
    from .bio_generator import generate_bios
    initial = generate_bios(count=args.population, top_n=args.population)
    ids = run_evolution(initial_bios=initial, generations=args.generations,
                        population_size=args.population, elite_size=args.elites, top_n=args.elites)
    print(f"Evolution complete. Saved {len(ids)} elite variants.")
    print("Top 3:")
    for vid in ids[:3]:
        print(f"  {vid}")


def cmd_dashboard(args):
    init_db()
    path = generate_dashboard()
    print(f"Dashboard generated: {path}")


def cmd_tokenize(args):
    init_db()
    conn = get_conn()
    rows = conn.execute("SELECT headline, description FROM content_variants WHERE kind='bio'").fetchall()
    conn.close()
    bios = [{"headline": r[0], "description": r[1]} for r in rows]
    vocab = build_vocab(bios, min_freq=args.min_freq)
    path = Path("rm_traffic/data/models/vocab.json")
    save_vocab(vocab, path)
    print(f"Vocabulary: {vocab['unique_tokens']} unique tokens, {vocab['total_tokens']} total")
    print(f"Saved to: {path}")
    print("Top 20 tokens:")
    for token, freq in list(vocab["token_freq"].items())[:20]:
        print(f"  {token}: {freq}")


def cmd_approve(args):
    init_db()
    approve_draft(args.variant_id)
    print(f"Approved {args.variant_id}")


def cmd_apply(args):
    init_db()
    api = _api_login(args)
    ok = apply_bio_variant(api, args.variant_id)
    print("Applied" if ok else "Failed")


def cmd_list_drafts(args):
    init_db()
    if args.status == "pending":
        drafts = list_pending(args.kind)
    elif args.status == "approved":
        drafts = list_approved(args.kind)
    else:
        drafts = get_variant_history(args.kind, limit=args.limit)
    for d in drafts:
        print(f"{d['variant_id']} | {d['status']:18s} | {d['headline'][:50] if d['headline'] else 'N/A'}")


def cmd_discover(args):
    init_db()
    seed_registry()
    result = run_discovery(args.target)
    print(json.dumps(result, indent=2, default=str))


def cmd_rank_check(args):
    init_db()
    api = _api_login(args)
    ranks = check_all_search_ranks(api, args.username)
    print(json.dumps(ranks, indent=2, default=str))


def cmd_report(args):
    init_db()
    api = _api_login(args)
    state = snapshot_state(api)
    ranks = check_all_search_ranks(api, args.username)
    report = generate_report(args.username, state, ranks)
    path = save_report(report)
    print(report)
    print(f"\nReport saved: {path}")


# ─── AGI Commands ───

def cmd_agi_inspect(args):
    """Show real corpus stats from C++ engine."""
    engine = CPPEngine()
    bios = args.bios or "rm_traffic/data/real_bios.jsonl"
    print(engine.inspect(bios))

def cmd_agi_train(args):
    """Train model on real data using C++ engine."""
    engine = CPPEngine()
    bios = args.bios or "rm_traffic/data/real_bios.jsonl"
    print(engine.train(bios, label=args.label, cv=args.cv,
                       walk_forward=args.walk_forward, epochs=args.epochs,
                       lr=args.lr, hidden=args.hidden))

def cmd_agi_pipeline(args):
    """Run full AGI pipeline: train → generate → score → evolve → select."""
    agi = RMAGIOrchestrator()
    bios = args.bios or "rm_traffic/data/real_bios.jsonl"
    agi.run_pipeline(bios, count=args.count, label=args.label,
                     generations=args.generations, top=args.top)

def cmd_agi_import(args):
    """Import top candidates into approval queue."""
    agi = RMAGIOrchestrator()
    from pathlib import Path
    path = Path(args.path) if args.path else None
    count = agi.import_winners(path)
    print(f"Imported {count} candidates into approval queue")

def cmd_agi_list_drafts(args):
    """List AGI draft candidates."""
    agi = RMAGIOrchestrator()
    if args.status == "pending":
        drafts = agi.queue.list_pending()
    elif args.status == "approved":
        drafts = agi.queue.list_approved()
    else:
        drafts = agi.queue.list_pending() + agi.queue.list_approved()
    for d in drafts:
        rank = d.get("rank", "?")
        score = d.get("score", 0)
        risk = d.get("risk", 0)
        status = d.get("status", "?")
        headline = d.get("headline", "N/A")[:50]
        print(f"  #{rank} score={score:.4f} risk={risk:.4f} [{status}] {headline}")

def cmd_agi_approve(args):
    """Approve an AGI candidate."""
    agi = RMAGIOrchestrator()
    result = agi.approve(args.variant_id)
    if result:
        print(f"Approved: {result.get('headline', args.variant_id)}")
    else:
        print(f"Not found: {args.variant_id}")

def cmd_agi_receipts(args):
    """Show receipt ledger."""
    agi = RMAGIOrchestrator()
    print(agi.receipt_report())
    if args.verbose:
        for e in agi.ledger.entries[-10:]:
            print(f"  [{e['index']}] {e['action']}: {e['description']}")

def cmd_agi_experiments(args):
    """List experiment results."""
    agi = RMAGIOrchestrator()
    exps = agi.experiments.list_experiments()
    if not exps:
        print("No experiments yet.")
        return
    for e in exps[-10:]:
        label = e.get("result_label", "running")
        ctr_lift = e.get("ctr_lift", 0)
        print(f"  {e['experiment_id']} variant={e['variant_id']} result={label} ctr_lift={ctr_lift:.4f}")

def cmd_agi_dashboard(args):
    """Show AGI control panel."""
    agi = RMAGIOrchestrator()
    data = agi.dashboard_data()
    print("RENTMASSEUR AGI CONTROL PANEL")
    print("=" * 60)
    if "account" in data:
        acct = data["account"]
        print(f"ACCOUNT:")
        print(f"  Visible:      {acct.get('visible', '?')}")
        print(f"  Available:    {acct.get('is_available', '?')}")
        print(f"  Gold:         {acct.get('is_gold', '?')}")
        print(f"  Headline:     {acct.get('headline', '?')[:50]}")
        print(f"  Bio length:   {acct.get('description_len', '?')} chars")
        print(f"  Views:        {acct.get('profile_views', '?')}")
        print(f"  Contact clicks: {acct.get('contact_clicks', '?')}")
        print(f"  CTR:          {acct.get('contact_click_rate', 0):.4f}")
    print(f"\nCORPUS & MODEL:")
    print(f"  Pending drafts:  {data['pending_count']}")
    print(f"  Approved drafts: {data['approved_count']}")
    print(f"\nRECEIPTS:")
    r = data["receipts"]
    print(f"  Total: {r['total_receipts']}  Valid: {r['chain_valid']}  Last: {r['last_action']}")
    if data["experiments"]:
        print(f"\nRECENT EXPERIMENTS:")
        for e in data["experiments"]:
            print(f"  {e['experiment_id']} → {e.get('result_label', 'running')}")


# ─── RM-PRI Commands (honest naming) ───

def cmd_validate_corpus(args):
    """Gate 1: validate corpus schema."""
    path = Path(args.path) if args.path else RAW_PATH
    result = pri_validate_corpus(path)
    print(f"CORPUS VALIDATION: {path}")
    print(f"  Total rows:  {result['total']}")
    print(f"  Valid:       {result['valid']}")
    print(f"  Invalid:     {result['invalid']}")
    print(f"  PASS:        {result['pass']}")
    if result["errors"]:
        print(f"  Errors ({len(result['errors'])}):")
        for e in result["errors"][:5]:
            print(f"    {e}")
    print(f"\nField completeness:")
    for f in REQUIRED_FIELDS_CLI:
        p = result["fields_present"][f]
        t = result["total"]
        print(f"  {f:20s} {p}/{t} ({100*p/t:.1f}%)")

    if args.check_enriched:
        print(f"\nENRICHED VALIDATION:")
        er = pri_validate_enriched(ENRICHED_PATH)
        if "error" in er:
            print(f"  {er['error']}")
        else:
            print(f"  Total:              {er['total']}")
            print(f"  Has views_per_day:  {er['has_views_per_day']}")
            print(f"  Missing:            {er['missing_views_per_day']}")
            print(f"  PASS:               {er['pass']}")

def cmd_enrich_views(args):
    """Gate 2: enrich bios with public visits/member-since."""
    inp = Path(args.input) if args.input else RAW_PATH
    out = Path(args.output) if args.output else ENRICHED_PATH
    result = pri_enrich_bios(inp, out, workers=args.workers, rate_limit=args.rate_limit)
    print(f"\nENRICHMENT RESULT:")
    print(f"  Total:    {result['total']}")
    print(f"  Enriched: {result['enriched']}")
    print(f"  Failed:   {result['failed']}")
    if result.get("captcha"):
        print(f"  BLOCKED:  CrowdSec captcha active")
        print(f"  Next:     Wait for ban to clear, then re-run this command")
    else:
        print(f"  Output:   {out}")

def cmd_rank_real(args):
    """Rank real bios by views_per_day."""
    inp = Path(args.input) if args.input else ENRICHED_PATH
    out = Path(args.output) if args.output else RANKED_PATH
    result = pri_rank_views(inp, out)
    if "error" in result:
        print(f"ERROR: {result['error']}")
    else:
        print(f"Ranked {result['ranked_bios']}/{result['total_bios']} bios by views/day")
        print(f"Output: {result['output']}")
        if result.get("top_5"):
            print(f"\nTop 5 by views/day:")
            for i, b in enumerate(result["top_5"], 1):
                print(f"  #{i} {b['username']} — {b['views_per_day']:.1f} v/day — {b['headline'][:50]}")

def cmd_atomize_bios(args):
    """Extract structural atoms from bios."""
    inp = Path(args.input) if args.input else RAW_PATH
    out = Path(args.output) if args.output else Path("rm_traffic/data/bio_atoms.jsonl")
    result = pri_atomize_bios(inp, out)
    print(f"Atomized {result['atomized']} bios")
    print(f"Output: {result['output']}")

def cmd_pri_status(args):
    """Show honest system status — what stage we're at."""
    print("RM-PRI STATUS — RentMasseur Profile Revenue Intelligence")
    print("=" * 60)

    # Stage 1: corpus
    v = pri_validate_corpus(RAW_PATH)
    print(f"\nStage 1: Real Corpus")
    print(f"  Rows: {v['total']}  Valid: {v['valid']}  PASS: {v['pass']}")

    # Stage 2: enrichment
    e = pri_validate_enriched(ENRICHED_PATH)
    print(f"\nStage 2: Views/Day Enrichment")
    if "error" in e:
        print(f"  STATUS: NOT STARTED — {e['error']}")
        print(f"  BLOCKER: CrowdSec captcha on rentmasseur.com")
        print(f"  NEXT: Run 'enrich-views' when ban clears")
    else:
        print(f"  Total: {e['total']}  Has v/day: {e['has_views_per_day']}  PASS: {e['pass']}")

    # Stage 3: dashboard
    print(f"\nStage 3: Dashboard Time Series")
    print(f"  STATUS: NOT STARTED — requires API access")
    print(f"  NEXT: Run 'snapshot' when API is accessible")

    # Stage 4: experiments
    print(f"\nStage 4: Live Experiment Labels")
    print(f"  STATUS: NOT STARTED — requires approved variant + apply + measure")

    # Stage 5: online learning
    print(f"\nStage 5: Validated Online Learner")
    print(f"  STATUS: NOT STARTED — requires stages 2-4")

    # Receipts
    ledger = PRIReceiptLedger()
    s = ledger.summary()
    print(f"\nReceipts: {s['total']} total, chain valid: {s['valid']}")

    print(f"\nHONEST ASSESSMENT:")
    print(f"  This is Stage 1: real corpus loaded.")
    print(f"  Not AGI. Not revenue oracle. Not CTR predictor.")
    print(f"  It is a real market corpus + language analysis foundation.")
    print(f"  Next real step: enrich with public visits/member-since.")


def cmd_audit(args):
    init_db()
    seed_registry()
    d = ProfileOpsDaemon(mode="audit", city=args.city, session_file=args.session)
    d.run()


def cmd_guard(args):
    init_db()
    seed_registry()
    d = ProfileOpsDaemon(mode="guard", city=args.city, session_file=args.session)
    d.run()


def cmd_draft(args):
    init_db()
    seed_registry()
    d = ProfileOpsDaemon(mode="draft", city=args.city, session_file=args.session)
    d.run()


def cmd_daemon(args):
    init_db()
    seed_registry()
    mode = "execute" if args.execute_approved else "safe"
    d = ProfileOpsDaemon(mode=mode, city=args.city, session_file=args.session)
    d.run()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    parser = argparse.ArgumentParser(description="RM ProfileOps CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("status", help="Read-only profile status")
    p.add_argument("--city", default="manhattan-ny")
    p.add_argument("--session", default="rm_traffic/session.json")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("snapshot", help="Save profile state snapshot")
    p.add_argument("--session", default="rm_traffic/session.json")
    p.set_defaults(func=cmd_snapshot)

    p = sub.add_parser("unhide", help="Ensure profile is visible")
    p.add_argument("--session", default="rm_traffic/session.json")
    p.set_defaults(func=cmd_unhide)

    p = sub.add_parser("draft-bio", help="Generate a bio draft")
    p.add_argument("--session", default="rm_traffic/session.json")
    p.set_defaults(func=cmd_draft_bio)

    p = sub.add_parser("draft-blog", help="Generate blog drafts")
    p.add_argument("--count", type=int, default=1)
    p.set_defaults(func=cmd_draft_blog)

    p = sub.add_parser("draft-interview", help="Generate interview drafts")
    p.add_argument("--session", default="rm_traffic/session.json")
    p.set_defaults(func=cmd_draft_interview)

    p = sub.add_parser("generate-bios", help="Generate many bio variants with scoring")
    p.add_argument("--count", type=int, default=1000)
    p.add_argument("--top-n", type=int, default=100)
    p.set_defaults(func=cmd_generate_bios)

    p = sub.add_parser("evolve-bios", help="Run GA to optimize bios for CTR/email/phone")
    p.add_argument("--population", type=int, default=100)
    p.add_argument("--generations", type=int, default=50)
    p.add_argument("--elites", type=int, default=10)
    p.set_defaults(func=cmd_evolve_bios)

    p = sub.add_parser("dashboard", help="Generate HTML stats dashboard")
    p.set_defaults(func=cmd_dashboard)

    p = sub.add_parser("tokenize", help="Build vocabulary from all bio drafts")
    p.add_argument("--min-freq", type=int, default=2)
    p.set_defaults(func=cmd_tokenize)

    p = sub.add_parser("approve", help="Approve a draft variant")
    p.add_argument("variant_id")
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("apply", help="Apply an approved bio variant")
    p.add_argument("variant_id")
    p.add_argument("--session", default="rm_traffic/session.json")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("list-drafts", help="List content drafts")
    p.add_argument("--kind", default="bio")
    p.add_argument("--status", choices=["all", "pending", "approved"], default="all")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(func=cmd_list_drafts)

    p = sub.add_parser("discover", help="Discover an endpoint via CDP")
    p.add_argument("target", choices=["availability", "blog", "interview"])
    p.set_defaults(func=cmd_discover)

    p = sub.add_parser("rank-check", help="Check search rank")
    p.add_argument("username")
    p.add_argument("--city", default="manhattan-ny")
    p.add_argument("--session", default="rm_traffic/session.json")
    p.set_defaults(func=cmd_rank_check)

    p = sub.add_parser("report", help="Generate daily report")
    p.add_argument("username")
    p.add_argument("--city", default="manhattan-ny")
    p.add_argument("--session", default="rm_traffic/session.json")
    p.set_defaults(func=cmd_report)

    for mode in ["audit", "guard", "draft"]:
        p = sub.add_parser(mode, help=f"Run {mode} mode")
        p.add_argument("--city", default="manhattan-ny")
        p.add_argument("--session", default="rm_traffic/session.json")
        p.set_defaults(func=globals()[f"cmd_{mode}"])

    p = sub.add_parser("daemon", help="Run daemon")
    p.add_argument("--city", default="manhattan-ny")
    p.add_argument("--session", default="rm_traffic/session.json")
    p.add_argument("--execute-approved", action="store_true", help="Auto-apply approved bio changes")
    p.set_defaults(func=cmd_daemon)

    # ─── AGI Commands ───

    p = sub.add_parser("agi-inspect", help="Show real corpus stats via C++ engine")
    p.add_argument("--bios", default=None, help="Path to real_bios.jsonl")
    p.set_defaults(func=cmd_agi_inspect)

    p = sub.add_parser("agi-train", help="Train model on real data via C++ engine")
    p.add_argument("--bios", default=None)
    p.add_argument("--label", default="reviews", choices=["reviews", "views_per_day", "rating"])
    p.add_argument("--cv", type=int, default=5)
    p.add_argument("--walk-forward", action="store_true")
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--lr", type=float, default=0.001)
    p.add_argument("--hidden", type=int, default=64)
    p.set_defaults(func=cmd_agi_train)

    p = sub.add_parser("agi-pipeline", help="Run full AGI pipeline (train→generate→score→evolve→select)")
    p.add_argument("--bios", default=None)
    p.add_argument("--count", type=int, default=100000)
    p.add_argument("--label", default="reviews")
    p.add_argument("--generations", type=int, default=100)
    p.add_argument("--top", type=int, default=25)
    p.set_defaults(func=cmd_agi_pipeline)

    p = sub.add_parser("agi-import", help="Import top candidates into approval queue")
    p.add_argument("--path", default=None)
    p.set_defaults(func=cmd_agi_import)

    p = sub.add_parser("agi-drafts", help="List AGI draft candidates")
    p.add_argument("--status", choices=["all", "pending", "approved"], default="all")
    p.set_defaults(func=cmd_agi_list_drafts)

    p = sub.add_parser("agi-approve", help="Approve an AGI candidate")
    p.add_argument("variant_id")
    p.set_defaults(func=cmd_agi_approve)

    p = sub.add_parser("agi-receipts", help="Show receipt ledger")
    p.add_argument("--verbose", action="store_true")
    p.set_defaults(func=cmd_agi_receipts)

    p = sub.add_parser("agi-experiments", help="List experiment results")
    p.set_defaults(func=cmd_agi_experiments)

    p = sub.add_parser("agi-dashboard", help="Show AGI control panel")
    p.set_defaults(func=cmd_agi_dashboard)

    # ─── RM-PRI Commands (honest naming) ───

    p = sub.add_parser("validate-corpus", help="Gate 1: validate corpus schema")
    p.add_argument("path", nargs="?", default=None)
    p.add_argument("--check-enriched", action="store_true")
    p.set_defaults(func=cmd_validate_corpus)

    p = sub.add_parser("enrich-views", help="Gate 2: enrich bios with public visits/member-since")
    p.add_argument("--input", default=None)
    p.add_argument("--output", default=None)
    p.add_argument("--workers", type=int, default=16)
    p.add_argument("--rate-limit", type=float, default=0.5)
    p.set_defaults(func=cmd_enrich_views)

    p = sub.add_parser("rank-real", help="Rank real bios by views_per_day")
    p.add_argument("--input", default=None)
    p.add_argument("--output", default=None)
    p.add_argument("--metric", default="views_per_day")
    p.set_defaults(func=cmd_rank_real)

    p = sub.add_parser("atomize-bios", help="Extract structural atoms from bios")
    p.add_argument("--input", default=None)
    p.add_argument("--output", default=None)
    p.set_defaults(func=cmd_atomize_bios)

    p = sub.add_parser("pri-status", help="Show honest RM-PRI system status")
    p.set_defaults(func=cmd_pri_status)

    args = parser.parse_args()

    # Credentials check for commands that need them
    if args.command in ("status", "snapshot", "unhide", "draft-bio", "apply", "audit", "guard", "draft", "daemon", "rank-check", "report"):
        if not get_credential("RM_USER") or not get_credential("RM_PASS"):
            print("Set RM_USER and RM_PASS environment variables first.")
            print("Do not hardcode credentials.")
            sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
