"""
Layer 1: Test/Build Crawler
Crawls for test coverage, build configuration, and CI/CD setup.
"""

import asyncio
import json
import os
import sys
from typing import Dict, List, Optional
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from layer_crawler_etl.layer1_crawlers.base_crawler import BaseCrawler, CrawlResult
from layer_crawler_etl.layer0_source_registry.source_registry import Source


class TestBuildCrawler(BaseCrawler):
    """Crawls for test and build configuration."""
    
    crawler_type = "test_build"
    
    # Common test file patterns
    TEST_PATTERNS = [
        "test_*.py", "*_test.py", "test/*.py", "tests/*.py",
        "*.test.js", "*.spec.js", "test/*.js", "tests/*.js",
        "*_test.go", "*_test.rs"
    ]
    
    # Common build files
    BUILD_FILES = [
        "Makefile", "CMakeLists.txt", "build.gradle", "pom.xml",
        "setup.py", "pyproject.toml", "Cargo.toml", "go.mod",
        "package.json", "Gruntfile.js", "Gulpfile.js", "webpack.config.js"
    ]
    
    # CI/CD configurations
    CI_FILES = [
        ".github/workflows/*.yml", ".github/workflows/*.yaml",
        ".gitlab-ci.yml", ".travis.yml", "circleci/config.yml",
        "Jenkinsfile", "azure-pipelines.yml", "bitbucket-pipelines.yml"
    ]
    
    def validate_source(self, source: Source) -> bool:
        """Validate that source can have test/build configuration."""
        return "repo" in source.source_type.value.lower() or "code" in source.source_type.value.lower()
    
    async def crawl(self, source: Source) -> CrawlResult:
        """Crawl test and build configuration."""
        result = CrawlResult(source_id=source.source_id)
        start_time = asyncio.get_event_loop().time()
        
        try:
            data = await self._analyze_test_build(source)
            result.data = data
            
            # Warn if no tests found
            if data.get("test_file_count", 0) == 0:
                result.add_warning("No test files found")
            
            # Warn if no CI/CD configured
            if not data.get("has_ci_cd", False):
                result.add_warning("No CI/CD configuration found")
            
            artifact_path = self.save_raw_data(source.source_id, data, "test_build.json")
            result.add_artifact(artifact_path)
            
        except Exception as e:
            result.add_error(f"Test/Build crawl failed: {str(e)}")
        
        result.crawl_duration_seconds = asyncio.get_event_loop().time() - start_time
        return result
    
    async def _analyze_test_build(self, source: Source) -> Dict:
        """Analyze test and build configuration."""
        data = {
            "source_url": source.url,
            "test_file_count": 0,
            "test_files": [],
            "test_frameworks": [],
            "build_system": None,
            "build_files": [],
            "has_ci_cd": False,
            "ci_config_files": [],
            "ci_provider": None,
            "coverage_configured": False,
            "linting_configured": False,
            "build_commands": []
        }
        
        # If local path, analyze directly
        if source.url.startswith("/") or source.url.startswith("./"):
            local_path = Path(source.url)
            if local_path.exists():
                data = await self._analyze_local_test_build(local_path, data)
        
        return data
    
    async def _analyze_local_test_build(self, path: Path, data: Dict) -> Dict:
        """Analyze local test and build configuration."""
        
        # Find test files
        for pattern in self.TEST_PATTERNS:
            for file_path in path.rglob(pattern):
                if file_path.is_file():
                    data["test_file_count"] += 1
                    data["test_files"].append(str(file_path))
        
        # Detect test frameworks
        data["test_frameworks"] = self._detect_test_frameworks(path)
        
        # Find build files
        for build_file in self.BUILD_FILES:
            if (path / build_file).exists():
                data["build_files"].append(build_file)
                data["build_system"] = self._identify_build_system(build_file)
        
        # Extract build commands
        data["build_commands"] = self._extract_build_commands(path, data["build_system"])
        
        # Check for CI/CD
        for ci_pattern in self.CI_FILES:
            for file_path in path.glob(ci_pattern):
                if file_path.exists():
                    data["has_ci_cd"] = True
                    data["ci_config_files"].append(str(file_path))
                    data["ci_provider"] = self._identify_ci_provider(str(file_path))
        
        # Check for coverage configuration
        coverage_files = [".coveragerc", "coverage.ini", ".nycrc", "jest.config.js"]
        for cov_file in coverage_files:
            if (path / cov_file).exists():
                data["coverage_configured"] = True
                break
        
        # Check for linting configuration
        lint_files = [".eslintrc", ".pylintrc", "pyproject.toml", ".flake8", ".golangci.yml"]
        for lint_file in lint_files:
            if (path / lint_file).exists():
                data["linting_configured"] = True
                break
        
        return data
    
    def _detect_test_frameworks(self, path: Path) -> List[str]:
        """Detect test frameworks in use."""
        frameworks = []
        
        # Python
        if any((path / f).exists() for f in ["pytest.ini", "setup.cfg", "tox.ini"]):
            frameworks.append("pytest")
        if (path / "conftest.py").exists():
            frameworks.append("pytest")
        
        # JavaScript/Node
        pkg_json = path / "package.json"
        if pkg_json.exists():
            with open(pkg_json, "r") as f:
                pkg = json.load(f)
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                if "jest" in deps:
                    frameworks.append("jest")
                if "mocha" in deps:
                    frameworks.append("mocha")
                if "jasmine" in deps:
                    frameworks.append("jasmine")
        
        # Go
        if any(f.name.endswith("_test.go") for f in path.rglob("*.go")):
            frameworks.append("go test")
        
        # Rust
        if (path / "Cargo.toml").exists():
            frameworks.append("cargo test")
        
        return frameworks
    
    def _identify_build_system(self, build_file: str) -> Optional[str]:
        """Identify build system from build file."""
        build_systems = {
            "Makefile": "make",
            "CMakeLists.txt": "cmake",
            "build.gradle": "gradle",
            "pom.xml": "maven",
            "setup.py": "setuptools",
            "pyproject.toml": "poetry/setuptools",
            "Cargo.toml": "cargo",
            "go.mod": "go",
            "package.json": "npm/yarn"
        }
        return build_systems.get(build_file)
    
    def _extract_build_commands(self, path: Path, build_system: Optional[str]) -> List[str]:
        """Extract build commands based on build system."""
        commands = []
        
        if build_system == "make" and (path / "Makefile").exists():
            commands.append("make")
            commands.append("make test")
            commands.append("make build")
        
        elif build_system == "npm/yarn" and (path / "package.json").exists():
            pkg_json = path / "package.json"
            with open(pkg_json, "r") as f:
                pkg = json.load(f)
                scripts = pkg.get("scripts", {})
                if "test" in scripts:
                    commands.append("npm test")
                if "build" in scripts:
                    commands.append("npm run build")
        
        elif build_system == "cargo" and (path / "Cargo.toml").exists():
            commands.append("cargo build")
            commands.append("cargo test")
        
        elif build_system == "go" and (path / "go.mod").exists():
            commands.append("go build")
            commands.append("go test ./...")
        
        elif build_system == "pytest":
            commands.append("pytest")
        
        return commands
    
    def _identify_ci_provider(self, ci_file: str) -> Optional[str]:
        """Identify CI/CD provider from config file."""
        if ".github" in ci_file:
            return "GitHub Actions"
        elif ".gitlab-ci.yml" in ci_file:
            return "GitLab CI"
        elif ".travis.yml" in ci_file:
            return "Travis CI"
        elif "circleci" in ci_file:
            return "CircleCI"
        elif "Jenkinsfile" in ci_file:
            return "Jenkins"
        elif "azure-pipelines.yml" in ci_file:
            return "Azure Pipelines"
        elif "bitbucket-pipelines.yml" in ci_file:
            return "Bitbucket Pipelines"
        return None
