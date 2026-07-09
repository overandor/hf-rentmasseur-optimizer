# Skill: terminal-safety-broker-skill

> **Reusable machinery for intercepting and validating terminal commands.**

## Capabilities

- Check commands against blocked patterns
- Request user approval for dangerous commands
- Log all command executions
- Audit command history for violations

## Interface

```python
class TerminalSafetyBrokerSkill:
    def check(self, command: str) -> dict:
        """Check command against rules. Returns {allowed, reason, needs_approval}."""

    def request_approval(self, command: str, context: str) -> bool:
        """Request user approval for blocked command. Returns True if approved."""

    def execute(self, command: str, cwd: str = None) -> subprocess.CompletedProcess:
        """Execute command if safe. Raises TerminalSafetyError if blocked and unapproved."""

    def audit(self) -> list:
        """Return list of all commands executed this session with classification."""

    def violation_count(self) -> int:
        """Return number of safety violations this session."""
```

## Blocked Patterns

Loaded from `.devin/rules/20-terminal-safety.md`:

| Pattern | Risk |
|---------|------|
| `rm -rf` | Data loss |
| `dd` | Disk corruption |
| `mkfs` | Disk wipe |
| `chmod 777` | Security hole |
| `sudo` | Privilege escalation |
| `curl *\| bash` | Supply chain attack |

## Enforcement

- Wraps `subprocess.run` — all terminal calls go through broker
- Blocked commands raise `TerminalSafetyError` unless pre-approved
- Three violations = session abort
- Every execution logged with: command, cwd, result, timestamp

## Used By

- All workflows that run terminal commands
- `agent_controller.py` (all subprocess calls)
- `terminal-audit` workflow
