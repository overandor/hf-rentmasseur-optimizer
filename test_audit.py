"""Test systemlake.audit — one command, five outputs."""
import os
import json
import shutil
import tempfile

# Create test repo
test_dir = tempfile.mkdtemp(prefix='audit_test_')
repo = os.path.join(test_dir, 'test_repo')
os.makedirs(repo, exist_ok=True)

with open(os.path.join(repo, 'app.py'), 'w') as f:
    f.write('from fastapi import FastAPI\napp = FastAPI()\n\n@app.get("/health")\ndef health():\n    return {"status": "ok"}\n')

with open(os.path.join(repo, 'test_app.py'), 'w') as f:
    f.write('def test_health():\n    assert True\n')

with open(os.path.join(repo, 'requirements.txt'), 'w') as f:
    f.write('fastapi\nuvicorn\n')

with open(os.path.join(repo, 'README.md'), 'w') as f:
    f.write('# Test Repo\n')

with open(os.path.join(repo, 'LICENSE'), 'w') as f:
    f.write('MIT License\n')

with open(os.path.join(repo, '.env'), 'w') as f:
    f.write('API_KEY=sk-test1234567890abcdef\n')

print(f"[1] Test repo: {repo}")

# Run audit
from systemlake.audit import run_audit

out_dir = os.path.join(test_dir, 'audit_out')
result = run_audit(repo_path=repo, output_dir=out_dir)

print(f"[2] Audit complete:")
print(f"    Merkle root: {result['merkle_root'][:16]}")
print(f"    Files: {result['file_count']}")
print(f"    Systems: {result['systems_scored']}")
print(f"    Focus packet: {result['focus_packet_b64_size']} chars")

# Verify all 12 outputs exist
expected = ['machine_manifest.json', 'merkle_root.json',
            'systems.json', 'proofbook.jsonl',
            'underwriting_memo.md', 'collateral_scores.json',
            'risk_register.json', 'focus_packet.json',
            'focus_packet.b64', 'receipt.json',
            'verification_results.json', 'underwriting_scores.json',
            'borrowing_base.json']

print(f"[3] Verifying outputs:")
for name in expected:
    path = os.path.join(out_dir, name)
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    print(f"    {name:30s}  {'OK' if exists else 'MISSING':>4s}  {size:>8,} bytes")
    assert exists, f"{name} should exist"

# Verify machine_manifest
with open(os.path.join(out_dir, 'machine_manifest.json')) as f:
    manifest = json.load(f)
assert manifest['schema'] == 'membra.systemlake.machine_manifest.v1'
assert manifest['merkle_root']
assert manifest['file_count'] > 0
print(f"[4] Manifest schema: {manifest['schema']}")

# Verify proofbook is valid JSONL with chain
with open(os.path.join(out_dir, 'proofbook.jsonl')) as f:
    lines = [json.loads(l) for l in f if l.strip()]
assert len(lines) > 0, "ProofBook should have entries"
prev = None
for entry in lines:
    if prev:
        assert entry['previous_entry_hash'] == prev, "Chain should be linked"
    prev = entry['entry_hash']
print(f"[5] ProofBook: {len(lines)} entries, chain linked")

# Verify memo is markdown
with open(os.path.join(out_dir, 'underwriting_memo.md')) as f:
    memo = f.read()
assert '# SystemLake Collateral Underwriting Memo' in memo
assert 'Collateral Scores' in memo
assert 'Adversarial Attribution' in memo
assert 'Disclaimer' in memo
print(f"[6] Memo: {len(memo)} chars, has all sections")

# Verify collateral_scores.json
with open(os.path.join(out_dir, 'collateral_scores.json')) as f:
    cs = json.load(f)
assert cs['schema'] == 'membra.systemlake.collateral_scores.v1'
assert len(cs['systems']) > 0
assert cs['settlement_chain']['valid']
print(f"[7] Collateral scores: {len(cs['systems'])} systems, chain valid")

# Verify focus_packet.b64 decodes
import base64, zlib
with open(os.path.join(out_dir, 'focus_packet.b64')) as f:
    b64 = f.read()
raw = zlib.decompress(base64.b64decode(b64))
focus = json.loads(raw)
assert focus['schema'] == 'membra.systemlake.underwriting_packet.v1'
assert focus['merkle_root']
assert focus['focus_sha256']
print(f"[8] Focus packet: schema={focus['schema']}, sha256={focus['focus_sha256'][:16]}")

# Verify raw files not included
assert focus.get('raw_files_included') == False, "Raw files must not be in packet"
print(f"[9] Raw files excluded: {focus['raw_files_included']}")

# Verify borrowing_base
with open(os.path.join(out_dir, 'borrowing_base.json')) as f:
    bb = json.load(f)
assert 'total_mid' in bb, "Borrowing base should have total_mid"
print(f"[10] Borrowing base: low=${bb['total_low']:.0f} mid=${bb['total_mid']:.0f} high=${bb['total_high']:.0f}")

# Verify verification_results
with open(os.path.join(out_dir, 'verification_results.json')) as f:
    vr = json.load(f)
assert vr['schema'] == 'membra.systemlake.verification.v1'
print(f"[11] Verification: {len(vr['systems'])} systems checked")

# Cleanup
shutil.rmtree(test_dir, ignore_errors=True)

print()
print("=" * 70)
print("  SYSTEMLAKE AUDIT TEST COMPLETE")
print("=" * 70)
print()
print("  One command: python3 -m systemlake.audit /path/to/repo --out out/")
print("  Thirteen outputs:")
print("    machine_manifest.json     — full machine map, merkle root")
print("    merkle_root.json          — Merkle tree root hash")
print("    systems.json              — all detected systems")
print("    proofbook.jsonl           — hash-chained receipt ledger")
print("    underwriting_memo.md      — lender-grade markdown memo")
print("    collateral_scores.json    — collateral + AAU settlements")
print("    risk_register.json        — standalone risk register")
print("    focus_packet.json         — full underwriting projection")
print("    focus_packet.b64          — compressed Base64 for LLM audit")
print("    receipt.json              — receipt proving audit occurred")
print("    verification_results.json — runnable/test/endpoint checks")
print("    underwriting_scores.json  — 10-dimension scores per system")
print("    borrowing_base.json       — low/mid/high USD estimates")
print()
print("  All verified:")
print("  - All 13 files written")
print("  - Machine manifest has correct schema")
print("  - ProofBook chain is linked and valid")
print("  - Memo has all required sections")
print("  - Collateral scores have settlement chain")
print("  - Focus packet decodes to valid JSON")
print("  - Raw files excluded from packet")
print("  - Borrowing base has low/mid/high estimates")
print("  - Verification results present")
print("  - Risk register present")
print("=" * 70)
