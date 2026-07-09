#!/usr/bin/env python3
"""
OverAgent Production Control Plane

The single dashboard that answers:
  Is the system alive?
  Is attention increasing?
  Did the latest change improve buyer intent?
  Should we keep, rollback, wait, or test next?

Endpoints:
  GET  /                          — Dashboard (HTML)
  GET  /health                    — Health check
  POST /api/metrics/ingest        — Ingest first-party metrics
  GET  /api/kpis                  — Current KPI scores
  GET  /api/kpis/history          — KPI history
  GET  /api/receipts              — Receipt ledger
  POST /api/receipts/write        — Write a receipt
  GET  /api/decisions             — Decision gate state
  POST /api/decisions/update      — Update decision state
  GET  /api/systems               — List all production systems
  GET  /api/operator-report       — Operator report

Run:
  python3 overagent_control_plane.py [--port 7862]
"""

import argparse
import hashlib
import json
import os
import sqlite3
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Body, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI(title="OverAgent Control Plane", version="1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

DATA_DIR = Path(os.environ.get("OVERAGENT_DATA", str(Path(__file__).parent / "overagent_data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "control_plane.db"


def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL,
        source TEXT,
        metric_name TEXT,
        metric_value REAL,
        metadata TEXT
    );
    CREATE TABLE IF NOT EXISTS receipts (
        receipt_id TEXT PRIMARY KEY,
        timestamp REAL,
        action TEXT,
        actor TEXT,
        result TEXT,
        evidence TEXT,
        metadata TEXT
    );
    CREATE TABLE IF NOT EXISTS decisions (
        decision_id TEXT PRIMARY KEY,
        timestamp REAL,
        experiment_id TEXT,
        state TEXT,
        reason TEXT,
        actor TEXT
    );
    CREATE TABLE IF NOT EXISTS kpi_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp REAL,
        immortality REAL,
        virality REAL,
        conversion REAL,
        proof REAL,
        raw_metrics TEXT
    );
    CREATE TABLE IF NOT EXISTS systems (
        system_id TEXT PRIMARY KEY,
        name TEXT,
        endpoint TEXT,
        status TEXT DEFAULT 'unknown',
        last_check REAL,
        receipt_count INTEGER DEFAULT 0
    );
    """)
    conn.commit()
    conn.close()


init_db()


def now_ts():
    return time.time()


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def compute_kpis(metrics: list) -> dict:
    """Compute KPI scores from raw metrics."""
    m = {}
    for metric in metrics:
        m[metric["metric_name"]] = metric["metric_value"]

    # Immortality: availability, durability, visibility, proof_density, age
    availability = min(1.0, m.get("uptime_seconds", 0) / 86400)
    durability = min(1.0, m.get("receipt_count", 0) / 100)
    visibility = min(1.0, m.get("endpoint_count", 0) / 20)
    proof_density = min(1.0, m.get("receipted_actions", 0) / max(m.get("total_actions", 1), 1))
    age_factor = min(1.0, m.get("system_age_hours", 0) / 720)
    immortality = (availability * 0.3) + (durability * 0.2) + (visibility * 0.2) + (proof_density * 0.15) + (age_factor * 0.15)

    # Virality: view_velocity, contact_click_lift, acceleration, spread
    view_velocity = min(1.0, m.get("view_velocity", 0) / 100)
    contact_click_lift = min(1.0, max(0, m.get("contact_click_lift", 0)) / 50)
    acceleration = min(1.0, max(0, m.get("acceleration", 0)) / 25)
    spread = min(1.0, m.get("spread_score", 0) / 10)
    virality = (view_velocity * 0.35) + (contact_click_lift * 0.25) + (acceleration * 0.2) + (spread * 0.2)

    # Conversion
    profile_views = m.get("profile_views", 0)
    contact_actions = m.get("contact_actions", 0)
    conversion = contact_actions / max(profile_views, 1) if profile_views > 0 else 0.0

    # Proof
    total_actions = m.get("total_actions", 0)
    receipted = m.get("receipted_actions", 0)
    proof = receipted / max(total_actions, 1) if total_actions > 0 else 0.0

    return {
        "immortality": round(immortality, 4),
        "virality": round(virality, 4),
        "conversion": round(conversion, 4),
        "proof": round(proof, 4),
        "raw_metric_count": len(m),
    }


def get_recent_metrics(hours=24):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cutoff = now_ts() - (hours * 3600)
    rows = conn.execute("SELECT * FROM metrics WHERE timestamp > ? ORDER BY timestamp DESC", (cutoff,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_receipts(limit=50):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM receipts ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_decisions(limit=20):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM decisions ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_kpi_history(limit=24):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM kpi_history ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_systems():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM systems").fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "OverAgent Control Plane",
        "version": "1.0",
        "timestamp": now_iso(),
    }


@app.post("/api/metrics/ingest")
async def ingest_metrics(
    source: str = Body(...),
    metrics: dict = Body(...),
):
    """Ingest first-party metrics. No scraping. No third-party data."""
    conn = sqlite3.connect(str(DB_PATH))
    ts = now_ts()
    for name, value in metrics.items():
        if isinstance(value, (int, float)):
            conn.execute(
                "INSERT INTO metrics (timestamp, source, metric_name, metric_value, metadata) VALUES (?, ?, ?, ?, ?)",
                (ts, source, name, float(value), json.dumps({"ingested_at": now_iso()}))
            )
    conn.commit()

    # Recompute KPIs and store
    recent = get_recent_metrics(24)
    kpis = compute_kpis(recent)
    conn.execute(
        "INSERT INTO kpi_history (timestamp, immortality, virality, conversion, proof, raw_metrics) VALUES (?, ?, ?, ?, ?, ?)",
        (ts, kpis["immortality"], kpis["virality"], kpis["conversion"], kpis["proof"], json.dumps(len(recent)))
    )
    conn.commit()
    conn.close()

    # Write receipt
    receipt_id = write_receipt("metrics_ingest", "system", "success", f"source={source} count={len(metrics)}")

    return {
        "status": "ok",
        "ingested": len(metrics),
        "source": source,
        "kpis": kpis,
        "receipt_id": receipt_id,
    }


@app.get("/api/kpis")
async def get_kpis():
    """Current KPI scores."""
    metrics = get_recent_metrics(24)
    kpis = compute_kpis(metrics)
    return {
        "kpis": kpis,
        "metric_count": len(metrics),
        "computed_at": now_iso(),
    }


@app.get("/api/kpis/history")
async def kpi_history():
    """KPI history (last 24 entries)."""
    return {"history": get_kpi_history(24)}


@app.get("/api/receipts")
async def list_receipts(limit: int = 50):
    """Receipt ledger."""
    return {"receipts": get_receipts(limit), "count": len(get_receipts(limit))}


@app.post("/api/receipts/write")
async def write_receipt_endpoint(
    action: str = Body(...),
    actor: str = Body("system"),
    result: str = Body("success"),
    evidence: str = Body(""),
    metadata: dict = Body({}),
):
    """Write a receipt. No receipt, no reality."""
    receipt_id = write_receipt(action, actor, result, evidence, metadata)
    return {"receipt_id": receipt_id, "status": "written"}


def write_receipt(action, actor, result, evidence, metadata=None):
    receipt_id = uuid.uuid4().hex[:16]
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO receipts (receipt_id, timestamp, action, actor, result, evidence, metadata) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (receipt_id, now_ts(), action, actor, result, evidence, json.dumps(metadata or {}))
    )
    conn.commit()
    conn.close()
    return receipt_id


@app.get("/api/decisions")
async def list_decisions():
    """Decision gate state."""
    return {"decisions": get_decisions(20)}


@app.post("/api/decisions/update")
async def update_decision(
    experiment_id: str = Body(...),
    state: str = Body(...),
    reason: str = Body(""),
    actor: str = Body("human"),
):
    """Update decision gate. States: keep, rollback, wait, test."""
    if state not in ("keep", "rollback", "wait", "test"):
        raise HTTPException(400, f"Invalid state: {state}. Must be: keep, rollback, wait, test")

    decision_id = uuid.uuid4().hex[:16]
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO decisions (decision_id, timestamp, experiment_id, state, reason, actor) VALUES (?, ?, ?, ?, ?, ?)",
        (decision_id, now_ts(), experiment_id, state, reason, actor)
    )
    conn.commit()
    conn.close()

    write_receipt("decision_update", actor, "success", f"experiment={experiment_id} state={state}", {"reason": reason})

    return {"decision_id": decision_id, "state": state, "experiment_id": experiment_id}


@app.get("/api/systems")
async def list_systems():
    """List all registered production systems."""
    return {"systems": get_systems()}


@app.post("/api/systems/register")
async def register_system(
    name: str = Body(...),
    endpoint: str = Body(...),
):
    """Register a production system for tracking."""
    system_id = uuid.uuid4().hex[:12]
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO systems (system_id, name, endpoint, status, last_check) VALUES (?, ?, ?, 'registered', ?)",
        (system_id, name, endpoint, now_ts())
    )
    conn.commit()
    conn.close()
    write_receipt("system_register", "system", "success", f"name={name} endpoint={endpoint}")
    return {"system_id": system_id, "name": name, "endpoint": endpoint}


@app.get("/api/operator-report")
async def operator_report():
    """Generate operator report: what changed, what is proven, what is unproven, what to do next."""
    metrics = get_recent_metrics(24)
    kpis = compute_kpis(metrics)
    receipts = get_receipts(20)
    decisions = get_decisions(10)
    systems = get_systems()

    receipt_count = len(get_receipts(10000))
    pass_count = sum(1 for r in receipts if r["result"] == "success")
    fail_count = sum(1 for r in receipts if r["result"] == "failure")

    proven = []
    unproven = []

    if kpis["proof"] > 0.5:
        proven.append(f"Proof density: {kpis['proof']:.0%} of actions have receipts")
    else:
        unproven.append(f"Proof density low: {kpis['proof']:.0%}")

    if kpis["immortality"] > 0.3:
        proven.append(f"System immortality: {kpis['immortality']:.0%}")
    else:
        unproven.append("System immortality below threshold")

    if receipt_count > 10:
        proven.append(f"{receipt_count} receipts written")
    else:
        unproven.append(f"Only {receipt_count} receipts — need more evidence")

    if systems:
        proven.append(f"{len(systems)} systems registered")
    else:
        unproven.append("No systems registered — register production endpoints")

    if kpis["conversion"] > 0:
        proven.append(f"Conversion rate: {kpis['conversion']:.1%}")
    else:
        unproven.append("No conversion data — no profile views or contact actions recorded")

    recent_decisions = [d for d in decisions if d["state"] in ("keep", "rollback")]
    if recent_decisions:
        latest = recent_decisions[0]
        next_move = f"Latest decision: {latest['state']} on {latest['experiment_id']}. "
        if latest["state"] == "keep":
            next_move += "Scale what works."
        elif latest["state"] == "rollback":
            next_move += "Revert and test alternative."
    else:
        next_move = "No decisions yet. Run an experiment, measure, then decide: keep, rollback, wait, or test."

    return {
        "report": {
            "what_changed": f"{receipt_count} receipts, {len(metrics)} metrics, {len(decisions)} decisions",
            "what_is_proven": proven,
            "what_is_unproven": unproven,
            "what_to_do_next": next_move,
        },
        "kpis": kpis,
        "counts": {
            "receipts": receipt_count,
            "metrics": len(metrics),
            "decisions": len(decisions),
            "systems": len(systems),
            "recent_pass": pass_count,
            "recent_fail": fail_count,
        },
        "status": "alive" if kpis["immortality"] > 0.1 else "dormant",
        "proof": f"{kpis['proof']:.0%}",
        "risk": "low" if kpis["proof"] > 0.5 else "medium" if kpis["proof"] > 0.2 else "high",
        "next_move": next_move,
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """The OverAgent dashboard."""
    return """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OverAgent Control Plane</title>
<style>
:root {
  --bg: #0a0a0a; --fg: #FF8800; --dim: #666; --green: #00FF66; --red: #FF3333;
  --yellow: #FFAA00; --blue: #00AAFF; --violet: #AA00FF; --card: #111;
  --border: #222;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: var(--bg); color: var(--fg); font-family: 'SF Mono', monospace; padding: 20px; }
h1 { color: var(--fg); font-size: 24px; margin-bottom: 4px; }
.subtitle { color: var(--dim); font-size: 12px; margin-bottom: 20px; }
.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 20px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
.card-title { font-size: 11px; color: var(--dim); text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
.kpi-value { font-size: 32px; font-weight: bold; }
.kpi-bar { height: 4px; background: var(--border); border-radius: 2px; margin-top: 8px; overflow: hidden; }
.kpi-fill { height: 100%; border-radius: 2px; transition: width 0.5s; }
.section { margin-bottom: 20px; }
.section-title { font-size: 14px; color: var(--yellow); margin-bottom: 12px; border-bottom: 1px solid var(--border); padding-bottom: 8px; }
table { width: 100%; border-collapse: collapse; font-size: 12px; }
th { text-align: left; color: var(--dim); padding: 8px; border-bottom: 1px solid var(--border); }
td { padding: 8px; border-bottom: 1px solid var(--border); }
.glyph { font-size: 14px; }
.status-ok { color: var(--green); } .status-fail { color: var(--red); } .status-warn { color: var(--yellow); }
.report { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 16px; }
.report-section { margin-bottom: 12px; }
.report-label { color: var(--dim); font-size: 11px; text-transform: uppercase; }
.report-content { color: var(--fg); font-size: 13px; }
.report-content ul { list-style: none; padding-left: 0; }
.report-content li { padding: 4px 0; }
.report-content li::before { content: "▸ "; color: var(--yellow); }
#refresh { color: var(--dim); font-size: 11px; float: right; }
</style>
</head>
<body>
<h1>◉ OverAgent Control Plane</h1>
<div class="subtitle">Proof Commander Mode — evidence-only RevenueOps</div>
<div id="refresh">auto-refresh 5s</div>

<div class="grid" id="kpis">
  <div class="card"><div class="card-title">Immortality</div><div class="kpi-value" id="kpi-imm">--</div><div class="kpi-bar"><div class="kpi-fill" id="bar-imm" style="background:var(--green);width:0%"></div></div></div>
  <div class="card"><div class="card-title">Virality</div><div class="kpi-value" id="kpi-vir">--</div><div class="kpi-bar"><div class="kpi-fill" id="bar-vir" style="background:var(--blue);width:0%"></div></div></div>
  <div class="card"><div class="card-title">Conversion</div><div class="kpi-value" id="kpi-con">--</div><div class="kpi-bar"><div class="kpi-fill" id="bar-con" style="background:var(--yellow);width:0%"></div></div></div>
  <div class="card"><div class="card-title">Proof</div><div class="kpi-value" id="kpi-prf">--</div><div class="kpi-bar"><div class="kpi-fill" id="bar-prf" style="background:var(--violet);width:0%"></div></div></div>
</div>

<div class="grid">
  <div class="card"><div class="card-title">Receipts</div><div class="kpi-value" id="cnt-receipts">--</div></div>
  <div class="card"><div class="card-title">Metrics (24h)</div><div class="kpi-value" id="cnt-metrics">--</div></div>
  <div class="card"><div class="card-title">Decisions</div><div class="kpi-value" id="cnt-decisions">--</div></div>
  <div class="card"><div class="card-title">Systems</div><div class="kpi-value" id="cnt-systems">--</div></div>
</div>

<div class="section">
  <div class="section-title">◆ Operator Report</div>
  <div class="report" id="report">Loading...</div>
</div>

<div class="section">
  <div class="section-title">⟁ Recent Receipts</div>
  <div class="card"><table><thead><tr><th>ID</th><th>Action</th><th>Result</th><th>Time</th></tr></thead><tbody id="receipts-table"></tbody></table></div>
</div>

<div class="section">
  <div class="section-title">⧖ Decision Gate</div>
  <div class="card"><table><thead><tr><th>Experiment</th><th>State</th><th>Reason</th><th>Actor</th></tr></thead><tbody id="decisions-table"></tbody></table></div>
</div>

<script>
const BASE = "";
async function fetchJSON(url) { const r = await fetch(url); return r.json(); }
function pct(v) { return (v * 100).toFixed(1) + "%"; }
function fmtTime(ts) { return new Date(ts * 1000).toLocaleTimeString(); }

async function refresh() {
  try {
    const [kpis, report, receipts, decisions, systems] = await Promise.all([
      fetchJSON(BASE + "/api/kpis"),
      fetchJSON(BASE + "/api/operator-report"),
      fetchJSON(BASE + "/api/receipts"),
      fetchJSON(BASE + "/api/decisions"),
      fetchJSON(BASE + "/api/systems"),
    ]);

    document.getElementById("kpi-imm").textContent = pct(kpis.kpis.immortality);
    document.getElementById("kpi-vir").textContent = pct(kpis.kpis.virality);
    document.getElementById("kpi-con").textContent = pct(kpis.kpis.conversion);
    document.getElementById("kpi-prf").textContent = pct(kpis.kpis.proof);
    document.getElementById("bar-imm").style.width = (kpis.kpis.immortality * 100) + "%";
    document.getElementById("bar-vir").style.width = (kpis.kpis.virality * 100) + "%";
    document.getElementById("bar-con").style.width = (kpis.kpis.conversion * 100) + "%";
    document.getElementById("bar-prf").style.width = (kpis.kpis.proof * 100) + "%";

    document.getElementById("cnt-receipts").textContent = report.counts.receipts;
    document.getElementById("cnt-metrics").textContent = report.counts.metrics;
    document.getElementById("cnt-decisions").textContent = report.counts.decisions;
    document.getElementById("cnt-systems").textContent = report.counts.systems;

    let reportHTML = "";
    reportHTML += '<div class="report-section"><div class="report-label">What Changed</div><div class="report-content">' + report.report.what_changed + '</div></div>';
    reportHTML += '<div class="report-section"><div class="report-label">Proven</div><div class="report-content"><ul>' + report.report.what_is_proven.map(p => "<li>" + p + "</li>").join("") + '</ul></div></div>';
    reportHTML += '<div class="report-section"><div class="report-label">Unproven</div><div class="report-content"><ul>' + report.report.what_is_unproven.map(p => "<li>" + p + "</li>").join("") + '</ul></div></div>';
    reportHTML += '<div class="report-section"><div class="report-label">Next Move</div><div class="report-content">' + report.report.what_to_do_next + '</div></div>';
    reportHTML += '<div class="report-section" style="margin-top:16px;border-top:1px solid var(--border);padding-top:12px"><div class="report-label">STATUS</div><div class="report-content status-' + (report.status === 'alive' ? 'ok' : 'warn') + '">' + report.status + '</div>';
    reportHTML += '<div class="report-label" style="margin-top:8px">PROOF</div><div class="report-content">' + report.proof + '</div>';
    reportHTML += '<div class="report-label" style="margin-top:8px">RISK</div><div class="report-content status-' + (report.risk === 'low' ? 'ok' : report.risk === 'medium' ? 'warn' : 'fail') + '">' + report.risk + '</div>';
    reportHTML += '<div class="report-label" style="margin-top:8px">NEXT MOVE</div><div class="report-content">' + report.next_move + '</div></div>';
    document.getElementById("report").innerHTML = reportHTML;

    document.getElementById("receipts-table").innerHTML = receipts.receipts.slice(0, 10).map(r =>
      '<tr><td class="glyph">' + r.receipt_id + '</td><td>' + r.action + '</td><td class="status-' + (r.result === 'success' ? 'ok' : 'fail') + '">' + r.result + '</td><td>' + fmtTime(r.timestamp) + '</td></tr>'
    ).join("");

    document.getElementById("decisions-table").innerHTML = decisions.decisions.slice(0, 10).map(d =>
      '<tr><td>' + d.experiment_id + '</td><td class="status-' + (d.state === 'keep' ? 'ok' : d.state === 'rollback' ? 'fail' : 'warn') + '">' + d.state + '</td><td>' + d.reason + '</td><td>' + d.actor + '</td></tr>'
    ).join("");

  } catch (e) {
    console.error(e);
  }
}
refresh();
setInterval(refresh, 5000);
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser(description="OverAgent Control Plane")
    parser.add_argument("--port", type=int, default=7862, help="Port (default 7862)")
    parser.add_argument("--host", default="0.0.0.0", help="Host")
    args = parser.parse_args()

    # Write startup receipt
    write_receipt("control_plane_start", "system", "success", f"port={args.port}")

    print(f"""
  ╔═══════════════════════════════════════════════════════════════╗
  ║                                                               ║
  ║   OVERAGENT CONTROL PLANE                                     ║
  ║   Proof Commander Mode                                        ║
  ║                                                               ║
  ║   Is the system alive?                                        ║
  ║   Is attention increasing?                                    ║
  ║   Did the latest change improve buyer intent?                 ║
  ║   Should we keep, rollback, wait, or test next?               ║
  ║                                                               ║
  ║   KPIs: Immortality · Virality · Conversion · Proof           ║
  ║                                                               ║
  ╚═══════════════════════════════════════════════════════════════╝

  Dashboard: http://localhost:{args.port}
  Health:    http://localhost:{args.port}/health
  KPIs:      http://localhost:{args.port}/api/kpis
  Report:    http://localhost:{args.port}/api/operator-report
  Data:      {DATA_DIR}
""")

    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
