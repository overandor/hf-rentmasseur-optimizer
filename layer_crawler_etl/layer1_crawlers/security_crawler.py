"""
Layer 1: Security/Secrets Crawler
Crawls code for exposed secrets, API keys, and security issues.
"""

import asyncio
import re
from typing import Dict, List, Optional
from pathlib import Path

from layer_crawler_etl.layer1_crawlers.base_crawler import BaseCrawler, CrawlResult
from layer_crawler_etl.layer0_source_registry.source_registry import Source


class SecurityCrawler(BaseCrawler):
    """Crawls for security issues and exposed secrets."""
    
    crawler_type = "security"
    
    # Patterns for detecting secrets (simplified)
    SECRET_PATTERNS = {
        "aws_access_key": r'AKIA[0-9A-Z]{16}',
        "aws_secret_key": r'[0-9a-zA-Z/+]{40}',
        "github_token": r'ghp_[a-zA-Z0-9]{36}',
        "slack_token": r'xox[baprs]-[a-zA-Z0-9-]+',
        "api_key": r'api[_-]?key\s*[:=]\s*["\']?[a-zA-Z0-9_\-]{16,}["\']?',
        "secret": r'secret\s*[:=]\s*["\']?[a-zA-Z0-9_\-]{16,}["\']?',
        "password": r'password\s*[:=]\s*["\']?[a-zA-Z0-9_\-]{8,}["\']?',
        "private_key": r'-----BEGIN[A-Z\s]+PRIVATE KEY-----',
        "jwt": r'eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+'
    }
    
    # Files to exclude from secret scanning
    EXCLUDE_PATTERNS = [
        "*.min.js",
        "node_modules/*",
        ".git/*",
        "vendor/*",
        "dist/*",
        "build/*"
    ]
    
    def validate_source(self, source: Source) -> bool:
        """Validate that source can have security issues."""
        return "repo" in source.source_type.value.lower() or "code" in source.source_type.value.lower()
    
    async def crawl(self, source: Source) -> CrawlResult:
        """Crawl for security issues."""
        result = CrawlResult(source_id=source.source_id)
        start_time = asyncio.get_event_loop().time()
        
        try:
            data = await self._analyze_security(source)
            result.data = data
            
            # Flag if secrets found
            if data.get("secrets_found", 0) > 0:
                result.add_error(f"Found {data['secrets_found']} potential secrets exposed")
            
            # Flag if security issues found
            if data.get("security_issues", 0) > 0:
                result.add_warning(f"Found {data['security_issues']} potential security issues")
            
            artifact_path = self.save_raw_data(source.source_id, data, "security.json")
            result.add_artifact(artifact_path)
            
        except Exception as e:
            result.add_error(f"Security crawl failed: {str(e)}")
        
        result.crawl_duration_seconds = asyncio.get_event_loop().time() - start_time
        return result
    
    async def _analyze_security(self, source: Source) -> Dict:
        """Analyze security issues."""
        data = {
            "source_url": source.url,
            "secrets_found": 0,
            "security_issues": 0,
            "secrets_by_type": {},
            "issues_by_type": {},
            "files_with_secrets": [],
            "high_risk_files": [],
            "recommendations": []
        }
        
        # If local path, scan files
        if source.url.startswith("/") or source.url.startswith("./"):
            local_path = Path(source.url)
            if local_path.exists():
                data = await self._scan_local_path(local_path, data)
        
        return data
    
    async def _scan_local_path(self, path: Path, data: Dict) -> Dict:
        """Scan local path for security issues."""
        
        # Scan for secrets
        for file_path in path.rglob("*"):
            if file_path.is_file() and not self._should_exclude(file_path):
                secrets = self._scan_file_for_secrets(file_path)
                if secrets:
                    data["secrets_found"] += len(secrets)
                    data["files_with_secrets"].append(str(file_path))
                    
                    for secret_type, matches in secrets.items():
                        if secret_type not in data["secrets_by_type"]:
                            data["secrets_by_type"][secret_type] = 0
                        data["secrets_by_type"][secret_type] += len(matches)
        
        # Check for common security issues
        data = self._check_security_issues(path, data)
        
        # Generate recommendations
        data["recommendations"] = self._generate_recommendations(data)
        
        return data
    
    def _should_exclude(self, file_path: Path) -> bool:
        """Check if file should be excluded from scanning."""
        for pattern in self.EXCLUDE_PATTERNS:
            if file_path.match(pattern):
                return True
        return False
    
    def _scan_file_for_secrets(self, file_path: Path) -> Dict[str, List[str]]:
        """Scan a single file for secrets."""
        secrets = {}
        
        try:
            content = file_path.read_text()
            
            for secret_type, pattern in self.SECRET_PATTERNS.items():
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    secrets[secret_type] = matches
        except Exception:
            # Binary files or unreadable files
            pass
        
        return secrets
    
    def _check_security_issues(self, path: Path, data: Dict) -> Dict:
        """Check for common security issues."""
        
        # Check for hardcoded credentials in config files
        config_extensions = [".env", ".config", "conf", "ini", "yaml", "yml"]
        for ext in config_extensions:
            for file_path in path.rglob(f"*{ext}"):
                if file_path.is_file():
                    try:
                        content = file_path.read_text()
                        if re.search(r'(password|secret|key)\s*=\s*\w+', content, re.IGNORECASE):
                            data["security_issues"] += 1
                            data["high_risk_files"].append(str(file_path))
                    except Exception:
                        pass
        
        # Check for debug modes enabled
        for file_path in path.rglob("*.py"):
            if file_path.is_file():
                try:
                    content = file_path.read_text()
                    if "DEBUG = True" in content or "app.debug = True" in content:
                        data["security_issues"] += 1
                        if "debug" not in data["issues_by_type"]:
                            data["issues_by_type"]["debug_enabled"] = 0
                        data["issues_by_type"]["debug_enabled"] += 1
                except Exception:
                    pass
        
        return data
    
    def _generate_recommendations(self, data: Dict) -> List[str]:
        """Generate security recommendations."""
        recommendations = []
        
        if data.get("secrets_found", 0) > 0:
            recommendations.append("Remove exposed secrets and use environment variables")
            recommendations.append("Add .env files to .gitignore")
            recommendations.append("Rotate any exposed credentials")
        
        if data.get("security_issues", 0) > 0:
            recommendations.append("Review and fix high-risk files")
            recommendations.append("Disable debug mode in production")
        
        if any("private_key" in t for t in data.get("secrets_by_type", {}).keys()):
            recommendations.append("Private keys should never be committed to version control")
        
        return recommendations
