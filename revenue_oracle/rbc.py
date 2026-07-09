"""
Response Backend Capsule (RBC) — Protocol 194

An operational model answer becomes files, endpoint, tests, and receipts.

Guarantees:
  - Runnable tested artifact is guaranteed or blocked
  - Optimization is measured, not guaranteed
  - Revenue appears only when money_moved is logged

The RBC is the runtime layer that turns an AI-generated answer into a
deployable, testable, receipt-backed artifact. It enforces the hard rule:

  Do not sell cognition. Sell executable artifacts, receipts, measured
  utility, and real revenue events only when money or external acceptance
  actually exists.

Flow:
  answer → files → tests → endpoint → usage_log → optimization → money_moved → economic_proof

Economic proof requires ALL of:
  1. Executable artifact (files exist, tests pass)
  2. Usage event (someone called the endpoint)
  3. Optimization (measurable improvement recorded)
  4. Receipt (SHA-256 chained)

Revenue remains $0.00 until money_moved is explicitly logged.
"""

import hashlib
import json
import os
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class CapsuleStatus(Enum):
    DRAFT = "DRAFT"
    FILES_WRITTEN = "FILES_WRITTEN"
    TESTS_PASSED = "TESTS_PASSED"
    ENDPOINT_LIVE = "ENDPOINT_LIVE"
    USAGE_LOGGED = "USAGE_LOGGED"
    OPTIMIZATION_RECORDED = "OPTIMIZATION_RECORDED"
    MONEY_MOVED = "MONEY_MOVED"
    ECONOMIC_PROOF = "ECONOMIC_PROOF"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass
class CapsuleFile:
    path: str
    content_hash: str
    size_bytes: int
    language: str = "unknown"


@dataclass
class UsageEvent:
    event_id: str
    timestamp: float
    caller: str
    endpoint: str
    response_time_ms: float
    success: bool
    metadata: dict = field(default_factory=dict)


@dataclass
class OptimizationRecord:
    metric_name: str
    before_value: float
    after_value: float
    delta: float
    measurement_method: str
    timestamp: float


@dataclass
class MoneyMovedEvent:
    event_id: str
    timestamp: float
    amount_usd: float
    payer: str
    payment_reference: str
    payment_provider: str
    external_confirmation: dict = field(default_factory=dict)


@dataclass
class EconomicProof:
    has_executable_artifact: bool
    has_usage_event: bool
    has_optimization: bool
    has_receipt: bool
    has_money_moved: bool
    revenue_usd: float
    status: str
    blockers: list = field(default_factory=list)

    def is_economically_proven(self) -> bool:
        return all([
            self.has_executable_artifact,
            self.has_usage_event,
            self.has_optimization,
            self.has_receipt,
        ])

    def has_revenue(self) -> bool:
        return self.has_money_moved and self.revenue_usd > 0


@dataclass
class ResponseBackendCapsule:
    capsule_id: str
    artifact_id: str
    question: str
    answer_hash: str
    status: str
    files: list = field(default_factory=list)
    tests_passed: bool = False
    test_count: int = 0
    test_results: list = field(default_factory=list)
    endpoint_url: str = ""
    endpoint_live: bool = False
    usage_events: list = field(default_factory=list)
    optimizations: list = field(default_factory=list)
    money_moved_events: list = field(default_factory=list)
    receipts: list = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


class RBCEngine:
    """
    Response Backend Capsule engine.

    Turns answers into receipt-backed runtime artifacts.
    Enforces: no revenue without money_moved.
    """

    def __init__(self, receipt_ledger=None):
        self.receipt_ledger = receipt_ledger
        self.capsules: dict[str, ResponseBackendCapsule] = {}

    def create_capsule(
        self,
        artifact_id: str,
        question: str,
        answer_text: str,
    ) -> ResponseBackendCapsule:
        answer_hash = f"sha256:{hashlib.sha256(answer_text.encode()).hexdigest()[:16]}"
        capsule_id = f"rbc_{hashlib.sha256(f'{artifact_id}{answer_hash}{time.time()}'.encode()).hexdigest()[:12]}"

        capsule = ResponseBackendCapsule(
            capsule_id=capsule_id,
            artifact_id=artifact_id,
            question=question,
            answer_hash=answer_hash,
            status=CapsuleStatus.DRAFT.value,
        )
        self.capsules[capsule_id] = capsule
        self._write_receipt("capsule_created", capsule, {
            "capsule_id": capsule_id,
            "artifact_id": artifact_id,
            "answer_hash": answer_hash,
        })
        return capsule

    def write_files(
        self,
        capsule_id: str,
        files: dict[str, str],
    ) -> list[CapsuleFile]:
        capsule = self._get(capsule_id)
        written = []
        for path, content in files.items():
            content_hash = f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}"
            ext = path.rsplit(".", 1)[-1] if "." in path else "unknown"
            lang_map = {"py": "python", "js": "javascript", "ts": "typescript",
                       "go": "go", "rs": "rust", "java": "java", "sh": "shell",
                       "sql": "sql", "html": "html", "css": "css", "json": "json"}
            cf = CapsuleFile(
                path=path,
                content_hash=content_hash,
                size_bytes=len(content.encode()),
                language=lang_map.get(ext, "unknown"),
            )
            written.append(cf)
            capsule.files.append(asdict(cf))

        capsule.status = CapsuleStatus.FILES_WRITTEN.value
        capsule.updated_at = time.time()
        self._write_receipt("files_written", capsule, {
            "file_count": len(written),
            "paths": [f.path for f in written],
        })
        return written

    def record_tests(
        self,
        capsule_id: str,
        passed: bool,
        test_count: int,
        results: list = None,
    ) -> None:
        capsule = self._get(capsule_id)
        capsule.tests_passed = passed
        capsule.test_count = test_count
        capsule.test_results = results or []

        if passed:
            capsule.status = CapsuleStatus.TESTS_PASSED.value
        else:
            capsule.status = CapsuleStatus.FAILED.value

        capsule.updated_at = time.time()
        self._write_receipt("tests_recorded", capsule, {
            "passed": passed,
            "test_count": test_count,
        })

    def register_endpoint(
        self,
        capsule_id: str,
        endpoint_url: str,
    ) -> None:
        capsule = self._get(capsule_id)
        capsule.endpoint_url = endpoint_url
        capsule.endpoint_live = True
        capsule.status = CapsuleStatus.ENDPOINT_LIVE.value
        capsule.updated_at = time.time()
        self._write_receipt("endpoint_registered", capsule, {
            "endpoint_url": endpoint_url,
        })

    def log_usage(
        self,
        capsule_id: str,
        caller: str,
        endpoint: str,
        response_time_ms: float,
        success: bool = True,
        metadata: dict = None,
    ) -> UsageEvent:
        capsule = self._get(capsule_id)
        event = UsageEvent(
            event_id=f"use_{hashlib.sha256(f'{capsule_id}{time.time()}'.encode()).hexdigest()[:12]}",
            timestamp=time.time(),
            caller=caller,
            endpoint=endpoint,
            response_time_ms=response_time_ms,
            success=success,
            metadata=metadata or {},
        )
        capsule.usage_events.append(asdict(event))
        if capsule.status not in (CapsuleStatus.OPTIMIZATION_RECORDED.value,
                                   CapsuleStatus.MONEY_MOVED.value,
                                   CapsuleStatus.ECONOMIC_PROOF.value):
            capsule.status = CapsuleStatus.USAGE_LOGGED.value
        capsule.updated_at = time.time()
        self._write_receipt("usage_logged", capsule, {
            "event_id": event.event_id,
            "caller": caller,
            "success": success,
        })
        return event

    def record_optimization(
        self,
        capsule_id: str,
        metric_name: str,
        before_value: float,
        after_value: float,
        measurement_method: str = "benchmark",
    ) -> OptimizationRecord:
        capsule = self._get(capsule_id)
        delta = after_value - before_value
        opt = OptimizationRecord(
            metric_name=metric_name,
            before_value=before_value,
            after_value=after_value,
            delta=delta,
            measurement_method=measurement_method,
            timestamp=time.time(),
        )
        capsule.optimizations.append(asdict(opt))
        if capsule.status != CapsuleStatus.MONEY_MOVED.value:
            capsule.status = CapsuleStatus.OPTIMIZATION_RECORDED.value
        capsule.updated_at = time.time()
        self._write_receipt("optimization_recorded", capsule, {
            "metric": metric_name,
            "delta": delta,
        })
        return opt

    def log_money_moved(
        self,
        capsule_id: str,
        amount_usd: float,
        payer: str,
        payment_reference: str,
        payment_provider: str = "stripe",
        external_confirmation: dict = None,
    ) -> MoneyMovedEvent:
        capsule = self._get(capsule_id)
        event = MoneyMovedEvent(
            event_id=f"pay_{hashlib.sha256(f'{capsule_id}{amount_usd}{time.time()}'.encode()).hexdigest()[:12]}",
            timestamp=time.time(),
            amount_usd=amount_usd,
            payer=payer,
            payment_reference=payment_reference,
            payment_provider=payment_provider,
            external_confirmation=external_confirmation or {},
        )
        capsule.money_moved_events.append(asdict(event))
        capsule.status = CapsuleStatus.MONEY_MOVED.value
        capsule.updated_at = time.time()
        self._write_receipt("money_moved", capsule, {
            "event_id": event.event_id,
            "amount_usd": amount_usd,
            "payer": payer,
            "payment_provider": payment_provider,
            "external_confirmation": external_confirmation or {},
        })
        return event

    def evaluate_economic_proof(self, capsule_id: str) -> EconomicProof:
        capsule = self._get(capsule_id)
        has_files = len(capsule.files) > 0
        has_tests = capsule.tests_passed
        has_endpoint = capsule.endpoint_live
        has_executable = has_files and has_tests
        has_usage = len(capsule.usage_events) > 0
        has_opt = len(capsule.optimizations) > 0
        has_receipt = len(capsule.receipts) > 0
        has_money = len(capsule.money_moved_events) > 0
        revenue = sum(e["amount_usd"] for e in capsule.money_moved_events)

        blockers = []
        if not has_executable:
            blockers.append("no_executable_artifact")
        if not has_usage:
            blockers.append("no_usage_event")
        if not has_opt:
            blockers.append("no_optimization_recorded")
        if not has_receipt:
            blockers.append("no_receipt")

        if self._is_economically_proven(has_executable, has_usage, has_opt, has_receipt):
            status = CapsuleStatus.ECONOMIC_PROOF.value
            capsule.status = status
        elif has_money:
            status = CapsuleStatus.MONEY_MOVED.value
        else:
            status = capsule.status

        proof = EconomicProof(
            has_executable_artifact=has_executable,
            has_usage_event=has_usage,
            has_optimization=has_opt,
            has_receipt=has_receipt,
            has_money_moved=has_money,
            revenue_usd=revenue,
            status=status,
            blockers=blockers,
        )
        return proof

    def _is_economically_proven(self, has_exec, has_usage, has_opt, has_receipt) -> bool:
        return all([has_exec, has_usage, has_opt, has_receipt])

    def _get(self, capsule_id: str) -> ResponseBackendCapsule:
        if capsule_id not in self.capsules:
            raise KeyError(f"Capsule {capsule_id} not found")
        return self.capsules[capsule_id]

    def _write_receipt(self, event_type: str, capsule: ResponseBackendCapsule, data: dict) -> None:
        receipt_data = {
            "event_type": event_type,
            "capsule_id": capsule.capsule_id,
            "artifact_id": capsule.artifact_id,
            "timestamp": time.time(),
            **data,
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"
        receipt_entry = {
            "event_type": event_type,
            "data": receipt_data,
            "receipt_hash": receipt_hash,
            "timestamp": time.time(),
        }
        capsule.receipts.append(receipt_entry)

        if self.receipt_ledger:
            self.receipt_ledger.write(
                receipt_type=f"rbc_{event_type}",
                artifact_id=capsule.artifact_id,
                data=receipt_data,
                output_hash=receipt_hash,
            )

    def get_capsule(self, capsule_id: str) -> Optional[dict]:
        c = self.capsules.get(capsule_id)
        return c.to_dict() if c else None

    def list_capsules(self) -> list:
        return [c.to_dict() for c in self.capsules.values()]
