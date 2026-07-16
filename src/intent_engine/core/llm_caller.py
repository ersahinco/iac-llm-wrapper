"""LLM caller with pluggable backend for structured extraction."""

from __future__ import annotations

import json
import math
import os
import subprocess
import time
from abc import ABC, abstractmethod
from typing import Any

import requests
from pydantic import BaseModel, ConfigDict, Field, field_validator

_RETRYABLE_HTTP_STATUSES = {429, 500, 502, 503, 504}
_TOKEN_KEYS = {
    "prompt_tokens": "prompt_tokens",
    "completion_tokens": "completion_tokens",
    "total_tokens": "total_tokens",
}
_BEDROCK_TOKEN_KEYS = {
    "inputTokens": "prompt_tokens",
    "outputTokens": "completion_tokens",
    "totalTokens": "total_tokens",
}


class _ProviderModel(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


class _OpenAIMessage(_ProviderModel):
    content: str

    @field_validator("content")
    @classmethod
    def _usable_content(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content must contain text")
        return value


class _OpenAIChoice(_ProviderModel):
    message: _OpenAIMessage


class _OpenAIResponse(_ProviderModel):
    choices: list[_OpenAIChoice] = Field(min_length=1)
    usage: Any = None


class _BedrockContentBlock(_ProviderModel):
    text: str | None = None


class _BedrockMessage(_ProviderModel):
    content: list[_BedrockContentBlock] = Field(min_length=1)


class _BedrockOutput(_ProviderModel):
    message: _BedrockMessage


class _BedrockResponse(_ProviderModel):
    output: _BedrockOutput
    usage: Any = None


def _token_usage(value: Any, keys: dict[str, str]) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    usage: dict[str, int] = {}
    for source, target in keys.items():
        token_count = value.get(source)
        if type(token_count) is int and token_count >= 0:
            usage[target] = token_count
    return usage


def _retry_attempts(value: Any) -> int:
    if type(value) is not int or not 1 <= value <= 5:
        raise ValueError("max_retries must be an integer from 1 to 5")
    return value


def _retry_delay(response: requests.Response | None, attempt: int) -> float:
    fallback: float = min(30.0, 0.5 * float(2**attempt))
    if response is None:
        return fallback
    raw = response.headers.get("Retry-After")
    if raw is None:
        return fallback
    try:
        delay = float(raw)
    except ValueError:
        return fallback
    return min(delay, 30.0) if math.isfinite(delay) and delay >= 0 else fallback


class LLMBackend(ABC):
    """Abstract base class for LLM backends."""

    last_token_usage: dict[str, int]

    @abstractmethod
    def complete(self, prompt: str, **kwargs: Any) -> str:
        """Send a completion request and return the response text."""
        ...


class OpenAICompatibleBackend(LLMBackend):
    """OpenAI-compatible REST API backend."""

    def __init__(
        self,
        base_url: str = "https://api.openai.com/v1",
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        timeout: int = 180,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.model = model
        self.timeout = timeout
        self.last_token_usage: dict[str, int] = {}

    def complete(self, prompt: str, **kwargs: Any) -> str:
        self.last_token_usage = {}
        headers: dict[str, str] = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": kwargs.get("model", self.model),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": kwargs.get("temperature", 0.1),
        }

        if kwargs.get("max_tokens"):
            payload["max_tokens"] = kwargs["max_tokens"]

        endpoint = f"{self.base_url}/chat/completions"

        timeout = kwargs.get("timeout", self.timeout)
        max_retries = _retry_attempts(kwargs.get("max_retries", 3))

        last_exc: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    endpoint,
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                )
                try:
                    response.raise_for_status()
                except requests.exceptions.HTTPError as exc:
                    if response.status_code not in _RETRYABLE_HTTP_STATUSES:
                        raise
                    last_exc = exc
                    if attempt < max_retries - 1:
                        time.sleep(_retry_delay(response, attempt))
                    continue
                data = _OpenAIResponse.model_validate(response.json())
                self.last_token_usage = _token_usage(data.usage, _TOKEN_KEYS)
                return data.choices[0].message.content
            except requests.exceptions.Timeout as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    time.sleep(_retry_delay(None, attempt))
                    continue
            except requests.exceptions.ConnectionError as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    time.sleep(_retry_delay(None, attempt))
                    continue

        if last_exc:
            raise last_exc
        raise RuntimeError("Unexpected: retries exhausted without result")


class BedrockCliBackend(LLMBackend):
    """Amazon Bedrock Converse backend using the local AWS CLI."""

    def __init__(
        self,
        model: str = "eu.amazon.nova-2-lite-v1:0",
        region: str | None = None,
        timeout: int = 180,
    ) -> None:
        self.model = model
        self.region = (
            region
            or os.environ.get("INTENT_ENGINE_AWS_REGION")
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or "eu-central-1"
        )
        self.timeout = timeout
        self.last_token_usage: dict[str, int] = {}

    def complete(self, prompt: str, **kwargs: Any) -> str:
        self.last_token_usage = {}
        inference_config = {
            "maxTokens": int(kwargs.get("max_tokens") or 4096),
            "temperature": float(kwargs.get("temperature", 0.1)),
        }
        messages = [{"role": "user", "content": [{"text": prompt}]}]
        result = subprocess.run(
            [
                "aws",
                "bedrock-runtime",
                "converse",
                "--region",
                self.region,
                "--model-id",
                str(kwargs.get("model") or self.model),
                "--messages",
                json.dumps(messages),
                "--inference-config",
                json.dumps(inference_config),
                "--output",
                "json",
            ],
            capture_output=True,
            text=True,
            timeout=kwargs.get("timeout", self.timeout),
            check=False,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(detail or f"Bedrock CLI exited with {result.returncode}")

        data = _BedrockResponse.model_validate(json.loads(result.stdout))
        self.last_token_usage = _token_usage(data.usage, _BEDROCK_TOKEN_KEYS)
        text_parts = [
            part.text for part in data.output.message.content if part.text and part.text.strip()
        ]
        if not text_parts:
            raise ValueError("Bedrock response did not contain usable text content")
        return "\n".join(text_parts)


class LLMEvidence:
    """Captures LLM call metadata for audit/debugging."""

    def __init__(
        self,
        prompt: str,
        response: str,
        model: str,
        latency_ms: float,
        backend: str,
        parse_error: str | None = None,
        token_usage: dict[str, int] | None = None,
    ) -> None:
        self.prompt = prompt
        self.response = response
        self.model = model
        self.latency_ms = latency_ms
        self.backend = backend
        self.parse_error = parse_error
        self.token_usage = token_usage or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "response": self.response,
            "model": self.model,
            "latency_ms": self.latency_ms,
            "backend": self.backend,
            "parse_error": self.parse_error,
            "token_usage": self.token_usage,
        }


class LLMEvidenceStore:
    """Stores LLM evidence per compilation run."""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []

    def record(self, evidence: LLMEvidence) -> None:
        self.entries.append(evidence.to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {"calls": self.entries}


class LLMCaller:
    """High-level LLM orchestration with pluggable backend and evidence tracking."""

    def __init__(self, backend: LLMBackend | None = None) -> None:
        self.backend = backend or OpenAICompatibleBackend()

    def call(self, prompt: str, **kwargs: Any) -> tuple[str, LLMEvidence]:
        import time

        start = time.perf_counter()
        try:
            response = self.backend.complete(prompt, **kwargs)
        except Exception as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            evidence = LLMEvidence(
                prompt=prompt,
                response="",
                model=getattr(self.backend, "model", "unknown"),
                latency_ms=latency_ms,
                backend=self.backend.__class__.__name__,
                parse_error=str(exc),
            )
            return "", evidence

        latency_ms = (time.perf_counter() - start) * 1000

        token_usage: dict[str, int] = {}
        backend_usage = getattr(self.backend, "last_token_usage", {})
        token_usage = _token_usage(backend_usage, _TOKEN_KEYS)

        evidence = LLMEvidence(
            prompt=prompt,
            response=response,
            model=getattr(self.backend, "model", "unknown"),
            latency_ms=latency_ms,
            backend=self.backend.__class__.__name__,
            token_usage=token_usage,
        )
        return response, evidence


def create_llm_caller(
    provider: str = "",
    api_key: str = "",
    base_url: str = "",
    model: str = "",
) -> LLMCaller | None:
    """Build an explicitly configured, model-pinned LLM caller."""
    if os.environ.get("INTENT_ENGINE_DISABLE_LLM") or not provider:
        return None
    if not model:
        raise ValueError("LLM use requires an explicit model name")

    backend_kwargs: dict[str, Any] = {"model": model}
    if provider == "openai":
        if not api_key and not os.environ.get("OPENAI_API_KEY") and not base_url:
            raise ValueError("OpenAI-compatible LLM use requires an API key or custom base URL")
        if api_key:
            backend_kwargs["api_key"] = api_key
        if base_url:
            backend_kwargs["base_url"] = base_url
    elif provider == "ollama":
        backend_kwargs["base_url"] = base_url or "http://localhost:11434/v1"
    return LLMCaller(create_backend(provider, **backend_kwargs))


def create_backend(
    provider: str = "openai",
    **kwargs: Any,
) -> LLMBackend:
    """Factory for LLM backends by provider name."""
    if provider == "openai":
        return OpenAICompatibleBackend(**kwargs)
    if provider == "ollama":
        base_url = kwargs.pop("base_url", "http://localhost:11434/v1")
        return OpenAICompatibleBackend(base_url=base_url, **kwargs)
    if provider == "bedrock":
        return BedrockCliBackend(**kwargs)
    raise ValueError(f"Unknown provider: {provider}")
