"""Test script for RECEPT language — interpreter, transpiler, receipts."""
import py_compile
import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from membra_gpt.recept.interpreter import run_source
from membra_gpt.recept.transpiler import transpile_source

_source_path = os.path.join(os.path.dirname(__file__), 'example.recept')
source = open(_source_path).read()

# 1. Interpreter
result = run_source(source, receipts_dir='/tmp/recept_test_receipts')
print(f"Interpreter: capsule={result['capsule']} endpoints={len(result['endpoints'])} "
      f"workflows={len(result['workflows'])} functions={len(result['functions'])} "
      f"receipts={len(result['receipts'])} errors={len(result['errors'])}")

# 2. Transpiler
capsule_dir = transpile_source(source, output_dir='/tmp/recept_capsules')
py_compile.compile(os.path.join(capsule_dir, 'app.py'), doraise=True)
print(f"Transpiler: {capsule_dir} compiles OK")

# 3. Receipts
receipts = sorted(os.listdir('/tmp/recept_test_receipts'))
for r in receipts:
    with open(os.path.join('/tmp/recept_test_receipts', r)) as f:
        data = json.load(f)
    prev = data['previous_receipt'][:8] if data['previous_receipt'] else 'none'
    print(f"  receipt: id={data['receipt_id'][:8]} prev={prev} hash={data['artifact_hash'][:16]}")

print("\nAll tests passed.")
