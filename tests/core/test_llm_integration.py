"""Integration tests using a real LLM (Ollama) to verify the full pipeline.

These tests accept non-determinism. They verify pipeline integrity — that the
LLM traverses the graph, the harness applies gates/defaults, and the output
is structurally valid — not exact field values.

Skipped automatically when no local LLM is available.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from intent_engine.core.compiler import compile_design
from intent_engine.core.extractor import Extractor
from intent_engine.core.llm_caller import LLMCaller, create_backend
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
    """Verify LLM graph traversal with real Ollama backend."""

    @pytest.fixture(scope="class")
    def llm_caller(self) -> LLMCaller:
        backend = create_backend("ollama", base_url="http://localhost:11434/v1")
        return LLMCaller(backend)

    def test_pipeline_runs_without_crash(self, llm_caller: LLMCaller, tmp_path: Path):
        """The full compile pipeline runs end-to-end with a real LLM."""
        output = tmp_path / "output"
        graph = GLOBAL_REGISTRY.get("minimal").create_graph()
        compile_design(
            FIXTURES / "valid-payments.md",
            output,
            graph=graph,
            llm_caller=llm_caller,
        )
        assert output.exists()
        assert (output / "decision-report.yaml").exists()

    def test_llm_prompt_contains_graph_context(self, llm_caller: LLMCaller):
        """The prompt sent to the LLM includes graph traversal instructions."""
        graph = GLOBAL_REGISTRY.get("minimal").create_graph()
        extractor = Extractor(graph=graph)
        prompt = extractor.build_prompt("Design doc text here")

        assert "TRAVERSE the requirement graph" in prompt
        assert "applies_if" in prompt or "Applies only when" in prompt
        assert "SIGNALS" in prompt
        assert "ADDONS" in prompt
        assert "decisions" in prompt
        assert "signal_decisions" in prompt

    def test_llm_returns_structured_json(self, llm_caller: LLMCaller):
        """The real LLM returns parseable structured JSON."""
        graph = GLOBAL_REGISTRY.get("minimal").create_graph()
        extractor = Extractor(graph=graph)
        text = (
            "# AWS Landing Zone Design\n\n"
            "## Region\n- primary: eu-west-1\n\n"
            "## Topology\n- single-vpc\n\n"
            "## Network\n- cidr: 10.0.0.0/16\n\n"
            "## Security\n- audit_retention_days: 2555\n"
        )
        prompt = extractor.build_prompt(text)
        response, evidence = llm_caller.call(prompt)

        # Accept empty response as a backend failure — pipeline still runs
        if not response:
            pytest.skip(f"LLM returned empty response: {evidence.parse_error}")

        # Must be parseable
        result = extractor.parse_response(response)
        assert isinstance(result.decisions, dict)
        # The LLM should extract at least the explicitly mentioned region
        assert "eu-west-1" in response.lower() or len(result.decisions) > 0

    def test_harness_applies_gates_and_defaults(self, llm_caller: LLMCaller, tmp_path: Path):
        """After LLM extraction, the harness fills gaps and applies defaults."""
        output = tmp_path / "output"
        graph = GLOBAL_REGISTRY.get("baseline").create_graph()
        compile_design(
            FIXTURES / "valid-payments.md",
            output,
            graph=graph,
            llm_caller=llm_caller,
        )

        report_path = output / "decision-report.yaml"
        assert report_path.exists()

        import ruamel.yaml

        yaml = ruamel.yaml.YAML(typ="safe")
        with open(report_path) as f:
            report = yaml.load(f)

        # Normalizer defaults should always be present
        assert report.get("primaryRegion") is not None
        assert report.get("security", {}).get("auditRetentionDays") is not None
        assert report.get("security", {}).get("kmsRotationRequired") in (True, False)

    def test_harness_catches_missing_hub_spoke_fields(self, llm_caller: LLMCaller, tmp_path: Path):
        """If the graph decides hub-spoke without a Network account,
        the validator catches it deterministically."""
        from intent_engine.core.compiler import CompileError

        output = tmp_path / "output"
        # Use baseline graph which has the central_network_account requirement
        graph = GLOBAL_REGISTRY.get("baseline").create_graph()
        # Manually decide hub-spoke to trigger the validation
        graph.decide("topology", "hub-spoke")
        graph.apply_defaults_for_remaining()

        # Create a fake design doc
        design = tmp_path / "design.md"
        design.write_text("# Design\n- topology: hub-spoke\n")

        with pytest.raises(CompileError) as exc_info:
            compile_design(design, output, graph=graph, llm_caller=None)

        codes = {v.code for v in exc_info.value.violations}
        assert "HUB_SPOKE_NETWORK_ACCOUNT_REQUIRED" in codes


@pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
class TestRealLLMGraphTraversal:
    """Verify that the LLM prompt guides graph traversal behavior."""

    def test_graph_context_includes_dependencies(self):
        graph = GLOBAL_REGISTRY.get("baseline").create_graph()
        extractor = Extractor(graph=graph)
        prompt = extractor.build_prompt("test")

        # The prompt should describe dependencies so the LLM knows ordering
        assert "Depends on:" in prompt
        # The prompt should describe conditional applicability
        assert "Applies only when" in prompt or "applies_if" in prompt

    def test_graph_context_includes_signals(self):
        graph = GLOBAL_REGISTRY.get("baseline").create_graph()
        extractor = Extractor(graph=graph)
        prompt = extractor.build_prompt("test")

        # Signal detection instructions (auto-generated from graph metadata)
        assert "SIGNALS" in prompt
        assert "on-prem-ad" in prompt
        assert "pci-scope" in prompt
        assert "sap-workload" in prompt

    def test_graph_context_includes_tradeoffs(self):
        graph = GLOBAL_REGISTRY.get("baseline").create_graph()
        extractor = Extractor(graph=graph)
        prompt = extractor.build_prompt("test")

        # Knowledge context for informed decisions
        assert "Tradeoffs:" in prompt
        assert "Consequences:" in prompt


@pytest.mark.skipif(not OLLAMA_AVAILABLE, reason="Ollama not available")
class TestRealLLMAuditTrail:
    """Verify that the LLM interaction is recorded in the evidence store."""

    def test_evidence_store_records_llm_call(self, tmp_path: Path):
        from intent_engine.core.llm_caller import LLMEvidenceStore

        backend = create_backend("ollama", base_url="http://localhost:11434/v1")
        llm_caller = LLMCaller(backend)
        evidence_store = LLMEvidenceStore()

        output = tmp_path / "output"
        graph = GLOBAL_REGISTRY.get("minimal").create_graph()
        compile_design(
            FIXTURES / "valid-payments.md",
            output,
            graph=graph,
            llm_caller=llm_caller,
            evidence_store=evidence_store,
        )

        assert len(evidence_store.entries) >= 1
        entry = evidence_store.entries[0]
        assert "prompt" in entry
        assert "response" in entry
        assert "latency_ms" in entry
        assert "backend" in entry
