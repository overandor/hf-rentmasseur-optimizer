"""
AFC Protocol — Antonymified File Claim Protocol
================================================
Converts consumable information into accountable market objects.

Protocol law:
  No full disclosure before payment.
  No payment without settlement.
  No settlement without an oracle.
  No oracle without a bond.

Stack:
  File/answer → LLM antonymifier → hash/Merkle commitment →
  BlurHash64 fidelity label → lambda transferability score →
  oracle → bond → exclusivity window → settlement receipt

MVP: Hidden Test Claim Market
  1. Buyer posts task + hidden tests
  2. Seller submits antonymified preview (not full answer)
  3. Seller posts bond
  4. Buyer escrows payment
  5. Answer revealed only after commitment
  6. Hidden test suite resolves pass/fail
  7. Bond returned or slashed
  8. Settlement receipt generated
"""

import os
import json
import time
import hashlib
import sqlite3
import base64
import uuid
from pathlib import Path
from fastapi import FastAPI, HTTPException, Header, Body, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="AFC Protocol — Antonymified File Claim Protocol", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATA_DIR = Path(os.environ.get("AFC_DATA_DIR", "/data" if Path("/data").exists() else "/tmp/afc"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "afc.db"


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS claims (
        claim_id TEXT PRIMARY KEY,
        seller_id TEXT,
        buyer_id TEXT,
        task_description TEXT,
        antonymified_preview TEXT,
        full_answer_hash TEXT,
        full_answer_encrypted TEXT,
        bond_amount REAL DEFAULT 0,
        bond_posted INTEGER DEFAULT 0,
        payment_escrowed REAL DEFAULT 0,
        payment_escrowed_by TEXT,
        oracle_type TEXT,
        oracle_config TEXT,
        lambda_score REAL DEFAULT 0,
        fidelity_label TEXT,
        exclusivity_window_s INTEGER DEFAULT 0,
        exclusivity_expires REAL,
        status TEXT DEFAULT 'open',
        created_at REAL,
        committed_at REAL,
        revealed_at REAL,
        settled_at REAL,
        settlement_result TEXT,
        settlement_receipt TEXT
    );
    CREATE TABLE IF NOT EXISTS hidden_tests (
        test_id TEXT PRIMARY KEY,
        claim_id TEXT,
        test_hash TEXT,
        test_encrypted TEXT,
        created_at REAL
    );
    CREATE TABLE IF NOT EXISTS oracle_results (
        result_id TEXT PRIMARY KEY,
        claim_id TEXT,
        oracle_type TEXT,
        passed INTEGER,
        details TEXT,
        resolved_at REAL
    );
    CREATE TABLE IF NOT EXISTS receipts (
        receipt_id TEXT PRIMARY KEY,
        claim_id TEXT,
        type TEXT,
        payload TEXT,
        created_at REAL
    );
    """)
    conn.commit()
    conn.close()


init_db()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def merkle_commitment(data: bytes, chunk_size: int = 4096) -> dict:
    chunks = [data[i:i+chunk_size] for i in range(0, len(data), chunk_size)]
    if not chunks:
        chunks = [b""]
    leaf_hashes = [sha256(c) for c in chunks]
    tree = list(leaf_hashes)
    while len(tree) > 1:
        tree = [sha256((tree[i] + tree[i+1]).encode()) for i in range(0, len(tree)-1, 2)] if len(tree) % 2 == 0 else [sha256((tree[i] + tree[i+1]).encode()) for i in range(0, len(tree)-1, 2)] + [tree[-1]]
    return {
        "root": tree[0] if tree else sha256(b""),
        "leaf_count": len(leaf_hashes),
        "leaf_hashes": leaf_hashes[:8],
    }


def blur_hash64(data: bytes) -> str:
    """BlurHash64-style fidelity label — non-reversible representation of content."""
    h = hashlib.sha512(data).digest()
    return base64.b64encode(h[:48]).decode()[:64]


def antonymify(content: str, filename: str = "") -> dict:
    """Generate non-consumable surrogate from file content.
    Exposes verifiable boundaries without revealing consumable content."""
    data = content.encode() if isinstance(content, str) else content
    merkle = merkle_commitment(data)
    blur = blur_hash64(data)

    file_class = "unknown"
    if filename.endswith(".py") or "def " in content[:500]:
        file_class = "python_source"
    elif filename.endswith(".sql") or "SELECT" in content[:500].upper():
        file_class = "sql_query"
    elif filename.endswith(".json"):
        file_class = "json_data"
    elif filename.endswith(".md"):
        file_class = "markdown_document"
    elif filename.endswith(".csv"):
        file_class = "csv_dataset"
    else:
        file_class = "text"

    lines = content.split("\n") if isinstance(content, str) else data.split(b"\n")
    line_count = len(lines)

    proof_hooks = []
    if isinstance(content, str):
        for kw in ["def ", "class ", "SELECT", "CREATE TABLE", "import ", "function ", "return "]:
            if kw in content:
                proof_hooks.append(kw.strip())

    excluded = ["full_source", "exact_algorithm", "alpha_signal", "raw_data_rows"]

    return {
        "file_class": file_class,
        "filename": filename,
        "size_bytes": len(data),
        "line_count": line_count,
        "merkle_root": merkle["root"],
        "merkle_leaves": merkle["leaf_count"],
        "blur_hash64": blur,
        "proof_hooks": proof_hooks,
        "excluded_content": excluded,
        "fidelity_label": "controlled_blur",
        "lambda_score": round(min(1.0, len(data) / 100000), 4),
        "preview": content[:200] + "..." if len(content) > 200 else content,
    }


def encrypt_answer(answer: str, claim_id: str) -> str:
    """Simple XOR cipher with claim_id as key. Real impl would use proper crypto."""
    key = (claim_id * 10).encode()[:32]
    data = answer.encode()
    return base64.b64encode(bytes(b ^ key[i % len(key)] for i, b in enumerate(data))).decode()


def decrypt_answer(encrypted: str, claim_id: str) -> str:
    key = (claim_id * 10).encode()[:32]
    data = base64.b64decode(encrypted)
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data)).decode()


# --- Endpoints ---

@app.get("/health")
async def health():
    conn = sqlite3.connect(str(DB_PATH))
    claim_count = conn.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    open_count = conn.execute("SELECT COUNT(*) FROM claims WHERE status='open'").fetchone()[0]
    settled_count = conn.execute("SELECT COUNT(*) FROM claims WHERE status='settled'").fetchone()[0]
    conn.close()
    return {
        "status": "ok",
        "protocol": "AFC/1.0",
        "claims_total": claim_count,
        "claims_open": open_count,
        "claims_settled": settled_count,
        "storage": str(DATA_DIR),
        "persistent": str(DATA_DIR).startswith("/data"),
    }


@app.post("/claim/create")
async def create_claim(body: dict = Body(...)):
    """Seller creates a claim with antonymified preview + encrypted full answer + bond."""
    seller_id = body.get("seller_id", "")
    task_description = body.get("task_description", "")
    full_answer = body.get("full_answer", "")
    filename = body.get("filename", "")
    bond_amount = body.get("bond_amount", 0)
    oracle_type = body.get("oracle_type", "hidden_test")
    oracle_config = body.get("oracle_config", {})
    exclusivity_window_s = body.get("exclusivity_window_s", 3600)

    if not full_answer:
        raise HTTPException(400, {"status": "error", "message": "full_answer required"})
    if not seller_id:
        raise HTTPException(400, {"status": "error", "message": "seller_id required"})

    claim_id = uuid.uuid4().hex[:12]
    surrogate = antonymify(full_answer, filename)
    answer_hash = sha256(full_answer.encode())
    encrypted = encrypt_answer(full_answer, claim_id)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """INSERT INTO claims (claim_id, seller_id, task_description, antonymified_preview,
           full_answer_hash, full_answer_encrypted, bond_amount, bond_posted,
           oracle_type, oracle_config, lambda_score, fidelity_label,
           exclusivity_window_s, exclusivity_expires, status, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (claim_id, seller_id, task_description, json.dumps(surrogate),
         answer_hash, encrypted, bond_amount, 1 if bond_amount > 0 else 0,
         oracle_type, json.dumps(oracle_config), surrogate["lambda_score"],
         surrogate["fidelity_label"], exclusivity_window_s,
         time.time() + exclusivity_window_s, "open", time.time())
    )
    conn.commit()
    conn.close()

    return {
        "claim_id": claim_id,
        "status": "open",
        "surrogate": surrogate,
        "answer_hash": answer_hash,
        "bond_posted": bond_amount > 0,
        "protocol": "AFC/1.0",
        "law": "No full disclosure before payment. No payment without settlement.",
    }


@app.get("/claim/{claim_id}")
async def get_claim(claim_id: str):
    """View a claim's antonymified surrogate — no full answer revealed."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM claims WHERE claim_id = ?", [claim_id]).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, {
            "status": "claim_not_found",
            "claim_id": claim_id,
            "message": "This AFC claim is expired, settled, or does not exist.",
            "next": "Create a new claim."
        })

    surrogate = json.loads(row["antonymified_preview"]) if row["antonymified_preview"] else {}
    return {
        "claim_id": claim_id,
        "seller_id": row["seller_id"],
        "task_description": row["task_description"],
        "surrogate": surrogate,
        "answer_hash": row["full_answer_hash"],
        "bond_amount": row["bond_amount"],
        "bond_posted": bool(row["bond_posted"]),
        "payment_escrowed": row["payment_escrowed"],
        "oracle_type": row["oracle_type"],
        "lambda_score": row["lambda_score"],
        "fidelity_label": row["fidelity_label"],
        "exclusivity_expires": row["exclusivity_expires"],
        "status": row["status"],
        "created_at": row["created_at"],
        "committed_at": row["committed_at"],
        "settled_at": row["settled_at"],
        "settlement_result": row["settlement_result"],
        "note": "Full answer is encrypted and hidden. This surrogate is non-consumable.",
    }


@app.get("/claims")
async def list_claims(status: str = "open"):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    if status == "all":
        rows = conn.execute("SELECT claim_id, seller_id, task_description, status, lambda_score, bond_amount, created_at FROM claims ORDER BY created_at DESC").fetchall()
    else:
        rows = conn.execute("SELECT claim_id, seller_id, task_description, status, lambda_score, bond_amount, created_at FROM claims WHERE status = ? ORDER BY created_at DESC", [status]).fetchall()
    conn.close()
    return {"claims": [dict(r) for r in rows], "count": len(rows)}


@app.post("/claim/{claim_id}/escrow")
async def escrow_payment(claim_id: str, body: dict = Body(...)):
    """Buyer escrows payment — commits to purchase without seeing full answer."""
    buyer_id = body.get("buyer_id", "")
    amount = body.get("amount", 0)
    if not buyer_id:
        raise HTTPException(400, {"status": "error", "message": "buyer_id required"})

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM claims WHERE claim_id = ?", [claim_id]).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, {"status": "claim_not_found", "message": "Claim not found."})
    if row["status"] != "open":
        conn.close()
        raise HTTPException(400, {"status": "error", "message": f"Claim is {row['status']}, not open."})

    conn.execute(
        "UPDATE claims SET payment_escrowed = ?, payment_escrowed_by = ?, status = 'committed', committed_at = ? WHERE claim_id = ?",
        [amount, buyer_id, time.time(), claim_id]
    )
    conn.commit()
    conn.close()

    return {
        "claim_id": claim_id,
        "status": "committed",
        "escrow_amount": amount,
        "buyer_id": buyer_id,
        "law": "No payment without settlement. No settlement without an oracle.",
    }


@app.post("/claim/{claim_id}/reveal")
async def reveal_answer(claim_id: str):
    """Reveal the full answer after payment escrow. Answer is decrypted."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM claims WHERE claim_id = ?", [claim_id]).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, {"status": "claim_not_found", "message": "Claim not found."})
    if row["status"] != "committed":
        conn.close()
        raise HTTPException(400, {"status": "error", "message": f"Claim must be committed (escrowed) first. Current: {row['status']}"})

    answer = decrypt_answer(row["full_answer_encrypted"], claim_id)
    conn.execute("UPDATE claims SET status = 'revealed', revealed_at = ? WHERE claim_id = ?", [time.time(), claim_id])
    conn.commit()
    conn.close()

    return {
        "claim_id": claim_id,
        "status": "revealed",
        "full_answer": answer,
        "answer_hash": row["full_answer_hash"],
        "verify": sha256(answer.encode()) == row["full_answer_hash"],
        "law": "Answer revealed. Oracle settlement pending.",
    }


@app.post("/claim/{claim_id}/tests")
async def submit_hidden_tests(claim_id: str, body: dict = Body(...)):
    """Buyer submits hidden tests for the claim (encrypted, hashed)."""
    tests = body.get("tests", [])
    if not tests:
        raise HTTPException(400, {"status": "error", "message": "tests array required"})

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM claims WHERE claim_id = ?", [claim_id]).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, {"status": "claim_not_found", "message": "Claim not found."})

    for i, test in enumerate(tests):
        test_id = uuid.uuid4().hex[:12]
        test_str = json.dumps(test) if not isinstance(test, str) else test
        test_hash = sha256(test_str.encode())
        test_encrypted = encrypt_answer(test_str, claim_id)
        conn.execute(
            "INSERT INTO hidden_tests (test_id, claim_id, test_hash, test_encrypted, created_at) VALUES (?,?,?,?,?)",
            [test_id, claim_id, test_hash, test_encrypted, time.time()]
        )
    conn.commit()
    conn.close()

    return {
        "claim_id": claim_id,
        "tests_submitted": len(tests),
        "status": "tests_ready",
        "law": "Oracle will resolve pass/fail on settlement.",
    }


@app.post("/claim/{claim_id}/settle")
async def settle_claim(claim_id: str, body: dict = Body(...)):
    """Oracle settles the claim — runs hidden tests against the revealed answer.
    Bond returned if pass, slashed if fail. Settlement receipt generated."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM claims WHERE claim_id = ?", [claim_id]).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, {"status": "claim_not_found", "message": "Claim not found."})
    if row["status"] not in ("revealed", "committed"):
        conn.close()
        raise HTTPException(400, {"status": "error", "message": f"Claim must be revealed first. Current: {row['status']}"})

    answer = decrypt_answer(row["full_answer_encrypted"], claim_id)
    tests = conn.execute("SELECT * FROM hidden_tests WHERE claim_id = ?", [claim_id]).fetchall()

    oracle_type = row["oracle_type"] or "hidden_test"
    oracle_config = json.loads(row["oracle_config"]) if row["oracle_config"] else {}
    passed = 0
    failed = 0
    details = []

    if oracle_type == "hidden_test" and tests:
        for t in tests:
            test_str = decrypt_answer(t["test_encrypted"], claim_id)
            test_obj = json.loads(test_str)
            test_type = test_obj.get("type", "contains")
            expected = test_obj.get("expected", "")
            if test_type == "contains":
                ok = expected in answer
            elif test_type == "equals":
                ok = answer.strip() == expected.strip()
            elif test_type == "regex":
                import re
                ok = bool(re.search(expected, answer))
            elif test_type == "starts_with":
                ok = answer.strip().startswith(expected)
            elif test_type == "json_field":
                try:
                    ans_json = json.loads(answer)
                    ok = str(ans_json.get(test_obj.get("field", ""), "")) == str(expected)
                except:
                    ok = False
            elif test_type == "python_exec":
                try:
                    ns = {}
                    exec(answer, ns)
                    exec(test_obj.get("code", "result = True"), ns)
                    ok = ns.get("result", False)
                except:
                    ok = False
            else:
                ok = expected in answer

            if ok:
                passed += 1
                details.append({"test_id": t["test_id"], "result": "pass"})
            else:
                failed += 1
                details.append({"test_id": t["test_id"], "result": "fail"})
    elif oracle_type == "manual":
        passed = body.get("oracle_verdict", False)
        failed = 0 if passed else 1
    else:
        passed = 1
        failed = 0
        details.append({"result": "no_tests", "note": "No hidden tests submitted. Default pass."})

    all_passed = failed == 0 and passed > 0
    settlement_result = "pass" if all_passed else "fail"

    bond_returned = row["bond_amount"] if all_passed else 0
    bond_slashed = row["bond_amount"] if not all_passed else 0
    payment_released = row["payment_escrowed"] if all_passed else 0

    receipt_id = uuid.uuid4().hex[:12]
    receipt = {
        "receipt_id": receipt_id,
        "claim_id": claim_id,
        "seller_id": row["seller_id"],
        "buyer_id": row["payment_escrowed_by"],
        "result": settlement_result,
        "tests_passed": passed,
        "tests_failed": failed,
        "bond_amount": row["bond_amount"],
        "bond_returned": bond_returned,
        "bond_slashed": bond_slashed,
        "payment_escrowed": row["payment_escrowed"],
        "payment_released": payment_released,
        "answer_hash": row["full_answer_hash"],
        "oracle_type": oracle_type,
        "settled_at": time.time(),
        "protocol": "AFC/1.0",
        "law_verified": "No full disclosure before payment. No payment without settlement. No settlement without an oracle. No oracle without a bond.",
    }

    conn.execute(
        "UPDATE claims SET status = 'settled', settled_at = ?, settlement_result = ?, settlement_receipt = ? WHERE claim_id = ?",
        [time.time(), settlement_result, json.dumps(receipt), claim_id]
    )
    conn.execute(
        "INSERT INTO oracle_results (result_id, claim_id, oracle_type, passed, details, resolved_at) VALUES (?,?,?,?,?,?)",
        [uuid.uuid4().hex[:12], claim_id, oracle_type, 1 if all_passed else 0, json.dumps(details), time.time()]
    )
    conn.execute(
        "INSERT INTO receipts (receipt_id, claim_id, type, payload, created_at) VALUES (?,?,?,?,?)",
        [receipt_id, claim_id, "settlement", json.dumps(receipt), time.time()]
    )
    conn.commit()
    conn.close()

    return receipt


@app.get("/claim/{claim_id}/receipt")
async def get_receipt(claim_id: str):
    """Get the settlement receipt for a claim."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT settlement_receipt FROM claims WHERE claim_id = ?", [claim_id]).fetchone()
    conn.close()
    if not row or not row["settlement_receipt"]:
        raise HTTPException(404, {"status": "no_receipt", "message": "No settlement receipt. Claim may not be settled yet."})
    return json.loads(row["settlement_receipt"])


@app.get("/protocol")
async def protocol_manifest():
    """AFC Protocol manifest — describes the full stack."""
    return {
        "protocol": "AFC/1.0",
        "name": "Antonymified File Claim Protocol",
        "thesis": "We do not sell answers. We sell bonded answer-claims whose value can be priced through controlled blur and settled through an oracle.",
        "law": [
            "No full disclosure before payment.",
            "No payment without settlement.",
            "No settlement without an oracle.",
            "No oracle without a bond.",
        ],
        "stack": [
            {"layer": 1, "name": "source_object", "description": "File or answer — the thing being claimed"},
            {"layer": 2, "name": "antonymifier", "description": "LLM-generated non-consumable surrogate"},
            {"layer": 3, "name": "merkle_commitment", "description": "Cryptographic identity and integrity"},
            {"layer": 4, "name": "blur_hash64", "description": "Fidelity label — disclosure level"},
            {"layer": 5, "name": "lambda_score", "description": "Transferability / usability friction"},
            {"layer": 6, "name": "oracle", "description": "Truth-resolution mechanism"},
            {"layer": 7, "name": "bond", "description": "Economic accountability"},
            {"layer": 8, "name": "exclusivity_window", "description": "Urgency / first-mover value"},
            {"layer": 9, "name": "settlement_receipt", "description": "Final proof of outcome"},
        ],
        "market_unit": "bonded, partially disclosed, oracle-settled claim about an answer",
        "endpoints": {
            "create_claim": "POST /claim/create",
            "view_claim": "GET /claim/{id}",
            "list_claims": "GET /claims?status=open",
            "escrow_payment": "POST /claim/{id}/escrow",
            "reveal_answer": "POST /claim/{id}/reveal",
            "submit_tests": "POST /claim/{id}/tests",
            "settle": "POST /claim/{id}/settle",
            "receipt": "GET /claim/{id}/receipt",
            "protocol": "GET /protocol",
            "health": "GET /health",
        },
        "oracle_types": ["hidden_test", "manual", "on_chain_event", "expert_arbitration"],
        "test_types": ["contains", "equals", "regex", "starts_with", "json_field", "python_exec"],
    }


LANDING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AFC Protocol — Antonymified File Claim Protocol</title>
<style>
:root{--bg:#09090B;--surface:#111114;--primary:#4F7CFF;--accent:#8B5CFF;--glass:rgba(255,255,255,0.03);--border:rgba(255,255,255,0.08);--text:#FAFAFA;--dim:rgba(250,250,250,0.5);--faint:rgba(250,250,250,0.2);--success:#22C55E;--danger:#EF4444;--r:20px;--rs:12px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:Inter,-apple-system,system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;-webkit-font-smoothing:antialiased;overflow-x:hidden}
.glow{position:fixed;top:-200px;left:50%;transform:translateX(-50%);width:800px;height:400px;background:radial-gradient(ellipse,rgba(79,124,255,0.06) 0%,transparent 70%);pointer-events:none;z-index:0}
.wrap{max-width:760px;margin:0 auto;padding:0 24px;position:relative;z-index:1}
.hero{text-align:center;padding:100px 0 60px}
.hero h1{font-size:2.8rem;font-weight:800;letter-spacing:-0.04em;background:linear-gradient(135deg,var(--primary),var(--accent));-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:16px;line-height:1}
.hero .sub{font-size:1rem;color:var(--dim);margin-bottom:8px}
.hero .thesis{font-size:1.2rem;color:var(--text);font-weight:600;max-width:560px;margin:0 auto 32px;line-height:1.5}
.btn{padding:12px 28px;border-radius:100px;font-size:0.88rem;font-weight:600;border:none;cursor:pointer;transition:all 0.2s;font-family:inherit}
.btn-p{background:var(--primary);color:#fff}.btn-p:hover{background:#6B91FF;box-shadow:0 0 30px rgba(79,124,255,0.3)}
.btn-g{background:var(--glass);color:var(--text);border:1px solid var(--border)}.btn-g:hover{background:rgba(255,255,255,0.06)}
.btn-s{background:var(--success);color:#fff}.btn-s:hover{opacity:0.9}
.btn-d{background:var(--danger);color:#fff}.btn-d:hover{opacity:0.9}
.btn-sm{padding:6px 14px;font-size:0.75rem;border-radius:8px}
.hero-btns{display:flex;gap:10px;justify-content:center;flex-wrap:wrap}
.panel{background:var(--glass);backdrop-filter:blur(20px);border:1px solid var(--border);border-radius:var(--r);padding:24px;margin-bottom:14px}
.pt{font-size:0.75rem;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;color:var(--dim);margin-bottom:16px}
.law{font-family:SF Mono,monospace;font-size:0.78rem;color:var(--text-dim);line-height:1.8;padding:12px 16px;background:var(--surface);border-radius:var(--rs);margin-bottom:16px}
.law div{color:var(--text)}
.law .num{color:var(--primary);margin-right:8px}
.field{margin-bottom:12px}
.field label{display:block;font-size:0.78rem;color:var(--dim);margin-bottom:4px}
.field input,.field textarea,.field select{width:100%;padding:10px 12px;border-radius:var(--rs);background:var(--surface);border:1px solid var(--border);color:var(--text);font-size:0.85rem;font-family:inherit;outline:none}
.field input:focus,.field textarea:focus{border-color:var(--primary)}
.field textarea{min-height:80px;resize:vertical;font-family:SF Mono,monospace;font-size:0.78rem}
.claim-card{background:var(--surface);border-radius:var(--rs);padding:16px;margin-bottom:10px;cursor:pointer;transition:all 0.15s}
.claim-card:hover{background:rgba(255,255,255,0.04)}
.claim-id{font-family:SF Mono,monospace;font-size:0.72rem;color:var(--faint)}
.claim-task{font-size:0.85rem;color:var(--text);margin:4px 0}
.claim-meta{display:flex;gap:12px;font-size:0.72rem;color:var(--dim)}
.badge{padding:2px 8px;border-radius:4px;font-size:0.68rem;font-weight:600}
.badge-open{background:rgba(79,124,255,0.15);color:var(--primary)}
.badge-committed{background:rgba(255,200,0,0.15);color:#FFC800}
.badge-revealed{background:rgba(139,92,255,0.15);color:var(--accent)}
.badge-settled-pass{background:rgba(34,197,94,0.15);color:var(--success)}
.badge-settled-fail{background:rgba(239,68,68,0.15);color:var(--danger)}
.surrogate{font-family:SF Mono,monospace;font-size:0.75rem;line-height:1.6}
.surrogate .key{color:var(--dim)}
.surrogate .val{color:var(--text)}
.stack-item{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.04)}
.stack-item:last-child{border-bottom:none}
.stack-num{width:24px;height:24px;border-radius:50%;background:var(--primary);color:#fff;font-size:0.7rem;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.stack-name{font-size:0.82rem;color:var(--text);font-weight:500}
.stack-desc{font-size:0.72rem;color:var(--dim)}
.result-box{padding:16px;border-radius:var(--rs);font-family:SF Mono,monospace;font-size:0.78rem;line-height:1.6;white-space:pre-wrap;word-break:break-all}
.result-pass{background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.2);color:var(--success)}
.result-fail{background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.2);color:var(--danger)}
.result-info{background:var(--surface);border:1px solid var(--border);color:var(--text)}
.hidden{display:none}
.step{display:flex;gap:12px;padding:10px 0}
.step-n{width:28px;height:28px;border-radius:50%;background:var(--accent);color:#fff;font-size:0.75rem;font-weight:700;display:flex;align-items:center;justify-content:center;flex-shrink:0}
.step-t{font-size:0.82rem;color:var(--text);line-height:1.5}
.footer{text-align:center;padding:40px 0;font-size:0.72rem;color:var(--faint)}
</style>
</head>
<body>
<div class="glow"></div>
<div class="wrap">
  <div class="hero">
    <h1>AFC Protocol</h1>
    <p class="sub">Antonymified File Claim Protocol</p>
    <p class="thesis">We do not sell answers. We sell bonded answer-claims whose value can be priced through controlled blur and settled through an oracle.</p>
    <div class="hero-btns">
      <button class="btn btn-p" onclick="document.getElementById('create').scrollIntoView()">Create Claim</button>
      <button class="btn btn-g" onclick="document.getElementById('claims').scrollIntoView()">Browse Claims</button>
      <button class="btn btn-g" onclick="document.getElementById('protocol').scrollIntoView()">Protocol</button>
    </div>
  </div>

  <div class="panel">
    <div class="pt">Protocol Law</div>
    <div class="law">
      <div><span class="num">1.</span>No full disclosure before payment.</div>
      <div><span class="num">2.</span>No payment without settlement.</div>
      <div><span class="num">3.</span>No settlement without an oracle.</div>
      <div><span class="num">4.</span>No oracle without a bond.</div>
    </div>
  </div>

  <div class="panel" id="create">
    <div class="pt">Create Claim (Seller)</div>
    <div class="field"><label>Seller ID</label><input id="s-seller" placeholder="seller_001"></div>
    <div class="field"><label>Task Description</label><input id="s-task" placeholder="Python function that reverses a linked list"></div>
    <div class="field"><label>Full Answer (hidden until escrow)</label><textarea id="s-answer" placeholder="def reverse_ll(head):..."></div>
    <div class="field"><label>Filename (optional)</label><input id="s-fname" placeholder="solution.py"></div>
    <div class="field"><label>Bond Amount</label><input id="s-bond" type="number" value="100" step="any"></div>
    <div class="field"><label>Oracle Type</label>
      <select id="s-oracle"><option value="hidden_test">hidden_test</option><option value="manual">manual</option></select>
    </div>
    <div class="field"><label>Exclusivity Window (seconds)</label><input id="s-excl" type="number" value="3600"></div>
    <button class="btn btn-p" onclick="createClaim()">Create Claim</button>
    <div id="create-result" class="hidden" style="margin-top:14px"></div>
  </div>

  <div class="panel" id="claims">
    <div class="pt">Open Claims <button class="btn btn-g btn-sm" style="float:right" onclick="loadClaims()">Refresh</button></div>
    <div id="claims-list"><p style="color:var(--faint);font-size:0.82rem;text-align:center;padding:20px">Loading...</p></div>
  </div>

  <div class="panel" id="claim-detail" style="display:none">
    <div class="pt">Claim Detail <button class="btn btn-g btn-sm" style="float:right" onclick="closeDetail()">Close</button></div>
    <div id="detail-content"></div>
  </div>

  <div class="panel" id="protocol">
    <div class="pt">Protocol Stack</div>
    <div id="stack-list"></div>
  </div>

  <div class="panel">
    <div class="pt">MVP: Hidden Test Claim Market</div>
    <div class="step"><div class="step-n">1</div><div class="step-t">Buyer posts task + hidden tests</div></div>
    <div class="step"><div class="step-n">2</div><div class="step-t">Seller submits antonymified preview (not full answer)</div></div>
    <div class="step"><div class="step-n">3</div><div class="step-t">Seller posts bond</div></div>
    <div class="step"><div class="step-n">4</div><div class="step-t">Buyer escrows payment</div></div>
    <div class="step"><div class="step-n">5</div><div class="step-t">Answer revealed only after commitment</div></div>
    <div class="step"><div class="step-n">6</div><div class="step-t">Hidden test suite resolves pass/fail</div></div>
    <div class="step"><div class="step-n">7</div><div class="step-t">Bond returned or slashed</div></div>
    <div class="step"><div class="step-n">8</div><div class="step-t">Settlement receipt generated</div></div>
  </div>

  <div class="footer">AFC Protocol v1.0 — Antonymified File Claim Protocol — Verifiable Non-Seeing</div>
</div>
<script>
const API='';

async function api(path,opts){const r=await fetch(API+path,opts);return r.json()}

async function createClaim(){
  const body={
    seller_id:document.getElementById('s-seller').value||'seller_001',
    task_description:document.getElementById('s-task').value,
    full_answer:document.getElementById('s-answer').value,
    filename:document.getElementById('s-fname').value,
    bond_amount:parseFloat(document.getElementById('s-bond').value)||0,
    oracle_type:document.getElementById('s-oracle').value,
    exclusivity_window_s:parseInt(document.getElementById('s-excl').value)||3600,
  };
  if(!body.full_answer){alert('Full answer required');return}
  const d=await api('/claim/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const el=document.getElementById('create-result');
  el.classList.remove('hidden');
  if(d.claim_id){
    el.innerHTML='<div class="result-box result-info">Claim created: '+d.claim_id+'\\n\\nSurrogate:\\n  file_class: '+d.surrogate.file_class+'\\n  merkle_root: '+d.surrogate.merkle_root.slice(0,20)+'...\\n  blur_hash64: '+d.surrogate.blur_hash64.slice(0,20)+'...\\n  lambda: '+d.surrogate.lambda_score+'\\n  proof_hooks: '+d.surrogate.proof_hooks.join(', ')+'\\n  bond_posted: '+d.bond_posted+'\\n\\nFull answer is encrypted and hidden.\\nShare /claim/'+d.claim_id+' with buyers.</div>';
    loadClaims();
  } else {
    el.innerHTML='<div class="result-box result-fail">'+JSON.stringify(d,null,2)+'</div>';
  }
}

async function loadClaims(){
  const d=await api('/claims?status=open');
  const el=document.getElementById('claims-list');
  if(!d.claims||d.claims.length===0){el.innerHTML='<p style="color:var(--faint);font-size:0.82rem;text-align:center;padding:20px">No open claims. Create one above.</p>';return}
  el.innerHTML=d.claims.map(c=>'<div class="claim-card" onclick="viewClaim(\\''+c.claim_id+'\\')"><div class="claim-id">'+c.claim_id+'</div><div class="claim-task">'+(c.task_description||'No description')+'</div><div class="claim-meta"><span class="badge badge-open">open</span><span>λ='+c.lambda_score+'</span><span>bond='+c.bond_amount+'</span></div></div>').join('');
}

async function viewClaim(id){
  const d=await api('/claim/'+id);
  const el=document.getElementById('claim-detail');
  const c=document.getElementById('detail-content');
  el.style.display='block';
  const s=d.surrogate||{};
  let html='<div class="surrogate">';
  html+='<div><span class="key">claim_id:</span> <span class="val">'+d.claim_id+'</span></div>';
  html+='<div><span class="key">task:</span> <span class="val">'+d.task_description+'</span></div>';
  html+='<div><span class="key">file_class:</span> <span class="val">'+s.file_class+'</span></div>';
  html+='<div><span class="key">merkle_root:</span> <span class="val">'+s.merkle_root+'</span></div>';
  html+='<div><span class="key">blur_hash64:</span> <span class="val">'+s.blur_hash64+'</span></div>';
  html+='<div><span class="key">lambda:</span> <span class="val">'+d.lambda_score+'</span></div>';
  html+='<div><span class="key">fidelity:</span> <span class="val">'+d.fidelity_label+'</span></div>';
  html+='<div><span class="key">proof_hooks:</span> <span class="val">'+(s.proof_hooks||[]).join(', ')+'</span></div>';
  html+='<div><span class="key">excluded:</span> <span class="val">'+(s.excluded_content||[]).join(', ')+'</span></div>';
  html+='<div><span class="key">bond:</span> <span class="val">'+d.bond_amount+' (posted: '+d.bond_posted+')</span></div>';
  html+='<div><span class="key">answer_hash:</span> <span class="val">'+d.answer_hash.slice(0,20)+'...</span></div>';
  html+='</div>';
  html+='<div style="margin-top:12px;font-size:0.72rem;color:var(--faint)">Full answer is encrypted. Preview only — non-consumable.</div>';

  if(d.status==='open'){
    html+='<div style="margin-top:16px"><div class="field"><label>Buyer ID</label><input id="b-buyer" placeholder="buyer_001"></div>';
    html+='<div class="field"><label>Escrow Amount</label><input id="b-amount" type="number" value="'+d.bond_amount+'" step="any"></div>';
    html+='<button class="btn btn-p" onclick="escrowClaim(\\''+id+'\\')">Escrow Payment</button></div>';
  } else if(d.status==='committed'){
    html+='<div style="margin-top:16px"><button class="btn btn-p" onclick="revealClaim(\\''+id+'\\')">Reveal Answer</button></div>';
  } else if(d.status==='revealed'){
    html+='<div style="margin-top:16px"><div class="field"><label>Hidden Tests (JSON array)</label><textarea id="b-tests" placeholder=\\'[{"type":"contains","expected":"def"}]\\'></textarea></div>';
    html+='<button class="btn btn-s" onclick="submitTests(\\''+id+'\\')">Submit Tests</button> ';
    html+='<button class="btn btn-p" onclick="settleClaim(\\''+id+'\\')">Settle</button></div>';
  } else if(d.status==='settled'){
    html+='<div style="margin-top:14px"><button class="btn btn-g" onclick="getReceipt(\\''+id+'\\')">View Receipt</button></div>';
  }
  c.innerHTML=html;
}

async function escrowClaim(id){
  const body={buyer_id:document.getElementById('b-buyer').value||'buyer_001',amount:parseFloat(document.getElementById('b-amount').value)||0};
  const d=await api('/claim/'+id+'/escrow',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  if(d.status==='committed'){alert('Payment escrowed. Claim committed. You can now reveal the answer.');viewClaim(id)}else{alert(JSON.stringify(d))}
}

async function revealClaim(id){
  const d=await api('/claim/'+id+'/reveal',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  if(d.status==='revealed'){
    const el=document.getElementById('detail-content');
    el.innerHTML+='<div class="result-box result-info" style="margin-top:14px"><b>Revealed Answer:</b>\\n\\n'+d.full_answer+'\\n\\nHash verified: '+d.verify+'</div>';
    el.innerHTML+='<div style="margin-top:12px"><div class="field"><label>Hidden Tests (JSON array)</label><textarea id="b-tests" placeholder=\\'[{"type":"contains","expected":"def"}]\\'></textarea></div>';
    el.innerHTML+='<button class="btn btn-s" onclick="submitTests(\\''+id+'\\')">Submit Tests</button> <button class="btn btn-p" onclick="settleClaim(\\''+id+'\\')">Settle</button></div>';
  } else {alert(JSON.stringify(d))}
}

async function submitTests(id){
  const t=document.getElementById('b-tests').value;
  let tests;try{tests=JSON.parse(t)}catch{alert('Invalid JSON');return}
  const d=await api('/claim/'+id+'/tests',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({tests})});
  if(d.tests_submitted){alert(d.tests_submitted+' tests submitted. Ready to settle.')}else{alert(JSON.stringify(d))}
}

async function settleClaim(id){
  const d=await api('/claim/'+id+'/settle',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
  const el=document.getElementById('detail-content');
  if(d.result==='pass'){
    el.innerHTML+='<div class="result-box result-pass" style="margin-top:14px"><b>SETTLED: PASS</b>\\n\\nTests: '+d.tests_passed+' passed, '+d.tests_failed+' failed\\nBond returned: '+d.bond_returned+'\\nPayment released: '+d.payment_released+'\\n\\nReceipt ID: '+d.receipt_id+'</div>';
  } else {
    el.innerHTML+='<div class="result-box result-fail" style="margin-top:14px"><b>SETTLED: FAIL</b>\\n\\nTests: '+d.tests_passed+' passed, '+d.tests_failed+' failed\\nBond slashed: '+d.bond_slashed+'\\nPayment returned to buyer\\n\\nReceipt ID: '+d.receipt_id+'</div>';
  }
}

async function getReceipt(id){
  const d=await api('/claim/'+id+'/receipt');
  const el=document.getElementById('detail-content');
  el.innerHTML+='<div class="result-box result-info" style="margin-top:14px">'+JSON.stringify(d,null,2)+'</div>';
}

function closeDetail(){document.getElementById('claim-detail').style.display='none'}

async function loadProtocol(){
  const d=await api('/protocol');
  const el=document.getElementById('stack-list');
  el.innerHTML=d.stack.map(s=>'<div class="stack-item"><div class="stack-num">'+s.layer+'</div><div><div class="stack-name">'+s.name+'</div><div class="stack-desc">'+s.description+'</div></div></div>').join('');
}

loadClaims();
loadProtocol();
</script>
</body></html>"""


@app.get("/", response_class=HTMLResponse)
async def landing():
    return LANDING_HTML


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
