# MCP Oracle 3-Head Hydra

## Purpose

Prevent Devin session timeout, shutdown, stall, or context loss from stopping software production. Devin is a disposable worker head, not the durable control plane. Durable state lives in Git, task files, receipt logs, build logs, and MCP-accessible resources.

## Core Principle

No AI session is trusted as the source of truth.

Source of truth:
1. Git commit history
2. Current branch/worktree diff
3. Task packet
4. Verification logs
5. Receipt ledger
6. Build/test results
7. Human-approved merge or release

## Three Heads

### Head A — Seer (Oracle)
Reads state, summarizes, predicts next failure, chooses route.

### Head B — Striker (Worker)
Applies code changes through Devin/Codex/Windsurf.

### Head C — Judge (Verifier)
Runs tests, audits diff, signs receipt, rejects unsupported success.

## Loop

```
Seer reads → Striker acts → Judge verifies → Seer reroutes
```

## State Classification

| Color | Condition | Action |
|-------|-----------|--------|
| GREEN | Worker active, verifiable progress | Continue, snapshot diff |
| YELLOW | Changes made, no verification | Run tests, request verification |
| ORANGE | Stalled, looping, drifting | Pause, snapshot, audit |
| RED | Broke build, edited forbidden files | Revoke lock, revert, relaunch |
| BLACK | Provider/session failure | Switch worker head |

## Timeout Strategy

12-minute checkpoint rhythm:

- Minute 0: launch worker
- Minute 8: request progress summary
- Minute 10: snapshot Git diff and logs
- Minute 12: write checkpoint receipt
- Minute 14: prepare relaunch packet
- Minute 15+: continue from durable state

## Worker Lock

Only one worker may write to a worktree at a time.

Lock file: `RUNS/<task_id>/lock.json`

## Relaunch Rule

When a worker drops, relaunch with exact continuation packet — never from scratch.

## Non-Negotiable Rules

1. Devin is not durable memory.
2. Chat history is not production evidence.
3. All durable state must be written to repo files or receipts.
4. No worker can claim success without verification.
5. Only one worker may write to a worktree at once.
6. Timeouts must be expected, not treated as exceptional.
7. Relaunch must continue from receipt, not from memory.
8. Broad refactors require explicit approval.
9. Xcode is the truth gate for Apple builds.
10. Git is the source of production history.
