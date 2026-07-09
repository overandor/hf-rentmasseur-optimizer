"""
Fortress Gateway — serves all 13 developed features as HTTP endpoints.

Usage:
    python3 fortress_gateway.py
    # or
    uvicorn fortress_gateway:app --host 0.0.0.0 --port 8000

Endpoints:
    GET  /                         → service catalog
    GET  /health                   → gateway health
    GET  /status                   → all 13 feature statuses
    POST /run/{feature}            → execute a feature action
    GET  /receipts                 → latest receipts
    GET  /docs                     → OpenAPI docs

Features served:
    profileops, systemlake, evidenceos, questionos, revenue_oracle,
    quadrantos, hyperflow, ytl_mcp_lab, serl, latentos, poptimizer,
    receipt_ledger, layer_crawler_etl
"""

import json
import os
import sys
import time
import hashlib
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Fortress Gateway",
    description="Unified API gateway for all developed features",
    version="1.0.0",
)

# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------

RECEIPTS_DB = Path(__file__).parent / "fortress_gateway.db"


def init_db():
    conn = sqlite3.connect(str(RECEIPTS_DB))
    conn.execute("""
    CREATE TABLE IF NOT EXISTS gateway_receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        feature TEXT NOT NULL,
        action TEXT NOT NULL,
        success INTEGER DEFAULT 1,
        detail TEXT,
        result TEXT,
        hash TEXT
    )
    """)
    conn.commit()
    conn.close()


init_db()


def receipt(feature: str, action: str, success: bool, detail: str, result: Any):
    ts = datetime.now(timezone.utc).isoformat()
    result_json = json.dumps(result, default=str) if result is not None else None
    h = hashlib.sha256(f"{ts}|{feature}|{action}|{detail}|{result_json}".encode()).hexdigest()[:16]
    conn = sqlite3.connect(str(RECEIPTS_DB))
    conn.execute(
        "INSERT INTO gateway_receipts (ts, feature, action, success, detail, result, hash) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (ts, feature, action, int(success), detail, result_json, h)
    )
    conn.commit()
    conn.close()
    return h


# ---------------------------------------------------------------------------
# Feature catalog
# ---------------------------------------------------------------------------

FEATURES = {
    "profileops": {
        "name": "ProfileOps / RentMasseur Fortress",
        "path": "rm_traffic.fortress",
        "demo_cmd": "python3 -m rm_traffic.fortress --status",
        "description": "Automated profile visibility, availability, and LLM bio optimization.",
    },
    "systemlake": {
        "name": "SystemLake Underwriter",
        "path": "systemlake",
        "demo_cmd": "python3 test_systemlake.py",
        "description": "Local policy-gated crawler, Merkle lake, and underwriting engine.",
    },
    "evidenceos": {
        "name": "EvidenceOS / B-Roll v8",
        "path": "broll",
        "demo_cmd": "python3 test_broll.py",
        "description": "Unified evidence graph, provenance, Merkle manifest, and receipt chain.",
    },
    "questionos": {
        "name": "QuestionOS",
        "path": "questionos",
        "demo_cmd": "python3 test_questionos.py",
        "description": "Terminal-native question execution with receipts and cost ledger.",
    },
    "revenue_oracle": {
        "name": "Revenue Oracle",
        "path": "revenue_oracle",
        "demo_cmd": "python3 test_revenue_oracle.py",
        "description": "216 protocol bridges, deployment adapters, and verification audit.",
    },
    "quadrantos": {
        "name": "QuadrantOS / Four-Screen Agent",
        "path": "quadrantos",
        "demo_cmd": "python3 quadrantos/demo.py",
        "description": "4-quadrant screen bus, vision gate, and safe execution broker.",
    },
    "hyperflow": {
        "name": "HyperFlow Ledger OS",
        "path": "hyperflow",
        "demo_cmd": "cat TASK_LEDGER.md",
        "description": "Multi-agent production loop with task ledger and receipts.",
    },
    "ytl_mcp_lab": {
        "name": "YTL-MCP Research Lab",
        "path": "ytl-mcp-lab",
        "demo_cmd": "cd ytl-mcp-lab && pytest",
        "description": "MCP-controlled YouTube research server with transcript scoring.",
    },
    "serl": {
        "name": "SERL / Patch-and-Evidence OS",
        "path": "serl.py",
        "demo_cmd": "python3 serl.py --help",
        "description": "Stateful observe → hypothesize → patch → benchmark → promote.",
    },
    "latentos": {
        "name": "LatentOS EDU",
        "path": "latentos",
        "demo_cmd": "python3 test_latentos.py",
        "description": "Academic credential liquidity and proof-of-scholarship.",
    },
    "poptimizer": {
        "name": "POptimizer",
        "path": "poptimizer.py",
        "demo_cmd": "python3 poptimizer.py",
        "description": "Anti-gaming safety constraints and fraud checks.",
    },
    "receipt_ledger": {
        "name": "Receipt Ledger",
        "path": "receipt_ledger.py",
        "demo_cmd": "python3 receipt_ledger.py",
        "description": "Tamper-evident SHA-256 chained receipt store.",
    },
    "layer_crawler_etl": {
        "name": "Layer Crawler ETL",
        "path": "layer_crawler_etl",
        "demo_cmd": "python3 -m layer_crawler_etl",
        "description": "Multi-layer web data extraction pipeline.",
    },
}


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------

def run_subprocess(cmd: list, timeout: int = 30, cwd: Optional[Path] = None, env: Optional[Dict] = None) -> Dict:
    """Run a command and return stdout/stderr/status."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd, env=env)
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:1000],
            "success": result.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "stdout": "", "stderr": "timeout", "success": False}
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e), "success": False}


def run_feature(feature: str, action: str = "status") -> Dict:
    """Execute a feature's demo command."""
    info = FEATURES.get(feature)
    if not info:
        raise HTTPException(status_code=404, detail=f"Feature {feature} not found")

    cwd = Path(__file__).parent
    if feature == "ytl_mcp_lab":
        cwd = cwd / "ytl-mcp-lab"

    cmd = info["demo_cmd"].split()
    if cmd[0].startswith("cd"):
        cmd = cmd[2:]

    result = run_subprocess(cmd, timeout=60)
    receipt(feature, action, result["success"], f"Ran {info['demo_cmd']}", result)
    return result


def run_python_module(module: str, timeout: int = 30) -> Dict:
    """Import and run a Python module's demo function."""
    try:
        result = subprocess.run([sys.executable, "-m", module], capture_output=True, text=True, timeout=timeout)
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[:2000],
            "stderr": result.stderr[:1000],
            "success": result.returncode == 0,
        }
    except Exception as e:
        return {"returncode": -1, "stdout": "", "stderr": str(e), "success": False}


# ---------------------------------------------------------------------------
# API Models
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    action: str = "status"
    args: Optional[Dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/")
def root():
    return {
        "service": "Fortress Gateway",
        "version": "1.0.0",
        "features": {k: {"name": v["name"], "description": v["description"]} for k, v in FEATURES.items()},
        "endpoints": [
            "/health",
            "/status",
            "/status/{feature}",
            "/run/{feature}",
            "/receipts",
        ],
    }


@app.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@app.get("/status")
def all_status():
    """Quick status of all features without running them."""
    results = {}
    for key, info in FEATURES.items():
        path = Path(__file__).parent / info["path"]
        if not path.exists():
            path = Path(__file__).parent / (info["path"].replace(".", "/") + ".py")
        exists = path.exists()
        results[key] = {
            "name": info["name"],
            "available": exists,
            "path": str(path),
            "demo_cmd": info["demo_cmd"],
        }
    receipt("gateway", "status_all", True, "Returned feature availability", results)
    return results


@app.get("/status/{feature}")
def feature_status(feature: str):
    if feature not in FEATURES:
        raise HTTPException(status_code=404, detail="Feature not found")
    info = FEATURES[feature]
    path = Path(__file__).parent / info["path"]
    exists = path.exists()
    result = {
        "name": info["name"],
        "available": exists,
        "path": str(path),
        "demo_cmd": info["demo_cmd"],
    }
    receipt(feature, "status", True, "Returned feature status", result)
    return result


@app.post("/run/{feature}")
def run_feature_endpoint(feature: str, req: RunRequest):
    if feature not in FEATURES:
        raise HTTPException(status_code=404, detail="Feature not found")

    if feature == "profileops":
        # Run a quick status via the fortress module
        result = run_python_module("rm_traffic.fortress", timeout=60)
    elif feature == "systemlake":
        result = run_subprocess([sys.executable, "test_systemlake.py"], timeout=60)
    elif feature == "evidenceos":
        result = run_subprocess([sys.executable, "test_broll.py"], timeout=120)
    elif feature == "questionos":
        result = run_subprocess([sys.executable, "test_questionos.py"], timeout=60)
    elif feature == "revenue_oracle":
        result = run_subprocess([sys.executable, "test_revenue_oracle.py"], timeout=120)
    elif feature == "quadrantos":
        result = run_subprocess([sys.executable, "quadrantos/demo.py"], timeout=60)
    elif feature == "hyperflow":
        try:
            task_ledger = Path(__file__).parent / "TASK_LEDGER.md"
            content = task_ledger.read_text()[:2000]
            result = {"returncode": 0, "stdout": content, "stderr": "", "success": True}
        except Exception as e:
            result = {"returncode": -1, "stdout": "", "stderr": str(e), "success": False}
    elif feature == "ytl_mcp_lab":
        cwd = Path(__file__).parent / "ytl-mcp-lab"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).parent)
        result = run_subprocess([sys.executable, "-m", "pytest", "tests/test_lab.py", "-v"], cwd=cwd, timeout=60, env=env)
    elif feature == "serl":
        result = run_subprocess([sys.executable, "serl.py", "--help"], timeout=30)
        if result["success"] and not result["stdout"]:
            result["stdout"] = "SERL help/CLI loaded successfully"
    elif feature == "latentos":
        result = run_subprocess([sys.executable, "test_latentos.py"], timeout=60)
        if result["success"] and not result["stdout"]:
            result["stdout"] = "LatentOS tests passed silently"
    elif feature == "poptimizer":
        result = run_subprocess([sys.executable, "poptimizer.py"], timeout=60)
        if result["success"] and not result["stdout"]:
            result["stdout"] = "POptimizer loaded successfully"
    elif feature == "receipt_ledger":
        result = run_subprocess([sys.executable, "receipt_ledger.py"], timeout=30)
        if result["success"] and not result["stdout"]:
            result["stdout"] = "Receipt ledger loaded successfully"
    elif feature == "layer_crawler_etl":
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).parent)
        result = run_subprocess([sys.executable, "layer_crawler_etl/example_usage.py"], timeout=60, env=env)
        if result["success"] and not result["stdout"]:
            result["stdout"] = "Layer Crawler ETL ran successfully"
    elif feature == "quadrantos":
        result = run_subprocess([sys.executable, "quadrantos/demo.py"], timeout=60)
    else:
        raise HTTPException(status_code=400, detail="No runner defined")

    receipt(feature, req.action, result["success"], f"Executed {feature} action={req.action}", result)
    return JSONResponse({
        "feature": feature,
        "action": req.action,
        "success": result["success"],
        "result": result,
    }, status_code=200 if result["success"] else 500)


@app.get("/receipts")
def get_receipts(limit: int = 20):
    conn = sqlite3.connect(str(RECEIPTS_DB))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM gateway_receipts ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
