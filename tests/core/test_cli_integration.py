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
        assert "--no-raw-evidence" in result.output
        assert "review html" in result.output
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

    def test_discover_with_decisions_shows_simulated_values(self):
        result = runner.invoke(
            app,
            [
                "discover",
                "--input",
                "fixtures/usability/architect-incomplete-lza.md",
                "--pattern",
                "aws-lza",
                "--no-llm",
                "--decisions",
                (
                    '{"network_account":"Network",'
                    '"identity_center_permission_sets":"ReadOnlyAccess",'
                    '"identity_center_assignments":"PlatformAdmins:ReadOnlyAccess:Management"}'
                ),
            ],
        )

        assert result.exit_code == 0, result.output
        assert "values from design doc and simulated decisions" in result.output
        assert "Applied 3 simulated decision(s)" in result.output
        assert "network_account = Network" in result.output
        assert "No gaps found" in result.output

    def test_discover_cloudformation_missing_packet_reports_gaps_without_traceback(self):
        result = runner.invoke(
            app,
            [
                "discover",
                "--input",
                "fixtures/eval/cloudformation-parameters-missing-blocked.md",
                "--pattern",
                "cloudformation-parameters",
                "--no-llm",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Traceback" not in result.output
        assert "Template URL" in result.output
        assert "Parameter Overrides" in result.output
        assert "--no-raw-evidence" in result.output
        assert "review html" in result.output


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

    def test_compile_incremental_from_baseline_bundle(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("INTENT_ENGINE_DISABLE_LLM", "1")
        before_dir = tmp_path / "before"
        after_dir = tmp_path / "after"
        baseline_doc = tmp_path / "before.md"
        changed_doc = tmp_path / "after.md"
        source = Path("fixtures/eval/aws-lza-standard-handoff.md").read_text()
        baseline_doc.write_text(source)
        changed_doc.write_text(
            source.replace(
                "- workload_accounts: AppProd",
                "- workload_accounts: AppProd, DataProd",
            )
        )

        baseline = runner.invoke(
            app,
            [
                "compile",
                "--input",
                str(baseline_doc),
                "--output",
                str(before_dir),
                "--no-raw-evidence",
            ],
        )
        assert baseline.exit_code == 0, baseline.output

        result = runner.invoke(
            app,
            [
                "compile",
                "--baseline-bundle",
                str(before_dir),
                "--baseline-doc",
                str(baseline_doc),
                "--changed-doc",
                str(changed_doc),
                "--output",
                str(after_dir),
                "--no-raw-evidence",
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Incremental Compile Summary" in result.output
        assert "Changed decisions: 1" in result.output
        assert (after_dir / "input-diff-report.yaml").exists()
        assert (after_dir / "incremental-compile-report.yaml").exists()
        incremental_report = (after_dir / "incremental-compile-report.yaml").read_text()
        assert "workload_accounts" in incremental_report
        assert "validationBoundary" in incremental_report

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
        assert "template --pattern aws-lza" in result.output
        assert "template --pattern <pattern>" not in result.output
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

    def test_review_compare_generated_bundles(self, tmp_path: Path, monkeypatch):
        monkeypatch.setenv("INTENT_ENGINE_DISABLE_LLM", "1")
        before_dir = tmp_path / "before"
        after_dir = tmp_path / "after"
        after_doc = tmp_path / "after.md"
        source = Path("fixtures/eval/aws-lza-standard-handoff.md").read_text()
        after_doc.write_text(
            source.replace(
                "- workload_accounts: AppProd",
                "- workload_accounts: AppProd, DataProd",
            )
        )

        before_compile = runner.invoke(
            app,
            [
                "compile",
                "--input",
                "fixtures/eval/aws-lza-standard-handoff.md",
                "--output",
                str(before_dir),
                "--no-raw-evidence",
            ],
        )
        assert before_compile.exit_code == 0, before_compile.output
        after_compile = runner.invoke(
            app,
            [
                "compile",
                "--input",
                str(after_doc),
                "--output",
                str(after_dir),
                "--no-raw-evidence",
            ],
        )
        assert after_compile.exit_code == 0, after_compile.output

        report = tmp_path / "handoff-comparison.yaml"
        html = tmp_path / "handoff-comparison.html"
        result = runner.invoke(
            app,
            [
                "review",
                "compare",
                "--before",
                str(before_dir),
                "--after",
                str(after_dir),
                "--output",
                str(report),
                "--html-output",
                str(html),
            ],
        )

        assert result.exit_code == 0, result.output
        assert "Handoff Bundle Comparison" in result.output
        assert "workload_accounts" in result.output
        assert "artifact file delta" in result.output
        assert report.exists()
        report_text = report.read_text()
        assert "schemaVersion: intent-engine/handoff-comparison/v1" in report_text
        assert "workload_accounts" in report_text
        assert html.exists()
        assert "handoff comparison" in html.read_text()

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
