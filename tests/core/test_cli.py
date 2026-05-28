"""CLI tests using Typer test runner."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from intent_engine.cli import app

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
runner = CliRunner()


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

    def test_compile_missing_input_fails(self, tmp_path: Path):
        result = runner.invoke(
            app,
            ["compile", "--input", "/nonexistent/path", "--output", str(tmp_path / "out")],
        )
        assert result.exit_code == 1
        assert "does not exist" in result.output


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
