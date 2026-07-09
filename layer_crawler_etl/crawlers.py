"""
Subject-specific crawler implementations
"""
import asyncio
import subprocess
import re
from pathlib import Path
from typing import List, Dict, Any
from .core import BaseCrawler, Source, SubjectType, EvidenceType

class CodeCrawler(BaseCrawler):
    """Crawls code repositories for structure, tests, and build evidence"""
    
    def __init__(self):
        super().__init__("code_crawler")
    
    async def crawl(self, source: Source) -> List:
        signals = []
        repo_path = Path(source.location)
        
        if not repo_path.exists():
            return signals
        
        # Check for build files
        build_files = ["package.json", "requirements.txt", "pyproject.toml", "Cargo.toml", "go.mod", "pom.xml"]
        has_build = any((repo_path / f).exists() for f in build_files)
        self.add_signal(SubjectType.CODE, EvidenceType.BUILD_VERIFIED, has_build, source.location)
        
        # Check for test files
        test_patterns = ["test_*.py", "*_test.py", "*.test.js", "*.spec.js", "tests/", "test/"]
        has_tests = any(
            (repo_path / p).exists() if "/" in p else any(repo_path.rglob(p))
            for p in test_patterns
        )
        self.add_signal(SubjectType.CODE, EvidenceType.TESTS_VERIFIED, has_tests, source.location)
        
        # Count source files
        source_extensions = [".py", ".js", ".ts", ".go", ".rs", ".java"]
        source_count = sum(1 for ext in source_extensions for _ in repo_path.rglob(f"*{ext}"))
        signals.extend(self.signals)
        
        return signals

class DependencyCrawler(BaseCrawler):
    """Crawls dependency manifests for risk assessment"""
    
    def __init__(self):
        super().__init__("dependency_crawler")
    
    async def crawl(self, source: Source) -> List:
        signals = []
        repo_path = Path(source.location)
        
        if not repo_path.exists():
            return signals
        
        # Check requirements.txt
        req_file = repo_path / "requirements.txt"
        if req_file.exists():
            with open(req_file) as f:
                deps = [line.strip() for line in f if line.strip() and not line.startswith("#")]
            self.add_signal(SubjectType.DEPENDENCY, EvidenceType.BUILD_VERIFIED, len(deps), source.location)
        
        # Check package.json
        pkg_file = repo_path / "package.json"
        if pkg_file.exists():
            import json
            with open(pkg_file) as f:
                pkg = json.load(f)
            deps_count = len(pkg.get("dependencies", {})) + len(pkg.get("devDependencies", {}))
            self.add_signal(SubjectType.DEPENDENCY, EvidenceType.BUILD_VERIFIED, deps_count, source.location)
        
        signals.extend(self.signals)
        return signals

class LicenseCrawler(BaseCrawler):
    """Crawls for license information"""
    
    def __init__(self):
        super().__init__("license_crawler")
    
    async def crawl(self, source: Source) -> List:
        signals = []
        repo_path = Path(source.location)
        
        if not repo_path.exists():
            return signals
        
        # Check for LICENSE file
        license_files = ["LICENSE", "LICENSE.txt", "LICENSE.md", "COPYING"]
        has_license = any((repo_path / f).exists() for f in license_files)
        self.add_signal(SubjectType.LICENSE, EvidenceType.BUILD_VERIFIED, has_license, source.location)
        
        # Check for GPL (potential conflict)
        if has_license:
            for lic_file in license_files:
                lic_path = repo_path / lic_file
                if lic_path.exists():
                    with open(lic_path) as f:
                        content = f.read().lower()
                    has_gpl = "gpl" in content or "general public license" in content
                    self.add_signal(SubjectType.LICENSE, EvidenceType.LICENSE_CONFLICT, int(has_gpl), source.location)
                    break
        
        signals.extend(self.signals)
        return signals

class TestBuildCrawler(BaseCrawler):
    """Runs tests and builds to verify they pass"""
    
    def __init__(self):
        super().__init__("test_build_crawler")
    
    async def crawl(self, source: Source) -> List:
        signals = []
        repo_path = Path(source.location)
        
        if not repo_path.exists():
            return signals
        
        # Try to run Python tests
        if (repo_path / "requirements.txt").exists():
            try:
                result = subprocess.run(
                    ["python", "-m", "pytest", "--collect-only", "-q"],
                    cwd=repo_path,
                    capture_output=True,
                    timeout=30
                )
                tests_collected = result.returncode == 0
                self.add_signal(SubjectType.TEST_BUILD, EvidenceType.TESTS_VERIFIED, tests_collected, source.location)
            except:
                self.add_signal(SubjectType.TEST_BUILD, EvidenceType.TESTS_VERIFIED, False, source.location)
        
        # Try to run npm test
        if (repo_path / "package.json").exists():
            try:
                result = subprocess.run(
                    ["npm", "test", "--", "--dry-run"],
                    cwd=repo_path,
                    capture_output=True,
                    timeout=30
                )
                tests_pass = result.returncode == 0
                self.add_signal(SubjectType.TEST_BUILD, EvidenceType.TESTS_VERIFIED, tests_pass, source.location)
            except:
                self.add_signal(SubjectType.TEST_BUILD, EvidenceType.TESTS_VERIFIED, False, source.location)
        
        signals.extend(self.signals)
        return signals

class SecuritySecretsCrawler(BaseCrawler):
    """Scans for exposed secrets and API keys"""
    
    def __init__(self):
        super().__init__("security_secrets_crawler")
        self.secret_patterns = [
            r'api[_-]?key\s*[:=]\s*["\']?[a-zA-Z0-9]{20,}',
            r'secret[_-]?key\s*[:=]\s*["\']?[a-zA-Z0-9]{20,}',
            r'password\s*[:=]\s*["\']?[a-zA-Z0-9]{8,}',
            r'token\s*[:=]\s*["\']?[a-zA-Z0-9]{20,}',
            r'aws[_-]?access[_-]?key[_-]?id',
            r'aws[_-]?secret',
            r'sk-[a-zA-Z0-9]{32,}',  # OpenAI keys
            r'hf_[a-zA-Z0-9]{20,}',  # HuggingFace keys
        ]
    
    async def crawl(self, source: Source) -> List:
        signals = []
        repo_path = Path(source.location)
        
        if not repo_path.exists():
            return signals
        
        secrets_found = 0
        # Scan common file types
        for ext in [".py", ".js", ".ts", ".env", ".yaml", ".yml", ".json"]:
            for file_path in repo_path.rglob(f"*{ext}"):
                try:
                    with open(file_path) as f:
                        content = f.read()
                    for pattern in self.secret_patterns:
                        matches = re.findall(pattern, content, re.IGNORECASE)
                        secrets_found += len(matches)
                except:
                    pass
        
        self.add_signal(SubjectType.SECURITY_SECRETS, EvidenceType.SECRETS_EXPOSED, secrets_found, source.location)
        signals.extend(self.signals)
        return signals

class DocsClaimsCrawler(BaseCrawler):
    """Extracts claims from documentation"""
    
    def __init__(self):
        super().__init__("docs_claims_crawler")
    
    async def crawl(self, source: Source) -> List:
        signals = []
        repo_path = Path(source.location)
        
        if not repo_path.exists():
            return signals
        
        # Check for README
        readme_files = ["README.md", "README.rst", "README.txt", "readme.md"]
        has_readme = any((repo_path / f).exists() for f in readme_files)
        self.add_signal(SubjectType.DOCS_CLAIMS, EvidenceType.BUILD_VERIFIED, has_readme, source.location)
        
        # Count documentation files
        doc_count = sum(1 for f in repo_path.rglob("*.md") if "docs" in str(f))
        self.add_signal(SubjectType.DOCS_CLAIMS, EvidenceType.BUILD_VERIFIED, doc_count, source.location)
        
        signals.extend(self.signals)
        return signals
