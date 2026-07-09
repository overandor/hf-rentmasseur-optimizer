"""SystemLake Serve — Read-only FastAPI gateway for audit outputs.

Usage:
    python3 -m systemlake.serve /path/to/repo --audit-dir out/ --port 8787

Starts a read-only FastAPI server that exposes:
    GET /health
    GET /manifest
    GET /systems
    GET /systems/{id}
    GET /systems/{id}/packet.b64
    GET /lake/latest.b64
    GET /lake/delta/{root}.b64
    GET /proofbook
    GET /audit/memo
    GET /audit/collateral-scores
    GET /audit/focus-packet.b64
    POST /query
    POST /export/redacted
    POST /benchmark/llm
    GET /receipts
    GET /receipts/verify

Every exposure creates a receipt. No raw files are served.
"""

import os
import sys
import argparse
import tempfile

from .lake import MachineLake
from .policy import PolicyEngine, RedactionEngine
from .compressor import CognitionCompressor
from .underwriter import UnderwritingEngine
from .gateway import create_gateway


def main():
    """CLI: python3 -m systemlake.serve /path/to/repo --audit-dir out/ --port 8787"""
    ap = argparse.ArgumentParser(
        description='SystemLake Serve — read-only FastAPI gateway for audit outputs.')
    ap.add_argument('repo', help='Path to the repo to serve')
    ap.add_argument('--audit-dir', default=None, help='Directory with audit outputs')
    ap.add_argument('--port', type=int, default=8787, help='Port to listen on')
    ap.add_argument('--host', default='127.0.0.1', help='Host to bind (default: localhost only)')
    ap.add_argument('--lake-db', default=None, help='Lake SQLite DB path')
    args = ap.parse_args()

    repo_path = os.path.expanduser(args.repo)
    tmp_dir = tempfile.mkdtemp(prefix='systemlake_serve_')
    lake_db = args.lake_db or os.path.join(tmp_dir, 'lake.db')

    # Crawl if no existing DB
    lake = MachineLake(db_path=lake_db)
    if not lake.summary().get('total_files'):
        print(f"Crawling {repo_path}...")
        lake.crawl(repo_path, max_files=1000)

    policy = PolicyEngine()
    redactor = RedactionEngine()
    compressor = CognitionCompressor(lake, policy, redactor)
    underwriter = UnderwritingEngine(lake_db)

    app = create_gateway(
        lake=lake,
        policy=policy,
        redactor=redactor,
        compressor=compressor,
        underwriter=underwriter,
        audit_dir=args.audit_dir,
    )

    import uvicorn
    print()
    print("=" * 60)
    print("  SYSTEMLAKE GATEWAY")
    print("=" * 60)
    print(f"  Repo: {repo_path}")
    print(f"  Audit dir: {args.audit_dir or 'none'}")
    print(f"  Listening: http://{args.host}:{args.port}")
    print(f"  Docs: http://{args.host}:{args.port}/docs")
    print()
    print("  Endpoints:")
    print("    GET  /health")
    print("    GET  /manifest")
    print("    GET  /systems")
    print("    GET  /proofbook")
    print("    GET  /audit/memo")
    print("    GET  /audit/collateral-scores")
    print("    GET  /audit/focus-packet.b64")
    print("    GET  /lake/latest.b64")
    print("    POST /query")
    print("    POST /export/redacted")
    print("    POST /benchmark/llm")
    print()
    print("  Every exposure creates a receipt.")
    print("  No raw files are served.")
    print("=" * 60)
    print()

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
