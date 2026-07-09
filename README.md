---
title: HyperFlow Ledger OS
emoji: ⚡
colorFrom: purple
colorTo: blue
sdk: docker
app_file: app.py
pinned: false
license: mit
---

# HyperFlow Ledger OS

> **One repo-centered hyper-flow connecting ChatGPT, Claude, Codex, Windsurf, and Xcode into a single production loop.**

A multi-agent production ledger that converts AI-assisted work into auditable, reusable, financeable software artifacts.

## The Primitive

```
Many AI agents, one repo, one task ledger, one artifact registry, one build truth.
```

## Pipeline

```
Intent → Spec → Task → Patch → Build → Test → Receipt → Commit → Release candidate
```

## Agent Roles

| Agent | Role |
|-------|------|
| ChatGPT | Strategist / spec compiler / reviewer |
| Claude | Long-context refactorer / architecture critic |
| Codex | Patch generator / test-driven implementer |
| Windsurf | IDE-native repo operator / integrator |
| Xcode | Apple build/test/sign authority |
| GitHub | Source of truth / evidence archive |

## State Machine

```
RAW_IDEA → SPECIFIED → PLANNED → PATCHED → BUILT → TESTED → AUDITED → COMMITTED → PACKAGED → VALUED → SOLD
```

## Hydra Anti-Timeout

Devin is a disposable 15-minute burst worker inside a persistent production ledger. The watchdog snapshots state every 12 minutes and generates relaunch packets when workers drop.

- `scripts/hydra_watchdog.py` — checks tasks, snapshots state, generates relaunch packets
- `scripts/devin_relaunch.py` — generates continuation prompt from task/receipt/git state
- `scripts/verify.sh` — runs build/test/lint
- `scripts/xcode_verify.sh` — Xcode build/test/signing verification

## CLI

```bash
python3 hyperflow/hyperflow_cli.py new "Build MVP"
python3 hyperflow/hyperflow_cli.py list
python3 hyperflow/hyperflow_cli.py assign HF-0001 claude
python3 hyperflow/hyperflow_cli.py build HF-0001
python3 hyperflow/hyperflow_cli.py test HF-0001
python3 hyperflow/hyperflow_cli.py status
```

## Key Principle

Do not connect the models to each other first. Connect all of them to the same artifact ledger. The repo is the memory, judge, and ledger.

---

## Legacy: Email Crawler Dashboard & Computational Capital Infrastructure

Dual-job email collection pipeline with real-time dashboard, plus computational capital valuation and underwriting infrastructure.

### Email Crawler

A comprehensive 4-layer crawler, ETL, scoring, and action engine for verifying software systems with receipts and audit trails. Deployed on Hugging Face Spaces.

### Features
- **2 simultaneous crawl jobs** running in parallel threads
- **Real-time WebSocket dashboard** with live stats and logs
- **Micro-dossier per email**: name, title, organization, location, phone, category
- **Response likelihood scoring** (0-100) based on heuristics
- **Clustering** by organization domain
- **SQLite storage** with JSON/CSV export

### Categories
- IP Lawyers (patent, trademark, copyright)
- M&A Lawyers (corporate, transactional)
- Hedge Funds
- Private Equity Firms
- Venture Capital Firms
- Tech Transfer Offices (universities)
- IP Brokers & Marketplaces
- IP Valuation Firms
- Investment Banks

## Layer Crawler ETL Engine

A POptimizer-style evidence layer sits above the crawler:

```text
Sources
→ Crawlers
→ Extractors
→ Normalizers
→ Classifiers
→ Evidence Scorers
→ Receipts
→ HardenRank / ProdScore
```

### Layers

1. **Source Registry** — `crawler_webapp.py`, `requirements.txt`, `README.md`, `Dockerfile`, SQLite DB, runtime endpoint.
2. **Subject Crawlers** — code, dependency, license, test/build, browser runtime, artifact, security/secrets, docs/claims.
3. **ETL** — extract files and probes, transform into a canonical `signals` schema, load JSON receipts under `receipts/`.
4. **Scoring** — `EvidenceScore`, `RealityPenalty`, `ProdScore`, `HardenRank`, `IPRisk`, `RuntimeRisk`.
5. **Action** — hardening recommendations. No receipt → no production claim.

### API

- `POST /api/etl/run` — run a full audit and write receipts.
- `GET /api/etl/receipts` — list all stored receipts.
- `GET /api/etl/run/latest` — latest aggregate run.
- `GET /api/etl/score` — aggregate scores + hardening actions.

The dashboard renders a **Receipts & Hardening** panel showing Evidence, ProdScore, HardenRank, and IP Risk.

### Canonical Receipt

```json
{
  "system": "Email Crawler Dashboard",
  "subject": "runtime",
  "source": "http_probe",
  "timestamp": "...",
  "artifact": "receipts/runtime-proof.json",
  "signals": {
    "build_verified": true,
    "tests_verified": false,
    "runtime_verified": true,
    "console_errors": null,
    "failed_requests": null,
    "secrets_exposed": 0,
    "license_conflict": 0
  },
  "scores": {
    "evidence": 82,
    "reality_penalty": 12,
    "prod_score": 70,
    "ip_risk": 0
  }
}
```
POptimizer-compliant evidence collection and scoring system for software systems.

### Architecture
```
Sources → Crawlers → Extractors → Normalizers → Classifiers → Evidence Scorers → Receipts → HardenRank / ProdScore
```

### Components
- **Code Crawler** - Analyzes repo structure, tests, build files
- **Dependency Crawler** - Scans dependency manifests for risk
- **License Crawler** - Checks for license information and conflicts
- **Test/Build Crawler** - Runs tests and builds to verify they pass
- **Security/Secrets Crawler** - Scans for exposed API keys and secrets
- **Docs/Claims Crawler** - Extracts claims from documentation
- **Browser Runtime Crawler** - Verifies runtime behavior, console errors, failed requests

### Scoring
- **EvidenceScore** - Weighted sum of verified signals
- **RealityPenalty** - Penalty for missing or failed evidence
- **ProdScore** - EvidenceScore minus RealityPenalty
- **IPRisk** - Risk of proprietary leakage

**Hard Rule:** No receipt → no production claim.

See [layer_crawler_etl/README.md](layer_crawler_etl/README.md) for details.

## Skills Integration

Integration of Membra ChatGPT Export Skills with the codebase for computational capital underwriting.

### Components

#### Underwriting Pipeline
Full underwriting pipeline: `intake → collect → value → benchmark → risk → eligibility → decide → memo`

- GitHub activity scoring
- Financial metrics (ARR/MRR, IP assignment)
- Compute memory continuity scoring
- Risk grade assignment (A-E)
- Borrowing base calculation

#### Compute Capital Valuation
Values machines as: `hardware + recoverable utility - reconstruction cost`

- Hardware depreciation calculation
- Recoverable state utility scoring
- Reconstruction cost estimation
- Productivity multiplier calculation

**Thesis:** A machine with accumulated productive state is worth more than resale value because it reduces future compute requirements.

#### ProofBook Integration
Plans and implements auditable evidence storage for underwriting decisions.

- SHA-256 content hashing
- Proof chain creation and verification
- Chain integrity validation

**Sequence:**
1. Hash and record underwriting memos
2. Attach signed reuse receipts from memory or compute runs
3. Feed receipts into node valuation model
4. Rerun underwriting pipeline with real proof, not claims

See [skills_integration/README.md](skills_integration/README.md) for details.

## Membra ChatGPT Export Skills

Skill pack extracted from ChatGPT exports containing reusable agent skills.

### Skills Included
- `chat_export_distiller` - turns raw ChatGPT export into compressed asset map
- `provenance_to_collateral_auditor` - checks if chat/code/history can become underwriting evidence
- `gateio_trading_system_auditor` - audits Gate.io trading systems
- `trading_code_appraiser` - appraises code value conservatively
- `compute_memory_continuity_underwriter` - converts memory/state reuse into underwriting criteria
- `receipt_ledger_designer` - designs signed receipts and tamper-evident ledgers
- `github_underwriting_extractor` - turns GitHub work into credit-screen inputs
- `proofbook_integration_planner` - plans how outputs become auditable ProofBook evidence
- `solana_devnet_token_guard` - keeps receipt-token work devnet/localnet only
- `conversation_to_product_spec_compiler` - converts repeated chat themes into buildable products

See [membra_chatgpt_export_skills/INDEX.md](membra_chatgpt_export_skills/INDEX.md) for details.

## POptimizer Compliance

All components follow the POptimizer formula:

```
x* = argmin_x [
  λ₁·latency
+ λ₂·RAM
+ λ₃·CPU
+ λ₄·bundle_size
+ λ₅·dependency_risk
+ λ₆·runtime_risk
+ λ₇·IP_leakage
- λ₈·code_quality
- λ₉·verification_confidence
]
```

Subject to:
- secrets_exposed = 0
- private_code_uploaded = 0
- license_conflict = 0
- tests_required = pass
- destructive_actions = approved
- receipt_created = true

Priority:
1. Security / proprietary protection
2. Correctness
3. Verification
4. RAM reduction
5. Speed improvement
6. Code quality
7. Developer convenience

## Features

- **4-Layer Architecture**: Source Registry → Crawlers → ETL → Scoring → Action
- **Multiple Crawlers**: Code, Dependency, License, Security, Test/Build, Browser Runtime (Playwright)
- **Real Browser Automation**: Uses Playwright for actual runtime verification (no mocks)
- **Underwriting Endpoints**: FEMA (natural hazard), OFAC (sanctions), Plaid (cash flow), Experian (credit)
- **Receipt System**: Canonical JSON receipts for all outputs
- **ProofBook Integration**: Tamper-evident audit trails
- **Queue-Based Processing**: Async job processing with Redis support

## API Endpoints

### Health & Status
- `GET /` - API information
- `GET /health` - Health check
- `GET /stats` - System-wide statistics

### Source Management
- `POST /sources/register` - Register a new source
- `GET /sources` - List all sources
- `GET /sources/{source_id}` - Get specific source

### Crawling
- `POST /crawl` - Crawl a source (synchronous)
- `POST /crawl/submit` - Submit crawl job (async)
- `GET /jobs/{job_id}` - Get job status
- `GET /jobs/stats` - Job queue statistics

### Scoring
- `POST /score` - Score a source based on crawl results

### Underwriting
- `POST /underwrite` - Full underwriting pipeline

### Receipts
- `GET /receipts/{receipt_id}` - Get receipt
- `GET /receipts/source/{source_id}` - Get receipts by source
- `POST /receipts/{receipt_id}/verify` - Verify receipt integrity
- `GET /receipts/stats` - Receipt statistics

### External APIs
- `POST /sanctions/check` - OFAC sanctions screening
- `POST /fema/risk` - FEMA National Risk Index
- `POST /address/validate` - Address validation (requires Smarty credentials)
- `POST /ocr/extract` - Extract text from images

### ProofBook
- `GET /proofbook/stats` - ProofBook statistics
- `GET /proofbook/chain/{chain_id}` - Get audit chain
- `POST /proofbook/chain/{chain_id}/verify` - Verify chain integrity

## Usage Examples

### Crawl a GitHub Repository

```bash
curl -X POST "https://your-space.hf.space/crawl" \
  -H "Content-Type: application/json" \
  -d '{
    "source_url": "https://github.com/user/repo",
    "source_type": "repo",
    "crawler_types": ["code", "dependency", "license", "security"]
  }'
```

### Check Sanctions

```bash
curl -X POST "https://your-space.hf.space/sanctions/check" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Doe",
    "address": "123 Main St"
  }'
```

### Get FEMA Risk Data

```bash
curl -X POST "https://your-space.hf.space/fema/risk" \
  -H "Content-Type: application/json" \
  -d '{
    "county_fips": "06075"
  }'
```
