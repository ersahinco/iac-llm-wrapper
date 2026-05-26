"""Tests for LLM integration layer."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from intent_engine.core.compiler import compile_design
from intent_engine.core.extractor import Extractor
from intent_engine.core.llm_caller import (
    LLMBackend,
    LLMCaller,
    LLMEvidence,
    LLMEvidenceStore,
    create_backend,
)


class MockLLMBackend(LLMBackend):
    def __init__(self, response: str = '{"primary_region": "eu-west-1"}') -> None:
        self.response = response
        self.calls: list[dict] = []

    def complete(self, prompt: str, **kwargs):
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.response


class TestLLMCaller:
    def test_call_returns_response_and_evidence(self):
        backend = MockLLMBackend("hello world")
        caller = LLMCaller(backend)
        response, evidence = caller.call("say hello")

        assert response == "hello world"
        assert evidence.backend == "MockLLMBackend"
        assert evidence.response == "hello world"
        assert evidence.prompt == "say hello"


class TestLLMEvidence:
    def test_to_dict(self):
        ev = LLMEvidence(
            prompt="test prompt",
            response="test response",
            model="gpt-4",
            latency_ms=150.5,
            backend="OpenAICompatibleBackend",
        )
        d = ev.to_dict()
        assert d["prompt"] == "test prompt"
        assert d["response"] == "test response"
        assert d["model"] == "gpt-4"
        assert d["latency_ms"] == 150.5
        assert d["backend"] == "OpenAICompatibleBackend"


class TestLLMEvidenceStore:
    def test_record_and_retrieve(self):
        store = LLMEvidenceStore()
        ev = LLMEvidence("p", "r", "m", 100.0, "Mock")
        store.record(ev)
        expected = {
            "calls": [
                {
                    "prompt": "p",
                    "response": "r",
                    "model": "m",
                    "latency_ms": 100.0,
                    "backend": "Mock",
                    "parse_error": None,
                    "token_usage": {},
                },
            ],
        }
        assert store.to_dict() == expected


class TestCreateBackend:
    def test_openai_backend_created(self):
        from intent_engine.core.llm_caller import OpenAICompatibleBackend

        backend = create_backend("openai", api_key="sk-test")
        assert isinstance(backend, OpenAICompatibleBackend)

    def test_ollama_backend_created(self):
        backend = create_backend("ollama", base_url="http://localhost:11434/v1")
        assert backend.base_url == "http://localhost:11434/v1"

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            create_backend("unknown-provider")

    def test_backend_uses_env_var_api_key(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}, clear=False):
            backend = create_backend("openai")
            assert backend.api_key == "env-key"


class TestEndToEndLLM:
    """End-to-end LLM round-trip tests with mocked responses."""

    LLM_DESIGN = """\
# AWS Landing Zone Design

## Region
- primary: eu-west-1

## Topology
- hub-spoke

## Network
- cidr: 10.0.0.0/16
- central_network_account: Network
- hub_cidr: 10.0.0.0/20

## Security
- audit_retention_days: 2555
- centralized_logging: true
- egress_inspection: required
- inspection_pattern: centralized-nat
- inspection_vendor: paloalto

## CI/CD
- mode: private
- placement: BuildVPC

## Hybrid Connectivity
- required: true
- dns_model: route53-resolver
- ip_model: bring-your-own
- on_prem_cidrs: 172.16.0.0/12,10.0.0.0/8
"""

    LLM_JSON_RESPONSE = json.dumps(
        {
            "decisions": {
                "primary_region": "eu-west-1",
                "topology": "hub-spoke",
                "network_cidr": "10.0.0.0/16",
                "central_network_account": "Network",
                "hub_cidr": "10.0.0.0/20",
                "audit_retention_days": "2555",
                "centralized_logging": "true",
                "egress_inspection": "required",
                "inspection_pattern": "centralized-nat",
                "inspection_vendor": "paloalto",
                "cicd_mode": "private",
                "cicd_placement": "BuildVPC",
                "hybrid_required": "true",
                "hybrid_dns_model": "route53-resolver",
                "hybrid_ip_model": "bring-your-own",
                "hybrid_on_prem_cidrs": "172.16.0.0/12,10.0.0.0/8",
            },
            "signal_decisions": {},
            "addons_suggested": [],
            "gaps": [],
            "contradictions": [],
        }
    )

    def test_full_baseline_llm_round_trip(self, tmp_path: Path):
        """Full baseline fields through Extractor + compile_design."""
        from intent_engine.core.patterns import GLOBAL_REGISTRY

        fixture = tmp_path / "design.md"
        fixture.write_text(self.LLM_DESIGN)

        mock_backend = MockLLMBackend(self.LLM_JSON_RESPONSE)
        llm_caller = LLMCaller(mock_backend)
        graph = GLOBAL_REGISTRY.get("baseline").create_graph()

        output = tmp_path / "output"
        compile_design(fixture, output, graph=graph, llm_caller=llm_caller)

        report = (output / "decision-report.yaml").read_text()
        assert "eu-west-1" in report
        assert "hub-spoke" in report
        sec_config = (output / "security-config.yaml").read_text()
        assert "paloalto" in sec_config
        net_config = (output / "network-config.yaml").read_text()
        assert "Network" in net_config

    def test_llm_with_addon_composed_graph(self, tmp_path: Path):
        """Baseline + pci-compliance addon through Extractor."""
        from intent_engine.core.patterns import ADDON_REGISTRY, GLOBAL_REGISTRY

        fixture = tmp_path / "design.md"
        fixture.write_text(self.LLM_DESIGN)

        graph = GLOBAL_REGISTRY.get("baseline").create_graph()
        graph = ADDON_REGISTRY.compose(graph, ["pci-compliance"])

        response = json.dumps(
            {
                "decisions": {
                    "primary_region": "eu-west-1",
                    "topology": "hub-spoke",
                    "network_cidr": "10.0.0.0/16",
                    "central_network_account": "Network",
                    "hub_cidr": "10.0.0.0/20",
                    "audit_retention_days": "2555",
                    "centralized_logging": "true",
                    "egress_inspection": "none",
                    "cicd_mode": "private",
                    "cicd_placement": "BuildVPC",
                    "hybrid_required": "false",
                    "data_residency": "true",
                    "encryption_key_management": "aws-kms-hsm",
                    "network_segmentation": "true",
                },
                "signal_decisions": {},
                "addons_suggested": [],
                "gaps": [],
                "contradictions": [],
            }
        )

        mock_backend = MockLLMBackend(response)
        llm_caller = LLMCaller(mock_backend)

        output = tmp_path / "output"
        compile_design(fixture, output, graph=graph, llm_caller=llm_caller)

        report = (output / "decision-report.yaml").read_text()
        assert "eu-west-1" in report
        assert "hub-spoke" in report

    def test_llm_round_trip_with_realistic_fixture(self, tmp_path: Path):
        """Use enterprise-full fixture with mocked LLM response."""
        from intent_engine.core.patterns import GLOBAL_REGISTRY

        fixture = Path(__file__).parent.parent.parent / "fixtures" / "enterprise-full.md"
        fixture_content = fixture.read_text()

        test_fixture = tmp_path / "enterprise-full.md"
        test_fixture.write_text(fixture_content)

        response = json.dumps(
            {
                "decisions": {
                    "primary_region": "eu-central-1",
                    "topology": "hub-spoke",
                    "network_cidr": "10.0.0.0/16",
                    "central_network_account": "NetworkHub",
                    "hub_cidr": "10.0.0.0/20",
                    "audit_retention_days": "2555",
                    "centralized_logging": "true",
                    "egress_inspection": "required",
                    "inspection_pattern": "centralized-nat",
                    "inspection_vendor": "paloalto",
                    "cicd_mode": "private",
                    "cicd_placement": "BuildVPC",
                    "hybrid_required": "true",
                    "hybrid_dns_model": "route53-resolver",
                    "hybrid_ip_model": "bring-your-own",
                    "hybrid_on_prem_cidrs": "10.0.0.0/8",
                },
                "signal_decisions": {},
                "addons_suggested": [],
                "gaps": [],
                "contradictions": [],
            }
        )

        mock_backend = MockLLMBackend(response)
        llm_caller = LLMCaller(mock_backend)
        graph = GLOBAL_REGISTRY.get("baseline").create_graph()

        output = tmp_path / "output"
        compile_design(test_fixture, output, graph=graph, llm_caller=llm_caller)

        report = (output / "decision-report.yaml").read_text()
        assert "hub-spoke" in report
        assert "NetworkHub" in report
        assert "private" in report


class TestMalformedLLMResponse:
    """Tests for recovery from malformed/partial LLM responses."""

    def test_markdown_fence_recovery(self):
        extractor = Extractor(pattern="minimal")
        response = (
            '```json\n{"decisions": {"primary_region": "us-east-1", "topology": "single-vpc"}}\n```'
        )
        result = extractor.parse_response(response)
        intent = result.to_intent(extractor)
        assert intent.primary_region == "us-east-1"
        assert intent.topology.value == "single-vpc"

    def test_json_prefix_recovery(self):
        extractor = Extractor(pattern="minimal")
        response = 'json\n{"decisions": {"primary_region": "eu-west-1"}}'
        result = extractor.parse_response(response)
        intent = result.to_intent(extractor)
        assert intent.primary_region == "eu-west-1"

    def test_partial_brace_recovery(self):
        extractor = Extractor(pattern="minimal")
        response = (
            'Here is the extracted data: {"decisions": {"primary_region": "ap-southeast-1", '
            '"topology": "single-vpc"}} and some trailing text'
        )
        result = extractor.parse_response(response)
        intent = result.to_intent(extractor)
        assert intent.primary_region == "ap-southeast-1"

    def test_invalid_json_returns_defaults(self):
        extractor = Extractor(pattern="minimal")
        response = "This is not JSON at all"
        result = extractor.parse_response(response)
        intent = result.to_intent(extractor)
        assert intent.primary_region == "eu-central-1"
        assert intent.topology is None

    def test_invalid_enum_is_skipped(self):
        extractor = Extractor(pattern="minimal")
        response = '{"decisions": {"topology": "mesh-network"}}'
        result = extractor.parse_response(response)
        intent = result.to_intent(extractor)
        assert intent.topology is None

    def test_wrong_type_for_int_is_coerced(self):
        extractor = Extractor(pattern="minimal")
        response = '{"decisions": {"audit_retention_days": "3650"}}'
        result = extractor.parse_response(response)
        intent = result.to_intent(extractor)
        assert intent.security.audit_retention_days == 3650

    def test_float_string_for_int_is_coerced(self):
        extractor = Extractor(pattern="minimal")
        response = '{"decisions": {"audit_retention_days": 2555.0}}'
        result = extractor.parse_response(response)
        intent = result.to_intent(extractor)
        assert intent.security.audit_retention_days == 2555

    def test_hybrid_cidrs_as_list(self):
        extractor = Extractor(pattern="baseline")
        response = '{"decisions": {"hybrid_on_prem_cidrs": ["10.0.0.0/8", "172.16.0.0/12"]}}'
        result = extractor.parse_response(response)
        intent = result.to_intent(extractor)
        assert "10.0.0.0/8" in intent.hybrid.on_prem_cidrs

    def test_workload_with_missing_fields(self):
        extractor = Extractor(pattern="baseline")
        response = '{"decisions": {}, "workloads": [{"name": "api"}]}'
        result = extractor.parse_response(response)
        intent = result.to_intent(extractor)
        # to_intent now parses legacy arrays from raw response
        assert len(intent.workloads) == 1
        assert intent.workloads[0].name == "api"
        assert intent.workloads[0].port == 8080  # Pydantic default preserved
        # extract() produces the same result
        intent2 = extractor.extract("", llm_response=response)
        assert len(intent2.workloads) == 1
        assert intent2.workloads[0].name == "api"

    def test_bool_from_string(self):
        extractor = Extractor(pattern="baseline")
        response = '{"decisions": {"centralized_logging": "true", "hybrid_required": "false"}}'
        result = extractor.parse_response(response)
        intent = result.to_intent(extractor)
        assert intent.security.centralized_logging is True
        assert intent.hybrid.required is False


class TestLLMGraphResult:
    """Tests for the new structured LLM graph traversal result format."""

    def test_structured_format_with_signals_and_gaps(self):
        extractor = Extractor(pattern="minimal")
        response = json.dumps(
            {
                "decisions": {"primary_region": "eu-west-1"},
                "signal_decisions": {"topology": "hub-spoke"},
                "addons_suggested": ["pci-compliance"],
                "gaps": [{"key": "network_cidr", "reason": "missing", "suggestion": "add it"}],
                "contradictions": [{"key": "topology", "reason": "conflict", "details": "x"}],
            }
        )
        result = extractor.parse_response(response)
        assert result.decisions == {"primary_region": "eu-west-1"}
        assert result.signal_decisions == {"topology": "hub-spoke"}
        assert result.addons_suggested == ["pci-compliance"]
        assert len(result.gaps) == 1
        assert len(result.contradictions) == 1

    def test_legacy_flat_format_backward_compatible(self):
        extractor = Extractor(pattern="minimal")
        response = '{"primary_region": "ap-southeast-1", "topology": "single-vpc"}'
        result = extractor.parse_response(response)
        intent = result.to_intent(extractor)
        assert intent.primary_region == "ap-southeast-1"
        assert intent.topology.value == "single-vpc"
