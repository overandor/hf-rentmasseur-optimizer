"""QuestionOS CLI — Terminal command interface.

Usage:
    python3 -m questionos ask "How do I optimize FastAPI?" --project myapp
    python3 -m questionos sessions
    python3 -m questionos status
    python3 -m questionos cost
    python3 -m questionos compress <session_id>
    python3 -m questionos serve <session_id>
    python3 -m questionos tui
    python3 -m questionos export [--label "pre-vacation"]
    python3 -m questionos import <snapshot.tar.gz>
    python3 -m questionos snapshots
"""

import sys
import argparse
from .qrc_engine import QRCEngine
from .shadow_sync import ShadowSync


def cmd_ask(args):
    """Ask a question and start a QRC session."""
    engine = QRCEngine()
    session = engine.ask(args.question, project=args.project, access_policy=args.access)
    print(f"Session started: {session.session_id}")
    print(f"  Intent: {session.intent_class}")
    print(f"  Work dir: {session.work_dir}")
    print(f"  Question hash: {session.question_hash[:16]}")

    if args.compress:
        result = engine.compress(session)
        print(f"  Compressed: {result['compressed']}")
        print(f"  Dataset: {result['dataset_path']}")

    if args.serve:
        result = engine.serve(session)
        print(f"  Endpoint: {result.get('url', 'failed')}")


def cmd_sessions(args):
    """List all sessions."""
    engine = QRCEngine()
    sessions = engine.list_sessions(project=args.project)
    if not sessions:
        print("No sessions yet.")
        return

    print(f"Sessions: {len(sessions)}")
    print("=" * 70)
    for s in sessions:
        status_icon = {'running': '*', 'done': '=', 'failed': '!', 'init': '?', 'compressing': '~'}.get(s['status'], '?')
        ep = "ENDPOINT" if s['endpoint'] else "NO EP"
        comp = "COMPRESSED" if s['compressed'] else "RAW"
        print(f"  {status_icon} {s['session_id'][:8]} [{s['intent']:12s}] "
              f"{s['project']:10s} {comp:10s} {ep}  {s['started_at']}")


def cmd_status(args):
    """Show QuestionOS status."""
    engine = QRCEngine()
    status = engine.status()
    print("QuestionOS Status")
    print("=" * 60)
    print(f"  Questions: {status['questions']['total_questions']}")
    print(f"  Compressed: {status['questions']['compressed']}")
    print(f"  With endpoints: {status['questions']['with_endpoints']}")
    print(f"  Projects: {', '.join(status['questions']['projects'])}")
    print()
    print(f"  Executions: {status['executions']['total_events']} events")
    print(f"  Sessions: {status['executions']['sessions']}")
    print(f"  Failures: {status['executions']['failures']}")
    print()
    print(f"  Cost avoidance: ${status['cost_avoidance']['total_estimated_usd']}")
    print(f"  Settled: ${status['cost_avoidance']['total_settled_usd']}")
    print(f"  Disputed: {status['cost_avoidance']['disputed']}")
    print()
    print(f"  Active sessions: {status['active_sessions']}")
    print(f"  Datasets: {status['datasets']}")


def cmd_cost(args):
    """Show cost avoidance report."""
    engine = QRCEngine()
    print(engine.cost_ledger.report())


def cmd_compress(args):
    """Compress a session into a reusable dataset."""
    engine = QRCEngine()
    session = engine.get_session(args.session_id)
    if not session:
        print(f"Session not found: {args.session_id}")
        return
    result = engine.compress(session)
    print(f"Compressed: {result['compressed']}")
    print(f"  Dataset: {result['dataset_path']}")
    print(f"  Summary: {result['summary_path']}")
    print(f"  Files preserved: {len(result['residue']['files'])}")
    print(f"  Commands: {len(result['residue']['commands'])}")
    print(f"  Errors: {len(result['residue']['errors'])}")


def cmd_serve(args):
    """Start a private endpoint for a session."""
    engine = QRCEngine()
    session = engine.get_session(args.session_id)
    if not session:
        print(f"Session not found: {args.session_id}")
        return
    if not session.compressed:
        print("Session not compressed. Compress first.")
        return
    result = engine.serve(session, port=args.port)
    print(f"Served: {result['served']}")
    if result['served']:
        print(f"  URL: {result['url']}")
        print(f"  Port: {result['port']}")
    else:
        print(f"  Error: {result.get('error', 'unknown')}")


def cmd_tui(args):
    """Launch the TUI dashboard."""
    from .tui import run_tui
    run_tui()


def cmd_export(args):
    """Export a snapshot for shadow VM."""
    sync = ShadowSync()
    manifest = sync.export_snapshot(label=args.label)
    print(f"Snapshot exported: {manifest['snapshot_id']}")
    print(f"  Tarball: {manifest['tarball_path']}")
    print(f"  Size: {manifest['tarball_size']} bytes")
    print(f"  Hash: {manifest['snapshot_hash'][:16]}")
    print(f"  Components: {', '.join(manifest['components'].keys())}")
    print(f"  Secrets: {manifest['secrets_policy']['policy']}")


def cmd_import(args):
    """Import a snapshot from shadow VM."""
    sync = ShadowSync()
    result = sync.import_snapshot(args.path)
    print(f"Imported: {result['imported']}")
    if result['imported']:
        print(f"  Snapshot: {result['snapshot']}")
        print(f"  Verified: {result['verified']}")
        for comp, info in result['components'].items():
            print(f"  {comp}: {info}")
    else:
        print(f"  Error: {result.get('error')}")


def cmd_snapshots(args):
    """List available snapshots."""
    sync = ShadowSync()
    snapshots = sync.list_snapshots()
    if not snapshots:
        print("No snapshots yet.")
        return
    print(f"Snapshots: {len(snapshots)}")
    print("=" * 60)
    for s in snapshots:
        print(f"  {s['name'][:40]}  {s['created']}  "
              f"{s['size']:>10} bytes  hash={s['hash']}")


def main():
    parser = argparse.ArgumentParser(
        prog='questionos',
        description='QuestionOS — Terminal-native question execution framework'
    )
    subparsers = parser.add_subparsers(dest='command', help='Command')

    # ask
    p_ask = subparsers.add_parser('ask', help='Ask a question and start a QRC session')
    p_ask.add_argument('question', help='The question to execute')
    p_ask.add_argument('--project', default='default', help='Project name')
    p_ask.add_argument('--access', default='private', choices=['private', 'nda', 'public'])
    p_ask.add_argument('--compress', action='store_true', help='Compress after asking')
    p_ask.add_argument('--serve', action='store_true', help='Start endpoint after asking')
    p_ask.set_defaults(func=cmd_ask)

    # sessions
    p_sessions = subparsers.add_parser('sessions', help='List all sessions')
    p_sessions.add_argument('--project', default=None)
    p_sessions.set_defaults(func=cmd_sessions)

    # status
    p_status = subparsers.add_parser('status', help='Show QuestionOS status')
    p_status.set_defaults(func=cmd_status)

    # cost
    p_cost = subparsers.add_parser('cost', help='Show cost avoidance report')
    p_cost.set_defaults(func=cmd_cost)

    # compress
    p_compress = subparsers.add_parser('compress', help='Compress a session')
    p_compress.add_argument('session_id')
    p_compress.set_defaults(func=cmd_compress)

    # serve
    p_serve = subparsers.add_parser('serve', help='Start endpoint for a session')
    p_serve.add_argument('session_id')
    p_serve.add_argument('--port', type=int, default=0)
    p_serve.set_defaults(func=cmd_serve)

    # tui
    p_tui = subparsers.add_parser('tui', help='Launch TUI dashboard')
    p_tui.set_defaults(func=cmd_tui)

    # export
    p_export = subparsers.add_parser('export', help='Export snapshot for shadow VM')
    p_export.add_argument('--label', default=None)
    p_export.set_defaults(func=cmd_export)

    # import
    p_import = subparsers.add_parser('import', help='Import snapshot from shadow VM')
    p_import.add_argument('path', help='Path to snapshot tarball')
    p_import.set_defaults(func=cmd_import)

    # snapshots
    p_snapshots = subparsers.add_parser('snapshots', help='List available snapshots')
    p_snapshots.set_defaults(func=cmd_snapshots)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
