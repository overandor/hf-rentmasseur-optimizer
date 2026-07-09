"""QRC Engine — Question Runtime Capsule.

When a serious question enters the terminal system, it becomes a private executable session.
The session may create files, run commands, scrape allowed sources, compute, compress notes,
build datasets, create endpoints, write receipts, and update private memory.

The user sees the useful service. Internally, we keep the proof that the question caused work.

Question → Runtime Session → Receipts → Compressed Dataset → Private Endpoint → Better Future Response
"""

import os
import json
import hashlib
import uuid
import subprocess
import time
import re
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field

from .ledgers import QuestionLedger, ExecutionLedger, CostAvoidanceLedger


# Intent classification — determines what tools the session gets
INTENT_KEYWORDS = {
    'research': ['what', 'why', 'how does', 'explain', 'compare', 'difference', 'overview'],
    'engineering': ['build', 'create', 'implement', 'fix', 'refactor', 'add', 'generate', 'write code'],
    'data': ['dataset', 'scrape', 'collect', 'analyze', 'pca', 'statistics', 'aggregate', 'transform'],
    'deployment': ['deploy', 'endpoint', 'api', 'serve', 'docker', 'container', 'cloud'],
    'debugging': ['debug', 'error', 'crash', 'traceback', 'fail', 'broken', 'why is'],
    'summarization': ['summarize', 'compress', 'tldr', 'digest', 'condense'],
}

# Cost avoidance estimates per intent class
COST_AVOIDANCE_ESTIMATES = {
    'research': {'category': 'research', 'hours': 2.0, 'confidence': 0.6},
    'engineering': {'category': 'engineering', 'hours': 4.0, 'confidence': 0.5},
    'data': {'category': 'data_building', 'hours': 3.0, 'confidence': 0.55},
    'deployment': {'category': 'engineering', 'hours': 1.5, 'confidence': 0.5},
    'debugging': {'category': 'debugging', 'hours': 2.5, 'confidence': 0.65},
    'summarization': {'category': 'explanation', 'hours': 0.5, 'confidence': 0.7},
}


@dataclass
class SessionState:
    """State of a QRC session — the semantic tmux."""
    session_id: str = ""
    question_id: str = ""
    question_hash: str = ""
    question_text: str = ""
    intent_class: str = "unknown"
    project: str = "default"
    started_at: str = ""
    ended_at: Optional[str] = None
    status: str = "init"  # init, running, compressing, done, failed
    work_dir: str = ""
    tmux_session: Optional[str] = None
    commands_run: List[str] = field(default_factory=list)
    files_created: List[str] = field(default_factory=list)
    tests_passed: Optional[bool] = None
    endpoint_url: Optional[str] = None
    receipts: List[str] = field(default_factory=list)
    compressed: bool = False
    compressed_path: Optional[str] = None
    dataset_path: Optional[str] = None
    runtime_seconds: float = 0.0
    errors: List[str] = field(default_factory=list)


class QRCEngine:
    """Question Runtime Capsule Engine.

    The core daemon that turns questions into executable sessions.

    Usage:
        engine = QRCEngine()
        session = engine.ask("How do I optimize my FastAPI endpoint?", project="myapp")
        # session is now a running capsule with receipts
        engine.compress(session)  # Compress residue into reusable dataset
        engine.serve(session)     # Start private endpoint serving the dataset
    """

    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or os.path.join(os.getcwd(), 'questionos')
        self.sessions_dir = os.path.join(self.base_dir, 'sessions')
        self.datasets_dir = os.path.join(self.base_dir, 'datasets')
        self.receipts_dir = os.path.join(self.base_dir, 'receipts')

        for d in [self.sessions_dir, self.datasets_dir, self.receipts_dir]:
            os.makedirs(d, exist_ok=True)

        # Three ledgers
        self.question_ledger = QuestionLedger(
            os.path.join(self.base_dir, 'ledgers', 'questions.json'))
        self.execution_ledger = ExecutionLedger(
            os.path.join(self.base_dir, 'ledgers', 'executions.json'))
        self.cost_ledger = CostAvoidanceLedger(
            os.path.join(self.base_dir, 'ledgers', 'cost_avoidance.json'))

        # Active sessions
        self._sessions: Dict[str, SessionState] = {}
        self._last_receipt_id: Optional[str] = None

    def classify_intent(self, question: str) -> str:
        """Classify the question's intent to determine available tools."""
        q_lower = question.lower()
        scores = {}
        for intent, keywords in INTENT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw in q_lower)
            if score > 0:
                scores[intent] = score
        if not scores:
            return 'research'
        return max(scores, key=scores.get)

    def ask(self, question: str, project: str = None,
            access_policy: str = 'private') -> SessionState:
        """Ask a question. This starts a QRC session.

        The question becomes a private executable session that:
        1. Records the question hash in the Question Ledger
        2. Creates a work directory for the session
        3. Spawns a tmux session for terminal work
        4. Records cost-avoidance estimate
        5. Returns the session state for further operations

        Args:
            question: The question to execute
            project: Project name for grouping
            access_policy: 'private', 'nda', or 'public'

        Returns:
            SessionState — the live session capsule
        """
        # Classify intent
        intent = self.classify_intent(question)

        # Record in Question Ledger
        q_record = self.question_ledger.record(
            question=question,
            project=project or 'default',
            intent_class=intent,
            access_policy=access_policy,
        )

        # Create session
        session_id = str(uuid.uuid4())
        session_dir = os.path.join(self.sessions_dir, session_id)
        os.makedirs(session_dir, exist_ok=True)

        state = SessionState(
            session_id=session_id,
            question_id=q_record['question_id'],
            question_hash=q_record['question_hash'],
            question_text=question,
            intent_class=intent,
            project=project or 'default',
            started_at=datetime.now().isoformat(),
            status='running',
            work_dir=session_dir,
        )

        # Link session to question
        self.question_ledger.link_session(q_record['question_id'], session_id)

        # Write question to session dir (private)
        with open(os.path.join(session_dir, 'question.txt'), 'w') as f:
            f.write(question)

        # Write session metadata
        self._save_session_state(state)

        # Record execution event
        self.execution_ledger.record(
            session_id=session_id,
            question_id=q_record['question_id'],
            event_type='session_start',
            details={'intent': intent, 'project': state.project},
        )

        # Record cost avoidance estimate
        est = COST_AVOIDANCE_ESTIMATES.get(intent, {'category': 'research', 'hours': 1.0, 'confidence': 0.4})
        self.cost_ledger.record(
            question_id=q_record['question_id'],
            session_id=session_id,
            work_category=est['category'],
            hours_avoided=est['hours'],
            confidence=est['confidence'],
            basis=f'Intent class "{intent}" — estimated {est["hours"]}h of {est["category"]} work avoided',
        )

        # Write initial receipt
        self._write_receipt(state, 'question_received', {
            'question_hash': state.question_hash,
            'intent': intent,
            'project': state.project,
        })

        self._sessions[session_id] = state
        return state

    def run_command(self, session: SessionState, command: str,
                    timeout: int = 30, approved: bool = False) -> Dict:
        """Run a command inside the session's work directory.

        Destructive commands require approved=True.
        """
        destructive = any(p in command for p in ['rm -rf', 'dd', 'mkfs', 'chmod 777', 'sudo', '> /dev/'])

        if destructive and not approved:
            result = {
                'command': command,
                'returncode': -1,
                'stdout': '',
                'stderr': 'BLOCKED: destructive command requires approved=True',
                'blocked': True,
            }
            session.errors.append(f'Blocked command: {command}')
            self.execution_ledger.record(
                session_id=session.session_id,
                question_id=session.question_id,
                event_type='command_blocked',
                details={'command': command},
                result='failure',
            )
            return result

        try:
            r = subprocess.run(
                command, shell=True, cwd=session.work_dir,
                capture_output=True, text=True, timeout=timeout,
            )
            result = {
                'command': command,
                'returncode': r.returncode,
                'stdout': r.stdout[:5000],
                'stderr': r.stderr[:2000],
                'blocked': False,
            }
            session.commands_run.append(command)

            self.execution_ledger.record(
                session_id=session.session_id,
                question_id=session.question_id,
                event_type='command',
                details={'command': command, 'returncode': r.returncode},
                result='success' if r.returncode == 0 else 'failure',
            )

            self._write_receipt(session, 'command_executed', {
                'command': command,
                'returncode': r.returncode,
                'stdout_hash': hashlib.sha256(r.stdout.encode()).hexdigest()[:16],
            })

            return result

        except subprocess.TimeoutExpired:
            result = {
                'command': command,
                'returncode': -1,
                'stdout': '',
                'stderr': f'TIMEOUT after {timeout}s',
                'blocked': False,
            }
            session.errors.append(f'Timeout: {command}')
            self.execution_ledger.record(
                session_id=session.session_id,
                question_id=session.question_id,
                event_type='command_timeout',
                details={'command': command, 'timeout': timeout},
                result='failure',
            )
            return result

    def write_file(self, session: SessionState, filename: str, content: str) -> str:
        """Write a file in the session's work directory."""
        filepath = os.path.join(session.work_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True) if os.path.dirname(filename) else None
        with open(filepath, 'w') as f:
            f.write(content)

        file_hash = hashlib.sha256(content.encode()).hexdigest()
        session.files_created.append(filename)

        self.execution_ledger.record(
            session_id=session.session_id,
            question_id=session.question_id,
            event_type='file_write',
            details={'filename': filename, 'hash': file_hash, 'bytes': len(content)},
        )

        self._write_receipt(session, 'file_written', {
            'filename': filename,
            'hash': file_hash,
            'bytes': len(content),
        })

        return filepath

    def run_tests(self, session: SessionState) -> Dict:
        """Run pytest in the session directory if test files exist."""
        test_files = [f for f in os.listdir(session.work_dir)
                      if f.startswith('test_') and f.endswith('.py')]

        if not test_files:
            return {'ran': False, 'reason': 'no test files'}

        result = self.run_command(session, 'python3 -m pytest -v --tb=short', timeout=60)
        session.tests_passed = result['returncode'] == 0

        self.execution_ledger.record(
            session_id=session.session_id,
            question_id=session.question_id,
            event_type='test',
            details={'passed': session.tests_passed, 'output_hash': hashlib.sha256(result['stdout'].encode()).hexdigest()[:16]},
            result='success' if session.tests_passed else 'failure',
        )

        return {'ran': True, 'passed': session.tests_passed, 'output': result['stdout'][:2000]}

    def compress(self, session: SessionState) -> Dict:
        """Compress the session into a reusable dataset.

        Not pretending 50 hours fits into 20KB. Extracting the valuable residue:
        - Decisions made
        - Claims proven
        - Datasets created
        - Source hashes
        - Failed attempts (so we don't repeat them)
        - Reusable endpoints
        - Compressed summary
        """
        session.status = 'compressing'
        self._save_session_state(session)

        dataset_dir = os.path.join(self.datasets_dir, session.session_id)
        os.makedirs(dataset_dir, exist_ok=True)

        # Gather residue
        residue = {
            'session_id': session.session_id,
            'question_id': session.question_id,
            'question_hash': session.question_hash,
            'intent_class': session.intent_class,
            'project': session.project,
            'started_at': session.started_at,
            'compressed_at': datetime.now().isoformat(),
            'runtime_seconds': session.runtime_seconds,
        }

        # 1. Decisions — extract from command outputs
        decisions = []
        for cmd in session.commands_run:
            if 'echo' in cmd or 'printf' in cmd:
                decisions.append({'source': 'command', 'command': cmd})
        residue['decisions'] = decisions

        # 2. Files — hash all created files
        files_residue = []
        for fname in session.files_created:
            fpath = os.path.join(session.work_dir, fname)
            if os.path.exists(fpath):
                with open(fpath, 'rb') as f:
                    h = hashlib.sha256(f.read()).hexdigest()
                files_residue.append({'filename': fname, 'hash': h, 'size': os.path.getsize(fpath)})
        residue['files'] = files_residue

        # 3. Commands — what was tried
        residue['commands'] = session.commands_run

        # 4. Tests
        residue['tests_passed'] = session.tests_passed

        # 5. Errors — failed attempts (so we don't repeat)
        residue['errors'] = session.errors

        # 6. Endpoint
        residue['endpoint_url'] = session.endpoint_url

        # 7. Receipts
        residue['receipts'] = session.receipts

        # 8. Execution events from ledger
        events = self.execution_ledger.get_session_events(session.session_id)
        residue['event_count'] = len(events)
        residue['event_types'] = list(set(e['event_type'] for e in events))

        # Write compressed dataset
        dataset_path = os.path.join(dataset_dir, 'residue.json')
        with open(dataset_path, 'w') as f:
            json.dump(residue, f, indent=2)

        # Write a human-readable summary
        summary_path = os.path.join(dataset_dir, 'summary.md')
        with open(summary_path, 'w') as f:
            f.write(self._generate_summary(session, residue))

        session.compressed = True
        session.compressed_path = dataset_path
        session.dataset_path = dataset_path
        session.status = 'done'
        session.ended_at = datetime.now().isoformat()
        session.runtime_seconds = time.time() - datetime.fromisoformat(session.started_at).timestamp()

        self._save_session_state(session)
        self.question_ledger.mark_compressed(session.question_id, session.endpoint_url)

        self._write_receipt(session, 'session_compressed', {
            'dataset_path': dataset_path,
            'residue_size': os.path.getsize(dataset_path),
            'files_preserved': len(files_residue),
            'commands_count': len(session.commands_run),
            'errors_count': len(session.errors),
        })

        return {
            'compressed': True,
            'dataset_path': dataset_path,
            'summary_path': summary_path,
            'residue': residue,
        }

    def serve(self, session: SessionState, port: int = 0) -> Dict:
        """Start a private endpoint serving the compressed dataset.

        Creates a minimal FastAPI app that serves the question's residue.
        """
        if not session.compressed:
            return {'served': False, 'reason': 'session not compressed'}

        # Generate a serving app
        app_code = self._generate_endpoint_app(session)
        app_path = os.path.join(session.work_dir, 'serve.py')
        with open(app_path, 'w') as f:
            f.write(app_code)

        if port == 0:
            port = 8000 + (hash(session.session_id) % 1000)

        endpoint_url = f"http://localhost:{port}"

        # Start uvicorn in background
        try:
            proc = subprocess.Popen(
                ['python3', '-c', f'import uvicorn; uvicorn.run("serve:app", host="127.0.0.1", port={port})'],
                cwd=session.work_dir,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(2)  # Wait for startup

            # Verify endpoint
            try:
                import urllib.request
                resp = urllib.request.urlopen(f"{endpoint_url}/health", timeout=5)
                alive = resp.status == 200
            except Exception:
                alive = False

            session.endpoint_url = endpoint_url if alive else None

            self.execution_ledger.record(
                session_id=session.session_id,
                question_id=session.question_id,
                event_type='endpoint',
                details={'url': endpoint_url, 'port': port, 'alive': alive},
                result='success' if alive else 'failure',
            )

            self._write_receipt(session, 'endpoint_started', {
                'url': endpoint_url,
                'port': port,
                'alive': alive,
            })

            return {'served': alive, 'url': endpoint_url, 'port': port}

        except Exception as e:
            session.errors.append(f'Endpoint error: {e}')
            return {'served': False, 'error': str(e)}

    def get_session(self, session_id: str) -> Optional[SessionState]:
        """Get a session by ID."""
        if session_id in self._sessions:
            return self._sessions[session_id]
        # Try loading from disk
        state_path = os.path.join(self.sessions_dir, session_id, 'state.json')
        if os.path.exists(state_path):
            with open(state_path) as f:
                data = json.load(f)
            state = SessionState(**data)
            self._sessions[session_id] = state
            return state
        return None

    def list_sessions(self, project: str = None) -> List[Dict]:
        """List all sessions, optionally filtered by project."""
        sessions = []
        for entry in os.listdir(self.sessions_dir):
            state_path = os.path.join(self.sessions_dir, entry, 'state.json')
            if os.path.exists(state_path):
                with open(state_path) as f:
                    data = json.load(f)
                if project and data.get('project') != project:
                    continue
                sessions.append({
                    'session_id': data['session_id'],
                    'question_hash': data['question_hash'][:16],
                    'intent': data['intent_class'],
                    'status': data['status'],
                    'compressed': data['compressed'],
                    'endpoint': data.get('endpoint_url'),
                    'project': data['project'],
                    'started_at': data['started_at'][:19],
                })
        return sessions

    def status(self) -> Dict:
        """Get overall QuestionOS status."""
        return {
            'questions': self.question_ledger.summary(),
            'executions': self.execution_ledger.summary(),
            'cost_avoidance': self.cost_ledger.summary(),
            'active_sessions': sum(1 for s in self._sessions.values() if s.status == 'running'),
            'datasets': len(os.listdir(self.datasets_dir)) if os.path.exists(self.datasets_dir) else 0,
        }

    def _save_session_state(self, state: SessionState):
        """Save session state to disk."""
        state_path = os.path.join(state.work_dir, 'state.json')
        with open(state_path, 'w') as f:
            json.dump(state.__dict__, f, indent=2)

    def _write_receipt(self, session: SessionState, action: str, details: Dict) -> Dict:
        """Write a receipt for a session event."""
        receipt_id = str(uuid.uuid4())
        timestamp = datetime.now().isoformat()
        content = json.dumps(details, sort_keys=True)
        artifact_hash = hashlib.sha256(content.encode()).hexdigest()

        receipt = {
            'receipt_id': receipt_id,
            'timestamp': timestamp,
            'session_id': session.session_id,
            'question_id': session.question_id,
            'action': action,
            'artifact_hash': artifact_hash,
            'details': details,
            'previous_receipt': self._last_receipt_id,
        }

        filename = f"{timestamp.replace(':', '-').replace('.', '_')}_{action}.json"
        filepath = os.path.join(self.receipts_dir, filename)
        with open(filepath, 'w') as f:
            json.dump(receipt, f, indent=2)

        session.receipts.append(receipt_id)
        self._last_receipt_id = receipt_id
        return receipt

    def _generate_summary(self, session: SessionState, residue: Dict) -> str:
        """Generate a human-readable summary of the compressed session."""
        lines = [
            f"# QRC Session Summary",
            f"",
            f"- **Session ID**: {session.session_id[:8]}",
            f"- **Question Hash**: {session.question_hash[:16]}",
            f"- **Intent**: {session.intent_class}",
            f"- **Project**: {session.project}",
            f"- **Runtime**: {session.runtime_seconds:.1f}s",
            f"- **Status**: {session.status}",
            f"",
            f"## Commands Run ({len(session.commands_run)})",
        ]
        for cmd in session.commands_run[:20]:
            lines.append(f"- `{cmd[:80]}`")
        if len(session.commands_run) > 20:
            lines.append(f"- ... and {len(session.commands_run) - 20} more")

        lines += [
            f"",
            f"## Files Created ({len(session.files_created)})",
        ]
        for f in residue['files']:
            lines.append(f"- `{f['filename']}` ({f['size']} bytes, hash={f['hash'][:16]})")

        lines += [
            f"",
            f"## Tests: {'PASSED' if session.tests_passed else 'FAILED' if session.tests_passed is False else 'NONE'}",
            f"",
            f"## Errors ({len(session.errors)})",
        ]
        for err in session.errors[:10]:
            lines.append(f"- {err[:80]}")

        lines += [
            f"",
            f"## Receipts: {len(session.receipts)}",
            f"",
            f"## Endpoint: {session.endpoint_url or 'none'}",
            f"",
            f"---",
            f"*This residue is a reusable dataset. Future questions can reference this session's*",
            f"*decisions, files, and errors to avoid repeating work.*",
        ]
        return '\n'.join(lines)

    def _generate_endpoint_app(self, session: SessionState) -> str:
        """Generate a FastAPI app that serves the compressed dataset."""
        return f'''"""Auto-generated QRC endpoint for session {session.session_id[:8]}."""
from fastapi import FastAPI
import json
import os

app = FastAPI(title="QRC Endpoint", description="Private question endpoint")

DATASET_PATH = "{session.dataset_path}"

@app.get("/health")
def health():
    return {{"status": "ok", "session": "{session.session_id[:8]}"}}

@app.get("/residue")
def get_residue():
    with open(DATASET_PATH) as f:
        return json.load(f)

@app.get("/summary")
def get_summary():
    summary_path = os.path.join(os.path.dirname(DATASET_PATH), "summary.md")
    with open(summary_path) as f:
        return {{"summary": f.read()}}
'''
