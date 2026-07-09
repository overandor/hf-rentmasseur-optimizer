"""
Layer 0: Source Registry
Manages all sources for crawling: repos, docs, PDFs, websites, dashboards, 
package manifests, CI logs, screenshots, runtime URLs.
"""

from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import hashlib
import json
from pathlib import Path


class SourceType(Enum):
    REPO = "repo"
    DOC = "doc"
    PDF = "pdf"
    WEBSITE = "website"
    DASHBOARD = "dashboard"
    PACKAGE_MANIFEST = "package_manifest"
    CI_LOG = "ci_log"
    SCREENSHOT = "screenshot"
    RUNTIME_URL = "runtime_url"
    GITHUB = "github"
    HUGGINGFACE = "huggingface"
    API_ENDPOINT = "api_endpoint"


class SourceStatus(Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Source:
    """Represents a source to be crawled."""
    source_id: str
    source_type: SourceType
    url: str
    name: str
    status: SourceStatus = SourceStatus.PENDING
    priority: int = 0
    metadata: Dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_crawled: Optional[str] = None
    crawl_count: int = 0
    tags: Set[str] = field(default_factory=set)
    
    def to_dict(self) -> Dict:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type.value,
            "url": self.url,
            "name": self.name,
            "status": self.status.value,
            "priority": self.priority,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_crawled": self.last_crawled,
            "crawl_count": self.crawl_count,
            "tags": list(self.tags)
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Source":
        return cls(
            source_id=data["source_id"],
            source_type=SourceType(data["source_type"]),
            url=data["url"],
            name=data["name"],
            status=SourceStatus(data["status"]),
            priority=data.get("priority", 0),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
            last_crawled=data.get("last_crawled"),
            crawl_count=data.get("crawl_count", 0),
            tags=set(data.get("tags", []))
        )
    
    def generate_id(self) -> str:
        """Generate a stable ID from URL and type."""
        content = f"{self.source_type.value}:{self.url}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


class SourceRegistry:
    """Registry for managing all crawl sources."""
    
    def __init__(self, storage_path: Optional[Path] = None):
        self.sources: Dict[str, Source] = {}
        self.storage_path = storage_path or Path("layer_crawler_etl/storage/sources.jsonl")
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._load()
    
    def register_source(
        self,
        source_type: SourceType,
        url: str,
        name: str,
        priority: int = 0,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None
    ) -> Source:
        """Register a new source."""
        temp_source = Source(
            source_id="",
            source_type=source_type,
            url=url,
            name=name,
            priority=priority,
            metadata=metadata or {},
            tags=set(tags or [])
        )
        source_id = temp_source.generate_id()
        temp_source.source_id = source_id
        
        self.sources[source_id] = temp_source
        self._save()
        return temp_source
    
    def get_source(self, source_id: str) -> Optional[Source]:
        """Get a source by ID."""
        return self.sources.get(source_id)
    
    def update_source_status(self, source_id: str, status: SourceStatus) -> bool:
        """Update source status."""
        if source_id in self.sources:
            self.sources[source_id].status = status
            self.sources[source_id].updated_at = datetime.utcnow().isoformat()
            if status == SourceStatus.COMPLETED:
                self.sources[source_id].last_crawled = datetime.utcnow().isoformat()
                self.sources[source_id].crawl_count += 1
            self._save()
            return True
        return False
    
    def get_sources_by_type(self, source_type: SourceType) -> List[Source]:
        """Get all sources of a specific type."""
        return [s for s in self.sources.values() if s.source_type == source_type]
    
    def get_sources_by_status(self, status: SourceStatus) -> List[Source]:
        """Get all sources with a specific status."""
        return [s for s in self.sources.values() if s.status == status]
    
    def get_pending_sources(self, limit: Optional[int] = None) -> List[Source]:
        """Get pending sources sorted by priority."""
        pending = [s for s in self.sources.values() if s.status == SourceStatus.PENDING]
        pending.sort(key=lambda x: (-x.priority, x.created_at))
        return pending[:limit] if limit else pending
    
    def get_sources_by_tag(self, tag: str) -> List[Source]:
        """Get all sources with a specific tag."""
        return [s for s in self.sources.values() if tag in s.tags]
    
    def remove_source(self, source_id: str) -> bool:
        """Remove a source from registry."""
        if source_id in self.sources:
            del self.sources[source_id]
            self._save()
            return True
        return False
    
    def get_stats(self) -> Dict:
        """Get registry statistics."""
        stats = {
            "total": len(self.sources),
            "by_type": {},
            "by_status": {}
        }
        
        for source in self.sources.values():
            stype = source.source_type.value
            status = source.status.value
            
            stats["by_type"][stype] = stats["by_type"].get(stype, 0) + 1
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
        
        return stats
    
    def _save(self):
        """Save registry to storage."""
        with open(self.storage_path, "w") as f:
            for source in self.sources.values():
                f.write(json.dumps(source.to_dict()) + "\n")
    
    def _load(self):
        """Load registry from storage."""
        if not self.storage_path.exists():
            return
        
        with open(self.storage_path, "r") as f:
            for line in f:
                if line.strip():
                    source = Source.from_dict(json.loads(line))
                    self.sources[source.source_id] = source
    
    def export_sources(self, output_path: Path):
        """Export all sources to JSON."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump([s.to_dict() for s in self.sources.values()], f, indent=2)
    
    def import_sources(self, input_path: Path):
        """Import sources from JSON."""
        with open(input_path, "r") as f:
            data = json.load(f)
            for source_data in data:
                source = Source.from_dict(source_data)
                self.sources[source.source_id] = source
        self._save()


# Convenience functions for common source types
def register_github_repo(
    registry: SourceRegistry,
    repo_url: str,
    name: Optional[str] = None,
    priority: int = 0
) -> Source:
    """Register a GitHub repository."""
    if not name:
        name = repo_url.rstrip("/").split("/")[-1]
    return registry.register_source(
        SourceType.GITHUB,
        repo_url,
        name,
        priority=priority,
        tags=["github", "repo", "code"]
    )


def register_huggingface_space(
    registry: SourceRegistry,
    space_url: str,
    name: Optional[str] = None,
    priority: int = 0
) -> Source:
    """Register a Hugging Face Space."""
    if not name:
        name = space_url.rstrip("/").split("/")[-1]
    return registry.register_source(
        SourceType.HUGGINGFACE,
        space_url,
        name,
        priority=priority,
        tags=["huggingface", "space", "ml"]
    )


def register_website(
    registry: SourceRegistry,
    url: str,
    name: Optional[str] = None,
    priority: int = 0
) -> Source:
    """Register a website for crawling."""
    if not name:
        name = url
    return registry.register_source(
        SourceType.WEBSITE,
        url,
        name,
        priority=priority,
        tags=["website", "docs"]
    )


def register_api_endpoint(
    registry: SourceRegistry,
    url: str,
    name: Optional[str] = None,
    priority: int = 0,
    metadata: Optional[Dict] = None
) -> Source:
    """Register an API endpoint."""
    if not name:
        name = url
    return registry.register_source(
        SourceType.API_ENDPOINT,
        url,
        name,
        priority=priority,
        metadata=metadata or {},
        tags=["api", "endpoint"]
    )
