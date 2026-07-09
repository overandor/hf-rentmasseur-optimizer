"""
Evidence Asset Revenue Oracle — local-first, Ollama-powered proof system.

Core thesis: Do not sell cognition. Sell verified evidence packets, proof reports,
licensed artifacts, and receipt-backed utility records.

Default token mode: proof_only
Default LLM: local Ollama (http://localhost:11434)
Default storage: SQLite
"""

from .schema import OracleDB, ArtifactRecord, EvidencePacket, RevenueReceipt, MediaAssetRecord
from .receipt_ledger import ReceiptLedger, Receipt
from .ollama_client import OllamaClient
from .risk_engine import RiskEngine, ComplianceBlocker, TokenMode, AssetStatus
from .evidence_packet import EvidencePacketBuilder
from .landing_page import LandingPageGenerator, LandingPage
from .revenue_module import RevenueModule, RevenueFlow
from .token_engine import TokenEngine, TokenManifest
from .bmma_builder import BMMABuilder, BMMAResult
from .videolake_bmma_bridge import VideoLakeBMMABridge, VideoLakeBMMAImport
from .arrow_vault import ArrowBacktestVault, ArrowReceipt, ArrowCase, SealedGrader, BaselineScorer
from .agent_loop import AgentLoop
from .dashboard import create_app
from .rbc import RBCEngine, ResponseBackendCapsule, EconomicProof, CapsuleStatus
from .integration_bridges import (
    SGEBridge, SealedGradeClaim,
    AAUBridge,
    PayoutWaterfallEngine, WaterfallTier, PayoutResult,
    LicensingEngine, LicenseRecord, LicenseType,
    EscrowProtocol, EscrowHold, EscrowStatus,
    RevenueSettlementEngine, SettlementResult,
    ValuationReconciliation, ReconciledValuation,
    EvidenceOSBridge,
    VideoLakeBridge,
)
from .extended_bridges import (
    SystemLakeBridge,
    QuestionOSBridge,
    ComplianceChecklistEngine, ComplianceReport, ComplianceCheck, ComplianceStatus,
    ModelSwappingLayer, ModelConfig, ModelResponse, ModelProvider,
    DeploymentReceiptProtocol, DeploymentReceipt,
    ProofExportEngine, ProofExport,
    MultiModelConsensus, ConsensusResult,
    HallucinationDetector, HallucinationReport,
)
from .deployment_adapters import (
    DeploymentManager, DeploymentConfig, AdapterResult,
    VercelAdapter, NetlifyAdapter, IPFSAdapter, LocalStaticAdapter,
)
from .verification_audit import (
    RevenueAttestationEngine, RevenueAttestation, AttestationStatus,
    AuditTrailExporter, AuditTrail,
    SLSABuildProvenance, SLSAProvenance, SLSALevel,
    FAIRRiskScoring, FAIRRiskScore, FAIRLossMagnitude,
)

__all__ = [
    "OracleDB",
    "ArtifactRecord",
    "EvidencePacket",
    "RevenueReceipt",
    "MediaAssetRecord",
    "ReceiptLedger",
    "Receipt",
    "OllamaClient",
    "RiskEngine",
    "ComplianceBlocker",
    "TokenMode",
    "AssetStatus",
    "EvidencePacketBuilder",
    "LandingPageGenerator",
    "LandingPage",
    "RevenueModule",
    "RevenueFlow",
    "TokenEngine",
    "TokenManifest",
    "BMMABuilder",
    "BMMAResult",
    "VideoLakeBMMABridge",
    "VideoLakeBMMAImport",
    "ArrowBacktestVault",
    "ArrowReceipt",
    "ArrowCase",
    "SealedGrader",
    "BaselineScorer",
    "AgentLoop",
    "create_app",
    # Protocol 194: RBC
    "RBCEngine",
    "ResponseBackendCapsule",
    "EconomicProof",
    "CapsuleStatus",
    # Protocol 195-204: Integration Bridges
    "SGEBridge",
    "SealedGradeClaim",
    "AAUBridge",
    "PayoutWaterfallEngine",
    "WaterfallTier",
    "PayoutResult",
    "LicensingEngine",
    "LicenseRecord",
    "LicenseType",
    "EscrowProtocol",
    "EscrowHold",
    "EscrowStatus",
    "RevenueSettlementEngine",
    "SettlementResult",
    "ValuationReconciliation",
    "ReconciledValuation",
    "EvidenceOSBridge",
    "VideoLakeBridge",
    # Protocol 205-212: Extended Bridges
    "SystemLakeBridge",
    "QuestionOSBridge",
    "ComplianceChecklistEngine",
    "ComplianceReport",
    "ComplianceCheck",
    "ComplianceStatus",
    "ModelSwappingLayer",
    "ModelConfig",
    "ModelResponse",
    "ModelProvider",
    "DeploymentReceiptProtocol",
    "DeploymentReceipt",
    "ProofExportEngine",
    "ProofExport",
    "MultiModelConsensus",
    "ConsensusResult",
    "HallucinationDetector",
    "HallucinationReport",
    # Protocol 213-216: Deployment Adapters
    "DeploymentManager",
    "DeploymentConfig",
    "AdapterResult",
    "VercelAdapter",
    "NetlifyAdapter",
    "IPFSAdapter",
    "LocalStaticAdapter",
    # Protocol 217-220: Verification & Audit
    "RevenueAttestationEngine",
    "RevenueAttestation",
    "AttestationStatus",
    "AuditTrailExporter",
    "AuditTrail",
    "SLSABuildProvenance",
    "SLSAProvenance",
    "SLSALevel",
    "FAIRRiskScoring",
    "FAIRRiskScore",
    "FAIRLossMagnitude",
]
