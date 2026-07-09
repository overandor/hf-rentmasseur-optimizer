# YTL-MCP Research Lab v0.1

> **Local-first MCP-controlled YouTube automation research server.**

Turns YouTube from content guessing into a receipt-backed experimental production system.

## What This Is

A local-first, MCP-controlled YouTube automation research server that lets ChatGPT command a Windsurf-managed codebase to ingest video metadata, analyze transcripts, generate hypotheses, produce scripts/assets, prepare uploads, inspect analytics, run experiments, and issue receipts — without violating platform rules or relying on unverifiable agent memory.

## One-Line Safety Spec

Automate production and measurement, not deception or fake engagement.

## One-Line Product Thesis

Turn YouTube from content guessing into a receipt-backed experimental production system.

## Architecture

```
ChatGPT App (command brain)
    → MCP Client
    → YouTube Lab MCP Server (safe tools)
    → Windsurf Repo (live operator bay)
    → Local/Cloud Workers (execution)
    → YouTube API / Analytics / FFmpeg / Whisper / ML Models
    → Receipt Ledger (evidence)
```

## Core Loop

```
Observe → Hypothesize → Generate → Verify → Publish/Prepare → Measure → Learn → Receipt
```

## Five Layers

1. **Control Layer** — ChatGPT gives intent, asks questions, routes work
2. **Tool Protocol Layer** — MCP exposes bounded, auditable tools
3. **Operator Layer** — Windsurf edits code, runs commands, inspects errors
4. **Execution Layer** — Lab server runs transcripts, scoring, FFmpeg, generation
5. **Evidence Layer** — JSONL receipts, Git commits, experiment configs, metrics

## Three Heads

| Head | Role |
|------|------|
| Research Oracle | Finds patterns, extracts transcripts, scores hooks, creates hypotheses |
| Production Oracle | Generates scripts, shot lists, metadata, thumbnails, editing plans |
| Measurement Oracle | Tracks uploads, analytics, experiment outcomes, revenue/retention deltas |

## MCP Tools (Capability Tiers)

### Tier 0: Read-only
- `ytl_get_lab_status` — server health, queue, channels, quota, errors
- `ytl_list_videos` — list ingested videos
- `ytl_list_experiments` — list experiments
- `ytl_get_receipts` — show receipt stream

### Tier 1: Local generation
- `ytl_ingest_video` — ingest video metadata + transcript
- `ytl_extract_transcript` — extract transcript from local file
- `ytl_score_transcript` — score hook, retention, novelty, density
- `ytl_generate_script` — generate script from hypothesis
- `ytl_generate_metadata` — title variants, description, tags, chapters
- `ytl_generate_shotlist` — shot list and B-roll plan

### Tier 2: Local execution
- `ytl_prepare_upload_package` — create publish-ready folder
- `ytl_run_experiment` — create formal experiment object

### Tier 3: Authorized external API
- `ytl_sync_my_channel` — OAuth-authorized channel sync
- `ytl_sync_analytics` — pull analytics for your channel
- `ytl_measure_experiment` — compare outcome vs baseline

### Tier 4: Publish-affecting (requires confirmation)
- `ytl_upload_draft` — upload as private/unlisted only
- `ytl_git_checkpoint` — commit to Git

## Compliance Boundary

**The lab MAY:**
- Automate your production workflow
- Analyze lawfully available data
- Upload your own authorized content
- Optimize metadata and experiments

**The lab MAY NOT:**
- Fake engagement, views, likes, subscribers
- Mass comment, mass like, mass subscribe
- Scrape private data or bypass access restrictions
- Reupload copyrighted material
- Impersonate humans or deceive
- Bypass platform controls

## Scoring Dimensions

| Dimension | What it measures |
|-----------|-----------------|
| Hook Score | Curiosity, stakes, contradiction, payoff expectation in first 30s |
| Retention Score | State changes, loop opening/closing, visual transitions, dead zones |
| Novelty Score | Non-generic claims, structure, entities, framing |
| Compression Score | Meaning per second |
| Entity Density | Named entities, objects, tools, numbers per minute |
| Payoff Timing | How quickly audience gets useful/surprising resolution |
| Visualizability | How easily each segment becomes a shot/diagram/animation |
| Policy Risk | Copyright, medical/legal/financial claims, misinformation |
| Reuse Value | Whether transcript/assets can become clips, articles, shorts |
| Machine-Consumability | Parseable by models, search, recommendation systems |

## MVP Roadmap

| MVP | Features |
|-----|----------|
| MVP 1 | MCP server, ingest 1 video, score transcript, generate 5 titles, 1 script, 1 package, receipt |
| MVP 2 | OAuth, analytics sync, experiment table, private upload |
| MVP 3 | Batch transcripts, model scoring, thumbnails, Shorts, dashboard |
| MVP 4 | GitHub CI, receipt verification, research reports |
| MVP 5 | Revenue attribution, sellable rights packages |

## Commands

```bash
make install      # Install dependencies
make db-init      # Initialize SQLite database
make mcp          # Start MCP server
make verify       # Run tests + lint
make dashboard    # Start dashboard
make receipt      # Show latest receipts
```

## File Structure

```
ytl-mcp-lab/
├── README.md              ← You are here
├── HYPERFLOW.md           ← Lab rules and constraints
├── AGENTS.md              ← Agent role definitions
├── POLICY.md              ← Compliance policy
├── COMPLIANCE.md          ← YouTube API compliance
├── Makefile               # Build/run commands
├── .env.example           # Config template
├── pyproject.toml         # Python dependencies
├── server/                # MCP server
│   ├── mcp_server.py      # Main MCP server
│   └── tools/             # Tool implementations
├── workers/               # Background workers
├── models/                # Scoring models
├── data/                  # Local data store
├── experiments/           # Experiment tracking
├── receipts/              # JSONL receipt ledger
├── dashboard/             # Web dashboard
├── scripts/               # Setup and utility scripts
└── tests/                 # Test suite
```
