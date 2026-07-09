"""LatentOS FastAPI app — unified liquidity protocol for pre-market value.

LatentOS Core endpoints:
    POST /v1/latent/liquidify
    POST /v1/breakage/map
    POST /v1/gaps/detect
    POST /v1/memory/grade
    POST /v1/valuation/pre-revenue
    POST /v1/monetization/routes

LatentOS EDU endpoints:
    POST /v1/edu/liquidify
    POST /v1/edu/credential/verify
    POST /v1/edu/disclosure/minimize
    POST /v1/edu/mint-cap
    POST /v1/edu/prediction/quote
    POST /v1/edu/prediction/settle
    POST /v1/edu/risk-score
    POST /v1/edu/proof-of-scholarship
    POST /v1/edu/privacy/check
    POST /v1/edu/claim/grade

Academic Performance Liquidity Protocol endpoints:
    POST /v1/academic/liquidify
    POST /v1/academic/score
    POST /v1/academic/credential/verify
    POST /v1/academic/privacy/grade
    POST /v1/academic/mint-cap
    POST /v1/academic/prediction/settle
    POST /v1/academic/scholarship/match
    POST /v1/academic/risk-score
    POST /v1/academic/proof-profile

Master endpoint:
    POST /v1/liquidity/settle-signal

Doctrine: liquidify the proof, not the person; liquidify the artifact, not the private source record.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from .models import (
    SignalType,
    ProvenanceSource,
    DisclosureMode,
    MarketPurpose,
    Provenance,
    PrivacyConfig,
    MarketContext,
    SettleSignalRequest,
    SettleSignalResponse,
    ValueRange,
    LiquidifyRequest,
    BreakageMapRequest,
    GapDetectRequest,
    MemoryGradeRequest,
    PreRevenueValuationRequest,
    MonetizationRoutesRequest,
    CredentialVerifyRequest,
    DisclosureMinimizeRequest,
    MintCapRequest,
    PredictionQuoteRequest,
    PredictionSettleRequest,
)
from .core import (
    LatentSignalScorer,
    BreakageMapper,
    GapDetector,
    MemoryGrader,
    PreRevenueValuator,
    MonetizationRouter,
)
from .edu import (
    AcademicLiquidityEngine,
    CredentialVerifier,
    ProofOfScholarshipScorer,
    AcademicLiquidityScorer,
    EduMintCapCalculator,
    AcademicPredictionEngine,
    AntiZKArrow,
)


app = FastAPI(
    title="LatentOS + LatentOS EDU",
    description="Credential-Settled Latent Liquidity Network — liquidify the proof, not the person.",
    version="1.0.0",
)

_scorer = LatentSignalScorer()
_breakage = BreakageMapper()
_gaps = GapDetector()
_memory = MemoryGrader()
_valuator = PreRevenueValuator()
_monetization = MonetizationRouter()
_edu = AcademicLiquidityEngine()
_credential_verifier = CredentialVerifier()
_pos_scorer = ProofOfScholarshipScorer()
_liquidity_scorer = AcademicLiquidityScorer()
_mint_calc = EduMintCapCalculator()
_prediction_engine = AcademicPredictionEngine()
_arrow = AntiZKArrow()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "LatentOS + LatentOS EDU",
        "version": "1.0.0",
        "doctrine": "liquidify the proof, not the person; liquidify the artifact, not the private source record",
        "endpoints": {
            "core": ["/v1/latent/liquidify", "/v1/breakage/map", "/v1/gaps/detect",
                     "/v1/memory/grade", "/v1/valuation/pre-revenue", "/v1/monetization/routes"],
            "edu": ["/v1/edu/liquidify", "/v1/edu/credential/verify", "/v1/edu/disclosure/minimize",
                    "/v1/edu/mint-cap", "/v1/edu/prediction/quote", "/v1/edu/prediction/settle",
                    "/v1/edu/risk-score", "/v1/edu/proof-of-scholarship", "/v1/edu/privacy/check",
                    "/v1/edu/claim/grade"],
            "academic": ["/v1/academic/liquidify", "/v1/academic/score", "/v1/academic/credential/verify",
                         "/v1/academic/privacy/grade", "/v1/academic/mint-cap",
                         "/v1/academic/prediction/settle", "/v1/academic/scholarship/match",
                         "/v1/academic/risk-score", "/v1/academic/proof-profile"],
            "master": ["/v1/liquidity/settle-signal"],
        },
    }


# ─── Master endpoint ────────────────────────────────────────────────────

@app.post("/v1/liquidity/settle-signal", response_model=SettleSignalResponse)
async def settle_signal(req: SettleSignalRequest):
    """Master endpoint — accepts either software artifacts or academic credentials."""
    result = _scorer.settle_signal(
        req.signal_type,
        req.payload,
        req.provenance,
        req.privacy,
        req.market_context,
    )
    return result


# ─── LatentOS Core endpoints ────────────────────────────────────────────

@app.post("/v1/latent/liquidify")
async def latent_liquidify(req: LiquidifyRequest):
    """Liquidify pre-market software value."""
    result = _scorer.settle_signal(
        SignalType.software_artifact,
        req.payload,
        req.provenance,
        req.privacy,
        req.market_context,
    )
    return result


@app.post("/v1/breakage/map")
async def breakage_map(req: BreakageMapRequest):
    """Map breakage signals into value leaks and opportunities."""
    return _breakage.map(req.payload, req.provenance)


@app.post("/v1/gaps/detect")
async def gaps_detect(req: GapDetectRequest):
    """Detect product gaps, safety gaps, and verification gaps."""
    return _gaps.detect(req.payload, req.provenance)


@app.post("/v1/memory/grade")
async def memory_grade(req: MemoryGradeRequest):
    """Grade memory claims — memory is not truth, claims are not proof."""
    return _memory.grade(req.claims, req.provenance)


@app.post("/v1/valuation/pre-revenue")
async def valuation_pre_revenue(req: PreRevenueValuationRequest):
    """Estimate pre-revenue valuation from latent signals."""
    return _valuator.value(req.payload, req.market_context)


@app.post("/v1/monetization/routes")
async def monetization_routes(req: MonetizationRoutesRequest):
    """Route latent value signals to monetization pathways."""
    return _monetization.route(req.payload, req.market_context)


# ─── LatentOS EDU endpoints ─────────────────────────────────────────────

@app.post("/v1/edu/liquidify")
async def edu_liquidify(req: LiquidifyRequest):
    """Liquidify verified learning progress into academic liquidity."""
    credential = req.payload
    student_permissions = {
        "reveal_grade_band": credential.get("reveal_grade_band", True),
        "reveal_raw_grade": credential.get("reveal_raw_grade", False),
        "reveal_institution": credential.get("reveal_institution", True),
        "reveal_course": credential.get("reveal_course", True),
        "reveal_identity": credential.get("reveal_identity", "selective"),
        "student_consent": credential.get("student_consent", True),
        "ferpa_compliant": credential.get("ferpa_compliant", True),
        "consent_for_market_use": credential.get("consent_for_market_use", False),
        "disclosure_mode": req.privacy.disclosure_mode.value,
    }
    context = {
        "use_case": req.market_context.purpose.value,
        "jurisdiction": credential.get("jurisdiction", "US"),
        "settlement_type": credential.get("settlement_type", "outcome_based"),
    }
    return _edu.liquidify(credential, student_permissions, context)


@app.post("/v1/edu/credential/verify")
async def edu_credential_verify(req: CredentialVerifyRequest):
    """Verify an academic credential using the W3C VC model."""
    return _credential_verifier.verify(req.credential, req.issuer_did)


@app.post("/v1/edu/disclosure/minimize")
async def edu_disclosure_minimize(req: DisclosureMinimizeRequest):
    """AntiZK/ARROW — minimize disclosure to the minimum sufficient receipt."""
    return _arrow.minimize_disclosure(req.credential, req.purpose, req.disclosure_mode)


@app.post("/v1/edu/mint-cap")
async def edu_mint_cap(req: MintCapRequest):
    """Calculate EDU mint capacity from verified evidence."""
    return _mint_calc.calculate(req.proof_of_scholarship_score, req.credential_count, req.issuer_trust)


@app.post("/v1/edu/prediction/quote")
async def edu_prediction_quote(req: PredictionQuoteRequest):
    """Get a prediction quote for an academic outcome."""
    return _prediction_engine.quote(
        req.credential, req.outcome, req.stake_amount, req.proof_of_scholarship_score
    )


@app.post("/v1/edu/prediction/settle")
async def edu_prediction_settle(req: PredictionSettleRequest):
    """Settle an academic prediction based on outcome evidence."""
    result = _prediction_engine.settle(req.prediction_id, req.outcome_achieved, req.evidence)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.post("/v1/edu/risk-score")
async def edu_risk_score(req: LiquidifyRequest):
    """Compute academic risk scores (privacy, fraud, dropout, compliance)."""
    profile = req.payload
    context = {
        "use_case": req.market_context.purpose.value,
        "jurisdiction": profile.get("jurisdiction", "US"),
    }
    return _liquidity_scorer.score(profile, context)


@app.post("/v1/edu/proof-of-scholarship")
async def edu_proof_of_scholarship(req: LiquidifyRequest):
    """Compute the Proof-of-Scholarship profile score."""
    return _pos_scorer.score(req.payload)


@app.post("/v1/edu/privacy/check")
async def edu_privacy_check(req: LiquidifyRequest):
    """Check privacy compliance of an academic profile."""
    return _arrow.privacy_grade(req.payload)


@app.post("/v1/edu/claim/grade")
async def edu_claim_grade(req: LiquidifyRequest):
    """Submit a grade claim for verification and liquidification.

    The financeable object is not the raw grade.
    It is a permissioned, issuer-signed academic claim.
    """
    credential = req.payload
    if not credential.get("issuer_signature") and not credential.get("proof"):
        return {
            "status": "rejected",
            "reason": "unverified_self_claim",
            "doctrine": "A claim is not proof. An unverified grade claim cannot be liquidified.",
            "required": ["issuer_signature", "credential_status", "student_consent"],
        }
    student_permissions = {
        "reveal_grade_band": credential.get("reveal_grade_band", True),
        "reveal_raw_grade": credential.get("reveal_raw_grade", False),
        "reveal_identity": credential.get("reveal_identity", "selective"),
        "student_consent": credential.get("student_consent", True),
        "ferpa_compliant": credential.get("ferpa_compliant", True),
        "disclosure_mode": req.privacy.disclosure_mode.value,
    }
    context = {
        "use_case": req.market_context.purpose.value,
        "jurisdiction": credential.get("jurisdiction", "US"),
    }
    return _edu.liquidify(credential, student_permissions, context)


# ─── Academic Performance Liquidity Protocol endpoints ──────────────────

@app.post("/v1/academic/liquidify")
async def academic_liquidify(req: LiquidifyRequest):
    """Main academic performance liquidity endpoint."""
    credential = req.payload
    student_permissions = {
        "reveal_grade_band": credential.get("reveal_grade_band", True),
        "reveal_raw_grade": credential.get("reveal_raw_grade", False),
        "reveal_institution": credential.get("reveal_institution", True),
        "reveal_course": credential.get("reveal_course", True),
        "reveal_identity": credential.get("reveal_identity", "selective"),
        "student_consent": credential.get("student_consent", True),
        "ferpa_compliant": credential.get("ferpa_compliant", True),
        "consent_for_market_use": credential.get("consent_for_market_use", False),
        "disclosure_mode": req.privacy.disclosure_mode.value,
    }
    context = {
        "use_case": req.market_context.purpose.value,
        "jurisdiction": credential.get("jurisdiction", "US"),
        "settlement_type": credential.get("settlement_type", "outcome_based"),
    }
    return _edu.liquidify(credential, student_permissions, context)


@app.post("/v1/academic/score")
async def academic_score(req: LiquidifyRequest):
    """Compute academic liquidity score."""
    profile = req.payload
    context = {
        "use_case": req.market_context.purpose.value,
        "jurisdiction": profile.get("jurisdiction", "US"),
    }
    return _liquidity_scorer.score(profile, context)


@app.post("/v1/academic/credential/verify")
async def academic_credential_verify(req: CredentialVerifyRequest):
    """Verify an academic credential."""
    return _credential_verifier.verify(req.credential, req.issuer_did)


@app.post("/v1/academic/privacy/grade")
async def academic_privacy_grade(req: LiquidifyRequest):
    """Grade privacy compliance of an academic profile."""
    return _arrow.privacy_grade(req.payload)


@app.post("/v1/academic/mint-cap")
async def academic_mint_cap(req: MintCapRequest):
    """Calculate EDU mint capacity."""
    return _mint_calc.calculate(req.proof_of_scholarship_score, req.credential_count, req.issuer_trust)


@app.post("/v1/academic/prediction/settle")
async def academic_prediction_settle(req: PredictionSettleRequest):
    """Settle an academic prediction."""
    result = _prediction_engine.settle(req.prediction_id, req.outcome_achieved, req.evidence)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


@app.post("/v1/academic/scholarship/match")
async def academic_scholarship_match(req: LiquidifyRequest):
    """Match academic profile to scholarship opportunities."""
    pos_result = _pos_scorer.score(req.payload)
    score = pos_result["proof_of_scholarship_score"]

    matches: list[dict[str, Any]] = []
    if score >= 80:
        matches.append({"scholarship": "merit_full", "fit": "high", "amount_range": [5000, 50000]})
        matches.append({"scholarship": "stem_excellence", "fit": "high", "amount_range": [3000, 25000]})
    if score >= 60:
        matches.append({"scholarship": "progress_grant", "fit": "medium", "amount_range": [1000, 10000]})
        matches.append({"scholarship": "completion_bonus", "fit": "medium", "amount_range": [500, 5000]})
    if score >= 40:
        matches.append({"scholarship": "need_based_progress", "fit": "low", "amount_range": [200, 2000]})

    return {
        "proof_of_scholarship_score": score,
        "matches": matches,
        "best_match": matches[0] if matches else None,
    }


@app.post("/v1/academic/risk-score")
async def academic_risk_score(req: LiquidifyRequest):
    """Compute comprehensive academic risk scores."""
    profile = req.payload
    context = {
        "use_case": req.market_context.purpose.value,
        "jurisdiction": profile.get("jurisdiction", "US"),
    }
    return _liquidity_scorer.score(profile, context)


@app.post("/v1/academic/proof-profile")
async def academic_proof_profile(req: LiquidifyRequest):
    """Generate the Proof-of-Scholarship Profile — the collateral object."""
    profile = req.payload
    pos_result = _pos_scorer.score(profile)
    privacy_result = _arrow.privacy_grade(profile)
    disclosure = _arrow.minimize_disclosure(
        profile,
        req.market_context.purpose,
        DisclosureMode.minimal,
    )

    return {
        "student_profile": {
            "identity_disclosure": profile.get("reveal_identity", "selective"),
            "credentials": profile.get("credentials", []),
            "verified_claims": profile.get("verified_claims", []),
            "evidence_links": profile.get("evidence_links", []),
            "credit_history": profile.get("credit_history", []),
            "improvement_trajectory": profile.get("improvement_trajectory", []),
            "prediction_settlement_history": profile.get("prediction_settlement_history", []),
            "privacy_permissions": profile.get("privacy_permissions", {}),
            "risk_haircuts": {
                "privacy_risk": privacy_result["privacy_score"],
                "fraud_risk": 100 - pos_result["components"].get("verified_academic_claims", 0),
                "dropout_risk": profile.get("dropout_risk", 0),
                "compliance_risk": profile.get("compliance_risk", 0),
            },
        },
        "proof_of_scholarship_score": pos_result["proof_of_scholarship_score"],
        "privacy_grade": privacy_result["privacy_grade"],
        "minimized_disclosure": disclosure,
        "doctrine": "The asset is the permissioned proof of useful progress.",
    }


# ─── Dashboard ──────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return HTMLResponse("""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LatentOS + LatentOS EDU</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#0d1117; color:#c9d1d9; padding:20px; max-width:1200px; margin:0 auto; }
h1 { color:#58a6ff; font-size:28px; margin-bottom:4px; }
.subtitle { color:#8b949e; font-size:14px; margin-bottom:24px; }
.doctrine { background:#161b22; border:1px solid #30363d; border-radius:8px; padding:16px; margin-bottom:24px; font-style:italic; color:#8b949e; }
.section-title { font-size:18px; color:#58a6ff; margin:24px 0 12px; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:16px; margin-bottom:24px; }
.card { background:#161b22; border:1px solid #30363d; border-radius:8px; padding:20px; }
.card h2 { font-size:14px; color:#8b949e; text-transform:uppercase; letter-spacing:0.5px; margin-bottom:12px; }
.endpoint { font-family:'SF Mono',Monaco,monospace; font-size:13px; padding:6px 0; border-bottom:1px solid #21262d; display:flex; justify-content:space-between; }
.endpoint:last-child { border-bottom:none; }
.method { color:#3fb950; font-weight:600; }
.path { color:#58a6ff; }
.footer { margin-top:32px; padding-top:16px; border-top:1px solid #30363d; color:#8b949e; font-size:12px; }
</style>
</head>
<body>
<h1>LatentOS + LatentOS EDU</h1>
<p class="subtitle">Credential-Settled Latent Liquidity Network</p>
<div class="doctrine">Liquidify the proof, not the person. Liquidify the artifact, not the private source record.</div>

<div class="section-title">Master Endpoint</div>
<div class="grid">
<div class="card"><h2>Unified Settlement</h2>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/liquidity/settle-signal</span></div>
</div></div>

<div class="section-title">LatentOS Core — Software Value</div>
<div class="grid">
<div class="card"><h2>Core Endpoints</h2>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/latent/liquidify</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/breakage/map</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/gaps/detect</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/memory/grade</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/valuation/pre-revenue</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/monetization/routes</span></div>
</div></div>

<div class="section-title">LatentOS EDU — Academic Performance Liquidity</div>
<div class="grid">
<div class="card"><h2>EDU Endpoints</h2>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/edu/liquidify</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/edu/credential/verify</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/edu/disclosure/minimize</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/edu/mint-cap</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/edu/prediction/quote</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/edu/prediction/settle</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/edu/risk-score</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/edu/proof-of-scholarship</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/edu/privacy/check</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/edu/claim/grade</span></div>
</div></div>

<div class="section-title">Academic Performance Liquidity Protocol</div>
<div class="grid">
<div class="card"><h2>Academic Endpoints</h2>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/academic/liquidify</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/academic/score</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/academic/credential/verify</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/academic/privacy/grade</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/academic/mint-cap</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/academic/prediction/settle</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/academic/scholarship/match</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/academic/risk-score</span></div>
<div class="endpoint"><span class="method">POST</span><span class="path">/v1/academic/proof-profile</span></div>
</div></div>

<div class="footer">
<p>LatentOS is a liquidity protocol for pre-market value: it converts software artifacts, failed workflows,
and verified academic progress into truth-graded, privacy-preserving, settlement-ready signals
that can be priced, funded, licensed, or routed into opportunity markets.</p>
<p style="margin-top:8px">Blocked: No public raw grade markets. No trading minors' private records. No doxxed transcripts.
No coercive grade speculation. No unauthorized FERPA-covered data exposure.</p>
</div>
</body></html>""")
