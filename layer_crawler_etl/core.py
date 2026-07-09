"""
Layer Crawler ETL Engine
Sources → Crawlers → Extractors → Normalizers → Classifiers → Evidence Scorers → Receipts → HardenRank / ProdScore
"""
import asyncio
import json
import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("layer_crawler")

class SubjectType(Enum):
    CODE = "code"
    DEPENDENCY = "dependency"
    LICENSE = "license"
    TEST_BUILD = "test_build"
    BROWSER_RUNTIME = "browser_runtime"
    ARTIFACT = "artifact"
    SECURITY_SECRETS = "security_secrets"
    DOCS_CLAIMS = "docs_claims"

class EvidenceType(Enum):
    BUILD_VERIFIED = "build_verified"
    TESTS_VERIFIED = "tests_verified"
    RUNTIME_VERIFIED = "runtime_verified"
    CONSOLE_ERRORS = "console_errors"
    FAILED_REQUESTS = "failed_requests"
    SECRETS_EXPOSED = "secrets_exposed"
    LICENSE_CONFLICT = "license_conflict"

@dataclass
class Source:
    type: str
    location: str
    metadata: Dict[str, Any]

@dataclass
class EvidenceSignal:
    subject: SubjectType
    evidence_type: EvidenceType
    value: Any
    timestamp: str
    source: str

@dataclass
class Receipt:
    system: str
    subject: str
    source: str
    timestamp: str
    artifact: str
    signals: Dict[str, Any]
    scores: Dict[str, float]
    hash: str

class EvidenceScorer:
    """Scores evidence based on POptimizer principles"""
    
    @staticmethod
    def calculate_evidence_score(signals: Dict[str, Any]) -> float:
        """EvidenceScore: weighted sum of verified signals"""
        score = 0
        if signals.get("build_verified"): score += 25
        if signals.get("tests_verified"): score += 25
        if signals.get("runtime_verified"): score += 25
        if signals.get("console_errors", 0) == 0: score += 10
        if signals.get("failed_requests", 0) == 0: score += 10
        if signals.get("secrets_exposed", 0) == 0: score += 5
        return min(100, score)
    
    @staticmethod
    def calculate_reality_penalty(signals: Dict[str, Any]) -> float:
        """RealityPenalty: penalty for missing or failed evidence"""
        penalty = 0
        if not signals.get("build_verified"): penalty += 30
        if not signals.get("tests_verified"): penalty += 20
        if not signals.get("runtime_verified"): penalty += 20
        penalty += signals.get("console_errors", 0) * 2
        penalty += signals.get("failed_requests", 0) * 5
        penalty += signals.get("secrets_exposed", 0) * 50
        return min(100, penalty)
    
    @staticmethod
    def calculate_prod_score(evidence_score: float, reality_penalty: float) -> float:
        """ProdScore: evidence score minus reality penalty"""
        return max(0, evidence_score - reality_penalty)
    
    @staticmethod
    def calculate_ip_risk(signals: Dict[str, Any]) -> float:
        """IPRisk: risk of proprietary leakage"""
        risk = 0
        if signals.get("secrets_exposed", 0) > 0: risk += 100
        if signals.get("license_conflict", 0) > 0: risk += 50
        return min(100, risk)

class BaseCrawler:
    """Base class for all subject crawlers"""
    
    def __init__(self, name: str):
        self.name = name
        self.signals: List[EvidenceSignal] = []
    
    async def crawl(self, source: Source) -> List[EvidenceSignal]:
        """Override in subclasses"""
        raise NotImplementedError
    
    def add_signal(self, subject: SubjectType, evidence_type: EvidenceType, value: Any, source: str):
        signal = EvidenceSignal(
            subject=subject,
            evidence_type=evidence_type,
            value=value,
            timestamp=datetime.now().isoformat(),
            source=source
        )
        self.signals.append(signal)

class CrawlerRegistry:
    """Registry for all crawlers"""
    
    def __init__(self):
        self.crawlers: Dict[SubjectType, BaseCrawler] = {}
    
    def register(self, subject: SubjectType, crawler: BaseCrawler):
        self.crawlers[subject] = crawler
        log.info(f"Registered crawler: {subject.value} -> {crawler.name}")
    
    def get(self, subject: SubjectType) -> Optional[BaseCrawler]:
        return self.crawlers.get(subject)

class ETLPipeline:
    """Main ETL pipeline"""
    
    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.registry = CrawlerRegistry()
        self.scorer = EvidenceScorer()
    
    def register_crawler(self, subject: SubjectType, crawler: BaseCrawler):
        self.registry.register(subject, crawler)
    
    async def extract(self, sources: List[Source]) -> Dict[SubjectType, List[EvidenceSignal]]:
        """Layer 1: Extract signals from sources using crawlers"""
        results = {}
        for source in sources:
            for subject_type, crawler in self.registry.crawlers.items():
                try:
                    signals = await crawler.crawl(source)
                    if subject_type not in results:
                        results[subject_type] = []
                    results[subject_type].extend(signals)
                except Exception as e:
                    log.error(f"Error crawling {subject_type.value} for {source.location}: {e}")
        return results
    
    def transform(self, signals: Dict[SubjectType, List[EvidenceSignal]]) -> Dict[str, Any]:
        """Layer 2: Transform signals into normalized schema"""
        normalized = {}
        for subject_type, signal_list in signals.items():
            normalized[subject_type.value] = [asdict(s) for s in signal_list]
        return normalized
    
    def load(self, normalized: Dict[str, Any], system: str) -> Receipt:
        """Layer 3: Load into receipt format with scoring"""
        # Aggregate signals
        aggregated = {}
        for subject_type, signal_list in normalized.items():
            for signal in signal_list:
                key = f"{signal['subject']}_{signal['evidence_type']}"
                aggregated[key] = signal['value']
        
        # Calculate scores
        evidence_score = self.scorer.calculate_evidence_score(aggregated)
        reality_penalty = self.scorer.calculate_reality_penalty(aggregated)
        prod_score = self.scorer.calculate_prod_score(evidence_score, reality_penalty)
        ip_risk = self.scorer.calculate_ip_risk(aggregated)
        
        scores = {
            "evidence": evidence_score,
            "reality_penalty": reality_penalty,
            "prod_score": prod_score,
            "ip_risk": ip_risk
        }
        
        # Create receipt
        receipt = Receipt(
            system=system,
            subject="runtime",
            source="layer_crawler",
            timestamp=datetime.now().isoformat(),
            artifact=f"receipts/{system}-{datetime.now().strftime('%Y%m%d%H%M%S')}.json",
            signals=aggregated,
            scores=scores,
            hash=hashlib.sha256(json.dumps(aggregated, sort_keys=True).encode()).hexdigest()[:16]
        )
        
        # Save receipt
        receipt_path = self.output_dir / receipt.artifact
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        with open(receipt_path, 'w') as f:
            json.dump(asdict(receipt), f, indent=2)
        
        log.info(f"Receipt saved: {receipt_path}")
        return receipt
    
    async def run(self, sources: List[Source], system: str) -> Receipt:
        """Run full ETL pipeline"""
        log.info(f"Starting ETL pipeline for system: {system}")
        
        # Extract
        signals = await self.extract(sources)
        log.info(f"Extracted {sum(len(s) for s in signals.values())} signals")
        
        # Transform
        normalized = self.transform(signals)
        
        # Load
        receipt = self.load(normalized, system)
        
        log.info(f"ETL complete. ProdScore: {receipt.scores['prod_score']}")
        return receipt
