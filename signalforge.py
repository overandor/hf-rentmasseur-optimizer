#!/usr/bin/env python3
"""
SignalForge — Market Microstructure Intelligence

Not a scraper. A mechanism mining engine that extracts laws from launches
and generates counterfactual product variants.

Endpoints:
  GET  /                          — Dashboard
  GET  /health                    — Health check
  POST /api/launches/ingest       — Ingest a launch (manual or PH API)
  GET  /api/launches              — List all launches
  POST /api/launches/ph           — Fetch from Product Hunt GraphQL (needs PH token)
  POST /api/mechanisms/extract    — Extract mechanism from a launch
  GET  /api/mechanisms            — List discovered mechanisms
  POST /api/variants/generate     — Generate counterfactual product variants
  GET  /api/variants              — List product variants
  POST /api/experiments/create    — Create microproduct experiment
  GET  /api/experiments           — List experiments
  POST /api/experiments/{id}/verdict — Record verdict (keep/kill/merge/iterate)
  POST /api/l4/start              — Start Layer4Meter capture session
  POST /api/l4/stop               — Stop capture, compute LCI score
  GET  /api/l4/sessions           — List L4 sessions
  GET  /api/l4/receipt/{id}       — Get L4 substrate receipt
  GET  /api/battalion             — Full battalion status (squads + counts)
  GET  /api/operator-report       — SignalForge operator report

Run:
  python3 signalforge.py [--port 7863]
"""

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Body, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="SignalForge — Market Microstructure Intelligence", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATA_DIR = Path(os.environ.get("SIGNALFORGE_DATA", str(Path(__file__).parent / "signalforge_data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "signalforge.db"

# Load .env
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

MECHANISM_TEMPLATES = [
    {"name": "before_after_transformation", "description": "Visual before/after showing improvement", "virality": 0.9, "monetization": 0.7},
    {"name": "scorecard_status_game", "description": "Score/rank that creates status signaling", "virality": 0.8, "monetization": 0.6},
    {"name": "receipt_proof_packet", "description": "Generates verifiable evidence document", "virality": 0.4, "monetization": 0.8},
    {"name": "risk_removal", "description": "Reduces anxiety about a specific risk", "virality": 0.3, "monetization": 0.9},
    {"name": "time_compression", "description": "Turns hours-long task into seconds", "virality": 0.6, "monetization": 0.7},
    {"name": "embarrassment_reduction", "description": "Fixes something people are ashamed of", "virality": 0.5, "monetization": 0.8},
    {"name": "identity_upgrade", "description": "Transforms user's perceived identity", "virality": 0.9, "monetization": 0.7},
    {"name": "money_recovery", "description": "Finds or recovers money for user", "virality": 0.4, "monetization": 0.9},
    {"name": "legal_anxiety_relief", "description": "Simplifies legal/conflict situation", "virality": 0.3, "monetization": 0.9},
    {"name": "creator_performance_feedback", "description": "Scores and improves creator output", "virality": 0.7, "monetization": 0.6},
    {"name": "private_to_shareable", "description": "Converts private work into shareable artifact", "virality": 0.8, "monetization": 0.6},
    {"name": "folder_to_valuation", "description": "Turns project files into economic packet", "virality": 0.3, "monetization": 0.9},
]

SQUADS = {
    "scout": {"name": "Scout Apps", "description": "Tiny experiments to test a pain", "target": 30},
    "infantry": {"name": "Infantry Apps", "description": "Simple utilities with fast shipping", "target": 50},
    "artillery": {"name": "Artillery Apps", "description": "Viral share-output products", "target": 20},
    "capital": {"name": "Capital Apps", "description": "Proof, valuation, receipts, deal rooms", "target": 15},
    "flagship": {"name": "Flagship Apps", "description": "Top 1-3 products with full polish", "target": 3},
}

FIRST_10_APPS = [
    {"name": "TenantProof", "squad": "scout", "hypothesis": "Tenants will pay to generate repair evidence packets", "mechanism": "receipt_proof_packet", "user": "renters", "pain": "landlord disputes", "artifact": "PDF evidence packet"},
    {"name": "HookJudge", "squad": "scout", "hypothesis": "Creators will pay to score short-video hooks", "mechanism": "creator_performance_feedback", "user": "tiktok creators", "pain": "low engagement", "artifact": "hook score + rewrite"},
    {"name": "FolderValuator", "squad": "capital", "hypothesis": "Builders will pay to convert folders into economic packets", "mechanism": "folder_to_valuation", "user": "developers/founders", "pain": "unvalued work", "artifact": "valuation PDF"},
    {"name": "DatingPhotoAudit", "squad": "scout", "hypothesis": "Singles will pay to score and fix dating photos", "mechanism": "identity_upgrade", "user": "dating app users", "pain": "bad photos", "artifact": "photo score + fixes"},
    {"name": "PetPawLog", "squad": "scout", "hypothesis": "Pet owners will pay to track health evidence", "mechanism": "receipt_proof_packet", "user": "pet owners", "pain": "vet disputes", "artifact": "health evidence log"},
    {"name": "ReceiptTaxPack", "squad": "capital", "hypothesis": "Freelancers will pay for receipt-to-deductible packets", "mechanism": "money_recovery", "user": "freelancers", "pain": "tax preparation", "artifact": "deductible packet"},
    {"name": "MasseurBooker", "squad": "infantry", "hypothesis": "Massage therapists will pay for booking pages", "mechanism": "time_compression", "user": "local service providers", "pain": "scheduling overhead", "artifact": "booking page"},
    {"name": "RoomReimagine", "squad": "artillery", "hypothesis": "Renters will share before/after room visualizations", "mechanism": "before_after_transformation", "user": "renters", "pain": "ugly rooms", "artifact": "before/after image"},
    {"name": "PromptLedger", "squad": "capital", "hypothesis": "AI workers will pay for proof-of-labor receipts", "mechanism": "receipt_proof_packet", "user": "AI practitioners", "pain": "untracked AI work", "artifact": "labor receipt"},
    {"name": "ContractorQuoteCheck", "squad": "scout", "hypothesis": "Homeowners will pay to detect risky quotes", "mechanism": "risk_removal", "user": "homeowners", "pain": "contractor overcharging", "artifact": "quote analysis"},
]

CAPITALFOLDER_SPEC = {
    "name": "CapitalFolder",
    "tagline": "Turn any project folder into a notarized economic packet",
    "mechanism": "folder_to_valuation",
    "squad": "flagship",
    "screens": ["Home", "CreateAssetFolder", "ScanImportFiles", "GenerateReceipt", "LaborLedger", "ValuationPacket", "ExportDealRoom", "Subscription"],
    "core_flow": "import → inventory + labor estimate + dependency risk + originality + commercial paths + proof hash → PDF valuation + JSON receipt + shareable buyer page",
    "monetization": {
        "free": "3 asset folders, basic receipts",
        "pro": "unlimited folders, valuation export, PDF reports, deal room",
        "studio": "team folders, licensing packets, IP vault, portfolio dashboard",
    },
    "patentable_mechanism": "A mobile system for converting heterogeneous user-created digital artifacts into a cryptographically verifiable economic asset packet comprising provenance, labor quantification, dependency risk, commercial pathway classification, and exportable valuation evidence.",
    "build_order": {
        "week_1": "SwiftUI shell + folder model + receipt hash",
        "week_2": "Import files + labor ledger + PDF export",
        "week_3": "Subscription + App Store assets + TestFlight",
        "week_4": "App Review + launch + first users",
    },
    "reusable_rails": ["Receipt Engine", "Valuation Engine", "PDF Export", "Subscription Gate", "Folder Scanner", "Deal Room Generator", "App Store Template"],
}


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS launches (
        id TEXT PRIMARY KEY,
        name TEXT, tagline TEXT, category TEXT, launch_date TEXT,
        rank INTEGER, votes INTEGER, comments INTEGER,
        vote_velocity REAL, comment_vote_ratio REAL,
        maker_response_speed REAL, pricing_model TEXT,
        ai_wording TEXT, audience_segment TEXT, pain_category TEXT,
        virality_artifact TEXT, source TEXT, raw_data TEXT,
        created_at REAL
    );
    CREATE TABLE IF NOT EXISTS mechanisms (
        id TEXT PRIMARY KEY,
        name TEXT, description TEXT, source_launch TEXT,
        virality_score REAL, monetization_score REAL,
        launch_power REAL, evidence_count INTEGER DEFAULT 1,
        created_at REAL
    );
    CREATE TABLE IF NOT EXISTS variants (
        id TEXT PRIMARY KEY,
        mechanism_id TEXT, app_name TEXT, user_segment TEXT,
        pain TEXT, artifact TEXT, platform TEXT,
        virality_prob REAL, monetization_prob REAL,
        squad TEXT, status TEXT DEFAULT 'hypothesized',
        created_at REAL
    );
    CREATE TABLE IF NOT EXISTS experiments (
        id TEXT PRIMARY KEY,
        app_name TEXT, hypothesis TEXT, mechanism TEXT,
        squad TEXT, user_segment TEXT, pain TEXT, artifact TEXT,
        status TEXT DEFAULT 'hypothesized',
        install_rate REAL, completion_rate REAL, share_rate REAL,
        paid_conversion REAL, retention_d1 REAL, retention_d7 REAL,
        artifact_completion REAL, verdict TEXT, verdict_reason TEXT,
        created_at REAL, launched_at REAL, decided_at REAL
    );
    CREATE TABLE IF NOT EXISTS l4_sessions (
        id TEXT PRIMARY KEY,
        project TEXT, mode TEXT,
        start_time REAL, end_time REAL,
        cpu_seconds REAL, gpu_activity REAL, disk_write_mb REAL,
        file_event_count INTEGER, process_spawn_count INTEGER,
        network_bytes REAL, memory_pressure REAL,
        snapshot_delta_mb REAL, screen_state_changes INTEGER,
        agent_idle_time REAL, useful_output TEXT,
        lci_score REAL, hidden_compute_lift REAL,
        receipt_hash TEXT, created_at REAL
    );
    CREATE TABLE IF NOT EXISTS receipts (
        receipt_id TEXT PRIMARY KEY,
        timestamp REAL, action TEXT, actor TEXT,
        result TEXT, evidence TEXT, metadata TEXT
    );
    """)
    conn.commit()
    conn.close()


init_db()


def now_ts(): return time.time()
def now_iso(): return datetime.now(timezone.utc).isoformat()
def write_receipt(action, actor, result, evidence, metadata=None):
    rid = uuid.uuid4().hex[:16]
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("INSERT INTO receipts VALUES (?,?,?,?,?,?,?)",
                 (rid, now_ts(), action, actor, result, evidence, json.dumps(metadata or {})))
    conn.commit(); conn.close()
    return rid


def compute_launch_power(launch):
    vv = launch.get("vote_velocity", 0)
    comments = launch.get("comments", 0)
    votes = launch.get("votes", 0)
    cv_ratio = comments / max(votes, 1)
    shareability = 0.5
    pain_clarity = 0.5
    monetization = 0.5
    clone_resistance = 0.5
    return round(vv * 0.2 + cv_ratio * 20 + shareability * 15 + pain_clarity * 15 + monetization * 15 + clone_resistance * 15, 2)


def classify_mechanism(launch):
    """Classify a launch into a mechanism using heuristics."""
    text = f"{launch.get('name','')} {launch.get('tagline','')} {launch.get('category','')}".lower()
    scores = {}
    for m in MECHANISM_TEMPLATES:
        score = 0
        if m["name"] == "before_after_transformation" and any(w in text for w in ["photo", "image", "visual", "transform", "headshot"]):
            score += 3
        if m["name"] == "scorecard_status_game" and any(w in text for w in ["score", "rank", "grade", "rate"]):
            score += 3
        if m["name"] == "receipt_proof_packet" and any(w in text for w in ["proof", "receipt", "evidence", "document", "certify"]):
            score += 3
        if m["name"] == "risk_removal" and any(w in text for w in ["legal", "contract", "risk", "safe", "compliance"]):
            score += 3
        if m["name"] == "time_compression" and any(w in text for w in ["fast", "quick", "instant", "automate", "schedule"]):
            score += 3
        if m["name"] == "identity_upgrade" and any(w in text for w in ["profile", "photo", "headshot", "resume", "brand"]):
            score += 3
        if m["name"] == "money_recovery" and any(w in text for w in ["tax", "refund", "money", "deduct", "save"]):
            score += 3
        if m["name"] == "creator_performance_feedback" and any(w in text for w in ["creator", "tiktok", "video", "hook", "content"]):
            score += 3
        if m["name"] == "private_to_shareable" and any(w in text for w in ["share", "export", "publish", "convert"]):
            score += 3
        if m["name"] == "folder_to_valuation" and any(w in text for w in ["folder", "project", "asset", "valuation", "portfolio"]):
            score += 3
        scores[m["name"]] = score + m["virality"] + m["monetization"]
    best = max(scores, key=scores.get)
    tmpl = next(m for m in MECHANISM_TEMPLATES if m["name"] == best)
    return tmpl


def generate_variants(mechanism_name, count=12):
    """Generate counterfactual product variants from a mechanism."""
    niches = {
        "receipt_proof_packet": [
            ("tenant", "renters", "landlord disputes", "repair evidence PDF"),
            ("freelancer", "freelancers", "unpaid invoices", "payment proof packet"),
            ("patient", "patients", "medical visits", "visit summary packet"),
            ("driver", "drivers", "accidents", "accident photo proof"),
            ("parent", "parents", "school issues", "bullying evidence log"),
            ("contractor", "homeowners", "bad work", "damage proof packet"),
            ("delivery", "consumers", "damaged delivery", "delivery damage proof"),
            ("employee", "workers", "workplace issues", "shift proof log"),
            ("pet_owner", "pet owners", "vet disputes", "health evidence log"),
            ("roommate", "renters", "deposit disputes", "deposit condition proof"),
            ("student", "students", "grade disputes", "submission proof packet"),
            ("small_business", "owners", "vendor disputes", "order proof packet"),
        ],
        "before_after_transformation": [
            ("room", "renters", "ugly rooms", "before/after room image"),
            ("body", "fitness users", "fitness progress", "transformation photo"),
            ("garden", "homeowners", "yard work", "before/after garden"),
            ("resume", "job seekers", "bad resume", "before/after resume"),
            ("presentation", "professionals", "ugly slides", "before/after deck"),
            ("logo", "startups", "bad branding", "before/after logo"),
            ("outfit", "fashion users", "wardrobe", "before/after outfit"),
            ("meal", "home cooks", "plating", "before/after dish"),
            ("desk", "remote workers", "workspace", "before/after desk"),
            ("handwriting", "students", "messy notes", "before/after notes"),
            ("code", "developers", "ugly code", "before/after refactor"),
            ("invoice", "freelancers", "bad invoice", "before/after invoice"),
        ],
        "identity_upgrade": [
            ("dating", "singles", "bad profile", "photo audit + fixes"),
            ("linkedin", "professionals", "weak profile", "profile upgrade packet"),
            ("resume", "job seekers", "generic resume", "targeted resume"),
            ("brand", "startups", "no identity", "brand kit"),
            ("bio", "creators", "weak bio", "creator bio upgrade"),
            ("headshot", "professionals", "bad photo", "AI headshot"),
            ("portfolio", "designers", "no portfolio", "portfolio site"),
            ("email", "professionals", "bad signature", "signature upgrade"),
            ("voicemail", "professionals", "bad greeting", "voicemail upgrade"),
            ("business_card", "networkers", "boring card", "digital card"),
            ("twitter", "creators", "weak profile", "profile upgrade"),
            ("github", "developers", "weak readme", "readme upgrade"),
        ],
    }
    all_niches = niches.get(mechanism_name, [
        (f"niche_{i}", f"segment_{i}", f"pain_{i}", f"artifact_{i}") for i in range(count)
    ])
    return all_niches[:count]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {"status": "ok", "service": "SignalForge", "version": "1.0", "timestamp": now_iso()}


@app.post("/api/launches/ingest")
async def ingest_launch(launch: dict = Body(...)):
    """Ingest a launch manually or from PH API data."""
    lid = uuid.uuid4().hex[:12]
    votes = launch.get("votes", 0)
    comments = launch.get("comments", 0)
    cv_ratio = comments / max(votes, 1) if votes > 0 else 0
    launch_power = compute_launch_power(launch)

    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""INSERT INTO launches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (lid, launch.get("name",""), launch.get("tagline",""), launch.get("category",""),
                  launch.get("launch_date",""), launch.get("rank",0), votes, comments,
                  launch.get("vote_velocity",0), cv_ratio, launch.get("maker_response_speed",0),
                  launch.get("pricing_model",""), launch.get("ai_wording",""),
                  launch.get("audience_segment",""), launch.get("pain_category",""),
                  launch.get("virality_artifact",""), launch.get("source","manual"),
                  json.dumps(launch), now_ts()))
    conn.commit(); conn.close()

    write_receipt("launch_ingest", "system", "success", f"launch={lid} power={launch_power}")
    return {"launch_id": lid, "launch_power": launch_power, "message": "Launch ingested as evidence"}


@app.get("/api/launches")
async def list_launches(limit: int = 50):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM launches ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"launches": [dict(r) for r in rows], "count": len(rows)}


@app.post("/api/launches/ph")
async def fetch_ph_launches(
    days: int = Body(1),
    ph_token: str = Body(None),
):
    """Fetch launches from Product Hunt GraphQL API. Needs PH API token."""
    token = ph_token or os.environ.get("PH_API_TOKEN", "") or os.environ.get("PRODUCTHUNT_TOKEN", "")
    if not token:
        raise HTTPException(400, "No Product Hunt API token. Set PH_API_TOKEN in .env or pass ph_token.")

    import urllib.request
    query = """
    query { posts(first: 20, order: VOTES) { edges { node { name tagline votesCount commentsCount website createdAt topics(first:5){edges{node{name}}} } } } }
    """
    payload = json.dumps({"query": query}).encode()
    req = urllib.request.Request("https://api.producthunt.com/v2/api/graphql", data=payload, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
    except Exception as e:
        raise HTTPException(502, f"PH API error: {e}")

    edges = data.get("data", {}).get("posts", {}).get("edges", [])
    ingested = []
    for edge in edges:
        node = edge["node"]
        launch = {
            "name": node["name"], "tagline": node["tagline"],
            "votes": node["votesCount"], "comments": node["commentsCount"],
            "launch_date": node.get("createdAt", ""),
            "category": ", ".join(t["node"]["name"] for t in node.get("topics", {}).get("edges", [])),
            "source": "producthunt_api",
        }
        lid = uuid.uuid4().hex[:12]
        conn = sqlite3.connect(str(DB_PATH))
        conn.execute("""INSERT INTO launches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (lid, launch["name"], launch["tagline"], launch["category"],
                      launch["launch_date"], 0, launch["votes"], launch["comments"],
                      0, launch["comments"]/max(launch["votes"],1), 0, "", "", "", "", "",
                      "producthunt_api", json.dumps(launch), now_ts()))
        conn.commit(); conn.close()
        ingested.append(lid)

    write_receipt("ph_fetch", "system", "success", f"count={len(ingested)}")
    return {"ingested": len(ingested), "launch_ids": ingested}


@app.post("/api/mechanisms/extract")
async def extract_mechanism(launch_id: str = Body(...)):
    """Extract mechanism from a specific launch."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM launches WHERE id = ?", (launch_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Launch not found")
    launch = dict(row)
    mech = classify_mechanism(launch)
    mid = uuid.uuid4().hex[:12]
    lp = compute_launch_power(launch)
    conn.execute("""INSERT INTO mechanisms VALUES (?,?,?,?,?,?,?,?,?)""",
                 (mid, mech["name"], mech["description"], launch_id,
                  mech["virality"], mech["monetization"], lp, 1, now_ts()))
    conn.commit(); conn.close()

    write_receipt("mechanism_extract", "system", "success", f"mechanism={mech['name']} launch={launch_id}")
    return {"mechanism_id": mid, "mechanism": mech["name"], "description": mech["description"],
            "launch_power": lp, "source_launch": launch["name"]}


@app.get("/api/mechanisms")
async def list_mechanisms():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM mechanisms ORDER BY launch_power DESC").fetchall()
    conn.close()
    return {"mechanisms": [dict(r) for r in rows], "count": len(rows)}


@app.post("/api/variants/generate")
async def generate_variant(
    mechanism_name: str = Body(...),
    count: int = Body(12),
):
    """Generate counterfactual product variants from a mechanism."""
    niches = generate_variants(mechanism_name, count)
    conn = sqlite3.connect(str(DB_PATH))
    created = []
    for niche_id, user, pain, artifact in niches:
        vid = uuid.uuid4().hex[:12]
        app_name = niche_id.replace("_", " ").title() + "App"
        squad = "scout"
        conn.execute("""INSERT INTO variants VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (vid, mechanism_name, app_name, user, pain, artifact, "iphone",
                      0.5, 0.5, squad, "hypothesized", now_ts()))
        created.append({"id": vid, "app_name": app_name, "user": user, "pain": pain, "artifact": artifact})
    conn.commit(); conn.close()

    write_receipt("variant_generate", "system", "success", f"mechanism={mechanism_name} count={len(created)}")
    return {"mechanism": mechanism_name, "variants": created, "count": len(created)}


@app.get("/api/variants")
async def list_variants(limit: int = 50):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM variants ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return {"variants": [dict(r) for r in rows], "count": len(rows)}


@app.post("/api/experiments/create")
async def create_experiment(exp: dict = Body(...)):
    """Create a microproduct experiment."""
    eid = uuid.uuid4().hex[:12]
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""INSERT INTO experiments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (eid, exp.get("app_name",""), exp.get("hypothesis",""), exp.get("mechanism",""),
                  exp.get("squad","scout"), exp.get("user_segment",""), exp.get("pain",""),
                  exp.get("artifact",""), "hypothesized",
                  0, 0, 0, 0, 0, 0, 0, None, None, now_ts(), None, None))
    conn.commit(); conn.close()
    write_receipt("experiment_create", "human", "success", f"app={exp.get('app_name')} squad={exp.get('squad')}")
    return {"experiment_id": eid, "status": "hypothesized"}


@app.get("/api/experiments")
async def list_experiments():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM experiments ORDER BY created_at DESC").fetchall()
    conn.close()
    return {"experiments": [dict(r) for r in rows], "count": len(rows)}


@app.post("/api/experiments/{eid}/verdict")
async def experiment_verdict(eid: str, verdict: str = Body(...), reason: str = Body(""), metrics: dict = Body({})):
    """Record verdict: keep, kill, merge, iterate, reposition, niche_variant."""
    if verdict not in ("keep", "kill", "merge", "iterate", "reposition", "niche_variant"):
        raise HTTPException(400, "Invalid verdict")
    conn = sqlite3.connect(str(DB_PATH))
    updates = []
    for k in ["install_rate", "completion_rate", "share_rate", "paid_conversion", "retention_d1", "retention_d7", "artifact_completion"]:
        if k in metrics:
            updates.append(f"{k} = {float(metrics[k])}")
    updates.append(f"verdict = '{verdict}'")
    updates.append(f"verdict_reason = '{reason}'")
    updates.append(f"decided_at = {now_ts()}")
    updates.append("status = 'decided'")
    conn.execute(f"UPDATE experiments SET {', '.join(updates)} WHERE id = ?", (eid,))
    conn.commit(); conn.close()
    write_receipt("experiment_verdict", "human", "success", f"exp={eid} verdict={verdict}")
    return {"experiment_id": eid, "verdict": verdict, "reason": reason}


@app.post("/api/l4/start")
async def l4_start(project: str = Body(...), mode: str = Body("agent")):
    """Start a Layer4Meter capture session."""
    sid = uuid.uuid4().hex[:12]
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("""INSERT INTO l4_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                 (sid, project, mode, now_ts(), 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "", 0, 0, "", now_ts()))
    conn.commit(); conn.close()
    write_receipt("l4_start", "system", "success", f"session={sid} project={project} mode={mode}")
    return {"session_id": sid, "project": project, "mode": mode, "status": "capturing"}


@app.post("/api/l4/stop")
async def l4_stop(session_id: str = Body(...), useful_output: str = Body(""), metrics: dict = Body({})):
    """Stop capture, compute LCI score."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM l4_sessions WHERE id = ?", (session_id,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(404, "Session not found")

    s = dict(row)
    end_time = now_ts()
    duration = end_time - s["start_time"]

    cpu = metrics.get("cpu_seconds", duration)
    gpu = metrics.get("gpu_activity", 0)
    disk = metrics.get("disk_write_mb", 0)
    file_events = metrics.get("file_event_count", 0)
    proc_spawns = metrics.get("process_spawn_count", 0)
    net_bytes = metrics.get("network_bytes", 0)
    mem_pressure = metrics.get("memory_pressure", 0)
    snap_delta = metrics.get("snapshot_delta_mb", 0)
    screen_changes = metrics.get("screen_state_changes", 0)
    agent_idle = metrics.get("agent_idle_time", 0)

    # LCI formula
    lci = (0.15 * cpu + 0.10 * gpu + 0.15 * disk + 0.10 * file_events +
           0.10 * proc_spawns + 0.05 * (net_bytes / 1e6) + 0.10 * mem_pressure +
           0.10 * snap_delta + 0.05 * screen_changes + 0.10 * agent_idle)

    # Hidden compute lift (simplified — would subtract baseline)
    hidden_lift = lci * 0.6  # placeholder

    receipt_data = {
        "session_id": session_id, "project": s["project"], "mode": s["mode"],
        "duration": round(duration, 1), "lci": round(lci, 2),
        "hidden_compute_lift": round(hidden_lift, 2),
        "useful_output": useful_output,
        "metrics": metrics,
    }
    receipt_hash = hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()

    conn.execute("""UPDATE l4_sessions SET end_time=?, cpu_seconds=?, gpu_activity=?, disk_write_mb=?,
                    file_event_count=?, process_spawn_count=?, network_bytes=?, memory_pressure=?,
                    snapshot_delta_mb=?, screen_state_changes=?, agent_idle_time=?, useful_output=?,
                    lci_score=?, hidden_compute_lift=?, receipt_hash=? WHERE id=?""",
                 (end_time, cpu, gpu, disk, file_events, proc_spawns, net_bytes, mem_pressure,
                  snap_delta, screen_changes, agent_idle, useful_output, lci, hidden_lift, receipt_hash, session_id))
    conn.commit(); conn.close()

    write_receipt("l4_stop", "system", "success", f"session={session_id} lci={lci:.2f}")
    return {"session_id": session_id, "lci_score": round(lci, 2),
            "hidden_compute_lift": round(hidden_lift, 2), "receipt_hash": receipt_hash[:24],
            "duration": round(duration, 1), "useful_output": useful_output}


@app.get("/api/l4/sessions")
async def l4_sessions():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM l4_sessions ORDER BY created_at DESC").fetchall()
    conn.close()
    return {"sessions": [dict(r) for r in rows], "count": len(rows)}


@app.get("/api/l4/receipt/{sid}")
async def l4_receipt(sid: str):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM l4_sessions WHERE id = ?", (sid,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Session not found")
    s = dict(row)
    return {
        "protocol": "Layer4Meter/1.0",
        "type": "L4_SUBSTRATE_RECEIPT",
        "session_id": sid,
        "project": s["project"],
        "mode": s["mode"],
        "duration_seconds": round(s["end_time"] - s["start_time"], 1) if s["end_time"] else 0,
        "lci_score": s["lci_score"],
        "hidden_compute_lift": s["hidden_compute_lift"],
        "useful_output": s["useful_output"],
        "receipt_hash": s["receipt_hash"],
        "planes": {
            "cpu_seconds": s["cpu_seconds"],
            "gpu_activity": s["gpu_activity"],
            "disk_write_mb": s["disk_write_mb"],
            "file_event_count": s["file_event_count"],
            "process_spawn_count": s["process_spawn_count"],
            "network_bytes": s["network_bytes"],
            "memory_pressure": s["memory_pressure"],
            "snapshot_delta_mb": s["snapshot_delta_mb"],
            "screen_state_changes": s["screen_state_changes"],
            "agent_idle_time": s["agent_idle_time"],
        },
    }


@app.get("/api/battalion")
async def battalion_status():
    """Full battalion status — squads, counts, mechanisms, experiments."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    experiments = [dict(r) for r in conn.execute("SELECT * FROM experiments").fetchall()]
    mechanisms = [dict(r) for r in conn.execute("SELECT * FROM mechanisms").fetchall()]
    variants = [dict(r) for r in conn.execute("SELECT * FROM variants").fetchall()]
    launches = conn.execute("SELECT COUNT(*) as c FROM launches").fetchone()["c"]

    squad_counts = {}
    for squad_key, squad_info in SQUADS.items():
        count = sum(1 for e in experiments if e["squad"] == squad_key)
        squad_counts[squad_key] = {"name": squad_info["name"], "count": count, "target": squad_info["target"]}

    conn.close()

    # Seed first 10 if no experiments
    if not experiments:
        seeded = []
        for app in FIRST_10_APPS:
            eid = uuid.uuid4().hex[:12]
            seeded.append(eid)
        conn = sqlite3.connect(str(DB_PATH))
        for app in FIRST_10_APPS:
            eid = uuid.uuid4().hex[:12]
            conn.execute("""INSERT INTO experiments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (eid, app["name"], app["hypothesis"], app["mechanism"], app["squad"],
                          app["user"], app["pain"], app["artifact"], "hypothesized",
                          0, 0, 0, 0, 0, 0, 0, None, None, now_ts(), None, None))
        conn.commit(); conn.close()
        experiments = seeded

    return {
        "squads": squad_counts,
        "total_experiments": len(experiments),
        "total_mechanisms": len(mechanisms),
        "total_variants": len(variants),
        "total_launches": launches,
        "first_10_apps": FIRST_10_APPS,
        "capitalfolder_spec": CAPITALFOLDER_SPEC,
    }


@app.get("/api/operator-report")
async def operator_report():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    exps = [dict(r) for r in conn.execute("SELECT * FROM experiments").fetchall()]
    mechs = [dict(r) for r in conn.execute("SELECT * FROM mechanisms").fetchall()]
    launches = conn.execute("SELECT COUNT(*) as c FROM launches").fetchone()["c"]
    variants = conn.execute("SELECT COUNT(*) as c FROM variants").fetchone()["c"]
    l4 = [dict(r) for r in conn.execute("SELECT * FROM l4_sessions WHERE end_time > 0").fetchall()]
    receipts = conn.execute("SELECT COUNT(*) as c FROM receipts").fetchone()["c"]
    conn.close()

    decided = [e for e in exps if e["verdict"]]
    kept = [e for e in decided if e["verdict"] == "keep"]
    killed = [e for e in decided if e["verdict"] == "kill"]

    proven = []
    unproven = []
    if launches > 0: proven.append(f"{launches} launches ingested as evidence")
    else: unproven.append("No launches ingested — add PH API token or ingest manually")
    if mechs: proven.append(f"{len(mechs)} mechanisms discovered")
    else: unproven.append("No mechanisms extracted — ingest launches first")
    if exps: proven.append(f"{len(exps)} experiments in battalion")
    else: unproven.append("No experiments created")
    if kept: proven.append(f"{len(kept)} experiments kept")
    if killed: proven.append(f"{len(killed)} experiments killed")
    if l4: proven.append(f"{len(l4)} L4 substrate sessions captured")
    else: unproven.append("No L4 sessions — start capturing agent compute")
    if receipts > 5: proven.append(f"{receipts} receipts written")

    next_move = "Ingest Product Hunt launches → extract mechanisms → generate variants → create experiments"
    if mechs and not variants:
        next_move = "Generate product variants from discovered mechanisms"
    elif exps and not decided:
        next_move = "Launch experiments to TestFlight, collect metrics, record verdicts"
    elif kept:
        next_move = f"Clone top mechanism into family. {len(kept)} winners to scale."

    return {
        "what_changed": f"{receipts} receipts, {launches} launches, {len(mechs)} mechanisms, {len(exps)} experiments, {variants} variants, {len(l4)} L4 sessions",
        "what_is_proven": proven,
        "what_is_unproven": unproven,
        "what_to_do_next": next_move,
        "status": "alive" if exps else "dormant",
        "proof": f"{receipts} receipts",
        "risk": "low" if receipts > 5 else "medium",
        "next_move": next_move,
    }


@app.get("/api/capitalfolder")
async def capitalfolder_spec():
    """Get the CapitalFolder app specification."""
    return CAPITALFOLDER_SPEC


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SignalForge — Market Microstructure Intelligence</title>
<style>
:root{--bg:#0a0a0a;--fg:#FF8800;--dim:#666;--green:#00FF66;--red:#FF3333;--yellow:#FFAA00;--blue:#00AAFF;--violet:#AA00FF;--card:#111;--border:#222}
*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:'SF Mono',monospace;padding:20px}
h1{color:var(--fg);font-size:22px;margin-bottom:4px}
.sub{color:var(--dim);font-size:12px;margin-bottom:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px}
.ct{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}
.cv{font-size:28px;font-weight:bold}
.sec{margin-bottom:20px}
.st{font-size:13px;color:var(--yellow);margin-bottom:10px;border-bottom:1px solid var(--border);padding-bottom:6px}
table{width:100%;border-collapse:collapse;font-size:11px}
th{text-align:left;color:var(--dim);padding:6px;border-bottom:1px solid var(--border)}
td{padding:6px;border-bottom:1px solid var(--border)}
.badge{padding:2px 8px;border-radius:3px;font-size:10px;font-weight:bold}
.b-scout{background:#1a3300;color:var(--green)}
.b-infantry{background:#003366;color:var(--blue)}
.b-artillery{background:#666600;color:var(--yellow)}
.b-capital{background:#330033;color:var(--violet)}
.b-flagship{background:#330000;color:var(--red)}
.b-keep{background:#1a3300;color:var(--green)}
.b-kill{background:#330000;color:var(--red)}
.b-iter{background:#333300;color:var(--yellow)}
.b-hyp{background:#111;color:var(--dim)}
.rpt{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:14px}
.rl{color:var(--dim);font-size:10px;text-transform:uppercase}
.rc{color:var(--fg);font-size:12px;margin-bottom:8px}
.rc ul{list-style:none;padding:0}.rc li{padding:3px 0}.rc li::before{content:"▸ ";color:var(--yellow)}
#ref{color:var(--dim);font-size:10px;float:right}
</style>
</head>
<body>
<h1>⟡ SignalForge</h1>
<div class="sub">Market Microstructure Intelligence — mechanism mining · microproduct battalion · L4 substrate</div>
<div id="ref">auto-refresh 5s</div>

<div class="grid" id="counts"></div>

<div class="sec">
  <div class="st">◆ Battalion Squads</div>
  <div class="grid" id="squads"></div>
</div>

<div class="sec">
  <div class="st">⟁ First 10 Microproduct Experiments</div>
  <div class="card"><table><thead><tr><th>App</th><th>Squad</th><th>Mechanism</th><th>User</th><th>Pain</th><th>Artifact</th><th>Status</th></tr></thead><tbody id="exps"></tbody></table></div>
</div>

<div class="sec">
  <div class="st">⧖ Operator Report</div>
  <div class="rpt" id="rpt">Loading...</div>
</div>

<script>
const B={scout:"b-scout",infantry:"b-infantry",artillery:"b-artillery",capital:"b-capital",flagship:"b-flagship"};
const V={keep:"b-keep",kill:"b-kill",iterate:"b-iter",merge:"b-iter",reposition:"b-iter",niche_variant:"b-iter"};
async function f(u){const r=await fetch(u);return r.json()}
async function refresh(){
  try{
    const[b,rpt]=await Promise.all([f("/api/battalion"),f("/api/operator-report")]);
    document.getElementById("counts").innerHTML=[
      ["Launches",b.total_launches],["Mechanisms",b.total_mechanisms],
      ["Experiments",b.total_experiments],["Variants",b.total_variants]
    ].map(([n,v])=>`<div class="card"><div class="ct">${n}</div><div class="cv">${v}</div></div>`).join("");
    document.getElementById("squads").innerHTML=Object.entries(b.squads).map(([k,s])=>
      `<div class="card"><div class="ct">${s.name}</div><div class="cv">${s.count}/${s.target}</div><div style="font-size:10px;color:var(--dim);margin-top:4px">${s.description}</div></div>`
    ).join("");
    const exps=b.first_10_apps;
    document.getElementById("exps").innerHTML=exps.map(e=>
      `<tr><td><b>${e.name}</b></td><td><span class="badge ${B[e.squad]||''}">${e.squad}</span></td><td>${e.mechanism}</td><td>${e.user}</td><td>${e.pain}</td><td>${e.artifact}</td><td><span class="badge b-hyp">hypothesized</span></td></tr>`
    ).join("");
    let h="";
    h+=`<div class="rl">What Changed</div><div class="rc">${rpt.what_changed}</div>`;
    h+=`<div class="rl">Proven</div><div class="rc"><ul>${rpt.what_is_proven.map(p=>"<li>"+p+"</li>").join("")}</ul></div>`;
    h+=`<div class="rl">Unproven</div><div class="rc"><ul>${rpt.what_is_unproven.map(p=>"<li>"+p+"</li>").join("")}</ul></div>`;
    h+=`<div class="rl">Next Move</div><div class="rc">${rpt.what_to_do_next}</div>`;
    h+=`<div style="margin-top:12px;border-top:1px solid var(--border);padding-top:10px">`;
    h+=`<span class="rl">STATUS:</span> <span style="color:var(--green)">${rpt.status}</span> &nbsp; `;
    h+=`<span class="rl">PROOF:</span> ${rpt.proof} &nbsp; `;
    h+=`<span class="rl">RISK:</span> ${rpt.risk} &nbsp; `;
    h+=`<span class="rl">NEXT:</span> ${rpt.next_move}</div>`;
    document.getElementById("rpt").innerHTML=h;
  }catch(e){console.error(e)}
}
refresh();setInterval(refresh,5000);
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="SignalForge — Market Microstructure Intelligence")
    parser.add_argument("--port", type=int, default=7863, help="Port (default 7863)")
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    # Seed first 10 experiments
    conn = sqlite3.connect(str(DB_PATH))
    existing = conn.execute("SELECT COUNT(*) FROM experiments").fetchone()[0]
    if existing == 0:
        for app in FIRST_10_APPS:
            eid = uuid.uuid4().hex[:12]
            conn.execute("""INSERT INTO experiments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                         (eid, app["name"], app["hypothesis"], app["mechanism"], app["squad"],
                          app["user"], app["pain"], app["artifact"], "hypothesized",
                          0, 0, 0, 0, 0, 0, 0, None, None, now_ts(), None, None))
        conn.commit()
        write_receipt("battalion_seed", "system", "success", "seeded first 10 experiments")
    conn.close()

    write_receipt("signalforge_start", "system", "success", f"port={args.port}")

    print(f"""
  ╔═══════════════════════════════════════════════════════════════╗
  ║                                                               ║
  ║   SIGNALFORGE                                                 ║
  ║   Market Microstructure Intelligence                          ║
  ║                                                               ║
  ║   Observe launches → extract mechanisms →                     ║
  ║   generate variants → run experiments → decide                ║
  ║                                                               ║
  ║   Battalion: 5 squads · 10 seeded experiments                 ║
  ║   L4 Meter: substrate capture ready                           ║
  ║   CapitalFolder: spec ready                                   ║
  ║                                                               ║
  ╚═══════════════════════════════════════════════════════════════╝

  Dashboard: http://localhost:{args.port}
  Health:    http://localhost:{args.port}/health
  Battalion: http://localhost:{args.port}/api/battalion
  CapitalFolder spec: http://localhost:{args.port}/api/capitalfolder
""")

    uvicorn.run("signalforge:app", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
