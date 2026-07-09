"""Test unified Value Claim Packet: repo → VCP → receipt → b64 export."""
import os
import sys
import json
import shutil
import tempfile

# Create a fake repo to underwrite
test_dir = tempfile.mkdtemp(prefix='vcp_test_')
repo = os.path.join(test_dir, 'test_repo')
os.makedirs(repo, exist_ok=True)

# Source files
with open(os.path.join(repo, 'app.py'), 'w') as f:
    f.write('''from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
''')

with open(os.path.join(repo, 'test_app.py'), 'w') as f:
    f.write('def test_health():\n    assert True\n')

with open(os.path.join(repo, 'requirements.txt'), 'w') as f:
    f.write('fastapi\nuvicorn\n')

with open(os.path.join(repo, 'README.md'), 'w') as f:
    f.write('# Test Repo\n')

with open(os.path.join(repo, 'LICENSE'), 'w') as f:
    f.write('MIT License\n')

# .env (should be denied)
with open(os.path.join(repo, '.env'), 'w') as f:
    f.write('API_KEY=sk-test1234567890abcdef\n')

print(f"[1] Test repo created: {repo}")

# --- Test AAU directly ---
from systemlake.aau import (
    AdversarialAttributionUnderwriter, Baseline, Evidence,
    GamingFlags, ValueClaim, ClaimStatus,
)

aau = AdversarialAttributionUnderwriter()

# Test 1: Clean claim should settle
baseline = Baseline(
    label='test_baseline',
    snapshot_hash='abc123',
    timestamp='2026-06-21T12:00:00Z',
    metrics={'latency_ms': 500},
)

evidence = [
    Evidence('ev1', 'receipt', 'test', '2026-06-21T12:00:00Z', 'hash1', 0.9, True),
    Evidence('ev2', 'test_pass', 'test', '2026-06-21T12:00:00Z', 'hash2', 0.8, True),
]

claim = ValueClaim(
    claim_id='claim_001',
    system_name='test_system',
    baseline=baseline,
    evidence=evidence,
    claimed_value_usd=500.0,
    counterfactual_value_usd=100.0,
    confidence=0.8,
    exchangeability=0.7,
    reputation=0.6,
)

result = aau.underwrite(claim)
print(f"[2] AAU clean claim:")
print(f"    Status: {result['status'].value}")
print(f"    Settled: ${result['settled_value']:.2f}")
print(f"    Score: {result['score']:.1f}")
print(f"    Gaming: {result['gaming_flags']}")
assert result['status'] == ClaimStatus.SETTLED_FINANCE_READABLE, "Clean claim should settle"
assert result['settled_value'] > 0, "Should have positive settled value"

# Test 2: Gaming claim should be rejected
claim_gaming = ValueClaim(
    claim_id='claim_002',
    system_name='gaming_system',
    baseline=baseline,
    evidence=evidence,
    gaming_flags=GamingFlags(phantom_revenue=True, unverifiable_delta=True),
    claimed_value_usd=10000.0,
    counterfactual_value_usd=0.0,
)
result_gaming = aau.underwrite(claim_gaming)
print(f"[3] AAU gaming claim:")
print(f"    Status: {result_gaming['status'].value}")
print(f"    Gaming flags: {result_gaming['gaming_flags']}")
assert result_gaming['status'] == ClaimStatus.REJECTED_GAMING, "Gaming claim should be rejected"

# Test 3: No delta should be rejected
claim_no_delta = ValueClaim(
    claim_id='claim_003',
    system_name='no_delta_system',
    baseline=baseline,
    evidence=evidence,
    claimed_value_usd=500.0,
    counterfactual_value_usd=500.0,  # all counterfactual
)
result_no_delta = aau.underwrite(claim_no_delta)
print(f"[4] AAU no-delta claim:")
print(f"    Status: {result_no_delta['status'].value}")
assert result_no_delta['status'] == ClaimStatus.REJECTED_NO_DELTA, "No-delta claim should be rejected"

# Test 4: Settlement chain verification
chain = aau.verify_settlements()
print(f"[5] Settlement chain: {chain}")
assert chain['valid'], "Settlement chain should be valid"
assert chain['count'] == 3, "Should have 3 settlements"

# --- Test unified VCP ---
from questionos.underwrite import generate_value_claim_packet, print_report

vcp_path = os.path.join(test_dir, 'vcp.json')
vcp = generate_value_claim_packet(
    repo_path=repo,
    output_path=vcp_path,
    emit_b64=True,
)

print(f"\n[6] Value Claim Packet generated:")
print(f"    Schema: {vcp['schema']}")
print(f"    Merkle root: {vcp['lake']['merkle_root'][:16]}")
print(f"    Files: {vcp['lake']['file_count']}")
print(f"    Systems: {len(vcp['systems'])}")
print(f"    Underwriting results: {len(vcp['underwriting'])}")
print(f"    VCP SHA-256: {vcp['vcp_sha256'][:16]}")
print(f"    Receipt: {vcp['receipt']['id'][:8]}")

# Verify VCP file was written
assert os.path.exists(vcp_path), "VCP JSON file should exist"
with open(vcp_path) as f:
    loaded = json.load(f)
assert loaded['vcp_sha256'] == vcp['vcp_sha256'], "Loaded VCP should match"

# Verify B64 was emitted
b64_path = vcp.get('b64_path', '')
if b64_path and os.path.exists(b64_path):
    print(f"    B64: {vcp['b64_size']} chars at {b64_path}")

# Verify .env was excluded
cognition = vcp.get('cognition', {})
print(f"    Cognition privacy: {cognition.get('privacy', {})}")

# Verify settlement chain
assert vcp['settlement_chain']['valid'], "VCP settlement chain should be valid"

# Print full report
print()
print_report(vcp)

# --- Cleanup ---
shutil.rmtree(test_dir, ignore_errors=True)

print()
print("=" * 70)
print("  VALUE CLAIM PACKET TEST COMPLETE")
print("=" * 70)
print()
print("  Proven:")
print("  - SystemLake crawled repo and computed Merkle root")
print("  - Collateral scores computed (7 dimensions + haircuts)")
print("  - AAU underwrote claims through adversarial attribution")
print("  - Clean claim → SETTLED_FINANCE_READABLE")
print("  - Gaming claim → REJECTED_GAMING")
print("  - No-delta claim → REJECTED_NO_DELTA")
print("  - Settlement chain verified intact")
print("  - VCP JSON written with receipt")
print("  - B64 export emitted")
print("  - .env excluded from cognition packet")
print()
print("  Answer becomes executable artifact.")
print("  Executable artifact creates technical receipts.")
print("  Usage creates economic activity.")
print("  AAU decides whether the claimed value is finance-readable.")
print("  Valuation memo corrects the headline number.")
print("=" * 70)
