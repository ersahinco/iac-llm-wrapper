"""CLI tests using Typer test runner."""

from __future__ import annotations

import json
from importlib.metadata import version as distribution_version
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from intent_engine.cli import APP_VERSION, app
from intent_engine.core.llm_caller import LLMBackend, LLMCaller

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
runner = CliRunner()


def test_cli_version_uses_installed_distribution_metadata():
    assert APP_VERSION == distribution_version("iac-llm-wrapper")


class _MockBackend(LLMBackend):
    def __init__(self, response: str) -> None:
        self.response = response

    def complete(self, prompt: str, **kwargs: Any) -> str:
        return self.response


class _FailingBackend(LLMBackend):
    def complete(self, prompt: str, **kwargs: Any) -> str:
        raise RuntimeError("model unavailable")


class TestCompileCommand:
    def test_compile_aws_lza_handoff(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("INTENT_ENGINE_DISABLE_LLM", "1")
        output = tmp_path / "output"
        result = runner.invoke(
            app,
            [
                "compile",
                "--input",
                str(FIXTURES / "usability" / "engineer-handoff-lza.md"),
                "--output",
                str(output),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Compilation successful" in result.stdout
        assert (output / "accounts-config.yaml").exists()
        assert (output / "lineage-manifest.yaml").exists()
        assert not (output / "terraform.tfvars").exists()

    def test_compile_with_llm_keeps_raw_evidence_by_default(
        self,
        tmp_path: Path,
        monkeypatch,
    ):
        output = tmp_path / "output"
        response = json.dumps({"decisions": {}, "signal_decisions": {}, "gaps": []})
        monkeypatch.setattr(
            "intent_engine.cli.create_llm_caller",
            lambda **kwargs: LLMCaller(_MockBackend(response)),
        )

        result = runner.invoke(
            app,
            [
                "compile",
                "--input",
                str(FIXTURES / "usability" / "engineer-handoff-lza.md"),
                "--output",
                str(output),
                "--provider",
                "ollama",
                "--model",
                "test-model",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "LLM evidence written to:" in result.stdout
        assert (output / "raw-evidence.yaml").exists()
        assert "raw-evidence.yaml" in (output / "llm-trace-summary.yaml").read_text()

    def test_compile_with_llm_can_skip_raw_evidence(
        self,
        tmp_path: Path,
        monkeypatch,
    ):
        output = tmp_path / "output"
        response = json.dumps({"decisions": {}, "signal_decisions": {}, "gaps": []})
        monkeypatch.setattr(
            "intent_engine.cli.create_llm_caller",
            lambda **kwargs: LLMCaller(_MockBackend(response)),
        )

        result = runner.invoke(
            app,
            [
                "compile",
                "--input",
                str(FIXTURES / "usability" / "engineer-handoff-lza.md"),
                "--output",
                str(output),
                "--provider",
                "ollama",
                "--model",
                "test-model",
                "--no-raw-evidence",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "LLM evidence written to:" not in result.stdout
        assert not (output / "raw-evidence.yaml").exists()
        assert "status: not-requested" in (output / "llm-trace-summary.yaml").read_text()

    def test_compile_warns_when_llm_fails_and_markdown_fallback_succeeds(
        self,
        tmp_path: Path,
        monkeypatch,
    ):
        output = tmp_path / "output"
        monkeypatch.setattr(
            "intent_engine.cli.create_llm_caller",
            lambda **kwargs: LLMCaller(_FailingBackend()),
        )

        result = runner.invoke(
            app,
            [
                "compile",
                "--input",
                str(FIXTURES / "usability" / "engineer-handoff-lza.md"),
                "--output",
                str(output),
                "--provider",
                "ollama",
                "--model",
                "test-model",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "WARNING: LLM extraction failed" in result.output
        assert "First LLM error: model unavailable" in result.output
        assert "parseError: model unavailable" in (output / "llm-trace-summary.yaml").read_text()

    def test_compile_missing_input_fails(self, tmp_path: Path):
        result = runner.invoke(
            app,
            ["compile", "--input", "/nonexistent/path", "--output", str(tmp_path / "out")],
        )
        assert result.exit_code == 1
        assert "does not exist" in result.output

    def test_compile_rejects_unpinned_llm_provider(self, tmp_path: Path):
        result = runner.invoke(
            app,
            [
                "compile",
                "--input",
                str(FIXTURES / "usability" / "engineer-handoff-lza.md"),
                "--output",
                str(tmp_path / "output"),
                "--provider",
                "ollama",
            ],
        )

        assert result.exit_code == 1
        assert "LLM use requires an explicit model name" in result.output


class TestDiscoverCommand:
    def test_discover_uses_explicit_llm_configuration(self, monkeypatch):
        calls: list[dict[str, Any]] = []
        response = json.dumps({"decisions": {}, "signal_decisions": {}, "gaps": []})

        def fake_create_llm_caller(**kwargs: Any) -> LLMCaller:
            calls.append(kwargs)
            return LLMCaller(_MockBackend(response))

        monkeypatch.setattr("intent_engine.cli.create_llm_caller", fake_create_llm_caller)

        result = runner.invoke(
            app,
            [
                "discover",
                "--input",
                str(FIXTURES / "usability" / "engineer-handoff-lza.md"),
                "--provider",
                "ollama",
                "--model",
                "test-model",
            ],
        )

        assert result.exit_code == 0, result.output
        assert calls
        assert calls[0]["provider"] == "ollama"
        assert calls[0]["model"] == "test-model"


class TestValidateCommand:
    def test_validate_generated_output(self, tmp_path: Path):
        output = tmp_path / "output"
        result = runner.invoke(
            app,
            [
                "interview",
                "--output",
                str(output),
                "--decisions",
                (
                    '{"network_account": "Network", '
                    '"identity_center_permission_sets": "ReadOnlyAccess", '
                    '"identity_center_assignments": "PlatformAdmins:ReadOnlyAccess:Management"}'
                ),
            ],
        )
        assert result.exit_code == 0, result.output

        result = runner.invoke(app, ["validate", "--input", str(output)])
        assert result.exit_code == 0
        assert "Validation passed" in result.stdout

    def test_validate_empty_dir_fails(self, tmp_path: Path):
        result = runner.invoke(app, ["validate", "--input", str(tmp_path)])
        assert result.exit_code == 1

    def test_validate_non_dir_fails(self, tmp_path: Path):
        f = tmp_path / "file.txt"
        f.write_text("not a dir")
        result = runner.invoke(app, ["validate", "--input", str(f)])
        assert result.exit_code == 1


class TestContractCommand:
    def test_contract_list_shows_registered_contracts(self):
        result = runner.invoke(app, ["contract", "list"])

        assert result.exit_code == 0
        assert "aws-lza-sample-configuration" in result.stdout
        assert "generic-handoff-plan" in result.stdout
        assert "kubernetes-cluster-config" in result.stdout
        assert "terraform-aws-vpc" in result.stdout

    def test_contract_show_by_pattern(self):
        result = runner.invoke(app, ["contract", "show", "--pattern", "aws-lza"])

        assert result.exit_code == 0
        assert "accounts-config.yaml" in result.stdout
        assert "network-config.yaml | paths: homeRegion" in result.stdout
        assert "assertions: defaultVpc.delete" in result.stdout
        assert "home_region" in result.stdout

    def test_contract_show_requires_selector(self):
        result = runner.invoke(app, ["contract", "show"])

        assert result.exit_code == 1
        assert "--name or --pattern required" in result.output


class TestGraphCommand:
    def test_graph_export_json(self):
        result = runner.invoke(app, ["graph", "export", "--pattern", "aws-lza", "--format", "json"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.stdout)
        assert data["pattern"] == "aws-lza"
        assert data["nodeCount"] >= 1
        assert any(node["key"] == "network_account" for node in data["nodes"])
        assert any(edge["kind"] == "applies_when" for edge in data["edges"])

    def test_graph_export_mermaid(self):
        result = runner.invoke(
            app,
            ["graph", "export", "--pattern", "aws-lza", "--format", "mermaid"],
        )

        assert result.exit_code == 0, result.output
        assert "flowchart TD" in result.stdout
        assert "Network Account" in result.stdout
        assert "applies_when" in result.stdout

    def test_graph_export_unknown_format_fails(self):
        result = runner.invoke(app, ["graph", "export", "--format", "dot"])

        assert result.exit_code == 1
        assert "Unknown graph export format" in result.output


class TestPatternCommand:
    def test_pattern_check_default(self):
        result = runner.invoke(app, ["pattern", "check", "--pattern", "aws-lza"])

        assert result.exit_code == 0, result.output
        assert "Pattern check passed: aws-lza" in result.stdout
        assert "Requirements:" in result.stdout
        assert "Contracts:" in result.stdout
        assert "Samples:" in result.stdout
        assert "Context rules:" in result.stdout


class TestSampleCommand:
    def test_sample_list_shows_registered_samples(self):
        result = runner.invoke(app, ["sample", "list", "--pattern", "aws-lza"])

        assert result.exit_code == 0
        assert "aws-lza-standard-v1" in result.stdout
        assert "aws-lza-regulated-v1" in result.stdout
        assert "Contract: aws-lza-sample-configuration" in result.stdout

    def test_sample_list_filters_by_tag(self):
        result = runner.invoke(app, ["sample", "list", "--tag", "regulated"])

        assert result.exit_code == 0
        assert "aws-lza-regulated-v1" in result.stdout
        assert "aws-lza-standard-v1" not in result.stdout

    def test_sample_list_filters_by_contract(self):
        result = runner.invoke(
            app,
            ["sample", "list", "--contract", "aws-lza-sample-configuration"],
        )

        assert result.exit_code == 0
        assert "aws-lza-standard-v1" in result.stdout
        assert "k8s-cluster-v1" not in result.stdout

    def test_sample_show_by_name(self):
        result = runner.invoke(app, ["sample", "show", "--name", "aws-lza-healthcare-v1"])

        assert result.exit_code == 0
        assert "Pattern: aws-lza" in result.stdout
        assert "Upstream variant: healthcare" in result.stdout
        assert "Source contract: aws-lza-sample-configuration" in result.stdout
        assert "compliance_overlay = healthcare" in result.stdout

    def test_sample_show_requires_selector(self):
        result = runner.invoke(app, ["sample", "show"])

        assert result.exit_code == 1
        assert "--name or --pattern required" in result.output


class TestExplainCommand:
    def test_explain_valid_report(self, tmp_path: Path):
        output = tmp_path / "output"
        runner.invoke(
            app,
            [
                "interview",
                "--output",
                str(output),
                "--decisions",
                (
                    '{"network_account": "Network", '
                    '"identity_center_permission_sets": "ReadOnlyAccess", '
                    '"identity_center_assignments": "PlatformAdmins:ReadOnlyAccess:Management"}'
                ),
            ],
        )
        result = runner.invoke(app, ["explain", "--report", str(output / "decision-report.yaml")])
        assert result.exit_code == 0
        assert "eu-central-1" in result.stdout
        assert "hub-spoke" in result.stdout

    def test_explain_missing_report_fails(self, tmp_path: Path):
        result = runner.invoke(app, ["explain", "--report", str(tmp_path / "missing.yaml")])
        assert result.exit_code == 1

    @pytest.mark.parametrize(
        ("content", "message"),
        [
            ("region: [unterminated\n", "invalid YAML"),
            ("- not\n- a\n- mapping\n", "expected YAML mapping"),
        ],
    )
    def test_explain_rejects_invalid_yaml_mapping(
        self,
        tmp_path: Path,
        content: str,
        message: str,
    ):
        report = tmp_path / "decision-report.yaml"
        report.write_text(content)

        result = runner.invoke(app, ["explain", "--report", str(report)])

        assert result.exit_code == 1
        assert message in result.output


class TestInterviewCommand:
    def test_interview_with_decisions_json(self, tmp_path: Path):
        output = tmp_path / "output"
        decisions = json.dumps(
            {
                "network_account": "Network",
                "identity_center_permission_sets": "ReadOnlyAccess",
                "identity_center_assignments": "PlatformAdmins:ReadOnlyAccess:Management",
            }
        )
        result = runner.invoke(
            app, ["interview", "--output", str(output), "--decisions", decisions]
        )
        assert result.exit_code == 0, result.output
        assert "Compilation successful" in result.stdout
        assert (output / "accounts-config.yaml").exists()
        assert (output / "llm-trace-summary.yaml").exists()
        assert (output / "model-benchmark.yaml").exists()
        report = (output / "decision-report.yaml").read_text()
        assert "handoffReadiness:" in report
        assert "handoffAllowed: true" in report
        assert "while status is blocked" not in report
        assert "Pass only reviewed artifacts" in report
        benchmark = (output / "model-benchmark.yaml").read_text()
        assert "mode: deterministic" in benchmark
        audit = (output / "decision-audit.yaml").read_text()
        assert "key: baseline" in audit
        assert "how: defaulted" in audit

    def test_interview_defaults_only_fails_closed(self, tmp_path: Path):
        output = tmp_path / "output"
        result = runner.invoke(app, ["interview", "--output", str(output), "--no-defaults"])
        assert result.exit_code == 1
        assert "'LZA Baseline' is required" in result.output

    def test_interview_prints_sample_match_for_aws_lza(self, tmp_path: Path):
        output = tmp_path / "output"
        decisions = json.dumps(
            {
                "network_account": "Network",
                "identity_center_permission_sets": "ReadOnlyAccess",
                "identity_center_assignments": "PlatformAdmins:ReadOnlyAccess:Management",
            }
        )
        result = runner.invoke(
            app, ["interview", "--output", str(output), "--decisions", decisions]
        )

        assert result.exit_code == 0
        assert "=== Sample Match ===" in result.stdout
        assert "aws-lza-standard-v1" in result.stdout
        assert "iac-llm-wrapper sample show --name aws-lza-standard-v1" in result.stdout
