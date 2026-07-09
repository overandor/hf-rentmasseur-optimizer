# API Contract — HyperFlow Ledger OS

## File-Based Contracts

All agent communication happens through files in the repo. No direct agent-to-agent messaging.

### Task Packet Format (tasks/TASK-XXXX.md)

```markdown
# TASK-XXXX — Title
Spec: SPEC/product_spec.md#section
Acceptance:
- Criterion 1
- Criterion 2
Agent: [Codex | Claude | Windsurf]
Constraints:
- No new dependencies
- Preserve existing tests
```

### Receipt Format (RECEIPTS/*/TASK-XXXX.md)

```markdown
Task ID: TASK-XXXX
Agent: [agent name]
Date: ISO 8601
Repo: [path]
Branch: [branch]
Commit: [hash]
Objective: [description]
Files changed: [list]
Commands run: [commands]
Results: Build/Tests/Lint PASS|FAIL
Pass/fail: [PASS|FAIL|PARTIAL]
Evidence: [paths]
Known limitations: [caveats]
Next recommended task: [TASK-XXXX or description]
```

### Task Ledger Entry Format (TASK_LEDGER.md)

```markdown
## TASK-XXXX — Title
Status: [TODO|ACTIVE|BLOCKED|DONE|FAILED_VERIFIED]
Owner: [agent]
Goal: [one line]
Acceptance: [criteria]
Evidence required: [artifacts]
```

## Script Contracts

### scripts/build.sh
- Input: None (uses repo state)
- Output: Exit code 0=success, non-zero=failure
- Side effect: Creates build artifacts

### scripts/test.sh
- Input: None
- Output: Exit code 0=pass, non-zero=fail
- Side effect: Creates test results

### scripts/lint.sh
- Input: None
- Output: Exit code 0=clean, non-zero=violations
- Side effect: None

## MCP Bridge Contract (mcp/hyperflow_bridge.py)

### Tools exposed:
- `get_task_ledger` — Return current TASK_LEDGER.md contents
- `get_next_task` — Return next TODO task
- `create_receipt` — Write a receipt file
- `get_latest_receipts` — Return latest receipts
- `run_build` — Execute scripts/build.sh
- `run_tests` — Execute scripts/test.sh
