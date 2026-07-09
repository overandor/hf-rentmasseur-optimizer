# Workflow: terminal-audit

> **Audit terminal commands for safety violations.**

## Prerequisites

- `TerminalSafetyBroker` class available in `agent_controller.py`
- Rule file `20-terminal-safety.md` loaded

## Steps

1. **Load blocked patterns**
   - Parse `.devin/rules/20-terminal-safety.md`
   - Extract blocked command patterns from the table
   - Build regex list: `rm -rf`, `dd`, `mkfs`, `chmod 777`, etc.

2. **Scan recent commands**
   - Review all `subprocess.run` calls in the current session
   - For each command, check against blocked patterns

3. **Classify each command**
   - `SAFE` — matches auto-approved list
   - `BLOCKED` — matches blocked list, was it approved?
   - `UNKNOWN` — not in either list, flag for review

4. **Generate report**
   - Count: safe, blocked (approved), blocked (denied), unknown
   - List all blocked commands with approval status
   - List all unknown commands
   - Flag any blocked commands that executed without approval

5. **Check for violations**
   - Any blocked command that executed without approval = VIOLATION
   - Log: `TERMINAL_VIOLATION: <command> executed without approval`
   - Three violations = session abort

6. **Write report**
   - Save to `/tmp/terminal_audit_{timestamp}.md`
   - Write receipt

## Sacred Rule

> No destructive terminal actions without approval.
