"""QuestionOS TUI — Terminal User Interface.

A tmux-like dashboard with panes for:
1. Current question
2. Running commands
3. Dataset state
4. Endpoint list
5. Receipts
6. Cost avoided
7. Compressed memory

Behaves like tmux + dashboard + local backend supervisor.
"""

import os
import sys
import time
import json
import subprocess
from datetime import datetime
from typing import Optional

from .qrc_engine import QRCEngine, SessionState


class QuestionTUI:
    """Terminal UI for QuestionOS.

    Renders a dashboard in the terminal showing:
    - Active questions/sessions
    - Running commands
    - Dataset state
    - Endpoints
    - Receipts
    - Cost avoidance
    - Compressed memory

    Uses ANSI escape codes for rendering. No external dependencies.
    """

    def __init__(self, engine: QRCEngine = None):
        self.engine = engine or QRCEngine()
        self.running = False
        self.selected_session = 0
        self.view_mode = 'dashboard'  # dashboard, session, cost, receipts

    def render(self) -> str:
        """Render the current view as a string."""
        if self.view_mode == 'dashboard':
            return self._render_dashboard()
        elif self.view_mode == 'session':
            return self._render_session_detail()
        elif self.view_mode == 'cost':
            return self._render_cost_report()
        elif self.view_mode == 'receipts':
            return self._render_receipts()
        return self._render_dashboard()

    def _render_dashboard(self) -> str:
        """Render the main dashboard."""
        status = self.engine.status()
        sessions = self.engine.list_sessions()
        q_summary = status['questions']
        e_summary = status['executions']
        c_summary = status['cost_avoidance']

        lines = []
        lines.append(self._box("QuestionOS — Terminal Question Runtime", width=70))
        lines.append("")
        lines.append(self._section("QUESTIONS"))
        lines.append(f"  Total: {q_summary['total_questions']}  "
                     f"Compressed: {q_summary['compressed']}  "
                     f"With Endpoints: {q_summary['with_endpoints']}")
        lines.append(f"  Projects: {', '.join(q_summary['projects'])}")
        lines.append(f"  Intents: {', '.join(q_summary['intent_classes'])}")
        lines.append("")

        lines.append(self._section("EXECUTIONS"))
        lines.append(f"  Total events: {e_summary['total_events']}")
        lines.append(f"  Sessions: {e_summary['sessions']}  "
                     f"Failures: {e_summary['failures']}")
        if e_summary['by_type']:
            for etype, count in e_summary['by_type'].items():
                lines.append(f"    {etype}: {count}")
        lines.append("")

        lines.append(self._section("COST AVOIDANCE"))
        lines.append(f"  Estimated: ${c_summary['total_estimated_usd']}  "
                     f"Settled: ${c_summary['total_settled_usd']}")
        lines.append(f"  Disputed: {c_summary['disputed']}  "
                     f"Settled: {c_summary['settled']}")
        if c_summary['by_category']:
            for cat, data in c_summary['by_category'].items():
                lines.append(f"    {cat:20s}  {data['hours']:6.1f}h  ${data['usd']:10.2f}")
        lines.append(f"  {c_summary['disclaimer'][:60]}")
        lines.append("")

        lines.append(self._section("ACTIVE SESSIONS"))
        if sessions:
            for i, s in enumerate(sessions[-10:]):
                marker = ">" if i == self.selected_session else " "
                status_icon = self._status_icon(s['status'])
                endpoint = s['endpoint'] or ''
                lines.append(f"  {marker} {status_icon} {s['session_id'][:8]} "
                             f"[{s['intent']:12s}] {s['project']:10s} "
                             f"{'ENDPOINT' if endpoint else 'NO EP'}")
        else:
            lines.append("  (no sessions yet)")
        lines.append("")

        lines.append(self._section("DATASETS"))
        lines.append(f"  Compressed datasets: {status['datasets']}")
        lines.append("")

        lines.append(self._footer())
        return '\n'.join(lines)

    def _render_session_detail(self) -> str:
        """Render detail for the selected session."""
        sessions = self.engine.list_sessions()
        if not sessions:
            return "No sessions to display.\n\nPress [d] for dashboard."

        idx = min(self.selected_session, len(sessions) - 1)
        s = sessions[idx]
        session = self.engine.get_session(s['session_id'])

        if not session:
            return f"Session {s['session_id'][:8]} not found."

        lines = []
        lines.append(self._box(f"Session {session.session_id[:8]}", width=70))
        lines.append("")
        lines.append(f"  Intent:     {session.intent_class}")
        lines.append(f"  Project:    {session.project}")
        lines.append(f"  Status:     {session.status}")
        lines.append(f"  Started:    {session.started_at[:19]}")
        lines.append(f"  Ended:      {session.ended_at[:19] if session.ended_at else 'running'}")
        lines.append(f"  Runtime:    {session.runtime_seconds:.1f}s")
        lines.append(f"  Compressed: {'YES' if session.compressed else 'NO'}")
        lines.append(f"  Endpoint:   {session.endpoint_url or 'none'}")
        lines.append("")

        lines.append(self._section("COMMANDS"))
        if session.commands_run:
            for cmd in session.commands_run[:15]:
                lines.append(f"  $ {cmd[:60]}")
            if len(session.commands_run) > 15:
                lines.append(f"  ... and {len(session.commands_run) - 15} more")
        else:
            lines.append("  (none)")
        lines.append("")

        lines.append(self._section("FILES"))
        if session.files_created:
            for f in session.files_created:
                lines.append(f"  {f}")
        else:
            lines.append("  (none)")
        lines.append("")

        lines.append(self._section("TESTS"))
        if session.tests_passed is True:
            lines.append("  PASSED")
        elif session.tests_passed is False:
            lines.append("  FAILED")
        else:
            lines.append("  (not run)")
        lines.append("")

        lines.append(self._section("RECEIPTS"))
        lines.append(f"  {len(session.receipts)} receipts written")
        lines.append("")

        lines.append(self._section("ERRORS"))
        if session.errors:
            for err in session.errors[:5]:
                lines.append(f"  ! {err[:60]}")
        else:
            lines.append("  (none)")
        lines.append("")

        lines.append(self._footer())
        return '\n'.join(lines)

    def _render_cost_report(self) -> str:
        """Render the cost avoidance report."""
        return self.engine.cost_ledger.report()

    def _render_receipts(self) -> str:
        """Render recent receipts."""
        receipts_dir = self.engine.receipts_dir
        if not os.path.exists(receipts_dir):
            return "No receipts directory."

        files = sorted(os.listdir(receipts_dir), reverse=True)[:20]
        if not files:
            return "No receipts yet."

        lines = [self._box("Receipts (latest 20)", width=70), ""]
        for fname in files:
            path = os.path.join(receipts_dir, fname)
            try:
                with open(path) as f:
                    r = json.load(f)
                lines.append(f"  {r['timestamp'][:19]}  {r['action']:25s}  "
                             f"hash={r['artifact_hash'][:16]}")
            except Exception:
                lines.append(f"  {fname} (error reading)")

        lines.append("")
        lines.append(self._footer())
        return '\n'.join(lines)

    def _box(self, text: str, width: int = 70) -> str:
        """Render a boxed title."""
        padded = f" {text} "
        pad_total = width - len(padded)
        left = pad_total // 2
        right = pad_total - left
        return "+" + "=" * left + padded + "=" * right + "+"

    def _section(self, title: str) -> str:
        """Render a section header."""
        return f"--- {title} {'-' * (60 - len(title))}"

    def _status_icon(self, status: str) -> str:
        icons = {'init': '?', 'running': '*', 'compressing': '~', 'done': '=', 'failed': '!'}
        return icons.get(status, '?')

    def _footer(self) -> str:
        return ("[d] dashboard  [s] session  [c] cost  [r] receipts  "
                "[a] ask question  [q] quit")

    def run(self):
        """Run the TUI loop."""
        self.running = True
        while self.running:
            # Clear screen
            sys.stdout.write('\033[2J\033[H')
            sys.stdout.write(self.render())
            sys.stdout.write('\n> ')
            sys.stdout.flush()

            try:
                cmd = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                break

            if cmd == 'q' or cmd == 'quit':
                self.running = False
            elif cmd == 'd':
                self.view_mode = 'dashboard'
            elif cmd == 's':
                self.view_mode = 'session'
            elif cmd == 'c':
                self.view_mode = 'cost'
            elif cmd == 'r':
                self.view_mode = 'receipts'
            elif cmd == 'a':
                self._ask_question()
            elif cmd == 'j':
                self.selected_session = min(self.selected_session + 1, 100)
            elif cmd == 'k':
                self.selected_session = max(self.selected_session - 1, 0)
            elif cmd == '':
                pass  # refresh

    def _ask_question(self):
        """Interactive question input."""
        sys.stdout.write('\033[2J\033[H')
        sys.stdout.write(self._box("Ask a Question", width=70) + '\n\n')
        sys.stdout.write("Enter your question (multi-line, end with empty line):\n> ")
        sys.stdout.flush()

        lines = []
        try:
            while True:
                line = input()
                if line == '':
                    break
                lines.append(line)
                sys.stdout.write('> ')
                sys.stdout.flush()
        except (EOFError, KeyboardInterrupt):
            pass

        question = '\n'.join(lines)
        if not question.strip():
            return

        project = input("Project (default): ").strip() or 'default'

        sys.stdout.write(f"\nStarting QRC session...\n")
        sys.stdout.flush()

        session = self.engine.ask(question, project=project)
        sys.stdout.write(f"Session {session.session_id[:8]} started (intent: {session.intent_class})\n")
        sys.stdout.write(f"Work dir: {session.work_dir}\n")
        sys.stdout.write(f"Cost avoidance estimate recorded.\n")
        sys.stdout.write("\nPress Enter to continue...")
        sys.stdout.flush()
        input()


def run_tui():
    """Entry point for the QuestionOS TUI."""
    tui = QuestionTUI()
    tui.run()
