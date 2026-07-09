#!/usr/bin/env python3
"""
Investigation YouTube OS — Command-line interface.

System-wide commands (after `pip install .`):

    broll investigate "Does Schumann resonance have measurable properties?" \\
        --out investigation_packet \\
        --export-b64

    broll verify asset_packet.b64

    broll info investigation_packet/

    broll channel create "Resonance Research"
    broll channel episode "Can ancient stone structures exhibit resonance?"
    broll channel publish <episode_id>
    broll channel list
    broll channel feed
    broll channel search "resonance"
    broll channel analytics
    broll channel machine-query --min-buyability 0.5
    broll channel serve --port 8000
    broll channel export --out channel_export.json
"""

import argparse
import json
import sys
import os

from .videolake import VideoLakeCompiler
from .youtube_os import InvestigationYouTubeOS, EpisodeStatus, create_youtube_os_api


def cmd_rights(args):
    """Inspect a Fractional Revenue Video Object (FRVO)."""
    import json as _json
    import os

    if not os.path.exists(args.frvo_path):
        print(f"Error: {args.frvo_path} not found")
        return

    with open(args.frvo_path) as f:
        frvo_data = _json.load(f)

    print(f"VideoRights OS — FRVO Inspection")
    print(f"FRVO ID: {frvo_data.get('frvo_id', '?')}")
    print(f"Project: {frvo_data.get('project_name', '?')}")
    print(f"Mode: {frvo_data.get('offering_mode', '?')}")
    print(f"Status: {frvo_data.get('offering_status', '?')}")
    print(f"Copyright Owner: {frvo_data.get('copyright_owner', '?')}")
    print(f"Units: {frvo_data.get('units_issued', 0)}/{frvo_data.get('fractional_units', 0)} issued")
    print(f"Backers: {len(frvo_data.get('backers', []))}")
    print(f"VRRUs: {len(frvo_data.get('vrrus', []))}")
    print(f"Revenue Sources: {len(frvo_data.get('revenue_sources', []))}")
    print(f"Risk Disclosures: {len(frvo_data.get('risk_disclosures', []))}")
    print(f"Ledger Entries: {len(frvo_data.get('ledger', []))}")
    print()

    if args.inspect:
        from .rights_vault import RightsVault, FRVO, OfferingMode, OfferingStatus
        vault = RightsVault()
        frvo = FRVO(
            frvo_id=frvo_data["frvo_id"],
            video_id=frvo_data.get("video_id", ""),
            project_name=frvo_data.get("project_name", ""),
            copyright_owner=frvo_data.get("copyright_owner", ""),
            offering_mode=OfferingMode(frvo_data.get("offering_mode", "PERK_ONLY")),
            offering_status=OfferingStatus(frvo_data.get("offering_status", "DRAFT")),
            machine_bid_packet=frvo_data.get("machine_bid_packet", {}),
            rights_metadata=frvo_data.get("rights_metadata", []),
        )
        inspection = vault.machine_inspect(frvo)
        print("Machine Inspection:")
        for k, v in inspection.items():
            if k != "schema":
                print(f"  {k}: {v}")

    if args.proof:
        from .rights_vault import RightsVault, FRVO, OfferingMode, OfferingStatus
        vault = RightsVault()
        frvo = FRVO(
            frvo_id=frvo_data["frvo_id"],
            video_id=frvo_data.get("video_id", ""),
            project_name=frvo_data.get("project_name", ""),
            copyright_owner=frvo_data.get("copyright_owner", ""),
            offering_mode=OfferingMode(frvo_data.get("offering_mode", "PERK_ONLY")),
            offering_status=OfferingStatus(frvo_data.get("offering_status", "DRAFT")),
            machine_bid_packet=frvo_data.get("machine_bid_packet", {}),
            rights_metadata=frvo_data.get("rights_metadata", []),
        )
        proof = vault.generate_proof_packet(frvo)
        print("\nProof Packet:")
        for k, v in proof.items():
            if k not in ("schema",):
                print(f"  {k}: {v}")

    if args.simulate is not None:
        from .rights_vault import RightsVault, PayoutSimulator, FRVO, OfferingMode, OfferingStatus, RevenueSource, PayoutWaterfallTier, Backer, BackerType
        _rs_fields = {"source_id", "source_type", "description", "gross_revenue_usd", "platform_fee_pct", "direct_cost_usd"}
        _pw_fields = {"tier", "name", "recipient", "share_pct", "cap_usd", "description"}
        frvo = FRVO(
            frvo_id=frvo_data["frvo_id"],
            video_id=frvo_data.get("video_id", ""),
            project_name=frvo_data.get("project_name", ""),
            copyright_owner=frvo_data.get("copyright_owner", ""),
            offering_mode=OfferingMode(frvo_data.get("offering_mode", "PERK_ONLY")),
            offering_status=OfferingStatus(frvo_data.get("offering_status", "DRAFT")),
            fractional_units=frvo_data.get("fractional_units", 1_000_000),
            units_issued=frvo_data.get("units_issued", 0),
            revenue_sources=[RevenueSource(**{k: v for k, v in rs.items() if k in _rs_fields}) for rs in frvo_data.get("revenue_sources", [])],
            payout_waterfall=[PayoutWaterfallTier(**{k: v for k, v in pw.items() if k in _pw_fields}) for pw in frvo_data.get("payout_waterfall", [])],
            backers=[Backer(
                backer_id=b["backer_id"],
                backer_type=BackerType(b["backer_type"]),
                amount_usd=b["amount_usd"],
                units=b["units"],
            ) for b in frvo_data.get("backers", [])],
        )
        payout = PayoutSimulator.simulate(frvo, args.simulate)
        print(f"\nPayout Simulation (${args.simulate:,.2f} gross):")
        print(f"  Net revenue: ${payout.total_net:,.2f}")
        print(f"  Creator: ${payout.creator_payout:,.2f}")
        print(f"  Platform: ${payout.platform_fee:,.2f}")
        print(f"  Reserve: ${payout.reserve:,.2f}")
        print(f"  Backers paid: {len(payout.backer_payouts)}")
        for bp in payout.backer_payouts:
            print(f"    {bp['backer_id']}: ${bp['payout_usd']:,.2f} ({bp['units']} units, {bp['share_pct']:.2f}%)")
        print(f"  Receipt: {payout.receipt_hash}")


def cmd_investigate(args):
    """Run a full investigation and compile into a research media packet."""
    compiler = VideoLakeCompiler()

    print(f"VideoLake Compiler — Research-to-Asset")
    print(f"Question: {args.question}")
    print(f"Output: {args.out or '(in-memory)'}")
    print()

    result = compiler.compile(
        question=args.question,
        output_dir=args.out,
        compile_video=not args.no_video,
        write_receipts=not args.no_receipts,
        export_b64=args.export_b64,
        pack_mcrv=getattr(args, "mcrv", False),
        render_all=getattr(args, "render_all", False),
        create_frvo=getattr(args, "frvo", False),
        offering_mode=__import__("broll.rights_vault", fromlist=["OfferingMode"]).OfferingMode(
            getattr(args, "offering_mode", "PERK_ONLY")
        ),
    )

    summary = result.summary()
    print(f"Investigation ID: {summary['investigation_id']}")
    print(f"Claims: {summary['claims']}")
    print(f"Papers: {summary['papers']}")
    print(f"Segments: {summary['segments']}")
    print(f"Trust grade: {summary['trust_grade']}")
    print(f"Avg buyability: {summary['avg_buyability']}")
    print(f"Total price: ${summary['total_price_usd']:.2f}")
    print(f"Files: {summary['files']}")
    print(f"Total size: {summary['total_size_bytes']:,} bytes")
    print(f"Scenes: {summary['scene_count']}")
    print()

    print(f"Files generated:")
    for f in result.files:
        size = len(result.bundle[f])
        print(f"  {f:40s} {size:>8,} bytes")
    print()

    if args.export_b64:
        print(f"Base64 packet: {len(result.base64_packet):,} chars")
        print(f"Packet hash: {result.receipt_hash}")

    if args.out:
        print(f"\nWritten to: {args.out}/")
        if args.export_b64:
            print(f"Base64 packet: {args.out}/asset_packet.b64")

    # Print claims summary
    if result.investigation:
        print(f"\nClaims:")
        for claim in result.investigation.claims:
            status_icon = {
                "verified": "[V]",
                "replicated": "[R]",
                "partially_replicated": "[P]",
                "disputed": "[D]",
                "speculative": "[S]",
                "unverified": "[U]",
                "retracted": "[X]",
            }.get(claim.status.value, "[?]")
            print(f"  {status_icon} {claim.claim_text[:70]}...")
            print(f"      confidence: {claim.confidence:.2f}, supporting: {len(claim.supporting_papers)}, counter: {len(claim.counter_papers)}")

    print(f"\nReceipt: {result.receipt_hash}")
    print("Done.")


def cmd_verify(args):
    """Verify a Base64 asset packet."""
    with open(args.packet, "r") as f:
        b64_content = f.read()

    compiler = VideoLakeCompiler()
    result = compiler.verify_packet(b64_content)

    if result["valid"]:
        print(f"Packet: VALID")
        print(f"Type: {result['packet_type']}")
        print(f"Files: {result['file_count']}")
        print(f"Timestamp: {result['timestamp']}")
        print(f"File list:")
        for f in result["files"]:
            print(f"  {f}")
    else:
        print(f"Packet: INVALID")
        print(f"Error: {result.get('error', 'unknown')}")
        if "stored" in result:
            print(f"Stored hash: {result['stored']}")
            print(f"Computed hash: {result['computed']}")
        sys.exit(1)


def cmd_info(args):
    """Show info about a VideoLake output directory."""
    dirpath = args.directory
    if not os.path.isdir(dirpath):
        print(f"Error: {dirpath} is not a directory")
        sys.exit(1)

    manifest_path = os.path.join(dirpath, "manifest.json")
    if not os.path.exists(manifest_path):
        print(f"Error: No manifest.json in {dirpath}")
        sys.exit(1)

    with open(manifest_path) as f:
        manifest = json.load(f)

    print(f"VideoLake Packet Info")
    print(f"=" * 60)
    print(f"Asset type: {manifest.get('asset_type', 'unknown')}")
    print(f"VRAP ID: {manifest.get('vrap_id', 'unknown')}")
    print(f"Title: {manifest.get('title', 'unknown')}")
    print(f"Question: {manifest.get('question', 'unknown')}")
    print(f"Trust grade: {manifest.get('trust_grade', 'unknown')}")
    print(f"Avg buyability: {manifest.get('avg_machine_buyability', 0):.3f}")
    print(f"Total price: ${manifest.get('total_price_usd', 0):.2f}")
    print(f"Claims: {manifest.get('claim_count', 0)}")
    print(f"Segments: {manifest.get('segment_count', 0)}")
    print()

    print(f"Files:")
    files = manifest.get("files", {})
    for filename, description in files.items():
        filepath = os.path.join(dirpath, filename)
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            print(f"  {filename:40s} {size:>8,} bytes  {description}")
        else:
            print(f"  {filename:40s}   MISSING  {description}")
    print()

    # Check for base64 packet
    b64_path = os.path.join(dirpath, "asset_packet.b64")
    if os.path.exists(b64_path):
        size = os.path.getsize(b64_path)
        print(f"Base64 packet: {size:,} bytes")

    print(f"\nReceipt: {manifest.get('receipt_hash', 'unknown')}")


# ── Channel State Persistence ───────────────────────────────────

_CHANNEL_DIR = os.path.expanduser("~/.broll")
_CHANNEL_FILE = os.path.join(_CHANNEL_DIR, "channel_state.json")


def _save_channel(os_sys: InvestigationYouTubeOS) -> None:
    """Persist channel state to ~/.broll/channel_state.json."""
    os.makedirs(_CHANNEL_DIR, exist_ok=True)
    export = os_sys.export_channel()
    with open(_CHANNEL_FILE, "w") as f:
        json.dump(export, f, indent=2)


def _load_channel() -> InvestigationYouTubeOS:
    """Load channel state from ~/.broll/channel_state.json."""
    if not os.path.exists(_CHANNEL_FILE):
        return InvestigationYouTubeOS(channel_name="Default Channel")
    with open(_CHANNEL_FILE) as f:
        data = json.load(f)
    manifest = data.get("manifest", {})
    os_sys = InvestigationYouTubeOS(
        channel_name=manifest.get("channel_name", "Default Channel"),
        channel_id=manifest.get("channel_id", ""),
    )
    # Restore episodes from saved metadata
    for ep_data in data.get("episodes", []):
        from .youtube_os import Episode
        ep = Episode(
            episode_id=ep_data["episode_id"],
            title=ep_data["title"],
            question=ep_data["question"],
            status=EpisodeStatus(ep_data["status"]),
            topic_tags=ep_data.get("topic_tags", []),
            created_at=ep_data.get("created_at", 0),
            compiled_at=ep_data.get("compiled_at", 0),
            published_at=ep_data.get("published_at", 0),
            duration_seconds=ep_data.get("duration_seconds", 0),
            trust_grade=ep_data.get("trust_grade", ""),
            avg_buyability=ep_data.get("avg_buyability", 0),
            claim_count=ep_data.get("claim_count", 0),
            segment_count=ep_data.get("segment_count", 0),
            paper_count=ep_data.get("paper_count", 0),
            total_price_usd=ep_data.get("total_price_usd", 0),
            receipt_hash=ep_data.get("receipt_hash", ""),
            scene_count=ep_data.get("scene_count", 0),
            description=ep_data.get("description", ""),
            view_count=ep_data.get("view_count", 0),
            machine_queries=ep_data.get("machine_queries", 0),
        )
        os_sys._episodes[ep.episode_id] = ep
    # Restore playlists
    for pl_data in data.get("playlists", []):
        from .youtube_os import Playlist
        pl = Playlist(
            playlist_id=pl_data["playlist_id"],
            title=pl_data["title"],
            description=pl_data.get("description", ""),
            episode_ids=pl_data.get("episode_ids", []),
            created_at=pl_data.get("created_at", 0),
            curator=pl_data.get("curator", ""),
        )
        os_sys._playlists[pl.playlist_id] = pl
    # Restore receipts
    os_sys._receipt_chain = data.get("receipts", [])
    return os_sys


# ── Channel Commands ────────────────────────────────────────────

def cmd_channel(args):
    """Channel subcommands."""
    sub = args.channel_command

    if sub == "create":
        os_sys = InvestigationYouTubeOS(channel_name=args.name)
        _save_channel(os_sys)
        manifest = os_sys.channel_manifest()
        print(f"Channel created: {manifest['channel_name']}")
        print(f"Channel ID: {manifest['channel_id']}")
        print(f"State saved: {_CHANNEL_FILE}")

    elif sub == "episode":
        os_sys = _load_channel()
        ep = os_sys.create_episode(
            question=args.question,
            title=args.title or "",
            topic_tags=args.tags.split(",") if args.tags else [],
        )
        print(f"Episode created: {ep.episode_id}")
        print(f"  Question: {ep.question}")
        print(f"  Status: {ep.status.value}")

        if args.compile:
            print("  Compiling...")
            ep = os_sys.compile_episode(ep.episode_id)
            print(f"  Compiled: {ep.claim_count} claims, {ep.segment_count} segments, grade: {ep.trust_grade}")
            print(f"  Buyability: {ep.avg_buyability:.3f}")
            print(f"  Price: ${ep.total_price_usd:.2f}")
            print(f"  Receipt: {ep.receipt_hash}")

            if args.out:
                import pathlib
                out_dir = pathlib.Path(args.out) / ep.episode_id
                out_dir.mkdir(parents=True, exist_ok=True)
                for filename, content in ep.bundle.items():
                    (out_dir / filename).write_text(content)
                (out_dir / "asset_packet.b64").write_text(ep.base64_packet)
                print(f"  Bundle written: {out_dir}")

            if args.publish:
                ep = os_sys.publish_episode(ep.episode_id)
                print(f"  Published: {ep.status.value}")

        _save_channel(os_sys)
        print(f"  State saved: {_CHANNEL_FILE}")

    elif sub == "publish":
        os_sys = _load_channel()
        ep = os_sys.publish_episode(args.episode_id)
        print(f"Published: {ep.episode_id}")
        print(f"  Title: {ep.title}")
        print(f"  Status: {ep.status.value}")
        _save_channel(os_sys)

    elif sub == "archive":
        os_sys = _load_channel()
        ep = os_sys.archive_episode(args.episode_id)
        print(f"Archived: {ep.episode_id}")
        _save_channel(os_sys)

    elif sub == "list":
        os_sys = _load_channel()
        status_filter = None
        if args.status:
            status_filter = EpisodeStatus(args.status)
        episodes = os_sys.list_episodes(status=status_filter, topic=args.topic, limit=args.limit or 50)
        if not episodes:
            print("No episodes found.")
            return
        print(f"{'ID':<20} {'Status':<12} {'Grade':<6} {'Claims':<8} {'Title'}")
        print("-" * 80)
        for ep in episodes:
            print(f"{ep.episode_id:<20} {ep.status.value:<12} {ep.trust_grade or '-':<6} {ep.claim_count:<8} {ep.title[:40]}")

    elif sub == "feed":
        os_sys = _load_channel()
        feed = os_sys.feed(limit=args.limit or 20)
        print(f"Feed: {feed['channel_name']}")
        print(f"Episodes: {feed['episode_count']}")
        print()
        for ep in feed["episodes"]:
            print(f"  [{ep['grade']}] {ep['title'][:50]}")
            print(f"    id={ep['id']}  buyability={ep['buyability']}  price=${ep['price']}  duration={ep['duration']}s")

    elif sub == "search":
        os_sys = _load_channel()
        results = os_sys.search(args.query, limit=args.limit or 20)
        print(f"Search '{args.query}': {len(results)} results")
        for r in results:
            ep = r["episode"]
            print(f"  [{ep['grade']}] {ep['title'][:50]} (score: {r['relevance_score']})")

    elif sub == "analytics":
        os_sys = _load_channel()
        analytics = os_sys.analytics()
        print(f"Channel Analytics")
        print(f"=" * 50)
        print(f"Total episodes:     {analytics.total_episodes}")
        print(f"Published:          {analytics.published_episodes}")
        print(f"Draft:              {analytics.draft_episodes}")
        print(f"Compiled:           {analytics.compiled_episodes}")
        print(f"Archived:           {analytics.archived_episodes}")
        print(f"Total claims:       {analytics.total_claims}")
        print(f"Total papers:       {analytics.total_papers}")
        print(f"Total segments:     {analytics.total_segments}")
        print(f"Total duration:     {analytics.total_duration_seconds:.1f}s")
        print(f"Total price:        ${analytics.total_price_usd:.2f}")
        print(f"Avg buyability:     {analytics.avg_buyability:.3f}")
        print(f"Total views:        {analytics.total_views}")
        print(f"Machine queries:    {analytics.total_machine_queries}")
        print(f"Playlists:          {analytics.total_playlists}")
        print(f"Subscriptions:      {analytics.total_subscriptions}")
        print(f"Grade distribution: {analytics.grade_distribution}")
        print(f"Topic distribution: {analytics.topic_distribution}")
        print(f"Receipts verified:  {analytics.receipt_chain_verified}")

    elif sub == "machine-query":
        os_sys = _load_channel()
        results = os_sys.machine_query(
            topic=args.topic,
            min_buyability=args.min_buyability or 0.0,
            min_trust_grade=args.min_grade or "F",
            rights_status=args.rights,
            for_sale_only=args.for_sale_only,
            limit=args.limit or 20,
        )
        print(f"Machine query: {len(results)} segments")
        for r in results:
            print(f"  [{r['trust_grade']}] {r['claim'][:50]}...")
            print(f"    episode={r['episode_id']}  buyability={r['buyability']:.3f}  rights={r['rights']}  price=${r['price']}")

    elif sub == "playlist":
        os_sys = _load_channel()
        if args.playlist_action == "create":
            pl = os_sys.create_playlist(
                title=args.playlist_title,
                description=args.playlist_desc or "",
                episode_ids=args.episode_ids.split(",") if args.episode_ids else [],
            )
            print(f"Playlist created: {pl.playlist_id}")
            print(f"  Title: {pl.title}")
            print(f"  Episodes: {len(pl.episode_ids)}")
            _save_channel(os_sys)
        elif args.playlist_action == "list":
            playlists = os_sys.list_playlists()
            print(f"Playlists: {len(playlists)}")
            for pl in playlists:
                print(f"  {pl.playlist_id}: {pl.title} ({len(pl.episode_ids)} episodes)")

    elif sub == "subscribe":
        os_sys = _load_channel()
        sub = os_sys.subscribe(topic=args.topic, subscriber_id=args.subscriber or "cli_user")
        print(f"Subscribed: {sub.subscription_id} to '{sub.topic}'")
        _save_channel(os_sys)

    elif sub == "notifications":
        os_sys = _load_channel()
        notifications = os_sys.check_notifications()
        print(f"Notifications: {len(notifications)}")
        for n in notifications:
            print(f"  [{n['topic']}] {n['episode_title']} (grade: {n['trust_grade']})")

    elif sub == "receipts":
        os_sys = _load_channel()
        receipts = os_sys.get_receipts()
        verified = os_sys.verify_receipts()
        print(f"Receipts: {len(receipts)}")
        print(f"Verified: {verified}")
        print()
        for r in receipts:
            print(f"  {r['receipt_id']}  {r['action']:<20}  {r['entity_id']:<20}  {r['timestamp']:.0f}")

    elif sub == "export":
        os_sys = _load_channel()
        export = os_sys.export_channel()
        if args.out:
            with open(args.out, "w") as f:
                json.dump(export, f, indent=2)
            print(f"Exported to: {args.out}")
        else:
            print(json.dumps(export, indent=2))

    elif sub == "serve":
        os_sys = _load_channel()
        app = create_youtube_os_api(os_sys)
        port = args.port or 8000
        print(f"Serving Investigation YouTube OS on port {port}")
        print(f"Channel: {os_sys.channel_name}")
        print(f"Endpoints: http://localhost:{port}/channel")
        print(f"Docs: http://localhost:{port}/docs")
        try:
            import uvicorn
            uvicorn.run(app, host="0.0.0.0", port=port)
        except ImportError:
            print("Error: uvicorn not installed. Run: pip install uvicorn")
            sys.exit(1)

    elif sub == "status":
        os_sys = _load_channel()
        manifest = os_sys.channel_manifest()
        print(f"Channel: {manifest['channel_name']}")
        print(f"ID: {manifest['channel_id']}")
        print(f"Platform: {manifest['platform']}")
        print(f"Episodes: {manifest['total_episodes']} ({manifest['published_episodes']} published)")
        print(f"Claims: {manifest['total_claims']}")
        print(f"Papers: {manifest['total_papers']}")
        print(f"Avg buyability: {manifest['avg_buyability']}")
        print(f"Grade distribution: {manifest['grade_distribution']}")
        print(f"Receipts: {manifest['receipt_count']} (verified: {manifest['receipt_chain_verified']})")
        print(f"Playlists: {manifest['total_playlists']}")
        print(f"Subscriptions: {manifest['total_subscriptions']}")
        print(f"State file: {_CHANNEL_FILE}")


def main():
    parser = argparse.ArgumentParser(
        prog="broll",
        description="Investigation YouTube OS — Evidence-backed research media platform",
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # investigate
    inv_parser = subparsers.add_parser("investigate", help="Compile a question into a research media packet")
    inv_parser.add_argument("question", help="The research question to investigate")
    inv_parser.add_argument("--out", "-o", default=None, help="Output directory")
    inv_parser.add_argument("--no-video", action="store_true", help="Skip video timeline")
    inv_parser.add_argument("--no-receipts", action="store_true", help="Skip receipt chain")
    inv_parser.add_argument("--export-b64", action="store_true", help="Export Base64 asset packet")
    inv_parser.add_argument("--mcrv", action="store_true", help="Pack .mcrv (Machine-Consumable Research Video) archive")
    inv_parser.add_argument("--render-all", action="store_true", help="Render all formats: report, dataset, slides, podcast, api")
    inv_parser.add_argument("--frvo", action="store_true", help="Create Fractional Revenue Video Object (rights vault)")
    inv_parser.add_argument("--offering-mode", default="PERK_ONLY",
        choices=["PERK_ONLY", "RIGHTS_RESERVATION", "REGULATED_REVENUE_SHARE", "MACHINE_RIGHTS_MARKET"],
        help="Offering mode for FRVO")
    inv_parser.set_defaults(func=cmd_investigate)

    # verify
    verify_parser = subparsers.add_parser("verify", help="Verify a Base64 asset packet")
    verify_parser.add_argument("packet", help="Path to .b64 file")
    verify_parser.set_defaults(func=cmd_verify)

    # info
    info_parser = subparsers.add_parser("info", help="Show info about a VideoLake output directory")
    info_parser.add_argument("directory", help="Path to output directory")
    info_parser.set_defaults(func=cmd_info)

    # rights
    rights_parser = subparsers.add_parser("rights", help="Inspect a Fractional Revenue Video Object (FRVO)")
    rights_parser.add_argument("frvo_path", help="Path to frvo.json file")
    rights_parser.add_argument("--inspect", action="store_true", help="Machine-readable rights inspection")
    rights_parser.add_argument("--proof", action="store_true", help="Generate proof packet")
    rights_parser.add_argument("--simulate", type=float, default=None, help="Simulate payout with given revenue amount")
    rights_parser.set_defaults(func=cmd_rights)

    # channel (YouTube OS commands)
    chan_parser = subparsers.add_parser("channel", help="Channel management commands")
    chan_sub = chan_parser.add_subparsers(dest="channel_command", help="Channel subcommand")

    # channel create
    chan_create = chan_sub.add_parser("create", help="Create a new channel")
    chan_create.add_argument("name", help="Channel name")
    chan_create.set_defaults(func=cmd_channel)

    # channel status
    chan_status = chan_sub.add_parser("status", help="Show channel status")
    chan_status.set_defaults(func=cmd_channel)

    # channel episode
    chan_ep = chan_sub.add_parser("episode", help="Create a new episode")
    chan_ep.add_argument("question", help="Research question")
    chan_ep.add_argument("--title", default="", help="Episode title")
    chan_ep.add_argument("--tags", default="", help="Comma-separated topic tags")
    chan_ep.add_argument("--compile", action="store_true", help="Compile immediately")
    chan_ep.add_argument("--publish", action="store_true", help="Publish after compile")
    chan_ep.add_argument("--out", default=None, help="Output directory for bundle")
    chan_ep.set_defaults(func=cmd_channel)

    # channel publish
    chan_pub = chan_sub.add_parser("publish", help="Publish a compiled episode")
    chan_pub.add_argument("episode_id", help="Episode ID")
    chan_pub.set_defaults(func=cmd_channel)

    # channel archive
    chan_arch = chan_sub.add_parser("archive", help="Archive an episode")
    chan_arch.add_argument("episode_id", help="Episode ID")
    chan_arch.set_defaults(func=cmd_channel)

    # channel list
    chan_list = chan_sub.add_parser("list", help="List episodes")
    chan_list.add_argument("--status", default=None, help="Filter by status (draft/compiled/published/archived)")
    chan_list.add_argument("--topic", default=None, help="Filter by topic tag")
    chan_list.add_argument("--limit", type=int, default=50, help="Max results")
    chan_list.set_defaults(func=cmd_channel)

    # channel feed
    chan_feed = chan_sub.add_parser("feed", help="Show published episode feed")
    chan_feed.add_argument("--limit", type=int, default=20, help="Max results")
    chan_feed.set_defaults(func=cmd_channel)

    # channel search
    chan_search = chan_sub.add_parser("search", help="Search episodes")
    chan_search.add_argument("query", help="Search query")
    chan_search.add_argument("--limit", type=int, default=20, help="Max results")
    chan_search.set_defaults(func=cmd_channel)

    # channel analytics
    chan_an = chan_sub.add_parser("analytics", help="Show channel analytics")
    chan_an.set_defaults(func=cmd_channel)

    # channel machine-query
    chan_mq = chan_sub.add_parser("machine-query", help="Cross-episode machine segment query")
    chan_mq.add_argument("--topic", default=None, help="Filter by topic")
    chan_mq.add_argument("--min-buyability", type=float, default=0.0, help="Min buyability score")
    chan_mq.add_argument("--min-grade", default="F", help="Min trust grade (F/D/C/B/A)")
    chan_mq.add_argument("--rights", default=None, help="Filter by rights status")
    chan_mq.add_argument("--for-sale-only", action="store_true", help="Only for-sale segments")
    chan_mq.add_argument("--limit", type=int, default=20, help="Max results")
    chan_mq.set_defaults(func=cmd_channel)

    # channel playlist
    chan_pl = chan_sub.add_parser("playlist", help="Playlist management")
    chan_pl.add_argument("playlist_action", choices=["create", "list"], help="Playlist action")
    chan_pl.add_argument("--title", dest="playlist_title", default="", help="Playlist title (for create)")
    chan_pl.add_argument("--desc", dest="playlist_desc", default="", help="Playlist description")
    chan_pl.add_argument("--episodes", dest="episode_ids", default="", help="Comma-separated episode IDs")
    chan_pl.set_defaults(func=cmd_channel)

    # channel subscribe
    chan_sub_cmd = chan_sub.add_parser("subscribe", help="Subscribe to a topic")
    chan_sub_cmd.add_argument("topic", help="Topic to subscribe to")
    chan_sub_cmd.add_argument("--subscriber", default="cli_user", help="Subscriber ID")
    chan_sub_cmd.set_defaults(func=cmd_channel)

    # channel notifications
    chan_notif = chan_sub.add_parser("notifications", help="Check subscription notifications")
    chan_notif.set_defaults(func=cmd_channel)

    # channel receipts
    chan_rct = chan_sub.add_parser("receipts", help="Show receipt ledger")
    chan_rct.set_defaults(func=cmd_channel)

    # channel export
    chan_export = chan_sub.add_parser("export", help="Export channel state")
    chan_export.add_argument("--out", "-o", default=None, help="Output file path")
    chan_export.set_defaults(func=cmd_channel)

    # channel serve
    chan_serve = chan_sub.add_parser("serve", help="Serve channel API via FastAPI")
    chan_serve.add_argument("--port", type=int, default=8000, help="Port to serve on")
    chan_serve.set_defaults(func=cmd_channel)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
