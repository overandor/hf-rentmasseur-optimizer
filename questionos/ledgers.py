"""QuestionOS Ledgers — Three separate ledgers for question provenance.

1. Question Ledger — private question hash, timestamp, intent class, access policy
2. Execution Ledger — what happened: commands, files, routes, tests, logs, receipts
3. Cost-Avoidance Ledger — estimated human work avoided with receipts

None of these ledgers expose raw questions to external clients unless explicitly allowed.
"""

import os
import json
import hashlib
import uuid
import threading
from datetime import datetime
from typing import Dict, List, Optional, Any


class QuestionLedger:
    """Stores private question metadata. Never exposes raw questions externally.

    Records: question hash (not raw text), timestamp, project, intent class, access policy.
    The raw question is stored locally with an access policy but never sent to clients.
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(os.getcwd(), 'questionos', 'ledgers', 'questions.json')
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._lock = threading.Lock()
        self._questions: List[Dict] = []
        self._load()

    def _load(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path) as f:
                    self._questions = json.load(f)
            except Exception:
                self._questions = []

    def _save(self):
        with open(self.db_path, 'w') as f:
            json.dump(self._questions, f, indent=2)

    def _hash_question(self, question: str) -> str:
        return hashlib.sha256(question.encode()).hexdigest()

    def record(self, question: str, project: str = None, intent_class: str = None,
               access_policy: str = 'private') -> Dict:
        """Record a new question. Returns the question record (without raw text in the public field)."""
        with self._lock:
            qid = str(uuid.uuid4())
            record = {
                'question_id': qid,
                'question_hash': self._hash_question(question),
                'timestamp': datetime.now().isoformat(),
                'project': project or 'default',
                'intent_class': intent_class or 'unknown',
                'access_policy': access_policy,
                'session_id': None,  # Linked later when session starts
                'compressed': False,  # Set true after compression
                'endpoint_url': None,  # Set if endpoint was created
            }

            # Store raw question separately, controlled by access_policy
            raw_path = os.path.join(os.path.dirname(self.db_path), 'raw_questions', f'{qid}.txt')
            os.makedirs(os.path.dirname(raw_path), exist_ok=True)
            with open(raw_path, 'w') as f:
                f.write(question)

            self._questions.append(record)
            self._save()
            return record

    def link_session(self, question_id: str, session_id: str):
        """Link a question to its runtime session."""
        with self._lock:
            for q in self._questions:
                if q['question_id'] == question_id:
                    q['session_id'] = session_id
                    self._save()
                    return True
            return False

    def mark_compressed(self, question_id: str, endpoint_url: str = None):
        """Mark a question as compressed and optionally link its endpoint."""
        with self._lock:
            for q in self._questions:
                if q['question_id'] == question_id:
                    q['compressed'] = True
                    if endpoint_url:
                        q['endpoint_url'] = endpoint_url
                    self._save()
                    return True
            return False

    def get(self, question_id: str) -> Optional[Dict]:
        for q in self._questions:
            if q['question_id'] == question_id:
                return q
        return None

    def list_questions(self, project: str = None) -> List[Dict]:
        if project:
            return [q for q in self._questions if q['project'] == project]
        return list(self._questions)

    def summary(self) -> Dict:
        return {
            'total_questions': len(self._questions),
            'compressed': sum(1 for q in self._questions if q['compressed']),
            'with_endpoints': sum(1 for q in self._questions if q['endpoint_url']),
            'projects': list(set(q['project'] for q in self._questions)),
            'intent_classes': list(set(q['intent_class'] for q in self._questions)),
        }


class ExecutionLedger:
    """Records what happened during a question session.

    Stores: commands, files, routes, tests, logs, receipts, failures, runtime cost.
    Every entry is linked to a session_id and question_id.
    """

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(os.getcwd(), 'questionos', 'ledgers', 'executions.json')
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._lock = threading.Lock()
        self._entries: List[Dict] = []
        self._load()

    def _load(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path) as f:
                    self._entries = json.load(f)
            except Exception:
                self._entries = []

    def _save(self):
        with open(self.db_path, 'w') as f:
            json.dump(self._entries, f, indent=2)

    def record(self, session_id: str, question_id: str, event_type: str,
               details: Dict = None, result: str = 'success') -> Dict:
        """Record an execution event."""
        with self._lock:
            entry = {
                'entry_id': str(uuid.uuid4()),
                'session_id': session_id,
                'question_id': question_id,
                'timestamp': datetime.now().isoformat(),
                'event_type': event_type,  # command, file_write, test, endpoint, receipt, failure
                'details': details or {},
                'result': result,
            }
            self._entries.append(entry)
            self._save()
            return entry

    def get_session_events(self, session_id: str) -> List[Dict]:
        return [e for e in self._entries if e['session_id'] == session_id]

    def get_question_events(self, question_id: str) -> List[Dict]:
        return [e for e in self._entries if e['question_id'] == question_id]

    def summary(self) -> Dict:
        by_type = {}
        for e in self._entries:
            t = e['event_type']
            by_type[t] = by_type.get(t, 0) + 1
        return {
            'total_events': len(self._entries),
            'by_type': by_type,
            'failures': sum(1 for e in self._entries if e['result'] == 'failure'),
            'sessions': len(set(e['session_id'] for e in self._entries)),
        }


class CostAvoidanceLedger:
    """Estimates what human work was avoided.

    NOT guaranteed revenue. Estimated avoided cost with receipts.
    Each entry links to a question_id and session_id.

    Categories: research_hours, engineering_hours, qa_hours, analyst_hours,
    duplicated_search, repeated_explanation, wrong_path_prevention.
    """

    # Hourly rates for human work (USD, conservative estimates)
    HOURLY_RATES = {
        'research': 75,
        'engineering': 120,
        'qa': 80,
        'analyst': 95,
        'explanation': 60,
        'search': 50,
        'debugging': 130,
        'data_building': 90,
    }

    def __init__(self, db_path: str = None):
        self.db_path = db_path or os.path.join(os.getcwd(), 'questionos', 'ledgers', 'cost_avoidance.json')
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._lock = threading.Lock()
        self._entries: List[Dict] = []
        self._load()

    def _load(self):
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path) as f:
                    self._entries = json.load(f)
            except Exception:
                self._entries = []

    def _save(self):
        with open(self.db_path, 'w') as f:
            json.dump(self._entries, f, indent=2)

    def record(self, question_id: str, session_id: str,
               work_category: str, hours_avoided: float,
               basis: str = None, confidence: float = 0.5) -> Dict:
        """Record estimated cost avoidance.

        Args:
            work_category: One of HOURLY_RATES keys
            hours_avoided: Estimated hours of human work avoided
            basis: Explanation of why this estimate was made
            confidence: 0.0-1.0, how confident we are the avoidance is real

        Returns:
            The cost avoidance record with calculated USD value.
        """
        with self._lock:
            rate = self.HOURLY_RATES.get(work_category, 50)
            usd_value = hours_avoided * rate * confidence

            entry = {
                'entry_id': str(uuid.uuid4()),
                'question_id': question_id,
                'session_id': session_id,
                'timestamp': datetime.now().isoformat(),
                'work_category': work_category,
                'hours_avoided': hours_avoided,
                'hourly_rate_usd': rate,
                'confidence': confidence,
                'estimated_value_usd': usd_value,
                'basis': basis or 'unspecified',
                'disputed': False,
                'settled': False,
            }
            self._entries.append(entry)
            self._save()
            return entry

    def dispute(self, entry_id: str, reason: str):
        """Mark a cost avoidance claim as disputed."""
        with self._lock:
            for e in self._entries:
                if e['entry_id'] == entry_id:
                    e['disputed'] = True
                    e['dispute_reason'] = reason
                    self._save()
                    return True
            return False

    def settle(self, entry_id: str, settled_value_usd: float = None):
        """Settle a cost avoidance claim after dispute resolution."""
        with self._lock:
            for e in self._entries:
                if e['entry_id'] == entry_id:
                    e['settled'] = True
                    if settled_value_usd is not None:
                        e['settled_value_usd'] = settled_value_usd
                    else:
                        e['settled_value_usd'] = e['estimated_value_usd']
                    self._save()
                    return True
            return False

    def summary(self) -> Dict:
        total_est = sum(e['estimated_value_usd'] for e in self._entries if not e['disputed'])
        total_settled = sum(e.get('settled_value_usd', 0) for e in self._entries if e['settled'])
        disputed = sum(1 for e in self._entries if e['disputed'])
        by_category = {}
        for e in self._entries:
            cat = e['work_category']
            if cat not in by_category:
                by_category[cat] = {'hours': 0, 'usd': 0}
            by_category[cat]['hours'] += e['hours_avoided']
            by_category[cat]['usd'] += e['estimated_value_usd']

        return {
            'total_entries': len(self._entries),
            'total_estimated_usd': round(total_est, 2),
            'total_settled_usd': round(total_settled, 2),
            'disputed': disputed,
            'settled': sum(1 for e in self._entries if e['settled']),
            'by_category': {k: {'hours': round(v['hours'], 2), 'usd': round(v['usd'], 2)}
                           for k, v in by_category.items()},
            'disclaimer': 'Estimated avoided cost, not guaranteed revenue. '
                         'Every claim must survive attribution review before settlement.',
        }

    def report(self) -> str:
        """Human-readable cost avoidance report."""
        s = self.summary()
        lines = [
            "=" * 60,
            "  COST-AVOIDANCE LEDGER REPORT",
            "=" * 60,
            f"  Total entries: {s['total_entries']}",
            f"  Estimated value: ${s['total_estimated_usd']}",
            f"  Settled value: ${s['total_settled_usd']}",
            f"  Disputed: {s['disputed']}  |  Settled: {s['settled']}",
            "",
            "  By category:",
        ]
        for cat, data in s['by_category'].items():
            lines.append(f"    {cat:20s}  {data['hours']:6.1f}h  ${data['usd']:10.2f}")
        lines += [
            "",
            f"  {s['disclaimer']}",
            "=" * 60,
        ]
        return '\n'.join(lines)
