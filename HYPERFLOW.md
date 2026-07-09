# ONE HYPER FLOW

## Purpose

Coordinate ChatGPT, Claude, Codex, Windsurf, and Xcode as one repo-backed production system.

## Roles

### ChatGPT
- Converts messy intent into architecture, specs, acceptance criteria, valuation logic, and task decomposition.
- Reviews receipts and decides the next highest-value task.

### Claude
- Handles long-context reasoning, refactors, documentation restructuring, and architecture critique.
- Must not bypass tests or invent repo state.

### Codex
- Generates focused patches from task instructions.
- Must produce minimal diffs and preserve tests.

### Windsurf
- Operates locally across the repo.
- Applies edits, navigates files, resolves integration problems, and maintains AGENTS.md compliance.

### Xcode
- Builds iOS/macOS targets.
- Runs simulator tests, signing checks, profiling, Instruments, and archive validation.

### GitHub
- Source of truth.
- Stores issues, commits, pull requests, tags, releases, and receipts.

## Canonical Pipeline

```
Intent → Spec → Task → Patch → Build → Test → Receipt → Commit → Release candidate
```

## Operational Loop

```
ChatGPT writes the spec.
Claude attacks the spec.
ChatGPT converts critique into tasks.
Codex patches one task.
Windsurf integrates locally.
Xcode proves build/test.
Receipt is committed.
ChatGPT reads receipt and assigns next task.
```

## Connection Topology

```
                ChatGPT (strategist)
                   │
                   ▼
            GitHub Issue / Task Ledger
                   │
          ┌────────┼────────┐
          ▼        ▼        ▼
     Claude      Codex    Windsurf
    (review)   (patch)  (integrate)
          │        │        │
          └────────┼────────┘
                   ▼
               Xcode (build/test/sign)
                   │
                   ▼
            Receipt + Commit
                   │
                   ▼
            ChatGPT (review → next task)
```

## Key Principle

Do not connect the models to each other first. Connect all of them to the same artifact ledger.

The repo is the memory, judge, and ledger.
