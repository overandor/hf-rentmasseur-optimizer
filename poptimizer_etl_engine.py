"""
POptimizer Layer Crawler ETL Engine

Sources -> Crawlers -> Extractors -> Normalizers -> Classifiers -> Evidence Scorers -> Receipts -> HardenRank / ProdScore
"""

import os, re, json, time, hashlib, asyncio, sqlite3, subprocess, traceback
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field, asdict
import httpx
import requests
from bs4 import BeautifulSoup

try:
    from playwright.async_api import async_playwright
    HAS_PLAYWRIGHT = True
except Exception:
    HAS_PLAYWRIGHT = False

# ─── Models ─────────────────────────────────────────────────────────────────

@dataclass
class Source:
    id: str
    type: str  # repo, url, api, docs, package, ci, screenshot, runtime
    path: str
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class RawEvidence:
    source_id: str
    subject: str  # code, dependency, license, test/build, runtime, artifact, security, docs
    extractor: str
    timestamp: str
    artifacts: List[str] = field(default_factory=list)
    signals: Dict[str, Any] = field(default_factory=dict)
    raw_data: Dict[str, Any] = field(default_factory=dict)

@dataclass
class NormalizedEvidence:
    system: str
    subject: str
    source: str
    timestamp: str
    artifact: str
    signals: Dict[str, Any]
    raw_hash: str

@dataclass
class ScoreCard:
    evidence: int = 0
    reality_penalty: int = 0
    prod_score: int = 0
    harden_rank: int = 0
    ip_risk: int = 0
    runtime_risk: int = 0

@dataclass
class Receipt:
    system: str
    subject: str
    source: str
    timestamp: str
    artifact: str
    signals: Dict[str, Any]
    scores: Dict[str, int]
    actions: List[str] = field(default_factory=list)
    receipt_id: str = ""

# ─── Source Registry ──────────────────────────────────────────────────────────

class SourceRegistry:
    def __init__(self):
        self.sources: List[Source] = []

    def register(self, source: Source) -> None:
        self.sources.append(source)

    def by_type(self, type_: str) -> List[Source]:
        return [s for s in self.sources if s.type == type_]

    def all(self) -> List[Source]:
        return self.sources

# ─── Extractors ─────────────────────────────────────────────────────────────

class Extractor(ABC):
    @abstractmethod
    async def extract(self, source: Source) -> List[RawEvidence]:
        pass

class FileSystemExtractor(Extractor):
    SECRET_RE = re.compile(
        r'(hf_[A-Za-z0-9]{20,}|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|'
        r'ghp_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9\-]{20,}|'
        r'private_key|password\s*=|secret\s*=|api_key\s*=|token\s*=)',
        re.I
    )

    async def extract(self, source: Source) -> List[RawEvidence]:
        evidences = []
        base = Path(source.path)
        if not base.exists():
            return evidences

        # Code scan
        code_files = list(base.rglob('*.py')) + list(base.rglob('*.js')) + list(base.rglob('*.ts'))
        total_lines = 0
        for f in code_files:
            try:
                total_lines += len(f.read_text().splitlines())
            except Exception:
                pass

        evidences.append(RawEvidence(
            source_id=source.id,
            subject='code',
            extractor='FileSystemExtractor',
            timestamp=datetime.utcnow().isoformat(),
            signals={'file_count': len(code_files), 'total_lines': total_lines},
            raw_data={'extensions': list(set(f.suffix for f in code_files))}
        ))

        # Dependency scan
        deps = {}
        req = base / 'requirements.txt'
        if req.exists():
            for line in req.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith('#') and not line.startswith('-'):
                    pkg = line.split('==')[0].split('>=')[0].strip()
                    if pkg:
                        deps[pkg] = line
        pkg = base / 'package.json'
        if pkg.exists():
            try:
                pj = json.loads(pkg.read_text())
                deps.update({k: v for k, v in {**pj.get('dependencies', {}), **pj.get('devDependencies', {})}.items()})
            except Exception:
                pass

        evidences.append(RawEvidence(
            source_id=source.id,
            subject='dependency',
            extractor='FileSystemExtractor',
            timestamp=datetime.utcnow().isoformat(),
            signals={'dependency_count': len(deps), 'has_requirements': req.exists(), 'has_package_json': pkg.exists()},
            raw_data={'dependencies': list(deps.keys())[:50]}
        ))

        # License scan
        licenses = list(base.glob('LICENSE*')) + list(base.glob('COPYING*'))
        license_text = licenses[0].read_text()[:2000] if licenses else ''
        has_gpl = 'GPL' in license_text.upper()
        has_mit = 'MIT' in license_text.upper()
        has_apache = 'APACHE' in license_text.upper()

        evidences.append(RawEvidence(
            source_id=source.id,
            subject='license',
            extractor='FileSystemExtractor',
            timestamp=datetime.utcnow().isoformat(),
            signals={'license_found': len(licenses) > 0, 'gpl': has_gpl, 'mit': has_mit, 'apache': has_apache},
            raw_data={'license_snippet': license_text[:500]}
        ))

        # Test/build scan
        tests = list(base.rglob('test_*.py')) + list(base.rglob('*_test.py')) + list(base.rglob('*.test.js'))
        ci = list(base.glob('.github/workflows/*.yml')) + list(base.glob('.github/workflows/*.yaml'))
        dockerfile = (base / 'Dockerfile').exists() or (base / 'docker-compose.yml').exists()
        makefile = (base / 'Makefile').exists()

        evidences.append(RawEvidence(
            source_id=source.id,
            subject='test_build',
            extractor='FileSystemExtractor',
            timestamp=datetime.utcnow().isoformat(),
            signals={
                'test_files': len(tests),
                'ci_files': len(ci),
                'has_docker': dockerfile,
                'has_makefile': makefile
            },
            raw_data={'test_paths': [str(t.relative_to(base)) for t in tests[:10]]}
        ))

        # Security scan
        secrets_found = 0
        secret_files = []
        for f in code_files[:100]:
            try:
                text = f.read_text()
                hits = self.SECRET_RE.findall(text)
                if hits:
                    secrets_found += len(hits)
                    secret_files.append(str(f.relative_to(base)))
            except Exception:
                pass

        evidences.append(RawEvidence(
            source_id=source.id,
            subject='security',
            extractor='FileSystemExtractor',
            timestamp=datetime.utcnow().isoformat(),
            signals={'secrets_exposed': secrets_found, 'secret_files': len(secret_files)},
            raw_data={'secret_file_paths': secret_files[:10]}
        ))

        # Docs scan
        readme = base / 'README.md'
        has_readme = readme.exists()
        readme_len = len(readme.read_text()) if has_readme else 0

        evidences.append(RawEvidence(
            source_id=source.id,
            subject='docs',
            extractor='FileSystemExtractor',
            timestamp=datetime.utcnow().isoformat(),
            signals={'has_readme': has_readme, 'readme_length': readme_len},
            raw_data={'readme_preview': (readme.read_text()[:300] if has_readme else '')}
        ))

        return evidences

class BrowserRuntimeExtractor(Extractor):
    async def extract(self, source: Source) -> List[RawEvidence]:
        if not HAS_PLAYWRIGHT:
            return [RawEvidence(
                source_id=source.id,
                subject='runtime',
                extractor='BrowserRuntimeExtractor',
                timestamp=datetime.utcnow().isoformat(),
                signals={'runtime_verified': False, 'playwright_missing': True, 'console_errors': 0, 'failed_requests': 0},
                raw_data={'error': 'playwright not installed'}
            )]

        url = source.path if source.path.startswith('http') else f"http://{source.path}"
        signals = {'runtime_verified': False, 'console_errors': 0, 'failed_requests': 0}
        artifact = ""
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(viewport={'width': 1280, 'height': 800})
                page = await context.new_page()

                console_errors = []
                failed_requests = []

                page.on('console', lambda msg: console_errors.append(msg.text) if msg.type == 'error' else None)
                page.on('response', lambda resp: failed_requests.append(resp.url) if resp.status >= 400 else None)

                await page.goto(url, wait_until='networkidle', timeout=15000)
                await page.wait_for_timeout(2000)

                signals['runtime_verified'] = True
                signals['console_errors'] = len(console_errors)
                signals['failed_requests'] = len(failed_requests)

                receipt_dir = Path('receipts')
                receipt_dir.mkdir(exist_ok=True)
                artifact = str(receipt_dir / f"runtime_{source.id}_{int(time.time())}.png")
                await page.screenshot(path=artifact)

                await browser.close()
        except Exception as e:
            signals['error'] = str(e)[:200]

        return [RawEvidence(
            source_id=source.id,
            subject='runtime',
            extractor='BrowserRuntimeExtractor',
            timestamp=datetime.utcnow().isoformat(),
            artifacts=[artifact] if artifact else [],
            signals=signals,
            raw_data={'url': url}
        )]

class URLExtractor(Extractor):
    async def extract(self, source: Source) -> List[RawEvidence]:
        url = source.path if source.path.startswith('http') else f"http://{source.path}"
        signals = {'reachable': False, 'status': 0, 'schema_valid': False}
        try:
            r = requests.get(url, timeout=15, headers={'User-Agent': 'POptimizer/1.0'})
            signals['reachable'] = True
            signals['status'] = r.status_code
            signals['schema_valid'] = bool(r.headers.get('content-type', ''))
            soup = BeautifulSoup(r.text, 'html.parser')
            signals['title'] = soup.title.get_text() if soup.title else ''
            signals['page_length'] = len(r.text)
        except Exception as e:
            signals['error'] = str(e)[:200]

        return [RawEvidence(
            source_id=source.id,
            subject='url',
            extractor='URLExtractor',
            timestamp=datetime.utcnow().isoformat(),
            signals=signals,
            raw_data={'url': url}
        )]

# ─── ETL Pipeline ───────────────────────────────────────────────────────────

class ETLPipeline:
    def __init__(self, system_name: str = "poptimizer_etl"):
        self.system = system_name
        self.extractors: List[Extractor] = []
        self.normalized: List[NormalizedEvidence] = []

    def add_extractor(self, extractor: Extractor) -> None:
        self.extractors.append(extractor)

    async def run(self, registry: SourceRegistry) -> List[NormalizedEvidence]:
        raw_all: List[RawEvidence] = []
        for source in registry.all():
            for extractor in self.extractors:
                try:
                    evs = await extractor.extract(source)
                    raw_all.extend(evs)
                except Exception as e:
                    raw_all.append(RawEvidence(
                        source_id=source.id,
                        subject='etl_error',
                        extractor=type(extractor).__name__,
                        timestamp=datetime.utcnow().isoformat(),
                        signals={'error': True},
                        raw_data={'exception': traceback.format_exc()}
                    ))

        normalized = []
        for ev in raw_all:
            payload = json.dumps(asdict(ev), sort_keys=True)
            normalized.append(NormalizedEvidence(
                system=self.system,
                subject=ev.subject,
                source=f"{ev.extractor}/{ev.source_id}",
                timestamp=ev.timestamp,
                artifact=ev.artifacts[0] if ev.artifacts else '',
                signals=ev.signals,
                raw_hash=hashlib.sha256(payload.encode()).hexdigest()[:16]
            ))
        self.normalized = normalized
        return normalized

# ─── Scoring Engine ───────────────────────────────────────────────────────────

class ScoringEngine:
    def score(self, evidence: NormalizedEvidence) -> ScoreCard:
        s = evidence.signals
        card = ScoreCard()

        # Evidence score: presence of verifiable artifacts
        checks = []
        if evidence.subject == 'code':
            checks = [s.get('file_count', 0) > 0, s.get('total_lines', 0) > 0]
        elif evidence.subject == 'dependency':
            checks = [s.get('has_requirements', False) or s.get('has_package_json', False)]
        elif evidence.subject == 'license':
            checks = [s.get('license_found', False)]
        elif evidence.subject == 'test_build':
            checks = [s.get('test_files', 0) > 0, s.get('ci_files', 0) > 0, s.get('has_docker', False)]
        elif evidence.subject == 'runtime':
            checks = [s.get('runtime_verified', False), s.get('console_errors', 999) == 0, s.get('failed_requests', 999) == 0]
        elif evidence.subject == 'security':
            checks = [s.get('secrets_exposed', 999) == 0]
        elif evidence.subject == 'docs':
            checks = [s.get('has_readme', False), s.get('readme_length', 0) > 100]
        elif evidence.subject == 'url':
            checks = [s.get('reachable', False), s.get('status', 0) == 200]

        evidence_hits = sum(1 for c in checks if c)
        evidence_total = len(checks) if checks else 1
        card.evidence = int((evidence_hits / evidence_total) * 100) if evidence_total > 0 else 0

        # Reality penalty: what is missing or wrong
        penalties = []
        if evidence.subject == 'runtime':
            if not s.get('runtime_verified', False):
                penalties.append(30)
            penalties.append(min(s.get('console_errors', 0) * 5, 30))
            penalties.append(min(s.get('failed_requests', 0) * 5, 20))
        if evidence.subject == 'security' and s.get('secrets_exposed', 0) > 0:
            penalties.append(50)
        if evidence.subject == 'license' and s.get('gpl', False) and not s.get('mit', False):
            penalties.append(20)
        if evidence.subject == 'test_build' and s.get('test_files', 0) == 0:
            penalties.append(15)
        if evidence.subject == 'docs' and not s.get('has_readme', False):
            penalties.append(10)

        card.reality_penalty = min(sum(penalties), 100)
        card.prod_score = max(0, card.evidence - card.reality_penalty)

        # HardenRank 1-5
        if card.prod_score >= 80:
            card.harden_rank = 5
        elif card.prod_score >= 60:
            card.harden_rank = 4
        elif card.prod_score >= 40:
            card.harden_rank = 3
        elif card.prod_score >= 20:
            card.harden_rank = 2
        else:
            card.harden_rank = 1

        # IP Risk
        ip_penalties = []
        if evidence.subject == 'security' and s.get('secrets_exposed', 0) > 0:
            ip_penalties.append(80)
        if evidence.subject == 'license':
            if s.get('gpl', False):
                ip_penalties.append(30)
            if not s.get('license_found', False):
                ip_penalties.append(40)
        card.ip_risk = min(sum(ip_penalties), 100)

        # Runtime Risk
        if evidence.subject == 'runtime':
            rr = 0
            if not s.get('runtime_verified', False):
                rr += 50
            rr += min(s.get('console_errors', 0) * 10, 30)
            rr += min(s.get('failed_requests', 0) * 10, 20)
            card.runtime_risk = min(rr, 100)
        elif evidence.subject == 'url':
            if not s.get('reachable', False):
                card.runtime_risk = 60
            elif s.get('status', 200) >= 500:
                card.runtime_risk = 40

        return card

# ─── Receipt Ledger ─────────────────────────────────────────────────────────

class ReceiptLedger:
    def __init__(self, path: str = "receipts/receipts.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db_path = str(self.path.parent / 'scores.db')
        self._init_db()

    def _init_db(self):
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS receipts (
            id TEXT PRIMARY KEY, system TEXT, subject TEXT, source TEXT,
            timestamp TEXT, artifact TEXT, signals TEXT, scores TEXT,
            actions TEXT, created_at TEXT
        )''')
        conn.commit()
        conn.close()

    def write(self, receipt: Receipt) -> str:
        rid = receipt.receipt_id or hashlib.sha256(
            f"{receipt.system}:{receipt.subject}:{receipt.timestamp}".encode()
        ).hexdigest()[:16]
        receipt.receipt_id = rid
        line = json.dumps(asdict(receipt), default=str)
        with open(self.path, 'a') as f:
            f.write(line + '\n')

        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        c.execute('''INSERT OR REPLACE INTO receipts VALUES (?,?,?,?,?,?,?,?,?,?)''',
                    (rid, receipt.system, receipt.subject, receipt.source, receipt.timestamp,
                     receipt.artifact, json.dumps(receipt.signals), json.dumps(receipt.scores),
                     json.dumps(receipt.actions), datetime.utcnow().isoformat()))
        conn.commit()
        conn.close()
        return rid

    def query(self, subject: str = '', min_prod_score: int = 0) -> List[Receipt]:
        conn = sqlite3.connect(self.db_path)
        c = conn.cursor()
        q = "SELECT * FROM receipts WHERE 1=1"
        params = []
        if subject:
            q += " AND subject=?"
            params.append(subject)
        if min_prod_score:
            # scores stored as JSON text; filter in python for simplicity
            pass
        q += " ORDER BY timestamp DESC LIMIT 500"
        c.execute(q, params)
        rows = c.fetchall()
        conn.close()
        results = []
        for r in rows:
            scores = json.loads(r[7])
            if min_prod_score and scores.get('prod_score', 0) < min_prod_score:
                continue
            results.append(Receipt(
                system=r[1], subject=r[2], source=r[3], timestamp=r[4],
                artifact=r[5], signals=json.loads(r[6]), scores=scores,
                actions=json.loads(r[8]), receipt_id=r[0]
            ))
        return results

# ─── Action Engine ──────────────────────────────────────────────────────────

class ActionEngine:
    def recommend(self, evidence: NormalizedEvidence, scores: ScoreCard) -> List[str]:
        actions = []
        s = evidence.signals

        if evidence.subject == 'runtime':
            if not s.get('runtime_verified', False):
                actions.append("runtime: verify service is running and reachable")
            if s.get('console_errors', 0) > 0:
                actions.append(f"runtime: fix {s['console_errors']} console errors")
            if s.get('failed_requests', 0) > 0:
                actions.append(f"runtime: fix {s['failed_requests']} failed requests")

        if evidence.subject == 'security' and s.get('secrets_exposed', 0) > 0:
            actions.append(f"security: rotate exposed secrets in {s.get('secret_files', 0)} files")
            actions.append("security: add pre-commit hooks for secret scanning")

        if evidence.subject == 'test_build':
            if s.get('test_files', 0) == 0:
                actions.append("test_build: add unit tests")
            if s.get('ci_files', 0) == 0:
                actions.append("test_build: add CI workflow (GitHub Actions)")
            if not s.get('has_docker', False):
                actions.append("test_build: add Dockerfile for reproducible builds")

        if evidence.subject == 'license' and not s.get('license_found', False):
            actions.append("license: add LICENSE file")
        if evidence.subject == 'license' and s.get('gpl', False):
            actions.append("license: verify GPL compatibility with downstream users")

        if evidence.subject == 'docs' and not s.get('has_readme', False):
            actions.append("docs: add README with setup instructions")

        if scores.prod_score < 50:
            actions.append("general: raise evidence quality before production claim")
        if scores.ip_risk > 0:
            actions.append("general: resolve IP/security risks before release")

        return actions

# ─── Main Orchestrator ──────────────────────────────────────────────────────

class POptimizerETL:
    def __init__(self, system_name: str = "Membra Desktop Operator"):
        self.system = system_name
        self.registry = SourceRegistry()
        self.etl = ETLPipeline(system_name)
        self.scorer = ScoringEngine()
        self.ledger = ReceiptLedger()
        self.actioner = ActionEngine()
        self._setup_extractors()

    def _setup_extractors(self):
        self.etl.add_extractor(FileSystemExtractor())
        self.etl.add_extractor(URLExtractor())
        if HAS_PLAYWRIGHT:
            self.etl.add_extractor(BrowserRuntimeExtractor())

    def register_source(self, id_: str, type_: str, path: str, meta: Optional[Dict] = None):
        self.registry.register(Source(id=id_, type=type_, path=path, metadata=meta or {}))

    async def run_all(self) -> List[Receipt]:
        normalized = await self.etl.run(self.registry)
        receipts = []
        for ev in normalized:
            scores = self.scorer.score(ev)
            actions = self.actioner.recommend(ev, scores)
            receipt = Receipt(
                system=self.system,
                subject=ev.subject,
                source=ev.source,
                timestamp=ev.timestamp,
                artifact=ev.artifact,
                signals=ev.signals,
                scores=asdict(scores),
                actions=actions
            )
            self.ledger.write(receipt)
            receipts.append(receipt)
        return receipts

    def get_receipts(self, subject: str = '', min_prod_score: int = 0) -> List[Receipt]:
        return self.ledger.query(subject=subject, min_prod_score=min_prod_score)

# ─── FastAPI Router Factory ─────────────────────────────────────────────────

def make_router(etl: POptimizerETL):
    from fastapi import APIRouter, Query
    from fastapi.responses import JSONResponse

    router = APIRouter(prefix="/poptimizer", tags=["poptimizer"])

    @router.post("/source")
    async def add_source(id: str, type: str, path: str):
        etl.register_source(id, type, path)
        return {"registered": True, "id": id, "type": type, "path": path}

    @router.post("/run")
    async def run_etl():
        receipts = await etl.run_all()
        return {
            "receipts_written": len(receipts),
            "subjects": list(set(r.subject for r in receipts)),
            "avg_prod_score": sum(r.scores['prod_score'] for r in receipts) / max(len(receipts), 1)
        }

    @router.get("/receipts")
    async def list_receipts(subject: str = Query(''), min_prod_score: int = Query(0)):
        rows = etl.get_receipts(subject=subject, min_prod_score=min_prod_score)
        return [asdict(r) for r in rows]

    @router.get("/scores/summary")
    async def scores_summary():
        rows = etl.get_receipts()
        if not rows:
            return {"receipts": 0}
        return {
            "receipts": len(rows),
            "avg_evidence": sum(r.scores['evidence'] for r in rows) / len(rows),
            "avg_reality_penalty": sum(r.scores['reality_penalty'] for r in rows) / len(rows),
            "avg_prod_score": sum(r.scores['prod_score'] for r in rows) / len(rows),
            "avg_ip_risk": sum(r.scores['ip_risk'] for r in rows) / len(rows),
            "avg_runtime_risk": sum(r.scores['runtime_risk'] for r in rows) / len(rows),
            "lowest_prod_score": min(r.scores['prod_score'] for r in rows),
            "highest_harden_rank": max(r.scores['harden_rank'] for r in rows),
            "actions_required": sum(len(r.actions) for r in rows),
        }

    return router
