"""Optional real-LLM integration tests for current product patterns."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from intent_engine.core.compiler import CompileError, compile_design
from intent_engine.core.extractor import Extractor
from intent_engine.core.llm_caller import LLMCaller, LLMEvidenceStore, create_backend
from intent_engine.core.patterns import GLOBAL_REGISTRY

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"


def _ollama_available() -> bool:
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=2.0)
        return resp.status_code == 200
    except Exception:
        return False


OLLAMA_AVAILABLE = _ollama_available()


@pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
class TestRealLLMExtract:
    @pytest.fixture(scope="class")
    def llm_caller(self) -> LLMCaller:
        backend = create_backend("ollama", base_url="http://localhost:11434/v1")
        return LLMCaller(backend)

    def test_aws_lza_pipeline_runs_without_crash(self, llm_caller: LLMCaller, tmp_path: Path):
        output = tmp_path / "output"
        compile_design(
            FIXTURES / "usability" / "engineer-handoff-lza.md",
            output,
            llm_caller=llm_caller,
            pattern="aws-lza",
        )
        assert (output / "decision-report.yaml").exists()
        assert (output / "lineage-manifest.yaml").exists()

    def test_prompt_contains_graph_context(self):
        graph = GLOBAL_REGISTRY.get("aws-lza").create_graph()
        prompt = Extractor(graph=graph, pattern="aws-lza").build_prompt("Design doc text here")

        assert "TRAVERSE the requirement graph" in prompt
        assert "applies_when" in prompt or "Applies when" in prompt
        assert "SIGNALS" in prompt
        assert "decisions" in prompt
        assert "signal_decisions" in prompt

    def test_llm_returns_parseable_structured_json(self, llm_caller: LLMCaller):
        graph = GLOBAL_REGISTRY.get("aws-lza").create_graph()
        extractor = Extractor(graph=graph, pattern="aws-lza")
        text = (
            "# AWS LZA Design\n\n"
            "## Regions\n- home_region: eu-west-1\n\n"
            "## Network\n- topology: hub-spoke\n- network_account: Network\n"
        )
        response, evidence = llm_caller.call(extractor.build_prompt(text))
        if not response:
            pytest.skip(f"LLM returned empty response: {evidence.parse_error}")

        result = extractor.parse_response(response)
        assert isinstance(result.decisions, dict)
        assert "eu-west-1" in response.lower() or len(result.decisions) > 0

    def test_harness_catches_missing_hub_spoke_account(self, tmp_path: Path):
        output = tmp_path / "output"
        design = tmp_path / "design.md"
        design.write_text("# Design\n\n## Network\n- topology: hub-spoke\n")

        with pytest.raises(CompileError) as exc_info:
            compile_design(design, output, llm_caller=None, pattern="aws-lza")

        codes = {v.code for v in exc_info.value.violations}
        assert "AWS_LZA_NETWORK_ACCOUNT_REQUIRED" in codes

    def test_evidence_store_records_llm_call(self, llm_caller: LLMCaller, tmp_path: Path):
        evidence_store = LLMEvidenceStore()
        output = tmp_path / "output"
        compile_design(
            FIXTURES / "usability" / "engineer-handoff-lza.md",
            output,
            llm_caller=llm_caller,
            evidence_store=evidence_store,
            pattern="aws-lza",
        )

        assert evidence_store.entries
        entry = evidence_store.entries[0]
        assert "prompt" in entry
        assert "response" in entry
        assert "latency_ms" in entry
        assert "backend" in entry
