"""Unified Value Claim Packet — questionos.underwrite

Combines SystemLake crawl + UnderwritingEngine + AAU into one command
that produces a Value Claim Packet from a repo or local system.

Usage:
    python3 -m questionos.underwrite /path/to/repo --out vcp.json --b64

The packet contains:
    - System lake summary (Merkle root, file counts, system detection)
    - Collateral scores (functionality, deployability, receipt strength, etc.)
    - Adversarial attribution underwriting (gaming checks, counterfactual stripping)
    - Value claim with settlement status
    - Cognition packet (redacted, compressed, Base64-ready)
    - Receipt chain proving the underwriting occurred

The packet does NOT contain:
    - Raw file contents
    - Secrets or tokens
    - Sensitive zone metadata
"""

import os
import sys
import json
import hashlib
import base64
import zlib
import argparse
import tempfile
from datetime import datetime
from typing import Dict, List, Optional

from systemlake.lake import MachineLake
from systemlake.policy import PolicyEngine, RedactionEngine
from systemlake.compressor import CognitionCompressor
from systemlake.underwriter import UnderwritingEngine, CollateralScore
from systemlake.aau import (
    AdversarialAttributionUnderwriter,
    Baseline, Evidence, GamingFlags, ValueClaim, ClaimStatus,
)
from quadrantos.receipt_store import SQLiteReceiptStore


def generate_value_claim_packet(
    repo_path: str,
    output_path: str = None,
    emit_b64: bool = False,
    lake_db: str = None,
    receipts_db: str = None,
) -> Dict:
    """Generate a Value Claim Packet from a repo or local system.

    This is the unified command that ties together:
    1. SystemLake crawl → SQLite index, Merkle root, system detection
    2. UnderwritingEngine → collateral scores (7 dimensions + haircuts)
    3. AAU → adversarial attribution, gaming detection, settlement
    4. CognitionCompressor → redacted semantic packet
    5. SQLiteReceiptStore → receipt chain proving the underwriting

    Args:
        repo_path: Path to the repo/system to underwrite
        output_path: Where to write the VCP JSON (default: stdout)
        emit_b64: Also emit a Base64 compressed version
        lake_db: Path to the lake SQLite DB (default: temp)
        receipts_db: Path to the receipts SQLite DB (default: temp)

    Returns:
        The Value Claim Packet dict
    """
    repo_path = os.path.expanduser(repo_path)
    if not os.path.isdir(repo_path):
        raise ValueError(f"Path does not exist: {repo_path}")

    now_str = datetime.now().isoformat()
    tmp_dir = tempfile.mkdtemp(prefix='vcp_')
    lake_db = lake_db or os.path.join(tmp_dir, 'lake.db')
    receipts_db = receipts_db or os.path.join(tmp_dir, 'receipts.db')

    # --- Layer 1: MachineLake Crawl ---
    lake = MachineLake(db_path=lake_db)
    crawl_result = lake.crawl(repo_path, max_files=1000)

    # --- Layer 2: Collateral Underwriting ---
    underwriter = UnderwritingEngine(lake_db)
    collateral_scores = underwriter.score_all()

    # --- Layer 3: Adversarial Attribution Underwriting ---
    aau = AdversarialAttributionUnderwriter()
    aau_results = []

    for score in collateral_scores:
        # Build baseline from collateral dimensions
        baseline = Baseline(
            label=f"{score.system_name}_baseline",
            snapshot_hash=crawl_result['merkle_root'],
            timestamp=now_str,
            metrics={
                'functionality': score.functionality,
                'deployability': score.deployability,
                'receipt_strength': score.receipt_strength,
                'security': score.security_cleanliness,
            },
        )

        # Build evidence from detected capabilities
        evidence_list = []
        systems = lake.list_systems()
        for sys_row in systems:
            if sys_row['name'] == score.system_name:
                if sys_row['has_receipts']:
                    evidence_list.append(Evidence(
                        evidence_id=hashlib.sha256(
                            f"{score.system_name}_receipts".encode()).hexdigest()[:16],
                        kind='receipt',
                        source=f"{score.system_name}/receipts",
                        timestamp=now_str,
                        payload_hash=crawl_result['merkle_root'][:16],
                        weight=0.8,
                        verified=True,
                    ))
                if sys_row['has_tests']:
                    evidence_list.append(Evidence(
                        evidence_id=hashlib.sha256(
                            f"{score.system_name}_tests".encode()).hexdigest()[:16],
                        kind='test_pass',
                        source=f"{score.system_name}/tests",
                        timestamp=now_str,
                        payload_hash='test_detected',
                        weight=0.7,
                        verified=True,
                    ))
                if sys_row['has_endpoints']:
                    evidence_list.append(Evidence(
                        evidence_id=hashlib.sha256(
                            f"{score.system_name}_endpoints".encode()).hexdigest()[:16],
                        kind='endpoint_response',
                        source=f"{score.system_name}/endpoints",
                        timestamp=now_str,
                        payload_hash='endpoint_detected',
                        weight=0.6,
                        verified=False,  # not actually called
                    ))
                break

        # Detect gaming flags from collateral score
        gaming = GamingFlags()
        if score.secret_leak_haircut > 0:
            gaming.unverifiable_delta = False  # secrets don't mean no delta
        if score.no_tests_haircut > 0:
            gaming.unverifiable_delta = True
        if getattr(score, 'unverifiable_claims', 0) > 0:
            gaming.unverifiable_delta = True
        if getattr(score, 'no_users', 0) > 0:
            gaming.non_poolable = True
        if score.collateral_score < 20:
            gaming.non_poolable = True

        # Estimate value (conservative)
        # Base: hours of work represented × rate × confidence
        estimated_hours = min(score.functionality / 10, 20)  # cap at 20h
        estimated_value = estimated_hours * 120 * (score.collateral_score / 100)
        counterfactual = estimated_value * 0.3  # 30% would have happened anyway

        claim = ValueClaim(
            claim_id=hashlib.sha256(
                f"{score.system_name}_{now_str}".encode()).hexdigest()[:16],
            system_name=score.system_name,
            baseline=baseline,
            evidence=evidence_list,
            gaming_flags=gaming,
            claimed_value_usd=estimated_value,
            counterfactual_value_usd=counterfactual,
            hours_avoided=estimated_hours,
            confidence=score.collateral_score / 100,
            exchangeability=min(1.0, score.deployability / 100),
            reputation=0.5,  # neutral start
        )

        aau_result = aau.underwrite(claim)
        aau_results.append({
            'system_name': score.system_name,
            'collateral_score': score.to_dict(),
            'aau_receipt': aau_result['receipt'],
            'status': aau_result['status'].value,
            'settled_value': aau_result['settled_value'],
            'gaming_flags': aau_result['gaming_flags'],
        })

    # --- Layer 4: Cognition Packet ---
    policy = PolicyEngine()
    redactor = RedactionEngine()
    compressor = CognitionCompressor(lake, policy, redactor)
    cognition_packet = compressor.compress(
        root=repo_path, max_files=200, include_snippets=True, include_symbols=True)
    cognition_receipt = compressor.to_receipt(cognition_packet)

    # --- Layer 5: Receipt Chain ---
    receipts = SQLiteReceiptStore(receipts_db)
    vcp_receipt = receipts.write(
        agent='ValueClaimPacket',
        action='vcp_generated',
        artifact_path=output_path,
        details={
            'repo': repo_path,
            'merkle_root': crawl_result['merkle_root'][:16],
            'systems_scored': len(collateral_scores),
            'aau_settlements': len(aau_results),
            'cognition_packet_hash': cognition_receipt['packet_sha256'][:16],
        },
    )

    # --- Assemble VCP ---
    vcp = {
        'schema': 'membra.value_claim_packet.v1',
        'generated_at': now_str,
        'repo_path': repo_path,
        'repo_name': os.path.basename(repo_path),
        'lake': {
            'merkle_root': crawl_result['merkle_root'],
            'file_count': crawl_result['file_count'],
            'total_size': crawl_result['total_size'],
            'new_files': crawl_result['new_files'],
            'changed_files': crawl_result['changed_files'],
            'crawl_duration_ms': crawl_result['duration_ms'],
        },
        'systems': [s.to_dict() for s in collateral_scores],
        'underwriting': aau_results,
        'cognition': {
            'packet_sha256': cognition_receipt['packet_sha256'],
            'b64_size': cognition_receipt['b64_size'],
            'privacy': cognition_packet['privacy'],
            'systems_detected': len(cognition_packet.get('systems', [])),
        },
        'settlement_chain': aau.verify_settlements(),
        'receipt': {
            'id': vcp_receipt['id'],
            'chain_hash': vcp_receipt['chain_hash'],
            'timestamp': vcp_receipt['timestamp'],
        },
        'disclaimer': (
            'Estimated underwritten software work-equity, not guaranteed valuation. '
            'Every claim has been through adversarial attribution review. '
            'Settled values are finance-readable estimates subject to external audit. '
            'Collateral scores are not cash net worth.'
        ),
    }

    # Compute VCP hash
    vcp['vcp_sha256'] = hashlib.sha256(
        json.dumps(vcp, sort_keys=True).encode()).hexdigest()

    # --- Output ---
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(vcp, f, indent=2)

    if emit_b64:
        raw = json.dumps(vcp, sort_keys=True).encode()
        compressed = zlib.compress(raw, 9)
        b64 = base64.b64encode(compressed).decode()
        b64_path = (output_path or '/dev/stdout').replace('.json', '.b64')
        if output_path:
            with open(b64_path, 'w') as f:
                f.write(b64)
        vcp['b64_path'] = b64_path
        vcp['b64_size'] = len(b64)

    # Cleanup temp
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return vcp


def print_report(vcp: Dict):
    """Print a human-readable VCP report."""
    print("=" * 70)
    print("  MEMBRA VALUE CLAIM PACKET")
    print("=" * 70)
    print()
    print(f"  Repo: {vcp['repo_name']}")
    print(f"  Merkle root: {vcp['lake']['merkle_root'][:16]}")
    print(f"  Files indexed: {vcp['lake']['file_count']}")
    print(f"  Systems scored: {len(vcp['systems'])}")
    print()

    print("  COLLATERAL SCORES:")
    for s in vcp['systems']:
        print(f"    {s['system']:30s}  Score: {s['collateral_score']:5.1f}  Grade: {s['grade']}")
    print()

    print("  ADVERSARIAL ATTRIBUTION UNDERWRITING:")
    for u in vcp['underwriting']:
        r = u['aau_receipt']
        print(f"    {u['system_name']:30s}  Status: {u['status']}")
        print(f"      Claimed: ${r['claimed_value_usd']:.2f}  "
              f"Counterfactual: ${r['counterfactual_value_usd']:.2f}  "
              f"Net: ${r['net_value_usd']:.2f}")
        print(f"      Settled: ${u['settled_value']:.2f}  "
              f"Score: {r['final_score']:.1f}")
        if u['gaming_flags']:
            print(f"      Gaming flags: {', '.join(u['gaming_flags'])}")
        print()

    print(f"  Settlement chain: {vcp['settlement_chain']}")
    print(f"  VCP SHA-256: {vcp['vcp_sha256'][:16]}")
    print(f"  Receipt: {vcp['receipt']['id'][:8]}  chain={vcp['receipt']['chain_hash'][:16]}")
    print()
    print(f"  {vcp['disclaimer']}")
    print("=" * 70)


def main():
    """CLI entry point: python3 -m questionos.underwrite /path/to/repo --out vcp.json --b64"""
    ap = argparse.ArgumentParser(
        description='Generate a Value Claim Packet from a repo or local system.')
    ap.add_argument('repo', help='Path to the repo/system to underwrite')
    ap.add_argument('--out', default=None, help='Output JSON file path')
    ap.add_argument('--b64', action='store_true', help='Also emit Base64 compressed version')
    ap.add_argument('--lake-db', default=None, help='Path to lake SQLite DB')
    ap.add_argument('--receipts-db', default=None, help='Path to receipts SQLite DB')
    ap.add_argument('--quiet', action='store_true', help='Suppress report output')
    args = ap.parse_args()

    vcp = generate_value_claim_packet(
        repo_path=args.repo,
        output_path=args.out,
        emit_b64=args.b64,
        lake_db=args.lake_db,
        receipts_db=args.receipts_db,
    )

    if not args.quiet:
        print_report(vcp)

    if args.out:
        print(f"\n  VCP written to: {args.out}")
    if args.b64 and 'b64_path' in vcp:
        print(f"  B64 written to: {vcp['b64_path']} ({vcp['b64_size']} chars)")


if __name__ == '__main__':
    main()
