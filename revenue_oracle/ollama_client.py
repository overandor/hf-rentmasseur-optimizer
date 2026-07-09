"""
Ollama Client — real local Ollama API client.

Default host: http://localhost:11434
Default API base: http://localhost:11434/api
Default generation endpoint: POST /api/generate

If Ollama is unavailable, fail closed with a clear error.
Never return mock model output as if it came from Ollama.
"""

import json
import time
import urllib.request
import urllib.parse
import urllib.error
from dataclasses import dataclass
from typing import Optional


@dataclass
class OllamaResponse:
    model: str
    response: str
    done: bool
    context: list = None
    total_duration: int = 0
    load_duration: int = 0
    prompt_eval_count: int = 0
    eval_count: int = 0
    created_at: float = 0.0

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "response": self.response,
            "done": self.done,
            "context": self.context or [],
            "total_duration": self.total_duration,
            "load_duration": self.load_duration,
            "prompt_eval_count": self.prompt_eval_count,
            "eval_count": self.eval_count,
            "created_at": self.created_at,
        }


class OllamaClient:
    """Real Ollama API client. Fails closed when Ollama is unavailable."""

    DEFAULT_HOST = "http://localhost:11434"
    DEFAULT_API_BASE = "http://localhost:11434/api"
    DEFAULT_MODEL = "llama3.2"
    TIMEOUT = 60

    def __init__(self, host: str = "", model: str = "", timeout: int = 0):
        self.host = host or self.DEFAULT_HOST
        self.api_base = self.host.rstrip("/") + "/api"
        self.model = model or self.DEFAULT_MODEL
        self.timeout = timeout or self.TIMEOUT

    def is_available(self) -> bool:
        """Check if Ollama is running and reachable."""
        try:
            url = f"{self.api_base}/tags"
            req = urllib.request.Request(url, headers={"User-Agent": "RevenueOracle/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return "models" in data
        except Exception:
            return False

    def list_models(self) -> list:
        """List available Ollama models."""
        try:
            url = f"{self.api_base}/tags"
            req = urllib.request.Request(url, headers={"User-Agent": "RevenueOracle/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return [m.get("name", "") for m in data.get("models", [])]
        except Exception:
            return []

    def generate(self, prompt: str, model: str = "", stream: bool = False,
                 context: list = None, options: dict = None) -> OllamaResponse:
        """
        Generate text using Ollama's /api/generate endpoint.

        Fails closed — raises ConnectionError if Ollama is unreachable.
        Never returns mock output.
        """
        use_model = model or self.model
        payload = {
            "model": use_model,
            "prompt": prompt,
            "stream": False,
        }
        if context:
            payload["context"] = context
        if options:
            payload["options"] = options

        url = f"{self.api_base}/generate"
        body = json.dumps(payload).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "RevenueOracle/1.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode()
                data = json.loads(raw)
                return OllamaResponse(
                    model=data.get("model", use_model),
                    response=data.get("response", ""),
                    done=data.get("done", True),
                    context=data.get("context", []),
                    total_duration=data.get("total_duration", 0),
                    load_duration=data.get("load_duration", 0),
                    prompt_eval_count=data.get("prompt_eval_count", 0),
                    eval_count=data.get("eval_count", 0),
                    created_at=time.time(),
                )
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Ollama is not reachable at {self.api_base}. "
                f"Start Ollama with `ollama serve` or check the host. Error: {e}"
            )
        except Exception as e:
            raise ConnectionError(
                f"Ollama request failed: {e}. "
                f"Ensure Ollama is running and model '{use_model}' is available."
            )

    def classify_artifact(self, artifact_data: dict) -> dict:
        """
        Ask Ollama to summarize and classify an artifact.

        Returns a dict with: summary, category, risk_assessment, suggested_claims.
        """
        prompt = f"""You are an evidence asset classifier. Analyze this artifact and respond in JSON only.

Artifact data:
{json.dumps(artifact_data, indent=2, default=str)[:4000]}

Respond with this exact JSON structure:
{{
  "summary": "one-line description of what this artifact is",
  "category": "one of: software, media, research, credential, dataset, receipt, other",
  "risk_assessment": "one of: low, medium, high, critical",
  "suggested_claims": ["list of factual claims that can be verified from this artifact"],
  "revenue_potential": "one of: none, report_sale, license_sale, api_access, consulting, sponsorship"
}}"""

        resp = self.generate(prompt)
        try:
            result = json.loads(resp.response.strip())
        except json.JSONDecodeError:
            text = resp.response.strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(text[start:end])
            else:
                result = {
                    "summary": "Classification failed — model did not return valid JSON",
                    "category": "other",
                    "risk_assessment": "medium",
                    "suggested_claims": [],
                    "revenue_potential": "none",
                }

        result["model"] = resp.model
        result["model_digest"] = ""
        result["runtime_ms"] = resp.total_duration // 1_000_000 if resp.total_duration else 0
        return result

    def status(self) -> dict:
        """Get Ollama connection status."""
        available = self.is_available()
        models = self.list_models() if available else []
        return {
            "available": available,
            "host": self.host,
            "api_base": self.api_base,
            "default_model": self.model,
            "models": models,
        }
