"""Tests for LLM plumbing and graph-driven extraction."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from intent_engine.core.compiler import compile_design
from intent_engine.core.extractor import Extractor
from intent_engine.core.llm_caller import (
    BedrockCliBackend,
    LLMBackend,
    LLMCaller,
    LLMEvidence,
    LLMEvidenceStore,
    OpenAICompatibleBackend,
    auto_detect_llm,
    create_backend,
)
from intent_engine.core.observability import build_model_benchmark


class MockLLMBackend(LLMBackend):
    def __init__(self, response: str = '{"decisions": {"home_region": "eu-west-1"}}') -> None:
        self.response = response
        self.calls: list[dict] = []

    def complete(self, prompt: str, **kwargs):
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        return self.response


def _complete_aws_lza_design() -> str:
    return """# AWS LZA Design

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


class TestLLMCaller:
    def test_call_returns_response_and_evidence(self):
        backend = MockLLMBackend("hello world")
        caller = LLMCaller(backend)
        response, evidence = caller.call("say hello")

        assert response == "hello world"
        assert evidence.backend == "MockLLMBackend"
        assert evidence.response == "hello world"
        assert evidence.prompt == "say hello"

    def test_call_captures_backend_token_usage(self):
        backend = MockLLMBackend("hello world")
        backend.last_token_usage = {
            "prompt_tokens": 11,
            "completion_tokens": 4,
            "total_tokens": 15,
        }
        _, evidence = LLMCaller(backend).call("say hello")

        assert evidence.token_usage == {
            "prompt_tokens": 11,
            "completion_tokens": 4,
            "total_tokens": 15,
        }


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


class TestModelBenchmark:
    def test_build_model_benchmark_rolls_up_trace_fields(self):
        benchmark = build_model_benchmark(
            {
                "pattern": "aws-lza",
                "provider": "ollama",
                "model": "qwen2.5:7b",
                "calls": [
                    {
                        "provider": "ollama",
                        "model": "qwen2.5:7b",
                        "latencyMs": 10.04,
                        "tokenUsage": {
                            "prompt_tokens": 7,
                            "completion_tokens": 5,
                            "total_tokens": 12,
                        },
                    },
                    {
                        "provider": "ollama",
                        "model": "qwen2.5:7b",
                        "latencyMs": 20.02,
                        "tokenUsage": {
                            "prompt_tokens": 3,
                            "completion_tokens": 2,
                            "total_tokens": 5,
                        },
                        "parseError": "bad json",
                    },
                ],
                "acceptedDecisions": {"home_region": "eu-central-1"},
                "rawLlmDecisions": {"home_region": "eu-central-1"},
                "rawLlmSignalDecisions": {},
                "appliedDecisions": {"llm": ["home_region"]},
                "gaps": {"resolved": [{}], "blocking": [], "raw": [{}]},
                "contradictions": {"blocking": [], "raw": []},
                "handoffReadiness": {
                    "status": "ready",
                    "handoffAllowed": True,
                    "blockerCount": 0,
                },
            }
        )

        assert benchmark["run"]["mode"] == "llm"
        assert benchmark["latency"]["totalMs"] == 30.1
        assert benchmark["tokens"]["status"] == "captured"
        assert benchmark["tokens"]["totalTokens"] == 17
        assert benchmark["quality"]["acceptedDecisionCount"] == 1
        assert benchmark["quality"]["rawLlmMissingAcceptedDecisionCount"] == 0
        assert benchmark["quality"]["parseErrorCount"] == 1
        assert benchmark["cost"]["status"] == "not-estimated"

    def test_build_model_benchmark_reports_raw_llm_coverage(self):
        benchmark = build_model_benchmark(
            {
                "pattern": "aws-lza",
                "provider": "ollama",
                "model": "qwen2.5:7b",
                "calls": [{"latencyMs": 1}],
                "acceptedDecisions": {
                    "network_account": "Network",
                    "identity_center_permission_sets": ["ReadOnlyAccess"],
                    "identity_center_assignments": ["Admins:ReadOnlyAccess:Network"],
                },
                "rawLlmDecisions": {"network_account": "Network"},
                "rawLlmSignalDecisions": {"identity_center_permission_sets": ["ReadOnlyAccess"]},
                "appliedDecisions": {"markdown": ["identity_center_assignments"]},
            }
        )

        assert benchmark["quality"]["rawLlmAcceptedCoverageCount"] == 2
        assert benchmark["quality"]["rawLlmMissingAcceptedDecisionCount"] == 1
        assert benchmark["quality"]["rawLlmMissingAcceptedDecisions"] == [
            "identity_center_assignments"
        ]
        assert benchmark["quality"]["rawLlmUnacceptedDecisionCount"] == 0


class TestCreateBackend:
    def test_openai_backend_created(self):
        backend = create_backend("openai", api_key="sk-test")
        assert isinstance(backend, OpenAICompatibleBackend)

    def test_ollama_backend_created(self):
        backend = create_backend("ollama", base_url="http://localhost:11434/v1")
        assert isinstance(backend, OpenAICompatibleBackend)
        assert backend.base_url == "http://localhost:11434/v1"

    def test_bedrock_backend_created(self):
        backend = create_backend("bedrock", model="eu.amazon.nova-2-lite-v1:0")

        assert isinstance(backend, BedrockCliBackend)
        assert backend.model == "eu.amazon.nova-2-lite-v1:0"

    def test_bedrock_backend_uses_aws_cli_converse(self):
        backend = BedrockCliBackend(model="eu.amazon.nova-2-lite-v1:0", region="eu-central-1")
        stdout = json.dumps(
            {
                "output": {
                    "message": {
                        "content": [{"text": '{"decisions": {"home_region": "eu-central-1"}}'}]
                    }
                },
                "usage": {"inputTokens": 10, "outputTokens": 5, "totalTokens": 15},
            }
        )

        with patch("intent_engine.core.llm_caller.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout=stdout,
                stderr="",
            )

            response = backend.complete("extract this")

        assert response == '{"decisions": {"home_region": "eu-central-1"}}'
        assert backend.last_token_usage == {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15,
        }
        command = run.call_args.args[0]
        assert command[:3] == ["aws", "bedrock-runtime", "converse"]
        assert "eu.amazon.nova-2-lite-v1:0" in command
        assert "eu-central-1" in command

    def test_bedrock_backend_surfaces_cli_failure(self):
        backend = BedrockCliBackend()

        with patch("intent_engine.core.llm_caller.subprocess.run") as run:
            run.return_value = subprocess.CompletedProcess(
                args=[],
                returncode=254,
                stdout="",
                stderr="model access denied",
            )

            with pytest.raises(RuntimeError, match="model access denied"):
                backend.complete("extract this")

    def test_auto_detect_bedrock_does_not_require_openai_key(self):
        with patch.dict("os.environ", {}, clear=True):
            caller = auto_detect_llm(provider="bedrock", model="eu.amazon.nova-2-lite-v1:0")

        assert isinstance(caller, LLMCaller)
        assert isinstance(caller.backend, BedrockCliBackend)

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            create_backend("unknown-provider")

    def test_backend_uses_env_var_api_key(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}, clear=False):
            backend = create_backend("openai")
            assert isinstance(backend, OpenAICompatibleBackend)
            assert backend.api_key == "env-key"


class TestEndToEndLLM:
    def test_prompt_scopes_findings_to_schema_keys(self):
        prompt = Extractor(pattern="aws-lza").build_prompt("Design doc text here")

        assert "Use only SCHEMA keys for decisions" in prompt
        assert "explicit 'schema_key: value' bullets" in prompt
        assert "Do not report gaps for design_doc, accounts, OUs, or workloads metadata" in prompt
        assert "If unsure about a SCHEMA key" in prompt

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
        assert "handoffAllowed: true" in report
        assert (output / "lineage-manifest.yaml").exists()
        assert (output / "llm-trace-summary.yaml").exists()
        assert (output / "model-benchmark.yaml").exists()
        trace = (output / "llm-trace-summary.yaml").read_text()
        assert "mockllm" in trace
        assert "rawLlmDecisions:" in trace
        assert "acceptedDecisions:" in trace
        assert "extractedDecisions:" not in trace
        assert "rawEvidencePath:" not in trace
        benchmark = (output / "model-benchmark.yaml").read_text()
        assert "schemaVersion: intent-engine/model-benchmark/v1" in benchmark
        assert "mode: llm" in benchmark
        assert "acceptedDecisionCount:" in benchmark
        assert "conformance:" in benchmark
        assert "status: not-estimated" in benchmark
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
        assert "handoffAllowed: false" in report
        assert "home region not enabled" in report

    def test_llm_non_contract_findings_do_not_block_handoff(self, tmp_path: Path):
        fixture = tmp_path / "design.md"
        fixture.write_text(_complete_aws_lza_design())
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
        assert "handoffAllowed: true" in report
        assert "project_name" in trace
        assert "compliance_tags" in trace
        assert "blocking: []" in trace
        assert "LLM_GAP_PROJECT_NAME" not in report

    def test_markdown_decisions_take_precedence_over_llm(self, tmp_path: Path):
        fixture = tmp_path / "design.md"
        fixture.write_text(_complete_aws_lza_design())
        response = json.dumps(
            {
                "decisions": {
                    "network_cidr": "10.99.0.0/16",
                    "security_hub_enabled": "false",
                },
                "signal_decisions": {"network_cidr": "10.88.0.0/16"},
                "gaps": [],
                "contradictions": [],
            }
        )

        output = tmp_path / "output"
        compile_design(fixture, output, llm_caller=LLMCaller(MockLLMBackend(response)))

        import ruamel.yaml

        yaml = ruamel.yaml.YAML(typ="safe")
        trace = yaml.load((output / "llm-trace-summary.yaml").read_text())
        assert trace["rawLlmDecisions"]["network_cidr"] == "10.99.0.0/16"
        assert trace["rawLlmSignalDecisions"]["network_cidr"] == "10.88.0.0/16"
        assert trace["acceptedDecisions"]["network_cidr"] == "10.50.0.0/16"
        assert trace["acceptedDecisions"]["security_hub_enabled"] is True
        assert "network_cidr" not in trace["appliedDecisions"]["llm"]
        assert "network_cidr" not in trace["appliedDecisions"]["signals"]

    def test_markdown_locked_llm_contradiction_does_not_block_compile(self, tmp_path: Path):
        import ruamel.yaml

        import intent_engine.patterns.terraform_vpc  # noqa: F401

        fixture = tmp_path / "design.md"
        fixture.write_text(
            """# Terraform VPC Customer Notes

The networking squad owns an approved VPC module. The team wants three
availability zones, per-AZ NAT for resilience, and DNS hostnames enabled.

- vpc_name: payments-shared-vpc
- primary_region: eu-west-1
- cidr: 10.90.0.0/16
- az_count: 3
- public_subnet_cidrs: 10.90.0.0/24, 10.90.1.0/24, 10.90.2.0/24
- private_subnet_cidrs: 10.90.10.0/24, 10.90.11.0/24, 10.90.12.0/24
- enable_nat_gateway: true
- single_nat_gateway: false
- enable_dns_hostnames: true
- target_account_id: 222233334444
- deployment_pipeline_ref: github://payments-platform/networking-vpc
"""
        )
        response = json.dumps(
            {
                "decisions": {
                    "enable_nat_gateway": "true",
                    "single_nat_gateway": "false",
                },
                "signal_decisions": {},
                "gaps": [],
                "contradictions": [
                    {
                        "key": "single_nat_gateway",
                        "reason": "Contradicts with enable_nat_gateway being true",
                        "details": "Cannot have both single NAT gateway and per-AZ NAT",
                    }
                ],
            }
        )

        output = tmp_path / "output"
        compile_design(
            fixture,
            output,
            llm_caller=LLMCaller(MockLLMBackend(response)),
            pattern="terraform-vpc",
        )

        yaml = ruamel.yaml.YAML(typ="safe")
        report = yaml.load((output / "decision-report.yaml").read_text())
        trace = yaml.load((output / "llm-trace-summary.yaml").read_text())
        benchmark = yaml.load((output / "model-benchmark.yaml").read_text())

        assert report["handoffReadiness"]["handoffAllowed"] is True
        assert trace["contradictions"]["raw"][0]["key"] == "single_nat_gateway"
        assert trace["contradictions"]["blocking"] == []
        assert benchmark["quality"]["rawContradictionCount"] == 1
        assert benchmark["quality"]["blockingContradictionCount"] == 0


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
