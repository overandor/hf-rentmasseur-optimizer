# Layer Crawler ETL Engine

A POptimizer-compliant evidence collection and scoring system for software systems.

## Architecture

```
Sources
→ Crawlers
→ Extractors
→ Normalizers
→ Classifiers
→ Evidence Scorers
→ Receipts
→ HardenRank / ProdScore
```

## Layers

### Layer 0: Source Registry
- repos
- docs
- PDFs
- websites
- dashboards
- package manifests
- CI logs
- screenshots
- runtime URLs

### Layer 1: Subject Crawlers
- code crawler
- dependency crawler
- license crawler
- test/build crawler
- browser runtime crawler
- artifact crawler
- security/secrets crawler
- docs/claims crawler
- huggingface assessor
- endpoint assessor
- github assessor

### Layer 2: ETL
- **Extract**: pull files, metadata, logs, pages, screenshots
- **Transform**: normalize into common schema
- **Load**: write JSONL/Parquet receipts into evidence lake

### Layer 3: Scoring
- EvidenceScore
- RealityPenalty
- ProdScore
- HardenRank
- IPRisk
- RuntimeRisk

### Layer 4: Action
- recommend hardening
- block fake production claims
- generate Devin tasks

## Canonical Record

```json
{
  "system": "Membra Desktop Operator 2",
  "subject": "runtime",
  "source": "puppeteer",
  "timestamp": "...",
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
  }
}
```

## Usage

### Basic Pipeline with Code Crawler

```python
import asyncio
from pathlib import Path
from layer_crawler_etl import (
    ETLPipeline,
    Source,
    SubjectType,
    CodeCrawler,
    BrowserRuntimeCrawler
)

async def main():
    pipeline = ETLPipeline(Path("receipts"))
    pipeline.register_crawler(SubjectType.CODE, CodeCrawler())
    pipeline.register_crawler(SubjectType.BROWSER_RUNTIME, BrowserRuntimeCrawler())
    
    sources = [
        Source(type="repo", location=".", metadata={"name": "my-project"}),
    ]
    
    receipt = await pipeline.run(sources, system="My System")
    print(f"ProdScore: {receipt.scores['prod_score']}")

asyncio.run(main())
```

### HuggingFace Space Assessment

```python
import asyncio
import os
from layer_crawler_etl import HuggingFaceAssessor

async def main():
    token = os.environ.get("HF_TOKEN")
    assessor = HuggingFaceAssessor(token=token)
    
    # Assess a single space
    result = await assessor.assess_space("gradio/titan-mlm-demo")
    print(f"Status: {result.status}")
    print(f"Verified: {result.verified}")
    print(f"Latency: {result.latency_ms:.0f}ms")
    
    # Batch assess multiple spaces
    spaces = ["gradio/titan-mlm-demo", "stabilityai/stable-diffusion-3-medium"]
    results = await assessor.batch_assess(spaces)
    for r in results:
        print(f"{r.space_id}: {r.status}")

asyncio.run(main())
```

### General Endpoint Assessment

```python
import asyncio
from layer_crawler_etl import EndpointAssessor, EndpointType

async def main():
    assessor = EndpointAssessor()
    
    # Assess REST endpoint
    result = await assessor.assess("https://api.github.com")
    print(f"Type: {result.endpoint_type.value}")
    print(f"Status: {result.status}")
    print(f"Latency: {result.latency_ms:.0f}ms")
    print(f"Verified: {result.verified}")
    
    # Assess GraphQL endpoint
    graphql_result = await assessor.assess("https://api.example.com/graphql")
    print(f"GraphQL Schema Valid: {graphql_result.schema_valid}")
    
    # Batch assess
    endpoints = [
        "https://httpbin.org/get",
        "https://jsonplaceholder.typicode.com/posts/1"
    ]
    results = await assessor.batch_assess(endpoints)

asyncio.run(main())
```

### GitHub Repository Assessment

```python
import asyncio
import os
from layer_crawler_etl import GitHubAssessor

async def main():
    token = os.environ.get("GITHUB_TOKEN")
    assessor = GitHubAssessor(token=token)
    
    # Assess a single repo
    result = await assessor.assess_repo("facebook/react")
    print(f"Stars: {result.stars}")
    print(f"Forks: {result.forks}")
    print(f"Has README: {result.has_readme}")
    print(f"Has License: {result.has_license}")
    print(f"Has Tests: {result.has_tests}")
    print(f"Has CI: {result.has_ci}")
    
    # Batch assess multiple repos
    repos = ["facebook/react", "tensorflow/tensorflow", "openai/openai-python"]
    results = await assessor.batch_assess(repos)
    for r in results:
        print(f"{r.repo}: {r.stars} stars, verified={r.verified}")

asyncio.run(main())
```

## Scoring Model

### EvidenceScore
Weighted sum of verified signals:
- build_verified: +25
- tests_verified: +25
- runtime_verified: +25
- console_errors == 0: +10
- failed_requests == 0: +10
- secrets_exposed == 0: +5

### RealityPenalty
Penalty for missing or failed evidence:
- !build_verified: +30
- !tests_verified: +20
- !runtime_verified: +20
- console_errors: +2 each
- failed_requests: +5 each
- secrets_exposed: +50 each

### ProdScore
```
ProdScore = EvidenceScore - RealityPenalty
```

### IPRisk
- secrets_exposed > 0: +100
- license_conflict > 0: +50

## Hard Rule

**No receipt → no production claim.**

## Integration with Skills

The Layer Crawler ETL Engine integrates with the Membra ChatGPT Export Skill Pack:

- `provenance_to_collateral_auditor` - evaluates evidence quality
- `compute_memory_continuity_underwriter` - converts state to underwriting criteria
- `proofbook_integration_planner` - plans auditable evidence storage
- `receipt_ledger_designer` - designs signed receipts
- `github_underwriting_extractor` - extracts underwriting inputs

## POptimizer Compliance

This system follows the POptimizer formula:

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
