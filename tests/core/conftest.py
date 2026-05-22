"""Shared pytest fixtures for intent-engine tests."""

from __future__ import annotations

import pytest

from intent_engine.core.llm_caller import LLMBackend, LLMCaller


class MockLLMBackend(LLMBackend):
    """Mock LLM backend that returns a fixed response."""

    def __init__(self, response: str = '{"primary_region": "eu-west-1"}') -> None:
        self.response = response
        self.calls: list[dict] = []

    def complete(self, prompt: str, **kwargs):
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.response


@pytest.fixture
def mock_llm_caller() -> LLMCaller:
    """Create an LLMCaller backed by MockLLMBackend."""
    backend = MockLLMBackend()
    return LLMCaller(backend)
