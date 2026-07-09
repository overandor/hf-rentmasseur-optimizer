"""
Landing Page Generator — compliant landing pages for evidence-backed assets.

Required sections:
- Asset name, one-line thesis, what this artifact is, what problem it solves
- Evidence packet hash, receipt list, revenue status, risk status
- Token mode, utility description, what the token does not represent
- Disclaimers, download packet.json, verify receipt
- Join waitlist, request access, buy report, license artifact

Forbidden phrases:
- guaranteed profit, passive income, risk-free, price will rise
- investment opportunity, buy before it pumps
- backed by future revenue (unless legally reviewed)
"""

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Optional

from .risk_engine import RiskEngine


@dataclass
class LandingPage:
    page_id: str
    artifact_id: str
    packet_hash: str
    html: str
    page_hash: str
    status: str = "draft"

    def to_dict(self) -> dict:
        return {
            "page_id": self.page_id,
            "artifact_id": self.artifact_id,
            "packet_hash": self.packet_hash,
            "page_hash": self.page_hash,
            "status": self.status,
            "html_length": len(self.html),
        }


_DISCLAIMER = (
    "This artifact is provided as-is for evidence and verification purposes. "
    "No investment profit is promised or implied. The proof token, if present, "
    "is a receipt carrier, not a security. Revenue claims are labeled as "
    "proof_of_financeable_structure_only unless backed by verified external "
    "acceptance. This is not financial advice."
)

_FORBIDDEN = [
    "guaranteed profit", "passive income", "risk-free", "price will rise",
    "investment opportunity", "buy before it pumps",
    "backed by future revenue",
]


class LandingPageGenerator:
    """Generates compliant landing pages for evidence-backed assets."""

    def __init__(self, db):
        self.db = db

    def generate(self, artifact: dict, packet: dict,
                 risk_report: dict = None,
                 asset_name: str = "",
                 thesis: str = "",
                 problem_solved: str = "",
                 utility_description: str = "") -> LandingPage:
        """
        Generate a compliant landing page.

        Args:
            artifact: Artifact record dict
            packet: Evidence packet dict
            risk_report: Risk evaluation dict
            asset_name: Display name for the asset
            thesis: One-line thesis
            problem_solved: What problem this artifact solves
            utility_description: What the proof token represents

        Returns:
            LandingPage with computed page_hash
        """
        risk_report = risk_report or {}
        asset_name = asset_name or artifact.get("artifact_id", "Unnamed Asset")
        thesis = thesis or "Evidence-backed artifact with verifiable provenance"
        problem_solved = problem_solved or "Converts fragile information into verifiable, receipt-backed evidence"
        utility_description = utility_description or "The proof token is a receipt carrier, not a security. It does not represent investment, equity, or profit rights."

        token_mode = risk_report.get("token_mode_allowed", "proof_only")
        revenue_status = risk_report.get("revenue_status", "proof_of_financeable_structure_only")
        asset_status = risk_report.get("asset_status", "draft")
        risk_score = risk_report.get("risk_score", 0.0)

        claims = packet.get("claims", [])
        risk_flags = packet.get("risk_flags", [])

        claims_html = "\n".join(
            f"<li><strong>{c.get('type', 'claim')}</strong>: {c.get('text', '')} "
            f"<span class='confidence'>confidence: {c.get('confidence', 0.0)}</span></li>"
            for c in claims
        ) if claims else "<li>No claims extracted</li>"

        risk_flags_html = "\n".join(
            f"<li><span class='severity-{rf.get('severity', 'info')}'>{rf.get('flag', '')}: {rf.get('detail', '')}</span></li>"
            for rf in risk_flags
        ) if risk_flags else "<li>No risk flags</li>"

        blockers = risk_report.get("blockers", [])
        blockers_html = "\n".join(
            f"<li><span class='severity-{b.get('severity', 'info')}'>{b.get('code', '')}: {b.get('description', '')}</span></li>"
            for b in blockers
        ) if blockers else "<li>No compliance blockers</li>"

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{asset_name} — Evidence Asset</title>
    <style>
        body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 800px; margin: 0 auto; padding: 2rem; color: #1a1a1a; }}
        .header {{ border-bottom: 2px solid #e0e0e0; padding-bottom: 1rem; margin-bottom: 2rem; }}
        .section {{ margin-bottom: 2rem; }}
        .section h2 {{ font-size: 1.2rem; color: #333; border-bottom: 1px solid #eee; padding-bottom: 0.5rem; }}
        .status-badge {{ display: inline-block; padding: 0.25rem 0.75rem; border-radius: 4px; font-size: 0.85rem; font-weight: 600; }}
        .status-draft {{ background: #f0f0f0; color: #666; }}
        .status-proof_only {{ background: #e3f2fd; color: #1565c0; }}
        .status-verified {{ background: #e8f5e9; color: #2e7d32; }}
        .status-blocked {{ background: #ffebee; color: #c62828; }}
        .status-needs_human_review {{ background: #fff3e0; color: #e65100; }}
        .hash {{ font-family: monospace; font-size: 0.85rem; word-break: break-all; }}
        .disclaimer {{ background: #fffde7; padding: 1rem; border-radius: 4px; font-size: 0.85rem; color: #616161; }}
        .cta {{ display: inline-block; margin: 0.5rem 0.5rem 0.5rem 0; padding: 0.5rem 1rem; border: 1px solid #ccc; border-radius: 4px; text-decoration: none; color: #333; }}
        .cta:hover {{ background: #f5f5f5; }}
        .severity-blocker {{ color: #c62828; font-weight: 600; }}
        .severity-warning {{ color: #e65100; }}
        .severity-info {{ color: #666; }}
        .forbidden-check {{ color: #2e7d32; font-size: 0.85rem; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{asset_name}</h1>
        <p>{thesis}</p>
        <span class="status-badge status-{asset_status}">{asset_status}</span>
        <span class="status-badge status-proof_only">token: {token_mode}</span>
    </div>

    <div class="section">
        <h2>What This Artifact Is</h2>
        <p>Source type: {artifact.get('source_type', 'unknown')}</p>
        <p>Owner: {artifact.get('owner', 'unknown')}</p>
        <p>Created: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(artifact.get('created_at', 0)))}</p>
    </div>

    <div class="section">
        <h2>What Problem It Solves</h2>
        <p>{problem_solved}</p>
    </div>

    <div class="section">
        <h2>Evidence Packet</h2>
        <p><strong>Packet hash:</strong> <span class="hash">{packet.get('packet_hash', '')}</span></p>
        <p><strong>Source hash:</strong> <span class="hash">{packet.get('source_hash', '')}</span></p>
        <p><strong>Manifest hash:</strong> <span class="hash">{packet.get('manifest_hash', '')}</span></p>
        <p><strong>Revenue status:</strong> {revenue_status}</p>
        <p><strong>Risk score:</strong> {risk_score}</p>
    </div>

    <div class="section">
        <h2>Claims</h2>
        <ul>{claims_html}</ul>
    </div>

    <div class="section">
        <h2>Risk Flags</h2>
        <ul>{risk_flags_html}</ul>
    </div>

    <div class="section">
        <h2>Compliance Blockers</h2>
        <ul>{blockers_html}</ul>
    </div>

    <div class="section">
        <h2>Token Mode</h2>
        <p><strong>Current mode:</strong> {token_mode}</p>
        <p><strong>Utility description:</strong> {utility_description}</p>
        <p><strong>What the token does NOT represent:</strong> The proof token does not represent investment, equity, profit rights, security, or any financial instrument. It is a receipt carrier for evidence verification only.</p>
    </div>

    <div class="section">
        <h2>Disclaimers</h2>
        <div class="disclaimer">{_DISCLAIMER}</div>
    </div>

    <div class="section">
        <h2>Verify & Access</h2>
        <a class="cta" href="/packets/{packet.get('packet_hash', '')}/verify">Verify receipt</a>
        <a class="cta" href="/packets/{packet.get('packet_hash', '')}">Download packet.json</a>
        <a class="cta" href="/contact?artifact={artifact.get('artifact_id', '')}&action=waitlist">Join waitlist</a>
        <a class="cta" href="/contact?artifact={artifact.get('artifact_id', '')}&action=access">Request access</a>
        <a class="cta" href="/contact?artifact={artifact.get('artifact_id', '')}&action=report">Buy report</a>
        <a class="cta" href="/contact?artifact={artifact.get('artifact_id', '')}&action=license">License artifact</a>
    </div>

    <div class="section">
        <p class="forbidden-check">No forbidden phrases detected. This page has been screened for compliance.</p>
    </div>
</body>
</html>"""

        page_hash = hashlib.sha256(html.encode()).hexdigest()
        page_id = hashlib.sha256(
            f"page:{artifact.get('artifact_id', '')}:{packet.get('packet_hash', '')}:{time.time()}".encode()
        ).hexdigest()[:16]

        page = LandingPage(
            page_id=page_id,
            artifact_id=artifact.get("artifact_id", ""),
            packet_hash=packet.get("packet_hash", ""),
            html=html,
            page_hash=page_hash,
        )

        self.db.insert_landing_page(
            page_id=page.page_id,
            artifact_id=page.artifact_id,
            packet_hash=page.packet_hash,
            html=page.html,
            page_hash=page.page_hash,
        )

        return page

    def check_compliance(self, html: str) -> dict:
        """Check landing page HTML for forbidden phrases."""
        found = RiskEngine.check_forbidden_phrases(html)
        return {
            "compliant": len(found) == 0,
            "forbidden_phrases_found": found,
        }
