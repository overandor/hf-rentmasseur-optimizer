# Layer Crawler ETL Engine

A comprehensive 4-layer crawler, ETL, scoring, and action engine for verifying software systems with receipts and audit trails.

## Architecture

```
Layer 0: Source Registry
  ├─ Repos
  ├─ Docs
  ├─ PDFs
  ├─ Websites
  ├─ Dashboards
  ├─ Package manifests
  ├─ CI logs
  ├─ Screenshots
  └─ Runtime URLs

Layer 1: Subject Crawlers
  ├─ Code Crawler
  ├─ Dependency Crawler
  ├─ License Crawler
  ├─ Security/Secrets Crawler
  ├─ Test/Build Crawler
  └─ Browser Runtime Crawler

Layer 2: ETL
  ├─ Extract: Pull raw data from crawlers
  ├─ Transform: Normalize to common schema
  └─ Load: Store in evidence lake (JSONL/Parquet)

Layer 3: Scoring
  ├─ EvidenceScore (0-100)
  ├─ RealityPenalty (0-100)
  ├─ ProdScore (evidence - penalty)
  ├─ HardenRank (hardening needed)
  ├─ IPRisk (0-100)
  └─ RuntimeRisk (0-100)

Layer 4: Action
  ├─ Recommend hardening
  ├─ Block fake production claims
  └─ Generate Devin tasks
```

## Canonical Receipt Format

```json
{
  "receipt_id": "rcpt_20250115_143022_abc12345",
  "receipt_type": "crawler_evidence",
  "system": "Layer Crawler ETL Engine",
  "subject": "runtime",
  "source": "puppeteer",
  "timestamp": "2025-01-15T14:30:22Z",
  "completed_at": "2025-01-15T14:30:25Z",
  "artifact": "receipts/runtime-proof.png",
  "signals": {
    "build_verified": true,
    "tests_verified": true,
    "runtime_verified": true,
    "console_errors": 0,
    "failed_requests": 0,
    "secrets_exposed": 0,
    "license_conflict": 0
  },
  "scores": {
    "evidence": 82,
    "reality_penalty": 12,
    "prod_score": 70,
    "ip_risk": 0
  },
  "verification_status": "verified",
  "verification_timestamp": "2025-01-15T14:30:26Z",
  "signature": null,
  "metadata": {}
}
```

## Usage

### Basic Crawling

```python
from layer_crawler_etl import SourceRegistry, CodeCrawler

# Register a source
registry = SourceRegistry()
source = registry.register_github_repo("https://github.com/user/repo", "my-repo")

# Crawl the source
crawler = CodeCrawler()
result = await crawler.crawl(source)
```

### Full Pipeline

```python
from layer_crawler_etl import (
    SourceRegistry, CrawlerWorker, JobQueue, QueueBackend
)

# Initialize components
registry = SourceRegistry()
job_queue = JobQueue(backend=QueueBackend.MEMORY)
worker = CrawlerWorker(job_queue, registry)

# Register sources
registry.register_github_repo("https://github.com/user/repo", priority=10)

# Submit jobs
await job_queue.submit_job("source_id", "code", priority=10)

# Run worker
await worker.run_batch(max_jobs=10)
```

### ETL Pipeline

```python
from layer_crawler_etl.layer2_etl import Extractor, Transformer, Loader
from layer_crawler_etl.layer3_scoring import Scorer
from layer_crawler_etl.layer4_action import ActionEngine

# Extract
extractor = Extractor()
extracted = extractor.extract_from_crawl_result(crawl_result)

# Transform
transformer = Transformer()
normalized = transformer.transform(extracted)

# Load
loader = Loader()
load_result = loader.load(normalized)

# Score
scorer = Scorer()
score_result = scorer.score(normalized)

# Generate actions
action_engine = ActionEngine()
actions = action_engine.generate_actions(score_result, normalized.data)
```

### Receipts

```python
from receipts import ReceiptGenerator, ReceiptLedger

generator = ReceiptGenerator("My System")
ledger = ReceiptLedger()

# Generate receipt
receipt = generator.generate_crawler_receipt(
    source_id="source_123",
    crawler_type="code",
    crawl_result=crawl_data,
    score_result=score_data
)

# Add to ledger
ledger.add_receipt(receipt)

# Verify
from receipts import ReceiptVerifier
verifier = ReceiptVerifier()
is_valid = verifier.verify_receipt(receipt)
```

## Underwriting Endpoints

### Plaid (Cash Flow)

```python
from underwriting_endpoints import PlaidClient

client = PlaidClient(client_id="...", secret="...", environment="sandbox")
async with client:
    # Exchange public token
    token_response = await client.exchange_public_token(public_token)
    access_token = token_response.data["access_token"]
    
    # Get transactions
    tx_response = await client.get_transactions(
        access_token,
        start_date="2024-01-01",
        end_date="2024-12-31"
    )
    
    # Parse for underwriting
    cash_flow = client.parse_cash_flow_data(auth_response, tx_response)
```

### FEMA (Natural Hazard Risk)

```python
from underwriting_endpoints import FEMAClient

client = FEMAClient()
async with client:
    # Get risk index by county
    response = await client.get_national_risk_index(county_fips="06075")
    risk_data = client.parse_risk_score(response)
```

### Experian (Business Credit)

```python
from underwriting_endpoints import ExperianClient

client = ExperianClient(api_key="...", environment="sandbox")
async with client:
    # Get business profile
    profile = await client.get_business_profile(business_name="Acme Corp")
    
    # Get credit score
    credit = await client.get_credit_score(business_id="...")
    
    # Parse for underwriting
    credit_data = client.parse_business_credit_data(profile, credit)
```

### OFAC (Sanctions Screening)

```python
from underwriting_endpoints import OFACClient, SanctionsComplianceEngine

client = OFACClient()
engine = SanctionsComplianceEngine(client)

# Screen individual
result = await engine.screen_individual(
    name="John Doe",
    address="123 Main St"
)

# Screen business
result = await engine.screen_business(
    business_name="Acme Corp"
)
```

## ProofBook Integration

```python
from proofbook_integration import UnderwritingProofBook

proofbook = UnderwritingProofBook()

# Create underwriting chain
chain_id = proofbook.create_underwriting_chain(source_id="source_123")

# Submit memo as proof
proof = proofbook.submit_underwriting_memo(
    source_id="source_123",
    memo=memo_data,
    chain_id=chain_id
)

# Verify chain
is_valid = proofbook.verify_chain(chain_id)
```

## Queue Architecture

The system supports multiple queue backends:

- **MEMORY**: In-memory queue for local development
- **REDIS**: Redis-based distributed queue
- **SQS**: AWS SQS for cloud deployment (TODO)

```python
from layer_crawler_etl.queue_workers import JobQueue, QueueBackend

# Memory queue (default)
queue = JobQueue(backend=QueueBackend.MEMORY)

# Redis queue
queue = JobQueue(backend=QueueBackend.REDIS, redis_url="redis://localhost:6379")
```

## Membra Skills Integration

The system includes 10 skills extracted from ChatGPT exports:

- `chat_export_distiller` - Turn raw ChatGPT export into intelligence assets
- `provenance_to_collateral_auditor` - Evaluate if work can become underwriting evidence
- `gateio_trading_system_auditor` - Audit Gate.io trading systems
- `trading_code_appraiser` - Appraise code value conservatively
- `compute_memory_continuity_underwriter` - Convert memory reuse into underwriting criteria
- `receipt_ledger_designer` - Design signed receipts and ledgers
- `github_underwriting_extractor` - Extract underwriting inputs from GitHub
- `proofbook_integration_planner` - Plan how outputs become auditable evidence
- `solana_devnet_token_guard` - Keep receipt-token work devnet-only
- `conversation_to_product_spec_compiler` - Convert chat themes into buildable products

## POptimizer Integration

The system follows POptimizer principles:

- **Security > Correctness > Verification > RAM > Speed > Quality > Convenience**
- No secrets exposure
- No private code upload
- No license conflicts
- Every artifact gets a receipt
- Claims must be backed by evidence

## Project Structure

```
layer_crawler_etl/
├── layer0_source_registry/    # Source registration and management
├── layer1_crawlers/           # Crawlers for different subjects
├── layer2_etl/                # Extract, Transform, Load pipeline
├── layer3_scoring/            # Evidence and risk scoring
├── layer4_action/             # Hardening recommendations and actions
├── queue_workers/             # Job queue and worker processes
├── storage/                   # Raw and normalized data storage
underwriting_endpoints/        # External API clients (Plaid, FEMA, etc.)
proofbook_integration/         # ProofBook ledger for audit trails
receipts/                      # Receipt generation and verification
skills/                        # Membra skills from ChatGPT exports
```

## Hard Constraints

The system enforces these hard constraints:

1. `secrets_exposed = 0` - No secrets may be exposed
2. `private_code_uploaded = 0` - No private code may be uploaded
3. `license_conflict = 0` - No license conflicts allowed
4. `tests_required = pass` - Required tests must pass
5. `destructive_action = approved` - Destructive actions require approval

## Receipt Generation

Every completed task produces a receipt with:

- timestamp
- repo/branch
- files_changed
- commands_run
- verification_result
- ΔSpeed
- ΔRAM
- ΔQuality
- IP risk
- verification confidence
