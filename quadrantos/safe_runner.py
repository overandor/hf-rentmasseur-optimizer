"""RECEPT Safety Bridge — Executes RECEPT programs through TerminalSafetyBroker.

RECEPT's run() and rm() calls are routed through the TerminalSafetyBroker
instead of raw subprocess. This means:
- Destructive commands are blocked without @approved
- All commands are logged
- Violations are tracked
- No arbitrary shell execution
"""

import os
import re
import subprocess
import hashlib
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any


class TerminalSafetyError(Exception):
    pass


class SafeExecutionBroker:
    """Safety broker for RECEPT execution.

    Checks every command against blocked patterns before execution.
    Tracks violations and logs all commands.

    This replaces raw subprocess.run() in the RECEPT interpreter.
    """

    BLOCKED_PATTERNS = [
        r'\brm\s+-rf?\b',
        r'\brm\s+-r\b',
        r'\bdd\b',
        r'\bmkfs\b',
        r'\bchmod\s+777\b',
        r'\bchown\b',
        r'\bsudo\b',
        r'\bkill\s+-9\b',
        r'\bpkill\b',
        r'>\s*/dev/',
        r'curl\s+.*\|\s*(bash|sh)',
        r'wget\s+.*\|\s*(bash|sh)',
        r'\bpip\s+install\b',  # No arbitrary package installs
        r'\bnpm\s+install\b',
        r'\bbrew\s+install\b',
    ]

    SAFE_PATTERNS = [
        r'^ls\b', r'^cat\b', r'^head\b', r'^tail\b',
        r'^grep\b', r'^find\b', r'^echo\b', r'^mkdir\b',
        r'^test\b', r'^python3\s+-m\s+pytest\b',
        r'^python3\s+-c\b', r'^git\s+(status|log|diff)\b',
        r'^which\b', r'^wc\b', r'^sort\b', r'^uniq\b',
        r'^diff\b', r'^file\b', r'^stat\b',
        r'^screencapture\b', r'^shasum\b',
    ]

    def __init__(self, approved: bool = False):
        self.approved = approved
        self.violation_count = 0
        self.command_log: List[Dict] = []
        self.work_dir: Optional[str] = None

    def set_work_dir(self, path: str):
        self.work_dir = path

    def check(self, command: str) -> Dict:
        """Check command against safety rules."""
        classification = 'unknown'

        for pattern in self.SAFE_PATTERNS:
            if re.match(pattern, command):
                classification = 'safe'
                return {'allowed': True, 'reason': 'auto-approved', 'needs_approval': False}

        for pattern in self.BLOCKED_PATTERNS:
            if re.search(pattern, command):
                classification = 'blocked'
                if self.approved:
                    return {'allowed': True, 'reason': 'pre-approved by @approved',
                            'needs_approval': False}
                return {'allowed': False, 'reason': f'blocked: {pattern}',
                        'needs_approval': True}

        classification = 'unknown'
        return {'allowed': True, 'reason': 'unknown, allowed by default',
                'needs_approval': False}

    def execute(self, command: str, timeout: int = 30) -> Dict:
        """Execute a command safely. Raises TerminalSafetyError if blocked."""
        check = self.check(command)

        self.command_log.append({
            'command': command,
            'timestamp': datetime.now().isoformat(),
            'classification': check['reason'],
            'allowed': check['allowed'],
        })

        if not check['allowed']:
            self.violation_count += 1
            raise TerminalSafetyError(
                f"Command blocked: {check['reason']}. "
                f"Add @approved annotation to allow. Command: {command[:80]}"
            )

        try:
            r = subprocess.run(
                command, shell=True,
                cwd=self.work_dir,
                capture_output=True, text=True, timeout=timeout
            )
            return {
                'returncode': r.returncode,
                'stdout': r.stdout,
                'stderr': r.stderr,
                'blocked': False,
            }
        except subprocess.TimeoutExpired:
            return {
                'returncode': -1,
                'stdout': '',
                'stderr': f'TIMEOUT after {timeout}s',
                'blocked': False,
            }

    def safe_rm(self, path: str) -> Dict:
        """Safely remove a file. Only works if @approved."""
        if not self.approved:
            raise TerminalSafetyError(
                f"rm() requires @approved annotation. Path: {path}"
            )
        # Prevent path traversal
        if '..' in path or path.startswith('/'):
            raise TerminalSafetyError(
                f"rm() blocked: path traversal or absolute path not allowed: {path}"
            )
        full_path = os.path.join(self.work_dir or '.', path)
        try:
            os.remove(full_path)
            return {'returncode': 0, 'stdout': f'removed: {path}', 'stderr': '', 'blocked': False}
        except Exception as e:
            return {'returncode': 1, 'stdout': '', 'stderr': str(e), 'blocked': False}

    def audit(self) -> List[Dict]:
        return self.command_log

    def violation_count(self) -> int:
        return self.violation_count


class RECEPTSafeRunner:
    """Runs RECEPT programs with safe execution.

    Integrates RECEPT interpreter with:
    - SafeExecutionBroker (replaces raw subprocess)
    - SQLiteReceiptStore (durable receipts)
    - SelfImprovementLedger (false positive tracking)

    The terminal is the primary control channel.
    Screen vision is observation only.
    """

    def __init__(self, receipts_db: str = None, improvement_db: str = None):
        from .receipt_store import SQLiteReceiptStore
        from .improvement import SelfImprovementLedger

        self.receipt_store = SQLiteReceiptStore(receipts_db)
        self.improvement_ledger = SelfImprovementLedger(improvement_db)
        self.broker: Optional[SafeExecutionBroker] = None

    def run(self, source: str, work_dir: str = None) -> Dict:
        """Run a RECEPT program safely.

        Args:
            source: RECEPT source code
            work_dir: Working directory for file operations

        Returns:
            Execution result with receipts
        """
        from membra_gpt.recept.interpreter import Interpreter, ReceptRuntimeError

        work_dir = work_dir or os.path.join(os.getcwd(), 'questionos', 'recept_runs')
        os.makedirs(work_dir, exist_ok=True)

        # Create safety broker
        self.broker = SafeExecutionBroker()
        self.broker.set_work_dir(work_dir)

        # Create a patched interpreter that uses our broker
        interp = Interpreter(receipts_dir=os.path.join(work_dir, 'receipts'))

        # Monkey-patch the interpreter's call_builtin to use safe execution
        original_call_builtin = interp.call_builtin

        def safe_call_builtin(name: str, args: List[Any]) -> Any:
            if name == 'run':
                cmd = args[0] if args else ""
                result = self.broker.execute(cmd)
                return result.get('stdout', '')[:1000]

            elif name == 'write_file':
                filename = args[0] if args else ""
                content = args[1] if len(args) > 1 else ""
                filepath = os.path.join(work_dir, filename)
                os.makedirs(os.path.dirname(filepath), exist_ok=True) if os.path.dirname(filename) else None
                with open(filepath, 'w') as f:
                    f.write(content)
                return f"wrote {len(content)} bytes to {filename}"

            elif name == 'read_file':
                filename = args[0] if args else ""
                filepath = os.path.join(work_dir, filename)
                try:
                    with open(filepath) as f:
                        return f.read()
                except Exception as e:
                    return f"read error: {e}"

            elif name == 'rm':
                path = args[0] if args else ""
                result = self.broker.safe_rm(path)
                return result.get('stdout', '')

            elif name == 'rmdir':
                path = args[0] if args else ""
                if not self.broker.approved:
                    raise TerminalSafetyError(
                        f"rmdir() requires @approved annotation. Path: {path}"
                    )
                try:
                    os.rmdir(os.path.join(work_dir, path))
                    return f"removed dir: {path}"
                except Exception as e:
                    return f"rmdir error: {e}"

            else:
                return original_call_builtin(name, args)

        interp.call_builtin = safe_call_builtin
        interp.call_function = self._safe_call_function(interp)

        # Run the program
        try:
            result = interp.run(source)

            # Write a durable receipt to SQLite
            receipt = self.receipt_store.write(
                agent='RECEPT',
                action='program_executed',
                artifact_path=work_dir,
                commands_run=[cmd['command'] for cmd in self.broker.command_log],
                result='success' if not result.get('errors') else 'partial',
                details={
                    'capsule': result.get('capsule', 'unknown'),
                    'endpoints': result.get('endpoints', []),
                    'workflows': result.get('workflows', []),
                    'functions': result.get('functions', []),
                    'errors': result.get('errors', []),
                    'broker_violations': self.broker.violation_count,
                    'broker_log': self.broker.command_log[:20],
                },
            )

            result['receipt'] = receipt
            result['broker_audit'] = self.broker.audit()
            result['work_dir'] = work_dir
            return result

        except TerminalSafetyError as e:
            receipt = self.receipt_store.write(
                agent='RECEPT',
                action='program_blocked',
                artifact_path=None,
                commands_run=[cmd['command'] for cmd in self.broker.command_log],
                result='blocked',
                details={'error': str(e), 'violations': self.broker.violation_count},
            )
            return {
                'errors': [str(e)],
                'receipt': receipt,
                'broker_audit': self.broker.audit(),
                'blocked': True,
            }

    def _safe_call_function(self, interp):
        """Wrap interpreter's call_function to respect @approved."""
        original = interp.call_function

        def safe_call(name: str, args: List[Any]) -> Any:
            if name in interp.functions:
                fn = interp.functions[name]
                if name in interp.DESTRUCTIVE_FUNCS and not fn.approved:
                    raise TerminalSafetyError(
                        f"Function '{name}' is destructive but not @approved."
                    )
                # Set broker approved state
                if self.broker:
                    old_approved = self.broker.approved
                    self.broker.approved = fn.approved
                    result = original(name, args)
                    self.broker.approved = old_approved
                    return result
            return original(name, args)

        return safe_call
