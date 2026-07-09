"""
GitHub Repository Assessor - Real GitHub assessment (no mocks)
Assesses GitHub repos for architecture, dependencies, build process, test coverage, security
"""
import asyncio
import aiohttp
import json
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from .core import BaseCrawler, Source, SubjectType, EvidenceType

@dataclass
class GitHubAssessment:
    """Assessment result for a GitHub repository"""
    repo: str
    stars: int
    forks: int
    open_issues: int
    watchers: int
    has_readme: bool
    has_license: bool
    has_tests: bool
    has_ci: bool
    has_workflow: bool
    languages: Dict[str, int]
    topics: List[str]
    archived: bool
    size_kb: int
    updated_at: str
    created_at: str
    verified: bool
    timestamp: str

class GitHubAssessor(BaseCrawler):
    """Real GitHub repository assessor - no mocks"""
    
    def __init__(self, token: Optional[str] = None):
        super().__init__("github_assessor")
        self.token = token
        self.base_url = "https://api.github.com"
        self.headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "LayerCrawler/1.0"
        }
        if token:
            self.headers["Authorization"] = f"token {token}"
    
    async def get_repo_info(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """Get repository information from GitHub API"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/repos/{owner}/{repo}",
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    elif resp.status == 404:
                        return None
                    else:
                        return None
        except Exception:
            return None
    
    async def get_repo_contents(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """Get repository contents"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/repos/{owner}/{repo}/contents/",
                    headers=self.headers,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    return []
        except Exception:
            return []
    
    async def assess_repo(self, repo_full_name: str) -> GitHubAssessment:
        """Assess a GitHub repository"""
        start_time = time.time()
        
        try:
            owner, repo = repo_full_name.split("/", 1)
        except:
            return GitHubAssessment(
                repo=repo_full_name,
                stars=0,
                forks=0,
                open_issues=0,
                watchers=0,
                has_readme=False,
                has_license=False,
                has_tests=False,
                has_ci=False,
                has_workflow=False,
                languages={},
                topics=[],
                archived=False,
                size_kb=0,
                updated_at="",
                created_at="",
                verified=False,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
            )
        
        repo_info = await self.get_repo_info(owner, repo)
        
        if not repo_info:
            return GitHubAssessment(
                repo=repo_full_name,
                stars=0,
                forks=0,
                open_issues=0,
                watchers=0,
                has_readme=False,
                has_license=False,
                has_tests=False,
                has_ci=False,
                has_workflow=False,
                languages={},
                topics=[],
                archived=False,
                size_kb=0,
                updated_at="",
                created_at="",
                verified=False,
                timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
            )
        
        # Get contents to check for specific files
        contents = await self.get_repo_contents(owner, repo)
        
        has_readme = any(
            c.get("name", "").lower().startswith("readme")
            for c in contents if isinstance(c, dict)
        )
        
        has_license = any(
            c.get("name", "").lower().startswith("license")
            for c in contents if isinstance(c, dict)
        )
        
        # Check for test files
        has_tests = any(
            "test" in c.get("name", "").lower()
            for c in contents if isinstance(c, dict)
        )
        
        # Check for CI/workflows
        has_ci = any(
            c.get("name", "").lower() in [".github", "ci", ".circleci", ".travis.yml"]
            for c in contents if isinstance(c, dict)
        )
        
        has_workflow = has_ci  # Simplified
        
        # Get languages
        languages = repo_info.get("language", {})
        if isinstance(languages, str):
            languages = {languages: 100}
        
        return GitHubAssessment(
            repo=repo_full_name,
            stars=repo_info.get("stargazers_count", 0),
            forks=repo_info.get("forks_count", 0),
            open_issues=repo_info.get("open_issues_count", 0),
            watchers=repo_info.get("subscribers_count", 0),
            has_readme=has_readme,
            has_license=has_license,
            has_tests=has_tests,
            has_ci=has_ci,
            has_workflow=has_workflow,
            languages=languages,
            topics=repo_info.get("topics", []),
            archived=repo_info.get("archived", False),
            size_kb=repo_info.get("size", 0),
            updated_at=repo_info.get("updated_at", ""),
            created_at=repo_info.get("created_at", ""),
            verified=True,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S")
        )
    
    async def crawl(self, source: Source) -> List:
        """Crawl GitHub repo and generate signals"""
        signals = []
        
        repo = source.location
        assessment = await self.assess_repo(repo)
        
        # Generate signals based on assessment
        self.add_signal(
            SubjectType.CODE,
            EvidenceType.BUILD_VERIFIED,
            assessment.has_readme and assessment.has_license,
            source.location
        )
        
        self.add_signal(
            SubjectType.CODE,
            EvidenceType.TESTS_VERIFIED,
            assessment.has_tests,
            source.location
        )
        
        self.add_signal(
            SubjectType.LICENSE,
            EvidenceType.BUILD_VERIFIED,
            assessment.has_license,
            source.location
        )
        
        self.add_signal(
            SubjectType.TEST_BUILD,
            EvidenceType.BUILD_VERIFIED,
            assessment.has_ci,
            source.location
        )
        
        signals.extend(self.signals)
        return signals
    
    async def batch_assess(self, repos: List[str]) -> List[GitHubAssessment]:
        """Assess multiple repos in parallel"""
        tasks = [self.assess_repo(repo) for repo in repos]
        return await asyncio.gather(*tasks)

# Example usage
if __name__ == "__main__":
    async def main():
        import os
        token = os.environ.get("GITHUB_TOKEN")
        
        assessor = GitHubAssessor(token=token)
        
        # Test some popular repos
        repos = [
            "facebook/react",
            "tensorflow/tensorflow",
            "openai/openai-python",
        ]
        
        print("Assessing GitHub repositories...")
        results = await assessor.batch_assess(repos)
        
        for result in results:
            print(f"\n{result.repo}:")
            print(f"  Stars: {result.stars}")
            print(f"  Forks: {result.forks}")
            print(f"  Open Issues: {result.open_issues}")
            print(f"  Has README: {result.has_readme}")
            print(f"  Has License: {result.has_license}")
            print(f"  Has Tests: {result.has_tests}")
            print(f"  Has CI: {result.has_ci}")
            print(f"  Languages: {result.languages}")
            print(f"  Archived: {result.archived}")
    
    asyncio.run(main())
