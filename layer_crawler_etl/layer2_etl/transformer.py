"""
Layer 2: ETL - Transform
Normalizes extracted data into a common schema for loading.
"""

import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from layer_crawler_etl.layer2_etl.extractor import ExtractedData


@dataclass
class NormalizedRecord:
    """Normalized record with common schema."""
    source_id: str
    record_type: str
    data: Dict = field(default_factory=dict)
    signals: Dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    hash: str = ""
    
    def to_dict(self) -> Dict:
        return {
            "source_id": self.source_id,
            "record_type": self.record_type,
            "data": self.data,
            "signals": self.signals,
            "timestamp": self.timestamp,
            "hash": self.hash
        }
    
    def compute_hash(self) -> str:
        """Compute hash of record for deduplication."""
        import hashlib
        content = json.dumps(self.data, sort_keys=True)
        self.hash = hashlib.sha256(content.encode()).hexdigest()[:16]
        return self.hash


class Transformer:
    """Transforms extracted data into normalized records."""
    
    # Common schema fields
    COMMON_FIELDS = {
        "source_id",
        "source_url",
        "timestamp",
        "success"
    }
    
    def __init__(self):
        pass
    
    def transform(self, extracted: ExtractedData) -> NormalizedRecord:
        """Transform extracted data into normalized record."""
        record_type = self._infer_record_type(extracted)
        
        normalized = NormalizedRecord(
            source_id=extracted.source_id,
            record_type=record_type,
            data=self._normalize_data(extracted.raw_data, record_type),
            signals=self._extract_signals(extracted.raw_data, record_type),
            timestamp=extracted.timestamp
        )
        
        normalized.compute_hash()
        return normalized
    
    def _infer_record_type(self, extracted: ExtractedData) -> str:
        """Infer record type from extracted data."""
        crawler_type = extracted.crawler_type
        
        type_mapping = {
            "code": "code_analysis",
            "dependency": "dependency_analysis",
            "license": "license_analysis",
            "security": "security_analysis",
            "test_build": "test_build_analysis",
            "browser_runtime": "runtime_analysis"
        }
        
        return type_mapping.get(crawler_type, "generic_analysis")
    
    def _normalize_data(self, raw_data: Dict, record_type: str) -> Dict:
        """Normalize data according to record type schema."""
        normalized = {
            "source_url": raw_data.get("source_url"),
            "analysis_type": record_type,
            "timestamp": raw_data.get("timestamp", datetime.utcnow().isoformat())
        }
        
        # Type-specific normalization
        if record_type == "code_analysis":
            normalized.update({
                "languages": raw_data.get("languages", {}),
                "file_count": raw_data.get("file_count", 0),
                "has_tests": raw_data.get("has_tests", False),
                "has_ci": raw_data.get("has_ci", False),
                "has_docs": raw_data.get("has_docs", False),
                "license": raw_data.get("license")
            })
        
        elif record_type == "dependency_analysis":
            normalized.update({
                "total_count": raw_data.get("total_count", 0),
                "direct_count": raw_data.get("direct_count", 0),
                "by_language": raw_data.get("by_language", {}),
                "vulnerabilities": raw_data.get("vulnerabilities", []),
                "license_risks": raw_data.get("license_risks", [])
            })
        
        elif record_type == "license_analysis":
            normalized.update({
                "primary_license": raw_data.get("primary_license"),
                "license_type": raw_data.get("license_type"),
                "commercial_use_allowed": raw_data.get("commercial_use_allowed", False),
                "compatibility_score": raw_data.get("compatibility_score", 0)
            })
        
        elif record_type == "security_analysis":
            normalized.update({
                "secrets_found": raw_data.get("secrets_found", 0),
                "security_issues": raw_data.get("security_issues", 0),
                "secrets_by_type": raw_data.get("secrets_by_type", {}),
                "files_with_secrets": raw_data.get("files_with_secrets", [])
            })
        
        elif record_type == "test_build_analysis":
            normalized.update({
                "test_file_count": raw_data.get("test_file_count", 0),
                "test_frameworks": raw_data.get("test_frameworks", []),
                "has_ci_cd": raw_data.get("has_ci_cd", False),
                "coverage_configured": raw_data.get("coverage_configured", False)
            })
        
        elif record_type == "runtime_analysis":
            normalized.update({
                "runtime_verified": raw_data.get("runtime_verified", False),
                "console_errors": raw_data.get("console_errors", []),
                "failed_requests": raw_data.get("failed_requests", []),
                "page_load_time_ms": raw_data.get("page_load_time_ms", 0),
                "js_errors_count": raw_data.get("js_errors_count", 0)
            })
        
        return normalized
    
    def _extract_signals(self, raw_data: Dict, record_type: str) -> Dict:
        """Extract signals for scoring."""
        signals = {
            "build_verified": False,
            "tests_verified": False,
            "runtime_verified": False,
            "console_errors": 0,
            "failed_requests": 0,
            "secrets_exposed": 0,
            "license_conflict": 0
        }
        
        if record_type == "code_analysis":
            signals["build_verified"] = raw_data.get("has_ci", False)
            signals["tests_verified"] = raw_data.get("has_tests", False)
        
        elif record_type == "dependency_analysis":
            signals["license_conflict"] = len(raw_data.get("license_risks", []))
        
        elif record_type == "security_analysis":
            signals["secrets_exposed"] = raw_data.get("secrets_found", 0)
        
        elif record_type == "runtime_analysis":
            signals["runtime_verified"] = raw_data.get("runtime_verified", False)
            signals["console_errors"] = len(raw_data.get("console_errors", []))
            signals["failed_requests"] = len(raw_data.get("failed_requests", []))
        
        return signals
    
    def batch_transform(self, extracted_list: List[ExtractedData]) -> List[NormalizedRecord]:
        """Transform multiple extracted records."""
        return [self.transform(e) for e in extracted_list]
