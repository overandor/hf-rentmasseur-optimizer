"""QuestionOS end-to-end test."""
import os
import sys
import json
import shutil

# Clean test dir
test_dir = '/tmp/questionos_test'
if os.path.exists(test_dir):
    shutil.rmtree(test_dir)

from questionos.qrc_engine import QRCEngine
from questionos.shadow_sync import ShadowSync

# 1. Create engine
engine = QRCEngine(base_dir=test_dir)
print("1. Engine created")

# 2. Ask a question
session = engine.ask(
    "How do I optimize my FastAPI endpoint for high throughput?",
    project="myapp"
)
print(f"2. Question asked: session={session.session_id[:8]} intent={session.intent_class}")

# 3. Write a file in the session
engine.write_file(session, 'solution.py', '''
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
''')
print(f"3. File written: solution.py")

# 4. Write a test file
engine.write_file(session, 'test_solution.py', '''
def test_health():
    assert True
''')
print("4. Test file written: test_solution.py")

# 5. Run tests
test_result = engine.run_tests(session)
print(f"5. Tests: ran={test_result['ran']} passed={test_result.get('passed')}")

# 6. Run a command
cmd_result = engine.run_command(session, 'echo "optimization complete"')
print(f"6. Command: rc={cmd_result['returncode']}")

# 7. Compress the session
compress_result = engine.compress(session)
print(f"7. Compressed: {compress_result['compressed']}")
print(f"   Dataset: {compress_result['dataset_path']}")
print(f"   Files preserved: {len(compress_result['residue']['files'])}")
print(f"   Commands: {len(compress_result['residue']['commands'])}")

# 8. Check ledgers
q_summary = engine.question_ledger.summary()
e_summary = engine.execution_ledger.summary()
c_summary = engine.cost_ledger.summary()
print(f"8. Ledgers:")
print(f"   Questions: {q_summary['total_questions']} (compressed: {q_summary['compressed']})")
print(f"   Executions: {e_summary['total_events']} events ({e_summary['failures']} failures)")
print(f"   Cost avoidance: ${c_summary['total_estimated_usd']}")

# 9. Export snapshot
sync = ShadowSync(base_dir=test_dir)
manifest = sync.export_snapshot(label="test_snapshot")
print(f"9. Snapshot exported: {manifest['snapshot_id'][:30]}")
print(f"   Tarball: {manifest['tarball_size']} bytes")
print(f"   Hash: {manifest['snapshot_hash'][:16]}")
print(f"   Components: {list(manifest['components'].keys())}")

# 10. List snapshots
snapshots = sync.list_snapshots()
print(f"10. Snapshots: {len(snapshots)}")

# 11. Verify receipts
receipts_dir = os.path.join(test_dir, 'receipts')
receipts = os.listdir(receipts_dir)
print(f"11. Receipts written: {len(receipts)}")
for r in sorted(receipts):
    with open(os.path.join(receipts_dir, r)) as f:
        data = json.load(f)
    prev = data.get('previous_receipt', '')[:8] if data.get('previous_receipt') else 'none'
    print(f"    {data['action']:25s} hash={data['artifact_hash'][:16]} prev={prev}")

# 12. Verify cost avoidance report
report = engine.cost_ledger.report()
print(f"12. Cost report:")
for line in report.split('\n'):
    print(f"    {line}")

print("\n=== All tests passed ===")
