"""
Layer 2: ETL - Load
Loads normalized records into evidence lake (JSONL/Parquet).
"""

import json
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from layer_crawler_etl.layer2_etl.transformer import NormalizedRecord


@dataclass
class LoadResult:
    """Result of a load operation."""
    records_loaded: int = 0
    records_skipped: int = 0
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    def to_dict(self) -> Dict:
        return {
            "records_loaded": self.records_loaded,
            "records_skipped": self.records_skipped,
            "errors": self.errors
        }


class Loader:
    """Loads normalized records into evidence lake."""
    
    def __init__(self, storage_path: Optional[Path] = None, format: str = "jsonl"):
        self.storage_path = storage_path or Path("layer_crawler_etl/storage/normalized")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.format = format.lower()
        
        if self.format not in ["jsonl", "parquet"]:
            raise ValueError(f"Unsupported format: {format}. Use 'jsonl' or 'parquet'")
    
    def load(self, record: NormalizedRecord, deduplicate: bool = True) -> LoadResult:
        """Load a single normalized record."""
        result = LoadResult()
        
        try:
            # Check for duplicates if deduplication enabled
            if deduplicate and self._record_exists(record):
                result.records_skipped = 1
                return result
            
            # Write record based on format
            if self.format == "jsonl":
                self._write_jsonl(record)
            elif self.format == "parquet":
                self._write_parquet(record)
            
            result.records_loaded = 1
            
        except Exception as e:
            result.errors.append(f"Load failed: {str(e)}")
        
        return result
    
    def batch_load(self, records: List[NormalizedRecord], deduplicate: bool = True) -> LoadResult:
        """Load multiple normalized records."""
        result = LoadResult()
        
        for record in records:
            load_result = self.load(record, deduplicate=deduplicate)
            result.records_loaded += load_result.records_loaded
            result.records_skipped += load_result.records_skipped
            result.errors.extend(load_result.errors)
        
        return result
    
    def _record_exists(self, record: NormalizedRecord) -> bool:
        """Check if record already exists (by hash)."""
        record_type_path = self.storage_path / f"{record.record_type}.{self.format}"
        
        if not record_type_path.exists():
            return False
        
        if self.format == "jsonl":
            with open(record_type_path, "r") as f:
                for line in f:
                    if line.strip():
                        existing = json.loads(line)
                        if existing.get("hash") == record.hash:
                            return True
        
        return False
    
    def _write_jsonl(self, record: NormalizedRecord):
        """Write record to JSONL file."""
        record_type_path = self.storage_path / f"{record.record_type}.jsonl"
        
        with open(record_type_path, "a") as f:
            f.write(json.dumps(record.to_dict()) + "\n")
    
    def _write_parquet(self, record: NormalizedRecord):
        """Write record to Parquet file."""
        # Note: Requires pyarrow or fastparquet
        # For now, we'll use JSONL as fallback
        import warnings
        warnings.warn("Parquet format not yet implemented, using JSONL fallback")
        self._write_jsonl(record)
    
    def load_by_source_id(self, source_id: str) -> List[Dict]:
        """Load all records for a specific source."""
        records = []
        
        for file_path in self.storage_path.glob("*.jsonl"):
            with open(file_path, "r") as f:
                for line in f:
                    if line.strip():
                        record = json.loads(line)
                        if record.get("source_id") == source_id:
                            records.append(record)
        
        return records
    
    def load_by_record_type(self, record_type: str) -> List[Dict]:
        """Load all records of a specific type."""
        file_path = self.storage_path / f"{record_type}.jsonl"
        
        if not file_path.exists():
            return []
        
        records = []
        with open(file_path, "r") as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        
        return records
    
    def get_stats(self) -> Dict:
        """Get statistics about loaded records."""
        stats = {
            "total_records": 0,
            "by_type": {}
        }
        
        for file_path in self.storage_path.glob("*.jsonl"):
            record_type = file_path.stem
            count = sum(1 for _ in open(file_path) if _.strip())
            stats["by_type"][record_type] = count
            stats["total_records"] += count
        
        return stats
