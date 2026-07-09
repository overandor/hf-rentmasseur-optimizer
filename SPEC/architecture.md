# HyperFlow Ledger OS — Architecture

## Overview

```
ChatGPT (strategist) → GitHub (ledger) → Claude/Codex/Windsurf (workers) → Xcode (verifier) → Receipt (evidence)
```

## Components

### 1. AGENTS.md (Master Control)
Every agent reads this first. Defines roles, rules, pipeline, file structure.

### 2. HYPERFLOW.md (Architecture)
Defines the canonical pipeline, connection topology, and operational loop.

### 3. TASK_LEDGER.md (Task Tracking)
Single source of truth for what needs to be done. Status: TODO → ACTIVE → DONE/FAILED.

### 4. SPEC/ (Specifications)
- product_spec.md — What we're building and why
- architecture.md — This file
- api_contract.md — Interface contracts between components
- acceptance_tests.md — What counts as done

### 5. RECEIPTS/ (Evidence)
Every state-changing action produces a receipt with:
- Task ID, agent, date, repo, branch, commit
- Files changed, commands run, results
- Pass/fail, evidence, known limitations, next task

### 6. scripts/ (Automation)
- build.sh — Build the project
- test.sh — Run tests
- lint.sh — Lint code
- receipt.sh — Generate a receipt

### 7. mcp/ (MCP Bridges)
Windsurf MCP tool servers for:
- Task ledger access
- Receipt creation
- Build status queries

### 8. ci/ (GitHub Actions)
CI pipeline that runs build, test, lint, and receipt validation on every push/PR.

## Data Flow

```
User intent
    │
    ▼
ChatGPT: SPEC/ + TASK_LEDGER.md entry
    │
    ▼
Claude: Review spec, identify risks
    │
    ▼
Codex: Pick task, implement, run tests, write diff
    │
    ▼
Windsurf: Apply diff, resolve integration, run local build
    │
    ▼
Xcode: xcodebuild build + test + archive
    │
    ▼
RECEIPTS/: Build/test/lint results
    │
    ▼
GitHub: Commit + PR + receipt artifact
    │
    ▼
ChatGPT: Review receipt, assign next task
```

## Security Model

- **Least privilege**: Each agent gets minimum needed access
- **Repo isolation**: Agents work in branches/worktrees
- **Receipt requirement**: No output counts without evidence
- **No universal freedom**: No agent gets all secrets, all shells, all repos
