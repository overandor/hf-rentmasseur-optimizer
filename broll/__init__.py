"""
OverVisual — Semantic Visual Evidence Compilation

A narration-to-evidence compilation system that maps claims into visual
representations while explicitly preserving uncertainty, evidentiary
status, provenance, and licensing constraints.

This is NOT standard multimedia retrieval (CLIP, CLIP4Clip, semantic
video retrieval). Those systems ask: "What image matches this sentence?"

OverVisual asks: "What visual evidence should accompany this claim,
and what is the epistemic status of that claim?"

The core object is a VisualEvidenceSegment — not a VideoClip.
A VideoClip is media. A VisualEvidenceSegment is:
    claim + visual explanation + truth label + rights label + provenance + receipt

That is closer to an evidence graph node than a media asset.

Architecture:
    OverLLM      — understands meaning
    OverVisual   — finds visual equivalents
    Truth Layer  — separates evidence from symbolism
    Rights Layer — separates usable from unusable footage
    Proof Layer  — creates audit receipts

The result is an evidence-backed audiovisual ledger, not an editing timeline.

Novelty claims (defensible):
    1. Claim-aware B-roll retrieval
    2. Separation of semantic similarity from truth status
    3. Rights-aware evidence compilation
    4. Hash-receipted visual provenance
    5. VisualEvidenceSegment as a first-class artifact

Prior art acknowledged:
    - Semantic video retrieval: CLIP, CLIP4Clip (arXiv:2103.00020, arXiv:2103.10095)
    - Fact checking: claim extraction, evidence retrieval, provenance
    - The fusion of these into a unified narration-to-evidence compiler
      is where the potentially novel contribution lies.

Core principle: semantic match ≠ truth
"""

from .concept_extractor import ConceptExtractor, Concept, MeaningAtom
from .claim_extractor import ClaimExtractor, Claim, TruthStatus
from .association_graph import VisualAssociationGraph, VisualArchetype, AssociationEdge
from .video_search import VideoSearch, VideoCandidate, ClipScore
from .clip_matcher import CLIPMatcher, FrameSample, ClipMatchResult
from .youtube_search import YouTubeSearch, YouTubeVideo, CaptionTrack
from .timeline import Timeline, TimelineSegment, TimelineAssembler
from .rights_filter import RightsFilter, RightsStatus, RightsAssessment, LicenseType
from .proofs import ProofGenerator, ProofChain
from .visual_evidence_segment import (
    VisualEvidenceSegment,
    VESEnsemble,
    compute_truth_safety_score,
    compute_evidence_relevance_score,
)
from .compiler import (
    OverVisualCompiler,
    BrollCompiler,
    CompilationResult,
    CompilationReceipt,
)
from .evidence_graph import EvidenceGraph, EvidenceAssessment, EvidenceNode, EvidenceType, ConfidenceLevel
from .missing_visual_detector import MissingVisualDetector, MissingVisual, MissingVisualReport
from .simulation_engine import SimulationEngine, SimulationSpec
from .scientific_claim import (
    ScientificClaim,
    ScientificStatus,
    Paper,
    Experiment,
    determine_status,
    compute_confidence,
)
from .investigation_graph import InvestigationGraph, SearchRecord, InvestigationStep
from .investigation_engine import InvestigationEngine
from .media_compiler import MediaCompiler, MediaOutput
from .machine_scores import (
    MachineScoreSet,
    compute_rights_safety_score,
    compute_provenance_completeness_score,
    compute_machine_buyability_score,
    compute_all_machine_scores,
)
from .mevf import MEVFObject, MEVFSegment, MEVFBuilder, query_segments
from .investigation_visualizer import (
    VisualizationData,
    claim_heatmap,
    evidence_density_timeline,
    contradiction_map,
    replication_ladder,
    rights_safety_timeline,
    machine_trust_curve,
    uncertainty_cinema,
    generate_all_visualizations,
)
from .investigation_memory import InvestigationMemory, ReusableArtifact, ReusableBundle
from .vrap import VRAPManifest, VRAPBuilder, MicroAsset
from .machine_attention import machine_attention_track, claim_lattice
from .videolake import VideoLakeCompiler, VideoLakeResult, SceneNode
from .evidence_core import (
    EvidenceGraphCore,
    EvidenceNode,
    EvidenceEdge,
    EvidenceNodeType,
    EvidenceEdgeType,
    EvidenceManifest,
    EvidenceReceipt,
    MerkleNode,
)
from .provenance_graph import ProvenanceGraph, FileArtifact, CommitRecord, DependencyRecord
from .evidence_os import EvidenceOS, EvidenceOSResult, UnifiedScores
from .renderer import MP4Renderer, RenderResult
from .youtube_metadata import YouTubeMetadataGenerator, YouTubeMetadata
from .mcrv import (
    MCRVCompiler,
    MCRVSidecar,
    MachinePersuasionVector,
    AgentPurchaseSurface,
    ReproductionCapsule,
    MachineNativeTimelineEntry,
    MCRVPacker,
)
from .multi_renderer import (
    MultiRenderer,
    ReportRenderer,
    DatasetRenderer,
    SlidesRenderer,
    PodcastRenderer,
    APIRenderer,
    RenderArtifact,
)
from .rights_vault import (
    RightsVault,
    RightsLedger,
    PayoutSimulator,
    FRVO,
    VRRU,
    Backer,
    OfferingMode,
    OfferingStatus,
    BackerType,
    RevenueSource,
    PayoutWaterfallTier,
    RiskDisclosure,
    PayoutResult,
)
from .youtube_os import (
    InvestigationYouTubeOS,
    Episode,
    Playlist,
    Subscription,
    ChannelAnalytics,
    EpisodeStatus,
    create_youtube_os_api,
)
from .astro_measurements import (
    AstroMeasurement,
    AstroMeasurementRegistry,
    AstroInvestigationEngine,
)
from .revenue_pipeline import (
    VideoToRevenuePipeline,
    VideoToRevenueResult,
    MonetizationMetadata,
    RevenueEstimate,
    RevenueTimeline,
    AdBreak,
    SponsorshipSlot,
)
from .belt_prospector import (
    BeltProspector,
    BeltProspect,
    BeltSurvey,
)
from .video_genome import (
    VideoSystemsGenome,
    RepoFingerprint,
    CapabilityNode,
    CapabilityEdge,
    CapabilityGraph,
    CapabilityType,
    LicenseSafety,
    SecurityRisk,
    IncorporationLevel,
    WorkflowComposition,
)
from .asset_compiler import (
    AssetCompiler,
    AssetManifest,
    AssetCompileResult,
)
from .grade_bond import (
    GradeBondProtocol,
    GradeBondLedger,
    GradeClaim,
    Bond,
    Challenge,
    Settlement,
    BMMA,
    Rubric,
    RubricDimension,
    SlashSchedule,
    SlashTier,
    ClaimStatus,
    ChallengeVerdict,
    ProducerTrackRecord,
    AuditDraw,
    BondedEvidenceAsset,
    compute_required_bond,
    verify_artifact_hash,
)
from .standards_export import (
    StandardsExporter,
    C2PAManifest,
    C2PAClaim,
    C2PAAssertion,
    C2PAIngredient,
    C2PAAction,
)
from .segment_marketplace import (
    SegmentMarketplace,
    SegmentListing,
    PriceQuote,
    Purchase,
    LicenseTier,
    PurchaseStatus,
)

__all__ = [
    "ConceptExtractor",
    "Concept",
    "MeaningAtom",
    "ClaimExtractor",
    "Claim",
    "TruthStatus",
    "VisualAssociationGraph",
    "VisualArchetype",
    "AssociationEdge",
    "VideoSearch",
    "VideoCandidate",
    "ClipScore",
    "CLIPMatcher",
    "FrameSample",
    "ClipMatchResult",
    "YouTubeSearch",
    "YouTubeVideo",
    "CaptionTrack",
    "Timeline",
    "TimelineSegment",
    "TimelineAssembler",
    "RightsFilter",
    "RightsStatus",
    "RightsAssessment",
    "LicenseType",
    "ProofGenerator",
    "ProofChain",
    "VisualEvidenceSegment",
    "VESEnsemble",
    "compute_truth_safety_score",
    "compute_evidence_relevance_score",
    "OverVisualCompiler",
    "BrollCompiler",
    "CompilationResult",
    "CompilationReceipt",
    "EvidenceGraph",
    "EvidenceAssessment",
    "EvidenceNode",
    "EvidenceType",
    "ConfidenceLevel",
    "MissingVisualDetector",
    "MissingVisual",
    "MissingVisualReport",
    "SimulationEngine",
    "SimulationSpec",
    "ScientificClaim",
    "ScientificStatus",
    "Paper",
    "Experiment",
    "determine_status",
    "compute_confidence",
    "InvestigationGraph",
    "SearchRecord",
    "InvestigationStep",
    "InvestigationEngine",
    "MediaCompiler",
    "MediaOutput",
    "MachineScoreSet",
    "compute_rights_safety_score",
    "compute_provenance_completeness_score",
    "compute_machine_buyability_score",
    "compute_all_machine_scores",
    "MEVFObject",
    "MEVFSegment",
    "MEVFBuilder",
    "query_segments",
    "VisualizationData",
    "claim_heatmap",
    "evidence_density_timeline",
    "contradiction_map",
    "replication_ladder",
    "rights_safety_timeline",
    "machine_trust_curve",
    "uncertainty_cinema",
    "generate_all_visualizations",
    "InvestigationMemory",
    "ReusableArtifact",
    "ReusableBundle",
    "VRAPManifest",
    "VRAPBuilder",
    "MicroAsset",
    "machine_attention_track",
    "claim_lattice",
    "VideoLakeCompiler",
    "VideoLakeResult",
    "SceneNode",
    "MP4Renderer",
    "RenderResult",
    "YouTubeMetadataGenerator",
    "YouTubeMetadata",
    "InvestigationYouTubeOS",
    "Episode",
    "Playlist",
    "Subscription",
    "ChannelAnalytics",
    "EpisodeStatus",
    "create_youtube_os_api",
    "EvidenceGraphCore",
    "EvidenceNode",
    "EvidenceEdge",
    "EvidenceNodeType",
    "EvidenceEdgeType",
    "EvidenceManifest",
    "EvidenceReceipt",
    "MerkleNode",
    "ProvenanceGraph",
    "FileArtifact",
    "CommitRecord",
    "DependencyRecord",
    "EvidenceOS",
    "EvidenceOSResult",
    "UnifiedScores",
    "YouTubeMetadata",
    "YouTubeMetadataGenerator",
    "MCRVCompiler",
    "MCRVSidecar",
    "MachinePersuasionVector",
    "AgentPurchaseSurface",
    "ReproductionCapsule",
    "MachineNativeTimelineEntry",
    "MCRVPacker",
    "MultiRenderer",
    "ReportRenderer",
    "DatasetRenderer",
    "SlidesRenderer",
    "PodcastRenderer",
    "APIRenderer",
    "RenderArtifact",
    "RightsVault",
    "RightsLedger",
    "PayoutSimulator",
    "FRVO",
    "VRRU",
    "Backer",
    "OfferingMode",
    "OfferingStatus",
    "BackerType",
    "RevenueSource",
    "PayoutWaterfallTier",
    "RiskDisclosure",
    "PayoutResult",
    "AstroMeasurement",
    "AstroMeasurementRegistry",
    "AstroInvestigationEngine",
    "VideoToRevenuePipeline",
    "VideoToRevenueResult",
    "MonetizationMetadata",
    "RevenueEstimate",
    "RevenueTimeline",
    "AdBreak",
    "SponsorshipSlot",
    "BeltProspector",
    "BeltProspect",
    "BeltSurvey",
    "VideoSystemsGenome",
    "RepoFingerprint",
    "CapabilityNode",
    "CapabilityEdge",
    "CapabilityGraph",
    "CapabilityType",
    "LicenseSafety",
    "SecurityRisk",
    "IncorporationLevel",
    "WorkflowComposition",
    "AssetCompiler",
    "AssetManifest",
    "AssetCompileResult",
    "GradeBondProtocol",
    "GradeBondLedger",
    "GradeClaim",
    "Bond",
    "Challenge",
    "Settlement",
    "BMMA",
    "Rubric",
    "RubricDimension",
    "SlashSchedule",
    "SlashTier",
    "ClaimStatus",
    "ChallengeVerdict",
    "ProducerTrackRecord",
    "AuditDraw",
    "BondedEvidenceAsset",
    "compute_required_bond",
    "verify_artifact_hash",
    "StandardsExporter",
    "C2PAManifest",
    "C2PAClaim",
    "C2PAAssertion",
    "C2PAIngredient",
    "C2PAAction",
    "SegmentMarketplace",
    "SegmentListing",
    "PriceQuote",
    "Purchase",
    "LicenseTier",
    "PurchaseStatus",
]
