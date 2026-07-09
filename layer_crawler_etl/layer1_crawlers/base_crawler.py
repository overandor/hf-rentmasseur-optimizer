"""
Layer 1: Base Crawler Interface
All subject crawlers inherit from this base class.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import json
from pathlib import Path

from layer_crawler_etl.layer0_source_registry.source_registry import Source


@dataclass
class CrawlResult:
    """Result of a crawl operation."""
    source_id: str
    success: bool
    data: Dict = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    artifacts: List[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    crawl_duration_seconds: float = 0.0
    
    def to_dict(self) -> Dict:
        return {
            "source_id": self.source_id,
            "success": self.success,
            "data": self.data,
            "errors": self.errors,
            "warnings": self.warnings,
            "artifacts": self.artifacts,
            "timestamp": self.timestamp,
            "crawl_duration_seconds": self.crawl_duration_seconds
        }
    
    def add_error(self, error: str):
        self.errors.append(error)
        self.success = False
    
    def add_warning(self, warning: str):
        self.warnings.append(warning)
    
    def add_artifact(self, artifact_path: str):
        self.artifacts.append(artifact_path)


class BaseCrawler(ABC):
    """Abstract base class for all crawlers."""
    
    crawler_type: str = "base"
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("layer_crawler_etl/storage/raw")
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    @abstractmethod
    async def crawl(self, source: Source) -> CrawlResult:
        """Crawl a source and return results."""
        pass
    
    @abstractmethod
    def validate_source(self, source: Source) -> bool:
        """Validate that the source is compatible with this crawler."""
        pass
    
    def get_storage_path(self, source_id: str) -> Path:
        """Get storage path for a source."""
        return self.storage_path / self.crawler_type / source_id
    
    def save_raw_data(self, source_id: str, data: Dict, filename: str = "raw.json"):
        """Save raw crawl data to storage."""
        path = self.get_storage_path(source_id)
        path.mkdir(parents=True, exist_ok=True)
        file_path = path / filename
        with open(file_path, "w") as f:
            json.dump(data, f, indent=2)
        return str(file_path)
    
    def load_raw_data(self, source_id: str, filename: str = "raw.json") -> Optional[Dict]:
        """Load raw crawl data from storage."""
        file_path = self.get_storage_path(source_id) / filename
        if file_path.exists():
            with open(file_path, "r") as f:
                return json.load(f)
        return None
