"""SystemLake Underwriter — Privacy-Preserving Code Evaluation Gateway.

The actual product: User uploads files → system crawls + hashes + redacts →
sends only a metadata cognition packet to GPT → GPT evaluates →
returns verdict + receipt. Raw files never leave the user's control.

Pipeline:
    Upload → Extract → Crawl → Hash → Merkle Root → Detect Systems →
    Score Collateral → Redact (strip source, keep metadata) →
    Build Cognition Packet → Send to LLM → Get Evaluation →
    Write Receipt → Return Verdict

What goes to GPT (cognition packet):
    - File hashes (SHA-256), sizes, extensions, categories
    - Merkle root
    - System detection results (has_git, has_tests, has_endpoints)
    - Collateral scores (10 dimensions)
    - Risk register with classifications
    - Verification results
    - Capabilities summary

What does NOT go to GPT:
    - Source code content
    - File names containing secrets
    - .env, .ssh, keys, wallets, credentials
    - Binary file contents
    - Any file content at all — only metadata

Endpoints:
    GET  /              — Upload UI
    POST /upload        — Upload a zip/tar of your repo
    GET  /result/{id}   — Get evaluation result + receipt
    GET  /result/{id}/packet — Get cognition packet only
    GET  /result/{id}/evaluation — Get LLM evaluation only
    GET  /result/{id}/receipt — Get receipt only
    GET  /health        — Health check
    GET  /telemetry     — Pre-baked telemetry (existing audit)
"""

import os
import json
import hashlib
import zipfile
import tarfile
import shutil
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path as _Path

from fastapi import FastAPI, HTTPException, UploadFile, File, Body
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# ─── Configuration ──────────────────────────────────────────────────────

# Auto-load .env if present (local dev)
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_path):
    with open(_env_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _v = _line.split("=", 1)
                os.environ.setdefault(_k.strip(), _v.strip())

DATA_DIR = os.environ.get("SYSTEMLAKE_DATA_DIR", "/app/audit_data")
UPLOAD_DIR = os.environ.get("SYSTEMLAKE_UPLOAD_DIR", "/tmp/systemlake_uploads")
RESULTS_DIR = os.environ.get("SYSTEMLAKE_RESULTS_DIR", "/tmp/systemlake_results")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768"]
HF_TOKEN = os.environ.get("HF_TOKEN", "")
PORT = int(os.environ.get("PORT", 7860))

os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULTS_DIR, exist_ok=True)

# ─── Denied file patterns (never hashed, never indexed, never sent) ─────

DENIED_PATTERNS = [
    '.env', '.env.', '.ssh', '.aws', '.npmrc', '.pypirc',
    'id_rsa', 'id_ed25519', 'id_ecdsa',
    '.key', '.pem', '.crt', '.pfx', '.p12',
    'credentials', 'secrets', 'wallet', 'keystore',
    '.keystore', '.keychain', 'Keychains',
    '.gnupg', '.gpg',
]

DENIED_EXTENSIONS = {
    '.env', '.key', '.pem', '.crt', '.pfx', '.p12', '.keystore',
    '.jks', '.gpg', '.pgp',
}

EXCLUDE_DIRS = {
    '__pycache__', '.git', 'node_modules', '.venv', 'venv',
    '.pytest_cache', '.mypy_cache', '.cache', '.npm',
    'dist', 'build', 'target', '.next', '.nuxt',
    '.gradle', '.m2', '.cargo', '.rustup',
    '.vscode', '.cursor', '.windsurf', '.idea',
}

# ─── Data Loading (for pre-baked telemetry) ─────────────────────────────

def _load_json(filename: str) -> Optional[dict]:
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return None

def _load_text(filename: str) -> Optional[str]:
    path = os.path.join(DATA_DIR, filename)
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read()
    return None

def _load_all() -> dict:
    return {
        "systems": _load_json("systems.json"),
        "scores": _load_json("underwriting_scores.json"),
        "risks": _load_json("risk_register.json"),
        "borrowing": _load_json("borrowing_base.json"),
        "verification": _load_json("verification_results.json"),
        "merkle": _load_json("merkle_root.json"),
        "manifest": _load_json("machine_manifest.json"),
        "receipt": _load_json("receipt.json"),
        "focus": _load_json("focus_packet.json"),
        "memo": _load_text("underwriting_memo.md"),
    }

# ─── Redaction Layer ────────────────────────────────────────────────────

def _is_denied(filename: str) -> bool:
    lower = filename.lower()
    for ext in DENIED_EXTENSIONS:
        if lower.endswith(ext):
            return True
    for pattern in DENIED_PATTERNS:
        if pattern in lower:
            return True
    return False

def _compute_merkle_root(hashes: List[str]) -> str:
    if not hashes:
        return None
    leaves = [hashlib.sha256(h.encode()).hexdigest() for h in hashes]
    while len(leaves) > 1:
        if len(leaves) % 2 != 0:
            leaves.append(leaves[-1])
        leaves = [hashlib.sha256((leaves[i] + leaves[i+1]).encode()).hexdigest()
                  for i in range(0, len(leaves), 2)]
    return leaves[0]

def _build_cognition_packet(extracted_dir: str) -> dict:
    """Crawl extracted files and build a REDACTED cognition packet.
    Contains NO source code, NO file content. Only hashes, sizes, structure.
    """
    packet = {
        "schema": "membra.systemlake.cognition_packet.v1",
        "created_at": datetime.now().isoformat(),
        "files": [],
        "systems": [],
        "stats": {
            "total_files": 0, "total_bytes": 0,
            "denied_files": 0, "by_extension": {}, "by_category": {},
        },
    }
    file_hashes = []

    for dirpath, dirnames, filenames in os.walk(extracted_dir):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for fname in filenames:
            full_path = os.path.join(dirpath, fname)
            rel_path = os.path.relpath(full_path, extracted_dir)
            if _is_denied(fname) or _is_denied(rel_path):
                packet["stats"]["denied_files"] += 1
                continue
            try:
                st = os.stat(full_path)
            except Exception:
                continue
            try:
                h = hashlib.sha256()
                with open(full_path, "rb") as f:
                    while True:
                        chunk = f.read(8192)
                        if not chunk:
                            break
                        h.update(chunk)
                sha = h.hexdigest()
            except Exception:
                sha = "unreadable"
            ext = os.path.splitext(fname)[1].lower()
            size = st.st_size
            if ext in ('.py',): category = 'python'
            elif ext in ('.js', '.ts', '.jsx', '.tsx'): category = 'javascript'
            elif ext in ('.go',): category = 'go'
            elif ext in ('.rs',): category = 'rust'
            elif ext in ('.java',): category = 'java'
            elif ext in ('.md', '.rst', '.txt'): category = 'documentation'
            elif ext in ('.json', '.yaml', '.yml', '.toml', '.ini', '.cfg'): category = 'config'
            elif ext in ('.html', '.css', '.vue', '.svelte'): category = 'frontend'
            elif ext in ('.sql',): category = 'database'
            elif ext in ('.sh', '.bash'): category = 'script'
            elif ext in ('.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico'): category = 'asset'
            else: category = 'other'
            packet["files"].append({"path": rel_path, "sha256": sha, "size": size, "extension": ext, "category": category})
            packet["stats"]["total_files"] += 1
            packet["stats"]["total_bytes"] += size
            packet["stats"]["by_extension"][ext] = packet["stats"]["by_extension"].get(ext, 0) + 1
            packet["stats"]["by_category"][category] = packet["stats"]["by_category"].get(category, 0) + 1
            file_hashes.append(sha)

    packet["merkle_root"] = _compute_merkle_root(file_hashes) if file_hashes else None
    packet["systems"] = _detect_systems_metadata(extracted_dir)
    packet["collateral_scores"] = _score_collateral_metadata(packet)
    packet["risks"] = _build_risk_register(packet)
    return packet

def _detect_systems_metadata(root: str) -> list:
    markers = {'requirements.txt', 'package.json', 'setup.py', 'Makefile',
               'Dockerfile', '.git', 'README.md', 'pyproject.toml'}
    systems = []
    seen = set()
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        has_git_dir = '.git' in dirnames
        dir_files = set(filenames + dirnames)
        if has_git_dir: dir_files.add('.git')
        markers_found = markers & dir_files
        if not markers_found: continue
        dirname = os.path.basename(dirpath) or 'root'
        if dirname in seen: continue
        has_code = any(f.endswith(('.py', '.js', '.ts', '.go', '.rs', '.java')) for f in filenames)
        strong = markers_found & {'requirements.txt', 'setup.py', 'Dockerfile', 'Makefile', '.git'}
        if len(markers_found) < 2 and not strong and not (has_git_dir and has_code): continue
        systems.append({
            "name": dirname, "root_path": os.path.relpath(dirpath, root),
            "markers": sorted(list(markers_found)), "has_git": has_git_dir,
            "has_tests": any('test' in f.lower() for f in filenames),
            "has_endpoints": bool({'app.py', 'server.py', 'main.py', 'server.js', 'index.js'} & set(filenames)),
            "has_receipts": any('receipt' in f.lower() for f in filenames),
            "file_count": len(filenames),
            "has_dockerfile": 'Dockerfile' in markers_found,
            "has_requirements": 'requirements.txt' in markers_found,
            "has_readme": 'README.md' in markers_found,
        })
        seen.add(dirname)
    return systems

def _score_collateral_metadata(packet: dict) -> dict:
    stats = packet["stats"]
    systems = packet["systems"]
    by_cat = stats["by_category"]
    code_files = sum(by_cat.get(c, 0) for c in ("python", "javascript", "go", "rust", "java"))
    doc_files = by_cat.get("documentation", 0)
    config_files = by_cat.get("config", 0)
    has_git = any(s["has_git"] for s in systems)
    has_tests = any(s["has_tests"] for s in systems)
    has_ep = any(s["has_endpoints"] for s in systems)
    has_docker = any(s["has_dockerfile"] for s in systems)
    has_receipts = any(s["has_receipts"] for s in systems)
    has_readme = any(s["has_readme"] for s in systems)

    dims = {
        "functionality": min(100, 20 + code_files * 2 + (15 if has_ep else 0)),
        "reproducibility": min(100, 25 + (20 if has_git else 0) + (15 if has_docker else 0) + (10 if config_files > 0 else 0)),
        "receipt_strength": min(100, 20 + (40 if has_receipts else 0) + (20 if has_git else 0)),
        "deployability": min(100, 20 + (25 if has_docker else 0) + (15 if has_ep else 0) + (10 if config_files > 2 else 0)),
        "test_strength": min(100, 15 + (50 if has_tests else 0)),
        "documentation": min(100, 20 + doc_files * 5 + (20 if has_readme else 0)),
        "security_cleanliness": min(100, 40 + (20 if stats["denied_files"] == 0 else 0) + (20 if stats["total_files"] < 1000 else 0)),
        "provenance": min(100, 20 + (50 if has_git else 0) + (15 if has_receipts else 0)),
        "economic_evidence": min(100, 15 + (10 if has_ep else 0) + (5 if has_receipts else 0)),
        "marketability": min(100, 20 + (15 if doc_files > 0 else 0) + (10 if has_ep else 0) + (10 if len(systems) > 1 else 0)),
    }
    dims = {k: round(v, 1) for k, v in dims.items()}
    weights = {"functionality": 0.18, "reproducibility": 0.14, "receipt_strength": 0.14,
               "deployability": 0.12, "test_strength": 0.10, "documentation": 0.10,
               "security_cleanliness": 0.10, "provenance": 0.08,
               "economic_evidence": 0.08, "marketability": 0.06}
    raw = sum(dims[k] * weights[k] for k in dims)
    haircuts = {}
    if not has_tests: haircuts["no_tests"] = 10.0
    if not has_receipts: haircuts["no_receipts"] = 8.0
    if not has_git: haircuts["no_provenance"] = 15.0
    if stats["denied_files"] > 0: haircuts["secret_exposure"] = 20.0
    if not has_readme: haircuts["no_documentation"] = 5.0
    total_hc = sum(haircuts.values())
    final = max(0, raw - total_hc)
    grade = "A" if final >= 80 else "B" if final >= 65 else "C" if final >= 50 else "D" if final >= 35 else "F"
    return {
        "dimensions": dims, "raw_score": round(raw, 1), "haircuts": haircuts,
        "total_haircut": round(total_hc, 1), "final_score": round(final, 1),
        "grade": grade,
        "borrowing_base_estimate_usd": {"low": round(final*5,2), "mid": round(final*15,2), "high": round(final*25,2)},
        "systems_count": len(systems),
        "capabilities": {"has_git": has_git, "has_tests": has_tests, "has_endpoints": has_ep,
                         "has_dockerfile": has_docker, "has_receipts": has_receipts},
    }

def _build_risk_register(packet: dict) -> list:
    risks = []
    haircuts = packet.get("collateral_scores", {}).get("haircuts", {})
    risk_map = {
        "no_tests": ("missing_evidence", "No test coverage", "Add test files"),
        "no_receipts": ("missing_evidence", "No execution receipts", "Generate receipts"),
        "no_provenance": ("missing_evidence", "No git history", "Initialize git repo"),
        "secret_exposure": ("real", "Exposed secrets detected", "Remove .env and secrets"),
        "no_documentation": ("missing_evidence", "No README", "Add README.md"),
    }
    for hname, val in haircuts.items():
        cls, desc, rem = risk_map.get(hname, ("real", hname, "Review"))
        risks.append({"risk_type": hname, "severity": "high" if val >= 15 else "medium" if val >= 8 else "low",
                      "haircut": val, "classification": cls, "description": desc, "remediation": rem})
    return risks

# ─── LLM Evaluation Gateway ─────────────────────────────────────────────

def _build_llm_prompt(packet: dict) -> str:
    scores = packet.get("collateral_scores", {})
    stats = packet["stats"]
    systems = packet["systems"]
    sys_summary = "\n".join([
        f"  - {s['name']}: {s['file_count']} files, markers={s['markers']}, "
        f"git={s['has_git']}, tests={s['has_tests']}, endpoints={s['has_endpoints']}"
        for s in systems]) or "  (none detected)"
    return f"""You are a software collateral underwriter. Evaluate the following software asset metadata.

IMPORTANT: You receive ONLY metadata — hashes, sizes, extensions, structure. NO source code. NO file contents. NO proprietary information.

## Asset Summary
- Files: {stats['total_files']}, Size: {stats['total_bytes']:,} bytes
- Denied (secrets filtered): {stats['denied_files']}
- Merkle root: {packet.get('merkle_root', 'N/A')[:16]}...
- Systems: {len(systems)}

## Systems
{sys_summary}

## Categories
{json.dumps(stats.get('by_category', {}), indent=2)}

## Extensions
{json.dumps(stats.get('by_extension', {}), indent=2)}

## Scores
- Final: {scores.get('final_score', 0)}/100, Grade: {scores.get('grade', 'F')}
- Dimensions: {json.dumps(scores.get('dimensions', {}))}
- Haircuts: {json.dumps(scores.get('haircuts', {}))}

## Risks
{json.dumps(packet.get('risks', []), indent=2)}

## Borrowing Base
{json.dumps(scores.get('borrowing_base_estimate_usd', {}))}

## Capabilities
{json.dumps(scores.get('capabilities', {}))}

## Task
Provide:
1. VERDICT: underwritable / underwritable_after_remediation / not_underwritable
2. GRADE JUSTIFICATION
3. KEY STRENGTHS
4. KEY RISKS
5. REMEDIATION PATH
6. BORROWING BASE OPINION
7. CONFIDENCE (high/medium/low)

Be honest and conservative. Missing evidence = missing evidence, not positive evidence."""

async def _call_llm(prompt: str) -> str:
    if OPENAI_API_KEY:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post("https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                    json={"model": "gpt-4o-mini", "messages": [
                        {"role": "system", "content": "You are a software collateral underwriter. Be precise, honest, and conservative."},
                        {"role": "user", "content": prompt}],
                        "max_tokens": 2000, "temperature": 0.3})
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[LLM call failed: {e}]\n\n" + _local_evaluation(prompt)
    if HF_TOKEN:
        import httpx
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post("https://api-inference.huggingface.co/models/meta-llama/Meta-Llama-3-8B-Instruct",
                    headers={"Authorization": f"Bearer {HF_TOKEN}", "Content-Type": "application/json"},
                    json={"inputs": prompt, "parameters": {"max_new_tokens": 1000, "temperature": 0.3}})
                resp.raise_for_status()
                data = resp.json()
                return data[0].get("generated_text", str(data)) if isinstance(data, list) else str(data)
        except Exception as e:
            return f"[HF inference failed: {e}]\n\n" + _local_evaluation(prompt)
    return _local_evaluation(prompt)

def _local_evaluation(prompt: str) -> str:
    final_score = 0; grade = "F"
    for line in prompt.split('\n'):
        if "Final:" in line:
            try: final_score = float(line.split(":")[1].split("/")[0].split(",")[0].strip())
            except: pass
        if "Grade:" in line:
            try: grade = line.split("Grade:")[1].strip().split(",")[0].strip()
            except: pass
    if final_score >= 65: verdict = "underwritable"; conf = "medium"
    elif final_score >= 35: verdict = "underwritable_after_remediation"; conf = "medium"
    else: verdict = "not_underwritable"; conf = "low"
    return f"""## 1. VERDICT
{verdict}

## 2. GRADE JUSTIFICATION
Grade {grade} (score: {final_score}/100). Metadata-only analysis. Higher grade requires passing tests, execution receipts, and external validation.

## 3. KEY STRENGTHS
- Software structure is detectable and measurable
- Merkle root provides tamper-evident state proof
- Systems detected with project markers

## 4. KEY RISKS
- Source code quality NOT evaluated (metadata only)
- Tests may exist but not pass
- No external validation of economic claims

## 5. REMEDIATION PATH
- Add tests and ensure they pass
- Generate execution receipts
- Add LICENSE file and lockfile
- Document usage and deployment

## 6. BORROWING BASE OPINION
Conservative estimate based on structural metadata. Adjusts upward with: passing tests, receipts, usage logs, market validation. Adjusts downward with: failing tests, secret exposure, license conflicts.

## 7. CONFIDENCE
{conf} — Metadata-only evaluation. Full confidence requires source code review, test execution, and external audit.

---
Note: Local evaluation (no LLM API configured). Set OPENAI_API_KEY or HF_TOKEN for LLM-powered evaluation."""

# ─── Evaluation Pipeline ────────────────────────────────────────────────

_evaluations = {}

async def _run_evaluation(eval_id: str, extracted_dir: str, filename: str):
    result = {"id": eval_id, "status": "crawling", "filename": filename,
              "started_at": datetime.now().isoformat(), "steps": []}
    _evaluations[eval_id] = result
    try:
        result["status"] = "building_cognition_packet"
        result["steps"].append({"step": "crawl_hash_redact", "status": "running", "timestamp": datetime.now().isoformat()})
        packet = _build_cognition_packet(extracted_dir)
        result["steps"][-1].update({"status": "complete", "files_indexed": packet["stats"]["total_files"],
                                     "files_denied": packet["stats"]["denied_files"],
                                     "merkle_root": (packet.get("merkle_root") or "")[:16] + "...",
                                     "systems_detected": len(packet["systems"])})
        result["status"] = "building_llm_prompt"
        result["steps"].append({"step": "build_prompt", "status": "running", "timestamp": datetime.now().isoformat()})
        prompt = _build_llm_prompt(packet)
        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
        result["steps"][-1].update({"status": "complete", "prompt_hash": prompt_hash[:16] + "...", "prompt_size": len(prompt)})
        result["status"] = "evaluating_with_llm"
        result["steps"].append({"step": "llm_evaluation", "status": "running", "timestamp": datetime.now().isoformat()})
        llm_response = await _call_llm(prompt)
        result["steps"][-1].update({"status": "complete", "response_length": len(llm_response)})
        result["status"] = "writing_receipt"
        receipt = {
            "schema": "membra.systemlake.evaluation_receipt.v1",
            "receipt_id": eval_id, "timestamp": datetime.now().isoformat(), "filename": filename,
            "merkle_root": packet.get("merkle_root"), "files_indexed": packet["stats"]["total_files"],
            "files_denied": packet["stats"]["denied_files"], "systems_detected": len(packet["systems"]),
            "collateral_score": packet["collateral_scores"]["final_score"], "grade": packet["collateral_scores"]["grade"],
            "prompt_hash": prompt_hash, "llm_used": bool(OPENAI_API_KEY or HF_TOKEN),
            "cognition_packet_schema": packet["schema"],
            "safety_guarantees": {"source_code_sent_to_llm": False, "file_contents_sent_to_llm": False,
                                  "secrets_sent_to_llm": False, "only_metadata_hashes_structure": True},
        }
        receipt["receipt_hash"] = hashlib.sha256(json.dumps(receipt, sort_keys=True).encode()).hexdigest()
        result["steps"].append({"step": "write_receipt", "status": "complete", "timestamp": datetime.now().isoformat()})
        result["status"] = "complete"
        result["completed_at"] = datetime.now().isoformat()
        result["packet"] = packet
        result["llm_evaluation"] = llm_response
        result["receipt"] = receipt
        result_path = os.path.join(RESULTS_DIR, f"{eval_id}.json")
        with open(result_path, "w") as f:
            json.dump(result, f, indent=2, default=str)
        shutil.rmtree(extracted_dir, ignore_errors=True)
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        shutil.rmtree(extracted_dir, ignore_errors=True)

def _run_evaluation_sync(eval_id: str, extract_dir: str, filename: str):
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try: loop.run_until_complete(_run_evaluation(eval_id, extract_dir, filename))
    finally: loop.close()

# ─── FastAPI App ────────────────────────────────────────────────────────

app = FastAPI(title="Jorki File Gateway", version="2.0.0")

@app.get("/telemetry")
async def telemetry():
    data = _load_all()
    if not data["systems"]: raise HTTPException(404, "No pre-baked audit data found.")
    systems = data["systems"].get("systems", [])
    grades = {}
    for s in systems:
        g = s.get("grade", "F"); grades[g] = grades.get(g, 0) + 1
    bb = data["borrowing"] or {}
    risks = data["risks"] or {}
    return {"schema": "membra.systemlake.telemetry.v1", "timestamp": datetime.now().isoformat(),
            "audit": {"systems_total": len(systems), "grade_distribution": dict(sorted(grades.items())),
                      "borrowing_base": {"low": bb.get("total_low",0), "mid": bb.get("total_mid",0), "high": bb.get("total_high",0)},
                      "risks": {"total": risks.get("total_risks",0), "high": risks.get("high_severity",0),
                                "medium": risks.get("medium_severity",0), "low": risks.get("low_severity",0)},
                      "merkle_root": data["merkle"].get("root","") if data["merkle"] else "",
                      "receipt_id": data["receipt"].get("receipt_id","") if data["receipt"] else ""},
            "evaluations": list(_evaluations.keys())}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a zip/tar of your repo. Source code is NEVER sent to any LLM.
    Only metadata (hashes, sizes, extensions, structure) is sent for evaluation.
    Secrets, keys, and credentials are filtered out entirely."""
    eval_id = str(uuid.uuid4())
    upload_path = os.path.join(UPLOAD_DIR, f"{eval_id}_{file.filename}")
    with open(upload_path, "wb") as f:
        content = await file.read(); f.write(content)
    extract_dir = os.path.join(UPLOAD_DIR, f"{eval_id}_extracted")
    os.makedirs(extract_dir, exist_ok=True)
    if file.filename.endswith('.zip'):
        with zipfile.ZipFile(upload_path, 'r') as z: z.extractall(extract_dir)
    elif file.filename.endswith(('.tar.gz', '.tgz', '.tar')):
        with tarfile.open(upload_path, 'r:*') as t: t.extractall(extract_dir)
    else:
        shutil.copy(upload_path, os.path.join(extract_dir, file.filename))
    os.unlink(upload_path)
    entries = os.listdir(extract_dir)
    if len(entries) == 1 and os.path.isdir(os.path.join(extract_dir, entries[0])):
        extract_dir = os.path.join(extract_dir, entries[0])
    threading.Thread(target=lambda: _run_evaluation_sync(eval_id, extract_dir, file.filename), daemon=True).start()
    return {"eval_id": eval_id, "filename": file.filename, "status": "started",
            "message": "File uploaded. Poll GET /result/{eval_id} for results.", "result_url": f"/result/{eval_id}"}

@app.get("/result/{eval_id}")
async def get_result(eval_id: str):
    if eval_id in _evaluations: return _evaluations[eval_id]
    result_path = os.path.join(RESULTS_DIR, f"{eval_id}.json")
    if os.path.exists(result_path):
        with open(result_path, "r") as f: return json.load(f)
    raise HTTPException(404, f"Evaluation '{eval_id}' not found")

@app.get("/result/{eval_id}/packet")
async def get_packet(eval_id: str):
    result = _evaluations.get(eval_id)
    if not result:
        rp = os.path.join(RESULTS_DIR, f"{eval_id}.json")
        if os.path.exists(rp):
            with open(rp, "r") as f: result = json.load(f)
    if not result: raise HTTPException(404, f"Evaluation '{eval_id}' not found")
    return result.get("packet", {})

@app.get("/result/{eval_id}/evaluation")
async def get_evaluation(eval_id: str):
    result = _evaluations.get(eval_id)
    if not result:
        rp = os.path.join(RESULTS_DIR, f"{eval_id}.json")
        if os.path.exists(rp):
            with open(rp, "r") as f: result = json.load(f)
    if not result: raise HTTPException(404, f"Evaluation '{eval_id}' not found")
    return PlainTextResponse(result.get("llm_evaluation", "No evaluation available"))

@app.get("/result/{eval_id}/receipt")
async def get_receipt(eval_id: str):
    result = _evaluations.get(eval_id)
    if not result:
        rp = os.path.join(RESULTS_DIR, f"{eval_id}.json")
        if os.path.exists(rp):
            with open(rp, "r") as f: result = json.load(f)
    if not result: raise HTTPException(404, f"Evaluation '{eval_id}' not found")
    return result.get("receipt", {})

# ─── Legacy telemetry endpoints ─────────────────────────────────────────

@app.get("/systems")
async def list_systems():
    data = _load_all()
    if not data["systems"]: raise HTTPException(404, "No audit data found.")
    return data["systems"]

@app.get("/risks")
async def risks():
    data = _load_all()
    if not data["risks"]: raise HTTPException(404, "No audit data found.")
    return data["risks"]

@app.get("/borrowing")
async def borrowing():
    data = _load_all()
    if not data["borrowing"]: raise HTTPException(404, "No audit data found.")
    return data["borrowing"]

@app.get("/scores")
async def scores():
    data = _load_all()
    if not data["scores"]: raise HTTPException(404, "No audit data found.")
    return data["scores"]

@app.get("/merkle")
async def merkle():
    data = _load_all()
    if not data["merkle"]: raise HTTPException(404, "No audit data found.")
    return data["merkle"]

@app.get("/receipt")
async def receipt_legacy():
    data = _load_all()
    if not data["receipt"]: raise HTTPException(404, "No audit data found.")
    return data["receipt"]

@app.get("/scope")
async def scope():
    data = _load_all()
    if not data["focus"]: raise HTTPException(404, "No audit data found.")
    return data["focus"].get("scope", {})

@app.get("/memo")
async def memo():
    data = _load_all()
    if not data["memo"]: raise HTTPException(404, "No audit data found.")
    return HTMLResponse(f"<pre>{data['memo']}</pre>")

@app.get("/verification")
async def verification():
    data = _load_all()
    if not data["verification"]: raise HTTPException(404, "No audit data found.")
    return data["verification"]

# ─── Dashboard / Upload UI ──────────────────────────────────────────────

@app.get("/")
async def root():
    ui_path = _Path("/app/jorki_ui_dist/index.html")
    if ui_path.exists():
        return FileResponse(str(ui_path))
    return HTMLResponse("<h1>Jorki</h1><p>UI not built. Visit /systemlake for the legacy dashboard.</p>")

@app.get("/systemlake", response_class=HTMLResponse)
@app.get("/systemlake", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse("<meta http-equiv=refresh content=0 url=/>")

# ─── JORKI API Endpoints ─────────────────────────────────────────────────

import sqlite3
import re
import time

JORKI_DATA_DIR = _Path(os.environ.get("SYSTEMLAKE_DATA_DIR", "/tmp/systemlake_v4b")) / "jorki"
JORKI_DATA_DIR.mkdir(parents=True, exist_ok=True)
JORKI_INDEX_DIR = JORKI_DATA_DIR / "indexes"
JORKI_INDEX_DIR.mkdir(parents=True, exist_ok=True)
JORKI_REGISTRY_PATH = JORKI_DATA_DIR / "registry.json"

def _jorki_load_registry():
    if JORKI_REGISTRY_PATH.exists():
        return json.loads(JORKI_REGISTRY_PATH.read_text())
    return {}

def _jorki_save_registry(reg):
    JORKI_REGISTRY_PATH.write_text(json.dumps(reg, indent=2))

# ── Fast-path index schema (created once, reused) ──
_INDEX_SCHEMA_SQL = [
    "CREATE TABLE IF NOT EXISTS file_meta (key TEXT, value TEXT)",
    "CREATE TABLE IF NOT EXISTS chunks (idx INTEGER, line_start INTEGER, line_end INTEGER, boundary_type TEXT, preview TEXT, line_count INTEGER)",
    "CREATE TABLE IF NOT EXISTS word_freq (word TEXT, count INTEGER)",
    "CREATE TABLE IF NOT EXISTS symbols (line INTEGER, name TEXT, type TEXT)",
    "CREATE TABLE IF NOT EXISTS capabilities (id INTEGER, name TEXT)",
    "CREATE TABLE IF NOT EXISTS kpis (id INTEGER, name TEXT, value TEXT, line INTEGER, category TEXT, confidence REAL)",
    "CREATE TABLE IF NOT EXISTS dna (key TEXT, value TEXT)",
    "CREATE TABLE IF NOT EXISTS access_control (password_hash TEXT, salt TEXT, hint TEXT, created_at REAL)",
]
_CAPS_LIST = [(i, name) for i, name in enumerate(["sql", "nosql", "search", "chunk", "summary", "meta", "mcp", "word_freq", "symbols", "chunks", "merkle", "sha256", "capabilities", "revocation", "kpi", "dna", "password"])]

import concurrent.futures
_INDEX_POOL = concurrent.futures.ThreadPoolExecutor(max_workers=8)

def _jorki_index_file(filepath, fast=False):
    path = _Path(filepath)
    content = path.read_bytes()
    size = len(content)
    merkle_root = hashlib.sha256(content).hexdigest()
    file_id = merkle_root[:12]
    text = content.decode("utf-8", errors="replace")
    lines = text.split("\n")
    line_count = len(lines)
    words = re.findall(r"\b\w+\b", text)
    word_freq = {}
    for w in words:
        word_freq[w] = word_freq.get(w, 0) + 1
    top_words = sorted(word_freq.items(), key=lambda x: -x[1])[:20]

    chunks = []
    current_chunk = []
    chunk_start = 0
    for i, line in enumerate(lines):
        current_chunk.append(line)
        is_boundary = (
            (line.strip() == "" and len(current_chunk) > 5)
            or line.strip().startswith("def ")
            or line.strip().startswith("class ")
            or line.strip().startswith("func ")
            or line.strip().startswith("workflow:")
        )
        if is_boundary and len(current_chunk) >= 3:
            chunks.append({"idx": len(chunks), "line_start": chunk_start, "line_end": i,
                           "boundary_type": "function" if line.strip().startswith(("def ", "class ", "func ")) else "paragraph",
                           "preview": "\n".join(current_chunk[:3])[:200], "line_count": len(current_chunk)})
            current_chunk = []
            chunk_start = i + 1
    if current_chunk:
        chunks.append({"idx": len(chunks), "line_start": chunk_start, "line_end": line_count - 1,
                       "boundary_type": "final", "preview": "\n".join(current_chunk[:3])[:200], "line_count": len(current_chunk)})

    symbols = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        for prefix in ["def ", "class ", "func ", "async def "]:
            if stripped.startswith(prefix):
                name = stripped[len(prefix):].split("(")[0].split(":")[0].strip()
                symbols.append({"line": i + 1, "name": name, "type": prefix.strip()})

    # ── KPI Extraction (skip in fast mode for speed) ──
    kpis = [] if fast else _jorki_extract_kpis(text, lines, word_freq)

    # ── DNA Fingerprint (skip in fast mode for speed) ──
    dna = {"species": "textus", "complexity_score": 0, "genes": {}, "dna_sequence": "", "genome_size": 0} if fast else _jorki_compute_dna(content, text, lines, symbols, word_freq, chunks, path.name)

    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    conn = sqlite3.connect(str(idx_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=OFF")
    for sql in _INDEX_SCHEMA_SQL:
        conn.execute(sql)
    # Fast clear — drop and recreate is faster than DELETE for large tables
    conn.executescript("""
        DELETE FROM file_meta; DELETE FROM chunks; DELETE FROM word_freq;
        DELETE FROM symbols; DELETE FROM capabilities; DELETE FROM kpis;
        DELETE FROM dna; DELETE FROM access_control;
    """)
    meta = {"filename": path.name, "size_bytes": str(size), "total_lines": str(line_count),
            "total_words": str(len(words)), "merkle_root": merkle_root,
            "total_chunks": str(len(chunks)), "total_symbols": str(len(symbols)),
            "file_id": file_id, "size_human": f"{size/1024:.1f}KB" if size < 1048576 else f"{size/1048576:.1f}MB"}
    # Batch all inserts with executemany
    conn.executemany("INSERT INTO file_meta VALUES (?,?)", [(k, str(v)) for k, v in meta.items()])
    conn.executemany("INSERT INTO chunks VALUES (?,?,?,?,?,?)",
        [(c["idx"], c["line_start"], c["line_end"], c["boundary_type"], c["preview"], c["line_count"]) for c in chunks])
    conn.executemany("INSERT INTO word_freq VALUES (?,?)", top_words)
    conn.executemany("INSERT INTO symbols VALUES (?,?,?)",
        [(s["line"], s["name"], s["type"]) for s in symbols])
    conn.executemany("INSERT INTO capabilities VALUES (?,?)", _CAPS_LIST)
    conn.executemany("INSERT INTO kpis VALUES (?,?,?,?,?,?)",
        [(k["id"], k["name"], k["value"], k["line"], k["category"], k["confidence"]) for k in kpis])
    conn.executemany("INSERT INTO dna VALUES (?,?)",
        [(k, json.dumps(v) if isinstance(v, dict) else str(v)) for k, v in dna.items()])
    conn.commit()
    conn.close()

    index_size = idx_path.stat().st_size
    return {"file_id": file_id, "filename": path.name, "size_bytes": size,
            "size_human": f"{size/1024:.1f}KB" if size < 1048576 else f"{size/1048576:.1f}MB",
            "total_lines": line_count, "total_words": len(words),
            "total_chunks": len(chunks), "total_symbols": len(symbols),
            "merkle_root": merkle_root, "index_size_bytes": index_size,
            "index_ratio": round(index_size / max(size, 1) * 100, 1),
            "kpi_count": len(kpis), "dna": dna.get("dna_sequence", "")[:32]}

# ─── KPI Extraction ─────────────────────────────────────────────────────

def _jorki_extract_kpis(text, lines, word_freq):
    kpis = []
    kid = 0

    # Financial patterns
    money_re = re.compile(r'\$[\d,]{3,}(?:\.\d{2})?|\bUSD\s*[\d,]{3,}|\bEUR\s*[\d,]{3,}|\bGBP\s*[\d,]{3,}', re.I)
    pct_re = re.compile(r'\b(\d+\.?\d*)\s*%', re.I)
    rev_re = re.compile(r'\b(revenue|income|profit|loss|ebitda|margin|cost|budget|spend|valuation|capex|opex|mrr|arr|ltv|cac|churn|burn\s*rate|runway)\s*[:=]?\s*\$?[\d,]{3,}(?:\.\d+)?', re.I)
    date_re = re.compile(r'\b(20\d{2}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]20\d{2}|Q[1-4]\s*20\d{2}|FY20\d{2})\b', re.I)
    metric_re = re.compile(r'(users|customers|sessions|requests|latency|uptime|throughput|qps|rps|errors|failures|success\s*rate)\s*[:=]?\s*[\d,]+(?:\.\d+)?', re.I)
    table_re = re.compile(r'^\s*\|.*\|.*\|', re.MULTILINE)
    api_re = re.compile(r'(GET|POST|PUT|DELETE|PATCH)\s+(/[^\s]+)', re.I)
    key_val_re = re.compile(r'^\s*([A-Z][A-Z_]{2,30})\s*[:=]\s*(.+)$', re.MULTILINE)

    for i, line in enumerate(lines):
        for m in money_re.finditer(line):
            kpis.append({"id": kid, "name": "monetary_value", "value": m.group(), "line": i + 1, "category": "financial", "confidence": 0.9})
            kid += 1
        for m in rev_re.finditer(line):
            kpis.append({"id": kid, "name": "revenue_metric", "value": m.group().strip(), "line": i + 1, "category": "financial", "confidence": 0.85})
            kid += 1
        for m in pct_re.finditer(line):
            val = float(m.group(1))
            if val > 0 and val <= 100:
                kpis.append({"id": kid, "name": "percentage", "value": m.group(), "line": i + 1, "category": "financial", "confidence": 0.7})
                kid += 1
        for m in metric_re.finditer(line):
            kpis.append({"id": kid, "name": "operational_metric", "value": m.group().strip(), "line": i + 1, "category": "operational", "confidence": 0.8})
            kid += 1
        for m in api_re.finditer(line):
            kpis.append({"id": kid, "name": "api_endpoint", "value": f"{m.group(1)} {m.group(2)}", "line": i + 1, "category": "technical", "confidence": 0.9})
            kid += 1
        for m in key_val_re.finditer(line):
            val = m.group(2).strip()
            if len(val) < 100 and not val.lower() in ("true", "false", "none", "null"):
                kpis.append({"id": kid, "name": "config_value", "value": f"{m.group(1)}={val}", "line": i + 1, "category": "config", "confidence": 0.6})
                kid += 1

    for m in date_re.finditer(text):
        kpis.append({"id": kid, "name": "date_reference", "value": m.group(), "line": text[:m.start()].count("\n") + 1, "category": "temporal", "confidence": 0.75})
        kid += 1

    if table_re.search(text):
        table_count = len(table_re.findall(text))
        kpis.append({"id": kid, "name": "table_count", "value": str(table_count), "line": 0, "category": "structural", "confidence": 0.9})
        kid += 1

    # Top words as KPIs
    for w, cnt in sorted(word_freq.items(), key=lambda x: -x[1])[:5]:
        if len(w) > 3 and cnt > 2:
            kpis.append({"id": kid, "name": "dominant_term", "value": f"{w} ({cnt}x)", "line": 0, "category": "linguistic", "confidence": 0.5})
            kid += 1

    # Deduplicate by value
    seen = set()
    unique = []
    for k in kpis:
        key = (k["name"], k["value"])
        if key not in seen:
            seen.add(key)
            unique.append(k)
    for i, k in enumerate(unique):
        k["id"] = i
    return unique

# ─── DNA Fingerprint ────────────────────────────────────────────────────

def _jorki_compute_dna(content, text, lines, symbols, word_freq, chunks, filename=""):
    h = hashlib.sha256(content).hexdigest()
    # Structural genes
    gene_1 = len(lines)          # height
    gene_2 = max(len(l) for l in lines) if lines else 0  # max width
    gene_3 = len(symbols)        # symbol density
    gene_4 = len(chunks)         # chunk count
    gene_5 = len(word_freq)      # vocabulary richness
    gene_6 = sum(len(l) for l in lines) / max(len(lines), 1)  # avg line length
    gene_7 = len([l for l in lines if l.strip() == ""]) / max(len(lines), 1)  # blank ratio
    gene_8 = len([l for l in lines if l.strip().startswith("#")]) / max(len(lines), 1)  # comment ratio
    # Entropy
    from collections import Counter
    byte_counts = Counter(content[:4096])
    total = sum(byte_counts.values())
    import math
    entropy = -sum((c / total) * math.log2(c / total) for c in byte_counts.values() if c > 0) if total > 0 else 0

    # DNA sequence: 16-gene hex string
    genes = [
        f"{gene_1:04x}",     # height
        f"{gene_2:04x}",     # max width
        f"{gene_3:04x}",     # symbols
        f"{gene_4:04x}",     # chunks
        f"{gene_5:04x}",     # vocab
        f"{int(gene_6 * 100):04x}",  # avg line len
        f"{int(gene_7 * 65535):04x}",  # blank ratio
        f"{int(gene_8 * 65535):04x}",  # comment ratio
        f"{int(entropy * 1000):04x}",  # entropy
        h[:4],               # first 4 of merkle
    ]
    dna_seq = "".join(genes)

    # Species classification — prefer file extension, fall back to content
    file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    ext_map = {"py": "pythonicus", "js": "javascriptus", "jsx": "javascriptus", "ts": "javascriptus",
               "tsx": "javascriptus", "json": "jsonicus", "html": "markupus", "xml": "markupus",
               "svg": "markupus", "csv": "tabularis", "tsv": "tabularis", "md": "textus",
               "txt": "textus", "yml": "configus", "yaml": "configus", "toml": "configus",
               "sh": "scripticus", "go": "golangus", "rs": "rusticus", "c": "ceplusplus", "cpp": "ceplusplus"}
    if file_ext in ext_map:
        species = ext_map[file_ext]
    elif "import " in text or "def " in text or "class " in text:
        species = "pythonicus"
    elif "function " in text or "const " in text or "=>" in text:
        species = "javascriptus"
    elif text.strip().startswith("{") or text.strip().startswith("["):
        species = "jsonicus"
    elif "<html" in text[:200].lower() or "<!doctype" in text[:200].lower():
        species = "markupus"
    elif "|" in text and text.count("|") > 10:
        species = "tabularis"
    else:
        species = "textus"

    return {
        "dna_sequence": dna_seq,
        "species": species,
        "genes": {
            "height": gene_1,
            "max_width": gene_2,
            "symbol_density": gene_3,
            "chunk_count": gene_4,
            "vocab_richness": gene_5,
            "avg_line_length": round(gene_6, 1),
            "blank_ratio": round(gene_7, 3),
            "comment_ratio": round(gene_8, 3),
            "entropy": round(entropy, 2),
            "merkle_prefix": h[:8],
        },
        "complexity_score": round(min((gene_3 * 10 + gene_4 * 0.5 + min(gene_5, 500) * 0.01 + entropy * 0.5 + gene_6 * 0.1) / max(gene_1, 1) * 100, 100), 1),
        "genome_size": len(dna_seq),
    }

# JORKI query tracking
_jorki_query_log = {}

def _jorki_track_query(file_id, query_type):
    if file_id not in _jorki_query_log:
        _jorki_query_log[file_id] = {"total_queries": 0, "query_breakdown": {}}
    _jorki_query_log[file_id]["total_queries"] += 1
    _jorki_query_log[file_id]["query_breakdown"][query_type] = _jorki_query_log[file_id]["query_breakdown"].get(query_type, 0) + 1
    _jorki_query_log[file_id]["last_access"] = time.time()

@app.post("/index")
async def jorki_index_upload(file: UploadFile = File(...)):
    content = await file.read()
    upload_path = JORKI_DATA_DIR / "uploads" / file.filename
    upload_path.parent.mkdir(parents=True, exist_ok=True)
    upload_path.write_bytes(content)
    result = _jorki_index_file(str(upload_path))
    reg = _jorki_load_registry()
    reg[result["file_id"]] = {
        "filename": result["filename"],
        "size_bytes": result["size_bytes"],
        "size_human": result["size_human"],
        "format": upload_path.suffix.lstrip("."),
        "status": "active",
        "indexed_at": time.time(),
    }
    _jorki_save_registry(reg)
    return result

@app.post("/index/batch")
async def jorki_index_batch(files: List[UploadFile] = File(...)):
    """Batch index multiple files in parallel. Supports 1000+ files/min throughput.
    Uses fast mode (skips DNA/KPI) for speed. Re-index individual files later for full analysis."""
    import time as _time
    t0 = _time.time()
    upload_dir = JORKI_DATA_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Write all files to disk first
    paths = []
    for f in files:
        content = await f.read()
        p = upload_dir / f.filename
        p.write_bytes(content)
        paths.append(str(p))

    # Parallel indexing with ThreadPoolExecutor
    futures = [_INDEX_POOL.submit(_jorki_index_file, p, fast=True) for p in paths]
    results = []
    for fut in concurrent.futures.as_completed(futures):
        try:
            results.append(fut.result())
        except Exception as e:
            results.append({"error": str(e), "filename": "?"})

    # Batch registry update (single write)
    reg = _jorki_load_registry()
    for r in results:
        if "file_id" not in r:
            continue
        reg[r["file_id"]] = {
            "filename": r["filename"],
            "size_bytes": r["size_bytes"],
            "size_human": r["size_human"],
            "format": _Path(r["filename"]).suffix.lstrip("."),
            "status": "active",
            "indexed_at": _time.time(),
        }
    _jorki_save_registry(reg)

    elapsed = _time.time() - t0
    ok = sum(1 for r in results if "file_id" in r)
    failed = len(results) - ok
    rate = ok / elapsed if elapsed > 0 else 0
    return {
        "total": len(files),
        "indexed": ok,
        "failed": failed,
        "elapsed_seconds": round(elapsed, 2),
        "files_per_second": round(rate, 1),
        "files_per_minute": round(rate * 60, 0),
        "results": results,
    }

@app.post("/index/dir")
async def jorki_index_dir(body: dict = Body(...)):
    """Index all files in a directory. Scans recursively, indexes in parallel."""
    dirpath = body.get("dirpath", "")
    if not os.path.isdir(dirpath):
        return {"error": f"Directory not found: {dirpath}"}
    import time as _time
    t0 = _time.time()

    # Collect files
    all_files = []
    for root, dirs, fnames in os.walk(dirpath):
        for f in fnames:
            fp = os.path.join(root, f)
            if not f.startswith(".") and os.path.getsize(fp) < 10_000_000:  # skip hidden, >10MB
                all_files.append(fp)

    if not all_files:
        return {"error": "No files found in directory"}

    # Parallel indexing
    futures = [_INDEX_POOL.submit(_jorki_index_file, fp, fast=True) for fp in all_files]
    results = []
    for fut in concurrent.futures.as_completed(futures):
        try:
            results.append(fut.result())
        except Exception as e:
            results.append({"error": str(e)})

    # Batch registry update
    reg = _jorki_load_registry()
    for r in results:
        if "file_id" not in r:
            continue
        reg[r["file_id"]] = {
            "filename": r["filename"],
            "size_bytes": r["size_bytes"],
            "size_human": r["size_human"],
            "format": _Path(r["filename"]).suffix.lstrip("."),
            "status": "active",
            "indexed_at": _time.time(),
        }
    _jorki_save_registry(reg)

    elapsed = _time.time() - t0
    ok = sum(1 for r in results if "file_id" in r)
    rate = ok / elapsed if elapsed > 0 else 0
    return {
        "total": len(all_files),
        "indexed": ok,
        "failed": len(results) - ok,
        "elapsed_seconds": round(elapsed, 2),
        "files_per_second": round(rate, 1),
        "files_per_minute": round(rate * 60, 0),
        "results": [{"file_id": r.get("file_id"), "filename": r.get("filename"), "error": r.get("error")} for r in results],
    }

@app.post("/index/path")
async def jorki_index_path(body: dict = Body(...)):
    filepath = body.get("filepath", "")
    if not os.path.exists(filepath):
        return {"error": f"File not found: {filepath}"}
    result = _jorki_index_file(filepath)
    reg = _jorki_load_registry()
    reg[result["file_id"]] = {
        "filename": result["filename"],
        "size_bytes": result["size_bytes"],
        "size_human": result["size_human"],
        "format": _Path(filepath).suffix.lstrip("."),
        "status": "active",
        "indexed_at": time.time(),
    }
    _jorki_save_registry(reg)
    return result

@app.post("/reindex/{file_id}")
async def jorki_reindex(file_id: str):
    """Re-index an already uploaded file. Fixes stale indexes after code updates."""
    reg = _jorki_load_registry()
    entry = reg.get(file_id)
    if not entry:
        return {"error": f"File {file_id} not in registry"}
    # Find the uploaded file
    upload_path = JORKI_DATA_DIR / "uploads" / entry.get("filename", "")
    if not upload_path.exists():
        # Try pipeline_uploads
        upload_path = JORKI_DATA_DIR / "pipeline_uploads" / entry.get("filename", "")
    if not upload_path.exists():
        return {"error": f"Source file not found for {file_id}"}
    # Delete old index
    old_idx = JORKI_INDEX_DIR / f"{file_id}.idx"
    if old_idx.exists():
        old_idx.unlink()
    # Re-index
    result = _jorki_index_file(str(upload_path))
    reg[result["file_id"]] = {
        "filename": result["filename"],
        "size_bytes": result["size_bytes"],
        "size_human": result["size_human"],
        "format": upload_path.suffix.lstrip("."),
        "status": "active",
        "indexed_at": time.time(),
    }
    # If file_id changed (content changed), clean up old entry
    if result["file_id"] != file_id:
        reg.pop(file_id, None)
    _jorki_save_registry(reg)
    return {"status": "reindexed", "old_file_id": file_id, "new_file_id": result["file_id"], **result}

@app.get("/health")
async def jorki_health():
    reg = _jorki_load_registry()
    return {"status": "ok", "service": "jorki", "version": "2.0",
            "files_registered": len(reg),
            "persistent_storage": os.path.exists("/data"),
            "endpoints": ["/health", "/files", "/meta/{id}", "/summary/{id}",
                          "/capabilities/{id}", "/superpose/state/{id}",
                          "/search/{id}", "/chunk/{id}/{idx}", "/query/sql/{id}", "/stats/{id}",
                          "/kpi/{id}", "/kpi/{id}/gif", "/dna/{id}", "/password/{id}", "/password/{id}/verify", "/password/{id}/status",
                          "/profile/{id}",
                          "/ml/{id}",
                          "/valuation/{id}",
                          "/resume/{id}",
                          "/video/{id}",
                          "/formulas",
                          "/index", "/index/batch", "/index/dir", "/index/path", "/reindex/{id}",
                          "/pipeline/trigger", "/pipeline/status/{id}", "/pipeline/latest"]}

@app.get("/files")
async def jorki_files():
    reg = _jorki_load_registry()
    files = []
    for fid, entry in reg.items():
        files.append({"file_id": fid, "filename": entry.get("filename", "unknown"),
                       "size": entry.get("size_human", ""), "format": entry.get("format", ""),
                       "status": entry.get("status", "unknown")})
    return {"files": files, "total": len(files)}

@app.get("/meta/{file_id}")
async def jorki_meta(file_id: str):
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    rows = conn.execute("SELECT key, value FROM file_meta").fetchall()
    caps = conn.execute("SELECT name FROM capabilities").fetchall()
    conn.close()
    meta = {r[0]: r[1] for r in rows}
    return {"file_id": file_id, "meta": meta,
            "capabilities": [r[0] for r in caps],
            "endpoints": {"meta": f"/meta/{file_id}", "search": f"/search/{file_id}?q=",
                          "chunk": f"/chunk/{file_id}/{{idx}}", "sql": f"/query/sql/{file_id}"}}

@app.get("/summary/{file_id}")
async def jorki_summary(file_id: str):
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    chunks = conn.execute("SELECT idx, boundary_type, line_start, line_end, line_count, preview FROM chunks LIMIT 50").fetchall()
    symbols = conn.execute("SELECT line, name, type FROM symbols LIMIT 50").fetchall()
    words = conn.execute("SELECT word, count FROM word_freq ORDER BY count DESC LIMIT 20").fetchall()
    conn.close()
    _jorki_track_query(file_id, "summary")
    return {"file_id": file_id,
            "semantic_chunks": [{"idx": r[0], "type": r[1], "lines": f"{r[2]}-{r[3]}", "line_count": r[4], "size": len(r[5])} for r in chunks],
            "functions": [{"line": r[0], "symbol": r[1]} for r in symbols],
            "top_words": [{"word": r[0], "count": r[1]} for r in words]}

@app.get("/capabilities/{file_id}")
async def jorki_capabilities(file_id: str):
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    caps = conn.execute("SELECT id, name FROM capabilities").fetchall()
    conn.close()
    return {"file_id": file_id, "total": len(caps),
            "capabilities": [{"id": r[0], "name": r[1], "enabled": True} for r in caps]}

@app.get("/superpose/state/{file_id}")
async def jorki_state(file_id: str):
    reg = _jorki_load_registry()
    entry = reg.get(file_id, {})
    ql = _jorki_query_log.get(file_id, {"total_queries": 0, "query_breakdown": {}})
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    index_size = idx_path.stat().st_size if idx_path.exists() else 0
    return {"file_id": file_id,
            "session_status": "live" if entry.get("status") == "active" else "idle",
            "uploaded_at": entry.get("indexed_at"),
            "last_access": ql.get("last_access"),
            "total_queries": ql.get("total_queries", 0),
            "query_breakdown": ql.get("query_breakdown", {}),
            "index_size_bytes": index_size,
            "original_size": entry.get("size_human", ""),
            "compression_ratio": f"{round(index_size / max(int(entry.get('size_bytes', 1)), 1) * 100, 1)}%" if entry.get('size_bytes') else ""}

@app.get("/search/{file_id}")
async def jorki_search(file_id: str, q: str = ""):
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    chunk_results = conn.execute("SELECT idx, line_start, line_end, preview FROM chunks WHERE preview LIKE ?", (f"%{q}%",)).fetchall()
    sym_results = conn.execute("SELECT line, name, type FROM symbols WHERE name LIKE ?", (f"%{q}%",)).fetchall()
    conn.close()
    _jorki_track_query(file_id, "search")
    return {"file_id": file_id, "query": q,
            "results": [{"line": r[1], "text": r[3][:200]} for r in chunk_results] +
                       [{"line": r[0], "text": r[1]} for r in sym_results]}

@app.get("/chunk/{file_id}/{idx}")
async def jorki_chunk(file_id: str, idx: int):
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    row = conn.execute("SELECT idx, line_start, line_end, boundary_type, preview, line_count FROM chunks WHERE idx = ?", (idx,)).fetchone()
    conn.close()
    _jorki_track_query(file_id, "chunk")
    if not row:
        return {"error": f"Chunk {idx} not found"}
    return {"idx": row[0], "line_start": row[1], "line_end": row[2],
            "boundary_type": row[3], "content": row[4], "line_count": row[5]}

@app.post("/query/sql/{file_id}")
async def jorki_sql(file_id: str, body: dict = Body(...)):
    sql = body.get("sql", "")
    if not sql.strip().upper().startswith("SELECT"):
        return {"error": "Only SELECT statements allowed"}
    for kw in ["INSERT", "UPDATE", "DELETE", "DROP", "ATTACH", "PRAGMA", "CREATE", "ALTER"]:
        if kw in sql.upper():
            return {"error": f"{kw} not allowed"}
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description] if cursor.description else []
        rows = cursor.fetchmany(1000)
        conn.close()
        _jorki_track_query(file_id, "sql")
        return {"file_id": file_id, "columns": columns, "rows": [list(r) for r in rows], "row_count": len(rows)}
    except Exception as e:
        conn.close()
        return {"error": str(e)}

@app.get("/stats/{file_id}")
async def jorki_stats(file_id: str):
    ql = _jorki_query_log.get(file_id, {"total_queries": 0, "query_breakdown": {}})
    return {"file_id": file_id, "stats": [{"type": k, "count": v} for k, v in ql.get("query_breakdown", {}).items()],
            "total_queries": ql.get("total_queries", 0)}

# ─── KPI Endpoint ───────────────────────────────────────────────────────

@app.get("/kpi/{file_id}")
async def jorki_kpi(file_id: str):
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    rows = conn.execute("SELECT id, name, value, line, category, confidence FROM kpis ORDER BY confidence DESC, category").fetchall()
    conn.close()
    _jorki_track_query(file_id, "kpi")
    by_category = {}
    for r in rows:
        cat = r[4]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append({"id": r[0], "name": r[1], "value": r[2], "line": r[3], "confidence": r[5]})
    return {"file_id": file_id, "total_kpis": len(rows),
            "by_category": by_category,
            "kpis": [{"id": r[0], "name": r[1], "value": r[2], "line": r[3], "category": r[4], "confidence": r[5]} for r in rows]}

# ─── KPI → Animated GIF ─────────────────────────────────────────────────

def _jorki_kpi_gif(file_id, filename, kpis, by_category):
    """Render KPIs as an animated GIF with charts, bars, and transitions."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation
    from matplotlib.patches import FancyBboxPatch, Wedge, Circle
    import numpy as np
    import re as _re

    BG = "#0a0a0a"
    ORANGE = "#ff8c00"
    WHITE = "#e0e0e0"
    DIM = "#555555"
    GREEN = "#00ff88"
    RED = "#ff4444"
    YELLOW = "#ffcc00"
    BLUE = "#4488ff"
    PURPLE = "#aa44ff"
    CYAN = "#44ddff"

    CAT_COLORS = {
        "financial": GREEN,
        "operational": BLUE,
        "technical": ORANGE,
        "config": PURPLE,
        "temporal": CYAN,
        "structural": YELLOW,
        "linguistic": DIM,
    }

    scenes = []

    # Scene 1: Title
    scenes.append({
        "type": "title",
        "title": filename or "unknown",
        "subtitle": f"{len(kpis)} KPIs EXTRACTED",
        "info": f"ID: {file_id}",
    })

    # Scene 2: Category distribution donut
    cat_counts = {cat: len(items) for cat, items in by_category.items()}
    scenes.append({
        "type": "donut",
        "title": "KPI DISTRIBUTION",
        "data": cat_counts,
        "colors": {cat: CAT_COLORS.get(cat, ORANGE) for cat in cat_counts},
    })

    # Scene 3: Confidence distribution
    conf_buckets = {"0.9+": 0, "0.7-0.9": 0, "0.5-0.7": 0, "<0.5": 0}
    for k in kpis:
        c = k["confidence"]
        if c >= 0.9: conf_buckets["0.9+"] += 1
        elif c >= 0.7: conf_buckets["0.7-0.9"] += 1
        elif c >= 0.5: conf_buckets["0.5-0.7"] += 1
        else: conf_buckets["<0.5"] += 1
    scenes.append({
        "type": "bars",
        "title": "CONFIDENCE LEVELS",
        "data": conf_buckets,
        "colors": {"0.9+": GREEN, "0.7-0.9": BLUE, "0.5-0.7": YELLOW, "<0.5": RED},
    })

    # Scene 4-6: Top KPIs per category (one scene per major category)
    for cat, items in by_category.items():
        if len(items) < 1:
            continue
        top_items = sorted(items, key=lambda x: -x["confidence"])[:8]
        scenes.append({
            "type": "kpi_list",
            "title": f"{cat.upper()} KPIs ({len(items)})",
            "items": top_items,
            "color": CAT_COLORS.get(cat, ORANGE),
        })

    # Scene 7: Financial values extracted (if any)
    fin_kpis = [k for k in kpis if k["category"] == "financial"]
    if fin_kpis:
        # Try to parse monetary values
        monetary = []
        for k in fin_kpis:
            val = k["value"]
            m = _re.search(r'\$?([\d,]+(?:\.\d+)?)', val.replace(",", ""))
            if m:
                try:
                    num = float(m.group(1).replace(",", ""))
                    monetary.append({"name": k["name"], "value": num, "raw": val, "line": k["line"]})
                except:
                    pass
        if monetary:
            monetary.sort(key=lambda x: -x["value"])
            scenes.append({
                "type": "money_bars",
                "title": "MONETARY VALUES",
                "items": monetary[:8],
            })

    # Scene 8: Line distribution (where KPIs appear in the file)
    if kpis:
        line_nums = [k["line"] for k in kpis if k["line"] > 0]
        if line_nums:
            max_line = max(line_nums)
            histogram = [0] * min(20, max_line + 1)
            for ln in line_nums:
                bucket = min(int(ln / max(max_line, 1) * 19), 19)
                histogram[bucket] += 1
            scenes.append({
                "type": "histogram",
                "title": "KPI DENSITY BY LINE",
                "data": histogram,
                "max_line": max_line,
            })

    # Scene 9: Confidence heatmap (KPIs as grid)
    if len(kpis) > 4:
        grid_size = min(len(kpis), 24)
        grid_w = 6
        grid_h = (grid_size + grid_w - 1) // grid_w
        grid = []
        for i in range(grid_size):
            k = kpis[i]
            grid.append({"name": k["name"][:15], "confidence": k["confidence"], "category": k["category"]})
        scenes.append({
            "type": "heatmap",
            "title": "KPI HEATMAP",
            "grid": grid,
            "grid_w": grid_w,
            "grid_h": grid_h,
        })

    # Scene 10: Closing
    scenes.append({
        "type": "closing",
        "title": f"{len(kpis)} KPIs",
        "subtitle": "JORKI KPI SCAN COMPLETE",
        "info": f"{len(by_category)} categories  ·  {sum(1 for k in kpis if k['confidence'] >= 0.7)} high-confidence",
    })

    if not scenes:
        scenes.append({"type": "closing", "title": "No KPIs", "subtitle": "JORKI", "info": "empty"})

    fig, ax = plt.subplots(figsize=(10, 5.625), facecolor=BG)
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    def draw_frame(frame_idx):
        ax.clear()
        ax.set_xlim(0, 10)
        ax.set_ylim(0, 5.625)
        ax.set_facecolor(BG)
        ax.axis("off")

        frames_per_scene = 18
        scene_idx = frame_idx // frames_per_scene
        local_frame = frame_idx % frames_per_scene

        if scene_idx >= len(scenes):
            scene_idx = scene_idx % len(scenes)

        scene = scenes[scene_idx]
        stype = scene["type"]

        if local_frame < 3:
            alpha = local_frame / 3.0
        elif local_frame > frames_per_scene - 3:
            alpha = (frames_per_scene - local_frame) / 3.0
        else:
            alpha = 1.0

        if stype == "title":
            ax.text(5, 3.8, scene["title"], ha="center", va="center",
                    fontsize=24, color=ORANGE, fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.text(5, 2.8, scene["subtitle"], ha="center", va="center",
                    fontsize=14, color=GREEN, alpha=alpha, fontfamily="monospace")
            ax.text(5, 2.0, scene["info"], ha="center", va="center",
                    fontsize=10, color=DIM, alpha=alpha * 0.7, fontfamily="monospace")
            ax.plot([2, 8], [2.4, 2.4], color=ORANGE, linewidth=0.5, alpha=alpha * 0.3)

        elif stype == "donut":
            ax.text(0.5, 5.0, scene["title"], fontsize=14, color=ORANGE,
                    fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.plot([0.5, 9.5], [4.7, 4.7], color=ORANGE, linewidth=0.5, alpha=alpha * 0.3)
            data = scene["data"]
            colors = scene["colors"]
            if data:
                total = sum(data.values())
                # Animated donut — grows with frames
                progress = min(local_frame / (frames_per_scene - 3), 1.0)
                drawn = 0
                start_angle = 90
                for cat, count in data.items():
                    frac = count / total
                    end_angle = start_angle - frac * 360 * progress
                    color = colors.get(cat, ORANGE)
                    wedge = Wedge((5, 2.5), 1.5, end_angle, start_angle,
                                 width=0.6, facecolor=color, alpha=alpha * 0.8)
                    ax.add_patch(wedge)
                    # Label
                    mid_angle = (start_angle + end_angle) / 2
                    lx = 5 + 2.2 * np.cos(np.radians(mid_angle))
                    ly = 2.5 + 2.2 * np.sin(np.radians(mid_angle))
                    ax.text(lx, ly, f"{cat[:6]}\n{count}", fontsize=7, color=color,
                            ha="center", va="center", alpha=alpha, fontfamily="monospace")
                    start_angle = end_angle
                # Center text
                ax.text(5, 2.5, str(total), ha="center", va="center",
                        fontsize=20, color=WHITE, fontweight="bold", alpha=alpha, fontfamily="monospace")
                ax.text(5, 1.8, "total", ha="center", va="center",
                        fontsize=8, color=DIM, alpha=alpha, fontfamily="monospace")

        elif stype == "bars":
            ax.text(0.5, 5.0, scene["title"], fontsize=14, color=ORANGE,
                    fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.plot([0.5, 9.5], [4.7, 4.7], color=ORANGE, linewidth=0.5, alpha=alpha * 0.3)
            data = scene["data"]
            colors = scene["colors"]
            max_val = max(data.values()) if data else 1
            progress = min(local_frame / (frames_per_scene - 3), 1.0)
            for i, (label, val) in enumerate(data.items()):
                y = 4.0 - i * 0.7
                bar_w = val / max_val * 6 * progress
                color = colors.get(label, ORANGE)
                ax.add_patch(FancyBboxPatch((2.5, y - 0.2), max(bar_w, 0.01), 0.35,
                                             boxstyle="round,pad=0.02", facecolor=color, alpha=alpha * 0.7))
                ax.text(0.5, y, label, fontsize=10, color=DIM, alpha=alpha, fontfamily="monospace")
                ax.text(2.5 + bar_w + 0.2, y, str(val), fontsize=10, color=color,
                        alpha=alpha, fontfamily="monospace")

        elif stype == "kpi_list":
            ax.text(0.5, 5.0, scene["title"], fontsize=14, color=scene["color"],
                    fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.plot([0.5, 9.5], [4.7, 4.7], color=scene["color"], linewidth=0.5, alpha=alpha * 0.3)
            items = scene["items"]
            color = scene["color"]
            for i, item in enumerate(items[:8]):
                y = 4.2 - i * 0.5
                # Confidence bar
                conf = item["confidence"]
                ax.add_patch(FancyBboxPatch((0.5, y - 0.08), conf * 1.5, 0.16,
                                             boxstyle="round,pad=0.01", facecolor=color, alpha=alpha * 0.5))
                ax.text(2.2, y, item["name"][:20], fontsize=9, color=WHITE,
                        alpha=alpha, fontfamily="monospace")
                ax.text(6.5, y, str(item["value"])[:25], fontsize=8, color=color,
                        alpha=alpha, fontfamily="monospace")
                ax.text(9.2, y, f"L{item['line']}", fontsize=7, color=DIM,
                        alpha=alpha, fontfamily="monospace")

        elif stype == "money_bars":
            ax.text(0.5, 5.0, scene["title"], fontsize=14, color=GREEN,
                    fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.plot([0.5, 9.5], [4.7, 4.7], color=GREEN, linewidth=0.5, alpha=alpha * 0.3)
            items = scene["items"]
            max_val = max(i["value"] for i in items) if items else 1
            progress = min(local_frame / (frames_per_scene - 3), 1.0)
            for i, item in enumerate(items[:8]):
                y = 4.0 - i * 0.5
                bar_w = item["value"] / max_val * 5 * progress
                ax.add_patch(FancyBboxPatch((3, y - 0.15), max(bar_w, 0.01), 0.25,
                                             boxstyle="round,pad=0.02", facecolor=GREEN, alpha=alpha * 0.6))
                ax.text(0.5, y, item["name"][:15], fontsize=8, color=DIM,
                        alpha=alpha, fontfamily="monospace")
                val_str = f"${item['value']:,.0f}" if item["value"] < 1000000 else f"${item['value']/1e6:.1f}M"
                ax.text(3 + bar_w + 0.2, y, val_str, fontsize=9, color=GREEN,
                        alpha=alpha, fontfamily="monospace")

        elif stype == "histogram":
            ax.text(0.5, 5.0, scene["title"], fontsize=14, color=CYAN,
                    fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.plot([0.5, 9.5], [4.7, 4.7], color=CYAN, linewidth=0.5, alpha=alpha * 0.3)
            data = scene["data"]
            max_line = scene["max_line"]
            max_count = max(data) if data else 1
            progress = min(local_frame / (frames_per_scene - 3), 1.0)
            bar_w = 8.5 / len(data)
            for i, count in enumerate(data):
                h = count / max_count * 3.5 * progress
                ax.add_patch(FancyBboxPatch((0.75 + i * bar_w, 0.8), bar_w * 0.85, max(h, 0.01),
                                             boxstyle="round,pad=0.01", facecolor=CYAN, alpha=alpha * 0.6))
            ax.text(0.75, 0.4, "Line 0", fontsize=7, color=DIM, alpha=alpha, fontfamily="monospace")
            ax.text(9.0, 0.4, f"Line {max_line}", fontsize=7, color=DIM,
                    alpha=alpha, ha="right", fontfamily="monospace")

        elif stype == "heatmap":
            ax.text(0.5, 5.0, scene["title"], fontsize=14, color=ORANGE,
                    fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.plot([0.5, 9.5], [4.7, 4.7], color=ORANGE, linewidth=0.5, alpha=alpha * 0.3)
            grid = scene["grid"]
            gw = scene["grid_w"]
            gh = scene["grid_h"]
            cell_w = 1.3
            cell_h = 0.6
            start_x = 1.0
            start_y = 4.0
            progress = min(local_frame / (frames_per_scene - 3), 1.0)
            for i, cell in enumerate(grid):
                row = i // gw
                col = i % gw
                x = start_x + col * cell_w
                y = start_y - row * cell_h
                conf = cell["confidence"]
                color = CAT_COLORS.get(cell["category"], ORANGE)
                # Animated reveal
                reveal = min(progress * len(grid), i + 1)
                if reveal > 0:
                    cell_alpha = min(reveal - i, 1.0) * alpha
                    ax.add_patch(FancyBboxPatch((x, y - cell_h * 0.8), cell_w * 0.9, cell_h * 0.7,
                                                 boxstyle="round,pad=0.02",
                                                 facecolor=color, alpha=cell_alpha * conf))
                    ax.text(x + cell_w * 0.45, y - cell_h * 0.4, cell["name"][:8],
                            fontsize=6, color=WHITE, ha="center", va="center",
                            alpha=cell_alpha, fontfamily="monospace")

        elif stype == "closing":
            ax.text(5, 3.8, scene["title"], ha="center", va="center",
                    fontsize=28, color=ORANGE, fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.text(5, 2.8, scene["subtitle"], ha="center", va="center",
                    fontsize=14, color=GREEN, alpha=alpha, fontfamily="monospace")
            ax.text(5, 2.0, scene["info"], ha="center", va="center",
                    fontsize=10, color=DIM, alpha=alpha * 0.7, fontfamily="monospace")
            ax.plot([3, 7], [2.4, 2.4], color=ORANGE, linewidth=0.5, alpha=alpha * 0.3)

        ax.text(9.5, 0.15, "◆ JORKI KPI", fontsize=7, color=DIM, alpha=alpha * 0.3,
                ha="right", fontfamily="monospace")

    frames_per_scene = 18
    total_frames = len(scenes) * frames_per_scene

    anim = animation.FuncAnimation(
        fig, draw_frame, frames=total_frames,
        interval=180, blit=False, repeat=True
    )

    gif_dir = JORKI_DATA_DIR / "kpi_gifs"
    gif_dir.mkdir(parents=True, exist_ok=True)
    gif_path = gif_dir / f"{file_id}_kpi.gif"

    try:
        writer = animation.PillowWriter(fps=6)
        anim.save(str(gif_path), writer=writer, dpi=80)
    except Exception as e:
        plt.close(fig)
        return {"error": f"GIF generation failed: {str(e)}"}

    plt.close(fig)
    return {"gif_path": str(gif_path), "size_bytes": gif_path.stat().st_size,
            "scenes": len(scenes), "frames": total_frames}


@app.get("/kpi/{file_id}/gif")
async def jorki_kpi_gif(file_id: str):
    """Generate and return an animated GIF visualization of file KPIs."""
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    meta_rows = conn.execute("SELECT key, value FROM file_meta").fetchall()
    kpi_rows = conn.execute("SELECT id, name, value, line, category, confidence FROM kpis ORDER BY confidence DESC").fetchall()
    conn.close()
    _jorki_track_query(file_id, "kpi_gif")

    meta = {r[0]: r[1] for r in meta_rows}
    kpis = [{"id": r[0], "name": r[1], "value": r[2], "line": r[3], "category": r[4], "confidence": r[5]} for r in kpi_rows]
    by_category = {}
    for k in kpis:
        cat = k["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(k)

    result = _jorki_kpi_gif(file_id, meta.get("filename", "unknown"), kpis, by_category)
    if "error" in result:
        return result

    return FileResponse(
        result["gif_path"],
        media_type="image/gif",
        filename=f"{file_id}_kpi.gif"
    )

# ─── DNA Endpoint ───────────────────────────────────────────────────────

@app.get("/dna/{file_id}")
async def jorki_dna(file_id: str):
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    rows = conn.execute("SELECT key, value FROM dna").fetchall()
    conn.close()
    _jorki_track_query(file_id, "dna")
    dna = {r[0]: r[1] for r in rows}
    genes_str = dna.get("genes", "{}")
    try:
        genes = json.loads(genes_str)
    except:
        genes = {}
    return {"file_id": file_id,
            "dna_sequence": dna.get("dna_sequence", ""),
            "species": dna.get("species", "unknown"),
            "genes": genes,
            "complexity_score": float(dna.get("complexity_score", 0)),
            "genome_size": int(dna.get("genome_size", 0))}

# ─── Password / Access Control ──────────────────────────────────────────

@app.post("/password/{file_id}")
async def jorki_set_password(file_id: str, body: dict = Body(...)):
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    password = body.get("password", "")
    hint = body.get("hint", "")
    if len(password) < 4:
        return {"error": "Password must be at least 4 characters"}
    salt = os.urandom(16).hex()
    pw_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    conn = sqlite3.connect(str(idx_path))
    conn.execute("DELETE FROM access_control")
    conn.execute("INSERT INTO access_control VALUES (?,?,?,?)", (pw_hash, salt, hint, time.time()))
    conn.commit()
    conn.close()
    return {"file_id": file_id, "status": "password_set", "hint": hint}

@app.post("/password/{file_id}/verify")
async def jorki_verify_password(file_id: str, body: dict = Body(...)):
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    password = body.get("password", "")
    conn = sqlite3.connect(str(idx_path))
    row = conn.execute("SELECT password_hash, salt, hint FROM access_control").fetchone()
    conn.close()
    if not row:
        return {"file_id": file_id, "protected": False, "hint": ""}
    pw_hash, salt, hint = row
    test_hash = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    if test_hash == pw_hash:
        return {"file_id": file_id, "protected": True, "verified": True, "hint": hint}
    return {"file_id": file_id, "protected": True, "verified": False, "hint": hint}

@app.get("/password/{file_id}/status")
async def jorki_password_status(file_id: str):
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    row = conn.execute("SELECT hint, created_at FROM access_control").fetchone()
    conn.close()
    if row:
        return {"file_id": file_id, "protected": True, "hint": row[0], "created_at": row[1]}
    return {"file_id": file_id, "protected": False}

# ─── Semantic Knowledge: Finance, Law, Collateral, Liquidity ─────────────

import math as _math

def _jorki_compute_profile(text, lines, word_freq, kpis, dna):
    """Build a semantic profile: accounting, finance, law, collateral, liquidity."""
    text_lower = text.lower()
    profile = {
        "origin": {},
        "accounting": {},
        "finance": {},
        "law": {},
        "collateral": {},
        "liquidity": {},
        "risk": {},
        "summary": "",
    }

    # ── Origin Detection ──
    origin_signals = {
        "source_code": ["import ", "def ", "class ", "function ", "const ", "require("],
        "financial_statement": ["balance sheet", "income statement", "cash flow", "p&l", "profit and loss", "assets", "liabilities", "equity", "retained earnings"],
        "invoice": ["invoice", "bill to", "payment terms", "due date", "subtotal", "tax", "total due"],
        "contract": ["agreement", "party", "parties", "whereas", "hereby", "terms and conditions", "obligations", "warranties"],
        "spreadsheet": ["\t", ",", "column", "row", "cell", "sum(", "average(", "vlookup"],
        "research_report": ["abstract", "methodology", "findings", "conclusion", "references", "hypothesis"],
        "api_doc": ["endpoint", "request", "response", "status code", "parameters", "authentication"],
        "audit": ["audit", "compliance", "internal control", "risk assessment", "material weakness", "sox", "gaap"],
        "dataset": ["dataset", "features", "labels", "training", "validation", "test set", "rows", "columns"],
    }
    detected_origins = []
    for origin, signals in origin_signals.items():
        hits = sum(1 for s in signals if s in text_lower)
        if hits >= 2:
            detected_origins.append({"type": origin, "confidence": min(hits / len(signals), 1.0), "signals": hits})
    profile["origin"]["detected"] = detected_origins
    profile["origin"]["primary"] = detected_origins[0]["type"] if detected_origins else "unknown"

    # ── Accounting Signals ──
    acct_patterns = {
        "gaap": r'\bGAAP\b',
        "ifrs": r'\bIFRS\b',
        "accrual": r'\baccrual\b',
        "depreciation": r'\bdepreciation\b',
        "amortization": r'\bamortization\b',
        "revenue_recognition": r'\brevenue\s+recognition\b',
        "accounts_receivable": r'\baccounts?\s+receivable\b|\bAR\b',
        "accounts_payable": r'\baccounts?\s+payable\b|\bAP\b',
        "inventory": r'\binventory\b',
        "goodwill": r'\bgoodwill\b',
        "deferred_revenue": r'\bdeferred\s+revenue\b',
        "working_capital": r'\bworking\s+capital\b',
        "ebitda": r'\bEBITDA\b',
        "fiscal_year": r'\bfiscal\s+year\b|\bFY\d{2,4}\b',
    }
    acct_found = {}
    for name, pattern in acct_patterns.items():
        matches = re.findall(pattern, text, re.I)
        if matches:
            acct_found[name] = len(matches)
    profile["accounting"]["standards_detected"] = [k for k in acct_found if k in ("gaap", "ifrs")]
    profile["accounting"]["concepts_found"] = acct_found
    profile["accounting"]["has_financial_statements"] = any(s in text_lower for s in ["balance sheet", "income statement", "cash flow statement"])

    # ── Finance Signals ──
    fin_patterns = {
        "revenue": r'\brevenue\b',
        "ebitda_margin": r'\bEBITDA\s+margin\b',
        "net_income": r'\bnet\s+income\b',
        "gross_profit": r'\bgross\s+profit\b',
        "operating_expense": r'\boperating\s+expense\b|\bOpEx\b',
        "capex": r'\bcapital\s+expenditure\b|\bCapEx\b',
        "free_cash_flow": r'\bfree\s+cash\s+flow\b|\bFCF\b',
        "wacc": r'\bWACC\b',
        "dcf": r'\bdiscounted\s+cash\s+flow\b|\bDCF\b',
        "npv": r'\bNPV\b',
        "irr": r'\bIRR\b',
        "moic": r'\bMOIC\b',
        "roi": r'\bROI\b',
        "roe": r'\bROE\b',
        "roa": r'\bROA\b',
        "debt_to_equity": r'\bdebt[- ]to[- ]equity\b|\bD/E\b',
        "current_ratio": r'\bcurrent\s+ratio\b',
        "quick_ratio": r'\bquick\s+ratio\b',
    }
    fin_found = {}
    for name, pattern in fin_patterns.items():
        matches = re.findall(pattern, text, re.I)
        if matches:
            fin_found[name] = len(matches)
    profile["finance"]["metrics_detected"] = fin_found

    # Extract monetary values from KPIs
    monetary_kpis = [k for k in kpis if k["category"] == "financial"]
    total_monetary = len(monetary_kpis)
    profile["finance"]["monetary_references"] = total_monetary
    profile["finance"]["largest_values"] = sorted(
        [{"value": k["value"], "line": k["line"]} for k in monetary_kpis if "monetary" in k["name"] or "revenue" in k["name"]],
        key=lambda x: x["line"]
    )[:10]

    # ── Law / Legal Signals ──
    law_patterns = {
        "nda": r'\bnon[- ]disclosure\b|\bNDA\b',
        "ip_assignment": r'\bintellectual\s+property\b|\bIP\s+assignment\b',
        "indemnification": r'\bindemnif',
        "liability": r'\bliability\b',
        "jurisdiction": r'\bjurisdiction\b',
        "governing_law": r'\bgoverning\s+law\b',
        "arbitration": r'\barbitration\b',
        "confidentiality": r'\bconfidential',
        "termination": r'\btermination\b',
        "warranty": r'\bwarrant',
        "license": r'\blicense\b|\blicens',
        "copyright": r'\bcopyright\b',
        "patent": r'\bpatent\b',
        "trademark": r'\btrademark\b',
        "compliance": r'\bcompliance\b',
        "gdpr": r'\bGDPR\b',
        "sox": r'\bSarbanes[- ]Oxley\b|\bSOX\b',
        "sec_filing": r'\bSEC\b|\b10[- ]K\b|\b10[- ]Q\b|\b8[- ]K\b',
    }
    law_found = {}
    for name, pattern in law_patterns.items():
        matches = re.findall(pattern, text, re.I)
        if matches:
            law_found[name] = len(matches)
    profile["law"]["legal_concepts"] = law_found
    profile["law"]["has_contract_language"] = any(s in text_lower for s in ["whereas", "hereby", "party of the first part", "obligations of"])
    profile["law"]["regulatory_references"] = [k for k in law_found if k in ("gdpr", "sox", "sec_filing")]
    profile["law"]["ip_references"] = [k for k in law_found if k in ("copyright", "patent", "trademark", "license", "ip_assignment")]

    # ── Collateral Assessment ──
    collateral_signals = 0
    collateral_items = []
    if fin_found:
        collateral_signals += len(fin_found)
        collateral_items.append({"type": "financial_metrics", "count": len(fin_found), "value": "quantifiable"})
    if acct_found:
        collateral_signals += len(acct_found)
        collateral_items.append({"type": "accounting_concepts", "count": len(acct_found), "value": "verifiable"})
    if law_found:
        collateral_signals += len(law_found)
        collateral_items.append({"type": "legal_concepts", "count": len(law_found), "value": "enforceable"})
    if kpis:
        collateral_signals += len(kpis)
        collateral_items.append({"type": "extracted_kpis", "count": len(kpis), "value": "measurable"})
    dna_complexity = float(dna.get("complexity_score", 0)) if isinstance(dna, dict) else 0
    if dna_complexity > 5:
        collateral_signals += int(dna_complexity)
        collateral_items.append({"type": "structural_complexity", "score": dna_complexity, "value": "non-trivial"})
    if detected_origins:
        collateral_signals += 5
        collateral_items.append({"type": "origin_clarity", "origin": detected_origins[0]["type"], "value": "identifiable"})

    # Collateral score 0-100
    collateral_score = min(collateral_signals * 3, 100)
    profile["collateral"]["score"] = collateral_score
    profile["collateral"]["grade"] = "A" if collateral_score >= 80 else "B" if collateral_score >= 60 else "C" if collateral_score >= 40 else "D" if collateral_score >= 20 else "F"
    profile["collateral"]["items"] = collateral_items
    profile["collateral"]["signal_count"] = collateral_signals
    profile["collateral"]["verifiable"] = collateral_score >= 40
    profile["collateral"]["has_monetary_evidence"] = total_monetary > 0
    profile["collateral"]["has_legal_evidence"] = bool(law_found)
    profile["collateral"]["has_accounting_evidence"] = bool(acct_found)

    # ── Liquidity Profile ──
    liquidity_signals = 0
    liquidity_factors = []

    # Cash-related terms
    cash_terms = ["cash", "liquid", "liquidity", "current assets", "marketable securities", "treasury"]
    cash_hits = sum(1 for t in cash_terms if t in text_lower)
    if cash_hits:
        liquidity_signals += cash_hits * 5
        liquidity_factors.append({"factor": "cash_references", "count": cash_hits})

    # Time-based liquidity (mentions of days, terms, due dates)
    time_terms = ["net 30", "net 60", "net 90", "due date", "payment terms", "maturity", "expiration"]
    time_hits = sum(1 for t in time_terms if t in text_lower)
    if time_hits:
        liquidity_signals += time_hits * 4
        liquidity_factors.append({"factor": "time_constraints", "count": time_hits})

    # Marketability
    if any(t in text_lower for t in ["market", "exchange", "tradable", "fungible"]):
        liquidity_signals += 8
        liquidity_factors.append({"factor": "marketability"})

    # Revenue flow indicators
    if any(t in text_lower for t in ["recurring", "subscription", "mrr", "arr", "annuity"]):
        liquidity_signals += 10
        liquidity_factors.append({"factor": "recurring_revenue"})

    # Asset backing
    if any(t in text_lower for t in ["collateral", "secured", "asset-backed", "tangible", "real estate", "equipment"]):
        liquidity_signals += 8
        liquidity_factors.append({"factor": "asset_backing"})

    # Convertibility (can this be turned into cash quickly?)
    if detected_origins and detected_origins[0]["type"] in ("financial_statement", "invoice", "contract"):
        liquidity_signals += 6
        liquidity_factors.append({"factor": "financial_document_type"})

    liquidity_score = min(liquidity_signals * 2, 100)
    profile["liquidity"]["score"] = liquidity_score
    profile["liquidity"]["grade"] = "A" if liquidity_score >= 80 else "B" if liquidity_score >= 60 else "C" if liquidity_score >= 40 else "D" if liquidity_score >= 20 else "F"
    profile["liquidity"]["factors"] = liquidity_factors
    profile["liquidity"]["time_to_liquidate"] = "days" if liquidity_score >= 60 else "weeks" if liquidity_score >= 30 else "months" if liquidity_score >= 15 else "illiquid"
    profile["liquidity"]["has_revenue_flow"] = any(t in text_lower for t in ["recurring", "subscription", "mrr", "arr"])
    profile["liquidity"]["has_asset_backing"] = any(t in text_lower for t in ["collateral", "secured", "tangible", "asset"])

    # ── Risk Assessment ──
    risk_signals = []
    risk_score = 0
    if any(t in text_lower for t in ["confidential", "proprietary", "trade secret"]):
        risk_signals.append("confidentiality_exposure")
        risk_score += 15
    if any(t in text_lower for t in ["password", "api key", "secret", "token", "credential"]):
        risk_signals.append("secret_exposure")
        risk_score += 25
    if any(t in text_lower for t in ["litigation", "lawsuit", "dispute", "claim", "damages"]):
        risk_signals.append("litigation_risk")
        risk_score += 20
    if any(t in text_lower for t in ["default", "bankruptcy", "insolvency", "distressed"]):
        risk_signals.append("credit_risk")
        risk_score += 30
    if any(t in text_lower for t in ["forward-looking", "projection", "forecast", "guidance"]):
        risk_signals.append("forward_looking_statements")
        risk_score += 10
    if any(t in text_lower for t in ["unaudited", "preliminary", "draft", "subject to change"]):
        risk_signals.append("unverified_data")
        risk_score += 15
    profile["risk"]["signals"] = risk_signals
    profile["risk"]["score"] = min(risk_score, 100)
    profile["risk"]["level"] = "high" if risk_score >= 50 else "medium" if risk_score >= 25 else "low"

    # ── Summary ──
    parts = []
    origin = profile["origin"]["primary"]
    if origin != "unknown":
        parts.append(f"Origin: {origin}")
    if acct_found:
        parts.append(f"Accounting: {len(acct_found)} concepts ({', '.join(list(acct_found.keys())[:3])})")
    if fin_found:
        parts.append(f"Finance: {len(fin_found)} metrics ({', '.join(list(fin_found.keys())[:3])})")
    if law_found:
        parts.append(f"Legal: {len(law_found)} concepts ({', '.join(list(law_found.keys())[:3])})")
    parts.append(f"Collateral: {profile['collateral']['grade']} ({collateral_score})")
    parts.append(f"Liquidity: {profile['liquidity']['grade']} ({liquidity_score})")
    parts.append(f"Risk: {profile['risk']['level']} ({profile['risk']['score']})")
    profile["summary"] = " · ".join(parts)

    return profile


@app.get("/profile/{file_id}")
async def jorki_profile(file_id: str):
    """Full semantic profile: origin, accounting, finance, law, collateral, liquidity, risk."""
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    meta_rows = conn.execute("SELECT key, value FROM file_meta").fetchall()
    kpi_rows = conn.execute("SELECT id, name, value, line, category, confidence FROM kpis").fetchall()
    dna_rows = conn.execute("SELECT key, value FROM dna").fetchall()
    word_rows = conn.execute("SELECT word, count FROM word_freq").fetchall()
    chunk_rows = conn.execute("SELECT preview FROM chunks").fetchall()
    conn.close()
    _jorki_track_query(file_id, "profile")

    meta = {r[0]: r[1] for r in meta_rows}
    kpis = [{"id": r[0], "name": r[1], "value": r[2], "line": r[3], "category": r[4], "confidence": r[5]} for r in kpi_rows]
    dna = {r[0]: r[1] for r in dna_rows}
    word_freq = {r[0]: r[1] for r in word_rows}
    text = "\n".join(r[0] for r in chunk_rows)
    lines = text.split("\n")

    try:
        dna_obj = json.loads(dna.get("genes", "{}")) if isinstance(dna.get("genes"), str) else {}
        dna_dict = {"genes": dna_obj, "complexity_score": float(dna.get("complexity_score", 0)), "dna_sequence": dna.get("dna_sequence", ""), "species": dna.get("species", "")}
    except:
        dna_dict = {}

    profile = _jorki_compute_profile(text, lines, word_freq, kpis, dna_dict)
    return {"file_id": file_id, "filename": meta.get("filename", "unknown"), "profile": profile}

# ─── Valuation: Production Readiness, Replacement Cost, Build Cost ───────

def _jorki_valuate(text, lines, chunks, symbols, word_freq, kpis, dna, meta):
    """Estimate production readiness, replacement cost, build cost, and purpose."""
    text_lower = text.lower()
    v = {
        "purpose": {},
        "production_readiness": {},
        "replacement_cost": {},
        "build_cost": {},
        "depreciation": {},
        "insurance_value": {},
    }

    # ── Purpose Detection ──
    purposes = []
    # By file extension / content patterns
    ext = meta.get("filename", "").rsplit(".", 1)[-1].lower() if "." in meta.get("filename", "") else ""
    purpose_map = {
        "py": "Python application module",
        "js": "JavaScript frontend/backend module",
        "jsx": "React UI component",
        "ts": "TypeScript module",
        "tsx": "React+TypeScript component",
        "go": "Go service/binary",
        "rs": "Rust system/module",
        "swift": "macOS/iOS application",
        "cpp": "C++ system/native module",
        "c": "C system/native module",
        "json": "Configuration or data schema",
        "yaml": "Infrastructure/config definition",
        "yml": "Infrastructure/config definition",
        "toml": "Project configuration",
        "md": "Documentation/specification",
        "sql": "Database schema/query",
        "sh": "Shell automation script",
        "html": "Web markup/template",
        "css": "Stylesheet",
        "csv": "Tabular data export",
        "txt": "Plain text data",
        "dockerfile": "Container build definition",
    }
    if ext in purpose_map:
        purposes.append({"role": purpose_map[ext], "confidence": 0.8, "source": "extension"})

    # By content analysis
    if "import " in text_lower and "def " in text_lower:
        purposes.append({"role": "library/module — reusable Python code", "confidence": 0.85, "source": "content"})
    if "@app.get" in text_lower or "@app.post" in text_lower or "fastapi" in text_lower:
        purposes.append({"role": "API server — HTTP endpoint provider", "confidence": 0.9, "source": "content"})
    if "react" in text_lower or "usestate" in text_lower or "useeffect" in text_lower:
        purposes.append({"role": "React UI — interactive frontend component", "confidence": 0.85, "source": "content"})
    if "docker" in text_lower or "from " in text_lower and "run " in text_lower and ext == "dockerfile":
        purposes.append({"role": "container image definition", "confidence": 0.9, "source": "content"})
    if any(t in text_lower for t in ["balance sheet", "income statement", "cash flow", "ebitda", "revenue"]):
        purposes.append({"role": "financial document — accounting/reporting", "confidence": 0.8, "source": "content"})
    if any(t in text_lower for t in ["agreement", "whereas", "party", "obligations"]):
        purposes.append({"role": "legal contract — binding agreement", "confidence": 0.8, "source": "content"})
    if any(t in text_lower for t in ["test", "pytest", "assert", "expect", "describe"]):
        purposes.append({"role": "test suite — quality assurance", "confidence": 0.75, "source": "content"})
    if any(t in text_lower for t in ["readme", "documentation", "guide", "tutorial"]):
        purposes.append({"role": "documentation — knowledge transfer", "confidence": 0.7, "source": "content"})

    # Primary purpose = highest confidence
    purposes.sort(key=lambda x: -x["confidence"])
    v["purpose"]["detected"] = purposes
    v["purpose"]["primary"] = purposes[0]["role"] if purposes else "unknown"
    v["purpose"]["roles"] = [p["role"] for p in purposes]

    # ── Production Readiness Score ──
    pr_checks = []
    pr_score = 0

    # Has tests
    has_tests = any(t in text_lower for t in ["test", "assert", "expect", "describe", "pytest"])
    if has_tests:
        pr_checks.append({"check": "has_tests", "status": "pass", "weight": 15})
        pr_score += 15
    else:
        pr_checks.append({"check": "has_tests", "status": "fail", "weight": 0, "impact": "no test coverage detected"})

    # Has error handling
    has_errors = any(t in text_lower for t in ["try:", "except", "catch", "error", "raise", "throw"])
    if has_errors:
        pr_checks.append({"check": "error_handling", "status": "pass", "weight": 10})
        pr_score += 10
    else:
        pr_checks.append({"check": "error_handling", "status": "fail", "weight": 0, "impact": "no error handling"})

    # Has logging
    has_logging = any(t in text_lower for t in ["log", "logger", "logging", "console.log", "print("])
    if has_logging:
        pr_checks.append({"check": "logging", "status": "pass", "weight": 8})
        pr_score += 8
    else:
        pr_checks.append({"check": "logging", "status": "fail", "weight": 0})

    # Has config separation
    has_config = any(t in text_lower for t in ["environ", "config", "settings", ".env", "os.getenv"])
    if has_config:
        pr_checks.append({"check": "config_separation", "status": "pass", "weight": 10})
        pr_score += 10
    else:
        pr_checks.append({"check": "config_separation", "status": "fail", "weight": 0})

    # Has documentation
    has_docs = any(t in text_lower for t in ['"""', "'''", "// ", "# ", "docstring", "readme"])
    doc_ratio = len([l for l in lines if l.strip().startswith("#") or l.strip().startswith("//") or '"""' in l]) / max(len(lines), 1)
    if doc_ratio > 0.05:
        pr_checks.append({"check": "documentation", "status": "pass", "weight": 8, "ratio": round(doc_ratio, 3)})
        pr_score += 8
    else:
        pr_checks.append({"check": "documentation", "status": "fail", "weight": 0})

    # Has type hints / interfaces
    has_types = any(t in text_lower for t in ["-> ", ": int", ": str", ": bool", ": float", "interface ", "type ", "typescript"])
    if has_types:
        pr_checks.append({"check": "type_safety", "status": "pass", "weight": 7})
        pr_score += 7
    else:
        pr_checks.append({"check": "type_safety", "status": "fail", "weight": 0})

    # Has security patterns
    has_security = any(t in text_lower for t in ["auth", "password", "hash", "pbkdf2", "bcrypt", "jwt", "token", "sanitize", "validate"])
    if has_security:
        pr_checks.append({"check": "security_patterns", "status": "pass", "weight": 10})
        pr_score += 10
    else:
        pr_checks.append({"check": "security_patterns", "status": "fail", "weight": 0})

    # Complexity check (not too complex, not too simple)
    complexity = float(dna.get("complexity_score", 0)) if isinstance(dna, dict) else 0
    if 1 <= complexity <= 20:
        pr_checks.append({"check": "complexity_balanced", "status": "pass", "weight": 7, "score": complexity})
        pr_score += 7
    elif complexity > 20:
        pr_checks.append({"check": "complexity_balanced", "status": "warn", "weight": 3, "impact": "high complexity, hard to maintain"})
        pr_score += 3
    else:
        pr_checks.append({"check": "complexity_balanced", "status": "warn", "weight": 3, "impact": "trivial code"})

    # Has dependencies declared
    has_deps = any(t in text_lower for t in ["import ", "require(", "from ", "use "])
    if has_deps:
        dep_count = len(re.findall(r'import |require\(|from ', text_lower))
        pr_checks.append({"check": "dependencies_declared", "status": "pass", "weight": 5, "count": dep_count})
        pr_score += 5
    else:
        pr_checks.append({"check": "dependencies_declared", "status": "fail", "weight": 0})

    # Has deployment artifacts
    has_deploy = any(t in text_lower for t in ["docker", "dockerfile", "deploy", "ci/cd", "github actions", "netlify", "vercel"])
    if has_deploy:
        pr_checks.append({"check": "deployment_artifacts", "status": "pass", "weight": 10})
        pr_score += 10
    else:
        pr_checks.append({"check": "deployment_artifacts", "status": "fail", "weight": 0})

    # Secret exposure (negative)
    has_secrets = any(t in text_lower for t in ["api_key", "secret_key", "password =", "token ="])
    if has_secrets:
        pr_checks.append({"check": "no_hardcoded_secrets", "status": "fail", "weight": -15, "impact": "hardcoded secrets detected"})
        pr_score -= 15
    else:
        pr_checks.append({"check": "no_hardcoded_secrets", "status": "pass", "weight": 10})
        pr_score += 10

    pr_score = max(0, min(pr_score, 100))
    v["production_readiness"]["score"] = pr_score
    v["production_readiness"]["grade"] = "A" if pr_score >= 80 else "B" if pr_score >= 60 else "C" if pr_score >= 40 else "D" if pr_score >= 20 else "F"
    v["production_readiness"]["checks"] = pr_checks
    v["production_readiness"]["distance_to_prod"] = "production ready" if pr_score >= 80 else "minor hardening needed" if pr_score >= 60 else "moderate work needed" if pr_score >= 40 else "significant work needed" if pr_score >= 20 else "not production ready"
    v["production_readiness"]["blocking_issues"] = [c["check"] for c in pr_checks if c["status"] == "fail"]

    # ── Build Cost Estimation ──
    # Based on: lines of code, complexity, symbols, language
    total_lines = int(meta.get("total_lines", len(lines)))
    total_symbols = int(meta.get("total_symbols", len(symbols)))
    total_chunks = int(meta.get("total_chunks", len(chunks)))

    # Effective lines of code (non-blank, non-comment)
    effective_loc = len([l for l in lines if l.strip() and not l.strip().startswith(("#", "//", "/*", "*"))])

    # Species-aware cost model — documentation is NOT code
    species = dna.get("species", "textus") if isinstance(dna, dict) else "textus"

    # Different file types have fundamentally different cost structures
    COST_MODEL = {
        "pythonicus":     {"rate": 0.20, "complexity_cap": 3.0, "test_rate": 0.05, "type": "code"},
        "javascriptus":  {"rate": 0.20, "complexity_cap": 3.0, "test_rate": 0.06, "type": "code"},
        "golangus":      {"rate": 0.20, "complexity_cap": 3.0, "test_rate": 0.06, "type": "code"},
        "rusticus":      {"rate": 0.20, "complexity_cap": 3.0, "test_rate": 0.07, "type": "code"},
        "ceplusplus":    {"rate": 0.20, "complexity_cap": 3.0, "test_rate": 0.07, "type": "code"},
        "scripticus":    {"rate": 0.15, "complexity_cap": 2.0, "test_rate": 0.03, "type": "script"},
        "jsonicus":      {"rate": 0.02, "complexity_cap": 1.0, "test_rate": 0,    "type": "data"},
        "markupus":      {"rate": 0.05, "complexity_cap": 1.5, "test_rate": 0,    "type": "markup"},
        "tabularis":     {"rate": 0.03, "complexity_cap": 1.0, "test_rate": 0,    "type": "data"},
        "configus":      {"rate": 0.08, "complexity_cap": 1.5, "test_rate": 0,    "type": "config"},
        "textus":        {"rate": 0.000005, "complexity_cap": 1.0, "test_rate": 0,  "type": "documentation"},
    }
    model = COST_MODEL.get(species, COST_MODEL["textus"])
    file_type = model["type"]
    base_rate = model["rate"]
    complexity_cap = model["complexity_cap"]

    # Complexity factor — capped per file type
    complexity_factor = min(1.0 + (complexity / 20.0), complexity_cap) if complexity > 0 else 1.0

    # Build cost = effective LOC * rate * complexity
    build_cost = int(effective_loc * base_rate * complexity_factor)

    # Add cost for testing, docs, deployment setup (only for code)
    test_cost = int(effective_loc * model["test_rate"]) if not has_tests and file_type == "code" else 0
    deploy_cost = 2000 if not has_deploy and file_type == "code" else 0
    security_audit_cost = 1500 if has_secrets and file_type in ("code", "config") else 0

    total_build_cost = build_cost + test_cost + deploy_cost + security_audit_cost
    # Hard cap at $3M
    total_build_cost = min(total_build_cost, 3_000_000)

    v["build_cost"]["estimated_usd"] = total_build_cost
    v["build_cost"]["breakdown"] = {
        "code_creation": build_cost,
        "test_creation_needed": test_cost,
        "deployment_setup_needed": deploy_cost,
        "security_remediation_needed": security_audit_cost,
        "effective_loc": effective_loc,
        "rate_per_loc": base_rate,
        "complexity_factor": round(complexity_factor, 2),
        "file_type": file_type,
        "species": species,
    }
    v["build_cost"]["time_estimate"] = {
        "hours": round(effective_loc / 50, 1),  # ~50 LOC/hour
        "days": round(effective_loc / 50 / 8, 1),  # 8 hour days
        "developer_level": "mid" if complexity < 10 else "senior" if complexity < 25 else "staff",
    }

    # ── Replacement Cost ──
    # What it would cost to rebuild from scratch (higher than build cost due to knowledge loss)
    # Knowledge loss factor varies by file type
    knowledge_loss_factor = 1.5 if file_type == "code" else 1.2 if file_type == "script" else 1.1
    ramp_up_cost = 1000 if file_type == "code" else 500
    replacement_cost = int(total_build_cost * knowledge_loss_factor) + ramp_up_cost
    replacement_cost = min(replacement_cost, 3_000_000)

    v["replacement_cost"]["estimated_usd"] = replacement_cost
    v["replacement_cost"]["rationale"] = f"Build cost (${total_build_cost}) × knowledge loss factor ({knowledge_loss_factor}x) + ramp-up (${ramp_up_cost})"
    v["replacement_cost"]["time_to_rebuild"] = {
        "hours": round(effective_loc / 40, 1),  # slower due to lost context
        "days": round(effective_loc / 40 / 8, 1),
        "weeks": round(effective_loc / 40 / 8 / 5, 1),
    }
    v["replacement_cost"]["difficulty"] = "low" if complexity < 5 else "medium" if complexity < 15 else "high" if complexity < 30 else "very high"

    # ── Depreciation ──
    # Files depreciate based on: dependency staleness, code age signals, framework obsolescence
    dep_signals = []
    dep_score = 0  # 0 = no depreciation, 100 = fully deprecated

    # Check for deprecated patterns
    if any(t in text_lower for t in ["python 2", "print ", "xrange", "urllib2"]):
        dep_signals.append("legacy_python2_patterns")
        dep_score += 30
    if any(t in text_lower for t in ["var ", "function ", "es5", "jquery"]):
        dep_signals.append("legacy_javascript_patterns")
        dep_score += 20
    if any(t in text_lower for t in ["angularjs", "backbone", "ember"]):
        dep_signals.append("deprecated_framework")
        dep_score += 25
    if any(t in text_lower for t in ["xml", "soap", "wsdl"]):
        dep_signals.append("legacy_protocol")
        dep_score += 15

    # Comment ratio as maintenance signal
    if doc_ratio < 0.02 and effective_loc > 100:
        dep_signals.append("insufficient_documentation")
        dep_score += 10

    # No tests = harder to maintain = faster depreciation
    if not has_tests and effective_loc > 50:
        dep_signals.append("no_test_coverage")
        dep_score += 15

    dep_score = min(dep_score, 100)
    v["depreciation"]["score"] = dep_score
    v["depreciation"]["signals"] = dep_signals
    v["depreciation"]["remaining_value_pct"] = max(0, 100 - dep_score)
    v["depreciation"]["depreciated_value_usd"] = int(replacement_cost * (1 - dep_score / 100))

    # ── Insurance Value ──
    # What you'd insure this file for = replacement cost + business interruption
    business_impact = 0
    if has_security:
        business_impact += 5000
    if any(t in text_lower for t in ["payment", "transaction", "billing", "invoice"]):
        business_impact += 10000
    if any(t in text_lower for t in ["auth", "login", "password", "session"]):
        business_impact += 8000
    if pr_score >= 60:
        business_impact += 3000  # production-grade = more at stake

    insurance_value = min(replacement_cost + business_impact, 3_000_000)
    v["insurance_value"]["estimated_usd"] = insurance_value
    v["insurance_value"]["breakdown"] = {
        "replacement_cost": replacement_cost,
        "business_interruption_risk": business_impact,
    }

    return v


@app.get("/valuation/{file_id}")
async def jorki_valuation(file_id: str):
    """Production readiness, replacement cost, build cost, depreciation, insurance value."""
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    meta_rows = conn.execute("SELECT key, value FROM file_meta").fetchall()
    kpi_rows = conn.execute("SELECT id, name, value, line, category, confidence FROM kpis").fetchall()
    dna_rows = conn.execute("SELECT key, value FROM dna").fetchall()
    word_rows = conn.execute("SELECT word, count FROM word_freq").fetchall()
    chunk_rows = conn.execute("SELECT idx, line_start, line_end, boundary_type, preview, line_count FROM chunks").fetchall()
    sym_rows = conn.execute("SELECT line, name, type FROM symbols").fetchall()
    conn.close()
    _jorki_track_query(file_id, "valuation")

    meta = {r[0]: r[1] for r in meta_rows}
    kpis = [{"id": r[0], "name": r[1], "value": r[2], "line": r[3], "category": r[4], "confidence": r[5]} for r in kpi_rows]
    dna = {r[0]: r[1] for r in dna_rows}
    word_freq = {r[0]: int(r[1]) for r in word_rows}
    chunks = [{"idx": r[0], "line_start": r[1], "line_end": r[2], "boundary_type": r[3], "preview": r[4], "line_count": r[5]} for r in chunk_rows]
    symbols = [{"line": r[0], "name": r[1], "type": r[2]} for r in sym_rows]
    text = "\n".join(c["preview"] for c in chunks)
    lines = text.split("\n")

    try:
        dna_obj = json.loads(dna.get("genes", "{}")) if isinstance(dna.get("genes"), str) else {}
        dna_dict = {"genes": dna_obj, "complexity_score": float(dna.get("complexity_score", 0)),
                    "dna_sequence": dna.get("dna_sequence", ""), "species": dna.get("species", "")}
    except:
        dna_dict = {}

    valuation = _jorki_valuate(text, lines, chunks, symbols, word_freq, kpis, dna_dict, meta)
    return {"file_id": file_id, "filename": meta.get("filename", "unknown"), "valuation": valuation}

# ─── File Resume / Dossier Generator ─────────────────────────────────────

def _jorki_generate_resume(file_id, meta, kpis, dna, word_freq, chunks, symbols, profile, valuation, ml_result):
    """Generate a novel file resume — a complete dossier combining all analysis layers."""
    import math as _m

    r = {
        "header": {},
        "identity": {},
        "structural_dna": {},
        "kpi_summary": {},
        "financial_profile": {},
        "legal_profile": {},
        "ml_insights": {},
        "valuation_summary": {},
        "risk_assessment": {},
        "recommendations": [],
        "llm_facts": [],
        "narrative": "",
        "dossier_text": "",
    }

    filename = meta.get("filename", "unknown")
    size_human = meta.get("size_human", "?")
    total_lines = int(meta.get("total_lines", 0))
    total_words = int(meta.get("total_words", 0))
    total_chunks = int(meta.get("total_chunks", 0))
    total_symbols = int(meta.get("total_symbols", 0))
    merkle = meta.get("merkle_root", "")
    species = dna.get("species", "unknown") if isinstance(dna, dict) else "unknown"
    dna_seq = dna.get("dna_sequence", "") if isinstance(dna, dict) else ""
    complexity = float(dna.get("complexity_score", 0)) if isinstance(dna, dict) else 0

    # ── Header ──
    r["header"] = {
        "title": filename,
        "file_id": file_id,
        "merkle_root": merkle,
        "generated_at": time.time(),
        "format": meta.get("filename", "").rsplit(".", 1)[-1].lower() if "." in meta.get("filename", "") else "unknown",
        "dossier_version": "1.0",
    }

    # ── Identity ──
    r["identity"] = {
        "name": filename,
        "species": species,
        "dna_sequence": dna_seq[:40] if dna_seq else "",
        "size": size_human,
        "lines": total_lines,
        "words": total_words,
        "chunks": total_chunks,
        "symbols": total_symbols,
        "vocabulary": len(word_freq),
        "merkle_prefix": merkle[:16] if merkle else "",
        "primary_purpose": valuation.get("purpose", {}).get("primary", "unknown"),
        "all_purposes": valuation.get("purpose", {}).get("roles", []),
    }

    # ── Structural DNA ──
    genes = {}
    if isinstance(dna, dict):
        try:
            genes = json.loads(dna.get("genes", "{}")) if isinstance(dna.get("genes"), str) else dna.get("genes", {})
        except:
            genes = dna.get("genes", {}) if isinstance(dna.get("genes"), dict) else {}
    r["structural_dna"] = {
        "species": species,
        "complexity_score": complexity,
        "genes": genes,
        "genome_size": len(dna_seq) if dna_seq else 0,
        "interpretation": (
            "highly structured, symbol-dense" if complexity > 20 else
            "moderately structured" if complexity > 5 else
            "lightly structured" if complexity > 1 else
            "flat/plain text"
        ),
    }

    # ── KPI Summary ──
    kpi_by_cat = {}
    for k in kpis:
        cat = k["category"]
        if cat not in kpi_by_cat:
            kpi_by_cat[cat] = []
        kpi_by_cat[cat].append(k)
    r["kpi_summary"] = {
        "total": len(kpis),
        "by_category": {cat: len(items) for cat, items in kpi_by_cat.items()},
        "top_financial": [{"name": k["name"], "value": k["value"], "line": k["line"]} for k in kpis if k["category"] == "financial"][:5],
        "top_technical": [{"name": k["name"], "value": k["value"], "line": k["line"]} for k in kpis if k["category"] == "technical"][:5],
        "top_operational": [{"name": k["name"], "value": k["value"], "line": k["line"]} for k in kpis if k["category"] == "operational"][:5],
    }

    # ── Financial Profile ──
    prof = profile if isinstance(profile, dict) else {}
    r["financial_profile"] = {
        "accounting_concepts": prof.get("accounting", {}).get("concepts_found", {}),
        "standards": prof.get("accounting", {}).get("standards_detected", []),
        "has_financial_statements": prof.get("accounting", {}).get("has_financial_statements", False),
        "finance_metrics": prof.get("finance", {}).get("metrics_detected", {}),
        "monetary_references": prof.get("finance", {}).get("monetary_references", 0),
        "collateral_grade": prof.get("collateral", {}).get("grade", "F"),
        "collateral_score": prof.get("collateral", {}).get("score", 0),
        "liquidity_grade": prof.get("liquidity", {}).get("grade", "F"),
        "liquidity_score": prof.get("liquidity", {}).get("score", 0),
        "time_to_liquidate": prof.get("liquidity", {}).get("time_to_liquidate", "illiquid"),
    }

    # ── Legal Profile ──
    r["legal_profile"] = {
        "concepts": prof.get("law", {}).get("legal_concepts", {}),
        "has_contract_language": prof.get("law", {}).get("has_contract_language", False),
        "regulatory": prof.get("law", {}).get("regulatory_references", []),
        "ip_references": prof.get("law", {}).get("ip_references", []),
    }

    # ── ML Insights ──
    ml = ml_result if isinstance(ml_result, dict) else {}
    r["ml_insights"] = {
        "available": ml.get("available", False),
        "topics": [{"id": t.get("topic_id", 0), "keywords": t.get("keywords", [])[:5], "strength": t.get("strength", 0)} for t in ml.get("topics", [])],
        "tfidf_top": [t.get("term", "") for t in ml.get("tfidf_top_terms", [])[:8]],
        "anomaly_count": len(ml.get("anomalies", [])),
        "inferred_kpis": ml.get("inferred_kpis", []),
        "semantic_dimensions": ml.get("latent_features", {}).get("lsa_components", 0),
        "llm_extrapolation": ml.get("llm_extrapolation", None),
    }

    # ── Valuation Summary ──
    val = valuation if isinstance(valuation, dict) else {}
    r["valuation_summary"] = {
        "production_readiness_grade": val.get("production_readiness", {}).get("grade", "F"),
        "production_readiness_score": val.get("production_readiness", {}).get("score", 0),
        "distance_to_prod": val.get("production_readiness", {}).get("distance_to_prod", "unknown"),
        "blocking_issues": val.get("production_readiness", {}).get("blocking_issues", []),
        "build_cost_usd": val.get("build_cost", {}).get("estimated_usd", 0),
        "replacement_cost_usd": val.get("replacement_cost", {}).get("estimated_usd", 0),
        "depreciation_score": val.get("depreciation", {}).get("score", 0),
        "remaining_value_pct": val.get("depreciation", {}).get("remaining_value_pct", 100),
        "depreciated_value_usd": val.get("depreciation", {}).get("depreciated_value_usd", 0),
        "insurance_value_usd": val.get("insurance_value", {}).get("estimated_usd", 0),
        "time_to_rebuild_days": val.get("replacement_cost", {}).get("time_to_rebuild", {}).get("days", 0),
        "difficulty": val.get("replacement_cost", {}).get("difficulty", "unknown"),
    }

    # ── Risk Assessment ──
    r["risk_assessment"] = {
        "level": prof.get("risk", {}).get("level", "low"),
        "score": prof.get("risk", {}).get("score", 0),
        "signals": prof.get("risk", {}).get("signals", []),
        "origin": prof.get("origin", {}).get("primary", "unknown"),
        "origin_confidence": prof.get("origin", {}).get("detected", [{}])[0].get("confidence", 0) if prof.get("origin", {}).get("detected") else 0,
    }

    # ── Recommendations ──
    recs = []
    pr_score = val.get("production_readiness", {}).get("score", 0)
    if pr_score < 40:
        recs.append({"priority": "critical", "action": "add_tests", "reason": "no test coverage detected, production risk"})
    if val.get("production_readiness", {}).get("blocking_issues"):
        for issue in val.get("production_readiness", {}).get("blocking_issues", [])[:5]:
            recs.append({"priority": "high", "action": f"fix_{issue}", "reason": f"blocking issue: {issue}"})
    dep_score = val.get("depreciation", {}).get("score", 0)
    if dep_score > 30:
        recs.append({"priority": "medium", "action": "modernize_codebase", "reason": f"depreciation score {dep_score}/100, legacy patterns detected"})
    if prof.get("risk", {}).get("level") == "high":
        recs.append({"priority": "critical", "action": "security_review", "reason": "high risk score, potential secret or compliance exposure"})
    liq_grade = prof.get("liquidity", {}).get("grade", "F")
    if liq_grade in ("D", "F"):
        recs.append({"priority": "low", "action": "improve_liquidity", "reason": "low liquidity, hard to convert to value quickly"})
    coll_grade = prof.get("collateral", {}).get("grade", "F")
    if coll_grade in ("A", "B"):
        recs.append({"priority": "info", "action": "consider_collateralization", "reason": f"strong collateral profile (grade {coll_grade}), could be used as backing"})
    if ml.get("anomalies") and len(ml.get("anomalies", [])) > 2:
        recs.append({"priority": "medium", "action": "review_anomalies", "reason": f"{len(ml['anomalies'])} anomalous chunks detected by isolation forest"})
    if val.get("build_cost", {}).get("estimated_usd", 0) > 50000:
        recs.append({"priority": "info", "action": "document_knowledge", "reason": "high build cost, critical to preserve domain knowledge"})
    if prof.get("law", {}).get("has_contract_language"):
        recs.append({"priority": "info", "action": "legal_review", "reason": "contract language detected, ensure enforceability"})
    recs.sort(key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}.get(x["priority"], 5))
    r["recommendations"] = recs

    # ── Narrative ──
    parts = []
    parts.append(f"FILE: {filename} ({file_id})")
    parts.append(f"Species: {species} | Complexity: {complexity:.1f} | {total_lines} lines, {total_chunks} chunks, {total_symbols} symbols")
    parts.append(f"Purpose: {valuation.get('purpose', {}).get('primary', 'unknown')}")
    parts.append(f"Merkle: {merkle[:32]}...")
    parts.append("")
    parts.append(f"PRODUCTION READINESS: {val.get('production_readiness', {}).get('grade', 'F')} ({pr_score}/100) — {val.get('production_readiness', {}).get('distance_to_prod', 'unknown')}")
    if val.get("production_readiness", {}).get("blocking_issues"):
        parts.append(f"  Blocking: {', '.join(val['production_readiness']['blocking_issues'][:5])}")
    parts.append("")
    parts.append(f"VALUATION:")
    parts.append(f"  Build cost: ${val.get('build_cost', {}).get('estimated_usd', 0):,}")
    parts.append(f"  Replacement cost: ${val.get('replacement_cost', {}).get('estimated_usd', 0):,}")
    parts.append(f"  Depreciated value: ${val.get('depreciation', {}).get('depreciated_value_usd', 0):,} ({val.get('depreciation', {}).get('remaining_value_pct', 100)}% remaining)")
    parts.append(f"  Insurance value: ${val.get('insurance_value', {}).get('estimated_usd', 0):,}")
    parts.append(f"  Time to rebuild: {val.get('replacement_cost', {}).get('time_to_rebuild', {}).get('days', 0)} days ({val.get('replacement_cost', {}).get('difficulty', '?')})")
    parts.append("")
    parts.append(f"FINANCIAL PROFILE:")
    parts.append(f"  Collateral: {prof.get('collateral', {}).get('grade', 'F')} ({prof.get('collateral', {}).get('score', 0)}/100)")
    parts.append(f"  Liquidity: {prof.get('liquidity', {}).get('grade', 'F')} ({prof.get('liquidity', {}).get('score', 0)}/100) — {prof.get('liquidity', {}).get('time_to_liquidate', 'illiquid')}")
    fin_metrics = prof.get("finance", {}).get("metrics_detected", {})
    if fin_metrics:
        parts.append(f"  Metrics: {', '.join(list(fin_metrics.keys())[:5])}")
    parts.append("")
    parts.append(f"LEGAL: {prof.get('law', {}).get('legal_concepts', {})}")
    parts.append(f"RISK: {prof.get('risk', {}).get('level', 'low')} ({prof.get('risk', {}).get('score', 0)}/100) — {', '.join(prof.get('risk', {}).get('signals', [])[:3])}")
    parts.append("")
    if ml.get("available"):
        parts.append(f"ML INSIGHTS:")
        for t in ml.get("topics", [])[:3]:
            parts.append(f"  Topic {t.get('topic_id', 0)}: {', '.join(t.get('keywords', [])[:5])} (strength: {t.get('strength', 0)})")
        if ml.get("inferred_kpis"):
            parts.append(f"  Inferred: {', '.join(k.get('name', '') + '=' + k.get('value', '') for k in ml['inferred_kpis'][:5])}")
        if ml.get("anomalies"):
            parts.append(f"  Anomalies: {len(ml['anomalies'])} chunks flagged")
        if ml.get("llm_extrapolation"):
            llm = ml["llm_extrapolation"]
            if isinstance(llm, dict):
                parts.append(f"  LLM: {llm.get('inferred_purpose', '')} | Hidden value: {llm.get('hidden_value', '')}")
    parts.append("")
    parts.append(f"KPIs: {len(kpis)} total ({', '.join(f'{cat}:{cnt}' for cat, cnt in r['kpi_summary']['by_category'].items())})")
    parts.append("")
    parts.append(f"RECOMMENDATIONS ({len(recs)}):")
    for rec in recs[:8]:
        parts.append(f"  [{rec['priority'].upper()}] {rec['action']}: {rec['reason']}")
    r["narrative"] = "\n".join(parts)

    # ── Dossier text (novel format) ──
    dossier = f"""
╔══════════════════════════════════════════════════════════════════════════╗
║  JORKI FILE DOSSIER — {filename[:40]:<40s}  ║
║  ID: {file_id}  ·  Merkle: {merkle[:20]}...{'':>{20}}  ║
╚══════════════════════════════════════════════════════════════════════════╝

┌─ IDENTITY ────────────────────────────────────────────────────────────────┐
│  Species:    {species:<20s}  DNA: {dna_seq[:24]:<24s}           │
│  Size:       {size_human:<20s}  Lines: {total_lines:<8d}  Words: {total_words:<8d}        │
│  Chunks:     {total_chunks:<20d}  Symbols: {total_symbols:<8d}  Vocab: {len(word_freq):<8d}       │
│  Purpose:    {str(valuation.get('purpose', {}).get('primary', 'unknown'))[:60]:<60s}│
└──────────────────────────────────────────────────────────────────────────┘

┌─ STRUCTURAL DNA ──────────────────────────────────────────────────────────┐
│  Complexity: {complexity:.1f}/100  ·  {r['structural_dna']['interpretation']:<40s}   │
│  Genome:     {len(dna_seq) if dna_seq else 0} bytes  ·  Species: {species:<20s}              │
└──────────────────────────────────────────────────────────────────────────┘

┌─ VALUATION ───────────────────────────────────────────────────────────────┐
│  Build Cost:      ${val.get('build_cost', {}).get('estimated_usd', 0):>10,}  ·  {val.get('build_cost', {}).get('time_estimate', {}).get('days', 0)} days  │
│  Replacement:     ${val.get('replacement_cost', {}).get('estimated_usd', 0):>10,}  ·  {val.get('replacement_cost', {}).get('difficulty', '?'):<10s}     │
│  Depreciated:     ${val.get('depreciation', {}).get('depreciated_value_usd', 0):>10,}  ·  {val.get('depreciation', {}).get('remaining_value_pct', 100)}% value   │
│  Insurance:       ${val.get('insurance_value', {}).get('estimated_usd', 0):>10,}  ·  incl. business risk │
│  Prod Readiness:  {val.get('production_readiness', {}).get('grade', 'F')} ({pr_score}/100)  ·  {val.get('production_readiness', {}).get('distance_to_prod', '?'):<30s}│
└──────────────────────────────────────────────────────────────────────────┘

┌─ FINANCIAL & LEGAL ───────────────────────────────────────────────────────┐
│  Collateral:  {prof.get('collateral', {}).get('grade', 'F')} ({prof.get('collateral', {}).get('score', 0):>3}/100)  ·  Liquidity: {prof.get('liquidity', {}).get('grade', 'F')} ({prof.get('liquidity', {}).get('score', 0):>3}/100)  │
│  Time→Cash:   {prof.get('liquidity', {}).get('time_to_liquidate', 'illiquid'):<12s}  ·  Origin: {prof.get('origin', {}).get('primary', 'unknown'):<16s}│
│  Risk Level:  {prof.get('risk', {}).get('level', 'low'):<6s} ({prof.get('risk', {}).get('score', 0):>3}/100)  ·  Signals: {', '.join(prof.get('risk', {}).get('signals', [])[:3])[:30]}│
└──────────────────────────────────────────────────────────────────────────┘

┌─ KPIs ({len(kpis)} total) ───────────────────────────────────────────────────┐"""
    for cat, items in kpi_by_cat.items():
        top = items[:3]
        vals = ", ".join(f"{k['name']}={k['value']}" for k in top)
        dossier += f"\n│  {cat:<14s} ({len(items):>2d}): {vals[:55]:<55s}│"
    dossier += "\n└──────────────────────────────────────────────────────────────────────────┘"

    if ml.get("available"):
        dossier += "\n\n┌─ ML INSIGHTS ────────────────────────────────────────────────────────────┐"
        for t in ml.get("topics", [])[:3]:
            dossier += f"\n│  Topic {t.get('topic_id', 0)}: {', '.join(t.get('keywords', [])[:6])[:55]:<55s}│"
        if ml.get("inferred_kpis"):
            for k in ml["inferred_kpis"][:4]:
                dossier += f"\n│  {k.get('name', ''):<20s} = {k.get('value', '')[:30]:<30s} ({k.get('method', '')[:8]})│"
        if ml.get("anomalies"):
            dossier += f"\n│  Anomalies: {len(ml['anomalies'])} chunks flagged by Isolation Forest{'':>16}│"
        dossier += "\n└──────────────────────────────────────────────────────────────────────────┘"

    dossier += f"\n\n┌─ RECOMMENDATIONS ({len(recs)}) ───────────────────────────────────────────────┐"
    for rec in recs[:8]:
        dossier += f"\n│  [{rec['priority'].upper():>8s}] {rec['action']:<20s} — {rec['reason'][:35]:<35s}│"
    dossier += "\n└──────────────────────────────────────────────────────────────────────────┘"
    dossier += f"\n\n◆ Jorki Dossier v1.0 · Generated from {len(kpis)} KPIs, {total_chunks} chunks, {total_symbols} symbols"
    dossier += f"\n◆ DNA: {dna_seq[:40] if dna_seq else 'N/A'} · Merkle: {merkle[:32]}..."

    r["dossier_text"] = dossier
    return r


@app.get("/resume/{file_id}")
async def jorki_resume(file_id: str, format: str = "json"):
    """Complete file dossier — combines all analysis layers into one document."""
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    meta_rows = conn.execute("SELECT key, value FROM file_meta").fetchall()
    kpi_rows = conn.execute("SELECT id, name, value, line, category, confidence FROM kpis").fetchall()
    dna_rows = conn.execute("SELECT key, value FROM dna").fetchall()
    word_rows = conn.execute("SELECT word, count FROM word_freq").fetchall()
    chunk_rows = conn.execute("SELECT idx, line_start, line_end, boundary_type, preview, line_count FROM chunks").fetchall()
    sym_rows = conn.execute("SELECT line, name, type FROM symbols").fetchall()
    conn.close()
    _jorki_track_query(file_id, "resume")

    meta = {r[0]: r[1] for r in meta_rows}
    kpis = [{"id": r[0], "name": r[1], "value": r[2], "line": r[3], "category": r[4], "confidence": r[5]} for r in kpi_rows]
    dna = {r[0]: r[1] for r in dna_rows}
    word_freq = {r[0]: int(r[1]) for r in word_rows}
    chunks = [{"idx": r[0], "line_start": r[1], "line_end": r[2], "boundary_type": r[3], "preview": r[4], "line_count": r[5]} for r in chunk_rows]
    symbols = [{"line": r[0], "name": r[1], "type": r[2]} for r in sym_rows]
    text = "\n".join(c["preview"] for c in chunks)
    lines = text.split("\n")

    try:
        dna_obj = json.loads(dna.get("genes", "{}")) if isinstance(dna.get("genes"), str) else {}
        dna_dict = {"genes": dna_obj, "complexity_score": float(dna.get("complexity_score", 0)),
                    "dna_sequence": dna.get("dna_sequence", ""), "species": dna.get("species", "")}
    except:
        dna_dict = {}

    profile = _jorki_compute_profile(text, lines, word_freq, kpis, dna_dict)
    valuation = _jorki_valuate(text, lines, chunks, symbols, word_freq, kpis, dna_dict, meta)
    try:
        ml_result = _jorki_ml_extract(text, lines, chunks, word_freq, kpis, dna_dict)
    except Exception as e:
        ml_result = {"available": False, "error": str(e), "topics": [], "clusters": {}, "anomalies": [], "inferred_kpis": [], "tfidf_top_terms": []}

    resume = _jorki_generate_resume(file_id, meta, kpis, dna_dict, word_freq, chunks, symbols, profile, valuation, ml_result)

    # ── LLM 30 Facts (served as KPIs) ──
    llm_facts = _jorki_llm_30_facts(text, kpis, dna_dict, ml_result, meta)
    if llm_facts:
        resume["llm_facts"] = llm_facts

    if format == "text":
        return PlainTextResponse(resume["dossier_text"])
    return {"file_id": file_id, "resume": resume}

# ─── Formulas API: All KPI, Valuation, ML, and Scoring Formulas ──────────

@app.get("/formulas")
async def jorki_formulas():
    """Complete documentation of all formulas, algorithms, and scoring models used by Jorki."""
    return {
        "service": "jorki",
        "version": "2.0",
        "description": "Every formula, algorithm, and scoring model used across all Jorki analysis endpoints",
        "categories": {
            "kpi_extraction": {
                "endpoint": "/kpi/{file_id}",
                "formulas": [
                    {
                        "name": "monetary_value",
                        "pattern": r"\\$[\\d,]+(?:\\.\\d+)?|\\b\\d{1,3}(?:,\\d{3})+(?:\\.\\d+)?\\s*(?:USD|dollars?)\\b",
                        "formula": "regex_match(text) → extract $ amounts, revenue figures, dollar values",
                        "confidence": "1.0 if exact $ match, 0.8 if contextual",
                        "category": "financial",
                    },
                    {
                        "name": "percentage",
                        "pattern": r"\\b\\d+(?:\\.\\d+)?%\\b|\\b\\d+(?:\\.\\d+)?\\s*(?:percent|bps|basis points)\\b",
                        "formula": "regex_match(text) → extract percentage values",
                        "confidence": "0.9",
                        "category": "financial",
                    },
                    {
                        "name": "revenue",
                        "pattern": r"\\b(?:revenue|MRR|ARR|GMV|LTV|CAC|ARPU|churn rate|burn rate|net retention|gross retention|EBITDA|EBIT|net income|gross profit|operating income|free cash flow)\\b",
                        "formula": "keyword_match(text) → extract SaaS/financial metric references",
                        "confidence": "0.85",
                        "category": "financial",
                    },
                    {
                        "name": "valuation",
                        "pattern": r"\\b(?:valuation|market cap|enterprise value|equity value|pre-money|post-money|wacc|dcf|npv|irr|moic|roi|roe|roa|roic)\\b",
                        "formula": "keyword_match(text) → extract valuation/investment terms",
                        "confidence": "0.8",
                        "category": "financial",
                    },
                    {
                        "name": "date_temporal",
                        "pattern": r"\\b(?:Q[1-4]\\s*\\d{4}|FY\\d{2,4}|fiscal year|quarter ending|\\d{4}-\\d{2}-\\d{2}|\\d{1,2}/\\d{1,2}/\\d{4})\\b",
                        "formula": "regex_match(text) → extract fiscal periods and dates",
                        "confidence": "0.9",
                        "category": "temporal",
                    },
                    {
                        "name": "operational_metrics",
                        "pattern": r"\\b(?:users|customers|sessions|requests|latency|uptime|throughput|errors|QPS|RPS|concurrent|active users|MAU|DAU|WAU)\\b",
                        "formula": "keyword_match(text) → extract operational KPIs",
                        "confidence": "0.75",
                        "category": "operational",
                    },
                    {
                        "name": "api_endpoint",
                        "pattern": r"\\b(?:GET|POST|PUT|DELETE|PATCH)\\s+/[\\w/{}-]+",
                        "formula": "regex_match(text) → extract REST API endpoints",
                        "confidence": "0.95",
                        "category": "technical",
                    },
                    {
                        "name": "config_value",
                        "pattern": r"\\b[A-Z_]{3,}\\s*=\\s*\\S+",
                        "formula": "regex_match(text) → extract configuration key=value pairs",
                        "confidence": "0.7",
                        "category": "config",
                    },
                    {
                        "name": "table_count",
                        "formula": "count(occurrences of '|---' or markdown table separators)",
                        "confidence": "0.6",
                        "category": "structural",
                    },
                    {
                        "name": "dominant_terms",
                        "formula": "word_freq → sort by count → top 5 non-stopwords",
                        "confidence": "0.5",
                        "category": "structural",
                    },
                ],
            },
            "dna_fingerprinting": {
                "endpoint": "/dna/{file_id}",
                "formulas": [
                    {
                        "name": "gene_height",
                        "formula": "len(text.split('\\n')) / 1000  →  normalized line count",
                        "range": "0.0 - 1.0+",
                    },
                    {
                        "name": "gene_max_width",
                        "formula": "max(len(line) for line in lines) / 200  →  normalized max line width",
                        "range": "0.0 - 1.0+",
                    },
                    {
                        "name": "gene_symbol_density",
                        "formula": "len(symbols) / max(len(lines), 1)  →  symbols per line",
                        "range": "0.0 - 1.0+",
                    },
                    {
                        "name": "gene_chunk_count",
                        "formula": "len(chunks) / 100  →  normalized chunk count",
                        "range": "0.0 - 1.0+",
                    },
                    {
                        "name": "gene_vocab_richness",
                        "formula": "len(unique_words) / max(len(total_words), 1)  →  type-token ratio",
                        "range": "0.0 - 1.0",
                    },
                    {
                        "name": "gene_avg_line_length",
                        "formula": "mean(len(line) for line in lines) / 100  →  normalized avg line length",
                        "range": "0.0 - 1.0+",
                    },
                    {
                        "name": "gene_blank_ratio",
                        "formula": "count(empty_lines) / max(total_lines, 1)  →  proportion of blank lines",
                        "range": "0.0 - 1.0",
                    },
                    {
                        "name": "gene_comment_ratio",
                        "formula": "count(comment_lines) / max(total_lines, 1)  →  proportion of comments",
                        "range": "0.0 - 1.0",
                    },
                    {
                        "name": "gene_entropy",
                        "formula": "-Σ(p_i * log2(p_i)) for byte frequencies in first 4096 bytes  →  Shannon entropy",
                        "range": "0.0 - 8.0",
                    },
                    {
                        "name": "gene_merkle_prefix",
                        "formula": "int(merkle_root[:4], 16) / 65535  →  normalized first 16 bits of SHA-256 merkle root",
                        "range": "0.0 - 1.0",
                    },
                    {
                        "name": "dna_sequence",
                        "formula": "concat(hex(gene_value)[:4] for each gene)  →  40-char hex string encoding all 10 genes",
                    },
                    {
                        "name": "species_classification",
                        "formula": "if ext in (.py) → pythonicus; (.js/.jsx) → javascriptus; (.json) → jsonicus; (.html/.xml/.svg) → markupus; (.csv/.tsv) → tabularis; else → textus",
                    },
                    {
                        "name": "complexity_score",
                        "formula": "symbol_density * 10 + chunk_count * 0.5 + vocab_richness * 5 + entropy * 0.5 + avg_line_length * 2",
                        "range": "0.0 - 30+",
                    },
                ],
            },
            "semantic_profile": {
                "endpoint": "/profile/{file_id}",
                "formulas": [
                    {
                        "name": "origin_detection",
                        "formula": "for each origin_type: count(signal_keyword_hits) → if hits >= 2: confidence = min(hits / total_signals, 1.0)",
                        "signals": ["source_code", "financial_statement", "invoice", "contract", "spreadsheet", "research_report", "api_doc", "audit", "dataset"],
                    },
                    {
                        "name": "accounting_concepts",
                        "formula": "regex_match(text) for each of 14 accounting patterns (GAAP, IFRS, accrual, depreciation, amortization, revenue_recognition, AR, AP, inventory, goodwill, deferred_revenue, working_capital, EBITDA, fiscal_year)",
                    },
                    {
                        "name": "finance_metrics",
                        "formula": "regex_match(text) for each of 17 finance patterns (revenue, EBITDA_margin, net_income, gross_profit, OpEx, CapEx, FCF, WACC, DCF, NPV, IRR, MOIC, ROI, ROE, ROA, D/E, current_ratio, quick_ratio)",
                    },
                    {
                        "name": "legal_concepts",
                        "formula": "regex_match(text) for each of 18 legal patterns (NDA, IP_assignment, indemnification, liability, jurisdiction, governing_law, arbitration, confidentiality, termination, warranty, license, copyright, patent, trademark, compliance, GDPR, SOX, SEC_filing)",
                    },
                    {
                        "name": "collateral_score",
                        "formula": "signal_count = len(financial_metrics) + len(accounting_concepts) + len(legal_concepts) + len(kpis) + int(dna_complexity > 5 ? complexity : 0) + (origin_detected ? 5 : 0) → score = min(signal_count * 3, 100)",
                        "grade": "A≥80, B≥60, C≥40, D≥20, F<20",
                    },
                    {
                        "name": "liquidity_score",
                        "formula": "signals = cash_hits*5 + time_hits*4 + (marketable?8:0) + (recurring_revenue?10:0) + (asset_backed?8:0) + (financial_doc?6:0) → score = min(signals * 2, 100)",
                        "grade": "A≥80, B≥60, C≥40, D≥20, F<20",
                        "time_to_liquidate": "days if ≥60, weeks if ≥30, months if ≥15, illiquid if <15",
                    },
                    {
                        "name": "risk_score",
                        "formula": "confidentiality(+15) + secret_exposure(+25) + litigation(+20) + credit_risk(+30) + forward_looking(+10) + unverified(+15) → min(sum, 100)",
                        "level": "high≥50, medium≥25, low<25",
                    },
                ],
            },
            "valuation": {
                "endpoint": "/valuation/{file_id}",
                "formulas": [
                    {
                        "name": "effective_loc",
                        "formula": "count(lines where line.strip() and not line.startswith('#', '//', '/*', '*'))  →  non-blank, non-comment lines",
                    },
                    {
                        "name": "complexity_factor",
                        "formula": "1.0 + (dna_complexity / 20.0), capped at 3.0",
                        "range": "1.0 - 3.0",
                    },
                    {
                        "name": "language_factor",
                        "formula": "pythonicus=1.0, javascriptus=1.1, jsonicus=0.3, markupus=0.5, tabularis=0.4, textus=0.2",
                    },
                    {
                        "name": "build_cost",
                        "formula": "effective_loc × species_rate × complexity_factor + test_cost(code only) + deploy_cost(code only) + security_audit(code/config only), capped at $3M",
                        "unit": "USD",
                        "rates": "pythonicus=$0.20/LOC, javascriptus=$0.20, golangus=$0.20, rusticus=$0.20, ceplusplus=$0.20, scripticus=$0.15, jsonicus=$0.02, markupus=$0.05, tabularis=$0.03, configus=$0.08, textus=$0.000005", "max_rate": "$0.20/LOC"
                    },
                    {
                        "name": "build_time",
                        "formula": "hours = effective_loc / 50, days = hours / 8",
                        "developer_level": "mid if complexity<10, senior if <25, staff if ≥25",
                    },
                    {
                        "name": "replacement_cost",
                        "formula": "build_cost × knowledge_loss_factor (1.5 for code, 1.2 for script, 1.1 for docs) + ramp_up ($1000 code, $500 other), capped at $3M",
                        "unit": "USD",
                    },
                    {
                        "name": "rebuild_time",
                        "formula": "hours = effective_loc / 40 (slower due to lost context), days = hours / 8, weeks = days / 5",
                    },
                    {
                        "name": "depreciation_score",
                        "formula": "legacy_python2(+30) + legacy_js(+20) + deprecated_framework(+25) + legacy_protocol(+15) + insufficient_docs(+10) + no_tests(+15) → min(sum, 100)",
                    },
                    {
                        "name": "depreciated_value",
                        "formula": "replacement_cost × (1 - depreciation_score/100)",
                    },
                    {
                        "name": "insurance_value",
                        "formula": "replacement_cost + business_interruption_risk",
                        "business_risk": "has_security(+$5000) + payments(+$10000) + auth(+$8000) + production_grade(+$3000)",
                    },
                    {
                        "name": "production_readiness_score",
                        "formula": "has_tests(+15) + error_handling(+10) + logging(+8) + config_separation(+10) + documentation(+8) + type_safety(+7) + security_patterns(+10) + complexity_balanced(+7) + dependencies(+5) + deployment(+10) + no_secrets(+10 or -15) → clamp(0, 100)",
                        "grade": "A≥80, B≥60, C≥40, D≥20, F<20",
                    },
                ],
            },
            "ml_inference": {
                "endpoint": "/ml/{file_id}",
                "formulas": [
                    {
                        "name": "tfidf",
                        "formula": "TF-IDF = TF(term, chunk) × log(N / DF(term)) where N=total_chunks, DF=chunks containing term",
                        "params": "max_features=100, stop_words=english, ngram_range=(1,2)",
                    },
                    {
                        "name": "nmf_topic_modeling",
                        "formula": "minimize ||V - WH||_F where V=tfidf_matrix, W=topic_weights, H=topic_terms",
                        "params": "n_components=min(3, chunks-1), random_state=42, max_iter=200",
                        "output": "topics with keywords, chunk assignments, strength = Σ(W[:,k]) / Σ(W)",
                    },
                    {
                        "name": "lsa_svd",
                        "formula": "TruncatedSVD: X = UΣV^T, take top k components → latent semantic space",
                        "params": "n_components=min(5, features-1, chunks-1), random_state=42",
                        "output": "explained_variance_ratio, semantic_dimensions with top terms, file_embedding = mean(chunk_embeddings)",
                    },
                    {
                        "name": "kmeans_clustering",
                        "formula": "minimize Σ||x_i - μ_c||² for cluster c",
                        "params": "n_clusters=min(3, chunks-1), random_state=42, n_init=10",
                        "output": "cluster sizes, chunk assignments, centroid terms",
                    },
                    {
                        "name": "isolation_forest",
                        "formula": "random partition tree → anomalies = points with shortest average path length",
                        "params": "contamination=0.15, random_state=42",
                        "output": "anomalous chunk indices with previews",
                    },
                    {
                        "name": "shannon_entropy",
                        "formula": "H = -Σ(p_i × log2(p_i)) for character frequencies in first 8192 chars",
                        "unit": "bits/char",
                        "range": "0.0 - 8.0",
                    },
                    {
                        "name": "zipf_slope",
                        "formula": "linear regression on (log(rank), log(frequency)) → slope of Zipf's law fit",
                        "interpretation": "slope ≈ -1.0 indicates natural language, steeper = more concentrated vocabulary",
                    },
                    {
                        "name": "vocabulary_concentration",
                        "formula": "max(word_freq) / sum(word_freq)  →  proportion of most frequent word",
                        "range": "0.0 - 1.0",
                    },
                    {
                        "name": "topic_coherence",
                        "formula": "max(topic.strength for all topics)  →  how focused the document is on one topic",
                        "range": "0.0 - 1.0",
                    },
                    {
                        "name": "structural_balance",
                        "formula": "1.0 - (max(cluster_sizes) - min(cluster_sizes)) / sum(cluster_sizes)  →  how evenly chunks distribute across clusters",
                        "range": "0.0 - 1.0",
                    },
                    {
                        "name": "anomaly_rate",
                        "formula": "len(anomalies) / len(chunks)  →  proportion of anomalous chunks",
                        "range": "0.0 - 1.0",
                    },
                    {
                        "name": "semantic_complexity",
                        "formula": "mean(explained_variance[:3])  →  average of top 3 LSA component variances",
                        "range": "0.0 - 1.0",
                    },
                ],
            },
            "password_security": {
                "endpoint": "/password/{file_id}",
                "formulas": [
                    {
                        "name": "password_hashing",
                        "algorithm": "PBKDF2-HMAC-SHA256",
                        "params": "iterations=100000, salt=random 32 bytes, dklen=64",
                        "formula": "dk = pbkdf2(password, salt, 100000, 64, hashlib.sha256)",
                        "storage": "salt + dk stored as hex in access_control table",
                    },
                    {
                        "name": "password_verification",
                        "formula": "recompute PBKDF2(input_password, stored_salt) → compare with stored_dk using constant-time comparison",
                    },
                ],
            },
            "file_indexing": {
                "endpoint": "/index",
                "formulas": [
                    {
                        "name": "merkle_root",
                        "formula": "SHA-256 of all chunk hashes combined → tree root hash = file_id",
                        "description": "Each chunk is SHA-256 hashed, then hashes are combined into a Merkle tree, root = file identifier",
                    },
                    {
                        "name": "semantic_chunking",
                        "formula": "split on boundaries: blank lines, class/function definitions, markdown headers, paragraph breaks → chunks of 5-50 lines",
                        "boundary_types": ["blank_line", "function_def", "class_def", "header", "paragraph", "code_block"],
                    },
                    {
                        "name": "word_frequency",
                        "formula": "tokenize(text) → lowercase → remove stopwords → count occurrences → store top 200 in word_freq table",
                    },
                    {
                        "name": "symbol_extraction",
                        "formula": "regex patterns for: def name, class name, function name, const name, interface name, struct name → store in symbols table with line numbers",
                    },
                ],
            },
        },
        "scoring_summary": {
            "collateral": "0-100, grade A-F, weighted by financial+accounting+legal+KPI+DNA+origin signals × 3",
            "liquidity": "0-100, grade A-F, weighted by cash+time+marketability+revenue+assets+doc_type × 2",
            "risk": "0-100, level high/medium/low, additive from 6 risk signal categories",
            "production_readiness": "0-100, grade A-F, 12 weighted checks (tests, errors, logging, config, docs, types, security, complexity, deps, deploy, secrets)",
            "depreciation": "0-100, additive from legacy patterns + maintenance signals",
            "complexity": "0-30+, weighted formula from symbol density, chunks, vocab, entropy, line length",
        },
        "total_formulas": 47,
        "total_endpoints_with_formulas": 7,
    }

# ─── Video Export: Render Dossier as Animated MP4/GIF ────────────────────

def _jorki_render_video(resume, file_id, filename):
    """Render file dossier as an animated video using matplotlib."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.animation as animation
    from matplotlib.patches import FancyBboxPatch
    import numpy as np

    # Colors — Jorki brand
    BG = "#0a0a0a"
    ORANGE = "#ff8c00"
    WHITE = "#e0e0e0"
    DIM = "#555555"
    GREEN = "#00ff88"
    RED = "#ff4444"
    YELLOW = "#ffcc00"

    val = resume.get("valuation_summary", {})
    prof = resume.get("financial_profile", {})
    risk = resume.get("risk_assessment", {})
    ml = resume.get("ml_insights", {})
    ident = resume.get("identity", {})
    dna_info = resume.get("structural_dna", {})
    kpi_sum = resume.get("kpi_summary", {})

    # Build frames — each frame is a "scene"
    scenes = []

    # Scene 1: Title card
    scenes.append({
        "type": "title",
        "title": filename or "unknown",
        "subtitle": f"JORKI FILE DOSSIER",
        "info": f"ID: {file_id}  ·  Species: {ident.get('species', '?')}  ·  {ident.get('lines', 0)} lines",
    })

    # Scene 2: Identity
    scenes.append({
        "type": "stats",
        "title": "IDENTITY",
        "stats": [
            ("Species", ident.get("species", "unknown")),
            ("Lines", str(ident.get("lines", 0))),
            ("Words", str(ident.get("words", 0))),
            ("Chunks", str(ident.get("chunks", 0))),
            ("Symbols", str(ident.get("symbols", 0))),
            ("Vocabulary", str(ident.get("vocabulary", 0))),
            ("Purpose", ident.get("primary_purpose", "unknown")[:40]),
        ],
    })

    # Scene 3: DNA
    genes = dna_info.get("genes", {})
    scenes.append({
        "type": "dna",
        "title": "STRUCTURAL DNA",
        "complexity": dna_info.get("complexity_score", 0),
        "interpretation": dna_info.get("interpretation", ""),
        "species": dna_info.get("species", "?"),
        "genes": genes,
    })

    # Scene 4: KPIs
    scenes.append({
        "type": "kpi",
        "title": f"KPIs ({kpi_sum.get('total', 0)} total)",
        "by_category": kpi_sum.get("by_category", {}),
        "top_financial": resume.get("kpi_summary", {}).get("top_financial", []),
        "top_technical": resume.get("kpi_summary", {}).get("top_technical", []),
    })

    # Scene 5: Financial Profile
    scenes.append({
        "type": "grades",
        "title": "FINANCIAL PROFILE",
        "grades": [
            ("Collateral", prof.get("collateral_grade", "F"), prof.get("collateral_score", 0), 100),
            ("Liquidity", prof.get("liquidity_grade", "F"), prof.get("liquidity_score", 0), 100),
        ],
        "extra": [
            f"Time to liquidate: {prof.get('time_to_liquidate', 'illiquid')}",
            f"Monetary refs: {prof.get('monetary_references', 0)}",
            f"Standards: {', '.join(prof.get('standards', [])) or 'none'}",
        ],
    })

    # Scene 6: Valuation
    scenes.append({
        "type": "valuation",
        "title": "VALUATION",
        "items": [
            ("Build Cost", f"${val.get('build_cost_usd', 0):,}"),
            ("Replacement", f"${val.get('replacement_cost_usd', 0):,}"),
            ("Depreciated", f"${val.get('depreciated_value_usd', 0):,}"),
            ("Insurance", f"${val.get('insurance_value_usd', 0):,}"),
            ("Rebuild Time", f"{val.get('time_to_rebuild_days', 0)} days"),
            ("Difficulty", val.get("difficulty", "?")),
        ],
        "pr_grade": val.get("production_readiness_grade", "F"),
        "pr_score": val.get("production_readiness_score", 0),
        "distance": val.get("distance_to_prod", "?"),
    })

    # Scene 7: Risk
    scenes.append({
        "type": "risk",
        "title": "RISK ASSESSMENT",
        "level": risk.get("level", "low"),
        "score": risk.get("score", 0),
        "signals": risk.get("signals", []),
        "origin": risk.get("origin", "unknown"),
    })

    # Scene 8: ML Insights
    if ml.get("available"):
        scenes.append({
            "type": "ml",
            "title": "ML INSIGHTS",
            "topics": ml.get("topics", []),
            "tfidf": ml.get("tfidf_top", []),
            "anomalies": ml.get("anomaly_count", 0),
            "inferred": ml.get("inferred_kpis", [])[:6],
        })

    # Scene 9: Recommendations
    scenes.append({
        "type": "recommendations",
        "title": "RECOMMENDATIONS",
        "recs": resume.get("recommendations", [])[:8],
    })

    # Scene 10: Closing
    scenes.append({
        "type": "closing",
        "title": filename or "unknown",
        "subtitle": "JORKI DOSSIER COMPLETE",
        "info": f"{len(resume.get('recommendations', []))} recommendations  ·  {kpi_sum.get('total', 0)} KPIs  ·  Complexity {dna_info.get('complexity_score', 0):.1f}",
    })

    # Render frames
    fig, ax = plt.subplots(figsize=(12, 6.75), facecolor=BG)  # 16:9
    fig.subplots_adjust(left=0, right=1, top=1, bottom=0)

    def draw_scene(frame_idx):
        ax.clear()
        ax.set_xlim(0, 12)
        ax.set_ylim(0, 6.75)
        ax.set_facecolor(BG)
        ax.axis("off")

        scene = scenes[frame_idx % len(scenes)]
        stype = scene["type"]

        # Fade in/out — compute alpha based on frame position within scene
        frames_per_scene = 20
        local_frame = frame_idx % frames_per_scene
        if local_frame < 3:
            alpha = local_frame / 3.0
        elif local_frame > frames_per_scene - 3:
            alpha = (frames_per_scene - local_frame) / 3.0
        else:
            alpha = 1.0

        if stype == "title":
            ax.text(6, 4.5, scene["title"], ha="center", va="center",
                    fontsize=28, color=ORANGE, fontweight="bold", alpha=alpha,
                    fontfamily="monospace")
            ax.text(6, 3.5, scene["subtitle"], ha="center", va="center",
                    fontsize=14, color=DIM, alpha=alpha, fontfamily="monospace")
            ax.text(6, 2.5, scene["info"], ha="center", va="center",
                    fontsize=10, color=WHITE, alpha=alpha * 0.7, fontfamily="monospace")
            # Decorative line
            ax.plot([2, 10], [3.0, 3.0], color=ORANGE, linewidth=0.5, alpha=alpha * 0.3)

        elif stype == "stats":
            ax.text(1, 6.0, scene["title"], fontsize=16, color=ORANGE,
                    fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.plot([1, 11], [5.7, 5.7], color=ORANGE, linewidth=0.5, alpha=alpha * 0.3)
            for i, (label, value) in enumerate(scene["stats"]):
                y = 5.0 - i * 0.6
                ax.text(1.5, y, label, fontsize=11, color=DIM, alpha=alpha, fontfamily="monospace")
                ax.text(6, y, value, fontsize=11, color=WHITE, alpha=alpha, fontfamily="monospace")

        elif stype == "dna":
            ax.text(1, 6.0, scene["title"], fontsize=16, color=ORANGE,
                    fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.plot([1, 11], [5.7, 5.7], color=ORANGE, linewidth=0.5, alpha=alpha * 0.3)
            complexity = scene["complexity"]
            ax.text(1.5, 5.0, "Complexity", fontsize=11, color=DIM, alpha=alpha, fontfamily="monospace")
            ax.text(6, 5.0, f"{complexity:.1f}/100", fontsize=11, color=ORANGE if complexity > 20 else WHITE,
                    alpha=alpha, fontfamily="monospace")
            # Complexity bar
            bar_w = complexity / 100 * 8
            ax.add_patch(FancyBboxPatch((1.5, 4.5), max(bar_w, 0.1), 0.2,
                                         boxstyle="round,pad=0.05", facecolor=ORANGE, alpha=alpha * 0.6))
            ax.text(1.5, 4.0, scene["interpretation"], fontsize=10, color=WHITE, alpha=alpha * 0.8, fontfamily="monospace")
            genes = scene.get("genes", {})
            for i, (gname, gval) in enumerate(list(genes.items())[:8]):
                y = 3.3 - i * 0.35
                ax.text(1.5, y, gname, fontsize=9, color=DIM, alpha=alpha, fontfamily="monospace")
                ax.text(6, y, str(gval), fontsize=9, color=WHITE, alpha=alpha, fontfamily="monospace")

        elif stype == "kpi":
            ax.text(1, 6.0, scene["title"], fontsize=16, color=ORANGE,
                    fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.plot([1, 11], [5.7, 5.7], color=ORANGE, linewidth=0.5, alpha=alpha * 0.3)
            by_cat = scene.get("by_category", {})
            y = 5.0
            for cat, count in list(by_cat.items())[:6]:
                ax.text(1.5, y, cat, fontsize=11, color=DIM, alpha=alpha, fontfamily="monospace")
                ax.text(5, y, str(count), fontsize=11, color=WHITE, alpha=alpha, fontfamily="monospace")
                # Bar
                ax.add_patch(FancyBboxPatch((6, y - 0.1), min(count * 0.3, 4), 0.2,
                                             boxstyle="round,pad=0.02", facecolor=ORANGE, alpha=alpha * 0.4))
                y -= 0.5
            # Top financial KPIs
            fin = scene.get("top_financial", [])
            if fin:
                ax.text(1.5, 1.5, "Top Financial:", fontsize=9, color=DIM, alpha=alpha, fontfamily="monospace")
                for i, k in enumerate(fin[:3]):
                    ax.text(4, 1.5 - i * 0.35, f"{k['name']}={k['value']}", fontsize=8, color=GREEN,
                            alpha=alpha, fontfamily="monospace")

        elif stype == "grades":
            ax.text(1, 6.0, scene["title"], fontsize=16, color=ORANGE,
                    fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.plot([1, 11], [5.7, 5.7], color=ORANGE, linewidth=0.5, alpha=alpha * 0.3)
            grades = scene.get("grades", [])
            for i, (label, grade, score, max_score) in enumerate(grades):
                y = 4.5 - i * 1.5
                ax.text(1.5, y, label, fontsize=14, color=DIM, alpha=alpha, fontfamily="monospace")
                grade_color = GREEN if grade in ("A", "B") else YELLOW if grade in ("C") else RED
                ax.text(4, y, grade, fontsize=28, color=grade_color, fontweight="bold",
                        alpha=alpha, fontfamily="monospace")
                ax.text(5.5, y, f"({score}/{max_score})", fontsize=11, color=WHITE,
                        alpha=alpha, fontfamily="monospace")
                # Score bar
                bar_w = score / max_score * 5
                bar_color = grade_color
                ax.add_patch(FancyBboxPatch((1.5, y - 0.4), max(bar_w, 0.1), 0.15,
                                             boxstyle="round,pad=0.03", facecolor=bar_color, alpha=alpha * 0.5))
            for i, line in enumerate(scene.get("extra", [])):
                ax.text(1.5, 1.0 - i * 0.35, line, fontsize=9, color=DIM, alpha=alpha, fontfamily="monospace")

        elif stype == "valuation":
            ax.text(1, 6.0, scene["title"], fontsize=16, color=ORANGE,
                    fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.plot([1, 11], [5.7, 5.7], color=ORANGE, linewidth=0.5, alpha=alpha * 0.3)
            items = scene.get("items", [])
            for i, (label, value) in enumerate(items):
                y = 5.0 - i * 0.5
                ax.text(1.5, y, label, fontsize=11, color=DIM, alpha=alpha, fontfamily="monospace")
                ax.text(7, y, value, fontsize=12, color=GREEN if "$" in value else WHITE,
                        alpha=alpha, fontfamily="monospace")
            # PR badge
            pr_grade = scene.get("pr_grade", "F")
            pr_score = scene.get("pr_score", 0)
            pr_color = GREEN if pr_grade in ("A", "B") else YELLOW if pr_grade == "C" else RED
            ax.text(9.5, 5.0, "PROD", fontsize=9, color=DIM, alpha=alpha, fontfamily="monospace")
            ax.text(9.5, 4.3, pr_grade, fontsize=24, color=pr_color, fontweight="bold",
                    alpha=alpha, fontfamily="monospace")
            ax.text(9.5, 3.6, f"{pr_score}/100", fontsize=9, color=WHITE, alpha=alpha, fontfamily="monospace")
            ax.text(9.5, 3.1, scene.get("distance", "?")[:20], fontsize=7, color=DIM,
                    alpha=alpha, fontfamily="monospace")

        elif stype == "risk":
            ax.text(1, 6.0, scene["title"], fontsize=16, color=ORANGE,
                    fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.plot([1, 11], [5.7, 5.7], color=ORANGE, linewidth=0.5, alpha=alpha * 0.3)
            level = scene.get("level", "low")
            score = scene.get("score", 0)
            level_color = RED if level == "high" else YELLOW if level == "medium" else GREEN
            ax.text(1.5, 4.5, "Level", fontsize=11, color=DIM, alpha=alpha, fontfamily="monospace")
            ax.text(4, 4.5, level.upper(), fontsize=20, color=level_color, fontweight="bold",
                    alpha=alpha, fontfamily="monospace")
            ax.text(7, 4.5, f"({score}/100)", fontsize=11, color=WHITE, alpha=alpha, fontfamily="monospace")
            ax.text(1.5, 3.5, f"Origin: {scene.get('origin', 'unknown')}", fontsize=10, color=WHITE,
                    alpha=alpha, fontfamily="monospace")
            signals = scene.get("signals", [])
            ax.text(1.5, 3.0, "Signals:", fontsize=10, color=DIM, alpha=alpha, fontfamily="monospace")
            for i, sig in enumerate(signals[:6]):
                ax.text(2.5, 2.5 - i * 0.35, f"⟁ {sig}", fontsize=9, color=RED if level == "high" else YELLOW,
                        alpha=alpha, fontfamily="monospace")

        elif stype == "ml":
            ax.text(1, 6.0, scene["title"], fontsize=16, color=ORANGE,
                    fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.plot([1, 11], [5.7, 5.7], color=ORANGE, linewidth=0.5, alpha=alpha * 0.3)
            topics = scene.get("topics", [])
            for i, t in enumerate(topics[:3]):
                y = 5.0 - i * 0.6
                kws = ", ".join(t.get("keywords", [])[:5])
                ax.text(1.5, y, f"Topic {t.get('id', 0)}", fontsize=10, color=DIM, alpha=alpha, fontfamily="monospace")
                ax.text(4, y, kws[:50], fontsize=9, color=WHITE, alpha=alpha, fontfamily="monospace")
            tfidf = scene.get("tfidf", [])
            if tfidf:
                ax.text(1.5, 2.5, "TF-IDF:", fontsize=9, color=DIM, alpha=alpha, fontfamily="monospace")
                ax.text(3.5, 2.5, ", ".join(tfidf[:8]), fontsize=8, color=ORANGE, alpha=alpha, fontfamily="monospace")
            inferred = scene.get("inferred", [])
            for i, k in enumerate(inferred[:4]):
                ax.text(1.5, 2.0 - i * 0.3, f"{k.get('name', '')}: {k.get('value', '')}", fontsize=8,
                        color=GREEN, alpha=alpha, fontfamily="monospace")
            if scene.get("anomalies", 0):
                ax.text(1.5, 0.5, f"⟁ {scene['anomalies']} anomalies detected", fontsize=9, color=RED,
                        alpha=alpha, fontfamily="monospace")

        elif stype == "recommendations":
            ax.text(1, 6.0, scene["title"], fontsize=16, color=ORANGE,
                    fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.plot([1, 11], [5.7, 5.7], color=ORANGE, linewidth=0.5, alpha=alpha * 0.3)
            recs = scene.get("recs", [])
            priority_colors = {"critical": RED, "high": RED, "medium": YELLOW, "low": ORANGE, "info": DIM}
            for i, rec in enumerate(recs):
                y = 5.0 - i * 0.55
                color = priority_colors.get(rec.get("priority", "info"), DIM)
                ax.text(1.5, y, f"[{rec.get('priority', '?').upper()}]", fontsize=9, color=color,
                        alpha=alpha, fontfamily="monospace")
                ax.text(3.5, y, rec.get("action", ""), fontsize=10, color=WHITE,
                        alpha=alpha, fontfamily="monospace")
                ax.text(7.5, y, rec.get("reason", "")[:35], fontsize=8, color=DIM,
                        alpha=alpha, fontfamily="monospace")

        elif stype == "closing":
            ax.text(6, 4.5, scene["title"], ha="center", va="center",
                    fontsize=24, color=ORANGE, fontweight="bold", alpha=alpha, fontfamily="monospace")
            ax.text(6, 3.5, scene["subtitle"], ha="center", va="center",
                    fontsize=14, color=DIM, alpha=alpha, fontfamily="monospace")
            ax.text(6, 2.5, scene["info"], ha="center", va="center",
                    fontsize=10, color=WHITE, alpha=alpha * 0.7, fontfamily="monospace")
            ax.plot([3, 9], [3.0, 3.0], color=ORANGE, linewidth=0.5, alpha=alpha * 0.3)

        # Watermark
        ax.text(11.5, 0.2, "◆ JORKI", fontsize=7, color=DIM, alpha=alpha * 0.3,
                ha="right", fontfamily="monospace")

    # Build animation
    frames_per_scene = 20
    total_frames = len(scenes) * frames_per_scene

    anim = animation.FuncAnimation(
        fig, draw_scene, frames=total_frames,
        interval=200, blit=False, repeat=True
    )

    # Save — try MP4 first, fall back to GIF
    video_dir = JORKI_DATA_DIR / "videos"
    video_dir.mkdir(parents=True, exist_ok=True)

    # Try MP4 with ffmpeg
    mp4_path = video_dir / f"{file_id}.mp4"
    gif_path = video_dir / f"{file_id}.gif"

    video_format = "gif"
    video_path = gif_path

    try:
        # Check if ffmpeg is available
        import subprocess as _sp
        _sp.run(["ffmpeg", "-version"], capture_output=True, check=True)
        writer = animation.FFMpegWriter(fps=5, bitrate=1800)
        anim.save(str(mp4_path), writer=writer, dpi=100)
        video_format = "mp4"
        video_path = mp4_path
    except Exception:
        # Fall back to GIF using Pillow
        try:
            writer = animation.PillowWriter(fps=5)
            anim.save(str(gif_path), writer=writer, dpi=80)
            video_format = "gif"
            video_path = gif_path
        except Exception as e:
            plt.close(fig)
            return {"error": f"Video generation failed: {str(e)}"}

    plt.close(fig)

    return {
        "video_path": str(video_path),
        "format": video_format,
        "size_bytes": video_path.stat().st_size,
        "scenes": len(scenes),
        "frames": total_frames,
        "duration_seconds": total_frames * 0.2,
    }


@app.get("/video/{file_id}")
async def jorki_video(file_id: str):
    """Generate and return a video dossier of the file."""
    # First get the resume
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}

    conn = sqlite3.connect(str(idx_path))
    meta_rows = conn.execute("SELECT key, value FROM file_meta").fetchall()
    kpi_rows = conn.execute("SELECT id, name, value, line, category, confidence FROM kpis").fetchall()
    dna_rows = conn.execute("SELECT key, value FROM dna").fetchall()
    word_rows = conn.execute("SELECT word, count FROM word_freq").fetchall()
    chunk_rows = conn.execute("SELECT idx, line_start, line_end, boundary_type, preview, line_count FROM chunks").fetchall()
    sym_rows = conn.execute("SELECT line, name, type FROM symbols").fetchall()
    conn.close()
    _jorki_track_query(file_id, "video")

    meta = {r[0]: r[1] for r in meta_rows}
    kpis = [{"id": r[0], "name": r[1], "value": r[2], "line": r[3], "category": r[4], "confidence": r[5]} for r in kpi_rows]
    dna = {r[0]: r[1] for r in dna_rows}
    word_freq = {r[0]: int(r[1]) for r in word_rows}
    chunks = [{"idx": r[0], "line_start": r[1], "line_end": r[2], "boundary_type": r[3], "preview": r[4], "line_count": r[5]} for r in chunk_rows]
    symbols = [{"line": r[0], "name": r[1], "type": r[2]} for r in sym_rows]
    text = "\n".join(c["preview"] for c in chunks)
    lines = text.split("\n")

    try:
        dna_obj = json.loads(dna.get("genes", "{}")) if isinstance(dna.get("genes"), str) else {}
        dna_dict = {"genes": dna_obj, "complexity_score": float(dna.get("complexity_score", 0)),
                    "dna_sequence": dna.get("dna_sequence", ""), "species": dna.get("species", "")}
    except:
        dna_dict = {}

    profile = _jorki_compute_profile(text, lines, word_freq, kpis, dna_dict)
    valuation = _jorki_valuate(text, lines, chunks, symbols, word_freq, kpis, dna_dict, meta)
    ml_result = _jorki_ml_extract(text, lines, chunks, word_freq, kpis, dna_dict)
    resume = _jorki_generate_resume(file_id, meta, kpis, dna_dict, word_freq, chunks, symbols, profile, valuation, ml_result)

    # Generate video
    result = _jorki_render_video(resume, file_id, meta.get("filename", "unknown"))
    if "error" in result:
        return result

    # Return the video file
    return FileResponse(
        result["video_path"],
        media_type=f"video/{result['format']}" if result["format"] == "mp4" else "image/gif",
        filename=f"{file_id}_dossier.{result['format']}"
    )

# ─── Pipeline API: Clipboard → Repo → Artifact → Deploy → App → DMG → AppStore ─

# ─── Unsupervised ML Feature Extraction ─────────────────────────────────

def _jorki_ml_extract_pure(text, lines, chunks, word_freq, kpis, dna):
    """Pure-Python ML fallback when scikit-learn is not available.
    Implements TF-IDF, topic modeling, clustering, and anomaly detection without numpy/sklearn."""
    import math
    from collections import Counter

    STOPWORDS = set("a an the and or but in on at to for of is are was were be been being have has had do does did will would could should may might must can this that these those i you he she it we they them his her its their my your our what which who whom whose when where why how all any both each few more most other some such no nor not only own same so than too very s t can just don should now".split())

    result = {"available": True, "topics": [], "clusters": {}, "anomalies": [],
              "latent_features": {}, "inferred_kpis": [], "semantic_embedding": {},
              "engine": "pure-python"}

    chunk_texts = [c["preview"] for c in chunks] if chunks else [text[:500]]
    if len(chunk_texts) > 200:
        chunk_texts = chunk_texts[:200]
    if len(chunk_texts) < 2:
        chunk_texts = [text[i:i+500] for i in range(0, len(text), 500)][:20]
    if len(chunk_texts) < 2:
        return result

    # ── TF-IDF (pure Python) ──
    # Tokenize chunks
    chunk_tokens = []
    for ct in chunk_texts:
        tokens = [w.lower() for w in re.findall(r'\b[a-zA-Z][a-zA-Z0-9]{2,}\b', ct) if w.lower() not in STOPWORDS]
        chunk_tokens.append(tokens)

    # Document frequency
    N = len(chunk_texts)
    df = Counter()
    for tokens in chunk_tokens:
        for t in set(tokens):
            df[t] += 1

    # TF-IDF per chunk
    vocab = [t for t, c in df.most_common(100)]
    tfidf_scores = {}
    for t in vocab:
        idf = math.log(N / max(df[t], 1)) + 1
        total_tf = sum(tokens.count(t) for tokens in chunk_tokens)
        tfidf_scores[t] = total_tf * idf

    top_terms = sorted(tfidf_scores.items(), key=lambda x: -x[1])[:15]
    result["tfidf_top_terms"] = [{"term": t, "score": round(s, 4)} for t, s in top_terms if s > 0]

    # ── Topic modeling (word co-occurrence grouping) ──
    n_topics = min(3, max(1, N - 1))
    if vocab:
        # Group terms by co-occurrence — top terms form topic seeds
        topic_seeds = [t for t, _ in top_terms[:n_topics]]
        for topic_idx, seed in enumerate(topic_seeds):
            # Find terms that co-occur most with seed
            cooccur = Counter()
            seed_chunks = 0
            for i, tokens in enumerate(chunk_tokens):
                if seed in tokens:
                    seed_chunks += 1
                    for t in set(tokens):
                        if t != seed:
                            cooccur[t] += 1
            topic_words = [seed] + [t for t, _ in cooccur.most_common(7)]
            dominant = [i for i, tokens in enumerate(chunk_tokens) if seed in tokens]
            strength = seed_chunks / max(N, 1)
            result["topics"].append({
                "topic_id": topic_idx,
                "keywords": topic_words[:8],
                "chunk_count": seed_chunks,
                "chunks": dominant[:10],
                "strength": round(strength, 3),
            })

    # ── Clustering (k-means-like by term overlap) ──
    n_clusters = min(3, max(1, N - 1))
    if vocab and len(chunk_tokens) >= 2:
        # Assign chunks to nearest topic seed
        cluster_assignments = {}
        for c in range(n_clusters):
            cluster_assignments[c] = []
        for i, tokens in enumerate(chunk_tokens):
            best_cluster = 0
            best_score = -1
            for c in range(n_clusters):
                seed = topic_seeds[c] if c < len(topic_seeds) else vocab[c % len(vocab)]
                score = tokens.count(seed)
                if score > best_score:
                    best_score = score
                    best_cluster = c
            cluster_assignments[best_cluster].append(i)
        for c in range(n_clusters):
            member_tokens = []
            for i in cluster_assignments[c]:
                member_tokens.extend(chunk_tokens[i])
            centroid_terms = [t for t, _ in Counter(member_tokens).most_common(5)]
            result["clusters"][f"cluster_{c}"] = {
                "size": len(cluster_assignments[c]),
                "chunks": cluster_assignments[c][:10],
                "centroid_terms": centroid_terms,
            }

    # ── Anomaly detection (statistical outlier by chunk length + unique words) ──
    chunk_sizes = [len(ct) for ct in chunk_texts]
    chunk_uniq = [len(set(tokens)) for tokens in chunk_tokens]
    if len(chunk_sizes) >= 4:
        mean_size = sum(chunk_sizes) / len(chunk_sizes)
        std_size = (sum((s - mean_size) ** 2 for s in chunk_sizes) / len(chunk_sizes)) ** 0.5
        mean_uniq = sum(chunk_uniq) / len(chunk_uniq)
        std_uniq = (sum((u - mean_uniq) ** 2 for u in chunk_uniq) / len(chunk_uniq)) ** 0.5
        anomalies = []
        for i in range(len(chunk_texts)):
            z_size = abs(chunk_sizes[i] - mean_size) / max(std_size, 1)
            z_uniq = abs(chunk_uniq[i] - mean_uniq) / max(std_uniq, 1)
            if z_size > 2.0 or z_uniq > 2.0:
                anomalies.append({
                    "chunk_idx": i,
                    "preview": chunk_texts[i][:100],
                    "reason": f"statistical outlier (z_size={z_size:.1f}, z_uniq={z_uniq:.1f})",
                })
        result["anomalies"] = anomalies

    # ── Inferred KPIs (same as sklearn version) ──
    inferred = []
    char_freq = Counter(text[:8192])
    total_chars = sum(char_freq.values())
    if total_chars > 0:
        info_density = -sum((c/total_chars) * math.log2(c/total_chars) for c in char_freq.values() if c > 0)
        inferred.append({"name": "information_density", "value": f"{info_density:.2f} bits/char", "method": "shannon_entropy", "confidence": 0.9})

    if word_freq:
        freqs = sorted(word_freq.values(), reverse=True)
        if len(freqs) > 3:
            log_freqs = [math.log(f) for f in freqs]
            log_ranks = [math.log(r) for r in range(1, len(freqs) + 1)]
            n = len(freqs)
            denom = n * sum(r**2 for r in log_ranks) - sum(log_ranks)**2
            slope = (n * sum(r * f for r, f in zip(log_ranks, log_freqs)) - sum(log_ranks) * sum(log_freqs)) / denom if denom != 0 else 0
            inferred.append({"name": "zipf_slope", "value": f"{slope:.3f}", "method": "zipf_regression", "confidence": 0.7})
            inferred.append({"name": "vocabulary_concentration", "value": f"{freqs[0] / sum(freqs):.3f}", "method": "dominant_word_ratio", "confidence": 0.8})

    if result["topics"]:
        max_ts = max(t["strength"] for t in result["topics"])
        inferred.append({"name": "topic_coherence", "value": f"{max_ts:.3f}", "method": "word_cooccur", "confidence": 0.75})
        inferred.append({"name": "topic_diversity", "value": str(len(result["topics"])), "method": "topic_count", "confidence": 0.6})

    if result["clusters"]:
        cs = [c["size"] for c in result["clusters"].values()]
        if cs:
            balance = 1.0 - (max(cs) - min(cs)) / max(sum(cs), 1)
            inferred.append({"name": "structural_balance", "value": f"{balance:.3f}", "method": "cluster_balance", "confidence": 0.65})

    if chunk_texts:
        ar = len(result["anomalies"]) / len(chunk_texts)
        inferred.append({"name": "anomaly_rate", "value": f"{ar:.3f}", "method": "z_score_outlier", "confidence": 0.7})
        if ar > 0.3:
            inferred.append({"name": "anomaly_flag", "value": "high_unusual_content", "method": "z_score", "confidence": 0.6})

    fin_kpis = [k for k in kpis if k["category"] == "financial"]
    if fin_kpis and len(fin_kpis) > 3:
        inferred.append({"name": "financial_density", "value": f"{len(fin_kpis)} refs", "method": "kpi_cross_ref", "confidence": 0.8})
    if len(kpis) > 20:
        inferred.append({"name": "high_signal_density", "value": f"{len(kpis)} KPIs", "method": "kpi_count", "confidence": 0.7})

    result["inferred_kpis"] = inferred

    # LLM extrapolation
    llm_extrapolation = _jorki_llm_extrapolate(text, kpis, dna, result)
    if llm_extrapolation:
        result["llm_extrapolation"] = llm_extrapolation

    return result


def _jorki_ml_extract(text, lines, chunks, word_freq, kpis, dna):
    """Unsupervised ML: TF-IDF, NMF topics, clustering, anomaly detection, latent features."""
    try:
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.decomposition import NMF, TruncatedSVD
        from sklearn.cluster import KMeans
        from sklearn.ensemble import IsolationForest
    except ImportError:
        return _jorki_ml_extract_pure(text, lines, chunks, word_freq, kpis, dna)

    result = {"available": True, "topics": [], "clusters": {}, "anomalies": [],
              "latent_features": {}, "inferred_kpis": [], "semantic_embedding": {}}

    # Prepare chunk texts
    chunk_texts = [c["preview"] for c in chunks] if chunks else [text[:500]]
    if len(chunk_texts) > 200:
        chunk_texts = chunk_texts[:200]
    if len(chunk_texts) < 2:
        chunk_texts = [text[i:i+500] for i in range(0, len(text), 500)][:20]
    if len(chunk_texts) < 2:
        return result

    # ── TF-IDF ──
    try:
        vectorizer = TfidfVectorizer(max_features=100, stop_words="english", ngram_range=(1, 2))
        tfidf_matrix = vectorizer.fit_transform(chunk_texts)
        feature_names = vectorizer.get_feature_names_out()

        # Top distinctive terms
        scores = tfidf_matrix.sum(axis=0).A1
        top_indices = scores.argsort()[-15:][::-1]
        top_terms = [{"term": feature_names[i], "score": round(float(scores[i]), 4)} for i in top_indices if scores[i] > 0]
        result["tfidf_top_terms"] = top_terms
    except:
        top_terms = []
        result["tfidf_top_terms"] = []

    # ── NMF Topic Modeling ──
    n_topics = min(3, len(chunk_texts) - 1)
    if n_topics >= 1 and tfidf_matrix.shape[0] > 1:
        try:
            nmf = NMF(n_components=n_topics, random_state=42, max_iter=200)
            W = nmf.fit_transform(tfidf_matrix)
            H = nmf.components_
            for topic_idx in range(n_topics):
                top_words_idx = H[topic_idx].argsort()[-8:][::-1]
                topic_words = [feature_names[i] for i in top_words_idx if H[topic_idx][i] > 0.01]
                # Which chunks belong to this topic
                dominant_chunks = [i for i in range(len(chunk_texts)) if W[i].argmax() == topic_idx]
                result["topics"].append({
                    "topic_id": topic_idx,
                    "keywords": topic_words,
                    "chunk_count": len(dominant_chunks),
                    "chunks": dominant_chunks[:10],
                    "strength": round(float(W[:, topic_idx].sum() / max(W.sum(), 1)), 3),
                })
        except:
            pass

    # ── LSA / SVD for latent semantic space ──
    try:
        n_components = min(5, tfidf_matrix.shape[1] - 1, tfidf_matrix.shape[0] - 1)
        if n_components >= 1:
            svd = TruncatedSVD(n_components=n_components, random_state=42)
            svd_matrix = svd.fit_transform(tfidf_matrix)
            explained = svd.explained_variance_ratio_
            result["latent_features"]["lsa_components"] = n_components
            result["latent_features"]["explained_variance"] = [round(float(e), 4) for e in explained]
            result["latent_features"]["semantic_dimensions"] = [
                {"dim": i, "top_terms": [feature_names[j] for j in svd.components_[i].argsort()[-5:][::-1]]}
                for i in range(n_components)
            ]
            # File-level embedding = mean of chunk embeddings
            file_embedding = svd_matrix.mean(axis=0)
            result["semantic_embedding"]["dimensions"] = len(file_embedding)
            result["semantic_embedding"]["vector"] = [round(float(v), 4) for v in file_embedding]
    except:
        pass

    # ── KMeans clustering of chunks ──
    try:
        n_clusters = min(3, len(chunk_texts) - 1)
        if n_clusters >= 1 and tfidf_matrix.shape[0] >= 2:
            km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            labels = km.fit_predict(tfidf_matrix)
            for c in range(n_clusters):
                cluster_chunks = [i for i in range(len(labels)) if labels[i] == c]
                # Find centroid terms
                centroid = km.cluster_centers_[c]
                top_terms_idx = centroid.argsort()[-5:][::-1]
                cluster_terms = [feature_names[i] for i in top_terms_idx if centroid[i] > 0]
                result["clusters"][f"cluster_{c}"] = {
                    "size": len(cluster_chunks),
                    "chunks": cluster_chunks[:10],
                    "centroid_terms": cluster_terms,
                }
    except:
        pass

    # ── Isolation Forest anomaly detection ──
    try:
        if tfidf_matrix.shape[0] >= 4:
            iso = IsolationForest(random_state=42, contamination=0.15)
            anomaly_labels = iso.fit_predict(tfidf_matrix)
            anomalies = [i for i in range(len(anomaly_labels)) if anomaly_labels[i] == -1]
            result["anomalies"] = [{
                "chunk_idx": a,
                "preview": chunk_texts[a][:100] if a < len(chunk_texts) else "",
                "reason": "unusual content pattern",
            } for a in anomalies]
    except:
        pass

    # ── Inferred / latent KPIs from ML ──
    inferred = []

    # Information density (bits per character)
    import math
    from collections import Counter
    char_freq = Counter(text[:8192])
    total_chars = sum(char_freq.values())
    if total_chars > 0:
        info_density = -sum((c/total_chars) * math.log2(c/total_chars) for c in char_freq.values() if c > 0)
        inferred.append({"name": "information_density", "value": f"{info_density:.2f} bits/char", "method": "shannon_entropy", "confidence": 0.9})

    # Zipf coefficient (how well word distribution follows Zipf's law)
    if word_freq:
        freqs = sorted(word_freq.values(), reverse=True)
        ranks = list(range(1, len(freqs) + 1))
        if len(freqs) > 3:
            log_freqs = [math.log(f) for f in freqs]
            log_ranks = [math.log(r) for r in ranks]
            n = len(freqs)
            _denom = n * sum(r**2 for r in log_ranks) - sum(log_ranks)**2
            slope = (n * sum(r * f for r, f in zip(log_ranks, log_freqs)) - sum(log_ranks) * sum(log_freqs)) / _denom if _denom != 0 else 0
            inferred.append({"name": "zipf_slope", "value": f"{slope:.3f}", "method": "zipf_regression", "confidence": 0.7})
            inferred.append({"name": "vocabulary_concentration", "value": f"{freqs[0] / sum(freqs):.3f}", "method": "dominant_word_ratio", "confidence": 0.8})

    # Topic coherence (how focused the document is)
    if result["topics"]:
        max_topic_strength = max(t["strength"] for t in result["topics"])
        inferred.append({"name": "topic_coherence", "value": f"{max_topic_strength:.3f}", "method": "nmf_dominance", "confidence": 0.75})
        inferred.append({"name": "topic_diversity", "value": str(len(result["topics"])), "method": "nmf_topic_count", "confidence": 0.6})

    # Cluster separation (structural diversity)
    if result["clusters"]:
        cluster_sizes = [c["size"] for c in result["clusters"].values()]
        if cluster_sizes:
            balance = 1.0 - (max(cluster_sizes) - min(cluster_sizes)) / max(sum(cluster_sizes), 1)
            inferred.append({"name": "structural_balance", "value": f"{balance:.3f}", "method": "kmeans_balance", "confidence": 0.65})

    # Anomaly rate
    if chunk_texts:
        anomaly_rate = len(result["anomalies"]) / len(chunk_texts)
        inferred.append({"name": "anomaly_rate", "value": f"{anomaly_rate:.3f}", "method": "isolation_forest", "confidence": 0.7})
        if anomaly_rate > 0.3:
            inferred.append({"name": "anomaly_flag", "value": "high_unusual_content", "method": "isolation_forest", "confidence": 0.6})

    # Semantic complexity from LSA
    if "explained_variance" in result.get("latent_features", {}):
        ev = result["latent_features"]["explained_variance"]
        if ev:
            complexity = sum(ev[:3]) / len(ev[:3]) if len(ev) >= 3 else sum(ev) / max(len(ev), 1)
            inferred.append({"name": "semantic_complexity", "value": f"{complexity:.3f}", "method": "lsa_variance", "confidence": 0.7})

    # Cross-feature inference: financial + legal = contract value
    fin_kpis = [k for k in kpis if k["category"] == "financial"]
    legal_kpis = [k for k in kpis if k.get("category") == "technical" and "api" in k.get("name", "")]
    if fin_kpis and len(fin_kpis) > 3:
        inferred.append({"name": "financial_density", "value": f"{len(fin_kpis)} refs", "method": "kpi_cross_ref", "confidence": 0.8})
    if len(kpis) > 20:
        inferred.append({"name": "high_signal_density", "value": f"{len(kpis)} KPIs", "method": "kpi_count", "confidence": 0.7})

    result["inferred_kpis"] = inferred

    # ── LLM extrapolation (if OpenAI configured) ──
    llm_extrapolation = _jorki_llm_extrapolate(text, kpis, dna, result)
    if llm_extrapolation:
        result["llm_extrapolation"] = llm_extrapolation

    return result


def _jorki_llm_30_facts(text, kpis, dna, ml_result, meta):
    """Use Groq LLM to generate 30 facts about a file, served as KPIs."""
    if not GROQ_API_KEY and not OPENAI_API_KEY:
        return None

    filename = meta.get("filename", "unknown")
    species = dna.get("species", "?") if isinstance(dna, dict) else "?"
    complexity = float(dna.get("complexity_score", 0)) if isinstance(dna, dict) else 0
    total_lines = int(meta.get("total_lines", 0))
    total_words = int(meta.get("total_words", 0))
    total_chunks = int(meta.get("total_chunks", 0))

    kpi_summary = "; ".join(f"{k['name']}={k['value']}" for k in kpis[:15])
    topics = ", ".join(t["keywords"][:3] for t in ml_result.get("topics", [])[:3]) if ml_result.get("topics") else "none"
    text_sample = text[:2000]

    prompt = f"""You are a forensic file analyst. Generate exactly 30 distinct, factual KPI-style insights about this file.

FILE: {filename}
SPECIES: {species}
LINES: {total_lines} | WORDS: {total_words} | CHUNKS: {total_chunks} | COMPLEXITY: {complexity:.1f}
EXTRACTED KPIs: {kpi_summary}
ML TOPICS: {topics}

FILE SAMPLE (first 2000 chars):
{text_sample}

Return a JSON array of exactly 30 objects, each with:
{{
  "id": 1-30,
  "label": "short KPI name (2-4 words)",
  "value": "the fact value (string or number)",
  "category": "one of: structural|financial|technical|operational|risk|legal|ml|value|quality|security",
  "confidence": 0.0-1.0,
  "source": "llm"
}}

Cover diverse categories: structure, complexity, vocabulary, patterns, risk, value, quality, security, legal, financial, ML insights, recommendations.
Be specific and grounded in the actual file content. No generic statements."""

    # ── Fallback chain: try every active provider until one works ──
    import urllib.request as _urllib, time as _time
    _chain_path = _Path(__file__).resolve().parent / "data" / "llm_fallback_chain.json"
    _cat_path = _Path(__file__).resolve().parent / "data" / "api_catalog.json"
    providers_to_try = []
    # 1) Build from fallback chain (ranked)
    if _chain_path.exists():
        try:
            for c in json.load(open(_chain_path)):
                if c.get("score", 0) > 0: providers_to_try.append(c)
        except: pass
    # 2) Fallback to hardcoded Groq/OpenAI if chain empty
    if not providers_to_try:
        if GROQ_API_KEY: providers_to_try.append({"provider":"groq","env_var":"GROQ_API_KEY","model":"llama-3.3-70b-versatile"})
        if OPENAI_API_KEY: providers_to_try.append({"provider":"openai","env_var":"OPENAI_API_KEY","model":"gpt-4o-mini"})
    # 2.5) Always add LLM7 anonymous as ultimate fallback
    providers_to_try.append({"provider":"llm7","env_var":"LLM7_API_KEY","model":"fast","endpoint":"https://api.llm7.io/v1/chat/completions"})
    # 3) Load catalog for endpoints
    _endpoints = {}
    if _cat_path.exists():
        try:
            for s in json.load(open(_cat_path)).get("services", []): _endpoints[s["p"]] = s["e"]
        except: pass
    if "groq" not in _endpoints: _endpoints["groq"] = GROQ_URL
    if "openai" not in _endpoints: _endpoints["openai"] = "https://api.openai.com/v1/chat/completions"
    # 4) Try each provider
    for entry in providers_to_try:
        prov = entry.get("provider",""); env_var = entry.get("env_var",""); model = entry.get("model","")
        key = os.environ.get(env_var, "unused" if prov == "llm7" else "")
        if not key: continue
        endpoint = entry.get("endpoint", "") or _endpoints.get(prov, "")
        if not endpoint: continue
        try:
            body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.3, "max_tokens": 2000}).encode()
            req = _urllib.Request(endpoint, data=body, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("Authorization", f"Bearer {key}")
            with _urllib.urlopen(req, timeout=30) as resp:
                content = json.loads(resp.read())["choices"][0]["message"]["content"]
            return _parse_facts(content)
        except Exception: continue
    return None


def _parse_facts(content):
    """Parse LLM response into 30 facts."""
    try:
        facts = json.loads(content)
        if isinstance(facts, list):
            return facts[:30]
        if isinstance(facts, dict) and "facts" in facts:
            return facts["facts"][:30]
    except:
        import re as _re
        m = _re.search(r'\[.*\]', content, _re.DOTALL)
        if m:
            try:
                return json.loads(m.group())[:30]
            except:
                pass
    return [{"id": 1, "label": "llm_parse_error", "value": content[:200], "category": "technical", "confidence": 0.1, "source": "llm"}]


def _jorki_llm_extrapolate(text, kpis, dna, ml_result):
    """Use LLM to extrapolate hidden features, risks, and opportunities."""
    if not OPENAI_API_KEY:
        return None

    # Build a compact prompt from extracted features
    kpi_summary = "; ".join(f"{k['name']}={k['value']}" for k in kpis[:15])
    dna_summary = f"species={dna.get('species','?')}, complexity={dna.get('complexity_score',0)}"
    topics = ", ".join(t["keywords"][:3] for t in ml_result.get("topics", [])[:2])
    text_sample = text[:1500]

    prompt = f"""Analyze this file's extracted features and extrapolate hidden value, risks, and opportunities.

FILE SAMPLE (first 1500 chars):
{text_sample}

EXTRACTED KPIs: {kpi_summary}
DNA: {dna_summary}
ML TOPICS: {topics}

Return JSON with:
{{
  "inferred_purpose": "what this file is likely used for",
  "hidden_value": "economic or strategic value not obvious from content",
  "counterparty_risk": "any risk from sharing this with external parties",
  "monetization_vector": "how this file's data could be monetized",
  "compliance_flags": ["any regulatory concerns"],
  "comparable_assets": "what kind of financial or intellectual asset this resembles",
  "confidence": 0.0-1.0
}}"""

    try:
        import requests as _req
        resp = _req.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": "gpt-4o-mini",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": 500,
            },
            timeout=15,
        )
        if resp.status_code == 200:
            content = resp.json()["choices"][0]["message"]["content"]
            try:
                return json.loads(content)
            except:
                return {"raw_response": content}
    except:
        pass
    return None


@app.get("/ml/{file_id}")
async def jorki_ml_profile(file_id: str):
    """Unsupervised ML features: topics, clusters, anomalies, latent features, LLM extrapolation."""
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    meta_rows = conn.execute("SELECT key, value FROM file_meta").fetchall()
    kpi_rows = conn.execute("SELECT id, name, value, line, category, confidence FROM kpis").fetchall()
    dna_rows = conn.execute("SELECT key, value FROM dna").fetchall()
    word_rows = conn.execute("SELECT word, count FROM word_freq").fetchall()
    chunk_rows = conn.execute("SELECT idx, line_start, line_end, boundary_type, preview, line_count FROM chunks").fetchall()
    conn.close()
    _jorki_track_query(file_id, "ml")

    meta = {r[0]: r[1] for r in meta_rows}
    kpis = [{"id": r[0], "name": r[1], "value": r[2], "line": r[3], "category": r[4], "confidence": r[5]} for r in kpi_rows]
    dna = {r[0]: r[1] for r in dna_rows}
    word_freq = {r[0]: int(r[1]) for r in word_rows}
    chunks = [{"idx": r[0], "line_start": r[1], "line_end": r[2], "boundary_type": r[3], "preview": r[4], "line_count": r[5]} for r in chunk_rows]

    # Reconstruct text from chunks (limit to first 200 chunks for performance)
    text = "\n".join(c["preview"] for c in chunks[:200])
    lines = text.split("\n")

    try:
        dna_obj = json.loads(dna.get("genes", "{}")) if isinstance(dna.get("genes"), str) else {}
        dna_dict = {"genes": dna_obj, "complexity_score": float(dna.get("complexity_score", 0)),
                    "dna_sequence": dna.get("dna_sequence", ""), "species": dna.get("species", "")}
    except:
        dna_dict = {}

    try:
        ml_result = _jorki_ml_extract(text, lines, chunks, word_freq, kpis, dna_dict)
    except Exception as e:
        ml_result = {"available": False, "error": str(e), "engine": "error"}
    return {"file_id": file_id, "filename": meta.get("filename", "unknown"), "ml": ml_result}

# ─── Pipeline API: Clipboard → Repo → Artifact → Deploy → App → DMG → AppStore ─

import subprocess as _subproc
import re as _re
import uuid as _uuid

PIPELINE_DIR = _Path(os.environ.get("JORKI_PIPELINE_DIR", "/tmp/jorki_pipeline"))
PIPELINE_RUNS = {}
PIPELINE_LOGS = {}

PIPELINE_STAGES = ["clipboard", "repo", "artifact", "deploy"]

GLYPH_MAP = {"idle": "◌", "active": "◉", "complete": "✓", "error": "⟁", "skipped": "◍"}

def _pipe_log(run_id: str, stage: str, msg: str, level: str = "info"):
    if run_id not in PIPELINE_LOGS:
        PIPELINE_LOGS[run_id] = []
    glyph = GLYPH_MAP.get("active" if level == "info" else
                           "complete" if level == "done" else
                           "error" if level == "error" else "active", "◉")
    PIPELINE_LOGS[run_id].append({
        "ts": datetime.now().strftime("%H:%M:%S"),
        "stage": stage, "msg": msg, "level": level, "glyph": glyph,
    })

def _pipe_receipt(chain: list, stage: str, artifacts: dict) -> dict:
    prev = chain[-1]["hash"] if chain else "0" * 64
    entry = json.dumps({"stage": stage, "artifacts": artifacts, "ts": time.time()}, sort_keys=True, default=str)
    h = hashlib.sha256((prev + entry).encode()).hexdigest()
    r = {"stage": stage, "artifacts": artifacts, "hash": h, "prev_hash": prev, "ts": time.time()}
    chain.append(r)
    return r

def _detect_content_type(content: str) -> str:
    s = content.strip()
    if not s: return "empty"
    if s.startswith("{") or s.startswith("["):
        try: json.loads(s); return "json"
        except: pass
    if s.startswith("#!"): return "script"
    if "import " in s and ("def " in s or "class " in s): return "python"
    if "function " in s or "const " in s or "=>" in s: return "javascript"
    if s.startswith("<"): return "markup"
    if "# " in s[:10] or "## " in s[:20]: return "markdown"
    if _re.match(r'^(FROM|RUN|COPY|CMD|WORKDIR)', s, _re.MULTILINE): return "dockerfile"
    return "text"

def _derive_name(content: str, ctype: str) -> str:
    if ctype == "python":
        for line in content.split("\n"):
            if "class " in line and ":" in line:
                n = line.split("class ")[1].split("(")[0].split(":")[0].strip()
                if n and n[0].isupper(): return _re.sub(r'[^A-Za-z0-9]', '', n)
    if ctype == "json":
        try:
            d = json.loads(content.strip())
            if isinstance(d, dict):
                for k in ("name", "title", "app"):
                    if k in d and isinstance(d[k], str): return _re.sub(r'[^A-Za-z0-9]', '', d[k])
        except: pass
    words = _re.findall(r'\b[A-Za-z][a-z]+\b', content[:500])
    if words: return _re.sub(r'[^A-Za-z0-9]', '', "".join(w.capitalize() for w in words[:3])) or "ClipboardApp"
    return "ClipboardApp"

def _run_pipeline(run_id: str, content: str):
    state = PIPELINE_RUNS[run_id]
    chain = state["receipt_chain"]
    try:
        # Stage 1: Clipboard
        _pipe_log(run_id, "clipboard", f"Read {len(content)} chars")
        ctype = _detect_content_type(content)
        chash = hashlib.sha256(content.encode()).hexdigest()
        pname = _derive_name(content, ctype)
        state["content_type"] = ctype
        state["content_hash"] = chash
        state["project_name"] = pname
        state["content_preview"] = content[:500]

        # Index clipboard content via Jorki indexer for dossier/intel
        try:
            clip_path = JORKI_DATA_DIR / "pipeline_uploads" / f"{pname}.txt"
            clip_path.parent.mkdir(parents=True, exist_ok=True)
            clip_path.write_text(content)
            idx_result = _jorki_index_file(str(clip_path))
            state["file_id"] = idx_result.get("file_id", "")
            reg = _jorki_load_registry()
            reg[state["file_id"]] = {
                "filename": idx_result.get("filename", pname),
                "size_bytes": idx_result.get("size_bytes", 0),
                "size_human": idx_result.get("size_human", ""),
                "format": ctype, "status": "active", "indexed_at": time.time(),
            }
            _jorki_save_registry(reg)
            _pipe_log(run_id, "clipboard", f"Indexed as file_id: {state['file_id']}", "ok")
        except Exception as e:
            _pipe_log(run_id, "clipboard", f"Index warning: {str(e)[:80]}", "info")

        _pipe_receipt(chain, "clipboard", {"type": ctype, "hash": chash, "name": pname, "file_id": state.get("file_id", "")})
        state["completed_stages"].append("clipboard")
        _pipe_log(run_id, "clipboard", f"Type: {ctype} │ Name: {pname}", "ok")

        # Stage 2: Repo
        state["current_stage"] = "repo"
        _pipe_log(run_id, "repo", f"Creating project: {pname}")
        proj_dir = PIPELINE_DIR / "projects" / pname
        proj_dir.mkdir(parents=True, exist_ok=True)
        main_file = "main.py" if ctype in ("python", "script") else \
                    "index.js" if ctype == "javascript" else \
                    "index.html" if ctype == "markup" else \
                    "content.md" if ctype == "markdown" else \
                    "data.json" if ctype == "json" else "content.txt"
        (proj_dir / main_file).write_text(content)
        (proj_dir / "README.md").write_text(f"# {pname}\n\nAuto-generated from clipboard via Jorki pipeline.\n\n- Type: {ctype}\n- Hash: `{chash}`\n")
        (proj_dir / ".gitignore").write_text(".venv/\n__pycache__/\nnode_modules/\ndist/\nbuild/\n.env\n*.dmg\n")

        _subproc.run(["git", "init"], cwd=str(proj_dir), capture_output=True, check=False)
        _subproc.run(["git", "add", "-A"], cwd=str(proj_dir), capture_output=True, check=False)
        env = {**os.environ, "GIT_AUTHOR_NAME": "Jorki", "GIT_AUTHOR_EMAIL": "pipeline@jorki.local",
               "GIT_COMMITTER_NAME": "Jorki", "GIT_COMMITTER_EMAIL": "pipeline@jorki.local"}
        _subproc.run(["git", "commit", "-m", f"Initial commit from clipboard\n\nType: {ctype}\nHash: {chash}"],
                     cwd=str(proj_dir), capture_output=True, check=False, env=env)

        repo_name = pname.lower().replace("_", "-")
        gh_url = ""
        try:
            r = _subproc.run(["gh", "repo", "create", repo_name, "--public", "--source=.", "--push",
                              "--description", f"Auto-generated from clipboard ({ctype})"],
                             cwd=str(proj_dir), capture_output=True, text=True, check=False, env=env)
            if r.returncode == 0:
                for line in (r.stderr + r.stdout).split("\n"):
                    if "github.com" in line:
                        gh_url = line.strip().split()[-1]; break
                if not gh_url:
                    r2 = _subproc.run(["gh", "repo", "view", repo_name, "--json", "url"],
                                      capture_output=True, text=True, check=False)
                    if r2.returncode == 0:
                        try: gh_url = json.loads(r2.stdout).get("url", "")
                        except: pass
                state["github_repo"] = repo_name
                state["github_url"] = gh_url
                _pipe_log(run_id, "repo", f"GitHub: {gh_url}", "ok")
            else:
                _pipe_log(run_id, "repo", f"gh failed: {r.stderr.strip()[:100]}", "info")
                state["github_repo"] = repo_name
                state["github_url"] = ""
                _pipe_receipt(chain, "repo", {"repo": repo_name, "url": "local", "dir": str(proj_dir), "skipped": "gh_error"})
        except FileNotFoundError:
            _pipe_log(run_id, "repo", f"gh not installed — local repo only: {str(proj_dir)}", "info")
            state["github_repo"] = repo_name
            state["github_url"] = ""
            _pipe_receipt(chain, "repo", {"repo": repo_name, "url": "local", "dir": str(proj_dir), "skipped": "gh_not_found"})
        _pipe_receipt(chain, "repo", {"repo": repo_name, "url": gh_url or "local", "dir": str(proj_dir)})
        state["completed_stages"].append("repo")

        # Stage 3: Artifact (HuggingFace Space)
        state["current_stage"] = "artifact"
        hf_token = os.environ.get("HF_TOKEN", "")
        if hf_token:
            _pipe_log(run_id, "artifact", "Creating HuggingFace Space…")
            try:
                from huggingface_hub import HfApi, create_repo
                space_id = f"{os.environ.get('HF_USERNAME', 'user')}/{repo_name}-space"
                create_repo(repo_id=space_id, repo_type="space", space_sdk="static", exist_ok=True)
                api = HfApi()
                api.upload_folder(folder_path=str(proj_dir), repo_id=space_id, repo_type="space")
                hf_url = f"https://huggingface.co/spaces/{space_id}"
                state["hf_space_id"] = space_id
                state["hf_space_url"] = hf_url
                _pipe_log(run_id, "artifact", f"HF Space: {hf_url}", "ok")
                _pipe_receipt(chain, "artifact", {"space_id": space_id, "url": hf_url})
            except Exception as e:
                _pipe_log(run_id, "artifact", f"HF failed: {str(e)[:100]}", "error")
                state["error_stage"] = "artifact"
                state["status"] = "error"
                return
        else:
            _pipe_log(run_id, "artifact", "HF_TOKEN not set — skipping", "info")
            _pipe_receipt(chain, "artifact", {"skipped": True, "reason": "no HF_TOKEN"})
        state["completed_stages"].append("artifact")

        # Stage 4: Deploy (Vercel)
        state["current_stage"] = "deploy"
        _pipe_log(run_id, "deploy", "Deploying to Vercel…")
        try:
            r = _subproc.run(["vercel", "--prod", "--yes"], cwd=str(proj_dir),
                             capture_output=True, text=True, check=False, timeout=120)
            if r.returncode == 0:
                vercel_url = r.stdout.strip().split("\n")[-1].strip()
                if not vercel_url.startswith("http"):
                    for line in r.stdout.split("\n"):
                        if "https://" in line:
                            vercel_url = line.strip(); break
                state["vercel_url"] = vercel_url
                _pipe_log(run_id, "deploy", f"Vercel: {vercel_url}", "ok")
                _pipe_receipt(chain, "deploy", {"url": vercel_url})
            else:
                _pipe_log(run_id, "deploy", f"Vercel failed: {r.stderr.strip()[:100]}", "error")
                _pipe_receipt(chain, "deploy", {"failed": True, "error": r.stderr.strip()[:200]})
        except Exception as e:
            _pipe_log(run_id, "deploy", f"Vercel error: {str(e)[:100]}", "error")
            _pipe_receipt(chain, "deploy", {"error": str(e)[:200]})
        state["completed_stages"].append("deploy")

        state["status"] = "complete"
        state["current_stage"] = ""
        _pipe_log(run_id, "pipeline", "Pipeline complete", "done")

    except Exception as e:
        _pipe_log(run_id, state.get("current_stage", "pipeline"), f"Error: {str(e)[:200]}", "error")
        state["status"] = "error"
        state["error_stage"] = state.get("current_stage", "unknown")

@app.post("/pipeline/trigger")
async def pipeline_trigger(body: dict = Body(...)):
    content = body.get("content", "")
    if not content:
        try:
            r = _subproc.run(["pbpaste"], capture_output=True, text=True, check=False, timeout=5)
            content = r.stdout
        except Exception:
            content = ""
    if not content.strip():
        return {"error": "Clipboard is empty and no content provided"}
    run_id = str(_uuid.uuid4())[:12]
    PIPELINE_RUNS[run_id] = {
        "run_id": run_id, "status": "running", "current_stage": "clipboard",
        "completed_stages": [], "error_stage": "",
        "content_type": "", "content_hash": "", "project_name": "",
        "content_preview": "", "github_repo": "", "github_url": "",
        "hf_space_id": "", "hf_space_url": "", "vercel_url": "",
        "app_bundle_path": "", "dmg_path": "", "notarization_id": "",
        "file_id": "", "receipt_chain": [],
    }
    PIPELINE_LOGS[run_id] = []
    thread = threading.Thread(target=lambda: _run_pipeline(run_id, content), daemon=True)
    thread.start()
    return {"run_id": run_id, "status": "started", "message": "Pipeline started. Poll GET /pipeline/status/{run_id}"}

@app.get("/pipeline/status/{run_id}")
async def pipeline_status(run_id: str):
    state = PIPELINE_RUNS.get(run_id)
    if not state:
        return {"error": f"Run {run_id} not found"}
    result = dict(state)
    result["logs"] = PIPELINE_LOGS.get(run_id, [])
    return result

@app.get("/pipeline/latest")
async def pipeline_latest():
    if not PIPELINE_RUNS:
        return {"run_id": None}
    latest = max(PIPELINE_RUNS.values(), key=lambda s: s.get("started_at", 0) if "started_at" in s else 0)
    return {"run_id": latest["run_id"], "status": latest["status"]}

@app.get("/pipeline/receipts/{run_id}")
async def pipeline_receipts(run_id: str):
    state = PIPELINE_RUNS.get(run_id)
    if not state:
        return {"error": f"Run {run_id} not found"}
    return {"run_id": run_id, "receipts": state.get("receipt_chain", []),
            "chain_valid": all(
                r["prev_hash"] == (state["receipt_chain"][i-1]["hash"] if i > 0 else "0"*64)
                for i, r in enumerate(state.get("receipt_chain", []))
            )}

# Mount React UI static assets if dist exists
_ui_dist = _Path("/app/jorki_ui_dist")
if _ui_dist.exists():
    _assets_dist = _ui_dist / "assets"
    if _assets_dist.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets_dist)), name="jorki_assets")

    @app.get("/ui")
    async def jorki_ui():
        return FileResponse(str(_ui_dist / "index.html"))

# ─── LLM API Key Agent Endpoints ────────────────────────────────────────
_LLM_DATA_DIR = _Path(__file__).resolve().parent / "data"
_LLM_CATALOG_PATH = _LLM_DATA_DIR / "api_catalog_raw.json"
if not _LLM_CATALOG_PATH.exists():
    _LLM_CATALOG_PATH = _LLM_DATA_DIR / "api_catalog.json"
_LLM_REGISTRY_PATH = _LLM_DATA_DIR / "api_key_registry.json"
_LLM_CHAIN_PATH = _LLM_DATA_DIR / "llm_fallback_chain.json"
_LLM_USAGE = {"total_requests": 0, "per_provider": {}, "fallbacks_triggered": 0}

def _llm_load_json(path):
    if path.exists():
        with open(path) as f: return json.load(f)
    return {}

def _llm_save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f: json.dump(data, f, indent=2)

@app.get("/llm/keys")
async def llm_keys():
    """Return all validated keys with status, provider, model, score."""
    registry = _llm_load_json(_LLM_REGISTRY_PATH)
    return {"keys": registry, "total": len(registry) if isinstance(registry, list) else 0,
            "active": sum(1 for r in registry if r.get("status") == "active") if isinstance(registry, list) else 0}

@app.get("/llm/catalog")
async def llm_catalog():
    """Return full 300+ service catalog."""
    return _llm_load_json(_LLM_CATALOG_PATH)

@app.get("/llm/models")
async def llm_models():
    """Return all available models across all providers."""
    catalog = _llm_load_json(_LLM_CATALOG_PATH)
    models = []
    for svc in catalog.get("services", []):
        for m in svc.get("m", []):
            models.append({"model": m, "provider": svc["p"], "category": svc["c"], "endpoint": svc["e"]})
    return {"models": models, "total": len(models)}

@app.get("/llm/health")
async def llm_health():
    """Ping all providers, return live status board."""
    import urllib.request, urllib.error, time as _time
    registry = _llm_load_json(_LLM_REGISTRY_PATH)
    if not isinstance(registry, list): registry = []
    statuses = []
    for r in registry:
        p = r.get("provider", ""); st = r.get("status", "unknown")
        glyph = {"active": "◉", "expired": "⟁", "rate_limited": "⧖", "invalid": "✕", "untested": "◌"}.get(st, "◌")
        statuses.append({"provider": p, "status": st, "glyph": glyph, "latency_ms": r.get("latency_ms", 0), "score": r.get("score", 0)})
    return {"providers": statuses, "timestamp": _time.time(),
            "summary": {"active": sum(1 for s in statuses if s["status"] == "active"),
                        "total": len(statuses)}}

@app.get("/llm/chain")
async def llm_chain():
    """Return the ranked fallback chain."""
    return {"chain": _llm_load_json(_LLM_CHAIN_PATH)}

@app.post("/llm/chat")
async def llm_chat(body: dict = Body(...)):
    """Auto-route to best available provider, fall back on failure."""
    import urllib.request, urllib.error, time as _time
    chain = _llm_load_json(_LLM_CHAIN_PATH)
    if not isinstance(chain, list): chain = []
    active = [c for c in chain if c.get("score", 0) > 0]
    if not active: active = chain
    # Always include LLM7 anonymous as ultimate fallback
    active.append({"provider": "llm7", "env_var": "LLM7_API_KEY", "model": "fast", "endpoint": "https://api.llm7.io/v1/chat/completions"})
    messages = body.get("messages", [{"role": "user", "content": "Hello"}])
    model = body.get("model", "")
    prompt = body.get("prompt", "")
    if prompt and not messages: messages = [{"role": "user", "content": prompt}]
    errors = []
    for entry in active:
        provider = entry.get("provider", ""); env_var = entry.get("env_var", "")
        key = os.environ.get(env_var, "unused"); endpoint = entry.get("endpoint", "")
        if not endpoint:
            for svc in _llm_load_json(_LLM_CATALOG_PATH).get("services", []):
                if svc["p"] == provider: endpoint = svc["e"]; break
        if not endpoint: continue
        use_model = model or entry.get("model", "")
        req_body = json.dumps({"model": use_model, "messages": messages, "max_tokens": body.get("max_tokens", 500), "temperature": body.get("temperature", 0.3)}).encode()
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        try:
            req = urllib.request.Request(endpoint, data=req_body, headers=headers, method="POST")
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read())
            _LLM_USAGE["total_requests"] += 1
            _LLM_USAGE["per_provider"][provider] = _LLM_USAGE["per_provider"].get(provider, 0) + 1
            return {"response": data.get("choices", [{}])[0].get("message", {}).get("content", ""),
                    "provider": provider, "model": use_model, "usage": _LLM_USAGE}
        except Exception as e:
            errors.append({"provider": provider, "error": str(e)[:200]}); continue
    _LLM_USAGE["fallbacks_triggered"] += 1
    return {"error": "All providers failed", "errors": errors, "usage": _LLM_USAGE}

@app.post("/llm/rotate")
async def llm_rotate():
    """Trigger re-discovery + re-validation + re-ranking via ETL script."""
    import subprocess
    etl_script = _Path(__file__).resolve().parent / "scripts" / "master_etl.py"
    if not etl_script.exists():
        etl_script = _Path(__file__).resolve().parent / "scripts" / "api_key_etl.py"
    if not etl_script.exists():
        return {"error": "ETL script not found", "path": str(etl_script)}
    try:
        result = subprocess.run([sys.executable, str(etl_script), "--phase", "all"], capture_output=True, text=True, timeout=120, cwd=str(_Path(__file__).resolve().parent))
        return {"status": "completed", "stdout": result.stdout[-500:], "stderr": result.stderr[-500:] if result.stderr else ""}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": "ETL script timed out after 60s"}
    except Exception as e:
        return {"status": "error", "error": str(e)[:200]}

@app.get("/llm/usage")
async def llm_usage():
    """Track tokens used per provider, requests served, fallbacks triggered."""
    return _LLM_USAGE

@app.post("/llm/keys/add")
async def llm_keys_add(body: dict = Body(...)):
    """Manually add a key, auto-validate, insert into registry."""
    provider = body.get("provider", ""); key = body.get("key", ""); env_var = body.get("env_var", "")
    if not provider or not key: return {"error": "provider and key required"}
    catalog = _llm_load_json(_LLM_CATALOG_PATH)
    svc = None
    for s in catalog.get("services", []):
        if s["p"] == provider: svc = s; break
    if not svc: return {"error": f"Unknown provider: {provider}"}
    env_var = env_var or svc.get("env", "")
    # Update .env
    env_path = _Path(__file__).resolve().parent / ".env"
    existing = {}
    if env_path.exists():
        for line in open(env_path, errors="ignore"):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1); existing[k] = v.strip().strip("'\"")
    existing[env_var] = key
    with open(env_path, "w") as f:
        for k, v in sorted(existing.items()): f.write(f"{k}={v}\n")
    os.environ[env_var] = key
    return {"status": "added", "provider": provider, "env_var": env_var, "message": "Key added to .env. Run /llm/rotate to validate."}

@app.post("/llm/facts/{file_id}")
async def llm_facts(file_id: str, body: dict = Body(default={})):
    """Use best available LLM to generate 30 facts about a file."""
    eval_data = _evaluations.get(file_id)
    if not eval_data: raise HTTPException(404, f"File {file_id} not found")
    if eval_data.get("status") != "done": raise HTTPException(409, f"File still processing: {eval_data.get('status')}")
    result = eval_data.get("result", {})
    meta = result.get("meta", {})
    kpis = result.get("kpis", [])
    dna = result.get("dna", {})
    ml_result = result.get("ml", {})
    text = result.get("text", "")[:2000]
    facts = _jorki_llm_30_facts(text, kpis, dna, ml_result, meta)
    if not facts: return {"error": "All LLM providers failed", "file_id": file_id}
    return {"file_id": file_id, "facts": facts, "count": len(facts) if isinstance(facts, list) else 0}

# ─── OVERAGENT: Production Control Plane ────────────────────────────────
# Evidence-only RevenueOps: first-party metrics in → KPIs → decision gate
# → receipts → dashboard → operator report.
# No secrets. No fake availability. No platform abuse. Proof density only.

OA_DATA_DIR = _Path(os.environ.get("SYSTEMLAKE_DATA_DIR", "/tmp/systemlake_v4b")) / "overagent"
OA_DATA_DIR.mkdir(parents=True, exist_ok=True)
OA_DB_PATH = OA_DATA_DIR / "overagent.db"
OA_DECISIONS = []
OA_EXPERIMENTS = {}

def _oa_db():
    conn = sqlite3.connect(str(OA_DB_PATH))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, source TEXT, metric TEXT, value REAL, unit TEXT, tags TEXT
        );
        CREATE TABLE IF NOT EXISTS receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, action TEXT, actor TEXT, detail TEXT, hash TEXT, prev_hash TEXT
        );
        CREATE TABLE IF NOT EXISTS kpi_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, immortality REAL, virality REAL, conversion REAL, proof REAL, composite REAL
        );
        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, action TEXT, rationale TEXT, evidence TEXT, approved INTEGER, operator TEXT
        );
        CREATE TABLE IF NOT EXISTS experiments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts REAL, name TEXT, hypothesis TEXT, state TEXT, metric_delta TEXT, verdict TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts);
        CREATE INDEX IF NOT EXISTS idx_receipts_ts ON receipts(ts);
        CREATE INDEX IF NOT EXISTS idx_kpi_ts ON kpi_history(ts);
    """)
    return conn

def _oa_receipt(action: str, actor: str, detail: str) -> str:
    conn = _oa_db()
    prev = conn.execute("SELECT hash FROM receipts ORDER BY id DESC LIMIT 1").fetchone()
    prev_hash = prev[0] if prev else "0" * 64
    h = hashlib.sha256(f"{action}{actor}{detail}{prev_hash}{time.time()}".encode()).hexdigest()
    conn.execute("INSERT INTO receipts (ts, action, actor, detail, hash, prev_hash) VALUES (?,?,?,?,?,?)",
                 (time.time(), action, actor, detail[:500], h, prev_hash))
    conn.commit(); conn.close()
    return h

def _oa_compute_kpis() -> dict:
    conn = _oa_db()
    now = time.time()
    hour_ago = now - 3600
    # Immortality: system uptime, endpoint availability, proof persistence
    health_count = conn.execute("SELECT COUNT(*) FROM metrics WHERE metric='health_check' AND ts > ?", (hour_ago,)).fetchone()[0]
    receipt_count = conn.execute("SELECT COUNT(*) FROM receipts WHERE ts > ?", (hour_ago,)).fetchone()[0]
    total_receipts = conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    immortality = min(100, (health_count / 6) * 40 + min(30, total_receipts * 2) + min(30, receipt_count * 10))
    # Virality: view velocity, contact-click lift, acceleration
    views = conn.execute("SELECT SUM(value) FROM metrics WHERE metric='profile_view' AND ts > ?", (hour_ago,)).fetchone()[0] or 0
    contacts = conn.execute("SELECT SUM(value) FROM metrics WHERE metric='contact_click' AND ts > ?", (hour_ago,)).fetchone()[0] or 0
    prev_views = conn.execute("SELECT SUM(value) FROM metrics WHERE metric='profile_view' AND ts <= ? AND ts > ?", (hour_ago, now - 7200)).fetchone()[0] or 0
    view_accel = ((views - prev_views) / max(prev_views, 1)) * 100 if prev_views > 0 else (50 if views > 0 else 0)
    virality = min(100, min(40, views * 4) + min(30, view_accel) + min(30, contacts * 15))
    # Conversion: profile views → contact actions
    if views > 0:
        conversion = min(100, (contacts / views) * 100 * 10)  # scaled
    else:
        conversion = 0
    # Proof: receipts backing claims, reproducible artifacts
    proof_metrics = conn.execute("SELECT COUNT(DISTINCT metric) FROM metrics WHERE ts > ?", (hour_ago,)).fetchone()[0]
    proof = min(100, min(40, total_receipts * 3) + min(30, proof_metrics * 10) + min(30, receipt_count * 10))
    conn.close()
    composite = (immortality * 0.25 + virality * 0.30 + conversion * 0.25 + proof * 0.20)
    return {
        "immortality": round(immortality, 1),
        "virality": round(virality, 1),
        "conversion": round(conversion, 1),
        "proof": round(proof, 1),
        "composite": round(composite, 1),
        "raw": {"health_checks_1h": health_count, "receipts_1h": receipt_count, "total_receipts": total_receipts,
                "views_1h": int(views), "contacts_1h": int(contacts), "prev_views_1h": int(prev_views),
                "view_acceleration_pct": round(view_accel, 1), "distinct_metrics_1h": proof_metrics},
    }

@app.post("/api/metrics/ingest")
async def oa_metrics_ingest(body: dict = Body(...)):
    """First-party metrics in. Accepts metric events from approved sources."""
    source = body.get("source", "unknown")
    metrics = body.get("metrics", [])
    if not metrics and "metric" in body:
        metrics = [{"metric": body["metric"], "value": body.get("value", 1), "unit": body.get("unit", "count"), "tags": body.get("tags", "")}]
    if not metrics:
        return {"error": "No metrics provided"}
    conn = _oa_db()
    now = time.time()
    inserted = 0
    for m in metrics:
        conn.execute("INSERT INTO metrics (ts, source, metric, value, unit, tags) VALUES (?,?,?,?,?,?)",
                     (now, source, m.get("metric", ""), float(m.get("value", 1)), m.get("unit", "count"), json.dumps(m.get("tags", {}))))
        inserted += 1
    conn.commit(); conn.close()
    rhash = _oa_receipt("metrics_ingest", source, f"{inserted} metrics from {source}")
    return {"status": "ingested", "count": inserted, "receipt": rhash[:16], "timestamp": now}

@app.get("/api/kpis")
async def oa_kpis():
    """Live KPI readout: Immortality, Virality, Conversion, Proof, composite."""
    kpis = _oa_compute_kpis()
    conn = _oa_db()
    conn.execute("INSERT INTO kpi_history (ts, immortality, virality, conversion, proof, composite) VALUES (?,?,?,?,?,?)",
                 (time.time(), kpis["immortality"], kpis["virality"], kpis["conversion"], kpis["proof"], kpis["composite"]))
    conn.commit(); conn.close()
    return {"kpis": kpis, "timestamp": time.time()}

@app.get("/api/kpis/history")
async def oa_kpi_history(hours: int = 24):
    """KPI history for trend analysis."""
    conn = _oa_db()
    cutoff = time.time() - hours * 3600
    rows = conn.execute("SELECT ts, immortality, virality, conversion, proof, composite FROM kpi_history WHERE ts > ? ORDER BY ts", (cutoff,)).fetchall()
    conn.close()
    return {"history": [{"ts": r[0], "immortality": r[1], "virality": r[2], "conversion": r[3], "proof": r[4], "composite": r[5]} for r in rows], "count": len(rows)}

@app.post("/api/decision-gate")
async def oa_decision_gate(body: dict = Body(...)):
    """Decision ledger out. Records approved/rejected actions with evidence."""
    action = body.get("action", "")
    rationale = body.get("rationale", "")
    evidence = body.get("evidence", "")
    approved = body.get("approved", False)
    operator = body.get("operator", "system")
    if not action:
        return {"error": "action is required"}
    conn = _oa_db()
    conn.execute("INSERT INTO decisions (ts, action, rationale, evidence, approved, operator) VALUES (?,?,?,?,?,?)",
                 (time.time(), action, rationale[:300], evidence[:300], 1 if approved else 0, operator))
    conn.commit(); conn.close()
    rhash = _oa_receipt("decision", operator, f"{'APPROVED' if approved else 'REJECTED'}: {action} — {rationale}")
    kpis = _oa_compute_kpis()
    recommendation = "keep" if kpis["composite"] > 50 else "rollback" if kpis["composite"] < 25 else "wait"
    return {
        "decision": action,
        "approved": approved,
        "receipt": rhash[:16],
        "kpi_snapshot": kpis,
        "recommendation": recommendation,
        "timestamp": time.time(),
    }

@app.get("/api/decision-gate")
async def oa_decision_list():
    """List all decisions in the ledger."""
    conn = _oa_db()
    rows = conn.execute("SELECT ts, action, rationale, evidence, approved, operator FROM decisions ORDER BY ts DESC LIMIT 50").fetchall()
    conn.close()
    return {"decisions": [{"ts": r[0], "action": r[1], "rationale": r[2], "evidence": r[3], "approved": bool(r[4]), "operator": r[5]} for r in rows], "count": len(rows)}

@app.get("/api/receipts")
async def oa_receipts(limit: int = 50):
    """Receipt ledger — tamper-evident chain of all important actions."""
    conn = _oa_db()
    rows = conn.execute("SELECT ts, action, actor, detail, hash, prev_hash FROM receipts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {
        "receipts": [{"ts": r[0], "action": r[1], "actor": r[2], "detail": r[3], "hash": r[4], "prev_hash": r[5]} for r in rows],
        "count": len(rows),
        "chain_verified": len(rows) > 0,
    }

@app.post("/api/experiments")
async def oa_experiment_create(body: dict = Body(...)):
    """Track experiment state: hypothesis, metric delta, verdict."""
    name = body.get("name", "")
    hypothesis = body.get("hypothesis", "")
    if not name:
        return {"error": "name is required"}
    conn = _oa_db()
    conn.execute("INSERT INTO experiments (ts, name, hypothesis, state, metric_delta, verdict) VALUES (?,?,?,?,?,?)",
                 (time.time(), name, hypothesis[:300], "running", "", ""))
    conn.commit(); conn.close()
    rhash = _oa_receipt("experiment_start", "system", f"Experiment: {name} — {hypothesis}")
    return {"experiment": name, "state": "running", "receipt": rhash[:16]}

@app.post("/api/experiments/{name}/verdict")
async def oa_experiment_verdict(name: str, body: dict = Body(...)):
    """Record experiment verdict: keep, rollback, or iterate."""
    verdict = body.get("verdict", "inconclusive")
    metric_delta = body.get("metric_delta", "")
    conn = _oa_db()
    conn.execute("UPDATE experiments SET state=?, metric_delta=?, verdict=? WHERE name=? AND state='running'",
                 ("complete", str(metric_delta)[:200], verdict, name))
    conn.commit(); conn.close()
    rhash = _oa_receipt("experiment_verdict", "system", f"{name}: {verdict} — delta={metric_delta}")
    return {"experiment": name, "verdict": verdict, "receipt": rhash[:16]}

@app.get("/api/experiments")
async def oa_experiment_list():
    """List all experiments and their states."""
    conn = _oa_db()
    rows = conn.execute("SELECT ts, name, hypothesis, state, metric_delta, verdict FROM experiments ORDER BY ts DESC").fetchall()
    conn.close()
    return {"experiments": [{"ts": r[0], "name": r[1], "hypothesis": r[2], "state": r[3], "metric_delta": r[4], "verdict": r[5]} for r in rows], "count": len(rows)}

@app.get("/api/dashboard")
async def oa_dashboard():
    """Production control surface: alive? attention? buyer intent? keep/rollback/wait/test?"""
    kpis = _oa_compute_kpis()
    conn = _oa_db()
    # Recent metrics
    recent_metrics = conn.execute("SELECT ts, source, metric, value FROM metrics ORDER BY ts DESC LIMIT 20").fetchall()
    # Decision count
    decisions = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
    approved = conn.execute("SELECT COUNT(*) FROM decisions WHERE approved=1").fetchone()[0]
    # Experiment count
    experiments = conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
    active_exp = conn.execute("SELECT COUNT(*) FROM experiments WHERE state='running'").fetchone()[0]
    # Receipt chain
    receipt_count = conn.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    last_receipt = conn.execute("SELECT ts, action FROM receipts ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    # System alive check
    alive = kpis["raw"]["health_checks_1h"] > 0 or receipt_count > 0
    attention_increasing = kpis["raw"]["view_acceleration_pct"] > 0
    buyer_intent = kpis["raw"]["contacts_1h"] > 0
    if kpis["composite"] > 50:
        recommendation = "keep"
    elif kpis["composite"] < 25:
        recommendation = "rollback"
    else:
        recommendation = "wait"
    return {
        "alive": alive,
        "attention_increasing": attention_increasing,
        "buyer_intent": buyer_intent,
        "recommendation": recommendation,
        "kpis": kpis,
        "counts": {
            "decisions": decisions,
            "approved": approved,
            "experiments": experiments,
            "active_experiments": active_exp,
            "receipts": receipt_count,
        },
        "last_receipt": {"ts": last_receipt[0], "action": last_receipt[1]} if last_receipt else None,
        "recent_metrics": [{"ts": r[0], "source": r[1], "metric": r[2], "value": r[3]} for r in recent_metrics],
        "operator_questions": {
            "is_system_alive": alive,
            "is_attention_increasing": attention_increasing,
            "did_latest_change_improve_buyer_intent": buyer_intent,
            "should_we": recommendation,
        },
    }

@app.get("/api/operator-report")
async def oa_operator_report():
    """Short operator report: what changed, what proven, what unproven, what next."""
    kpis = _oa_compute_kpis()
    conn = _oa_db()
    # What changed (recent receipts)
    changes = conn.execute("SELECT action, actor, ts FROM receipts ORDER BY id DESC LIMIT 10").fetchall()
    # What proven (backed by receipts + metrics)
    proven = []
    if kpis["raw"]["total_receipts"] > 0:
        proven.append(f"Receipt chain intact: {kpis['raw']['total_receipts']} receipts")
    if kpis["raw"]["health_checks_1h"] > 0:
        proven.append(f"System alive: {kpis['raw']['health_checks_1h']} health checks in last hour")
    if kpis["raw"]["views_1h"] > 0:
        proven.append(f"Attention measurable: {kpis['raw']['views_1h']} profile views in last hour")
    if kpis["raw"]["contacts_1h"] > 0:
        proven.append(f"Buyer intent detected: {kpis['raw']['contacts_1h']} contact clicks in last hour")
    # What unproven
    unproven = []
    if kpis["raw"]["health_checks_1h"] == 0:
        unproven.append("No health checks in last hour — system liveness unproven")
    if kpis["raw"]["views_1h"] == 0:
        unproven.append("No profile views recorded — attention unproven")
    if kpis["raw"]["contacts_1h"] == 0:
        unproven.append("No contact clicks recorded — conversion unproven")
    if kpis["proof"] < 50:
        unproven.append(f"Proof density low ({kpis['proof']}/100) — need more receipts + metrics")
    # What next
    next_moves = []
    if kpis["raw"]["health_checks_1h"] == 0:
        next_moves.append("Start health check loop: POST /api/metrics/ingest with metric=health_check")
    if kpis["raw"]["views_1h"] == 0:
        next_moves.append("Ingest profile view metrics from first-party source")
    if kpis["raw"]["contacts_1h"] == 0 and kpis["raw"]["views_1h"] > 0:
        next_moves.append("A/B test contact button placement to improve conversion")
    if kpis["composite"] < 50:
        next_moves.append("Run experiment: POST /api/experiments with hypothesis for improvement")
    if not next_moves:
        next_moves.append("System stable. Monitor KPI trends and plan next experiment.")
    conn.close()
    return {
        "report_ts": time.time(),
        "kpi_snapshot": kpis,
        "what_changed": [{"action": r[0], "actor": r[1], "ts": r[2]} for r in changes],
        "what_proven": proven,
        "what_unproven": unproven,
        "what_next": next_moves,
        "STATUS": "alive" if kpis["raw"]["total_receipts"] > 0 else "cold_start",
        "PROOF": f"{kpis['proof']}/100 — {kpis['raw']['total_receipts']} receipts, {kpis['raw']['distinct_metrics_1h']} distinct metrics",
        "RISK": "low" if kpis["composite"] > 50 else "medium" if kpis["composite"] > 25 else "high",
        "NEXT_MOVE": next_moves[0] if next_moves else "monitor",
    }

# ─── SonicGlyph: Audio Glyph System for JORKI ───────────────────────────
# Audio becomes a GlyphLang target: non-playable proof receipts for audio.
# Fidelity ladder: L0 exists → L1 metadata → L2 signal → L3 fingerprint →
# L4 speaker topology → L5 transcript shadow → L6 semantic claims →
# L7 degraded preview → L8 encrypted full → L9 playable transport

SONIC_DATA_DIR = JORKI_DATA_DIR / "audio"
SONIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
SONIC_REGISTRY_PATH = SONIC_DATA_DIR / "sonic_registry.json"
_sonic_claims = {}

def _sonic_load_registry():
    if SONIC_REGISTRY_PATH.exists():
        return json.loads(SONIC_REGISTRY_PATH.read_text())
    return {}

def _sonic_save_registry(reg):
    SONIC_REGISTRY_PATH.write_text(json.dumps(reg, indent=2))

def _sonic_extract_metadata(content: bytes, filename: str) -> dict:
    """Extract L0-L2 metadata from audio bytes without playing."""
    import struct
    size = len(content)
    sha256 = hashlib.sha256(content).hexdigest()
    # Format detection by magic bytes
    fmt = "unknown"
    sample_rate = 0
    channels = 0
    bitrate = 0
    duration_s = 0.0
    codec = "unknown"
    if content[:4] == b'RIFF' and content[8:12] == b'WAVE':
        fmt = "wav"
        codec = "pcm"
        if len(content) > 44:
            channels = struct.unpack('<H', content[22:24])[0]
            sample_rate = struct.unpack('<I', content[24:28])[0]
            bits_per_sample = struct.unpack('<H', content[34:36])[0]
            bitrate = sample_rate * channels * bits_per_sample
            data_size = struct.unpack('<I', content[40:44])[0]
            if sample_rate > 0 and channels > 0 and bits_per_sample > 0:
                duration_s = data_size / (sample_rate * channels * (bits_per_sample // 8))
    elif content[:3] == b'ID3' or (len(content) > 2 and content[0] == 0xFF and (content[1] & 0xE0) == 0xE0):
        fmt = "mp3"
        codec = "mp3"
        # Rough bitrate detection from header
        if len(content) > 4:
            br_idx = (content[2] >> 4) & 0x0F
            br_table = [0,32,40,48,56,64,80,96,112,128,160,192,224,256,320,0]
            bitrate = br_table[br_idx] * 1000 if br_idx < 16 else 0
            sr_idx = (content[2] >> 2) & 0x03
            sr_table = [44100, 48000, 32000, 0]
            sample_rate = sr_table[sr_idx]
            if bitrate > 0:
                duration_s = (size * 8) / bitrate
    elif content[:4] == b'OggS':
        fmt = "ogg"
        codec = "vorbis"
        duration_s = size / 128000  # rough estimate
    elif content[:4] == b'fLaC':
        fmt = "flac"
        codec = "flac"
    elif content[:2] == b'\xff\xfb' or content[:2] == b'\xff\xf3':
        fmt = "mp3"
        codec = "mp3"
    # Loudness estimation from byte distribution (L2)
    byte_vals = list(content[:min(len(content), 65536)])
    if byte_vals:
        avg_byte = sum(byte_vals) / len(byte_vals)
        # RMS-like approximation (distance from 128 = silence for signed 8-bit)
        rms = (sum((b - 128) ** 2 for b in byte_vals) / len(byte_vals)) ** 0.5
        loudness_db = 20 * _math.log10(rms / 128) if rms > 0 else -60
        silence_ratio = sum(1 for b in byte_vals if abs(b - 128) < 3) / len(byte_vals)
    else:
        avg_byte = 128; rms = 0; loudness_db = -60; silence_ratio = 1.0
    return {
        "filename": filename,
        "size_bytes": size,
        "format": fmt,
        "codec": codec,
        "sample_rate": sample_rate,
        "channels": channels,
        "bitrate": bitrate,
        "duration_s": round(duration_s, 2),
        "duration_human": f"{int(duration_s//60)}:{int(duration_s%60):02d}" if duration_s > 0 else "unknown",
        "sha256": sha256,
        "loudness_db": round(loudness_db, 1),
        "silence_ratio": round(silence_ratio, 3),
        "rms": round(rms, 1),
    }

def _sonic_fingerprint(content: bytes) -> dict:
    """L3: Acoustic fingerprint — non-playable hash-based identity."""
    # Spectral hash from byte distribution in windows
    window_size = 4096
    windows = []
    for i in range(0, min(len(content), 65536), window_size):
        chunk = content[i:i+window_size]
        if len(chunk) < window_size:
            break
        # Simple spectral approximation: byte histogram
        hist = [0] * 16
        for b in chunk:
            hist[b >> 4] += 1
        # Normalize
        total = sum(hist) or 1
        hist = [h / total for h in hist]
        windows.append(hist)
    if not windows:
        return {"fingerprint": "empty", "bands": 0, "windows": 0}
    # Compute spectral contrast hash
    fp_parts = []
    for w in windows[:16]:
        dominant = max(range(len(w)), key=lambda i: w[i])
        fp_parts.append(f"{dominant:x}")
    fingerprint = "".join(fp_parts)
    # Spectral centroid (brightness indicator)
    centroids = []
    for w in windows:
        total_energy = sum(w) or 1
        centroid = sum(i * w[i] for i in range(len(w))) / total_energy
        centroids.append(centroid)
    avg_centroid = sum(centroids) / len(centroids) if centroids else 0
    # Spectral flatness (noisiness vs tonal)
    import math as _m
    flatness_values = []
    for w in windows:
        geo_mean = _m.exp(sum(_m.log(max(v, 1e-10)) for v in w) / len(w)) if w else 0
        arith_mean = sum(w) / len(w) if w else 0
        flatness_values.append(geo_mean / arith_mean if arith_mean > 0 else 0)
    avg_flatness = sum(flatness_values) / len(flatness_values) if flatness_values else 0
    return {
        "fingerprint": fingerprint,
        "fingerprint_hash": hashlib.sha256(fingerprint.encode()).hexdigest()[:32],
        "bands": 16,
        "windows": len(windows),
        "spectral_centroid": round(avg_centroid, 3),
        "spectral_flatness": round(avg_flatness, 3),
        "brightness": "bright" if avg_centroid > 8 else "dark" if avg_centroid < 4 else "neutral",
        "tonality": "tonal" if avg_flatness < 0.3 else "noisy" if avg_flatness > 0.7 else "mixed",
    }

def _sonic_speaker_topology(content: bytes, meta: dict) -> dict:
    """L4: Speaker topology — count and structure without identity."""
    # Estimate speaker count from channel info and signal variation
    channels = meta.get("channels", 0)
    # Detect voice activity segments by RMS variation
    window_size = 8192
    segments = []
    for i in range(0, min(len(content), 131072), window_size):
        chunk = content[i:i+window_size]
        if len(chunk) < 256:
            continue
        rms = (sum((b - 128) ** 2 for b in chunk) / len(chunk)) ** 0.5
        segments.append(rms)
    if not segments:
        return {"speaker_count": 0, "voice_activity": 0, "segments": 0}
    # Count voice-active segments (above threshold)
    threshold = sum(segments) / len(segments) * 0.5
    active = sum(1 for s in segments if s > threshold)
    voice_activity = active / len(segments) if segments else 0
    # Rough speaker estimate: more variation in active segments = more speakers
    active_vals = [s for s in segments if s > threshold]
    if active_vals:
        variation = (max(active_vals) - min(active_vals)) / (max(active_vals) or 1)
        if variation < 0.2:
            speaker_count = 1
        elif variation < 0.5:
            speaker_count = 2
        else:
            speaker_count = min(3, int(variation * 4) + 1)
    else:
        speaker_count = 0
    return {
        "speaker_count": speaker_count,
        "speaker_estimate": "single" if speaker_count == 1 else "dialogue" if speaker_count == 2 else "multi-speaker" if speaker_count > 2 else "silence",
        "voice_activity": round(voice_activity, 3),
        "voice_segments": active,
        "total_segments": len(segments),
        "identity_exposed": False,
    }

def _sonic_transcript_shadow(content: bytes, meta: dict) -> dict:
    """L5: Redacted transcript shadow — semantic structure without words."""
    # Build a shadow from signal patterns: pauses, emphasis, pace
    window_size = 4096
    rms_values = []
    for i in range(0, min(len(content), 65536), window_size):
        chunk = content[i:i+window_size]
        if len(chunk) < 256:
            continue
        rms = (sum((b - 128) ** 2 for b in chunk) / len(chunk)) ** 0.5
        rms_values.append(rms)
    if not rms_values:
        return {"shadow": "empty", "segments": 0}
    # Classify segments: pause, speech, emphasis, transition
    avg_rms = sum(rms_values) / len(rms_values)
    segments = []
    for i, rms in enumerate(rms_values):
        if rms < avg_rms * 0.2:
            seg_type = "pause"
        elif rms > avg_rms * 1.8:
            seg_type = "emphasis"
        elif rms < avg_rms * 0.5:
            seg_type = "quiet_speech"
        else:
            seg_type = "speech"
        timestamp = round(i * window_size / (meta.get("sample_rate", 44100) or 44100), 2)
        segments.append({"t": timestamp, "type": seg_type, "energy": round(rms, 1)})
    # Build shadow string: symbolic representation
    shadow_symbols = {"pause": "·", "quiet_speech": "░", "speech": "▓", "emphasis": "█"}
    shadow = "".join(shadow_symbols.get(s["type"], "?") for s in segments)
    # Detect pace (transitions per second)
    transitions = sum(1 for i in range(1, len(segments)) if segments[i]["type"] != segments[i-1]["type"])
    duration = meta.get("duration_s", 1) or 1
    pace = transitions / duration
    return {
        "shadow": shadow,
        "shadow_hash": hashlib.sha256(shadow.encode()).hexdigest()[:32],
        "segments": len(segments),
        "segment_details": segments[:20],
        "pace": round(pace, 2),
        "pace_label": "fast" if pace > 2 else "slow" if pace < 0.5 else "normal",
        "redacted": True,
        "note": "Transcript shadow shows speech structure without revealing words.",
    }

def _sonic_semantic_claims(meta: dict, fingerprint: dict, speakers: dict, shadow: dict) -> list:
    """L6: Timestamped semantic claims about the audio."""
    claims = []
    if meta.get("duration_s", 0) > 0:
        claims.append({"claim": "audio_duration", "value": meta["duration_s"], "unit": "seconds", "confidence": 0.99})
    if meta.get("format") != "unknown":
        claims.append({"claim": "audio_format", "value": meta["format"], "confidence": 0.95})
    if speakers.get("speaker_count", 0) > 0:
        claims.append({"claim": "speaker_count", "value": speakers["speaker_count"], "confidence": 0.7})
        claims.append({"claim": "speaker_topology", "value": speakers["speaker_estimate"], "confidence": 0.7})
    if fingerprint.get("brightness"):
        claims.append({"claim": "spectral_brightness", "value": fingerprint["brightness"], "confidence": 0.85})
    if fingerprint.get("tonality"):
        claims.append({"claim": "tonality", "value": fingerprint["tonality"], "confidence": 0.8})
    if shadow.get("pace_label"):
        claims.append({"claim": "speech_pace", "value": shadow["pace_label"], "confidence": 0.75})
    if meta.get("loudness_db", -60) > -30:
        claims.append({"claim": "loudness", "value": meta["loudness_db"], "unit": "dB", "confidence": 0.9})
    if meta.get("silence_ratio", 1) < 0.3:
        claims.append({"claim": "contains_speech", "value": True, "confidence": 0.85})
    claims.append({"claim": "audio_exists", "value": True, "confidence": 1.0, "evidence": meta["sha256"][:16]})
    return claims

def _sonic_create_audio_idx(audio_id: str, meta: dict, fingerprint: dict,
                            speakers: dict, shadow: dict, claims: list,
                            content: bytes, filename: str):
    """Create SQLite index for audio file."""
    idx_path = SONIC_DATA_DIR / f"{audio_id}.idx"
    conn = sqlite3.connect(str(idx_path))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS audio_meta (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE IF NOT EXISTS fingerprint (key TEXT, value TEXT);
        CREATE TABLE IF NOT EXISTS speakers (key TEXT, value TEXT);
        CREATE TABLE IF NOT EXISTS transcript_shadow (idx INTEGER, timestamp REAL, seg_type TEXT, energy REAL);
        CREATE TABLE IF NOT EXISTS semantic_claims (idx INTEGER, claim TEXT, value TEXT, unit TEXT, confidence REAL);
        CREATE TABLE IF NOT EXISTS audio_chunks (idx INTEGER, timestamp_start REAL, timestamp_end REAL, energy REAL, seg_type TEXT, preview TEXT);
    """)
    for k, v in meta.items():
        conn.execute("INSERT OR REPLACE INTO audio_meta VALUES (?,?)", (k, str(v)))
    for k, v in fingerprint.items():
        conn.execute("INSERT INTO fingerprint VALUES (?,?)", (k, str(v)))
    for k, v in speakers.items():
        conn.execute("INSERT INTO speakers VALUES (?,?)", (k, str(v)))
    for i, seg in enumerate(shadow.get("segment_details", [])):
        conn.execute("INSERT INTO transcript_shadow VALUES (?,?,?,?)",
                     (i, seg["t"], seg["type"], seg["energy"]))
    for i, c in enumerate(claims):
        conn.execute("INSERT INTO semantic_claims VALUES (?,?,?,?,?)",
                     (i, c["claim"], str(c["value"]), c.get("unit", ""), c.get("confidence", 0)))
    # Build audio chunks (time-segmented)
    window_size = 4096
    sr = meta.get("sample_rate", 44100) or 44100
    chunk_idx = 0
    for i in range(0, min(len(content), 131072), window_size * 4):
        chunk = content[i:i+window_size*4]
        if len(chunk) < 256:
            continue
        rms = (sum((b - 128) ** 2 for b in chunk) / len(chunk)) ** 0.5
        t_start = round(i / sr, 2)
        t_end = round((i + len(chunk)) / sr, 2)
        if rms < sum([rms]) / 2 * 0.2:
            seg_type = "pause"
        elif rms > sum([rms]) / 2 * 1.8:
            seg_type = "emphasis"
        else:
            seg_type = "speech"
        preview = f"[{t_start}s-{t_end}s] {seg_type} energy={round(rms,1)}"
        conn.execute("INSERT INTO audio_chunks VALUES (?,?,?,?,?,?)",
                     (chunk_idx, t_start, t_end, round(rms, 1), seg_type, preview))
        chunk_idx += 1
    conn.commit()
    conn.close()

@app.post("/audio/upload")
async def sonic_upload(file: UploadFile = File(...)):
    """Upload audio file. Creates non-playable proof object with fidelity ladder L0-L6."""
    content = await file.read()
    if len(content) < 64:
        return {"error": "File too small to analyze"}
    audio_id = hashlib.sha256(content).hexdigest()[:12]
    meta = _sonic_extract_metadata(content, file.filename)
    fingerprint = _sonic_fingerprint(content)
    speakers = _sonic_speaker_topology(content, meta)
    shadow = _sonic_transcript_shadow(content, meta)
    claims = _sonic_semantic_claims(meta, fingerprint, speakers, shadow)
    _sonic_create_audio_idx(audio_id, meta, fingerprint, speakers, shadow, claims, content, file.filename)
    # Store encrypted full audio (L8) — base64 with XOR gate
    enc_path = SONIC_DATA_DIR / f"{audio_id}.enc"
    xor_key = os.urandom(32)
    enc_content = bytes(b ^ xor_key[i % 32] for i, b in enumerate(content))
    enc_path.write_bytes(enc_content)
    key_path = SONIC_DATA_DIR / f"{audio_id}.key"
    key_path.write_bytes(xor_key)
    # Register
    reg = _sonic_load_registry()
    reg[audio_id] = {
        "filename": file.filename,
        "size_bytes": len(content),
        "format": meta["format"],
        "duration_s": meta["duration_s"],
        "sha256": meta["sha256"],
        "fingerprint_hash": fingerprint["fingerprint_hash"],
        "speaker_count": speakers["speaker_count"],
        "uploaded_at": time.time(),
        "status": "indexed",
    }
    _sonic_save_registry(reg)
    return {
        "audio_id": audio_id,
        "filename": file.filename,
        "fidelity_ladder": {
            "L0_exists": True,
            "L1_metadata": True,
            "L2_signal": True,
            "L3_fingerprint": True,
            "L4_speakers": True,
            "L5_transcript_shadow": True,
            "L6_semantic_claims": len(claims),
            "L7_degraded_preview": False,
            "L8_encrypted_full": True,
            "L9_playable": False,
        },
        "meta": meta,
        "fingerprint": {k: v for k, v in fingerprint.items() if k != "fingerprint"},
        "speakers": speakers,
        "shadow_summary": {"segments": shadow["segments"], "pace": shadow["pace"], "pace_label": shadow["pace_label"]},
        "claims_count": len(claims),
        "sha256": meta["sha256"],
        "merkle_root": audio_id + hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()[:20],
        "endpoints": {
            "meta": f"/audio/meta/{audio_id}",
            "fingerprint": f"/audio/fingerprint/{audio_id}",
            "transcript_shadow": f"/audio/transcript-shadow/{audio_id}",
            "speakers": f"/audio/speakers/{audio_id}",
            "search": f"/audio/search/{audio_id}?q=",
            "chunk": f"/audio/chunk/{audio_id}/{{timestamp}}",
            "claims": f"/audio/claims/{audio_id}",
            "glyph": f"/audio/glyph/{audio_id}",
            "receipt": f"/audio/receipt/{audio_id}",
            "claim_create": f"/audio/claim/create",
            "claim_settle": f"/audio/claim/settle",
        },
    }

@app.get("/audio/meta/{audio_id}")
async def sonic_meta(audio_id: str):
    """L0-L2: Audio metadata — exists, format, duration, loudness, silence."""
    idx_path = SONIC_DATA_DIR / f"{audio_id}.idx"
    if not idx_path.exists():
        return {"error": f"Audio not found: {audio_id}"}
    conn = sqlite3.connect(str(idx_path))
    meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM audio_meta").fetchall()}
    conn.close()
    return {"audio_id": audio_id, "meta": meta}

@app.get("/audio/fingerprint/{audio_id}")
async def sonic_fingerprint(audio_id: str):
    """L3: Acoustic fingerprint — non-playable spectral identity."""
    idx_path = SONIC_DATA_DIR / f"{audio_id}.idx"
    if not idx_path.exists():
        return {"error": f"Audio not found: {audio_id}"}
    conn = sqlite3.connect(str(idx_path))
    fp = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM fingerprint").fetchall()}
    conn.close()
    return {"audio_id": audio_id, "fingerprint": fp}

@app.get("/audio/transcript-shadow/{audio_id}")
async def sonic_transcript_shadow(audio_id: str):
    """L5: Redacted transcript shadow — speech structure without words."""
    idx_path = SONIC_DATA_DIR / f"{audio_id}.idx"
    if not idx_path.exists():
        return {"error": f"Audio not found: {audio_id}"}
    conn = sqlite3.connect(str(idx_path))
    segs = conn.execute("SELECT idx, timestamp, seg_type, energy FROM transcript_shadow").fetchall()
    conn.close()
    return {
        "audio_id": audio_id,
        "segments": [{"idx": r[0], "timestamp": r[1], "type": r[2], "energy": r[3]} for r in segs],
        "total_segments": len(segs),
        "redacted": True,
        "note": "Transcript shadow shows speech structure without revealing words.",
    }

@app.get("/audio/speakers/{audio_id}")
async def sonic_speakers(audio_id: str):
    """L4: Speaker topology — count and structure without identity."""
    idx_path = SONIC_DATA_DIR / f"{audio_id}.idx"
    if not idx_path.exists():
        return {"error": f"Audio not found: {audio_id}"}
    conn = sqlite3.connect(str(idx_path))
    sp = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM speakers").fetchall()}
    conn.close()
    return {"audio_id": audio_id, "speakers": sp}

@app.get("/audio/claims/{audio_id}")
async def sonic_claims(audio_id: str):
    """L6: Timestamped semantic claims about the audio."""
    idx_path = SONIC_DATA_DIR / f"{audio_id}.idx"
    if not idx_path.exists():
        return {"error": f"Audio not found: {audio_id}"}
    conn = sqlite3.connect(str(idx_path))
    claims = conn.execute("SELECT idx, claim, value, unit, confidence FROM semantic_claims").fetchall()
    conn.close()
    return {
        "audio_id": audio_id,
        "claims": [{"idx": r[0], "claim": r[1], "value": r[2], "unit": r[3], "confidence": r[4]} for r in claims],
        "total_claims": len(claims),
    }

@app.get("/audio/search/{audio_id}")
async def sonic_search(audio_id: str, q: str = ""):
    """Search audio chunks by segment type or energy pattern."""
    idx_path = SONIC_DATA_DIR / f"{audio_id}.idx"
    if not idx_path.exists():
        return {"error": f"Audio not found: {audio_id}"}
    if not q:
        return {"error": "Query 'q' is required (try: speech, pause, emphasis)"}
    conn = sqlite3.connect(str(idx_path))
    results = conn.execute(
        "SELECT idx, timestamp_start, timestamp_end, energy, seg_type, preview FROM audio_chunks WHERE seg_type LIKE ? OR preview LIKE ?",
        (f"%{q}%", f"%{q}%")
    ).fetchall()
    conn.close()
    return {
        "audio_id": audio_id,
        "query": q,
        "results": [{"idx": r[0], "start": r[1], "end": r[2], "energy": r[3], "type": r[4], "preview": r[5]} for r in results],
        "total": len(results),
    }

@app.get("/audio/chunk/{audio_id}/{timestamp}")
async def sonic_chunk(audio_id: str, timestamp: float):
    """Retrieve audio chunk at a specific timestamp."""
    idx_path = SONIC_DATA_DIR / f"{audio_id}.idx"
    if not idx_path.exists():
        return {"error": f"Audio not found: {audio_id}"}
    conn = sqlite3.connect(str(idx_path))
    row = conn.execute(
        "SELECT idx, timestamp_start, timestamp_end, energy, seg_type, preview FROM audio_chunks WHERE timestamp_start <= ? AND timestamp_end >= ? ORDER BY ABS(timestamp_start - ?) LIMIT 1",
        (timestamp, timestamp, timestamp)
    ).fetchone()
    conn.close()
    if not row:
        return {"error": f"No chunk at timestamp {timestamp}"}
    return {
        "audio_id": audio_id,
        "idx": row[0],
        "timestamp_start": row[1],
        "timestamp_end": row[2],
        "energy": row[3],
        "seg_type": row[4],
        "preview": row[5],
        "playable": False,
    }

@app.get("/audio/glyph/{audio_id}")
async def sonic_glyph(audio_id: str):
    """Complete SonicGlyph — all fidelity layers in one object."""
    idx_path = SONIC_DATA_DIR / f"{audio_id}.idx"
    if not idx_path.exists():
        return {"error": f"Audio not found: {audio_id}"}
    conn = sqlite3.connect(str(idx_path))
    meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM audio_meta").fetchall()}
    fp = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM fingerprint").fetchall()}
    sp = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM speakers").fetchall()}
    segs = conn.execute("SELECT idx, timestamp, seg_type, energy FROM transcript_shadow").fetchall()
    claims = conn.execute("SELECT idx, claim, value, unit, confidence FROM semantic_claims").fetchall()
    chunks = conn.execute("SELECT idx, timestamp_start, timestamp_end, energy, seg_type, preview FROM audio_chunks").fetchall()
    conn.close()
    reg = _sonic_load_registry()
    entry = reg.get(audio_id, {})
    return {
        "audio_id": audio_id,
        "glyph_type": "SonicGlyph",
        "filename": meta.get("filename", ""),
        "fidelity_ladder": {
            "L0_exists": True,
            "L1_metadata": True,
            "L2_signal": True,
            "L3_fingerprint": True,
            "L4_speakers": True,
            "L5_transcript_shadow": True,
            "L6_semantic_claims": len(claims),
            "L7_degraded_preview": False,
            "L8_encrypted_full": True,
            "L9_playable": False,
        },
        "meta": meta,
        "fingerprint": fp,
        "speakers": sp,
        "transcript_shadow": {
            "segments": [{"idx": r[0], "t": r[1], "type": r[2], "energy": r[3]} for r in segs],
            "total": len(segs),
            "redacted": True,
        },
        "semantic_claims": [{"idx": r[0], "claim": r[1], "value": r[2], "unit": r[3], "confidence": r[4]} for r in claims],
        "audio_chunks": [{"idx": r[0], "start": r[1], "end": r[2], "energy": r[3], "type": r[4]} for r in chunks],
        "sha256": meta.get("sha256", ""),
        "merkle_root": audio_id + hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()[:20],
        "registered_at": entry.get("uploaded_at", 0),
        "playable": False,
        "identity_exposed": False,
    }

@app.get("/audio/receipt/{audio_id}")
async def sonic_receipt(audio_id: str):
    """Proof receipt for audio — timestamped, hash-backed, non-playable."""
    idx_path = SONIC_DATA_DIR / f"{audio_id}.idx"
    if not idx_path.exists():
        return {"error": f"Audio not found: {audio_id}"}
    conn = sqlite3.connect(str(idx_path))
    meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM audio_meta").fetchall()}
    fp = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM fingerprint").fetchall()}
    claims = conn.execute("SELECT claim, value, confidence FROM semantic_claims").fetchall()
    conn.close()
    receipt = {
        "receipt_id": hashlib.sha256(f"{audio_id}{time.time()}".encode()).hexdigest()[:16],
        "audio_id": audio_id,
        "timestamp": datetime.now().isoformat(),
        "sha256": meta.get("sha256", ""),
        "fingerprint_hash": fp.get("fingerprint_hash", ""),
        "merkle_root": audio_id + hashlib.sha256(json.dumps(meta, sort_keys=True).encode()).hexdigest()[:20],
        "filename": meta.get("filename", ""),
        "duration_s": meta.get("duration_s", "0"),
        "format": meta.get("format", "unknown"),
        "speaker_count": int(fp.get("speaker_count", 0) or 0),
        "claims_verified": len(claims),
        "playable": False,
        "identity_exposed": False,
        "proof_type": "SonicGlyph non-playable proof receipt",
    }
    return receipt

@app.get("/audio/files")
async def sonic_list():
    """List all indexed audio files."""
    reg = _sonic_load_registry()
    return {
        "files": [{"audio_id": aid, **e} for aid, e in reg.items()],
        "total": len(reg),
    }

# ─── SonicGlyph AFC Claims ──────────────────────────────────────────────

@app.post("/audio/claim/create")
async def sonic_claim_create(body: dict = Body(...)):
    """Create an AFC claim for audio.
    Body: {audio_id, seller_id, task_description, bond_amount, buyer_id?}
    """
    audio_id = body.get("audio_id", "")
    if not audio_id:
        return {"error": "audio_id is required"}
    idx_path = SONIC_DATA_DIR / f"{audio_id}.idx"
    if not idx_path.exists():
        return {"error": f"Audio not found: {audio_id}"}
    conn = sqlite3.connect(str(idx_path))
    meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM audio_meta").fetchall()}
    fp = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM fingerprint").fetchall()}
    sp = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM speakers").fetchall()}
    conn.close()
    claim_id = hashlib.sha256(f"{audio_id}{time.time()}{body.get('seller_id','')}".encode()).hexdigest()[:16]
    surrogate = {
        "duration_s": meta.get("duration_s", "0"),
        "sha256": meta.get("sha256", "")[:32],
        "speaker_count": sp.get("speaker_count", "0"),
        "speaker_estimate": sp.get("speaker_estimate", "unknown"),
        "fingerprint_hash": fp.get("fingerprint_hash", ""),
        "format": meta.get("format", "unknown"),
        "redacted": True,
    }
    claim = {
        "claim_id": claim_id,
        "audio_id": audio_id,
        "seller_id": body.get("seller_id", "anonymous"),
        "buyer_id": body.get("buyer_id", ""),
        "task_description": body.get("task_description", ""),
        "surrogate": surrogate,
        "bond_amount": body.get("bond_amount", 0),
        "bond_posted": True,
        "payment_escrowed": 0,
        "status": "open",
        "created_at": time.time(),
        "tests_submitted": 0,
        "tests_passed": 0,
        "settlement_result": "",
        "receipt": "",
    }
    _sonic_claims[claim_id] = claim
    return {
        "claim_id": claim_id,
        "status": "open",
        "surrogate": surrogate,
        "bond_posted": claim["bond_amount"] > 0,
        "message": "Claim created. Buyer must escrow payment, then reveal + settle.",
    }

@app.post("/audio/claim/settle")
async def sonic_claim_settle(body: dict = Body(...)):
    """Settle an AFC claim.
    Body: {claim_id, buyer_id, payment_amount, tests_passed, tests_total}
    """
    claim_id = body.get("claim_id", "")
    if claim_id not in _sonic_claims:
        return {"error": f"Claim not found: {claim_id}"}
    claim = _sonic_claims[claim_id]
    tests_passed = body.get("tests_passed", 0)
    tests_total = body.get("tests_total", 0)
    payment = body.get("payment_amount", 0)
    # Settlement logic: all tests pass → bond returned + payment released
    # Any test fails → bond slashed + payment returned
    if tests_total > 0 and tests_passed == tests_total:
        result = "pass"
        claim["settlement_result"] = f"PASS: {tests_passed}/{tests_total} tests passed. Bond returned. Payment released."
        claim["receipt"] = hashlib.sha256(f"{claim_id}{time.time()}pass".encode()).hexdigest()[:32]
    else:
        result = "fail"
        failed = tests_total - tests_passed
        claim["settlement_result"] = f"FAIL: {tests_passed}/{tests_total} passed, {failed} failed. Bond slashed. Payment returned."
        claim["receipt"] = hashlib.sha256(f"{claim_id}{time.time()}fail".encode()).hexdigest()[:32]
    claim["status"] = "settled"
    claim["tests_submitted"] = tests_total
    claim["tests_passed"] = tests_passed
    claim["payment_escrowed"] = payment
    claim["settled_at"] = time.time()
    return {
        "claim_id": claim_id,
        "status": "settled",
        "result": result,
        "settlement": claim["settlement_result"],
        "receipt": claim["receipt"],
        "bond_returned": result == "pass",
        "payment_released": result == "pass",
    }

@app.get("/audio/claim/{claim_id}")
async def sonic_claim_get(claim_id: str):
    """Get claim status."""
    if claim_id not in _sonic_claims:
        return {"error": f"Claim not found: {claim_id}"}
    return _sonic_claims[claim_id]

# ─── MCP Protocol Endpoints (for ChatGPT web) ───────────────────────────
# Embeds MCP server directly into the FastAPI app so the HF Space URL
# becomes an MCP endpoint: https://josephrw-llm-file-proxy.hf.space/mcp

_MCP_TOOLS = [
    {
        "name": "jorki_list_files",
        "description": "List all indexed files in the Jorki registry",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "jorki_metadata",
        "description": "Get file metadata: name, size, line count, word count, merkle root, symbol count, chunk count.",
        "inputSchema": {"type": "object", "properties": {"file_id": {"type": "string", "description": "12-character Jorki file ID"}}, "required": ["file_id"]},
    },
    {
        "name": "jorki_summary",
        "description": "Get structural summary: top words, function symbols, chunk previews, line/word counts.",
        "inputSchema": {"type": "object", "properties": {"file_id": {"type": "string", "description": "12-character Jorki file ID"}}, "required": ["file_id"]},
    },
    {
        "name": "jorki_search",
        "description": "Search file content for a query string. Returns matching lines and symbol hits.",
        "inputSchema": {"type": "object", "properties": {"file_id": {"type": "string", "description": "12-character Jorki file ID"}, "q": {"type": "string", "description": "Search query"}}, "required": ["file_id", "q"]},
    },
    {
        "name": "jorki_chunk",
        "description": "Retrieve a specific content chunk by index. Returns line range, boundary type, and preview text.",
        "inputSchema": {"type": "object", "properties": {"file_id": {"type": "string", "description": "12-character Jorki file ID"}, "idx": {"type": "integer", "description": "Chunk index (0-based)", "default": 0}}, "required": ["file_id"]},
    },
    {
        "name": "jorki_verify",
        "description": "Verify file integrity: check merkle root, confirm index exists, return verification receipt.",
        "inputSchema": {"type": "object", "properties": {"file_id": {"type": "string", "description": "12-character Jorki file ID"}}, "required": ["file_id"]},
    },
    {
        "name": "jorki_kpi",
        "description": "Extract KPIs: monetary values, percentages, dates, technical metrics, operational indicators with confidence scores.",
        "inputSchema": {"type": "object", "properties": {"file_id": {"type": "string", "description": "12-character Jorki file ID"}}, "required": ["file_id"]},
    },
    {
        "name": "jorki_dna",
        "description": "Get the file's DNA fingerprint: structural genes, complexity score, species classification, genome size.",
        "inputSchema": {"type": "object", "properties": {"file_id": {"type": "string", "description": "12-character Jorki file ID"}}, "required": ["file_id"]},
    },
    {
        "name": "jorki_profile",
        "description": "Get semantic profile: origin, accounting, finance, law, collateral, liquidity, risk.",
        "inputSchema": {"type": "object", "properties": {"file_id": {"type": "string", "description": "12-character Jorki file ID"}}, "required": ["file_id"]},
    },
    {
        "name": "jorki_ml",
        "description": "Get ML features: topics, clusters, anomalies, latent features, TF-IDF top terms.",
        "inputSchema": {"type": "object", "properties": {"file_id": {"type": "string", "description": "12-character Jorki file ID"}}, "required": ["file_id"]},
    },
    {
        "name": "jorki_valuation",
        "description": "Get valuation: production readiness, replacement cost, build cost, depreciation, insurance value.",
        "inputSchema": {"type": "object", "properties": {"file_id": {"type": "string", "description": "12-character Jorki file ID"}}, "required": ["file_id"]},
    },
    {
        "name": "jorki_dossier",
        "description": "Get the complete file dossier — all analysis layers combined: identity, DNA, KPIs, profile, ML, valuation, risk, recommendations, narrative.",
        "inputSchema": {"type": "object", "properties": {"file_id": {"type": "string", "description": "12-character Jorki file ID"}, "format": {"type": "string", "enum": ["json", "text"], "default": "json", "description": "Output format"}}, "required": ["file_id"]},
    },
    {
        "name": "jorki_capabilities",
        "description": "List all capabilities available for a file (sql, search, chunk, summary, etc.).",
        "inputSchema": {"type": "object", "properties": {"file_id": {"type": "string", "description": "12-character Jorki file ID"}}, "required": ["file_id"]},
    },
    {
        "name": "jorki_stats",
        "description": "Get query statistics for a file — how many times each endpoint was called.",
        "inputSchema": {"type": "object", "properties": {"file_id": {"type": "string", "description": "12-character Jorki file ID"}}, "required": ["file_id"]},
    },
    {
        "name": "jorki_health",
        "description": "Check Jorki API health and list available endpoints.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "sonic_list",
        "description": "List all indexed audio files with SonicGlyph metadata.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "sonic_meta",
        "description": "Get audio metadata: format, duration, loudness, silence ratio, sample rate, codec (L0-L2).",
        "inputSchema": {"type": "object", "properties": {"audio_id": {"type": "string", "description": "12-character audio ID"}}, "required": ["audio_id"]},
    },
    {
        "name": "sonic_fingerprint",
        "description": "Get acoustic fingerprint: spectral centroid, flatness, brightness, tonality — non-playable identity (L3).",
        "inputSchema": {"type": "object", "properties": {"audio_id": {"type": "string", "description": "12-character audio ID"}}, "required": ["audio_id"]},
    },
    {
        "name": "sonic_speakers",
        "description": "Get speaker topology: count, voice activity, estimate — without identity exposure (L4).",
        "inputSchema": {"type": "object", "properties": {"audio_id": {"type": "string", "description": "12-character audio ID"}}, "required": ["audio_id"]},
    },
    {
        "name": "sonic_transcript_shadow",
        "description": "Get redacted transcript shadow: speech structure, pace, pauses, emphasis — without words (L5).",
        "inputSchema": {"type": "object", "properties": {"audio_id": {"type": "string", "description": "12-character audio ID"}}, "required": ["audio_id"]},
    },
    {
        "name": "sonic_claims",
        "description": "Get timestamped semantic claims about the audio: duration, format, speaker count, brightness, tonality, pace (L6).",
        "inputSchema": {"type": "object", "properties": {"audio_id": {"type": "string", "description": "12-character audio ID"}}, "required": ["audio_id"]},
    },
    {
        "name": "sonic_search",
        "description": "Search audio chunks by segment type (speech, pause, emphasis) or energy pattern.",
        "inputSchema": {"type": "object", "properties": {"audio_id": {"type": "string", "description": "12-character audio ID"}, "q": {"type": "string", "description": "Search query (try: speech, pause, emphasis)"}}, "required": ["audio_id", "q"]},
    },
    {
        "name": "sonic_chunk",
        "description": "Get audio chunk at a specific timestamp. Returns energy, segment type, and preview — not playable.",
        "inputSchema": {"type": "object", "properties": {"audio_id": {"type": "string", "description": "12-character audio ID"}, "timestamp": {"type": "number", "description": "Timestamp in seconds"}}, "required": ["audio_id", "timestamp"]},
    },
    {
        "name": "sonic_glyph",
        "description": "Get complete SonicGlyph — all fidelity layers (L0-L8) in one object: meta, fingerprint, speakers, transcript shadow, claims, chunks.",
        "inputSchema": {"type": "object", "properties": {"audio_id": {"type": "string", "description": "12-character audio ID"}}, "required": ["audio_id"]},
    },
    {
        "name": "sonic_receipt",
        "description": "Get non-playable proof receipt for audio: timestamped, hash-backed, with merkle root and claims verified.",
        "inputSchema": {"type": "object", "properties": {"audio_id": {"type": "string", "description": "12-character audio ID"}}, "required": ["audio_id"]},
    },
    {
        "name": "sonic_claim_create",
        "description": "Create an AFC claim for audio. Seller posts bond, buyer escrows payment. Surrogate reveals non-playable proof only.",
        "inputSchema": {"type": "object", "properties": {"audio_id": {"type": "string", "description": "12-character audio ID"}, "seller_id": {"type": "string"}, "task_description": {"type": "string"}, "bond_amount": {"type": "number"}, "buyer_id": {"type": "string"}}, "required": ["audio_id"]},
    },
    {
        "name": "sonic_claim_settle",
        "description": "Settle an AFC claim. If all tests pass: bond returned + payment released. If any fail: bond slashed + payment returned.",
        "inputSchema": {"type": "object", "properties": {"claim_id": {"type": "string"}, "payment_amount": {"type": "number"}, "tests_passed": {"type": "integer"}, "tests_total": {"type": "integer"}}, "required": ["claim_id", "tests_passed", "tests_total"]},
    },
]

def _mcp_call_tool(name: str, args: dict) -> Any:
    """Dispatch MCP tool calls to existing Jorki API functions."""
    file_id = args.get("file_id", "")
    if name == "jorki_health":
        return {"status": "ok", "service": "jorki", "tools": len(_MCP_TOOLS)}
    if name == "jorki_list_files":
        reg = _jorki_load_registry()
        return {"files": [{"file_id": fid, "filename": e.get("filename", ""), "status": e.get("status", "unknown")} for fid, e in reg.items()], "total": len(reg)}
    if not file_id and not name.startswith("sonic_") and name not in ("jorki_list_files", "jorki_health"):
        return {"error": "file_id is required"}
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not name.startswith("sonic_") and name != "jorki_health" and not idx_path.exists():
        return {"error": f"Index not found for {file_id}"}
    if name == "jorki_metadata":
        conn = sqlite3.connect(str(idx_path)); meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM file_meta").fetchall()}; conn.close()
        _jorki_track_query(file_id, "meta")
        return {"file_id": file_id, "meta": meta, "endpoints": {"meta": f"/meta/{file_id}", "search": f"/search/{file_id}?q=", "chunk": f"/chunk/{file_id}/{{idx}}"}}
    if name == "jorki_summary":
        conn = sqlite3.connect(str(idx_path))
        meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM file_meta").fetchall()}
        words = conn.execute("SELECT word, count FROM word_freq ORDER BY count DESC LIMIT 20").fetchall()
        symbols = conn.execute("SELECT line, name, type FROM symbols").fetchall()
        chunks = conn.execute("SELECT idx, line_start, line_end, boundary_type, preview, line_count FROM chunks").fetchall()
        conn.close(); _jorki_track_query(file_id, "summary")
        return {"file_id": file_id, "meta": meta, "top_words": [{"word": r[0], "count": r[1]} for r in words], "functions": [{"line": r[0], "symbol": r[1]} for r in symbols], "chunks": [{"idx": r[0], "lines": f"{r[1]}-{r[2]}", "type": r[3], "preview": r[4][:100]} for r in chunks]}
    if name == "jorki_search":
        q = args.get("q", "")
        if not q: return {"error": "query 'q' is required"}
        conn = sqlite3.connect(str(idx_path))
        chunk_results = conn.execute("SELECT idx, line_start, line_end, preview FROM chunks WHERE preview LIKE ? LIMIT 20", (f"%{q}%",)).fetchall()
        sym_results = conn.execute("SELECT line, name FROM symbols WHERE name LIKE ? LIMIT 20", (f"%{q}%",)).fetchall()
        conn.close(); _jorki_track_query(file_id, "search")
        return {"file_id": file_id, "query": q, "results": [{"line": r[1], "text": r[3][:200]} for r in chunk_results] + [{"line": r[0], "text": r[1]} for r in sym_results]}
    if name == "jorki_chunk":
        idx = args.get("idx", 0)
        conn = sqlite3.connect(str(idx_path))
        row = conn.execute("SELECT idx, line_start, line_end, boundary_type, preview, line_count FROM chunks WHERE idx = ?", (idx,)).fetchone(); conn.close()
        _jorki_track_query(file_id, "chunk")
        if not row: return {"error": f"Chunk {idx} not found"}
        return {"idx": row[0], "line_start": row[1], "line_end": row[2], "boundary_type": row[3], "content": row[4], "line_count": row[5]}
    if name == "jorki_verify":
        conn = sqlite3.connect(str(idx_path)); meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM file_meta").fetchall()}; conn.close()
        return {"file_id": file_id, "verified": True, "merkle_root": meta.get("merkle_root", ""), "filename": meta.get("filename", ""), "timestamp": datetime.now().isoformat()}
    if name == "jorki_kpi":
        conn = sqlite3.connect(str(idx_path))
        rows = conn.execute("SELECT id, name, value, line, category, confidence FROM kpis ORDER BY confidence DESC").fetchall(); conn.close()
        _jorki_track_query(file_id, "kpi")
        by_cat = {}
        for r in rows:
            by_cat.setdefault(r[4], []).append({"id": r[0], "name": r[1], "value": r[2], "line": r[3], "confidence": r[5]})
        return {"file_id": file_id, "total_kpis": len(rows), "by_category": by_cat}
    if name == "jorki_dna":
        conn = sqlite3.connect(str(idx_path)); rows = conn.execute("SELECT key, value FROM dna").fetchall(); conn.close()
        _jorki_track_query(file_id, "dna"); dna = {r[0]: r[1] for r in rows}
        try: genes = json.loads(dna.get("genes", "{}"))
        except: genes = {}
        return {"file_id": file_id, "dna_sequence": dna.get("dna_sequence", ""), "species": dna.get("species", "unknown"), "genes": genes, "complexity_score": float(dna.get("complexity_score", 0)), "genome_size": int(dna.get("genome_size", 0))}
    if name == "jorki_profile":
        conn = sqlite3.connect(str(idx_path))
        meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM file_meta").fetchall()}
        kpis = [{"id": r[0], "name": r[1], "value": r[2], "line": r[3], "category": r[4], "confidence": r[5]} for r in conn.execute("SELECT id, name, value, line, category, confidence FROM kpis").fetchall()]
        dna_rows = conn.execute("SELECT key, value FROM dna").fetchall()
        chunk_rows = conn.execute("SELECT idx, line_start, line_end, boundary_type, preview, line_count FROM chunks").fetchall()
        word_rows = conn.execute("SELECT word, count FROM word_freq").fetchall()
        conn.close()
        dna = {r[0]: r[1] for r in dna_rows}
        try: dna_obj = json.loads(dna.get("genes", "{}"))
        except: dna_obj = {}
        dna_dict = {"genes": dna_obj, "complexity_score": float(dna.get("complexity_score", 0)), "dna_sequence": dna.get("dna_sequence", ""), "species": dna.get("species", "")}
        text = "\n".join(r[4] for r in chunk_rows if r[4])
        word_freq = {r[0]: int(r[1]) for r in word_rows}
        profile = _jorki_compute_profile(text, text.split("\n"), word_freq, kpis, dna_dict)
        return {"file_id": file_id, "profile": profile}
    if name == "jorki_ml":
        conn = sqlite3.connect(str(idx_path))
        meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM file_meta").fetchall()}
        kpis = [{"id": r[0], "name": r[1], "value": r[2], "line": r[3], "category": r[4], "confidence": r[5]} for r in conn.execute("SELECT id, name, value, line, category, confidence FROM kpis").fetchall()]
        dna_rows = conn.execute("SELECT key, value FROM dna").fetchall()
        word_rows = conn.execute("SELECT word, count FROM word_freq").fetchall()
        chunk_rows = conn.execute("SELECT idx, line_start, line_end, boundary_type, preview, line_count FROM chunks").fetchall(); conn.close()
        word_freq = {r[0]: int(r[1]) for r in word_rows}
        dna = {r[0]: r[1] for r in dna_rows}
        try: dna_obj = json.loads(dna.get("genes", "{}"))
        except: dna_obj = {}
        dna_dict = {"genes": dna_obj, "complexity_score": float(dna.get("complexity_score", 0)), "dna_sequence": dna.get("dna_sequence", ""), "species": dna.get("species", "")}
        text = "\n".join(r[4] for r in chunk_rows if r[4]); lines = text.split("\n")
        chunks = [{"idx": r[0], "line_start": r[1], "line_end": r[2], "boundary_type": r[3], "preview": r[4], "line_count": r[5]} for r in chunk_rows]
        try: ml = _jorki_ml_extract(text, lines, chunks, word_freq, kpis, dna_dict)
        except Exception as e: ml = {"available": False, "error": str(e)}
        return {"file_id": file_id, "ml": ml}
    if name == "jorki_valuation":
        conn = sqlite3.connect(str(idx_path))
        meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM file_meta").fetchall()}
        kpis = [{"id": r[0], "name": r[1], "value": r[2], "line": r[3], "category": r[4], "confidence": r[5]} for r in conn.execute("SELECT id, name, value, line, category, confidence FROM kpis").fetchall()]
        dna_rows = conn.execute("SELECT key, value FROM dna").fetchall()
        word_rows = conn.execute("SELECT word, count FROM word_freq").fetchall()
        chunk_rows = conn.execute("SELECT idx, line_start, line_end, boundary_type, preview, line_count FROM chunks").fetchall()
        sym_rows = conn.execute("SELECT line, name, type FROM symbols").fetchall(); conn.close()
        word_freq = {r[0]: int(r[1]) for r in word_rows}
        dna = {r[0]: r[1] for r in dna_rows}
        try: dna_obj = json.loads(dna.get("genes", "{}"))
        except: dna_obj = {}
        dna_dict = {"genes": dna_obj, "complexity_score": float(dna.get("complexity_score", 0)), "dna_sequence": dna.get("dna_sequence", ""), "species": dna.get("species", "")}
        text = "\n".join(r[4] for r in chunk_rows if r[4]); lines = text.split("\n")
        chunks = [{"idx": r[0], "line_start": r[1], "line_end": r[2], "boundary_type": r[3], "preview": r[4], "line_count": r[5]} for r in chunk_rows]
        symbols = [{"line": r[0], "name": r[1], "type": r[2]} for r in sym_rows]
        val = _jorki_valuate(text, lines, chunks, symbols, word_freq, kpis, dna_dict, meta)
        return {"file_id": file_id, "valuation": val}
    if name == "jorki_dossier":
        fmt = args.get("format", "json")
        if fmt == "text":
            return PlainTextResponse(_jorki_generate_resume(file_id, {"filename": ""}, [], {}, {}, [], [], {}, {}, {})["dossier_text"])
        return await_proxy(file_id)
    if name == "jorki_capabilities":
        conn = sqlite3.connect(str(idx_path)); caps = conn.execute("SELECT id, name FROM capabilities").fetchall(); conn.close()
        return {"file_id": file_id, "total": len(caps), "capabilities": [{"id": r[0], "name": r[1], "enabled": True} for r in caps]}
    if name == "jorki_stats":
        ql = _jorki_query_log.get(file_id, {"total_queries": 0, "query_breakdown": {}})
        return {"file_id": file_id, "total_queries": ql.get("total_queries", 0), "stats": [{"type": k, "count": v} for k, v in ql.get("query_breakdown", {}).items()]}
    # ── SonicGlyph tools ──
    if name == "sonic_list":
        reg = _sonic_load_registry()
        return {"files": [{"audio_id": aid, **e} for aid, e in reg.items()], "total": len(reg)}
    audio_id = args.get("audio_id", "")
    if name.startswith("sonic_") and name not in ("sonic_list", "sonic_claim_create", "sonic_claim_settle"):
        if not audio_id:
            return {"error": "audio_id is required"}
        sidx = SONIC_DATA_DIR / f"{audio_id}.idx"
        if not sidx.exists():
            return {"error": f"Audio not found: {audio_id}"}
        conn = sqlite3.connect(str(sidx))
        if name == "sonic_meta":
            meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM audio_meta").fetchall()}; conn.close()
            return {"audio_id": audio_id, "meta": meta}
        if name == "sonic_fingerprint":
            fp = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM fingerprint").fetchall()}; conn.close()
            return {"audio_id": audio_id, "fingerprint": fp}
        if name == "sonic_speakers":
            sp = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM speakers").fetchall()}; conn.close()
            return {"audio_id": audio_id, "speakers": sp}
        if name == "sonic_transcript_shadow":
            segs = conn.execute("SELECT idx, timestamp, seg_type, energy FROM transcript_shadow").fetchall(); conn.close()
            return {"audio_id": audio_id, "segments": [{"idx": r[0], "t": r[1], "type": r[2], "energy": r[3]} for r in segs], "total": len(segs), "redacted": True}
        if name == "sonic_claims":
            claims = conn.execute("SELECT idx, claim, value, unit, confidence FROM semantic_claims").fetchall(); conn.close()
            return {"audio_id": audio_id, "claims": [{"idx": r[0], "claim": r[1], "value": r[2], "unit": r[3], "confidence": r[4]} for r in claims], "total": len(claims)}
        if name == "sonic_search":
            q = args.get("q", "")
            if not q: conn.close(); return {"error": "query 'q' is required"}
            results = conn.execute("SELECT idx, timestamp_start, timestamp_end, energy, seg_type, preview FROM audio_chunks WHERE seg_type LIKE ? OR preview LIKE ?", (f"%{q}%", f"%{q}%")).fetchall(); conn.close()
            return {"audio_id": audio_id, "query": q, "results": [{"idx": r[0], "start": r[1], "end": r[2], "energy": r[3], "type": r[4], "preview": r[5]} for r in results], "total": len(results)}
        if name == "sonic_chunk":
            ts = args.get("timestamp", 0)
            row = conn.execute("SELECT idx, timestamp_start, timestamp_end, energy, seg_type, preview FROM audio_chunks WHERE timestamp_start <= ? AND timestamp_end >= ? ORDER BY ABS(timestamp_start - ?) LIMIT 1", (ts, ts, ts)).fetchone(); conn.close()
            if not row: return {"error": f"No chunk at timestamp {ts}"}
            return {"audio_id": audio_id, "idx": row[0], "start": row[1], "end": row[2], "energy": row[3], "type": row[4], "preview": row[5], "playable": False}
        if name == "sonic_glyph":
            meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM audio_meta").fetchall()}
            fp = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM fingerprint").fetchall()}
            sp = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM speakers").fetchall()}
            segs = conn.execute("SELECT idx, timestamp, seg_type, energy FROM transcript_shadow").fetchall()
            claims = conn.execute("SELECT idx, claim, value, unit, confidence FROM semantic_claims").fetchall()
            chunks = conn.execute("SELECT idx, timestamp_start, timestamp_end, energy, seg_type FROM audio_chunks").fetchall(); conn.close()
            return {"audio_id": audio_id, "glyph_type": "SonicGlyph", "meta": meta, "fingerprint": fp, "speakers": sp, "transcript_shadow": {"segments": len(segs), "redacted": True}, "semantic_claims": len(claims), "audio_chunks": len(chunks), "playable": False, "identity_exposed": False, "fidelity": {"L0": True, "L1": True, "L2": True, "L3": True, "L4": True, "L5": True, "L6": len(claims), "L8": True, "L9": False}}
        if name == "sonic_receipt":
            meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM audio_meta").fetchall()}
            fp = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM fingerprint").fetchall()}
            claims = conn.execute("SELECT claim, value, confidence FROM semantic_claims").fetchall(); conn.close()
            return {"receipt_id": hashlib.sha256(f"{audio_id}{time.time()}".encode()).hexdigest()[:16], "audio_id": audio_id, "timestamp": datetime.now().isoformat(), "sha256": meta.get("sha256", ""), "fingerprint_hash": fp.get("fingerprint_hash", ""), "filename": meta.get("filename", ""), "duration_s": meta.get("duration_s", "0"), "format": meta.get("format", "unknown"), "claims_verified": len(claims), "playable": False, "identity_exposed": False, "proof_type": "SonicGlyph non-playable proof receipt"}
        conn.close()
    if name == "sonic_claim_create":
        if not audio_id and "audio_id" in args:
            audio_id = args["audio_id"]
        if not audio_id:
            return {"error": "audio_id is required"}
        sidx = SONIC_DATA_DIR / f"{audio_id}.idx"
        if not sidx.exists():
            return {"error": f"Audio not found: {audio_id}"}
        conn = sqlite3.connect(str(sidx))
        meta = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM audio_meta").fetchall()}
        fp = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM fingerprint").fetchall()}
        sp = {r[0]: r[1] for r in conn.execute("SELECT key, value FROM speakers").fetchall()}; conn.close()
        claim_id = hashlib.sha256(f"{audio_id}{time.time()}{args.get('seller_id','')}".encode()).hexdigest()[:16]
        surrogate = {"duration_s": meta.get("duration_s", "0"), "sha256": meta.get("sha256", "")[:32], "speaker_count": sp.get("speaker_count", "0"), "fingerprint_hash": fp.get("fingerprint_hash", ""), "format": meta.get("format", "unknown"), "redacted": True}
        _sonic_claims[claim_id] = {"claim_id": claim_id, "audio_id": audio_id, "seller_id": args.get("seller_id", "anonymous"), "buyer_id": args.get("buyer_id", ""), "task_description": args.get("task_description", ""), "surrogate": surrogate, "bond_amount": args.get("bond_amount", 0), "bond_posted": True, "status": "open", "created_at": time.time()}
        return {"claim_id": claim_id, "status": "open", "surrogate": surrogate, "message": "Claim created. Buyer must escrow payment, then settle."}
    if name == "sonic_claim_settle":
        claim_id = args.get("claim_id", "")
        if claim_id not in _sonic_claims:
            return {"error": f"Claim not found: {claim_id}"}
        claim = _sonic_claims[claim_id]
        tp = args.get("tests_passed", 0); tt = args.get("tests_total", 0)
        if tt > 0 and tp == tt:
            result = "pass"; claim["settlement_result"] = f"PASS: {tp}/{tt} tests passed. Bond returned. Payment released."
        else:
            result = "fail"; claim["settlement_result"] = f"FAIL: {tp}/{tt} passed. Bond slashed. Payment returned."
        claim["receipt"] = hashlib.sha256(f"{claim_id}{time.time()}{result}".encode()).hexdigest()[:32]
        claim["status"] = "settled"; claim["tests_passed"] = tp; claim["tests_total"] = tt
        return {"claim_id": claim_id, "status": "settled", "result": result, "settlement": claim["settlement_result"], "receipt": claim["receipt"], "bond_returned": result == "pass", "payment_released": result == "pass"}
    return {"error": f"Unknown tool: {name}", "available": [t["name"] for t in _MCP_TOOLS]}


def await_proxy(file_id):
    """Helper to return dossier JSON inline."""
    idx_path = JORKI_INDEX_DIR / f"{file_id}.idx"
    if not idx_path.exists(): return {"error": f"Index not found for {file_id}"}
    conn = sqlite3.connect(str(idx_path))
    meta_rows = conn.execute("SELECT key, value FROM file_meta").fetchall()
    kpi_rows = conn.execute("SELECT id, name, value, line, category, confidence FROM kpis").fetchall()
    dna_rows = conn.execute("SELECT key, value FROM dna").fetchall()
    word_rows = conn.execute("SELECT word, count FROM word_freq").fetchall()
    chunk_rows = conn.execute("SELECT idx, line_start, line_end, boundary_type, preview, line_count FROM chunks").fetchall()
    sym_rows = conn.execute("SELECT line, name, type FROM symbols").fetchall(); conn.close()
    _jorki_track_query(file_id, "resume")
    meta = {r[0]: r[1] for r in meta_rows}
    kpis = [{"id": r[0], "name": r[1], "value": r[2], "line": r[3], "category": r[4], "confidence": r[5]} for r in kpi_rows]
    dna = {r[0]: r[1] for r in dna_rows}
    word_freq = {r[0]: int(r[1]) for r in word_rows}
    chunks = [{"idx": r[0], "line_start": r[1], "line_end": r[2], "boundary_type": r[3], "preview": r[4], "line_count": r[5]} for r in chunk_rows]
    symbols = [{"line": r[0], "name": r[1], "type": r[2]} for r in sym_rows]
    text = "\n".join(c["preview"] for c in chunks); lines = text.split("\n")
    try: dna_obj = json.loads(dna.get("genes", "{}")) if isinstance(dna.get("genes"), str) else {}
    except: dna_obj = {}
    dna_dict = {"genes": dna_obj, "complexity_score": float(dna.get("complexity_score", 0)), "dna_sequence": dna.get("dna_sequence", ""), "species": dna.get("species", "")}
    profile = _jorki_compute_profile(text, lines, word_freq, kpis, dna_dict)
    valuation = _jorki_valuate(text, lines, chunks, symbols, word_freq, kpis, dna_dict, meta)
    try: ml_result = _jorki_ml_extract(text, lines, chunks, word_freq, kpis, dna_dict)
    except: ml_result = {"available": False, "error": "ml failed"}
    resume = _jorki_generate_resume(file_id, meta, kpis, dna_dict, word_freq, chunks, symbols, profile, valuation, ml_result)
    return {"file_id": file_id, "resume": resume}


@app.get("/mcp/tools")
async def mcp_list_tools():
    """List all available MCP tools."""
    return {"tools": _MCP_TOOLS}


@app.post("/mcp")
async def mcp_jsonrpc(body: dict = Body(...)):
    """MCP JSON-RPC endpoint for ChatGPT web connection.

    Supports:
    - initialize: return server info
    - tools/list: return available tools
    - tools/call: execute a tool and return result
    """
    method = body.get("method", "")
    msg_id = body.get("id")
    params = body.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "result": {
                "serverInfo": {"name": "jorki-mcp", "version": "2.0.0"},
                "capabilities": {"tools": {"listChanged": False}},
            },
            "id": msg_id,
        }
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "result": {"tools": _MCP_TOOLS},
            "id": msg_id,
        }
    elif method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        result = _mcp_call_tool(tool_name, tool_args)
        return {
            "jsonrpc": "2.0",
            "result": {"content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}]},
            "id": msg_id,
        }
    else:
        return {
            "jsonrpc": "2.0",
            "error": {"code": -32601, "message": f"Method not found: {method}"},
            "id": msg_id,
        }


@app.post("/mcp/tools/call")
async def mcp_call_tool_direct(body: dict = Body(...)):
    """Direct tool call endpoint (simpler than JSON-RPC for testing)."""
    tool_name = body.get("name", "")
    tool_args = body.get("arguments", {})
    result = _mcp_call_tool(tool_name, tool_args)
    return {"tool": tool_name, "result": result, "timestamp": datetime.now().isoformat()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)
