"""
Layer 1: Code Crawler
Crawls code repositories for structure, dependencies, tests, and build configuration.
"""

import asyncio
import re
from typing import Dict, List, Optional
from pathlib import Path
import json
import subprocess

from layer_crawler_etl.layer1_crawlers.base_crawler import BaseCrawler, CrawlResult
from layer_crawler_etl.layer0_source_registry.source_registry import Source


class CodeCrawler(BaseCrawler):
    """Crawls code repositories for structure and metadata."""
    
    crawler_type = "code"
    
    def __init__(self, storage_path: Optional[Path] = None):
        super().__init__(storage_path)
    
    def validate_source(self, source: Source) -> bool:
        """Validate that source is a code repository."""
        valid_types = ["repo", "github", "git"]
        return any(t in source.source_type.value.lower() for t in valid_types)
    
    async def crawl(self, source: Source) -> CrawlResult:
        """Crawl a code repository."""
        result = CrawlResult(source_id=source.source_id)
        start_time = asyncio.get_event_loop().time()
        
        try:
            # For now, we'll handle local repos or GitHub URLs
            # In production, this would clone repos and analyze them
            data = await self._analyze_repository(source)
            result.data = data
            
            # Save raw data
            artifact_path = self.save_raw_data(source.source_id, data, "code_analysis.json")
            result.add_artifact(artifact_path)
            
        except Exception as e:
            result.add_error(f"Code crawl failed: {str(e)}")
        
        result.crawl_duration_seconds = asyncio.get_event_loop().time() - start_time
        return result
    
    async def _analyze_repository(self, source: Source) -> Dict:
        """Analyze repository structure and metadata."""
        # This is a simplified version
        # In production, would clone and analyze actual repo
        
        data = {
            "source_url": source.url,
            "analysis_type": "code_structure",
            "languages": {},
            "file_count": 0,
            "directory_structure": [],
            "has_tests": False,
            "has_ci": False,
            "has_docs": False,
            "dependency_files": [],
            "build_files": [],
            "license": None,
            "readme_exists": False
        }
        
        # If local path, analyze directly
        if source.url.startswith("/") or source.url.startswith("./"):
            local_path = Path(source.url)
            if local_path.exists():
                data = await self._analyze_local_repo(local_path, data)
        
        return data
    
    async def _analyze_local_repo(self, path: Path, data: Dict) -> Dict:
        """Analyze a local repository."""
        data["file_count"] = sum(1 for _ in path.rglob("*") if _.is_file())
        
        # Detect languages
        lang_extensions = {
            ".py": "Python",
            ".js": "JavaScript",
            ".ts": "TypeScript",
            ".go": "Go",
            ".rs": "Rust",
            ".java": "Java",
            ".cpp": "C++",
            ".c": "C",
            ".rb": "Ruby",
            ".php": "PHP"
        }
        
        for file_path in path.rglob("*"):
            if file_path.is_file():
                ext = file_path.suffix
                if ext in lang_extensions:
                    lang = lang_extensions[ext]
                    data["languages"][lang] = data["languages"].get(lang, 0) + 1
        
        # Check for common files
        data["readme_exists"] = any(
            f.name.lower().startswith("readme") 
            for f in path.iterdir() if f.is_file()
        )
        
        data["has_tests"] = any(
            "test" in f.name.lower() or "spec" in f.name.lower()
            for f in path.rglob("*") if f.is_file()
        )
        
        data["has_ci"] = any(
            f.name in [".github", ".gitlab-ci.yml", ".travis.yml", "circleci"]
            for f in path.iterdir() if f.is_dir() or f.is_file()
        )
        
        data["has_docs"] = any(
            d.name.lower() in ["docs", "documentation"]
            for d in path.iterdir() if d.is_dir()
        )
        
        dependency_patterns = [
            "requirements.txt", "package.json", "go.mod", "Cargo.toml",
            "pom.xml", "build.gradle", "Gemfile", "composer.json"
        ]
        
        data["dependency_files"] = [
            str(f) for f in path.rglob("*")
            if f.is_file() and f.name in dependency_patterns
        ]
        
        build_patterns = [
            "Makefile", "CMakeLists.txt", "build.gradle", "pom.xml",
            "setup.py", "pyproject.toml"
        ]
        
        data["build_files"] = [
            str(f) for f in path.rglob("*")
            if f.is_file() and f.name in build_patterns
        ]
        
        # Try to detect license
        license_files = ["LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"]
        for f in path.iterdir():
            if f.is_file() and f.name in license_files:
                data["license"] = f.name
                break
        
        return data
