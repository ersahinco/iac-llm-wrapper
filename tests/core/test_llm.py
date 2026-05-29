"""Tests for LLM plumbing and graph-driven extraction."""

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
    def __init__(self, response: str = '{"decisions": {"home_region": "eu-west-1"}}') -> None:
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
        assert store.to_dict()["calls"][0]["prompt"] == "p"
        assert store.to_dict()["calls"][0]["response"] == "r"


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
    def test_aws_lza_llm_round_trip(self, tmp_path: Path):
        fixture = tmp_path / "design.md"
        fixture.write_text(
            """# AWS LZA Design

## Organization
- org_mode: control-tower
- organization_name: ExampleCorp

## Accounts
- workload_accounts: AppProd
- network_account: Network

## Network
- topology: hub-spoke
- network_cidr: 10.50.0.0/16
"""
        )
        response = json.dumps(
            {
                "decisions": {
                    "baseline": "standard",
                    "org_mode": "control-tower",
                    "organization_name": "ExampleCorp",
                    "home_region": "eu-central-1",
                    "enabled_regions": ["eu-central-1"],
                    "organizational_units": ["Security", "Infrastructure", "Workloads"],
                    "workload_accounts": ["AppProd"],
                    "network_account": "Network",
                    "identity_center_permission_sets": ["ReadOnlyAccess", "PowerUserAccess"],
                    "identity_center_assignments": [
                        "PlatformAdmins:PowerUserAccess:Management",
                        "AppTeam:ReadOnlyAccess:AppProd",
                    ],
                    "topology": "hub-spoke",
                    "network_cidr": "10.50.0.0/16",
                    "centralized_logging": "true",
                    "security_hub_enabled": "true",
                    "guardduty_enabled": "true",
                },
                "signal_decisions": {},
                "gaps": [],
                "contradictions": [],
            }
        )

        output = tmp_path / "output"
        evidence_store = LLMEvidenceStore()
        compile_design(
            fixture,
            output,
            llm_caller=LLMCaller(MockLLMBackend(response)),
            evidence_store=evidence_store,
        )

        report = (output / "decision-report.yaml").read_text()
        assert "aws-lza" in report
        assert "AppProd" in report
        assert "Network" in report
        assert "deploymentAllowed: true" in report
        assert (output / "lineage-manifest.yaml").exists()
        assert (output / "llm-trace-summary.yaml").exists()
        trace = (output / "llm-trace-summary.yaml").read_text()
        assert "mockllm" in trace
        assert "rawLlmDecisions:" in trace
        assert "acceptedDecisions:" in trace
        assert "extractedDecisions:" not in trace
        assert "rawEvidencePath:" not in trace
        assert not (output / "terraform.tfvars").exists()

    def test_llm_contradiction_blocks_compile_with_assessment(self, tmp_path: Path):
        fixture = tmp_path / "design.md"
        fixture.write_text(
            """# AWS LZA Design

## Accounts
- network_account: Network
"""
        )
        response = json.dumps(
            {
                "decisions": {"network_account": "Network", "topology": "hub-spoke"},
                "signal_decisions": {},
                "gaps": [],
                "contradictions": [
                    {
                        "key": "enabled_regions",
                        "reason": "region mismatch",
                        "details": "home region not enabled",
                    }
                ],
            }
        )

        output = tmp_path / "output"
        with pytest.raises(Exception, match="LLM_CONTRADICTION_ENABLED_REGIONS"):
            compile_design(fixture, output, llm_caller=LLMCaller(MockLLMBackend(response)))

        report = (output / "decision-report.yaml").read_text()
        assert "deploymentAllowed: false" in report
        assert "home region not enabled" in report

    def test_llm_non_contract_findings_do_not_block_handoff(self, tmp_path: Path):
        fixture = tmp_path / "design.md"
        fixture.write_text(
            """# AWS LZA Design

## LZA Baseline
- baseline: standard

## Organization
- org_mode: control-tower
- organization_name: ExampleCorp
- organizational_units: Security, Infrastructure, Workloads

## Regions
- home_region: eu-central-1
- enabled_regions: eu-central-1

## Accounts
- workload_accounts: AppProd
- audit_account: Audit
- log_archive_account: LogArchive
- security_tooling_account: SecurityTooling
- network_account: Network

## Identity
- identity_center_delegated_admin_account: SecurityTooling
- identity_center_permission_sets: ReadOnlyAccess, PowerUserAccess
- identity_center_assignments: PlatformAdmins:PowerUserAccess:Management,
  AppTeam:ReadOnlyAccess:AppProd

## Network
- topology: hub-spoke
- network_cidr: 10.50.0.0/16

## Security
- centralized_logging: true
- security_hub_enabled: true
- guardduty_enabled: true
- compliance_overlay: none
"""
        )
        response = json.dumps(
            {
                "decisions": {},
                "signal_decisions": {},
                "gaps": [
                    {
                        "key": "project_name",
                        "reason": "Not mentioned.",
                        "suggestion": "Ask for a project name.",
                    }
                ],
                "contradictions": [
                    {
                        "key": "compliance_tags",
                        "reason": "Not mentioned consistently.",
                    }
                ],
            }
        )

        output = tmp_path / "output"
        compile_design(fixture, output, llm_caller=LLMCaller(MockLLMBackend(response)))

        report = (output / "decision-report.yaml").read_text()
        trace = (output / "llm-trace-summary.yaml").read_text()
        assert "deploymentAllowed: true" in report
        assert "project_name" in trace
        assert "compliance_tags" in trace
        assert "blocking: []" in trace
        assert "LLM_GAP_PROJECT_NAME" not in report


class TestMalformedLLMResponse:
    def test_markdown_fence_recovery(self):
        extractor = Extractor(pattern="aws-lza")
        response = '```json\n{"decisions": {"home_region": "us-east-1"}}\n```'
        result = extractor.parse_response(response)
        intent = result.to_intent(extractor)
        assert intent.home_region == "us-east-1"

    def test_json_prefix_recovery(self):
        extractor = Extractor(pattern="aws-lza")
        response = 'json\n{"decisions": {"home_region": "eu-west-1"}}'
        result = extractor.parse_response(response)
        intent = result.to_intent(extractor)
        assert intent.home_region == "eu-west-1"

    def test_partial_brace_recovery(self):
        extractor = Extractor(pattern="aws-lza")
        response = (
            'Here is the extracted data: {"decisions": {"home_region": "ap-southeast-1"}} '
            "and trailing text"
        )
        result = extractor.parse_response(response)
        intent = result.to_intent(extractor)
        assert intent.home_region == "ap-southeast-1"

    def test_invalid_json_returns_model_defaults(self):
        extractor = Extractor(pattern="aws-lza")
        result = extractor.parse_response("not json").to_intent(extractor)
        assert result.home_region == "eu-central-1"

    def test_invalid_enum_is_skipped(self):
        extractor = Extractor(pattern="aws-lza")
        response = '{"decisions": {"topology": "mesh-network"}}'
        result = extractor.parse_response(response)
        intent = result.to_intent(extractor)
        assert intent.topology.value == "hub-spoke"

    def test_bool_and_list_coercion(self):
        extractor = Extractor(pattern="aws-lza")
        response = json.dumps(
            {
                "decisions": {
                    "centralized_logging": "false",
                    "enabled_regions": ["eu-central-1", "eu-west-1"],
                }
            }
        )
        intent = extractor.parse_response(response).to_intent(extractor)
        assert intent.centralized_logging is False
        assert intent.enabled_regions == ["eu-central-1", "eu-west-1"]


class TestLLMGraphResult:
    def test_structured_format_with_signals_and_gaps(self):
        extractor = Extractor(pattern="aws-lza")
        response = json.dumps(
            {
                "decisions": {"home_region": "eu-west-1"},
                "signal_decisions": {"topology": "hub-spoke"},
                "gaps": [{"key": "network_account", "reason": "missing", "suggestion": "ask"}],
                "contradictions": [{"key": "topology", "reason": "conflict", "details": "x"}],
            }
        )
        result = extractor.parse_response(response)
        assert result.decisions == {"home_region": "eu-west-1"}
        assert result.signal_decisions == {"topology": "hub-spoke"}
        assert len(result.gaps) == 1
        assert len(result.contradictions) == 1

    def test_flat_format_backward_compatible(self):
        extractor = Extractor(pattern="aws-lza")
        result = extractor.parse_response('{"home_region": "ap-southeast-1"}')
        intent = result.to_intent(extractor)
        assert intent.home_region == "ap-southeast-1"
