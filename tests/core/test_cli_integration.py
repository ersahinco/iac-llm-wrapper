"""CLI integration tests for current product paths."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from intent_engine.cli import app

runner = CliRunner()


class TestCLIDiscover:
    def test_discover_aws_lza_gaps(self):
        result = runner.invoke(
            app,
            [
                "discover",
                "--input",
                "fixtures/usability/architect-incomplete-lza.md",
                "--no-llm",
                "--suggest",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Next Steps" in result.output
        assert "Re-run discovery until no gaps remain" in result.output
        assert "network_account" in result.output
        assert "Clarifying questions" in result.output

    def test_discover_with_path(self):
        result = runner.invoke(
            app,
            [
                "discover",
                "--input",
                "fixtures/usability/engineer-handoff-lza.md",
                "--no-llm",
                "--path",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Next Steps" in result.output
        assert "--no-raw-evidence" in result.output
        assert "network_account" in result.output


class TestCLICompile:
    def test_compile_default_aws_lza(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("INTENT_ENGINE_DISABLE_LLM", "1")
        output_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "compile",
                "--input",
                "fixtures/usability/engineer-handoff-lza.md",
                "--output",
                str(output_dir),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Next steps:" in result.output
        assert "review html" in result.output
        assert "handoff-plan.yaml" in result.output
        assert (output_dir / "decision-report.yaml").exists()
        assert (output_dir / "lineage-manifest.yaml").exists()
        assert not (output_dir / "terraform.tfvars").exists()

    def test_compile_dry_run(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("INTENT_ENGINE_DISABLE_LLM", "1")
        output_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "compile",
                "--input",
                "fixtures/usability/engineer-handoff-lza.md",
                "--output",
                str(output_dir),
                "--dry-run",
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Dry-run" in result.output
        assert not (output_dir / "decision-report.yaml").exists()

    def test_compile_blocked_design_writes_safe_assessment(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("INTENT_ENGINE_DISABLE_LLM", "1")
        output_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "compile",
                "--input",
                "fixtures/eval/aws-lza-enterprise-messy-blocked.md",
                "--output",
                str(output_dir),
            ],
        )
        assert result.exit_code != 0
        assert "handoff is blocked" in result.output
        assert "Generate the blocked review page" in result.output
        assert "Resolve the blocker questions" in result.output
        assert "AWS_LZA_NETWORK_ACCOUNT_REQUIRED" in result.output
        report = (output_dir / "decision-report.yaml").read_text()
        assert "deploymentAllowed: false" in report
        assert "Cannot hand off yet" in report
        trace = (output_dir / "llm-trace-summary.yaml").read_text()
        assert "callCount: 0" in trace
        assert "acceptedDecisions:" in trace
        assert "rawEvidence:" in trace
        assert "extractedDecisions:" not in trace
        assert "rawEvidencePath:" not in trace
        benchmark = (output_dir / "model-benchmark.yaml").read_text()
        assert "mode: deterministic" in benchmark
        assert "deploymentAllowed: false" in benchmark
        assert "blockingGapCount:" in benchmark

    def test_compile_duplicate_structured_decision_blocks(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("INTENT_ENGINE_DISABLE_LLM", "1")
        design = tmp_path / "design.md"
        design.write_text(
            """# AWS LZA Design

## Accounts
- network_account: Network

## Network
- topology: hub-spoke
- network_cidr: 10.0.0.0/16
- network_cidr: 10.1.0.0/16
"""
        )
        output_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "compile",
                "--input",
                str(design),
                "--output",
                str(output_dir),
            ],
        )
        assert result.exit_code != 0
        assert "MARKDOWN_CONTRADICTION_NETWORK_CIDR" in result.output
        report = (output_dir / "decision-report.yaml").read_text()
        assert "MARKDOWN_CONTRADICTION_NETWORK_CIDR" in report


class TestCLIVersion:
    def test_version_flag(self):
        result = runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert "iac-llm-wrapper" in result.output
        assert "0.1.0" in result.output


class TestCLIInterview:
    def test_interview_with_decisions(self, tmp_path: Path):
        output_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "interview",
                "--output",
                str(output_dir),
                "--decisions",
                (
                    '{"network_account": "Network", '
                    '"identity_center_permission_sets": "ReadOnlyAccess", '
                    '"identity_center_assignments": "PlatformAdmins:ReadOnlyAccess:Management"}'
                ),
            ],
        )
        assert result.exit_code == 0, result.output
        assert "Next steps:" in result.output
        assert "review html" in result.output
        assert (output_dir / "accounts-config.yaml").exists()

    def test_interview_missing_required_fails(self, tmp_path: Path):
        output_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "interview",
                "--output",
                str(output_dir),
                "--decisions",
                '{"topology": "hub-spoke"}',
                "--no-defaults",
            ],
        )
        assert result.exit_code != 0
        assert "AWS_LZA_NETWORK_ACCOUNT_REQUIRED" in result.output


class TestCLIValidate:
    def test_validate_generated_artifacts(self, tmp_path: Path):
        output_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "interview",
                "--output",
                str(output_dir),
                "--decisions",
                (
                    '{"network_account": "Network", '
                    '"identity_center_permission_sets": "ReadOnlyAccess", '
                    '"identity_center_assignments": "PlatformAdmins:ReadOnlyAccess:Management"}'
                ),
            ],
        )
        assert result.exit_code == 0, result.output

        result = runner.invoke(app, ["validate", "--input", str(output_dir)])
        assert result.exit_code == 0, result.output

    def test_validate_missing_files(self, tmp_path: Path):
        result = runner.invoke(app, ["validate", "--input", str(tmp_path)])
        assert result.exit_code != 0


class TestCLIReview:
    def test_review_identical_reports(self, tmp_path: Path):
        before = tmp_path / "before.yaml"
        after = tmp_path / "after.yaml"
        data = "homeRegion: eu-central-1\ntopology: hub-spoke\n"
        before.write_text(data)
        after.write_text(data)
        result = runner.invoke(app, ["review", "--before", str(before), "--after", str(after)])
        assert result.exit_code == 0
        assert "No differences found" in result.output

    def test_review_changed_values(self, tmp_path: Path):
        before = tmp_path / "before.yaml"
        after = tmp_path / "after.yaml"
        before.write_text("homeRegion: eu-central-1\n")
        after.write_text("homeRegion: eu-west-1\n")
        result = runner.invoke(app, ["review", "--before", str(before), "--after", str(after)])
        assert result.exit_code == 0
        assert "Changed" in result.output
        assert "eu-central-1" in result.output
        assert "eu-west-1" in result.output

    def test_review_html_from_complex_lza_handoff(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("INTENT_ENGINE_DISABLE_LLM", "1")
        output_dir = tmp_path / "out"
        compile_result = runner.invoke(
            app,
            [
                "compile",
                "--input",
                "fixtures/eval/aws-lza-complex-enterprise-handoff.md",
                "--output",
                str(output_dir),
            ],
        )
        assert compile_result.exit_code == 0, compile_result.output

        review_path = output_dir / "handoff-review.html"
        result = runner.invoke(
            app,
            ["review", "html", "--input", str(output_dir), "--output", str(review_path)],
        )

        assert result.exit_code == 0, result.output
        html = review_path.read_text()
        assert "aws-lza handoff review" in html
        assert "ContosoEnterprise" in html
        assert "Readiness" in html
        assert "Reviewer Next Actions" in html
        assert "Pass only reviewed artifacts" in html
        assert "Accepted Decisions" in html
        assert "Graph Decisions" in html
        assert "Requirement Graph" in html
        assert "requirement-graph.json" in html
        assert "requirement-graph.mmd" in html
        assert (output_dir / "requirement-graph.json").exists()
        assert (output_dir / "requirement-graph.mmd").exists()
        assert (output_dir / "contract-validation.yaml").exists()
        assert "Contract Validation" in html
        assert "aws-lza-sample-configuration" in html
        assert "generic-handoff-plan" in html
        assert "Target Artifacts" in html
        assert "Trace Summary" in html
        assert "llm-trace-summary.yaml" in html
        assert "Model Benchmark" in html
        assert "model-benchmark.yaml" in html

        outside_review = tmp_path / "handoff-review.html"
        outside_result = runner.invoke(
            app,
            ["review", "html", "--input", str(output_dir), "--output", str(outside_review)],
        )
        assert outside_result.exit_code == 0, outside_result.output
        outside_html = outside_review.read_text()
        assert f"{output_dir.name}/requirement-graph.json" in outside_html
        assert f"{output_dir.name}/llm-trace-summary.yaml" in outside_html

    def test_review_html_requires_input_and_output(self):
        result = runner.invoke(app, ["review", "html"])

        assert result.exit_code == 1
        assert "requires --input and --output" in result.output


class TestCLITemplate:
    def test_template_default_pattern_is_aws_lza(self, tmp_path: Path):
        output = tmp_path / "design.md"
        result = runner.invoke(app, ["template", "--output", str(output)])
        assert result.exit_code == 0, result.output
        assert "aws-lza pattern" in output.read_text()

    def test_template_terraform_vpc(self, tmp_path: Path):
        output = tmp_path / "design.md"
        result = runner.invoke(
            app,
            ["template", "--pattern", "terraform-vpc", "--output", str(output)],
        )
        assert result.exit_code == 0, result.output
        assert "## VPC Module" in output.read_text()

    def test_template_unknown_pattern(self, tmp_path: Path):
        output = tmp_path / "design.md"
        result = runner.invoke(
            app,
            ["template", "--pattern", "nonexistent", "--output", str(output)],
        )
        assert result.exit_code != 0
        assert "Unknown pattern" in result.output
