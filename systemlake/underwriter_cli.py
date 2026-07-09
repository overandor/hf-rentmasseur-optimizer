"""SystemLake Underwriter CLI — Full-machine collateral underwriting.

Usage:
    python3 -m systemlake.underwriter /Users/alep \
      --full-machine-index \
      --local-only-raw \
      --export-redacted-focus-b64 \
      --collateralize

    python3 -m systemlake.underwriter /Users/alep \
      --metadata-all \
      --content-roots /Users/alep/Downloads,/Users/alep/CascadeProjects \
      --deny .ssh,Library/Keychains,Library/Messages,Library/Mail \
      --underwrite --collateralize --sbom --scorecard \
      --out systemlake_full_underwrite

SystemLake Underwriter turns your laptop into a private software collateral
data room. It crawls everything locally, proves what exists by hash, verifies
what runs by receipt, prices what matters by underwriting score, and exports
only redacted Base64 cognition packets for LLM audit.
"""

import argparse
import sys

from systemlake.audit import run_audit


def main():
    """CLI entry point for the SystemLake Underwriter."""
    ap = argparse.ArgumentParser(
        description='SystemLake Underwriter — full-machine local audit, '
                    'collateral scoring, and redacted Base64 focus packet export. '
                    'Turns your laptop into a private software collateral data room.')
    ap.add_argument('path', help='Path to the machine root or repo to underwrite')
    ap.add_argument('--out', default='systemlake_full_underwrite',
                    help='Output directory (default: systemlake_full_underwrite)')
    ap.add_argument('--max-files', type=int, default=2000,
                    help='Max files to crawl (default: 2000)')

    # Crawl mode
    ap.add_argument('--full-machine-index', action='store_true',
                    help='Full machine index: metadata for every reachable file')
    ap.add_argument('--metadata-all', action='store_true',
                    help='Alias for --full-machine-index')

    # Content policy
    ap.add_argument('--content-roots', default=None,
                    help='Comma-separated paths where content reading is allowed')
    ap.add_argument('--deny', default=None,
                    help='Comma-separated paths to deny (no content, no descent)')
    ap.add_argument('--local-only-raw', action='store_true', default=True,
                    help='Keep raw files local only (always on)')

    # Underwriting
    ap.add_argument('--underwrite', action='store_true', default=True,
                    help='Run 10-dimension underwriting engine (default: on)')
    ap.add_argument('--collateralize', action='store_true', default=True,
                    help='Compute borrowing base estimates (default: on)')
    ap.add_argument('--sbom', action='store_true', default=False,
                    help='Generate lightweight SBOM from dependency files')
    ap.add_argument('--scorecard', action='store_true', default=False,
                    help='Generate OpenSSF Scorecard-style security posture summary')

    # Export
    ap.add_argument('--export-redacted-focus-b64', action='store_true', default=True,
                    help='Export redacted Base64 focus packet (always on)')

    args = ap.parse_args()

    metadata_all = args.full_machine_index or args.metadata_all

    content_roots = None
    if args.content_roots:
        content_roots = [r.strip() for r in args.content_roots.split(',')]

    deny_paths = None
    if args.deny:
        deny_paths = [d.strip() for d in args.deny.split(',')]

    result = run_audit(
        repo_path=args.path,
        output_dir=args.out,
        max_files=args.max_files,
        metadata_all=metadata_all,
        content_roots=content_roots,
        deny_paths=deny_paths,
        underwrite=args.underwrite,
        collateralize=args.collateralize,
        sbom=args.sbom,
        scorecard=args.scorecard,
    )

    print()
    print("=" * 70)
    print("  SYSTEMLAKE UNDERWRITER — COLLATERAL AUDIT COMPLETE")
    print("=" * 70)
    print(f"  Path: {args.path}")
    print(f"  Output: {result['output_dir']}")
    print(f"  Merkle root: {result['merkle_root'][:16]}")
    print(f"  Files indexed: {result['file_count']}")
    print(f"  Systems scored: {result['systems_scored']}")
    print(f"  Borrowing base (mid): ${result.get('borrowing_base_total', 0):,.2f}")
    print(f"  Focus packet: {result['focus_packet_b64_size']} chars (b64)")
    print(f"  Focus SHA-256: {result['focus_sha256'][:16]}")
    print(f"  Receipt: {result['receipt_id'][:16]}")
    print()
    print("  Files written:")
    for f in result['files_written']:
        import os
        fpath = os.path.join(result['output_dir'], f)
        size = os.path.getsize(fpath) if os.path.exists(fpath) else 0
        print(f"    {f:30s}  {size:>10,} bytes")
    print()
    print("  To export the focus packet:")
    print(f"    cat {result['output_dir']}/focus_packet.b64")
    print()
    print("  SystemLake Underwriter turns your laptop into a private software")
    print("  collateral data room. It crawls everything locally, proves what")
    print("  exists by hash, verifies what runs by receipt, prices what matters")
    print("  by underwriting score, and exports only redacted Base64 cognition")
    print("  packets for LLM audit.")
    print("=" * 70)


if __name__ == '__main__':
    main()
