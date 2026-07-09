# HYDRA — Anti-Timeout Nervous System

## Definition

MCP Oracle 3-Head Hydra = anti-timeout nervous system for AI software workers.

It does not need Devin to be immortal. It makes Devin replaceable.

## Architecture

```
MCP Oracle 3-Head Hydra
    → Devin / Windsurf / Codex / Claude / ChatGPT
    → Git Worktree
    → Build/Test Gate
    → Receipt Ledger
    → Relaunch / Continue / Escalate
```

## Worker Routing

| Situation | Route to |
|-----------|----------|
| Architecture uncertainty | Claude |
| Spec compression | ChatGPT |
| Bounded code patch | Codex |
| Interactive repo editing | Windsurf |
| Autonomous cloud task | Devin |
| Apple compile truth | Xcode |
| Ledger truth | Git/GitHub |

## Failover Chain

```
Devin dies → Codex continues from diff
Codex makes bad patch → Windsurf inspects
Windsurf drifts → Claude audits
Claude over-theorizes → Xcode/test gate rejects
All pass → Git commits → GitHub PR
```

## Windsurf Role

Windsurf is the human-visible override cockpit:
- Inspect diff
- Repair stuck state
- Accept/reject edits
- Run local commands
- Open Xcode
- Manually intervene when Hydra cannot resolve ambiguity

**Windsurf is cockpit. Git is memory. MCP is nervous system. Oracle is decision function. Devin is worker. Xcode is truth gate.**

## Control Formula

```
Next Action = argmax(Expected Progress − Risk − Cost − Drift)
```

## Checkpoint Rhythm (12-minute cycle)

| Minute | Action |
|--------|--------|
| 0 | Launch worker with scoped prompt |
| 8 | Request progress summary |
| 10 | Force receipt write + snapshot Git diff |
| 12 | Write checkpoint receipt |
| 14 | Prepare relaunch packet if no progress |
| 15+ | No loss — state already exists outside worker |
