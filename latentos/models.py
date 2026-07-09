"""Pydantic models for LatentOS + LatentOS EDU API."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SignalType(str, Enum):
    software_artifact = "software_artifact"
    academic_credential = "academic_credential"
    deployment_failure = "deployment_failure"
    memory_claim = "memory_claim"
    verification_gap = "verification_gap"


class ProvenanceSource(str, Enum):
    user_declared = "user_declared"
    observed_behavior = "observed_behavior"
    uploaded_file = "uploaded_file"
    issuer_signed = "issuer_signed"
    tool_verified = "tool_verified"
    external_verified = "external_verified"


class DisclosureMode(str, Enum):
    minimal = "minimal"
    threshold_only = "threshold_only"
    settlement_only = "settlement_only"
    full_with_consent = "full_with_consent"


class MarketPurpose(str, Enum):
    valuation = "valuation"
    scholarship = "scholarship"
    credit = "credit"
    prediction = "prediction"
    eval_dataset = "eval_dataset"
    saas_opportunity = "SaaS_opportunity"
    grant = "grant"
    advisory = "advisory"


class Provenance(BaseModel):
    source: ProvenanceSource = ProvenanceSource.user_declared
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    verification_required: bool = True


class PrivacyConfig(BaseModel):
    disclosure_mode: DisclosureMode = DisclosureMode.minimal
    blocked_fields: List[str] = Field(default_factory=list)


class MarketContext(BaseModel):
    purpose: MarketPurpose = MarketPurpose.valuation


class SettleSignalRequest(BaseModel):
    signal_type: SignalType
    payload: Dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    market_context: MarketContext = Field(default_factory=MarketContext)


class ValueRange(BaseModel):
    low: float = 0.0
    mid: float = 0.0
    high: float = 0.0


class SettleSignalResponse(BaseModel):
    signal_liquidity_score: float
    proof_strength: float
    privacy_risk: float
    fraud_risk: float
    deployment_or_settlement_readiness: float
    estimated_value_range_usd: ValueRange
    allowed_disclosure: List[str] = Field(default_factory=list)
    blocked_disclosure: List[str] = Field(default_factory=list)
    liquidification_routes: List[str] = Field(default_factory=list)
    required_next_proofs: List[str] = Field(default_factory=list)
    receipt: Dict[str, Any] = Field(default_factory=dict)


class LiquidifyRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    market_context: MarketContext = Field(default_factory=MarketContext)


class BreakageMapRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)


class GapDetectRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)
    provenance: Provenance = Field(default_factory=Provenance)


class MemoryGradeRequest(BaseModel):
    claims: List[Dict[str, Any]] = Field(default_factory=list)
    provenance: Provenance = Field(default_factory=Provenance)


class PreRevenueValuationRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)
    market_context: MarketContext = Field(default_factory=MarketContext)


class MonetizationRoutesRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)
    market_context: MarketContext = Field(default_factory=MarketContext)


class CredentialVerifyRequest(BaseModel):
    credential: Dict[str, Any] = Field(default_factory=dict)
    issuer_did: Optional[str] = None
    verification_method: Optional[str] = None


class DisclosureMinimizeRequest(BaseModel):
    credential: Dict[str, Any] = Field(default_factory=dict)
    purpose: MarketPurpose = MarketPurpose.scholarship
    disclosure_mode: DisclosureMode = DisclosureMode.minimal


class MintCapRequest(BaseModel):
    proof_of_scholarship_score: float = Field(0.0, ge=0.0, le=100.0)
    credential_count: int = Field(0, ge=0)
    issuer_trust: float = Field(0.0, ge=0.0, le=1.0)


class PredictionQuoteRequest(BaseModel):
    credential: Dict[str, Any] = Field(default_factory=dict)
    outcome: str = ""
    stake_amount: float = Field(0.0, ge=0.0)
    proof_of_scholarship_score: float = Field(0.0, ge=0.0, le=100.0)


class PredictionSettleRequest(BaseModel):
    prediction_id: str
    outcome_achieved: bool
    evidence: Dict[str, Any] = Field(default_factory=dict)
