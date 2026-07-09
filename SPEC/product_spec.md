# HyperFlow Ledger OS — Product Spec

## Definition

HyperFlow Ledger OS is a repo-centered multi-agent development control plane that routes intent through ChatGPT, implementation through Codex/Claude/Windsurf, platform verification through Xcode, and converts every code change into an auditable receipt.

## Problem

Using multiple AI coding tools (ChatGPT, Claude, Codex, Windsurf, Xcode) creates:
- Lost work across tools
- Duplicated context
- Hallucinated claims without evidence
- No portable work state
- No auditable build evidence

## Solution

One repository, one task ledger, one artifact format, one test receipt, many agents.

The repo is the memory, judge, and ledger.

## Core Primitive

```
Intent → Spec → Patch → Build → Test → Receipt → Commit → Next Intent
```

## Value Propositions

1. **Multi-agent continuity** — Work state survives across tools and sessions.
2. **Less duplicated context** — All agents read the same repo files.
3. **Fewer hallucinated claims** — Receipts require evidence.
4. **Portable work state** — Repo is the state, not the chat window.
5. **Auditable build evidence** — Every change has a receipt.
6. **Repo-backed valuation** — Receipts become financeable evidence.
7. **Repeatable production loop** — Same pipeline every time.

## Success Criteria

- A user can start a task in ChatGPT, have Codex implement it, Claude review it, Windsurf integrate it, Xcode build it, and GitHub store the receipt — all reading from the same repo.
- No agent claims success without a verifiable receipt.
- The task ledger tracks all work state.
- Any new agent can join the flow by reading AGENTS.md.
