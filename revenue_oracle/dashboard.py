"""
Dashboard — FastAPI app with all dashboard routes + API endpoints.

Dashboard routes:
  /dashboard, /artifacts, /artifact/:id, /packets, /tokens,
  /pages, /revenue, /risks, /receipts, /settings

API endpoints:
  GET /health
  GET /ollama/status
  POST /artifacts/intake
  GET /artifacts
  GET /artifacts/{artifact_id}
  POST /artifacts/{artifact_id}/packet
  GET /packets/{packet_hash}
  POST /packets/{packet_hash}/verify
  POST /artifacts/{artifact_id}/landing-page
  POST /landing-pages/{page_id}/deploy
  POST /artifacts/{artifact_id}/token/manifest
  POST /artifacts/{artifact_id}/token/mint-devnet-nontransferable
  POST /revenue/checkout
  GET /revenue
  GET /receipts/{receipt_hash}
"""

import hashlib
import json
import time
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from .schema import OracleDB, ArtifactRecord, EvidencePacket, RevenueReceipt
from .receipt_ledger import ReceiptLedger
from .ollama_client import OllamaClient
from .evidence_packet import EvidencePacketBuilder
from .risk_engine import RiskEngine, TokenMode
from .landing_page import LandingPageGenerator
from .revenue_module import RevenueModule, ProductType
from .token_engine import TokenEngine
from .bmma_builder import BMMABuilder
from .agent_loop import AgentLoop


class IntakeRequest(BaseModel):
    source_type: str
    source_uri_or_path: str
    owner: str = "default"
    claims: list = []
    risk_flags: list = []
    license_flags: list = []
    reproducibility_notes: str = ""
    limitations: str = ""


class PacketRequest(BaseModel):
    claims: list = []
    risk_flags: list = []
    license_flags: list = []
    reproducibility_notes: str = ""
    limitations: str = ""


class LandingPageRequest(BaseModel):
    asset_name: str = ""
    thesis: str = ""
    problem_solved: str = ""
    utility_description: str = ""


class DeployRequest(BaseModel):
    target: str = "local"  # local, vercel, netlify, static


class TokenManifestRequest(BaseModel):
    token_name: str = ""
    token_symbol: str = ""
    token_mode_requested: str = "proof_only"
    compliance_approved: bool = False
    human_approved: bool = False
    disclaimers_present: bool = True


class DevnetMintRequest(BaseModel):
    compliance_approved: bool = False


class CheckoutRequest(BaseModel):
    artifact_id: str
    packet_hash: str
    product_type: str
    amount: float
    buyer_reference: str
    currency: str = "USD"
    payment_provider: str = "stripe"


class ConfirmPaymentRequest(BaseModel):
    flow_id: str
    payment_provider: str = ""
    external_confirmation: dict = {}


class SettingsRequest(BaseModel):
    key: str
    value: str


class BMMARequest(BaseModel):
    question: str = ""
    claims: list = []
    transcript: str = ""
    visual_evidence_segments: list = []
    truth_labels: list = []
    rights_labels: list = []
    revenue_ledger: dict = {}
    machine_scores: dict = {}
    bond_amount_usd: float = 0.0
    rubric_id: str = "video_evidence_quality_v1"
    producer_id: str = "default"


def create_app(db_path: str = "revenue_oracle.db") -> FastAPI:
    """Create the FastAPI dashboard app."""
    app = FastAPI(title="Evidence Asset Revenue Oracle", version="1.0.0")

    db = OracleDB(db_path)
    ollama = OllamaClient()
    receipt_ledger = ReceiptLedger(db)
    packet_builder = EvidencePacketBuilder(db)
    risk_engine = RiskEngine(db)
    page_generator = LandingPageGenerator(db)
    revenue_module = RevenueModule(db, receipt_ledger)
    token_engine = TokenEngine(db, receipt_ledger)
    bmma_builder = BMMABuilder(db, receipt_ledger)
    agent = AgentLoop(db, ollama, ollama_enabled=True, create_tokens=True)

    # --- Health ---

    @app.get("/health")
    async def health():
        return {
            "status": "ok",
            "timestamp": time.time(),
            "db": db_path,
        }

    @app.get("/ollama/status")
    async def ollama_status():
        return ollama.status()

    # --- Artifact Intake ---

    @app.post("/artifacts/intake")
    async def intake(req: IntakeRequest):
        source_hash = packet_builder.compute_source_hash(req.source_uri_or_path)
        manifest_hash = packet_builder.compute_manifest_hash(
            source_hash, req.source_type, req.owner
        )
        artifact_id = hashlib.sha256(
            f"artifact:{source_hash}:{req.owner}:{time.time()}".encode()
        ).hexdigest()[:16]

        rec = ArtifactRecord(
            artifact_id=artifact_id,
            source_type=req.source_type,
            source_uri_or_path=req.source_uri_or_path,
            owner=req.owner,
            created_at=time.time(),
            source_hash=source_hash,
            manifest_hash=manifest_hash,
        )
        db.insert_artifact(rec)
        receipt_ledger.write(
            receipt_type="artifact_intake",
            artifact_id=artifact_id,
            data=rec.to_dict(),
            input_hash=source_hash,
        )
        return rec.to_dict()

    @app.get("/artifacts")
    async def list_artifacts():
        return db.list_artifacts()

    @app.get("/artifacts/{artifact_id}")
    async def get_artifact(artifact_id: str):
        artifact = db.get_artifact(artifact_id)
        if not artifact:
            raise HTTPException(404, "Artifact not found")
        return artifact

    # --- Evidence Packets ---

    @app.post("/artifacts/{artifact_id}/packet")
    async def build_packet(artifact_id: str, req: PacketRequest):
        artifact = db.get_artifact(artifact_id)
        if not artifact:
            raise HTTPException(404, "Artifact not found")

        rec = ArtifactRecord(**artifact)
        packet = packet_builder.build_packet(
            artifact=rec,
            claims=req.claims,
            risk_flags=req.risk_flags,
            license_flags=req.license_flags,
            reproducibility_notes=req.reproducibility_notes,
            limitations=req.limitations,
        )
        receipt_ledger.write(
            receipt_type="packet_creation",
            artifact_id=artifact_id,
            data={"packet_hash": packet.packet_hash},
            output_hash=packet.packet_hash,
            packet_hash=packet.packet_hash,
        )
        return packet.to_dict()

    @app.get("/packets/{packet_hash}")
    async def get_packet(packet_hash: str):
        packet = db.get_evidence_packet(packet_hash)
        if not packet:
            raise HTTPException(404, "Packet not found")
        return packet

    @app.post("/packets/{packet_hash}/verify")
    async def verify_packet(packet_hash: str):
        return packet_builder.verify_packet(packet_hash)

    # --- Landing Pages ---

    @app.post("/artifacts/{artifact_id}/landing-page")
    async def generate_landing_page(artifact_id: str, req: LandingPageRequest):
        artifact = db.get_artifact(artifact_id)
        if not artifact:
            raise HTTPException(404, "Artifact not found")

        # Find latest packet for this artifact
        packets = db.list_artifacts()
        packet = db.get_evidence_packet(
            hashlib.sha256(artifact_id.encode()).hexdigest()[:64]
        )
        # Use the artifact's source hash to find packet
        all_packets = db.list_artifacts(limit=1000)
        # Get the packet from the evidence_packets table
        conn = db._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM evidence_packets WHERE artifact_id = ? ORDER BY created_at DESC LIMIT 1",
                (artifact_id,),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            raise HTTPException(400, "No evidence packet found for artifact")
        packet_data = dict(row)
        for k in ("claims", "risk_flags", "license_flags", "provenance_chain", "receipt_list"):
            packet_data[k] = json.loads(packet_data[k])

        # Get risk report
        conn = db._get_conn()
        try:
            risk_row = conn.execute(
                "SELECT * FROM risk_reports WHERE artifact_id = ? ORDER BY created_at DESC LIMIT 1",
                (artifact_id,),
            ).fetchone()
        finally:
            conn.close()

        risk_report = dict(risk_row) if risk_row else {}
        if risk_report and "blockers" in risk_report:
            risk_report["blockers"] = json.loads(risk_report["blockers"])

        page = page_generator.generate(
            artifact=artifact,
            packet=packet_data,
            risk_report=risk_report,
            asset_name=req.asset_name,
            thesis=req.thesis,
            problem_solved=req.problem_solved,
            utility_description=req.utility_description,
        )
        receipt_ledger.write(
            receipt_type="landing_page_generation",
            artifact_id=artifact_id,
            data={"page_id": page.page_id, "page_hash": page.page_hash},
            output_hash=page.page_hash,
            packet_hash=packet_data.get("packet_hash", ""),
        )
        return page.to_dict()

    @app.post("/landing-pages/{page_id}/deploy")
    async def deploy_page(page_id: str, req: DeployRequest):
        page = db.get_landing_page(page_id)
        if not page:
            raise HTTPException(404, "Landing page not found")

        deployment_id = hashlib.sha256(
            f"deploy:{page_id}:{req.target}:{time.time()}".encode()
        ).hexdigest()[:16]

        if req.target == "local":
            url = f"/pages/{page_id}"
            status = "deployed_local"
        else:
            url = ""
            status = "pending"

        db.insert_deployment(
            deployment_id=deployment_id,
            page_id=page_id,
            target=req.target,
            url=url,
            page_hash=page["page_hash"],
            packet_hash=page["packet_hash"],
            status=status,
        )
        receipt_ledger.write(
            receipt_type="deployment",
            artifact_id=page["artifact_id"],
            data={"deployment_id": deployment_id, "target": req.target, "url": url},
            packet_hash=page["packet_hash"],
        )
        return {"deployment_id": deployment_id, "url": url, "status": status}

    # --- Token Manifests ---

    @app.post("/artifacts/{artifact_id}/token/manifest")
    async def create_token_manifest(artifact_id: str, req: TokenManifestRequest):
        artifact = db.get_artifact(artifact_id)
        if not artifact:
            raise HTTPException(404, "Artifact not found")

        # Get latest packet
        conn = db._get_conn()
        try:
            pkt_row = conn.execute(
                "SELECT packet_hash FROM evidence_packets WHERE artifact_id = ? ORDER BY created_at DESC LIMIT 1",
                (artifact_id,),
            ).fetchone()
            risk_row = conn.execute(
                "SELECT * FROM risk_reports WHERE artifact_id = ? ORDER BY created_at DESC LIMIT 1",
                (artifact_id,),
            ).fetchone()
        finally:
            conn.close()

        if not pkt_row:
            raise HTTPException(400, "No evidence packet found")

        packet_hash = pkt_row["packet_hash"]
        risk_report = dict(risk_row) if risk_row else {}
        if risk_report and "blockers" in risk_report:
            risk_report["blockers"] = json.loads(risk_report["blockers"])

        # Re-evaluate risk with requested token mode
        risk_report = risk_engine.evaluate(
            artifact_id=artifact_id,
            packet_hash=packet_hash,
            token_mode_requested=req.token_mode_requested,
            compliance_approved=req.compliance_approved,
            human_approved=req.human_approved,
            disclaimers_present=req.disclaimers_present,
        )

        try:
            manifest = token_engine.create_manifest(
                artifact_id=artifact_id,
                packet_hash=packet_hash,
                risk_report=risk_report,
                token_name=req.token_name,
                token_symbol=req.token_symbol,
            )
            return manifest.to_dict()
        except ValueError as e:
            raise HTTPException(403, str(e))

    @app.post("/artifacts/{artifact_id}/token/mint-devnet-nontransferable")
    async def mint_devnet(artifact_id: str, req: DevnetMintRequest):
        # Get latest manifest
        manifests = db.list_token_manifests(limit=100)
        manifest_data = None
        for m in manifests:
            if m["artifact_id"] == artifact_id and m["token_mode"] != "disabled":
                manifest_data = m
                break

        if not manifest_data:
            raise HTTPException(404, "No token manifest found for artifact")

        from .token_engine import TokenManifest
        manifest = TokenManifest(
            manifest_id=manifest_data["manifest_id"],
            artifact_id=manifest_data["artifact_id"],
            packet_hash=manifest_data["packet_hash"],
            token_mode=manifest_data["token_mode"],
            token_name=manifest_data["token_name"],
            token_symbol=manifest_data["token_symbol"],
            metadata_json=manifest_data["metadata_json"],
            mint_address=manifest_data["mint_address"],
            tx_hash=manifest_data["tx_hash"],
            status=manifest_data["status"],
            created_at=manifest_data["created_at"],
        )

        try:
            manifest = token_engine.mint_devnet_nontransferable(
                manifest, compliance_approved=req.compliance_approved
            )
            return manifest.to_dict()
        except ValueError as e:
            raise HTTPException(403, str(e))

    # --- Revenue ---

    @app.post("/revenue/checkout")
    async def create_checkout(req: CheckoutRequest):
        try:
            flow = revenue_module.create_checkout(
                artifact_id=req.artifact_id,
                packet_hash=req.packet_hash,
                product_type=req.product_type,
                amount=req.amount,
                buyer_reference=req.buyer_reference,
                currency=req.currency,
                payment_provider=req.payment_provider,
            )
            return flow.to_dict()
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/revenue/confirm-payment")
    async def confirm_payment(req: ConfirmPaymentRequest):
        # Search receipts for checkout_creation with this flow_id
        conn = db._get_conn()
        try:
            rows = conn.execute(
                "SELECT data FROM receipts WHERE receipt_type = 'checkout_creation' ORDER BY rowid DESC LIMIT 200"
            ).fetchall()
        finally:
            conn.close()
        flow_data = None
        for r in rows:
            try:
                d = json.loads(r["data"]) if isinstance(r["data"], str) else r["data"]
                if d.get("flow_id") == req.flow_id:
                    flow_data = d
                    break
            except (json.JSONDecodeError, TypeError, KeyError):
                continue
        if not flow_data:
            raise HTTPException(404, "Flow not found")
        from .revenue_module import RevenueFlow
        flow = RevenueFlow(
            flow_id=flow_data["flow_id"],
            artifact_id=flow_data["artifact_id"],
            packet_hash=flow_data["packet_hash"],
            product_type=flow_data["product_type"],
            amount=flow_data["amount"],
            currency=flow_data["currency"],
            buyer_reference=flow_data["buyer_reference"],
            payment_provider=flow_data.get("payment_provider", ""),
            payment_status=flow_data["payment_status"],
            created_at=flow_data["created_at"],
        )
        receipt = revenue_module.confirm_payment(
            flow,
            payment_provider=req.payment_provider,
            external_confirmation=req.external_confirmation,
        )
        return receipt.to_dict()

    @app.get("/revenue")
    async def get_revenue():
        return {
            "receipts": revenue_module.list_revenue(),
            "totals": revenue_module.total_revenue(),
        }

    # --- Receipts ---

    @app.get("/receipts/{receipt_hash}")
    async def get_receipt(receipt_hash: str):
        receipt = receipt_ledger.get(receipt_hash)
        if not receipt:
            raise HTTPException(404, "Receipt not found")
        return receipt

    @app.get("/receipts")
    async def list_receipts():
        return receipt_ledger.list_all()

    # --- Settings ---

    @app.get("/settings")
    async def get_settings():
        conn = db._get_conn()
        try:
            rows = conn.execute("SELECT key, value FROM settings ORDER BY key").fetchall()
            return {r["key"]: r["value"] for r in rows}
        finally:
            conn.close()

    @app.post("/settings")
    async def set_setting(req: SettingsRequest):
        db.set_setting(req.key, req.value)
        return {"key": req.key, "value": req.value}

    # --- Dashboard HTML ---

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        artifacts = db.list_artifacts()
        ollama_status = ollama.status()
        runs = db.list_agent_runs()
        revenue = revenue_module.total_revenue()
        receipts = receipt_ledger.list_all(limit=10)
        risk_reports = db.list_risk_reports()
        pages = db.list_landing_pages()
        tokens = db.list_token_manifests()
        deployments = db.list_deployments()
        revenue_receipts = revenue_module.list_revenue()
        proof_only_count = sum(1 for r in revenue_receipts if r["payment_status"] != "confirmed")
        confirmed_count = sum(1 for r in revenue_receipts if r["payment_status"] == "confirmed")

        return f"""<!DOCTYPE html>
<html><head><title>Evidence Asset Revenue Oracle</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 1200px; margin: 0 auto; padding: 2rem; }}
.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 2rem; }}
.card {{ border: 1px solid #e0e0e0; border-radius: 8px; padding: 1rem; }}
.card h2 {{ font-size: 1.1rem; margin-top: 0; }}
.status-ok {{ color: #2e7d32; }} .status-error {{ color: #c62828; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
td, th {{ padding: 0.4rem; border-bottom: 1px solid #eee; text-align: left; }}
a {{ color: #1565c0; text-decoration: none; }}
.nav {{ margin-bottom: 1rem; }}
.nav a {{ margin-right: 1rem; }}
.proof-badge {{ background: #e3f2fd; color: #1565c0; padding: 0.15rem 0.5rem; border-radius: 3px; font-size: 0.8rem; }}
.confirmed-badge {{ background: #e8f5e9; color: #2e7d32; padding: 0.15rem 0.5rem; border-radius: 3px; font-size: 0.8rem; }}
</style></head><body>
<h1>Evidence Asset Revenue Oracle</h1>
<div class="nav">
  <a href="/dashboard">Dashboard</a> |
  <a href="/packets">Packets</a> |
  <a href="/media-assets">Media Assets</a> |
  <a href="/tokens">Tokens</a> |
  <a href="/pages">Pages</a> |
  <a href="/risks">Risks</a> |
  <a href="/receipts">Receipts</a>
</div>
<div class="grid">
  <div class="card">
    <h2>Agent Status</h2>
    <p>Runs: {len(runs)} | Ollama: {"✅ available" if ollama_status["available"] else "❌ unavailable"}</p>
    <p>Models: {", ".join(ollama_status["models"][:5]) or "none"}</p>
  </div>
  <div class="card">
    <h2>Revenue</h2>
    <p><span class="confirmed-badge">Confirmed: ${revenue["total_confirmed_usd"]} ({confirmed_count})</span></p>
    <p><span class="proof-badge">Proof only: {proof_only_count}</span></p>
    <p>Pending external: {revenue["pending_count"]}</p>
  </div>
  <div class="card">
    <h2>Artifacts ({len(artifacts)})</h2>
    <table><tr><th>ID</th><th>Type</th><th>Status</th></tr>
    {"".join(f"<tr><td><a href='/artifacts/{a['artifact_id']}'>{a['artifact_id'][:12]}</a></td><td>{a['source_type']}</td><td>{a['status']}</td></tr>" for a in artifacts[:10])}
    </table>
  </div>
  <div class="card">
    <h2>Recent Receipts ({len(receipts)})</h2>
    <table><tr><th>Type</th><th>Artifact</th><th>Time</th></tr>
    {"".join(f"<tr><td>{r['receipt_type']}</td><td>{r['artifact_id'][:12]}</td><td>{time.strftime('%H:%M', time.gmtime(r['created_at']))}</td></tr>" for r in receipts)}
    </table>
  </div>
  <div class="card">
    <h2>Risk Reports ({len(risk_reports)})</h2>
    <table><tr><th>Artifact</th><th>Score</th><th>Status</th><th>Token Mode</th></tr>
    {"".join(f"<tr><td>{r['artifact_id'][:12]}</td><td>{r['risk_score']}</td><td>{r['asset_status']}</td><td>{r['token_mode_allowed']}</td></tr>" for r in risk_reports[:10])}
    </table>
  </div>
  <div class="card">
    <h2>Token Manifests ({len(tokens)})</h2>
    <table><tr><th>Name</th><th>Mode</th><th>Status</th></tr>
    {"".join(f"<tr><td>{t['token_name']}</td><td>{t['token_mode']}</td><td>{t['status']}</td></tr>" for t in tokens[:10])}
    </table>
  </div>
  <div class="card">
    <h2>Landing Pages ({len(pages)})</h2>
    <table><tr><th>ID</th><th>Status</th></tr>
    {"".join(f"<tr><td>{p['page_id'][:12]}</td><td>{p['status']}</td></tr>" for p in pages[:10])}
    </table>
  </div>
  <div class="card">
    <h2>Deployments ({len(deployments)})</h2>
    <table><tr><th>Target</th><th>URL</th><th>Status</th></tr>
    {"".join(f"<tr><td>{d['target']}</td><td>{d.get('url', '') or '—'}</td><td>{d['status']}</td></tr>" for d in deployments[:10])}
    </table>
  </div>
</div>
</body></html>"""

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard_route():
        return await dashboard()

    # --- Dashboard HTML sub-pages ---

    @app.get("/packets", response_class=HTMLResponse)
    async def packets_page():
        conn = db._get_conn()
        try:
            rows = conn.execute("SELECT packet_hash, artifact_id, revenue_status, created_at FROM evidence_packets ORDER BY created_at DESC LIMIT 100").fetchall()
        finally:
            conn.close()
        return f"<h1>Evidence Packets ({len(rows)})</h1><table><tr><th>Hash</th><th>Artifact</th><th>Revenue Status</th><th>Created</th></tr>" + "".join(
            f"<tr><td><span class='hash'>{r['packet_hash'][:16]}...</span></td><td><a href='/artifacts/{r['artifact_id']}'>{r['artifact_id'][:12]}</a></td><td>{r['revenue_status']}</td><td>{time.strftime('%Y-%m-%d %H:%M', time.gmtime(r['created_at']))}</td></tr>" for r in rows
        ) + "</table>"

    @app.get("/tokens", response_class=HTMLResponse)
    async def tokens_page():
        tokens = db.list_token_manifests()
        return f"<h1>Token Manifests ({len(tokens)})</h1><table><tr><th>Name</th><th>Symbol</th><th>Mode</th><th>Status</th><th>Artifact</th></tr>" + "".join(
            f"<tr><td>{t['token_name']}</td><td>{t['token_symbol']}</td><td>{t['token_mode']}</td><td>{t['status']}</td><td><a href='/artifacts/{t['artifact_id']}'>{t['artifact_id'][:12]}</a></td></tr>" for t in tokens
        ) + "</table>"

    @app.get("/pages", response_class=HTMLResponse)
    async def pages_page():
        pages = db.list_landing_pages()
        deployments = db.list_deployments()
        return f"<h1>Landing Pages ({len(pages)})</h1><table><tr><th>ID</th><th>Artifact</th><th>Status</th><th>Deployed</th></tr>" + "".join(
            f"<tr><td>{p['page_id'][:12]}</td><td><a href='/artifacts/{p['artifact_id']}'>{p['artifact_id'][:12]}</a></td><td>{p['status']}</td><td>{p.get('deployment_url', '') or '—'}</td></tr>" for p in pages
        ) + "</table><h2>Deployments ({len(deployments)})</h2><table><tr><th>Target</th><th>URL</th><th>Status</th></tr>" + "".join(
            f"<tr><td>{d['target']}</td><td>{d.get('url', '') or '—'}</td><td>{d['status']}</td></tr>" for d in deployments
        ) + "</table>"

    @app.get("/risks", response_class=HTMLResponse)
    async def risks_page():
        reports = db.list_risk_reports()
        return f"<h1>Risk Reports ({len(reports)})</h1><table><tr><th>Artifact</th><th>Score</th><th>Status</th><th>Token Mode</th><th>Blockers</th></tr>" + "".join(
            f"<tr><td><a href='/artifacts/{r['artifact_id']}'>{r['artifact_id'][:12]}</a></td><td>{r['risk_score']}</td><td>{r['asset_status']}</td><td>{r['token_mode_allowed']}</td><td>{len(json.loads(r['blockers'])) if r.get('blockers') else 0}</td></tr>" for r in reports
        ) + "</table>"

    @app.get("/artifacts", response_class=HTMLResponse)
    async def artifacts_page():
        artifacts = db.list_artifacts()
        return f"<h1>Artifacts ({len(artifacts)})</h1><table><tr><th>ID</th><th>Type</th><th>Owner</th><th>Status</th><th>Created</th></tr>" + "".join(
            f"<tr><td><a href='/artifacts/{a['artifact_id']}'>{a['artifact_id'][:12]}</a></td><td>{a['source_type']}</td><td>{a['owner']}</td><td>{a['status']}</td><td>{time.strftime('%Y-%m-%d', time.gmtime(a['created_at']))}</td></tr>"
            for a in artifacts
        ) + "</table>"

    @app.get("/revenue", response_class=HTMLResponse)
    async def revenue_page():
        receipts = revenue_module.list_revenue()
        totals = revenue_module.total_revenue()
        return f"<h1>Revenue</h1><p>Confirmed: ${totals['total_confirmed_usd']} ({totals['confirmed_count']})</p><table><tr><th>ID</th><th>Product</th><th>Amount</th><th>Status</th></tr>" + "".join(
            f"<tr><td>{r['receipt_id'][:12]}</td><td>{r['product_type']}</td><td>${r['amount']}</td><td>{r['payment_status']}</td></tr>"
            for r in receipts
        ) + "</table>"

    @app.get("/receipts", response_class=HTMLResponse)
    async def receipts_page():
        receipts = receipt_ledger.list_all()
        return f"<h1>Receipts ({len(receipts)})</h1><table><tr><th>Hash</th><th>Type</th><th>Artifact</th><th>Time</th></tr>" + "".join(
            f"<tr><td><a href='/receipts/{r['receipt_hash']}'>{r['receipt_hash'][:12]}</a></td><td>{r['receipt_type']}</td><td>{r['artifact_id'][:12]}</td><td>{time.strftime('%Y-%m-%d %H:%M', time.gmtime(r['created_at']))}</td></tr>"
            for r in receipts
        ) + "</table>"

    # --- Media Assets (BMMA) ---

    @app.get("/media-assets", response_class=HTMLResponse)
    async def media_assets_page():
        assets = db.list_media_assets()
        return f"""<h1>Bonded Machine Media Assets ({len(assets)})</h1>
        <table><tr><th>BMMA ID</th><th>Artifact</th><th>Grade</th><th>Bond</th><th>Segments</th><th>Status</th></tr>""" + "".join(
            f"<tr><td>{a['bmma_id'][:16]}</td><td><a href='/artifacts/{a['artifact_id']}'>{a['artifact_id'][:12]}</a></td><td>{a['quality_grade']}/{a['computed_grade']}</td><td>${a['bond_amount_usd']}</td><td>{a['segment_listings_count']}</td><td>{a['status']}</td></tr>"
            for a in assets
        ) + "</table>"

    @app.get("/media-assets/{media_asset_id}")
    async def get_media_asset(media_asset_id: str):
        asset = db.get_media_asset(media_asset_id)
        if not asset:
            raise HTTPException(404, "Media asset not found")
        return asset

    @app.post("/artifacts/{artifact_id}/bmma")
    async def build_bmma(artifact_id: str, req: BMMARequest):
        artifact = db.get_artifact(artifact_id)
        if not artifact:
            raise HTTPException(404, "Artifact not found")

        conn = db._get_conn()
        try:
            pkt_row = conn.execute(
                "SELECT * FROM evidence_packets WHERE artifact_id = ? ORDER BY created_at DESC LIMIT 1",
                (artifact_id,),
            ).fetchone()
        finally:
            conn.close()
        if not pkt_row:
            raise HTTPException(400, "No evidence packet found for artifact")
        packet_data = dict(pkt_row)
        for k in ("claims", "risk_flags", "license_flags", "provenance_chain", "receipt_list"):
            packet_data[k] = json.loads(packet_data[k])

        result = bmma_builder.build_bmma(
            artifact=artifact,
            packet=packet_data,
            question=req.question,
            claims=req.claims or packet_data.get("claims", []),
            transcript=req.transcript,
            visual_evidence_segments=req.visual_evidence_segments,
            truth_labels=req.truth_labels,
            rights_labels=req.rights_labels,
            revenue_ledger=req.revenue_ledger,
            machine_scores=req.machine_scores,
            bond_amount_usd=req.bond_amount_usd,
            rubric_id=req.rubric_id,
            producer_id=req.producer_id,
        )
        return result.to_dict()

    return app
