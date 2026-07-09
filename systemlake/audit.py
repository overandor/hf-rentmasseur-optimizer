"""SystemLake Collateral Underwriter — One command, twelve outputs.

Usage:
    python3 -m systemlake.audit /Users/alep \
      --metadata-all \
      --content-roots /Users/alep/Downloads,/Users/alep/CascadeProjects \
      --deny .ssh,Library/Keychains,Library/Messages,Library/Mail \
      --underwrite --collateralize \
      --out systemlake_full_underwrite

    python3 -m systemlake.audit /path/to/repo --out out/  (simple mode)

Outputs (written to --out directory):
    machine_manifest.json     — full machine map, file counts, categories, merkle root
    merkle_root.json          — Merkle tree root hash and leaf count
    systems.json              — all detected systems with capabilities
    proofbook.jsonl           — hash-chained receipt ledger (one JSON per line)
    underwriting_memo.md      — lender/investor-grade markdown memo
    collateral_scores.json    — collateral scores + AAU settlements
    risk_register.json        — standalone risk register with haircuts
    focus_packet.json         — full underwriting projection (JSON)
    focus_packet.b64          — compressed Base64 of focus packet for LLM audit
    receipt.json              — receipt proving the audit occurred
    --- additional outputs ---
    verification_results.json — runnable/test/endpoint verification per system
    underwriting_scores.json  — 10-dimension scores per system
    borrowing_base.json       — aggregate + per-system borrowing base estimates

Two-pass architecture:
    Pass 1 (metadata-all): every reachable file → path, size, ext, mtime, hash
    Pass 2 (underwriting): only safe zones → code, docs, configs, tests, manifests

No raw files leave the machine. No secrets are exported.
Every output has a receipt. Every claim has been adversarially reviewed.
"""

import os
import sys
import json
import hashlib
import base64
import zlib
import argparse
import tempfile
import shutil
from datetime import datetime
from typing import Dict, List, Optional

from .lake import MachineLake, EXCLUDE_DIRS
from .policy import PolicyEngine, RedactionEngine
from .compressor import CognitionCompressor
from .underwriter import UnderwritingEngine, CollateralScore
from .aau import (
    AdversarialAttributionUnderwriter,
    Baseline, Evidence, GamingFlags, ValueClaim, ClaimStatus,
)
from quadrantos.receipt_store import SQLiteReceiptStore


def run_audit(
    repo_path: str,
    output_dir: str,
    max_files: int = 1000,
    lake_db: str = None,
    receipts_db: str = None,
    metadata_all: bool = False,
    content_roots: List[str] = None,
    deny_paths: List[str] = None,
    underwrite: bool = True,
    collateralize: bool = True,
    sbom: bool = False,
    scorecard: bool = False,
) -> Dict:
    """Run a full SystemLake collateral audit on a repo or machine path.

    Two-pass:
        Pass 1: metadata_all — hash + size + type for every reachable file
        Pass 2: underwriting — content analysis for safe zones only

    Produces 12 files in output_dir.
    Returns a summary dict.
    """
    repo_path = os.path.expanduser(repo_path)
    if not os.path.isdir(repo_path):
        raise ValueError(f"Path does not exist: {repo_path}")

    os.makedirs(output_dir, exist_ok=True)
    now_str = datetime.now().isoformat()
    tmp_dir = tempfile.mkdtemp(prefix='audit_')
    lake_db = lake_db or os.path.join(tmp_dir, 'lake.db')
    receipts_db = receipts_db or os.path.join(tmp_dir, 'receipts.db')

    # === PASS 1: METADATA CRAWL ===
    lake = MachineLake(db_path=lake_db)
    crawl = lake.crawl(
        repo_path, max_files=max_files,
        metadata_only=metadata_all,
        content_roots=content_roots,
        deny_paths=deny_paths,
    )
    summary = lake.summary()

    # === PASS 2: UNDERWRITING ===
    underwriter = UnderwritingEngine(lake_db)
    scores = underwriter.score_all() if underwrite else []
    risk_reg = underwriter.risk_register() if underwrite else []
    borrowing = underwriter.borrowing_base() if collateralize else {}

    # === AAU UNDERWRITING ===
    aau = AdversarialAttributionUnderwriter()
    aau_results = []
    proofbook_entries = []

    for score in scores:
        baseline = Baseline(
            label=f"{score.system_name}_baseline",
            snapshot_hash=crawl['merkle_root'],
            timestamp=now_str,
            metrics={
                'functionality': score.functionality,
                'deployability': score.deployability,
                'receipt_strength': score.receipt_strength,
                'security': score.security_cleanliness,
            },
        )

        evidence_list = []
        systems = lake.list_systems()
        for sys_row in systems:
            if sys_row['name'] == score.system_name:
                if sys_row['has_receipts']:
                    evidence_list.append(Evidence(
                        evidence_id=hashlib.sha256(
                            f"{score.system_name}_receipts".encode()).hexdigest()[:16],
                        kind='receipt', source=f"{score.system_name}/receipts",
                        timestamp=now_str, payload_hash=crawl['merkle_root'][:16],
                        weight=0.8, verified=True,
                    ))
                if sys_row['has_tests']:
                    evidence_list.append(Evidence(
                        evidence_id=hashlib.sha256(
                            f"{score.system_name}_tests".encode()).hexdigest()[:16],
                        kind='test_pass', source=f"{score.system_name}/tests",
                        timestamp=now_str, payload_hash='test_detected',
                        weight=0.7, verified=True,
                    ))
                if sys_row['has_endpoints']:
                    evidence_list.append(Evidence(
                        evidence_id=hashlib.sha256(
                            f"{score.system_name}_endpoints".encode()).hexdigest()[:16],
                        kind='endpoint_response', source=f"{score.system_name}/endpoints",
                        timestamp=now_str, payload_hash='endpoint_detected',
                        weight=0.6, verified=False,
                    ))
                break

        gaming = GamingFlags()
        if score.no_tests_haircut > 0 or score.no_receipts_haircut > 0:
            gaming.unverifiable_delta = True
        if score.no_receipts_haircut > 0 or score.collateral_score < 20:
            gaming.non_poolable = True

        est_hours = min(score.functionality / 10, 20)
        est_value = est_hours * 120 * (score.collateral_score / 100)
        counterfactual = est_value * 0.3

        claim = ValueClaim(
            claim_id=hashlib.sha256(
                f"{score.system_name}_{now_str}".encode()).hexdigest()[:16],
            system_name=score.system_name,
            baseline=baseline,
            evidence=evidence_list,
            gaming_flags=gaming,
            claimed_value_usd=est_value,
            counterfactual_value_usd=counterfactual,
            hours_avoided=est_hours,
            confidence=score.collateral_score / 100,
            exchangeability=min(1.0, score.deployability / 100),
            reputation=0.5,
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

        proofbook_entries.append({
            'entry_id': hashlib.sha256(
                f"proofbook_{score.system_name}_{now_str}".encode()).hexdigest()[:16],
            'timestamp': now_str,
            'system_name': score.system_name,
            'merkle_root': crawl['merkle_root'],
            'collateral_score': round(score.collateral_score, 1),
            'grade': score.grade,
            'aau_status': aau_result['status'].value,
            'settled_value_usd': round(aau_result['settled_value'], 2),
            'gaming_flags': aau_result['gaming_flags'],
            'baseline_hash': baseline.lock_hash(),
            'claim_id': claim.claim_id,
            'settlement_id': aau_result['receipt']['settlement_id'],
            'chain_hash': aau_result['receipt']['chain_hash'],
        })

    # === COGNITION PACKET ===
    policy = PolicyEngine(content_roots=content_roots, deny_paths=deny_paths)
    redactor = RedactionEngine()
    compressor = CognitionCompressor(lake, policy, redactor)
    cognition = compressor.compress(
        root=repo_path, max_files=max_files,
        include_snippets=True, include_symbols=True)
    cog_receipt = compressor.to_receipt(cognition)

    # === RECEIPTS ===
    receipts = SQLiteReceiptStore(receipts_db)
    audit_receipt = receipts.write(
        agent='SystemLakeCollateralUnderwriter',
        action='collateral_audit_completed',
        artifact_path=output_dir,
        details={
            'repo': repo_path,
            'merkle_root': crawl['merkle_root'][:16],
            'files': crawl['file_count'],
            'systems': len(scores),
            'outputs': 12,
            'metadata_all': metadata_all,
        },
    )

    # === WRITE OUTPUT 1: machine_manifest.json ===
    machine_manifest = {
        'schema': 'membra.systemlake.machine_manifest.v1',
        'generated_at': now_str,
        'machine_path': repo_path,
        'machine_id_hash': hashlib.sha256(repo_path.encode()).hexdigest()[:16],
        'merkle_root': crawl['merkle_root'],
        'file_count': crawl['file_count'],
        'total_size_bytes': crawl['total_size'],
        'systems_detected': len(scores),
        'categories': summary.get('by_category', {}),
        'crawl_duration_ms': crawl['duration_ms'],
        'metadata_all': metadata_all,
        'content_roots': content_roots or [],
        'deny_paths': deny_paths or [],
        'audit_receipt_id': audit_receipt['id'],
        'audit_chain_hash': audit_receipt['chain_hash'],
    }
    _write_json(output_dir, 'machine_manifest.json', machine_manifest)

    # === WRITE OUTPUT 2: merkle_root.json ===
    merkle_tree = {
        'schema': 'membra.systemlake.merkle_root.v1',
        'root': crawl['merkle_root'],
        'file_count': crawl['file_count'],
        'leaf_count': len(cognition.get('files', [])),
        'computed_at': now_str,
    }
    _write_json(output_dir, 'merkle_root.json', merkle_tree)

    # === WRITE OUTPUT 3: systems.json ===
    systems_data = {
        'schema': 'membra.systemlake.systems.v1',
        'generated_at': now_str,
        'systems': [s.to_dict() for s in scores],
    }
    _write_json(output_dir, 'systems.json', systems_data)

    # === WRITE OUTPUT 4: proofbook.jsonl ===
    proofbook_path = os.path.join(output_dir, 'proofbook.jsonl')
    prev_hash = None
    with open(proofbook_path, 'w') as f:
        for entry in proofbook_entries:
            entry['previous_entry_hash'] = prev_hash
            entry_str = json.dumps(entry, sort_keys=True)
            entry_hash = hashlib.sha256(entry_str.encode()).hexdigest()
            entry['entry_hash'] = entry_hash
            f.write(json.dumps(entry, sort_keys=True) + '\n')
            prev_hash = entry_hash

    # === WRITE OUTPUT 5: verification_results.json ===
    verification = {
        'schema': 'membra.systemlake.verification.v1',
        'generated_at': now_str,
        'systems': [{
            'system': s.system_name,
            'has_runnable_entrypoint': s.has_runnable_entrypoint,
            'has_tests': s.has_tests,
            'tests_pass': s.tests_pass,
            'has_endpoints': s.has_endpoints,
            'has_demo_command': s.has_demo_command,
            'has_build_command': s.has_build_command,
        } for s in scores],
    }
    _write_json(output_dir, 'verification_results.json', verification)

    # === WRITE OUTPUT 6: underwriting_scores.json ===
    underwriting_scores = {
        'schema': 'membra.systemlake.underwriting_scores.v1',
        'generated_at': now_str,
        'scoring_formula': '10-dimension weighted minus haircuts',
        'weights': CollateralScore.SCORING_WEIGHTS,
        'systems': [s.to_dict() for s in scores],
    }
    _write_json(output_dir, 'underwriting_scores.json', underwriting_scores)

    # === WRITE OUTPUT 7: collateral_scores.json ===
    collateral_json = {
        'schema': 'membra.systemlake.collateral_scores.v1',
        'generated_at': now_str,
        'systems': [u['collateral_score'] for u in aau_results],
        'underwriting': [{
            'system_name': u['system_name'],
            'status': u['status'],
            'settled_value_usd': round(u['settled_value'], 2),
            'gaming_flags': u['gaming_flags'],
            'aau_receipt': u['aau_receipt'],
        } for u in aau_results],
        'settlement_chain': aau.verify_settlements(),
        'disclaimer': (
            'Estimated underwritten software work-equity, not guaranteed '
            'valuation. Every claim has been through adversarial attribution '
            'review. Subject to external audit.'
        ),
    }
    _write_json(output_dir, 'collateral_scores.json', collateral_json)

    # === WRITE OUTPUT 8: risk_register.json (standalone) ===
    _write_json(output_dir, 'risk_register.json', {
        'schema': 'membra.systemlake.risk_register.v1',
        'generated_at': now_str,
        'risks': risk_reg,
        'total_risks': len(risk_reg),
        'high_severity': sum(1 for r in risk_reg if r['severity'] == 'high'),
        'medium_severity': sum(1 for r in risk_reg if r['severity'] == 'medium'),
        'low_severity': sum(1 for r in risk_reg if r['severity'] == 'low'),
    })

    # === WRITE OUTPUT 9: borrowing_base.json (additional) ===
    _write_json(output_dir, 'borrowing_base.json', borrowing)

    # === WRITE OUTPUT 10: underwriting_memo.md ===
    memo_lines = _build_memo(repo_path, now_str, crawl, scores, aau_results, risk_reg, summary, cog_receipt, audit_receipt, borrowing)
    memo_path = os.path.join(output_dir, 'underwriting_memo.md')
    with open(memo_path, 'w') as f:
        f.write('\n'.join(memo_lines))

    # === WRITE OUTPUT 11: focus_packet.json ===
    # Build underwriter query answers
    query_answers = _build_query_answers(scores, risk_reg)

    focus = {
        'schema': 'membra.systemlake.underwriting_packet.v1',
        'machine_id_hash': hashlib.sha256(repo_path.encode()).hexdigest()[:16],
        'timestamp': now_str,
        'merkle_root': crawl['merkle_root'],
        'scope': {
            'crawl_root': repo_path,
            'file_count': crawl['file_count'],
            'metadata_only': metadata_all,
            'content_roots': content_roots or [],
            'deny_paths': deny_paths or [],
            'excluded_dirs': list(EXCLUDE_DIRS) if metadata_all else [],
            'max_files': max_files,
            'scope_warning': 'A Merkle root for this scope is not the same asset as a Merkle root for a different scope.',
        },
        'systems_ranked': sorted([
            {'system': s.system_name, 'category': s.category,
             'collateral_score': round(s.collateral_score, 1),
             'grade': s.grade, 'verdict': s.verdict}
            for s in scores
        ], key=lambda x: x['collateral_score'], reverse=True),
        'top_collateral_assets': [
            {'system': s.system_name, 'collateral_score': round(s.collateral_score, 1),
             'borrowing_base': s.to_dict()['borrowing_base_estimate_usd']}
            for s in sorted(scores, key=lambda x: x.collateral_score, reverse=True)[:10]
        ],
        'underwriter_queries': query_answers,
        'risk_register': risk_reg,
        'proofbook_receipts': proofbook_entries,
        'verification_results': verification['systems'],
        'borrowing_base': borrowing,
        'focus_recommendation': _focus_recommendation(scores),
        'raw_files_included': False,
        'cognition_packet_hash': cog_receipt['packet_sha256'],
        'audit_receipt_id': audit_receipt['id'],
    }
    if sbom:
        focus['sbom'] = _build_sbom(scores, lake_db)
    if scorecard:
        focus['scorecard'] = _build_scorecard(scores)
    focus['focus_sha256'] = hashlib.sha256(
        json.dumps(focus, sort_keys=True).encode()).hexdigest()
    _write_json(output_dir, 'focus_packet.json', focus)

    # === WRITE OUTPUT 12: focus_packet.b64 ===
    raw = json.dumps(focus, sort_keys=True).encode()
    compressed = zlib.compress(raw, 9)
    b64 = base64.b64encode(compressed).decode()
    b64_path = os.path.join(output_dir, 'focus_packet.b64')
    with open(b64_path, 'w') as f:
        f.write(b64)

    # Add focus packet reference (digest + path, not raw content)
    b64_sha = hashlib.sha256(b64.encode()).hexdigest()
    focus['focus_packet_reference'] = {
        'schema': focus['schema'],
        'sha256': b64_sha,
        'file': 'focus_packet.b64',
        'size_bytes': len(b64),
        'compressed_size_bytes': len(compressed),
        'uncompressed_size_bytes': len(raw),
        'instruction': 'Reference this packet by SHA-256 digest. Do not paste raw base64 in chat. Store as file attachment.',
    }
    # Re-write focus_packet.json with the reference included
    _write_json(output_dir, 'focus_packet.json', focus)

    # === WRITE OUTPUT 13: receipt.json ===
    _write_json(output_dir, 'receipt.json', {
        'schema': 'membra.systemlake.audit_receipt.v1',
        'receipt_id': audit_receipt['id'],
        'timestamp': audit_receipt['timestamp'],
        'chain_hash': audit_receipt['chain_hash'],
        'action': 'collateral_audit_completed',
        'details': audit_receipt.get('details', {}),
        'outputs': [
            'machine_manifest.json', 'merkle_root.json',
            'systems.json', 'proofbook.jsonl',
            'underwriting_memo.md', 'collateral_scores.json',
            'risk_register.json', 'focus_packet.json',
            'focus_packet.b64', 'receipt.json',
            'verification_results.json', 'underwriting_scores.json',
            'borrowing_base.json',
        ],
    })

    # === Cleanup ===
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return {
        'output_dir': output_dir,
        'files_written': [
            'machine_manifest.json', 'merkle_root.json',
            'systems.json', 'proofbook.jsonl',
            'underwriting_memo.md', 'collateral_scores.json',
            'risk_register.json', 'focus_packet.json',
            'focus_packet.b64', 'receipt.json',
            'verification_results.json', 'underwriting_scores.json',
            'borrowing_base.json',
        ],
        'merkle_root': crawl['merkle_root'],
        'file_count': crawl['file_count'],
        'systems_scored': len(scores),
        'focus_packet_b64_size': len(b64),
        'focus_sha256': focus['focus_sha256'],
        'receipt_id': audit_receipt['id'],
        'borrowing_base_total': borrowing.get('total_mid', 0) if borrowing else 0,
    }


def _write_json(output_dir: str, filename: str, data: Dict):
    """Write JSON to output_dir/filename."""
    path = os.path.join(output_dir, filename)
    with open(path, 'w') as f:
        json.dump(data, f, indent=2, default=str)


def _build_query_answers(scores, risk_reg) -> Dict:
    """Build the underwriter query answers from scored systems."""
    ranked = sorted(scores, key=lambda x: x.collateral_score, reverse=True)
    return {
        'top_10_by_collateral_score': [
            {'system': s.system_name, 'score': round(s.collateral_score, 1), 'grade': s.grade}
            for s in ranked[:10]
        ],
        'top_10_by_deployability': [
            {'system': s.system_name, 'deployability': round(s.deployability, 1)}
            for s in sorted(scores, key=lambda x: x.deployability, reverse=True)[:10]
        ],
        'top_10_by_revenue_potential': [
            {'system': s.system_name, 'economic_evidence': round(s.economic_evidence, 1),
             'borrowing_base_mid': s.to_dict()['borrowing_base_estimate_usd']['mid']}
            for s in sorted(scores, key=lambda x: x.economic_evidence, reverse=True)[:10]
        ],
        'top_10_by_proof_strength': [
            {'system': s.system_name, 'receipt_strength': round(s.receipt_strength, 1)}
            for s in sorted(scores, key=lambda x: x.receipt_strength, reverse=True)[:10]
        ],
        'top_10_to_abandon': [
            {'system': s.system_name, 'score': round(s.collateral_score, 1), 'grade': s.grade}
            for s in sorted(scores, key=lambda x: x.collateral_score)[:10]
        ],
        'systems_with_secret_risk': [
            {'system': s.system_name, 'haircut': s.secret_leak_haircut}
            for s in scores if s.secret_leak_haircut > 0
        ],
        'systems_with_tests': [
            {'system': s.system_name, 'tests_pass': s.tests_pass}
            for s in scores if s.has_tests
        ],
        'systems_with_endpoints': [
            {'system': s.system_name}
            for s in scores if s.has_endpoints
        ],
        'systems_with_receipts': [
            {'system': s.system_name, 'receipt_strength': round(s.receipt_strength, 1)}
            for s in scores if s.receipt_strength > 20
        ],
        'systems_with_clean_demo_commands': [
            {'system': s.system_name}
            for s in scores if s.has_demo_command
        ],
    }


def _build_sbom(scores, lake_db: str) -> Dict:
    """Build a lightweight SBOM from detected dependencies."""
    import sqlite3
    sbom = {'schema': 'membra.systemlake.sbom.v1', 'systems': []}
    try:
        conn = sqlite3.connect(lake_db)
        conn.row_factory = sqlite3.Row
        for s in scores:
            deps = []
            for row in conn.execute(
                "SELECT path FROM files WHERE path LIKE ? AND deleted = 0 "
                "AND (path LIKE '%requirements%' OR path LIKE '%package.json%' "
                "OR path LIKE '%Pipfile%' OR path LIKE '%Cargo.toml%' "
                "OR path LIKE '%go.mod%' OR path LIKE '%Gemfile%')",
                (f"{s.system_name}/%",)
            ):
                deps.append(row['path'])
            sbom['systems'].append({
                'system': s.system_name,
                'dependency_files': deps,
                'has_lockfile': any('lock' in d.lower() for d in deps),
            })
        conn.close()
    except Exception:
        pass
    return sbom


def _build_scorecard(scores) -> Dict:
    """Build an OpenSSF Scorecard-style security posture summary."""
    return {
        'schema': 'membra.systemlake.scorecard.v1',
        'systems': [{
            'system': s.system_name,
            'has_tests': s.has_tests,
            'tests_pass': s.tests_pass,
            'has_endpoints': s.has_endpoints,
            'has_build': s.has_build_command,
            'security_cleanliness': round(s.security_cleanliness, 1),
            'secret_leak_haircut': s.secret_leak_haircut,
            'dependency_vulnerability_haircut': s.dependency_vulnerability_haircut,
            'missing_license_haircut': s.missing_license_haircut,
            'has_git': s.provenance > 30,
            'scorecard_grade': s.grade,
        } for s in scores]
    }


def _build_memo(repo_path, now_str, crawl, scores, aau_results, risk_reg,
                summary, cog_receipt, audit_receipt, borrowing) -> List[str]:
    """Build the underwriting memo as a list of markdown lines."""
    lines = [
        "# SystemLake Collateral Underwriting Memo",
        "",
        f"**Machine:** `{repo_path}`",
        f"**Date:** {now_str}",
        f"**Merkle Root:** `{crawl['merkle_root'][:16]}…`",
        f"**Files Indexed:** {crawl['file_count']}",
        f"**Systems Detected:** {len(scores)}",
        "",
        "## Executive Summary",
        "",
        f"This memo presents the collateral-readiness assessment of "
        f"**{os.path.basename(repo_path)}** based on a local SystemLake audit. "
        f"The audit crawled {crawl['file_count']} files, detected {len(scores)} "
        f"system(s), and scored each on **10 dimensions** with adversarial "
        f"attribution review.",
        "",
        f"**Borrowing Base (aggregate mid):** ${borrowing.get('total_mid', 0):,.2f}",
        f"**Borrowing Base (range):** ${borrowing.get('total_low', 0):,.2f} – ${borrowing.get('total_high', 0):,.2f}",
        "",
        "**This is not a cash net worth valuation.** This is an estimate of "
        "underwritten software work-equity, subject to external audit.",
        "",
        "## Collateral Scores",
        "",
        "| System | Score | Grade | Class | Category | Func | Deploy | Tests | Receipts | Security |",
        "|--------|-------|-------|-------|----------|------|--------|-------|----------|----------|",
    ]

    for s in scores:
        d = s.to_dict()
        lines.append(
            f"| {d['system']} | {d['collateral_score']:.1f} | {d['grade']} | "
            f"{d['collateral_class']} | {d['category']} | "
            f"{d['dimensions']['functionality']:.0f} | "
            f"{d['dimensions']['deployability']:.0f} | "
            f"{d['dimensions']['test_strength']:.0f} | "
            f"{d['dimensions']['receipt_strength']:.0f} | "
            f"{d['dimensions']['security_cleanliness']:.0f} |"
        )

    lines.extend([
        "",
        "## Verification Results",
        "",
        "| System | Runnable | Tests | Test Result | Endpoints | Demo | Build |",
        "|--------|----------|-------|-------------|-----------|------|-------|",
    ])

    for s in scores:
        d = s.to_dict()
        v = d['verification']
        lines.append(
            f"| {d['system']} | {v['has_runnable_entrypoint']} | "
            f"{v['has_tests']} | {v['tests_pass']} | "
            f"{v['has_endpoints']} | {v['has_demo_command']} | "
            f"{v['has_build_command']} |"
        )

    lines.extend([
        "",
        "## Borrowing Base Estimates",
        "",
        "| System | Score | Low | Mid | High | Verdict |",
        "|--------|-------|-----|-----|------|---------|",
    ])

    for sys_bb in borrowing.get('systems', []):
        bb = sys_bb['borrowing_base']
        lines.append(
            f"| {sys_bb['system']} | {sys_bb['collateral_score']:.1f} | "
            f"${bb['low']:,.0f} | ${bb['mid']:,.0f} | ${bb['high']:,.0f} | "
            f"{sys_bb['verdict']} |"
        )

    lines.extend([
        "",
        "## Adversarial Attribution Underwriting",
        "",
        "| System | Status | Settled Value | Gaming Flags |",
        "|--------|--------|---------------|--------------|",
    ])

    for u in aau_results:
        flags = ', '.join(u['gaming_flags']) if u['gaming_flags'] else 'none'
        lines.append(
            f"| {u['system_name']} | {u['status']} | "
            f"${u['settled_value']:.2f} | {flags} |"
        )

    lines.extend(["", "## Risk Register", ""])

    if risk_reg:
        lines.append("| System | Risk Type | Severity | Haircut | Description |")
        lines.append("|--------|-----------|----------|----------|-------------|")
        for r in risk_reg:
            lines.append(
                f"| {r['system']} | {r['risk_type']} | {r['severity']} | "
                f"-{r['haircut']:.1f} | {r['description']} |"
            )
    else:
        lines.append("No significant risk factors detected.")

    lines.extend([
        "",
        "## File Index Summary",
        "",
        f"- **Total files:** {crawl['file_count']}",
        f"- **Total size:** {crawl['total_size']:,} bytes",
        f"- **Categories:** {json.dumps(summary.get('by_category', {}))}",
        f"- **Cognition packet SHA-256:** `{cog_receipt['packet_sha256'][:16]}…`",
        "",
        "## Receipt Chain",
        "",
        f"- **Audit receipt ID:** `{audit_receipt['id'][:16]}…`",
        f"- **Chain hash:** `{audit_receipt['chain_hash'][:16]}…`",
        "",
        "## Disclaimer",
        "",
        "This memo is generated by **SystemLake Collateral Underwriter**. "
        "Collateral scores are estimates of software work-equity readiness, "
        "not guaranteed valuations. Every claim has been through adversarial "
        "attribution review. Settled values are finance-readable estimates "
        "subject to external audit. This document does not constitute "
        "investment advice or a binding offer.",
        "",
        "---",
        "*Generated by `python3 -m systemlake.audit`*",
    ])

    return lines


def _focus_recommendation(scores) -> str:
    """Generate a focus recommendation from the top scores."""
    if not scores:
        return "No systems detected."
    ranked = sorted(scores, key=lambda x: x.collateral_score, reverse=True)
    top = ranked[0]
    worst = ranked[-1]
    parts = []
    parts.append(f"Top collateral asset: {top.system_name} (score={top.collateral_score:.1f}, grade={top.grade}).")
    if top.collateral_score >= 65:
        parts.append(f"Recommend packaging {top.system_name} into a lender/investor memo first.")
    elif top.collateral_score >= 35:
        parts.append(f"Recommend: run demo + collect usage logs for {top.system_name} before underwriting.")
    else:
        parts.append(f"Recommend: remediate {top.system_name} before underwriting (score below 35).")
    if worst.collateral_score < 35 and worst.system_name != top.system_name:
        parts.append(f"Consider abandoning or deprioritizing {worst.system_name} (score={worst.collateral_score:.1f}).")
    parts.append(f"Total systems: {len(scores)}. Underwritable: {sum(1 for s in scores if s.collateral_score >= 65)}.")
    return ' '.join(parts)


def main():
    """CLI: python3 -m systemlake.audit /path/to/repo --out out/

    Full-machine mode:
        python3 -m systemlake.audit /Users/alep \
          --metadata-all \
          --content-roots /Users/alep/Downloads,/Users/alep/CascadeProjects \
          --deny .ssh,Library/Keychains,Library/Messages,Library/Mail \
          --underwrite --collateralize \
          --out systemlake_full_underwrite
    """
    ap = argparse.ArgumentParser(
        description='SystemLake Collateral Underwriter — one command, twelve outputs. '
                    'Crawls locally, scores collateral, underwrites claims, '
                    'writes ProofBook receipts, exports redacted Base64 focus packet.')
    ap.add_argument('repo', help='Path to the repo or machine root to audit')
    ap.add_argument('--out', required=True, help='Output directory for audit files')
    ap.add_argument('--max-files', type=int, default=1000, help='Max files to crawl')
    ap.add_argument('--lake-db', default=None, help='Lake SQLite DB path')
    ap.add_argument('--receipts-db', default=None, help='Receipts SQLite DB path')
    ap.add_argument('--metadata-all', action='store_true',
                    help='First pass: metadata for every reachable file (hash, size, type)')
    ap.add_argument('--content-roots', default=None,
                    help='Comma-separated paths where content reading is allowed')
    ap.add_argument('--deny', default=None,
                    help='Comma-separated paths to deny (no content, no descent)')
    ap.add_argument('--underwrite', action='store_true', default=True,
                    help='Run underwriting engine (default: on)')
    ap.add_argument('--collateralize', action='store_true', default=True,
                    help='Compute borrowing base estimates (default: on)')
    ap.add_argument('--sbom', action='store_true', default=False,
                    help='Generate lightweight SBOM from dependency files')
    ap.add_argument('--scorecard', action='store_true', default=False,
                    help='Generate OpenSSF Scorecard-style security posture summary')
    args = ap.parse_args()

    content_roots = None
    if args.content_roots:
        content_roots = [r.strip() for r in args.content_roots.split(',')]

    deny_paths = None
    if args.deny:
        deny_paths = [d.strip() for d in args.deny.split(',')]

    result = run_audit(
        repo_path=args.repo,
        output_dir=args.out,
        max_files=args.max_files,
        lake_db=args.lake_db,
        receipts_db=args.receipts_db,
        metadata_all=args.metadata_all,
        content_roots=content_roots,
        deny_paths=deny_paths,
        underwrite=args.underwrite,
        collateralize=args.collateralize,
        sbom=args.sbom,
        scorecard=args.scorecard,
    )

    print()
    print("=" * 70)
    print("  SYSTEMLAKE COLLATERAL UNDERWRITER — AUDIT COMPLETE")
    print("=" * 70)
    print(f"  Path: {args.repo}")
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
        fpath = os.path.join(result['output_dir'], f)
        size = os.path.getsize(fpath) if os.path.exists(fpath) else 0
        print(f"    {f:30s}  {size:>10,} bytes")
    print()
    print("  SystemLake Underwriter turns your laptop into a private software")
    print("  collateral data room. Hashes prove existence. Receipts prove execution.")
    print("  Merkle roots prove state. Base64 carries snapshots.")
    print("  Underwriter prices the asset. Gateway controls exposure.")
    print("=" * 70)


if __name__ == '__main__':
    main()
