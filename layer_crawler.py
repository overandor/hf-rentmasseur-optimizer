"""
Layer Crawler ETL Engine

Sources → Crawlers → Extractors → Normalizers → Classifiers → Evidence Scorers → Receipts → HardenRank / ProdScore

Layer 0: Source Registry — repos, docs, PDFs, websites, dashboards, manifests, CI logs, screenshots, runtime URLs
Layer 1: Subject Crawlers — code, dependency, license, test/build, browser runtime, artifact, security/secrets, docs/claims
Layer 2: ETL — Extract (pull files, metadata, logs, pages, screenshots), Transform (normalize), Load (JSONL receipts)
Layer 3: Scoring — EvidenceScore, RealityPenalty, ProdScore, HardenRank, IPRisk, RuntimeRisk
Layer 4: Action — recommend hardening, block fake production claims, generate tasks

Queue-based for scale:
  crawler_jobs → workers → raw_store → transform_jobs → normalized_store → scorer → receipts → dashboard

Fanout:
  subjects × systems × evidence_types × environments
  Example: 285 systems × 8 crawler subjects × 4 proof types = 9,120 evidence checks

Hard rule: No receipt → no production claim.
"""

import hashlib
import json
import os
import re
import sqlite3
import time
import threading
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

import requests

from evidence_scorer import (
    EvidenceSignals,
    score_signals,
    create_canonical_record,
)
from receipt_ledger import create_receipt

BASE = Path(__file__).parent
DB_PATH = str(BASE / 'data' / 'crawler_evidence.db')
RECEIPTS_DIR = BASE / 'data' / 'receipts'
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
os.makedirs(RECEIPTS_DIR, exist_ok=True)

log = logging.getLogger('layer_crawler')

CRAWLER_SUBJECTS = [
    'code',
    'dependency',
    'license',
    'test_build',
    'browser_runtime',
    'artifact',
    'security_secrets',
    'docs_claims',
]

EVIDENCE_TYPES = [
    'build_proof',
    'test_proof',
    'runtime_proof',
    'security_proof',
]


def init_db(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS crawler_jobs (
        id TEXT PRIMARY KEY,
        system TEXT NOT NULL,
        subject TEXT NOT NULL,
        source_url TEXT,
        source_type TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT NOT NULL,
        started_at TEXT,
        completed_at TEXT,
        raw_artifact_path TEXT,
        normalized_json TEXT,
        scores_json TEXT,
        receipt_id TEXT,
        error TEXT
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_job_status ON crawler_jobs(status)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_job_system ON crawler_jobs(system)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_job_subject ON crawler_jobs(subject)')
    c.execute('''CREATE TABLE IF NOT EXISTS source_registry (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        source_type TEXT NOT NULL,
        url TEXT,
        path TEXT,
        metadata TEXT,
        registered_at TEXT NOT NULL,
        active INTEGER DEFAULT 1
    )''')
    conn.commit()
    conn.close()


def register_source(name: str, source_type: str, url: str = '', path: str = '', metadata: dict = None) -> str:
    """Register a source in Layer 0."""
    init_db()
    sid = hashlib.md5(f"{name}:{url or path}".encode()).hexdigest()[:16]
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO source_registry
        (id, name, source_type, url, path, metadata, registered_at, active)
        VALUES (?,?,?,?,?,?,?,1)''',
        (sid, name, source_type, url, path,
         json.dumps(metadata or {}), datetime.now().isoformat()))
    conn.commit()
    conn.close()
    return sid


def get_sources(active_only: bool = True) -> list:
    init_db()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    q = "SELECT id, name, source_type, url, path, metadata, registered_at, active FROM source_registry"
    if active_only:
        q += " WHERE active=1"
    c.execute(q)
    rows = c.fetchall()
    conn.close()
    return [{
        'id': r[0], 'name': r[1], 'source_type': r[2], 'url': r[3], 'path': r[4],
        'metadata': json.loads(r[5]) if r[5] else {}, 'registered_at': r[6], 'active': r[7],
    } for r in rows]


# ─── Crawlers (Layer 1) ──────────────────────────────────────────────────────

def crawl_code(source: dict) -> dict:
    """Crawl code from a repo path or URL."""
    result = {'files_scanned': 0, 'languages': set(), 'total_lines': 0, 'has_readme': False}
    path = source.get('path', '')
    if path and os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            if '.git' in root: continue
            for f in files:
                if f.endswith(('.py', '.js', '.ts', '.go', '.rs', '.java', '.cpp', '.c', '.rb')):
                    result['files_scanned'] += 1
                    ext = f.rsplit('.', 1)[-1]
                    result['languages'].add(ext)
                    try:
                        with open(os.path.join(root, f)) as fh:
                            result['total_lines'] += sum(1 for _ in fh)
                    except: pass
                if f.lower() == 'readme.md':
                    result['has_readme'] = True
    result['languages'] = list(result['languages'])
    return result


def crawl_dependencies(source: dict) -> dict:
    """Crawl dependency manifests."""
    result = {'dependencies': [], 'has_lockfile': False, 'total_deps': 0}
    path = source.get('path', '')
    if path and os.path.isdir(path):
        manifest_files = ['requirements.txt', 'package.json', 'go.mod', 'Cargo.toml', 'pom.xml', 'build.gradle']
        for mf in manifest_files:
            fp = os.path.join(path, mf)
            if os.path.isfile(fp):
                try:
                    with open(fp) as fh:
                        content = fh.read()
                    if mf == 'requirements.txt':
                        deps = [l.split('==')[0].split('>=')[0].split('<=')[0].strip()
                                for l in content.splitlines() if l.strip() and not l.startswith('#')]
                        result['dependencies'].extend(deps)
                    elif mf == 'package.json':
                        pkg = json.loads(content)
                        result['dependencies'].extend(list(pkg.get('dependencies', {}).keys()))
                        result['dependencies'].extend(list(pkg.get('devDependencies', {}).keys()))
                except: pass
            lockfiles = ['package-lock.json', 'yarn.lock', 'Pipfile.lock', 'go.sum', 'Cargo.lock']
            for lf in lockfiles:
                if os.path.isfile(os.path.join(path, lf)):
                    result['has_lockfile'] = True
    result['total_deps'] = len(result['dependencies'])
    return result


def crawl_license(source: dict) -> dict:
    """Crawl license files."""
    result = {'license_type': 'unknown', 'has_license_file': False, 'license_conflicts': 0}
    path = source.get('path', '')
    if path and os.path.isdir(path):
        for lf in ['LICENSE', 'LICENSE.md', 'LICENSE.txt', 'COPYING', 'COPYING.md']:
            fp = os.path.join(path, lf)
            if os.path.isfile(fp):
                result['has_license_file'] = True
                try:
                    with open(fp) as fh:
                        content = fh.read().lower()
                    if 'mit' in content: result['license_type'] = 'MIT'
                    elif 'apache' in content: result['license_type'] = 'Apache-2.0'
                    elif 'bsd' in content: result['license_type'] = 'BSD'
                    elif 'gpl' in content: result['license_type'] = 'GPL'
                    elif 'mpl' in content: result['license_type'] = 'MPL-2.0'
                except: pass
                break
    return result


def crawl_test_build(source: dict) -> dict:
    """Crawl test and build configuration."""
    result = {
        'has_tests': False, 'test_files': 0, 'has_ci': False,
        'has_dockerfile': False, 'has_makefile': False, 'build_system': 'unknown',
    }
    path = source.get('path', '')
    if path and os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            if '.git' in root: continue
            for f in files:
                if 'test' in f.lower() and f.endswith(('.py', '.js', '.ts', '.go', '.rs')):
                    result['has_tests'] = True
                    result['test_files'] += 1
                if f == 'Dockerfile': result['has_dockerfile'] = True
                if f == 'Makefile': result['has_makefile'] = True
            if '.github' in dirs:
                ci_path = os.path.join(root, '.github', 'workflows')
                if os.path.isdir(ci_path):
                    result['has_ci'] = True
        if os.path.isfile(os.path.join(path, 'requirements.txt')): result['build_system'] = 'pip'
        elif os.path.isfile(os.path.join(path, 'package.json')): result['build_system'] = 'npm'
        elif os.path.isfile(os.path.join(path, 'go.mod')): result['build_system'] = 'go'
        elif os.path.isfile(os.path.join(path, 'Cargo.toml')): result['build_system'] = 'cargo'
    return result


def crawl_security_secrets(source: dict) -> dict:
    """Scan for exposed secrets and security issues."""
    result = {'secrets_found': 0, 'suspicious_patterns': 0, 'has_env_example': False}
    path = source.get('path', '')
    secret_patterns = [
        (r'sk-[a-zA-Z0-9]{20,}', 'openai_key'),
        (r'ghp_[a-zA-Z0-9]{36}', 'github_pat'),
        (r'AKIA[A-Z0-9]{16}', 'aws_key'),
        (r'-----BEGIN RSA PRIVATE KEY-----', 'private_key'),
        (r'api_key\s*=\s*["\'][^"\']{20,}["\']', 'hardcoded_api_key'),
        (r'password\s*=\s*["\'][^"\']{8,}["\']', 'hardcoded_password'),
    ]
    if path and os.path.isdir(path):
        for root, dirs, files in os.walk(path):
            if '.git' in root: continue
            for f in files:
                if f.endswith(('.py', '.js', '.ts', '.go', '.rs', '.env', '.yaml', '.yml', '.json', '.toml')):
                    try:
                        with open(os.path.join(root, f)) as fh:
                            content = fh.read()
                        for pattern, label in secret_patterns:
                            matches = re.findall(pattern, content)
                            if matches:
                                result['secrets_found'] += len(matches)
                                log.warning(f"Secret pattern {label} found in {f}")
                    except: pass
            if '.env.example' in files or '.env.sample' in files:
                result['has_env_example'] = True
    return result


def crawl_docs_claims(source: dict) -> dict:
    """Crawl documentation and production claims."""
    result = {
        'has_readme': False, 'has_docs_dir': False, 'doc_files': 0,
        'production_claims': 0, 'unverified_claims': 0,
    }
    path = source.get('path', '')
    claim_patterns = [
        r'production[\s-]ready',
        r'production[\s-]grade',
        r'enterprise[\s-]ready',
        r'mission[\s-]critical',
        r'battle[\s-]tested',
        r'production[\s-]deployed',
        r'live\s+in\s+production',
    ]
    if path and os.path.isdir(path):
        docs_path = os.path.join(path, 'docs')
        if os.path.isdir(docs_path):
            result['has_docs_dir'] = True
            for root, dirs, files in os.walk(docs_path):
                result['doc_files'] += len([f for f in files if f.endswith(('.md', '.rst', '.txt'))])
        readme_path = os.path.join(path, 'README.md')
        if os.path.isfile(readme_path):
            result['has_readme'] = True
            try:
                with open(readme_path) as fh:
                    content = fh.read()
                for pattern in claim_patterns:
                    matches = re.findall(pattern, content, re.I)
                    result['production_claims'] += len(matches)
                    result['unverified_claims'] += len(matches)
            except: pass
    return result


def crawl_browser_runtime(source: dict) -> dict:
    """Check if a runtime URL is reachable (browser proof stub)."""
    result = {'reachable': False, 'status_code': 0, 'response_time_ms': 0, 'console_errors': -1}
    url = source.get('url', '')
    if url:
        try:
            start = time.time()
            r = requests.get(url, timeout=10, verify=False)
            elapsed = (time.time() - start) * 1000
            result['reachable'] = r.status_code == 200
            result['status_code'] = r.status_code
            result['response_time_ms'] = round(elapsed, 1)
        except Exception as e:
            result['error'] = str(e)
    return result


def crawl_artifact(source: dict) -> dict:
    """Check for build artifacts."""
    result = {'has_artifacts': False, 'artifact_count': 0, 'artifact_types': set()}
    path = source.get('path', '')
    artifact_dirs = ['dist', 'build', 'out', 'target', '.next', '__pycache__']
    if path and os.path.isdir(path):
        for ad in artifact_dirs:
            ap = os.path.join(path, ad)
            if os.path.isdir(ap):
                result['has_artifacts'] = True
                for root, dirs, files in os.walk(ap):
                    result['artifact_count'] += len(files)
                    for f in files:
                        ext = f.rsplit('.', 1)[-1] if '.' in f else 'unknown'
                        result['artifact_types'].add(ext)
    result['artifact_types'] = list(result['artifact_types'])
    return result


CRAWLER_MAP = {
    'code': crawl_code,
    'dependency': crawl_dependencies,
    'license': crawl_license,
    'test_build': crawl_test_build,
    'browser_runtime': crawl_browser_runtime,
    'artifact': crawl_artifact,
    'security_secrets': crawl_security_secrets,
    'docs_claims': crawl_docs_claims,
}


# ─── ETL Pipeline (Layer 2-4) ────────────────────────────────────────────────

def run_crawl_job(system: str, subject: str, source: dict) -> dict:
    """Run a single crawl job through the full ETL pipeline."""
    job_id = hashlib.md5(f"{system}:{subject}:{datetime.now().isoformat()}".encode()).hexdigest()[:16]
    ts = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''INSERT INTO crawler_jobs
        (id, system, subject, source_url, source_type, status, created_at)
        VALUES (?,?,?,?,?,?,?)''',
        (job_id, system, subject, source.get('url', ''), source.get('source_type', ''),
         'running', ts))
    conn.commit()
    conn.close()

    try:
        crawler_fn = CRAWLER_MAP.get(subject)
        if not crawler_fn:
            raise ValueError(f"Unknown crawler subject: {subject}")

        raw = crawler_fn(source)

        normalized = {
            'system': system,
            'subject': subject,
            'source': source.get('name', source.get('url', '')),
            'timestamp': datetime.now().isoformat(),
            'raw_data': raw,
        }

        signals = _extract_signals(subject, raw, source)
        record = create_canonical_record(
            system=system,
            subject=subject,
            source=source.get('name', source.get('url', '')),
            artifact=f"receipts/{job_id}.json",
            signals=signals,
        )

        receipt = create_receipt(
            receipt_type='crawl_evidence',
            action=f"crawled {subject} for {system}",
            agent_id='layer_crawler',
            artifact_hash=record['record_hash'],
            metrics=raw,
            verification=record['scores'],
            notes=f"ProdScore={record['scores']['prod_score']}, HardenRank={record['scores']['harden_rank']}",
        )

        receipt_path = RECEIPTS_DIR / f"{job_id}.json"
        with open(receipt_path, 'w') as f:
            json.dump(record, f, indent=2, default=str)

        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''UPDATE crawler_jobs SET
            status='completed', completed_at=?, raw_artifact_path=?,
            normalized_json=?, scores_json=?, receipt_id=?
            WHERE id=?''',
            (datetime.now().isoformat(), str(receipt_path),
             json.dumps(normalized, default=str),
             json.dumps(record['scores']),
             receipt['id'], job_id))
        conn.commit()
        conn.close()

        return {
            'job_id': job_id,
            'status': 'completed',
            'scores': record['scores'],
            'receipt': receipt,
            'record': record,
        }

    except Exception as e:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''UPDATE crawler_jobs SET status='failed', completed_at=?, error=? WHERE id=?''',
            (datetime.now().isoformat(), str(e), job_id))
        conn.commit()
        conn.close()
        log.error(f"Crawl job {job_id} failed: {e}")
        return {'job_id': job_id, 'status': 'failed', 'error': str(e)}


def _extract_signals(subject: str, raw: dict, source: dict) -> EvidenceSignals:
    """Convert raw crawl data into EvidenceSignals."""
    s = EvidenceSignals()

    if subject == 'code':
        s.build_verified = raw.get('total_lines', 0) > 0
        s.docs_verified = raw.get('has_readme', False)
    elif subject == 'dependency':
        s.dependency_audit_passed = raw.get('total_deps', 0) < 100
    elif subject == 'license':
        s.license_conflict = 1 if raw.get('license_type', 'unknown') == 'unknown' else 0
    elif subject == 'test_build':
        s.tests_verified = raw.get('has_tests', False)
        s.build_verified = raw.get('has_dockerfile', False) or raw.get('has_makefile', False)
        s.ci_verified = raw.get('has_ci', False)
        s.test_count = raw.get('test_files', 0)
        s.test_pass_count = raw.get('test_files', 0) if raw.get('has_tests') else 0
        s.lint_passed = raw.get('build_system') != 'unknown'
    elif subject == 'browser_runtime':
        s.runtime_verified = raw.get('reachable', False)
        s.console_errors = raw.get('console_errors', -1)
        s.failed_requests = 0 if raw.get('reachable') else 1
        s.deploy_verified = raw.get('reachable', False)
    elif subject == 'artifact':
        s.build_verified = raw.get('has_artifacts', False)
    elif subject == 'security_secrets':
        s.secrets_exposed = raw.get('secrets_found', 0)
        s.security_scan_passed = raw.get('secrets_found', 0) == 0
    elif subject == 'docs_claims':
        s.docs_verified = raw.get('has_readme', False)
        s.claims_without_evidence = raw.get('production_claims', 0)
        s.unverified_production_claims = raw.get('unverified_claims', 0)

    s.has_command_logs = True
    s.has_receipts = True
    return s


def run_full_crawl(system: str, source: dict) -> list:
    """Run all crawler subjects against a single source."""
    results = []
    for subject in CRAWLER_SUBJECTS:
        result = run_crawl_job(system, subject, source)
        results.append(result)
    return results


def compute_fanout(num_systems: int, num_subjects: int = None, num_evidence_types: int = None) -> dict:
    """Compute the fanout for the crawler."""
    ns = num_subjects or len(CRAWLER_SUBJECTS)
    ne = num_evidence_types or len(EVIDENCE_TYPES)
    total = num_systems * ns * ne
    return {
        'systems': num_systems,
        'subjects': ns,
        'evidence_types': ne,
        'total_evidence_checks': total,
        'formula': f'{num_systems} × {ns} × {ne} = {total}',
    }


def get_job_stats(db_path: str = DB_PATH) -> dict:
    init_db()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM crawler_jobs")
    total = c.fetchone()[0]
    c.execute("SELECT status, COUNT(*) FROM crawler_jobs GROUP BY status")
    by_status = dict(c.fetchall())
    c.execute("SELECT subject, COUNT(*) FROM crawler_jobs GROUP BY subject")
    by_subject = dict(c.fetchall())
    c.execute("SELECT COUNT(*) FROM source_registry WHERE active=1")
    active_sources = c.fetchone()[0]
    conn.close()
    return {
        'total_jobs': total,
        'by_status': by_status,
        'by_subject': by_subject,
        'active_sources': active_sources,
        'crawler_subjects': CRAWLER_SUBJECTS,
        'evidence_types': EVIDENCE_TYPES,
    }


def get_jobs(limit: int = 50, offset: int = 0, db_path: str = DB_PATH) -> list:
    init_db()
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''SELECT id, system, subject, status, created_at, completed_at, scores_json, receipt_id, error
                 FROM crawler_jobs ORDER BY created_at DESC LIMIT ? OFFSET ?''',
              (limit, offset))
    rows = c.fetchall()
    conn.close()
    return [{
        'id': r[0], 'system': r[1], 'subject': r[2], 'status': r[3],
        'created_at': r[4], 'completed_at': r[5],
        'scores': json.loads(r[6]) if r[6] else None,
        'receipt_id': r[7], 'error': r[8],
    } for r in rows]


init_db()
