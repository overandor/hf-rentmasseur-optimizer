"""
Layer 2: ETL - Extract
Extracts raw data from crawler results and prepares for transformation.
"""

import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from layer_crawler_etl.layer1_crawlers.base_crawler import CrawlResult


@dataclass
class ExtractedData:
    """Extracted data from a crawl result."""
    source_id: str
    crawler_type: str
    raw_data: Dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    artifacts: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        return {
            "source_id": self.source_id,
            "crawler_type": self.crawler_type,
            "raw_data": self.raw_data,
            "timestamp": self.timestamp,
            "artifacts": self.artifacts,
            "metadata": self.metadata
        }


class Extractor:
    """Extracts data from crawl results."""
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.storage_path = storage_path or Path("layer_crawler_etl/storage/raw")
    
    def extract_from_crawl_result(self, result: CrawlResult) -> ExtractedData:
        """Extract data from a crawl result."""
        extracted = ExtractedData(
            source_id=result.source_id,
            crawler_type=result.data.get("crawler_type", "unknown"),
            raw_data=result.data,
            artifacts=result.artifacts,
            metadata={
                "success": result.success,
                "errors": result.errors,
                "warnings": result.warnings,
                "crawl_duration_seconds": result.crawl_duration_seconds
            }
        )
        return extracted
    
    def extract_from_file(self, source_id: str, crawler_type: str, file_path: Path) -> Optional[ExtractedData]:
        """Extract data from a stored file."""
        if not file_path.exists():
            return None
        
        with open(file_path, "r") as f:
            raw_data = json.load(f)
        
        return ExtractedData(
            source_id=source_id,
            crawler_type=crawler_type,
            raw_data=raw_data,
            timestamp=datetime.utcnow().isoformat()
        )
    
    def batch_extract(self, results: List[CrawlResult]) -> List[ExtractedData]:
        """Extract data from multiple crawl results."""
        return [self.extract_from_crawl_result(r) for r in results]
