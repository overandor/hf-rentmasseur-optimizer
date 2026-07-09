"""Tests for LatentOS + LatentOS EDU — Credential-Settled Latent Liquidity Network."""

import pytest
from fastapi.testclient import TestClient

from latentos.app import app
from latentos.models import (
    SignalType,
    ProvenanceSource,
    DisclosureMode,
    MarketPurpose,
    Provenance,
    PrivacyConfig,
    MarketContext,
)
from latentos.core import (
    LatentSignalScorer,
    BreakageMapper,
    GapDetector,
    MemoryGrader,
    PreRevenueValuator,
    MonetizationRouter,
)
from latentos.edu import (
    AcademicLiquidityEngine,
    CredentialVerifier,
    ProofOfScholarshipScorer,
    AcademicLiquidityScorer,
    EduMintCapCalculator,
    AcademicPredictionEngine,
    AntiZKArrow,
)

client = TestClient(app)


# ─── Core Engine Tests ──────────────────────────────────────────────────

class TestLatentSignalScorer:
    def test_software_artifact_with_full_evidence(self):
        scorer = LatentSignalScorer()
        result = scorer.settle_signal(
            SignalType.software_artifact,
            payload={
                "artifact_hash": "abc123",
                "deployment_evidence": True,
                "test_pass": True,
                "receipt": True,
                "usage_log": True,
                "endpoint_response": True,
            },
            provenance=Provenance(source=ProvenanceSource.tool_verified, confidence=0.9),
            privacy=PrivacyConfig(disclosure_mode=DisclosureMode.minimal, blocked_fields=[]),
            market_context=MarketContext(purpose=MarketPurpose.valuation),
        )
        assert result["signal_liquidity_score"] > 50
        assert result["proof_strength"] > 70
        assert "receipt" in result["receipt"]
        assert result["receipt"]["schema"] == "membra.latentos.settlement_receipt.v1"

    def test_software_artifact_with_no_evidence(self):
        scorer = LatentSignalScorer()
        result = scorer.settle_signal(
            SignalType.software_artifact,
            payload={},
            provenance=Provenance(source=ProvenanceSource.user_declared, confidence=0.1),
            privacy=PrivacyConfig(disclosure_mode=DisclosureMode.minimal),
            market_context=MarketContext(),
        )
        assert result["signal_liquidity_score"] < 30
        assert len(result["required_next_proofs"]) > 0

    def test_privacy_risk_blocks_secrets(self):
        scorer = LatentSignalScorer()
        result = scorer.settle_signal(
            SignalType.software_artifact,
            payload={"secrets_included": True, "source_code_included": True},
            provenance=Provenance(source=ProvenanceSource.tool_verified, confidence=0.9),
            privacy=PrivacyConfig(disclosure_mode=DisclosureMode.full_with_consent, blocked_fields=["secrets"]),
            market_context=MarketContext(),
        )
        assert result["privacy_risk"] > 0
        assert "secrets" in result["blocked_disclosure"]

    def test_academic_credential_signal(self):
        scorer = LatentSignalScorer()
        result = scorer.settle_signal(
            SignalType.academic_credential,
            payload={
                "issuer_signature": True,
                "student_consent": True,
                "ferpa_compliant": True,
            },
            provenance=Provenance(source=ProvenanceSource.issuer_signed, confidence=0.95),
            privacy=PrivacyConfig(disclosure_mode=DisclosureMode.minimal, blocked_fields=["raw_grade", "transcript"]),
            market_context=MarketContext(purpose=MarketPurpose.scholarship),
        )
        assert result["proof_strength"] > 40
        assert "scholarship_pool" in result["liquidification_routes"]

    def test_value_range_estimation(self):
        scorer = LatentSignalScorer()
        result = scorer.settle_signal(
            SignalType.software_artifact,
            payload={"artifact_hash": "x", "test_pass": True, "receipt": True},
            provenance=Provenance(source=ProvenanceSource.tool_verified, confidence=0.8),
            privacy=PrivacyConfig(disclosure_mode=DisclosureMode.minimal),
            market_context=MarketContext(purpose=MarketPurpose.saas_opportunity),
        )
        vr = result["estimated_value_range_usd"]
        assert vr["low"] > 0
        assert vr["high"] > vr["mid"] > vr["low"]

    def test_receipt_has_hash(self):
        scorer = LatentSignalScorer()
        result = scorer.settle_signal(
            SignalType.software_artifact,
            payload={"artifact_hash": "x"},
            provenance=Provenance(source=ProvenanceSource.tool_verified, confidence=0.8),
            privacy=PrivacyConfig(),
            market_context=MarketContext(),
        )
        assert "receipt_hash" in result["receipt"]
        assert len(result["receipt"]["receipt_hash"]) == 64


class TestBreakageMapper:
    def test_deployment_failure_mapping(self):
        mapper = BreakageMapper()
        result = mapper.map(
            payload={
                "breakage_type": "deployment_failure",
                "severity": "high",
                "root_cause": "missing dependency",
                "remediation_path": "add requirements.txt",
                "reproducible": True,
            },
            provenance=Provenance(source=ProvenanceSource.observed_behavior, confidence=0.8),
        )
        assert result["breakage_type"] == "deployment_failure"
        assert "remediation_bounty" in result["liquidity_opportunities"]
        assert result["estimated_value_leak_usd"] > 0

    def test_memory_conflict_mapping(self):
        mapper = BreakageMapper()
        result = mapper.map(
            payload={"breakage_type": "memory_conflict", "severity": "medium", "reproducible": True},
            provenance=Provenance(source=ProvenanceSource.observed_behavior, confidence=0.7),
        )
        assert "memory_repair_grant" in result["liquidity_opportunities"]


class TestGapDetector:
    def test_gap_detection(self):
        detector = GapDetector()
        result = detector.detect(
            payload={"has_tests": False, "has_receipts": False, "has_deployment": False, "secret_exposure": True},
            provenance=Provenance(source=ProvenanceSource.tool_verified, confidence=0.9),
        )
        assert result["total_gaps"] >= 4
        assert result["critical_gaps"] >= 1
        assert result["gap_liquidity_score"] > 0


class TestMemoryGrader:
    def test_verified_claim(self):
        grader = MemoryGrader()
        result = grader.grade(
            claims=[{"claim_id": "c1", "summary": "deployed app", "evidence": True, "receipt": True, "delta_proof": True}],
            provenance=Provenance(source=ProvenanceSource.tool_verified, confidence=0.9),
        )
        assert result["verified"] == 1
        assert result["graded_claims"][0]["grade"] == "verified"

    def test_unverified_claim(self):
        grader = MemoryGrader()
        result = grader.grade(
            claims=[{"claim_id": "c2", "summary": "improved performance"}],
            provenance=Provenance(source=ProvenanceSource.user_declared, confidence=0.1),
        )
        assert result["unverified"] == 1
        assert result["graded_claims"][0]["grade"] == "unverified"


class TestPreRevenueValuator:
    def test_valuation(self):
        v = PreRevenueValuator()
        result = v.value(
            payload={"proof_strength": 70, "deployment_readiness": 60, "market_demand_signal": 50},
            market_context=MarketContext(purpose=MarketPurpose.saas_opportunity),
        )
        assert result["pre_revenue_composite_score"] > 0
        assert result["estimated_valuation_usd"]["high"] > result["estimated_valuation_usd"]["low"]


class TestMonetizationRouter:
    def test_high_liquidity_routes(self):
        r = MonetizationRouter()
        result = r.route(
            payload={"liquidity_score": 85, "signal_type": "software_artifact"},
            market_context=MarketContext(purpose=MarketPurpose.valuation),
        )
        assert len(result["routes"]) >= 4
        assert result["best_route"] == "revenue_share"


# ─── EDU Engine Tests ───────────────────────────────────────────────────

class TestCredentialVerifier:
    def test_valid_credential(self):
        v = CredentialVerifier()
        result = v.verify({
            "issuer": {"id": "did:web:university.edu"},
            "credential_subject": {"student": "x", "grade_band": "A"},
            "issuance_date": "2026-01-01",
            "type": "GradeBandCredential",
            "proof": {"type": "Ed25519Signature2020"},
            "evidence": [{"id": "e1", "type": "Transcript"}],
        })
        assert result["valid"] is True
        assert "issuer_signature_present" in result["verified_fields"]

    def test_missing_proof(self):
        v = CredentialVerifier()
        result = v.verify({
            "issuer": {"id": "did:web:university.edu"},
            "credential_subject": {},
            "issuance_date": "2026-01-01",
            "type": "GradeBandCredential",
        })
        assert "missing_issuer_signature" in result["issues"]

    def test_revoked_credential(self):
        v = CredentialVerifier()
        result = v.verify({
            "issuer": {"id": "did:web:university.edu"},
            "credential_subject": {},
            "issuance_date": "2026-01-01",
            "type": "GradeBandCredential",
            "proof": {"type": "Ed25519Signature2020"},
            "credential_status": {"type": "RevocationList2020", "revoked": True},
        })
        assert "credential_revoked" in result["issues"]


class TestProofOfScholarshipScorer:
    def test_high_score(self):
        s = ProofOfScholarshipScorer()
        result = s.score({
            "verified_claims": [{"verified": True}, {"verified": True}, {"verified": True}],
            "issuer_trust_score": 90,
            "credentials": [{"status": "active"}, {"status": "active"}],
            "improvement_trajectory": [60, 70, 80, 90],
            "skill_scarcity_score": 70,
            "evidence_links": ["e1", "e2", "e3"],
            "prediction_settlement_history": [{"status": "settled"}, {"status": "settled"}],
            "counterparty_acceptance_score": 60,
            "privacy_permissions": {"disclosure_mode": "minimal"},
        })
        assert result["proof_of_scholarship_score"] > 50
        assert "verified_academic_claims" in result["components"]

    def test_low_score(self):
        s = ProofOfScholarshipScorer()
        result = s.score({})
        assert result["proof_of_scholarship_score"] < 30


class TestAcademicLiquidityScorer:
    def test_liquidity_score(self):
        s = AcademicLiquidityScorer()
        result = s.score(
            profile={
                "verified_performance_score": 80,
                "completion_probability": 0.9,
                "skill_scarcity_score": 60,
                "counterparty_acceptance_score": 50,
                "issuer_trust_score": 85,
                "improvement_trajectory_score": 0.8,
                "time_to_outcome_discount": 0.9,
                "privacy_permissions": {"reveal_raw_grade": False, "student_consent": True},
            },
            context={"use_case": "scholarship", "jurisdiction": "US"},
        )
        assert result["academic_liquidity_score"] > 0
        assert "privacy_risk" in result
        assert "fraud_risk" in result
        assert "dropout_risk" in result

    def test_privacy_risk_for_raw_grade(self):
        s = AcademicLiquidityScorer()
        result = s.score(
            profile={"privacy_permissions": {"reveal_raw_grade": True, "student_consent": True}},
            context={"jurisdiction": "US"},
        )
        assert result["privacy_risk"] >= 30

    def test_compliance_risk_for_minor(self):
        s = AcademicLiquidityScorer()
        result = s.score(
            profile={"minor_record": True, "parental_consent": False},
            context={"jurisdiction": "US"},
        )
        assert result["compliance_risk"] >= 40


class TestEduMintCapCalculator:
    def test_mint_cap(self):
        calc = EduMintCapCalculator()
        result = calc.calculate(pos_score=75, credential_count=5, issuer_trust=0.9)
        assert result["edu_mint_cap"] > 0
        assert result["risk_haircut"] < 0.2

    def test_low_score_haircut(self):
        calc = EduMintCapCalculator()
        result = calc.calculate(pos_score=20, credential_count=3, issuer_trust=0.5)
        assert result["risk_haircut"] == 0.5


class TestAcademicPredictionEngine:
    def test_quote_and_settle(self):
        engine = AcademicPredictionEngine()
        quote = engine.quote(
            credential={"type": "CourseCompletedCredential"},
            outcome="complete_with_grade_B",
            stake_amount=100,
            pos_score=80,
        )
        assert quote["prediction_id"]
        assert quote["confidence"] == 0.8
        assert quote["potential_payout"] > 100

        settlement = engine.settle(quote["prediction_id"], True, {"final_grade": "B"})
        assert settlement["status"] == "settled"
        assert settlement["settlement_amount"] > 0

    def test_settle_not_found(self):
        engine = AcademicPredictionEngine()
        result = engine.settle("nonexistent", True, {})
        assert "error" in result


class TestAntiZKArrow:
    def test_minimize_disclosure_blocks_raw_grade(self):
        arrow = AntiZKArrow()
        result = arrow.minimize_disclosure(
            credential={"raw_grade": 95, "grade_band": "A", "student_name": "Jane", "issuer_id": "did:web:uni.edu"},
            purpose=MarketPurpose.scholarship,
            disclosure_mode=DisclosureMode.minimal,
        )
        assert "raw_grade" in result["blocked_disclosure"]
        assert "student_name" in result["blocked_disclosure"]
        assert "grade_band" in result["allowed_disclosure"]

    def test_privacy_grade_a(self):
        arrow = AntiZKArrow()
        result = arrow.privacy_grade({
            "privacy_permissions": {
                "reveal_raw_grade": False,
                "reveal_transcript": False,
                "reveal_identity": "selective",
                "student_consent": True,
            },
        })
        assert result["privacy_grade"] in ("A", "B")

    def test_privacy_grade_f(self):
        arrow = AntiZKArrow()
        result = arrow.privacy_grade({
            "privacy_permissions": {
                "reveal_raw_grade": True,
                "reveal_transcript": True,
                "reveal_identity": "full",
                "student_consent": False,
            },
        })
        assert result["privacy_grade"] == "F"


class TestAcademicLiquidityEngine:
    def test_full_liquidify(self):
        engine = AcademicLiquidityEngine()
        result = engine.liquidify(
            credential={
                "type": "GradeBandCredential",
                "issuer": {"id": "did:web:university.edu"},
                "issuer_trust_score": 85,
                "proof": {"type": "Ed25519Signature2020"},
                "evidence": [{"id": "e1"}],
                "verified_claims": [{"verified": True, "claim": "grade_band_A"}],
                "improvement_trajectory": [70, 75, 80, 85],
                "skill_scarcity_score": 60,
                "counterparty_acceptance_score": 50,
                "verified_performance_score": 82,
                "completion_probability": 0.9,
                "improvement_trajectory_score": 0.8,
                "time_to_outcome_discount": 0.9,
                "attendance_signal": 0.95,
                "grade_band": "A",
                "completion_status": "completed",
            },
            student_permissions={
                "reveal_grade_band": True,
                "reveal_raw_grade": False,
                "reveal_identity": "selective",
                "student_consent": True,
                "ferpa_compliant": True,
                "disclosure_mode": "minimal",
            },
            context={"use_case": "scholarship", "jurisdiction": "US"},
        )
        assert result["academic_liquidity_score"] > 0
        assert result["proof_of_scholarship_score"] > 0
        assert result["edu_mint_cap"] > 0
        assert "scholarship_pool" in result["recommended_routes"]
        assert result["receipt"]["schema"] == "membra.latentos.edu.liquidify_receipt.v1"

    def test_unverified_credential_low_score(self):
        engine = AcademicLiquidityEngine()
        result = engine.liquidify(
            credential={"type": "GradeBandCredential"},
            student_permissions={},
            context={},
        )
        assert result["academic_liquidity_score"] < 50
        assert "issuer_signature" in result["required_proofs"]


# ─── API Endpoint Tests ─────────────────────────────────────────────────

class TestAPI:
    def test_health(self):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"

    def test_dashboard(self):
        r = client.get("/")
        assert r.status_code == 200
        assert "LatentOS" in r.text

    def test_settle_signal_software(self):
        r = client.post("/v1/liquidity/settle-signal", json={
            "signal_type": "software_artifact",
            "payload": {"artifact_hash": "abc", "test_pass": True, "receipt": True},
            "provenance": {"source": "tool_verified", "confidence": 0.9, "verification_required": True},
            "privacy": {"disclosure_mode": "minimal", "blocked_fields": []},
            "market_context": {"purpose": "valuation"},
        })
        assert r.status_code == 200
        data = r.json()
        assert data["signal_liquidity_score"] > 0
        assert "receipt" in data

    def test_settle_signal_academic(self):
        r = client.post("/v1/liquidity/settle-signal", json={
            "signal_type": "academic_credential",
            "payload": {"issuer_signature": True, "student_consent": True, "ferpa_compliant": True},
            "provenance": {"source": "issuer_signed", "confidence": 0.95, "verification_required": True},
            "privacy": {"disclosure_mode": "minimal", "blocked_fields": ["raw_grade", "transcript"]},
            "market_context": {"purpose": "scholarship"},
        })
        assert r.status_code == 200
        data = r.json()
        assert data["proof_strength"] > 0

    def test_latent_liquidify(self):
        r = client.post("/v1/latent/liquidify", json={
            "payload": {"artifact_hash": "x", "deployment_evidence": True, "test_pass": True},
            "provenance": {"source": "tool_verified", "confidence": 0.8},
            "privacy": {"disclosure_mode": "minimal"},
            "market_context": {"purpose": "valuation"},
        })
        assert r.status_code == 200

    def test_breakage_map(self):
        r = client.post("/v1/breakage/map", json={
            "payload": {"breakage_type": "deployment_failure", "severity": "high", "reproducible": True},
            "provenance": {"source": "observed_behavior", "confidence": 0.8},
        })
        assert r.status_code == 200
        assert "liquidity_opportunities" in r.json()

    def test_gaps_detect(self):
        r = client.post("/v1/gaps/detect", json={
            "payload": {"has_tests": False, "secret_exposure": True},
            "provenance": {"source": "tool_verified", "confidence": 0.9},
        })
        assert r.status_code == 200
        assert r.json()["total_gaps"] >= 2

    def test_memory_grade(self):
        r = client.post("/v1/memory/grade", json={
            "claims": [{"summary": "deployed", "evidence": True, "receipt": True, "delta_proof": True}],
            "provenance": {"source": "tool_verified", "confidence": 0.9},
        })
        assert r.status_code == 200
        assert r.json()["verified"] == 1

    def test_valuation_pre_revenue(self):
        r = client.post("/v1/valuation/pre-revenue", json={
            "payload": {"proof_strength": 70, "deployment_readiness": 60},
            "market_context": {"purpose": "saas_opportunity"},
        })
        assert r.status_code == 200
        assert "estimated_valuation_usd" in r.json()

    def test_monetization_routes(self):
        r = client.post("/v1/monetization/routes", json={
            "payload": {"liquidity_score": 85, "signal_type": "software_artifact"},
            "market_context": {"purpose": "valuation"},
        })
        assert r.status_code == 200
        assert len(r.json()["routes"]) >= 3

    def test_edu_liquidify(self):
        r = client.post("/v1/edu/liquidify", json={
            "payload": {
                "type": "GradeBandCredential",
                "issuer": {"id": "did:web:uni.edu"},
                "proof": {"type": "Ed25519Signature2020"},
                "evidence": [{"id": "e1"}],
                "verified_claims": [{"verified": True}],
                "issuer_trust_score": 85,
                "grade_band": "A",
                "completion_status": "completed",
                "student_consent": True,
                "ferpa_compliant": True,
            },
            "provenance": {"source": "issuer_signed", "confidence": 0.95},
            "privacy": {"disclosure_mode": "minimal"},
            "market_context": {"purpose": "scholarship"},
        })
        assert r.status_code == 200
        data = r.json()
        assert data["academic_liquidity_score"] > 0
        assert data["edu_mint_cap"] > 0

    def test_edu_credential_verify(self):
        r = client.post("/v1/edu/credential/verify", json={
            "credential": {
                "issuer": {"id": "did:web:uni.edu"},
                "credential_subject": {"grade_band": "A"},
                "issuance_date": "2026-01-01",
                "type": "GradeBandCredential",
                "proof": {"type": "Ed25519Signature2020"},
                "evidence": [{"id": "e1"}],
            },
        })
        assert r.status_code == 200
        assert r.json()["valid"] is True

    def test_edu_disclosure_minimize(self):
        r = client.post("/v1/edu/disclosure/minimize", json={
            "credential": {"raw_grade": 95, "grade_band": "A", "student_name": "Jane", "issuer_id": "did:web:uni.edu"},
            "purpose": "scholarship",
            "disclosure_mode": "minimal",
        })
        assert r.status_code == 200
        assert "raw_grade" in r.json()["blocked_disclosure"]
        assert "grade_band" in r.json()["allowed_disclosure"]

    def test_edu_mint_cap(self):
        r = client.post("/v1/edu/mint-cap", json={
            "proof_of_scholarship_score": 75,
            "credential_count": 5,
            "issuer_trust": 0.9,
        })
        assert r.status_code == 200
        assert r.json()["edu_mint_cap"] > 0

    def test_edu_prediction_quote_and_settle(self):
        r1 = client.post("/v1/edu/prediction/quote", json={
            "credential": {"type": "CourseCompletedCredential"},
            "outcome": "complete_with_B",
            "stake_amount": 100,
            "proof_of_scholarship_score": 80,
        })
        assert r1.status_code == 200
        pred_id = r1.json()["prediction_id"]

        r2 = client.post("/v1/edu/prediction/settle", json={
            "prediction_id": pred_id,
            "outcome_achieved": True,
            "evidence": {"final_grade": "B"},
        })
        assert r2.status_code == 200
        assert r2.json()["status"] == "settled"

    def test_edu_claim_grade_rejected(self):
        r = client.post("/v1/edu/claim/grade", json={
            "payload": {"grade": 95},
            "provenance": {"source": "user_declared", "confidence": 0.1},
            "privacy": {"disclosure_mode": "minimal"},
            "market_context": {"purpose": "scholarship"},
        })
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"
        assert r.json()["reason"] == "unverified_self_claim"

    def test_academic_liquidify(self):
        r = client.post("/v1/academic/liquidify", json={
            "payload": {
                "type": "GradeBandCredential",
                "issuer": {"id": "did:web:uni.edu"},
                "proof": {"type": "Ed25519Signature2020"},
                "evidence": [{"id": "e1"}],
                "verified_claims": [{"verified": True}],
                "issuer_trust_score": 80,
                "grade_band": "B",
                "completion_status": "completed",
                "student_consent": True,
                "ferpa_compliant": True,
            },
            "provenance": {"source": "issuer_signed", "confidence": 0.9},
            "privacy": {"disclosure_mode": "minimal"},
            "market_context": {"purpose": "scholarship"},
        })
        assert r.status_code == 200
        assert r.json()["academic_liquidity_score"] > 0

    def test_academic_scholarship_match(self):
        r = client.post("/v1/academic/scholarship/match", json={
            "payload": {
                "verified_claims": [{"verified": True}] * 5,
                "issuer_trust_score": 90,
                "credentials": [{"status": "active"}] * 3,
                "improvement_trajectory": [70, 80, 90],
                "skill_scarcity_score": 70,
                "evidence_links": ["e1", "e2"],
                "privacy_permissions": {"disclosure_mode": "minimal"},
            },
            "market_context": {"purpose": "scholarship"},
        })
        assert r.status_code == 200
        assert len(r.json()["matches"]) > 0

    def test_academic_proof_profile(self):
        r = client.post("/v1/academic/proof-profile", json={
            "payload": {
                "credentials": [{"type": "GradeBandCredential", "status": "active"}],
                "verified_claims": [{"verified": True}],
                "evidence_links": ["e1"],
                "privacy_permissions": {"disclosure_mode": "minimal"},
                "reveal_identity": "selective",
            },
            "market_context": {"purpose": "scholarship"},
        })
        assert r.status_code == 200
        assert "proof_of_scholarship_score" in r.json()
        assert "student_profile" in r.json()
