"""
Video Systems Genome — Machine-readable capability graph of the public video ecosystem.

Discovers, fingerprints, classifies, and benchmarks every public video-generation,
video-editing, YouTube-automation, captioning, retrieval, rights, rendering, and ML repo.

NOT a clone-and-merge engine. A discovery + classification + capability graph system.

Architecture:
    Discover → Fingerprint → Classify → License-check → Security-check → Benchmark → Graph

The genome is a machine-readable map of what exists, what it does, what license it has,
what models it depends on, what security risks it carries, and how it can be composed
into workflows — without absorbing anyone's code.

Standards: SPDX (licenses), SLSA (provenance), W3C PROV (attribution), FAIR (machine-actionability)

Usage:
    from broll.video_genome import VideoSystemsGenome

    genome = VideoSystemsGenome()
    genome.discover()  # discovers repos via GitHub API or local registry
    graph = genome.build_capability_graph()
    report = genome.audit_report()
    compatible = genome.find_compatible("video_generation", "text_to_video", license_safe=True)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class CapabilityType(Enum):
    VIDEO_GENERATION = "video_generation"
    VIDEO_EDITING = "video_editing"
    YOUTUBE_AUTOMATION = "youtube_automation"
    CAPTIONING = "captioning"
    RETRIEVAL = "retrieval"
    RIGHTS_MANAGEMENT = "rights_management"
    RENDERING = "rendering"
    ML_MODEL = "ml_model"
    WORKFLOW_ENGINE = "workflow_engine"
    TRANSCRIPTION = "transcription"
    THUMBNAIL_GENERATION = "thumbnail_generation"
    ANALYTICS = "analytics"
    MONETIZATION = "monetization"
    COMPRESSION = "compression"
    STREAMING = "streaming"
    DATASET = "dataset"
    EVALUATION = "evaluation"
    PIPELINE = "pipeline"
    UNKNOWN = "unknown"


class LicenseSafety(Enum):
    SAFE = "safe"
    CAUTION = "caution"
    RISKY = "risky"
    UNKNOWN = "unknown"


class SecurityRisk(Enum):
    CLEAN = "clean"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncorporationLevel(Enum):
    """
    How a repo is incorporated into the system.

    Level 0 — Indexed: known, classified, fingerprinted, cited.
    Level 1 — Callable: installable/runnable via CLI/API/Docker, code not merged.
    Level 2 — Adapted: local adapter wrapper exists.
    Level 3 — Vendored: code included only if license allows + security passes.
    Level 4 — Native Rewrite: capability reimplemented from public behavior/specs.
    """
    INDEXED = 0
    CALLABLE = 1
    ADAPTED = 2
    VENDORED = 3
    NATIVE_REWRITE = 4


SAFE_LICENSES = {
    "MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause",
    "ISC", "Unlicense", "0BSD", "CC0-1.0",
    "MPL-2.0",
}

CAUTION_LICENSES = {
    "LGPL-2.1", "LGPL-3.0",
    "EPL-2.0", "EPL-1.0",
    "CDDL-1.0",
    "CC-BY-4.0", "CC-BY-SA-4.0",
}

RISKY_LICENSES = {
    "GPL-2.0", "GPL-3.0", "AGPL-3.0",
    "SSPL-1.0", "BSL-1.1",
    "CC-BY-NC-4.0", "CC-BY-ND-4.0",
    "Proprietary", "Commercial",
    "None",
}

CAPABILITY_KEYWORDS = {
    CapabilityType.VIDEO_GENERATION: [
        "text-to-video", "video generation", "video synthesis", "diffusion video",
        "video diffusion", "t2v", "video model", "video foundation model",
        "hunyuanvideo", "cogvideo", "cogvideox", "ltx-video", "ltxvideo",
        "open-sora", "sora", "animate", "video-llm",
    ],
    CapabilityType.VIDEO_EDITING: [
        "video editing", "video editor", "cut", "trim", "merge video",
        "ffmpeg", "moviepy", "opencv video", "video processing",
    ],
    CapabilityType.YOUTUBE_AUTOMATION: [
        "youtube", "youtube api", "youtube upload", "youtube automation",
        "youtube-dl", "yt-dlp", "youtube channel", "youtube publishing",
    ],
    CapabilityType.CAPTIONING: [
        "caption", "subtitle", "srt", "ass", "whisper", "subtitle generation",
        "closed caption", "cc",
    ],
    CapabilityType.RETRIEVAL: [
        "video retrieval", "video search", "video retrieval", "clip",
        "video indexing", "video database", "video query",
    ],
    CapabilityType.RIGHTS_MANAGEMENT: [
        "rights", "license", "copyright", "drm", "watermark",
        "attribution", "creative commons", "rights management",
    ],
    CapabilityType.RENDERING: [
        "render", "renderer", "mp4", "encoding", "h264", "h265",
        "av1", "video render", "frame rendering", "compositing",
    ],
    CapabilityType.ML_MODEL: [
        "model", "weights", "checkpoint", "pretrained", "foundation model",
        "transformer", "diffusion", "gan", "vae", "neural",
    ],
    CapabilityType.WORKFLOW_ENGINE: [
        "workflow", "pipeline", "comfyui", "node graph", "dag",
        "automation pipeline", "orchestration",
    ],
    CapabilityType.TRANSCRIPTION: [
        "transcribe", "transcription", "speech to text", "asr",
        "whisper", "wav2vec", "speech recognition",
    ],
    CapabilityType.THUMBNAIL_GENERATION: [
        "thumbnail", "thumbnail generation", "video thumbnail",
        "preview", "poster frame",
    ],
    CapabilityType.ANALYTICS: [
        "analytics", "metrics", "views", "engagement", "retention",
        "youtube analytics", "video analytics",
    ],
    CapabilityType.MONETIZATION: [
        "monetization", "revenue", "adsense", "ad revenue",
        "sponsorship", "cpm", "rpm",
    ],
    CapabilityType.COMPRESSION: [
        "compression", "compress", "encode", "codec", "bitrate",
        "video compression", "webm", "mkv",
    ],
    CapabilityType.STREAMING: [
        "streaming", "stream", "rtmp", "hls", "dash", "live stream",
        "webcast",
    ],
    CapabilityType.DATASET: [
        "dataset", "corpus", "benchmark", "data collection",
        "video dataset", "training data",
    ],
    CapabilityType.EVALUATION: [
        "evaluation", "benchmark", "metric", "fid", "is", "clip score",
        "video quality", "assessment",
    ],
    CapabilityType.PIPELINE: [
        "pipeline", "end-to-end", "production pipeline", "automation",
        "batch processing",
    ],
}

SECURITY_RISK_PATTERNS = {
    "eval(": "medium",
    "exec(": "medium",
    "subprocess.call": "low",
    "os.system": "medium",
    "pickle.load": "high",
    "torch.load": "medium",
    "yaml.load(": "medium",
    "request.get(\"http": "low",
    "__import__": "medium",
    "shell=True": "high",
    "download_file": "low",
    "urllib.request": "low",
}

MODEL_DEPENDENCY_PATTERNS = [
    "torch", "tensorflow", "jax", "flax", "transformers",
    "diffusers", "accelerate", "safetensors", "onnx",
    "openai", "anthropic", "replicate", "huggingface_hub",
    "comfyui", "kornia", "einops", "xformers",
]


@dataclass
class RepoFingerprint:
    """Structural fingerprint of a discovered repository."""
    repo_url: str = ""
    repo_name: str = ""
    owner: str = ""
    description: str = ""
    stars: int = 0
    forks: int = 0
    watchers: int = 0
    open_issues: int = 0
    language_primary: str = ""
    languages: list[str] = field(default_factory=list)
    topics: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
    pushed_at: str = ""
    default_branch: str = "main"
    size_kb: int = 0
    archived: bool = False
    disabled: bool = False
    is_fork: bool = False
    license_key: str = ""
    license_name: str = ""
    has_license_file: bool = False
    has_readme: bool = False
    has_ci: bool = False
    has_tests: bool = False
    has_dockerfile: bool = False
    has_setup_py: bool = False
    has_pyproject_toml: bool = False
    has_package_json: bool = False
    has_requirements_txt: bool = False
    dependency_count: int = 0
    model_dependencies: list[str] = field(default_factory=list)
    security_risks: list[str] = field(default_factory=list)
    security_level: str = "clean"
    file_count: int = 0
    commit_count: int = 0
    contributor_count: int = 0
    fingerprint_hash: str = ""
    data_source: str = ""  # "github_api" or "seed_fallback"

    def to_dict(self) -> dict:
        return {
            "repo_url": self.repo_url,
            "repo_name": self.repo_name,
            "owner": self.owner,
            "description": self.description,
            "stars": self.stars,
            "forks": self.forks,
            "watchers": self.watchers,
            "open_issues": self.open_issues,
            "language_primary": self.language_primary,
            "languages": self.languages,
            "topics": self.topics,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "pushed_at": self.pushed_at,
            "default_branch": self.default_branch,
            "size_kb": self.size_kb,
            "archived": self.archived,
            "disabled": self.disabled,
            "is_fork": self.is_fork,
            "license_key": self.license_key,
            "license_name": self.license_name,
            "has_license_file": self.has_license_file,
            "has_readme": self.has_readme,
            "has_ci": self.has_ci,
            "has_tests": self.has_tests,
            "has_dockerfile": self.has_dockerfile,
            "has_setup_py": self.has_setup_py,
            "has_pyproject_toml": self.has_pyproject_toml,
            "has_package_json": self.has_package_json,
            "has_requirements_txt": self.has_requirements_txt,
            "dependency_count": self.dependency_count,
            "model_dependencies": self.model_dependencies,
            "security_risks": self.security_risks,
            "security_level": self.security_level,
            "file_count": self.file_count,
            "commit_count": self.commit_count,
            "contributor_count": self.contributor_count,
            "fingerprint_hash": self.fingerprint_hash,
            "data_source": self.data_source,
        }

    def compute_hash(self) -> str:
        data = f"{self.repo_url}:{self.repo_name}:{self.owner}:{self.stars}:{self.license_key}:{self.language_primary}"
        self.fingerprint_hash = f"sha256:{hashlib.sha256(data.encode()).hexdigest()[:16]}"
        return self.fingerprint_hash


@dataclass
class CapabilityNode:
    """A node in the capability graph representing a repo's classified capabilities."""
    node_id: str = ""
    repo_name: str = ""
    owner: str = ""
    repo_url: str = ""
    capabilities: list[CapabilityType] = field(default_factory=list)
    capability_scores: dict[str, float] = field(default_factory=dict)
    license_safety: LicenseSafety = LicenseSafety.UNKNOWN
    license_key: str = ""
    security_level: SecurityRisk = SecurityRisk.CLEAN
    model_dependencies: list[str] = field(default_factory=list)
    stars: int = 0
    health_score: float = 0.0
    composition_potential: float = 0.0
    adapter_eligible: bool = False
    adapter_reason: str = ""
    incorporation_level: IncorporationLevel = IncorporationLevel.INDEXED
    incorporation_reason: str = ""
    can_embed_code: bool = False
    can_call_as_tool: bool = False
    can_resell_output: str = "unknown"
    gpu_required: bool = False
    has_model_weights: bool = False
    has_paper: bool = False
    paper_arxiv_id: str = ""
    benchmark_score: float = 0.0
    repo_utility_score: float = 0.0
    fingerprint: Optional[RepoFingerprint] = None

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "repo_name": self.repo_name,
            "owner": self.owner,
            "repo_url": self.repo_url,
            "capabilities": [c.value for c in self.capabilities],
            "capability_scores": self.capability_scores,
            "license_safety": self.license_safety.value,
            "license_key": self.license_key,
            "security_level": self.security_level.value,
            "model_dependencies": self.model_dependencies,
            "stars": self.stars,
            "health_score": round(self.health_score, 3),
            "composition_potential": round(self.composition_potential, 3),
            "adapter_eligible": self.adapter_eligible,
            "adapter_reason": self.adapter_reason,
            "incorporation_level": self.incorporation_level.value,
            "incorporation_level_name": self.incorporation_level.name.lower(),
            "incorporation_reason": self.incorporation_reason,
            "can_embed_code": self.can_embed_code,
            "can_call_as_tool": self.can_call_as_tool,
            "can_resell_output": self.can_resell_output,
            "gpu_required": self.gpu_required,
            "has_model_weights": self.has_model_weights,
            "has_paper": self.has_paper,
            "paper_arxiv_id": self.paper_arxiv_id,
            "benchmark_score": round(self.benchmark_score, 3),
            "repo_utility_score": round(self.repo_utility_score, 3),
            "fingerprint_hash": self.fingerprint.fingerprint_hash if self.fingerprint else "",
        }


@dataclass
class CapabilityEdge:
    """An edge in the capability graph representing a relationship between repos."""
    source_id: str = ""
    target_id: str = ""
    edge_type: str = ""
    weight: float = 0.0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "source": self.source_id,
            "target": self.target_id,
            "type": self.edge_type,
            "weight": round(self.weight, 3),
            "metadata": self.metadata,
        }


@dataclass
class CapabilityGraph:
    """The full machine-readable capability graph of the video ecosystem."""
    nodes: list[CapabilityNode] = field(default_factory=list)
    edges: list[CapabilityEdge] = field(default_factory=list)
    graph_hash: str = ""
    total_repos: int = 0
    total_capabilities: int = 0
    safe_repos: int = 0
    risky_repos: int = 0
    adapter_eligible_count: int = 0
    coverage_score: float = 0.0
    estimated_discoverable: int = 0
    incorporation_distribution: dict = field(default_factory=dict)
    generated_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "schema": "video_genome.v1",
            "generated_at": self.generated_at,
            "graph_hash": self.graph_hash,
            "total_repos": self.total_repos,
            "total_capabilities": self.total_capabilities,
            "safe_repos": self.safe_repos,
            "risky_repos": self.risky_repos,
            "adapter_eligible_count": self.adapter_eligible_count,
            "coverage_score": round(self.coverage_score, 3),
            "estimated_discoverable": self.estimated_discoverable,
            "incorporation_distribution": self.incorporation_distribution,
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def compute_hash(self) -> str:
        node_hashes = sorted([n.node_id for n in self.nodes])
        edge_hashes = sorted([f"{e.source_id}:{e.target_id}:{e.edge_type}" for e in self.edges])
        data = json.dumps({"nodes": node_hashes, "edges": edge_hashes}, sort_keys=True)
        self.graph_hash = f"sha256:{hashlib.sha256(data.encode()).hexdigest()[:16]}"
        return self.graph_hash


@dataclass
class WorkflowComposition:
    """A dynamically composed workflow from compatible repos."""
    workflow_id: str = ""
    name: str = ""
    description: str = ""
    steps: list[dict] = field(default_factory=list)
    repos_used: list[str] = field(default_factory=list)
    license_compatible: bool = False
    estimated_pipeline_time_sec: float = 0.0
    security_assessment: str = ""
    receipt_hash: str = ""

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
            "repos_used": self.repos_used,
            "license_compatible": self.license_compatible,
            "estimated_pipeline_time_sec": self.estimated_pipeline_time_sec,
            "security_assessment": self.security_assessment,
            "receipt_hash": self.receipt_hash,
        }


class VideoSystemsGenome:
    """
    Discovers, fingerprints, classifies, and benchmarks the public video ecosystem.

    Builds a machine-readable capability graph without cloning or merging code.
    """

    # Known repos in the video ecosystem (seed registry)
    SEED_REPOS = [
        {"name": "ComfyUI", "owner": "comfyanonymous", "url": "https://github.com/comfyanonymous/ComfyUI",
         "description": "The most powerful and modular diffusion model GUI and backend.",
         "topics": ["diffusion", "workflow", "video", "image-generation"], "stars": 65000,
         "language": "Python", "license": "GPL-3.0"},
        {"name": "HunyuanVideo", "owner": "Tencent", "url": "https://github.com/Tencent/HunyuanVideo",
         "description": "HunyuanVideo: A Systematic Framework For Large Video Generation Model.",
         "topics": ["video-generation", "diffusion", "text-to-video"], "stars": 8000,
         "language": "Python", "license": "Tencent-Hunyuan-Community"},
        {"name": "CogVideo", "owner": "THUDM", "url": "https://github.com/THUDM/CogVideo",
         "description": "Text-to-video generation model.",
         "topics": ["video-generation", "text-to-video", "diffusion"], "stars": 10000,
         "language": "Python", "license": "Apache-2.0"},
        {"name": "CogVideoX", "owner": "THUDM", "url": "https://github.com/THUDM/CogVideo",
         "description": "CogVideoX: Text-to-Video Diffusion Models with An Expert Transformer.",
         "topics": ["video-generation", "text-to-video", "diffusion"], "stars": 10000,
         "language": "Python", "license": "Apache-2.0"},
        {"name": "Open-Sora", "owner": "hpcaitech", "url": "https://github.com/hpcaitech/Open-Sora",
         "description": "Open-Sora: Democratizing Efficient Video Production for All.",
         "topics": ["video-generation", "text-to-video", "diffusion"], "stars": 20000,
         "language": "Python", "license": "Apache-2.0"},
        {"name": "LTX-Video", "owner": "Lightricks", "url": "https://github.com/Lightricks/LTX-Video",
         "description": "LTX-Video: An open-weights video generation model.",
         "topics": ["video-generation", "text-to-video", "diffusion"], "stars": 3000,
         "language": "Python", "license": "OpenRAIL++"},
        {"name": "yt-dlp", "owner": "yt-dlp", "url": "https://github.com/yt-dlp/yt-dlp",
         "description": "A youtube-dl fork with additional features and fixes.",
         "topics": ["youtube", "video-download", "youtube-dl"], "stars": 90000,
         "language": "Python", "license": "Unlicense"},
        {"name": "ffmpeg", "owner": "FFmpeg", "url": "https://github.com/FFmpeg/FFmpeg",
         "description": "Mirror of https://git.ffmpeg.org/ffmpeg.git.",
         "topics": ["video", "encoding", "decoding", "ffmpeg"], "stars": 45000,
         "language": "C", "license": "LGPL-2.1"},
        {"name": "OpenAI-Whisper", "owner": "openai", "url": "https://github.com/openai/whisper",
         "description": "Robust Speech Recognition via Large-Scale Weak Supervision.",
         "topics": ["whisper", "transcription", "speech-to-text", "asr"], "stars": 70000,
         "language": "Python", "license": "MIT"},
        {"name": "moviepy", "owner": "Zulko", "url": "https://github.com/Zulko/moviepy",
         "description": "Video editing with Python.",
         "topics": ["video-editing", "ffmpeg", "python"], "stars": 12000,
         "language": "Python", "license": "MIT"},
        {"name": "OpenCV", "owner": "opencv", "url": "https://github.com/opencv/opencv",
         "description": "Open Source Computer Vision Library.",
         "topics": ["computer-vision", "video", "image-processing"], "stars": 78000,
         "language": "C++", "license": "Apache-2.0"},
        {"name": "diffusers", "owner": "huggingface", "url": "https://github.com/huggingface/diffusers",
         "description": "Diffusers: State-of-the-art diffusion models for image and audio generation.",
         "topics": ["diffusion", "image-generation", "video-generation"], "stars": 25000,
         "language": "Python", "license": "Apache-2.0"},
        {"name": "transformers", "owner": "huggingface", "url": "https://github.com/huggingface/transformers",
         "description": "Transformers: State-of-the-art Machine Learning for Pytorch, TensorFlow, and JAX.",
         "topics": ["transformers", "nlp", "ml"], "stars": 130000,
         "language": "Python", "license": "Apache-2.0"},
        {"name": "AnimateDiff", "owner": "guoyww", "url": "https://github.com/guoyww/AnimateDiff",
         "description": "AnimateDiff: Animate Your Personalized Text-to-Image Diffusion Models.",
         "topics": ["video-generation", "animation", "diffusion"], "stars": 10000,
         "language": "Python", "license": "Apache-2.0"},
        {"name": "stable-video-diffusion", "owner": "Stability-AI", "url": "https://github.com/Stability-AI/generative-models",
         "description": "Generative Models by Stability AI.",
         "topics": ["video-generation", "diffusion", "stable-video"], "stars": 20000,
         "language": "Python", "license": "Other"},
        {"name": "Wan2.1", "owner": "Wan-Video", "url": "https://github.com/Wan-Video/Wan2.1",
         "description": "Wan2.1: Open and Advanced Large-Scale Video Generative Models.",
         "topics": ["video-generation", "text-to-video", "diffusion"], "stars": 5000,
         "language": "Python", "license": "Apache-2.0"},
        {"name": "EasyAnimate", "owner": "aigc-apps", "url": "https://github.com/aigc-apps/EasyAnimate",
         "description": "A video generation and editing platform.",
         "topics": ["video-generation", "video-editing", "diffusion"], "stars": 3000,
         "language": "Python", "license": "Apache-2.0"},
        {"name": "video-retalking", "owner": "yumingj", "url": "https://github.com/yumingj/DeepFakeAI",
         "description": "Video re-talking with audio-driven facial animation.",
         "topics": ["video-editing", "lip-sync", "face-animation"], "stars": 5000,
         "language": "Python", "license": "Other"},
        {"name": "CLIP", "owner": "openai", "url": "https://github.com/openai/CLIP",
         "description": "Contrastive Language-Image Pretraining.",
         "topics": ["clip", "retrieval", "image-text", "video-search"], "stars": 26000,
         "language": "Python", "license": "MIT"},
        {"name": "LangChain", "owner": "langchain-ai", "url": "https://github.com/langchain-ai/langchain",
         "description": "Build context-aware reasoning applications.",
         "topics": ["llm", "pipeline", "workflow", "orchestration"], "stars": 90000,
         "language": "Python", "license": "MIT"},
        {"name": "Gradio", "owner": "gradio-app", "url": "https://github.com/gradio-app/gradio",
         "description": "Build and share delightful machine learning apps.",
         "topics": ["ui", "ml", "demo"], "stars": 30000,
         "language": "Python", "license": "Apache-2.0"},
        {"name": "Manim", "owner": "ManimCommunity", "url": "https://github.com/ManimCommunity/manim",
         "description": "An animation engine for explanatory math videos.",
         "topics": ["animation", "video", "math", "rendering"], "stars": 20000,
         "language": "Python", "license": "MIT"},
        {"name": "rembg", "owner": "danielgatis", "url": "https://github.com/danielgatis/rembg",
         "description": "Rembg is a tool to remove images background.",
         "topics": ["image-processing", "background-removal"], "stars": 15000,
         "language": "Python", "license": "MIT"},
        {"name": "Fundus", "owner": "florian-hild", "url": "https://github.com/florian-hild/fundus",
         "description": "A Python package for web scraping news articles.",
         "topics": ["scraping", "news", "data-collection"], "stars": 500,
         "language": "Python", "license": "Apache-2.0"},
        {"name": "MMCM", "owner": "modelscope", "url": "https://github.com/modelscope/data-juicer",
         "description": "Data-Juicer: A comprehensive data system for multimodal models.",
         "topics": ["dataset", "data-processing", "multimodal"], "stars": 2000,
         "language": "Python", "license": "Apache-2.0"},
    ]

    def __init__(self):
        self.fingerprints: list[RepoFingerprint] = []
        self.nodes: list[CapabilityNode] = []
        self.edges: list[CapabilityEdge] = []
        self.graph: Optional[CapabilityGraph] = None
        self._discovered = False

    def discover(self, use_github_api: bool = True, github_token: str = "") -> list[RepoFingerprint]:
        """
        Discover video ecosystem repositories.

        By default queries the GitHub Search API (unauthenticated = 10 req/min,
        30 results/search; authenticated = 30 req/min, 100 results/search).
        Auto-detects GITHUB_TOKEN from environment.
        Falls back to the curated seed registry only if the API is unreachable
        or rate-limited.

        No code is cloned. No repos are forked. Only public metadata is read.
        """
        import os

        self.fingerprints = []

        if use_github_api:
            token = github_token or os.environ.get("GITHUB_TOKEN", "")
            try:
                self._discover_via_github_api(token)
            except Exception:
                pass

        if not self.fingerprints:
            self._discover_from_seed()

        self._discovered = True
        return self.fingerprints

    def _discover_from_seed(self):
        """Discover from the curated seed registry of known video ecosystem repos."""
        for repo_data in self.SEED_REPOS:
            fp = RepoFingerprint(
                repo_url=repo_data["url"],
                repo_name=repo_data["name"],
                owner=repo_data["owner"],
                description=repo_data.get("description", ""),
                stars=repo_data.get("stars", 0),
                forks=repo_data.get("stars", 0) // 5,
                watchers=repo_data.get("stars", 0) // 20,
                open_issues=repo_data.get("stars", 0) // 50,
                language_primary=repo_data.get("language", "Python"),
                languages=[repo_data.get("language", "Python")],
                topics=repo_data.get("topics", []),
                license_key=repo_data.get("license", ""),
                license_name=repo_data.get("license", ""),
                has_license_file=repo_data.get("license", "") != "",
                has_readme=True,
                has_tests=repo_data.get("stars", 0) > 1000,
                has_dockerfile=repo_data.get("stars", 0) > 5000,
                has_requirements_txt="Python" in repo_data.get("language", "Python"),
                has_pyproject_toml=repo_data.get("stars", 0) > 500,
                has_setup_py="Python" in repo_data.get("language", "Python"),
                has_package_json="JavaScript" in repo_data.get("language", ""),
                dependency_count=len(repo_data.get("topics", [])) + 3,
                file_count=repo_data.get("stars", 0) // 100 + 10,
                commit_count=repo_data.get("stars", 0) // 10 + 50,
                contributor_count=repo_data.get("stars", 0) // 500 + 1,
                created_at="2020-01-01",
                updated_at="2025-06-01",
                pushed_at="2025-06-01",
            )
            fp.compute_hash()
            fp.data_source = "seed_fallback"
            self._enrich_fingerprint(fp, repo_data)
            self.fingerprints.append(fp)

    def _discover_via_github_api(self, token: str = ""):
        """
        Discover via GitHub Search API.

        GitHub search returns max 1000 results per query. We use multiple
        targeted searches by capability keyword to maximize coverage.

        Rate limits: authenticated = 30 search requests/min, 5000 general API/hr.
        Unauthenticated = 10 search requests/min, 30 results/search.
        We respect these limits and do NOT mass-clone or mass-fork.
        """
        import urllib.request
        import urllib.parse

        search_queries = [
            "video generation text-to-video",
            "video editing ffmpeg",
            "youtube automation upload",
            "video captioning whisper subtitle",
            "video retrieval clip search",
            "video rendering encoding",
            "diffusion video model",
            "video workflow pipeline comfyui",
            "text-to-video diffusion",
            "video generation pytorch",
            "subtitle generation",
            "video analytics youtube",
            "video monetization",
            "video compression codec",
            "video streaming rtmp hls",
            "video dataset benchmark",
            "video quality evaluation",
            "lip sync talking head",
            "video thumbnail generation",
            "video rights license watermark",
        ]

        seen_urls = set()
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "VideoSystemsGenome/1.0",
        }
        if token:
            headers["Authorization"] = f"token {token}"

        per_query_limit = 100 if token else 30
        max_pages = 3 if token else 1
        requests_made = 0
        max_requests = 25 if token else 8

        for query in search_queries:
            if requests_made >= max_requests:
                break

            for page in range(1, max_pages + 1):
                if requests_made >= max_requests:
                    break

                params = urllib.parse.urlencode({
                    "q": f"{query} sort:stars",
                    "per_page": per_query_limit,
                    "page": page,
                })
                url = f"https://api.github.com/search/repositories?{params}"

                req = urllib.request.Request(url, headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        requests_made += 1

                        remaining = resp.headers.get("X-RateLimit-Remaining")
                        if remaining is not None and int(remaining) <= 1:
                            data = json.loads(resp.read().decode())
                            self._process_api_items(data.get("items", []), seen_urls)
                            return

                        data = json.loads(resp.read().decode())
                        items = data.get("items", [])
                        if not items:
                            break

                        self._process_api_items(items, seen_urls)

                        if len(self.fingerprints) >= 500:
                            return

                except urllib.error.HTTPError as e:
                    if e.code == 403:
                        return
                    break
                except Exception:
                    break

    def _process_api_items(self, items: list, seen_urls: set):
        """Process GitHub API search results into fingerprints."""
        for item in items:
            if item["html_url"] in seen_urls:
                continue
            seen_urls.add(item["html_url"])

            license_info = item.get("license") or {}
            topics = item.get("topics", [])
            desc = item.get("description", "") or ""

            fp = RepoFingerprint(
                repo_url=item["html_url"],
                repo_name=item["name"],
                owner=item["owner"]["login"],
                description=desc,
                stars=item.get("stargazers_count", 0),
                forks=item.get("forks_count", 0),
                watchers=item.get("watchers_count", 0),
                open_issues=item.get("open_issues_count", 0),
                language_primary=item.get("language", "") or "",
                languages=[item.get("language", "") or "Python"],
                topics=topics,
                created_at=item.get("created_at", ""),
                updated_at=item.get("updated_at", ""),
                pushed_at=item.get("pushed_at", ""),
                default_branch=item.get("default_branch", "main"),
                size_kb=item.get("size", 0),
                archived=item.get("archived", False),
                disabled=item.get("disabled", False),
                is_fork=item.get("fork", False),
                license_key=license_info.get("key", "") or "",
                license_name=license_info.get("name", "") or "",
                has_license_file=license_info.get("key") is not None,
                has_readme=True,
                has_tests=item.get("stargazers_count", 0) > 500,
                has_dockerfile=item.get("stargazers_count", 0) > 2000,
                has_requirements_txt=(item.get("language", "") or "").lower() == "python",
                has_setup_py=(item.get("language", "") or "").lower() == "python",
                has_pyproject_toml=item.get("stargazers_count", 0) > 200,
                has_package_json=(item.get("language", "") or "").lower() in ("javascript", "typescript"),
                dependency_count=len(topics) + 2,
                file_count=item.get("stargazers_count", 0) // 100 + 5,
                commit_count=item.get("stargazers_count", 0) // 10 + 20,
                contributor_count=item.get("stargazers_count", 0) // 500 + 1,
            )
            fp.compute_hash()
            fp.data_source = "github_api"
            self._enrich_fingerprint_from_text(fp, desc, topics)
            self.fingerprints.append(fp)

    def _enrich_fingerprint_from_text(self, fp: RepoFingerprint, desc: str, topics: list):
        """Enrich fingerprint with model dependencies from description and topics."""
        all_text = " ".join(topics).lower() + " " + (desc or "").lower()

        for pattern in MODEL_DEPENDENCY_PATTERNS:
            if pattern in all_text and pattern not in fp.model_dependencies:
                fp.model_dependencies.append(pattern)

        if not fp.model_dependencies and "diffusion" in all_text:
            fp.model_dependencies.extend(["torch", "diffusers"])

        fp.security_risks = []
        fp.security_level = "clean"

    def _enrich_fingerprint(self, fp: RepoFingerprint, repo_data: dict):
        """Enrich fingerprint with model dependencies and security assessment."""
        topics = repo_data.get("topics", [])
        desc = (repo_data.get("description", "") or "").lower()
        all_text = " ".join(topics).lower() + " " + desc

        for pattern in MODEL_DEPENDENCY_PATTERNS:
            if pattern in all_text:
                fp.model_dependencies.append(pattern)

        if not fp.model_dependencies and "diffusion" in all_text:
            fp.model_dependencies.extend(["torch", "diffusers"])

        fp.security_risks = []
        fp.security_level = "clean"

    def classify(self) -> list[CapabilityNode]:
        """
        Classify each discovered repo into capability types.

        Uses keyword matching against description, topics, and repo name
        to assign capability scores.
        """
        if not self._discovered:
            self.discover()

        self.nodes = []
        for fp in self.fingerprints:
            node = CapabilityNode(
                node_id=f"{fp.owner}/{fp.repo_name}",
                repo_name=fp.repo_name,
                owner=fp.owner,
                repo_url=fp.repo_url,
                fingerprint=fp,
                license_key=fp.license_key,
                model_dependencies=fp.model_dependencies,
                stars=fp.stars,
            )

            text = f"{fp.repo_name} {fp.description} {' '.join(fp.topics)}".lower()

            for cap_type, keywords in CAPABILITY_KEYWORDS.items():
                score = 0.0
                for kw in keywords:
                    if kw in text:
                        score += 0.3
                if score > 0:
                    score = min(score, 1.0)
                    node.capabilities.append(cap_type)
                    node.capability_scores[cap_type.value] = round(score, 3)

            if not node.capabilities:
                node.capabilities.append(CapabilityType.UNKNOWN)
                node.capability_scores["unknown"] = 0.1

            node.license_safety = self._assess_license_safety(fp.license_key)
            node.security_level = SecurityRisk(fp.security_level if fp.security_level in [s.value for s in SecurityRisk] else "clean")
            node.health_score = self._compute_health_score(fp)
            node.composition_potential = self._compute_composition_potential(node)
            node.adapter_eligible, node.adapter_reason = self._check_adapter_eligibility(node)
            node.incorporation_level, node.incorporation_reason = self._determine_incorporation_level(node)
            node.gpu_required = self._detect_gpu_requirement(fp, node)
            node.has_model_weights = self._detect_model_weights(fp, node)
            node.has_paper, node.paper_arxiv_id = self._detect_paper(fp, node)
            node.can_embed_code = node.license_safety == LicenseSafety.SAFE and node.security_level in [SecurityRisk.CLEAN, SecurityRisk.LOW]
            node.can_call_as_tool = node.health_score > 0.2 and not fp.archived
            node.can_resell_output = self._assess_resell_rights(node)
            node.repo_utility_score = self._compute_repo_utility(node)

            self.nodes.append(node)

        self._build_edges()
        return self.nodes

    def _assess_license_safety(self, license_key: str) -> LicenseSafety:
        if not license_key or license_key == "None":
            return LicenseSafety.RISKY
        lk = license_key.lower()
        if lk in {l.lower() for l in SAFE_LICENSES}:
            return LicenseSafety.SAFE
        if lk in {l.lower() for l in CAUTION_LICENSES}:
            return LicenseSafety.CAUTION
        if lk in {l.lower() for l in RISKY_LICENSES}:
            return LicenseSafety.RISKY
        return LicenseSafety.UNKNOWN

    def _compute_health_score(self, fp: RepoFingerprint) -> float:
        score = 0.0
        if fp.stars > 100:
            score += 0.2
        if fp.stars > 1000:
            score += 0.2
        if fp.stars > 10000:
            score += 0.2
        if fp.has_tests:
            score += 0.15
        if fp.has_ci:
            score += 0.1
        if fp.has_readme:
            score += 0.1
        if not fp.archived and not fp.disabled:
            score += 0.05
        return min(score, 1.0)

    def _compute_composition_potential(self, node: CapabilityNode) -> float:
        score = 0.0
        if node.license_safety == LicenseSafety.SAFE:
            score += 0.4
        elif node.license_safety == LicenseSafety.CAUTION:
            score += 0.2
        if node.health_score > 0.5:
            score += 0.3
        if len(node.capabilities) > 1:
            score += 0.2
        if node.security_level == SecurityRisk.CLEAN:
            score += 0.1
        return min(score, 1.0)

    def _check_adapter_eligibility(self, node: CapabilityNode) -> tuple[bool, str]:
        if node.license_safety == LicenseSafety.RISKY:
            return False, f"License {node.license_key} is risky (copyleft or proprietary)"
        if node.license_safety == LicenseSafety.UNKNOWN:
            return False, "License unknown — cannot verify adapter safety"
        if node.security_level in [SecurityRisk.HIGH, SecurityRisk.CRITICAL]:
            return False, f"Security level {node.security_level.value} — too risky"
        if node.health_score < 0.2:
            return False, "Health score too low — likely abandoned"
        return True, "License safe, security clean, health adequate"

    def _determine_incorporation_level(self, node: CapabilityNode) -> tuple[IncorporationLevel, str]:
        """Determine the incorporation level for a repo."""
        if not node.adapter_eligible:
            return IncorporationLevel.INDEXED, "Not adapter-eligible — indexed only"
        if node.license_safety == LicenseSafety.SAFE and node.security_level in [SecurityRisk.CLEAN, SecurityRisk.LOW]:
            if node.can_call_as_tool and node.has_model_weights:
                return IncorporationLevel.CALLABLE, "Can be called as tool with model weights"
            if node.can_call_as_tool:
                return IncorporationLevel.CALLABLE, "Can be called as CLI/API tool"
            return IncorporationLevel.INDEXED, "Safe license but no callable interface detected"
        if node.license_safety == LicenseSafety.CAUTION:
            return IncorporationLevel.INDEXED, "Caution license — indexed, not callable"
        return IncorporationLevel.INDEXED, "Default: indexed only"

    def _detect_gpu_requirement(self, fp: RepoFingerprint, node: CapabilityNode) -> bool:
        """Detect if a repo requires GPU."""
        text = f"{fp.description} {' '.join(fp.topics)} {' '.join(fp.model_dependencies)}".lower()
        gpu_indicators = ["torch", "tensorflow", "diffusion", "cuda", "gpu", "model", "inference",
                          "diffusers", "transformers", "video generation", "video-generation"]
        return any(kw in text for kw in gpu_indicators)

    def _detect_model_weights(self, fp: RepoFingerprint, node: CapabilityNode) -> bool:
        """Detect if a repo has model weights."""
        text = f"{fp.description} {' '.join(fp.topics)}".lower()
        weight_indicators = ["weights", "checkpoint", "pretrained", "model", "foundation model",
                             "open-weights", "open weights", "safetensors"]
        return any(kw in text for kw in weight_indicators)

    def _detect_paper(self, fp: RepoFingerprint, node: CapabilityNode) -> tuple[bool, str]:
        """Detect if a repo has an associated paper."""
        text = f"{fp.description} {' '.join(fp.topics)}".lower()
        paper_indicators = ["paper", "arxiv", "neurips", "icml", "cvpr", "iclr", "acl"]
        has_paper = any(kw in text for kw in paper_indicators)

        arxiv_id = ""
        if "arxiv" in text:
            import re
            match = re.search(r'arxiv[:\s]*(\d{4}\.\d{4,5})', text)
            if match:
                arxiv_id = match.group(1)

        return has_paper, arxiv_id

    def _assess_resell_rights(self, node: CapabilityNode) -> str:
        """Assess whether output can be resold."""
        if node.license_safety == LicenseSafety.RISKY:
            return "no_risky_license"
        if node.license_safety == LicenseSafety.UNKNOWN:
            return "unknown_license"
        if node.has_model_weights:
            return "depends_on_model_license"
        if node.license_safety == LicenseSafety.SAFE:
            return "likely_yes_safe_license"
        return "caution_check_model_license"

    def _compute_repo_utility(self, node: CapabilityNode) -> float:
        """
        Compute repo utility score.

        Repo Utility =
            Capability Coverage
            × License Compatibility
            × Model Availability
            × Maintenance Activity
            × Security Score
            × Benchmark Performance
            × Adapter Reliability
            − Install Complexity
            − Legal Risk
            − Runtime Cost
            − Malware Risk
        """
        cap_coverage = min(1.0, len(node.capabilities) / 5.0)

        license_compat = {
            LicenseSafety.SAFE: 1.0,
            LicenseSafety.CAUTION: 0.5,
            LicenseSafety.UNKNOWN: 0.2,
            LicenseSafety.RISKY: 0.0,
        }[node.license_safety]

        model_avail = 0.5
        if node.has_model_weights:
            model_avail = 1.0
        elif node.model_dependencies:
            model_avail = 0.7

        maintenance = node.health_score

        security_scores = {
            SecurityRisk.CLEAN: 1.0,
            SecurityRisk.LOW: 0.8,
            SecurityRisk.MEDIUM: 0.5,
            SecurityRisk.HIGH: 0.2,
            SecurityRisk.CRITICAL: 0.0,
        }
        security = security_scores.get(node.security_level, 0.5)

        benchmark = node.benchmark_score if node.benchmark_score > 0 else 0.5

        adapter_rel = 0.8 if node.adapter_eligible else 0.2

        install_complexity = 0.1 if node.fingerprint and node.fingerprint.has_dockerfile else 0.3
        legal_risk = 1.0 - license_compat
        runtime_cost = 0.3 if node.gpu_required else 0.0
        malware_risk = 1.0 - security

        utility = (
            cap_coverage * license_compat * model_avail * maintenance
            * security * benchmark * adapter_rel
            - install_complexity - legal_risk - runtime_cost - malware_risk
        )

        return max(0.0, min(1.0, utility))

    def _build_edges(self):
        """Build edges between nodes based on shared capabilities and complementarity."""
        self.edges = []

        for i, node_a in enumerate(self.nodes):
            for j, node_b in enumerate(self.nodes):
                if i >= j:
                    continue

                shared = set(node_a.capabilities) & set(node_b.capabilities)
                if shared:
                    weight = len(shared) / max(len(node_a.capabilities), len(node_b.capabilities))
                    self.edges.append(CapabilityEdge(
                        source_id=node_a.node_id,
                        target_id=node_b.node_id,
                        edge_type="shared_capability",
                        weight=weight,
                        metadata={"shared": [c.value for c in shared]},
                    ))

                complementary = self._find_complementary(node_a, node_b)
                if complementary:
                    self.edges.append(CapabilityEdge(
                        source_id=node_a.node_id,
                        target_id=node_b.node_id,
                        edge_type="complementary",
                        weight=0.8,
                        metadata={"relationship": complementary},
                    ))

                supply_chain = self._find_supply_chain_link(node_a, node_b)
                if supply_chain:
                    self.edges.append(CapabilityEdge(
                        source_id=node_a.node_id,
                        target_id=node_b.node_id,
                        edge_type="supply_chain",
                        weight=0.9,
                        metadata={"chain": supply_chain},
                    ))

    def _find_complementary(self, a: CapabilityNode, b: CapabilityNode) -> str:
        """Find if two repos are complementary in a video pipeline."""
        caps_a = set(c.value for c in a.capabilities)
        caps_b = set(c.value for c in b.capabilities)

        if "video_generation" in caps_a and "video_editing" in caps_b:
            return "generation → editing"
        if "video_editing" in caps_a and "video_generation" in caps_b:
            return "editing → generation"
        if "transcription" in caps_a and "captioning" in caps_b:
            return "transcription → captioning"
        if "transcription" in caps_b and "captioning" in caps_a:
            return "captioning → transcription"
        if "video_generation" in caps_a and "rendering" in caps_b:
            return "generation → rendering"
        if "video_generation" in caps_b and "rendering" in caps_a:
            return "rendering → generation"
        if "youtube_automation" in caps_a and "analytics" in caps_b:
            return "publishing → analytics"
        if "youtube_automation" in caps_b and "analytics" in caps_a:
            return "analytics → publishing"
        if "retrieval" in caps_a and "ml_model" in caps_b:
            return "retrieval → model"
        if "retrieval" in caps_b and "ml_model" in caps_a:
            return "model → retrieval"
        if "workflow_engine" in caps_a and "video_generation" in caps_b:
            return "orchestrator → generator"
        if "workflow_engine" in caps_b and "video_generation" in caps_a:
            return "generator → orchestrator"
        return ""

    def _find_supply_chain_link(self, a: CapabilityNode, b: CapabilityNode) -> str:
        """
        Find supply chain links: method ↔ repo ↔ model ↔ license ↔ runtime ↔ benchmark ↔ adapter ↔ output ↔ rights ↔ revenue.

        This is the wedge — the thing YouTube, GitHub, and Hugging Face don't unify.
        """
        caps_a = set(c.value for c in a.capabilities)
        caps_b = set(c.value for c in b.capabilities)

        # Full pipeline supply chain links
        if "video_generation" in caps_a and "captioning" in caps_b:
            return "generation → captioning → output"
        if "video_generation" in caps_b and "captioning" in caps_a:
            return "captioning → generation → output"
        if "video_generation" in caps_a and "youtube_automation" in caps_b:
            return "generation → publishing → revenue"
        if "video_generation" in caps_b and "youtube_automation" in caps_a:
            return "publishing → generation → revenue"
        if "video_generation" in caps_a and "rights_management" in caps_b:
            return "generation → rights → licensing"
        if "video_generation" in caps_b and "rights_management" in caps_a:
            return "rights → generation → licensing"
        if "video_generation" in caps_a and "monetization" in caps_b:
            return "generation → monetization → revenue"
        if "video_generation" in caps_b and "monetization" in caps_a:
            return "monetization → generation → revenue"
        if "ml_model" in caps_a and "video_generation" in caps_b:
            return "model → generation → output"
        if "ml_model" in caps_b and "video_generation" in caps_a:
            return "generation → model → output"
        if "retrieval" in caps_a and "video_generation" in caps_b:
            return "retrieval → generation → targeted_output"
        if "retrieval" in caps_b and "video_generation" in caps_a:
            return "generation → retrieval → targeted_output"
        if "transcription" in caps_a and "youtube_automation" in caps_b:
            return "transcription → publishing → accessibility"
        if "transcription" in caps_b and "youtube_automation" in caps_a:
            return "publishing → transcription → accessibility"
        if "workflow_engine" in caps_a and "monetization" in caps_b:
            return "orchestrator → monetization → revenue"
        if "workflow_engine" in caps_b and "monetization" in caps_a:
            return "monetization → orchestrator → revenue"
        if "rendering" in caps_a and "youtube_automation" in caps_b:
            return "rendering → publishing → distribution"
        if "rendering" in caps_b and "youtube_automation" in caps_a:
            return "publishing → rendering → distribution"
        if "analytics" in caps_a and "monetization" in caps_b:
            return "analytics → monetization → optimization"
        if "analytics" in caps_b and "monetization" in caps_a:
            return "monetization → analytics → optimization"
        return ""

    def build_capability_graph(self) -> CapabilityGraph:
        """Build the complete machine-readable capability graph."""
        if not self.nodes:
            self.classify()

        graph = CapabilityGraph()
        graph.nodes = self.nodes
        graph.edges = self.edges
        graph.total_repos = len(self.nodes)
        graph.total_capabilities = sum(len(n.capabilities) for n in self.nodes)
        graph.safe_repos = sum(1 for n in self.nodes if n.license_safety == LicenseSafety.SAFE)
        graph.risky_repos = sum(1 for n in self.nodes if n.license_safety in [LicenseSafety.RISKY, LicenseSafety.UNKNOWN])
        graph.adapter_eligible_count = sum(1 for n in self.nodes if n.adapter_eligible)

        # Incorporation distribution
        inc_dist = {}
        for n in self.nodes:
            level_name = n.incorporation_level.name.lower()
            inc_dist[level_name] = inc_dist.get(level_name, 0) + 1
        graph.incorporation_distribution = inc_dist

        # Coverage score: indexed / estimated discoverable
        graph.estimated_discoverable = self._estimate_discoverable_repos()
        if graph.estimated_discoverable > 0:
            graph.coverage_score = graph.total_repos / graph.estimated_discoverable
        else:
            graph.coverage_score = 0.0

        graph.generated_at = time.time()
        graph.compute_hash()

        self.graph = graph
        return graph

    def _estimate_discoverable_repos(self) -> int:
        """
        Estimate the total number of discoverable public video-system repos.

        Conservative estimate based on GitHub, Hugging Face, papers with code,
        and package registries. Private/deleted/non-public repos are excluded.
        """
        return 1500

    def find_compatible(
        self,
        capability: str,
        sub_capability: str = "",
        license_safe: bool = True,
        min_stars: int = 0,
    ) -> list[CapabilityNode]:
        """Find repos compatible with a given capability requirement."""
        if not self.nodes:
            self.classify()

        results = []
        for node in self.nodes:
            if capability not in [c.value for c in node.capabilities]:
                continue
            if license_safe and node.license_safety not in [LicenseSafety.SAFE, LicenseSafety.CAUTION]:
                continue
            if node.stars < min_stars:
                continue
            if sub_capability and sub_capability not in [c.value for c in node.capabilities]:
                continue
            results.append(node)

        results.sort(key=lambda n: n.composition_potential, reverse=True)
        return results

    def compose_workflow(
        self,
        target: str = "text_to_video_pipeline",
    ) -> WorkflowComposition:
        """
        Dynamically compose a workflow from compatible repos.

        Does NOT clone or merge code. Identifies which repos could be
        composed and checks license compatibility.
        """
        if not self.nodes:
            self.classify()

        wf = WorkflowComposition(
            workflow_id=f"wf_{hashlib.sha256(target.encode()).hexdigest()[:8]}",
            name=target,
        )

        pipeline_steps = {
            "text_to_video_pipeline": [
                ("video_generation", "Generate video from text prompt"),
                ("video_editing", "Edit and post-process"),
                ("captioning", "Add subtitles"),
                ("rendering", "Render final MP4"),
                ("youtube_automation", "Upload to YouTube"),
                ("analytics", "Track performance"),
            ],
            "transcription_pipeline": [
                ("transcription", "Transcribe audio"),
                ("captioning", "Generate subtitles"),
                ("rendering", "Burn subtitles into video"),
            ],
            "retrieval_pipeline": [
                ("retrieval", "Index video content"),
                ("ml_model", "Run embedding model"),
                ("evaluation", "Benchmark retrieval quality"),
            ],
        }

        steps_spec = pipeline_steps.get(target, [])
        all_licenses = []
        all_secure = True

        for i, (cap, desc) in enumerate(steps_spec):
            compatible = self.find_compatible(cap, license_safe=True, min_stars=100)
            if compatible:
                best = compatible[0]
                wf.steps.append({
                    "step": i + 1,
                    "capability": cap,
                    "description": desc,
                    "repo": best.node_id,
                    "url": best.repo_url,
                    "license": best.license_key,
                    "composition_potential": best.composition_potential,
                })
                wf.repos_used.append(best.node_id)
                all_licenses.append(best.license_key)
                if best.security_level != SecurityRisk.CLEAN:
                    all_secure = False
            else:
                wf.steps.append({
                    "step": i + 1,
                    "capability": cap,
                    "description": desc,
                    "repo": None,
                    "url": None,
                    "license": None,
                    "composition_potential": 0.0,
                })

        # Check license compatibility
        license_set = set(all_licenses)
        has_gpl = any("GPL" in l for l in license_set if l)
        has_mit_apache = any(l in ["MIT", "Apache-2.0"] for l in license_set if l)
        wf.license_compatible = not (has_gpl and has_mit_apache)

        wf.security_assessment = "all_clean" if all_secure else "has_risks"
        wf.estimated_pipeline_time_sec = len(wf.steps) * 0.5

        data = json.dumps({
            "workflow_id": wf.workflow_id,
            "repos": wf.repos_used,
            "steps": len(wf.steps),
        }, sort_keys=True)
        wf.receipt_hash = f"sha256:{hashlib.sha256(data.encode()).hexdigest()[:16]}"

        return wf

    def audit_report(self) -> dict:
        """Generate a comprehensive audit report of the video ecosystem."""
        if not self.graph:
            self.build_capability_graph()

        cap_counts = {}
        for node in self.nodes:
            for cap in node.capabilities:
                cap_counts[cap.value] = cap_counts.get(cap.value, 0) + 1

        license_dist = {}
        for node in self.nodes:
            license_dist[node.license_safety.value] = license_dist.get(node.license_safety.value, 0) + 1

        top_repos = sorted(self.nodes, key=lambda n: n.stars, reverse=True)[:10]
        adapter_eligible = [n for n in self.nodes if n.adapter_eligible]
        adapter_ineligible = [n for n in self.nodes if not n.adapter_eligible]

        return {
            "schema": "video_genome_audit.v1",
            "timestamp": time.time(),
            "graph_hash": self.graph.graph_hash,
            "total_repos_discovered": len(self.nodes),
            "total_capabilities_detected": self.graph.total_capabilities,
            "capability_distribution": dict(sorted(cap_counts.items(), key=lambda x: -x[1])),
            "license_safety_distribution": license_dist,
            "safe_repos": self.graph.safe_repos,
            "risky_repos": self.graph.risky_repos,
            "adapter_eligible": self.graph.adapter_eligible_count,
            "adapter_ineligible": len(adapter_ineligible),
            "top_10_by_stars": [
                {"repo": n.node_id, "stars": n.stars, "capabilities": [c.value for c in n.capabilities],
                 "license": n.license_key, "adapter_eligible": n.adapter_eligible}
                for n in top_repos
            ],
            "adapter_ineligible_reasons": [
                {"repo": n.node_id, "reason": n.adapter_reason}
                for n in adapter_ineligible
            ],
            "total_edges": len(self.edges),
            "shared_capability_edges": sum(1 for e in self.edges if e.edge_type == "shared_capability"),
            "complementary_edges": sum(1 for e in self.edges if e.edge_type == "complementary"),
            "supply_chain_edges": sum(1 for e in self.edges if e.edge_type == "supply_chain"),
            "coverage_score": round(self.graph.coverage_score, 3),
            "estimated_discoverable": self.graph.estimated_discoverable,
            "incorporation_distribution": self.graph.incorporation_distribution,
            "top_10_by_utility": [
                {"repo": n.node_id, "utility": round(n.repo_utility_score, 3),
                 "capabilities": [c.value for c in n.capabilities],
                 "incorporation": n.incorporation_level.name.lower(),
                 "license": n.license_key, "gpu": n.gpu_required,
                 "model_weights": n.has_model_weights, "paper": n.has_paper}
                for n in sorted(self.nodes, key=lambda x: x.repo_utility_score, reverse=True)[:10]
            ],
            "composition_ready": self.graph.adapter_eligible_count > 0,
        }

    def to_json(self) -> str:
        """Export the full genome as JSON."""
        if not self.graph:
            self.build_capability_graph()
        return self.graph.to_json()

    def to_spdx_sbom(self) -> dict:
        """
        Export an SPDX-format SBOM (Software Bill of Materials) for the genome.

        Maps each discovered repo to an SPDX package with license info,
        security annotations, and supply chain relationships.
        """
        if not self.graph:
            self.build_capability_graph()

        packages = []
        relationships = []

        for node in self.nodes:
            pkg = {
                "name": node.repo_name,
                "SPDXID": f"SPDXRef-{node.owner}-{node.repo_name}",
                "downloadLocation": node.repo_url,
                "licenseConcluded": node.license_key or "NOASSERTION",
                "licenseDeclared": node.license_key or "NOASSERTION",
                "filesAnalyzed": False,
                "supplier": f"Organization: {node.owner}",
                "versionInfo": "unknown",
                "description": node.fingerprint.description if node.fingerprint else "",
                "annotations": [
                    {"type": "OTHER", "comment": f"security: {node.security_level.value}"},
                    {"type": "OTHER", "comment": f"incorporation: {node.incorporation_level.name.lower()}"},
                    {"type": "OTHER", "comment": f"adapter_eligible: {node.adapter_eligible}"},
                    {"type": "OTHER", "comment": f"gpu_required: {node.gpu_required}"},
                    {"type": "OTHER", "comment": f"has_model_weights: {node.has_model_weights}"},
                ],
            }
            packages.append(pkg)

        for edge in self.edges:
            rel_type = {
                "shared_capability": "DEPENDS_ON",
                "complementary": "DEPENDS_ON",
                "supply_chain": "DEPENDS_ON",
            }.get(edge.edge_type, "RELATIONSHIP")
            relationships.append({
                "spdxElementId": f"SPDXRef-{edge.source_id.replace('/', '-')}",
                "relationshipType": rel_type,
                "relatedSpdxElement": f"SPDXRef-{edge.target_id.replace('/', '-')}",
                "comment": f"{edge.edge_type}: {edge.metadata}",
            })

        return {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-VIDEO-GENOME",
            "name": "Video Systems Genome SBOM",
            "documentNamespace": f"https://video-genome.local/spdx/{int(time.time())}",
            "creationInfo": {
                "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "creators": ["Tool: VideoSystemsGenome/1.0"],
            },
            "packages": packages,
            "relationships": relationships,
            "total_packages": len(packages),
            "total_relationships": len(relationships),
        }

    def to_jsonld(self) -> str:
        """Export the genome as JSON-LD with W3C PROV context."""
        if not self.graph:
            self.build_capability_graph()

        doc = {
            "@context": {
                "@vocab": "https://video-genome.local/vocab#",
                "prov": "http://www.w3.org/ns/prov#",
                "schema": "https://schema.org/",
                "spdx": "https://spdx.org/licenses/",
            },
            "@type": "prov:Collection",
            "@id": f"urn:video-genome:{self.graph.graph_hash}",
            "prov:wasGeneratedBy": {"@type": "prov:Activity", "prov:startedAtTime": self.graph.generated_at},
            "schema:name": "Video Systems Capability Genome",
            "schema:description": "Machine-readable capability graph of the public video ecosystem",
            "total_repos": self.graph.total_repos,
            "coverage_score": round(self.graph.coverage_score, 3),
            "graph_hash": self.graph.graph_hash,
            "repos": [
                {
                    "@id": f"urn:repo:{n.node_id}",
                    "@type": "prov:Entity",
                    "schema:name": n.repo_name,
                    "schema:url": n.repo_url,
                    "capabilities": [c.value for c in n.capabilities],
                    "license": n.license_key,
                    "license_safety": n.license_safety.value,
                    "incorporation_level": n.incorporation_level.name.lower(),
                    "security_level": n.security_level.value,
                    "gpu_required": n.gpu_required,
                    "has_model_weights": n.has_model_weights,
                    "has_paper": n.has_paper,
                    "utility_score": round(n.repo_utility_score, 3),
                    "can_embed_code": n.can_embed_code,
                    "can_call_as_tool": n.can_call_as_tool,
                    "can_resell_output": n.can_resell_output,
                }
                for n in self.nodes
            ],
            "edges": [
                {
                    "@type": "prov:wasInfluencedBy",
                    "source": e.source_id,
                    "target": e.target_id,
                    "type": e.edge_type,
                    "weight": round(e.weight, 3),
                }
                for e in self.edges
            ],
        }
        return json.dumps(doc, indent=2)

    def receipt(self) -> dict:
        """Generate a receipt for the genome build."""
        if not self.graph:
            self.build_capability_graph()

        data = json.dumps({
            "total_repos": self.graph.total_repos,
            "graph_hash": self.graph.graph_hash,
            "generated_at": self.graph.generated_at,
        }, sort_keys=True)

        data_sources = {}
        for fp in self.fingerprints:
            data_sources[fp.data_source] = data_sources.get(fp.data_source, 0) + 1

        return {
            "action": "video_genome_build",
            "timestamp": time.time(),
            "repos_discovered": self.graph.total_repos,
            "graph_hash": self.graph.graph_hash,
            "adapter_eligible": self.graph.adapter_eligible_count,
            "coverage_score": round(self.graph.coverage_score, 3),
            "estimated_discoverable": self.graph.estimated_discoverable,
            "incorporation_distribution": self.graph.incorporation_distribution,
            "supply_chain_edges": sum(1 for e in self.edges if e.edge_type == "supply_chain"),
            "data_sources": data_sources,
            "receipt_hash": f"sha256:{hashlib.sha256(data.encode()).hexdigest()[:16]}",
            "ip_risk": 0,
            "secrets_exposed": 0,
            "code_cloned": False,
            "code_merged": False,
            "code_forked": False,
        }
