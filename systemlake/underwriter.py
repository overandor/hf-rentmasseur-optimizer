"""Underwriting Engine — Computes collateral scores for software assets.

10-dimension scoring formula:

    collateral_score =
      0.18 * functionality
    + 0.14 * reproducibility
    + 0.14 * receipt_strength
    + 0.12 * deployability
    + 0.10 * test_strength
    + 0.10 * documentation
    + 0.10 * security_cleanliness
    + 0.08 * provenance
    + 0.08 * economic_evidence
    + 0.06 * marketability
    - risk_haircuts

Risk haircuts:
    secret_leak_haircut
    missing_license_haircut
    no_tests_haircut
    no_receipts_haircut
    PII_or_sensitive_data_haircut
    trading_claim_haircut
    prototype_sprawl_haircut
    dependency_vulnerability_haircut

Borrowing base estimates (low/mid/high USD) derived from collateral score
and estimated replacement cost.
"""

import os
import json
import sqlite3
import subprocess
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict


@dataclass
class CollateralScore:
    """Collateral readiness score for a software asset — 10 dimensions."""
    system_name: str
    category: str = 'unknown'
    root_path: str = ''

    # System capabilities (from DB)
    has_git: bool = False
    has_dockerfile: bool = False
    has_requirements: bool = False
    has_package_json: bool = False
    has_setup_py: bool = False
    has_makefile: bool = False
    has_readme: bool = False
    file_count: int = 0

    # 10 scoring dimensions (0-100)
    functionality: float = 0.0
    reproducibility: float = 0.0
    receipt_strength: float = 0.0
    deployability: float = 0.0
    test_strength: float = 0.0
    documentation: float = 0.0
    security_cleanliness: float = 0.0
    provenance: float = 0.0
    economic_evidence: float = 0.0
    marketability: float = 0.0

    # Risk haircuts (subtracted from raw score)
    secret_leak_haircut: float = 0.0
    missing_license_haircut: float = 0.0
    no_tests_haircut: float = 0.0
    no_receipts_haircut: float = 0.0
    pii_sensitive_data_haircut: float = 0.0
    trading_claim_haircut: float = 0.0
    prototype_sprawl_haircut: float = 0.0
    dependency_vulnerability_haircut: float = 0.0

    # Verification results
    has_runnable_entrypoint: bool = False
    has_tests: bool = False
    tests_pass: Optional[str] = 'unknown'
    has_endpoints: bool = False
    has_demo_command: bool = False
    has_build_command: bool = False

    # Borrowing base
    borrowing_base_low: float = 0.0
    borrowing_base_mid: float = 0.0
    borrowing_base_high: float = 0.0

    # Verdict
    verdict: str = ''
    next_required_proof: List[str] = field(default_factory=list)

    SCORING_WEIGHTS = {
        'functionality': 0.18,
        'reproducibility': 0.14,
        'receipt_strength': 0.14,
        'deployability': 0.12,
        'test_strength': 0.10,
        'documentation': 0.10,
        'security_cleanliness': 0.10,
        'provenance': 0.08,
        'economic_evidence': 0.08,
        'marketability': 0.06,
    }

    @property
    def raw_score(self) -> float:
        dims = {
            'functionality': self.functionality,
            'reproducibility': self.reproducibility,
            'receipt_strength': self.receipt_strength,
            'deployability': self.deployability,
            'test_strength': self.test_strength,
            'documentation': self.documentation,
            'security_cleanliness': self.security_cleanliness,
            'provenance': self.provenance,
            'economic_evidence': self.economic_evidence,
            'marketability': self.marketability,
        }
        return sum(dims[k] * w for k, w in self.SCORING_WEIGHTS.items())

    @property
    def total_haircut(self) -> float:
        return (self.secret_leak_haircut + self.missing_license_haircut +
                self.no_tests_haircut + self.no_receipts_haircut +
                self.pii_sensitive_data_haircut + self.trading_claim_haircut +
                self.prototype_sprawl_haircut +
                self.dependency_vulnerability_haircut)

    @property
    def collateral_score(self) -> float:
        return max(0.0, min(100.0, self.raw_score - self.total_haircut))

    @property
    def grade(self) -> str:
        s = self.collateral_score
        if s >= 80: return 'A'
        elif s >= 65: return 'B'
        elif s >= 50: return 'C'
        elif s >= 35: return 'D'
        else: return 'F'

    @property
    def collateral_class(self) -> str:
        if self.collateral_score >= 65:
            return 'software_work_equity'
        elif self.collateral_score >= 35:
            return 'prototype_equity'
        else:
            return 'unverifiable'

    def _compute_borrowing_base(self):
        base_hours = max(5, self.functionality / 10)
        rate = 120
        replacement_cost = base_hours * rate * (self.collateral_score / 100)
        self.borrowing_base_low = round(replacement_cost * 0.15, 2)
        self.borrowing_base_mid = round(replacement_cost * 0.40, 2)
        self.borrowing_base_high = round(replacement_cost * 0.70, 2)

    def _compute_verdict(self):
        s = self.collateral_score
        proofs = []
        if not self.has_tests:
            proofs.append('run tests')
        if self.has_endpoints:
            proofs.append('show endpoint health')
        if self.receipt_strength < 50:
            proofs.append('produce receipt chain')
        if self.economic_evidence < 30:
            proofs.append('show usage event')
            proofs.append('show cost avoided')
        if self.missing_license_haircut > 0:
            proofs.append('add license file')
        if self.secret_leak_haircut > 0:
            proofs.append('remove exposed secrets')
        if s >= 65:
            self.verdict = 'underwritable'
        elif s >= 35:
            self.verdict = 'underwritable_after_demo_and_usage_logs'
        else:
            self.verdict = 'not_underwritable_needs_remediation'
        self.next_required_proof = proofs if proofs else ['external audit recommended']

    def to_dict(self) -> Dict:
        self._compute_borrowing_base()
        self._compute_verdict()
        return {
            'system': self.system_name,
            'category': self.category,
            'root_path': self.root_path,
            'collateral_score': round(self.collateral_score, 1),
            'grade': self.grade,
            'collateral_class': self.collateral_class,
            'capabilities': {
                'has_git': self.has_git,
                'has_dockerfile': self.has_dockerfile,
                'has_requirements': self.has_requirements,
                'has_package_json': self.has_package_json,
                'has_setup_py': self.has_setup_py,
                'has_makefile': self.has_makefile,
                'has_readme': self.has_readme,
                'file_count': self.file_count,
            },
            'dimensions': {
                'functionality': round(self.functionality, 1),
                'reproducibility': round(self.reproducibility, 1),
                'receipt_strength': round(self.receipt_strength, 1),
                'deployability': round(self.deployability, 1),
                'test_strength': round(self.test_strength, 1),
                'documentation': round(self.documentation, 1),
                'security_cleanliness': round(self.security_cleanliness, 1),
                'provenance': round(self.provenance, 1),
                'economic_evidence': round(self.economic_evidence, 1),
                'marketability': round(self.marketability, 1),
            },
            'haircuts': {
                'secret_leak': round(self.secret_leak_haircut, 1),
                'missing_license': round(self.missing_license_haircut, 1),
                'no_tests': round(self.no_tests_haircut, 1),
                'no_receipts': round(self.no_receipts_haircut, 1),
                'pii_sensitive_data': round(self.pii_sensitive_data_haircut, 1),
                'trading_claim': round(self.trading_claim_haircut, 1),
                'prototype_sprawl': round(self.prototype_sprawl_haircut, 1),
                'dependency_vulnerability': round(self.dependency_vulnerability_haircut, 1),
            },
            'verification': {
                'has_runnable_entrypoint': self.has_runnable_entrypoint,
                'has_tests': self.has_tests,
                'tests_pass': self.tests_pass,
                'has_endpoints': self.has_endpoints,
                'has_demo_command': self.has_demo_command,
                'has_build_command': self.has_build_command,
            },
            'borrowing_base_estimate_usd': {
                'low': self.borrowing_base_low,
                'mid': self.borrowing_base_mid,
                'high': self.borrowing_base_high,
            },
            'verdict': self.verdict,
            'next_required_proof': self.next_required_proof,
            'raw_score': round(self.raw_score, 1),
            'total_haircut': round(self.total_haircut, 1),
        }


class UnderwritingEngine:
    """Reads the lake and computes collateral scores for software assets."""

    CATEGORY_KEYWORDS = {
        'runtime_infrastructure': ['questionos', 'systemlake', 'quadrantos', 'gateway', 'daemon'],
        'underwriting': ['underwriter', 'underwriting', 'aau', 'collateral', 'attribution'],
        'ai_ml': ['gpt', 'llm', 'model', 'neural', 'transformer', 'embedding'],
        'trading': ['trading', 'backtest', 'strategy', 'exchange', 'signal'],
        'packaging': ['dmg', 'capsule', 'package', 'build', 'release'],
        'web': ['web', 'frontend', 'react', 'vue', 'svelte'],
        'data': ['crawler', 'etl', 'pipeline', 'data', 'scraper'],
        'research': ['research', 'experiment', 'analysis', 'benchmark'],
    }

    def __init__(self, lake_db: str = None):
        self.lake_db = lake_db
        self._conn = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.lake_db)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def _classify_system(self, name: str, root_path: str) -> str:
        low = name.lower()
        for cat, keywords in self.CATEGORY_KEYWORDS.items():
            if any(kw in low for kw in keywords):
                return cat
        return 'general_software'

    def _verify_runnable(self, system: Dict) -> Tuple[bool, bool, str, bool, bool]:
        root = system.get('root_path', '')
        if not root or not os.path.isdir(root):
            return False, False, 'unknown', False, False

        has_entrypoint = False
        has_endpoints = False
        has_demo = False
        has_build = False

        entrypoint_files = ['app.py', 'main.py', 'server.py', 'run.py', 'cli.py',
                           'index.js', 'server.js', 'main.ts', 'main.go']
        for ef in entrypoint_files:
            if os.path.exists(os.path.join(root, ef)):
                has_entrypoint = True
                break

        for f in os.listdir(root):
            if 'demo' in f.lower():
                has_demo = True
                break

        build_files = ['Makefile', 'Dockerfile', 'setup.py', 'pyproject.toml',
                       'package.json', 'build.sh']
        for bf in build_files:
            if os.path.exists(os.path.join(root, bf)):
                has_build = True
                break

        has_endpoints = bool(system.get('has_endpoints', 0))

        has_tests = bool(system.get('has_tests', 0))
        tests_pass = 'unknown'
        if has_tests:
            test_files = [f for f in os.listdir(root)
                         if 'test' in f.lower() and f.endswith('.py')]
            if test_files:
                try:
                    result = subprocess.run(
                        ['python3', '-m', 'pytest', root, '-x', '--tb=no', '-q'],
                        capture_output=True, text=True, timeout=15,
                        cwd=root,
                    )
                    if result.returncode == 0:
                        tests_pass = 'pass'
                    else:
                        tests_pass = 'fail'
                except Exception:
                    tests_pass = 'unknown'

        return has_entrypoint, has_tests, tests_pass, has_endpoints, has_demo or has_build

    def score_system(self, system: Dict) -> CollateralScore:
        name = system['name']
        score = CollateralScore(
            system_name=name,
            category=self._classify_system(name, system.get('root_path', '')),
            root_path=system.get('root_path', ''),
            has_git=bool(system.get('has_git', 0)),
            has_dockerfile=bool(system.get('has_dockerfile', 0)),
            has_requirements=bool(system.get('has_requirements', 0)),
            has_package_json=bool(system.get('has_package_json', 0)),
            has_setup_py=bool(system.get('has_setup_py', 0)),
            has_makefile=bool(system.get('has_makefile', 0)),
            has_readme=bool(system.get('has_readme', 0)),
            file_count=system.get('file_count', 0),
        )

        has_entry, has_tests, tests_pass, has_endpoints, has_demo_build = \
            self._verify_runnable(system)
        score.has_runnable_entrypoint = has_entry
        score.has_tests = has_tests
        score.tests_pass = tests_pass
        score.has_endpoints = has_endpoints
        score.has_demo_command = has_demo_build
        score.has_build_command = has_demo_build

        # 1. Functionality (0.18)
        func = 10  # baseline for existing as a detected system
        if has_entry: func += 20
        if system.get('file_count', 0) > 5: func += 15
        if system.get('file_count', 0) > 20: func += 10
        if system.get('file_count', 0) > 50: func += 5
        if system.get('has_requirements') or system.get('has_package_json'): func += 10
        if system.get('has_setup_py') or system.get('has_makefile'): func += 10
        if system.get('has_git'): func += 10
        if has_endpoints: func += 10
        if has_demo_build: func += 10
        score.functionality = min(100, func)

        # 2. Reproducibility (0.14)
        repro = 10  # baseline
        if system.get('has_requirements') or system.get('has_package_json'): repro += 25
        if system.get('has_readme'): repro += 20
        if system.get('has_dockerfile'): repro += 20
        if system.get('has_setup_py') or system.get('has_makefile'): repro += 10
        if system.get('has_git'): repro += 15
        score.reproducibility = min(100, repro)

        # 3. Receipt Strength (0.14)
        receipt = 10  # baseline — system exists and was detected
        if system.get('has_receipts'): receipt += 30
        receipt_files = self._count_files(system, 'receipt')
        if receipt_files > 0: receipt += min(30, receipt_files * 5)
        db_files = self._count_files(system, 'database')
        if db_files > 0: receipt += 15
        if system.get('has_git'): receipt += 20  # git history is provenance evidence
        score.receipt_strength = min(100, receipt)

        # 4. Deployability (0.12)
        deploy = 10  # baseline
        if has_endpoints: deploy += 30
        if system.get('has_dockerfile'): deploy += 25
        if has_tests: deploy += 15
        if system.get('has_requirements') or system.get('has_package_json'): deploy += 10
        if has_entry: deploy += 10
        score.deployability = min(100, deploy)

        # 5. Test Strength (0.10)
        test_score = 5  # baseline
        if has_tests: test_score += 35
        if tests_pass == 'pass': test_score += 40
        elif tests_pass == 'fail': test_score += 15  # failing tests still show discipline
        test_files = self._count_files(system, 'test')
        if test_files > 0: test_score += min(20, test_files * 3)
        score.test_strength = min(100, test_score)

        # 6. Documentation (0.10)
        doc = 5  # baseline
        if system.get('has_readme'): doc += 45
        doc_files = self._count_files_by_pattern(system, ['readme', 'doc', 'guide', 'runbook'])
        if doc_files > 0: doc += min(30, doc_files * 10)
        if system.get('has_dockerfile'): doc += 10
        if system.get('has_makefile'): doc += 10
        score.documentation = min(100, doc)

        # 7. Security Cleanliness (0.10)
        security = 60  # baseline — innocent until proven dirty
        env_files = self._count_files_by_pattern(system, ['.env'])
        if env_files == 0:
            security += 15  # clean
        else:
            security -= 15
            score.secret_leak_haircut = min(20, env_files * 8)
        secret_files = self._count_files_by_pattern(
            system, ['token', 'secret', 'private', 'key', 'credential'])
        if secret_files > 0:
            security -= 10
            score.secret_leak_haircut += min(10, secret_files * 3)
        if system.get('has_dockerfile'): security += 10
        if system.get('has_git'): security += 5  # version control is a security practice
        score.security_cleanliness = max(0, min(100, security))

        # 8. Provenance (0.08)
        prov = 10  # baseline
        if system.get('has_git'): prov += 40
        if system.get('has_readme'): prov += 15
        license_files = self._count_files_by_pattern(system, ['license', 'licence', 'copying'])
        if license_files > 0: prov += 25
        if system.get('has_receipts'): prov += 10
        score.provenance = min(100, prov)

        # 9. Economic Evidence (0.08)
        econ = 5  # baseline
        econ_files = self._count_files_by_pattern(system, ['cost', 'economic', 'ledger', 'invoice'])
        if econ_files > 0: econ += min(40, econ_files * 10)
        if system.get('has_receipts'): econ += 20
        if has_endpoints: econ += 15
        usage_files = self._count_files_by_pattern(system, ['usage', 'analytics', 'metrics'])
        if usage_files > 0: econ += 15
        if system.get('has_git'): econ += 5  # version history is economic evidence
        score.economic_evidence = min(100, econ)

        # 10. Marketability (0.06)
        market = 35  # baseline — detected system has some marketability
        if system.get('has_readme'): market += 20
        if has_endpoints: market += 15
        if has_demo_build: market += 15
        if system.get('has_dockerfile'): market += 15
        score.marketability = min(100, market)

        # Risk Haircuts — proportional, not punitive
        if not has_tests:
            score.no_tests_haircut = 10
        if score.receipt_strength < 20:
            score.no_receipts_haircut = 8
        if license_files == 0:
            score.missing_license_haircut = 5
        if system.get('file_count', 0) < 3:
            score.prototype_sprawl_haircut = 5
        elif system.get('file_count', 0) > 200:
            score.prototype_sprawl_haircut = 3
        if score.category == 'trading':
            score.trading_claim_haircut = 10
        pii_files = self._count_files_by_pattern(
            system, ['medical', 'legal', 'personal', 'private', 'password'])
        if pii_files > 0:
            score.pii_sensitive_data_haircut = min(10, pii_files * 3)
        lock_files = self._count_files_by_pattern(
            system, ['poetry.lock', 'package-lock.json', 'yarn.lock', 'Pipfile.lock'])
        if lock_files == 0 and (system.get('has_requirements') or system.get('has_package_json')):
            score.dependency_vulnerability_haircut = 5

        return score

    def _system_path_prefix(self, system: Dict) -> str:
        """Compute the DB path prefix for a system by finding the crawl root."""
        root_path = system.get('root_path', '')
        if not root_path:
            return system.get('name', '') + '/'
        conn = self._get_conn()
        # Get the most recent crawl root
        crawl = conn.execute(
            'SELECT root FROM crawls ORDER BY started_at DESC LIMIT 1'
        ).fetchone()
        if crawl:
            try:
                rel = os.path.relpath(root_path, crawl['root'])
                return rel + '/'
            except Exception:
                pass
        return system.get('name', '') + '/'

    def _count_files(self, system: Dict, category: str) -> int:
        conn = self._get_conn()
        prefix = self._system_path_prefix(system)
        row = conn.execute(
            "SELECT COUNT(*) as c FROM files WHERE path LIKE ? AND category = ? AND deleted = 0",
            (prefix + '%', category)
        ).fetchone()
        return row['c'] if row else 0

    def _count_files_by_pattern(self, system: Dict, patterns: List[str]) -> int:
        conn = self._get_conn()
        prefix = self._system_path_prefix(system)
        count = 0
        for pat in patterns:
            rows = conn.execute(
                "SELECT COUNT(*) as c FROM files WHERE path LIKE ? AND deleted = 0",
                (prefix + '%' + pat + '%',)
            ).fetchone()
            count += rows['c'] if rows else 0
        return count

    def score_all(self) -> List[CollateralScore]:
        conn = self._get_conn()
        rows = conn.execute('SELECT * FROM systems ORDER BY name').fetchall()
        return [self.score_system(dict(r)) for r in rows]

    def risk_register(self) -> List[Dict]:
        scores = self.score_all()
        risks = []
        for s in scores:
            d = s.to_dict()
            for haircut_name, value in d['haircuts'].items():
                if value > 0:
                    risk_class = self._risk_classification(haircut_name, s)
                    risks.append({
                        'system': s.system_name,
                        'risk_type': haircut_name,
                        'severity': 'high' if value >= 20 else 'medium' if value >= 10 else 'low',
                        'haircut': value,
                        'classification': risk_class,
                        'description': self._risk_description(haircut_name),
                        'remediation': self._risk_remediation(haircut_name),
                    })
        return risks

    def _risk_classification(self, name: str, score: CollateralScore) -> str:
        """Classify risk as false_positive, real, or missing_evidence."""
        if name == 'secret_leak':
            return 'real'
        if name == 'pii_sensitive_data':
            return 'real'
        if name == 'trading_claim':
            return 'missing_evidence'
        if name == 'no_tests':
            return 'missing_evidence'
        if name == 'no_receipts':
            return 'missing_evidence'
        if name == 'missing_license':
            return 'missing_evidence'
        if name == 'dependency_vulnerability':
            return 'missing_evidence'
        if name == 'prototype_sprawl':
            return 'false_positive'
        return 'real'

    def _risk_remediation(self, name: str) -> str:
        remediation = {
            'secret_leak': 'Remove .env files and secrets from repo. Use environment variables or secret manager.',
            'missing_license': 'Add LICENSE file (MIT, Apache-2.0, or proprietary).',
            'no_tests': 'Add test files (test_*.py or *.test.js). Run pytest or jest.',
            'no_receipts': 'Generate execution receipts for build/test/deploy commands.',
            'pii_sensitive_data': 'Remove or encrypt PII files. Add to .gitignore.',
            'trading_claim': 'Provide external validation: backtest results, exchange API logs, or audit report.',
            'prototype_sprawl': 'Consolidate or document the system scope.',
            'dependency_vulnerability': 'Add lockfile (requirements.txt with --hash-args, package-lock.json, or Pipfile.lock).',
        }
        return remediation.get(name, 'Review and address risk.')

    def _risk_description(self, name: str) -> str:
        descriptions = {
            'secret_leak': 'Exposed secrets or credentials detected',
            'missing_license': 'No license file found — IP clarity unclear',
            'no_tests': 'No test coverage — functionality unverified',
            'no_receipts': 'No execution receipts — claims unverifiable',
            'pii_sensitive_data': 'PII or sensitive data files present',
            'trading_claim': 'Trading/financial system — claims need external validation',
            'prototype_sprawl': 'Prototype sprawl — too few or too many files',
            'dependency_vulnerability': 'No lockfile — dependency versions not pinned',
        }
        return descriptions.get(name, 'Unknown risk')

    def borrowing_base(self) -> Dict:
        scores = self.score_all()
        total_low = 0
        total_mid = 0
        total_high = 0
        per_system = []
        for s in scores:
            d = s.to_dict()
            bb = d['borrowing_base_estimate_usd']
            total_low += bb['low']
            total_mid += bb['mid']
            total_high += bb['high']
            per_system.append({
                'system': s.system_name,
                'collateral_score': d['collateral_score'],
                'grade': d['grade'],
                'borrowing_base': bb,
                'verdict': d['verdict'],
            })
        return {
            'total_low': round(total_low, 2),
            'total_mid': round(total_mid, 2),
            'total_high': round(total_high, 2),
            'systems': sorted(per_system, key=lambda x: x['collateral_score'], reverse=True),
            'disclaimer': (
                'Borrowing base estimates are derived from collateral scores '
                'and estimated replacement cost. Not a guaranteed valuation. '
                'Subject to external audit and due diligence.'
            ),
        }

    def report(self) -> str:
        scores = self.score_all()
        if not scores:
            return "No systems found to underwrite."

        lines = []
        lines.append("=" * 70)
        lines.append("  MEMBRA SYSTEMLAKE — COLLATERAL UNDERWRITING REPORT")
        lines.append("=" * 70)
        lines.append("")

        for s in sorted(scores, key=lambda x: x.collateral_score, reverse=True):
            d = s.to_dict()
            lines.append(f"  {d['system']:30s}  Score: {d['collateral_score']:5.1f}  Grade: {d['grade']}  Class: {d['collateral_class']}")
            lines.append(f"    Functionality:     {d['dimensions']['functionality']:5.1f}")
            lines.append(f"    Reproducibility:   {d['dimensions']['reproducibility']:5.1f}")
            lines.append(f"    Receipt Strength:  {d['dimensions']['receipt_strength']:5.1f}")
            lines.append(f"    Deployability:     {d['dimensions']['deployability']:5.1f}")
            lines.append(f"    Test Strength:     {d['dimensions']['test_strength']:5.1f}")
            lines.append(f"    Documentation:     {d['dimensions']['documentation']:5.1f}")
            lines.append(f"    Security:          {d['dimensions']['security_cleanliness']:5.1f}")
            lines.append(f"    Provenance:        {d['dimensions']['provenance']:5.1f}")
            lines.append(f"    Economic Evidence: {d['dimensions']['economic_evidence']:5.1f}")
            lines.append(f"    Marketability:     {d['dimensions']['marketability']:5.1f}")
            lines.append(f"    Verification: entry={d['verification']['has_runnable_entrypoint']} tests={d['verification']['tests_pass']} endpoints={d['verification']['has_endpoints']}")
            lines.append(f"    Borrowing base: ${d['borrowing_base_estimate_usd']['low']:.0f} / ${d['borrowing_base_estimate_usd']['mid']:.0f} / ${d['borrowing_base_estimate_usd']['high']:.0f}")
            lines.append(f"    Verdict: {d['verdict']}")
            for h, v in d['haircuts'].items():
                if v > 0:
                    lines.append(f"    [HAIRCUT] {h}: -{v:.1f}")
            lines.append("")

        lines.append("=" * 70)
        lines.append("  Collateral score = weighted dimensions minus haircuts.")
        lines.append("  Estimated asset readiness, not guaranteed valuation.")
        lines.append("  Every claim must survive attribution review before settlement.")
        lines.append("=" * 70)

        return '\n'.join(lines)


if __name__ == '__main__':
    from systemlake.underwriter_cli import main
    main()
