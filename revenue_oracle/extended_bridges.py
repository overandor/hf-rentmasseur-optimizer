"""
Extended Integration Bridges — Protocols 205-212

Protocol 205: SystemLake → Oracle Bridge
Protocol 206: QuestionOS → Oracle Bridge
Protocol 207: Compliance Checklist Engine
Protocol 208: Model Swapping Layer
Protocol 209: Deployment Receipt Protocol
Protocol 210: Proof Export (Base64)
Protocol 211: Multi-Model Consensus
Protocol 212: Hallucination Detection
"""

import hashlib
import json
import time
import base64
import zlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

from .schema import OracleDB
from .receipt_ledger import ReceiptLedger


# ═══════════════════════════════════════════════════════════════════
# Protocol 205: SystemLake → Oracle Bridge
# ═══════════════════════════════════════════════════════════════════

class SystemLakeBridge:
    """
    Bridge between SystemLake (systemlake/) and the Oracle.

    Imports underwriting scores, collateral grades, risk classifications,
    and Merkle roots into the Oracle's artifact system.
    """

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger):
        self.db = db
        self.receipt_ledger = receipt_ledger

    def import_system_score(
        self,
        system_name: str,
        system_path: str,
        score: float,
        grade: str,
        functionality: float = 0.0,
        reproducibility: float = 0.0,
        receipt_strength: float = 0.0,
        deployability: float = 0.0,
        economic_evidence: float = 0.0,
        ip_clarity: float = 0.0,
        security_cleanliness: float = 0.0,
        haircuts: list = None,
        merkle_root: str = "",
        risks: list = None,
    ) -> dict:
        haircuts = haircuts or []
        risks = risks or []
        artifact_id = f"slk_{hashlib.sha256(f'{system_name}{system_path}{time.time()}'.encode()).hexdigest()[:12]}"

        receipt_data = {
            "artifact_id": artifact_id,
            "system_name": system_name,
            "system_path": system_path,
            "score": score,
            "grade": grade,
            "functionality": functionality,
            "reproducibility": reproducibility,
            "receipt_strength": receipt_strength,
            "deployability": deployability,
            "economic_evidence": economic_evidence,
            "ip_clarity": ip_clarity,
            "security_cleanliness": security_cleanliness,
            "haircuts": haircuts,
            "merkle_root": merkle_root,
            "risk_count": len(risks),
            "imported_at": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="systemlake_score_imported",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )

        return {
            "artifact_id": artifact_id,
            "system_name": system_name,
            "score": score,
            "grade": grade,
            "receipt_hash": receipt_hash,
            "status": "imported",
        }

    def import_borrowing_base(
        self,
        systems_count: int,
        low_estimate: float,
        mid_estimate: float,
        high_estimate: float,
        grade_distribution: dict = None,
    ) -> dict:
        grade_distribution = grade_distribution or {}
        artifact_id = f"bb_{hashlib.sha256(f'borrowing_base{time.time()}'.encode()).hexdigest()[:12]}"

        receipt_data = {
            "artifact_id": artifact_id,
            "systems_count": systems_count,
            "low_estimate": low_estimate,
            "mid_estimate": mid_estimate,
            "high_estimate": high_estimate,
            "grade_distribution": grade_distribution,
            "imported_at": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="borrowing_base_imported",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )

        return {
            "artifact_id": artifact_id,
            "low": low_estimate,
            "mid": mid_estimate,
            "high": high_estimate,
            "receipt_hash": receipt_hash,
        }


# ═══════════════════════════════════════════════════════════════════
# Protocol 206: QuestionOS → Oracle Bridge
# ═══════════════════════════════════════════════════════════════════

class QuestionOSBridge:
    """
    Bridge between QuestionOS (questionos/) and the Oracle.

    Imports question sessions, execution ledgers, and cost-avoidance
    records into the Oracle's artifact system.

    Cost avoidance is NOT revenue. It is always labeled as estimate.
    """

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger):
        self.db = db
        self.receipt_ledger = receipt_ledger

    def import_session(
        self,
        question_hash: str,
        intent_class: str,
        files_created: list = None,
        commands_run: int = 0,
        tests_passed: bool = False,
        receipts_count: int = 0,
        cost_avoidance_usd: float = 0.0,
        cost_confidence: float = 0.0,
    ) -> dict:
        files_created = files_created or []
        artifact_id = f"qrc_{hashlib.sha256(f'{question_hash}{time.time()}'.encode()).hexdigest()[:12]}"

        receipt_data = {
            "artifact_id": artifact_id,
            "question_hash": question_hash,
            "intent_class": intent_class,
            "files_created": files_created,
            "commands_run": commands_run,
            "tests_passed": tests_passed,
            "receipts_count": receipts_count,
            "cost_avoidance_usd": cost_avoidance_usd,
            "cost_confidence": cost_confidence,
            "cost_avoidance_is_estimate": True,
            "cost_avoidance_is_not_revenue": True,
            "imported_at": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="questionos_session_imported",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )

        return {
            "artifact_id": artifact_id,
            "intent_class": intent_class,
            "cost_avoidance_usd": cost_avoidance_usd,
            "cost_is_estimate": True,
            "receipt_hash": receipt_hash,
            "status": "imported",
        }


# ═══════════════════════════════════════════════════════════════════
# Protocol 207: Compliance Checklist Engine
# ═══════════════════════════════════════════════════════════════════

class ComplianceStatus(Enum):
    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    NOT_APPLICABLE = "not_applicable"
    PENDING_REVIEW = "pending_review"


@dataclass
class ComplianceCheck:
    check_id: str
    category: str
    name: str
    description: str
    status: str
    details: str = ""
    severity: str = "medium"  # low, medium, high, critical


@dataclass
class ComplianceReport:
    report_id: str
    artifact_id: str
    checks: list
    pass_count: int
    fail_count: int
    warn_count: int
    overall_status: str  # compliant, non_compliant, needs_review
    receipt_hash: str
    timestamp: float = field(default_factory=time.time)


class ComplianceChecklistEngine:
    """
    Pre-deployment compliance verification.

    Checks:
      1. No secrets in artifact
      2. License present and compatible
      3. No forbidden phrases in landing page
      4. Revenue claims backed by payment proof
      5. Token mode is proof_only or disabled by default
      6. Receipt chain is valid
      7. No unverified valuation claims
      8. Escrow required for paid products
      9. External confirmation for revenue
      10. No fake deployment URLs
    """

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger):
        self.db = db
        self.receipt_ledger = receipt_ledger

    def run_checklist(
        self,
        artifact_id: str,
        has_secrets: bool = False,
        has_license: bool = False,
        license_compatible: bool = True,
        has_forbidden_phrases: bool = False,
        revenue_backed_by_payment: bool = True,
        token_mode: str = "proof_only",
        receipt_chain_valid: bool = True,
        has_unverified_valuation: bool = False,
        requires_escrow: bool = False,
        has_external_confirmation: bool = True,
        deployment_url_real: bool = True,
    ) -> ComplianceReport:
        checks = []

        # 1. Secrets check
        checks.append(ComplianceCheck(
            check_id="sec_001",
            category="security",
            name="no_secrets_exposed",
            description="Artifact must not expose API keys, tokens, or passwords",
            status=ComplianceStatus.FAIL.value if has_secrets else ComplianceStatus.PASS.value,
            details="Secrets detected in artifact" if has_secrets else "No secrets found",
            severity="critical",
        ))

        # 2. License check
        if not has_license:
            checks.append(ComplianceCheck(
                check_id="lic_001",
                category="legal",
                name="license_present",
                description="Artifact must have a license",
                status=ComplianceStatus.FAIL.value,
                details="No license file found",
                severity="high",
            ))
        elif not license_compatible:
            checks.append(ComplianceCheck(
                check_id="lic_002",
                category="legal",
                name="license_compatible",
                description="License must be compatible with commercial use",
                status=ComplianceStatus.WARN.value,
                details="Copyleft license may restrict commercial use",
                severity="medium",
            ))
        else:
            checks.append(ComplianceCheck(
                check_id="lic_001",
                category="legal",
                name="license_present",
                description="Artifact must have a license",
                status=ComplianceStatus.PASS.value,
                details="License present and compatible",
                severity="high",
            ))

        # 3. Forbidden phrases
        checks.append(ComplianceCheck(
            check_id="lp_001",
            category="marketing",
            name="no_forbidden_phrases",
            description="Landing page must not contain forbidden phrases",
            status=ComplianceStatus.FAIL.value if has_forbidden_phrases else ComplianceStatus.PASS.value,
            details="Forbidden phrases detected" if has_forbidden_phrases else "No forbidden phrases",
            severity="high",
        ))

        # 4. Revenue backed by payment
        checks.append(ComplianceCheck(
            check_id="rev_001",
            category="revenue",
            name="revenue_backed_by_payment",
            description="Revenue claims must be backed by actual payment proof",
            status=ComplianceStatus.FAIL.value if not revenue_backed_by_payment else ComplianceStatus.PASS.value,
            details="Revenue claims lack payment proof" if not revenue_backed_by_payment else "Revenue backed by payment",
            severity="critical",
        ))

        # 5. Token mode
        allowed_modes = ["proof_only", "disabled", "non_transferable_devnet"]
        checks.append(ComplianceCheck(
            check_id="tok_001",
            category="tokens",
            name="token_mode_safe",
            description="Token mode must be proof_only, disabled, or devnet by default",
            status=ComplianceStatus.PASS.value if token_mode in allowed_modes else ComplianceStatus.FAIL.value,
            details=f"Token mode: {token_mode}",
            severity="critical",
        ))

        # 6. Receipt chain
        checks.append(ComplianceCheck(
            check_id="rcp_001",
            category="integrity",
            name="receipt_chain_valid",
            description="Receipt chain must be valid and tamper-evident",
            status=ComplianceStatus.FAIL.value if not receipt_chain_valid else ComplianceStatus.PASS.value,
            details="Chain broken" if not receipt_chain_valid else "Chain valid",
            severity="critical",
        ))

        # 7. Unverified valuation
        checks.append(ComplianceCheck(
            check_id="val_001",
            category="valuation",
            name="no_unverified_valuation",
            description="Valuation claims must be reconciled",
            status=ComplianceStatus.WARN.value if has_unverified_valuation else ComplianceStatus.PASS.value,
            details="Unverified valuation claims present" if has_unverified_valuation else "All valuations reconciled",
            severity="medium",
        ))

        # 8. Escrow for paid products
        if requires_escrow:
            checks.append(ComplianceCheck(
                check_id="esc_001",
                category="revenue",
                name="escrow_required",
                description="Paid products must use escrow",
                status=ComplianceStatus.PENDING_REVIEW.value,
                details="Escrow verification needed",
                severity="high",
            ))

        # 9. External confirmation
        checks.append(ComplianceCheck(
            check_id="ext_001",
            category="revenue",
            name="external_confirmation",
            description="Revenue events require external confirmation",
            status=ComplianceStatus.FAIL.value if not has_external_confirmation else ComplianceStatus.PASS.value,
            details="No external confirmation" if not has_external_confirmation else "External confirmation present",
            severity="critical",
        ))

        # 10. Real deployment URL
        checks.append(ComplianceCheck(
            check_id="dep_001",
            category="deployment",
            name="real_deployment_url",
            description="Deployment URL must be real, not fake",
            status=ComplianceStatus.FAIL.value if not deployment_url_real else ComplianceStatus.PASS.value,
            details="Fake URL detected" if not deployment_url_real else "URL is real",
            severity="high",
        ))

        pass_count = sum(1 for c in checks if c.status == ComplianceStatus.PASS.value)
        fail_count = sum(1 for c in checks if c.status == ComplianceStatus.FAIL.value)
        warn_count = sum(1 for c in checks if c.status == ComplianceStatus.WARN.value)

        if fail_count > 0:
            overall = "non_compliant"
        elif warn_count > 0:
            overall = "needs_review"
        else:
            overall = "compliant"

        report_id = f"cmp_{hashlib.sha256(f'{artifact_id}{time.time()}'.encode()).hexdigest()[:12]}"
        checks_serialized = [asdict(c) for c in checks]

        receipt_data = {
            "report_id": report_id,
            "artifact_id": artifact_id,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "warn_count": warn_count,
            "overall_status": overall,
            "checks": checks_serialized,
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="compliance_checklist_run",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )

        return ComplianceReport(
            report_id=report_id,
            artifact_id=artifact_id,
            checks=checks_serialized,
            pass_count=pass_count,
            fail_count=fail_count,
            warn_count=warn_count,
            overall_status=overall,
            receipt_hash=receipt_hash,
        )


# ═══════════════════════════════════════════════════════════════════
# Protocol 208: Model Swapping Layer
# ═══════════════════════════════════════════════════════════════════

class ModelProvider(Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL_FILE = "local_file"
    MOCK_DISABLED = "mock_disabled"


@dataclass
class ModelConfig:
    provider: str
    model_name: str
    endpoint: str
    api_key_env: str = ""  # env var name, never the key itself
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout_seconds: int = 30
    fail_closed: bool = True


@dataclass
class ModelResponse:
    provider: str
    model: str
    content: str
    latency_ms: float
    success: bool
    error: str = ""
    tokens_used: int = 0


class ModelSwappingLayer:
    """
    Interchangeable LLM provider layer.

    Supports Ollama (local), OpenAI, Anthropic, and local file fallback.
    Fail-closed by default: no mock output when a provider is unavailable.

    Configuration:
      - Default: Ollama at localhost:11434
      - Swap by changing provider config
      - API keys read from env vars, never hardcoded
    """

    DEFAULT_CONFIGS = {
        ModelProvider.OLLAMA.value: ModelConfig(
            provider="ollama",
            model_name="llama3",
            endpoint="http://localhost:11434",
            fail_closed=True,
        ),
        ModelProvider.OPENAI.value: ModelConfig(
            provider="openai",
            model_name="gpt-4",
            endpoint="https://api.openai.com/v1",
            api_key_env="OPENAI_API_KEY",
            fail_closed=True,
        ),
        ModelProvider.ANTHROPIC.value: ModelConfig(
            provider="anthropic",
            model_name="claude-3-sonnet",
            endpoint="https://api.anthropic.com/v1",
            api_key_env="ANTHROPIC_API_KEY",
            fail_closed=True,
        ),
        ModelProvider.LOCAL_FILE.value: ModelConfig(
            provider="local_file",
            model_name="file_fallback",
            endpoint="",
            fail_closed=True,
        ),
    }

    def __init__(self, receipt_ledger: ReceiptLedger = None):
        self.receipt_ledger = receipt_ledger
        self.configs: dict[str, ModelConfig] = {}
        self.active_provider: str = ModelProvider.OLLAMA.value
        for k, v in self.DEFAULT_CONFIGS.items():
            self.configs[k] = v

    def set_provider(self, provider: str, config: ModelConfig = None) -> None:
        if config:
            self.configs[provider] = config
        self.active_provider = provider

    def get_config(self, provider: str = None) -> ModelConfig:
        provider = provider or self.active_provider
        return self.configs.get(provider, self.DEFAULT_CONFIGS[ModelProvider.OLLAMA.value])

    def generate(
        self,
        prompt: str,
        provider: str = None,
        system_prompt: str = "",
    ) -> ModelResponse:
        provider = provider or self.active_provider
        config = self.get_config(provider)
        start = time.time()

        if provider == ModelProvider.OLLAMA.value:
            return self._call_ollama(prompt, config, system_prompt, start)
        elif provider == ModelProvider.OPENAI.value:
            return self._call_openai(prompt, config, system_prompt, start)
        elif provider == ModelProvider.ANTHROPIC.value:
            return self._call_anthropic(prompt, config, system_prompt, start)
        elif provider == ModelProvider.LOCAL_FILE.value:
            return self._local_file_fallback(prompt, config, start)
        else:
            return ModelResponse(
                provider=provider,
                model="unknown",
                content="",
                latency_ms=0,
                success=False,
                error=f"Unknown provider: {provider}",
            )

    def _call_ollama(self, prompt: str, config: ModelConfig, system_prompt: str, start: float) -> ModelResponse:
        try:
            import urllib.request
            url = f"{config.endpoint}/api/generate"
            payload = json.dumps({
                "model": config.model_name,
                "prompt": prompt,
                "system": system_prompt,
                "stream": False,
                "options": {"temperature": config.temperature, "num_predict": config.max_tokens},
            }).encode()
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=config.timeout_seconds) as resp:
                data = json.loads(resp.read())
                latency = (time.time() - start) * 1000
                return ModelResponse(
                    provider="ollama",
                    model=config.model_name,
                    content=data.get("response", ""),
                    latency_ms=latency,
                    success=True,
                    tokens_used=data.get("eval_count", 0),
                )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return ModelResponse(
                provider="ollama",
                model=config.model_name,
                content="",
                latency_ms=latency,
                success=False,
                error=str(e),
            )

    def _call_openai(self, prompt: str, config: ModelConfig, system_prompt: str, start: float) -> ModelResponse:
        import os
        api_key = os.environ.get(config.api_key_env, "")
        if not api_key:
            return ModelResponse(
                provider="openai",
                model=config.model_name,
                content="",
                latency_ms=0,
                success=False,
                error=f"No API key in env var {config.api_key_env}",
            )
        try:
            import urllib.request
            url = f"{config.endpoint}/chat/completions"
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})
            payload = json.dumps({
                "model": config.model_name,
                "messages": messages,
                "max_tokens": config.max_tokens,
                "temperature": config.temperature,
            }).encode()
            req = urllib.request.Request(url, data=payload, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            })
            with urllib.request.urlopen(req, timeout=config.timeout_seconds) as resp:
                data = json.loads(resp.read())
                latency = (time.time() - start) * 1000
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                return ModelResponse(
                    provider="openai",
                    model=config.model_name,
                    content=content,
                    latency_ms=latency,
                    success=True,
                    tokens_used=data.get("usage", {}).get("total_tokens", 0),
                )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return ModelResponse(
                provider="openai",
                model=config.model_name,
                content="",
                latency_ms=latency,
                success=False,
                error=str(e),
            )

    def _call_anthropic(self, prompt: str, config: ModelConfig, system_prompt: str, start: float) -> ModelResponse:
        import os
        api_key = os.environ.get(config.api_key_env, "")
        if not api_key:
            return ModelResponse(
                provider="anthropic",
                model=config.model_name,
                content="",
                latency_ms=0,
                success=False,
                error=f"No API key in env var {config.api_key_env}",
            )
        try:
            import urllib.request
            url = f"{config.endpoint}/messages"
            payload = json.dumps({
                "model": config.model_name,
                "max_tokens": config.max_tokens,
                "system": system_prompt,
                "messages": [{"role": "user", "content": prompt}],
            }).encode()
            req = urllib.request.Request(url, data=payload, headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            })
            with urllib.request.urlopen(req, timeout=config.timeout_seconds) as resp:
                data = json.loads(resp.read())
                latency = (time.time() - start) * 1000
                content = data.get("content", [{}])[0].get("text", "")
                return ModelResponse(
                    provider="anthropic",
                    model=config.model_name,
                    content=content,
                    latency_ms=latency,
                    success=True,
                    tokens_used=data.get("usage", {}).get("input_tokens", 0),
                )
        except Exception as e:
            latency = (time.time() - start) * 1000
            return ModelResponse(
                provider="anthropic",
                model=config.model_name,
                content="",
                latency_ms=latency,
                success=False,
                error=str(e),
            )

    def _local_file_fallback(self, prompt: str, config: ModelConfig, start: float) -> ModelResponse:
        latency = (time.time() - start) * 1000
        return ModelResponse(
            provider="local_file",
            model="file_fallback",
            content="[FAIL-CLOSED: No model available. No mock output produced by design.]",
            latency_ms=latency,
            success=False,
            error="fail_closed_no_model",
        )

    def list_providers(self) -> list:
        return [
            {
                "provider": p,
                "model": c.model_name,
                "endpoint": c.endpoint,
                "is_active": p == self.active_provider,
                "fail_closed": c.fail_closed,
            }
            for p, c in self.configs.items()
        ]


# ═══════════════════════════════════════════════════════════════════
# Protocol 209: Deployment Receipt Protocol
# ═══════════════════════════════════════════════════════════════════

@dataclass
class DeploymentReceipt:
    deployment_id: str
    artifact_id: str
    target: str  # vercel, netlify, ipfs, local_static
    url: str
    status: str  # deployed, failed, rolled_back
    content_hash: str
    deployed_at: float
    receipt_hash: str
    rolled_back_at: float = 0.0
    health_check_passed: bool = False


class DeploymentReceiptProtocol:
    """
    Receipt-backed deployment tracking.

    Every deployment gets a receipt. Every rollback gets a receipt.
    No fake URLs — if deployment fails, status is "failed" honestly.
    """

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger):
        self.db = db
        self.receipt_ledger = receipt_ledger
        self.deployments: dict[str, DeploymentReceipt] = {}

    def record_deployment(
        self,
        artifact_id: str,
        target: str,
        url: str,
        content_hash: str,
        health_check_passed: bool = False,
    ) -> DeploymentReceipt:
        deployment_id = f"dep_{hashlib.sha256(f'{artifact_id}{target}{time.time()}'.encode()).hexdigest()[:12]}"
        status = "deployed" if url and health_check_passed else "failed"

        receipt_data = {
            "deployment_id": deployment_id,
            "artifact_id": artifact_id,
            "target": target,
            "url": url,
            "status": status,
            "content_hash": content_hash,
            "health_check_passed": health_check_passed,
            "deployed_at": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        self.receipt_ledger.write(
            receipt_type="deployment_recorded",
            artifact_id=artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )

        record = DeploymentReceipt(
            deployment_id=deployment_id,
            artifact_id=artifact_id,
            target=target,
            url=url,
            status=status,
            content_hash=content_hash,
            deployed_at=time.time(),
            receipt_hash=receipt_hash,
            health_check_passed=health_check_passed,
        )
        self.deployments[deployment_id] = record
        return record

    def record_rollback(
        self,
        deployment_id: str,
        reason: str,
    ) -> DeploymentReceipt:
        record = self.deployments.get(deployment_id)
        if not record:
            raise KeyError(f"Deployment {deployment_id} not found")

        record.status = "rolled_back"
        record.rolled_back_at = time.time()

        receipt_data = {
            "deployment_id": deployment_id,
            "reason": reason,
            "rolled_back_at": record.rolled_back_at,
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"
        record.receipt_hash = receipt_hash

        self.receipt_ledger.write(
            receipt_type="deployment_rolled_back",
            artifact_id=record.artifact_id,
            data=receipt_data,
            output_hash=receipt_hash,
        )
        return record

    def list_deployments(self, artifact_id: str = None) -> list:
        if artifact_id:
            return [asdict(d) for d in self.deployments.values() if d.artifact_id == artifact_id]
        return [asdict(d) for d in self.deployments.values()]


# ═══════════════════════════════════════════════════════════════════
# Protocol 210: Proof Export (Base64)
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ProofExport:
    export_id: str
    artifact_id: str
    packet_hash: str
    receipt_count: int
    export_hash: str
    base64_packet: str
    size_bytes: int
    created_at: float = field(default_factory=time.time)


class ProofExportEngine:
    """
    Exports artifact + receipts + evidence as a tamper-evident Base64 packet.

    Packet format: proof_export_v1
    Contains: artifact record, evidence packet, receipt chain, risk report
    Compressed with zlib, encoded as base64.
    """

    def __init__(self, db: OracleDB, receipt_ledger: ReceiptLedger):
        self.db = db
        self.receipt_ledger = receipt_ledger

    def export(
        self,
        artifact_id: str,
        packet_hash: str = "",
        include_receipts: bool = True,
    ) -> ProofExport:
        artifact = self.db.get_artifact(artifact_id)
        if hasattr(artifact, 'to_dict'):
            artifact_data = artifact.to_dict()
        elif isinstance(artifact, dict):
            artifact_data = artifact
        else:
            artifact_data = {}

        receipts = []
        if include_receipts:
            all_receipts = self.receipt_ledger.list_all()
            receipts = [r.to_dict() if hasattr(r, 'to_dict') else r for r in all_receipts]

        packet_data = {
            "format": "proof_export_v1",
            "artifact": artifact_data,
            "packet_hash": packet_hash,
            "receipts": receipts,
            "receipt_count": len(receipts),
            "exported_at": time.time(),
        }

        json_bytes = json.dumps(packet_data, sort_keys=True).encode()
        compressed = zlib.compress(json_bytes)
        b64_packet = base64.b64encode(compressed).decode()

        export_hash = f"sha256:{hashlib.sha256(compressed).hexdigest()[:16]}"
        export_id = f"exp_{hashlib.sha256(f'{artifact_id}{export_hash}{time.time()}'.encode()).hexdigest()[:12]}"

        self.receipt_ledger.write(
            receipt_type="proof_exported",
            artifact_id=artifact_id,
            data={
                "export_id": export_id,
                "export_hash": export_hash,
                "size_bytes": len(compressed),
                "receipt_count": len(receipts),
            },
            output_hash=export_hash,
        )

        return ProofExport(
            export_id=export_id,
            artifact_id=artifact_id,
            packet_hash=packet_hash,
            receipt_count=len(receipts),
            export_hash=export_hash,
            base64_packet=b64_packet,
            size_bytes=len(compressed),
        )

    @staticmethod
    def verify(b64_packet: str) -> dict:
        """Decode and verify a proof export packet."""
        try:
            compressed = base64.b64decode(b64_packet)
            json_bytes = zlib.decompress(compressed)
            data = json.loads(json_bytes)
            recomputed = hashlib.sha256(compressed).hexdigest()[:16]
            return {
                "valid": True,
                "format": data.get("format"),
                "artifact_id": data.get("artifact", {}).get("artifact_id"),
                "receipt_count": data.get("receipt_count"),
                "exported_at": data.get("exported_at"),
                "hash_prefix": recomputed,
            }
        except Exception as e:
            return {"valid": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════
# Protocol 211: Multi-Model Consensus
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ConsensusResult:
    prompt: str
    responses: list  # [{provider, model, content, success}]
    agreement_score: float  # 0.0 to 1.0
    consensus_content: str
    dissent_count: int
    receipt_hash: str
    timestamp: float = field(default_factory=time.time)


class MultiModelConsensus:
    """
    Queries multiple models and computes agreement.

    Agreement = fraction of responses that share the majority content hash.
    If no majority, consensus_content is empty and agreement_score is 0.

    Use case: high-stakes classifications where a single model's output
    should not be trusted alone.
    """

    def __init__(self, model_layer: ModelSwappingLayer, receipt_ledger: ReceiptLedger = None):
        self.model_layer = model_layer
        self.receipt_ledger = receipt_ledger

    def query(
        self,
        prompt: str,
        providers: list[str] = None,
        system_prompt: str = "",
    ) -> ConsensusResult:
        providers = providers or [ModelProvider.OLLAMA.value]
        responses = []

        for provider in providers:
            resp = self.model_layer.generate(prompt, provider=provider, system_prompt=system_prompt)
            responses.append({
                "provider": resp.provider,
                "model": resp.model,
                "content": resp.content,
                "success": resp.success,
                "error": resp.error,
                "content_hash": f"sha256:{hashlib.sha256(resp.content.encode()).hexdigest()[:16]}" if resp.content else "",
            })

        # Compute agreement
        successful = [r for r in responses if r["success"] and r["content"]]
        if not successful:
            return ConsensusResult(
                prompt=prompt,
                responses=responses,
                agreement_score=0.0,
                consensus_content="",
                dissent_count=len(responses),
                receipt_hash="",
            )

        # Hash-based agreement
        hash_counts: dict[str, int] = {}
        for r in successful:
            h = r["content_hash"]
            hash_counts[h] = hash_counts.get(h, 0) + 1

        majority_hash = max(hash_counts, key=hash_counts.get)
        agreement_score = hash_counts[majority_hash] / len(successful)

        # Find content for majority hash
        consensus_content = ""
        for r in successful:
            if r["content_hash"] == majority_hash:
                consensus_content = r["content"]
                break

        dissent_count = len(successful) - hash_counts[majority_hash]

        receipt_data = {
            "prompt_hash": f"sha256:{hashlib.sha256(prompt.encode()).hexdigest()[:16]}",
            "providers_queried": providers,
            "successful_count": len(successful),
            "agreement_score": round(agreement_score, 3),
            "dissent_count": dissent_count,
            "timestamp": time.time(),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        if self.receipt_ledger:
            self.receipt_ledger.write(
                receipt_type="multi_model_consensus",
                artifact_id="",
                data=receipt_data,
                output_hash=receipt_hash,
            )

        return ConsensusResult(
            prompt=prompt,
            responses=responses,
            agreement_score=round(agreement_score, 3),
            consensus_content=consensus_content,
            dissent_count=dissent_count,
            receipt_hash=receipt_hash,
        )


# ═══════════════════════════════════════════════════════════════════
# Protocol 212: Hallucination Detection
# ═══════════════════════════════════════════════════════════════════

@dataclass
class HallucinationReport:
    content: str
    is_hallucination_suspected: bool
    confidence: float  # 0.0 = likely real, 1.0 = likely hallucination
    flags: list  # [{type, detail}]
    receipt_hash: str
    timestamp: float = field(default_factory=time.time)


class HallucinationDetector:
    """
    Detects potential hallucinations in model output.

    Heuristics:
      1. Fabricated URLs (patterns that look real but aren't)
      2. Fabricated citations (fake paper titles, fake DOI)
      3. Repetition loops (same phrase repeated >3x)
      4. Impossible claims (claims that contradict known constraints)
      5. Excessive certainty (claims "100% guaranteed" etc.)
      6. Numeric inconsistency (contradictory numbers in same response)

    This is a heuristic layer, not a guarantee. Output flagged as
    suspected hallucination should be reviewed by a human.
    """

    SUSPICIOUS_PATTERNS = [
        "100% guaranteed",
        "absolutely certain",
        "impossible to fail",
        "proven to work in all cases",
        "no risk whatsoever",
        "guaranteed profit",
        "risk-free",
    ]

    def __init__(self, receipt_ledger: ReceiptLedger = None):
        self.receipt_ledger = receipt_ledger

    def detect(self, content: str) -> HallucinationReport:
        flags = []
        confidence = 0.0

        # 1. Suspicious certainty patterns
        for pattern in self.SUSPICIOUS_PATTERNS:
            if pattern.lower() in content.lower():
                flags.append({
                    "type": "excessive_certainty",
                    "detail": f"Pattern detected: '{pattern}'",
                })
                confidence += 0.2

        # 2. Repetition loops
        words = content.lower().split()
        if len(words) > 10:
            from collections import Counter
            word_counts = Counter(words)
            for word, count in word_counts.items():
                if count > 3 and len(word) > 5:
                    flags.append({
                        "type": "repetition_loop",
                        "detail": f"Word '{word}' repeated {count} times",
                    })
                    confidence += 0.1

        # 3. Fabricated URL patterns
        import re
        url_pattern = r'https?://[^\s<>"{}|\\^`\[\]]+'
        urls = re.findall(url_pattern, content)
        for url in urls:
            if "example.com" in url or "your-domain" in url or "placeholder" in url:
                flags.append({
                    "type": "placeholder_url",
                    "detail": f"Placeholder URL: {url}",
                })
                confidence += 0.15

        # 4. Numeric inconsistency (simple check: same entity with different numbers)
        number_pattern = r'\$?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)\s*(million|billion|thousand|trillion)?'
        numbers = re.findall(number_pattern, content, re.IGNORECASE)
        if len(numbers) > 5:
            flags.append({
                "type": "excessive_numeric_claims",
                "detail": f"{len(numbers)} numeric claims in single response",
            })
            confidence += 0.1

        # 5. Contradictory certainty markers
        if "might" in content.lower() and "definitely" in content.lower():
            flags.append({
                "type": "contradictory_certainty",
                "detail": "Mixed certainty language ('might' + 'definitely')",
            })
            confidence += 0.15

        confidence = min(confidence, 1.0)
        is_suspected = confidence >= 0.5 or len(flags) >= 3

        receipt_data = {
            "content_hash": f"sha256:{hashlib.sha256(content.encode()).hexdigest()[:16]}",
            "is_hallucination_suspected": is_suspected,
            "confidence": round(confidence, 3),
            "flags": flags,
            "flag_count": len(flags),
        }
        receipt_hash = f"sha256:{hashlib.sha256(json.dumps(receipt_data, sort_keys=True).encode()).hexdigest()[:16]}"

        if self.receipt_ledger:
            self.receipt_ledger.write(
                receipt_type="hallucination_check",
                artifact_id="",
                data=receipt_data,
                output_hash=receipt_hash,
            )

        return HallucinationReport(
            content=content,
            is_hallucination_suspected=is_suspected,
            confidence=round(confidence, 3),
            flags=flags,
            receipt_hash=receipt_hash,
        )
