"""
Layer 1: License Crawler
Crawls and analyzes license information for compliance risks.
"""

import asyncio
from typing import Dict, List, Optional
from pathlib import Path

from layer_crawler_etl.layer1_crawlers.base_crawler import BaseCrawler, CrawlResult
from layer_crawler_etl.layer0_source_registry.source_registry import Source


class LicenseCrawler(BaseCrawler):
    """Crawls and analyzes license information."""
    
    crawler_type = "license"
    
    # License compatibility matrix (simplified)
    PERMISSIVE_LICENSES = ["MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC"]
    COPYLEFT_LICENSES = ["GPL-2.0", "GPL-3.0", "AGPL-3.0", "LGPL-2.1", "LGPL-3.0"]
    PROPRIETARY_LICENSES = ["Proprietary", "Commercial", "All Rights Reserved"]
    
    def validate_source(self, source: Source) -> bool:
        """Validate that source can have license information."""
        return True  # Any source can have license info
    
    async def crawl(self, source: Source) -> CrawlResult:
        """Crawl license information."""
        result = CrawlResult(source_id=source.source_id)
        start_time = asyncio.get_event_loop().time()
        
        try:
            data = await self._analyze_licenses(source)
            result.data = data
            
            # Check for license conflicts
            conflicts = self._check_license_conflicts(data)
            if conflicts:
                result.add_warning(f"Found {len(conflicts)} potential license conflicts")
                data["conflicts"] = conflicts
            
            artifact_path = self.save_raw_data(source.source_id, data, "licenses.json")
            result.add_artifact(artifact_path)
            
        except Exception as e:
            result.add_error(f"License crawl failed: {str(e)}")
        
        result.crawl_duration_seconds = asyncio.get_event_loop().time() - start_time
        return result
    
    async def _analyze_licenses(self, source: Source) -> Dict:
        """Analyze licenses from source."""
        data = {
            "source_url": source.url,
            "primary_license": None,
            "all_licenses": [],
            "license_type": None,
            "commercial_use_allowed": False,
            "modification_allowed": False,
            "distribution_allowed": False,
            "patent_grant": False,
            "liability_limit": False,
            "requires_copyleft": False,
            "requires_source_disclosure": False,
            "compatibility_score": 0
        }
        
        # If local path, analyze license files
        if source.url.startswith("/") or source.url.startswith("./"):
            local_path = Path(source.url)
            if local_path.exists():
                data = await self._analyze_local_licenses(local_path, data)
        
        return data
    
    async def _analyze_local_licenses(self, path: Path, data: Dict) -> Dict:
        """Analyze licenses from local files."""
        license_files = ["LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING", "NOTICE"]
        
        for filename in license_files:
            license_file = path / filename
            if license_file.exists():
                content = license_file.read_text()
                license_info = self._parse_license_content(content)
                if license_info:
                    data["all_licenses"].append(license_info)
                    if not data["primary_license"]:
                        data["primary_license"] = license_info["name"]
        
        if data["primary_license"]:
            data = self._classify_license(data)
        
        return data
    
    def _parse_license_content(self, content: str) -> Optional[Dict]:
        """Parse license file content to identify license."""
        content_lower = content.lower()
        
        license_keywords = {
            "MIT": ["mit license", "permission is hereby granted"],
            "Apache-2.0": ["apache license", "version 2.0", "apache-2.0"],
            "GPL-2.0": ["gnu general public license", "version 2"],
            "GPL-3.0": ["gnu general public license", "version 3"],
            "AGPL-3.0": ["gnu affero general public", "version 3"],
            "BSD-2-Clause": ["bsd 2-clause", "simplified bsd"],
            "BSD-3-Clause": ["bsd 3-clause", "new bsd", "modified bsd"],
            "ISC": ["isc license"]
        }
        
        for license_name, keywords in license_keywords.items():
            if any(kw in content_lower for kw in keywords):
                return {
                    "name": license_name,
                    "type": self._get_license_type(license_name),
                    "spdx_id": license_name
                }
        
        return None
    
    def _get_license_type(self, license_name: str) -> str:
        """Classify license type."""
        if license_name in self.PERMISSIVE_LICENSES:
            return "permissive"
        elif license_name in self.COPYLEFT_LICENSES:
            return "copyleft"
        elif license_name in self.PROPRIETARY_LICENSES:
            return "proprietary"
        return "unknown"
    
    def _classify_license(self, data: Dict) -> Dict:
        """Classify license properties."""
        license_name = data["primary_license"]
        
        if license_name in self.PERMISSIVE_LICENSES:
            data["license_type"] = "permissive"
            data["commercial_use_allowed"] = True
            data["modification_allowed"] = True
            data["distribution_allowed"] = True
            data["compatibility_score"] = 100
        elif license_name in self.COPYLEFT_LICENSES:
            data["license_type"] = "copyleft"
            data["commercial_use_allowed"] = True
            data["modification_allowed"] = True
            data["distribution_allowed"] = True
            data["requires_copyleft"] = True
            data["requires_source_disclosure"] = True
            data["compatibility_score"] = 60
        else:
            data["license_type"] = "unknown"
            data["compatibility_score"] = 0
        
        return data
    
    def _check_license_conflicts(self, data: Dict) -> List[Dict]:
        """Check for license conflicts."""
        conflicts = []
        
        # Check for mixing permissive and copyleft
        has_permissive = any(l["type"] == "permissive" for l in data.get("all_licenses", []))
        has_copyleft = any(l["type"] == "copyleft" for l in data.get("all_licenses", []))
        
        if has_permissive and has_copyleft:
            conflicts.append({
                "type": "mixed_licenses",
                "description": "Mixing permissive and copyleft licenses may require careful integration"
            })
        
        # Check for AGPL (requires network copyleft)
        has_agpl = any("AGPL" in l.get("name", "") for l in data.get("all_licenses", []))
        if has_agpl:
            conflicts.append({
                "type": "agpl_network_copyleft",
                "description": "AGPL requires source disclosure for network use"
            })
        
        return conflicts
