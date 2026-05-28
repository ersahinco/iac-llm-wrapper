"""CLI integration tests using Typer test runner."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from intent_engine.cli import app

FIXTURES = Path(__file__).parent.parent.parent / "fixtures"
runner = CliRunner()


class TestCompileCommand:
    def test_compile_valid_payments(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("INTENT_ENGINE_DISABLE_LLM", "1")
        output = tmp_path / "output"
        result = runner.invoke(
            app,
            [
                "compile",
                "--input",
                str(FIXTURES / "valid-payments.md"),
                "--output",
                str(output),
                "--pattern",
                "baseline",
            ],
        )
        assert result.exit_code == 0
        assert "Compilation successful" in result.stdout
        assert (output / "organization-config.yaml").exists()

    def test_compile_invalid_design_fails(self, tmp_path: Path):
        output = tmp_path / "output"
        # Use interview with decisions to trigger hub-spoke without network account
        result = runner.invoke(
            app,
            [
                "interview",
                "--output",
                str(output),
                "--decisions",
                '{"topology": "hub-spoke", "cicd_mode": "private"}',
                "--pattern",
                "baseline",
                "--no-defaults",
            ],
        )
        assert result.exit_code == 1
        assert "HUB_SPOKE_NETWORK_ACCOUNT_REQUIRED" in result.output

    def test_compile_missing_input_fails(self, tmp_path: Path):
        result = runner.invoke(
            app,
            ["compile", "--input", "/nonexistent/path", "--output", str(tmp_path / "out")],
        )
        assert result.exit_code == 1
        assert "does not exist" in result.output


class TestValidateCommand:
    def test_validate_valid_output(self, tmp_path: Path):
        output = tmp_path / "output"
        output.mkdir()
        # Create valid intent artifacts
        (output / "organization-config.yaml").write_text(
            "organization:\n  primaryRegion: eu-central-1\norganizationalUnits:\n"
        )
        (output / "accounts-config.yaml").write_text("accounts:\n  - name: TestAccount\n")
        (output / "global-config.yaml").write_text(
            "global:\n"
            "  primaryRegion: eu-central-1\n"
            "  cloudtrail:\n"
            "    organizationTrail: true\n"
            "  kms:\n"
            "    rotationRequired: true\n"
        )
        (output / "security-config.yaml").write_text(
            "security:\n  s3:\n    blockPublicAccess: true\n  audit:\n    retentionDays: 2555\n"
        )
        (output / "network-config.yaml").write_text("network:\n  topology: single-vpc\n")
        (output / "iam-config.yaml").write_text("permissionBoundary: enabled\n")
        (output / "customizations-config.yaml").write_text("customizations:\n")
        (output / "decision-report.yaml").write_text("primaryRegion: eu-central-1\n")
        (output / "deployment-graph.yaml").write_text("phases:\n")
        (output / "sample-recommendations.yaml").write_text("recommendations: []\n")
        result = runner.invoke(app, ["validate", "--input", str(output), "--pattern", "baseline"])
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
        assert "Required artifacts: 6" in result.stdout

    def test_contract_show_by_pattern(self):
        result = runner.invoke(app, ["contract", "show", "--pattern", "aws-lza"])

        assert result.exit_code == 0
        assert "accounts-config.yaml" in result.stdout
        assert "network-config.yaml | paths: homeRegion" in result.stdout
        assert "assertions: defaultVpc.delete" in result.stdout
        assert "customizations-config.yaml" in result.stdout
        assert "home_region" in result.stdout
        assert "network_cidr -> network-config.yaml:vpcs[].cidrs[]" in result.stdout

    def test_contract_show_kubernetes_pattern(self):
        result = runner.invoke(app, ["contract", "show", "--pattern", "kubernetes-cluster"])

        assert result.exit_code == 0
        assert "kubernetes-cluster-config" in result.stdout
        assert "cluster-config.yaml | paths: cluster.name, cluster.version" in result.stdout
        assert "cluster_name -> cluster-config.yaml:cluster.name" in result.stdout

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

    def test_sample_list_empty_filter_fails(self):
        result = runner.invoke(app, ["sample", "list", "--tag", "does-not-exist"])

        assert result.exit_code == 1
        assert "No sample configs matched current filters." in result.output


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
                '{"topology": "hub-spoke", "primary_region": "eu-central-1", '
                '"network_cidr": "10.0.0.0/16", "central_network_account": "Network", '
                '"hub_cidr": "10.0.0.0/20"}',
                "--pattern",
                "baseline",
            ],
        )
        report = output / "decision-report.yaml"
        result = runner.invoke(app, ["explain", "--report", str(report)])
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
                "primary_region": "eu-central-1",
                "topology": "single-vpc",
            }
        )
        result = runner.invoke(
            app,
            ["interview", "--output", str(output), "--decisions", decisions],
        )
        assert result.exit_code == 0
        assert "Compilation successful" in result.stdout
        assert (output / "organization-config.yaml").exists()

    def test_interview_defaults_only(self, tmp_path: Path):
        output = tmp_path / "output"
        result = runner.invoke(
            app,
            ["interview", "--output", str(output), "--pattern", "baseline"],
        )
        assert result.exit_code == 0
        assert "Compilation successful" in result.stdout

        report_path = output / "decision-report.yaml"
        assert report_path.exists()
        import ruamel.yaml

        yaml = ruamel.yaml.YAML(typ="safe")
        with open(report_path) as f:
            report = yaml.load(f)
        assert report["primaryRegion"] == "eu-central-1"

    def test_interview_prints_sample_match_for_aws_lza(self, tmp_path: Path):
        output = tmp_path / "output"
        decisions = json.dumps({"network_account": "Network"})
        result = runner.invoke(
            app,
            [
                "interview",
                "--output",
                str(output),
                "--decisions",
                decisions,
            ],
        )

        assert result.exit_code == 0
        assert "=== Sample Match ===" in result.stdout
        assert "aws-lza-standard-v1" in result.stdout
        assert "intent-engine sample show --name aws-lza-standard-v1" in result.stdout

    def test_interview_missing_required_fails(self, tmp_path: Path):
        output = tmp_path / "output"
        decisions = json.dumps(
            {
                "topology": "hub-spoke",
            }
        )
        result = runner.invoke(
            app,
            [
                "interview",
                "--output",
                str(output),
                "--decisions",
                decisions,
                "--pattern",
                "baseline",
                "--no-defaults",
            ],
        )
        assert result.exit_code == 1
        assert "HUB_SPOKE_NETWORK_ACCOUNT_REQUIRED" in result.output
