"""
Layer 1: Dependency Crawler
Crawls and analyzes package dependencies for security and license risks.
"""

import asyncio
import json
from typing import Dict, List, Optional
from pathlib import Path

from layer_crawler_etl.layer1_crawlers.base_crawler import BaseCrawler, CrawlResult
from layer_crawler_etl.layer0_source_registry.source_registry import Source


class DependencyCrawler(BaseCrawler):
    """Crawls and analyzes package dependencies."""
    
    crawler_type = "dependency"
    
    # Known risky licenses
    RISKY_LICENSES = ["GPL", "AGPL", "SSPL", "CPOL"]
    
    # Common vulnerability patterns (simplified)
    VULNERABILITY_PATTERNS = [
        "lodash<4.17.21",
        "axios<0.21.1",
        "node-forge<1.3.0",
        "minimist<1.2.6"
    ]
    
    def validate_source(self, source: Source) -> bool:
        """Validate that source has dependency information."""
        return "package" in source.source_type.value.lower() or "repo" in source.source_type.value.lower()
    
    async def crawl(self, source: Source) -> CrawlResult:
        """Crawl dependencies from source."""
        result = CrawlResult(source_id=source.source_id)
        start_time = asyncio.get_event_loop().time()
        
        try:
            data = await self._analyze_dependencies(source)
            result.data = data
            
            # Check for vulnerabilities
            vulnerabilities = self._check_vulnerabilities(data)
            if vulnerabilities:
                result.add_warning(f"Found {len(vulnerabilities)} potential vulnerabilities")
                data["vulnerabilities"] = vulnerabilities
            
            # Check for license risks
            license_risks = self._check_license_risks(data)
            if license_risks:
                result.add_warning(f"Found {len(license_risks)} risky licenses")
                data["license_risks"] = license_risks
            
            artifact_path = self.save_raw_data(source.source_id, data, "dependencies.json")
            result.add_artifact(artifact_path)
            
        except Exception as e:
            result.add_error(f"Dependency crawl failed: {str(e)}")
        
        result.crawl_duration_seconds = asyncio.get_event_loop().time() - start_time
        return result
    
    async def _analyze_dependencies(self, source: Source) -> Dict:
        """Analyze dependencies from source."""
        data = {
            "source_url": source.url,
            "dependencies": [],
            "total_count": 0,
            "direct_count": 0,
            "transitive_count": 0,
            "by_language": {},
            "outdated_count": 0
        }
        
        # If local path, analyze dependency files
        if source.url.startswith("/") or source.url.startswith("./"):
            local_path = Path(source.url)
            if local_path.exists():
                data = await self._analyze_local_dependencies(local_path, data)
        
        return data
    
    async def _analyze_local_dependencies(self, path: Path, data: Dict) -> Dict:
        """Analyze dependencies from local files."""
        
        # Python requirements.txt
        req_file = path / "requirements.txt"
        if req_file.exists():
            python_deps = await self._parse_requirements_txt(req_file)
            data["dependencies"].extend(python_deps)
            data["by_language"]["Python"] = len(python_deps)
        
        # Node package.json
        pkg_file = path / "package.json"
        if pkg_file.exists():
            node_deps = await self._parse_package_json(pkg_file)
            data["dependencies"].extend(node_deps)
            data["by_language"]["JavaScript/Node"] = len(node_deps)
        
        # Go go.mod
        go_mod = path / "go.mod"
        if go_mod.exists():
            go_deps = await self._parse_go_mod(go_mod)
            data["dependencies"].extend(go_deps)
            data["by_language"]["Go"] = len(go_deps)
        
        # Rust Cargo.toml
        cargo_toml = path / "Cargo.toml"
        if cargo_toml.exists():
            rust_deps = await self._parse_cargo_toml(cargo_toml)
            data["dependencies"].extend(rust_deps)
            data["by_language"]["Rust"] = len(rust_deps)
        
        data["total_count"] = len(data["dependencies"])
        data["direct_count"] = len(data["dependencies"])  # Simplified
        
        return data
    
    async def _parse_requirements_txt(self, path: Path) -> List[Dict]:
        """Parse Python requirements.txt."""
        deps = []
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    # Parse: package==version or package>=version
                    parts = re.split(r"[=<>~!]", line, 1)
                    name = parts[0].strip()
                    version = parts[1].strip() if len(parts) > 1 else None
                    deps.append({
                        "name": name,
                        "version": version,
                        "language": "Python",
                        "type": "direct"
                    })
        return deps
    
    async def _parse_package_json(self, path: Path) -> List[Dict]:
        """Parse Node package.json."""
        deps = []
        with open(path, "r") as f:
            pkg = json.load(f)
            
            for dep_type in ["dependencies", "devDependencies"]:
                if dep_type in pkg:
                    for name, version in pkg[dep_type].items():
                        deps.append({
                            "name": name,
                            "version": version,
                            "language": "JavaScript/Node",
                            "type": "dev" if dep_type == "devDependencies" else "direct"
                        })
        return deps
    
    async def _parse_go_mod(self, path: Path) -> List[Dict]:
        """Parse Go go.mod."""
        deps = []
        with open(path, "r") as f:
            in_require = False
            for line in f:
                line = line.strip()
                if line == "require (":
                    in_require = True
                    continue
                if in_require and line == ")":
                    break
                if in_require:
                    parts = line.split()
                    if len(parts) >= 2:
                        deps.append({
                            "name": parts[0],
                            "version": parts[1],
                            "language": "Go",
                            "type": "direct"
                        })
        return deps
    
    async def _parse_cargo_toml(self, path: Path) -> List[Dict]:
        """Parse Rust Cargo.toml."""
        deps = []
        # Simplified parsing
        with open(path, "r") as f:
            content = f.read()
            # This is a simplified parser - production would use toml library
            if "[dependencies]" in content:
                deps_section = content.split("[dependencies]")[1].split("\n\n")[0]
                for line in deps_section.split("\n"):
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        parts = line.split("=")
                        name = parts[0].strip()
                        version = parts[1].strip().strip('"')
                        deps.append({
                            "name": name,
                            "version": version,
                            "language": "Rust",
                            "type": "direct"
                        })
        return deps
    
    def _check_vulnerabilities(self, data: Dict) -> List[Dict]:
        """Check for known vulnerable dependencies."""
        vulnerabilities = []
        for dep in data.get("dependencies", []):
            for pattern in self.VULNERABILITY_PATTERNS:
                if pattern in f"{dep['name']}{dep.get('version', '')}":
                    vulnerabilities.append({
                        "dependency": dep["name"],
                        "version": dep.get("version"),
                        "pattern": pattern
                    })
        return vulnerabilities
    
    def _check_license_risks(self, data: Dict) -> List[Dict]:
        """Check for risky licenses."""
        risks = []
        for dep in data.get("dependencies", []):
            # In production, would query license databases
            # This is a simplified check
            for risky in self.RISKY_LICENSES:
                if risky.lower() in dep.get("license", "").lower():
                    risks.append({
                        "dependency": dep["name"],
                        "license": dep.get("license"),
                        "risk_type": risky
                    })
        return risks


import re
