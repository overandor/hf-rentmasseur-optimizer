# Acceptance Tests — HyperFlow Ledger OS

## Test 1: Control Plane Initialization
- **Given**: A fresh repo
- **When**: AGENTS.md, HYPERFLOW.md, TASK_LEDGER.md, SPEC/, RECEIPTS/ are created
- **Then**: All files exist and contain meaningful content
- **Verify**: `test -f AGENTS.md && test -f HYPERFLOW.md && test -f TASK_LEDGER.md`

## Test 2: Task Ledger Round-Trip
- **Given**: A TODO task in TASK_LEDGER.md
- **When**: An agent picks the task, implements it, writes a receipt
- **Then**: Task status changes to DONE, receipt exists in RECEIPTS/
- **Verify**: `grep "Status: DONE" TASK_LEDGER.md && ls RECEIPTS/*/TASK-*.md`

## Test 3: Receipt Evidence Requirement
- **Given**: An agent claims a task is complete
- **When**: Checking for evidence
- **Then**: Receipt must contain files changed, commands run, and pass/fail result
- **Verify**: Receipt file contains all required fields

## Test 4: Build Gate
- **Given**: Code changes in src/
- **When**: `scripts/build.sh` is executed
- **Then**: Exit code 0 means build passed, non-zero means failed
- **Verify**: `scripts/build.sh; echo $?`

## Test 5: Test Gate
- **Given**: Code changes in src/ or tests/
- **When**: `scripts/test.sh` is executed
- **Then**: Exit code 0 means tests passed, non-zero means failed
- **Verify**: `scripts/test.sh; echo $?`

## Test 6: No Receipt = No Claim
- **Given**: An agent produces output
- **When**: No receipt file exists
- **Then**: The output is not considered valid
- **Verify**: Every DONE task in TASK_LEDGER.md has a corresponding receipt

## Test 7: Agent Role Compliance
- **Given**: An agent starts work
- **When**: It reads AGENTS.md
- **Then**: It follows its role-specific instructions
- **Verify**: ChatGPT produces specs, Codex produces patches, Claude produces reviews, Windsurf integrates, Xcode builds

## Test 8: Xcode Build Authority
- **Given**: iOS/macOS code changes
- **When**: `xcodebuild` is run
- **Then**: Xcode output is the court of truth — no agent can override it
- **Verify**: `xcodebuild -scheme APP_SCHEME -destination 'platform=iOS Simulator,name=iPhone 16' build`
