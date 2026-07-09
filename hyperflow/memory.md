# HyperFlow Project Memory

## Project: HyperFlow Ledger OS

### What
A repo-centered multi-agent development control plane that routes intent through ChatGPT, implementation through Codex/Claude/Windsurf, platform verification through Xcode, and converts every code change into an auditable receipt.

### Why
Using multiple AI coding tools creates lost work, duplicated context, hallucinated claims, no portable work state, and no auditable build evidence. HyperFlow solves this by making the repo the memory, judge, and ledger.

### How
One repository, one task ledger, one artifact format, one test receipt, many agents.

### Current State
- **HF-0001**: Control plane initialized (AGENTS.md, HYPERFLOW.md, TASK_LEDGER.md, SPEC/, RECEIPTS/, hyperflow/, scripts/, mcp/, ci/)
- **Artifact score**: 4 (verified build)
- **Next**: HF-0002 (acceptance test validation)

### Key Decisions
- File-based contracts, no direct agent-to-agent messaging
- JSONL for machine-readable task/receipt tracking
- Markdown for human-readable specs and receipts
- State machine: RAW_IDEA → SPECIFIED → PLANNED → PATCHED → BUILT → TESTED → AUDITED → COMMITTED → PACKAGED → VALUED → SOLD
- Artifact scoring 0-10 from residue to platform kernel
- Xcode output is court of truth for Apple platforms

### Agent Assignments
- ChatGPT: Spec compiler, valuation, audit
- Claude: Architecture review, refactor planning
- Codex: Bounded patches, test execution
- Windsurf: IDE operation, repo navigation, multi-file edits
- Xcode: Build, sign, simulate, profile, archive
- GitHub: Ledger, commits, PRs, receipt storage
