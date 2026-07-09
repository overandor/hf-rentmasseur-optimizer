"""
Multi-provider LLM client — Transformers.js (local), Ollama, Groq, OpenRouter.

Providers (tried in order by generate_with_fallback):
  1. transformers — local Node.js model via @huggingface/transformers (FREE, no API key)
  2. ollama — local Ollama server
  3. groq — Groq cloud API
  4. openrouter — OpenRouter cloud API

Environment variables:
  - TRANSFORMERS_LLM_PATH (default: rm_traffic/transformers_llm.js)
  - TRANSFORMERS_MODEL (default: Xenova/Qwen2.5-0.5B-Instruct)
  - OLLAMA_URL (default: http://localhost:11434/api/generate)
  - GROQ_API_KEY
  - OPENROUTER_API_KEY

Usage:
    from rm_traffic.llm_client import LLMClient
    client = LLMClient(provider="transformers")
    response = client.generate(prompt)
"""

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

import requests

log = logging.getLogger("llm_client")

DEFAULT_OLLAMA_URL = "http://localhost:11434/api/generate"


class LLMClient:
    """Unified LLM client supporting Ollama, Groq, and OpenRouter."""

    def __init__(self, provider: str = "ollama", model: Optional[str] = None):
        self.provider = provider.lower().strip()
        self.model = model or self._default_model()
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "ProfileOps/1.0",
            "Accept": "application/json",
        })

    def _default_model(self) -> str:
        defaults = {
            "transformers": os.environ.get("TRANSFORMERS_MODEL", "Xenova/Qwen2.5-0.5B-Instruct"),
            "ollama": "llama3.2",
            "groq": "llama-3.1-8b-instant",
            "openrouter": "meta-llama/llama-3.1-8b-instruct",
        }
        return defaults.get(self.provider, "llama3.2")

    def _transformers_generate(self, prompt: str, max_tokens: int = 800) -> Optional[str]:
        """Generate text using local transformers.js model via Node.js."""
        script_path = os.environ.get(
            "TRANSFORMERS_LLM_PATH",
            str(Path(__file__).parent / "transformers_llm.js"),
        )
        if not os.path.exists(script_path):
            log.error("transformers_llm.js not found at %s", script_path)
            return None
        try:
            proc = subprocess.run(
                ["node", script_path, "--model", self.model, "--max-tokens", str(max_tokens)],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(Path(__file__).parent.parent),
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return proc.stdout.strip()
            log.error("transformers.js error: %s", proc.stderr[:300])
            return None
        except subprocess.TimeoutExpired:
            log.error("transformers.js timed out (30s)")
            return None
        except Exception as e:
            log.error("transformers.js failed: %s", e)
            return None

    def _ollama_generate(self, prompt: str, max_tokens: int = 800) -> Optional[str]:
        url = os.environ.get("OLLAMA_URL", DEFAULT_OLLAMA_URL)
        try:
            resp = self.session.post(url, json={
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.75,
                    "num_predict": max_tokens,
                }
            }, timeout=120)
            if resp.status_code == 200:
                return resp.json().get("response", "")
            log.error("Ollama error: %d %s", resp.status_code, resp.text[:300])
            return None
        except Exception as e:
            log.error("Ollama failed: %s", e)
            return None

    def _groq_generate(self, prompt: str, max_tokens: int = 800) -> Optional[str]:
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            log.error("GROQ_API_KEY not set")
            return None
        try:
            resp = self.session.post("https://api.groq.com/openai/v1/chat/completions", json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.75,
                "max_tokens": max_tokens,
            }, headers={"Authorization": f"Bearer {key}"}, timeout=60)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            log.error("Groq error: %d %s", resp.status_code, resp.text[:300])
            return None
        except Exception as e:
            log.error("Groq failed: %s", e)
            return None

    def _openrouter_generate(self, prompt: str, max_tokens: int = 800) -> Optional[str]:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            log.error("OPENROUTER_API_KEY not set")
            return None
        try:
            resp = self.session.post("https://openrouter.ai/api/v1/chat/completions", json={
                "model": self.model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.75,
                "max_tokens": max_tokens,
            }, headers={
                "Authorization": f"Bearer {key}",
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "ProfileOps",
            }, timeout=60)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            log.error("OpenRouter error: %d %s", resp.status_code, resp.text[:300])
            return None
        except Exception as e:
            log.error("OpenRouter failed: %s", e)
            return None

    def generate(self, prompt: str, max_tokens: int = 800) -> Optional[str]:
        """Generate text from the configured provider."""
        log.info("Generating with %s/%s", self.provider, self.model)
        start = time.time()
        if self.provider == "transformers":
            result = self._transformers_generate(prompt, max_tokens)
        elif self.provider == "ollama":
            result = self._ollama_generate(prompt, max_tokens)
        elif self.provider == "groq":
            result = self._groq_generate(prompt, max_tokens)
        elif self.provider == "openrouter":
            result = self._openrouter_generate(prompt, max_tokens)
        else:
            log.error("Unknown provider: %s", self.provider)
            return None
        log.info("LLM response in %.1fs", time.time() - start)
        return result


# ---------------------------------------------------------------------------
# Convenience: try multiple providers in order
# ---------------------------------------------------------------------------

_PROVIDERS_CACHE = None
_CLIENTS_CACHE = {}


def _get_providers():
    global _PROVIDERS_CACHE
    if _PROVIDERS_CACHE is not None:
        return _PROVIDERS_CACHE
    providers = []
    tf_script = os.environ.get(
        "TRANSFORMERS_LLM_PATH",
        str(Path(__file__).parent / "transformers_llm.js"),
    )
    if os.path.exists(tf_script):
        providers.append(("transformers", os.environ.get("TRANSFORMERS_MODEL", "Xenova/Qwen2.5-0.5B-Instruct")))
    if os.environ.get("OLLAMA_URL") or os.environ.get("LLM_PROVIDER") == "ollama":
        providers.append(("ollama", "llama3.2"))
    if os.environ.get("GROQ_API_KEY"):
        providers.append(("groq", "llama-3.1-8b-instant"))
    if os.environ.get("OPENROUTER_API_KEY"):
        providers.append(("openrouter", "meta-llama/llama-3.1-8b-instruct"))
    if not providers:
        providers.append(("transformers", "Xenova/Qwen2.5-0.5B-Instruct"))
    _PROVIDERS_CACHE = providers
    return providers


def _get_client(provider: str, model: str) -> "LLMClient":
    key = (provider, model)
    if key not in _CLIENTS_CACHE:
        _CLIENTS_CACHE[key] = LLMClient(provider, model)
    return _CLIENTS_CACHE[key]


def generate_with_fallback(prompt: str, max_tokens: int = 800) -> Optional[str]:
    """Try Transformers.js (local, free), then Ollama, then Groq, then OpenRouter."""
    for provider, model in _get_providers():
        client = _get_client(provider, model)
        result = client.generate(prompt, max_tokens)
        if result:
            return result
    log.error("All LLM providers failed")
    return None
